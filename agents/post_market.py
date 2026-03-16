"""
Post-Market Analyst Agent
Runs daily at 4:15 PM ET on weekdays.
Reads the day's trades/alerts/account data, calls Claude for analysis,
sends a Telegram report, and stores the result in agent_reports.
"""

import json
import time
import logging
from contextlib import closing
from datetime import datetime, timezone

import pandas as pd
import pytz

from agents.base import get_db, save_report, send_telegram

LOGGER = logging.getLogger("agents.post_market")
ET = pytz.timezone("America/New_York")


def _today_range_unix() -> tuple[float, float]:
    now_et = datetime.now(ET)
    start_et = now_et.replace(hour=0, minute=0, second=0, microsecond=0)
    end_et = now_et.replace(hour=23, minute=59, second=59, microsecond=0)
    return start_et.timestamp(), end_et.timestamp()


def collect_stats() -> dict:
    start_ts, end_ts = _today_range_unix()

    with closing(get_db()) as conn:
        trades = pd.read_sql_query(
            "SELECT * FROM live_trades WHERE timestamp >= ? AND timestamp <= ?",
            conn, params=(start_ts, end_ts)
        )
        alerts = pd.read_sql_query(
            "SELECT * FROM alerts WHERE timestamp >= ? AND timestamp <= ?",
            conn, params=(start_ts, end_ts)
        )
        account = pd.read_sql_query(
            "SELECT * FROM account_history WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 2",
            conn, params=(start_ts, end_ts)
        )

    stats: dict = {}

    # --- Trade metrics ---
    if trades.empty:
        stats["total_trades"] = 0
        stats["win_rate"] = None
        stats["avg_pnl"] = None
        stats["total_pnl"] = None
    else:
        wins = trades[trades["pnl"] > 0]
        stats["total_trades"] = len(trades)
        stats["win_rate"] = round(len(wins) / len(trades) * 100, 1)
        stats["avg_pnl"] = round(trades["pnl"].mean(), 4)
        stats["total_pnl"] = round(trades["pnl"].sum(), 4)

        # Per-symbol breakdown
        sym_stats = []
        for sym, grp in trades.groupby("symbol"):
            w = grp[grp["pnl"] > 0]
            sym_stats.append({
                "symbol": sym,
                "trades": len(grp),
                "win_rate": round(len(w) / len(grp) * 100, 1),
                "total_pnl": round(grp["pnl"].sum(), 4),
            })
        stats["by_symbol"] = sym_stats

        # Hourly breakdown
        trades["hour"] = pd.to_datetime(trades["timestamp"], unit="s", utc=True) \
            .dt.tz_convert("America/New_York").dt.hour
        hourly = trades.groupby("hour")["pnl"].agg(["sum", "count", "mean"]).reset_index()
        hourly.columns = ["hour", "total_pnl", "trades", "avg_pnl"]
        stats["by_hour"] = hourly.round(4).to_dict(orient="records")

    # --- Alert metrics ---
    stats["total_alerts"] = len(alerts)
    if not alerts.empty and stats["total_trades"] > 0:
        stats["alert_to_trade_ratio"] = round(stats["total_trades"] / len(alerts) * 100, 1)
    else:
        stats["alert_to_trade_ratio"] = None

    # --- Account metrics ---
    if len(account) >= 2:
        latest = account.iloc[0]
        earliest = account.iloc[-1]
        stats["day_pnl"] = round(float(latest["day_pnl"]), 2) if "day_pnl" in account.columns else None
        stats["account_value"] = round(float(latest["liquidation_value"]), 2)
    elif len(account) == 1:
        stats["account_value"] = round(float(account.iloc[0]["liquidation_value"]), 2)
        stats["day_pnl"] = round(float(account.iloc[0]["day_pnl"]), 2) if "day_pnl" in account.columns else None
    else:
        stats["account_value"] = None
        stats["day_pnl"] = None

    return stats


def format_report(stats: dict) -> str:
    date_str = datetime.now(ET).strftime("%b %d, %Y")
    pnl = stats.get("total_pnl")
    pnl_emoji = "🟢" if pnl and pnl >= 0 else "🔴"
    pnl_str = f"${pnl:+.4f}" if pnl is not None else "N/A"
    acct = stats.get("account_value")
    acct_str = f"${acct:,.2f}" if acct is not None else "N/A"
    wr = stats.get("win_rate")
    wr_str = f"{wr}%" if wr is not None else "N/A"

    lines = [
        f"📊 *Post-Market Report — {date_str}*\n",
        f"*Trades:* `{stats['total_trades']}`  |  *Win Rate:* `{wr_str}`",
        f"{pnl_emoji} *PnL:* `{pnl_str}`  |  *Account:* `{acct_str}`",
        f"*Alerts:* `{stats['total_alerts']}`  |  *Conversion:* `{stats.get('alert_to_trade_ratio', 'N/A')}%`",
    ]

    # Per-symbol breakdown
    by_sym = stats.get("by_symbol", [])
    if by_sym:
        lines.append("\n*By Symbol:*")
        for s in sorted(by_sym, key=lambda x: x["total_pnl"], reverse=True):
            e = "🟢" if s["total_pnl"] >= 0 else "🔴"
            lines.append(f"  {e} `{s['symbol']}` — {s['trades']} trades, {s['win_rate']}% WR, ${s['total_pnl']:+.4f}")

    # Best and worst hour
    by_hour = stats.get("by_hour", [])
    if by_hour:
        best = max(by_hour, key=lambda x: x["total_pnl"])
        worst = min(by_hour, key=lambda x: x["total_pnl"])
        lines.append(f"\n*Best hour:* `{best['hour']}:00` (${best['total_pnl']:+.4f})")
        lines.append(f"*Worst hour:* `{worst['hour']}:00` (${worst['total_pnl']:+.4f})")

    return "\n".join(lines)


def run():
    LOGGER.info("Post-market analyst starting.")
    stats = collect_stats()
    report_md = format_report(stats)
    save_report("post_market", report_md, stats)
    send_telegram(report_md)
    LOGGER.info("Post-market report sent and saved.")
