"""
generate_weekly_report.py
-------------------------
Crunches training_data.csv (867K+ rows) and penny_basing.db (live trades)
into a compact ~100-line text report for LLM analysis.

Run locally or on the server:
  python3 generate_weekly_report.py

Outputs: weekly_report.txt  (paste this into your LLM conversation)
"""

import csv
import sqlite3
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

TRAINING_CSV = "training_data.csv"
DB_PATH = os.getenv("DB_PATH", "penny_basing.db")
OUT_FILE = "weekly_report.txt"

# ── Helpers ──────────────────────────────────────────────────────────────────

def ts_to_hour(ts):
    try:
        return datetime.utcfromtimestamp(ts).hour
    except Exception:
        return -1

def ts_to_date(ts):
    try:
        return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        return "unknown"

def ts_to_weekday(ts):
    try:
        return datetime.utcfromtimestamp(ts).strftime("%A")
    except Exception:
        return "unknown"

def pct(num, denom):
    return f"{100 * num / denom:.1f}%" if denom else "N/A"

def avg(vals):
    return sum(vals) / len(vals) if vals else 0.0

def median(vals):
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    if n % 2 == 0:
        return (s[n//2 - 1] + s[n//2]) / 2
    return s[n//2]


# ── Section 1: Training Data Analysis (IMBALANCE_DEBUG snapshots) ────────────

def analyze_training_data():
    if not Path(TRAINING_CSV).exists():
        return "⚠️  training_data.csv not found. Run extract_training_data.py first.\n"

    lines = []
    total = 0
    alert_count = 0
    no_alert_count = 0

    # Per-symbol stats
    sym_counts = defaultdict(int)
    sym_alerts = defaultdict(int)

    # Price change distributions (for alert=1 rows only)
    alert_changes_10 = []
    alert_changes_30 = []
    alert_changes_60 = []

    # By venue count
    venue_changes_30 = defaultdict(list)  # heavy_venues -> [change_30s...]

    # By hour
    hour_changes_30 = defaultdict(list)   # hour -> [change_30s...]
    hour_alert_count = defaultdict(int)

    # By symbol (alert rows only)
    sym_changes_30 = defaultdict(list)

    # Volume correlation
    vol_buckets = {"low (<50K)": [], "med (50-200K)": [], "high (200K+)": []}

    # Near-miss analysis: non-alert rows with high venue counts
    near_miss_changes = []

    with open(TRAINING_CSV, "r") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            total += 1
            ts = float(row.get("timestamp", 0))
            sym = row.get("symbol", "")
            is_alert = int(row.get("alert", 0))
            heavy = int(row.get("heavy_venues", 0))
            vol = float(row.get("vol_per_min", 0))
            c10 = float(row.get("change_10s", 0))
            c30 = float(row.get("change_30s", 0))
            c60 = float(row.get("change_60s", 0))

            sym_counts[sym] += 1
            hour = ts_to_hour(ts)

            if is_alert:
                alert_count += 1
                sym_alerts[sym] += 1
                alert_changes_10.append(c10)
                alert_changes_30.append(c30)
                alert_changes_60.append(c60)
                hour_alert_count[hour] += 1
                sym_changes_30[sym].append(c30)
            else:
                no_alert_count += 1

            # Venue analysis (all rows)
            venue_changes_30[heavy].append(c30)
            hour_changes_30[hour].append(c30)

            # Volume buckets (alert rows)
            if is_alert:
                if vol < 50000:
                    vol_buckets["low (<50K)"].append(c30)
                elif vol < 200000:
                    vol_buckets["med (50-200K)"].append(c30)
                else:
                    vol_buckets["high (200K+)"].append(c30)

            # Near-miss: no alert but high venue count (absolute)
            if not is_alert and abs(heavy) >= 3:
                near_miss_changes.append(c30)

    # ── Build report section ──
    lines.append("=" * 65)
    lines.append("  SECTION 1: MARKET DATA ANALYSIS (training_data.csv)")
    lines.append("=" * 65)
    lines.append(f"Total snapshots:    {total:,}")
    lines.append(f"Alert snapshots:    {alert_count:,}  ({pct(alert_count, total)})")
    lines.append(f"Non-alert:          {no_alert_count:,}")
    lines.append("")

    # Symbol breakdown
    lines.append("── Snapshots by Symbol ──")
    for sym in sorted(sym_counts, key=lambda s: sym_counts[s], reverse=True):
        a = sym_alerts.get(sym, 0)
        lines.append(f"  {sym:8s}  {sym_counts[sym]:>8,} snapshots  {a:>5,} alerts  ({pct(a, sym_counts[sym])} alert rate)")
    lines.append("")

    # What happens after an alert fires?
    if alert_changes_30:
        positive_10 = sum(1 for c in alert_changes_10 if c > 0)
        positive_30 = sum(1 for c in alert_changes_30 if c > 0)
        positive_60 = sum(1 for c in alert_changes_60 if c > 0)
        n = len(alert_changes_30)

        lines.append("── After Alert Fires: Price Movement ──")
        lines.append(f"  {'Window':<12} {'Moved Favorably':<18} {'Avg Change':<14} {'Median':<14}")
        lines.append(f"  {'10s':<12} {pct(positive_10, n):<18} {avg(alert_changes_10)*100:>+.4f}%{'':6} {median(alert_changes_10)*100:>+.4f}%")
        lines.append(f"  {'30s':<12} {pct(positive_30, n):<18} {avg(alert_changes_30)*100:>+.4f}%{'':6} {median(alert_changes_30)*100:>+.4f}%")
        lines.append(f"  {'60s':<12} {pct(positive_60, n):<18} {avg(alert_changes_60)*100:>+.4f}%{'':6} {median(alert_changes_60)*100:>+.4f}%")
        lines.append(f"  (Note: 'favorably' = price moved in any positive direction, not trade direction)")
        lines.append("")

    # By venue count (net heavy venues)
    lines.append("── Price Change by Net Heavy Venues (30s window, alert rows) ──")
    for v in sorted(venue_changes_30.keys()):
        vals = venue_changes_30[v]
        if len(vals) < 10:
            continue
        pos = sum(1 for c in vals if c > 0)
        lines.append(f"  Venues={v:>+2d}:  {len(vals):>7,} rows  Avg={avg(vals)*100:>+.4f}%  Positive={pct(pos, len(vals))}")
    lines.append("")

    # By hour (alert rows)
    lines.append("── Alerts by Hour (UTC) ──")
    for h in sorted(hour_alert_count.keys()):
        if h < 0:
            continue
        vals = [c for c in hour_changes_30[h]]
        alert_vals = []
        # We need to re-scan for alert-only hour changes
        # Use hour_alert_count for count, and approximate with all rows
        count = hour_alert_count[h]
        pos = sum(1 for c in vals if c > 0)
        lines.append(f"  {h:02d}:00 UTC:  {count:>5,} alerts  Avg 30s chg={avg(vals)*100:>+.4f}%  Positive={pct(pos, len(vals))}")
    lines.append("")

    # By symbol (alert rows, 30s change)
    lines.append("── Alert Performance by Symbol (30s price change) ──")
    for sym in sorted(sym_changes_30, key=lambda s: len(sym_changes_30[s]), reverse=True):
        vals = sym_changes_30[sym]
        if len(vals) < 5:
            continue
        pos = sum(1 for c in vals if c > 0)
        lines.append(f"  {sym:8s}  {len(vals):>5,} alerts  Avg={avg(vals)*100:>+.4f}%  Positive={pct(pos, len(vals))}  Median={median(vals)*100:>+.4f}%")
    lines.append("")

    # Volume impact
    lines.append("── Volume Impact on Alert Outcome (30s) ──")
    for bucket in ["low (<50K)", "med (50-200K)", "high (200K+)"]:
        vals = vol_buckets[bucket]
        if not vals:
            continue
        pos = sum(1 for c in vals if c > 0)
        lines.append(f"  {bucket:>14s}:  {len(vals):>5,} alerts  Avg={avg(vals)*100:>+.4f}%  Positive={pct(pos, len(vals))}")
    lines.append("")

    # Near-miss analysis
    if near_miss_changes:
        pos = sum(1 for c in near_miss_changes if c > 0)
        lines.append("── Near-Miss Analysis (no alert, but |venues| >= 3) ──")
        lines.append(f"  Count: {len(near_miss_changes):,}  Positive 30s: {pct(pos, len(near_miss_changes))}  Avg: {avg(near_miss_changes)*100:>+.4f}%")
        lines.append(f"  (If this is significantly better than random, your threshold may be too strict)")
        lines.append("")

    return "\n".join(lines)


# ── Section 2: Live Trade Analysis (penny_basing.db) ─────────────────────────

def analyze_live_trades():
    if not Path(DB_PATH).exists():
        return "⚠️  penny_basing.db not found. No live trade data available.\n"

    lines = []
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Check if live_trades table exists
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='live_trades'")
    if not c.fetchone():
        conn.close()
        return "⚠️  live_trades table not found in DB.\n"

    # Get column info
    c.execute("PRAGMA table_info(live_trades)")
    columns = [col[1] for col in c.fetchall()]

    # Fetch all live trades
    c.execute("SELECT * FROM live_trades ORDER BY timestamp")
    rows = c.fetchall()

    if not rows:
        conn.close()
        return "⚠️  No live trades recorded.\n"

    # Build dicts
    trades = []
    for row in rows:
        trade = dict(zip(columns, row))
        trades.append(trade)

    lines.append("=" * 65)
    lines.append("  SECTION 2: LIVE TRADE ANALYSIS (penny_basing.db)")
    lines.append("=" * 65)
    lines.append(f"Total live trades:  {len(trades):,}")

    # Date range
    ts_col = "timestamp"
    if ts_col in columns:
        first = ts_to_date(trades[0].get(ts_col, 0))
        last = ts_to_date(trades[-1].get(ts_col, 0))
        lines.append(f"Date range:         {first} → {last}")
    lines.append("")

    # PnL analysis
    pnl_col = None
    for candidate in ["pnl", "realized_pnl", "profit"]:
        if candidate in columns:
            pnl_col = candidate
            break

    if pnl_col:
        pnls = [float(t.get(pnl_col, 0) or 0) for t in trades]
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p < 0]
        flat = [p for p in pnls if p == 0]

        lines.append("── PnL Summary ──")
        lines.append(f"  Total PnL:        ${sum(pnls):,.2f}")
        lines.append(f"  Winners:          {len(winners)} ({pct(len(winners), len(pnls))})")
        lines.append(f"  Losers:           {len(losers)} ({pct(len(losers), len(pnls))})")
        lines.append(f"  Flat:             {len(flat)}")
        if winners:
            lines.append(f"  Avg winner:       ${avg(winners):,.4f}")
            lines.append(f"  Largest winner:   ${max(winners):,.4f}")
        if losers:
            lines.append(f"  Avg loser:        ${avg(losers):,.4f}")
            lines.append(f"  Largest loser:    ${min(losers):,.4f}")
        if winners and losers:
            lines.append(f"  Win/Loss ratio:   {abs(avg(winners)/avg(losers)):.2f}")
        lines.append("")

        # PnL by symbol
        sym_col = None
        for candidate in ["symbol", "sym"]:
            if candidate in columns:
                sym_col = candidate
                break

        if sym_col:
            sym_pnls = defaultdict(list)
            for t in trades:
                sym_pnls[t.get(sym_col, "?")].append(float(t.get(pnl_col, 0) or 0))

            lines.append("── PnL by Symbol ──")
            for sym in sorted(sym_pnls, key=lambda s: sum(sym_pnls[s]), reverse=True):
                vals = sym_pnls[sym]
                w = sum(1 for v in vals if v > 0)
                lines.append(f"  {sym:8s}  {len(vals):>4} trades  PnL=${sum(vals):>+8,.2f}  WinRate={pct(w, len(vals))}")
            lines.append("")

        # PnL by hour
        if ts_col in columns:
            hour_pnls = defaultdict(list)
            for t in trades:
                h = ts_to_hour(t.get(ts_col, 0))
                hour_pnls[h].append(float(t.get(pnl_col, 0) or 0))

            lines.append("── PnL by Hour (UTC) ──")
            for h in sorted(hour_pnls.keys()):
                if h < 0:
                    continue
                vals = hour_pnls[h]
                w = sum(1 for v in vals if v > 0)
                lines.append(f"  {h:02d}:00  {len(vals):>4} trades  PnL=${sum(vals):>+8,.2f}  WinRate={pct(w, len(vals))}")
            lines.append("")

        # PnL by day of week
        if ts_col in columns:
            day_pnls = defaultdict(list)
            for t in trades:
                day = ts_to_weekday(t.get(ts_col, 0))
                day_pnls[day].append(float(t.get(pnl_col, 0) or 0))

            lines.append("── PnL by Day of Week ──")
            for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
                if day in day_pnls:
                    vals = day_pnls[day]
                    w = sum(1 for v in vals if v > 0)
                    lines.append(f"  {day:12s}  {len(vals):>4} trades  PnL=${sum(vals):>+8,.2f}  WinRate={pct(w, len(vals))}")
            lines.append("")

        # PnL by date (daily breakdown)
        if ts_col in columns:
            date_pnls = defaultdict(list)
            for t in trades:
                d = ts_to_date(t.get(ts_col, 0))
                date_pnls[d].append(float(t.get(pnl_col, 0) or 0))

            lines.append("── Daily PnL Breakdown ──")
            for d in sorted(date_pnls.keys()):
                vals = date_pnls[d]
                w = sum(1 for v in vals if v > 0)
                lines.append(f"  {d}  {len(vals):>4} trades  PnL=${sum(vals):>+8,.2f}  WinRate={pct(w, len(vals))}")
            lines.append("")

    # Trade side analysis
    side_col = None
    for candidate in ["side", "direction", "action"]:
        if candidate in columns:
            side_col = candidate
            break

    if side_col and pnl_col:
        side_pnls = defaultdict(list)
        for t in trades:
            side_pnls[t.get(side_col, "?")].append(float(t.get(pnl_col, 0) or 0))

        lines.append("── PnL by Side/Direction ──")
        for side in sorted(side_pnls.keys()):
            vals = side_pnls[side]
            w = sum(1 for v in vals if v > 0)
            lines.append(f"  {side:12s}  {len(vals):>4} trades  PnL=${sum(vals):>+8,.2f}  WinRate={pct(w, len(vals))}")
        lines.append("")

    # List all columns for context
    lines.append(f"── DB Columns: {', '.join(columns)} ──")
    lines.append("")

    # Account history if available
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='account_history'")
    if c.fetchone():
        c.execute("SELECT COUNT(*) FROM account_history")
        ah_count = c.fetchone()[0]
        if ah_count > 0:
            c.execute("SELECT MIN(timestamp), MAX(timestamp), MIN(day_pnl), MAX(day_pnl) FROM account_history")
            ah_min_ts, ah_max_ts, ah_min_pnl, ah_max_pnl = c.fetchone()
            lines.append("── Account History ──")
            lines.append(f"  Records:      {ah_count:,}")
            lines.append(f"  Date range:   {ts_to_date(ah_min_ts or 0)} → {ts_to_date(ah_max_ts or 0)}")
            lines.append(f"  Day PnL range: ${ah_min_pnl or 0:,.2f} to ${ah_max_pnl or 0:,.2f}")
            lines.append("")

    conn.close()
    return "\n".join(lines)


# ── Section 3: Strategy Recommendations Prompt ───────────────────────────────

def build_prompt_section():
    lines = []
    lines.append("=" * 65)
    lines.append("  SECTION 3: QUESTIONS FOR LLM ANALYSIS")
    lines.append("=" * 65)
    lines.append("""
Based on the data above, please analyze:

1. ENTRY QUALITY: Which venue counts, volumes, and times of day
   produce the best win rates? Should I adjust thresholds?

2. EXIT TIMING: Are losers held too long vs winners? What does
   the hold-time data suggest about exit strategy?

3. SYMBOL PERFORMANCE: Should I stop trading any symbols?
   Any symbols I should focus on?

4. TIME FILTERS: Are there hours I should avoid entirely?

5. SPECIFIC PARAMETER SUGGESTIONS: Based on the data, give me
   concrete numbers to change (e.g., "raise venue threshold
   from 4 to 5 during 14:00-15:00 UTC").

6. RISK MANAGEMENT: Is my position sizing appropriate given
   the win rate and avg winner/loser?
""")
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    report = []

    report.append("=" * 65)
    report.append(f"  WEEKLY TRADING STRATEGY REPORT")
    report.append(f"  Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    report.append("=" * 65)
    report.append("")

    # Section 1: Training data (market snapshots)
    print("Analyzing training data...")
    report.append(analyze_training_data())

    # Section 2: Live trades (actual P&L)
    print("Analyzing live trades...")
    report.append(analyze_live_trades())

    # Section 3: LLM prompt
    report.append(build_prompt_section())

    full_report = "\n".join(report)

    with open(OUT_FILE, "w") as fh:
        fh.write(full_report)

    print(f"\nReport written to {OUT_FILE}")
    print(f"Lines: {len(full_report.splitlines())}")
    print(f"Size: {len(full_report):,} bytes")
    print(f"\nPaste the contents of {OUT_FILE} into your LLM conversation for analysis.")


if __name__ == "__main__":
    main()
