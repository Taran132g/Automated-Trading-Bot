import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import sys

def run_backtest(db_path="penny_basing.db"):
    conn = sqlite3.connect(db_path)
    
    # 1. Fetch alerts
    query = """
    SELECT timestamp, symbol, direction, price 
    FROM alerts 
    ORDER BY timestamp ASC
    """
    try:
        alerts_df = pd.read_sql_query(query, conn)
    except Exception as e:
        print(f"Error reading alerts: {e}")
        return

    if alerts_df.empty:
        print("No alerts found in database.")
        return

    # 2. Fetch chart data to simulate price action
    try:
        chart_query = "SELECT timestamp, symbol, high, low FROM chart_data ORDER BY timestamp ASC"
        chart_df = pd.read_sql_query(chart_query, conn)
    except Exception as e:
        print(f"Error reading chart_data: {e}")
        chart_df = pd.DataFrame()

    if chart_df.empty:
         print("No chart data available for simulation.")
         return
         
    # Group chart data by symbol for faster lookup
    print(f"Loaded {len(chart_df)} rows of chart data.")
    
    # Simulation metrics
    wins = 0
    losses = 0
    total_pnl = 0.0
    
    print(f"Starting simulation on {len(alerts_df)} historical alerts using $0.01 Target and $0.01 Stop Loss...")
    
    for _, row in alerts_df.iterrows():
        # Using string splitting because sqlite might have returned strings for timestamps
        alert_time = row['timestamp']
        if isinstance(alert_time, str):
             alert_time = pd.to_numeric(alert_time, errors='coerce')
             
        symbol = row['symbol']
        direction = row['direction']
        entry_price = float(row['price'])
        
        # Filter chart data for this symbol
        symbol_data = chart_df[chart_df['symbol'] == symbol]
        if symbol_data.empty:
            continue
            
        # Get data from entry to 3 hours later
        future_data = symbol_data[(symbol_data['timestamp'] > alert_time) & (symbol_data['timestamp'] <= alert_time + 10800)]
        
        if future_data.empty:
            continue
            
        # Target Prices
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
            
            if direction == 'ask-heavy': # Short position
                # Check if stop loss hit 
                if high >= stop_loss:
                    trade_result = -0.01
                    break
                # Check if take profit hit
                if low <= take_profit:
                    trade_result = 0.01
                    break
            else: # Long position
                # Check if stop loss hit
                if low <= stop_loss:
                    trade_result = -0.01
                    break
                # Check if take profit hit
                if high >= take_profit:
                    trade_result = 0.01
                    break
                    
        if trade_result is not None:
             total_pnl += trade_result
             if trade_result > 0:
                 wins += 1
             else:
                 losses += 1
                 
    conn.close()
    
    total_trades = wins + losses
    if total_trades > 0:
        win_rate = (wins / total_trades) * 100
        print(f"\n--- Backtest Results (Target +/- $0.01) ---")
        print(f"Total Trades Simulated: {total_trades}")
        print(f"Wins: {wins}")
        print(f"Losses: {losses}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Net PnL (Per Share): ${total_pnl:.4f}")
    else:
        print("\nNo trades met the criteria to hit +0.01 or -0.01 within 3 hours. Or missing chart data overlap.")

if __name__ == "__main__":
    run_backtest()
