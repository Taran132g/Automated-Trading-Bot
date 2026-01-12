import sqlite3
import os
from datetime import datetime
from collections import defaultdict

def calculate_fees_and_hourly_pnl(db_path):
    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_trades'")
        if not cursor.fetchone():
            print("Table 'paper_trades' does not exist in the database yet.")
            return

        cursor.execute("SELECT symbol, side, qty, timestamp, pnl FROM paper_trades ORDER BY timestamp ASC")
        rows = cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return
    finally:
        conn.close()

    if not rows:
        print("No trades found.")
        return

    fee_per_1000_shares = 0.25
    
    # Per-symbol stats
    symbol_stats = defaultdict(lambda: {"shares": 0, "trades": 0, "pnl": 0.0, "fees": 0.0})
    
    # For active hours calculation
    prev_ts = None
    active_seconds = 0.0
    
    print(f"{'Timestamp':<20} | {'Action':<10} | {'Symbol':<8} | {'Qty':<8} | {'PnL':<10} | {'Fee':<8}")
    print("-" * 90)

    for row in rows:
        symbol = row["symbol"]
        side = row["side"]
        qty = row["qty"]
        ts = row["timestamp"]
        pnl = row["pnl"] or 0.0
        
        dt_object = datetime.fromtimestamp(ts)
        time_str = dt_object.strftime("%Y-%m-%d %H:%M:%S")

        fee = (qty / 1000.0) * fee_per_1000_shares
        
        symbol_stats[symbol]["shares"] += qty
        symbol_stats[symbol]["trades"] += 1
        symbol_stats[symbol]["pnl"] += pnl
        symbol_stats[symbol]["fees"] += fee
        
        # Calculate active time (exclude gaps > 1 hour)
        if prev_ts is not None:
            gap = ts - prev_ts
            if gap <= 3600:  # 1 hour max gap
                active_seconds += gap
        prev_ts = ts
        
        print(f"{time_str:<20} | {side:<10} | {symbol:<8} | {qty:<8} | ${pnl:>8.2f} | ${fee:.4f}")

    active_hours = active_seconds / 3600.0

    # Summary
    print("-" * 90)
    print(f"\n{'='*90}")
    print("SUMMARY BY SYMBOL")
    print(f"{'='*90}")
    print(f"{'Symbol':<8} | {'Trades':<8} | {'Shares':<10} | {'Gross PnL':<12} | {'Fees':<10} | {'Net PnL':<12} | {'$/Hour':<10}")
    print("-" * 90)

    total_shares = 0
    total_trades = 0
    total_gross_pnl = 0.0
    total_fees = 0.0

    for sym in sorted(symbol_stats.keys()):
        stats = symbol_stats[sym]
        net_pnl = stats["pnl"] - stats["fees"]
        hourly = net_pnl / active_hours if active_hours > 0 else 0.0
        
        total_shares += stats["shares"]
        total_trades += stats["trades"]
        total_gross_pnl += stats["pnl"]
        total_fees += stats["fees"]
        
        print(f"{sym:<8} | {stats['trades']:<8} | {stats['shares']:<10,} | ${stats['pnl']:>10.2f} | ${stats['fees']:>8.2f} | ${net_pnl:>10.2f} | ${hourly:>8.2f}")

    total_net_pnl = total_gross_pnl - total_fees
    total_hourly = total_net_pnl / active_hours if active_hours > 0 else 0.0

    print("-" * 90)
    print(f"{'TOTAL':<8} | {total_trades:<8} | {total_shares:<10,} | ${total_gross_pnl:>10.2f} | ${total_fees:>8.2f} | ${total_net_pnl:>10.2f} | ${total_hourly:>8.2f}")
    print(f"\nACTIVE TRADING HOURS: {active_hours:.2f} hours")

if __name__ == "__main__":
    db_file = "penny_basing.db"
    calculate_fees_and_hourly_pnl(db_file)
