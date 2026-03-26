"""pattern_trader.py — Standalone chart-pattern breakout trader (paper simulation).

Runs alongside the scalping strategy, trading independently on confirmed chart
pattern breakouts. Signals come from ChartPatternDetector on 1-minute bar closes.

Exit cascade (checked in order on every bar close):
    1. Pattern failure stop  — price retreats back through stop_level
    2. ATR stop              — fixed level at entry ± (atr_stop_multiplier × ATR)
    3. Trailing stop         — activates after partial profit or 0.5% move in favor
    4. Price target          — measured-move target_level from PatternSignal
    5. Time stop             — hard exit after pattern_hold_seconds

Entry filter:
    ATR must be below pattern_atr_entry_max_pct of price at the moment of entry.
    High ATR = noisy tape, pattern geometry unreliable → skip.

Partial profit (exit 7):
    When price reaches 50% of (entry → target), close 50% of the position and
    anchor a trailing stop at the breakout level, locking in a free trade on
    the remaining half.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import atexit
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import config_manager
from chart_pattern_detector import ChartPatternDetector, PatternSignal
from telegram_notifier import TelegramNotifier

LOGGER = logging.getLogger("pattern_trader")

# ── Constants ─────────────────────────────────────────────────────────────────
SLIPPAGE            = 0.001   # $/share simulated slippage (paper fills only)
POLL_INTERVAL       = 0.5     # seconds between live price polls for exit checks
TRAIL_TRIGGER_PCT   = 0.005   # 0.5 % in favor to activate trailing stop
TRAIL_OFFSET_PCT    = 0.003   # trailing stop trails 0.3 % behind best price seen
PARTIAL_PROFIT_AT   = 0.50    # trigger partial at 50 % of the way to target
PARTIAL_SIZE_FRAC   = 0.50    # close this fraction of position on partial
COOLDOWN_AFTER_EXIT = 300     # 5-min cooldown before re-entering same symbol after exit
DEFAULT_HOLD_SECS   = 1800    # 30-min time stop (overridden by pattern_hold_seconds)
MIN_BARS_REQUIRED   = 40      # minimum bars before pattern detection runs
MAX_BARS_STORED     = 400     # rolling window kept per symbol


# ── Position state ────────────────────────────────────────────────────────────

@dataclass
class PatternPosition:
    symbol: str
    direction: int          # +1 long, -1 short
    qty: int
    entry_price: float
    entry_time: float
    pattern: str
    target_level: float
    stop_level: float       # pattern-failure stop
    atr_stop: float         # ATR-based stop computed at entry (fixed level)
    breakout_level: float   # anchor price for trailing stop after partial
    hold_seconds: int       # time-stop threshold
    trailing_active: bool = False
    trailing_stop: float = 0.0
    partial_taken: bool = False
    best_price: float = 0.0  # best price seen since entry (for trailing)


# ── Trader ────────────────────────────────────────────────────────────────────

class PatternTrader:
    """Bar-driven pattern strategy.

    Call ``on_new_bar(symbol, bar)`` on every completed 1-minute bar.
    The trader manages its own OHLCV store, runs detection, and handles all exits.

    Args:
        mode: ``"live"`` — fires real Schwab market orders when executor is attached.
              ``"paper"`` — paper simulation only (no real orders).
              Controls which config size key is read and which DB tables are used.
    """

    DB_PATH = "penny_basing.db"

    def __init__(self, mode: str = "paper") -> None:
        self.mode = mode  # "live" or "paper"

        # Per-mode table and state file names
        if mode == "live":
            self._trade_table  = "pattern_trades"
            self._pos_table    = "pattern_positions"
            self._state_file   = "pattern_trader_state.json"
        else:
            self._trade_table  = "pattern_trades_paper"
            self._pos_table    = "pattern_positions_paper"
            self._state_file   = "pattern_trader_paper_state.json"

        self._lock = threading.Lock()
        self._bars: Dict[str, List[dict]] = {}
        self._positions: Dict[str, PatternPosition] = {}
        self._last_exit_time: Dict[str, float] = {}
        self._intraday_pnls: Dict[str, List[float]] = {}
        self._daily_pnl: float = 0.0
        self._daily_date: str = time.strftime("%Y-%m-%d")
        self._last_price: Dict[str, float] = {}   # latest price per symbol (from stream)
        self._executor: Optional[Any] = None       # SchwabOrderExecutor, if live
        self._stop_poll = threading.Event()
        self._detector = ChartPatternDetector()
        self._telegram = TelegramNotifier()
        self._init_db()
        self._load_state()
        self._start_poll_thread()
        atexit.register(self._shutdown)
        LOGGER.info("[PatternTrader:%s] Initialized (polling every %.1fs)", mode, POLL_INTERVAL)

    # ── DB setup ──────────────────────────────────────────────────────────────

    def _open_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        t = self._trade_table
        p = self._pos_table
        with closing(self._open_conn()) as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {t} (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   REAL,
                    symbol      TEXT,
                    side        TEXT,
                    qty         INTEGER,
                    price       REAL,
                    entry_price REAL,
                    pnl         REAL,
                    pattern     TEXT,
                    exit_reason TEXT
                )
            """)
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {p} (
                    symbol          TEXT PRIMARY KEY,
                    qty             INTEGER,
                    direction       INTEGER,
                    entry_price     REAL,
                    entry_time      REAL,
                    pattern         TEXT,
                    target_level    REAL,
                    stop_level      REAL,
                    atr_stop        REAL    DEFAULT 0.0,
                    breakout_level  REAL,
                    hold_seconds    INTEGER,
                    trailing_active INTEGER DEFAULT 0,
                    trailing_stop   REAL    DEFAULT 0.0,
                    partial_taken   INTEGER DEFAULT 0,
                    best_price      REAL    DEFAULT 0.0
                )
            """)
            # Migrate existing table if atr_stop column is missing
            try:
                conn.execute(f"ALTER TABLE {p} ADD COLUMN atr_stop REAL DEFAULT 0.0")
            except Exception:
                pass  # Column already exists
            conn.commit()

    # ── State persistence ──────────────────────────────────────────────────────

    def _load_state(self) -> None:
        try:
            p = Path(self._state_file)
            if p.exists():
                data = json.loads(p.read_text())
                self._daily_pnl  = float(data.get("daily_pnl", 0.0))
                self._daily_date = data.get("daily_date", time.strftime("%Y-%m-%d"))
                for sym, pnls in data.get("intraday_pnls", {}).items():
                    self._intraday_pnls[sym] = [float(v) for v in pnls]
        except Exception as exc:
            LOGGER.warning("[PatternTrader:%s] Failed to load state: %s", self.mode, exc)

    def _save_state(self) -> None:
        try:
            state = {
                "daily_pnl":    self._daily_pnl,
                "daily_date":   self._daily_date,
                "intraday_pnls": {k: v for k, v in self._intraday_pnls.items()},
            }
            Path(self._state_file).write_text(json.dumps(state, indent=2))
        except Exception as exc:
            LOGGER.warning("[PatternTrader:%s] Failed to save state: %s", self.mode, exc)

    def _reset_daily_if_needed(self) -> None:
        today = time.strftime("%Y-%m-%d")
        if today != self._daily_date:
            self._daily_pnl  = 0.0
            self._daily_date = today
            self._intraday_pnls.clear()

    def _shutdown(self) -> None:
        self._stop_poll.set()
        self._save_state()

    # ── Live executor (optional) ───────────────────────────────────────────────

    def set_executor(self, executor: Any) -> None:
        """Attach a SchwabOrderExecutor for live order placement.

        When set, stop exits fire real market orders instead of paper fills.
        Call this after PatternTrader.__init__ from grok.py once the primary
        LiveTrader's executor is available.
        """
        self._executor = executor
        order_mode = "DRY-RUN" if getattr(executor, "dry_run", True) else "LIVE"
        LOGGER.info("[PatternTrader:%s] Executor attached — mode=%s", self.mode, order_mode)

    def update_live_price(self, symbol: str, price: float) -> None:
        """Called by grok.py on every L1 tick to cache the latest stream price.

        This eliminates HTTP fetch_quote() calls in the poll thread — the stream
        price is always more current and has zero network latency.
        """
        if price > 0:
            self._last_price[symbol] = price

    # ── 0.5-second exit polling ────────────────────────────────────────────────

    def _start_poll_thread(self) -> None:
        t = threading.Thread(target=self._poll_loop, daemon=True, name="pattern-exit-poll")
        t.start()

    def _poll_loop(self) -> None:
        """Background thread: fetch live prices and run exit checks every 0.5 s."""
        while not self._stop_poll.is_set():
            try:
                with self._lock:
                    symbols = list(self._positions.keys())

                for symbol in symbols:
                    price = self._fetch_live_price(symbol)
                    if price and price > 0:
                        with self._lock:
                            if symbol in self._positions:
                                # Update best price tracking
                                pos = self._positions[symbol]
                                if pos.direction == +1:
                                    pos.best_price = max(pos.best_price, price)
                                else:
                                    pos.best_price = min(pos.best_price, price) \
                                                     if pos.best_price > 0 else price
                                self._check_exits(symbol, price)
            except Exception as exc:
                LOGGER.debug("[PatternTrader] poll error: %s", exc)
            self._stop_poll.wait(POLL_INTERVAL)

    def _fetch_live_price(self, symbol: str) -> Optional[float]:
        """Return the latest price for *symbol*.

        Prefers the stream-cached price (set by update_live_price on every L1 tick)
        which has zero network latency. Falls back to HTTP fetch_quote() only on
        cold start before any stream data has arrived.
        """
        # Stream cache is always fresher and has zero latency — use it first
        cached = self._last_price.get(symbol)
        if cached and cached > 0:
            return cached
        # Cold-start fallback: no stream data yet, try HTTP
        if self._executor is not None:
            try:
                quote = self._executor.fetch_quote(symbol)
                if isinstance(quote, dict):
                    price = (
                        quote.get("lastPrice")
                        or quote.get("mark")
                        or quote.get("last")
                    )
                    if price:
                        val = float(price)
                        self._last_price[symbol] = val
                        return val
            except Exception as exc:
                LOGGER.debug("[PatternTrader:%s] fetch_quote error %s: %s", self.mode, symbol, exc)
        return None

    # ── Main entry point ───────────────────────────────────────────────────────

    def on_new_bar(self, symbol: str, bar: dict) -> None:
        """Called by grok.py each time a completed 1-minute bar is available."""
        cfg = config_manager.load_config()
        pattern_syms = [
            s.strip().upper()
            for s in cfg.get("pattern_symbols", "").split(",")
            if s.strip()
        ]
        if pattern_syms and symbol not in pattern_syms:
            return

        with self._lock:
            self._reset_daily_if_needed()
            self._append_bar(symbol, bar)
            close = float(bar.get("close", 0.0))
            if close <= 0:
                return

            self._last_price[symbol] = close  # keep last known price for poll thread

            df = self._get_df(symbol)
            if df is None or len(df) < MIN_BARS_REQUIRED:
                return

            # Check exits first, then entries
            if symbol in self._positions:
                self._check_exits(symbol, close, df)

            if symbol not in self._positions:
                self._check_entries(symbol, close, df)

    # ── Bar store ─────────────────────────────────────────────────────────────

    def _append_bar(self, symbol: str, bar: dict) -> None:
        bucket = self._bars.setdefault(symbol, [])
        bucket.append(bar)
        if len(bucket) > MAX_BARS_STORED:
            self._bars[symbol] = bucket[-MAX_BARS_STORED:]

    def _get_df(self, symbol: str) -> Optional[pd.DataFrame]:
        bars = self._bars.get(symbol)
        if not bars:
            return None
        df = pd.DataFrame(bars)
        df.columns = [c.lower() for c in df.columns]
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                df[col] = 0.0
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    # ── ATR helper ────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_atr(df: pd.DataFrame, period: int = 14) -> float:
        """Return the most recent ATR value from the df (standard Wilder/rolling mean)."""
        if len(df) < period + 1:
            return 0.0
        high  = df["high"]
        low   = df["low"]
        close = df["close"]
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low  - prev_close).abs(),
        ], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])

    # ── Entry logic ───────────────────────────────────────────────────────────

    def _check_entries(self, symbol: str, close: float, df: pd.DataFrame) -> None:
        # Respect cooldown after last exit
        if time.time() - self._last_exit_time.get(symbol, 0.0) < COOLDOWN_AFTER_EXIT:
            return

        cfg                  = config_manager.load_config()
        min_conf             = float(cfg.get("pattern_min_confidence", 0.60))
        max_hold_secs        = int(cfg.get("pattern_hold_seconds", DEFAULT_HOLD_SECS))
        size_key             = f"pattern_{self.mode}_position_size"
        base_qty             = int(cfg.get(size_key, cfg.get("pattern_position_size", 100)))
        atr_period           = int(cfg.get("pattern_atr_period", 14))
        atr_entry_max_pct    = float(cfg.get("pattern_atr_entry_max_pct", 0.005))
        atr_stop_multiplier  = float(cfg.get("pattern_atr_stop_multiplier", 1.5))

        # ── ATR entry filter ─────────────────────────────────────────────────
        atr = self._compute_atr(df, atr_period)
        if atr <= 0:
            return  # Can't assess volatility yet
        if close > 0 and (atr / close) > atr_entry_max_pct:
            LOGGER.debug(
                "[PatternTrader] %s ATR filter: atr=%.4f is %.3f%% of price (max %.3f%%) — skipping",
                symbol, atr, atr / close * 100, atr_entry_max_pct * 100,
            )
            return

        try:
            signals = self._detector.latest(df)
        except Exception as exc:
            LOGGER.debug("[PatternTrader] detect error %s: %s", symbol, exc)
            return

        candidates = [
            s for s in signals
            if s.breakout
            and s.confidence >= min_conf
            and s.direction in ("bullish", "bearish")
            and s.target_level is not None
            and s.stop_level is not None
            and s.price_level is not None
        ]
        if not candidates:
            return

        sig       = max(candidates, key=lambda s: s.confidence)
        direction = +1 if sig.direction == "bullish" else -1
        atr_stop  = close - direction * atr_stop_multiplier * atr  # fixed at entry
        qty       = max(1, int(base_qty * self._kelly_size_multiplier(symbol)))

        # Derive hold time from pattern width: a breakout should resolve in roughly
        # the same time the pattern took to form. Clamped to [5 min, max_hold_secs].
        pattern_bars = max(1, sig.end_idx - sig.start_idx)
        hold_secs    = max(300, min(pattern_bars * 60, max_hold_secs))
        LOGGER.info(
            "[PatternTrader:%s] %s pattern_bars=%d → hold=%ds (cap=%ds)",
            self.mode, symbol, pattern_bars, hold_secs, max_hold_secs,
        )
        self._enter(symbol, sig, close, direction, qty, hold_secs, atr_stop)

    def _enter(
        self,
        symbol: str,
        sig: PatternSignal,
        price: float,
        direction: int,
        qty: int,
        hold_seconds: int,
        atr_stop: float = 0.0,
    ) -> None:
        fill = price + SLIPPAGE * direction
        side = "BUY" if direction == +1 else "SHORT"

        pos = PatternPosition(
            symbol=symbol,
            direction=direction,
            qty=qty,
            entry_price=fill,
            entry_time=time.time(),
            pattern=sig.pattern,
            target_level=float(sig.target_level),
            stop_level=float(sig.stop_level),
            atr_stop=float(atr_stop),
            breakout_level=float(sig.price_level),
            hold_seconds=hold_seconds,
            best_price=fill,
        )
        self._positions[symbol] = pos
        self._write_trade(symbol, side, qty, fill, fill, 0.0, sig.pattern, "entry")
        self._persist_position(pos)
        LOGGER.info(
            "[PatternTrader] ENTER %s %s %d @ $%.4f  pattern=%s  target=$%.4f  "
            "failure_stop=$%.4f  atr_stop=$%.4f",
            side, symbol, qty, fill, sig.pattern, sig.target_level,
            sig.stop_level, atr_stop,
        )

    # ── Exit logic ────────────────────────────────────────────────────────────

    def _check_exits(self, symbol: str, close: float, df: Optional[pd.DataFrame] = None) -> None:
        pos = self._positions.get(symbol)
        if not pos:
            return

        d = pos.direction  # +1 long, -1 short

        # Track best price for trailing stop
        if d == +1:
            pos.best_price = max(pos.best_price, close)
        else:
            pos.best_price = min(pos.best_price, close) if pos.best_price > 0 else close

        # ── 1. Pattern failure stop ───────────────────────────────────────────
        failure = (d == +1 and close <= pos.stop_level) or \
                  (d == -1 and close >= pos.stop_level)
        if failure:
            self._exit(symbol, close, "failure_stop", pos.qty)
            return

        # ── 2. ATR stop (fixed level computed at entry) ───────────────────────
        if pos.atr_stop > 0:
            atr_hit = (d == +1 and close <= pos.atr_stop) or \
                      (d == -1 and close >= pos.atr_stop)
            if atr_hit:
                self._exit(symbol, close, "atr_stop", pos.qty)
                return

        # ── 3. Trailing stop (if active) ─────────────────────────────────────
        if pos.trailing_active and pos.trailing_stop > 0:
            hit_trail = (d == +1 and close <= pos.trailing_stop) or \
                        (d == -1 and close >= pos.trailing_stop)
            if hit_trail:
                self._exit(symbol, close, "trailing_stop", pos.qty)
                return
            # Ratchet the stop tighter as price improves
            if d == +1:
                new_trail = pos.best_price * (1.0 - TRAIL_OFFSET_PCT)
                pos.trailing_stop = max(pos.trailing_stop, new_trail)
            else:
                new_trail = pos.best_price * (1.0 + TRAIL_OFFSET_PCT)
                pos.trailing_stop = min(pos.trailing_stop, new_trail) \
                                    if pos.trailing_stop > 0 else new_trail

        # ── 7. Partial profit at 50 % of target ──────────────────────────────
        if not pos.partial_taken:
            midpoint = pos.entry_price + \
                       (pos.target_level - pos.entry_price) * PARTIAL_PROFIT_AT
            hit_mid = (d == +1 and close >= midpoint) or \
                      (d == -1 and close <= midpoint)
            if hit_mid:
                partial_qty = max(1, int(pos.qty * PARTIAL_SIZE_FRAC))
                self._exit(symbol, close, "partial_profit", partial_qty)
                # Check if the partial closed the whole position (qty was 1)
                if symbol not in self._positions:
                    return
                pos = self._positions[symbol]
                pos.partial_taken   = True
                pos.trailing_active = True
                # Anchor trailing stop at breakout level — locked-in free trade
                pos.trailing_stop   = pos.breakout_level
                self._persist_position(pos)
                LOGGER.info(
                    "[PatternTrader] PARTIAL %s: trailing stop anchored at $%.4f",
                    symbol, pos.trailing_stop,
                )

        # ── 3. Full price target ──────────────────────────────────────────────
        hit_target = (d == +1 and close >= pos.target_level) or \
                     (d == -1 and close <= pos.target_level)
        if hit_target:
            self._exit(symbol, close, "target", pos.qty)
            return

        # Activate trailing stop once price moves TRAIL_TRIGGER_PCT in favor
        # (even without a partial, we want to protect a meaningful unrealised gain)
        if not pos.trailing_active:
            move_pct = (close - pos.entry_price) / pos.entry_price * d
            if move_pct >= TRAIL_TRIGGER_PCT:
                pos.trailing_active = True
                pos.trailing_stop   = pos.breakout_level
                self._persist_position(pos)

        # ── 4. Time stop ──────────────────────────────────────────────────────
        if time.time() - pos.entry_time >= pos.hold_seconds:
            self._exit(symbol, close, "time_stop", pos.qty)

    def _exit(self, symbol: str, price: float, reason: str, qty: int) -> None:
        pos = self._positions.get(symbol)
        if not pos:
            return

        d    = pos.direction
        side = "SELL" if d == +1 else "COVER"

        # Live mode: fire real market order; use submitted price or fall back to quote
        if self._executor is not None and not getattr(self._executor, "dry_run", True):
            try:
                self._executor.submit_market(symbol=symbol, qty=qty, side=side)
                LOGGER.info(
                    "[PatternTrader] LIVE ORDER %s %s %d  reason=%s", side, symbol, qty, reason
                )
                # Price already known from poll; use it as fill estimate
                fill = price - SLIPPAGE * d
            except Exception as exc:
                LOGGER.error("[PatternTrader] submit_market error %s: %s", symbol, exc)
                fill = price - SLIPPAGE * d
        else:
            fill = price - SLIPPAGE * d

        pnl  = (fill - pos.entry_price) * d * qty

        self._daily_pnl += pnl
        self._intraday_pnls.setdefault(symbol, []).append(pnl)

        self._write_trade(symbol, side, qty, fill, pos.entry_price, pnl, pos.pattern, reason)

        remaining = pos.qty - qty
        if remaining > 0:
            pos.qty = remaining
            self._persist_position(pos)
            LOGGER.info(
                "[PatternTrader] PARTIAL EXIT %s %s %d @ $%.4f  pnl=$%.2f  reason=%s  remaining=%d",
                side, symbol, qty, fill, pnl, reason, remaining,
            )
        else:
            del self._positions[symbol]
            self._last_exit_time[symbol] = time.time()
            self._remove_db_position(symbol)
            self._save_state()
            LOGGER.info(
                "[PatternTrader] EXIT %s %s %d @ $%.4f  pnl=$%.2f  reason=%s  daily=$%.2f",
                side, symbol, qty, fill, pnl, reason, self._daily_pnl,
            )
            # Telegram notification on full close (live mode only — paper is too noisy)
            if self.mode == "live":
                try:
                    direction_label = "LONG" if d == +1 else "SHORT"
                    pnl_sign = "+" if pnl >= 0 else ""
                    msg = (
                        f"{'✅' if pnl >= 0 else '🔴'} *Pattern Trade Closed*\n"
                        f"Symbol: `{symbol}` ({direction_label})\n"
                        f"Pattern: `{pos.pattern}`\n"
                        f"Entry: `${pos.entry_price:.4f}` → Exit: `${fill:.4f}`\n"
                        f"Qty: `{qty}` | PnL: `{pnl_sign}${pnl:.2f}`\n"
                        f"Reason: `{reason}`\n"
                        f"Daily PnL: `{'+' if self._daily_pnl >= 0 else ''}${self._daily_pnl:.2f}`\n"
                        f"Cooldown: 5 min on `{symbol}`"
                    )
                    threading.Thread(
                        target=self._telegram.send_message,
                        args=(msg,),
                        daemon=True,
                    ).start()
                except Exception as _tg_err:
                    LOGGER.debug("[PatternTrader] Telegram notify error: %s", _tg_err)

    # ── Kelly without PI ──────────────────────────────────────────────────────

    def _kelly_size_multiplier(self, symbol: str) -> float:
        try:
            cfg = config_manager.load_config()
            if not cfg.get("pattern_kelly_enabled", True):
                return 1.0

            kelly_fraction = float(cfg.get("pattern_kelly_fraction", 0.5))
            max_mult       = float(cfg.get("pattern_kelly_max_multiplier", 2.0))
            min_mult       = float(cfg.get("pattern_kelly_min_multiplier", 0.25))
            lookback_days  = int(cfg.get("pattern_kelly_lookback_days", 30))

            pnls   = list(self._intraday_pnls.get(symbol, []))
            wins   = [p for p in pnls if p > 0]
            losses = [abs(p) for p in pnls if p < 0]

            if not pnls:
                kelly_mult = 1.0
            elif wins and losses:
                W          = len(wins) / len(pnls)
                R          = (sum(wins) / len(wins)) / (sum(losses) / len(losses))
                full_kelly = (W * R - (1.0 - W)) / R
                kelly_mult = 1.0 + full_kelly * kelly_fraction
            else:
                W, R = self._db_kelly_params(symbol, lookback_days)
                if W is not None:
                    full_kelly = (W * R - (1.0 - W)) / R
                    kelly_mult = 1.0 + full_kelly * kelly_fraction
                else:
                    kelly_mult = 1.0

            multiplier = max(min_mult, min(kelly_mult, max_mult))
            LOGGER.info(
                "[PatternTrader] [KELLY] %s: kelly=%.3f → mult=%.3f",
                symbol, kelly_mult, multiplier,
            )
            return multiplier
        except Exception:
            return 1.0

    def _db_kelly_params(
        self, symbol: str, lookback_days: int
    ) -> Tuple[Optional[float], Optional[float]]:
        cutoff = time.time() - lookback_days * 86_400
        t = self._trade_table
        try:
            with closing(self._open_conn()) as conn:
                rows = conn.execute(
                    f"SELECT pnl FROM {t} "
                    "WHERE symbol=? AND side IN ('SELL','COVER') "
                    "AND timestamp>=? AND pnl IS NOT NULL",
                    (symbol, cutoff),
                ).fetchall()
                pnls = [float(r[0]) for r in rows if r[0] not in (None, 0.0)]
                if not pnls:
                    rows = conn.execute(
                        f"SELECT pnl FROM {t} "
                        "WHERE side IN ('SELL','COVER') AND timestamp>=? AND pnl IS NOT NULL",
                        (cutoff,),
                    ).fetchall()
                    pnls = [float(r[0]) for r in rows if r[0] not in (None, 0.0)]
        except Exception:
            return None, None

        wins   = [p      for p in pnls if p > 0]
        losses = [abs(p) for p in pnls if p < 0]
        if not wins or not losses:
            return None, None

        W = len(wins) / len(pnls)
        R = (sum(wins) / len(wins)) / (sum(losses) / len(losses))
        return W, R

    # ── DB helpers ────────────────────────────────────────────────────────────

    def _write_trade(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        entry_price: float,
        pnl: float,
        pattern: str,
        exit_reason: str,
    ) -> None:
        try:
            with closing(self._open_conn()) as conn:
                conn.execute(
                    f"INSERT INTO {self._trade_table} "
                    "(timestamp,symbol,side,qty,price,entry_price,pnl,pattern,exit_reason) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (time.time(), symbol, side, qty, price,
                     entry_price, pnl, pattern, exit_reason),
                )
                conn.commit()
        except Exception as exc:
            LOGGER.error("[PatternTrader:%s] DB write error: %s", self.mode, exc)

    def _persist_position(self, pos: PatternPosition) -> None:
        try:
            with closing(self._open_conn()) as conn:
                conn.execute(
                    f"""INSERT INTO {self._pos_table}
                       (symbol, qty, direction, entry_price, entry_time, pattern,
                        target_level, stop_level, atr_stop, breakout_level, hold_seconds,
                        trailing_active, trailing_stop, partial_taken, best_price)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(symbol) DO UPDATE SET
                         qty=excluded.qty,
                         direction=excluded.direction,
                         entry_price=excluded.entry_price,
                         entry_time=excluded.entry_time,
                         pattern=excluded.pattern,
                         target_level=excluded.target_level,
                         stop_level=excluded.stop_level,
                         atr_stop=excluded.atr_stop,
                         breakout_level=excluded.breakout_level,
                         hold_seconds=excluded.hold_seconds,
                         trailing_active=excluded.trailing_active,
                         trailing_stop=excluded.trailing_stop,
                         partial_taken=excluded.partial_taken,
                         best_price=excluded.best_price""",
                    (
                        pos.symbol, pos.qty, pos.direction,
                        pos.entry_price, pos.entry_time, pos.pattern,
                        pos.target_level, pos.stop_level, pos.atr_stop,
                        pos.breakout_level, pos.hold_seconds,
                        int(pos.trailing_active), pos.trailing_stop,
                        int(pos.partial_taken), pos.best_price,
                    ),
                )
                conn.commit()
        except Exception as exc:
            LOGGER.error("[PatternTrader] Position persist error: %s", exc)

    def _remove_db_position(self, symbol: str) -> None:
        try:
            with closing(self._open_conn()) as conn:
                conn.execute(f"DELETE FROM {self._pos_table} WHERE symbol=?", (symbol,))
                conn.commit()
        except Exception as exc:
            LOGGER.error("[PatternTrader:%s] Position remove error: %s", self.mode, exc)
