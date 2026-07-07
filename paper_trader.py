# paper_trader.py
# ----------------
# Paper (simulated) trader that mirrors the LiveTrader flip-only logic without
# touching real money. It reads alerts from SQLite, flips between long/short
# with fixed sizes, and records PnL so you can see how the strategy would have
# behaved.
import sqlite3
import time
import threading
import json
import atexit
from pathlib import Path
from contextlib import closing

import os
import sys

DB_PATH = "penny_basing.db"
KILL_SWITCH_PATH = Path(os.getenv("LIVE_KILL_SWITCH_FILE", "kill_switch.flag"))

import config_manager

# Load position size from trading config
_config = config_manager.load_config()
_paper_size = int(_config.get("paper_position_size", 1000))

POSITION_SIZE = _paper_size   # Long size
SHORT_SIZE = _paper_size      # Short size
SLIPPAGE = 0.001
COMMISSION = 0.0
STATE_FILE = "paper_trader_state.json"
BASELINE_CASH = 1_000_000.0

# Sweep cadence for the maker liveness timer (see _maker_timer_loop). Kept
# small so pending exits cross the spread and the kill switch fires within a
# second of their deadline even when the alert feed goes quiet.
MAKER_SWEEP_INTERVAL = 1.0

# ============================================================
# Maker (passive-limit) fill model
# ------------------------------------------------------------
# When enabled, entries/exits rest a passive limit at the near touch instead
# of taking liquidity at the mid. A resting order only fills when a LATER
# observed price trades through it (forward-safe — no peeking). Entries that
# never fill in the window are MISSED; exits that never fill CROSS the spread
# to guarantee we get flat. This reproduces the backtest's maker economics
# (earn ~half-spread, miss the fast moves) in live simulation.
MAKER_ENABLED = bool(_config.get("maker_enabled", False))
MAKER_HALF_SPREAD = float(_config.get("maker_half_spread_cents", 1.0)) / 100.0  # $/share
MAKER_FILL_WINDOW = float(_config.get("maker_fill_window_sec", 30.0))           # seconds


class PaperTrader:
    """Paper trading engine — FLIP-ONLY version.
    Only flips when signal direction changes. No stacking positions.
    """

    def __init__(self, db_path: str = "penny_basing.db", state_file: str = "paper_trader_state.json", name: str = "paper") -> None:
        self._lock = threading.Lock()
        self.dry_run = True
        self.name = name
        self.db_path = db_path
        self.state_file = state_file

        # === Injectable clock (default: wall clock) ===
        # The backfill replay sets this per-alert so deadlines, cooldowns and
        # logged trade timestamps advance on the historical clock instead of
        # "now". Everything on the maker/cooldown path reads self._now().
        self._now_override = None

        # === Injectable price source (default: live DB) ===
        # When set to a {symbol: price} dict, resting-order sweeps read the last
        # OBSERVED price from here instead of querying the alerts table. This
        # keeps the replay forward-safe: the alerts table already holds every
        # (future) row, so a DB query would let an order fill against a price it
        # could not have seen yet.
        self._price_source = None

        self._maker_timer = None
        self._timer_stop = threading.Event()

        self.load_state()
        self._init_db_schema()
        self.last_alert_id = self._get_last_alert_id()

        # === Daily PnL tracking ===
        self.daily_pnl = 0.0
        self.daily_date = time.strftime("%Y-%m-%d")

        # === Exit cooldown (mirrors live trader: 30s after any close) ===
        self.last_exit_time: dict = {}

        # === Maker: resting passive limit orders (one per symbol) ===
        # symbol -> {side, qty, limit, deadline, is_exit, mid}
        self.pending: dict = {}

        atexit.register(self.save_state)

    # ============================================================
    # State Persistence
    # ============================================================
    def _now(self) -> float:
        """Current time on the active clock (wall clock, or replay sim time)."""
        return self._now_override if self._now_override is not None else time.time()

    def load_state(self):
        # Cash and positions are persisted TOGETHER and must stay consistent:
        # cash only ever reflects closed round-trips, so it is only correct
        # relative to the open positions that produced it. The old code kept
        # cash but always discarded positions, so a crash with a position open
        # left the entry's cash movement stranded — a permanent phantom
        # drawdown. We now resume both, or reset both to baseline if the file
        # is missing/corrupt, so the two can never disagree.
        self.cash = BASELINE_CASH
        self.positions = {}
        if not Path(self.state_file).exists():
            return
        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)
            cash = float(data.get("cash", BASELINE_CASH))
            positions = data.get("positions", {}) or {}
            # Validate structure before trusting it — a malformed position must
            # not silently corrupt fills.
            clean = {}
            for sym, pos in positions.items():
                clean[sym] = {
                    "qty": int(pos["qty"]),
                    "entry_price": float(pos["entry_price"]),
                    "entry_time": float(pos.get("entry_time", self._now())),
                }
            self.cash = cash
            self.positions = clean
            print(f"[{self.name.upper()}] Loaded state: Cash ${self.cash:,.2f}, "
                  f"{len(self.positions)} position(s) resumed", flush=True)
        except Exception as e:
            # Reset cash AND positions together so the invariant holds.
            self.cash = BASELINE_CASH
            self.positions = {}
            print(f"[{self.name.upper()}] State file unreadable ({e}); "
                  f"reset to baseline ${BASELINE_CASH:,.2f}", flush=True)

    def save_state(self):
        # Persist cash and positions together (see load_state).
        state = {"cash": self.cash, "positions": self.positions}
        try:
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
            print(f"[PAPER] State saved.", flush=True)
        except Exception as e:
            print(f"[PAPER] Failed to save state: {e}", flush=True)

    # ============================================================
    # DB
    # ============================================================
    def _open_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db_schema(self) -> None:
        with closing(self._open_conn()) as conn:
            cur = conn.cursor()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    symbol TEXT,
                    side TEXT,
                    qty INTEGER,
                    price REAL,
                    slippage REAL,
                    commission REAL,
                    pnl REAL,
                    size_factor REAL DEFAULT 1.0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS paper_positions (
                    symbol TEXT PRIMARY KEY,
                    qty INTEGER,
                    entry_price REAL,
                    current_price REAL,
                    entry_time REAL,
                    pnl REAL,
                    pnl_percent REAL
                )
            """)
            
            # Add size_factor column if it doesn't exist (migration)
            try:
                cur.execute("ALTER TABLE paper_trades ADD COLUMN size_factor REAL DEFAULT 1.0")
            except sqlite3.OperationalError:
                pass

            # Conviction instrumentation (migration): stamp each trade with the
            # order-book imbalance that triggered it so we can later answer
            # "did stronger signals do better?" NULL on rows predating this.
            for _col, _decl in (
                ("imbalance_ratio", "REAL"),
                ("imbalance_duration", "REAL"),
                ("heavy_venues", "INTEGER"),
                ("drift_60s", "REAL"),
            ):
                try:
                    cur.execute(f"ALTER TABLE paper_trades ADD COLUMN {_col} {_decl}")
                except sqlite3.OperationalError:
                    pass

            # Miss diagnostics: every entry that never filled in the maker
            # window. Records how far the resting limit was from where price
            # actually traded — tells "barely missing" (tweak offset) from
            # "wildly missing" (no edge), without abandoning the maker posture.
            cur.execute("""
                CREATE TABLE IF NOT EXISTS paper_misses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    symbol TEXT,
                    side TEXT,
                    rest_limit REAL,
                    mid_at_rest REAL,
                    observed_price REAL,
                    missed_by_cents REAL,
                    imbalance_ratio REAL,
                    imbalance_duration REAL,
                    heavy_venues INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            try:
                cur.execute("ALTER TABLE paper_misses ADD COLUMN drift_60s REAL")
            except sqlite3.OperationalError:
                pass

            cur.execute("DELETE FROM paper_positions")
            conn.commit()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS paper_seen_prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_id INTEGER,
                    symbol TEXT,
                    direction TEXT,
                    price REAL,
                    seen_at REAL DEFAULT (strftime('%s','now'))
                )
            """)

            conn.commit()

    def _get_last_alert_id(self) -> int:
        with closing(self._open_conn()) as conn:
            cur = conn.cursor()
            try:
                cur.execute("SELECT MAX(rowid) FROM alerts")
                row = cur.fetchone()
                return row[0] if row and row[0] else 0
            except sqlite3.OperationalError:
                # Some test setups use a fresh DB without the alerts table; start from 0.
                return 0

    def _get_current_price(self, symbol: str):
        """Most recent observed price for a symbol, or None if we have none.

        Returns None rather than a fabricated fallback — every caller must
        decide what to do without a real quote instead of settling a fill at a
        made-up number (the old code invented 13.35). During replay this reads
        the injected forward-safe price source.
        """
        if self._price_source is not None:
            return self._price_source.get(symbol)
        with closing(self._open_conn()) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT price FROM alerts WHERE symbol=? ORDER BY timestamp DESC LIMIT 1",
                (symbol,),
            )
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else None

    # ============================================================
    # Order Wrapper Functions (required)
    # ============================================================
    def _buy(self, symbol, qty, price):   self._execute_order(symbol, qty, price, "BUY")
    def _sell(self, symbol, qty, price):  self._execute_order(symbol, -qty, price, "SELL")
    def _short(self, symbol, qty, price): self._execute_order(symbol, -qty, price, "SHORT")
    def _cover(self, symbol, qty, price): self._execute_order(symbol, qty, price, "COVER")

    # ============================================================
    # Order Execution
    # ============================================================
    def _execute_order(self, symbol, qty, price, side, size_factor=1.0, conviction=None):
        notional = abs(qty) * price

        # In maker mode the fill price IS the limit price (passive fills earn
        # the spread; forced exit-crosses already bake the half-spread penalty
        # into `price`). Charging taker slippage on top would double-count
        # friction and, worse, make the cash book disagree with the realized
        # PnL book — which uses no slippage — so they could never reconcile.
        slip = 0.0 if MAKER_ENABLED else SLIPPAGE

        # Cash movements
        if qty > 0:  # Buy/Cover
            cost = notional * (1 + slip)
            if cost > self.cash:
                print(f"[PAPER] Not enough cash for {side}", flush=True)
                return
            self.cash -= cost
        else:  # Sell/Short
            proceeds = notional * (1 - slip)
            self.cash += proceeds

        # Old position values
        old_pos = self.positions.get(symbol, {"qty": 0, "entry_price": price})
        old_qty = old_pos["qty"]
        old_entry = old_pos["entry_price"]

        # Create new position if needed
        if symbol not in self.positions:
            self.positions[symbol] = {"qty": 0, "entry_price": price, "entry_time": self._now()}

        pos = self.positions[symbol]
        pos["qty"] = pos["qty"] + qty

        # Weighted average entry for same-direction adds
        if pos["qty"] != 0 and (old_qty * qty > 0):
            total = abs(old_qty) + abs(qty)
            pos["entry_price"] = (
                (abs(old_qty) * old_entry + abs(qty) * price) / total
            )

        # Log trade + PnL
        self._log_trade(symbol, side, abs(qty), price, old_entry, old_qty, size_factor=size_factor, conviction=conviction)

        # If back to flat remove position
        if pos["qty"] == 0:
            del self.positions[symbol]

        self._update_position_db(symbol, cur_price=price)

    # ============================================================
    # Daily PnL reset
    # ============================================================
    def _reset_daily_pnl_if_needed(self):
        today = time.strftime("%Y-%m-%d")
        if today != self.daily_date:
            self.daily_date = today
            self.daily_pnl = 0.0
            print(f"[PAPER] New day detected — Daily PnL reset.", flush=True)

    # ============================================================
    # Trade Logging + PNL Calculation
    # ============================================================
    def _log_trade(self, symbol, side, qty, price, entry_price, old_qty, size_factor=1.0, conviction=None):

        # Correct realized PnL
        pnl = 0.0

        # Closing a LONG
        if old_qty > 0 and side == "SELL":
            pnl = (price - entry_price) * qty

        # Closing a SHORT
        elif old_qty < 0 and side == "COVER":
            pnl = (entry_price - price) * qty

        # === Daily PnL update ===
        self._reset_daily_pnl_if_needed()

        if (old_qty > 0 and side == "SELL") or (old_qty < 0 and side == "COVER"):
            self.daily_pnl += pnl

        # Save daily pnl so UI can read it
        pnl_file = "daily_pnl.txt"
        if "patterns" in self.db_path:
            pnl_file = "daily_pnl_patterns.txt"
        with open(pnl_file, "w") as f:
            f.write(str(self.daily_pnl))

        # Conviction stamp (order-book imbalance that triggered this trade).
        conv = conviction or {}
        _ratio = conv.get("ratio")
        _dur = conv.get("imbalance_duration")
        _venues = conv.get("heavy_venues")
        _drift = conv.get("drift_60s")

        # Log to DB
        with closing(self._open_conn()) as conn:
            cur = conn.cursor()
            slip_cost = 0.0 if MAKER_ENABLED else (qty * price * SLIPPAGE)
            cur.execute("""
                INSERT INTO paper_trades
                (timestamp, symbol, side, qty, price, slippage, commission, pnl, size_factor,
                 imbalance_ratio, imbalance_duration, heavy_venues, drift_60s)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (self._now(), symbol, side, qty, price,
                slip_cost, COMMISSION, pnl, size_factor,
                _ratio, _dur, _venues, _drift))
            conn.commit()

        # === Enhanced log with daily PnL ===
        print(
            f"[PAPER] {side} {qty} {symbol} @ ${price:.3f} | "
            f"Cash: ${self.cash:,.2f} | Trade PnL: ${pnl:.2f} | Daily PnL: ${self.daily_pnl:.2f}",
            flush=True
        )
    #loser
    # ============================================================
    # Update Position Table
    # ============================================================
    def _update_position_db(self, symbol, cur_price=None):
        if symbol not in self.positions:
            with closing(self._open_conn()) as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM paper_positions WHERE symbol=?", (symbol,))
                conn.commit()
            return

        pos = self.positions[symbol]
        cur_price = cur_price if cur_price is not None else self._get_current_price(symbol)

        qty = pos["qty"]
        entry = pos["entry_price"]

        if qty > 0:
            pnl = (cur_price - entry) * qty
        else:
            pnl = (entry - cur_price) * abs(qty)

        cost_basis = abs(qty) * entry
        pnl_pct = (pnl / cost_basis) * 100 if cost_basis != 0 else 0

        with closing(self._open_conn()) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO paper_positions
                (symbol, qty, entry_price, current_price, entry_time, pnl, pnl_percent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (symbol, qty, entry, cur_price, pos["entry_time"], pnl, pnl_pct))
            conn.commit()

    # ============================================================
    # MAKER: passive resting-limit fill model
    # ============================================================
    @staticmethod
    def _is_sell_side(side: str) -> bool:
        return side in ("SHORT", "SELL")

    def _register_pending(self, symbol, side, qty, mid, is_exit, conviction=None, rest_price=None):
        """Rest a passive limit at the near touch (sell at offer, buy at bid).

        `rest_price`, when supplied, is the REAL touch from the live order book
        (grok's target_limit_price) and is used verbatim. When absent — the
        backfill replay only has a mid/last price — we derive the touch as
        mid ± half_spread. `mid` is retained for miss diagnostics either way.
        """
        if rest_price is not None:
            limit = float(rest_price)
        else:
            h = MAKER_HALF_SPREAD
            limit = (mid + h) if self._is_sell_side(side) else (mid - h)
        self.pending[symbol] = {
            "side": side, "qty": qty, "limit": limit,
            "deadline": self._now() + MAKER_FILL_WINDOW, "is_exit": is_exit, "mid": mid,
            "conviction": conviction,
        }
        print(f"[PAPER][MAKER] Rest {side} {qty} {symbol} @ ${limit:.4f} "
              f"(mid ${mid:.4f}, {'exit' if is_exit else 'entry'}, "
              f"{MAKER_FILL_WINDOW:.0f}s window)", flush=True)

    def _fill_pending(self, symbol, p, fill_price, crossed=False):
        side = p["side"]
        qty = p["qty"]
        self.pending.pop(symbol, None)
        print(f"[PAPER][{'CROSS' if crossed else 'MAKER'}] Fill {side} {qty} "
              f"{symbol} @ ${fill_price:.4f}", flush=True)
        signed = {"SHORT": -qty, "SELL": -qty, "BUY": qty, "COVER": qty}[side]
        self._execute_order(symbol, signed, fill_price, side, conviction=p.get("conviction"))
        if p["is_exit"]:
            self.last_exit_time[symbol] = self._now()

    def _check_pending(self, symbol, observed_price, now=None):
        """Resolve a resting order against a freshly observed price.

        Order matters: we check the DEADLINE FIRST. A resting order lives for
        exactly MAKER_FILL_WINDOW seconds; once it expires it is cancelled
        (entry) or crossed (exit). Only while it is still live can a passive
        fill happen. The old code checked the cross condition before the
        deadline, so an order whose window had long since lapsed would still
        "fill" against the next observed price — which on a thin feed can
        arrive minutes or hours later — granting fills the real strategy would
        never get.
        """
        p = self.pending.get(symbol)
        if not p:
            return
        now = now if now is not None else self._now()
        sell_side = self._is_sell_side(p["side"])

        # Expired first.
        if now >= p["deadline"]:
            if p["is_exit"]:
                # didn't fill passively -> cross to get flat (worse by half-spread)
                h = MAKER_HALF_SPREAD
                cross_px = (observed_price - h) if sell_side else (observed_price + h)
                self._fill_pending(symbol, p, cross_px, crossed=True)
            else:
                # entry never filled -> we simply miss the trade
                missed_by = ((p["limit"] - observed_price) if sell_side
                             else (observed_price - p["limit"])) * 100.0
                print(f"[PAPER][MAKER] {p['side']} {symbol} entry unfilled in "
                      f"window -> MISS (by {missed_by:.2f}c)", flush=True)
                self._record_miss(symbol, p, observed_price, missed_by)
                self.pending.pop(symbol, None)
            return

        # Still live -> passive fill only if the market has traded through us.
        crossed = (observed_price >= p["limit"]) if sell_side else (observed_price <= p["limit"])
        if crossed:
            self._fill_pending(symbol, p, p["limit"])

    def _record_miss(self, symbol, p, observed_price, missed_by_cents):
        """Persist an unfilled maker entry for fill-quality analysis."""
        conv = p.get("conviction") or {}
        try:
            with closing(self._open_conn()) as conn:
                conn.execute(
                    """
                    INSERT INTO paper_misses
                    (timestamp, symbol, side, rest_limit, mid_at_rest, observed_price,
                     missed_by_cents, imbalance_ratio, imbalance_duration, heavy_venues, drift_60s)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (self._now(), symbol, p["side"], p["limit"], p.get("mid"),
                     observed_price, missed_by_cents,
                     conv.get("ratio"), conv.get("imbalance_duration"), conv.get("heavy_venues"),
                     conv.get("drift_60s")),
                )
                conn.commit()
        except Exception as e:
            print(f"[PAPER] miss-log failed: {e}", flush=True)

    def _last_alert_price(self, symbol):
        """Most recent observed price for a symbol, or None if we have none.

        A resting order must not fill against a made-up quote, so this never
        invents a fallback. During replay it reads the injected forward-safe
        price source instead of the alerts table (which already holds future
        rows).
        """
        if self._price_source is not None:
            return self._price_source.get(symbol)
        with closing(self._open_conn()) as conn:
            row = conn.execute(
                "SELECT price FROM alerts WHERE symbol=? ORDER BY timestamp DESC LIMIT 1",
                (symbol,),
            ).fetchone()
        return float(row[0]) if row and row[0] is not None else None

    def _sweep_all_pending(self):
        """Advance every resting order on each tick so deadlines fire promptly."""
        if not (MAKER_ENABLED and self.pending):
            return
        for sym in list(self.pending.keys()):
            px = self._last_alert_price(sym)
            if px is not None:
                self._check_pending(sym, px)

    def _maker_handle(self, symbol, direction, price, short_size, long_size, conviction=None, rest_price=None):
        """Flip-only decision, but rest a passive limit instead of taking.

        `rest_price` is the real order-book touch (bid for a buy/cover, offer
        for a sell/short) forwarded from grok; when None we fall back to
        price ± half_spread inside _register_pending.
        """
        if symbol in self.pending:
            return  # one resting order per symbol at a time
        current_qty = self.positions.get(symbol, {}).get("qty", 0)
        cooldown = 30.0
        if direction == "ask-heavy":
            if current_qty > 0:                       # exit long -> rest SELL at offer
                self._register_pending(symbol, "SELL", current_qty, price, is_exit=True, conviction=conviction, rest_price=rest_price)
            elif current_qty < 0:
                return                                # already short
            else:                                     # flat -> rest SHORT entry
                if self._now() - self.last_exit_time.get(symbol, 0) < cooldown:
                    return
                self._register_pending(symbol, "SHORT", short_size, price, is_exit=False, conviction=conviction, rest_price=rest_price)
        elif direction == "bid-heavy":
            if current_qty < 0:                       # exit short -> rest COVER at bid
                self._register_pending(symbol, "COVER", abs(current_qty), price, is_exit=True, conviction=conviction, rest_price=rest_price)
            elif current_qty > 0:
                return                                # already long
            else:                                     # flat -> rest BUY entry
                if self._now() - self.last_exit_time.get(symbol, 0) < cooldown:
                    return
                self._register_pending(symbol, "BUY", long_size, price, is_exit=False, conviction=conviction, rest_price=rest_price)

    # ============================================================
    # FLIP-ONLY ALERT LOGIC
    # ============================================================
    def _handle_alert(self, alert_id: int, symbol: str, direction: str, price: float, range_cents: float = 0.0, pattern_info: dict = None, conviction: dict = None, rest_price: float = None) -> None:
        """Core flip-only logic shared by inline + DB polling paths."""
        
        # Determine dynamic size
        size_factor = 1.0
        if pattern_info and "size_factor" in pattern_info:
            size_factor = float(pattern_info["size_factor"])
        elif pattern_info and "execution" in pattern_info:
            # Fallback for manual overrides
            size_factor = float(pattern_info["execution"].get("qty", POSITION_SIZE)) / POSITION_SIZE
            
        current_position_size = int(POSITION_SIZE * size_factor)
        current_short_size = int(SHORT_SIZE * size_factor)

        self._record_seen_price(alert_id=alert_id, symbol=symbol, direction=direction, price=price)

        # Maker mode: resolve any resting order against this price, then post a
        # fresh passive limit. Instant-fill (taker) logic below is skipped.
        if MAKER_ENABLED:
            self._check_pending(symbol, price)
            self._maker_handle(symbol, direction, price, current_short_size, current_position_size, conviction=conviction, rest_price=rest_price)
            self._update_position_db(symbol, cur_price=price)
            return

        pos = self.positions.get(symbol, {})
        current_qty = pos.get("qty", 0)
        cooldown_seconds = 30.0

        # ASK-HEAVY → exit long OR enter short (not both on same alert)
        if direction == "ask-heavy":
            if current_qty > 0:  # close long, then wait for next alert to enter short
                self._execute_order(symbol, -current_qty, price, "SELL", size_factor=size_factor)
                self.last_exit_time[symbol] = self._now()
                return
            elif current_qty < 0:  # already short, skip
                pass
            else:  # flat — check cooldown before entering short
                last_exit = self.last_exit_time.get(symbol, 0)
                if self._now() - last_exit < cooldown_seconds:
                    remaining = cooldown_seconds - (self._now() - last_exit)
                    print(f"[{self.name.upper()}] Cooldown active for {symbol} ({remaining:.1f}s remaining); skipping Short entry", flush=True)
                    return
                self._execute_order(symbol, -current_short_size, price, "SHORT", size_factor=size_factor)

        # BID-HEAVY → exit short OR enter long (not both on same alert)
        elif direction == "bid-heavy":
            if current_qty < 0:  # close short, then wait for next alert to enter long
                self._execute_order(symbol, abs(current_qty), price, "COVER", size_factor=size_factor)
                self.last_exit_time[symbol] = self._now()
                return
            elif current_qty > 0:  # already long, skip
                pass
            else:  # flat — check cooldown before entering long
                last_exit = self.last_exit_time.get(symbol, 0)
                if self._now() - last_exit < cooldown_seconds:
                    remaining = cooldown_seconds - (self._now() - last_exit)
                    print(f"[{self.name.upper()}] Cooldown active for {symbol} ({remaining:.1f}s remaining); skipping Long entry", flush=True)
                    return
                self._execute_order(symbol, current_position_size, price, "BUY", size_factor=size_factor)

        # Update current price and PnL even when no trade is executed
        self._update_position_db(symbol, cur_price=price)

    def _record_seen_price(self, alert_id: int, symbol: str, direction: str, price: float) -> None:
        """Persist the Schwab quote we acted on so we can audit simulated fills."""

        print(
            f"[PAPER] Alert {alert_id} {symbol} {direction} @ ${price:.4f} (Schwab quote)",
            flush=True,
        )

        with closing(self._open_conn()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO paper_seen_prices (alert_id, symbol, direction, price)
                VALUES (?, ?, ?, ?)
                """,
                (alert_id, symbol, direction, price),
            )
            conn.commit()

    def _check_kill_switch(self) -> None:
        """Flatten all positions and exit gracefully if kill switch file is present."""
        if not KILL_SWITCH_PATH.exists():
            return
        print(f"[{self.name.upper()}] Kill switch detected. Flattening all positions and exiting...", flush=True)
        with self._lock:
            snapshot = dict(self.positions)
        for sym, pos in snapshot.items():
            qty = pos.get("qty", 0)
            if qty == 0:
                continue
            # No fabricated price: if we have no real quote, flatten at the
            # entry price (zero realized PnL) rather than settling on a made-up
            # number.
            price = self._get_current_price(sym)
            if price is None:
                price = pos.get("entry_price")
            if price is None:
                print(f"[{self.name.upper()}] No price for {sym}; leaving position open", flush=True)
                continue
            if qty > 0:
                self._execute_order(sym, -qty, price, "SELL")
            else:
                self._execute_order(sym, abs(qty), price, "COVER")
        self.save_state()
        print(f"[{self.name.upper()}] Positions flattened. Exiting.", flush=True)
        sys.exit(0)

    def process_alert(self, alert_id: int, symbol: str, direction: str, price: float, **kwargs) -> None:
        """Expose inline hook so grok can dispatch alerts directly."""
        self._check_kill_switch()
        range_cents = kwargs.get("range_cents", 0.0)
        pattern_info = kwargs.get("pattern_info")
        # Conviction passed from grok's alert dict (None when polling the DB).
        conviction = None
        if any(k in kwargs for k in ("ratio", "imbalance_duration", "heavy_venues", "drift_60s")):
            conviction = {
                "ratio": kwargs.get("ratio"),
                "imbalance_duration": kwargs.get("imbalance_duration"),
                "heavy_venues": kwargs.get("heavy_venues"),
                # 60s trailing price drift at alert time. Sign vs trade
                # direction = counter-trend / trend-aligned A/B (tag only —
                # no filtering until forward data confirms the backtests).
                "drift_60s": kwargs.get("drift_60s"),
            }
        # Real order-book touch from grok (bid for a buy/cover, offer for a
        # sell/short). None when polling the DB or replaying history, where we
        # only have a mid/last price and fall back to mid ± half_spread. Guard
        # against grok's empty-book 0.0 default — a bogus 0 touch would never
        # fill a buy and would instantly fill a sell.
        rest_price = kwargs.get("target_limit_price")
        try:
            rest_price = float(rest_price) if rest_price and float(rest_price) > 0 else None
        except (TypeError, ValueError):
            rest_price = None
        with self._lock:
            self.last_alert_id = max(self.last_alert_id, int(alert_id))
            self._sweep_all_pending()  # advance every resting order's deadline
            self._handle_alert(alert_id, symbol, direction, price, range_cents, pattern_info, conviction=conviction, rest_price=rest_price)
            self.save_state()

    def monitor_alerts(self):
        print("[PAPER] Monitoring alerts (Flip-Only Mode)…", flush=True)

        # Sleep is adaptive: immediately after seeing alerts we use the 50ms
        # minimum to react quickly; consecutive empty polls (no rows newer
        # than last_alert_id) double the wait time up to a 2s ceiling to
        # avoid hot loops when idle. To avoid sleeping through a new alert
        # that arrives just after a poll, we watch for DB file writes during
        # the longer idle backoff and wake early when the file mtime changes.
        # Fast-path latency target when alerts are flowing. Compared to the
        # original fixed 1s poll, a new alert is usually seen within ~50ms
        # after activity or ~10ms during idle file-probing.
        min_sleep = 0.05

        # While idling we probe the DB file mtime on a tighter cadence so a
        # newly written alert is noticed within ~10ms even if the outer backoff
        # has grown toward the 2s ceiling.
        mtime_probe = 0.01

        max_sleep = 2.0    # back off to 2s when idle
        idle_sleep = min_sleep
        db_path = Path(self.db_path)
        last_db_mtime = db_path.stat().st_mtime if db_path.exists() else 0.0

        # Open one long-lived connection for monitoring
        monitor_conn = self._open_conn()
        monitor_conn.isolation_level = None # Ensure auto-commit mode to see fresh data
        cur = monitor_conn.cursor()

        while True:
            try:
                cur.execute("""
                    SELECT rowid, symbol, direction, price
                    FROM alerts
                    WHERE rowid > ?
                    ORDER BY rowid ASC
                """, (self.last_alert_id,))
                rows = cur.fetchall()
            except sqlite3.OperationalError:
                # Table might not exist yet if grok.py is starting up
                time.sleep(1)
                continue

            for row in rows:
                alert_id, symbol, direction, price = row
                self.process_alert(alert_id, symbol, direction, price)

            activity_detected = bool(rows)

            # Track DB file changes so we can wake early from long sleeps.
            db_mtime_snapshot = db_path.stat().st_mtime if db_path.exists() else last_db_mtime

            if activity_detected:
                # Fresh alerts observed → use minimum sleep for quick response.
                idle_sleep = min_sleep
                last_db_mtime = db_mtime_snapshot
                time.sleep(idle_sleep)
                continue

            # No alerts observed → back off exponentially up to the ceiling,
            # but poll the DB mtime every few milliseconds so we can break out
            # quickly if new alerts are inserted right after the query.
            target_sleep = min(idle_sleep * 2, max_sleep)
            wake_deadline = time.monotonic() + target_sleep
            woke_for_write = False

            while time.monotonic() < wake_deadline:
                time.sleep(mtime_probe)
                current_mtime = db_path.stat().st_mtime if db_path.exists() else 0.0
                if current_mtime != db_mtime_snapshot:
                    woke_for_write = True
                    db_mtime_snapshot = current_mtime
                    break

            last_db_mtime = db_mtime_snapshot
            idle_sleep = min_sleep if woke_for_write else target_sleep

            # If a write occurred, immediately loop to fetch new alerts; if not,
            # we've already slept the full backoff duration via the wake loop.
            if woke_for_write:
                continue

    # ============================================================
    # Maker liveness timer
    # ============================================================
    def _maker_timer_loop(self):
        """Advance resting orders and honor the kill switch on a fixed cadence.

        Sweeps and the kill-switch check used to run ONLY when a new alert
        arrived. On a quiet feed that meant a pending exit never crossed the
        spread at its deadline (we'd hold the position indefinitely) and
        `touch kill_switch.flag` did nothing until the next alert. This timer
        fires every MAKER_SWEEP_INTERVAL seconds so both happen on time.
        """
        while not self._timer_stop.is_set():
            try:
                self._check_kill_switch()  # may sys.exit if flag present
                with self._lock:
                    self._sweep_all_pending()
            except SystemExit:
                raise
            except Exception as e:
                print(f"[PAPER][MAKER] timer sweep error: {e}", flush=True)
            self._timer_stop.wait(MAKER_SWEEP_INTERVAL)

    def start_maker_timer(self):
        """Start the liveness timer (idempotent). No-op unless maker mode is on.

        Called from both the subprocess entrypoint (start) and grok's inline
        setup, since inline mode constructs the trader but never calls start().
        """
        if not MAKER_ENABLED:
            return None
        if self._maker_timer and self._maker_timer.is_alive():
            return self._maker_timer
        self._timer_stop.clear()
        self._maker_timer = threading.Thread(
            target=self._maker_timer_loop, daemon=True, name=f"{self.name}-maker-timer")
        self._maker_timer.start()
        print(f"[PAPER][MAKER] Liveness timer started ({MAKER_SWEEP_INTERVAL:.0f}s cadence)", flush=True)
        return self._maker_timer

    # ============================================================
    # Start Trader Thread
    # ============================================================
    def start(self):
        t = threading.Thread(target=self.monitor_alerts, daemon=True)
        t.start()
        self.start_maker_timer()
        print(f"[PAPER] LIVE (Flip-Only Mode) | Cash: ${self.cash:,.2f}", flush=True)
        return t


if __name__ == "__main__":
    trader = PaperTrader()
    trader.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[PAPER] Stopped.", flush=True)
