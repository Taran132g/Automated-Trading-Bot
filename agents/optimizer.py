"""
Strategy Parameter Optimizer Agent
Runs weekly on Sundays at 7 PM ET (after alert_quality has run).
Analyzes 30 days of alerts + trades to surface parameter optimization opportunities.
"""

import logging
from contextlib import closing
from datetime import datetime, timedelta

import pandas as pd
import pytz

from agents.base import get_db, save_report, send_telegram, get_previous_reports, call_claude

LOGGER = logging.getLogger("agents.optimizer")
ET = pytz.timezone("America/New_York")
LOOKBACK_DAYS = 30
MATCH_WINDOW_SECS = 5


def collect_stats() -> dict:
    cutoff = (datetime.now(ET) - timedelta(days=LOOKBACK_DAYS)).timestamp()

    with closing(get_db()) as conn:
        trades = pd.read_sql_query(
            "SELECT timestamp, symbol, side, pnl FROM live_trades WHERE timestamp >= ?",
            conn, params=(cutoff,)
        )
        alerts = pd.read_sql_query(
            "SELECT timestamp, symbol, direction, total_bids, total_asks FROM alerts WHERE timestamp >= ?",
            conn, params=(cutoff,)
        )

    if trades.empty:
        return {"error": "No trade data in the last 30 days"}

    trades["dt"] = pd.to_datetime(trades["timestamp"], unit="s", utc=True).dt.tz_convert("America/New_York")
    trades["hour"] = trades["dt"].dt.hour
    trades["minute"] = trades["dt"].dt.minute
    trades["half_hour"] = (trades["hour"] * 60 + trades["minute"]) // 30
    trades["win"] = trades["pnl"] > 0

    stats: dict = {"lookback_days": LOOKBACK_DAYS, "total_trades": len(trades)}

    # --- Time-of-day (30-min buckets) ---
    tod = []
    for bucket, grp in trades.groupby("half_hour"):
        hour = (bucket * 30) // 60
        minute = (bucket * 30) % 60
        label = f"{hour:02d}:{minute:02d}"
        wins = grp[grp["win"]]
        tod.append({
            "window": label,
            "trades": len(grp),
            "win_rate": round(len(wins) / len(grp) * 100, 1),
            "total_pnl": round(grp["pnl"].sum(), 4),
            "avg_pnl": round(grp["pnl"].mean(), 4),
        })
    stats["by_time_window"] = sorted(tod, key=lambda x: x["window"])

    # --- Per-symbol ---
    sym_stats = []
    for sym, grp in trades.groupby("symbol"):
        wins = grp[grp["win"]]
        sym_stats.append({
            "symbol": sym,
            "trades": len(grp),
            "win_rate": round(len(wins) / len(grp) * 100, 1),
            "total_pnl": round(grp["pnl"].sum(), 4),
            "avg_pnl": round(grp["pnl"].mean(), 4),
        })
    stats["by_symbol"] = sorted(sym_stats, key=lambda x: x["total_pnl"], reverse=True)

    # --- Bullish vs bearish alert performance ---
    if not alerts.empty:
        alerts["imbalance"] = alerts["total_bids"] - alerts["total_asks"]
        # Match alerts to trades (same symbol, trade within 5s after alert)
        matched = []
        for _, alert in alerts.iterrows():
            candidates = trades[
                (trades["symbol"] == alert["symbol"]) &
                (trades["timestamp"] >= alert["timestamp"]) &
                (trades["timestamp"] <= alert["timestamp"] + MATCH_WINDOW_SECS)
            ]
            if not candidates.empty:
                nearest = candidates.iloc[(candidates["timestamp"] - alert["timestamp"]).abs().argsort()[:1]]
                matched.append({
                    "direction": alert["direction"],
                    "imbalance": alert["imbalance"],
                    "pnl": float(nearest.iloc[0]["pnl"]),
                    "win": float(nearest.iloc[0]["pnl"]) > 0,
                })

        if matched:
            mdf = pd.DataFrame(matched)
            dir_perf = []
            for direction, grp in mdf.groupby("direction"):
                wins = grp[grp["win"]]
                dir_perf.append({
                    "direction": direction,
                    "matched_trades": len(grp),
                    "win_rate": round(len(wins) / len(grp) * 100, 1),
                    "avg_pnl": round(grp["pnl"].mean(), 4),
                    "total_pnl": round(grp["pnl"].sum(), 4),
                })
            stats["by_alert_direction"] = dir_perf

            # Imbalance size vs outcome
            mdf["imb_bucket"] = pd.cut(
                mdf["imbalance"],
                bins=[-float("inf"), -1000, -200, 200, 1000, float("inf")],
                labels=["large_ask", "small_ask", "neutral", "small_bid", "large_bid"]
            )
            imb_perf = []
            for bucket, grp in mdf.groupby("imb_bucket", observed=True):
                wins = grp[grp["win"]]
                imb_perf.append({
                    "imbalance_size": str(bucket),
                    "count": len(grp),
                    "win_rate": round(len(wins) / len(grp) * 100, 1) if len(grp) > 0 else None,
                    "avg_pnl": round(grp["pnl"].mean(), 4),
                })
            stats["by_imbalance_size"] = imb_perf

    return stats


def format_report(stats: dict) -> str:
    lines = [
        f"⚙️ *Strategy Optimizer — Last {LOOKBACK_DAYS} Days*\n",
        f"*Total trades:* `{stats['total_trades']}`",
    ]

    # Per-symbol
    by_sym = stats.get("by_symbol", [])
    if by_sym:
        lines.append("\n*By Symbol:*")
        for s in by_sym:
            e = "🟢" if s["total_pnl"] >= 0 else "🔴"
            lines.append(f"  {e} `{s['symbol']}` — {s['trades']} trades, {s['win_rate']}% WR, ${s['total_pnl']:+.4f}")

    # Best and worst 30-min windows
    by_tod = stats.get("by_time_window", [])
    if by_tod:
        active = [w for w in by_tod if w["trades"] >= 3]  # ignore tiny sample windows
        if active:
            best = max(active, key=lambda x: x["avg_pnl"])
            worst = min(active, key=lambda x: x["avg_pnl"])
            lines.append(f"\n*Best window:* `{best['window']}` — {best['trades']} trades, {best['win_rate']}% WR, ${best['avg_pnl']:+.4f} avg")
            lines.append(f"*Worst window:* `{worst['window']}` — {worst['trades']} trades, {worst['win_rate']}% WR, ${worst['avg_pnl']:+.4f} avg")

    # By alert direction
    by_dir = stats.get("by_alert_direction", [])
    if by_dir:
        lines.append("\n*By Alert Direction:*")
        for d in sorted(by_dir, key=lambda x: x["avg_pnl"], reverse=True):
            e = "🟢" if d["avg_pnl"] >= 0 else "🔴"
            lines.append(f"  {e} `{d['direction']}` — {d['matched_trades']} trades, {d['win_rate']}% WR, ${d['avg_pnl']:+.4f} avg")

    # By imbalance size
    by_imb = stats.get("by_imbalance_size", [])
    if by_imb:
        lines.append("\n*By Imbalance Size:*")
        for b in by_imb:
            if b["count"] < 3:
                continue
            e = "🟢" if b["avg_pnl"] >= 0 else "🔴"
            lines.append(f"  {e} `{b['imbalance_size']}` — {b['count']} trades, {b['win_rate']}% WR, ${b['avg_pnl']:+.4f} avg")

    return "\n".join(lines)


def _build_claude_prompt(stats: dict, previous: list[dict]) -> str:
    from datetime import datetime
    date_str = datetime.now(ET).strftime("%Y-%m-%d")
    by_sym = stats.get("by_symbol", [])[:5]
    by_tod = stats.get("by_time_window", [])
    by_dir = stats.get("by_alert_direction", [])
    by_imb = stats.get("by_imbalance_size", [])

    active_windows = [w for w in by_tod if w["trades"] >= 3]
    best_win = max(active_windows, key=lambda x: x["avg_pnl"], default=None)
    worst_win = min(active_windows, key=lambda x: x["avg_pnl"], default=None)
    best_sym = by_sym[0] if by_sym else None
    worst_sym = by_sym[-1] if by_sym else None

    current = (
        f"Period ending {date_str} (last {LOOKBACK_DAYS} days)  Total trades: {stats['total_trades']}\n"
        f"Top symbol: {best_sym['symbol'] if best_sym else 'N/A'} ${best_sym['total_pnl'] if best_sym else 0:+.4f} {best_sym['win_rate'] if best_sym else 'N/A'}%WR\n"
        f"Worst symbol: {worst_sym['symbol'] if worst_sym else 'N/A'} ${worst_sym['total_pnl'] if worst_sym else 0:+.4f} {worst_sym['win_rate'] if worst_sym else 'N/A'}%WR\n"
        f"Best window: {best_win['window'] if best_win else 'N/A'} {best_win['avg_pnl'] if best_win else 'N/A'} avg  "
        f"Worst window: {worst_win['window'] if worst_win else 'N/A'} {worst_win['avg_pnl'] if worst_win else 'N/A'} avg\n"
        f"By direction: {' | '.join(f\"{d['direction']} {d['win_rate']}%WR ${d['avg_pnl']:+.4f}\" for d in sorted(by_dir, key=lambda x: x['avg_pnl'], reverse=True))}\n"
        f"By imbalance: {' | '.join(f\"{b['imbalance_size']} {b['win_rate']}%WR ${b['avg_pnl']:+.4f}\" for b in by_imb if b['count'] >= 3)}"
    )

    hist_lines = []
    for r in previous:
        dt = datetime.fromtimestamp(r["timestamp"], tz=ET).strftime("%Y-%m-%d")
        d = r["report_data"]
        syms = d.get("by_symbol", [])[:2]
        sym_str = " | ".join(f"{s['symbol']} ${s['total_pnl']:+.4f} {s['win_rate']}%WR" for s in syms)
        hist_lines.append(
            f"{dt}: {d.get('total_trades', 'N/A')} trades | {sym_str}"
        )

    hist = "\n".join(hist_lines) if hist_lines else "No prior weekly history available."

    return (
        "You are a concise strategy parameter advisor for an imbalance-based momentum trading system.\n\n"
        f"CURRENT PERIOD:\n{current}\n\n"
        f"PREVIOUS WEEKLY REPORTS (newest first):\n{hist}\n\n"
        "In 4-5 sentences: describe what is shifting in the data week-over-week (symbols rising/falling, "
        "time windows changing), which parameters show the clearest edge right now, "
        "and give 2 concrete parameter adjustment suggestions (e.g. restrict to specific windows, "
        "weight imbalance thresholds differently). Be direct and specific. Plain text only."
    )


def run():
    LOGGER.info("Strategy optimizer starting.")
    previous = get_previous_reports("optimizer", limit=4)
    stats = collect_stats()
    if "error" in stats:
        LOGGER.warning(stats["error"])
        return
    report_md = format_report(stats)
    analysis = call_claude(_build_claude_prompt(stats, previous), max_tokens=350)
    if analysis:
        report_md += f"\n\n🤖 *AI Analysis:*\n{analysis}"
    save_report("optimizer", report_md, stats)
    send_telegram(report_md)
    LOGGER.info("Optimizer report sent and saved.")
