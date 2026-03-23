"""
Alert Quality Analyst Agent
Runs weekly on Sundays at 6 PM ET.
Joins alerts with live_trades over the last 5 days to measure signal quality,
then calls Claude for tuning recommendations.
"""

import json
import logging
from contextlib import closing
from datetime import datetime, timedelta

import pandas as pd
import pytz

from agents.base import get_db, save_report, send_telegram, get_previous_reports, call_claude

LOGGER = logging.getLogger("agents.alert_quality")
ET = pytz.timezone("America/New_York")
LOOKBACK_DAYS = 5
MATCH_WINDOW_SECS = 5  # max seconds between alert and trade to be considered related


def collect_stats() -> dict:
    cutoff = (datetime.now(ET) - timedelta(days=LOOKBACK_DAYS)).timestamp()

    with closing(get_db()) as conn:
        alerts = pd.read_sql_query(
            "SELECT timestamp, symbol, direction, total_bids, total_asks, heavy_venues "
            "FROM alerts WHERE timestamp >= ?",
            conn, params=(cutoff,)
        )
        trades = pd.read_sql_query(
            "SELECT id, timestamp, symbol, side, pnl FROM live_trades WHERE timestamp >= ?",
            conn, params=(cutoff,)
        )

    if alerts.empty:
        return {"error": f"No alerts in the last {LOOKBACK_DAYS} days"}

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


def _build_claude_prompt(stats: dict, previous: list[dict]) -> str:
    date_str = datetime.now(ET).strftime("%Y-%m-%d")
    by_dir = stats.get("by_direction", [])
    by_imb = stats.get("by_imbalance_bucket", [])
    by_hour = stats.get("by_hour", [])

    match_rate = None
    if stats.get("alerts_traded") and stats.get("total_alerts"):
        match_rate = round(stats["alerts_traded"] / stats["total_alerts"] * 100, 1)

    dir_lines = "\n".join(
        f"  {d['direction']}: {d['count']} trades, {d['win_rate']}% WR, avg ${d['avg_pnl']:+.4f}"
        for d in sorted(by_dir, key=lambda x: x["avg_pnl"], reverse=True)
    ) if by_dir else "  N/A"

    imb_lines = "\n".join(
        f"  {b['imbalance_bucket']}: {b['count']} trades, {b['win_rate']}% WR, avg ${b['avg_pnl']:+.4f}"
        for b in by_imb if b["count"] > 0
    ) if by_imb else "  N/A"

    hour_lines = "\n".join(
        f"  {h['hour_et']:02d}:00 ET: {h['count']} trades, {h['win_rate']}% WR, avg ${h['avg_pnl']:+.4f}"
        for h in sorted(by_hour, key=lambda x: x["hour_et"])
    ) if by_hour else "  N/A"

    current = (
        f"Period ending {date_str} (last {LOOKBACK_DAYS} days)\n"
        f"Total alerts: {stats['total_alerts']}  Traded: {stats.get('alerts_traded', 'N/A')}  "
        f"Match rate: {match_rate}%  Overall WR: {stats.get('overall_win_rate', 'N/A')}%  "
        f"Avg PnL: ${stats.get('overall_avg_pnl', 0):+.4f}\n\n"
        f"BY DIRECTION:\n{dir_lines}\n\n"
        f"BY IMBALANCE BUCKET:\n{imb_lines}\n\n"
        f"BY HOUR (ET):\n{hour_lines}"
    )

    hist_lines = []
    for r in previous:
        dt = datetime.fromtimestamp(r["timestamp"], tz=ET).strftime("%Y-%m-%d")
        d = r["report_data"]
        bd = max(d.get("by_direction", []), key=lambda x: x["avg_pnl"], default=None)
        hist_lines.append(
            f"{dt}: WR {d.get('overall_win_rate', 'N/A')}%  Avg PnL ${d.get('overall_avg_pnl', 0):+.4f}  "
            f"Alerts {d.get('total_alerts', 'N/A')} traded {d.get('alerts_traded', 'N/A')}  "
            f"Best dir: {bd['direction'] if bd else 'N/A'} {bd['win_rate'] if bd else 'N/A'}%WR"
        )

    hist = "\n".join(hist_lines) if hist_lines else "No prior weekly history available."

    return (
        "You are a signal quality analyst for an imbalance-based momentum trading system.\n\n"
        f"CURRENT PERIOD:\n{current}\n\n"
        f"PREVIOUS WEEKLY REPORTS (newest first):\n{hist}\n\n"
        "In 5-6 sentences: describe whether signal quality is trending better or worse week-over-week, "
        "identify which direction or imbalance bucket shows the most meaningful shift, "
        "identify the best and worst trading hours and whether they are consistent week-over-week, "
        "and give 2-3 specific tuning recommendations based on the data (e.g. filter out weak buckets, "
        "restrict to best hours, focus on top-performing directions). Be direct and data-driven. Plain text only."
    )


def run():
    LOGGER.info("Alert quality analyst starting.")
    previous = get_previous_reports("alert_quality", limit=4)
    stats = collect_stats()
    if "error" in stats:
        LOGGER.warning(stats["error"])
        return
    report_md = format_report(stats)
    analysis = call_claude(_build_claude_prompt(stats, previous), max_tokens=600)
    if analysis:
        report_md += f"\n\n🤖 *AI Analysis:*\n{analysis}"
    save_report("alert_quality", report_md, stats)
    send_telegram(report_md)
    LOGGER.info("Alert quality report sent and saved.")
