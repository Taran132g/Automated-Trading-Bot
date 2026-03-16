"""
Alert Quality Analyst Agent
Runs weekly on Sundays at 6 PM ET.
Joins alerts with live_trades over the last 30 days to measure signal quality,
then calls Claude for tuning recommendations.
"""

import json
import logging
from contextlib import closing
from datetime import datetime, timedelta

import pandas as pd
import pytz

from agents.base import get_db, save_report, send_telegram

LOGGER = logging.getLogger("agents.alert_quality")
ET = pytz.timezone("America/New_York")
LOOKBACK_DAYS = 30
MATCH_WINDOW_SECS = 5  # max seconds between alert and trade to be considered related


def collect_stats() -> dict:
    cutoff = (datetime.now(ET) - timedelta(days=LOOKBACK_DAYS)).timestamp()

    with closing(get_db()) as conn:
        alerts = pd.read_sql_query(
            "SELECT id, timestamp, symbol, direction, total_bids, total_asks, heavy_venues "
            "FROM alerts WHERE timestamp >= ?",
            conn, params=(cutoff,)
        )
        trades = pd.read_sql_query(
            "SELECT id, timestamp, symbol, side, pnl FROM live_trades WHERE timestamp >= ?",
            conn, params=(cutoff,)
        )

    if alerts.empty:
        return {"error": "No alerts in the last 30 days"}

    # Match each alert to the nearest trade on same symbol within MATCH_WINDOW_SECS
    matched_rows = []
    for _, alert in alerts.iterrows():
        candidates = trades[
            (trades["symbol"] == alert["symbol"]) &
            (trades["timestamp"] >= alert["timestamp"]) &
            (trades["timestamp"] <= alert["timestamp"] + MATCH_WINDOW_SECS)
        ]
        if not candidates.empty:
            nearest = candidates.iloc[(candidates["timestamp"] - alert["timestamp"]).abs().argsort()[:1]]
            row = alert.to_dict()
            row["trade_pnl"] = float(nearest.iloc[0]["pnl"])
            row["trade_side"] = nearest.iloc[0]["side"]
            matched_rows.append(row)
        else:
            row = alert.to_dict()
            row["trade_pnl"] = None
            row["trade_side"] = None
            matched_rows.append(row)

    df = pd.DataFrame(matched_rows)
    df["imbalance"] = df["total_bids"] - df["total_asks"]
    df["was_traded"] = df["trade_pnl"].notna()
    df["win"] = df["trade_pnl"].apply(lambda x: x > 0 if x is not None else None)

    stats: dict = {
        "lookback_days": LOOKBACK_DAYS,
        "total_alerts": len(df),
        "alerts_traded": int(df["was_traded"].sum()),
        "overall_win_rate": None,
    }

    traded = df[df["was_traded"]]
    if not traded.empty:
        stats["overall_win_rate"] = round(traded["win"].sum() / len(traded) * 100, 1)
        stats["overall_avg_pnl"] = round(traded["trade_pnl"].mean(), 4)

        # By direction
        dir_stats = []
        for direction, grp in traded.groupby("direction"):
            wins = grp[grp["win"] == True]
            dir_stats.append({
                "direction": direction,
                "count": len(grp),
                "win_rate": round(len(wins) / len(grp) * 100, 1),
                "avg_pnl": round(grp["trade_pnl"].mean(), 4),
            })
        stats["by_direction"] = dir_stats

        # By imbalance size bucket
        traded = traded.copy()
        traded["imbalance_bucket"] = pd.cut(
            traded["imbalance"],
            bins=[-float("inf"), -500, -100, 100, 500, float("inf")],
            labels=["strong_ask", "mild_ask", "neutral", "mild_bid", "strong_bid"]
        )
        imb_stats = []
        for bucket, grp in traded.groupby("imbalance_bucket", observed=True):
            wins = grp[grp["win"] == True]
            imb_stats.append({
                "imbalance_bucket": str(bucket),
                "count": len(grp),
                "win_rate": round(len(wins) / len(grp) * 100, 1) if len(grp) > 0 else None,
                "avg_pnl": round(grp["trade_pnl"].mean(), 4),
            })
        stats["by_imbalance_bucket"] = imb_stats

        # By hour of day (ET)
        traded = traded.copy()
        traded["hour_et"] = pd.to_datetime(traded["timestamp"], unit="s", utc=True) \
            .dt.tz_convert("America/New_York").dt.hour
        hour_stats = []
        for hour, grp in traded.groupby("hour_et"):
            wins = grp[grp["win"] == True]
            hour_stats.append({
                "hour_et": int(hour),
                "count": len(grp),
                "win_rate": round(len(wins) / len(grp) * 100, 1),
                "avg_pnl": round(grp["trade_pnl"].mean(), 4),
            })
        stats["by_hour"] = hour_stats

    return stats


def format_report(stats: dict) -> str:
    wr = stats.get("overall_win_rate")
    wr_str = f"{wr}%" if wr is not None else "N/A"
    avg = stats.get("overall_avg_pnl")
    avg_str = f"${avg:+.4f}" if avg is not None else "N/A"

    lines = [
        f"🔬 *Alert Quality Report — Last {LOOKBACK_DAYS} Days*\n",
        f"*Alerts:* `{stats['total_alerts']}`  |  *Traded:* `{stats.get('alerts_traded', 'N/A')}`",
        f"*Overall Win Rate:* `{wr_str}`  |  *Avg PnL:* `{avg_str}`",
    ]

    # By direction
    by_dir = stats.get("by_direction", [])
    if by_dir:
        lines.append("\n*By Direction:*")
        for d in sorted(by_dir, key=lambda x: x["avg_pnl"], reverse=True):
            e = "🟢" if d["avg_pnl"] >= 0 else "🔴"
            lines.append(f"  {e} `{d['direction']}` — {d['count']} trades, {d['win_rate']}% WR, ${d['avg_pnl']:+.4f} avg")

    # By imbalance bucket
    by_imb = stats.get("by_imbalance_bucket", [])
    if by_imb:
        lines.append("\n*By Imbalance Size:*")
        for b in by_imb:
            if b["count"] == 0:
                continue
            e = "🟢" if b["avg_pnl"] >= 0 else "🔴"
            lines.append(f"  {e} `{b['imbalance_bucket']}` — {b['count']} trades, {b['win_rate']}% WR, ${b['avg_pnl']:+.4f} avg")

    # Best and worst hour
    by_hour = stats.get("by_hour", [])
    if by_hour:
        best = max(by_hour, key=lambda x: x["avg_pnl"])
        worst = min(by_hour, key=lambda x: x["avg_pnl"])
        lines.append(f"\n*Best hour:* `{best['hour_et']}:00 ET` ({best['win_rate']}% WR, ${best['avg_pnl']:+.4f} avg)")
        lines.append(f"*Worst hour:* `{worst['hour_et']}:00 ET` ({worst['win_rate']}% WR, ${worst['avg_pnl']:+.4f} avg)")

    return "\n".join(lines)


def run():
    LOGGER.info("Alert quality analyst starting.")
    stats = collect_stats()
    if "error" in stats:
        LOGGER.warning(stats["error"])
        return
    report_md = format_report(stats)
    save_report("alert_quality", report_md, stats)
    send_telegram(report_md)
    LOGGER.info("Alert quality report sent and saved.")
