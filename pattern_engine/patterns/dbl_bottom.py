"""
pattern_engine/patterns/dbl_bottom.py

Double bottom detector.

Structure:
  BOTTOM 1  — first low (price falls and bounces)
  NECKLINE  — middle peak between the two bottoms
  BOTTOM 2  — second low near the same price as Bottom 1
  BREAKOUT  — price closes above the neckline

Key insight from SOXS April 1 walkthrough:
  Bottom 2 volume was 2.32× where Bottom 1 was 1.03×.
  Buyers came back MORE aggressively the second time.
  That is the real confirmation of the pattern.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import numpy as np
import pandas as pd

from pattern_engine.signal import PatternSignal, PATTERN_DBL_BOTTOM


# ── Thresholds (calibrated for 15-min bars) ───────────────────────────────────
# 1 bar = 15 minutes.  1 trading day ≈ 26 bars.
# Patterns span hours to a few days on 15-min charts.
MIN_BARS          = 20      # 20 × 15min = 5 hours minimum
MAX_BARS          = 80      # 80 × 15min = 20 hours (~3.5 days)
BOTTOM_TOL        = 0.030   # both bottoms within 3% — tight W shapes only
MIN_BOUNCE        = 0.5     # neckline >= 0.5× ATR above the bottoms
B2_VOL_MIN        = 0.7     # bottom 2 volume >= 70% of bottom 1 volume
NECKLINE_APPROACH = 0.030   # (unused — breakout confirmation is required)
ATR_STOP_BUFFER   = 1.0     # stop = neckline - (ATR × this); wider for intraday noise
MIN_RR            = 1.5


def detect(df: pd.DataFrame, symbol: str) -> List[PatternSignal]:
    """
    Scan df for double bottom patterns.

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
    dates   = df.index

    signals: List[PatternSignal] = []
    last_signal_i = -999

    for end in range(MAX_BARS, len(df)):
        for start in range(end - MAX_BARS, end - MIN_BARS + 1):
            n = end - start
            if n < MIN_BARS:
                continue

            # NOTE: intraday-only rule removed for 15-min timeframe.
            # Double bottoms on 15m charts routinely span 1-2 days.
            # Overnight gaps within the pattern are acceptable.

            # Use bars BEFORE the current bar to establish the pattern levels.
            # The current bar (end) is the breakout confirmation bar — its
            # close must be at or above the neckline to confirm the breakout.
            sl_l = lows[start:  end]       # exclude current bar
            sl_h = highs[start: end]       # exclude current bar
            sl_v = volumes[start: end]     # exclude current bar
            t    = len(sl_l)
            if t < 6:
                continue

            # Split into thirds: bottom1 in first third, neckline in middle,
            # bottom2 in last third
            seg1 = sl_l[: t // 3]
            seg2 = sl_h[t // 3: 2 * t // 3]   # neckline from highs
            seg3 = sl_l[2 * t // 3:]

            if len(seg1) == 0 or len(seg2) == 0 or len(seg3) == 0:
                continue

            b1 = float(seg1.min())
            b2 = float(seg3.min())

            # ── Rule 1: bottoms within tolerance ─────────────────────────────
            if abs(b1 - b2) / b1 > BOTTOM_TOL:
                continue

            # ── Rule 2: neckline meaningfully above both bottoms ──────────────
            neckline      = float(seg2.max())
            lower_bottom  = min(b1, b2)
            bounce_height = neckline - lower_bottom
            if bounce_height < atrs[end] * MIN_BOUNCE:
                continue

            # ── Rule 3: overall range must be meaningful ──────────────────────
            overall_range = float(sl_h.max() - sl_l.min())
            if overall_range < atrs[end] * 2.0:
                continue

            # ── Rule 4: bottom 2 volume >= bottom 1 volume ───────────────────
            b1_idx_local = int(np.argmin(seg1))
            b2_idx_local = int(2 * (t // 3) + np.argmin(seg3))
            vol_b1 = float(sl_v[b1_idx_local])
            vol_b2 = float(sl_v[b2_idx_local])
            if vol_b1 > 0 and vol_b2 < vol_b1 * B2_VOL_MIN:
                continue

            # ── Rule 5: confirmed neckline breakout ───────────────────────────
            # Price must close AT or ABOVE the neckline — not just approaching.
            # This is the confirmation that buyers have actually broken through.
            if closes[end] < neckline:
                continue

            # ── Rule 6: deduplicate ───────────────────────────────────────────
            if end - last_signal_i < MIN_BARS:
                continue

            # ── Rule 6b: EMA trend filter — EMA20 > EMA50 + price above EMA20 ─
            # Double bottom is a bullish reversal — only take it when the
            # broader trend is also turning bullish (EMA20 crossed above EMA50).
            if "ema20" in df.columns and "ema50" in df.columns:
                if df["ema20"].iloc[end] <= df["ema50"].iloc[end]:
                    continue
            if "ema20" in df.columns and closes[end] < df["ema20"].iloc[end] * 0.995:
                continue

            # ── Sanity check: both bottoms must be below current close ──────────
            # If lower_bottom >= closes[end] the window is degenerate — skip.
            if lower_bottom >= closes[end]:
                continue

            # ── Build trade levels ────────────────────────────────────────────
            # Entry is the neckline (breakout level). Stop is placed 1× ATR
            # below the neckline — tight enough for good R/R on daily bars.
            target = neckline + bounce_height
            stop   = neckline - atrs[end] * ATR_STOP_BUFFER
            if stop >= neckline:             # guard: ATR=0 edge case
                stop = neckline * 0.98
            risk   = neckline - stop
            if risk <= 0:
                continue
            rr = (target - closes[end]) / risk
            if rr < MIN_RR:
                continue

            # ── Confidence ────────────────────────────────────────────────────
            bottom_symmetry = 1.0 - abs(b1 - b2) / (b1 * BOTTOM_TOL)
            vol_ratio_score = min(vol_b2 / max(vol_b1, 1), 2.0) / 2.0
            bounce_score    = min(bounce_height / (atrs[end] * MIN_BOUNCE), 2.0) / 2.0
            rr_score        = min(rr / MIN_RR, 2.0) / 2.0
            scores = [bottom_symmetry, vol_ratio_score, bounce_score, rr_score]
            confidence = float(min(max(sum(scores) / len(scores), 0.0), 1.0))

            pattern_bars = df.iloc[start: end + 1].copy()

            b2_vol_ratio = vol_b2 / max(vol_b1, 1)

            sig = PatternSignal(
                symbol      = symbol,
                pattern     = PATTERN_DBL_BOTTOM,
                direction   = "long",
                entry       = round(neckline, 4),
                stop        = round(stop, 4),
                target      = round(target, 4),
                rr          = round(rr, 2),
                confidence  = round(confidence, 3),
                bars        = pattern_bars,
                detected_at = dates[end].to_pydatetime(),
                meta        = {
                    "bottom1"      : round(b1, 4),
                    "bottom2"      : round(b2, 4),
                    "neckline"     : round(neckline, 4),
                    "bounce_height": round(bounce_height, 4),
                    "b2_vol_ratio" : round(b2_vol_ratio, 2),
                    "n_bars"       : n,
                },
            )
            signals.append(sig)
            last_signal_i = end
            break

    return signals


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import yfinance as yf
    import sys
    sys.path.insert(0, ".")
    from pattern_engine.indicators import add_all

    print("Double bottom scan — SOXS 5d...")
    raw = yf.Ticker("SOXS").history(period="5d", interval="1m")
    raw.columns = [c.lower() for c in raw.columns]
    df = raw[["open","high","low","close","volume"]].copy()
    df = df.between_time("09:30","16:00").dropna()
    df = add_all(df)

    signals = detect(df, "SOXS")
    print(f"  Found {len(signals)} double bottom(s)\n")
    for s in signals[:3]:
        print(s.detail())
        print()
