import sqlite3
import pandas as pd
import json
import os
import sys

def run_log_backtest_fast(log_path="grok.log", db_path="penny_basing.db"):
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
        
    # Group by symbol quickly
    chart_by_sym = {}
    for ts, sym, h, l in chart_rows:
        if sym not in chart_by_sym:
            chart_by_sym[sym] = []
        chart_by_sym[sym].append((ts, h, l))
        
    # Sort each symbol's data by timestamp
    for sym in chart_by_sym:
        # unique by timestamp
        unique_candles = {}
        for ts, h, l in chart_by_sym[sym]:
            unique_candles[ts] = (h, l)
        chart_by_sym[sym] = sorted([(ts, unique_candles[ts][0], unique_candles[ts][1]) for ts in unique_candles.keys()])
        
    all_ts = [r[0] for r in chart_rows]
    min_ts, max_ts = min(all_ts), max(all_ts)
    
    print("Fetching alerts from database in the same timeframe...")
    conn = sqlite3.connect(db_path)
    query = f"""
    SELECT timestamp, symbol, direction, price 
    FROM alerts 
    WHERE timestamp >= {min_ts} AND timestamp <= {max_ts}
    ORDER BY timestamp ASC
    """
    alerts_df = pd.read_sql_query(query, conn)
    conn.close()
    
    if alerts_df.empty:
        print("No alerts found in this timeframe.")
        return
        
    print(f"Found {len(alerts_df)} alerts. Running +/- $0.01 simulation (Fast Mode)...")
    
    wins = 0
    losses = 0
    total_pnl = 0.0
    
    # Iterate with pure python dicts/lists for massive speedup
    for row in alerts_df.itertuples(index=False):
        alert_time = float(row.timestamp)
        symbol = row.symbol
        direction = row.direction
        entry_price = float(row.price)
        
        candles = chart_by_sym.get(symbol, [])
        if not candles: continue
            
        if direction == 'ask-heavy': # Short
            take_profit = entry_price - 0.01
            stop_loss = entry_price + 0.01
        else: # Long
            take_profit = entry_price + 0.01
            stop_loss = entry_price - 0.01
            
        trade_result = None
        for ts, high, low in candles:
            if ts < alert_time: continue
            if ts > alert_time + 10800: break # 3 hours max hold
            
            if direction == 'ask-heavy': # Short
                if high >= stop_loss:
                    trade_result = -0.01
                    break
                if low <= take_profit:
                    trade_result = 0.01
                    break
            else: # Long
                if low <= stop_loss:
                    trade_result = -0.01
                    break
                if high >= take_profit:
                    trade_result = 0.01
                    break
                    
        if trade_result is not None:
             total_pnl += trade_result
             if trade_result > 0:
                 wins += 1
             else:
                 losses += 1
         
        # Progress indicator every 25k alerts
        if (wins + losses) % 25000 == 0 and (wins+losses) > 0:
             print(f"Processed {wins+losses} completions...")

    total_trades = wins + losses
    if total_trades > 0:
        win_rate = (wins / total_trades) * 100
        print(f"\n======== TARGET +/- $0.01 BACKTEST OUTCOME ========")
        print(f"Total Completed Trades: {total_trades}/{len(alerts_df)} alerts")
        print(f"Wins  (+$0.01/share): {wins}")
        print(f"Losses (-$0.01/share): {losses}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Net Realized PnL (per share): ${total_pnl:.4f}")
    else:
        print("No simulated trades hit the 1 cent target/stop loss based on the available chart data.")

if __name__ == "__main__":
    run_log_backtest_fast()
