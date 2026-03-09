import os
import sqlite3
import pandas as pd
import sys
import argparse
from datetime import datetime, timedelta
from typing import Optional, Dict
from pathlib import Path
from dotenv import load_dotenv

# Add current directory to path for imports
sys.path.append(os.getcwd())

def run_backtest(symbol: str, days: int = 10, csv_path: Optional[str] = None):
    print(f"--- Starting Exhaustive Backtest for {symbol} ({days} days) ---")
    
    hist_df = None
    
    # 1. Fetch Price History
    if csv_path and os.path.exists(csv_path):
        print(f"Loading history from {csv_path}...")
        hist_df = pd.read_csv(csv_path)
    else:
        # Initialize Schwab Executor only if no CSV provided
        try:
            executor = SchwabOrderExecutor(dry_run=False, name="backtest")
            print(f"Fetching {days} days of history for {symbol} from Schwab...")
            hist_df = executor.get_price_history(symbol, days=days)
        except Exception as e:
            print(f"Error initializing Schwab client or fetching data: {e}")
            print("Try running with --csv BBAI_yfinance.csv instead.")
            return

    if hist_df is None or hist_df.empty:
        print(f"Could not load/fetch price history for {symbol}")
        return

    # Standardize timestamps to SECONDS
    # yfinance output usually has 'timestamp' or 'datetime' already
    if 'timestamp' in hist_df.columns:
        # If it's already in seconds skip, if it's in ms (like Schwab) divide
        if hist_df['timestamp'].max() > 2e9: 
            hist_df['timestamp'] = (hist_df['timestamp'] / 1000.0).astype(float)
    elif 'datetime' in hist_df.columns:
        hist_df['timestamp'] = pd.to_datetime(hist_df['datetime']).apply(lambda x: x.timestamp())
    
    min_ts = hist_df['timestamp'].min()
    max_ts = hist_df['timestamp'].max()
    print(f"Successfully loaded {len(hist_df)} candles from {datetime.fromtimestamp(min_ts)} to {datetime.fromtimestamp(max_ts)}")

    # 3. Fetch Historical Alerts from Database
    db_path = "penny_basing.db"
    conn = sqlite3.connect(db_path)
    
    query = """
    SELECT timestamp, symbol, direction, price 
    FROM alerts 
    WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?
    ORDER BY timestamp ASC
    """
    alerts_df = pd.read_sql_query(query, conn, params=(symbol, min_ts, max_ts))
    conn.close()

    if alerts_df.empty:
        print(f"No historical alerts found in {db_path} for {symbol} in the candle range.")
        return

    print(f"Found {len(alerts_df)} historical alerts to replay.")

    # 4. Initialize Pipeline in Backtest Mode
    cfg = PatternIntegrationConfig(
        min_confidence=0.40,
        block_strong_countertrend_entries=True,
        strong_countertrend_threshold=0.50,
        max_bars_per_symbol=1000 # Increase history for better pattern context
    )
    pipeline = IntegratedSignalPipeline(cfg, is_backtest=True)
    
    # 5. Simulation
    results = []
    current_alert_idx = 0
    total_alerts = len(alerts_df)
    
    # Pre-calculated future high/lows for PnL check
    # We turn the hist_df into a list of dicts for faster iteration
    candles = hist_df.to_dict('records')
    
    print("Replaying simulation...")
    for i, candle in enumerate(candles):
        # Feed the bar to the pipeline
        pipeline.on_new_bar(symbol, candle)
        
        # Check if there are alerts at or before this timestamp
        candle_ts = candle['timestamp']
        while current_alert_idx < len(alerts_df):
            alert = alerts_df.iloc[current_alert_idx].to_dict()
            if alert['timestamp'] <= candle_ts:
                # A. Pattern Enrichment
                enriched = pipeline.on_l2_alert(alert)
                decision = enriched.get("decision", "enter_or_manage")
                bias = enriched.get("chart_bias", "neutral")
                
                # if bias != "neutral":
                #     print(f"!!! [{datetime.fromtimestamp(alert['timestamp'])}] BBAI ALERT BIAS: {bias} (Decision: {decision})")
                
                # B. Outcome Simulation ($0.01 target/stop)
                entry_price = float(alert['price'])
                direction = alert['direction']
                
                # Dynamic sizing from pattern engine
                size_factor = float(enriched.get("size_factor", 1.0))
                
                target = entry_price + 0.01 if direction == 'bid-heavy' else entry_price - 0.01
                stop = entry_price - 0.01 if direction == 'bid-heavy' else entry_price + 0.01
                
                # B. Outcome Simulation ($0.01 target/stop)
                entry_price = float(alert['price'])
                direction = alert['direction']
                
                # Dynamic sizing from pattern engine
                size_factor = float(enriched.get("size_factor", 1.0))
                
                target = entry_price + 0.01 if direction == 'bid-heavy' else entry_price - 0.01
                stop = entry_price - 0.01 if direction == 'bid-heavy' else entry_price + 0.01
                
                baseline_pnl = 0.0
                sized_pnl = 0.0
                outcome = "timed_out"
                
                # Look forward up to 300 minutes (5 hours)
                for j in range(i + 1, min(i + 301, len(candles))):
                    future = candles[j]
                    high = future['high']
                    low = future['low']
                    
                    if direction == 'bid-heavy': # Long
                        if low <= stop:
                            baseline_pnl = -0.01
                            sized_pnl = -0.01 * size_factor
                            outcome = "loss"
                            break
                        if high >= target:
                            baseline_pnl = 0.01
                            sized_pnl = 0.01 * size_factor
                            outcome = "win"
                            break
                    else: # Short
                        if high >= stop:
                            baseline_pnl = -0.01
                            sized_pnl = -0.01 * size_factor
                            outcome = "loss"
                            break
                        if low <= target:
                            baseline_pnl = 0.01
                            sized_pnl = 0.01 * size_factor
                            outcome = "win"
                            break
                
                res = {
                    "timestamp": alert['timestamp'],
                    "direction": alert['direction'],
                    "price": entry_price,
                    "bias": bias,
                    "decision": decision,
                    "baseline_pnl": baseline_pnl,
                    "sized_pnl": sized_pnl,
                    "outcome": outcome,
                    "size_factor": size_factor,
                    "pattern": enriched.get("top_patterns", [{}])[0].get("pattern") if enriched.get("top_patterns") else "none"
                }
                results.append(res)
                current_alert_idx += 1
                
                if current_alert_idx % 1000 == 0:
                    # print(f"Replayed {current_alert_idx}/{total_alerts} alerts... (Last Bias: {bias})")
                    sys.stdout.flush()
            else:
                break

    # 6. Final Reporting
    if not results:
        print("No results to report.")
        return
        
    res_df = pd.DataFrame(results)
    
    # Baseline: Take ALL alerts with size 1.0
    total_baseline_pnl = res_df['baseline_pnl'].sum()
    
    # Filtered: Take ONLY non-skip alerts with sizing
    passed_df = res_df[res_df['decision'] != 'skip']
    total_filtered_pnl = passed_df['sized_pnl'].sum()
    
    # Analysis
    bias_counts = res_df['bias'].value_counts()
    win_rate_all = (len(res_df[res_df['outcome'] == 'win']) / len(res_df)) * 100 if len(res_df) > 0 else 0
    win_rate_filtered = (len(passed_df[passed_df['outcome'] == 'win']) / len(passed_df)) * 100 if len(passed_df) > 0 else 0
    outcome_counts = res_df['outcome'].value_counts().to_dict()

    print("\n" + "="*50)
    print(f"BACKTEST RESULTS: {symbol}")
    print("="*50)
    print(f"Total Alerts:   {len(res_df)}")
    print(f"Outcomes:       {outcome_counts}")
    print(f"Filter Rate:    {len(res_df) - len(passed_df)} trades blocked ({ (len(res_df) - len(passed_df))/len(res_df)*100:.1f}%)")
    print(f"Pattern Bias Distribution: {bias_counts.to_dict()}")
    print("-" * 30)
    print(f"BASELINE (All, Size 1.0): Win Rate {win_rate_all:.1f}% | Total PnL ${total_baseline_pnl:.4f}")
    print(f"FILTERED (Sel, Sizing):   Win Rate {win_rate_filtered:.1f}% | Total PnL ${total_filtered_pnl:.4f}")
    print("-" * 30)
    
    if total_filtered_pnl > total_baseline_pnl:
        print(f"SUCCESS: Filter + Sizing improved PnL by ${total_filtered_pnl - total_baseline_pnl:.4f}!")
    else:
        print(f"WARNING: Filter + Sizing reduced PnL by ${total_baseline_pnl - total_filtered_pnl:.4f}.")

    res_df.to_csv(f"backtest_detailed_{symbol}.csv", index=False)
    print(f"\nDetailed CSV: backtest_detailed_{symbol}.csv")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest Pattern Filter with PnL")
    parser.add_argument("--symbol", type=str, required=True)
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--csv", type=str, default=None, help="Path to local OHLCV CSV file")
    args = parser.parse_args()
    
    # Reload env here if needed, but it's done at top
    from data import PatternIntegrationConfig, IntegratedSignalPipeline
    from live_trader import SchwabOrderExecutor
    
    run_backtest(args.symbol, args.days, csv_path=args.csv)
