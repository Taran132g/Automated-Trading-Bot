import sqlite3
import pandas as pd
import json
import os

def run_log_backtest(log_path="grok.log", db_path="penny_basing.db"):
    print("Reading grok.log for 1-minute chart data...")
    chart_rows = []
    
    if not os.path.exists(log_path):
        print(f"Log path {log_path} not found.")
        return
        
    with open(log_path, 'r') as f:
        for line in f:
            if "CHART_DEBUG" in line:
                try:
                    # Find the JSON part
                    json_str = line[line.find('{'):]
                    data = json.loads(json_str)
                    
                    if data.get('event') == 'CHART_DEBUG':
                        payload = data.get('payload', {})
                        symbol = data.get('symbol')
                        
                        ts_ms = payload.get('CHART_TIME_MILLIS')
                        if ts_ms:
                            ts_sec = ts_ms / 1000.0
                            chart_rows.append({
                                'timestamp': ts_sec,
                                'symbol': symbol,
                                'high': payload.get('HIGH_PRICE', 0.0),
                                'low': payload.get('LOW_PRICE', 0.0)
                            })
                except Exception:
                    pass
                    
    chart_df = pd.DataFrame(chart_rows)
    if chart_df.empty:
        print("No chart data extracted from log.")
        return
        
    # Sort and remove duplicates from parsing overlaps
    chart_df = chart_df.sort_values(by=['timestamp']).drop_duplicates(subset=['timestamp', 'symbol'])
    print(f"Extracted {len(chart_df)} unique 1-minute candles from the log.")
    
    min_ts = chart_df['timestamp'].min()
    max_ts = chart_df['timestamp'].max()
    
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
        
    print(f"Found {len(alerts_df)} alerts. Running +/- $0.01 simulation...")
    
    wins = 0
    losses = 0
    total_pnl = 0.0
    
    # Track the outcome of trades that actually completed
    for _, row in alerts_df.iterrows():
        # Handle string timestamps from db if needed
        alert_time = float(row['timestamp'])
        symbol = row['symbol']
        direction = row['direction']
        entry_price = float(row['price'])
        
        symbol_data = chart_df[chart_df['symbol'] == symbol]
        if symbol_data.empty:
            continue
            
        future_data = symbol_data[symbol_data['timestamp'] >= alert_time]
        
        if future_data.empty:
            continue
            
        if direction == 'ask-heavy': # Short
            take_profit = entry_price - 0.01
            stop_loss = entry_price + 0.01
        else: # Long
            take_profit = entry_price + 0.01
            stop_loss = entry_price - 0.01
            
        trade_result = None
        for _, candle in future_data.iterrows():
            high = float(candle['high'])
            low = float(candle['low'])
            
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
    run_log_backtest()
