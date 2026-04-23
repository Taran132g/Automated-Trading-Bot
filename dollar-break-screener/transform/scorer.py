"""
Momentum scoring engine.

Scores each stock 0–100 based on weighted sub-scores:
  - Proximity score (40%): linear scale from $1.15 (0 pts) to $1.00 (40 pts)
  - Trend score     (30%): negative slope over 15 min → higher score
  - Velocity score  (20%): faster descent → higher score
  - Volume score    (10%): higher relative volume → higher score

Returns a sorted list of scored records, updated every SCORE_INTERVAL seconds
by the caller (stream.py).
"""

import threading
from db.database import insert_snapshot, get_universe

PROX_WEIGHT = 0.40
TREND_WEIGHT = 0.30
VEL_WEIGHT = 0.20
VOL_WEIGHT = 0.10

# Proximity thresholds
PROX_MAX_DIST = 0.15   # $1.15 → 0 pts
PROX_MIN_DIST = 0.00   # $1.00 → full pts


def _proximity_score(distance: float) -> float:
    """distance = price - 1.00. Between 0 and 0.15, linearly scaled to 0–40."""
    if distance <= PROX_MIN_DIST:
        return 40.0
    if distance >= PROX_MAX_DIST:
        return 0.0
    return round(40.0 * (1 - distance / PROX_MAX_DIST), 2)


def _normalize(values: list[float], invert: bool = False) -> list[float]:
    """Min-max normalize a list to [0, 1]. Optionally invert (higher raw → lower norm)."""
    if not values:
        return values
    mn, mx = min(values), max(values)
    if mx == mn:
        return [0.5] * len(values)
    normed = [(v - mn) / (mx - mn) for v in values]
    if invert:
        normed = [1 - v for v in normed]
    return normed


class Scorer:
    def __init__(self):
        self._last_ranked: list[dict] = []
        self._lock = threading.Lock()

    def rank(self, universe_stats: list[dict]) -> list[dict]:
        """
        Score and rank a list of stats dicts from Tracker.get_all_stats().
        Returns sorted list (highest score first).
        Also persists snapshots to SQLite.
        """
        if not universe_stats:
            return []

        # Only score stocks that are above $0.80 and at most $1.15 (within range)
        stats = [s for s in universe_stats if 0.80 <= s["current_price"] <= 1.15]
        if not stats:
            return []

        # Trend: slope is $/min; negative = down. We want most-negative → highest score.
        slopes = [s["direction"] for s in stats]
        slope_norm = _normalize(slopes, invert=True)  # most-negative → 1.0

        # Velocity: negative = descending. Most-negative → highest score.
        velocities = [s["velocity"] for s in stats]
        vel_norm = _normalize(velocities, invert=True)

        # Volume: use avg_volume as proxy for relative volume (absolute for now)
        volumes = [s["avg_volume"] for s in stats]
        vol_norm = _normalize(volumes)

        results = []
        for i, s in enumerate(stats):
            prox = _proximity_score(s["distance_to_dollar"])
            trend = round(slope_norm[i] * 30, 2)
            vel = round(vel_norm[i] * 20, 2)
            vol = round(vol_norm[i] * 10, 2)
            total = round(prox + trend + vel + vol, 2)

            # Trend arrow indicator
            if s["direction"] < -0.005:
                trend_arrow = "↓↓↓" if s["direction"] < -0.02 else "↓↓"
            elif s["direction"] > 0.005:
                trend_arrow = "↑"
            else:
                trend_arrow = "→"

            results.append({
                **s,
                "score": total,
                "trend_arrow": trend_arrow,
            })

        results.sort(key=lambda x: x["score"], reverse=True)

        # Persist snapshots for top 50
        for r in results[:50]:
            try:
                insert_snapshot(r["symbol"], r["current_price"], r["score"], r["distance_to_dollar"])
            except Exception:
                pass

        with self._lock:
            self._last_ranked = results

        return results

    def get_last_ranked(self) -> list[dict]:
        with self._lock:
            return list(self._last_ranked)
