"""
IBKR order executor — drop-in replacement for SchwabOrderExecutor.

Connects to a locally running IB Gateway or TWS instance via ib_insync.
All ib_insync async calls run on a dedicated background event loop so this
class is safe to call from any thread (e.g. the grok.py thread pool).

Environment variables
---------------------
IBKR_HOST        IB Gateway / TWS host          (default: 127.0.0.1)
IBKR_PORT        Connection port                 (default: 7497 = paper TWS)
                   7497 = paper TWS
                   7496 = live  TWS
                   4002 = paper IB Gateway
                   4001 = live  IB Gateway
IBKR_CLIENT_ID   Client ID — must be unique per connection (default: 10)
IBKR_ACCOUNT_ID  Account string e.g. DU1234567  (auto-detected if blank)
LIVE_DRY_RUN     If "true", skip all real order calls
"""

import asyncio
import logging
import os
import threading
import time
from typing import Dict, Optional

import pandas as pd

LOGGER = logging.getLogger("executors.ibkr")

# Side → IBKR action mapping
_ACTION = {
    "BUY":   "BUY",
    "SELL":  "SELL",
    "SHORT": "SELL",   # IBKR treats as sell-short when no long position
    "COVER": "BUY",    # IBKR treats as buy-to-cover when short
}

# IBKR fill statuses that mean the order is done
_FILLED_STATUSES = {"Filled", "ApiCancelled", "Cancelled", "Inactive"}
_WORKING_STATUSES = {"PendingSubmit", "PreSubmitted", "Submitted"}


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class IBKROrderExecutor:
    """Executor that routes orders through IB Gateway / TWS via ib_insync."""

    def __init__(
        self,
        *,
        dry_run: bool = False,
        host: Optional[str] = None,
        port: Optional[int] = None,
        client_id: Optional[int] = None,
        account_id: Optional[str] = None,
        name: str = "ibkr",
    ) -> None:
        self.dry_run = dry_run or _bool_env("LIVE_DRY_RUN", False)
        self.name = name
        self.account_id = account_id or os.getenv("IBKR_ACCOUNT_ID", "")

        self._host = host or os.getenv("IBKR_HOST", "127.0.0.1")
        self._port = port or int(os.getenv("IBKR_PORT", "7497"))
        self._client_id = client_id or int(os.getenv("IBKR_CLIENT_ID", "10"))

        # orderId → ib_insync Trade object (for cancel / status lookup)
        self._trades: Dict[int, object] = {}
        self._lock = threading.Lock()

        if not self.dry_run:
            self._start_ib()
        else:
            self.ib = None
            LOGGER.info("[%s] DRY-RUN mode — no IB connection", self.name)

    # ------------------------------------------------------------------
    # Event loop management
    # ------------------------------------------------------------------

    def _start_ib(self) -> None:
        """Start the ib_insync event loop in a daemon thread and connect."""
        from ib_insync import IB, util

        self._loop = asyncio.new_event_loop()
        self._ib_thread = threading.Thread(
            target=self._loop.run_forever, daemon=True, name="ib-event-loop"
        )
        self._ib_thread.start()

        self.ib = IB()

        future = asyncio.run_coroutine_threadsafe(
            self._connect_async(), self._loop
        )
        try:
            future.result(timeout=30)
        except Exception as exc:
            raise RuntimeError(
                f"[{self.name}] Failed to connect to IB Gateway at "
                f"{self._host}:{self._port} — {exc}\n"
                "Make sure IB Gateway or TWS is running and API connections are enabled."
            ) from exc

    async def _connect_async(self) -> None:
        from ib_insync import IB
        await self.ib.connectAsync(
            self._host, self._port, clientId=self._client_id, timeout=20
        )
        # Auto-detect account if not set
        if not self.account_id:
            accounts = self.ib.managedAccounts()
            if accounts:
                self.account_id = accounts[0]
        LOGGER.info(
            "[%s] Connected to IB Gateway %s:%d | account=%s | paper=%s",
            self.name, self._host, self._port, self.account_id,
            self._port in (7497, 4002),
        )

    def _run(self, coro, timeout: float = 15):
        """Run an async coroutine on the IB event loop and return the result."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_result(
        self,
        *,
        symbol: str,
        side: str,
        qty: int,
        order_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Dict:
        return {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "order_id": order_id,
            "location": None,
            "status_code": "200" if error is None else "500",
            "error": error,
            "dry_run": self.dry_run,
        }

    async def _place_order_async(self, symbol: str, qty: int, side: str, price: Optional[float] = None):
        from ib_insync import Stock, MarketOrder, LimitOrder

        action = _ACTION[side.upper()]
        contract = Stock(symbol, "SMART", "USD")
        await self.ib.qualifyContractsAsync(contract)

        if price is not None:
            order = LimitOrder(action, qty, round(price, 2))
        else:
            order = MarketOrder(action, qty)

        trade = self.ib.placeOrder(contract, order)
        # Brief yield so IB acknowledges the order
        await asyncio.sleep(0.3)
        return trade

    # ------------------------------------------------------------------
    # Public interface (mirrors SchwabOrderExecutor)
    # ------------------------------------------------------------------

    def submit_market(self, *, symbol: str, qty: int, side: str) -> Dict:
        if self.dry_run:
            LOGGER.info("[DRY-RUN] MARKET %s %s %s", side, qty, symbol)
            return self._make_result(symbol=symbol, side=side, qty=qty, order_id="dry-run")

        try:
            trade = self._run(self._place_order_async(symbol, qty, side))
            order_id = str(trade.order.orderId)
            with self._lock:
                self._trades[trade.order.orderId] = trade
            LOGGER.info("[%s] MARKET %s %s %s → order_id=%s", self.name, side, qty, symbol, order_id)
            return self._make_result(symbol=symbol, side=side, qty=qty, order_id=order_id)
        except Exception as exc:
            LOGGER.error("[%s] submit_market failed for %s: %s", self.name, symbol, exc)
            return self._make_result(symbol=symbol, side=side, qty=qty, error=str(exc))

    def submit_limit(self, *, symbol: str, qty: int, side: str, price: float) -> Dict:
        if self.dry_run:
            LOGGER.info("[DRY-RUN] LIMIT %s %s %s @ %.4f", side, qty, symbol, price)
            return self._make_result(symbol=symbol, side=side, qty=qty, order_id="dry-run")

        try:
            trade = self._run(self._place_order_async(symbol, qty, side, price=price))
            order_id = str(trade.order.orderId)
            with self._lock:
                self._trades[trade.order.orderId] = trade
            LOGGER.info("[%s] LIMIT %s %s %s @ %.4f → order_id=%s", self.name, side, qty, symbol, price, order_id)
            return self._make_result(symbol=symbol, side=side, qty=qty, order_id=order_id)
        except Exception as exc:
            LOGGER.error("[%s] submit_limit failed for %s: %s", self.name, symbol, exc)
            return self._make_result(symbol=symbol, side=side, qty=qty, error=str(exc))

    def cancel_order(self, order_id: str) -> bool:
        if self.dry_run:
            LOGGER.info("[DRY-RUN] cancel_order %s", order_id)
            return True

        try:
            oid = int(order_id)
            with self._lock:
                trade = self._trades.get(oid)
            if trade is None:
                LOGGER.warning("[%s] cancel_order: no trade found for id=%s", self.name, order_id)
                return False
            self._run(self._cancel_async(trade))
            LOGGER.info("[%s] cancel_order sent for %s", self.name, order_id)
            return True
        except Exception as exc:
            LOGGER.error("[%s] cancel_order failed for %s: %s", self.name, order_id, exc)
            return False

    async def _cancel_async(self, trade) -> None:
        self.ib.cancelOrder(trade.order)
        await asyncio.sleep(0.3)

    def cancel_all_orders(self) -> int:
        if self.dry_run:
            LOGGER.info("[DRY-RUN] cancel_all_orders")
            return 0

        try:
            trades = self._run(self._cancel_all_async())
            count = len(trades)
            LOGGER.info("[%s] cancel_all_orders: cancelled %d", self.name, count)
            return count
        except Exception as exc:
            LOGGER.error("[%s] cancel_all_orders failed: %s", self.name, exc)
            return 0

    async def _cancel_all_async(self):
        open_trades = self.ib.openTrades()
        for t in open_trades:
            self.ib.cancelOrder(t.order)
        await asyncio.sleep(0.5)
        return open_trades

    def fetch_quote(self, symbol: str) -> Optional[dict]:
        if self.dry_run:
            return None

        try:
            return self._run(self._fetch_quote_async(symbol))
        except Exception as exc:
            LOGGER.warning("[%s] fetch_quote failed for %s: %s", self.name, symbol, exc)
            return None

    async def _fetch_quote_async(self, symbol: str) -> Optional[dict]:
        from ib_insync import Stock

        contract = Stock(symbol, "SMART", "USD")
        await self.ib.qualifyContractsAsync(contract)
        ticker = self.ib.reqMktData(contract, "", False, False)
        await asyncio.sleep(0.5)
        self.ib.cancelMktData(contract)

        if ticker is None:
            return None

        def _safe(v):
            import math
            return None if (v is None or (isinstance(v, float) and math.isnan(v))) else v

        return {
            "lastPrice": _safe(ticker.last),
            "bidPrice":  _safe(ticker.bid),
            "askPrice":  _safe(ticker.ask),
            "closePrice": _safe(ticker.close),
        }

    def fetch_order_status(self, order_id: str) -> Dict:
        result: Dict = {"order_id": order_id, "status": None, "error": None}

        if self.dry_run:
            result["status"] = "Filled"
            result["dry_run"] = True
            return result

        try:
            return self._run(self._fetch_order_status_async(order_id))
        except Exception as exc:
            LOGGER.error("[%s] fetch_order_status failed for %s: %s", self.name, order_id, exc)
            result["error"] = str(exc)
            return result

    async def _fetch_order_status_async(self, order_id: str) -> Dict:
        result: Dict = {"order_id": order_id, "status": None, "error": None}
        try:
            oid = int(order_id)
        except ValueError:
            result["error"] = f"Invalid order_id: {order_id}"
            return result

        with self._lock:
            trade = self._trades.get(oid)

        # Also search open trades in case we lost the reference
        if trade is None:
            for t in self.ib.trades():
                if t.order.orderId == oid:
                    trade = t
                    break

        if trade is None:
            result["status"] = "Unknown"
            result["error"] = "Trade not found in local cache or open trades"
            return result

        order_state = trade.orderStatus
        result["status"] = order_state.status
        result["filled_quantity"] = order_state.filled
        result["avg_fill_price"] = order_state.avgFillPrice or None
        result["remaining"] = order_state.remaining
        return result

    def fetch_account_details(self) -> Dict[str, float]:
        if self.dry_run:
            return {
                "liquidation_value": 100_000.0,
                "cash_balance": 100_000.0,
                "day_pnl": 0.0,
                "buying_power": 100_000.0,
            }

        try:
            return self._run(self._fetch_account_async())
        except Exception as exc:
            LOGGER.error("[%s] fetch_account_details failed: %s", self.name, exc)
            return {}

    async def _fetch_account_async(self) -> Dict[str, float]:
        values = self.ib.accountValues(self.account_id)
        lookup: Dict[str, float] = {}
        for v in values:
            if v.currency == "USD" or v.currency == "BASE":
                try:
                    lookup[v.tag] = float(v.value)
                except (ValueError, TypeError):
                    pass

        return {
            "liquidation_value": lookup.get("NetLiquidation", 0.0),
            "cash_balance":      lookup.get("CashBalance", lookup.get("TotalCashBalance", 0.0)),
            "day_pnl":           lookup.get("DailyPnL", lookup.get("UnrealizedPnL", 0.0)),
            "buying_power":      lookup.get("BuyingPower", 0.0),
        }

    def fetch_positions(self) -> Dict[str, int]:
        if self.dry_run:
            return {}

        try:
            return self._run(self._fetch_positions_async())
        except Exception as exc:
            LOGGER.error("[%s] fetch_positions failed: %s", self.name, exc)
            return {}

    async def _fetch_positions_async(self) -> Dict[str, int]:
        positions = self.ib.positions(self.account_id)
        result = {}
        for pos in positions:
            sym = pos.contract.symbol
            qty = int(pos.position)
            if qty != 0:
                result[sym] = qty
        return result

    def get_price_history(self, symbol: str, days: int = 5) -> Optional[pd.DataFrame]:
        if self.dry_run:
            return None

        try:
            return self._run(self._fetch_history_async(symbol, days), timeout=30)
        except Exception as exc:
            LOGGER.error("[%s] get_price_history failed for %s: %s", self.name, symbol, exc)
            return None

    async def _fetch_history_async(self, symbol: str, days: int) -> Optional[pd.DataFrame]:
        from ib_insync import Stock

        contract = Stock(symbol, "SMART", "USD")
        await self.ib.qualifyContractsAsync(contract)

        bars = await self.ib.reqHistoricalDataAsync(
            contract,
            endDateTime="",
            durationStr=f"{days} D",
            barSizeSetting="1 min",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )

        if not bars:
            return None

        df = pd.DataFrame([{
            "timestamp": b.date.timestamp() * 1000 if hasattr(b.date, "timestamp") else b.date,
            "open":   b.open,
            "high":   b.high,
            "low":    b.low,
            "close":  b.close,
            "volume": b.volume,
        } for b in bars])

        return df if not df.empty else None
