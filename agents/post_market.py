"""
Post-Market Analyst Agent
Runs daily at 4:15 PM ET on weekdays.
Reads the day's trades/alerts/account data, builds round-trip trades,
attributes pattern buckets from entry time, calls Claude Opus for analysis,
sends a Telegram report, and stores the result in agent_reports.
"""

import logging
import time
from contextlib import closing
from datetime import datetime

import pandas as pd
import pytz

from agents.base import get_db, save_report, send_telegram, get_previous_reports, call_claude

LOGGER = logging.getLogger("agents.post_market")
ET = pytz.timezone("America/New_York")

def _today_range_unix() -> tuple[float, float]:
    now_et = datetime.now(ET)
    start_et = now_et.replace(hour=0, minute=0, second=0, microsecond=0)
    end_et = now_et.replace(hour=23, minute=59, second=59, microsecond=0)
    return start_et.timestamp(), end_et.timestamp()


def build_round_trips(trades_df: pd.DataFrame) -> pd.DataFrame:
    """
    Pair opening trades (pnl == 0) with subsequent closing trades (pnl != 0)
    per symbol in timestamp order. The entry pattern_bucket comes from the
    opener row, not the closer row.
    Returns a DataFrame with one row per completed round-trip.
    """
    trips = []

    for symbol, sym_df in trades_df.groupby("symbol"):
        sym_df = sym_df.sort_values("timestamp").reset_index(drop=True)
        open_row = None

        for _, row in sym_df.iterrows():
            pnl = float(row.get("pnl", 0.0) or 0.0)
            qty = float(row.get("qty", 0) or 0)

            if pnl == 0.0:
                # Opening trade — capture entry metadata
                open_row = row
            else:
                # Closing trade — complete the round-trip
                if open_row is not None:
                    entry_bucket = (
                        str(open_row.get("pattern_bucket") or "neutral").strip()
                        or "neutral"
                    )
                else:
                    # Closer without a matching opener in today's window
                    # (e.g. position opened yesterday); use closer's bucket as fallback
                    entry_bucket = (
                        str(row.get("pattern_bucket") or "neutral").strip()
                        or "neutral"
                    )

                trips.append(
                    {
                        "symbol": symbol,
                        "open_ts": open_row["timestamp"] if open_row is not None else None,
                        "close_ts": row["timestamp"],
                        "entry_price": float(open_row["price"]) if open_row is not None else None,
                        "exit_price": float(row["price"]),
                        "qty": qty,
                        "pnl": pnl,
                        "pnl_per_share": round(pnl / qty, 6) if qty != 0 else 0.0,
                        "entry_bucket": entry_bucket,
                        "win": pnl > 0,
                    }
                )
                open_row = None  # reset; next trade starts a new round-trip

    if not trips:
        return pd.DataFrame()

    return pd.DataFrame(trips)


def calc_round_trip_stats(trips_df: pd.DataFrame) -> dict:
    """
    Compute win rate, avg PnL/share, and total PnL grouped by:
      - overall
      - per symbol
      - per entry_bucket (aligned / countertrend / neutral)
      - per (symbol × entry_bucket)
    """
    if trips_df.empty:
        return {}

    def _agg(df):
        total = len(df)
        wins = int(df["win"].sum())
        return {
            "count": total,
            "win_rate": round(wins / total * 100, 1) if total > 0 else None,
            "wins": wins,
            "total_pnl": round(float(df["pnl"].sum()), 4),
            "avg_pnl": round(float(df["pnl"].mean()), 4) if total > 0 else None,
            "avg_pnl_per_share": round(float(df["pnl_per_share"].mean()), 6) if total > 0 else None,
        }

    stats = {}

    # Overall
    stats["overall"] = _agg(trips_df)
    stats["total_trips"] = len(trips_df)

    # Per symbol
    sym_stats = []
    for sym, grp in trips_df.groupby("symbol"):
        row = _agg(grp)
        row["symbol"] = sym
        sym_stats.append(row)
    stats["by_symbol"] = sorted(sym_stats, key=lambda x: x["total_pnl"], reverse=True)

    # Per entry bucket
    bucket_stats = []
    BUCKET_ORDER = ["aligned", "countertrend", "neutral"]
    for bucket in BUCKET_ORDER:
        grp = trips_df[trips_df["entry_bucket"] == bucket]
        if grp.empty:
            continue
        row = _agg(grp)
        row["bucket"] = bucket
        bucket_stats.append(row)
    # Include any unexpected bucket values
    for bucket, grp in trips_df.groupby("entry_bucket"):
        if bucket not in BUCKET_ORDER:
            row = _agg(grp)
            row["bucket"] = bucket
            bucket_stats.append(row)
    stats["by_bucket"] = bucket_stats

    # Per (symbol × bucket)
    sym_bucket_stats = []
    for (sym, bucket), grp in trips_df.groupby(["symbol", "entry_bucket"]):
        row = _agg(grp)
        row["symbol"] = sym
        row["bucket"] = bucket
        sym_bucket_stats.append(row)
    stats["by_symbol_bucket"] = sorted(
        sym_bucket_stats, key=lambda x: x["total_pnl"], reverse=True
    )

    return stats



def collect_stats() -> dict:
    start_ts, end_ts = _today_range_unix()

    with closing(get_db()) as conn:
        trades = pd.read_sql_query(
            "SELECT * FROM live_trades WHERE timestamp >= ? AND timestamp <= ?",
            conn,
            params=(start_ts, end_ts),
        )
        alerts = pd.read_sql_query(
            "SELECT * FROM alerts WHERE timestamp >= ? AND timestamp <= ?",
            conn,
            params=(start_ts, end_ts),
        )
        account = pd.read_sql_query(
            "SELECT * FROM account_history WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 2",
            conn,
            params=(start_ts, end_ts),
        )

    stats: dict = {}

    # --- Account metrics ---
    if len(account) >= 1:
        latest = account.iloc[0]
        stats["account_value"] = round(float(latest["liquidation_value"]), 2)
        stats["day_pnl"] = round(float(latest["day_pnl"]), 2) if "day_pnl" in account.columns else None
    else:
        stats["account_value"] = None
        stats["day_pnl"] = None

    # --- Alert metrics ---
    stats["total_alerts"] = len(alerts)
    stats["total_raw_trades"] = len(trades)

    # --- Round-trip analysis ---
    if trades.empty:
        stats["trip_stats"] = {}
        stats["trip_stats"] = {}
        return stats

    # Ensure pattern_bucket column exists with neutral default
    if "pattern_bucket" not in trades.columns:
        trades["pattern_bucket"] = "neutral"
    else:
        trades["pattern_bucket"] = trades["pattern_bucket"].fillna("neutral")

    trips_df = build_round_trips(trades)
    trip_stats = calc_round_trip_stats(trips_df)
    stats["trip_stats"] = trip_stats

    # Alert conversion rate
    if stats["total_alerts"] > 0 and trip_stats.get("total_trips", 0) > 0:
        stats["alert_to_trip_ratio"] = round(
            trip_stats["total_trips"] / stats["total_alerts"] * 100, 1
        )
    else:
        stats["alert_to_trip_ratio"] = None

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
        f"📊 *Post-Market Report — {date_str}*\n",
        f"*Round-Trips:* `{trips}`  |  *Win Rate:* `{wr_str}`",
        f"{pnl_emoji} *PnL:* `{pnl_str}`  |  *Account:* `{acct_str}`",
        f"*Alerts:* `{stats['total_alerts']}`  |  *Conversion:* `{stats.get('alert_to_trip_ratio', 'N/A')}%`",
    ]

    # Per-symbol breakdown
    by_sym = trip_stats.get("by_symbol", [])
    if by_sym:
        lines.append("\n*By Symbol:*")
        for s in by_sym:
            e = "🟢" if s["total_pnl"] >= 0 else "🔴"
            avg_ps = s.get("avg_pnl_per_share")
            avg_ps_str = f"${avg_ps:+.4f}/sh" if avg_ps is not None else ""
            lines.append(
                f"  {e} `{s['symbol']}` — {s['count']} trips, {s['win_rate']}% WR, "
                f"${s['total_pnl']:+.4f} {avg_ps_str}"
            )

    # Pattern bucket breakdown (entry-time attribution)
    by_bucket = trip_stats.get("by_bucket", [])
    if by_bucket:
        BUCKET_EMOJI = {"aligned": "✅", "countertrend": "❌", "neutral": "⚪"}
        lines.append("\n*By Pattern Alignment (entry bucket):*")
        for b in by_bucket:
            emoji = BUCKET_EMOJI.get(b["bucket"], "⚪")
            wr_b = f"{b['win_rate']}%" if b["win_rate"] is not None else "N/A"
            avg_ps = b.get("avg_pnl_per_share")
            avg_ps_str = f"${avg_ps:+.4f}/sh" if avg_ps is not None else ""
            lines.append(
                f"  {emoji} `{b['bucket']}` — {b['count']} trips, {wr_b} WR, "
                f"${b['total_pnl']:+.4f} total {avg_ps_str}"
            )

    # Symbol × bucket breakdown
    by_sym_bucket = trip_stats.get("by_symbol_bucket", [])
    if by_sym_bucket:
        lines.append("\n*By Symbol × Pattern Bucket:*")
        for r in by_sym_bucket:
            e = "🟢" if r["total_pnl"] >= 0 else "🔴"
            BUCKET_EMOJI = {"aligned": "✅", "countertrend": "❌", "neutral": "⚪"}
            be = BUCKET_EMOJI.get(r["bucket"], "⚪")
            avg_ps = r.get("avg_pnl_per_share")
            avg_ps_str = f"${avg_ps:+.4f}/sh" if avg_ps is not None else ""
            lines.append(
                f"  {e}{be} `{r['symbol']}` / `{r['bucket']}` — {r['count']} trips, "
                f"{r['win_rate']}% WR, ${r['total_pnl']:+.4f} {avg_ps_str}"
            )

    return "\n".join(lines)


def _build_claude_prompt(stats: dict, previous: list[dict]) -> str:
    date_str = datetime.now(ET).strftime("%Y-%m-%d")
    overall = stats.get("trip_stats", {}).get("overall", {})
    trips = stats.get("trip_stats", {}).get("total_trips", 0)
    by_sym = stats.get("trip_stats", {}).get("by_symbol", [])[:4]
    by_bucket = stats.get("trip_stats", {}).get("by_bucket", [])

    sym_str = " | ".join("{} ${:+.4f} {}%WR".format(s["symbol"], s["total_pnl"], s["win_rate"]) for s in by_sym) or "none"
    bucket_str = " | ".join("{} ${:+.4f} {}%WR".format(b["bucket"], b["total_pnl"], b["win_rate"]) for b in by_bucket) or "none"
    today = (
        f"Date: {date_str}  PnL: ${overall.get('total_pnl', 0):+.4f}  "
        f"Win rate: {overall.get('win_rate', 'N/A')}%  Trips: {trips}  "
        f"Alert conversion: {stats.get('alert_to_trip_ratio', 'N/A')}%\n"
        f"By symbol: {sym_str}\n"
        f"By pattern bucket: {bucket_str}"
    )

    hist_lines = []
    for r in previous:
        dt = datetime.fromtimestamp(r["timestamp"], tz=ET).strftime("%Y-%m-%d")
        d = r["report_data"]
        ov = d.get("trip_stats", {}).get("overall", {})
        syms = d.get("trip_stats", {}).get("by_symbol", [])[:3]
        sym_str = " | ".join(f"{s['symbol']} ${s['total_pnl']:+.4f} {s['win_rate']}%WR" for s in syms)
        hist_lines.append(
            f"{dt}: PnL ${ov.get('total_pnl', 0):+.4f}  WR {ov.get('win_rate', 'N/A')}%  "
            f"{d.get('trip_stats', {}).get('total_trips', 0)} trips  "
            f"conv {d.get('alert_to_trip_ratio', 'N/A')}% | {sym_str}"
        )

    hist = "\n".join(hist_lines) if hist_lines else "No prior history available."

    return (
        "You are a trading performance analyst for a momentum/imbalance strategy.\n\n"
        f"TODAY:\n{today}\n\n"
        f"RECENT HISTORY (newest first):\n{hist}\n\n"
        "Answer these four points concisely:\n"
        "1. CONTEXT: Is today better/worse than recent average, and by how much in PnL and win rate?\n"
        "2. EDGE: Which symbol or pattern bucket showed the clearest edge today and why does the data support it?\n"
        "3. DRAG: What was the single biggest drag today — a specific symbol, bucket, or time window?\n"
        "4. TOMORROW: One specific change to make tomorrow based purely on today's data "
        "(e.g. skip a symbol, focus on a bucket, avoid a time window).\n"
        "Be direct and data-driven. Use actual numbers. Plain text only — no bullet points or headers."
    )


def run():
    LOGGER.info("Post-market analyst starting.")
    previous = get_previous_reports("post_market", limit=5)
    stats = collect_stats()
    report_md = format_report(stats)
    analysis = call_claude(_build_claude_prompt(stats, previous), max_tokens=500)
    if analysis:
        report_md += f"\n\n🤖 *AI Analysis:*\n{analysis}"
    save_report("post_market", report_md, stats)
    send_telegram(report_md)
    LOGGER.info("Post-market report sent and saved.")
