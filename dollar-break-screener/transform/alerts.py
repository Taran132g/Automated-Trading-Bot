"""
Alert generation engine.

Triggers:
  - APPROACHING: score >= 75 AND price within $0.03 of $1.00 AND direction is down
  - BREAK:       price crosses below $1.00 from above

Deduplication: same alert type for same symbol suppressed for 15 min.
"""

import logging
import threading

from db.database import insert_alert, recent_alert_exists

log = logging.getLogger(__name__)

APPROACHING_SCORE_THRESHOLD = 75
APPROACHING_DISTANCE_THRESHOLD = 0.03
BREAK_PRICE = 1.00
DEDUP_MINUTES = 15


class AlertEngine:
    def __init__(self):
        self._prev_prices: dict[str, float] = {}
        self._lock = threading.Lock()

    def evaluate(self, ranked: list[dict]) -> list[dict]:
        """
        Evaluate ranked list from Scorer.rank() and fire alerts.
        Returns list of newly fired alert dicts.
        """
        fired = []
        with self._lock:
            for r in ranked:
                symbol = r["symbol"]
                price = r["current_price"]
                score = r["score"]
                direction = r["direction"]
                distance = r["distance_to_dollar"]
                prev_price = self._prev_prices.get(symbol)

                # APPROACHING alert
                if (
                    score >= APPROACHING_SCORE_THRESHOLD
                    and 0 <= distance <= APPROACHING_DISTANCE_THRESHOLD
                    and direction < 0
                    and not recent_alert_exists(symbol, "APPROACHING", DEDUP_MINUTES)
                ):
                    insert_alert(symbol, "APPROACHING", price, score)
                    fired.append({"symbol": symbol, "type": "APPROACHING", "price": price, "score": score})
                    log.info("APPROACHING alert: %s @ $%.4f (score=%.1f)", symbol, price, score)

                # BREAK alert: price just crossed below $1.00
                if (
                    prev_price is not None
                    and prev_price >= BREAK_PRICE
                    and price < BREAK_PRICE
                    and not recent_alert_exists(symbol, "BREAK", DEDUP_MINUTES)
                ):
                    insert_alert(symbol, "BREAK", price, score)
                    fired.append({"symbol": symbol, "type": "BREAK", "price": price, "score": score})
                    log.info("BREAK alert: %s @ $%.4f (score=%.1f)", symbol, price, score)

                self._prev_prices[symbol] = price

        return fired
