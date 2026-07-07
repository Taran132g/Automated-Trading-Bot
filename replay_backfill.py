#!/usr/bin/env python3
"""Backfill: replay the historical alert stream through the FIXED maker model.

Why this exists
---------------
The 2026-06-26 → 07-01 paper runs recorded corrupted results: open positions
were vaporized on restart (stranding their cash), expired resting orders could
fill against stale prices, and the resting limit sat a full 1c OUTSIDE the ~1c
book instead of at the touch. This script regenerates `paper_trades` and
`paper_misses` from scratch by replaying every alert through the corrected
PaperTrader, so the persisted results reflect the fixed logic.

Forward-safety
--------------
The replay injects a per-symbol "last observed price" map and a simulated clock
into the trader, so a resting order can only ever resolve against a price that
was observed at or before its own timestamp — never a future row that already
sits in the alerts table.

Half-spread assumption
----------------------
The `alerts` table stores only `price` (grok's LAST_PRICE or mid), not the real
bid/ask. Observed spreads on these names were ~1c, so the near touch is ~0.5c
from the observed price. We therefore replay at half_spread = 0.5c by default
(rest AT the touch of a 1c book). The LIVE path forward uses the true touch that
grok now forwards; this approximation only applies to the historical replay.

Usage
-----
    python replay_backfill.py                 # 0.5c touch, regenerate DB tables
    BACKFILL_HALF_SPREAD_CENTS=1.0 python replay_backfill.py --dry-run
"""
import argparse
import importlib
import os
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

DB = os.getenv("BACKFILL_DB", "penny_basing.db")
HALF_SPREAD_CENTS = float(os.getenv("BACKFILL_HALF_SPREAD_CENTS", "0.5"))
FILL_WINDOW_SEC = float(os.getenv("BACKFILL_WINDOW_SEC", "30"))
POSITION_SIZE = int(os.getenv("BACKFILL_POSITION_SIZE", "100"))
STATE_FILE = "backfill_state.json"


def _build_trader():
    """Reload PaperTrader with maker config forced on for the replay."""
    import config_manager
    config_manager.load_config = lambda *a, **k: {
        "paper_position_size": POSITION_SIZE,
        "maker_enabled": True,
        "maker_half_spread_cents": HALF_SPREAD_CENTS,
        "maker_fill_window_sec": FILL_WINDOW_SEC,
    }
    import paper_trader
    importlib.reload(paper_trader)
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    pt = paper_trader.PaperTrader(db_path=DB, state_file=STATE_FILE)
    # Forward-safe price source + don't pollute the real observed-price audit
    # table with replayed rows.
    pt._price_source = {}
    pt._record_seen_price = lambda *a, **k: None
    return pt, paper_trader


def _load_alerts():
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        return c.execute(
            "SELECT rowid, timestamp, symbol, direction, price, ratio, heavy_venues "
            "FROM alerts ORDER BY timestamp ASC, rowid ASC"
        ).fetchall()


def _clear_results():
    with sqlite3.connect(DB) as c:
        c.execute("DELETE FROM paper_trades")
        c.execute("DELETE FROM paper_misses")
        c.commit()


def run(dry_run: bool):
    alerts = _load_alerts()
    if not alerts:
        print("No alerts to replay.")
        return

    backup = None
    if not dry_run:
        backup = f"{DB}.bak.{datetime.now():%Y%m%d_%H%M%S}"
        shutil.copy2(DB, backup)
        print(f"Backed up {DB} -> {backup}")
        _clear_results()

    pt, paper_trader = _build_trader()

    # In dry-run we still let the trader write to paper_trades (it opens its own
    # connections); to keep dry-run non-destructive we route it at an in-memory
    # copy instead. Simplest: for dry-run, operate on a temp copy of the DB.
    if dry_run:
        import tempfile
        tmp = os.path.join(tempfile.mkdtemp(), "replay.db")
        shutil.copy2(DB, tmp)
        with sqlite3.connect(tmp) as c:
            c.execute("DELETE FROM paper_trades")
            c.execute("DELETE FROM paper_misses")
            c.commit()
        pt.db_path = tmp

    print(f"Replaying {len(alerts)} alerts | half_spread={HALF_SPREAD_CENTS}c "
          f"window={FILL_WINDOW_SEC:.0f}s size={POSITION_SIZE}"
          f"{' (DRY-RUN)' if dry_run else ''}\n")

    for a in alerts:
        pt._now_override = float(a["timestamp"])
        pt._price_source[a["symbol"]] = float(a["price"])
        pt.process_alert(
            a["rowid"], a["symbol"], a["direction"], float(a["price"]),
            ratio=a["ratio"], heavy_venues=a["heavy_venues"],
        )

    # End-of-data sweep: advance the clock past the final deadline so any still
    # resting EXIT crosses the spread (gets flat) and any resting ENTRY expires
    # as a miss — exactly what the live liveness timer would do after close.
    pt._now_override = float(alerts[-1]["timestamp"]) + FILL_WINDOW_SEC + 1
    with pt._lock:
        pt._sweep_all_pending()

    _report(pt.db_path, pt)


def _report(db_path, pt):
    with sqlite3.connect(db_path) as c:
        c.row_factory = sqlite3.Row
        trades = c.execute(
            "SELECT timestamp, symbol, side, qty, price, pnl FROM paper_trades ORDER BY timestamp"
        ).fetchall()
        n_miss = c.execute("SELECT COUNT(*) FROM paper_misses").fetchone()[0]

    entries = [t for t in trades if t["side"] in ("SHORT", "BUY")]
    closes = [t for t in trades if t["side"] in ("SELL", "COVER")]
    passive_entries = len(entries)
    total_rested = passive_entries + n_miss  # entries that filled + entries that missed
    fill_rate = (passive_entries / total_rested * 100) if total_rested else 0.0

    realized = sum(t["pnl"] for t in trades)
    wins = [t for t in closes if t["pnl"] > 0]
    win_rate = (len(wins) / len(closes) * 100) if closes else 0.0

    print("=" * 60)
    print("BACKFILL RESULT (corrected maker logic)")
    print("=" * 60)
    print(f"  Alerts replayed        : {sum(1 for _ in trades) and len(trades)} trades logged")
    print(f"  Entry orders rested    : {total_rested}")
    print(f"    ├─ passively filled  : {passive_entries}")
    print(f"    └─ missed (unfilled) : {n_miss}")
    print(f"  Passive fill rate      : {fill_rate:.1f}%   (backtest edge needs 35-65%)")
    print(f"  Round-trip closes      : {len(closes)}  (win rate {win_rate:.1f}%)")
    print(f"  Realized PnL           : ${realized:.2f}")
    if closes:
        cents = realized / (len(closes) * POSITION_SIZE) * 100
        print(f"  Avg per closed trip    : ${realized/len(closes):.2f}  ({cents:.2f}c/share)")
    print(f"  Ending cash            : ${pt.cash:,.2f}  (baseline $1,000,000.00)")
    # Cash should equal baseline + realized + open-position mark; with no open
    # positions cash-baseline must equal realized exactly (reconciliation check).
    open_positions = pt.positions
    print(f"  Open positions at end  : {len(open_positions)} {list(open_positions.keys())}")
    print()

    # Per-symbol
    by_sym = defaultdict(lambda: {"pnl": 0.0, "trips": 0})
    for t in closes:
        by_sym[t["symbol"]]["pnl"] += t["pnl"]
        by_sym[t["symbol"]]["trips"] += 1
    print("  Per-symbol (closed round-trips):")
    for sym in sorted(by_sym):
        d = by_sym[sym]
        cps = d["pnl"] / (d["trips"] * POSITION_SIZE) * 100 if d["trips"] else 0
        print(f"    {sym:5s}  trips={d['trips']:3d}  pnl=${d['pnl']:8.2f}  {cps:+.2f}c/share")

    # Per-day
    by_day = defaultdict(float)
    for t in trades:
        day = datetime.fromtimestamp(t["timestamp"]).strftime("%Y-%m-%d")
        by_day[day] += t["pnl"]
    print("\n  Per-day realized PnL:")
    for day in sorted(by_day):
        print(f"    {day}  ${by_day[day]:8.2f}")
    print("=" * 60)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Replay against a temp copy; do not touch the live DB.")
    args = ap.parse_args()
    run(dry_run=args.dry_run)
