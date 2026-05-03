"""
pattern_engine/scanner.py

Main entry point.  Fetches bars for all symbols, runs all 3 detectors,
sends hits through the Claude filter, and prints final signals.

Usage:
    # Scan live (last 5 days of 1-min bars):
    .venv/bin/python3 -m pattern_engine.scanner

    # Backtest a specific date range:
    .venv/bin/python3 -m pattern_engine.scanner --backtest --start 2026-03-31 --end 2026-04-06

    # Skip Claude filter (faster, for testing detectors):
    .venv/bin/python3 -m pattern_engine.scanner --no-claude

    # Only Grade A/B signals:
    .venv/bin/python3 -m pattern_engine.scanner --min-grade B
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, date
from typing import List, Optional, Tuple

import pandas as pd
import yfinance as yf

from pattern_engine.indicators import add_all
from pattern_engine.signal import PatternSignal
from pattern_engine.patterns import bull_flag, asc_triangle, dbl_bottom, dbl_top
from pattern_engine.claude_filter import ask_claude

logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt= "%H:%M:%S",
)
LOGGER = logging.getLogger("scanner")

SYMBOLS = ["AAL", "BBAI", "F", "RIG", "SOXS"]

GRADE_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1}


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_bars(symbol: str, period: str = "30d") -> pd.DataFrame:
    """Download 15-min bars, return clean OHLCV df (market hours only)."""
    raw = yf.Ticker(symbol).history(period=period, interval="15m")
    if raw.empty:
        return pd.DataFrame()
    raw.columns = [c.lower() for c in raw.columns]
    df = raw[["open", "high", "low", "close", "volume"]].copy()
    if df.index.tz is not None:
        df.index = df.index.tz_convert("America/New_York").tz_localize(None)
    df = df.between_time("09:30", "15:45")
    return df.dropna(subset=["open", "high", "low", "close"])


def fetch_spy(start: str, end: str) -> Optional[pd.DataFrame]:
    """Fetch SPY daily bars for market context filter."""
    try:
        raw = yf.download("SPY", start=start, end=end, interval="1d",
                          auto_adjust=True, progress=False)
        if raw.empty:
            return None
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [col[0].lower() for col in raw.columns]
        else:
            raw.columns = [c.lower() for c in raw.columns]
        df = raw[["open", "high", "low", "close", "volume"]].copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df.dropna()
    except Exception as exc:
        LOGGER.warning("Could not fetch SPY: %s", exc)
        return None


def fetch_bars_range(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Download 15-min bars for a specific date range (max ~60 days back)."""
    raw = yf.download(
        symbol, start=start, end=end,
        interval="15m", auto_adjust=True, progress=False,
    )
    if raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [col[0].lower() for col in raw.columns]
    else:
        raw.columns = [c.lower() for c in raw.columns]
    df = raw[["open", "high", "low", "close", "volume"]].copy()
    if df.index.tz is not None:
        df.index = df.index.tz_convert("America/New_York").tz_localize(None)
    df = df.between_time("09:30", "15:45")
    return df.dropna(subset=["open", "high", "low", "close"])


# ── Signal filtering ──────────────────────────────────────────────────────────

def grade_value(sig: PatternSignal) -> int:
    return GRADE_ORDER.get(sig.confidence_grade, 0)


def passes_grade(sig: PatternSignal, min_grade: str) -> bool:
    return grade_value(sig) >= GRADE_ORDER.get(min_grade, 0)


# ── Scan one symbol ───────────────────────────────────────────────────────────

def _cross_pattern_deduplicate(
    signals: List[PatternSignal],
    lockout_minutes: int = 390,
) -> List[PatternSignal]:
    """
    Cross-pattern deduplication.

    Each individual detector deduplicates within itself, but two different
    detectors can still fire on the same symbol within a short window.

    Rule: after accepting any signal for a symbol, suppress all signals for
    that same symbol for the next lockout_minutes of clock time.
    Keep the highest-confidence signal when multiple fire in the same window.

    Default 390 min = 1 full trading day (suitable for 15-min bars).
    """
    signals.sort(key=lambda s: (s.detected_at, -s.confidence))

    last_accepted: dict[str, datetime] = {}
    kept: List[PatternSignal] = []

    for sig in signals:
        last = last_accepted.get(sig.symbol)
        if last is not None:
            elapsed_min = (sig.detected_at - last).total_seconds() / 60
            if elapsed_min < lockout_minutes:
                continue
        kept.append(sig)
        last_accepted[sig.symbol] = sig.detected_at

    return kept


def _market_context_ok(df_spy: Optional[pd.DataFrame], signal_date: date) -> bool:
    """
    Fix 3: Market context filter.

    Don't trade bullish patterns on days when the broad market (SPY) opened
    down more than 1% from the prior close.  On those days the entire market
    is in sell mode — individual bullish patterns are swimming upstream.

    Returns True (ok to trade) if:
      - SPY data is unavailable (fail open)
      - SPY daily move is within -1% of prior close
    Returns False (skip) if SPY opened down > 1%.
    """
    if df_spy is None or df_spy.empty:
        return True   # no data → don't block

    day_bars = df_spy[df_spy.index.date == signal_date]
    if day_bars.empty:
        return True

    # Compare open of first bar to close of prior day
    prior_bars = df_spy[df_spy.index.date < signal_date]
    if prior_bars.empty:
        return True

    prior_close = float(prior_bars.iloc[-1]["close"])
    day_open    = float(day_bars.iloc[0]["open"])
    pct_change  = (day_open - prior_close) / prior_close

    if pct_change < -0.01:   # opened down more than 1%
        LOGGER.info(
            "Market context filter: SPY opened %.2f%% on %s — skipping bullish signals",
            pct_change * 100, signal_date,
        )
        return False

    return True


def scan_symbol(
    df: pd.DataFrame,
    symbol: str,
    use_claude: bool = True,
    min_grade: str = "C",
    df_spy: Optional[pd.DataFrame] = None,
) -> List[PatternSignal]:
    """
    Run all 3 detectors on df, apply all filters, optionally call Claude.
    Returns list of approved signals sorted by detected_at.
    """
    if df.empty or len(df) < 20:
        return []

    df = add_all(df)

    raw_signals: List[PatternSignal] = []
    raw_signals.extend(bull_flag.detect(df, symbol))
    raw_signals.extend(asc_triangle.detect(df, symbol))
    raw_signals.extend(dbl_bottom.detect(df, symbol))
    raw_signals.extend(dbl_top.detect(df, symbol))

    # Grade filter
    raw_signals = [s for s in raw_signals if passes_grade(s, min_grade)]

    # Fix 3: Market context filter (per signal date)
    if df_spy is not None:
        raw_signals = [
            s for s in raw_signals
            if _market_context_ok(df_spy, s.detected_at.date())
        ]

    # Cross-pattern deduplication (1 day = 390 min on 15-min bars)
    raw_signals = _cross_pattern_deduplicate(raw_signals, lockout_minutes=390)

    if not use_claude:
        return raw_signals

    approved: List[PatternSignal] = []
    for sig in raw_signals:
        result = ask_claude(sig)
        if result is not None:
            approved.append(result)

    return approved


# ── Backtest ──────────────────────────────────────────────────────────────────

def backtest_signal(
    sig: PatternSignal,
    df_full: pd.DataFrame,
) -> dict:
    """
    Walk forward from the signal's detected_at bar until target or stop is hit.
    If the dataset ends before either triggers, outcome is 'open' (still live).
    """
    future = df_full[df_full.index > sig.detected_at]

    if future.empty:
        return {
            "outcome"   : "open",
            "exit_time" : None,
            "exit_price": None,
            "pnl"       : 0.0,
            "bars_held" : 0,
        }

    for i, (ts, row) in enumerate(future.iterrows()):
        if sig.direction == "long":
            if row["low"] <= sig.stop:
                return {
                    "outcome"   : "stop",
                    "exit_time" : ts,
                    "exit_price": sig.stop,
                    "pnl"       : round(sig.stop - sig.entry, 4),
                    "bars_held" : i + 1,
                }
            if row["high"] >= sig.target:
                return {
                    "outcome"   : "target",
                    "exit_time" : ts,
                    "exit_price": sig.target,
                    "pnl"       : round(sig.target - sig.entry, 4),
                    "bars_held" : i + 1,
                }
        else:  # short
            if row["high"] >= sig.stop:
                return {
                    "outcome"   : "stop",
                    "exit_time" : ts,
                    "exit_price": sig.stop,
                    "pnl"       : round(sig.entry - sig.stop, 4),
                    "bars_held" : i + 1,
                }
            if row["low"] <= sig.target:
                return {
                    "outcome"   : "target",
                    "exit_time" : ts,
                    "exit_price": sig.target,
                    "pnl"       : round(sig.entry - sig.target, 4),
                    "bars_held" : i + 1,
                }

    # Data ended before target or stop — trade is still open
    return {
        "outcome"   : "open",
        "exit_time" : None,
        "exit_price": None,
        "pnl"       : 0.0,
        "bars_held" : len(future),
    }


# ── Pretty printing ───────────────────────────────────────────────────────────

def print_header(title: str) -> None:
    w = 70
    print()
    print("═" * w)
    print(f"  {title}")
    print("═" * w)


def print_backtest_results(results: list[dict]) -> None:
    """Print a summary table of backtest outcomes."""
    if not results:
        print("  No signals to backtest.")
        return

    wins   = [r for r in results if r["result"]["outcome"] == "target"]
    stops  = [r for r in results if r["result"]["outcome"] == "stop"]
    opens  = [r for r in results if r["result"]["outcome"] == "open"]
    total  = len(results)

    total_pnl = sum(r["result"]["pnl"] for r in results)
    win_rate  = len(wins) / total * 100 if total else 0

    print(f"\n  {'Symbol':<6} {'Pattern':<20} {'Dir':<5} {'Entry':>7} "
          f"{'Stop':>7} {'Target':>7} {'Outcome':<8} {'P&L':>7}  {'Time'}")
    print(f"  {'──────':<6} {'───────':<20} {'───':<5} {'─────':>7} "
          f"{'────':>7} {'──────':>7} {'───────':<8} {'───':>7}  {'────'}")

    for r in results:
        sig = r["signal"]
        res = r["result"]
        outcome_str = res["outcome"].upper()
        exit_t = res["exit_time"].strftime("%H:%M") if res["exit_time"] else "—"
        pnl_str = f"{res['pnl']:+.3f}"
        print(
            f"  {sig.symbol:<6} {sig.pattern_name:<20} {sig.direction:<5} "
            f"${sig.entry:>6.3f} ${sig.stop:>6.3f} ${sig.target:>6.3f} "
            f"{outcome_str:<8} {pnl_str:>7}  {exit_t}"
        )

    print()
    closed = len(wins) + len(stops)
    print(f"  Total signals : {total}")
    print(f"  Targets hit   : {len(wins)}  ({win_rate:.0f}% of closed)")
    print(f"  Stops hit     : {len(stops)}")
    print(f"  Still open    : {len(opens)}  (data ended before target/stop)")
    print(f"  Net P&L/share : {total_pnl:+.4f}  (closed trades only, 1 share each)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Pattern Engine Scanner")
    parser.add_argument("--backtest",   action="store_true", help="Run in backtest mode")
    parser.add_argument("--start",      default="2006-01-01", help="Backtest start date YYYY-MM-DD")
    parser.add_argument("--end",        default="2026-04-07", help="Backtest end date YYYY-MM-DD (exclusive)")
    parser.add_argument("--no-claude",  action="store_true", help="Skip Claude filter")
    parser.add_argument("--min-grade",  default="C",         help="Minimum grade A/B/C/D")
    parser.add_argument("--symbols",    default=",".join(SYMBOLS), help="Comma-separated symbols")
    args = parser.parse_args()

    symbols    = [s.strip().upper() for s in args.symbols.split(",")]
    use_claude = not args.no_claude
    mode       = "BACKTEST" if args.backtest else "LIVE SCAN"

    print_header(
        f"Pattern Engine — {mode}  |  "
        f"{'Claude ON' if use_claude else 'Claude OFF'}  |  "
        f"Min grade: {args.min_grade}"
    )

    if args.backtest:
        print(f"  Date range: {args.start} → {args.end}")
    print(f"  Symbols: {', '.join(symbols)}")

    # Fetch SPY for market context filter
    df_spy: Optional[pd.DataFrame] = None
    if args.backtest:
        LOGGER.info("Fetching SPY for market context...")
        df_spy = fetch_spy(args.start, args.end)
        if df_spy is not None:
            LOGGER.info("SPY: %d bars loaded", len(df_spy))
        else:
            LOGGER.warning("SPY unavailable — market context filter disabled")

    all_signals: List[PatternSignal] = []
    all_results: list[dict] = []

    for symbol in symbols:
        LOGGER.info("Fetching %s...", symbol)

        if args.backtest:
            df = fetch_bars_range(symbol, args.start, args.end)
        else:
            df = fetch_bars(symbol, period="5d")

        if df.empty:
            LOGGER.warning("%s: no data", symbol)
            continue

        LOGGER.info("%s: %d bars loaded", symbol, len(df))

        signals = scan_symbol(
            df, symbol,
            use_claude=use_claude,
            min_grade=args.min_grade,
            df_spy=df_spy,
        )

        if not signals:
            LOGGER.info("%s: no signals", symbol)
            continue

        LOGGER.info("%s: %d signal(s) approved", symbol, len(signals))

        for sig in signals:
            all_signals.append(sig)
            print()
            print(sig.detail())

            if args.backtest:
                result = backtest_signal(sig, df)
                all_results.append({"signal": sig, "result": result})
                outcome = result["outcome"].upper()
                exit_t  = result["exit_time"].strftime("%H:%M") if result["exit_time"] else "—"
                pnl     = result["pnl"]
                print(f"  BACKTEST → {outcome}  exit {exit_t}  P&L ${pnl:+.3f}/share")

    # ── Summary ───────────────────────────────────────────────────────────────
    print_header(f"SUMMARY — {len(all_signals)} signal(s) across {len(symbols)} symbols")

    if args.backtest and all_results:
        print_backtest_results(all_results)
    elif all_signals:
        for sig in sorted(all_signals, key=lambda s: s.detected_at):
            print(f"  {sig.summary()}")
    else:
        print("  No signals found.")
        if use_claude:
            print("  (Try --no-claude to see raw detector output before Claude filters)")


if __name__ == "__main__":
    main()
