"""
WebSocket price ingestion — Charles Schwab edition.

Connects to Schwab's Streaming API, subscribes to QUOTE updates for the
universe of low-priced stocks, and writes raw trades to SQLite.

Schwab streaming uses a WebSocket with a JSON-over-socket protocol.
schwab-py wraps this via `schwab.streaming.StreamClient`.

Run directly:  python -m ingestion.stream
"""

import asyncio
import logging
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

import schwab
from dotenv import load_dotenv

from db.database import init_db, insert_trades, purge_old_trades
from ingestion.universe import refresh_universe, start_background_refresh, _get_client
from transform.tracker import Tracker
from transform.scorer import Scorer
from transform.alerts import AlertEngine

load_dotenv()
log = logging.getLogger(__name__)

MAX_DEQUE = 10_000
PERSIST_INTERVAL = 60   # seconds between SQLite flushes
SCORE_INTERVAL = 10     # seconds between scoring runs


class PriceStream:
    def __init__(self):
        self._buffers: dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_DEQUE))
        self._pending: list[dict] = []
        self._lock = threading.Lock()
        self._tracker = Tracker()
        self._scorer = Scorer()
        self._alert_engine = AlertEngine()
        self._symbols: list[str] = []
        self._stream_client: schwab.streaming.StreamClient | None = None

    # ── Schwab quote handler ──────────────────────────────────────────────────
    # Schwab QUOTE service fields:
    #   1=bid, 2=ask, 3=last, 8=total volume, 52=trade time (epoch ms)

    def _handle_quote(self, msg: dict) -> None:
        content = msg.get("content", [])
        rows = []
        for item in content:
            symbol = item.get("key")
            price = item.get("3")  # last price
            volume = item.get("8")  # cumulative volume
            ts_ms = item.get("52")  # trade time epoch ms

            if symbol is None or price is None:
                continue

            price = float(price)
            volume = float(volume) if volume is not None else None
            ts = (
                datetime.utcfromtimestamp(int(ts_ms) / 1000).isoformat()
                if ts_ms
                else datetime.utcnow().isoformat()
            )

            entry = {"symbol": symbol, "price": price, "volume": volume, "ts": ts}
            with self._lock:
                self._buffers[symbol].append(entry)
                self._pending.append(entry)

            self._tracker.update(symbol, price, ts, volume)
            rows.append(entry)

    # ── Periodic SQLite flush ─────────────────────────────────────────────────

    def _flush_loop(self):
        while True:
            time.sleep(PERSIST_INTERVAL)
            with self._lock:
                batch = self._pending.copy()
                self._pending.clear()
            if batch:
                try:
                    insert_trades(batch)
                    log.debug("Flushed %d quotes to SQLite", len(batch))
                except Exception as e:
                    log.error("SQLite flush error: %s", e)
            purge_old_trades(hours=24)

    # ── Periodic scoring + alert run ──────────────────────────────────────────

    def _score_loop(self):
        while True:
            time.sleep(SCORE_INTERVAL)
            try:
                universe_stats = self._tracker.get_all_stats()
                ranked = self._scorer.rank(universe_stats)
                self._alert_engine.evaluate(ranked)
            except Exception as e:
                log.error("Scoring error: %s", e)

    # ── Universe refresh callback ─────────────────────────────────────────────

    def _on_universe_refresh(self, symbols: list[str]) -> None:
        if not self._stream_client or not symbols:
            return
        self._symbols = symbols
        # Re-subscribe is handled by re-running the async subscription
        # on next reconnect; for running streams just update the tracker's
        # symbol awareness (no-op — tracker accepts any symbol that arrives)
        log.info("Universe refreshed: %d symbols", len(symbols))

    # ── Async streaming loop ──────────────────────────────────────────────────

    async def _stream_loop(self):
        client = _get_client()
        self._stream_client = schwab.streaming.StreamClient(client)

        await self._stream_client.login()
        log.info("Schwab stream connected")

        # Subscribe to QUOTE service for each symbol
        # Schwab caps a single subscription at ~500 symbols
        chunk_size = 500
        for i in range(0, len(self._symbols), chunk_size):
            chunk = self._symbols[i : i + chunk_size]
            await self._stream_client.level_one_equity_subs(
                symbols=chunk,
                fields=[
                    schwab.streaming.StreamClient.LevelOneEquityFields.BID_PRICE,
                    schwab.streaming.StreamClient.LevelOneEquityFields.ASK_PRICE,
                    schwab.streaming.StreamClient.LevelOneEquityFields.LAST_PRICE,
                    schwab.streaming.StreamClient.LevelOneEquityFields.TOTAL_VOLUME,
                    schwab.streaming.StreamClient.LevelOneEquityFields.TRADE_TIME_MILLIS,
                ],
            )

        self._stream_client.add_level_one_equity_handler(self._handle_quote)
        log.info("Subscribed to %d symbols", len(self._symbols))

        await self._stream_client.handle_message()  # blocks until disconnect

    # ── Entry point ───────────────────────────────────────────────────────────

    def run(self):
        init_db()

        log.info("Building initial universe…")
        self._symbols = refresh_universe()
        if not self._symbols:
            log.warning("Universe is empty — check credentials and market hours")

        threading.Thread(target=self._flush_loop, daemon=True, name="flush").start()
        threading.Thread(target=self._score_loop, daemon=True, name="scorer").start()
        start_background_refresh(callback=self._on_universe_refresh)

        # Async stream with outer retry loop
        backoff = 5
        while True:
            try:
                asyncio.run(self._stream_loop())
            except KeyboardInterrupt:
                log.info("Shutting down")
                break
            except Exception as e:
                log.error("Stream error: %s — retrying in %ds", e, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 120)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    PriceStream().run()
