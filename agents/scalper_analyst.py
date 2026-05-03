"""
Scalper Analyst Agent
Runs daily at 4:15 PM ET on weekdays.
Analyzes the scalper/imbalance strategy from live_trades — round-trip PnL by symbol,
time window, alert direction, and imbalance strength.
Pattern bucket logic lives in pattern_analyst.py instead.
"""

import logging
from contextlib import closing
from datetime import datetime

import pandas as pd
import pytz

from agents.base import get_db, save_report, send_telegram, get_previous_reports, call_claude

LOGGER = logging.getLogger("agents.scalper_analyst")
ET = pytz.timezone("America/New_York")
MATCH_WINDOW_SECS = 5


def _today_range_unix() -> tuple[float, float]:
    now_et = datetime.now(ET)
    start_et = now_et.replace(hour=0, minute=0, second=0, microsecond=0)
    end_et = now_et.replace(hour=23, minute=59, second=59, microsecond=0)
    return start_et.timestamp(), end_et.timestamp()


def _build_round_trips(trades_df: pd.DataFrame) -> pd.DataFrame:
    trips = []
    for symbol, sym_df in trades_df.groupby("symbol"):
        sym_df = sym_df.sort_values("timestamp").reset_index(drop=True)
        open_row = None
        for _, row in sym_df.iterrows():
            pnl = float(row.get("pnl", 0.0) or 0.0)
            qty = float(row.get("qty", 0) or 0)
            if pnl == 0.0:
                open_row = row
            else:
                open_ts = open_row["timestamp"] if open_row is not None else None
                trips.append({
                    "symbol": symbol,
                    "open_ts": open_ts,
                    "close_ts": row["timestamp"],
                    "qty": qty,
                    "pnl": pnl,
                    "pnl_per_share": round(pnl / qty, 6) if qty != 0 else 0.0,
                    "win": pnl > 0,
                })
                open_row = None
    return pd.DataFrame(trips) if trips else pd.DataFrame()


def _agg(df: pd.DataFrame) -> dict:
    total = len(df)
    wins = int(df["win"].sum())
    return {
        "count": total,
        "win_rate": round(wins / total * 100, 1) if total > 0 else None,
        "total_pnl": round(float(df["pnl"].sum()), 4),
        "avg_pnl": round(float(df["pnl"].mean()), 4) if total > 0 else None,
        "avg_pnl_per_share": round(float(df["pnl_per_share"].mean()), 6) if total > 0 else None,
    }


def collect_stats() -> dict:
    start_ts, end_ts = _today_range_unix()

    with closing(get_db()) as conn:
        trades = pd.read_sql_query(
            "SELECT * FROM live_trades WHERE timestamp >= ? AND timestamp <= ?",
            conn, params=(start_ts, end_ts),
        )
        alerts = pd.read_sql_query(
            "SELECT timestamp, symbol, direction, total_bids, total_asks FROM alerts "
            "WHERE timestamp >= ? AND timestamp <= ?",
            conn, params=(start_ts, end_ts),
        )
        account = pd.read_sql_query(
            "SELECT liquidation_value, day_pnl FROM account_history "
            "WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1",
            conn, params=(start_ts, end_ts),
        )

    stats: dict = {
        "total_alerts": len(alerts),
        "total_raw_trades": len(trades),
        "account_value": None,
        "day_pnl": None,
    }

    if not account.empty:
        stats["account_value"] = round(float(account.iloc[0]["liquidation_value"]), 2)
        if "day_pnl" in account.columns:
            stats["day_pnl"] = round(float(account.iloc[0]["day_pnl"]), 2)

    if trades.empty:
        return stats

    trips_df = _build_round_trips(trades)
    if trips_df.empty:
        return stats

    # Add time columns to trips using open_ts
    trips_df["dt"] = pd.to_datetime(trips_df["open_ts"].fillna(trips_df["close_ts"]), unit="s", utc=True).dt.tz_convert(ET)
    trips_df["half_hour"] = (trips_df["dt"].dt.hour * 60 + trips_df["dt"].dt.minute) // 30

    trip_stats: dict = {}
    trip_stats["overall"] = _agg(trips_df)
    trip_stats["total_trips"] = len(trips_df)

    # By symbol
    sym_stats = []
    for sym, grp in trips_df.groupby("symbol"):
        row = _agg(grp)
        row["symbol"] = sym
        sym_stats.append(row)
    trip_stats["by_symbol"] = sorted(sym_stats, key=lambda x: x["total_pnl"], reverse=True)

    # By 30-min time window
    window_stats = []
    for bucket, grp in trips_df.groupby("half_hour"):
        hour = (int(bucket) * 30) // 60
        minute = (int(bucket) * 30) % 60
        row = _agg(grp)
        row["window"] = f"{hour:02d}:{minute:02d}"
        window_stats.append(row)
    trip_stats["by_time_window"] = sorted(window_stats, key=lambda x: x["window"])

    stats["trip_stats"] = trip_stats

    # Alert conversion rate
    if stats["total_alerts"] > 0:
        stats["alert_to_trip_ratio"] = round(len(trips_df) / stats["total_alerts"] * 100, 1)
    else:
        stats["alert_to_trip_ratio"] = None

    # Alert direction and imbalance performance (match alerts to trips)
    if not alerts.empty:
        alerts = alerts.copy()
        alerts["imbalance"] = alerts["total_bids"] - alerts["total_asks"]
        matched = []
        for _, alert in alerts.iterrows():
            candidates = trips_df[
                (trips_df["symbol"] == alert["symbol"]) &
                (trips_df["open_ts"] >= alert["timestamp"]) &
                (trips_df["open_ts"] <= alert["timestamp"] + MATCH_WINDOW_SECS)
            ]
            if not candidates.empty:
                nearest = candidates.iloc[(candidates["open_ts"] - alert["timestamp"]).abs().argsort()[:1]]
                matched.append({
                    "direction": alert["direction"],
                    "imbalance": alert["imbalance"],
                    "pnl": float(nearest.iloc[0]["pnl"]),
                    "win": float(nearest.iloc[0]["pnl"]) > 0,
                })

        if matched:
            mdf = pd.DataFrame(matched)

            by_dir = []
            for direction, grp in mdf.groupby("direction"):
                wins = grp[grp["win"] == True]
                by_dir.append({
                    "direction": direction,
                    "count": len(grp),
                    "win_rate": round(len(wins) / len(grp) * 100, 1),
                    "avg_pnl": round(float(grp["pnl"].mean()), 4),
                    "total_pnl": round(float(grp["pnl"].sum()), 4),
                })
            stats["by_alert_direction"] = sorted(by_dir, key=lambda x: x["avg_pnl"], reverse=True)

            mdf["imb_bucket"] = pd.cut(
                mdf["imbalance"],
                bins=[-float("inf"), -500, -100, 100, 500, float("inf")],
                labels=["strong_ask", "mild_ask", "neutral", "mild_bid", "strong_bid"],
            )
            by_imb = []
            for bucket, grp in mdf.groupby("imb_bucket", observed=True):
                if len(grp) < 2:
                    continue
                wins = grp[grp["win"] == True]
                by_imb.append({
                    "imbalance_bucket": str(bucket),
                    "count": len(grp),
                    "win_rate": round(len(wins) / len(grp) * 100, 1),
                    "avg_pnl": round(float(grp["pnl"].mean()), 4),
                })
            stats["by_imbalance_bucket"] = by_imb

    return stats


def format_report(stats: dict) -> str:
    date_str = datetime.now(ET).strftime("%b %d, %Y")
    trip_stats = stats.get("trip_stats", {})
    overall = trip_stats.get("overall", {})

    pnl = overall.get("total_pnl")
    pnl_emoji = "🟢" if pnl and pnl >= 0 else "🔴"
    pnl_str = f"${pnl:+.4f}" if pnl is not None else "N/A"
    acct = stats.get("account_value")
    acct_str = f"${acct:,.2f}" if acct is not None else "N/A"
    wr = overall.get("win_rate")
    wr_str = f"{wr}%" if wr is not None else "N/A"
    trips = trip_stats.get("total_trips", 0)

    lines = [
        f"📡 *Scalper Report — {date_str}*\n",
        f"*Round-Trips:* `{trips}`  |  *Win Rate:* `{wr_str}`",
        f"{pnl_emoji} *PnL:* `{pnl_str}`  |  *Account:* `{acct_str}`",
        f"*Alerts:* `{stats['total_alerts']}`  |  *Conversion:* `{stats.get('alert_to_trip_ratio', 'N/A')}%`",
    ]

    by_sym = trip_stats.get("by_symbol", [])
    if by_sym:
        lines.append("\n*By Symbol:*")
        for s in by_sym:
            e = "🟢" if s["total_pnl"] >= 0 else "🔴"
            avg_ps = s.get("avg_pnl_per_share")
            avg_ps_str = f"  ${avg_ps:+.4f}/sh" if avg_ps is not None else ""
            lines.append(f"  {e} `{s['symbol']}` — {s['count']} trips  {s['win_rate']}% WR  ${s['total_pnl']:+.4f}{avg_ps_str}")

    by_window = trip_stats.get("by_time_window", [])
    active_windows = [w for w in by_window if w["count"] >= 2]
    if active_windows:
        best = max(active_windows, key=lambda x: x["avg_pnl"])
        worst = min(active_windows, key=lambda x: x["avg_pnl"])
        lines.append(f"\n*Best window:* `{best['window']}` — {best['count']} trips  {best['win_rate']}% WR  ${best['avg_pnl']:+.4f} avg")
        if worst["window"] != best["window"]:
            lines.append(f"*Worst window:* `{worst['window']}` — {worst['count']} trips  {worst['win_rate']}% WR  ${worst['avg_pnl']:+.4f} avg")

    by_dir = stats.get("by_alert_direction", [])
    if by_dir:
        lines.append("\n*By Alert Direction:*")
        for d in by_dir:
            e = "🟢" if d["avg_pnl"] >= 0 else "🔴"
            lines.append(f"  {e} `{d['direction']}` — {d['count']} trades  {d['win_rate']}% WR  ${d['avg_pnl']:+.4f} avg")

    by_imb = stats.get("by_imbalance_bucket", [])
    if by_imb:
        lines.append("\n*By Imbalance Strength:*")
        for b in by_imb:
            e = "🟢" if b["avg_pnl"] >= 0 else "🔴"
            lines.append(f"  {e} `{b['imbalance_bucket']}` — {b['count']} trades  {b['win_rate']}% WR  ${b['avg_pnl']:+.4f} avg")

    return "\n".join(lines)


def _build_claude_prompt(stats: dict, previous: list[dict]) -> str:
    date_str = datetime.now(ET).strftime("%Y-%m-%d")
    trip_stats = stats.get("trip_stats", {})
    overall = trip_stats.get("overall", {})
    trips = trip_stats.get("total_trips", 0)
    by_sym = trip_stats.get("by_symbol", [])[:5]
    by_window = trip_stats.get("by_time_window", [])
    active_windows = [w for w in by_window if w["count"] >= 2]
    by_dir = stats.get("by_alert_direction", [])
    by_imb = stats.get("by_imbalance_bucket", [])

    sym_str = " | ".join(
        "{} ${:+.4f} {}%WR {}t".format(s["symbol"], s["total_pnl"], s["win_rate"], s["count"])
        for s in by_sym
    ) or "none"

    window_str = " | ".join(
        "{} {}%WR ${:+.4f}avg {}t".format(w["window"], w["win_rate"], w["avg_pnl"], w["count"])
        for w in active_windows
    ) or "none"

    dir_str = " | ".join(
        "{} {}%WR ${:+.4f}avg {}t".format(d["direction"], d["win_rate"], d["avg_pnl"], d["count"])
        for d in by_dir
    ) or "none"

    imb_str = " | ".join(
        "{} {}%WR ${:+.4f}avg {}t".format(b["imbalance_bucket"], b["win_rate"], b["avg_pnl"], b["count"])
        for b in by_imb
    ) or "none"

    today = (
        f"Date: {date_str}  PnL: ${overall.get('total_pnl', 0):+.4f}  "
        f"WR: {overall.get('win_rate', 'N/A')}%  Trips: {trips}  "
        f"Alert conversion: {stats.get('alert_to_trip_ratio', 'N/A')}%\n"
        f"By symbol: {sym_str}\n"
        f"By time window: {window_str}\n"
        f"By alert direction: {dir_str}\n"
        f"By imbalance strength: {imb_str}"
    )

    hist_lines = []
    for r in previous:
        dt = datetime.fromtimestamp(r["timestamp"], tz=ET).strftime("%Y-%m-%d")
        d = r["report_data"]
        ov = d.get("trip_stats", {}).get("overall", {})
        syms = d.get("trip_stats", {}).get("by_symbol", [])[:3]
        sym_hist = " | ".join(
            "{} ${:+.4f} {}%WR".format(s["symbol"], s["total_pnl"], s["win_rate"])
            for s in syms
        )
        hist_lines.append(
            f"{dt}: PnL ${ov.get('total_pnl', 0):+.4f}  WR {ov.get('win_rate', 'N/A')}%  "
            f"{d.get('trip_stats', {}).get('total_trips', 0)} trips  "
            f"conv {d.get('alert_to_trip_ratio', 'N/A')}%  | {sym_hist}"
        )

    hist = "\n".join(hist_lines) if hist_lines else "No prior history available."

    return (
        "You are a trading analyst for an imbalance/momentum scalper strategy.\n\n"
        f"TODAY:\n{today}\n\n"
        f"RECENT HISTORY (newest first):\n{hist}\n\n"
        "Answer these four points concisely:\n"
        "1. CONTEXT: Is today better/worse than the recent average — by how much in PnL and win rate?\n"
        "2. SIGNAL EDGE: Which alert direction or imbalance bucket showed the clearest edge today? "
        "Is the alert conversion rate healthy or are too many/few signals getting traded?\n"
        "3. TIMING DRAG: Which time window hurt performance today? Is this a recurring weak spot across recent days?\n"
        "4. TOMORROW: One specific scalper adjustment — a direction to favor, a time window to skip, "
        "or an imbalance threshold to raise/lower.\n"
        "Be direct and data-driven. Use actual numbers. Plain text only — no bullet points or headers."
    )


def run():
    LOGGER.info("Scalper analyst starting.")
    previous = get_previous_reports("scalper_analyst", limit=5)
    stats = collect_stats()
    report_md = format_report(stats)
    analysis = call_claude(_build_claude_prompt(stats, previous), max_tokens=500)
    if analysis:
        report_md += f"\n\n🤖 *AI Analysis:*\n{analysis}"
    save_report("scalper_analyst", report_md, stats)
    send_telegram(report_md)
    LOGGER.info("Scalper analyst report sent and saved.")
