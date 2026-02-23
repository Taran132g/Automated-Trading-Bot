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

from dotenv import load_dotenv
from schwab.auth import easy_client
from schwab.orders import equities as equity_orders
import config_manager

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
            self.client = easy_client(
                api_key=api_key,
                app_secret=app_secret,
                callback_url=redirect_uri,
                token_path=token_file,
            )
        except Exception as exc:  # pragma: no cover - network interaction
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

        try:
            response = self.client.place_order(self.account_id, payload)
        except Exception as exc:  # pragma: no cover - network interaction
            LOGGER.error("Order failed: %s", exc)
            result["error"] = str(exc)
            return result

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
            response = fetch_quote([symbol])
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

    def cancel_all_orders(self) -> bool:
        """Cancel all open/working orders on the account.
        
        Tries native cancel_all first; falls back to fetching all orders
        and cancelling each WORKING one individually.
        """
        if self.dry_run:
            LOGGER.info("[DRY-RUN] Skip cancel_all_orders")
            return True

        # Try native cancel_all first
        cancel_all = getattr(self.client, "cancel_all_orders", None)
        if cancel_all is not None:
            try:
                cancel_all(self.account_id)
                LOGGER.info("Cancel-all request sent (native)")
                return True
            except Exception as exc:
                LOGGER.warning("Native cancel_all failed: %s. Falling back to individual cancels.", exc)

        # Fallback: fetch all orders and cancel each WORKING one
        get_orders = getattr(self.client, "get_orders_for_account", None) or getattr(self.client, "get_orders", None)
        if get_orders is None:
            LOGGER.warning("Schwab client does not expose get_orders; cannot cancel working orders")
            return False

        try:
            from datetime import datetime, timedelta
            # Fetch today's orders
            now = datetime.utcnow()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            response = get_orders(self.account_id, from_entered_datetime=start, to_entered_datetime=now)
            orders = response.json() if hasattr(response, "json") else response
        except Exception as exc:
            LOGGER.error("Failed to fetch orders for cancel-all fallback: %s", exc)
            return False

        if not isinstance(orders, list):
            LOGGER.warning("Unexpected orders response type: %s", type(orders))
            return False

        cancelled_count = 0
        cancel_one = getattr(self.client, "cancel_order", None)
        if cancel_one is None:
            LOGGER.warning("Schwab client does not expose cancel_order; cannot cancel")
            return False

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
        return True


class LiveTrader:
    """Flip-only alert monitor that places Schwab orders.

    Think of this as a traffic cop: it listens for new alerts, checks whether
    you're already long/short, and then decides whether to flip, close, or
    stay flat. The class also guards against runaway trading via rate limits
    and a kill-switch file.
    """

    def __init__(self, *, dry_run: bool = False, executor: Optional[SchwabOrderExecutor] = None, name: str = "default") -> None:
        self.name = name  # Identifier for multi-account logging
        self.db_path = Path(os.getenv("DB_PATH", "penny_basing.db"))
        
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
        self.recent_pi: list[float] = []  # Rolling PI per share for last 5 trades
        self.pi_cooldown_until: float = 0.0  # Timestamp when PI cooldown ends
        self.pending_limit_orders: Dict[str, str] = {}  # symbol -> order_id (prevent duplicates)
        self.active_limit_stops: Dict[str, bool] = {}  # symbol -> True (if a limit lock-in is active)
        self.last_exit_time: Dict[str, float] = {}  # Track last exit time for cooldown
        self.position_entry_times: Dict[str, float] = {}
        self.position_entry_prices: Dict[str, float] = {}  # Track entry prices for PnL
        self.daily_pnl: float = 0.0
        self.daily_date: str = time.strftime("%Y-%m-%d")
        self.check_bad_fills = _bool_env("LIVE_CHECK_BAD_FILLS", True)
        self.consecutive_bad_fills: int = 0  # Track consecutive bad fills
        self.live_symbols = self._parse_live_symbols()
        self.account_details: Dict[str, float] = {}
        self.account_details: Dict[str, float] = {}
        self.min_range_cents = int(os.getenv("MIN_RANGE_CENTS", "2"))
        
        # Penalty Box State
        # Penalty Box State
        self.consecutive_loss_cents: float = 0.0
        self.loss_cooldown_until: float = 0.0
        
        self._lock = threading.RLock()

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
            LOGGER.warning("⚠️ Position mismatch detected! Auto-reconciling to trust Schwab...")
            for m in mismatches:
                LOGGER.warning("   - %s", m)
            
            # Trust Schwab
            with self._lock:
                self.positions = schwab_positions.copy()
                
                # Clean up entry times for positions that no longer exist
                for symbol in list(self.position_entry_times.keys()):
                    if symbol not in self.positions:
                        del self.position_entry_times[symbol]
                
                # Initialize entry time for newly discovered positions (start tracking from now)
                for symbol in self.positions:
                    if symbol not in self.position_entry_times:
                        self.position_entry_times[symbol] = time.time()
                
                self._save_state()
            LOGGER.info("✅ State auto-corrected to match Schwab.")
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
                self.account_details = data.get("account_details", {})
                self.consecutive_loss_cents = float(data.get("consecutive_loss_cents", 0.0))
                self.loss_cooldown_until = float(data.get("loss_cooldown_until", 0.0))
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
        if now < self.pi_cooldown_until:
            active_cooldowns.append({
                "reason": "PI Cooldown",
                "detail": "Avg price improvement ≤ $0.001 over last 5 trades",
                "remaining_seconds": round(self.pi_cooldown_until - now),
                "until": self.pi_cooldown_until,
            })
        if now < self.loss_cooldown_until:
            active_cooldowns.append({
                "reason": "Loss Cooldown",
                "detail": f"Consecutive losses exceeded threshold",
                "remaining_seconds": round(self.loss_cooldown_until - now),
                "until": self.loss_cooldown_until,
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
                "consecutive_loss_cents": self.consecutive_loss_cents,
                "loss_cooldown_until": self.loss_cooldown_until,
                "pi_cooldown_until": self.pi_cooldown_until,
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
                    self.consecutive_loss_cents += abs(per_share_pnl)
                    LOGGER.info("Loss detected ($%.4f/share). Cumulative Bucket: $%.4f", per_share_pnl, self.consecutive_loss_cents)
                    
                    if self.consecutive_loss_cents >= 0.02:
                        self.loss_cooldown_until = time.time() + 120
                        self.consecutive_loss_cents = 0.0 # Reset after penalty applied
                        msg = f"🚨 PENALTY BOX TRIGGERED: Cumulative Loss >= $0.02/share. Cooldown for 2 minutes."
                        LOGGER.warning(msg)
                        print(f"\n{'='*60}\n{msg}\n{'='*60}\n", flush=True)
                else:
                    # Empathetic Reset: Any profitable trade resets the anxiety bucket
                    if self.consecutive_loss_cents > 0:
                        LOGGER.info("Win/Flat trade ($%.4f/share) resets cumulative loss bucket (was $%.4f)", per_share_pnl, self.consecutive_loss_cents)
                    self.consecutive_loss_cents = 0.0
            
            # Update daily PnL
            today = time.strftime("%Y-%m-%d")
            if today != self.daily_date:
                self.daily_date = today
                self.daily_pnl = 0.0
            if pnl != 0:
                self.daily_pnl += pnl
            
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



    def _enforce_trade_rate_limit(self) -> None:
        cutoff = time.time() - 3600
        self.trade_timestamps = [ts for ts in self.trade_timestamps if ts >= cutoff]
        if len(self.trade_timestamps) > self.max_trades_per_hour:
            msg = f"⚠️  Trade rate exceeded limit ({len(self.trade_timestamps)} in the last hour)"
            LOGGER.warning(msg)
            print(f"\n{'='*60}\n{msg}\n{'='*60}\n", flush=True)

    def _engage_emergency_shutdown(self, reason: str) -> None:
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

        for symbol, qty in list(self.positions.items()):
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
        raise SystemExit(1)

    def _check_kill_switch(self) -> None:
        if self.kill_switch_path.exists():
            LOGGER.error("Kill switch file %s detected", self.kill_switch_path)
            self._engage_emergency_shutdown("Kill switch activated")

    def _check_time_stops(self) -> None:
        """Disabled — positions close only on opposing signals."""
        pass

    def _check_profit_limits(self) -> None:
        """Lock in profits with a limit order if PnL crosses $0.03 threshold."""
        if not self.positions:
            return

        with self._lock:
            # Snapshot positions to iterate safely
            current_positions = dict(self.positions)

        for symbol, qty in current_positions.items():
            if qty == 0:
                self.active_limit_stops.pop(symbol, None)
                continue

            if self.active_limit_stops.get(symbol):
                continue  # Limit already submitted

            entry_price = self.position_entry_prices.get(symbol, 0.0)
            if entry_price <= 0:
                continue

            current_price = self._latest_price(symbol)
            if not current_price or current_price <= 0:
                continue

            direction = "LONG" if qty > 0 else "SHORT"
            pnl = (current_price - entry_price) if direction == "LONG" else (entry_price - current_price)

            if pnl >= 0.03:
                target_price = entry_price + 0.01 if direction == "LONG" else entry_price - 0.01
                side = "SELL" if direction == "LONG" else "COVER"

                LOGGER.info("💰 Profit limit trigger for %s at Current: $%.4f (Entry: $%.4f). Submitting target Limit %s at $%.4f", 
                            symbol, current_price, entry_price, side, target_price)

                # Mark as active *before* submitting to prevent duplicate submissions on the next poll
                self.active_limit_stops[symbol] = True

                try:
                    self._submit_order(
                        alert_id=-1,
                        symbol=symbol,
                        direction="profit-limit",
                        side=side,
                        qty=abs(qty),
                        price=target_price,
                        order_type="LIMIT",
                    )
                except Exception as exc:
                    LOGGER.error("Failed to submit profit limit for %s: %s", symbol, exc)
                    self.active_limit_stops.pop(symbol, None)  # Re-allow attempt if failed

    # ------------------------------------------------------------------
    # Order + alert processing
    # ------------------------------------------------------------------
    def _check_fill_quality(self, side: str, price: float) -> None:
        """Check for 'bad fills' (longs at .99, shorts at .01) and log consecutive occurrences."""
        if not self.check_bad_fills:
            return

        if price is None or price <= 0:
            return

        cents = price % 1.0
        # Floating point math safety
        is_99 = 0.985 <= cents <= 0.995
        is_01 = 0.005 <= cents <= 0.015

        bad_fill = False
        fill_type = ""
        if side in {"BUY", "COVER"} and is_99:
            bad_fill = True
            fill_type = ".99"
        elif side in {"SELL", "SHORT"} and is_01:
            bad_fill = True
            fill_type = ".01"

        if bad_fill:
            self.consecutive_bad_fills += 1
            msg = f"⚠️  BAD FILL #{self.consecutive_bad_fills}: {side} at ${price:.2f} ({fill_type})"
            LOGGER.warning(msg)
            print(f"\n{'='*60}\n{msg}\n{'='*60}\n", flush=True)
            
            if self.consecutive_bad_fills >= 3:
                LOGGER.error("🚨 ALERT: %d consecutive bad fills detected!", self.consecutive_bad_fills)
                print(f"\n🚨🚨🚨 ALERT: {self.consecutive_bad_fills} CONSECUTIVE BAD FILLS! 🚨🚨🚨\n", flush=True)
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
        """Track price improvement per share for last 5 trades."""
        self.recent_pi.append(pi_per_share)
        if len(self.recent_pi) > 5:
            self.recent_pi.pop(0)
        avg_pi = sum(self.recent_pi) / len(self.recent_pi)
        LOGGER.info("PI per share: $%.4f  (avg last %d: $%.4f)",
                    pi_per_share, len(self.recent_pi), avg_pi)
        if len(self.recent_pi) >= 5 and avg_pi <= 0.001:
            self.pi_cooldown_until = time.time() + 1800  # 30 minutes
            LOGGER.warning("⚠️ PI COOLDOWN: Avg PI $%.4f <= $0.001 over last 5 trades. "
                          "Pausing entries until %s",
                          avg_pi, time.strftime('%H:%M:%S', time.localtime(self.pi_cooldown_until)))

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
            self._record_fill(symbol=symbol, side=side, qty=qty, price=price)
            filled = True
            filled_qty = qty
            fill_status = "FILLED"
            result["filled_via"] = "MARKET"

            # Fetch actual fill price for bad fill detection and PI tracking
            order_id = result.get("order_id")
            if order_id and not result.get("dry_run"):
                # Fetch quote for PI calculation before waiting
                quote = self.executor.fetch_quote(symbol)
                quoted_bid = float(quote.get("bidPrice", 0)) if quote else 0.0
                quoted_ask = float(quote.get("askPrice", 0)) if quote else 0.0
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

        # Dedup guard: skip if there's already a pending limit order for this symbol
        existing = self.pending_limit_orders.get(symbol)
        if existing:
            LOGGER.info("Limit order %s already pending for %s; skipping duplicate", existing, symbol)
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
             return False

        # Track this as a pending order to prevent duplicates
        self.pending_limit_orders[symbol] = order_id

        try:
            # Wait and Poll
            LOGGER.info("Waiting %.1fs for fill on order %s...", self.limit_poll_interval, order_id)
            time.sleep(self.limit_poll_interval)
        
            status = self.executor.fetch_order_status(order_id)
            order_status = status.get("status", "").upper()
            filled_qty = status.get("filled_quantity") or 0
            avg_price = status.get("avg_fill_price")
        
            LOGGER.info("Order %s status: %s (Filled: %s)", order_id, order_status, filled_qty)

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
                # Still Open (WORKING, QUEUED, etc) -> CANCEL ALL WORKING ORDERS
                LOGGER.info("Order %s not filled (Status: %s). Cancelling ALL working orders...", order_id, order_status)
                cancel_success = self.executor.cancel_all_orders()
            
                if cancel_success:
                    LOGGER.info("Order %s cancelled request sent. Verifying final status...", order_id)
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
                         LOGGER.info("Order %s confirmed cancelled (Status: %s)", order_id, final_state)
                         result["fill_status"] = "CANCELED_TIMEOUT"
                         result["filled_qty"] = 0
                else:
                    # If cancel failed, it might have just filled?
                    LOGGER.warning("Failed to cancel order %s. Re-checking status...", order_id)
                    status = self.executor.fetch_order_status(order_id)
                    last_filled = status.get("filled_quantity") or 0
                
                    if last_filled > 0:
                         final_filled = True
                         avg_price = status.get("avg_fill_price")
                         realized_price = float(avg_price) if avg_price else limit_price
                         self._record_fill(symbol=symbol, side=side, qty=int(last_filled), price=realized_price)
                         result["fill_status"] = "FILLED" if last_filled >= qty else "PARTIAL_UNK"
                         result["filled_qty"] = int(last_filled)
                    else:
                         result["fill_status"] = "CANCEL_FAILED"
        
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
            # Always clear pending order when done (even on exception)
            self.pending_limit_orders.pop(symbol, None)

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

    def _handle_alert(self, alert_id: int, symbol: str, direction: str, price: float, range_cents: float = 0.0) -> None:
        # Check if symbol is allowed for live trading
        if symbol not in self.live_symbols:
            LOGGER.info("Skipping live trade for %s (not in LIVE_SYMBOLS)", symbol)
            return

        max_retries = 2
        for attempt in range(max_retries):
            try:
                with self._lock:
                    position = self.positions.get(symbol, 0)

                # Penalty Box Check: Block NEW ENTRIES if in cooldown
                # Exits/Flips from existing positions are allowed.
                if position == 0 and time.time() < self.loss_cooldown_until:
                     remaining = self.loss_cooldown_until - time.time()
                     LOGGER.warning("In 2-min Penalty Box (%.1fs left); skipping entry alert %s", remaining, alert_id)
                     return

                # Volatility Filter (ENTRY ONLY)
                # If we are FLAT (position == 0) and range is too low, skip entry.
                # Exits are ALWAYS allowed (so if position != 0, we ignore this check).
                # if position == 0 and range_cents > 0 and range_cents <= self.min_range_cents:
                #     LOGGER.info("Skipping entry for %s: Volatility range %.2fc <= %.2fc", symbol, range_cents, self.min_range_cents)
                #     return

                # Cooldown check
                cooldown_seconds = 30.0
                last_exit = self.last_exit_time.get(symbol, 0)
                if time.time() - last_exit < cooldown_seconds:
                    # We are in cooldown. Only allow logical exits?
                    # Actually, if we are in cooldown, it means we just exited.
                    # So we shouldn't be entering.
                    # But what if we are closing a position during cooldown? 
                    # (e.g. manual intervention or some other logic).
                    # The request is "wait 30s before trading the next alert".
                    # This usually implies ENTRY. Exits should always be allowed.
                    pass

                if direction == "ask-heavy":
                    # Check if already short - skip to avoid stacking
                    if position < 0:
                        LOGGER.info("Already short %s; skip stacking", symbol)
                        return
                    
                    # If currently long, close the long position first (use actual position size)
                    if position > 0:
                        close_qty = abs(position)
                        LOGGER.info("Closing long position on %s (%d shares) (Exit Only - No Flip)", symbol, close_qty)
                        # FORCE MARKET CLOSE FOR EXITS
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
                        return # EXIT ONLY - NO FLIP

                    # We are flat. Check Cooldown before Entry.
                    if time.time() - self.last_exit_time.get(symbol, 0) < cooldown_seconds:
                         LOGGER.info("Cooldown active for %s (%.1fs remaining); skipping Short entry", 
                                     symbol, cooldown_seconds - (time.time() - self.last_exit_time.get(symbol, 0)))
                         return


                    # Check PI cooldown (avg PI too low = poor fills, take a break)
                    if time.time() < self.pi_cooldown_until:
                        remaining = self.pi_cooldown_until - time.time()
                        LOGGER.info("PI cooldown active (%.0fs remaining); skipping entry", remaining)
                        return
                    filled = self._submit_order(
                        alert_id=alert_id,
                        symbol=symbol,
                        direction=direction,
                        side="SHORT",
                        qty=self.initial_entry_size,
                        price=price,
                        order_type="LIMIT",
                    )
                elif direction == "bid-heavy":
                    # Check if already long - skip to avoid stacking
                    if position > 0:
                        LOGGER.info("Already long %s; skip stacking", symbol)
                        return
                    
                    # If currently short, close the short position first (use actual position size)
                    if position < 0:
                        close_qty = abs(position)
                        LOGGER.info("Closing short position on %s (%d shares) (Exit Only - No Flip)", symbol, close_qty)
                        # FORCE MARKET CLOSE FOR EXITS
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
                        return # EXIT ONLY - NO FLIP

                    # We are flat. Check Cooldown before Entry.
                    if time.time() - self.last_exit_time.get(symbol, 0) < cooldown_seconds:
                         LOGGER.info("Cooldown active for %s (%.1fs remaining); skipping Long entry", 
                                     symbol, cooldown_seconds - (time.time() - self.last_exit_time.get(symbol, 0)))
                         return


                    # Check PI cooldown (avg PI too low = poor fills, take a break)
                    if time.time() < self.pi_cooldown_until:
                        remaining = self.pi_cooldown_until - time.time()
                        LOGGER.info("PI cooldown active (%.0fs remaining); skipping entry", remaining)
                        return
                    filled = self._submit_order(
                        alert_id=alert_id,
                        symbol=symbol,
                        direction=direction,
                        side="BUY",
                        qty=self.initial_entry_size,
                        price=price,
                        order_type="LIMIT",
                    )
                
                # If successful, break out of retry loop
                break 
            
            except BoxedPositionError as e:
                LOGGER.warning("Boxed Position Error caught: %s. Attempt %d/%d. Reconciling and retrying...", e, attempt + 1, max_retries)
                self._reconcile_positions_on_startup()
                time.sleep(1.0) # Give broker a moment to update
                if attempt == max_retries - 1:
                    LOGGER.error("Max retries reached for Boxed Position Error. Skipping alert %s.", alert_id)
            except Exception as e:
                LOGGER.error("An unexpected error occurred in _handle_alert for alert %s: %s", alert_id, e)
                break # Don't retry for other unexpected errors

    def process_alert(
        self,
        alert_id: int,
        symbol: str,
        direction: str,
        price: float,
        *,
        persist_state: bool = True,
        range_cents: float = 0.0,
    ) -> None:
        """Process a single alert, optionally persisting state immediately.

        This entry point lets ``grok.py`` dispatch alerts inline without
        waiting for the polling loop, while keeping the standalone ``run``
        method available for tailing the DB.
        """
        with self._lock:
            self.last_alert_id = max(self.last_alert_id, int(alert_id))
            # Fast-path inline alert
            self._handle_alert(alert_id, symbol, direction, price, range_cents)
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

            with self._lock:
                self.account_details = details
            
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
        while True:
            try:
                self._poll_account_details()
            except Exception as exc:
                LOGGER.error("Account polling error: %s", exc)
            try:
                self._reconcile_positions_on_startup()
            except Exception as exc:
                LOGGER.error("Position reconciliation error: %s", exc)
            time.sleep(10)

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
        
        while True:
            try:
                # Poll for new alerts
                new_alerts = []
                with self._open_conn() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT rowid, symbol, direction, price, range_cents FROM alerts WHERE rowid > ? ORDER BY rowid ASC",
                        (self.last_alert_id,)
                    )
                    new_alerts = cur.fetchall()
                
                if new_alerts:
                    for row in new_alerts:
                        alert_id = row[0]
                        symbol = row[1]
                        direction = row[2]
                        price = float(row[3]) if row[3] is not None else 0.0
                        range_cents = float(row[4]) if len(row) > 4 and row[4] is not None else 0.0
                        
                        self.process_alert(alert_id, symbol, direction, price, range_cents=range_cents)
                    
                    # Short sleep if we had activity
                    time.sleep(0.05)
                else:
                    # Sleep longer if no activity
                    time.sleep(self.poll_interval)
                    
            except Exception as exc:
                LOGGER.error("Error in main loop: %s", exc)
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
