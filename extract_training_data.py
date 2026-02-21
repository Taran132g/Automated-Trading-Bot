"""
extract_training_data.py
------------------------
Extracts ALL IMBALANCE_DEBUG rows from grok.log (per-book-update snapshots),
not just ALERT rows. This gives us:
  - Near-miss rows (market data when no alert fired)   -> alert=0
  - Alert rows (market data just before a trade fired) -> alert=1

For each row we look forward in time (per symbol) to compute:
  change_10s, change_30s, change_60s  (fractional price change, e.g. 0.0035 = +0.35%)

These three columns become the regression target(s) in train_model.py.

Run on the server:
  python3 extract_training_data.py
"""

import json
import csv
import sys
from collections import defaultdict

LOG_FILE  = "grok.log"
OUT_FILE  = "training_data.csv"

LOOKAHEAD = [10, 30, 60]   # seconds to look forward for price change

# ── Parse ────────────────────────────────────────────────────────────────────

def parse_log(path: str):
    """
    Yield dicts for every IMBALANCE_DEBUG and ALERT line in the log.
    Each dict has keys: ts (float), event (str), plus all JSON payload fields.
    """
    with open(path, "r", errors="replace") as fh:
        for raw in fh:
            # Log format: "2024-01-15 10:00:01,123 - INFO - {json}"
            # Find the first '{' to locate the JSON payload
            brace = raw.find("{")
            if brace == -1:
                continue
            try:
                payload = json.loads(raw[brace:])
            except json.JSONDecodeError:
                continue

            event = payload.get("event")
            if event not in ("IMBALANCE_DEBUG", "ALERT"):
                continue

            # Parse timestamp from the log prefix  "2024-01-15 10:00:01,123"
            prefix = raw[:brace].strip(" -\t")
            try:
                # Remove trailing " - INFO" / " - WARNING" etc.
                dt_part = prefix.split("-")[0].strip()
                from datetime import datetime
                ts = datetime.strptime(dt_part, "%Y-%m-%d %H:%M:%S,%f").timestamp()
            except Exception:
                ts = 0.0

            payload["_ts"] = ts
            yield payload


# ── Build per-symbol price timeline ──────────────────────────────────────────

def build_price_timeline(rows):
    """
    Returns dict: symbol -> sorted list of (ts, price)
    Used to look up the price at ts+N seconds.
    """
    timeline = defaultdict(list)
    for r in rows:
        sym = r.get("symbol") or r.get("sym")
        price = r.get("price", 0.0)
        ts = r.get("_ts", 0.0)
        if sym and price and ts:
            timeline[sym].append((ts, price))
    for sym in timeline:
        timeline[sym].sort()
    return timeline


def price_at(timeline, sym, target_ts):
    """Binary search for the closest price at or after target_ts."""
    entries = timeline.get(sym, [])
    lo, hi = 0, len(entries) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if entries[mid][0] < target_ts:
            lo = mid + 1
        else:
            hi = mid
    if lo < len(entries):
        return entries[lo][1]
    return None


# ── Build alert timestamp set ─────────────────────────────────────────────────

def build_alert_set(rows):
    """Returns set of (sym, ts_rounded) for rows where event=ALERT."""
    alerts = set()
    for r in rows:
        if r.get("event") == "ALERT":
            sym = r.get("symbol") or r.get("sym")
            ts = round(r.get("_ts", 0.0), 1)
            if sym:
                alerts.add((sym, ts))
    return alerts


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"Reading {LOG_FILE} …  (this may take a while for large files)")

    all_rows = list(parse_log(LOG_FILE))
    print(f"  Parsed {len(all_rows):,} IMBALANCE_DEBUG + ALERT rows")

    timeline  = build_price_timeline(all_rows)
    alert_set = build_alert_set(all_rows)

    # Keep only IMBALANCE_DEBUG rows for the final dataset
    debug_rows = [r for r in all_rows if r.get("event") == "IMBALANCE_DEBUG"]
    print(f"  IMBALANCE_DEBUG rows: {len(debug_rows):,}")

    fieldnames = [
        "timestamp", "symbol",
        "ratio", "total_bids", "total_asks",
        "heavy_venues", "vol_per_min",
        "price",
        "alert",          # 1 if an ALERT fired within ±1s of this snapshot
        "change_10s", "change_30s", "change_60s",
    ]

    written = 0
    skipped = 0

    with open(OUT_FILE, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()

        for r in debug_rows:
            ts     = r.get("_ts", 0.0)
            sym    = r.get("symbol") or r.get("sym", "")
            bids   = r.get("bids", 0)
            asks   = r.get("asks", 0)
            ratio  = round(bids / asks, 4) if asks else 0.0
            heavy  = r.get("bid_heavy", 0) - r.get("ask_heavy", 0)  # net heavy venues
            vol    = r.get("vol_per_min", 0.0)
            price  = r.get("price", 0.0)

            if not price or not sym:
                skipped += 1
                continue

            # Compute forward price changes
            changes = {}
            ok = True
            for sec in LOOKAHEAD:
                future_price = price_at(timeline, sym, ts + sec)
                if future_price is None:
                    ok = False
                    break
                changes[f"change_{sec}s"] = round((future_price - price) / price, 6)

            if not ok:
                skipped += 1
                continue

            # Was an alert triggered near this snapshot?
            ts_key = round(ts, 1)
            is_alert = int(
                (sym, ts_key) in alert_set
                or (sym, round(ts - 0.1, 1)) in alert_set
                or (sym, round(ts + 0.1, 1)) in alert_set
            )

            writer.writerow({
                "timestamp":   round(ts, 3),
                "symbol":      sym,
                "ratio":       ratio,
                "total_bids":  bids,
                "total_asks":  asks,
                "heavy_venues": heavy,
                "vol_per_min": vol,
                "price":       price,
                "alert":       is_alert,
                **changes,
            })
            written += 1

            if written % 50_000 == 0:
                print(f"  … {written:,} rows written")

    print(f"\nDone. Wrote {written:,} rows to {OUT_FILE}  (skipped {skipped:,})")


if __name__ == "__main__":
    main()
