"""
train_model.py
--------------
Trains a RandomForestRegressor to predict the PERCENTAGE PRICE CHANGE
30 seconds after an order-book imbalance snapshot.

Output  : model.pkl  (loaded by grok.py / live_trader.py at runtime)
Metric  : Mean Absolute Error + R²  (vs binary accuracy before)
Inference: model.predict([features])[0]  -> float, e.g. 0.0035 = +0.35%
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
import joblib
import sys

TARGET      = "change_30s"     # predict 30-second % price change
FEATURES    = [
    "ratio",
    "total_bids",
    "total_asks",
    "heavy_venues",
    "vol_per_min",
]

# Optional: also available in new CSV from extract_training_data.py
EXTRA_FEATURES = ["alert"]     # 1 if an alert fired near this snapshot


def train():
    try:
        print("Loading data…")
        df = pd.read_csv("training_data.csv")
        print(f"  Raw rows: {len(df):,}")

        # ── Feature selection ────────────────────────────────────────────────
        available_features = [f for f in FEATURES + EXTRA_FEATURES if f in df.columns]
        print(f"  Using features: {available_features}")

        X = df[available_features].copy()
        y = df[TARGET].copy()

        # Drop rows where target or any feature is missing
        mask = X.notna().all(axis=1) & y.notna()
        X, y = X[mask], y[mask]
        print(f"  Clean rows after dropping NaN: {len(X):,}")

        # ── Optional: clip extreme outliers (e.g. circuit-breaker spikes) ───
        p1, p99 = y.quantile(0.01), y.quantile(0.99)
        mask_clip = (y >= p1) & (y <= p99)
        X, y = X[mask_clip], y[mask_clip]
        print(f"  Rows after clipping outliers (1st–99th pct): {len(X):,}")
        print(f"  Target range: [{y.min():.4%}  to  {y.max():.4%}]")

        # ── Train / test split ───────────────────────────────────────────────
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        # ── Train ────────────────────────────────────────────────────────────
        print("\nTraining RandomForestRegressor…")
        model = RandomForestRegressor(
            n_estimators=200,
            max_depth=12,
            min_samples_leaf=10,   # prevents overfitting on rare events
            n_jobs=-1,
            random_state=42,
        )
        model.fit(X_train, y_train)

        # ── Evaluate ─────────────────────────────────────────────────────────
        y_pred = model.predict(X_test)
        mae   = mean_absolute_error(y_test, y_pred)
        r2    = r2_score(y_test, y_pred)

        print(f"\n── Evaluation ───────────────────────────────")
        print(f"  MAE  : {mae:.4%}  (avg prediction error in %)")
        print(f"  R²   : {r2:.4f}   (1.0 = perfect, 0 = no better than mean)")

        # Direction accuracy (did we at least get UP vs DOWN right?)
        direction_acc = np.mean(np.sign(y_pred) == np.sign(y_test))
        print(f"  Direction accuracy: {direction_acc:.1%}  (did we call UP/DOWN correctly?)")

        # ── Feature importance ───────────────────────────────────────────────
        importances = pd.DataFrame({
            "feature":    available_features,
            "importance": model.feature_importances_,
        }).sort_values("importance", ascending=False)
        print(f"\n── Feature Importance ───────────────────────")
        print(importances.to_string(index=False))

        # ── Save ─────────────────────────────────────────────────────────────
        print("\nSaving model to model.pkl…")
        joblib.dump(model, "model.pkl")
        print("Done.")

        # ── Show how to use at inference time ─────────────────────────────────
        print("""
── Inference Example ─────────────────────────────
  import joblib
  model = joblib.load('model.pkl')

  features = [ratio, total_bids, total_asks, heavy_venues, vol_per_min]
  pct_change = model.predict([features])[0]
  print(f"Predicted 30s price change: {pct_change:.3%}")
  # e.g.  Predicted 30s price change: +0.412%
""")

    except Exception as e:
        print(f"Error: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    train()
