import sqlite3
import pandas as pd
import json
import os
from statistics import mean

def run_winner_analysis(log_path="grok.log", db_path="penny_basing.db"):
    print("Reading grok.log for 1-minute chart data...")
    chart_rows = []
    
    if not os.path.exists(log_path):
        print(f"Log path {log_path} not found.")
        return
        
    with open(log_path, 'r') as f:
        for line in f:
            if "CHART_DEBUG" in line:
                try:
                    json_str = line[line.find('{'):]
                    data = json.loads(json_str)
                    if data.get('event') == 'CHART_DEBUG':
                        payload = data.get('payload', {})
                        symbol = data.get('symbol')
                        ts_ms = payload.get('CHART_TIME_MILLIS')
                        if ts_ms:
                            ts_sec = ts_ms / 1000.0
                            chart_rows.append((ts_sec, symbol, float(payload.get('HIGH_PRICE', 0.0)), float(payload.get('LOW_PRICE', 0.0))))
                except Exception:
                    pass
                    
    if not chart_rows:
        print("No chart data extracted from log.")
        return
        
    # Group by symbol
    chart_by_sym = {}
    for ts, sym, h, l in chart_rows:
        if sym not in chart_by_sym:
            chart_by_sym[sym] = []
        chart_by_sym[sym].append((ts, h, l))
        
    # Sort and deduplicate
    for sym in chart_by_sym:
        unique_candles = {}
        for ts, h, l in chart_by_sym[sym]:
            unique_candles[ts] = (h, l)
        chart_by_sym[sym] = sorted([(ts, unique_candles[ts][0], unique_candles[ts][1]) for ts in unique_candles.keys()])
        
    all_ts = [r[0] for r in chart_rows]
    min_ts, max_ts = min(all_ts), max(all_ts)
    
    print("Fetching winning live trades from database...")
    conn = sqlite3.connect(db_path)
    query = f"""
    SELECT timestamp, symbol, side, qty, price, entry_price, pnl 
    FROM live_trades 
    WHERE timestamp >= {min_ts} AND timestamp <= {max_ts}
    AND side IN ('SELL', 'COVER')
    ORDER BY timestamp ASC
    """
    trades_df = pd.read_sql_query(query, conn)
    
    entry_query = f"""
    SELECT timestamp, symbol, side, price 
    FROM live_trades 
    WHERE timestamp >= {min_ts} AND timestamp <= {max_ts}
    AND side IN ('BUY', 'SHORT')
    ORDER BY timestamp ASC
    """
    entries_df = pd.read_sql_query(entry_query, conn)
    conn.close()
    
    if trades_df.empty:
        print("No live trades found in this timeframe.")
        return

    # Filter only WINNING TRADES
    winning_trades = trades_df[trades_df['pnl'] > 0]
    print(f"Found {len(winning_trades)} winning trades in the time window.")
    
    better_exits_during = 0
    better_exits_after_15 = 0
    better_exits_after_60 = 0
    
    missed_profits_during = []
    missed_profits_after_15 = []
    missed_profits_after_60 = []
    
    for row in winning_trades.itertuples(index=False):
        exit_time = float(row.timestamp)
        symbol = row.symbol
        side = row.side 
        exit_price = float(row.price)
        entry_price = float(row.entry_price)
        actual_profit_per_share = abs(exit_price - entry_price) # Positive since it's a winner
        
        valid_entries = entries_df[(entries_df['symbol'] == symbol) & (entries_df['timestamp'] < exit_time)]
        if valid_entries.empty:
            continue
        entry_time = float(valid_entries.iloc[-1]['timestamp'])
        
        candles = chart_by_sym.get(symbol, [])
        if not candles: continue
            
        during_candles = [c for c in candles if c[0] >= entry_time and c[0] <= exit_time]
        after_5_candles = [c for c in candles if c[0] > exit_time and c[0] <= exit_time + 300]
        after_10_candles = [c for c in candles if c[0] > exit_time and c[0] <= exit_time + 600]
        
        is_long = side == 'SELL'
        
        # 1. Did we give back profits during the hold? (Peak MFE > Exit Profit)
        max_profit_during = 0.0
        if during_candles:
            if is_long:
                max_profit_during = max([c[1] for c in during_candles]) - entry_price
            else:
                max_profit_during = entry_price - min([c[2] for c in during_candles])
                
        if max_profit_during > actual_profit_per_share + 0.005: # At least half a cent better
            better_exits_during += 1
            missed_profits_during.append(max_profit_during - actual_profit_per_share)
            
        # 2. Would holding 5 mins have yielded more?
        max_profit_after_5 = 0.0
        if after_5_candles:
            if is_long:
                max_profit_after_5 = max([c[1] for c in after_5_candles]) - entry_price
            else:
                max_profit_after_5 = entry_price - min([c[2] for c in after_5_candles])
                
        if max_profit_after_5 > actual_profit_per_share + 0.005:
            better_exits_after_15 += 1
            missed_profits_after_15.append(max_profit_after_5 - actual_profit_per_share)
            
        # 3. Would holding 10 mins have yielded more?
        max_profit_after_10 = 0.0
        if after_10_candles:
            if is_long:
                max_profit_after_10 = max([c[1] for c in after_10_candles]) - entry_price
            else:
                max_profit_after_10 = entry_price - min([c[2] for c in after_10_candles])
                
        if max_profit_after_10 > actual_profit_per_share + 0.005:
            better_exits_after_60 += 1
            missed_profits_after_60.append(max_profit_after_10 - actual_profit_per_share)
            
    total_winners = len(winning_trades)
    
    print("\n" + "="*50)
    print(f"ANALYSIS OF {total_winners} WINNING TRADES")
    print("="*50)
    
    if total_winners == 0:
        return
        
    pc_during = (better_exits_during / total_winners) * 100
    print(f"1. Did the trade peak significantly higher BEFORE the AI told us to exit?")
    print(f"   Yes: {better_exits_during} trades ({pc_during:.1f}%) gave back at least $0.005/share of peak unrealized profit.")
    if missed_profits_during:
        print(f"   -> Average profit given back: ${mean(missed_profits_during):.4f}/share")
        
    print("\n   Conclusion:")
    if pc_during > 50:
         print("   The AI exits late. By the time the reversal alert fires, the stock has already retraced heavily. A trailing stop in profit would be better than waiting for the reverse alert.")
    else:
         print("   The AI exits gracefully near the peak. You are capturing the majority of the move before the retracement kills your gains.")

    pc_after_15 = (better_exits_after_15 / total_winners) * 100
    print(f"\n2. Would holding for 5 MINUTES after the exit alert yield more profit?")
    print(f"   Yes: {better_exits_after_15} trades ({pc_after_15:.1f}%) continued to run after the AI told us to sell.")
    if missed_profits_after_15:
        print(f"   -> Average additional profit missed: ${mean(missed_profits_after_15):.4f}/share")

    pc_after_60 = (better_exits_after_60 / total_winners) * 100
    print(f"\n3. Would holding for 10 MINUTES after the exit alert yield more profit?")
    print(f"   Yes: {better_exits_after_60} trades ({pc_after_60:.1f}%) continued to run.")
    if missed_profits_after_60:
        print(f"   -> Average additional profit missed: ${mean(missed_profits_after_60):.4f}/share")
        
    print("\n   Conclusion:")
    if pc_after_15 > 50 or pc_after_60 > 50:
         print("   The AI is firing exit alerts too early and leaving meat on the bone. The trend actually continues the majority of the time.")
    else:
         print("   The AI is making the right call to exit when it does. If you held past the alert, you would lose money over 50% of the time as the trend has officially reversed.")
    print("="*50)

if __name__ == "__main__":
    run_winner_analysis()
