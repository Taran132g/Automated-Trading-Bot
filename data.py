from __future__ import annotations

"""
Glue code to integrate chart_pattern_detector.py into an existing L2 / alert-driven bot.

This file is intentionally modular so you can copy only the parts you need.
It assumes you already have:

1. A live microstructure signal engine that produces alerts like bid-heavy / ask-heavy.
2. A way to build or receive OHLCV bars per symbol.
3. A trader / executor that consumes enriched alerts.

Expected companion module:
    from chart_pattern_detector import PatternEngine, ChartPatternDetector, merge_pattern_bias

Main idea:
    - Maintain rolling OHLCV bars per symbol.
    - Cache the latest chart-pattern results per symbol.
    - When an L2 alert fires, enrich it with chart context.
    - Let execution use the enriched alert for sizing / timing / filtering.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import threading
import time
from datetime import datetime

import pandas as pd

from chart_pattern_detector import PatternEngine, ChartPatternDetector, PatternSignal, merge_pattern_bias


# ============================================================================
# Config
# ============================================================================

@dataclass
class PatternIntegrationConfig:
    timeframe: str = "1min"
    max_bars_per_symbol: int = 400
    min_confidence: float = 0.40
    require_breakout: bool = False

    # Execution shaping
    breakout_size_factor: float = 1.50   # aligned + breakout confirmed
    aligned_size_factor: float = 1.25    # aligned, no breakout yet
    neutral_size_factor: float = 1.00
    countertrend_size_factor: float = 0.75

    aligned_hold_seconds: int = 600
    neutral_hold_seconds: int = 420
    countertrend_hold_seconds: int = 180

    # Optional hard filters
    block_strong_countertrend_entries: bool = False
    strong_countertrend_threshold: float = 1.50

    # Optional confidence gating
    min_pattern_count_for_bias: int = 1

    # Backtest signal lookback window (how many bars back a pattern can end and still count)
    backtest_signal_lookback: int = 120


# ============================================================================
# Rolling OHLCV store
# ============================================================================

class OHLCVStore:
    """
    Thread-safe rolling OHLCV cache keyed by symbol.

    Each symbol stores a DataFrame with columns:
        open, high, low, close, volume
    """
    def __init__(self, max_bars_per_symbol: int = 400):
        self.max_bars_per_symbol = max_bars_per_symbol
        self._frames: Dict[str, pd.DataFrame] = {}
        self._lock = threading.Lock()

    def set_frame(self, symbol: str, df: pd.DataFrame) -> None:
        cleaned = self._normalize_df(df).tail(self.max_bars_per_symbol).reset_index(drop=True)
        with self._lock:
            self._frames[symbol] = cleaned

    def append_bar(self, symbol: str, bar: Dict[str, Any]) -> None:
        new_row = pd.DataFrame([bar])
        new_row = self._normalize_df(new_row)

        with self._lock:
            existing = self._frames.get(symbol)
            if existing is None or existing.empty:
                self._frames[symbol] = new_row.tail(self.max_bars_per_symbol).reset_index(drop=True)
                return

            combined = pd.concat([existing, new_row], ignore_index=True)
            combined = combined.tail(self.max_bars_per_symbol).reset_index(drop=True)
            self._frames[symbol] = combined

    def get_frame(self, symbol: str) -> Optional[pd.DataFrame]:
        with self._lock:
            df = self._frames.get(symbol)
            if df is None:
                return None
            return df.copy()

    @staticmethod
    def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out.columns = [c.lower() for c in out.columns]
        required = ["open", "high", "low", "close"] # timestamp is optional but allowed
        missing = [c for c in required if c not in out.columns]
        if missing:
            raise ValueError(f"OHLCVStore missing required columns: {missing}")
        if "volume" not in out.columns:
            out["volume"] = 0.0

        for c in ["open", "high", "low", "close", "volume"]:
            out[c] = pd.to_numeric(out[c], errors="coerce")

        out = out.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
        cols = ["open", "high", "low", "close", "volume"]
        if "timestamp" in out.columns:
            cols.append("timestamp")
            
        return out[cols]


# ============================================================================
# Pattern cache and enricher
# ============================================================================

@dataclass
class SymbolPatternState:
    symbol: str
    timeframe: str
    updated_at: float
    raw_signals: List[Dict[str, Any]] = field(default_factory=list)
    chart_bias: str = "neutral"
    bullish_score: float = 0.0
    bearish_score: float = 0.0
    pattern_count: int = 0
    top_patterns: List[Dict[str, Any]] = field(default_factory=list)

class PatternContextManager:
    def __init__(self, cfg: Optional[PatternIntegrationConfig] = None, is_backtest: bool = False):
        self.cfg = cfg or PatternIntegrationConfig()
        self.is_backtest = is_backtest
        self.engine = PatternEngine()
        self.detector = ChartPatternDetector()
        self._cache: Dict[str, SymbolPatternState] = {}
        self._last_df_ts: Dict[str, float] = {} # For caching detection
        self._lock = threading.Lock()
    def update_symbol(self, symbol: str, df: pd.DataFrame, is_backtest: bool = False) -> SymbolPatternState:
        # Optimization: skip if we've already handled this DF state
        last_ts = float(df.iloc[-1]["timestamp"]) if "timestamp" in df.columns else float(len(df))
        with self._lock:
            if self._last_df_ts.get(symbol) == last_ts and symbol in self._cache:
                return self._cache[symbol]
            self._last_df_ts[symbol] = last_ts

        if is_backtest:
            all_signals = self.detector.detect(df)
            last_idx = len(df) - 1
            signals = [s for s in all_signals if s.end_idx >= last_idx - self.cfg.backtest_signal_lookback]
        else:
            signals = self.detector.latest(df)
            
        filtered = [
            s for s in signals
            if s.confidence >= self.cfg.min_confidence and (s.breakout or not self.cfg.require_breakout)
        ]
        

        bullish_score = sum(s.confidence for s in filtered if s.direction == "bullish")
        bearish_score = sum(s.confidence for s in filtered if s.direction == "bearish")

        chart_bias = "neutral"
        if len(filtered) >= self.cfg.min_pattern_count_for_bias:
            if bullish_score > bearish_score:
                chart_bias = "bullish"
            elif bearish_score > bullish_score:
                chart_bias = "bearish"
 
        # if is_backtest and filtered:
        #     p_info = [f"{s.pattern}({s.direction}:{s.confidence:.2f})" for s in filtered]
        #     ts = df.iloc[len(df)-1]['timestamp']
        #     ts_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        #     print(f"[DEBUG] {symbol} @ {ts_str} (idx {len(df)-1}): {p_info} | Bull={bullish_score:.2f} Bear={bearish_score:.2f} Bias={chart_bias}")

        state = SymbolPatternState(
            symbol=symbol,
            timeframe=self.cfg.timeframe,
            updated_at=time.time(),
            raw_signals=[s.to_dict() for s in signals],
            chart_bias=chart_bias,
            bullish_score=bullish_score,
            bearish_score=bearish_score,
            pattern_count=len(filtered),
            top_patterns=[s.to_dict() for s in sorted(filtered, key=lambda x: x.confidence, reverse=True)[:5]],
        )

        with self._lock:
            self._cache[symbol] = state
        return state

    def get_symbol_state(self, symbol: str) -> Optional[SymbolPatternState]:
        with self._lock:
            state = self._cache.get(symbol)
            return state

    def enrich_alert(self, alert: Dict[str, Any], df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """
        Enrich an existing L2 alert using cached pattern state.
        If df is provided, refresh the pattern state before enrichment.
        """
        symbol = str(alert["symbol"])
        direction = str(alert.get("direction") or alert.get("imbalance") or "").strip()

        state = self.update_symbol(symbol, df, is_backtest=self.is_backtest) if df is not None else self.get_symbol_state(symbol)
        
        # DEBUG TRACE
        # if self.is_backtest:
        #     print(f"[TRACE] enrich_alert {symbol} @ {alert.get('timestamp')} -> df={len(df) if df is not None else 'None'} bias={state.chart_bias if state else 'None'}")
            
        enriched = dict(alert)

        if state is None:
            enriched.update(
                {
                    "chart_bias": "neutral",
                    "pattern_alignment": False,
                    "bullish_score": 0.0,
                    "bearish_score": 0.0,
                    "pattern_count": 0,
                    "top_patterns": [],
                    "size_factor": self.cfg.neutral_size_factor,
                    "recommended_hold_seconds": self.cfg.neutral_hold_seconds,
                    "block_entry": False,
                }
            )
            return enriched

        synthetic_signals = [
            _dict_to_pattern_signal(p) for p in state.top_patterns
        ]
        combined = merge_pattern_bias(direction, synthetic_signals, min_confidence=self.cfg.min_confidence)

        size_factor = self.cfg.neutral_size_factor
        hold_seconds = self.cfg.neutral_hold_seconds
        block_entry = False

        if combined["alignment"]:
            # Breakout confirmed → 1.5x. Pattern aligned but no breakout yet → 1.25x.
            broken_out = [p for p in state.top_patterns if p.get("breakout_idx") is not None]
            if broken_out:
                size_factor = self.cfg.breakout_size_factor  # 1.5x — reversal confirmed + L2 agrees
            else:
                size_factor = self.cfg.aligned_size_factor   # 1.25x — aligned but no breakout yet
            hold_seconds = self.cfg.aligned_hold_seconds
        elif state.chart_bias == "neutral":
            size_factor = self.cfg.neutral_size_factor
            hold_seconds = self.cfg.neutral_hold_seconds
        else:
            size_factor = self.cfg.countertrend_size_factor
            hold_seconds = self.cfg.countertrend_hold_seconds
            strength = max(state.bullish_score, state.bearish_score)
            if self.cfg.block_strong_countertrend_entries and strength >= self.cfg.strong_countertrend_threshold:
                block_entry = True

        enriched.update(
            {
                "chart_bias": state.chart_bias,
                "pattern_alignment": combined["alignment"],
                "bullish_score": state.bullish_score,
                "bearish_score": state.bearish_score,
                "pattern_count": state.pattern_count,
                "top_patterns": state.top_patterns,
                "size_factor": size_factor,
                "recommended_hold_seconds": hold_seconds,
                "block_entry": block_entry,
                "pattern_timeframe": state.timeframe,
                "pattern_updated_at": state.updated_at,
            }
        )
        return enriched


# ============================================================================
# Helpers
# ============================================================================


def _dict_to_pattern_signal(d: Dict[str, Any]) -> PatternSignal:
    return PatternSignal(
        pattern=d["pattern"],
        direction=d["direction"],
        confidence=float(d["confidence"]),
        breakout=bool(d["breakout"]),
        score=float(d["score"]),
        start_idx=int(d["start_idx"]),
        end_idx=int(d["end_idx"]),
        breakout_idx=d.get("breakout_idx"),
        price_level=d.get("price_level"),
        stop_level=d.get("stop_level"),
        target_level=d.get("target_level"),
        meta=d.get("meta", {}),
    )


def shape_execution_params(enriched_alert: Dict[str, Any], base_qty: int) -> Dict[str, Any]:
    """
    Translate chart context into simple execution parameters.
    Keep this adapter thin so it can plug into your live trader.
    """
    size_factor = float(enriched_alert.get("size_factor", 1.0))
    recommended_hold_seconds = int(enriched_alert.get("recommended_hold_seconds", 600))
    block_entry = bool(enriched_alert.get("block_entry", False))

    shaped_qty = max(1, int(round(base_qty * size_factor)))
    return {
        "qty": shaped_qty,
        "max_hold_seconds": recommended_hold_seconds,
        "block_entry": block_entry,
    }


# ============================================================================
# Example integration into a live alert pipeline
# ============================================================================

class IntegratedSignalPipeline:
    """
    Example orchestrator.

    Replace these methods with your actual code:
        - on_new_bar()
        - on_l2_alert()
        - dispatch_to_trader()

    This class shows the exact integration pattern.
    """
    def __init__(self, cfg: Optional[PatternIntegrationConfig] = None, is_backtest: bool = False):
        self.cfg = cfg or PatternIntegrationConfig()
        self.is_backtest = is_backtest
        self.ohlcv_store = OHLCVStore(max_bars_per_symbol=self.cfg.max_bars_per_symbol)
        self.patterns = PatternContextManager(self.cfg, is_backtest=self.is_backtest)

    # ----------------------------------------------------------------------
    # Called whenever a new OHLCV bar is available for a symbol.
    # Best practice: call this on each 1-minute bar close.
    # ----------------------------------------------------------------------
    def on_new_bar(self, symbol: str, bar: Dict[str, Any]) -> None:
        self.ohlcv_store.append_bar(symbol, bar)
        if not self.is_backtest:
            df = self.ohlcv_store.get_frame(symbol)
            if df is not None and len(df) >= 40:
                self.patterns.update_symbol(symbol, df, is_backtest=False)

    # ----------------------------------------------------------------------
    # Seeding historical data (e.g., on startup)
    # ----------------------------------------------------------------------
    def seed_historical_data(self, symbol: str, df: pd.DataFrame) -> None:
        """
        Seed the pipeline with historical OHLCV data to build immediate context.
        """
        if df.empty:
            return
            
        self.ohlcv_store.set_frame(symbol, df)
        # Force a pattern analysis update immediately
        df_for_analysis = self.ohlcv_store.get_frame(symbol)
        if df_for_analysis is not None and len(df_for_analysis) >= 40:
            self.patterns.update_symbol(symbol, df_for_analysis)

    # ----------------------------------------------------------------------
    # Called whenever your existing L2 engine emits a trading alert.
    # ----------------------------------------------------------------------
    def on_l2_alert(self, alert: Dict[str, Any], base_qty: int = 100) -> Optional[Dict[str, Any]]:
        symbol = str(alert["symbol"])
        df = self.ohlcv_store.get_frame(symbol)

        # If a fresh frame exists, enrich from it. Otherwise use cached context.
        enriched = self.patterns.enrich_alert(alert, df=df)
        execution = shape_execution_params(enriched, base_qty=base_qty)
        enriched["execution"] = execution

        # Never block entries per user instruction, always allow but with sized qty
        enriched["decision"] = "enter_or_manage"
        
        if not self.is_backtest:
            self.dispatch_to_trader(enriched)
        return enriched

    # ----------------------------------------------------------------------
    # Replace this with your real trader hook.
    # ----------------------------------------------------------------------
    def dispatch_to_trader(self, enriched_alert: Dict[str, Any]) -> None:
        print("[dispatch_to_trader]", enriched_alert)


# ============================================================================
# Drop-in example for an existing live_trader-style interface
# ============================================================================

class TraderAdapter:
    """
    Example adapter showing how a trader could consume enriched alerts.
    """
    def handle_enriched_alert(self, enriched_alert: Dict[str, Any]) -> Dict[str, Any]:
        execution = enriched_alert["execution"]
        direction = enriched_alert.get("direction")
        chart_bias = enriched_alert.get("chart_bias")
        top_patterns = enriched_alert.get("top_patterns", [])

        return {
            "action": enriched_alert.get("decision", "hold"),
            "symbol": enriched_alert["symbol"],
            "direction": direction,
            "qty": execution["qty"],
            "max_hold_seconds": execution["max_hold_seconds"],
            "chart_bias": chart_bias,
            "top_patterns": [p.get("pattern") for p in top_patterns[:3]],
        }


# ============================================================================
# Example of direct usage with an existing on_book() function
# ============================================================================

# Global singletons you can create during startup
PATTERN_CFG = PatternIntegrationConfig(
    timeframe="1min",
    max_bars_per_symbol=400,
    min_confidence=0.60,
    require_breakout=False,
    aligned_size_factor=1.00,
    neutral_size_factor=0.75,
    countertrend_size_factor=0.40,
    aligned_hold_seconds=600,
    neutral_hold_seconds=420,
    countertrend_hold_seconds=180,
    block_strong_countertrend_entries=False,
)

PIPELINE = IntegratedSignalPipeline(PATTERN_CFG)
TRADER = TraderAdapter()


def example_existing_bar_handler(symbol: str, bar: Dict[str, Any]) -> None:
    """
    Call this from your real bar aggregator when a new 1-minute bar closes.
    """
    PIPELINE.on_new_bar(symbol, bar)


def example_existing_on_book_generated_alert(alert: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Call this right after your existing L2 engine creates an alert.

    Expected incoming alert example:
        {
            "symbol": "AAPL",
            "direction": "bid-heavy",
            "price": 213.48,
            "vol_per_min": 185000,
            "timestamp": 1712345678.0,
        }
    """
    enriched = PIPELINE.on_l2_alert(alert, base_qty=100)
    if enriched is None:
        return None

    trader_view = TRADER.handle_enriched_alert(enriched)
    print("[trader_view]", trader_view)
    return enriched


# ============================================================================
# If your bot already has an alert object schema, use this mapper.
# ============================================================================

def enrich_existing_alert_schema(
    symbol: str,
    direction: str,
    price: float,
    vol_per_min: float,
    timestamp: float,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base_alert = {
        "symbol": symbol,
        "direction": direction,
        "price": price,
        "vol_per_min": vol_per_min,
        "timestamp": timestamp,
    }
    if extra:
        base_alert.update(extra)
    return PIPELINE.on_l2_alert(base_alert, base_qty=100) or base_alert


if __name__ == "__main__":
    # ------------------------------------------------------------
    # Tiny demo showing the integration flow.
    # ------------------------------------------------------------
    demo_bars = [
        {"open": 100.0, "high": 100.5, "low": 99.8, "close": 100.3, "volume": 12000},
        {"open": 100.3, "high": 100.8, "low": 100.1, "close": 100.6, "volume": 14000},
        {"open": 100.6, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 16000},
    ]

    # Pad the store with synthetic bars so the detector has enough history.
    seed = []
    px = 95.0
    for _ in range(60):
        seed.append({"open": px, "high": px + 0.6, "low": px - 0.4, "close": px + 0.2, "volume": 10000})
        px += 0.12

    for bar in seed + demo_bars:
        example_existing_bar_handler("TEST", bar)

    alert = {
        "symbol": "TEST",
        "direction": "bid-heavy",
        "price": 101.0,
        "vol_per_min": 180000,
        "timestamp": time.time(),
    }
    example_existing_on_book_generated_alert(alert)
