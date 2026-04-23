"""
Price tracking module.

Maintains a rolling 30-minute window of trades per symbol and computes:
  - current_price
  - distance_to_dollar  (price - 1.00, so $1.07 → 0.07)
  - pct_from_dollar     (percentage distance)
  - direction           (linear regression slope over last 15 min, in $/min)
  - velocity            (average cents/min over last 5 min)
"""

import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

DOLLAR = 1.00
WINDOW_MINUTES = 30
SLOPE_MINUTES = 15
VEL_MINUTES = 5
MAX_TRADES = 10_000


class Tracker:
    def __init__(self):
        self._buffers: dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_TRADES))
        self._lock = threading.Lock()

    def update(self, symbol: str, price: float, ts: str, volume: float | None = None) -> None:
        entry = (ts, price, volume or 0.0)
        with self._lock:
            self._buffers[symbol].append(entry)

    def get_stats(self, symbol: str) -> dict | None:
        with self._lock:
            buf = list(self._buffers.get(symbol, []))
        if not buf:
            return None

        now = datetime.utcnow()
        window_start = now - timedelta(minutes=WINDOW_MINUTES)
        slope_start = now - timedelta(minutes=SLOPE_MINUTES)
        vel_start = now - timedelta(minutes=VEL_MINUTES)

        df = pd.DataFrame(buf, columns=["ts", "price", "volume"])
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_localize(None)
        df = df[df["ts"] >= window_start].sort_values("ts")

        if df.empty:
            return None

        current_price = df["price"].iloc[-1]
        distance = round(current_price - DOLLAR, 4)
        pct = round(distance / DOLLAR * 100, 2)

        # Direction: linear regression slope over last 15 min ($/min)
        slope_df = df[df["ts"] >= slope_start]
        direction = 0.0
        if len(slope_df) >= 3:
            t_sec = (slope_df["ts"] - slope_df["ts"].iloc[0]).dt.total_seconds().values
            p = slope_df["price"].values
            if t_sec[-1] > 0:
                coeffs = np.polyfit(t_sec / 60, p, 1)  # $/min
                direction = round(float(coeffs[0]), 6)

        # Velocity: (last_price - first_price) / elapsed_minutes over last 5 min
        vel_df = df[df["ts"] >= vel_start]
        velocity = 0.0
        if len(vel_df) >= 2:
            elapsed = (vel_df["ts"].iloc[-1] - vel_df["ts"].iloc[0]).total_seconds() / 60
            if elapsed > 0:
                velocity = round((vel_df["price"].iloc[-1] - vel_df["price"].iloc[0]) / elapsed, 6)

        avg_vol = df["volume"].mean() if not df["volume"].empty else 0.0

        return {
            "symbol": symbol,
            "current_price": current_price,
            "distance_to_dollar": distance,
            "pct_from_dollar": pct,
            "direction": direction,   # negative = trending down
            "velocity": velocity,     # negative = descending
            "avg_volume": avg_vol,
            "trade_count": len(df),
        }

    def get_all_stats(self) -> list[dict]:
        with self._lock:
            symbols = list(self._buffers.keys())
        results = []
        for sym in symbols:
            stats = self.get_stats(sym)
            if stats:
                results.append(stats)
        return results
