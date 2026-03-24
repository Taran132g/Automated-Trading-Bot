"""Bridge paper trading alerts to Schwab paperMoney/live orders.

This module tails the ``alerts`` table written by ``grok.py`` and turns the
flip-only logic from ``paper_trader.py`` into real Schwab order requests. By
default it targets the paperMoney environment: simply point
``SCHWAB_ACCOUNT_ID`` at your paper account hash and the script will place
market orders through the official REST API.

When ``grok.py`` runs inline with :class:`LiveTrader`, alerts never need to hit
SQLite; they can be delivered directly via the in-process callback. The polling
loop in this file remains for the cases where you run ``live_trader.py`` as a
standalone service (e.g., on a different host or to backfill older alerts).
"""
from __future__ import annotations

import argparse
import atexit
import json
import logging
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

import pandas as pd
from dotenv import load_dotenv
from schwab.auth import easy_client
from schwab.orders import equities as equity_orders
import config_manager
from telegram_notifier import TelegramNotifier

load_dotenv()

LOGGER = logging.getLogger("live_trader")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# Config helpers: these keep setup failures obvious so you don't place trades
# without the right Schwab credentials.
def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# Schwab's OAuth callback must be a full URL; this keeps mistakes user-friendly
# by explaining what went wrong instead of failing silently.
def _normalize_and_validate_callback(url: str) -> str:
    if not url:
        raise ValueError("SCHWAB_REDIRECT_URI is empty")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            f"Invalid SCHWAB_REDIRECT_URI '{url}'. Expected full URL like 'https://127.0.0.1:8182/'."
        )
    return url if url.endswith("/") else url + "/"


# Tiny parser for yes/no env vars (e.g., LIVE_DRY_RUN=1 turns off real orders)
def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class BoxedPositionError(Exception):
    """Raised when Schwab rejects an order due to a boxed position (Long + Short)."""
    pass

class SchwabOrderExecutor:
    """Thin wrapper around ``schwab-py`` order placement.

    Separating this layer keeps trading decisions (LiveTrader) and API calls
    (SchwabOrderExecutor) loosely coupled, which makes dry-run testing and
    error handling easier to follow.
    """

    def __init__(self, *, dry_run: bool = False, account_id: Optional[str] = None, token_path: Optional[str] = None, name: str = "default") -> None:
        self.dry_run = dry_run or _bool_env("LIVE_DRY_RUN", False)
        self.name = name  # Identifier for logging
        self.account_id = account_id or _require_env("SCHWAB_ACCOUNT_ID")
        api_key = _require_env("SCHWAB_CLIENT_ID")
        app_secret = _require_env("SCHWAB_APP_SECRET")
        redirect_uri = _normalize_and_validate_callback(_require_env("SCHWAB_REDIRECT_URI"))
        token_file = Path(token_path or os.getenv("SCHWAB_TOKEN_PATH", "./schwab_tokens.json"))

        LOGGER.info("[%s] Initializing Schwab client (account=%s, dry_run=%s)", self.name, self.account_id[-4:], self.dry_run)
        try:
            # Use non-interactive token refresh (headless-safe)
            from schwab.auth import client_from_token_file
            self.client = client_from_token_file(str(token_file), api_key, app_secret)
            LOGGER.info("[%s] Client created via token file (non-interactive)", self.name)
        except Exception as exc:
            raise RuntimeError(f"Failed to create Schwab client: {exc}") from exc

    def _send(self, builder, *, symbol: str, side: str, qty: int) -> Dict[str, Optional[str]]:
        payload = builder.build() if hasattr(builder, "build") else builder
        result = {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "order_id": None,
            "location": None,
            "status_code": None,
            "error": None,
            "dry_run": self.dry_run,
        }

        if self.dry_run:
            LOGGER.info("[DRY-RUN] %s %s %s", side, qty, symbol)
            return result

        max_429_retries = 3
        response = None
        for attempt in range(max_429_retries):
            try:
                response = self.client.place_order(self.account_id, payload)
            except Exception as exc:  # pragma: no cover - network interaction
                LOGGER.error("Order failed: %s", exc)
                result["error"] = str(exc)
                return result

            if response.status_code == 429 and attempt < max_429_retries - 1:
                wait = 2 ** attempt  # 1s, 2s on retries 1 and 2
                LOGGER.warning(
                    "429 Too Many Requests for %s %s %s (attempt %d/%d); retrying in %ds",
                    side, qty, symbol, attempt + 1, max_429_retries, wait,
                )
                time.sleep(wait)
                continue

            break

        result["status_code"] = str(response.status_code)
        location = response.headers.get("Location") if response else None
        if location:
            result["location"] = location
            if "/orders/" in location:
                result["order_id"] = location.rstrip("/").split("/")[-1]

        if not response or not (200 <= response.status_code < 300):
            LOGGER.error(
                "Order rejected (status=%s) for %s %s %s", response.status_code if response else "?", side, qty, symbol
            )
            result["error"] = response.text if response else "Unknown order error"
        else:
            LOGGER.info("Order accepted (id=%s) for %s %s %s", result["order_id"], side, qty, symbol)

        return result

    def cancel_order(self, order_id: str) -> bool:
        if self.dry_run:
            LOGGER.info("[DRY-RUN] Skip cancel order %s", order_id)
            return True

        cancel_one = getattr(self.client, "cancel_order", None)
        if cancel_one is None:
            LOGGER.warning("Schwab client does not expose cancel_order; attempting cancel_all")
            return self.cancel_all_orders()

        try:
            cancel_one(order_id, self.account_id)
            LOGGER.info("Cancel request sent for order %s", order_id)
            return True
        except Exception as exc:  # pragma: no cover - network interaction
            LOGGER.error("Failed to cancel order %s: %s", order_id, exc)
            return False

    def fetch_quote(self, symbol: str) -> Optional[dict]:
        if self.dry_run:
            return None

        fetch_quote = getattr(self.client, "get_quote", None)
        if fetch_quote is None:
            LOGGER.warning("Schwab client does not expose get_quote; skipping refresh")
            return None

        try:
            response = fetch_quote(symbol)
        except Exception as exc:  # pragma: no cover - network interaction
            LOGGER.warning("Quote fetch failed for %s: %s", symbol, exc)
            return None

        try:
            payload = response.json() if hasattr(response, "json") else None
        except Exception:
            payload = None

        if isinstance(payload, dict):
            return payload.get(symbol) or payload
        return None

    def fetch_order_status(self, order_id: str) -> Dict[str, Optional[str]]:
        result: Dict[str, Optional[str]] = {"order_id": order_id, "status": None, "error": None}

        if self.dry_run:
            result["status"] = "FILLED"
            result["dry_run"] = True
            return result

        fetch_order = getattr(self.client, "get_order", None)
        if fetch_order is None:
            result["error"] = "Schwab client does not expose get_order"
            return result

        try:
            response = fetch_order(order_id, self.account_id)
        except Exception as exc:  # pragma: no cover - network interaction
            LOGGER.error("Failed to fetch order %s: %s", order_id, exc)
            result["error"] = str(exc)
            return result

        result["status_code"] = str(getattr(response, "status_code", None))
        try:
            payload = response.json() if hasattr(response, "json") else None
        except Exception:
            payload = None

        if isinstance(payload, dict):
            status = payload.get("status") or payload.get("orderStatus") or payload.get("order_status")
            filled_qty = payload.get("filledQuantity") or payload.get("filled_quantity")
            avg_fill_price = payload.get("averageExecutionPrice") or payload.get("avg_execution_price")
            
            # Schwab often omits averageExecutionPrice but provides the fill price
            # inside orderActivityCollection[].executionLegs[].price
            if not avg_fill_price:
                try:
                    activities = payload.get("orderActivityCollection", [])
                    if activities:
                        legs = activities[0].get("executionLegs", [])
                        if legs:
                            avg_fill_price = legs[0].get("price")
                except (IndexError, KeyError, TypeError):
                    pass
            
            result["status"] = status
            result["filled_quantity"] = filled_qty
            result["avg_fill_price"] = avg_fill_price
            result["raw"] = payload
        else:
            result["raw"] = str(payload)

        return result

    def fetch_account_details(self) -> Dict[str, float]:
        """Fetch account balance and PnL details."""
        if self.dry_run:
            return {
                "liquidation_value": 100000.0,
                "cash_balance": 100000.0,
                "day_pnl": 0.0,
                "buying_power": 100000.0,
            }

        get_account = getattr(self.client, "get_account", None)
        if get_account is None:
            LOGGER.warning("Schwab client does not expose get_account")
            return {}

        try:
            # Request positions to get PnL data if needed, but for now just base details
            response = get_account(self.account_id, fields=[self.client.Account.Fields.POSITIONS])
        except Exception as exc:  # pragma: no cover
            LOGGER.error("Failed to fetch account details: %s", exc)
            return {}

        try:
            data = response.json() if hasattr(response, "json") else response
        except Exception:
            return {}

        if not isinstance(data, dict):
            return {}
        
        # Schwab API structure for account details
        securities_account = data.get("securitiesAccount", {})
        current_balances = securities_account.get("currentBalances", {})
        initial_balances = securities_account.get("initialBalances", {})
        
        # Calculate Day PnL: Liquidation Value - Previous Day Liquidation Value
        # Or sometimes provided directly depending on fields
        
        liquidation_value = float(current_balances.get("liquidationValue", 0.0))
        cash_balance = float(current_balances.get("cashBalance", 0.0))
        buying_power = float(current_balances.get("buyingPower", 0.0))
        
        # Try to find PnL from positions or balances
        # Schwab doesn't always give a direct "day PnL" field in the top level
        # We might need to sum up position PnL or compare with start of day
        # For now, let's trust what we can get.
        
        # Attempt to get day PnL if available, otherwise 0.0
        # Some endpoints provide 'profitAndLoss'
        day_pnl = 0.0
        
        # If we have positions, we might sum their day PnL
        positions = securities_account.get("positions", [])
        if positions:
            for pos in positions:
                instrument = pos.get("instrument", {})
                # Only count PnL for symbols we are trading if we want to be specific,
                # but for account level, we want everything.
                current_day_pnl = pos.get("currentDayProfitLoss", 0.0)
                day_pnl += float(current_day_pnl)

        return {
            "liquidation_value": liquidation_value,
            "cash_balance": cash_balance,
            "day_pnl": day_pnl,
            "buying_power": buying_power,
        }

    def fetch_positions(self) -> Dict[str, int]:
        """Fetch current open positions from Schwab."""
        if self.dry_run:
            return {}

        get_account = getattr(self.client, "get_account", None)
        if get_account is None:
            LOGGER.warning("Schwab client does not expose get_account")
            return {}

        try:
            response = get_account(self.account_id, fields=[self.client.Account.Fields.POSITIONS])
        except Exception as exc:
            LOGGER.error("Failed to fetch positions: %s", exc)
            return {}

        try:
            data = response.json() if hasattr(response, "json") else response
        except Exception:
            return {}

        if not isinstance(data, dict):
            return {}

        securities_account = data.get("securitiesAccount", {})
        positions_raw = securities_account.get("positions", [])
        
        result = {}
        for pos in positions_raw:
            instrument = pos.get("instrument", {})
            symbol = instrument.get("symbol")
            qty = pos.get("longQuantity", 0) - pos.get("shortQuantity", 0)
            
            # Schwab sometimes returns 0 quantity positions for recently closed trades
            if symbol and qty != 0:
                result[symbol] = int(qty)
                
        return result
    def get_price_history(self, symbol: str, days: int = 5) -> Optional[pd.DataFrame]:
        """Fetch historical 1-minute bars for a symbol."""
        if self.dry_run:
            return None

        get_history = getattr(self.client, "get_price_history", None)
        if get_history is None:
            LOGGER.warning("Schwab client does not expose get_price_history")
            return None

        try:
            from datetime import datetime, timedelta
            # Fetch last 'days' of 1-minute data
            # Using start/end datetime to avoid Enum issues with 'period'
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            response = get_history(
                symbol,
                frequency_type=self.client.PriceHistory.FrequencyType.MINUTE,
                frequency=self.client.PriceHistory.Frequency.EVERY_MINUTE,
                start_datetime=start_date,
                end_datetime=end_date
            )
        except Exception as exc:
            LOGGER.error("Failed to fetch price history for %s: %s", symbol, exc)
            return None

        try:
            data = response.json() if hasattr(response, "json") else response
            candles = data.get("candles", [])
            if not candles:
                return None
            
            df = pd.DataFrame(candles)
            # Standardize column names for OHLCVStore
            # Schwab returns: open, high, low, close, volume, datetime
            if not df.empty:
                df = df.rename(columns={"datetime": "timestamp"})
                return df
        except Exception as exc:
            LOGGER.error("Failed to parse price history for %s: %s", symbol, exc)
            return None
        
        return None

    def submit_limit(self, *, symbol: str, qty: int, side: str, price: float) -> Dict[str, Optional[str]]:
        builders = {
            "BUY": equity_orders.equity_buy_limit,
            "SELL": equity_orders.equity_sell_limit,
            "SHORT": equity_orders.equity_sell_short_limit,
            "COVER": equity_orders.equity_buy_to_cover_limit,
        }
        try:
            builder_factory = builders[side.upper()]
        except KeyError as exc:
            raise ValueError(f"Unsupported side '{side}'") from exc

        try:
            builder = builder_factory(symbol, qty, price)
        except TypeError:
            builder = builder_factory(symbol=symbol, quantity=qty, price=price)
        return self._send(builder, symbol=symbol, side=side.upper(), qty=qty)

    def submit_market(self, *, symbol: str, qty: int, side: str) -> Dict[str, Optional[str]]:
        builders = {
            "BUY": equity_orders.equity_buy_market,
            "SELL": equity_orders.equity_sell_market,
            "SHORT": equity_orders.equity_sell_short_market,
            "COVER": equity_orders.equity_buy_to_cover_market,
        }
        try:
            builder_factory = builders[side.upper()]
        except KeyError as exc:
            raise ValueError(f"Unsupported side '{side}'") from exc

        try:
            builder = builder_factory(symbol, qty)
        except TypeError:
            builder = builder_factory(symbol=symbol, quantity=qty)
        return self._send(builder, symbol=symbol, side=side.upper(), qty=qty)

    def cancel_all_orders(self) -> int:
        """Cancel all open/working orders on the account.
        
        Returns the number of orders cancelled, or -1 if using native cancel.
        and cancelling each WORKING one individually.
        """
        if self.dry_run:
            LOGGER.info("[DRY-RUN] Skip cancel_all_orders")
            return 0

        # Try native cancel_all first
        cancel_all = getattr(self.client, "cancel_all_orders", None)
        if cancel_all is not None:
            try:
                cancel_all(self.account_id)
                LOGGER.info("Cancel-all request sent (native)")
                return -1
            except Exception as exc:
                LOGGER.warning("Native cancel_all failed: %s. Falling back to individual cancels.", exc)

        # Fallback: fetch all orders and cancel each WORKING one
        get_orders = getattr(self.client, "get_orders_for_account", None) or getattr(self.client, "get_orders", None)
        if get_orders is None:
            LOGGER.warning("Schwab client does not expose get_orders; cannot cancel working orders")
            return 0

        try:
            from datetime import datetime, timedelta
            # Fetch today's orders
            now = datetime.utcnow()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            response = get_orders(self.account_id, from_entered_datetime=start, to_entered_datetime=now)
            orders = response.json() if hasattr(response, "json") else response
        except Exception as exc:
            LOGGER.error("Failed to fetch orders for cancel-all fallback: %s", exc)
            return 0

        if not isinstance(orders, list):
            LOGGER.warning("Unexpected orders response type: %s", type(orders))
            return 0

        cancelled_count = 0
        cancel_one = getattr(self.client, "cancel_order", None)
        if cancel_one is None:
            LOGGER.warning("Schwab client does not expose cancel_order; cannot cancel")
            return 0

        for order in orders:
            status = (order.get("status") or "").upper()
            order_id = order.get("orderId")
            if status in ("WORKING", "QUEUED", "PENDING_ACTIVATION", "ACCEPTED") and order_id:
                try:
                    cancel_one(order_id, self.account_id)
                    LOGGER.info("Cancelled order %s (was %s)", order_id, status)
                    cancelled_count += 1
                except Exception as exc:
                    LOGGER.warning("Failed to cancel order %s: %s", order_id, exc)

        LOGGER.info("Cancel-all fallback complete: cancelled %d orders", cancelled_count)
        return cancelled_count


class LiveTrader:
    """Flip-only alert monitor that places Schwab orders.

    Think of this as a traffic cop: it listens for new alerts, checks whether
    you're already long/short, and then decides whether to flip, close, or
    stay flat. The class also guards against runaway trading via rate limits
    and a kill-switch file.
    """

    def __init__(self, *, dry_run: bool = False, executor: Optional[SchwabOrderExecutor] = None, name: str = "default", inline: bool = False, db_path: Optional[str] = None) -> None:
        self.name = name  # Identifier for multi-account logging
        self.inline = inline
        self.db_path = Path(db_path or os.getenv("DB_PATH", "penny_basing.db"))
        
        # Load dynamic config
        self.config = config_manager.load_config()
        self.position_size = int(self.config.get("live_position_size", 100))
        self.initial_entry_size = int(os.getenv("LIVE_INITIAL_SIZE", str(self.position_size)))
        self.flip_size = int(os.getenv("LIVE_FLIP_SIZE", str(self.initial_entry_size * 2)))
        self.poll_interval = float(os.getenv("LIVE_POLL_INTERVAL", "1"))
        self.limit_poll_interval = float(os.getenv("LIVE_LIMIT_POLL_INTERVAL", "0.5"))  # Poll interval for limit orders
        self.use_limit_orders = _bool_env("LIVE_USE_LIMIT_ORDERS", True)
        # Unique state file per account
        state_base = os.getenv("LIVE_STATE_FILE", "live_trader_state.json")
        if name != "default":
            state_base = state_base.replace(".json", f"_{name}.json")
        self.state_path = Path(state_base)
        self.executor = executor if executor is not None else SchwabOrderExecutor(dry_run=dry_run, name=name)
        self.dry_run = getattr(self.executor, "dry_run", dry_run)
        self.kill_switch_path = Path(os.getenv("LIVE_KILL_SWITCH_FILE", "kill_switch.flag"))
        self.max_trades_per_hour = int(self.config.get("live_max_trades_per_hour", 60))
        self.account_stop_loss = float(self.config.get("account_stop_loss", 0.0))
        self.positions: Dict[str, int] = {}
        self.last_alert_id = 0
        self.trade_timestamps: list[float] = []
        self.trade_timestamps: list[float] = []
        self.position_entry_times: Dict[str, float] = {}
        self.last_entry_attempt: Dict[str, float] = {}  # Cooldown after failed limit entries
        self.rolling_pi: float = 0.0
        self.recent_pi: list[float] = []  # Rolling PI per share for last 5 trades
        self.pi_cooldown_until: float = 0.0  # Timestamp when PI cooldown ends
        self.pending_limit_orders: Dict[str, str] = {}  # symbol -> order_id (bookkeeping only)
        self.pending_limit_count: int = 0  # Tally of currently in-flight limit orders (anti-stacking gate)
        
        # Zero-Latency State
        self.live_prices: Dict[str, float] = {} # symbol -> latest stream price (zero-latency)
        self.active_limit_stops: Dict[str, bool] = {}  # symbol -> True (exit order in flight, block re-entry)
        self.trailing_high_water: Dict[str, float] = {}  # LONG: peak price seen; SHORT: trough price seen
        self.trailing_activated: Dict[str, bool] = {}   # True once pnl >= trailing_activate_pps
        self.last_exit_time: Dict[str, float] = {}  # Track last exit time for cooldown
        self.position_entry_times: Dict[str, float] = {}
        self.position_entry_prices: Dict[str, float] = {}  # Track entry prices for PnL
        self.pattern_buckets: Dict[str, str] = {}  # symbol -> aligned/countertrend/neutral
        self.daily_pnl: float = 0.0
        self.daily_date: str = time.strftime("%Y-%m-%d")
        self._intraday_pnls: Dict[str, List[float]] = {}  # symbol -> today's closed-trade PnLs for Kelly
        self._intraday_qty: Dict[str, int] = {}            # symbol -> today's closed-trade share volume (for PI/share)
        self.start_day_liquidation: float = 0.0
        self.check_bad_fills = _bool_env("LIVE_CHECK_BAD_FILLS", True)
        self.consecutive_bad_fills: int = 0  # Track consecutive bad fills
        self.live_symbols = self._parse_live_symbols()
        self.account_details: Dict[str, float] = {}
        self.min_range_cents = int(os.getenv("MIN_RANGE_CENTS", "2"))
        
        # Penalty Box State (per-symbol dicts)
        self.consecutive_loss_cents: Dict[str, float] = {}
        self.loss_cooldown_until: Dict[str, float] = {}
        self.pi_cooldown_until: float = 0.0
        self.telegram = TelegramNotifier()
        
        self._lock = threading.RLock()
        self._order_in_flight: set = set()  # symbols with an order currently being processed
        self._shutdown_event = threading.Event()

        LOGGER.info("[%s] LiveTrader initialized (pos_size=%d, state=%s)", self.name, self.position_size, self.state_path)
        self._load_state()
        self._init_db_schema()
        if not self.dry_run:
            atexit.register(self._save_state)
            # Auto-sync state on startup (replaces force_update_state.py)
            LOGGER.info("Performing initial account sync...")
            try:
                self._poll_account_details()
                self._reconcile_positions_on_startup()
            except Exception as exc:
                LOGGER.warning("Initial account sync failed: %s", exc)
            self._start_account_polling_thread()

    def _reconcile_positions_on_startup(self) -> None:
        """Verify local state matches Schwab positions on startup."""
        if self.dry_run:
            return

        LOGGER.info("Reconciling positions with Schwab...")
        try:
            schwab_positions = self.executor.fetch_positions()
        except Exception as exc:
            LOGGER.warning("Failed to fetch Schwab positions for reconciliation: %s", exc)
            return

        # Check for mismatches
        all_symbols = set(self.positions.keys()) | set(schwab_positions.keys())
        mismatches = []

        for symbol in all_symbols:
            local_qty = self.positions.get(symbol, 0)
            schwab_qty = schwab_positions.get(symbol, 0)

            if local_qty != schwab_qty:
                mismatches.append(f"{symbol}: Local={local_qty}, Schwab={schwab_qty}")

        if mismatches:
            LOGGER.warning("⚠️ Position mismatch detected! Reconciling per-symbol...")
            for m in mismatches:
                LOGGER.warning("   - %s", m)

            # Reconcile per-symbol instead of bulk-replacing so we can protect
            # positions entered within the last 30 s.  Schwab's account endpoint
            # lags 1-2 s behind fills; bulk-trusting it during that window wipes
            # valid local state.
            _now = time.time()
            _lag_window = 30.0  # seconds
            with self._lock:
                for symbol in all_symbols:
                    local_qty = self.positions.get(symbol, 0)
                    schwab_qty = schwab_positions.get(symbol, 0)
                    if local_qty == schwab_qty:
                        continue

                    entry_ts = self.position_entry_times.get(symbol, 0.0)
                    age = _now - entry_ts
                    if local_qty != 0 and 0 < age < _lag_window:
                        # Position was entered < 30 s ago.  Schwab may not have
                        # propagated the fill yet — keep local state.
                        LOGGER.warning(
                            "   - %s: skipping overwrite (local=%d, schwab=%d, age=%.1fs < %.0fs lag window)",
                            symbol, local_qty, schwab_qty, age, _lag_window,
                        )
                        continue

                    # Trust Schwab for this symbol
                    LOGGER.warning(
                        "   - %s: overwriting local=%d → schwab=%d", symbol, local_qty, schwab_qty
                    )
                    if schwab_qty == 0:
                        self.positions.pop(symbol, None)
                        self.position_entry_times.pop(symbol, None)
                        self.position_entry_prices.pop(symbol, None)
                    else:
                        self.positions[symbol] = schwab_qty
                        if symbol not in self.position_entry_times:
                            self.position_entry_times[symbol] = _now

                # Remove local symbols that Schwab no longer holds and are past the lag window
                for symbol in list(self.positions.keys()):
                    if symbol not in schwab_positions:
                        entry_ts = self.position_entry_times.get(symbol, 0.0)
                        age = _now - entry_ts
                        if age >= _lag_window:
                            LOGGER.warning("   - %s: removing (not in Schwab, age=%.1fs)", symbol, age)
                            self.positions.pop(symbol, None)
                            self.position_entry_times.pop(symbol, None)
                            self.position_entry_prices.pop(symbol, None)

                # --- Fix #11: entry price recovery ---
                # For every position we're now tracking, ensure we have a valid entry price
                # so _check_profit_limits works correctly after reconciliation.
                # Query the last OPENING trade (BUY/SHORT) — not the last trade of any kind,
                # because a SELL/COVER price is not a useful entry anchor.
                for symbol in list(self.positions.keys()):
                    if self.position_entry_prices.get(symbol, 0.0) <= 0:
                        try:
                            with self._open_conn() as conn:
                                cur = conn.cursor()
                                cur.execute(
                                    "SELECT price FROM live_trades "
                                    "WHERE symbol=? AND side IN ('BUY','SHORT') "
                                    "ORDER BY rowid DESC LIMIT 1",
                                    (symbol,)
                                )
                                row = cur.fetchone()
                                if row and float(row[0]) > 0:
                                    self.position_entry_prices[symbol] = float(row[0])
                                    LOGGER.info("   - Recovered entry price for %s: $%.4f", symbol, row[0])
                                else:
                                    # No opening trade in DB — leave at 0 so profit limits
                                    # are explicitly skipped with a warning rather than using
                                    # a misleading current-price anchor.
                                    LOGGER.error(
                                        "   - Cannot recover entry price for %s "
                                        "(no BUY/SHORT in live_trades). "
                                        "Profit limits will be skipped until a new entry is recorded.",
                                        symbol,
                                    )
                        except Exception as _e:
                            LOGGER.error("   - Failed to recover entry price for %s: %s", symbol, _e)

                self._save_state()
            LOGGER.info("✅ Per-symbol reconcile complete.")
        else:
            LOGGER.info("✅ Positions reconciled successfully (Local: %d, Schwab: %d)", len(self.positions), len(schwab_positions))

    def _parse_live_symbols(self) -> set[str]:
        # Reload config to get latest symbols
        config = config_manager.load_config()
        raw = config.get("live_symbols", "")
        if not raw:
            return set()
        return {s.strip().upper() for s in raw.split(",") if s.strip()}

    # ------------------------------------------------------------------
    # State & persistence helpers
    # ------------------------------------------------------------------
    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text())
            with self._lock:
                self.positions = {k: int(v) for k, v in data.get("positions", {}).items()}
                self.position_entry_times = {k: float(v) for k, v in data.get("position_entry_times", {}).items()}
                self.last_exit_time = {k: float(v) for k, v in data.get("last_exit_time", {}).items()}
                self.last_alert_id = int(data.get("last_alert_id", 0))
                self.start_day_liquidation = float(data.get("start_day_liquidation", 0.0))
                self.daily_pnl = float(data.get("daily_pnl", 0.0))
                self.daily_date = data.get("daily_date", time.strftime("%Y-%m-%d"))
                self.consecutive_loss_cents = dict(data.get("consecutive_loss_cents", {}))
                # Validate cooldown timestamps: discard any value that is more than
                # 1 hour in the future (corrupt/edited JSON) or already expired.
                # The real cooldown is 120 s, so 1 h headroom is generous.
                _now = time.time()
                _max_allowed = _now + 3600
                raw_cooldowns = data.get("loss_cooldown_until", {})
                self.loss_cooldown_until = {}
                for _sym, _until in raw_cooldowns.items():
                    _until = float(_until)
                    if _until <= _now:
                        pass  # already expired — drop it silently
                    elif _until > _max_allowed:
                        LOGGER.warning("Discarding corrupt cooldown for %s (ts=%.0f, >1h in future); resetting",
                                       _sym, _until)
                    else:
                        self.loss_cooldown_until[_sym] = _until
                self.pi_cooldown_until = float(data.get("pi_cooldown_until", 0.0))
            LOGGER.info("Loaded state: %s positions", len(self.positions))
        except Exception as exc:
            LOGGER.warning("Failed to load state: %s", exc)

    def _save_state(self) -> None:
        if self.dry_run:
            return
        now = time.time()
        # Build active cooldowns list for UI display
        active_cooldowns = []
        for _sym, _until in self.loss_cooldown_until.items():
            if now < _until:
                active_cooldowns.append({
                    "reason": f"Loss Cooldown ({_sym})",
                    "detail": "Consecutive losses exceeded threshold",
                    "remaining_seconds": round(_until - now),
                    "until": _until,
                })
        if hasattr(self, '_emergency_shutdown') and self._emergency_shutdown:
            active_cooldowns.append({
                "reason": "Account Stop Loss",
                "detail": "Daily loss limit reached — trading halted",
                "remaining_seconds": -1,
                "until": 0,
            })

        with self._lock:
            payload = {
                "positions": self.positions,
                "position_entry_times": self.position_entry_times,
                "last_exit_time": self.last_exit_time,
                "last_alert_id": self.last_alert_id,
                "account_details": self.account_details,
                "daily_pnl": self.daily_pnl,
                "daily_date": self.daily_date,
                "start_day_liquidation": self.start_day_liquidation,
                "consecutive_loss_cents": dict(self.consecutive_loss_cents),
                "loss_cooldown_until": dict(self.loss_cooldown_until),
                "rolling_pi": getattr(self, "rolling_pi", 0.0),
                "active_cooldowns": active_cooldowns,
            }
        try:
            self.state_path.write_text(json.dumps(payload, indent=2))
        except Exception as exc:
            LOGGER.error("Failed to persist state: %s", exc)

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------
    def _open_conn(self) -> sqlite3.Connection:
        # Simple, thread-safe-ish SQLite connection helper so every DB touch
        # uses the same pragmatic settings.
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db_schema(self) -> None:
        with self._open_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    timestamp REAL,
                    symbol TEXT,
                    ratio REAL,
                    total_bids INTEGER,
                    total_asks INTEGER,
                    heavy_venues INTEGER,
                    direction TEXT,
                    price REAL,
                    range_cents REAL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS live_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_rowid INTEGER,
                    symbol TEXT,
                    direction TEXT,
                    side TEXT,
                    qty INTEGER,
                    price REAL,
                    order_id TEXT,
                    status_code TEXT,
                    location TEXT,
                    error TEXT,
                    raw_response TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            # Live trades table for PnL comparison with paper trades
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS live_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    symbol TEXT,
                    side TEXT,
                    qty INTEGER,
                    price REAL,
                    entry_price REAL,
                    pnl REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    pattern_bucket TEXT DEFAULT 'neutral'
                )
                """
            )
            # Migrate: add pattern_bucket if missing from existing DB
            cols = [r[1] for r in cur.execute("PRAGMA table_info(live_trades)").fetchall()]
            if "pattern_bucket" not in cols:
                cur.execute("ALTER TABLE live_trades ADD COLUMN pattern_bucket TEXT DEFAULT 'neutral'")
            # Filtered alerts table: logs neutral/countertrend signals that were skipped
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS filtered_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    symbol TEXT,
                    direction TEXT,
                    price REAL,
                    pattern_bucket TEXT,
                    chart_bias TEXT,
                    size_factor REAL,
                    bull_score REAL,
                    bear_score REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            # Account history table for PnL graphing
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS account_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    liquidation_value REAL,
                    cash_balance REAL,
                    day_pnl REAL,
                    buying_power REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

        if self.last_alert_id == 0:
            self.last_alert_id = self._get_last_alert_id_from_db()

    def _get_last_alert_id_from_db(self) -> int:
        try:
            with self._open_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT MAX(rowid) FROM alerts")
                row = cur.fetchone()
                return int(row[0]) if row and row[0] else 0
        except sqlite3.Error:
            LOGGER.warning("alerts table missing; starting with last_alert_id=0")
            return 0

    def _latest_price(self, symbol: str) -> Optional[float]:
        with self._open_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT price FROM alerts WHERE symbol=? ORDER BY rowid DESC LIMIT 1",
                (symbol,),
            )
            row = cur.fetchone()
            return float(row[0]) if row else None



    def _reference_price(self, symbol: str, direction: str, fallback: float) -> float:
        quote = None
        try:
            quote = self.executor.fetch_quote(symbol)
        except Exception:
            quote = None

        if quote:
            if direction == "ask-heavy":
                for key in ("bidPrice", "lastPrice", "askPrice"):
                    if key in quote and quote[key] not in {None, 0}:
                        return float(quote[key])
            else:
                for key in ("askPrice", "lastPrice", "bidPrice"):
                    if key in quote and quote[key] not in {None, 0}:
                        return float(quote[key])
        return float(fallback)

    def _log_live_trade(self, *, symbol: str, side: str, qty: int, price: float, entry_price: float, pnl: float) -> None:
        """Log live trade to database for comparison with paper trades."""
        LOGGER.info(
            "[LIVE] %s %s %s @ $%.4f | Entry: $%.4f | PnL: $%.2f | Daily PnL: $%.2f",
            side, qty, symbol, price, entry_price, pnl, self.daily_pnl
        )
        with self._open_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO live_trades (timestamp, symbol, side, qty, price, entry_price, pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (time.time(), symbol, side, qty, price, entry_price, pnl)
            )
            conn.commit()

    def _log_filtered_alert(self, *, symbol: str, direction: str, price: float,
                            pattern_bucket: str, chart_bias: str,
                            size_factor: float, bull_score: float, bear_score: float) -> None:
        """Log a filtered (neutral/countertrend) alert to DB for post-market analysis."""
        with self._open_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO filtered_alerts
                    (timestamp, symbol, direction, price, pattern_bucket, chart_bias, size_factor, bull_score, bear_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (time.time(), symbol, direction, price, pattern_bucket, chart_bias, size_factor, bull_score, bear_score),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Kelly Criterion position sizing
    # ------------------------------------------------------------------
    def _db_kelly_params(self, symbol: str, lookback_days: int) -> tuple:
        """Return (W, R) from DB historical closed trades for *symbol*.

        Falls back to global stats if per-symbol data is thin.
        Returns (None, None) if there is no data at all.
        """
        cutoff = time.time() - lookback_days * 86_400
        _cols  = "pnl, entry_price, price, qty, side"

        def _extract(rows):
            result = []
            for pnl, ep, ex, qty, side in rows:
                if pnl not in (None, 0.0):
                    result.append(pnl)
                elif ep and ep > 0 and ex and ex > 0 and qty:
                    computed = (ex - ep) * qty if side == "SELL" else (ep - ex) * qty
                    if computed != 0.0:
                        result.append(computed)
            return result

        with self._open_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT {_cols} FROM live_trades "
                "WHERE symbol=? AND side IN ('SELL','COVER') AND timestamp>=?",
                (symbol, cutoff),
            )
            pnls = _extract(cur.fetchall())
            if not pnls:
                cur.execute(
                    f"SELECT {_cols} FROM live_trades "
                    "WHERE side IN ('SELL','COVER') AND timestamp>=?",
                    (cutoff,),
                )
                pnls = _extract(cur.fetchall())

        wins   = [p      for p in pnls if p > 0]
        losses = [abs(p) for p in pnls if p < 0]
        if not wins or not losses:
            return (None, None)

        W = len(wins) / len(pnls)
        R = (sum(wins) / len(wins)) / (sum(losses) / len(losses))
        return (W, R)

    def _kelly_size_multiplier(self, symbol: str) -> float:
        """Return an intraday-adaptive position-size multiplier combining Kelly + PI.

        Starts at 1.0 each day and updates after every closed trade (SELL/COVER).

        Step 1 — Kelly edge (win/loss data):
          - Intraday has both wins & losses  → use intraday W and R
          - Intraday is one-sided so far     → use DB historical W and R
          - No trade data at all             → kelly_mult = 1.0

        Step 2 — PI adjustment (PnL/share vs neutral):
          Uses tanh so the adjustment is always bounded in [−weight, +weight],
          giving diminishing returns at extremes and 0 at exactly the neutral.

            pi_per_share = sum(intraday_pnl) / total_shares_closed_today
            pi_ratio     = pi_per_share / pi_neutral − 1.0   (0 at neutral)
            pi_adj       = pi_kelly_weight * tanh(pi_ratio)
              → pi == pi_neutral         → ratio=0, tanh(0)=0  → no change
              → pi == 2×neutral          → ratio=1, tanh(1)≈0.76 → boost ≈ +0.38
              → pi == 4×neutral          → ratio=3, tanh(3)≈1.00 → boost ≈ +0.50 (cap)
              → pi == 0                  → ratio=-1              → reduce ≈ -0.38
              → pi strongly negative     → ratio≪0, tanh→-1    → reduce ≈ -0.50 (floor)

        Final: multiplier = clamp(kelly_mult + pi_adj, min_mult, max_mult)
        """
        import math
        try:
            cfg = config_manager.load_config()
            if not cfg.get("kelly_enabled", True):
                return 1.0

            kelly_fraction  = float(cfg.get("kelly_fraction",      0.5))
            max_mult        = float(cfg.get("kelly_max_multiplier", 2.0))
            min_mult        = float(cfg.get("kelly_min_multiplier", 0.25))
            lookback_days   = int(  cfg.get("kelly_lookback_days",  30))
            pi_neutral      = float(cfg.get("pi_neutral",           0.001))
            pi_kelly_weight = float(cfg.get("pi_kelly_weight",      0.5))

            with self._lock:
                raw_pnls    = list(self._intraday_pnls.get(symbol, []))
                intraday_qty = self._intraday_qty.get(symbol, 0)

            # ── Step 1: Kelly from win/loss edge ──────────────────────────
            pnls   = [p for p in raw_pnls if p != 0.0]
            wins   = [p      for p in pnls if p > 0]
            losses = [abs(p) for p in pnls if p < 0]

            if not pnls:
                kelly_mult = 1.0
                source     = "no-trades"
            elif wins and losses:
                W = len(wins) / len(pnls)
                R = (sum(wins) / len(wins)) / (sum(losses) / len(losses))
                full_kelly = (W * R - (1.0 - W)) / R
                kelly_mult = 1.0 + full_kelly * kelly_fraction
                source     = "intraday"
            else:
                W, R = self._db_kelly_params(symbol, lookback_days)
                if W is None:
                    kelly_mult = 1.0
                    source     = "no-history"
                else:
                    full_kelly = (W * R - (1.0 - W)) / R
                    kelly_mult = 1.0 + full_kelly * kelly_fraction
                    source     = "db-fallback"

            # ── Step 2: PI adjustment (PnL/share vs neutral) ─────────────
            pi_adj = 0.0
            pi_per_share = 0.0
            if intraday_qty > 0:
                pi_per_share = sum(raw_pnls) / intraday_qty   # include $0 fills in denominator
                pi_ratio = pi_per_share / pi_neutral - 1.0    # 0 at neutral, ±N elsewhere
                pi_adj   = pi_kelly_weight * math.tanh(pi_ratio)

            # ── Final: combine and clamp ──────────────────────────────────
            multiplier = max(min_mult, min(kelly_mult + pi_adj, max_mult))

            LOGGER.info(
                "[KELLY] %s (%s, n=%d): kelly=%.3f pi/share=$%.5f pi_adj=%.3f → mult=%.3f",
                symbol, source, len(pnls), kelly_mult, pi_per_share, pi_adj, multiplier,
            )
            return multiplier

        except Exception as exc:
            LOGGER.warning("[KELLY] Error computing Kelly for %s: %s — using 1.0x", symbol, exc)
            return 1.0

    # ------------------------------------------------------------------
    # Position bookkeeping
    # ------------------------------------------------------------------
    def _apply_position_delta(self, symbol: str, delta: int) -> None:
        old_qty = self.positions.get(symbol, 0)
        new_qty = old_qty + delta
        
        # Track entry time for new positions or flips
        if old_qty == 0 and new_qty != 0:
            self.position_entry_times[symbol] = time.time()
        elif (old_qty > 0 and new_qty < 0) or (old_qty < 0 and new_qty > 0):
            self.position_entry_times[symbol] = time.time()

        if new_qty == 0:
            self.positions.pop(symbol, None)
            self.position_entry_times.pop(symbol, None)
            # Clear all per-position exit-tracking state so a fresh entry starts clean
            self.trailing_activated.pop(symbol, None)
            self.trailing_high_water.pop(symbol, None)
            self.active_limit_stops.pop(symbol, None)
        else:
            self.positions[symbol] = new_qty
        LOGGER.info("Position update %s => %s", symbol, new_qty)

    def _record_fill(self, *, symbol: str, side: str, qty: int, price: float = 0.0) -> None:
        with self._lock:
            old_qty = self.positions.get(symbol, 0)
            entry_price = self.position_entry_prices.get(symbol, price)
            
            # Calculate PnL for closing trades
            pnl = 0.0
            per_share_pnl = 0.0
            if old_qty > 0 and side == "SELL":
                pnl = (price - entry_price) * qty
                per_share_pnl = price - entry_price
            elif old_qty < 0 and side == "COVER":
                pnl = (entry_price - price) * qty
                per_share_pnl = entry_price - price
            
            # Penalty Box Logic: Cumulative Loss Bucket
            # Threshold: Cumulative loss of >= $0.02 per share in consecutive trades
            if pnl != 0: # Only check closing trades
                if per_share_pnl < 0:
                    self.consecutive_loss_cents[symbol] = self.consecutive_loss_cents.get(symbol, 0.0) + abs(per_share_pnl)
                    LOGGER.info("Loss detected on %s ($%.4f/share). Cumulative Bucket: $%.4f", symbol, per_share_pnl, self.consecutive_loss_cents[symbol])

                    if self.consecutive_loss_cents[symbol] >= 0.02:
                        self.loss_cooldown_until[symbol] = time.time() + 120
                        self.consecutive_loss_cents[symbol] = 0.0  # Reset after penalty applied
                        msg = f"🚨 PENALTY BOX TRIGGERED [{symbol}]: Cumulative Loss >= $0.02/share. Cooldown for 2 minutes."
                        LOGGER.warning(msg)
                        print(f"\n{'='*60}\n{msg}\n{'='*60}\n", flush=True)
                        self.telegram.notify_cooldown("Loss Cooldown", self.account_details.get("liquidation_value", 0.0))
                else:
                    # Empathetic Reset: Any profitable trade resets the anxiety bucket for this symbol
                    if self.consecutive_loss_cents.get(symbol, 0.0) > 0:
                        LOGGER.info("Win/Flat trade on %s ($%.4f/share) resets cumulative loss bucket (was $%.4f)", symbol, per_share_pnl, self.consecutive_loss_cents[symbol])
                    self.consecutive_loss_cents[symbol] = 0.0
            
            # Update daily PnL
            today = time.strftime("%Y-%m-%d")
            if today != self.daily_date:
                self.daily_date = today
                self.daily_pnl = 0.0
                self._intraday_pnls.clear()   # Reset intraday Kelly tracking each day
                self._intraday_qty.clear()    # Reset intraday PI share volume each day
            if pnl != 0:
                self.daily_pnl += pnl

            # Track intraday PnL and share volume for Kelly + PI calculation
            if side in ("SELL", "COVER"):
                self._intraday_pnls.setdefault(symbol, []).append(pnl)
                self._intraday_qty[symbol] = self._intraday_qty.get(symbol, 0) + qty
            
            # Log trade to database
            self._log_live_trade(symbol=symbol, side=side, qty=qty, price=price, entry_price=entry_price, pnl=pnl)
            
            delta = qty if side in {"BUY", "COVER"} else -qty
            self._apply_position_delta(symbol, delta)
            
            # Track entry price for new positions
            new_qty = self.positions.get(symbol, 0)
            if old_qty == 0 and new_qty != 0:
                self.position_entry_prices[symbol] = price
            elif new_qty == 0:
                self.position_entry_prices.pop(symbol, None)
            elif (old_qty > 0 and new_qty < 0) or (old_qty < 0 and new_qty > 0):
                self.position_entry_prices[symbol] = price
            
            if not self.dry_run:
                self._save_state()
            self.trade_timestamps.append(time.time())
        self._enforce_trade_rate_limit()
        
        # Aggressively clear all working orders to prevent ghosts
        LOGGER.info("Trade finalized. Cancelling any remaining working orders to clear the book.")
        self.executor.cancel_all_orders()



    def _enforce_trade_rate_limit(self) -> None:
        cutoff = time.time() - 3600
        self.trade_timestamps = [ts for ts in self.trade_timestamps if ts >= cutoff]
        if len(self.trade_timestamps) > self.max_trades_per_hour:
            msg = f"⚠️  Trade rate exceeded limit ({len(self.trade_timestamps)} in the last hour)"
            LOGGER.warning(msg)
            print(f"\n{'='*60}\n{msg}\n{'='*60}\n", flush=True)

    def _engage_emergency_shutdown(self, reason: str) -> None:
        # Set the event FIRST so all other threads stop accepting new alerts immediately.
        self._shutdown_event.set()
        LOGGER.error("EMERGENCY STOP: %s", reason)
        try:
            self.executor.cancel_all_orders()
            LOGGER.info("Cancelled all open orders. Waiting 2s for propagation...")
            time.sleep(2.0)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to request cancel-all: %s", exc)

        # FORCE RECONCILE: Ensure we know exactly what we have before trying to close it.
        # This prevents "Boxed Position" errors caused by stale state or race conditions.
        try:
            self._reconcile_positions_on_startup()
        except Exception as exc:
            LOGGER.error("Failed to reconcile positions during shutdown: %s", exc)
            # Fallback to cached positions if reconcile fails (risky but necessary)

        with self._lock:
            snapshot = self.positions.copy()
        for symbol, qty in snapshot.items():
            if qty == 0:
                continue
            side = "SELL" if qty > 0 else "COVER"
            price = self._latest_price(symbol) or 0.0
            
            LOGGER.info("Flattening %s %s (Qty: %d) due to shutdown...", side, symbol, abs(qty))
            
            self._submit_order(
                alert_id=-1,
                symbol=symbol,
                direction="kill-switch",
                side=side,
                qty=abs(qty),
                price=price,
                order_type="MARKET"  # Force MARKET for emergency exit
            )

        self._save_state()
        # _shutdown_event is already set at the top of this method; all loops
        # will exit on their next iteration. Do NOT raise SystemExit here —
        # that would only kill the calling thread (typically a daemon), not
        # the main alert-processing thread.

    def _check_kill_switch(self) -> None:
        if self.kill_switch_path.exists():
            LOGGER.error("Kill switch file %s detected", self.kill_switch_path)
            self._engage_emergency_shutdown("Kill switch activated")

    def _check_time_stops(self) -> None:
        """Disabled — positions close only on opposing signals."""
        pass

    def update_live_price(self, symbol: str, price: float) -> None:
        """Zero-latency update from grok.py's streaming websocket feed."""
        if price > 0:
            self.live_prices[symbol] = price

    def _check_profit_limits(self) -> None:
        """Per-position exit logic running every 0.5 s on zero-latency WebSocket prices.

        Layer 1 — Hard SL
          Exit immediately (limit at current price) when unrealized loss >= sl_per_share.
          The limit is submitted AT current_price, so it fills at the live bid/ask rather
          than at a stale trigger level.  Works symmetrically for LONG (SELL) and SHORT
          (COVER).

        Layer 2 — Trailing TP
          Activates once pnl >= trailing_activate_pps.  Tracks a per-symbol high-water
          mark (lowest price for shorts).  When price retraces by trailing_trail_pps from
          that peak, a limit exit is submitted AT the trail level.

          For LONG:  trail fires when current_price <= high_water - trail_amount
                     → SELL limit at trail_level
          For SHORT: trail fires when current_price >= low_water  + trail_amount
                     → COVER limit at trail_level

          Both cases submit the limit AT the trail trigger price, which is at or very near
          current market, so the order fills immediately.  This is NOT placing a limit
          below/above the current price as a standing order — it is submitted only when
          price has already reached the exit level.

        Layer 0 — Time Stop
          Unconditional market exit once a position has been held for >= time_stop_seconds.
          Fires regardless of PnL direction.  No limit order — straight MARKET so the
          position is guaranteed flat.

        Config keys (config_manager):
          time_stop_seconds     default 180    (exit any position held >= 3 minutes)
          sl_per_share          default 0.008  ($0.008 / share hard stop)
          trailing_activate_pps default 0.012  (activate trailing after +$0.012 / share)
          trailing_trail_pps    default 0.008  (trail by $0.008 from peak)
        """
        if not self.positions:
            return

        cfg = config_manager.load_config()
        time_stop_secs = float(cfg.get("time_stop_seconds",     180))
        sl_threshold   = float(cfg.get("sl_per_share",          0.008))
        trail_activate = float(cfg.get("trailing_activate_pps", 0.012))
        trail_amount   = float(cfg.get("trailing_trail_pps",    0.008))

        with self._lock:
            current_positions = dict(self.positions)

        for symbol, qty in current_positions.items():
            if qty == 0:
                # Shouldn't normally appear (positions are removed on close), but clean up
                # if stale state somehow remains.
                self.trailing_activated.pop(symbol, None)
                self.trailing_high_water.pop(symbol, None)
                self.active_limit_stops.pop(symbol, None)
                continue

            # Skip while an exit order for this symbol is already in flight.
            if self.active_limit_stops.get(symbol):
                continue

            entry_price = self.position_entry_prices.get(symbol, 0.0)
            if entry_price <= 0:
                continue

            # Use zero-latency WebSocket price exclusively — REST API adds 3-5 s lag.
            current_price = self.live_prices.get(symbol, 0.0)
            if current_price <= 0:
                continue

            direction = "LONG" if qty > 0 else "SHORT"
            pnl = (current_price - entry_price) if direction == "LONG" else (entry_price - current_price)

            # ── Layer 0: Time Stop ────────────────────────────────────────────────
            entry_ts = self.position_entry_times.get(symbol, 0.0)
            age_secs = time.time() - entry_ts
            if entry_ts > 0 and age_secs >= time_stop_secs:
                side = "SELL" if direction == "LONG" else "COVER"
                LOGGER.warning(
                    "[TIME-STOP] %s %s held %.1fs >= %.0fs → MARKET %s (pnl=%.5f)",
                    direction, symbol, age_secs, time_stop_secs, side, pnl,
                )
                self.active_limit_stops[symbol] = True
                try:
                    self._submit_order(
                        alert_id=-1,
                        symbol=symbol,
                        direction="time-stop",
                        side=side,
                        qty=abs(qty),
                        price=current_price,
                        order_type="MARKET",
                    )
                except Exception as exc:
                    LOGGER.error("[TIME-STOP] Submit failed for %s: %s", symbol, exc)
                    self.active_limit_stops.pop(symbol, None)
                continue  # one exit per symbol per iteration

            # ── Update high-water mark ────────────────────────────────────────────
            with self._lock:
                if direction == "LONG":
                    hw = self.trailing_high_water.get(symbol, entry_price)
                    if current_price > hw:
                        self.trailing_high_water[symbol] = current_price
                        hw = current_price
                else:  # SHORT: track lowest price (most favourable)
                    hw = self.trailing_high_water.get(symbol, entry_price)
                    if current_price < hw:
                        self.trailing_high_water[symbol] = current_price
                        hw = current_price

            hw_pnl = abs(hw - entry_price)

            # ── Layer 1: Hard SL ─────────────────────────────────────────────────
            # Reactive: fire MARKET exit when unrealized loss >= sl_threshold.
            if pnl <= -sl_threshold:
                side = "SELL" if direction == "LONG" else "COVER"
                LOGGER.warning(
                    "[SL] %s %s pnl=%.5f <= -%.5f → MARKET %s",
                    direction, symbol, pnl, sl_threshold, side,
                )
                try:
                    self.executor.cancel_all_orders()
                except Exception:
                    pass
                self.active_limit_stops[symbol] = True
                try:
                    self._submit_order(
                        alert_id=-1,
                        symbol=symbol,
                        direction="hard-sl",
                        side=side,
                        qty=abs(qty),
                        price=current_price,
                        order_type="MARKET",
                    )
                except Exception as exc:
                    LOGGER.error("[SL] Submit failed for %s: %s", symbol, exc)
                    self.active_limit_stops.pop(symbol, None)
                continue

            # ── Layer 2: Trailing TP ─────────────────────────────────────────────
            # Trail not armed yet — nothing more to do this iteration.
            if hw_pnl < trail_activate:
                continue

            # Log first activation.
            if not self.trailing_activated.get(symbol):
                self.trailing_activated[symbol] = True
                LOGGER.info(
                    "[TRAIL] Armed for %s %s: hw=$%.4f locked=+%.5f",
                    direction, symbol, hw, hw_pnl,
                )

            # Compute desired trail level.
            if direction == "LONG":
                desired_stop  = round(hw - trail_amount,         4)
                desired_limit = round(hw - trail_amount - 0.001, 4)
                exit_side = "SELL"
            else:
                desired_stop  = round(hw + trail_amount,         4)
                desired_limit = round(hw + trail_amount + 0.001, 4)
                exit_side = "COVER"

            # ── Price at/past trail level → MARKET exit ───────────────────────
            if (direction == "LONG"  and current_price <= desired_stop) or \
               (direction == "SHORT" and current_price >= desired_stop):
                LOGGER.info(
                    "[TRAIL-TP] %s %s price $%.4f reached trail $%.4f → MARKET %s",
                    direction, symbol, current_price, desired_stop, exit_side,
                )
                try:
                    self.executor.cancel_all_orders()
                except Exception:
                    pass
                self.active_limit_stops[symbol] = True
                try:
                    self._submit_order(
                        alert_id=-1, symbol=symbol, direction="trailing-tp",
                        side=exit_side, qty=abs(qty), price=current_price,
                        order_type="MARKET",
                    )
                except Exception as exc:
                    LOGGER.error("[TRAIL-TP] Submit failed for %s: %s", symbol, exc)
                    self.active_limit_stops.pop(symbol, None)
                continue

    # ------------------------------------------------------------------
    # Order + alert processing
    # ------------------------------------------------------------------
    def _check_fill_quality(self, side: str, price: float) -> None:
        """Check for 'bad fills' (longs at .xx99, shorts at .xx01) and log consecutive occurrences."""
        if not self.check_bad_fills:
            return

        if price is None or price <= 0:
            return

        # Use string formatting to 4 decimal places to avoid float precision issues
        price_str = f"{price:.4f}"
        
        # Check if the price exactly ends in '99' or '01'
        is_99 = price_str.endswith("99")
        is_01 = price_str.endswith("01")

        bad_fill = False
        fill_type = ""
        if side in {"BUY", "COVER"} and is_99:
            bad_fill = True
            fill_type = ".xx99"
        elif side in {"SELL", "SHORT"} and is_01:
            bad_fill = True
            fill_type = ".xx01"

        if bad_fill:
            self.consecutive_bad_fills += 1
            msg = f"⚠️  BAD FILL #{self.consecutive_bad_fills}: {side} at ${price:.4f} ({fill_type})"
            LOGGER.warning(msg)
            print(f"\n{'='*60}\n{msg}\n{'='*60}\n", flush=True)
            
            if self.consecutive_bad_fills >= 3:
                LOGGER.error("🚨 ALERT: %d consecutive bad fills detected! (%s at $%.4f)", self.consecutive_bad_fills, side, price)
                print(f"\n🚨🚨🚨 ALERT: {self.consecutive_bad_fills} CONSECUTIVE BAD FILLS! 🚨🚨🚨\n", flush=True)
                try:
                    self.telegram.notify_error("🚨 CONSECUTIVE BAD FILLS", f"{self.consecutive_bad_fills} consecutive bad sub-penny fills detected! Last: {side} at ${price:.4f} ({fill_type})")
                except Exception:
                    pass
        else:
            # Reset counter on good fill
            if self.consecutive_bad_fills > 0:
                LOGGER.info("Good fill - resetting bad fill counter from %d", self.consecutive_bad_fills)
            self.consecutive_bad_fills = 0

    def _record_order(self, *, alert_id: int, symbol: str, direction: str, side: str, qty: int, price: float, result: dict) -> None:
        serialized = json.dumps(result, default=str)
        with self._open_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO live_orders
                (alert_rowid, symbol, direction, side, qty, price, order_id, status_code, location, error, raw_response)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert_id,
                    symbol,
                    direction,
                    side,
                    qty,
                    price,
                    result.get("order_id"),
                    result.get("status_code"),
                    result.get("location"),
                    result.get("error"),
                    serialized,
                ),
            )
            conn.commit()
    def _record_pi(self, pi_per_share: float) -> None:
        """Track cumulative price improvement per share since startup."""
        self.recent_pi.append(pi_per_share)
        avg_pi = sum(self.recent_pi) / len(self.recent_pi)
        self.rolling_pi = avg_pi
        
        LOGGER.info("PI per share: $%.4f  (Cumulative Avg over %d trades: $%.4f)",
                    pi_per_share, len(self.recent_pi), avg_pi)
        
        # Trigger PI Cooldown if avg PI < $0.0005 (5.0 per-10k shares logic)
        if len(self.recent_pi) >= 5 and avg_pi < 0.0005:
            if time.time() >= self.pi_cooldown_until:
                self.pi_cooldown_until = time.time() + 300 # 5 minutes
                msg = f"❄️ PI COOLDOWN TRIGGERED: Avg PI ${avg_pi:.5f} < $0.0005. Frozen for 5m."
                LOGGER.warning(msg)
                print(f"\n{'='*60}\n{msg}\n{'='*60}\n", flush=True)
                self.telegram.notify_cooldown("PI Cooldown", self.account_details.get("liquidation_value", 0.0))

    def _record_and_apply_market(
        self, *, alert_id: int, symbol: str, direction: str, side: str, qty: int, price: float
    ) -> bool:
        result = self.executor.submit_market(symbol=symbol, qty=qty, side=side)
        submitted = result.get("error") is None and (
            result.get("dry_run")
            or (
                result.get("status_code") not in {None, ""}
                and str(result.get("status_code")).startswith("2")
            )
        )

        filled = False
        filled_qty = 0
        fill_status: Optional[str] = None
        actual_price = price

        if submitted:
            filled = True
            filled_qty = qty
            fill_status = "FILLED"
            result["filled_via"] = "MARKET"

            # Fetch actual fill price for bad fill detection and PI tracking.
            # Record the fill AFTER Schwab confirms it to avoid updating
            # self.positions before the order is actually on the books.
            order_id = result.get("order_id")
            if order_id and not result.get("dry_run"):
                # Fetch quote for PI calculation before waiting
                quote = self.executor.fetch_quote(symbol)
                quote_data = quote.get("quote", quote) if quote else {}
                quoted_bid = float(quote_data.get("bidPrice", 0))
                quoted_ask = float(quote_data.get("askPrice", 0))
                # Give Schwab a moment to process the fill
                time.sleep(2.0)
                status = self.executor.fetch_order_status(order_id)
                avg_price = status.get("avg_fill_price")
                LOGGER.info("[PI-DEBUG] Order %s: avg_fill_price=%s, status=%s", order_id, avg_price, status.get("status"))
                if avg_price:
                    actual_price = float(avg_price)
                    self._check_fill_quality(side, actual_price)
                    # Calculate PI: how much better than NBBO
                    if side in ("BUY", "COVER") and quoted_ask > 0:
                        pi = quoted_ask - actual_price
                        LOGGER.info("[PI-DEBUG] BUY/COVER PI calc: ask=$%.4f - fill=$%.4f = $%.4f", quoted_ask, actual_price, pi)
                        self._record_pi(max(pi, 0.0))
                    elif side in ("SELL", "SHORT") and quoted_bid > 0:
                        pi = actual_price - quoted_bid
                        LOGGER.info("[PI-DEBUG] SELL/SHORT PI calc: fill=$%.4f - bid=$%.4f = $%.4f", actual_price, quoted_bid, pi)
                        self._record_pi(max(pi, 0.0))
                else:
                    LOGGER.warning("[PI-DEBUG] No avg_fill_price for order %s. Raw status: %s", order_id, status)
                # Record fill with confirmed actual price (or submitted price if status unavailable)
                self._record_fill(symbol=symbol, side=side, qty=qty, price=actual_price)
            else:
                # dry_run or no order_id: record immediately (no real order on Schwab)
                self._record_fill(symbol=symbol, side=side, qty=qty, price=price)
        else:
            fill_status = "FAILED"
            # CHECK FOR BOXED POSITION ERROR
            err_msg = str(result.get("error") or "").lower()
            if "boxed" in err_msg:
                 LOGGER.warning("Boxed Position Error detected in result: %s", err_msg)
                 raise BoxedPositionError(err_msg)

            if "replacement" in str(result.get("error") or "").lower():
                LOGGER.info("Order replaced (or similar status), treating as PENDING/FILLED for now.")
                fill_status = "FILLED"

        if filled and filled_qty == 0:
            filled_qty = qty

        result["fill_status"] = fill_status
        result["filled_qty"] = filled_qty

        self._record_order(
            alert_id=alert_id,
            symbol=symbol,
            direction=direction,
            side=side,
            qty=qty,
            price=actual_price,
            result=result,
        )
        return filled

    def _record_and_apply_limit(
        self, *, alert_id: int, symbol: str, direction: str, side: str, qty: int, price: Optional[float] = None
    ) -> bool:
        """Submit a limit order at Bid/Ask and cancel if not filled within timeout."""

        # Anti-stacking gate: skip if another limit order is currently in-flight
        # NOTE: tally is incremented only AFTER Schwab confirms the order via order_id
        with self._lock:
            if self.pending_limit_count > 0:
                LOGGER.info("ANTI-STACKING: %d limit order(s) in flight, skipping new %s %s",
                            self.pending_limit_count, side, symbol)
                return False

        limit_price = 0.0

        # Preference 1: Use passed price if valid
        if price is not None and price > 0:
            limit_price = price
        else:
            # Preference 2: Fetch fresh quote
            quote = self.executor.fetch_quote(symbol)
            if not quote:
                LOGGER.warning("Could not fetch quote for %s; skipping limit order", symbol)
                return False

            if side in {"BUY", "COVER"}:
                 # Buy at Bid
                 limit_price = float(quote.get("bidPrice", 0.0))
            else:
                 # Sell at Ask
                 limit_price = float(quote.get("askPrice", 0.0))
        
        if limit_price <= 0:
             LOGGER.warning("Invalid limit price %.2f for %s; skipping", limit_price, symbol)
             return False

        LOGGER.info("[LIMIT] Submitting %s %d %s @ $%.2f", side, qty, symbol, limit_price)
        
        result = self.executor.submit_limit(symbol=symbol, qty=qty, side=side, price=limit_price)
        
        error = result.get("error")
        if error:
             LOGGER.error("Limit order submission failed: %s", error)
             # CHECK FOR BOXED POSITION ERROR
             err_msg = str(error).lower()
             if "boxed" in err_msg:
                  LOGGER.warning("Boxed Position Error detected in result: %s", err_msg)
                  raise BoxedPositionError(err_msg)
             # Record failure
             self._record_order(
                alert_id=alert_id,
                symbol=symbol,
                direction=direction,
                side=side,
                qty=qty,
                price=limit_price,
                result=result,
            )
             return False

        if result.get("dry_run"):
             # In dry run, assume filled after "wait"
             time.sleep(self.limit_poll_interval)
             LOGGER.info("[DRY-RUN] Limit order 'filled' after wait")
             self._record_fill(symbol=symbol, side=side, qty=qty, price=limit_price)
             result["fill_status"] = "FILLED"
             result["filled_qty"] = qty
             self._record_order(
                alert_id=alert_id,
                symbol=symbol,
                direction=direction,
                side=side,
                qty=qty,
                price=limit_price,
                result=result,
            )
             return True

        order_id = result.get("order_id")
        if not order_id:
            LOGGER.error("No order_id returned for limit order")
            # Tally was NOT yet incremented — decrement guard in finally will handle it
            # but we need to signal that tally shouldn't be decremented either
            # Use a flag: only increment if we actually have a live order
            return False

        # Order confirmed on exchange — NOW increment tally and track it
        with self._lock:
            self.pending_limit_count += 1
            self.pending_limit_orders[symbol] = order_id
        LOGGER.info("[LIMIT] Tally now %d (order %s confirmed for %s %s)", self.pending_limit_count, order_id, side, symbol)

        try:
            LOGGER.info("Waiting %.1fs for fill on order %s...", self.limit_poll_interval, order_id)
            time.sleep(self.limit_poll_interval)
        
            status = self.executor.fetch_order_status(order_id)
            order_status = status.get("status", "").upper()
            filled_qty = status.get("filled_quantity") or 0
            avg_price = status.get("avg_fill_price")
        
            LOGGER.info("Order %s status: %s (Filled: %s)", order_id, order_status, filled_qty)

            # Cancel remaining working orders only AFTER poll — saves one full API round-trip on entries
            if order_status not in {"FILLED", "EXPIRED", "CANCELED", "REJECTED"}:
                try:
                    self.executor.cancel_all_orders()
                except Exception as exc:
                    LOGGER.warning("Post-poll cancel_all failed: %s", exc)

            final_filled = False
        
            if order_status in {"FILLED", "EXPIRED"} or filled_qty == qty:
                # Filled!
                final_filled = True
                realized_price = float(avg_price) if avg_price else limit_price
                # Use actual filled qty if available, otherwise assume full qty if status is FILLED
                actual_fill = int(filled_qty) if filled_qty > 0 else qty
                self._record_fill(symbol=symbol, side=side, qty=actual_fill, price=realized_price)
                result["fill_status"] = "FILLED"
                result["filled_qty"] = actual_fill

                # Calculate PI on limit fill
                quote = self.executor.fetch_quote(symbol)
                if quote:
                    quoted_bid = float(quote.get("bidPrice", 0))
                    quoted_ask = float(quote.get("askPrice", 0))
                    if side in ("BUY", "COVER") and quoted_ask > 0:
                        pi = quoted_ask - realized_price
                        self._record_pi(max(pi, 0.0))
                    elif side in ("SELL", "SHORT") and quoted_bid > 0:
                        pi = realized_price - quoted_bid
                        self._record_pi(max(pi, 0.0))
        
            elif order_status in {"CANCELED", "REJECTED"}:
                 LOGGER.warning("Order %s was already %s", order_id, order_status)
                 # Even if canceled, check if there was partial fill
                 if filled_qty > 0:
                     realized_price = float(avg_price) if avg_price else limit_price
                     self._record_fill(symbol=symbol, side=side, qty=int(filled_qty), price=realized_price)
                     result["fill_status"] = "PARTIAL_CANCELED"
                     result["filled_qty"] = int(filled_qty)
                 else:
                     result["fill_status"] = order_status
                     result["filled_qty"] = 0
             
            else:
                # Still Open (WORKING, QUEUED, etc) -> check fill status one more time
                # before sending any cancel to avoid the cancel/fill race.
                LOGGER.info("Order %s not filled (Status: %s). Re-checking before cancel...", order_id, order_status)
                pre_cancel_status = self.executor.fetch_order_status(order_id)
                pre_cancel_qty = pre_cancel_status.get("filled_quantity") or 0
                if pre_cancel_qty >= qty:
                    LOGGER.info("Order %s already fully filled (%d shares) on re-check; skipping cancel.", order_id, pre_cancel_qty)
                    realized_price = float(pre_cancel_status.get("avg_fill_price") or limit_price)
                    self._record_fill(symbol=symbol, side=side, qty=int(pre_cancel_qty), price=realized_price)
                    result["fill_status"] = "FILLED"
                    result["filled_qty"] = int(pre_cancel_qty)
                    final_filled = True
                    # Jump to _record_order; skip the entire cancel block below.
                    self._record_order(
                        alert_id=alert_id, symbol=symbol, direction=direction,
                        side=side, qty=qty, price=limit_price, result=result,
                    )
                    return True

                LOGGER.info("Order %s confirmed still open (%d filled); proceeding with cancel.", order_id, pre_cancel_qty)

                # 1. Direct Cancel first
                _direct_cancel_ok = False
                try:
                    self.executor.client.cancel_order(order_id, self.executor.account_id)
                    _direct_cancel_ok = True
                    LOGGER.info("Direct cancel sent for order %s", order_id)
                except Exception as _ce:
                    LOGGER.error("Direct cancel FAILED for order %s: %s", order_id, _ce)

                # 2. Aggressive Sweep Loop for ghost orders
                cancel_count = self.executor.cancel_all_orders()
                retry = 0
                while cancel_count == 0 and retry < 5:
                    time.sleep(1.0)
                    recheck = self.executor.fetch_order_status(order_id)
                    if (recheck.get("filled_quantity") or 0) > 0:
                        LOGGER.info("Abort cancel loop: Order %s filled in background", order_id)
                        break
                    
                    LOGGER.warning("Cancel sweep found 0 orders. API delay? Retrying...")
                    cancel_count = self.executor.cancel_all_orders()
                    retry += 1
            
                if True: # Always proceed to verification
                    LOGGER.info("Order %s cancel procedure finished. Verifying final status...", order_id)
                    time.sleep(2.0) # Give Schwab time to propagate cancel vs fill race
                    final_status = self.executor.fetch_order_status(order_id)
                    final_state = final_status.get("status", "").upper()
                    final_filled_qty = final_status.get("filled_quantity") or 0
                
                    # Double-check: If Schwab says 0 fills, wait and ask again
                    # (their API sometimes lags behind actual fill propagation)
                    if final_filled_qty == 0 and final_state not in {"CANCELED", "REJECTED"}:
                        LOGGER.info("Order %s shows 0 fills but status=%s. Double-checking in 2s...", order_id, final_state)
                        time.sleep(2.0)
                        recheck = self.executor.fetch_order_status(order_id)
                        recheck_qty = recheck.get("filled_quantity") or 0
                        if recheck_qty > 0:
                            LOGGER.warning("Double-check caught partial fill! Order %s actually filled %s shares", order_id, recheck_qty)
                            final_filled_qty = recheck_qty
                            final_status = recheck
                            final_state = recheck.get("status", "").upper()

                    # Update logic: Handle ANY fill amount, full or partial
                    if final_filled_qty > 0:
                         LOGGER.warning("Order %s had fill qty %s after cancel!", order_id, final_filled_qty)
                         final_filled = True
                         avg_price = final_status.get("avg_fill_price")
                         realized_price = float(avg_price) if avg_price else limit_price
                         self._record_fill(symbol=symbol, side=side, qty=int(final_filled_qty), price=realized_price)
                     
                         if final_filled_qty >= qty:
                             result["fill_status"] = "FILLED"
                         else:
                             result["fill_status"] = "PARTIAL_CANCELED"
                         result["filled_qty"] = int(final_filled_qty)
                    else:
                        if final_state in {"CANCELED", "REJECTED", "EXPIRED"}:
                            LOGGER.info("Order %s confirmed cancelled (Status: %s)", order_id, final_state)
                        else:
                            # Cancel did NOT propagate — order is still live on Schwab.
                            # This is a critical state: an open order we think we cancelled.
                            LOGGER.critical(
                                "CANCEL FAILURE: Order %s still %s after all cancel attempts! "
                                "Manual intervention may be required.",
                                order_id, final_state,
                            )
                            try:
                                self.telegram.notify_error(
                                    "Cancel Failure",
                                    f"Order {order_id} ({side} {qty} {symbol}) still {final_state} after cancel. Check account.",
                                )
                            except Exception:
                                pass
                        result["fill_status"] = "CANCELED_TIMEOUT"
                        result["filled_qty"] = 0
        
            self._record_order(
                alert_id=alert_id,
                symbol=symbol,
                direction=direction,
                side=side,
                qty=qty,
                price=limit_price,
                result=result,
            )
            return final_filled

        finally:
            # Always clear pending tally and order tracking when done (even on exception)
            with self._lock:
                self.pending_limit_count = max(0, self.pending_limit_count - 1)
                self.pending_limit_orders.pop(symbol, None)
            LOGGER.info("[LIMIT] Tally now %d after finishing %s %s", self.pending_limit_count, side, symbol)

    def _submit_order(
        self,
        *,
        alert_id: int,
        symbol: str,
        direction: str,
        side: str,
        qty: int,
        price: float,
        order_type: str = "AUTO",  # AUTO, MARKET, LIMIT
    ) -> bool:
        use_limit = self.use_limit_orders
        if order_type == "MARKET":
            use_limit = False
        elif order_type == "LIMIT":
            use_limit = True

        if use_limit:
            return self._record_and_apply_limit(
                alert_id=alert_id,
                symbol=symbol,
                direction=direction,
                side=side,
                qty=qty,
                price=price,
            )
        else:
            return self._record_and_apply_market(
                alert_id=alert_id,
                symbol=symbol,
                direction=direction,
                side=side,
                qty=qty,
                price=price,
            )

    def _handle_alert(self, alert_id: int, symbol: str, direction: str, price: float, range_cents: float = 0.0, target_limit_price: float = 0.0, pattern_info: dict = None) -> None:
        """Handle a single alert: flip position or enter new one."""
        # Reject immediately if shutdown is in progress (kill switch or stop-loss triggered).
        if self._shutdown_event.is_set():
            LOGGER.warning("[%s] Shutdown in progress; rejecting alert %s for %s", self.name, alert_id, symbol)
            return

        # Check if symbol is allowed for live trading
        if symbol not in self.live_symbols:
            LOGGER.info("Skipping live trade for %s (not in LIVE_SYMBOLS)", symbol)
            return

        # 1. Pattern Lab Filter (The Skip Logic)
        size_factor = 1.0
        chart_bias = "neutral"
        aligned = False
        pattern_bucket = "neutral"
        bull_score = 0.0
        bear_score = 0.0
        if pattern_info:
            decision = pattern_info.get("decision", "enter_or_manage")
            size_factor = float(pattern_info.get("size_factor", 1.0))
            chart_bias = pattern_info.get("chart_bias", "neutral")
            aligned = pattern_info.get("pattern_alignment", False)
            bull_score = pattern_info.get("bullish_score", 0.0)
            bear_score = pattern_info.get("bearish_score", 0.0)
            if aligned:
                pattern_bucket = "aligned"
            elif chart_bias != "neutral":
                pattern_bucket = "countertrend"

            self.pattern_buckets[symbol] = pattern_bucket

            # Check if this alert would close an existing opposing position.
            # Exits are always allowed regardless of alignment; only entries require alignment.
            with self._lock:
                current_position = self.positions.get(symbol, 0)
            is_exit = (direction == "ask-heavy" and current_position > 0) or \
                      (direction == "bid-heavy" and current_position < 0)

            if not is_exit:
                # Execution filter: log non-aligned signals but allow them through
                if pattern_bucket in ("neutral", "countertrend"):
                    self._log_filtered_alert(
                        symbol=symbol, direction=direction, price=price,
                        pattern_bucket=pattern_bucket, chart_bias=chart_bias,
                        size_factor=size_factor, bull_score=bull_score, bear_score=bear_score,
                    )
                    LOGGER.info(
                        "[%s] [UNALIGNED] Allowing %s %s alert - bucket=%s (bias=%s, bull=%.2f, bear=%.2f)",
                        self.name, direction, symbol, pattern_bucket, chart_bias, bull_score, bear_score,
                    )

                if decision == "skip":
                    LOGGER.info("[%s] [FILTER] Skipping %s %s alert due to pattern mismatch (bias=%s)",
                                self.name, direction, symbol, chart_bias)
                    return
            else:
                LOGGER.info(
                    "[%s] [EXIT] Allowing unaligned %s %s exit - bucket=%s (bias=%s, bull=%.2f, bear=%.2f)",
                    self.name, direction, symbol, pattern_bucket, chart_bias, bull_score, bear_score,
                )

        # 2. Dynamic Sizing
        # Start with the pattern-aligned size factor (1.0x – 1.5x from chart engine).
        current_initial_size = int(self.initial_entry_size * size_factor)

        # 2a. Kelly Criterion overlay — scale further based on historical edge.
        # Queries live_trades for this symbol (falls back to global stats when thin).
        # Returns a multiplier in [kelly_min_multiplier, kelly_max_multiplier].
        kelly_mult = self._kelly_size_multiplier(symbol)
        current_initial_size = int(current_initial_size * kelly_mult)

        if current_initial_size <= 0:
            LOGGER.info("[%s] [FILTER] Skipping %s %s due to size_factor/kelly yielding 0 shares",
                        self.name, direction, symbol)
            return

        # Guard against concurrent alerts stacking orders for the same symbol.
        # If another thread is already handling an order for this symbol, skip.
        with self._lock:
            if symbol in self._order_in_flight:
                LOGGER.info("[%s] Order already in flight for %s; skipping concurrent alert %s", self.name, symbol, alert_id)
                return
            self._order_in_flight.add(symbol)

        max_retries = 2
        for attempt in range(max_retries):
            try:
                with self._lock:
                    position = self.positions.get(symbol, 0)

                # Penalty Box Check: Block NEW ENTRIES if in cooldown (per-symbol)
                if position == 0 and time.time() < self.loss_cooldown_until.get(symbol, 0.0):
                    remaining = self.loss_cooldown_until[symbol] - time.time()
                    LOGGER.warning("[%s] In 2-min Penalty Box (%.1fs left); skipping entry alert %s", symbol, remaining, alert_id)
                    self._order_in_flight.discard(symbol)
                    return

                # Cooldown check
                cooldown_seconds = 30.0
                last_exit = self.last_exit_time.get(symbol, 0)

                if direction == "ask-heavy":
                    # Check if already short - skip to avoid stacking
                    if position < 0:
                        LOGGER.info("Already short %s; skip stacking", symbol)
                        self._order_in_flight.discard(symbol)
                        return
                    
                    # If currently long, close the long position first
                    if position > 0:
                        close_qty = abs(position)
                        LOGGER.info("Closing long position on %s (%d shares) (Exit Only - No Flip)", symbol, close_qty)
                        self._submit_order(
                            alert_id=alert_id,
                            symbol=symbol,
                            direction=direction,
                            side="SELL",
                            qty=close_qty,
                            price=price,
                            order_type="MARKET",
                        )
                        with self._lock:
                            self.last_exit_time[symbol] = time.time()
                        try:
                            self.executor.cancel_all_orders()
                        except Exception as exc:
                            LOGGER.warning("Post-exit cancel_all failed: %s", exc)
                        self._order_in_flight.discard(symbol)
                        return

                    # We are flat. Check Cooldown before Entry.
                    if time.time() - last_exit < cooldown_seconds:
                         LOGGER.info("Cooldown active for %s (%.1fs remaining); skipping Short entry",
                                     symbol, cooldown_seconds - (time.time() - last_exit))
                         self._order_in_flight.discard(symbol)
                         return

                    filled = self._submit_order(
                        alert_id=alert_id,
                        symbol=symbol,
                        direction=direction,
                        side="SHORT",
                        qty=current_initial_size,
                        price=target_limit_price if target_limit_price else price,
                        order_type="LIMIT",
                    )
                    LOGGER.info(
                        "[%s] [PATTERN] %s %s | bias=%s aligned=%s bucket=%s size_factor=%.2f bull=%.2f bear=%.2f",
                        self.name, symbol, direction, chart_bias, aligned, pattern_bucket, size_factor, bull_score, bear_score,
                    )
                elif direction == "bid-heavy":
                    # Check if already long - skip to avoid stacking
                    if position > 0:
                        LOGGER.info("Already long %s; skip stacking", symbol)
                        self._order_in_flight.discard(symbol)
                        return
                    
                    # If currently short, close the short position first
                    if position < 0:
                        close_qty = abs(position)
                        LOGGER.info("Closing short position on %s (%d shares) (Exit Only - No Flip)", symbol, close_qty)
                        self._submit_order(
                            alert_id=alert_id,
                            symbol=symbol,
                            direction=direction,
                            side="COVER",
                            qty=close_qty,
                            price=price,
                            order_type="MARKET",
                        )
                        with self._lock:
                            self.last_exit_time[symbol] = time.time()
                        try:
                            self.executor.cancel_all_orders()
                        except Exception as exc:
                            LOGGER.warning("Post-exit cancel_all failed: %s", exc)
                        self._order_in_flight.discard(symbol)
                        return

                    # We are flat. Check Cooldown before Entry.
                    if time.time() - last_exit < cooldown_seconds:
                         LOGGER.info("Cooldown active for %s (%.1fs remaining); skipping Long entry",
                                     symbol, cooldown_seconds - (time.time() - last_exit))
                         self._order_in_flight.discard(symbol)
                         return

                    filled = self._submit_order(
                        alert_id=alert_id,
                        symbol=symbol,
                        direction=direction,
                        side="BUY",
                        qty=current_initial_size,
                        price=target_limit_price if target_limit_price else price,
                        order_type="LIMIT",
                    )
                    LOGGER.info(
                        "[%s] [PATTERN] %s %s | bias=%s aligned=%s bucket=%s size_factor=%.2f bull=%.2f bear=%.2f",
                        self.name, symbol, direction, chart_bias, aligned, pattern_bucket, size_factor, bull_score, bear_score,
                    )

                self._order_in_flight.discard(symbol)
                break

            except BoxedPositionError as e:
                LOGGER.warning("Boxed Position Error caught: %s. Attempt %d/%d. Reconciling and retrying...", e, attempt + 1, max_retries)
                self._reconcile_positions_on_startup()
                time.sleep(1.0)
                if attempt == max_retries - 1:
                    LOGGER.error("Max retries reached for Boxed Position Error. Skipping alert %s.", alert_id)
                    self._order_in_flight.discard(symbol)
                    try:
                        self.telegram.notify_error("Boxed Position Reached", f"Skipping alert {alert_id}")
                    except Exception:
                        pass
            except Exception as e:
                LOGGER.error("An unexpected error occurred in _handle_alert for alert %s: %s", alert_id, e)
                self._order_in_flight.discard(symbol)
                try:
                    self.telegram.notify_error("Schwab API / Trade Execution", f"Alert {alert_id}: {e}")
                except Exception:
                    pass
                break 

    def process_alert(
        self,
        alert_id: int,
        symbol: str,
        direction: str,
        price: float,
        *,
        persist_state: bool = True,
        range_cents: float = 0.0,
        target_limit_price: float = 0.0,
        pattern_info: dict = None,
    ) -> None:
        """Process a single alert: update state and handle order execution."""
        with self._lock:
            # Deduplicate: the same alert can arrive from both the inline callback
            # (grok dispatch) and the DB polling loop.  Rejecting any id we have
            # already seen prevents double-submission.
            if int(alert_id) <= self.last_alert_id:
                LOGGER.info("[%s] Alert %d already processed (last_id=%d); skipping duplicate",
                            self.name, alert_id, self.last_alert_id)
                return
            self.last_alert_id = int(alert_id)

        self._handle_alert(alert_id, symbol, direction, price, range_cents, target_limit_price, pattern_info)
        
        if persist_state and not self.dry_run:
            self._save_state()

    def _poll_account_details(self) -> None:
        """Fetch and update account details."""
        details = self.executor.fetch_account_details()
        if details:
            # Check account stop loss
            liquidation_value = details.get("liquidation_value", 0.0)
            if self.account_stop_loss > 0 and liquidation_value > 0 and liquidation_value < self.account_stop_loss:
                msg = f"🚨 ACCOUNT STOP LOSS TRIGGERED: Value ${liquidation_value:,.2f} < Limit ${self.account_stop_loss:,.2f}"
                LOGGER.critical(msg)
                print(f"\n{'='*60}\n{msg}\n{'='*60}\n", flush=True)
                self._engage_emergency_shutdown("Account Stop Loss Triggered")

            today = time.strftime("%Y-%m-%d")
            with self._lock:
                if today != self.daily_date or self.start_day_liquidation <= 0:
                    self.daily_date = today
                    self.start_day_liquidation = liquidation_value
                    LOGGER.info("📊 New Day Anchor: %s (Liquidation: $%.2f)", self.daily_date, self.start_day_liquidation)
                
                # Update PnL based on liquidation change
                old_pnl = self.daily_pnl
                self.daily_pnl = liquidation_value - self.start_day_liquidation
                details['day_pnl'] = self.daily_pnl
                self.account_details = details
                
                # Notify on significant PnL change (REMOVED - User only wants cooldowns)
                # if abs(self.daily_pnl - old_pnl) >= 1.0:
                #    self.telegram.notify_account_update(details)
            
            self._save_state()
            
            # Log to DB
            try:
                LOGGER.info("Attempting to log account history to DB: %s", self.db_path)
                with self._open_conn() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO account_history (timestamp, liquidation_value, cash_balance, day_pnl, buying_power)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            time.time(),
                            details.get("liquidation_value", 0.0),
                            details.get("cash_balance", 0.0),
                            details.get("day_pnl", 0.0),
                            details.get("buying_power", 0.0),
                        )
                    )
                    conn.commit()
                LOGGER.info("Successfully logged account history")
            except Exception as exc:
                LOGGER.error("Failed to log account history: %s", exc)

    def _account_polling_loop(self) -> None:
        """Background thread to poll account details and reconcile positions."""
        LOGGER.info("Starting account polling thread...")
        while not self._shutdown_event.is_set():
            try:
                self._poll_account_details()
            except Exception as exc:
                LOGGER.error("Account polling error: %s", exc)
            try:
                self._reconcile_positions_on_startup()
            except Exception as exc:
                LOGGER.error("Position reconciliation error: %s", exc)
            # Use event wait so shutdown wakes this thread immediately
            self._shutdown_event.wait(timeout=10)
        LOGGER.info("[%s] Account polling thread exiting (shutdown event set).", self.name)

    def _start_account_polling_thread(self) -> None:
        LOGGER.info("Calling _start_account_polling_thread...")
        thread = threading.Thread(target=self._account_polling_loop, daemon=True)
        thread.start()
        LOGGER.info("Account polling thread started.")

    def run(self) -> None:
        # Keep the hot path responsive: when alerts are flowing we poll on a
        # ~50ms cadence. During lulls we exponentially back off to avoid hot
        # loops, but we watch for DB file writes every 10ms so a new alert can
        # break the longer sleep immediately. This mirrors the low-latency
        # monitoring used in ``paper_trader``.
        LOGGER.info("Starting LiveTrader loop...")
        self._check_kill_switch()
        
        if self.inline:
            LOGGER.info("LiveTrader is running INLINE. Skipping DB polling loop.")
            # Keep the background account polling thread alive
            while not self._shutdown_event.is_set():
                self._check_kill_switch()
                self._check_time_stops()
                time.sleep(1.0)
            LOGGER.error("[%s] Shutdown event set; inline loop exiting.", self.name)
            return
        
        # High-frequency polling back-off
        min_sleep = 0.05
        max_sleep = self.poll_interval
        idle_sleep = min_sleep
        db_mtime = 0.0
        
        monitor_conn = self._open_conn()
        monitor_conn.isolation_level = None
        monitor_cur = monitor_conn.cursor()

        while not self._shutdown_event.is_set():
            try:
                # Poll for new alerts
                new_alerts = []
                monitor_cur.execute(
                    "SELECT rowid, symbol, direction, price, range_cents FROM alerts WHERE rowid > ? ORDER BY rowid ASC",
                    (self.last_alert_id,)
                )
                new_alerts = monitor_cur.fetchall()
                
                if new_alerts:
                    for row in new_alerts:
                        alert_id = row[0]
                        symbol = row[1]
                        direction = row[2]
                        price = float(row[3]) if row[3] is not None else 0.0
                        range_cents = float(row[4]) if len(row) > 4 and row[4] is not None else 0.0
                        
                        # Note: DB polling doesn't currently store target_limit_price.
                        # We would need a DB schema update for that. Since alerts are 
                        # dispatched inline now with target_limit_price inside the dict,
                        # this fallback path just uses the standard price.
                        self.process_alert(alert_id, symbol, direction, price, range_cents=range_cents)
                    
                    # Update mtime so we don't immediately wake up for old writes
                    try:
                        db_mtime = os.stat(self.db_path).st_mtime
                    except Exception:
                        pass
                    
                    idle_sleep = min_sleep
                    time.sleep(0.01)
                else:
                    # Low-latency idle sleep: check DB modified time every 10ms
                    target_sleep = min(idle_sleep * 2, max_sleep)
                    wake_deadline = time.monotonic() + target_sleep
                    
                    woke_for_write = False
                    mtime_probe = 0.01
                    while time.monotonic() < wake_deadline:
                        try:
                            current_mtime = os.stat(self.db_path).st_mtime
                            if current_mtime > db_mtime:
                                db_mtime = current_mtime
                                woke_for_write = True
                                break
                        except Exception:
                            pass
                        time.sleep(mtime_probe)
                    
                    idle_sleep = min_sleep if woke_for_write else target_sleep
                    
            except Exception as exc:
                LOGGER.error("Error in main loop: %s", exc)
                try:
                    self.telegram.notify_error("LiveTrader Crash Loop", str(exc))
                except Exception:
                    pass
                time.sleep(1.0)
            
            self._check_kill_switch()
            self._check_time_stops()


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send Schwab paperMoney/live orders based on alerts")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without sending Schwab orders")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)
    trader = LiveTrader(dry_run=args.dry_run)
    try:
        trader.run()
    except KeyboardInterrupt:
        LOGGER.info("Live trader stopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
