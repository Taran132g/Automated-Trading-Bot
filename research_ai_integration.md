# AI Integration Strategy: From Rules to Probabilities

## Executive Summary
Currently, `grok.py` uses a **Deterministic Rule-Based System**. It triggers alerts when specific, hardcoded conditions are met (e.g., "Exchange Imbalance >= 4" AND "Volume > 100k").

To move to an **AI/ML-based System**, we shift to a **Probabilistic Approach**. Instead of "If X > 4, then Buy", the logic becomes "Based on current inputs (X, Volume, Time), the Probability of Profit is 85%. Since 85% > Threshold, Buy."

## 1. Recommended Approach: Supervised Learning (Classification)

For your specific algorithmic trading setup (order book imbalances, high frequency), **Gradient Boosted Decision Trees (XGBoost or LightGBM)** or **Random Forests** are the industry standard for a first iteration.

### Why not Deep Learning (Neural Nets) yet?
- **Speed**: Decision trees are extremely fast for inference (microseconds), crucial for your real-time loop.
- **Tabular Data**: Your inputs (Book Ratios, Venue Counts, Volume) are structured "tabular" data, where trees often outperform raw neural nets.
- **Interpretability**: It is easier to see *why* a tree made a decision (feature importance) than a neural net.

## 2. The Model: What are we predicting?

We want to train a model to answer: **"If I enter a trade NOW, will it be profitable in T seconds?"**

- **Inputs (Features):**
    - `bid_ask_ratio`: (Total Bids / Total Asks)
    - `venue_imbalance`: (Bid Heavy Venues - Ask Heavy Venues)
    - `volume_velocity`: (`vol_per_min`)
    - `spread`: (Ask Price - Bid Price)
    - `time_of_day`: (Hour, Minute)
    - `recent_volatility`: (High - Low over last 60s)
    - **Lagged Features**: The same values from 1 second ago, 5 seconds ago (to capture momentum).

- **Output (Labels):**
    - `1` (Buy): Price increased by > $0.02 in the next 60 seconds.
    - `0` (Hold/Ignore): Price stayed flat or dropped.
    - `-1` (Sell/Short): Price decreased by > $0.02 in the next 60 seconds.

## 3. Implementation Roadmap

### Phase 1: Data Collection (The "Feature Store")
AI models are only as good as their data. Currently, you only log *Alerts*. We need to log *Non-Alerts* too (snapshots of the market when we *didn't* trade), so the model learns what "Noise" looks like.

**Action:** Modify `grok.py` to write a "State Snapshot" to a CSV or Parquet file every 1-5 seconds.
```csv
timestamp, symbol, bid_vol, ask_vol, ratio, heavy_venues, price
10:00:01,  ABC,    5000,    1000,    5.0,   3,            1.05
10:00:02,  ABC,    5100,    900,     5.6,   4,            1.05
...
```

### Phase 2: Offline Training
Once you have ~1-2 weeks of data:
1.  **Label the Data**: Write a script to look forward in time (e.g., 1 minute) for each row and determine if price went UP, DOWN, or FLAT.
2.  **Train Model**: Use Python libraries (`scikit-learn`, `xgboost`).
    ```python
    model = XGBClassifier()
    model.fit(X_train, y_train)
    ```
3.  **Evaluate**: Check "Precision" (accuracy when it predicts Buy) vs "Recall" (how many opportunities it found).

### Phase 3: Online Inference (The "AI Logic")
Replace the `if` statements in `grok.py` with the model.

**Current Code:**
```python
if metrics.bid_heavy_venues >= metrics.ask_heavy_venues + 4:
    trigger_alert()
```

**New AI Code:**
```python
# Create feature vector from current state
features = [metrics.ratio, metrics.bid_heavy_venues, vol_per_min, ...]

# Get probability from loaded model
probability = model.predict_proba([features])[0][1] # Probability of "UP" class

# Dynamic Threshold
if probability > 0.85:
    trigger_alert()
```

## 4. Specific Libraries & Tools

-   **Data Storage**: `pandas` (for CSV/Parquet handling).
-   **Machine Learning**: `scikit-learn` (RandomForest), `xgboost` (Gradient Boosting).
-   **Model Serialization**: `joblib` (to save the trained model to a file like `model.pkl` so `grok.py` can load it).

## 5. Weights Application
If you want a simpler step before full AI, you can use **Weighted Scoring**:

`Score = (Weight_A * Ratio) + (Weight_B * Venue_Count) + (Weight_C * Volume)`


## 6. Random Forest Strategy: "Weighing Parameters"

To address your request for **finding optimal parameter weights for success**, Random Forest is an excellent choice because it provides **Feature Importance** scores out of the box.

### The Concept
Instead of guessing whether `Exchange Imbalance` (e.g., 4 vs 3) is more important than `Bid/Ask Ratio` (e.g., 20x vs 10x), we train a model on your past trades and ask: *"Which features best predicted a profitable trade?"*

### Step-by-Step Research Plan

#### A. Data Preparation (The Missing Piece)
Currently, `penny_basing.db` stores `alerts` (triggers) and `live_trades` (outcomes).
- **Target Variable (y)**: Did the trade make money?
    - `1` (Success): PnL > $0.00
    - `0` (Failure): PnL <= $0.00
- **Features (X)**:
    - `ratio`: Bid/Ask Ratio
    - `total_bids` / `total_asks`: Raw liquidity
    - `heavy_venues`: Number of exchanges favoring the direction
    - `vol_per_min`: Velocity of trading
    - `range_cents`: Volatility metric
    - `spread`: Bid-Ask spread

**Crucial Gap**: We currently only save alerts that *triggered* a trade (or at least passed the initial filter). To build a robust model, we need to log **"Near Misses"** — situations where the bot *almost* traded but didn't (e.g., ratio was 15x but threshold is 20x). This helps the model learn the difference between "Good" and "Bad" market conditions, not just "Good" vs "Better".

#### B. Model Selection: Random Forest Classifier
Why this model?
1.  **Feature Importance**: It explicitly tells you which columns (Ratio, Volume, Venues) contributed most to the decision.
2.  **Non-Linear**: It captures complex relationships (e.g., "High Ratio is good, BUT only if Volume is also high").
3.  **Robust**: It's less prone to overfitting than a single decision tree.

#### C. Training Workflow (Offline)
1.  **Export Data**: `sqlite3 penny_basing.db "SELECT * FROM alerts JOIN live_trades ..."` to CSV.
2.  **Train**:
    ```python
    from sklearn.ensemble import RandomForestClassifier
    
    # X = [ratio, heavy_venues, vol_per_min, range_cents]
    # y = [1 if pnl > 0 else 0]
    
    clf = RandomForestClassifier(n_estimators=100)
    clf.fit(X_train, y_train)
    ```
3.  **Analyze Weights**:
    ```python
    print(clf.feature_importances_)
    # Output: [Ratio: 0.15, Venues: 0.40, Volume: 0.25, Range: 0.20]
    ```
    *Insight*: "Oh, `heavy_venues` (0.40) is twice as important as `ratio` (0.15). We should focus on optimizing the venue count threshold!"

#### D. Application (No Code Changes Yet)
Once you have these insights, you don't even need to deploy the AI immediately. You can:
1.  **Manually Adjust Config**: If the model says `vol_per_min` is the strongest predictor of loss, you can increase your `min_volume` threshold.
2.  **Hybrid Approach**: Use the AI to *filter* your existing logic. "Only take the trade if `RandomForest_Probability > 0.65`".

### Next Expected Actions
To proceed with this research, we would need to:
1.  **Enable "Snapshots"**: Start logging market state even when *no alert* is triggered (every 1-5 seconds) to build a background dataset.
2.  **run_analysis.py**: Create a script to perform the "Feature Importance" analysis on your existing `live_trades` data (even if limited) to give you an initial "Weighting Report".


## Training Data Recovery (Post-Reset)
Since the main database was reset, we are recovering training data from the server's raw execution logs (`grok.log` ~8.6GB).

### Extraction Status
A script `extract_training_data.py` is running on the server to parse these logs into a clean CSV.
- **Source**: `/root/taranveer-singh.github.io/grok.log`
- **Output**: `/root/taranveer-singh.github.io/training_data.csv`
- **Estimated Rows**: ~500,000+ examples

### How to Download the Data
Once the script finishes (check via `ssh root@157.245.8.48 "pgrep -f extract_training_data.py"` - if empty, it's done), run this locally:

```bash
scp root@157.245.8.48:~/taranveer-singh.github.io/training_data.csv ./training_data.csv
```

### Dataset Schema
The CSV contains features and future targets:
- **Features**: `ratio`, `total_bids`, `total_asks`, `heavy_venues`, `vol_per_min`, `imbalance_duration`
- **Targets**: `change_10s`, `change_30s`, `change_60s` (Percentage price change after the alert)
