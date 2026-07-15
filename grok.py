"""
Beginner-friendly overview
-------------------------
This file is the "brain" of the alerting pipeline. It does four things:
1) Reads config from the environment/CLI so you can tune symbols and thresholds.
2) Streams live market data from Schwab, cleaning it up into simple Python
   dicts.
3) Decides when an imbalance is "ask-heavy" or "bid-heavy" and writes that
   alert into a small SQLite database.
4) Immediately hands each alert to the in-process LiveTrader so trades can
   fire without waiting on a slower polling loop.

The comments scattered through the file aim to explain each stage in plain
language rather than trading jargon. Feel free to scroll to the section you
care about; each header notes what it controls.
"""

import os
import sys
import argparse
import asyncio
import concurrent.futures
from pathlib import Path
from urllib.parse import urlparse
from collections import deque, defaultdict
from dataclasses import dataclass
from time import time
from datetime import datetime
from typing import Deque, Dict, List, Optional, TypedDict
import sqlite3
import json
import pytz
import logging
from dotenv import load_dotenv
import config_manager
from schwab.auth import easy_client
from schwab.client import Client
from schwab.streaming import StreamClient

# Configure Logging
# Keep log lines structured and timestamped so you can follow what happened
# without digging through print statements.
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Small helper: print a JSON line with a consistent shape so humans and tools
# can read it easily. Warnings are elevated when they relate to alerts.
def log_structured(event: str, data: dict):
    level = logging.INFO if event != "ALERT" else logging.WARNING
    logging.log(level, json.dumps({"event": event, **data}))

# Exchange Code Mapping
# Schwab sends short exchange codes; this map turns them into readable names
# before we evaluate order-book imbalances.
EXCHANGE_MAP = {
    "NYSE": "NYSE",
    "MEMX": "MEMX",
    "IEXG": "IEX",
    "NSDQ": "NASDAQ",
    "NASDAQ": "NASDAQ",
    "ARCX": "NYSE_ARCA",
    "EDGX": "CBOE_EDGX",
    "MIAX": "MIAX",
    "BATX": "CBOE_BZX",
    "BATY": "CBOE_BYX",
    "MWSE": "MIAX_SAPPHIRE",
    "EDGA": "CBOE_EDGA",
    "AMEX": "NYSE_AMEX",
    "CINN": "CINCINNATI",
    "BOSX": "BOX",
    "PHLX": "NASDAQ_PHLX",
    # SIP Codes
    "A": "NYSE_AMEX",
    "B": "NASDAQ_BX",
    "C": "CINCINNATI",  # NYSE National
    "H": "MIAX",
    "I": "ISE",
    "J": "CBOE_EDGA",
    "K": "CBOE_EDGX",
    "M": "MIAX_SAPPHIRE", # NYSE Chicago usually, but mapping to existing MWSE/MIAX_SAPPHIRE logic if appropriate, or just CHICAGO
    "N": "NYSE",
    "P": "NYSE_ARCA",
    "Q": "NASDAQ",
    "U": "MEMX",
    "V": "IEX",
    "X": "NASDAQ_PHLX", # NASDAQ PSX usually, but PHLX is close
    "Y": "CBOE_BYX",
    "Z": "CBOE_BZX",
    "ETMM": "OFF_EXCHANGE", # Likely internal/OTC
    "G": "UNKNOWN_G", # Often TRF or similar
    # Market Makers (BBAI and others)
    "GSCO": "GSCO",
    "XGWD": "XGWD",
    "BTBS": "BTBS",
    "SGAS": "SGAS",
    "WBPX": "WBPX",
    "SSUS": "SSUS",
    "IMCC": "IMCC",
    "FLTG": "FLTG",
    "VIRT": "VIRT",
    "CDRG": "CDRG",
    "TSSM": "TSSM",
    "MLCO": "MLCO",
    "NORT": "NORT",
    "AEXG": "AEXG",
    "LEHM": "LEHM",
    "MAXM": "MAXM",
}

# Helpers
# Environment + parsing utilities so the rest of the file can assume clean
# inputs (no need to remember how each env var is formatted).
def _normalize_and_validate_callback(url: str) -> str:
    if not url:
        raise ValueError("SCHWAB_REDIRECT_URI is empty")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid SCHWAB_REDIRECT_URI '{url}'. Expected full URL like 'https://127.0.0.1:8182/'.")
    return url if url.endswith("/") else url + "/"

def _get_int_env(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return max(default, minimum)
    try:
        val = int(raw)
    except ValueError:
        return max(default, minimum)
    return max(val, minimum)

def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

def _get_float_env(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return max(default, minimum)
    try:
        val = float(raw)
    except ValueError:
        return max(default, minimum)
    return max(val, minimum)
def _get_symbols() -> List[str]:
    config = config_manager.load_config()
    live  = config.get("live_symbols",  "").split(",")
    paper = config.get("paper_symbols", "").split(",")
    all_syms = set()
    for s in live + paper:
        s = s.strip().upper()
        if s:
            all_syms.add(s)
    return sorted(list(all_syms))



# Book Processing
# Convert the raw level-2 order book into bid/ask lists we can count. This is
# the heart of the imbalance detection logic.
class _Row(TypedDict, total=False):
    EX: str
    SIZE: int
    PRICE: float

class _Book(TypedDict, total=False):
    BIDS: List[_Row]
    ASKS: List[_Row]

def _flatten_l2(it: dict) -> _Book:
    out_bids: List[_Row] = []
    out_asks: List[_Row] = []
    symbol = it.get("key", "UNKNOWN")
    error_reported = {"missing_price": False, "parse_price_error": False, "invalid_price": False}

    if DEBUG_BOOK_RAW and _book_raw_remaining[symbol] > 0:
        _book_raw_remaining[symbol] -= 1
        log_structured("BOOK_RAW", {"symbol": symbol, "payload": it})

    bids_src = it.get("2", []) or it.get("BIDS", []) or []
    asks_src = it.get("3", []) or it.get("ASKS", []) or []

    def parse_entries(entries, is_bid: bool) -> List[_Row]:
        result = []
        if not isinstance(entries, list):
            if not error_reported.get("invalid_level", False):
                log_structured("L2_ERROR", {"symbol": symbol, "error": f"Non-list {'bids' if is_bid else 'asks'}"})
                error_reported["invalid_level"] = True
            return result
        for level in entries:
            if not isinstance(level, dict):
                if not error_reported.get("invalid_level", False):
                    log_structured("L2_ERROR", {"symbol": symbol, "error": f"Invalid {'bid' if is_bid else 'ask'} level"})
                    error_reported["invalid_level"] = True
                continue
            price = level.get("0") or level.get("BID_PRICE" if is_bid else "ASK_PRICE")
            if price is None:
                if not error_reported["missing_price"]:
                    log_structured("L2_ERROR", {"symbol": symbol, "error": "missing_price", "is_bid": is_bid})
                    error_reported["missing_price"] = True
                continue
            try:
                price_f = float(price)
            except (TypeError, ValueError) as err:
                if not error_reported["parse_price_error"]:
                    log_structured("L2_ERROR", {"symbol": symbol, "error": "parse_price_error", "is_bid": is_bid})
                    error_reported["parse_price_error"] = True
                continue
            if price_f <= 0:
                if not error_reported["invalid_price"]:
                    log_structured("L2_ERROR", {"symbol": symbol, "error": "invalid_price", "price": price_f, "is_bid": is_bid})
                    error_reported["invalid_price"] = True
                continue
            orders = level.get("3", []) or level.get("BIDS" if is_bid else "ASKS", [])
            if not orders:
                log_structured("L2_ERROR", {"symbol": symbol, "error": f"no_orders in {'bid' if is_bid else 'ask'}"})
                continue
            for order in orders:
                if not isinstance(order, dict):
                    log_structured("L2_ERROR", {"symbol": symbol, "error": f"invalid_order in {'bid' if is_bid else 'ask'}"})
                    continue
                ex = (order.get("0") or order.get("EXCHANGE") or "").upper()
                ex = "NASDAQ" if ex == "NSDQ" else ex
                if not ex or ex not in EXCHANGE_MAP:
                    log_structured("L2_ERROR", {"symbol": symbol, "error": "invalid_exchange", "exchange": ex})
                    continue
                vol = order.get("1") or order.get("BID_VOLUME" if is_bid else "ASK_VOLUME")
                try:
                    vol_i = int(float(vol))
                except (TypeError, ValueError):
                    log_structured("L2_ERROR", {"symbol": symbol, "error": f"parse_volume_error in {'bid' if is_bid else 'ask'}"})
                    continue
                if vol_i <= 0:
                    log_structured("L2_ERROR", {"symbol": symbol, "error": f"invalid_volume in {'bid' if is_bid else 'ask'}"})
                    continue
                result.append({"EX": ex, "SIZE": vol_i, "PRICE": price_f})
        if DEBUG and result:
            log_structured("L2_DEBUG", {
                "symbol": symbol,
                "is_bid": is_bid,
                "count": len(result),
                "exchanges": sorted({r["EX"] for r in result}),
                "top_price": max((r["PRICE"] for r in result), default=0.0),
                "total_volume": sum(r["SIZE"] for r in result)
            })
        return result

    out_bids.extend(parse_entries(bids_src, True))
    out_asks.extend(parse_entries(asks_src, False))

    top_bid = max((row["PRICE"] for row in out_bids), default=0.0)
    top_ask = min((row["PRICE"] for row in out_asks), default=0.0)
    total_bid_vol = sum(row["SIZE"] for row in out_bids)
    total_ask_vol = sum(row["SIZE"] for row in out_asks)
    log_structured("BOOK_SUMMARY", {
        "symbol": symbol,
        "top_bid": top_bid,
        "top_ask": top_ask,
        "bid_volume": total_bid_vol,
        "ask_volume": total_ask_vol,
        "spread_cents": (top_ask - top_bid) * 100.0 if top_bid and top_ask else 0.0
    })
    if DEBUG:
        log_structured("EXCHANGE_DEBUG", {
            "symbol": symbol,
            "bid_exchanges": sorted({row["EX"] for row in out_bids}),
            "ask_exchanges": sorted({row["EX"] for row in out_asks}),
            "total_exchanges": len(set(row["EX"] for row in out_bids) | set(row["EX"] for row in out_asks))
        })

    return {"BIDS": out_bids, "ASKS": out_asks}

@dataclass(frozen=True)
class BookMetrics:
    symbol: str
    total_bids: int
    total_asks: int
    ask_to_bid_ratio: float
    bid_to_ask_ratio: float
    ask_heavy_venues: int
    bid_heavy_venues: int
    per_venue: Dict[str, tuple[int, int]]
    valid_exchanges: int

def process_book(book: _Book, sym: str) -> BookMetrics:
    total_bids = 0
    total_asks = 0
    venue_cells: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    venue_prices: Dict[str, tuple[List[float], List[float]]] = defaultdict(lambda: ([], []))

    for row in book.get("BIDS", []):
        ex = row.get("EX", "UNK") or "UNK"
        try:
            size = int(row.get("SIZE", 0) or 0)
            price = float(row.get("PRICE", 0) or 0)
        except (TypeError, ValueError):
            continue
        if size > 0 and price > 0:
            venue_cells[ex][0] += size
            venue_prices[ex][0].append(price)

    for row in book.get("ASKS", []):
        ex = row.get("EX", "UNK") or "UNK"
        try:
            size = int(row.get("SIZE", 0) or 0)
            price = float(row.get("PRICE", 0) or 0)
        except (TypeError, ValueError):
            continue
        if size > 0 and price > 0:
            venue_cells[ex][1] += size
            venue_prices[ex][1].append(price)

    valid_venues: Dict[str, tuple[int, int]] = {}
    valid_exchanges = 0
    for ex, (bid_sum, ask_sum) in venue_cells.items():
        bid_prices, ask_prices = venue_prices[ex]
        if DEBUG:
            log_structured("VENUE_DEBUG", {
                "symbol": sym,
                "exchange": EXCHANGE_MAP.get(ex, ex),
                "bid_sum": bid_sum,
                "ask_sum": ask_sum,
                "bid_prices": bid_prices,
                "ask_prices": ask_prices
            })
        if bid_prices and ask_prices:
            spread_cents = (min(ask_prices) - max(bid_prices)) * 100.0
            if DEBUG:
                status = "ask-heavy" if ask_sum > bid_sum else "bid-heavy" if bid_sum > ask_sum else "balanced"
                log_structured("SPREAD_DEBUG", {
                    "symbol": sym,
                    "exchange": EXCHANGE_MAP.get(ex, ex),
                    "spread_cents": spread_cents,
                    "bids": bid_sum,
                    "asks": ask_sum,
                    "status": status,
                    "included": spread_cents <= MAX_RANGE_CENTS
                })
            if spread_cents <= MAX_RANGE_CENTS:
                valid_venues[ex] = (bid_sum, ask_sum)
                valid_exchanges += 1
                total_bids += bid_sum
                total_asks += ask_sum

    ask_heavy = sum(1 for b, a in valid_venues.values() if a > b)
    bid_heavy = sum(1 for b, a in valid_venues.values() if b > a)
    ask_to_bid_ratio = (total_asks / total_bids) if total_bids > 0 else float("inf")
    bid_to_ask_ratio = (total_bids / total_asks) if total_asks > 0 else float("inf")

    return BookMetrics(
        symbol=sym,
        total_bids=total_bids,
        total_asks=total_asks,
        ask_to_bid_ratio=ask_to_bid_ratio,
        bid_to_ask_ratio=bid_to_ask_ratio,
        ask_heavy_venues=ask_heavy,
        bid_heavy_venues=bid_heavy,
        per_venue=valid_venues,
        valid_exchanges=valid_exchanges,
    )

# Trade Data Structures
# Global knobs and rolling state that track how many heavy venues exist and
# when an alert was last triggered. Most users only tweak the constants near
# the top of this section.
SYMBOLS: List[str] = []
WINDOW_SECONDS: int = 60
VOL_WINDOW_SECONDS: int = 180
HEARTBEAT_SEC: int = 5
MIN_ASK_HEAVY: int = 4
MIN_BID_HEAVY: int = 4
MAX_RANGE_CENTS: int = 1
MIN_RANGE_CENTS: int = 2
MIN_VOLUME: int = 100000
STOCK_VOLUME_OVERRIDES = {
    "BATL": 15000,
    "PDYN": 8000,
    "UMAC": 3000,
    "CAPR": 5000,
    "OMDA": 5000,
    "WOLF": 5000
}
MIN_IMBALANCE_DURATION_SEC: float = 10.0
# Max real-time gap between two recorded same-direction ticks before we treat
# the imbalance as having lapsed. The deque only records ticks where an
# imbalance fired, so without this a brief re-trigger after a neutral lull
# would otherwise look like one continuous (stale) imbalance.
MAX_IMBALANCE_GAP_SEC: float = 3.0
DB_PATH: str = "penny_basing.db"
MIN_IMBALANCE_RATIO: float = 2.0
DISABLE_BID_HEAVY: bool = False
PRINTED_NO_INSTR: set = set()
last_l1: Dict[str, dict] = {}
trades: Dict[str, Deque] = {}
last_cum_volume: Dict[str, int] = defaultdict(int)
msg_count: Dict[str, int] = {}
last_alert: Dict[str, float] = {}
traders: List = [] # Global list of (name, trader) tuples
last_imbalance: Dict[str, Deque[tuple[float, str, BookMetrics]]] = defaultdict(lambda: deque(maxlen=200))
tape_ticks: Dict[str, Deque] = defaultdict(deque)   # (ts, lee_ready_dir, vol_per_min)
# Trailing-drift tag: the Jun-15 edge backtest and the Jul-06 log replay both
# found the imbalance signal is MEAN-REVERTING (counter-trend alerts carry the
# edge; trend-aligned alerts lose). We stamp every alert with the 60s price
# drift so the Paper Lab can A/B counter vs aligned on forward data before any
# filtering is turned on.
price_hist: Dict[str, Deque[tuple[float, float]]] = defaultdict(deque)  # (ts, price)
DRIFT_WINDOW_SEC: float = 60.0
_tape_prev_price: Dict[str, float] = {}              # last known price per symbol for tick rule
_last_msg_ts: float = 0.0
PRINT_EVERY: int = 20
DEBUG_BOOK_RAW: bool = False
JSON_BOOK: bool = False
SHOW_BOOK: bool = False
BOOK_INTERVAL_SEC: int = 2
_book_raw_remaining: Dict[str, int] = defaultdict(lambda: 5)
volume_window: Dict[str, Deque[int]] = defaultdict(lambda: deque(maxlen=10))
exchange_cache: Dict[str, Optional[str]] = {}
alert_history: Dict[str, List[dict]] = defaultdict(list)
DEBUG: bool = False
_l1_debug_remaining: Dict[str, int] = defaultdict(lambda: 10)
_chart_debug_remaining: Dict[str, int] = defaultdict(lambda: 10)
_timesale_debug_remaining: Dict[str, int] = defaultdict(lambda: 10)
_last_chart_or_timesale_ts: Dict[str, float] = defaultdict(float)
last_bar_minute: Dict[str, int] = {}
current_bar: Dict[str, dict] = {}
_last_volume_fallback_ts: Dict[str, float] = defaultdict(float)
# Persistent thread pools — created once in run_stream() to avoid per-alert overhead
_TRADER_POOL: Optional[concurrent.futures.ThreadPoolExecutor] = None
# Pre-built ET timezone — avoids reconstructing it on every L2 imbalance check
ET_TZ = pytz.timezone("America/New_York")
# Inline live trader hook
# -----------------------
# When grok writes a new alert to SQLite, it also forwards that alert directly
# to LiveTrader in the same process. This keeps latency as low as possible and
# avoids waiting for a separate polling script.
inline_trader_dispatch = None
inline_only_mode: bool = False
inline_only_next_alert_id: int = 0

@dataclass
class Trade:
    ts: float
    px: float
    sz: int

def _touch():
    global _last_msg_ts
    _last_msg_ts = time()

def _prune(sym: str, now_ts: float):
    q = trades[sym]
    cutoff = now_ts - max(WINDOW_SECONDS, VOL_WINDOW_SECONDS)
    while q and q[0].ts < cutoff:
        q.popleft()

def _summarize(sym: str, now: float):
    q = trades[sym]
    if not q:
        log_structured("ROLL", {"symbol": sym, "message": "No prints yet"})
        return 0

    # Price range logic (1-minute window)
    price_q = [t for t in q if t.ts >= now - WINDOW_SECONDS]
    if price_q:
        hi = max(t.px for t in price_q)
        lo = min(t.px for t in price_q)
    else:
        hi, lo = 0.0, 0.0

    # Volume logic (3-minute window)
    vol_q = [t for t in q if t.ts >= now - VOL_WINDOW_SECONDS]
    vol = sum(t.sz for t in vol_q)
    volume_window[sym].append(vol)
    smoothed_vol = sum(volume_window[sym]) / len(volume_window[sym]) if volume_window[sym] else vol

    vol_window_duration = max(min(now - vol_q[0].ts, VOL_WINDOW_SECONDS), 1.0) if vol_q else VOL_WINDOW_SECONDS
    vol_per_min = (smoothed_vol / (vol_window_duration / 60)) if vol_window_duration > 0 else 0

    log_structured("ROLL", {
        "symbol": sym,
        "window_sec": WINDOW_SECONDS,
        "vol_window_sec": VOL_WINDOW_SECONDS,
        "high": hi,
        "low": lo,
        "range_cents": (hi - lo) * 100.0 if hi and lo else 0.0,
        "volume": vol,
        "vol_per_min": vol_per_min,
        "window_duration": vol_window_duration
    })
    if DEBUG:
        log_structured("VOLUME_DEBUG", {
            "symbol": sym,
            "raw_volume": vol,
            "smoothed_volume": smoothed_vol,
            "volume_window": list(volume_window[sym]),
            "vol_per_min": vol_per_min,
            "window_duration": vol_window_duration
        })
    return vol_per_min

# Handlers
# Callback functions triggered by Schwab streaming events. Each one updates the
# rolling state and may emit alerts when conditions are met.
def on_level1(msg: dict):
    for it in msg.get("content", []):
        sym = it.get("key")
        if sym in SYMBOLS:
            if DEBUG and _l1_debug_remaining[sym] > 0:
                _l1_debug_remaining[sym] -= 1
                log_structured("L1_DEBUG", {"symbol": sym, "payload": it})

            # Merge update into state
            if sym not in last_l1:
                last_l1[sym] = {}
            last_l1[sym].update(it)

            # Use merged state for price lookup
            merged = last_l1[sym]
            price = None
            missing_fields = []

            if "LAST_PRICE" in merged:
                price = merged["LAST_PRICE"]
            elif "BID_PRICE" in merged:
                price = merged["BID_PRICE"]
            elif "ASK_PRICE" in merged:
                price = merged["ASK_PRICE"]
            elif "CLOSE_PRICE" in merged:
                price = merged["CLOSE_PRICE"]

            if not price:
                # Check what's missing from the MERGED state
                if "LAST_PRICE" not in merged: missing_fields.append("LAST_PRICE")
                if "BID_PRICE" not in merged: missing_fields.append("BID_PRICE")
                if "ASK_PRICE" not in merged: missing_fields.append("ASK_PRICE")
                if "CLOSE_PRICE" not in merged: missing_fields.append("CLOSE_PRICE")

                log_structured("L1_WARNING", {
                    "symbol": sym,
                    "message": "No valid price",
                    "missing_fields": missing_fields
                })
                continue

            try:
                price = float(price)
                # Zero-latency price routing to inline live traders for Profit Monitoring
                if traders:
                    for name, trader in traders:
                        if hasattr(trader, "update_live_price"):
                            trader.update_live_price(sym, price)
            except (TypeError, ValueError):
                log_structured("L1_WARNING", {"symbol": sym, "message": "Invalid price", "value": price})
                continue

def on_chart_equity(msg: dict):
    now = time()
    for it in msg.get("content", []):
        sym = it.get("key")
        if sym not in trades:
            continue
        if DEBUG and _chart_debug_remaining[sym] > 0:
            _chart_debug_remaining[sym] -= 1
            log_structured("CHART_DEBUG", {"symbol": sym, "payload": it})
        _last_chart_or_timesale_ts[sym] = now
        t_ms = it.get("CHART_TIME", it.get("TIME"))
        try:
            ts = (float(t_ms) / 1000.0) if t_ms is not None else now
        except (TypeError, ValueError):
            ts = now
        px_val = (it.get("CLOSE_PRICE") or it.get("LAST_PRICE") or
                  it.get("PRICE") or it.get("OPEN_PRICE") or
                  it.get("HIGH_PRICE") or it.get("LOW_PRICE"))
        try:
            px = float(px_val)
        except (TypeError, ValueError):
            log_structured("CHART_ERROR", {"symbol": sym, "error": "Invalid price", "value": px_val})
            continue
        try:
            cum = int(it.get("VOLUME", 0) or 0)
        except (TypeError, ValueError):
            log_structured("CHART_ERROR", {"symbol": sym, "error": "Invalid volume", "value": it.get("VOLUME")})
            cum = 0
        prev = last_cum_volume[sym]
        delta = cum - prev
        if delta < 0:
            log_structured("CHART_WARNING", {"symbol": sym, "message": "Negative volume delta, resetting", "cum_volume": cum, "prev_volume": prev})
            last_cum_volume[sym] = cum
            trades[sym].clear()
            volume_window[sym].clear()
            continue
        last_cum_volume[sym] = cum
        if delta > 0:
            trades[sym].append(Trade(ts, px, delta))
            _prune(sym, ts)
            _touch()
            msg_count[sym] += 1
            if DEBUG:
                log_structured("CHART_VOLUME_DEBUG", {
                    "symbol": sym,
                    "cum_volume": cum,
                    "delta_volume": delta,
                    "trade_count": len(trades[sym])
                })
            if msg_count[sym] % PRINT_EVERY == 0:
                _summarize(sym, now)


def on_timesale(msg: dict):
    now = time()
    for it in msg.get("content", []):
        sym = it.get("key")
        if sym not in trades:
            continue
        if DEBUG and _timesale_debug_remaining[sym] > 0:
            _timesale_debug_remaining[sym] -= 1
            log_structured("TIMESALE_DEBUG", {"symbol": sym, "payload": it})
        _last_chart_or_timesale_ts[sym] = now
        px_val = it.get("LAST_PRICE", it.get("PRICE"))
        sz_val = it.get("LAST_SIZE", it.get("TRADE_SIZE", 0))
        t_ms = it.get("TRADE_TIME", it.get("TIME"))
        try:
            px = float(px_val)
            sz = int(sz_val or 0)
            ts = (float(t_ms) / 1000.0) if t_ms is not None else now
        except (TypeError, ValueError):
            log_structured("TIMESALE_ERROR", {"symbol": sym, "error": "Invalid price or size", "price": px_val, "size": sz_val})
            continue
        if sz > 0:
            trades[sym].append(Trade(ts, px, sz))
            _prune(sym, ts)
            _touch()
            msg_count[sym] += 1
            if DEBUG:
                log_structured("TIMESALE_VOLUME_DEBUG", {
                    "symbol": sym,
                    "trade_size": sz,
                    "trade_count": len(trades[sym])
                })
            if msg_count[sym] % PRINT_EVERY == 0:
                _summarize(sym, now)

_last_pi_read_ts = 0.0
_cached_rolling_pi = 0.0

def _drift_60s(sym: str, now: float) -> Optional[float]:
    """Signed price change over the trailing DRIFT_WINDOW_SEC.

    Returns latest_price − price_at_or_before(now − 60s), or None when the
    history doesn't yet reach back 60s (session open, new symbol). The deque
    is ascending, so the reference is the last entry old enough to qualify.
    """
    ph = price_hist.get(sym)
    if not ph:
        return None
    past = None
    for ts, px in ph:
        if ts <= now - DRIFT_WINDOW_SEC:
            past = px
        else:
            break
    if past is None:
        return None
    return ph[-1][1] - past

def on_book(msg: dict):
    global _last_msg_ts, _last_pi_read_ts, _cached_rolling_pi
    now = time()

    # Lightweight cache refresh for Rolling PI to avoid disk IO bottleneck
    if now - _last_pi_read_ts > 5.0:
        _last_pi_read_ts = now
        try:
            state_path = Path(__file__).parent / "live_trader_state.json"
            if state_path.exists():
                with open(state_path, "r") as f:
                    state = json.load(f)
                    _cached_rolling_pi = float(state.get("rolling_pi", 0.0))
        except Exception:
            pass

    for it in msg.get("content", []):
        sym = it.get("key")
        if sym not in SYMBOLS:
            continue
        book = _flatten_l2(it)
        metrics = process_book(book, sym)
        _last_msg_ts = now
        price = last_l1.get(sym, {}).get("LAST_PRICE", 0.0)
        bid_price = max((b.get("PRICE", 0) for b in book["BIDS"]), default=0.0)
        ask_price = min((a.get("PRICE", 0) for a in book["ASKS"]), default=0.0)
        if not price and bid_price and ask_price:
            price = (bid_price + ask_price) / 2
            log_structured("PRICE_FALLBACK", {
                "symbol": sym,
                "bid_price": bid_price,
                "ask_price": ask_price,
                "midpoint": price
            })
        elif not price:
            log_structured("PRICE_FALLBACK_ERROR", {
                "symbol": sym,
                "bid_price": bid_price,
                "ask_price": ask_price
            })
        q = trades.get(sym, deque())
        vol_per_min = 0
        if (now - _last_chart_or_timesale_ts[sym]) > 90.0:
            log_structured("NO_DATA_WARNING", {
                "symbol": sym,
                "message": "No CHART_EQUITY or TIMESALE_EQUITY data for 90s"
            })
            if (now - _last_volume_fallback_ts[sym]) >= 10.0:
                est_volume = (metrics.total_bids + metrics.total_asks) // 2
                est_volume_per_min = (est_volume / (VOL_WINDOW_SECONDS / 60)) if est_volume > 0 else 0
                trades[sym].append(Trade(now, price or bid_price or ask_price or 0.0, est_volume))
                _last_volume_fallback_ts[sym] = now
                _prune(sym, now)
                log_structured("VOLUME_FALLBACK", {
                    "symbol": sym,
                    "est_volume": est_volume,
                    "vol_per_min": est_volume_per_min
                })
                vol_per_min = _summarize(sym, now)
            else:
                vol_per_min = _summarize(sym, now) if q else 0
        else:
            vol_per_min = _summarize(sym, now) if q else 0

        # ── Lee-Ready tape tick (recorded every L2 update) ────────────────────
        if price and bid_price and ask_price:
            if price >= ask_price:
                _tape_dir = 1
            elif price <= bid_price:
                _tape_dir = -1
            else:
                _prev = _tape_prev_price.get(sym, 0.0)
                _tape_dir = 1 if price > _prev else (-1 if price < _prev else 0)
            tape_ticks[sym].append((now, _tape_dir, vol_per_min))
            while tape_ticks[sym] and tape_ticks[sym][0][0] < now - 30:
                tape_ticks[sym].popleft()
        if price:
            _tape_prev_price[sym] = price
            ph = price_hist[sym]
            ph.append((now, price))
            while ph and ph[0][0] < now - (DRIFT_WINDOW_SEC + 30.0):
                ph.popleft()
        # ──────────────────────────────────────────────────────────────────────

        if DEBUG:
            log_structured("IMBALANCE_DEBUG", {
                "symbol": sym,
                "ask_heavy": metrics.ask_heavy_venues,
                "bid_heavy": metrics.bid_heavy_venues,
                "valid_ex": metrics.valid_exchanges,
                "bids": metrics.total_bids,
                "asks": metrics.total_asks,
                "vol_per_min": vol_per_min,
                "price": price,
                "rolling_pi": _cached_rolling_pi
            })
        direction = None

        # Time-of-day venue threshold, evaluated in EXCHANGE (ET) time. The
        # previous version read datetime.fromtimestamp(now) (machine-local time)
        # against hours that were commented as UTC, so the windows never landed
        # where intended. Use ET explicitly so this matches the venue-count
        # windows computed below.
        imbalance_threshold = 4
        _thr_et = datetime.now(ET_TZ)
        _thr_h = _thr_et.hour + _thr_et.minute / 60.0

        if 15.0 <= _thr_h < 16.0:
            imbalance_threshold = 3   # 3-4pm ET: power hour, institutional flow
        elif 10.5 <= _thr_h < 12.0:
            imbalance_threshold = 3   # 10:30am-12pm ET: morning surge
        elif 12.0 <= _thr_h < 14.0:
            imbalance_threshold = 5   # 12-2pm ET: lunch lull

        if not DISABLE_BID_HEAVY and metrics.bid_heavy_venues >= metrics.ask_heavy_venues + imbalance_threshold:
            direction = "bid-heavy"
        elif metrics.ask_heavy_venues >= metrics.bid_heavy_venues + imbalance_threshold:
            direction = "ask-heavy"
        if direction:
            last_imbalance[sym].append((now, direction, metrics))
            # Measure how long the imbalance has continuously persisted. Walk
            # back over consecutive same-direction ticks, but stop at any gap
            # larger than MAX_IMBALANCE_GAP_SEC — the deque only records ticks
            # where an imbalance fired, so a gap means the book went neutral in
            # between and the streak is NOT continuous.
            imbalance_duration = 0.0
            first_ts = now
            prev_ts = now
            for ts, dir, _ in reversed(last_imbalance[sym]):
                if dir != direction:
                    break
                if prev_ts - ts > MAX_IMBALANCE_GAP_SEC:
                    break
                first_ts = ts
                prev_ts = ts
            imbalance_duration = now - first_ts
            if DEBUG:
                log_structured("DIRECTION_DEBUG", {
                    "symbol": sym,
                    "direction": direction,
                    "bid_heavy_venues": metrics.bid_heavy_venues,
                    "ask_heavy_venues": metrics.ask_heavy_venues,
                    "imbalance_duration": round(imbalance_duration, 2)
                })

            # Volatility Filter
            # Volatility Calculation (Passed to Trader)
            range_cents = 0.0
            q = trades.get(sym)
            if q:
                hi = max(t.px for t in q)
                lo = min(t.px for t in q)
                range_cents = (hi - lo) * 100.0

            # Dynamic Duration Logic (Position Aware):
            # We check the REAL position in LiveTrader.
            # If (Position > 0 and Ask-Heavy) OR (Position < 0 and Bid-Heavy):
            #    We are losing money -> Exit Fast (2s).
            # Else (Flat or Stacking):
            #    Wait for standard confirmation (10s).

            curr_min_duration = MIN_IMBALANCE_DURATION_SEC

            # Helper to get net position
            net_pos = 0
            for _, trader in traders:
                if hasattr(trader, "positions"):
                    pos_val = trader.positions.get(sym, 0)
                    if isinstance(pos_val, dict):
                        net_pos += pos_val.get("qty", 0)
                    else:
                        net_pos += pos_val

            is_long = net_pos > 0
            is_short = net_pos < 0

            if (is_long and direction == "ask-heavy") or \
               (is_short and direction == "bid-heavy"):
                 curr_min_duration = 2.0

            # Time-based venue threshold (ET):
            #   10:30–12:00 → 3 venues (active open)
            #   12:00–14:00 → 5 venues (midday lull, stricter)
            #   15:00–16:00 → 3 venues (close rush)
            #   otherwise   → default (MIN_ASK_HEAVY)
            _now_et = datetime.now(ET_TZ)
            _et_h = _now_et.hour + _now_et.minute / 60.0
            if 10.5 <= _et_h < 12.0:
                curr_min_venues = 3
            elif 12.0 <= _et_h < 14.0:
                curr_min_venues = 5
            elif 15.0 <= _et_h < 16.0:
                curr_min_venues = 3
            else:
                curr_min_venues = max(MIN_ASK_HEAVY, MIN_BID_HEAVY)

            curr_min_volume = STOCK_VOLUME_OVERRIDES.get(sym, MIN_VOLUME)
            ratio = metrics.ask_to_bid_ratio if direction == "ask-heavy" else metrics.bid_to_ask_ratio
            is_exit_signal = (is_long and direction == "ask-heavy") or (is_short and direction == "bid-heavy")
            if (imbalance_duration >= curr_min_duration and
                metrics.valid_exchanges >= curr_min_venues and
                vol_per_min >= curr_min_volume and
                (is_exit_signal or ratio >= MIN_IMBALANCE_RATIO)):

                # ── Buy-volume confirmation (Lee-Ready, 10s lookback) ─────────
                _tape_window = [(d, v) for ts, d, v in tape_ticks[sym]
                                if ts >= now - 10 and v > 0]
                if _tape_window:
                    _buy_vol  = sum(v for d, v in _tape_window if d ==  1)
                    _sell_vol = sum(v for d, v in _tape_window if d == -1)
                    _total    = _buy_vol + _sell_vol
                    _buy_frac = _buy_vol / _total if _total > 0 else 0.5
                    _tape_fail = (direction == "bid-heavy" and _buy_frac < 0.60) or \
                                 (direction == "ask-heavy" and _buy_frac > 0.40)
                    if _tape_fail:
                        log_structured("TAPE_FILTER", {
                            "symbol": sym, "direction": direction,
                            "buy_frac": round(_buy_frac, 3), "action": "skipped",
                        })
                        continue
                # ─────────────────────────────────────────────────────────────

                heavy_venues = metrics.ask_heavy_venues if direction == "ask-heavy" else metrics.bid_heavy_venues
                target_limit_price = bid_price if direction == "bid-heavy" else ask_price
                drift_60s = _drift_60s(sym, now)
                alert = {
                    "timestamp": now,
                    "symbol": sym,
                    "ratio": ratio,
                    "total_bids": metrics.total_bids,
                    "total_asks": metrics.total_asks,
                    "heavy_venues": heavy_venues,
                    "direction": direction,
                    "price": price,
                    "target_limit_price": target_limit_price,
                    "vol_per_min": vol_per_min,
                    "range_cents": range_cents,
                    "imbalance_duration": round(imbalance_duration, 2),
                    "drift_60s": round(drift_60s, 4) if drift_60s is not None else None,
                    "exchanges": [EXCHANGE_MAP.get(ex, ex) for ex in metrics.per_venue.keys()]
                }
                alert_history[sym].append(alert)
                if len(alert_history[sym]) > 10:
                    alert_history[sym].pop(0)
                global inline_only_next_alert_id
                c = conn.cursor()
                # Always use in-memory counter (initialized from DB at startup)
                # — avoids a SELECT MAX query on every alert
                inline_only_next_alert_id += 1
                next_alert_id = inline_only_next_alert_id
                inline_ok = True
                if inline_trader_dispatch:
                    inline_ok = inline_trader_dispatch(next_alert_id, alert)

                # Always insert to DB for history, even if inline dispatch happened
                c.execute(
                    "INSERT INTO alerts (rowid, timestamp, symbol, ratio, total_bids, total_asks, heavy_venues, direction, price, vol_per_min, range_cents) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (next_alert_id, alert["timestamp"], alert["symbol"], alert["ratio"], alert["total_bids"],
                     alert["total_asks"], alert["heavy_venues"], alert["direction"], alert["price"], alert["vol_per_min"], alert["range_cents"])
                )
                conn.commit()
                last_alert[sym] = now
                log_structured("ALERT", {
                    "symbol": sym,
                    "direction": direction,
                    "ratio": round(ratio, 2),
                    "venues": heavy_venues,
                    "bids": metrics.total_bids,
                    "asks": metrics.total_asks,
                    "price": round(price, 4),
                    "vol_per_min": round(vol_per_min, 2),
                    "imbalance_duration": round(imbalance_duration, 2),
                    "drift_60s": alert["drift_60s"]
                })

async def resolve_exchange(client: Client, sym: str) -> Optional[str]:
    if sym in exchange_cache:
        return exchange_cache[sym]
    try:
        get_instruments = getattr(client, "get_instruments", None)
        if get_instruments is None:
            raise RuntimeError("Client missing get_instruments")

        instruments = get_instruments([sym], projection="fundamental")
        if asyncio.iscoroutine(instruments):
            instruments = await instruments
        if hasattr(instruments, "json"):
            instruments = instruments.json()
        for inst in instruments:
            if inst.get("symbol") == sym:
                exchange = inst.get("primary_exchange")
                if exchange in {"NASDAQ", "NYSE"}:
                    exchange_cache[sym] = exchange
                    if DEBUG_INSTR:
                        log_structured("INSTR_DEBUG", {"symbol": sym, "exchange": exchange})
                    return exchange
                else:
                    exchange_cache[sym] = None
                    if DEBUG_INSTR:
                        log_structured("INSTR_DEBUG", {"symbol": sym, "exchange": exchange, "action": "subscribing to both"})
                    return None
        exchange_cache[sym] = None
        if DEBUG_INSTR:
            log_structured("INSTR_DEBUG", {"symbol": sym, "error": "No instrument found", "action": "subscribing to both"})
        return None
    except Exception as e:
        log_structured("INSTR_ERROR", {"symbol": sym, "error": str(e)})
        exchange_cache[sym] = None
        return None

async def _book_monitor_task():
    while True:
        log_structured("BOOK_MONITOR", {"message": "Monitoring book updates"})
        await asyncio.sleep(BOOK_INTERVAL_SEC)

async def _heartbeat_task():
    kill_switch_path = Path(os.getenv("LIVE_KILL_SWITCH_FILE", "kill_switch.flag"))
    while True:
        now = time()
        age = (now - _last_msg_ts) if _last_msg_ts else float("inf")
        if age == float("inf"):
            log_structured("HEARTBEAT", {"status": "alive", "message": "No market data yet"})
        else:
            log_structured("HEARTBEAT", {"status": "alive", "last_data_age": round(age, 2)})

        if kill_switch_path.exists():
            log_structured("KILL_SWITCH_DETECTED", {"source": "heartbeat", "message": "Kill switch flag detected — flattening traders before stop"})
            # Run each trader's flatten in the shared pool and AWAIT completion
            # (bounded by a timeout) instead of a blind 3s sleep. The old version
            # fired daemon threads then stopped the loop after 3s, which killed
            # the flatten mid-order and could leave positions open after a
            # "shutdown". Awaiting the pool futures keeps the loop alive so the
            # flatten orders actually finish.
            pool = _TRADER_POOL
            flatten_futs = []
            for _name, trader in list(traders):
                if not hasattr(trader, "_check_kill_switch"):
                    continue
                if pool is not None:
                    flatten_futs.append(asyncio.wrap_future(pool.submit(trader._check_kill_switch)))
                else:
                    # No pool — run inline; the loop is stopping anyway.
                    trader._check_kill_switch()
            if flatten_futs:
                flatten_timeout = _get_float_env("KILL_SWITCH_FLATTEN_TIMEOUT", 30.0, 1.0)
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*flatten_futs, return_exceptions=True),
                        timeout=flatten_timeout,
                    )
                    log_structured("KILL_SWITCH_FLATTEN", {"status": "complete"})
                except asyncio.TimeoutError:
                    log_structured("KILL_SWITCH_FLATTEN", {
                        "status": "timeout",
                        "seconds": flatten_timeout,
                        "message": "Flatten did not finish within timeout; stopping anyway",
                    })
            asyncio.get_running_loop().stop()
            return

        await asyncio.sleep(HEARTBEAT_SEC)

# Main function
async def main():
    # CLI setup: these flags let you tune alert sensitivity without editing
    # code. Defaults come from environment variables so scripts and terminals
    # behave the same way.
    parser = argparse.ArgumentParser(description="Stream L2 data for penny basing detection.")
    parser.add_argument("--symbols", type=str, help="Comma or space separated symbols (overrides $SYMBOLS).")
    parser.add_argument("--window", type=int, help="Rolling window seconds (overrides $WINDOW_SECONDS).")
    parser.add_argument("--heartbeat", type=int, help="Heartbeat interval seconds (overrides $HEARTBEAT_SEC).")
    parser.add_argument("--min-venues", type=int, help="Min heavy venues for alert (overrides $MIN_ASK_HEAVY/$MIN_BID_HEAVY).")
    parser.add_argument("--max-range", type=int, help="Max exchange bid-ask spread in cents (overrides $MAX_RANGE_CENTS).")
    parser.add_argument("--min-range", type=int, help="Min high-low range in cents to allow alert (overrides $MIN_RANGE_CENTS).")
    parser.add_argument("--min-volume", type=int, help="Min volume per minute for alert (overrides $MIN_VOLUME).")
    parser.add_argument("--min-imbalance-duration", type=float, help="Min duration in seconds for imbalance to trigger alert (overrides $MIN_IMBALANCE_DURATION_SEC).")
    parser.add_argument("--db-path", type=str, help="SQLite database path (overrides $DB_PATH).")
    parser.add_argument("--show-book", action="store_true", help="Show book updates.")
    parser.add_argument("--book-interval", type=int, help="Book print interval seconds (overrides $BOOK_INTERVAL_SEC).")
    parser.add_argument("--json-book", action="store_true", help="Show book as JSON.")
    parser.add_argument("--debug-instr", action="store_true", help="Debug: print instrument lookups.")
    parser.add_argument("--debug-book-raw", action="store_true", help="Debug: print raw book payloads.")
    parser.add_argument("--book-raw-limit", type=int, help="How many raw L2 payloads to print when --debug-book-raw is set (default 5).")
    parser.add_argument("--disable-bid-heavy", action="store_true", help="Disable bid-heavy (buyer) alerts.")
    parser.add_argument("--debug", action="store_true", help="Enable detailed debug logging.")
    args = parser.parse_args()

    load_dotenv()

    api_key = os.getenv("SCHWAB_CLIENT_ID")
    app_secret = os.getenv("SCHWAB_APP_SECRET")
    redirect_uri = os.getenv("SCHWAB_REDIRECT_URI")
    token_path = os.getenv("SCHWAB_TOKEN_PATH", "./schwab_tokens.json")
    account_id_s = os.getenv("SCHWAB_ACCOUNT_ID")

    if not api_key or not app_secret or not redirect_uri or not account_id_s:
        missing = [k for k, v in {
            "SCHWAB_CLIENT_ID": api_key,
            "SCHWAB_APP_SECRET": app_secret,
            "SCHWAB_REDIRECT_URI": redirect_uri,
            "SCHWAB_ACCOUNT_ID": account_id_s,
        }.items() if not v]
        log_structured("CONFIG_ERROR", {"missing_vars": missing})
        sys.exit(1)

    try:
        redirect_uri = _normalize_and_validate_callback(redirect_uri)
    except ValueError as e:
        log_structured("CONFIG_ERROR", {"error": str(e)})
        sys.exit(2)

    account_id = account_id_s

    # Auto-start paper_trader if requested (unified startup)
    paper_proc = None
    if _bool_env("RUN_PAPER_TRADER", False) and not _bool_env("ENABLE_INLINE_DISPATCH", False):
        import subprocess
        log_structured("STARTUP", {"message": "Launching paper_trader.py subprocess..."})
        try:
            # Use same python executable
            paper_proc = subprocess.Popen(
                [sys.executable, "paper_trader.py"],
                stdout=open("paper_trader.log", "a"),
                stderr=subprocess.STDOUT
            )
            log_structured("STARTUP", {"message": f"paper_trader started (PID: {paper_proc.pid})"})
        except Exception as e:
            log_structured("STARTUP_ERROR", {"error": f"Failed to start paper_trader: {e}"})

    global WINDOW_SECONDS, VOL_WINDOW_SECONDS, HEARTBEAT_SEC, MIN_ASK_HEAVY, MIN_BID_HEAVY
    global MAX_RANGE_CENTS, MIN_RANGE_CENTS, MIN_VOLUME, MIN_IMBALANCE_DURATION_SEC
    global DB_PATH, SYMBOLS, DISABLE_BID_HEAVY, MIN_IMBALANCE_RATIO, trades, msg_count, _book_raw_remaining
    global DEBUG_BOOK_RAW, JSON_BOOK, SHOW_BOOK, BOOK_INTERVAL_SEC, DEBUG_INSTR, DEBUG

    WINDOW_SECONDS = args.window if args.window is not None else _get_int_env("WINDOW_SECONDS", 60, 30)
    VOL_WINDOW_SECONDS = _get_int_env("VOL_WINDOW_SECONDS", 180, 60)
    HEARTBEAT_SEC = args.heartbeat if args.heartbeat is not None else _get_int_env("HEARTBEAT_SEC", 5, 1)
    MIN_ASK_HEAVY = args.min_venues if args.min_venues is not None else _get_int_env("MIN_ASK_HEAVY", 4, 1)
    MIN_BID_HEAVY = args.min_venues if args.min_venues is not None else _get_int_env("MIN_BID_HEAVY", 4, 1)
    MAX_RANGE_CENTS = args.max_range if args.max_range is not None else _get_int_env("MAX_RANGE_CENTS", 1, 1)
    MIN_RANGE_CENTS = args.min_range if args.min_range is not None else _get_int_env("MIN_RANGE_CENTS", 2, 0)
    MIN_VOLUME = args.min_volume if args.min_volume is not None else _get_int_env("MIN_VOLUME", 100000, 1000)
    MIN_IMBALANCE_DURATION_SEC = args.min_imbalance_duration if args.min_imbalance_duration is not None else _get_float_env("MIN_IMBALANCE_DURATION_SEC", 10.0, 0.0)
    MIN_IMBALANCE_RATIO = _get_float_env("MIN_IMBALANCE_RATIO", 2.0, 1.0)
    DB_PATH = args.db_path if args.db_path is not None else os.getenv("DB_PATH", "penny_basing.db")
    os.environ["DB_PATH"] = str(DB_PATH)
    inline_only_requested = _bool_env("ENABLE_INLINE_DISPATCH", False)
    inline_dry_run = _bool_env(
        "INLINE_DRY_RUN",
        _bool_env("INLINE_LIVE_DRY_RUN", _bool_env("LIVE_DRY_RUN", False)),
    )
    # if args.symbols:
    #     SYMBOLS = [s.strip().upper() for s in args.symbols.replace(" ", ",").split(",") if s.strip()]
    # else:
    SYMBOLS = _get_symbols()
    DISABLE_BID_HEAVY = bool(args.disable_bid_heavy)
    DEBUG_BOOK_RAW = bool(args.debug_book_raw)
    JSON_BOOK = bool(args.json_book)
    SHOW_BOOK = bool(args.show_book)
    BOOK_INTERVAL_SEC = args.book_interval if args.book_interval is not None else _get_int_env("BOOK_INTERVAL_SEC", 2, 1)
    _book_raw_remaining = defaultdict(lambda: args.book_raw_limit if args.book_raw_limit is not None else _get_int_env("BOOK_RAW_LIMIT", 5, 1))
    DEBUG_INSTR = bool(args.debug_instr) or any(sym in {"CRON", "F"} for sym in SYMBOLS)
    DEBUG = bool(args.debug)

    if not SYMBOLS:
        log_structured("CONFIG_ERROR", {"error": "No symbols provided"})
        sys.exit(2)

    trades = {s: deque() for s in SYMBOLS}
    msg_count = {s: 0 for s in SYMBOLS}

    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    global conn, inline_only_next_alert_id
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    c = conn.cursor()
    c.execute("PRAGMA table_info(alerts)")
    columns = [info[1] for info in c.fetchall()]
    required_columns = {"timestamp", "symbol", "ratio", "total_bids", "total_asks", "heavy_venues", "direction", "price", "range_cents"}
    if not all(col in columns for col in required_columns):
        c.execute("DROP TABLE IF EXISTS alerts")
        c.execute('''
            CREATE TABLE alerts (
                timestamp REAL,
                symbol TEXT,
                ratio REAL,
                total_bids INTEGER,
                total_asks INTEGER,
                heavy_venues INTEGER,
                direction TEXT,
                price REAL,
                vol_per_min REAL,
                range_cents REAL
            )
        ''')
    inline_only_next_alert_id = (c.execute("SELECT IFNULL(MAX(rowid), 0) FROM alerts").fetchone() or [0])[0]
    conn.commit()

    global inline_trader_dispatch, inline_only_mode, traders
    inline_trader_dispatch = None
    inline_only_mode = False
    try:
        trader_kind = "live"
        traders.clear()

        inline_requests = _bool_env("ENABLE_INLINE_DISPATCH", False)

        if inline_requests:
            if inline_dry_run:
                from paper_trader import PaperTrader
                _paper = PaperTrader()
                # Inline mode dispatches process_alert directly and never calls
                # start(), so start the maker liveness timer here (no-op unless
                # maker mode is on) — otherwise pending exits never cross and
                # the kill switch is ignored on a quiet feed.
                _paper.start_maker_timer()
                traders.append(("paper", _paper))
                trader_kind = "paper"
            else:
                from live_trader import LiveTrader, SchwabOrderExecutor
                # Primary account (original settings)
                traders.append(("primary", LiveTrader(dry_run=False, name="primary")))
        else:
            log_structured("STARTUP", {"message": "In-process (inline) traders disabled via ENABLE_INLINE_DISPATCH=0"})

        # Persistent thread pool — created once, reused for every alert dispatch
        global _TRADER_POOL
        _TRADER_POOL = concurrent.futures.ThreadPoolExecutor(
            max_workers=max(4, len(traders) * 2),
            thread_name_prefix="trader-dispatch",
        )


        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=_get_int_env("INLINE_TRADER_QUEUE", 100, 10))
        worker_count = _get_int_env("INLINE_TRADER_WORKERS", 1, 1)
        inline_queue_drops = 0
        _inline_base_qty = config_manager.load_config().get("paper_position_size" if inline_dry_run else "live_position_size", 100)

        async def _inline_worker() -> None:
            while True:
                alert_id, alert, enqueued_at = await queue.get()
                try:
                    lag = time() - enqueued_at
                    if lag > 0.5:
                        log_structured("INLINE_TRADER_LAG", {"alert_id": alert_id, "lag_sec": round(lag, 3)})

                    if not traders:
                        log_structured("INLINE_DISPATCH", {"alert_id": alert_id, "message": "No in-process traders to notify"})
                        continue

                    pool = _TRADER_POOL
                    if pool is not None:
                        futs = [
                            pool.submit(
                                trader.process_alert,
                                int(alert_id),
                                alert["symbol"],
                                alert["direction"],
                                float(alert["price"]),
                                range_cents=float(alert.get("range_cents", 0.0)),
                                ratio=alert.get("ratio"),
                                imbalance_duration=alert.get("imbalance_duration"),
                                heavy_venues=alert.get("heavy_venues"),
                                drift_60s=alert.get("drift_60s"),
                                # Real near-touch (bid for bid-heavy, offer for
                                # ask-heavy) so the maker sim rests AT the touch
                                # instead of rebuilding it from a flat constant.
                                target_limit_price=alert.get("target_limit_price"),
                            )
                            for name, trader in traders
                        ]
                        # Await the pool work WITHOUT blocking the event loop:
                        # wrap each concurrent.futures.Future so the loop stays
                        # free to process market data while the order executes.
                        # The limit-order polls, the market-path sleep, and the
                        # cancel sweeps all run in the pool thread, not here.
                        if futs:
                            results = await asyncio.gather(
                                *(asyncio.wrap_future(f) for f in futs),
                                return_exceptions=True,
                            )
                            for r in results:
                                if isinstance(r, Exception):
                                    log_structured("INLINE_TRADER_THREAD_ERROR", {"error": str(r)})
                except Exception as exc:
                    log_structured("INLINE_TRADER_ERROR", {"error": str(exc), "alert_id": alert_id})
                finally:
                    queue.task_done()

        for _ in range(worker_count):
            asyncio.create_task(_inline_worker())

        def inline_trader_dispatch(alert_id: int, alert: dict) -> bool:
            nonlocal inline_queue_drops
            try:
                queue.put_nowait((alert_id, alert, time()))
                return True
            except asyncio.QueueFull:
                inline_queue_drops += 1
                log_structured(
                    "INLINE_TRADER_WARNING",
                    {
                        "status": "queue_full",
                        "alert_id": alert_id,
                        "symbol": alert.get("symbol"),
                        "drops": inline_queue_drops,
                    },
                )
                return False

        inline_only_mode = inline_only_requested
        inline_log = {
            "status": "enabled",
            "dry_run": inline_dry_run,
            "trader": trader_kind,
        }
        if inline_only_mode:
            inline_log["mode"] = "inline_only"
        log_structured("INLINE_TRADER", inline_log)
    except Exception as exc:
        inline_only_mode = False
        log_structured("INLINE_TRADER_ERROR", {"error": str(exc)})

    if inline_only_requested and not inline_only_mode:
        log_structured(
            "INLINE_TRADER",
            {"status": "inline_only_disabled", "reason": "dispatch unavailable"},
        )

    try:
        log_structured("CLIENT_INIT", {"token_path": token_path})
        from schwab import auth
        client = auth.client_from_token_file(token_path=token_path, api_key=api_key, app_secret=app_secret, enforce_enums=False)
    except Exception as e:
        log_structured("CLIENT_ERROR", {"error": f"Failed to initialize Schwab client: {e}"})
        sys.exit(3)

    stream = StreamClient(client, account_id=account_id)

    stream.add_level_one_equity_handler(on_level1)
    has_ts = hasattr(stream, "add_timesale_equity_handler") and hasattr(stream, "timesale_equity_subs")
    if has_ts:
        stream.add_timesale_equity_handler(on_timesale)
    else:
        stream.add_chart_equity_handler(on_chart_equity)
    stream.add_nasdaq_book_handler(on_book)
    stream.add_nyse_book_handler(on_book)

    async def connect_with_retries(max_attempts: int = 3):
        for attempt in range(1, max_attempts + 1):
            try:
                await stream.login()
                log_structured("SUBS", {"status": "success"})
                return True
            except Exception as e:
                log_structured("SUBS_ERROR", {"attempt": attempt, "error": str(e)})
                if attempt < max_attempts:
                    await asyncio.sleep(5)
                continue
        log_structured("SUBS_ERROR", {"error": "Max retry attempts reached"})
        return False

    if not await connect_with_retries():
        log_structured("SUBS_ERROR", {"error": "Failed to establish stream connection"})
        sys.exit(4)

    async def _subscribe_all() -> None:
        """(Re)apply QoS and every subscription. Safe to call after each (re)login:
        Schwab SUBS replaces any prior subscription, so calling this again after a
        reconnect restores the full feed. Without it, a fresh login leaves the
        stream silently unsubscribed and the bot goes dark until manual restart."""
        try:
            if hasattr(stream, "quality_of_service"):
                await stream.quality_of_service(StreamClient.QOSLevel.EXPRESS)
            elif hasattr(stream, "set_quality_of_service"):
                await stream.set_quality_of_service(StreamClient.QOSLevel.EXPRESS)
            elif hasattr(stream, "set_qos"):
                await stream.set_qos(StreamClient.QOSLevel.EXPRESS)
        except Exception as e:
            log_structured("QOS_ERROR", {"error": f"Failed to set QoS: {e}"})

        await stream.level_one_equity_subs(SYMBOLS)
        if has_ts:
            await stream.timesale_equity_subs(SYMBOLS)
        else:
            await stream.chart_equity_subs(SYMBOLS)

        nasdaq_syms = []
        nyse_syms = []

        for sym in SYMBOLS:
            if sym == "CRON":
                log_structured("SUBS", {"symbol": sym, "exchange": "NASDAQ"})
                nasdaq_syms.append(sym)
                continue
            ex = await resolve_exchange(client, sym)
            if ex is None:
                if sym not in PRINTED_NO_INSTR:
                    log_structured("SUBS_WARNING", {"symbol": sym, "message": "No instrument found, subscribing to both books"})
                    PRINTED_NO_INSTR.add(sym)
                nasdaq_syms.append(sym)
                nyse_syms.append(sym)
            elif ex == "NASDAQ":
                nasdaq_syms.append(sym)
            elif ex == "NYSE":
                nyse_syms.append(sym)
            else:
                if sym not in PRINTED_NO_INSTR:
                    log_structured("SUBS_WARNING", {"symbol": sym, "exchange": ex, "message": "Unsupported exchange, subscribing to both"})
                    PRINTED_NO_INSTR.add(sym)
                nasdaq_syms.append(sym)
                nyse_syms.append(sym)

        if nasdaq_syms:
            await stream.nasdaq_book_subs(nasdaq_syms)
        if nyse_syms:
            await stream.nyse_book_subs(nyse_syms)

        log_structured("SUBS", {"message": f"Subscribed to L1, {'timesales' if has_ts else 'chart'}, and L2 for: {', '.join(SYMBOLS)}"})

    await _subscribe_all()
    log_structured("START", {
        "symbols": SYMBOLS,
        "window": WINDOW_SECONDS,
        "venues": MIN_ASK_HEAVY,
        "spread_cents": MAX_RANGE_CENTS,
        "volume_per_min": MIN_VOLUME,
        "min_imbalance_duration": MIN_IMBALANCE_DURATION_SEC,
        "imbalance_threshold": 4
    })

    hb_task = asyncio.create_task(_heartbeat_task())
    book_task = None
    if SHOW_BOOK:
        book_task = asyncio.create_task(_book_monitor_task())

    async def _profit_limit_monitor_task() -> None:
        """Periodically check inline traders for limit lock-in thresholds."""
        while True:
            try:
                if not traders:
                    await asyncio.sleep(1)
                    continue
                pool = _TRADER_POOL
                if pool is not None:
                    futs = [
                        pool.submit(trader._check_profit_limits)
                        for name, trader in traders
                        if hasattr(trader, "_check_profit_limits")
                    ]
                    # Await pool work without blocking the loop (see _inline_worker).
                    if futs:
                        results = await asyncio.gather(
                            *(asyncio.wrap_future(f) for f in futs),
                            return_exceptions=True,
                        )
                        for r in results:
                            if isinstance(r, Exception):
                                log_structured("LIMIT_MONITOR_ERROR", {"error": str(r)})
            except Exception as exc:
                log_structured("LIMIT_MONITOR_CRITICAL", {"error": str(exc)})

            await asyncio.sleep(0.5)

    profit_task = asyncio.create_task(_profit_limit_monitor_task())

    try:
        while True:
            try:
                msg = await asyncio.wait_for(stream.handle_message(), timeout=30.0)
                if DEBUG:
                    log_structured("STREAM_DEBUG", {"message": msg})
            except asyncio.TimeoutError:
                log_structured("STREAM_ERROR", {"error": "No messages for 30s"})
                # Stream went silent — reconcile positions on all live traders before
                # reconnecting so any in-flight order is caught during the gap.
                for _name, _trader in traders:
                    if hasattr(_trader, "_reconcile_positions_on_startup"):
                        try:
                            pool = _TRADER_POOL
                            if pool is not None:
                                pool.submit(_trader._reconcile_positions_on_startup).result(timeout=8)
                            log_structured("STREAM_RECONCILE", {"trader": _name, "reason": "stream_timeout"})
                        except Exception as _e:
                            log_structured("STREAM_RECONCILE_ERROR", {"trader": _name, "error": str(_e)})
                if not await connect_with_retries():
                    log_structured("STREAM_ERROR", {"error": "Reconnection failed"})
                    break
                # A fresh login starts an unsubscribed session — re-apply every
                # subscription or the stream stays silent forever (perpetual 30s
                # timeout loop) while we may still be holding a position.
                try:
                    await _subscribe_all()
                    log_structured("SUBS", {"status": "resubscribed_after_reconnect"})
                except Exception as _sub_e:
                    log_structured("SUBS_ERROR", {"error": f"Re-subscribe after reconnect failed: {_sub_e}"})
                    break
            except Exception as _conn_err:
                _err_str = str(_conn_err)
                _is_close = any(x in _err_str for x in (
                    "close frame", "1000", "1001", "1006",
                    "ConnectionClosed", "connection closed", "no close frame",
                ))
                if not _is_close:
                    raise
                log_structured("STREAM_RECONNECT", {"reason": "connection_closed", "error": _err_str})
                await asyncio.sleep(2)
                if not await connect_with_retries():
                    log_structured("STREAM_ERROR", {"error": "Reconnection failed after close"})
                    break
                try:
                    await _subscribe_all()
                    log_structured("SUBS", {"status": "resubscribed_after_close"})
                except Exception as _sub_e:
                    log_structured("SUBS_ERROR", {"error": f"Re-subscribe after close failed: {_sub_e}"})
                    break
    except KeyboardInterrupt:
        log_structured("STOP", {"message": "User stopped"})
    finally:
        hb_task.cancel()
        if book_task:
            book_task.cancel()
        if conn:
            conn.close()
        if _TRADER_POOL is not None:
            _TRADER_POOL.shutdown(wait=False)
        try:
            await stream.logout()
        except Exception:
            pass
        if paper_proc:
            log_structured("SHUTDOWN", {"message": "Stopping paper_trader subprocess..."})
            paper_proc.terminate()
            try:
                paper_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                paper_proc.kill()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log_structured("STOP", {"message": "User stopped"})
    except Exception as e:
        log_structured("FATAL_ERROR", {"error": str(e)})
        try:
            from telegram_notifier import TelegramNotifier
            TelegramNotifier().notify_error("Grok Pipeline Fatal Crash", str(e))
        except Exception:
            pass
        sys.exit(5)
