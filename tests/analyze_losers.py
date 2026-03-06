import sqlite3
import pandas as pd
import json
import os
from statistics import mean

def run_loser_analysis(log_path="grok.log", db_path="penny_basing.db"):
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
    
    print("Fetching losing live trades from database...")
    conn = sqlite3.connect(db_path)
    # Get all closing trades
    query = f"""
    SELECT timestamp, symbol, side, qty, price, entry_price, pnl 
    FROM live_trades 
    WHERE timestamp >= {min_ts} AND timestamp <= {max_ts}
    AND side IN ('SELL', 'COVER')
    ORDER BY timestamp ASC
    """
    trades_df = pd.read_sql_query(query, conn)
    
    # Needs entry times, so we fetch entries too
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

    # Filter only LOSING TRADES
    losing_trades = trades_df[trades_df['pnl'] < 0]
    print(f"Found {len(losing_trades)} losing trades in the time window.")
    
    in_profit_during = 0
    in_profit_after = 0
    max_profits_during = []
    max_profits_after = []
    
    # Loop over losers
    for row in losing_trades.itertuples(index=False):
        exit_time = float(row.timestamp)
        symbol = row.symbol
        side = row.side # SELL means we were LONG. COVER means we were SHORT.
        exit_price = float(row.price)
        entry_price = float(row.entry_price)
        
        # Find entry time
        # The closest BUY/SHORT before this exit
        valid_entries = entries_df[(entries_df['symbol'] == symbol) & (entries_df['timestamp'] < exit_time)]
        if valid_entries.empty:
            continue
        entry_time = float(valid_entries.iloc[-1]['timestamp'])
        
        candles = chart_by_sym.get(symbol, [])
        if not candles: continue
            
        # Analysis 1: During the Trade (Entry -> Exit)
        during_candles = [c for c in candles if c[0] >= entry_time and c[0] <= exit_time]
        
        # Analysis 2: After the Trade (Exit -> Exit + 5 mins)
        after_candles = [c for c in candles if c[0] > exit_time and c[0] <= exit_time + 300]
        
        is_long = side == 'SELL'
        
        # Max profit during trade
        max_profit_during = 0.0
        if during_candles:
            if is_long:
                peak_price = max([c[1] for c in during_candles]) # max High
                max_profit_during = peak_price - entry_price
            else:
                valley_price = min([c[2] for c in during_candles]) # min Low
                max_profit_during = entry_price - valley_price
                
        if max_profit_during > 0:
            in_profit_during += 1
            max_profits_during.append(max_profit_during)
            
        # Max profit after trade
        max_profit_after = 0.0
        if after_candles:
            if is_long:
                peak_price = max([c[1] for c in after_candles])
                max_profit_after = peak_price - entry_price
            else:
                valley_price = min([c[2] for c in after_candles])
                max_profit_after = entry_price - valley_price
                
        if max_profit_after > 0:
            in_profit_after += 1
            max_profits_after.append(max_profit_after)
            
    total_losers = len(losing_trades)
    
    print("\n" + "="*50)
    print(f"ANALYSIS OF {total_losers} LOSING TRADES")
    print("="*50)
    
    if total_losers == 0:
        return
        
    pc_during = (in_profit_during / total_losers) * 100
    print(f"1. Were they in profit before stopping out?")
    print(f"   Yes: {in_profit_during} trades ({pc_during:.1f}%)")
    if max_profits_during:
        print(f"   -> Average Peak Profit before loss: ${mean(max_profits_during):.4f}/share")
        print(f"   -> Max Peak Profit before loss: ${max(max_profits_during):.4f}/share")
        
    print("\n   Conclusion:")
    if pc_during > 50:
         print("   The bot is consistently letting winning trades turn into losing trades. A trailing stop or take profit could fix this.")
    else:
         print("   Most losing trades were simply wrong from the start and immediately went negative.")

    pc_after = (in_profit_after / total_losers) * 100
    print(f"\n2. Did they recover if held for 5 MINUTES after taking the loss?")
    print(f"   Yes: {in_profit_after} trades ({pc_after:.1f}%)")
    if max_profits_after:
        print(f"   -> Average Peak Profit if held: ${mean(max_profits_after):.4f}/share")
        print(f"   -> Max Peak Profit if held: ${max(max_profits_after):.4f}/share")
        
    print("\n   Conclusion:")
    if pc_after > 50:
         print("   The stop loss is too tight or premature. Market noise is shaking you out right before the trend corrects.")
    else:
         print("   Taking the loss was mathematically correct the majority of the time, as it continued to plunge.")
    print("="*50)

if __name__ == "__main__":
    run_loser_analysis()
