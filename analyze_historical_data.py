import pandas as pd
import numpy as np

def analyze_data(file_path):
    print(f"Loading data from {file_path}...")
    df = pd.read_csv(file_path)
    print(f"Loaded {len(df)} rows.")
    
    # Drop rows with NaN targets
    df = df.dropna(subset=['change_10s', 'change_30s', 'change_60s'])
    print(f"Valid rows after dropping NaNs: {len(df)}")
    
    alert_df = df[df['alert'] == 1]
    non_alert_df = df[df['alert'] == 0]
    
    print(f"\n--- ALERT VS NON-ALERT STATS ---")
    print(f"Total Alerts: {len(alert_df)}")
    if len(alert_df) > 0:
        for col in ['ratio', 'heavy_venues', 'vol_per_min']:
            print(f"Mean {col} | Alerts: {alert_df[col].mean():.2f} | Non-Alerts: {non_alert_df[col].mean():.2f}")
    
    print(f"\n--- ALERT PROFITABILITY ---")
    if len(alert_df) == 0:
        print("No alerts found in data.")
        return
        
    for timeframe in ['change_10s', 'change_30s', 'change_60s']:
        mean_change = alert_df[timeframe].mean() * 10000  # in basis points
        win_rate = (alert_df[timeframe] > 0).mean() * 100
        loss_rate = (alert_df[timeframe] < 0).mean() * 100
        print(f"{timeframe}: Mean Change = {mean_change:.2f} bps | Win Rate = {win_rate:.2f}% | Loss Rate = {loss_rate:.2f}%")

    print(f"\n--- CORRELATIONS WITH FUTURE PERFORMANCE (ONLY ALERTS) ---")
    features = ['ratio', 'total_bids', 'total_asks', 'heavy_venues', 'vol_per_min']
    targets = ['change_10s', 'change_30s', 'change_60s']
    corr = alert_df[features + targets].corr()
    for target in targets:
        print(f"\nCorrelations with {target}:")
        print(corr[target][features].sort_values(ascending=False).to_string())
        
    print(f"\n--- TOP DECILE ANALYSIS (Best entry signals) ---")
    print("What do the features look like for the top 10% most profitable alerts at 30s?")
    if len(alert_df) > 10:
        top_10_percent = alert_df.nlargest(int(len(alert_df) * 0.1), 'change_30s')
        bottom_10_percent = alert_df.nsmallest(int(len(alert_df) * 0.1), 'change_30s')
        for feature in features:
            print(f"{feature} | Top 10% Profits: {top_10_percent[feature].mean():.2f} | Bottom 10% Losses: {bottom_10_percent[feature].mean():.2f}")
            
    print("\n--- RATIO THRESHOLDS ---")
    # Let's test different ratio thresholds for alerts
    for threshold in [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]:
        subset = alert_df[alert_df['ratio'] >= threshold]
        if len(subset) > 0:
            win_rate = (subset['change_30s'] > 0).mean() * 100
            mean_change = subset['change_30s'].mean() * 10000
            print(f"Ratio >= {threshold:.1f}: Count = {len(subset)} | Win Rate 30s = {win_rate:.2f}% | Mean Diff = {mean_change:.2f} bps")

if __name__ == '__main__':
    analyze_data('training_data.csv')
