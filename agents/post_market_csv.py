"""
Post-Market CSV Analyst
Parses Schwab trade activity HTML/CSV exports, builds accurate round-trip PnL
via FIFO matching, annotates each trip with pattern_bucket from DB opener rows,
then produces full symbol × bucket breakdowns.
"""

import logging
import re
from collections import defaultdict, deque
from contextlib import closing
from datetime import datetime

import pandas as pd
import pytz

from agents.base import get_db, save_report, send_telegram, get_previous_reports, call_claude

LOGGER = logging.getLogger("agents.post_market_csv")
ET = pytz.timezone("America/New_York")

BUCKET_ORDER = ["aligned", "countertrend", "neutral"]
BUCKET_EMOJI = {"aligned": "✅", "countertrend": "❌", "neutral": "⚪"}
MATCH_WINDOW_SECS = 600   # how far (±) to search for a DB opener match (10 min)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def extract_date_from_filename(filename: str) -> str | None:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    return m.group(1) if m else None


def parse_schwab_html(content: str) -> pd.DataFrame:
    rows = []
    in_filled = False

    for line in content.splitlines():
        line = line.strip()
        if "Filled Orders" in line:
            in_filled = True
            continue
        if in_filled and "Canceled Orders" in line:
            break
        if not in_filled or not line.startswith(",,"):
            continue
        if "Exec Time" in line:
            continue

        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 12:
            continue
        try:
            time_str   = parts[2]
            side       = parts[4]
            qty        = int(parts[5].lstrip("+-"))
            pos_effect = parts[6]
            symbol     = parts[7]
            price      = float(parts[11])
        except (ValueError, IndexError):
            continue

        if side not in ("BUY", "SELL") or pos_effect not in ("TO OPEN", "TO CLOSE") or not symbol:
            continue

        rows.append({"time_str": time_str, "side": side, "qty": qty,
                     "pos_effect": pos_effect, "symbol": symbol, "price": price})

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["time_str"], format="%m/%d/%y %H:%M:%S", errors="coerce")
    return df.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)


def aggregate_fills(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    records = []
    for (ts, side, pe, sym), grp in df.groupby(["ts", "side", "pos_effect", "symbol"], sort=False):
        total_qty = int(grp["qty"].sum())
        avg_price = float((grp["price"] * grp["qty"]).sum()) / total_qty
        records.append({"ts": ts, "side": side, "pos_effect": pe,
                        "symbol": sym, "qty": total_qty, "price": avg_price})
    return pd.DataFrame(records).sort_values("ts").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Round-trip matching
# ---------------------------------------------------------------------------

def build_round_trips(fills_df: pd.DataFrame):
    open_positions: dict[str, deque] = defaultdict(deque)
    trips, overnight_closes = [], []

    for _, row in fills_df.iterrows():
        sym, side, qty = row["symbol"], row["side"], int(row["qty"])
        price, ts, pe  = float(row["price"]), row["ts"], row["pos_effect"]

        if pe == "TO OPEN":
            direction = "LONG" if side == "BUY" else "SHORT"
            open_positions[sym].append({"dir": direction, "qty": qty, "price": price, "ts": ts})

        elif pe == "TO CLOSE":
            remaining = qty
            while remaining > 0:
                if not open_positions[sym]:
                    overnight_closes.append({"symbol": sym, "side": side,
                                             "qty": remaining, "price": price, "ts": str(ts)})
                    remaining = 0
                    break

                pos = open_positions[sym][0]
                fill_qty = min(remaining, pos["qty"])
                pnl = ((price - pos["price"]) if pos["dir"] == "LONG"
                       else (pos["price"] - price)) * fill_qty

                trips.append({
                    "symbol":        sym,
                    "dir":           pos["dir"],
                    "qty":           fill_qty,
                    "entry_price":   round(pos["price"], 6),
                    "exit_price":    round(price, 6),
                    "entry_ts":      pos["ts"],          # kept as Timestamp for matching
                    "exit_ts":       str(ts),
                    "pnl":           round(pnl, 6),
                    "pnl_per_share": round(pnl / fill_qty, 6) if fill_qty else 0.0,
                    "win":           pnl > 0,
                    "pattern_bucket": "neutral",          # filled in by annotate_trips_with_buckets
                })

                pos["qty"] -= fill_qty
                if pos["qty"] == 0:
                    open_positions[sym].popleft()
                remaining -= fill_qty

    open_at_eod = [
        {"symbol": sym, **pos, "ts": str(pos["ts"])}
        for sym, q in open_positions.items()
        for pos in q if pos["qty"] > 0
    ]
    return trips, overnight_closes, open_at_eod


# ---------------------------------------------------------------------------
# DB lookups
# ---------------------------------------------------------------------------

def _day_range(date_str: str) -> tuple[float, float]:
    dt_et = ET.localize(datetime.strptime(date_str, "%Y-%m-%d"))
    start = dt_et.timestamp()
    return start, start + 86400


def annotate_trips_with_buckets(trips: list, date_str: str) -> list:
    """
    For each round trip, find the closest opener row in DB (same symbol,
    entry_ts within ±MATCH_WINDOW_SECS) and copy its pattern_bucket.
    Unmatched trips stay "neutral".
    """
    try:
        start_ts, end_ts = _day_range(date_str)
        with closing(get_db()) as conn:
            db_openers = pd.read_sql_query(
                "SELECT timestamp, symbol, pattern_bucket FROM live_trades "
                "WHERE timestamp >= ? AND timestamp < ? AND (pnl = 0 OR pnl IS NULL)",
                conn, params=(start_ts, end_ts),
            )
    except Exception as e:
        LOGGER.warning("DB opener lookup failed: %s", e)
        return trips

    if db_openers.empty:
        return trips

    db_openers["pattern_bucket"] = (
        db_openers["pattern_bucket"].fillna("neutral")
        .replace("", "neutral")
        .str.strip()
    )

    for trip in trips:
        # CSV timestamps are naive ET — must localize before converting to Unix
        entry_unix = ET.localize(trip["entry_ts"].to_pydatetime()).timestamp()
        candidates = db_openers[
            (db_openers["symbol"] == trip["symbol"]) &
            (db_openers["timestamp"] >= entry_unix - MATCH_WINDOW_SECS) &
            (db_openers["timestamp"] <= entry_unix + MATCH_WINDOW_SECS)
        ]
        if not candidates.empty:
            closest = candidates.iloc[
                (candidates["timestamp"] - entry_unix).abs().argsort()[:1]
            ]
            bucket = str(closest.iloc[0]["pattern_bucket"]) or "neutral"
            trip["pattern_bucket"] = bucket

    return trips


def get_db_account_stats(date_str: str) -> dict:
    try:
        start_ts, end_ts = _day_range(date_str)
        with closing(get_db()) as conn:
            df = pd.read_sql_query(
                "SELECT liquidation_value, day_pnl FROM account_history "
                "WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp DESC LIMIT 1",
                conn, params=(start_ts, end_ts),
            )
        if not df.empty:
            return {
                "account_value": round(float(df.iloc[0]["liquidation_value"]), 2),
                "day_pnl": round(float(df.iloc[0]["day_pnl"]), 2) if "day_pnl" in df.columns else None,
            }
    except Exception as e:
        LOGGER.warning("DB account query failed: %s", e)
    return {"account_value": None, "day_pnl": None}


def get_pattern_trades_stats(date_str: str) -> dict:
    """Query pattern_trades table for the day and return per-pattern, per-exit-reason stats."""
    try:
        start_ts, end_ts = _day_range(date_str)
        with closing(get_db()) as conn:
            df = pd.read_sql_query(
                "SELECT symbol, qty, price, entry_price, pnl, pattern, exit_reason "
                "FROM pattern_trades "
                "WHERE timestamp >= ? AND timestamp < ?",
                conn, params=(start_ts, end_ts),
            )
    except Exception as e:
        LOGGER.warning("Pattern trades DB query failed: %s", e)
        return {}

    if df.empty:
        return {}

    # Closers have a non-zero realized PnL
    closers = df[df["pnl"].notna() & (df["pnl"] != 0)].copy()
    if closers.empty:
        return {}

    closers["win"] = closers["pnl"] > 0
    closers["qty"] = closers["qty"].replace(0, 1)
    closers["pnl_per_share"] = closers["pnl"] / closers["qty"]

    total = len(closers)
    wins = int(closers["win"].sum())

    stats: dict = {
        "count": total,
        "wins": wins,
        "win_rate": round(wins / total * 100, 1) if total else None,
        "total_pnl": round(float(closers["pnl"].sum()), 4),
        "avg_pnl_per_share": round(float(closers["pnl_per_share"].mean()), 6) if total else None,
    }

    # By pattern name
    by_pattern = []
    for pat, grp in closers.groupby("pattern"):
        w = int(grp["win"].sum())
        n = len(grp)
        by_pattern.append({
            "pattern": pat or "unknown",
            "count": n,
            "win_rate": round(w / n * 100, 1),
            "total_pnl": round(float(grp["pnl"].sum()), 4),
        })
    stats["by_pattern"] = sorted(by_pattern, key=lambda x: x["total_pnl"], reverse=True)

    # By exit reason
    by_exit = []
    for reason, grp in closers.groupby("exit_reason"):
        w = int(grp["win"].sum())
        n = len(grp)
        by_exit.append({
            "exit_reason": reason or "unknown",
            "count": n,
            "win_rate": round(w / n * 100, 1),
            "total_pnl": round(float(grp["pnl"].sum()), 4),
        })
    stats["by_exit_reason"] = sorted(by_exit, key=lambda x: x["count"], reverse=True)

    # Top individual wins and losses
    sorted_cl = closers.sort_values("pnl", ascending=False)
    stats["top_wins"] = sorted_cl.head(3)[
        ["symbol", "pattern", "exit_reason", "qty", "pnl", "pnl_per_share"]
    ].to_dict("records")
    stats["top_losses"] = sorted_cl.tail(3)[
        ["symbol", "pattern", "exit_reason", "qty", "pnl", "pnl_per_share"]
    ].to_dict("records")

    return stats


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def _agg(d: pd.DataFrame) -> dict:
    total = len(d)
    wins  = int(d["win"].sum())
    return {
        "count":           total,
        "wins":            wins,
        "win_rate":        round(wins / total * 100, 1) if total else None,
        "total_pnl":       round(float(d["pnl"].sum()), 4),
        "avg_pnl_per_share": round(float(d["pnl_per_share"].mean()), 6) if total else None,
    }


def calc_stats(trips: list) -> dict:
    if not trips:
        return {}

    df = pd.DataFrame(trips)
    df["pattern_bucket"] = df["pattern_bucket"].fillna("neutral").replace("", "neutral")

    stats = {
        "overall":     _agg(df),
        "total_trips": len(df),
    }

    # Per symbol
    by_sym = []
    for sym, grp in df.groupby("symbol"):
        row = _agg(grp)
        row["symbol"] = sym
        by_sym.append(row)
    stats["by_symbol"] = sorted(by_sym, key=lambda x: x["total_pnl"], reverse=True)

    # Per bucket (overall)
    by_bucket = []
    for b in BUCKET_ORDER:
        grp = df[df["pattern_bucket"] == b]
        if grp.empty:
            continue
        row = _agg(grp)
        row["bucket"] = b
        by_bucket.append(row)
    for b, grp in df.groupby("pattern_bucket"):
        if b not in BUCKET_ORDER:
            row = _agg(grp)
            row["bucket"] = b
            by_bucket.append(row)
    stats["by_bucket"] = by_bucket

    # Per symbol × bucket
    by_sym_bucket = []
    for (sym, bucket), grp in df.groupby(["symbol", "pattern_bucket"]):
        row = _agg(grp)
        row["symbol"] = sym
        row["bucket"] = bucket
        by_sym_bucket.append(row)
    stats["by_symbol_bucket"] = sorted(by_sym_bucket, key=lambda x: x["total_pnl"], reverse=True)

    return stats


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_report(date_str, stats, account, overnight_closes, open_at_eod) -> str:
    try:
        date_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %d, %Y")
    except Exception:
        date_display = date_str

    overall   = stats.get("overall", {})
    trips     = stats.get("total_trips", 0)
    pnl       = overall.get("total_pnl")
    wr        = overall.get("win_rate")
    pnl_emoji = "🟢" if pnl and pnl >= 0 else "🔴"
    pnl_str   = f"${pnl:+.4f}" if pnl is not None else "N/A"
    wr_str    = f"{wr}%" if wr is not None else "N/A"

    acct      = account.get("account_value")
    day_pnl   = account.get("day_pnl")
    acct_str  = f"${acct:,.2f}" if acct is not None else "N/A"
    dpnl_str  = f"${day_pnl:+,.2f}" if day_pnl is not None else "N/A"

    lines = [
        f"📊 *Post-Market Report — {date_display}*\n",
        f"*Round-Trips:* `{trips}`  |  *Win Rate:* `{wr_str}`",
        f"{pnl_emoji} *Realized PnL:* `{pnl_str}`",
        f"💰 *Account:* `{acct_str}`  |  *Day PnL (broker):* `{dpnl_str}`",
    ]

    if overnight_closes:
        syms = ", ".join(sorted({r["symbol"] for r in overnight_closes}))
        lines.append(f"\n⚠️ *Overnight positions closed at open (excluded):* {syms}")

    if open_at_eod:
        for pos in open_at_eod:
            lines.append(f"⚠️ *Open at EOD:* `{pos['symbol']}` {pos['dir']} {pos['qty']}sh @ ${pos['price']:.4f}")

    # --- By Symbol ---
    by_sym = stats.get("by_symbol", [])
    if by_sym:
        lines.append("\n*By Symbol:*")
        for s in by_sym:
            e   = "🟢" if s["total_pnl"] >= 0 else "🔴"
            aps = s.get("avg_pnl_per_share")
            lines.append(
                f"  {e} `{s['symbol']}` — {s['count']} trips  "
                f"{s['win_rate']}% WR  ${s['total_pnl']:+.4f}  "
                f"${aps:+.4f}/sh" if aps is not None else
                f"  {e} `{s['symbol']}` — {s['count']} trips  {s['win_rate']}% WR  ${s['total_pnl']:+.4f}"
            )

    # --- By Pattern Bucket ---
    by_bucket = stats.get("by_bucket", [])
    if by_bucket:
        lines.append("\n*By Pattern Bucket:*")
        for b in by_bucket:
            e   = "🟢" if b["total_pnl"] >= 0 else "🔴"
            em  = BUCKET_EMOJI.get(b["bucket"], "⚪")
            aps = b.get("avg_pnl_per_share")
            aps_str = f"  ${aps:+.4f}/sh" if aps is not None else ""
            lines.append(
                f"  {e}{em} `{b['bucket']}` — {b['count']} trips  "
                f"{b['win_rate']}% WR  ${b['total_pnl']:+.4f}{aps_str}"
            )

    # --- Symbol × Bucket (the main in-depth section) ---
    by_sb = stats.get("by_symbol_bucket", [])
    if by_sb:
        lines.append("\n*By Symbol × Pattern Bucket:*")
        current_sym = None
        for r in sorted(by_sb, key=lambda x: (x["symbol"], ["aligned","countertrend","neutral"].index(x["bucket"]) if x["bucket"] in ["aligned","countertrend","neutral"] else 99)):
            if r["symbol"] != current_sym:
                current_sym = r["symbol"]
                lines.append(f"\n  `{current_sym}`")
            e   = "🟢" if r["total_pnl"] >= 0 else "🔴"
            em  = BUCKET_EMOJI.get(r["bucket"], "⚪")
            aps = r.get("avg_pnl_per_share")
            aps_str = f"  ${aps:+.4f}/sh" if aps is not None else ""
            lines.append(
                f"    {e}{em} {r['bucket']:<14} "
                f"{r['count']:>2} trips  {r['win_rate']:>5}% WR  "
                f"${r['total_pnl']:>+8.4f}{aps_str}"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _extract_ai_analysis(markdown: str) -> str:
    """Pull just the AI analysis text out of a saved report markdown."""
    marker = "🤖 *AI Analysis:*"
    idx = markdown.find(marker)
    if idx == -1:
        return ""
    return markdown[idx + len(marker):].strip()


def _build_claude_prompt(
    date_str: str,
    stats: dict,
    account: dict,
    previous: list[dict],
    trips: list,
    pattern_stats: dict,
) -> str:
    # ── Scalper summary ──────────────────────────────────────────────────────
    overall = stats.get("overall", {})
    scalper_trips = stats.get("total_trips", 0)
    by_sym = stats.get("by_symbol", [])[:6]
    by_bucket = stats.get("by_bucket", [])
    day_pnl = account.get("day_pnl")
    day_pnl_str = f"${day_pnl:+.2f}" if day_pnl is not None else "N/A"
    acct_val = account.get("account_value")
    acct_str = f"${acct_val:,.2f}" if acct_val is not None else "N/A"

    sym_parts = "  ".join(
        f"{s['symbol']} ${s['total_pnl']:+.4f} {s['win_rate']}%WR ({s['count']}t)"
        for s in by_sym
    ) or "none"
    bucket_parts = "  ".join(
        f"{b['bucket']} ${b['total_pnl']:+.4f} {b['win_rate']}%WR ({b['count']}t)"
        for b in by_bucket
    ) or "none"

    # Top 3 wins and losses from CSV trips
    sorted_trips = sorted(trips, key=lambda t: t["pnl"], reverse=True)
    def _fmt_trip(t: dict) -> str:
        return (
            f"  {t['symbol']} {t['dir']} {t['qty']}sh "
            f"${t['entry_price']:.4f}→${t['exit_price']:.4f} "
            f"pnl=${t['pnl']:+.4f} bucket={t['pattern_bucket']} "
            f"@ {str(t['entry_ts'])[:16]}"
        )
    top_wins_str = "\n".join(_fmt_trip(t) for t in sorted_trips[:3]) or "  none"
    top_losses_str = "\n".join(_fmt_trip(t) for t in sorted_trips[-3:][::-1]) or "  none"

    scalper_block = (
        f"SCALPER STRATEGY (from Schwab CSV + DB annotations):\n"
        f"  Trips: {scalper_trips}  WR: {overall.get('win_rate', 'N/A')}%  "
        f"PnL: ${overall.get('total_pnl', 0):+.4f}  "
        f"Avg $/sh: ${overall.get('avg_pnl_per_share', 0) or 0:+.6f}\n"
        f"  By symbol: {sym_parts}\n"
        f"  By pattern_bucket: {bucket_parts}\n"
        f"  Top wins:\n{top_wins_str}\n"
        f"  Top losses:\n{top_losses_str}"
    )

    # ── Pattern strategy summary ──────────────────────────────────────────────
    if pattern_stats:
        pat_by_pattern = "  ".join(
            f"{p['pattern']} ${p['total_pnl']:+.4f} {p['win_rate']}%WR ({p['count']}t)"
            for p in pattern_stats.get("by_pattern", [])
        ) or "none"
        pat_by_exit = "  ".join(
            f"{e['exit_reason']} ${e['total_pnl']:+.4f} {e['win_rate']}%WR ({e['count']}t)"
            for e in pattern_stats.get("by_exit_reason", [])
        ) or "none"
        def _fmt_pat(t: dict) -> str:
            return (
                f"  {t['symbol']} pattern={t['pattern']} exit={t['exit_reason']} "
                f"{int(t['qty'])}sh pnl=${t['pnl']:+.4f} (${t['pnl_per_share']:+.4f}/sh)"
            )
        pw = "\n".join(_fmt_pat(t) for t in pattern_stats.get("top_wins", [])) or "  none"
        pl = "\n".join(_fmt_pat(t) for t in pattern_stats.get("top_losses", [])) or "  none"
        pattern_block = (
            f"PATTERN STRATEGY (from DB pattern_trades):\n"
            f"  Trades: {pattern_stats['count']}  WR: {pattern_stats.get('win_rate', 'N/A')}%  "
            f"PnL: ${pattern_stats['total_pnl']:+.4f}  "
            f"Avg $/sh: ${pattern_stats.get('avg_pnl_per_share', 0) or 0:+.6f}\n"
            f"  By pattern: {pat_by_pattern}\n"
            f"  By exit reason: {pat_by_exit}\n"
            f"  Top wins:\n{pw}\n"
            f"  Top losses:\n{pl}"
        )
    else:
        pattern_block = "PATTERN STRATEGY: No trades recorded today."

    # ── Previous report history ───────────────────────────────────────────────
    hist_lines = []
    for r in previous:
        d = r["report_data"]
        dt = d.get("date") or datetime.fromtimestamp(r["timestamp"], tz=ET).strftime("%Y-%m-%d")
        ov = d.get("trip_stats", {}).get("overall", {})
        prev_ai = _extract_ai_analysis(r.get("report_markdown", ""))
        summary = (
            f"{dt}: scalper PnL ${ov.get('total_pnl', 0):+.4f} "
            f"WR {ov.get('win_rate', 'N/A')}%  {d.get('trip_stats', {}).get('total_trips', 0)} trips"
        )
        if prev_ai:
            summary += f"\n  AI notes: {prev_ai[:400]}"
        hist_lines.append(summary)

    hist = "\n\n".join(hist_lines) if hist_lines else "No prior reports available."

    return (
        "You are an expert quantitative trading analyst reviewing daily performance for a 2-strategy bot.\n\n"
        "STRATEGY CONTEXT:\n"
        "- SCALPER: Momentum/imbalance strategy. pattern_bucket (aligned/countertrend/neutral) "
        "shows whether the scalp entry was with or against the chart pattern at entry time.\n"
        "- PATTERN: Chart-pattern recognition strategy. Each trade has a named pattern and exit_reason "
        "(target/failure_stop/time_stop/trailing_stop).\n\n"
        f"DATE: {date_str}  |  Account: {acct_str}  |  Broker Day PnL: {day_pnl_str}\n\n"
        f"{scalper_block}\n\n"
        f"{pattern_block}\n\n"
        f"PREVIOUS REPORTS (newest first — for maturity/trend analysis):\n{hist}\n\n"
        "Write a structured analysis covering ALL of the following sections. "
        "Be specific and data-driven. Reference exact numbers. Plain text, use section headers.\n\n"
        "SCALPER ANALYSIS: How did the scalper perform? Highlight the biggest win and loss. "
        "What does the pattern_bucket breakdown reveal about entry quality?\n\n"
        "PATTERN STRATEGY ANALYSIS: How did the pattern strategy perform? "
        "Which patterns worked or failed? What exit reasons dominate — is the bot hitting targets "
        "or getting stopped out?\n\n"
        "COMPARISON: Which strategy outperformed today and why? "
        "Is there a divergence worth noting?\n\n"
        "RECURRING PATTERNS & ISSUES: Based on today's data AND previous reports, "
        "what behavioral patterns or systemic issues do you see? "
        "(e.g. countertrend scalps consistently losing, a specific pattern always failing, "
        "certain symbols underperforming repeatedly)\n\n"
        "RECOMMENDATIONS: Give 2-3 specific actionable fixes or parameter adjustments. "
        "Cite the data that supports each.\n\n"
        "BOT MATURITY: Is the bot improving vs. previous sessions? "
        "Are past issues being resolved or persisting?"
    )


def run_from_upload(content: bytes, filename: str) -> tuple[str, dict]:
    date_str = extract_date_from_filename(filename)
    if not date_str:
        raise ValueError(f"Could not extract a YYYY-MM-DD date from filename: {filename}")

    LOGGER.info("Post-market CSV analysis for %s", date_str)

    text = content.decode("utf-8", errors="replace")
    raw_fills = parse_schwab_html(text)
    if raw_fills.empty:
        raise ValueError("No filled orders found in the uploaded file.")

    fills  = aggregate_fills(raw_fills)
    trips, overnight_closes, open_at_eod = build_round_trips(fills)
    trips  = annotate_trips_with_buckets(trips, date_str)

    stats   = calc_stats(trips)
    account = get_db_account_stats(date_str)
    pattern_stats = get_pattern_trades_stats(date_str)

    previous = get_previous_reports("post_market", limit=7)
    report_md = format_report(date_str, stats, account, overnight_closes, open_at_eod)
    prompt = _build_claude_prompt(date_str, stats, account, previous, trips, pattern_stats)
    analysis = call_claude(prompt, max_tokens=1200)
    if analysis:
        report_md += f"\n\n🤖 *AI Analysis:*\n{analysis}"

    report_data = {
        "date":             date_str,
        "source":           "schwab_csv",
        "trip_stats":       stats,
        "pattern_stats":    pattern_stats,
        "account":          account,
        "overnight_closes": overnight_closes,
        "open_at_eod":      open_at_eod,
    }

    save_report("post_market", report_md, report_data)
    tg_ok = send_telegram(report_md)
    report_data["telegram_sent"] = tg_ok
    LOGGER.info("Post-market CSV report saved%s.", " and sent" if tg_ok else " (Telegram failed)")
    return report_md, report_data
