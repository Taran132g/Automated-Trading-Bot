"""
Weekly Review Agent
Runs Sunday at 6 PM ET.
Comprehensive end-of-week analysis combining live trades, pattern trades,
alerts, and account equity — replaces the old alert_quality + optimizer reports.
"""

import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytz

from agents.base import get_db, save_report, send_telegram, get_previous_reports, call_claude

LOGGER = logging.getLogger("agents.weekly_review")
ET = pytz.timezone("America/New_York")
LOOKBACK_DAYS = 5
DB_PATH = Path(__file__).parent.parent / "penny_basing.db"


def _week_range() -> tuple[float, float]:
    now = datetime.now(ET)
    start = (now - timedelta(days=LOOKBACK_DAYS)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.timestamp(), now.timestamp()


def collect_stats() -> dict:
    cutoff_ts, now_ts = _week_range()

    with closing(get_db()) as conn:
        live_trades = pd.read_sql_query(
            "SELECT * FROM live_trades WHERE timestamp >= ? AND timestamp <= ?",
            conn, params=(cutoff_ts, now_ts),
        )
        alerts = pd.read_sql_query(
            "SELECT timestamp, symbol, direction, total_bids, total_asks FROM alerts "
            "WHERE timestamp >= ? AND timestamp <= ?",
            conn, params=(cutoff_ts, now_ts),
        )
        account = pd.read_sql_query(
            "SELECT timestamp, liquidation_value, day_pnl FROM account_history "
            "WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp ASC",
            conn, params=(cutoff_ts, now_ts),
        )

    # Optional tables (may not exist)
    pattern_trades = pd.DataFrame()
    claude_log = pd.DataFrame()
    try:
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            pattern_trades = pd.read_sql_query(
                "SELECT * FROM pattern_trades WHERE timestamp >= ? AND timestamp <= ?",
                conn, params=(cutoff_ts, now_ts),
            )
    except Exception:
        pass
    try:
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            claude_log = pd.read_sql_query(
                "SELECT * FROM pattern_claude_log WHERE timestamp >= ? AND timestamp <= ?",
                conn, params=(cutoff_ts, now_ts),
            )
    except Exception:
        pass

    stats: dict = {
        "lookback_days": LOOKBACK_DAYS,
        "week_start": datetime.fromtimestamp(cutoff_ts, tz=ET).strftime("%Y-%m-%d"),
        "week_end": datetime.now(ET).strftime("%Y-%m-%d"),
    }

    # --- Account equity ---
    if not account.empty:
        first_val = float(account.iloc[0]["liquidation_value"])
        last_val = float(account.iloc[-1]["liquidation_value"])
        week_pnl = round(last_val - first_val, 2)
        account["dt"] = pd.to_datetime(account["timestamp"], unit="s", utc=True).dt.tz_convert(ET)
        account["date"] = account["dt"].dt.date.astype(str)
        daily_pnl = []
        for date, grp in account.groupby("date"):
            last_snap = grp.sort_values("timestamp").iloc[-1]
            daily_pnl.append({
                "date": date,
                "day_pnl": round(float(last_snap.get("day_pnl", 0) or 0), 2),
                "equity": round(float(last_snap["liquidation_value"]), 2),
            })
        stats["account"] = {
            "start_value": round(first_val, 2),
            "end_value": round(last_val, 2),
            "week_pnl": week_pnl,
            "week_pnl_pct": round(week_pnl / first_val * 100, 2) if first_val > 0 else None,
            "daily": daily_pnl,
        }

    # --- Live trades (scalper) ---
    if not live_trades.empty:
        live_trades["win"] = live_trades["pnl"] > 0
        live_trades["dt"] = pd.to_datetime(live_trades["timestamp"], unit="s", utc=True).dt.tz_convert(ET)
        live_trades["date"] = live_trades["dt"].dt.date.astype(str)
        live_trades["half_hour"] = (live_trades["dt"].dt.hour * 60 + live_trades["dt"].dt.minute) // 30
        closing_trades = live_trades[live_trades["pnl"] != 0]

        live_stats: dict = {
            "total_trades": len(closing_trades),
            "total_pnl": round(float(closing_trades["pnl"].sum()), 4),
        }
        if not closing_trades.empty:
            live_stats["win_rate"] = round(float(closing_trades["win"].sum()) / len(closing_trades) * 100, 1)
            live_stats["avg_pnl"] = round(float(closing_trades["pnl"].mean()), 4)

            # By symbol
            sym_stats = []
            for sym, grp in closing_trades.groupby("symbol"):
                sym_stats.append({
                    "symbol": sym,
                    "trades": len(grp),
                    "win_rate": round(float(grp["win"].sum()) / len(grp) * 100, 1),
                    "total_pnl": round(float(grp["pnl"].sum()), 4),
                    "avg_pnl": round(float(grp["pnl"].mean()), 4),
                })
            live_stats["by_symbol"] = sorted(sym_stats, key=lambda x: x["total_pnl"], reverse=True)

            # By 30-min time window (min 3 trades to include)
            window_stats = []
            for bucket, grp in closing_trades.groupby("half_hour"):
                if len(grp) < 3:
                    continue
                hour = (int(bucket) * 30) // 60
                minute = (int(bucket) * 30) % 60
                window_stats.append({
                    "window": f"{hour:02d}:{minute:02d}",
                    "trades": len(grp),
                    "win_rate": round(float(grp["win"].sum()) / len(grp) * 100, 1),
                    "avg_pnl": round(float(grp["pnl"].mean()), 4),
                    "total_pnl": round(float(grp["pnl"].sum()), 4),
                })
            live_stats["by_time_window"] = sorted(window_stats, key=lambda x: x["avg_pnl"], reverse=True)

            # By day
            day_stats = []
            for date, grp in closing_trades.groupby("date"):
                day_stats.append({
                    "date": date,
                    "trades": len(grp),
                    "win_rate": round(float(grp["win"].sum()) / len(grp) * 100, 1),
                    "total_pnl": round(float(grp["pnl"].sum()), 4),
                })
            live_stats["by_day"] = sorted(day_stats, key=lambda x: x["date"])

        stats["live"] = live_stats

    # --- Pattern trades ---
    if not pattern_trades.empty:
        exits = pattern_trades[pattern_trades["side"].isin(["SELL", "COVER"])]
        pat_stats: dict = {
            "total_exits": len(exits),
            "total_pnl": round(float(pattern_trades["pnl"].fillna(0).sum()), 4),
        }
        if not exits.empty:
            pat_stats["win_rate"] = round(float((exits["pnl"] > 0).sum()) / len(exits) * 100, 1)
            by_pat = []
            for pat, grp in pattern_trades.groupby("pattern"):
                pat_exits = grp[grp["side"].isin(["SELL", "COVER"])]
                by_pat.append({
                    "pattern": pat,
                    "exits": len(pat_exits),
                    "total_pnl": round(float(grp["pnl"].fillna(0).sum()), 4),
                    "win_rate": round(float((pat_exits["pnl"] > 0).sum()) / len(pat_exits) * 100, 1) if len(pat_exits) > 0 else None,
                })
            pat_stats["by_pattern"] = sorted(by_pat, key=lambda x: x["total_pnl"], reverse=True)
            exit_rows = pattern_trades[pattern_trades["exit_reason"].notna() & (pattern_trades["exit_reason"] != "entry")]
            by_exit = []
            for reason, grp in exit_rows.groupby("exit_reason"):
                by_exit.append({
                    "reason": reason,
                    "count": len(grp),
                    "total_pnl": round(float(grp["pnl"].fillna(0).sum()), 4),
                })
            pat_stats["by_exit_reason"] = sorted(by_exit, key=lambda x: x["total_pnl"], reverse=True)
        stats["pattern"] = pat_stats

    # --- Claude filter stats ---
    if not claude_log.empty:
        approved = claude_log[claude_log["approved"] == 1]
        rejected = claude_log[claude_log["approved"] == 0]
        stats["claude_filter"] = {
            "total_evaluated": len(claude_log),
            "approved": len(approved),
            "rejected": len(rejected),
            "approval_rate": round(len(approved) / len(claude_log) * 100, 1),
            "avg_rr_approved": round(float(approved["rr_ratio"].mean()), 2) if len(approved) > 0 else None,
            "avg_rr_rejected": round(float(rejected["rr_ratio"].mean()), 2) if len(rejected) > 0 else None,
        }

    # --- Alert stats ---
    if not alerts.empty:
        by_dir = []
        for direction, grp in alerts.groupby("direction"):
            by_dir.append({"direction": direction, "count": len(grp)})
        stats["alerts"] = {"total": len(alerts), "by_direction": by_dir}

    return stats


def format_report(stats: dict) -> str:
    lines = [f"📅 *Weekly Review — {stats.get('week_start')} → {stats.get('week_end')}*\n"]

    acct = stats.get("account", {})
    if acct:
        pnl = acct.get("week_pnl", 0)
        pct = acct.get("week_pnl_pct")
        emoji = "🟢" if pnl >= 0 else "🔴"
        pct_str = f" ({pct:+.2f}%)" if pct is not None else ""
        lines.append(
            f"{emoji} *Week PnL:* `${pnl:+.2f}`{pct_str}  |  *Equity:* `${acct.get('end_value', 0):,.2f}`"
        )
        daily = acct.get("daily", [])
        if daily:
            day_strs = "  ".join(f"{d['date'][-5:]} `${d['day_pnl']:+.2f}`" for d in daily)
            lines.append(f"*Daily:* {day_strs}")

    live = stats.get("live", {})
    if live:
        lines.append(
            f"\n*Scalper:* `{live['total_trades']}` trades  `{live.get('win_rate', 'N/A')}%` WR  `${live['total_pnl']:+.4f}`"
        )
        for s in live.get("by_symbol", [])[:6]:
            e = "🟢" if s["total_pnl"] >= 0 else "🔴"
            lines.append(f"  {e} `{s['symbol']}` — {s['trades']}t  {s['win_rate']}% WR  ${s['total_pnl']:+.4f}")
        windows = live.get("by_time_window", [])
        if windows:
            best = windows[0]
            worst = sorted(windows, key=lambda x: x["avg_pnl"])[0]
            lines.append(f"*Best window:* `{best['window']}` — {best['win_rate']}% WR  ${best['avg_pnl']:+.4f} avg")
            if worst["window"] != best["window"]:
                lines.append(f"*Worst window:* `{worst['window']}` — {worst['win_rate']}% WR  ${worst['avg_pnl']:+.4f} avg")

    pat = stats.get("pattern", {})
    if pat:
        lines.append(
            f"\n*Pattern:* `{pat['total_exits']}` exits  `{pat.get('win_rate', 'N/A')}%` WR  `${pat['total_pnl']:+.4f}`"
        )
        for p in pat.get("by_pattern", []):
            e = "🟢" if p["total_pnl"] >= 0 else "🔴"
            wr = f"{p['win_rate']}%" if p["win_rate"] is not None else "N/A"
            lines.append(f"  {e} `{p['pattern']}` — {p['exits']} exits  {wr} WR  ${p['total_pnl']:+.4f}")

    cf = stats.get("claude_filter", {})
    if cf:
        lines.append(
            f"\n🤖 *Claude Filter:* `{cf['approved']}/{cf['total_evaluated']}` approved "
            f"(`{cf['approval_rate']}%`)  R:R approved=`{cf.get('avg_rr_approved')}` / rejected=`{cf.get('avg_rr_rejected')}`"
        )

    return "\n".join(lines)


def _get_week_daily_analyses(cutoff_ts: float) -> list[str]:
    """Pull this week's Claude analysis snippets from saved daily reports."""
    try:
        with closing(get_db()) as conn:
            rows = conn.execute(
                "SELECT agent_name, timestamp, report_markdown FROM agent_reports "
                "WHERE agent_name IN ('scalper_analyst', 'pattern_analyst') AND timestamp >= ? "
                "ORDER BY timestamp ASC",
                (cutoff_ts,),
            ).fetchall()
        analyses = []
        for agent_name, ts, md in rows:
            if not md:
                continue
            dt = datetime.fromtimestamp(ts, tz=ET).strftime("%a %m/%d")
            if "🤖 *AI Analysis:*" in md:
                ai_part = md.split("🤖 *AI Analysis:*")[-1].strip()
                analyses.append(f"[{dt} {agent_name}] {ai_part}")
        return analyses
    except Exception:
        return []


def _build_claude_prompt(stats: dict, previous: list[dict], daily_analyses: list[str]) -> str:
    date_str = datetime.now(ET).strftime("%Y-%m-%d")

    # Account block
    acct = stats.get("account", {})
    if acct:
        daily = acct.get("daily", [])
        day_strs = "  ".join(f"{d['date'][-5:]} ${d['day_pnl']:+.2f}" for d in daily)
        acct_str = (
            f"Equity: ${acct.get('start_value', 0):,.2f} → ${acct.get('end_value', 0):,.2f}  "
            f"Week PnL: ${acct.get('week_pnl', 0):+.2f} ({acct.get('week_pnl_pct', 0):+.2f}%)\n"
            f"Day-by-day: {day_strs}"
        )
    else:
        acct_str = "No account data."

    # Live trades block
    live = stats.get("live", {})
    if live:
        sym_lines = "  ".join(
            f"{s['symbol']} ${s['total_pnl']:+.4f} {s['win_rate']}%WR {s['trades']}t"
            for s in live.get("by_symbol", [])
        )
        windows = live.get("by_time_window", [])
        best_w = windows[0] if windows else None
        worst_w = sorted(windows, key=lambda x: x["avg_pnl"])[0] if windows else None
        day_lines = "  ".join(
            f"{d['date'][-5:]} ${d['total_pnl']:+.4f} {d['win_rate']}%WR {d['trades']}t"
            for d in live.get("by_day", [])
        )
        live_str = (
            f"Trades: {live['total_trades']}  WR: {live.get('win_rate', 'N/A')}%  "
            f"Total PnL: ${live['total_pnl']:+.4f}  Avg: ${live.get('avg_pnl', 0):+.4f}\n"
            f"By symbol: {sym_lines or 'N/A'}\n"
            f"By day: {day_lines or 'N/A'}"
        )
        if best_w and worst_w and best_w["window"] != worst_w["window"]:
            live_str += (
                f"\nBest window: {best_w['window']} {best_w['win_rate']}%WR ${best_w['avg_pnl']:+.4f} avg ({best_w['trades']}t)"
                f"\nWorst window: {worst_w['window']} {worst_w['win_rate']}%WR ${worst_w['avg_pnl']:+.4f} avg ({worst_w['trades']}t)"
            )
    else:
        live_str = "No scalper trades this week."

    # Pattern trades block
    pat = stats.get("pattern", {})
    if pat:
        by_pat_lines = "  ".join(
            f"{p['pattern']} ${p['total_pnl']:+.4f} {p['win_rate']}%WR {p['exits']}exits"
            for p in pat.get("by_pattern", [])
        )
        by_exit_lines = "  ".join(
            f"{e['reason']}×{e['count']} ${e['total_pnl']:+.4f}"
            for e in pat.get("by_exit_reason", [])
        )
        pat_str = (
            f"Exits: {pat['total_exits']}  WR: {pat.get('win_rate', 'N/A')}%  Total PnL: ${pat['total_pnl']:+.4f}\n"
            f"By pattern: {by_pat_lines or 'N/A'}\n"
            f"By exit reason: {by_exit_lines or 'N/A'}"
        )
    else:
        pat_str = "No pattern trades this week."

    # Claude filter block
    cf = stats.get("claude_filter", {})
    cf_str = ""
    if cf:
        cf_str = (
            f"\nClaude filter: {cf['total_evaluated']} evaluated  "
            f"{cf['approved']} approved ({cf['approval_rate']}%)  {cf['rejected']} rejected  "
            f"Avg R:R approved={cf.get('avg_rr_approved')} rejected={cf.get('avg_rr_rejected')}"
        )

    # Daily analyses from this week
    daily_ctx = "\n---\n".join(daily_analyses) if daily_analyses else "No daily analyses this week."

    # Prior weekly reviews
    prev_lines = []
    for r in previous:
        dt = datetime.fromtimestamp(r["timestamp"], tz=ET).strftime("%Y-%m-%d")
        d = r["report_data"]
        a = d.get("account", {})
        lv = d.get("live", {})
        if isinstance(a, dict) and isinstance(lv, dict):
            prev_lines.append(
                f"{dt}: Week PnL ${a.get('week_pnl', 'N/A'):+.2f} ({a.get('week_pnl_pct', 'N/A'):+.2f}%)  "
                f"Scalper {lv.get('total_trades', 0)}t {lv.get('win_rate', 'N/A')}%WR ${lv.get('total_pnl', 0):+.4f}"
            )
        else:
            prev_lines.append(f"{dt}: limited data")
    prev_str = "\n".join(prev_lines) if prev_lines else "No prior weekly reviews."

    return (
        "You are a trading performance analyst reviewing a full week of results.\n\n"
        f"WEEK: {stats.get('week_start')} to {stats.get('week_end')}\n\n"
        f"ACCOUNT:\n{acct_str}\n\n"
        f"SCALPER (LIVE TRADES):\n{live_str}\n\n"
        f"PATTERN STRATEGY:\n{pat_str}"
        f"{cf_str}\n\n"
        f"THIS WEEK'S DAILY AI ANALYSES (for context):\n{daily_ctx}\n\n"
        f"PREVIOUS WEEKLY REVIEWS:\n{prev_str}\n\n"
        "Write a structured weekly review with these five sections:\n"
        "1. WEEK GRADE: A/B/C/D/F and one sentence on overall vs recent weeks.\n"
        "2. WHAT WORKED: Top 2 specific symbols or patterns that added real edge — include the numbers.\n"
        "3. BIGGEST DRAG: The single biggest PnL leak (symbol, time window, or pattern) and what's causing it.\n"
        "4. NEXT WEEK FOCUS: 2-3 specific symbols to prioritize and which time windows to favor.\n"
        "5. ONE CHANGE: The single most impactful adjustment before Monday open (e.g. skip a window, cut a symbol, tighten a filter).\n"
        "Be direct. Use actual numbers from the data. Max 280 words. Plain text only."
    )


def run():
    LOGGER.info("Weekly review agent starting.")
    cutoff_ts, _ = _week_range()
    previous = get_previous_reports("weekly_review", limit=3)
    stats = collect_stats()

    if not stats.get("live") and not stats.get("pattern"):
        LOGGER.warning("No trade data this week — skipping weekly review.")
        return

    daily_analyses = _get_week_daily_analyses(cutoff_ts)
    report_md = format_report(stats)
    analysis = call_claude(_build_claude_prompt(stats, previous, daily_analyses), max_tokens=1000)
    if analysis:
        report_md += f"\n\n🤖 *Weekly AI Review:*\n{analysis}"
    save_report("weekly_review", report_md, stats)
    send_telegram(report_md)
    LOGGER.info("Weekly review sent and saved.")
