"""
pattern_engine/patterns/asc_triangle.py

Ascending triangle detector.

Structure:
  FLAT RESISTANCE — 3+ highs within RESIST_TOL% of each other
  RISING SUPPORT  — lows trending upward across thirds of the pattern
  BREAKOUT        — price closes above the resistance level

All rules derived from the SOXS March 30 walkthrough.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import numpy as np
import pandas as pd

from pattern_engine.signal import PatternSignal, PATTERN_ASC_TRIANGLE


# ── Thresholds (calibrated for 15-min bars) ───────────────────────────────────
# 1 bar = 15 minutes.  1 trading day ≈ 26 bars.
# Patterns span hours to a few days on 15-min charts.
MIN_BARS          = 20      # 20 × 15min = 5 hours minimum
MAX_BARS          = 80      # 80 × 15min = 20 hours (~3.5 days)
RESIST_TOL        = 0.015   # intraday prices are tighter — allow 1.5%
MIN_RESIST_TOUCH  = 3       # still need 3 touches of resistance
SLOPE_MIN_PCT     = 0.001   # rising lows rise >= 0.1% (smaller moves intraday)
BREAKOUT_VOL_MIN  = 1.3     # breakout bar volume >= 1.3× average
ATR_STOP_BUFFER   = 1.0     # stop = last higher low - (ATR × this); wider for noise
MIN_RR            = 1.5


def detect(df: pd.DataFrame, symbol: str) -> List[PatternSignal]:
    """
    Scan df for ascending triangle patterns.

    Parameters
    ----------
    df     : DataFrame with indicators already added (add_all)
    symbol : ticker string
    """
    if len(df) < MAX_BARS + 5:
        return []

    highs   = df["high"].values
    lows    = df["low"].values
    closes  = df["close"].values
    volumes = df["volume"].values
    atrs    = df["atr"].values
    vol_avg = df["vol_avg"].values
    dates   = df.index

    signals: List[PatternSignal] = []
    last_signal_i = -999

    for end in range(MAX_BARS, len(df)):
        for start in range(end - MAX_BARS, end - MIN_BARS + 1):
            n = end - start
            if n < MIN_BARS:
                continue

            # NOTE: intraday-only rule removed for 15-min timeframe.
            # Ascending triangles on 15m charts routinely span 1-2 days.
            # Overnight gaps within the pattern are acceptable.

            # Resistance is measured from bars BEFORE the current bar so that
            # the breakout check (closes[end] >= resistance) is meaningful.
            sl_h = highs[start: end]       # exclude current bar
            sl_l = lows[start:  end + 1]
            sl_c = closes[start: end + 1]
            sl_v = volumes[start: end + 1]

            if len(sl_h) == 0:
                continue

            # ── Rule 1: flat resistance — 3+ highs near the max ───────────────
            resistance = float(sl_h.max())
            near_top   = int((sl_h >= resistance * (1 - RESIST_TOL)).sum())
            if near_top < MIN_RESIST_TOUCH:
                continue

            # ── Rule 2: rising lows across thirds ────────────────────────────
            t  = len(sl_l)
            t1 = float(sl_l[: t // 3].min())
            t2 = float(sl_l[t // 3: 2 * t // 3].min())
            t3 = float(sl_l[2 * t // 3:].min())
            if not (t3 > t2 > t1):
                continue

            # ── Rule 3: lows must rise meaningfully ──────────────────────────
            if (t3 - t1) / closes[end] < SLOPE_MIN_PCT:
                continue

            # ── Rule 4: range must be large enough to be a real pattern ──────
            overall_range = resistance - t1
            if overall_range < atrs[end] * 2.0:
                continue

            # ── Rule 5: deduplicate ───────────────────────────────────────────
            if end - last_signal_i < MIN_BARS:
                continue

            # ── Rule 5b: Confirmed breakout — close must be above resistance ──
            # Don't enter "approaching" — wait for price to actually close
            # above the resistance level before calling this a breakout.
            if closes[end] < resistance:
                continue

            # ── Rule 5c: EMA trend filter — EMA20 > EMA50 + price above both ─
            # Only trade when the short-term trend is above the medium-term
            # trend (EMA20 crossed above EMA50 = confirmed uptrend).
            if "ema20" in df.columns and "ema50" in df.columns:
                if df["ema20"].iloc[end] <= df["ema50"].iloc[end]:
                    continue
            if "ema20" in df.columns and closes[end] < df["ema20"].iloc[end]:
                continue

            # ── Build trade levels ────────────────────────────────────────────
            height = overall_range
            target = resistance + height
            stop   = t3 - atrs[end] * ATR_STOP_BUFFER
            risk   = closes[end] - stop
            if risk <= 0:
                continue
            rr = (target - closes[end]) / risk
            if rr < MIN_RR:
                continue

            # ── Rule 6: breakout volume check ────────────────────────────────
            # Since we now require a confirmed breakout, always enforce volume.
            at_breakout = True
            avg_v = float(vol_avg[end])
            if avg_v > 0 and volumes[end] < avg_v * BREAKOUT_VOL_MIN:
                continue

            # ── Confidence ────────────────────────────────────────────────────
            scores = [
                min(near_top / MIN_RESIST_TOUCH, 3.0) / 3.0,
                min((t3 - t1) / closes[end] / SLOPE_MIN_PCT, 3.0) / 3.0,
                min(overall_range / (atrs[end] * 2.0), 2.0) / 2.0,
                min(rr / MIN_RR, 2.0) / 2.0,
            ]
            confidence = float(min(max(sum(scores) / len(scores), 0.0), 1.0))

            pattern_bars = df.iloc[start: end + 1].copy()

            sig = PatternSignal(
                symbol      = symbol,
                pattern     = PATTERN_ASC_TRIANGLE,
                direction   = "long",
                entry       = round(float(resistance), 4),
                stop        = round(stop, 4),
                target      = round(target, 4),
                rr          = round(rr, 2),
                confidence  = round(confidence, 3),
                bars        = pattern_bars,
                detected_at = dates[end].to_pydatetime(),
                meta        = {
                    "resistance"  : round(resistance, 4),
                    "low1"        : round(t1, 4),
                    "low2"        : round(t2, 4),
                    "low3"        : round(t3, 4),
                    "n_touches"   : near_top,
                    "height"      : round(height, 4),
                    "n_bars"      : n,
                    "at_breakout" : at_breakout,
                },
            )
            signals.append(sig)
            last_signal_i = end
            break   # one signal per end-bar, move to next end

    return signals


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import yfinance as yf
    import sys
    sys.path.insert(0, ".")
    from pattern_engine.indicators import add_all

    print("Ascending triangle scan — SOXS 5d...")
    raw = yf.Ticker("SOXS").history(period="5d", interval="1m")
    raw.columns = [c.lower() for c in raw.columns]
    df = raw[["open","high","low","close","volume"]].copy()
    df = df.between_time("09:30","16:00").dropna()
    df = add_all(df)

    signals = detect(df, "SOXS")
    print(f"  Found {len(signals)} ascending triangle(s)\n")
    for s in signals[:3]:
        print(s.detail())
        print()
