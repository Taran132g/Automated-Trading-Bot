"""
extract_training_data.py
------------------------
Extracts ALL IMBALANCE_DEBUG rows from grok.log (per-book-update snapshots),
not just ALERT rows. This gives us:
  - Near-miss rows (market data when no alert fired)   -> alert=0
  - Alert rows (market data just before a trade fired) -> alert=1

For each row we look forward in time (per symbol) to compute:
  change_10s, change_30s, change_60s  (fractional price change)

MEMORY-SAFE: Uses a two-pass streaming approach so it can process
logs with 50M+ lines on a 2GB server without crashing.

  Pass 1: Build compact price timeline + alert set (lightweight dicts)
  Pass 2: Stream IMBALANCE_DEBUG rows and write CSV directly

Run on the server:
  python3 extract_training_data.py
"""

import json
import csv
import sys
import bisect
from collections import defaultdict
from datetime import datetime

LOG_FILE  = "grok.log"
OUT_FILE  = "training_data.csv"

LOOKAHEAD = [10, 30, 60]   # seconds to look forward for price change


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_ts(raw_line: str, brace_pos: int) -> float:
    """Parse timestamp from log prefix. Returns 0.0 on failure."""
    try:
        # "2026-02-20 16:07:57,688 - INFO - {json...}"
        # grab the datetime part before " - INFO"
        prefix = raw_line[:brace_pos]
        dash_info = prefix.find(" - ")
        if dash_info > 0:
            dt_str = prefix[:dash_info].strip()
        else:
            dt_str = prefix.strip()
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S,%f").timestamp()
    except Exception:
        return 0.0


def price_at(timeline_ts, timeline_px, target_ts):
    """Binary search for the closest price at or after target_ts."""
    idx = bisect.bisect_left(timeline_ts, target_ts)
    if idx < len(timeline_ts):
        return timeline_px[idx]
    return None


# ── Pass 1: Build price timeline + alert set (low memory) ───────────────────

def pass1_build_indexes(path: str):
    """
    Stream through the entire log once. Only store:
      - price_ts[symbol] = [timestamps...]  (sorted)
      - price_px[symbol] = [prices...]       (parallel array)
      - alert_set = set of (symbol, rounded_ts)

    Each entry is just a float + float = ~16 bytes.
    Even 5M price points = ~80MB — fits in 2GB easily.
    """
    price_ts = defaultdict(list)     # symbol -> [ts, ts, ...]
    price_px = defaultdict(list)     # symbol -> [price, price, ...]
    alert_set = set()                # (symbol, rounded_ts)

    row_count = 0
    relevant_count = 0

    print(f"Pass 1: Building price timeline from {path} ...")

    with open(path, "r", errors="replace") as fh:
        for raw in fh:
            row_count += 1
            if row_count % 5_000_000 == 0:
                print(f"  ... scanned {row_count:,} lines  ({relevant_count:,} relevant)")

            brace = raw.find("{")
            if brace == -1:
                continue

            # Quick pre-filter before JSON parse (much faster)
            if "IMBALANCE_DEBUG" not in raw and "ALERT" not in raw:
                continue

            try:
                payload = json.loads(raw[brace:])
            except json.JSONDecodeError:
                continue

            event = payload.get("event")
            if event not in ("IMBALANCE_DEBUG", "ALERT"):
                continue

            relevant_count += 1
            ts = _parse_ts(raw, brace)
            sym = payload.get("symbol") or payload.get("sym", "")
            price = payload.get("price", 0.0)

            if sym and price and ts:
                price_ts[sym].append(ts)
                price_px[sym].append(price)

            if event == "ALERT" and sym and ts:
                alert_set.add((sym, round(ts, 1)))

    print(f"  Pass 1 complete: {row_count:,} lines scanned, {relevant_count:,} relevant")
    for sym in sorted(price_ts):
        print(f"    {sym}: {len(price_ts[sym]):,} price points")
    print(f"    Alert timestamps: {len(alert_set):,}")

    return price_ts, price_px, alert_set


# ── Pass 2: Stream IMBALANCE_DEBUG rows → CSV ───────────────────────────────

def pass2_write_csv(path: str, price_ts, price_px, alert_set):
    """
    Stream through the log again. For each IMBALANCE_DEBUG row:
      - Look up forward prices using the pre-built timeline
      - Write directly to CSV (no in-memory accumulation)
    """
    fieldnames = [
        "timestamp", "symbol",
        "ratio", "total_bids", "total_asks",
        "heavy_venues", "vol_per_min",
        "price",
        "rolling_pi",
        "alert",
        "change_10s", "change_30s", "change_60s",
    ]

    written = 0
    skipped = 0
    row_count = 0

    print(f"\nPass 2: Writing training data to {OUT_FILE} ...")

    with open(OUT_FILE, "w", newline="") as out_fh, \
         open(path, "r", errors="replace") as in_fh:

        writer = csv.DictWriter(out_fh, fieldnames=fieldnames)
        writer.writeheader()

        for raw in in_fh:
            row_count += 1
            if row_count % 5_000_000 == 0:
                print(f"  ... scanned {row_count:,} lines  (written {written:,})")

            # Quick pre-filter
            if "IMBALANCE_DEBUG" not in raw:
                continue

            brace = raw.find("{")
            if brace == -1:
                continue

            try:
                payload = json.loads(raw[brace:])
            except json.JSONDecodeError:
                continue

            if payload.get("event") != "IMBALANCE_DEBUG":
                continue

            ts    = _parse_ts(raw, brace)
            sym   = payload.get("symbol") or payload.get("sym", "")
            bids  = payload.get("bids", 0)
            asks  = payload.get("asks", 0)
            ratio = round(bids / asks, 4) if asks else 0.0
            heavy = payload.get("bid_heavy", 0) - payload.get("ask_heavy", 0)
            vol   = payload.get("vol_per_min", 0.0)
            price = payload.get("price", 0.0)
            rolling_pi = payload.get("rolling_pi", 0.0)

            if not price or not sym or not ts:
                skipped += 1
                continue

            # Compute forward price changes
            sym_ts = price_ts.get(sym, [])
            sym_px = price_px.get(sym, [])
            changes = {}
            ok = True
            for sec in LOOKAHEAD:
                future_price = price_at(sym_ts, sym_px, ts + sec)
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
                "timestamp":    round(ts, 3),
                "symbol":       sym,
                "ratio":        ratio,
                "total_bids":   bids,
                "total_asks":   asks,
                "heavy_venues": heavy,
                "vol_per_min":  vol,
                "price":        price,
                "rolling_pi":   rolling_pi,
                "alert":        is_alert,
                **changes,
            })
            written += 1

            if written % 50_000 == 0:
                print(f"  ... {written:,} rows written")

    print(f"\nDone. Wrote {written:,} rows to {OUT_FILE}  (skipped {skipped:,})")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    price_ts, price_px, alert_set = pass1_build_indexes(LOG_FILE)
    pass2_write_csv(LOG_FILE, price_ts, price_px, alert_set)


if __name__ == "__main__":
    main()
