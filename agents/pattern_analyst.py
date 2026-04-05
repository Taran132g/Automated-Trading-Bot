"""
Pattern Analyst Agent

Two roles:
  1. evaluate_signal() — intraday Claude filter called by PatternTrader before each entry.
     Returns {"approved": bool, "reason": str}.
     Falls back to approved=True if Claude is unavailable, so trading continues normally.
     All decisions are logged to the pattern_claude_log DB table.

  2. run() — post-market agent for pattern-specific trade analysis.
     Run at 4:30 PM ET on weekdays (after post_market runs at 4:15).
     Reads pattern_trades (live) and pattern_trades_paper, calls Claude for analysis,
     sends Telegram report, saves to agent_reports.
"""

import logging
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytz

from agents.base import get_db, save_report, send_telegram, get_previous_reports, call_claude

LOGGER = logging.getLogger("agents.pattern_analyst")
ET = pytz.timezone("America/New_York")

DB_PATH = Path(__file__).parent.parent / "penny_basing.db"


# ── Claude log table ────────────────────────────────────────────────────────

def _ensure_filter_log_table() -> None:
    with closing(sqlite3.connect(str(DB_PATH))) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pattern_claude_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   REAL,
                symbol      TEXT,
                pattern     TEXT,
                direction   TEXT,
                confidence  REAL,
                rr_ratio    REAL,
                approved    INTEGER,
                reason      TEXT,
                mode        TEXT
            )
        """)
        conn.commit()


def _log_decision(
    symbol: str, pattern: str, direction: str, confidence: float,
    rr_ratio: float, approved: bool, reason: str, mode: str,
) -> None:
    try:
        _ensure_filter_log_table()
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            conn.execute(
                "INSERT INTO pattern_claude_log "
                "(timestamp, symbol, pattern, direction, confidence, rr_ratio, approved, reason, mode) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (time.time(), symbol, pattern, direction, confidence, rr_ratio,
                 int(approved), reason, mode),
            )
            conn.commit()
    except Exception as exc:
        LOGGER.warning("[pattern_analyst] Failed to log decision: %s", exc)


# ── Intraday signal filter ──────────────────────────────────────────────────

def _build_market_context(df) -> str:
    """
    Compute trend indicators and format the full price history for the prompt.

    Sections returned:
      - EMA20 / EMA50 trend assessment
      - ATR(14)
      - Full 400-bar range (high/low)
      - All closes oldest→newest (one compact line)
      - Last 50 bars full OHLC (oldest→newest)
    """
    import numpy as np

    closes = df["close"].values.astype(float)
    highs  = df["high"].values.astype(float)
    lows   = df["low"].values.astype(float)
    n      = len(closes)

    # ── EMAs ──────────────────────────────────────────────────────────────────
    def _ema(arr, period):
        k   = 2.0 / (period + 1)
        out = np.empty(len(arr))
        out[0] = arr[0]
        for i in range(1, len(arr)):
            out[i] = arr[i] * k + out[i - 1] * (1 - k)
        return out

    ema20 = _ema(closes, 20)[-1] if n >= 20 else None
    ema50 = _ema(closes, 50)[-1] if n >= 50 else None
    price = closes[-1]

    if ema20 and ema50:
        if price > ema20 > ema50:
            trend = "UPTREND"
        elif price < ema20 < ema50:
            trend = "DOWNTREND"
        elif price > ema50:
            trend = "MIXED (above EMA50, choppy near EMA20)"
        else:
            trend = "MIXED (below EMA50, choppy)"
        ema_line = (
            f"Trend: {trend}  |  EMA20=${ema20:.4f}  EMA50=${ema50:.4f}  "
            f"Price ${price:.4f} ({(price/ema20-1)*100:+.2f}% vs EMA20, "
            f"{(price/ema50-1)*100:+.2f}% vs EMA50)"
        )
    else:
        ema_line = f"Trend: insufficient bars for EMAs  |  Price=${price:.4f}"

    # ── ATR(14) ───────────────────────────────────────────────────────────────
    atr_str = "N/A"
    if n >= 15:
        prev_c = df["close"].shift(1).values.astype(float)
        tr = np.maximum.reduce([
            highs - lows,
            np.abs(highs - prev_c),
            np.abs(lows  - prev_c),
        ])
        atr_val = float(np.mean(tr[-14:]))
        atr_str = f"${atr_val:.4f} ({atr_val/price*100:.2f}% of price)"

    # ── 400-bar range ─────────────────────────────────────────────────────────
    rng_high = float(highs.max())
    rng_low  = float(lows.min())
    rng_pct  = (rng_high - rng_low) / rng_low * 100 if rng_low > 0 else 0.0
    rng_mid  = (rng_high + rng_low) / 2
    price_in_range = (price - rng_low) / (rng_high - rng_low) * 100 if (rng_high - rng_low) > 0 else 50.0

    # ── All closes (compact) ──────────────────────────────────────────────────
    all_closes = ",".join(f"{c:.2f}" for c in closes)

    # ── Last 50 bars full OHLC ────────────────────────────────────────────────
    last50 = df.tail(50)
    ohlc_lines = "  ".join(
        f"{r['open']:.2f}/{r['high']:.2f}/{r['low']:.2f}/{r['close']:.2f}"
        for _, r in last50.iterrows()
    )

    return (
        f"{ema_line}\n"
        f"ATR(14): {atr_str}\n"
        f"{n}-bar range: Low=${rng_low:.4f}  High=${rng_high:.4f}  "
        f"Range={rng_pct:.1f}%  Mid=${rng_mid:.4f}  "
        f"Price is at {price_in_range:.0f}% of the range\n\n"
        f"ALL {n} CLOSES (oldest→newest):\n{all_closes}\n\n"
        f"LAST 50 BARS OHLC (oldest→newest, open/high/low/close):\n{ohlc_lines}"
    )


def _build_signal_prompt(
    symbol: str,
    pattern: str,
    direction: str,
    confidence: float,
    entry_price: float,
    stop_level: float,
    target_level: float,
    rr_ratio: float,
    pattern_bars: int,
    market_context: str,
    intraday_pnl: float,
) -> str:
    dir_label = "LONG" if direction == "bullish" else "SHORT"
    return (
        "You are a breakout pattern filter. Evaluate this setup using the full price context below.\n\n"
        f"SYMBOL: {symbol}  |  DIRECTION: {dir_label}\n"
        f"PATTERN: {pattern}  |  CONFIDENCE: {confidence:.0%}  |  BARS FORMED: {pattern_bars}\n"
        f"ENTRY: ${entry_price:.4f}  |  STOP: ${stop_level:.4f}  |  TARGET: ${target_level:.4f}\n"
        f"R:R RATIO: {rr_ratio:.2f}  (reward / risk)\n"
        f"INTRADAY P&L SO FAR: ${intraday_pnl:+.2f}\n\n"
        f"MARKET CONTEXT:\n{market_context}\n\n"
        "Respond with exactly two lines:\n"
        "Line 1: YES or NO\n"
        "Line 2: One sentence reason (max 25 words). Reference trend direction and R:R. Be direct.\n\n"
        "Approve (YES) ONLY if ALL of these hold: R:R >= 2.0, trend clearly aligns with trade "
        "direction (price on correct side of EMA20 and EMA50), pattern formed over enough bars "
        "to be credible, price is not already within 20% of the target.\n"
        "Reject (NO) if ANY of: R:R < 1.5, trend opposes direction, price at a range extreme "
        "with no room left to run, stop is wider than 1.5x ATR, or the closes show erratic "
        "choppy action with no clear directional structure. Be strict — only the cleanest setups."
    )


def evaluate_signal(
    symbol: str,
    pattern: str,
    direction: str,
    confidence: float,
    entry_price: float,
    stop_level: float,
    target_level: float,
    pattern_bars: int,
    recent_df,          # pd.DataFrame with up to 400 bars (open/high/low/close)
    intraday_pnl: float = 0.0,
    mode: str = "paper",
) -> dict:
    """
    Ask Claude whether a detected pattern signal is worth trading.

    Passes the full bar history (up to 400 bars) so Claude can assess market direction,
    trend strength, and whether the setup is aligned with the broader tape.

    Returns {"approved": bool, "reason": str}.
    If Claude is unavailable or errors, returns approved=True (fail-safe — don't block trading).
    """
    risk   = abs(entry_price - stop_level)
    reward = abs(target_level - entry_price)
    rr     = round(reward / risk, 2) if risk > 0 else 0.0

    market_context = "N/A"
    if recent_df is not None and not recent_df.empty:
        try:
            market_context = _build_market_context(recent_df)
        except Exception as exc:
            LOGGER.warning("[pattern_analyst] market context error: %s", exc)
            # Fallback: just the last 20 bars
            last20 = recent_df.tail(20)
            market_context = "LAST 20 BARS (O/H/L/C):\n" + "  ".join(
                f"{r['open']:.2f}/{r['high']:.2f}/{r['low']:.2f}/{r['close']:.2f}"
                for _, r in last20.iterrows()
            )

    prompt = _build_signal_prompt(
        symbol=symbol, pattern=pattern, direction=direction,
        confidence=confidence, entry_price=entry_price,
        stop_level=stop_level, target_level=target_level,
        rr_ratio=rr, pattern_bars=pattern_bars,
        market_context=market_context, intraday_pnl=intraday_pnl,
    )

    response = call_claude(prompt, max_tokens=120)
    if not response:
        LOGGER.warning("[pattern_analyst] Claude unavailable — approving %s %s by default.", symbol, pattern)
        _log_decision(symbol, pattern, direction, confidence, rr, True, "claude_unavailable", mode)
        return {"approved": True, "reason": "claude_unavailable"}

    lines = [ln.strip() for ln in response.strip().splitlines() if ln.strip()]
    approved = lines[0].upper().startswith("YES") if lines else True
    reason   = lines[1] if len(lines) > 1 else response[:120].strip()

    LOGGER.info(
        "[pattern_analyst] %s %s %s → %s  R:R=%.2f  %s",
        symbol, pattern, direction.upper(),
        "APPROVED" if approved else "REJECTED", rr, reason,
    )
    _log_decision(symbol, pattern, direction, confidence, rr, approved, reason, mode)
    return {"approved": approved, "reason": reason}


# ── Post-market pattern report ───────────────────────────────────────────────

def _today_range_unix() -> tuple:
    now_et = datetime.now(ET)
    start  = now_et.replace(hour=0, minute=0, second=0, microsecond=0)
    end    = now_et.replace(hour=23, minute=59, second=59, microsecond=0)
    return start.timestamp(), end.timestamp()


def _load_pattern_trades(table: str, start_ts: float, end_ts: float) -> pd.DataFrame:
    try:
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            conn.row_factory = sqlite3.Row
            return pd.read_sql_query(
                f"SELECT * FROM {table} WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp ASC",
                conn, params=(start_ts, end_ts),
            )
    except Exception:
        return pd.DataFrame()


def _load_claude_log(start_ts: float, end_ts: float) -> pd.DataFrame:
    try:
        _ensure_filter_log_table()
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            return pd.read_sql_query(
                "SELECT * FROM pattern_claude_log WHERE timestamp >= ? AND timestamp <= ?",
                conn, params=(start_ts, end_ts),
            )
    except Exception:
        return pd.DataFrame()


def _calc_trade_stats(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    exits = df[df["side"].isin(["SELL", "COVER"])]
    total_pnl = float(df["pnl"].fillna(0).sum())
    win_exits = exits[exits["pnl"] > 0] if not exits.empty else pd.DataFrame()
    win_rate  = round(len(win_exits) / len(exits) * 100, 1) if len(exits) > 0 else None
    by_pattern = {}
    for pat, grp in df.groupby("pattern"):
        pat_exits = grp[grp["side"].isin(["SELL", "COVER"])]
        pat_pnl   = float(grp["pnl"].fillna(0).sum())
        pat_wins  = len(pat_exits[pat_exits["pnl"] > 0]) if not pat_exits.empty else 0
        by_pattern[pat] = {
            "trades":    len(grp),
            "exits":     len(pat_exits),
            "total_pnl": round(pat_pnl, 4),
            "win_rate":  round(pat_wins / len(pat_exits) * 100, 1) if len(pat_exits) > 0 else None,
        }
    by_exit = {}
    exit_rows = df[df["exit_reason"].notna() & (df["exit_reason"] != "entry")]
    for reason, grp in exit_rows.groupby("exit_reason"):
        by_exit[reason] = {
            "count":     len(grp),
            "total_pnl": round(float(grp["pnl"].fillna(0).sum()), 4),
        }
    return {
        "total_rows": len(df),
        "total_exits": len(exits),
        "total_pnl": round(total_pnl, 4),
        "win_rate": win_rate,
        "by_pattern": by_pattern,
        "by_exit_reason": by_exit,
    }


def collect_stats() -> dict:
    start_ts, end_ts = _today_range_unix()

    live_df    = _load_pattern_trades("pattern_trades",       start_ts, end_ts)
    paper_df   = _load_pattern_trades("pattern_trades_paper", start_ts, end_ts)
    claude_log = _load_claude_log(start_ts, end_ts)

    claude_stats: dict = {}
    if not claude_log.empty:
        approved = claude_log[claude_log["approved"] == 1]
        rejected = claude_log[claude_log["approved"] == 0]
        claude_stats = {
            "total_evaluated": len(claude_log),
            "approved":        len(approved),
            "rejected":        len(rejected),
            "avg_rr_approved": round(float(approved["rr_ratio"].mean()), 2) if len(approved) > 0 else None,
            "avg_rr_rejected": round(float(rejected["rr_ratio"].mean()), 2) if len(rejected) > 0 else None,
        }

    return {
        "live":   _calc_trade_stats(live_df),
        "paper":  _calc_trade_stats(paper_df),
        "claude": claude_stats,
    }


def format_report(stats: dict) -> str:
    date_str = datetime.now(ET).strftime("%b %d, %Y")
    lines = [f"📈 *Pattern Strategy Report — {date_str}*\n"]

    for mode in ("live", "paper"):
        s = stats.get(mode, {})
        if not s:
            lines.append(f"*{mode.capitalize()}:* No trades today.")
            continue
        pnl     = s.get("total_pnl", 0)
        wr      = s.get("win_rate")
        exits   = s.get("total_exits", 0)
        emoji   = "🟢" if pnl >= 0 else "🔴"
        wr_str  = f"{wr}%" if wr is not None else "N/A"
        lines.append(f"{emoji} *{mode.capitalize()}:* `{exits}` exits | `{wr_str}` WR | `${pnl:+.4f}` P&L")

        by_pat = s.get("by_pattern", {})
        if by_pat:
            lines.append(f"  _By pattern:_")
            for pat, ps in sorted(by_pat.items(), key=lambda x: x[1]["total_pnl"], reverse=True):
                wr_p = f"{ps['win_rate']}%" if ps["win_rate"] is not None else "N/A"
                e    = "🟢" if ps["total_pnl"] >= 0 else "🔴"
                lines.append(f"  {e} `{pat}` — {ps['exits']} exits, {wr_p} WR, ${ps['total_pnl']:+.4f}")

        by_exit = s.get("by_exit_reason", {})
        if by_exit:
            lines.append(f"  _By exit:_")
            for reason, rs in sorted(by_exit.items(), key=lambda x: x[1]["total_pnl"], reverse=True):
                e = "🟢" if rs["total_pnl"] >= 0 else "🔴"
                lines.append(f"  {e} `{reason}` ×{rs['count']} → ${rs['total_pnl']:+.4f}")

    # Claude filter summary
    cs = stats.get("claude", {})
    if cs:
        approved = cs.get("approved", 0)
        rejected = cs.get("rejected", 0)
        rr_a     = cs.get("avg_rr_approved")
        rr_r     = cs.get("avg_rr_rejected")
        lines.append(
            f"\n🤖 *Claude Filter:* `{approved}` approved / `{rejected}` rejected"
            + (f" | Avg R:R approved `{rr_a}` / rejected `{rr_r}`" if rr_a else "")
        )

    return "\n".join(lines)


def _build_claude_prompt(stats: dict, previous: list) -> str:
    date_str = datetime.now(ET).strftime("%Y-%m-%d")
    live  = stats.get("live", {})
    paper = stats.get("paper", {})
    cs    = stats.get("claude", {})

    def _s(s: dict) -> str:
        if not s:
            return "no trades"
        return (
            f"exits={s.get('total_exits', 0)} "
            f"WR={s.get('win_rate', 'N/A')}% "
            f"PnL=${s.get('total_pnl', 0):+.4f} "
            f"patterns={list(s.get('by_pattern', {}).keys())} "
            f"exits_by_reason={s.get('by_exit_reason', {})}"
        )

    today = (
        f"Date: {date_str}\n"
        f"LIVE: {_s(live)}\n"
        f"PAPER: {_s(paper)}\n"
        f"CLAUDE FILTER: evaluated={cs.get('total_evaluated', 0)} "
        f"approved={cs.get('approved', 0)} rejected={cs.get('rejected', 0)} "
        f"avg_rr_approved={cs.get('avg_rr_approved')} avg_rr_rejected={cs.get('avg_rr_rejected')}"
    )

    hist_lines = []
    for r in previous:
        dt = datetime.fromtimestamp(r["timestamp"], tz=ET).strftime("%Y-%m-%d")
        d  = r["report_data"]
        lv = d.get("live", {})
        hist_lines.append(
            f"{dt}: live exits={lv.get('total_exits', 0)} WR={lv.get('win_rate', 'N/A')}% "
            f"PnL=${lv.get('total_pnl', 0):+.4f}"
        )
    hist = "\n".join(hist_lines) if hist_lines else "No prior history."

    return (
        "You are a pattern trading analyst. Today's results and recent history are below.\n\n"
        f"TODAY:\n{today}\n\n"
        f"RECENT HISTORY (newest first):\n{hist}\n\n"
        "In 3-4 sentences: compare today's pattern results to recent days, "
        "call out the best or worst performing pattern or exit reason, "
        "and give one specific tuning recommendation. "
        "If the Claude filter rejected setups, note whether the R:R on rejected vs approved differed meaningfully. "
        "Be direct and data-driven. Plain text only."
    )


def run() -> None:
    LOGGER.info("Pattern analyst starting.")
    previous = get_previous_reports("pattern_analyst", limit=5)
    stats    = collect_stats()
    report   = format_report(stats)

    analysis = call_claude(_build_claude_prompt(stats, previous), max_tokens=300)
    if analysis:
        report += f"\n\n🤖 *AI Analysis:*\n{analysis}"

    save_report("pattern_analyst", report, stats)
    send_telegram(report)
    LOGGER.info("Pattern analyst report sent and saved.")
