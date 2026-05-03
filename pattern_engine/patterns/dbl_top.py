"""
pattern_engine/patterns/dbl_top.py

Double top detector  (inverse double bottom — SHORT setup).

Structure:
  TOP 1     — first high (price rallies and pulls back)
  NECKLINE  — middle trough between the two tops
  TOP 2     — second high near the same price as Top 1
  BREAKDOWN — price closes below the neckline

Key insight (mirror of SOXS double bottom):
  Top 2 volume should come back >= T2_VOL_MIN × Top 1 volume.
  Sellers return MORE aggressively the second time = real distribution.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import numpy as np
import pandas as pd

from pattern_engine.signal import PatternSignal, PATTERN_DBL_TOP


# ── Thresholds (calibrated for 15-min bars) ───────────────────────────────────
# 1 bar = 15 minutes.  1 trading day ≈ 26 bars.
# Patterns span hours to a few days on 15-min charts.
MIN_BARS          = 20      # 20 × 15min = 5 hours minimum
MAX_BARS          = 80      # 80 × 15min = 20 hours (~3.5 days)
TOP_TOL           = 0.030   # both tops must be within 3% of each other
MIN_BOUNCE        = 0.5     # neckline >= 0.5× ATR below the tops
T2_VOL_MIN        = 0.7     # top 2 volume >= 70% of top 1 volume
ATR_STOP_BUFFER   = 1.0     # stop = neckline + (ATR × this)  [above neckline for short]
MIN_RR            = 1.5


def detect(df: pd.DataFrame, symbol: str) -> List[PatternSignal]:
    """
    Scan df for double top patterns (bearish reversal → short).

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

            # Use bars BEFORE the current bar to establish pattern levels.
            # The current bar (end) is the breakdown confirmation bar —
            # its close must be at or below the neckline.
            sl_h = highs[start: end]       # exclude current bar
            sl_l = lows[start:  end]       # exclude current bar
            sl_v = volumes[start: end]     # exclude current bar
            t    = len(sl_h)
            if t < 6:
                continue

            # Split into thirds: top1 in first third, neckline trough in
            # middle, top2 in last third
            seg1_h = sl_h[: t // 3]
            seg2_l = sl_l[t // 3: 2 * t // 3]   # neckline from lows
            seg3_h = sl_h[2 * t // 3:]

            if len(seg1_h) == 0 or len(seg2_l) == 0 or len(seg3_h) == 0:
                continue

            t1 = float(seg1_h.max())
            t2 = float(seg3_h.max())

            # ── Rule 1: tops within tolerance ────────────────────────────────
            if abs(t1 - t2) / t1 > TOP_TOL:
                continue

            # ── Rule 2: neckline meaningfully below both tops ─────────────────
            neckline      = float(seg2_l.min())
            upper_top     = max(t1, t2)
            bounce_height = upper_top - neckline
            if bounce_height < atrs[end] * MIN_BOUNCE:
                continue

            # ── Rule 3: overall range must be meaningful ──────────────────────
            overall_range = float(sl_h.max() - sl_l.min())
            if overall_range < atrs[end] * 2.0:
                continue

            # ── Rule 4: top 2 volume >= top 1 volume ─────────────────────────
            t1_idx_local = int(np.argmax(seg1_h))
            t2_idx_local = int(2 * (t // 3) + np.argmax(seg3_h))
            vol_t1 = float(sl_v[t1_idx_local])
            vol_t2 = float(sl_v[t2_idx_local])
            if vol_t1 > 0 and vol_t2 < vol_t1 * T2_VOL_MIN:
                continue

            # ── Rule 5: confirmed neckline breakdown ──────────────────────────
            # Price must close AT or BELOW the neckline — not just approaching.
            if closes[end] > neckline:
                continue

            # ── Rule 6: deduplicate ───────────────────────────────────────────
            if end - last_signal_i < MIN_BARS:
                continue

            # ── Rule 6b: EMA filter — price below EMA20 ──────────────────────
            # Double top is a bearish reversal — only take it when price has
            # already broken below its short-term average (EMA20).
            if "ema20" in df.columns and closes[end] > df["ema20"].iloc[end] * 1.005:
                continue

            # ── Sanity check: both tops must be above current close ────────────
            if upper_top <= closes[end]:
                continue

            # ── Build trade levels ────────────────────────────────────────────
            # Entry is the neckline (breakdown level). Stop is placed 1× ATR
            # above the neckline. Target is the measured move down.
            target = neckline - bounce_height
            stop   = neckline + atrs[end] * ATR_STOP_BUFFER
            if stop <= neckline:             # guard: ATR=0 edge case
                stop = neckline * 1.02
            risk   = stop - neckline
            if risk <= 0:
                continue
            rr = (closes[end] - target) / risk
            if rr < MIN_RR:
                continue

            # ── Confidence ────────────────────────────────────────────────────
            top_symmetry    = 1.0 - abs(t1 - t2) / (t1 * TOP_TOL)
            vol_ratio_score = min(vol_t2 / max(vol_t1, 1), 2.0) / 2.0
            bounce_score    = min(bounce_height / (atrs[end] * MIN_BOUNCE), 2.0) / 2.0
            rr_score        = min(rr / MIN_RR, 2.0) / 2.0
            scores = [top_symmetry, vol_ratio_score, bounce_score, rr_score]
            confidence = float(min(max(sum(scores) / len(scores), 0.0), 1.0))

            pattern_bars = df.iloc[start: end + 1].copy()

            t2_vol_ratio = vol_t2 / max(vol_t1, 1)

            sig = PatternSignal(
                symbol      = symbol,
                pattern     = PATTERN_DBL_TOP,
                direction   = "short",
                entry       = round(neckline, 4),
                stop        = round(stop, 4),
                target      = round(target, 4),
                rr          = round(rr, 2),
                confidence  = round(confidence, 3),
                bars        = pattern_bars,
                detected_at = dates[end].to_pydatetime(),
                meta        = {
                    "top1"         : round(t1, 4),
                    "top2"         : round(t2, 4),
                    "neckline"     : round(neckline, 4),
                    "bounce_height": round(bounce_height, 4),
                    "t2_vol_ratio" : round(t2_vol_ratio, 2),
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

    print("Double top scan — AAPL 30d 15m...")
    raw = yf.Ticker("AAPL").history(period="30d", interval="15m")
    raw.columns = [c.lower() for c in raw.columns]
    df = raw[["open","high","low","close","volume"]].copy()
    if df.index.tz is not None:
        df.index = df.index.tz_convert("America/New_York").tz_localize(None)
    df = df.between_time("09:30", "15:45").dropna()
    df = add_all(df)

    signals = detect(df, "AAPL")
    print(f"  Found {len(signals)} double top(s)\n")
    for s in signals[:3]:
        print(s.detail())
        print()
