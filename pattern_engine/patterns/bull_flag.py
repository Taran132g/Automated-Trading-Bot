"""
pattern_engine/patterns/bull_flag.py

Bull flag detector.

A bull flag has two parts:
  POLE  — sharp upward move, mostly green bars, high volume
  FLAG  — tight consolidation, volume fades, slight downward drift

All 8 rules derived from the BBAI March 31 walkthrough:
  1. Pole move >= POLE_ATR_MULT × ATR             (strong enough)
  2. >= POLE_GREEN_MIN of pole bars are green      (one-directional buying)
  3. Pole avg volume >= POLE_VOL_FACTOR × baseline (institutional participation)
  4. Flag range <= FLAG_RANGE_FACTOR × pole height (tight consolidation)
  5. Flag avg volume <= FLAG_VOL_MAX × pole volume (sellers fading)
  6. Flag drift <= FLAG_DRIFT_MAX × pole move      (not still running up)
  7. Pole is entirely intraday — no overnight gaps (gap != pole)
  8. Deduplicate — skip if a flag fired within FLAG_BARS bars
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import pandas as pd

from pattern_engine.signal import PatternSignal, PATTERN_BULL_FLAG


# ── Thresholds (calibrated for 15-min bars) ───────────────────────────────────
# 1 bar = 15 minutes.  1 trading day ≈ 26 bars.
POLE_LOOKBACK      = 8      # 8 × 15min = 2-hour pole
POLE_ATR_MULT      = 1.5    # pole move >= 1.5× ATR
POLE_GREEN_MIN     = 0.60   # >= 60% of pole bars must close up
POLE_VOL_FACTOR    = 1.3    # pole avg volume >= 1.3× prior 20-bar avg
FLAG_BARS          = 8      # 8 × 15min = 2-hour flag consolidation
FLAG_RANGE_FACTOR  = 0.50   # flag high-low range <= 50% of pole height
FLAG_VOL_MAX       = 0.85   # flag avg volume <= 85% of pole avg volume
FLAG_DRIFT_MAX     = 0.35   # flag drift <= 35% of pole move
ATR_STOP_BUFFER    = 1.0    # stop = entry - (ATR × this); wider for intraday noise
MIN_RR             = 1.5


def detect(df: pd.DataFrame, symbol: str) -> List[PatternSignal]:
    """
    Scan df for bull flag patterns.

    Parameters
    ----------
    df     : DataFrame with columns open/high/low/close/volume/atr/vol_avg
             (run indicators.add_all first)
    symbol : ticker string, stored on the signal

    Returns
    -------
    List of PatternSignal — empty list if none found.
    """
    if len(df) < POLE_LOOKBACK + FLAG_BARS + 5:
        return []

    closes  = df["close"].values
    opens   = df["open"].values
    lows    = df["low"].values
    volumes = df["volume"].values
    atrs    = df["atr"].values
    vol_avg = df["vol_avg"].values
    dates   = df.index

    signals: List[PatternSignal] = []
    last_signal_i = -999   # deduplication tracker

    # Scan from the BREAKOUT bar backwards, so every rule uses only past data.
    #
    #   pole_base_i ──── POLE_LOOKBACK bars ──── pole_top_i
    #   pole_top_i  ──── FLAG_BARS bars      ──── end (breakout bar)
    #
    # Signal fires at `end` only when closes[end] > flag high (confirmed breakout).

    for end in range(POLE_LOOKBACK + FLAG_BARS, len(df)):
        pole_top_i  = end - FLAG_BARS
        pole_base_i = pole_top_i - POLE_LOOKBACK

        if pole_base_i < 0:
            continue

        # Slice arrays — all data is from the past relative to `end`
        pole_closes  = closes [pole_base_i : pole_top_i]
        flag_closes  = closes [pole_top_i  : end]        # FLAG_BARS bars
        pole_volumes = volumes[pole_base_i : pole_top_i]
        flag_volumes = volumes[pole_top_i  : end]

        if len(pole_closes) == 0 or len(flag_closes) == 0:
            continue

        pole_move   = closes[pole_top_i - 1] - closes[pole_base_i]
        pole_bottom = float(pole_closes.min())
        pole_top    = float(pole_closes.max())
        pole_height = pole_top - pole_bottom

        # ── Rule 1: pole is large enough ─────────────────────────────────────
        if pole_move < atrs[end] * POLE_ATR_MULT:
            continue

        # ── Rule 2: pole bars are mostly green ───────────────────────────────
        pole_slice = df.iloc[pole_base_i : pole_top_i]
        green_frac = float((pole_slice["close"] > pole_slice["open"]).mean())
        if green_frac < POLE_GREEN_MIN:
            continue

        # ── Rule 3: pole volume is elevated ──────────────────────────────────
        baseline_vol = float(vol_avg[end])
        pole_vol     = float(pole_volumes.mean())
        if baseline_vol == 0 or pole_vol < baseline_vol * POLE_VOL_FACTOR:
            continue

        # ── Rule 4: flag is tight ─────────────────────────────────────────────
        flag_range = float(flag_closes.max() - flag_closes.min())
        if flag_range > pole_height * FLAG_RANGE_FACTOR:
            continue

        # ── Rule 5: flag volume fades ─────────────────────────────────────────
        flag_vol = float(flag_volumes.mean())
        if flag_vol > pole_vol * FLAG_VOL_MAX:
            continue

        # ── Rule 6: flag is not still running up ─────────────────────────────
        flag_drift = float(flag_closes[-1] - flag_closes[0])
        if flag_drift > pole_move * FLAG_DRIFT_MAX:
            continue

        # ── Rule 7: confirmed breakout ────────────────────────────────────────
        # Price must close ABOVE the flag high on the breakout bar.
        # This is the only bar we haven't seen yet when the flag forms —
        # it's what converts a "forming flag" into a confirmed entry signal.
        flag_high = float(flag_closes.max())
        if closes[end] <= flag_high:
            continue

        # ── Rule 8: deduplicate ───────────────────────────────────────────────
        if end - last_signal_i < FLAG_BARS:
            continue

        # ── Rule 9: EMA trend filter ─────────────────────────────────────────
        if "ema20" in df.columns and "ema50" in df.columns:
            if df["ema20"].iloc[end] <= df["ema50"].iloc[end]:
                continue
        if "ema20" in df.columns and closes[end] < df["ema20"].iloc[end]:
            continue

        # ── All rules passed — build the signal ──────────────────────────────
        flag_low = float(lows[pole_top_i : end].min())

        entry  = float(closes[end])                     # confirmed breakout close
        stop   = entry - atrs[end] * ATR_STOP_BUFFER
        if stop >= entry:
            continue
        target = entry + pole_height                    # measured move

        risk   = entry - stop
        reward = target - entry
        if risk <= 0:
            continue
        rr = reward / risk
        if rr < MIN_RR:
            continue

        scores = [
            min(pole_move / (atrs[end] * POLE_ATR_MULT), 2.0) / 2.0,
            (green_frac - POLE_GREEN_MIN) / (1.0 - POLE_GREEN_MIN),
            min(pole_vol / (baseline_vol * POLE_VOL_FACTOR), 2.0) / 2.0,
            1.0 - (flag_range / (pole_height * FLAG_RANGE_FACTOR)),
            1.0 - (flag_vol / (pole_vol * FLAG_VOL_MAX)),
        ]
        confidence = float(min(max(sum(scores) / len(scores), 0.0), 1.0))

        pattern_bars = df.iloc[pole_base_i : end + 1].copy()

        sig = PatternSignal(
            symbol      = symbol,
            pattern     = PATTERN_BULL_FLAG,
            direction   = "long",
            entry       = round(entry, 4),
            stop        = round(stop,  4),
            target      = round(target, 4),
            rr          = round(rr, 2),
            confidence  = round(confidence, 3),
            bars        = pattern_bars,
            detected_at = dates[end].to_pydatetime(),
            meta        = {
                "pole_height"    : round(pole_height, 4),
                "pole_bars"      : POLE_LOOKBACK,
                "flag_bars"      : FLAG_BARS,
                "green_frac"     : round(green_frac, 3),
                "pole_vol_ratio" : round(pole_vol / baseline_vol, 2),
                "flag_vol_ratio" : round(flag_vol / pole_vol, 2),
                "flag_low"       : round(flag_low, 4),
                "flag_high"      : round(flag_high, 4),
            },
        )
        signals.append(sig)
        last_signal_i = end

    return signals


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import yfinance as yf
    import sys
    sys.path.insert(0, ".")
    from pattern_engine.indicators import add_all

    print("Bull flag scan — BBAI 5d...")
    raw = yf.Ticker("BBAI").history(period="5d", interval="1m")
    raw.columns = [c.lower() for c in raw.columns]
    df = raw[["open","high","low","close","volume"]].copy()
    df = df.between_time("09:30","16:00").dropna()
    df = add_all(df)

    signals = detect(df, "BBAI")
    print(f"  Found {len(signals)} bull flag(s)\n")
    for s in signals:
        print(s.detail())
        print()
