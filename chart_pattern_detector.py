from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple, Iterable, Any
import numpy as np
import pandas as pd


REQUIRED_COLUMNS = ["open", "high", "low", "close"]
OPTIONAL_COLUMNS = ["volume"]


@dataclass
class PatternSignal:
    pattern: str
    direction: str  # bullish / bearish / neutral
    confidence: float  # 0.0 -> 1.0
    breakout: bool
    score: float
    start_idx: int
    end_idx: int
    breakout_idx: Optional[int]
    price_level: Optional[float]
    stop_level: Optional[float]
    target_level: Optional[float]
    meta: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DetectorConfig:
    pivot_left: int = 3
    pivot_right: int = 3
    min_pattern_bars: int = 20
    max_pattern_bars: int = 120
    price_tolerance_pct: float = 0.0125
    slope_tolerance_pct: float = 0.003
    breakout_buffer_pct: float = 0.002
    volume_confirm_multiplier: float = 1.15
    min_touches: int = 2
    lookback: int = 250
    atr_period: int = 14
    trend_ema_fast: int = 20
    trend_ema_slow: int = 50
    allow_overlap: bool = False
    min_range_width_pct: float = 0.005  # range_breakout: minimum range width as % of price (0.5%)


class ChartPatternDetector:
    def __init__(self, config: Optional[DetectorConfig] = None):
        self.cfg = config or DetectorConfig()

    def detect(self, df: pd.DataFrame) -> List[PatternSignal]:
        data = self._prepare(df)
        if len(data) < max(self.cfg.min_pattern_bars, self.cfg.atr_period + 5):
            return []

        pivots = self._find_pivots(data)
        signals: List[PatternSignal] = []

        signals.extend(self._detect_double_top(data, pivots))
        signals.extend(self._detect_double_bottom(data, pivots))
        signals.extend(self._detect_head_and_shoulders(data, pivots))
        signals.extend(self._detect_inverse_head_and_shoulders(data, pivots))
        signals.extend(self._detect_ascending_triangle(data, pivots))
        signals.extend(self._detect_descending_triangle(data, pivots))
        signals.extend(self._detect_symmetrical_triangle(data, pivots))
        signals.extend(self._detect_bull_flag(data))
        signals.extend(self._detect_bear_flag(data))
        signals.extend(self._detect_range_breakout(data, pivots))

        signals = self._deduplicate(signals)
        signals.sort(key=lambda x: (x.end_idx, x.score), reverse=True)
        return signals

    def latest(self, df: pd.DataFrame) -> List[PatternSignal]:
        all_signals = self.detect(df)
        if not all_signals:
            return []
        last_idx = len(df) - 1
        return [s for s in all_signals if s.end_idx >= last_idx - self.cfg.max_pattern_bars]

    def detect_as_dicts(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self.detect(df)]

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        data.columns = [c.lower() for c in data.columns]

        missing = [c for c in REQUIRED_COLUMNS if c not in data.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        if "volume" not in data.columns:
            data["volume"] = 0.0

        for c in ["open", "high", "low", "close", "volume"]:
            data[c] = pd.to_numeric(data[c], errors="coerce")
        data = data.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

        data["ema_fast"] = data["close"].ewm(span=self.cfg.trend_ema_fast, adjust=False).mean()
        data["ema_slow"] = data["close"].ewm(span=self.cfg.trend_ema_slow, adjust=False).mean()
        data["atr"] = self._atr(data, self.cfg.atr_period)
        data["avg_volume"] = data["volume"].rolling(20, min_periods=1).mean()
        return data

    def _atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        prev_close = df["close"].shift(1)
        tr = pd.concat(
            [
                (df["high"] - df["low"]).abs(),
                (df["high"] - prev_close).abs(),
                (df["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        return tr.rolling(period, min_periods=1).mean()

    def _find_pivots(self, df: pd.DataFrame) -> Dict[str, List[Tuple[int, float]]]:
        highs: List[Tuple[int, float]] = []
        lows: List[Tuple[int, float]] = []
        l = self.cfg.pivot_left
        r = self.cfg.pivot_right

        high_vals = df["high"].values
        low_vals = df["low"].values

        for i in range(l, len(df) - r):
            left_h = high_vals[i - l : i]
            right_h = high_vals[i + 1 : i + r + 1]
            if high_vals[i] >= left_h.max() and high_vals[i] >= right_h.max():
                highs.append((i, float(high_vals[i])))

            left_l = low_vals[i - l : i]
            right_l = low_vals[i + 1 : i + r + 1]
            if low_vals[i] <= left_l.min() and low_vals[i] <= right_l.min():
                lows.append((i, float(low_vals[i])))

        return {"highs": highs, "lows": lows}

    def _pct_diff(self, a: float, b: float) -> float:
        denom = max(abs(a), abs(b), 1e-9)
        return abs(a - b) / denom

    def _line_value(self, p1: Tuple[int, float], p2: Tuple[int, float], x: int) -> float:
        (x1, y1), (x2, y2) = p1, p2
        if x2 == x1:
            return y1
        return y1 + (y2 - y1) * ((x - x1) / (x2 - x1))

    def _slope(self, p1: Tuple[int, float], p2: Tuple[int, float]) -> float:
        (x1, y1), (x2, y2) = p1, p2
        if x2 == x1:
            return 0.0
        return (y2 - y1) / (x2 - x1)

    def _volume_confirmed(self, df: pd.DataFrame, idx: int) -> bool:
        if idx < 0 or idx >= len(df):
            return False
        vol = float(df.iloc[idx]["volume"])
        avg = float(df.iloc[idx]["avg_volume"])
        if avg <= 0:
            return True
        return vol >= avg * self.cfg.volume_confirm_multiplier

    def _breakout_up(self, df: pd.DataFrame, idx: int, level: float) -> bool:
        close = float(df.iloc[idx]["close"])
        return close > level * (1.0 + self.cfg.breakout_buffer_pct)

    def _breakout_down(self, df: pd.DataFrame, idx: int, level: float) -> bool:
        close = float(df.iloc[idx]["close"])
        return close < level * (1.0 - self.cfg.breakout_buffer_pct)

    def _deduplicate(self, signals: List[PatternSignal]) -> List[PatternSignal]:
        if not signals:
            return []

        kept: List[PatternSignal] = []
        occupied: List[Tuple[str, int, int]] = []

        for s in sorted(signals, key=lambda x: x.score, reverse=True):
            if self.cfg.allow_overlap:
                kept.append(s)
                continue

            overlap = False
            for p, a, b in occupied:
                if p == s.pattern and not (s.end_idx < a or s.start_idx > b):
                    overlap = True
                    break
            if not overlap:
                kept.append(s)
                occupied.append((s.pattern, s.start_idx, s.end_idx))

        return kept

    def _base_score(
        self,
        similarity_score: float,
        structure_score: float,
        breakout: bool,
        volume_ok: bool,
    ) -> Tuple[float, float]:
        confidence = (
            0.45 * similarity_score
            + 0.35 * structure_score
            + 0.10 * float(breakout)
            + 0.10 * float(volume_ok)
        )
        confidence = max(0.0, min(1.0, confidence))
        score = 100.0 * confidence
        return confidence, score

    def _prior_trend(self, df: pd.DataFrame, before_idx: int, lookback: int = 20) -> str:
        """Classify the trend in `lookback` bars immediately before `before_idx`.
        Uses EMA alignment + linear regression slope. Returns 'bullish', 'bearish', or 'neutral'."""
        start = max(0, before_idx - lookback)
        if before_idx - start < 5:
            return "neutral"
        seg = df.iloc[start:before_idx]
        last = seg.iloc[-1]
        ema_f = float(last["ema_fast"])
        ema_s = float(last["ema_slow"])
        ema_signal = "bullish" if ema_f > ema_s * 1.001 else ("bearish" if ema_f < ema_s * 0.999 else "neutral")
        closes = seg["close"].values.astype(float)
        x = np.arange(len(closes))
        slope = float(np.polyfit(x, closes, 1)[0])
        mid = float(np.mean(closes)) or 1e-9
        norm_slope = slope / mid
        lr_signal = "bullish" if norm_slope > 0.0001 else ("bearish" if norm_slope < -0.0001 else "neutral")
        if ema_signal == lr_signal and ema_signal != "neutral":
            return ema_signal
        return "neutral"

    def _detect_double_top(self, df: pd.DataFrame, pivots: Dict[str, List[Tuple[int, float]]]) -> List[PatternSignal]:
        res: List[PatternSignal] = []
        highs = pivots["highs"]
        lows = pivots["lows"]

        for i in range(len(highs) - 1):
            p1 = highs[i]
            p2 = highs[i + 1]
            bars = p2[0] - p1[0]
            if bars < 5 or bars > self.cfg.max_pattern_bars:
                continue

            if self._pct_diff(p1[1], p2[1]) > self.cfg.price_tolerance_pct:
                continue

            valley_candidates = [x for x in lows if p1[0] < x[0] < p2[0]]
            if not valley_candidates:
                continue
            valley = min(valley_candidates, key=lambda x: x[1])

            depth = (min(p1[1], p2[1]) - valley[1]) / max(min(p1[1], p2[1]), 1e-9)
            if depth < 0.01:
                continue

            breakout_idx = None
            for j in range(p2[0] + 1, len(df)):
                if self._breakout_down(df, j, valley[1]):
                    breakout_idx = j
                    break

            volume_ok = self._volume_confirmed(df, breakout_idx) if breakout_idx is not None else False
            similarity = 1.0 - min(1.0, self._pct_diff(p1[1], p2[1]) / max(self.cfg.price_tolerance_pct, 1e-9))
            structure = min(1.0, depth / 0.03)
            confidence, score = self._base_score(similarity, structure, breakout_idx is not None, volume_ok)

            prior_trend = self._prior_trend(df, p1[0])
            trend_factor = 1.0 if prior_trend == "bullish" else (0.85 if prior_trend == "neutral" else 0.6)
            confidence = max(0.0, min(1.0, confidence * trend_factor))
            score = 100.0 * confidence

            res.append(
                PatternSignal(
                    pattern="double_top",
                    direction="bearish",
                    confidence=confidence,
                    breakout=breakout_idx is not None,
                    score=score,
                    start_idx=p1[0],
                    end_idx=p2[0],
                    breakout_idx=breakout_idx,
                    price_level=valley[1],
                    stop_level=max(p1[1], p2[1]),
                    target_level=valley[1] - (max(p1[1], p2[1]) - valley[1]),
                    meta={
                        "left_peak": p1[1],
                        "right_peak": p2[1],
                        "valley": valley[1],
                        "depth_pct": depth,
                    },
                )
            )
        return res

    def _detect_double_bottom(self, df: pd.DataFrame, pivots: Dict[str, List[Tuple[int, float]]]) -> List[PatternSignal]:
        res: List[PatternSignal] = []
        highs = pivots["highs"]
        lows = pivots["lows"]

        for i in range(len(lows) - 1):
            p1 = lows[i]
            p2 = lows[i + 1]
            bars = p2[0] - p1[0]
            if bars < 5 or bars > self.cfg.max_pattern_bars:
                continue

            if self._pct_diff(p1[1], p2[1]) > self.cfg.price_tolerance_pct:
                continue

            peak_candidates = [x for x in highs if p1[0] < x[0] < p2[0]]
            if not peak_candidates:
                continue
            peak = max(peak_candidates, key=lambda x: x[1])

            rebound = (peak[1] - max(p1[1], p2[1])) / max(peak[1], 1e-9)
            if rebound < 0.01:
                continue

            breakout_idx = None
            for j in range(p2[0] + 1, len(df)):
                if self._breakout_up(df, j, peak[1]):
                    breakout_idx = j
                    break

            volume_ok = self._volume_confirmed(df, breakout_idx) if breakout_idx is not None else False
            similarity = 1.0 - min(1.0, self._pct_diff(p1[1], p2[1]) / max(self.cfg.price_tolerance_pct, 1e-9))
            structure = min(1.0, rebound / 0.03)
            confidence, score = self._base_score(similarity, structure, breakout_idx is not None, volume_ok)

            prior_trend = self._prior_trend(df, p1[0])
            trend_factor = 1.0 if prior_trend == "bearish" else (0.85 if prior_trend == "neutral" else 0.6)
            confidence = max(0.0, min(1.0, confidence * trend_factor))
            score = 100.0 * confidence

            res.append(
                PatternSignal(
                    pattern="double_bottom",
                    direction="bullish",
                    confidence=confidence,
                    breakout=breakout_idx is not None,
                    score=score,
                    start_idx=p1[0],
                    end_idx=p2[0],
                    breakout_idx=breakout_idx,
                    price_level=peak[1],
                    stop_level=min(p1[1], p2[1]),
                    target_level=peak[1] + (peak[1] - min(p1[1], p2[1])),
                    meta={
                        "left_trough": p1[1],
                        "right_trough": p2[1],
                        "peak": peak[1],
                        "rebound_pct": rebound,
                    },
                )
            )
        return res

    def _detect_head_and_shoulders(self, df: pd.DataFrame, pivots: Dict[str, List[Tuple[int, float]]]) -> List[PatternSignal]:
        res: List[PatternSignal] = []
        highs = pivots["highs"]
        lows = pivots["lows"]

        for i in range(len(highs) - 2):
            ls, h, rs = highs[i], highs[i + 1], highs[i + 2]
            if not (ls[0] < h[0] < rs[0]):
                continue
            width = rs[0] - ls[0]
            if width < 10 or width > self.cfg.max_pattern_bars:
                continue
            if not (h[1] > ls[1] and h[1] > rs[1]):
                continue
            if self._pct_diff(ls[1], rs[1]) > self.cfg.price_tolerance_pct * 1.5:
                continue

            valley1_candidates = [x for x in lows if ls[0] < x[0] < h[0]]
            valley2_candidates = [x for x in lows if h[0] < x[0] < rs[0]]
            if not valley1_candidates or not valley2_candidates:
                continue
            v1 = min(valley1_candidates, key=lambda x: x[1])
            v2 = min(valley2_candidates, key=lambda x: x[1])
            neckline = (v1[1] + v2[1]) / 2.0

            breakout_idx = None
            for j in range(rs[0] + 1, len(df)):
                line_j = self._line_value(v1, v2, j)
                if self._breakout_down(df, j, line_j):
                    breakout_idx = j
                    break

            head_height = (h[1] - neckline) / max(h[1], 1e-9)
            structure = min(1.0, head_height / 0.04)
            symmetry = 1.0 - min(1.0, self._pct_diff(ls[1], rs[1]) / max(self.cfg.price_tolerance_pct * 1.5, 1e-9))
            volume_ok = self._volume_confirmed(df, breakout_idx) if breakout_idx is not None else False
            confidence, score = self._base_score(symmetry, structure, breakout_idx is not None, volume_ok)

            prior_trend = self._prior_trend(df, ls[0])
            trend_factor = 1.0 if prior_trend == "bullish" else (0.85 if prior_trend == "neutral" else 0.6)
            confidence = max(0.0, min(1.0, confidence * trend_factor))
            score = 100.0 * confidence

            res.append(
                PatternSignal(
                    pattern="head_and_shoulders",
                    direction="bearish",
                    confidence=confidence,
                    breakout=breakout_idx is not None,
                    score=score,
                    start_idx=ls[0],
                    end_idx=rs[0],
                    breakout_idx=breakout_idx,
                    price_level=neckline,
                    stop_level=max(ls[1], rs[1]),
                    target_level=neckline - (h[1] - neckline),
                    meta={
                        "left_shoulder": ls[1],
                        "head": h[1],
                        "right_shoulder": rs[1],
                        "neckline_left": v1[1],
                        "neckline_right": v2[1],
                    },
                )
            )
        return res

    def _detect_inverse_head_and_shoulders(self, df: pd.DataFrame, pivots: Dict[str, List[Tuple[int, float]]]) -> List[PatternSignal]:
        res: List[PatternSignal] = []
        highs = pivots["highs"]
        lows = pivots["lows"]

        for i in range(len(lows) - 2):
            ls, h, rs = lows[i], lows[i + 1], lows[i + 2]
            if not (ls[0] < h[0] < rs[0]):
                continue
            width = rs[0] - ls[0]
            if width < 10 or width > self.cfg.max_pattern_bars:
                continue
            if not (h[1] < ls[1] and h[1] < rs[1]):
                continue
            if self._pct_diff(ls[1], rs[1]) > self.cfg.price_tolerance_pct * 1.5:
                continue

            peak1_candidates = [x for x in highs if ls[0] < x[0] < h[0]]
            peak2_candidates = [x for x in highs if h[0] < x[0] < rs[0]]
            if not peak1_candidates or not peak2_candidates:
                continue
            p1 = max(peak1_candidates, key=lambda x: x[1])
            p2 = max(peak2_candidates, key=lambda x: x[1])
            neckline = (p1[1] + p2[1]) / 2.0

            breakout_idx = None
            for j in range(rs[0] + 1, len(df)):
                line_j = self._line_value(p1, p2, j)
                if self._breakout_up(df, j, line_j):
                    breakout_idx = j
                    break

            head_depth = (neckline - h[1]) / max(neckline, 1e-9)
            structure = min(1.0, head_depth / 0.04)
            symmetry = 1.0 - min(1.0, self._pct_diff(ls[1], rs[1]) / max(self.cfg.price_tolerance_pct * 1.5, 1e-9))
            volume_ok = self._volume_confirmed(df, breakout_idx) if breakout_idx is not None else False
            confidence, score = self._base_score(symmetry, structure, breakout_idx is not None, volume_ok)

            prior_trend = self._prior_trend(df, ls[0])
            trend_factor = 1.0 if prior_trend == "bearish" else (0.85 if prior_trend == "neutral" else 0.6)
            confidence = max(0.0, min(1.0, confidence * trend_factor))
            score = 100.0 * confidence

            res.append(
                PatternSignal(
                    pattern="inverse_head_and_shoulders",
                    direction="bullish",
                    confidence=confidence,
                    breakout=breakout_idx is not None,
                    score=score,
                    start_idx=ls[0],
                    end_idx=rs[0],
                    breakout_idx=breakout_idx,
                    price_level=neckline,
                    stop_level=min(ls[1], rs[1]),
                    target_level=neckline + (neckline - h[1]),
                    meta={
                        "left_shoulder": ls[1],
                        "head": h[1],
                        "right_shoulder": rs[1],
                        "neckline_left": p1[1],
                        "neckline_right": p2[1],
                    },
                )
            )
        return res

    def _detect_ascending_triangle(self, df: pd.DataFrame, pivots: Dict[str, List[Tuple[int, float]]]) -> List[PatternSignal]:
        res: List[PatternSignal] = []
        highs = pivots["highs"]
        lows = pivots["lows"]

        for i in range(len(highs) - 1):
            h1, h2 = highs[i], highs[i + 1]
            if h2[0] - h1[0] < 10:
                continue
            if self._pct_diff(h1[1], h2[1]) > self.cfg.price_tolerance_pct:
                continue

            local_lows = [x for x in lows if h1[0] <= x[0] <= h2[0]]
            if len(local_lows) < 2:
                continue
            l1, l2 = local_lows[0], local_lows[-1]
            slope = self._slope(l1, l2)
            if slope <= 0:
                continue

            resistance = (h1[1] + h2[1]) / 2.0
            breakout_idx = None
            for j in range(h2[0] + 1, len(df)):
                if self._breakout_up(df, j, resistance):
                    breakout_idx = j
                    break

            compression = min(1.0, abs(slope) / max(resistance * self.cfg.slope_tolerance_pct, 1e-9))
            flatness = 1.0 - min(1.0, self._pct_diff(h1[1], h2[1]) / max(self.cfg.price_tolerance_pct, 1e-9))
            volume_ok = self._volume_confirmed(df, breakout_idx) if breakout_idx is not None else False
            confidence, score = self._base_score(flatness, compression, breakout_idx is not None, volume_ok)

            prior_trend = self._prior_trend(df, h1[0])
            trend_factor = 1.0 if prior_trend == "bullish" else (0.85 if prior_trend == "neutral" else 0.65)
            confidence = max(0.0, min(1.0, confidence * trend_factor))
            score = 100.0 * confidence

            res.append(
                PatternSignal(
                    pattern="ascending_triangle",
                    direction="bullish",
                    confidence=confidence,
                    breakout=breakout_idx is not None,
                    score=score,
                    start_idx=min(h1[0], l1[0]),
                    end_idx=max(h2[0], l2[0]),
                    breakout_idx=breakout_idx,
                    price_level=resistance,
                    stop_level=min(l1[1], l2[1]),
                    target_level=resistance + (resistance - min(l1[1], l2[1])),
                    meta={
                        "resistance_1": h1[1],
                        "resistance_2": h2[1],
                        "support_1": l1[1],
                        "support_2": l2[1],
                        "support_slope": slope,
                    },
                )
            )
        return res

    def _detect_descending_triangle(self, df: pd.DataFrame, pivots: Dict[str, List[Tuple[int, float]]]) -> List[PatternSignal]:
        res: List[PatternSignal] = []
        highs = pivots["highs"]
        lows = pivots["lows"]

        for i in range(len(lows) - 1):
            l1, l2 = lows[i], lows[i + 1]
            if l2[0] - l1[0] < 10:
                continue
            if self._pct_diff(l1[1], l2[1]) > self.cfg.price_tolerance_pct:
                continue

            local_highs = [x for x in highs if l1[0] <= x[0] <= l2[0]]
            if len(local_highs) < 2:
                continue
            h1, h2 = local_highs[0], local_highs[-1]
            slope = self._slope(h1, h2)
            if slope >= 0:
                continue

            support = (l1[1] + l2[1]) / 2.0
            breakout_idx = None
            for j in range(l2[0] + 1, len(df)):
                if self._breakout_down(df, j, support):
                    breakout_idx = j
                    break

            compression = min(1.0, abs(slope) / max(abs(support) * self.cfg.slope_tolerance_pct, 1e-9))
            flatness = 1.0 - min(1.0, self._pct_diff(l1[1], l2[1]) / max(self.cfg.price_tolerance_pct, 1e-9))
            volume_ok = self._volume_confirmed(df, breakout_idx) if breakout_idx is not None else False
            confidence, score = self._base_score(flatness, compression, breakout_idx is not None, volume_ok)

            prior_trend = self._prior_trend(df, l1[0])
            trend_factor = 1.0 if prior_trend == "bearish" else (0.85 if prior_trend == "neutral" else 0.65)
            confidence = max(0.0, min(1.0, confidence * trend_factor))
            score = 100.0 * confidence

            res.append(
                PatternSignal(
                    pattern="descending_triangle",
                    direction="bearish",
                    confidence=confidence,
                    breakout=breakout_idx is not None,
                    score=score,
                    start_idx=min(l1[0], h1[0]),
                    end_idx=max(l2[0], h2[0]),
                    breakout_idx=breakout_idx,
                    price_level=support,
                    stop_level=max(h1[1], h2[1]),
                    target_level=support - (max(h1[1], h2[1]) - support),
                    meta={
                        "support_1": l1[1],
                        "support_2": l2[1],
                        "resistance_1": h1[1],
                        "resistance_2": h2[1],
                        "resistance_slope": slope,
                    },
                )
            )
        return res

    def _detect_symmetrical_triangle(self, df: pd.DataFrame, pivots: Dict[str, List[Tuple[int, float]]]) -> List[PatternSignal]:
        res: List[PatternSignal] = []
        highs = pivots["highs"]
        lows = pivots["lows"]

        for i in range(min(len(highs), len(lows)) - 1):
            if i + 1 >= len(highs) or i + 1 >= len(lows):
                break
            h1, h2 = highs[i], highs[i + 1]
            l1, l2 = lows[i], lows[i + 1]

            if min(h2[0] - h1[0], l2[0] - l1[0]) < 8:
                continue

            high_slope = self._slope(h1, h2)
            low_slope = self._slope(l1, l2)
            if not (high_slope < 0 and low_slope > 0):
                continue

            start = min(h1[0], l1[0])
            end = max(h2[0], l2[0])
            if end - start < 12:
                continue

            breakout_idx = None
            breakout_dir = None
            for j in range(end + 1, len(df)):
                upper = self._line_value(h1, h2, j)
                lower = self._line_value(l1, l2, j)
                if self._breakout_up(df, j, upper):
                    breakout_idx = j
                    breakout_dir = "bullish"
                    break
                if self._breakout_down(df, j, lower):
                    breakout_idx = j
                    breakout_dir = "bearish"
                    break

            compression = min(
                1.0,
                (abs(high_slope) + abs(low_slope)) / max(df.iloc[end]["close"] * self.cfg.slope_tolerance_pct, 1e-9),
            )
            balance = 1.0
            volume_ok = self._volume_confirmed(df, breakout_idx) if breakout_idx is not None else False
            confidence, score = self._base_score(balance, compression, breakout_idx is not None, volume_ok)

            prior_trend = self._prior_trend(df, start)
            if breakout_dir is not None:
                contradicts = (
                    (breakout_dir == "bullish" and prior_trend == "bearish")
                    or (breakout_dir == "bearish" and prior_trend == "bullish")
                )
                if contradicts:
                    confidence = max(0.0, min(1.0, confidence * 0.7))
                    score = 100.0 * confidence

            stop_level = l2[1] if breakout_dir == "bullish" else h2[1]
            measured_height = max(h1[1], h2[1]) - min(l1[1], l2[1])
            target_level = None
            if breakout_idx is not None:
                breakout_price = float(df.iloc[breakout_idx]["close"])
                if breakout_dir == "bullish":
                    target_level = breakout_price + measured_height
                else:
                    target_level = breakout_price - measured_height

            res.append(
                PatternSignal(
                    pattern="symmetrical_triangle",
                    direction=breakout_dir or "neutral",
                    confidence=confidence,
                    breakout=breakout_idx is not None,
                    score=score,
                    start_idx=start,
                    end_idx=end,
                    breakout_idx=breakout_idx,
                    price_level=float(df.iloc[end]["close"]),
                    stop_level=stop_level,
                    target_level=target_level,
                    meta={
                        "high_slope": high_slope,
                        "low_slope": low_slope,
                        "upper_start": h1[1],
                        "upper_end": h2[1],
                        "lower_start": l1[1],
                        "lower_end": l2[1],
                    },
                )
            )
        return res

    def _detect_bull_flag(self, df: pd.DataFrame) -> List[PatternSignal]:
        res: List[PatternSignal] = []
        closes = df["close"].values
        highs = df["high"].values
        lows = df["low"].values

        for i in range(12, len(df) - 5):
            pole_start = max(0, i - 12)
            pole_return = (closes[i] - closes[pole_start]) / max(closes[pole_start], 1e-9)
            if pole_return < 0.03:
                continue

            flag_end = min(len(df) - 1, i + 8)
            seg_highs = highs[i : flag_end + 1]
            seg_lows = lows[i : flag_end + 1]
            x = np.arange(len(seg_highs))
            high_coef = np.polyfit(x, seg_highs, 1)
            low_coef = np.polyfit(x, seg_lows, 1)
            if not (high_coef[0] <= 0 and low_coef[0] <= 0):
                continue

            upper_now = high_coef[0] * (len(seg_highs) - 1) + high_coef[1]
            breakout_idx = None
            for j in range(flag_end + 1, len(df)):
                if self._breakout_up(df, j, upper_now):
                    breakout_idx = j
                    break

            structure = min(1.0, pole_return / 0.06)
            channel_quality = (
                1.0
                if abs(high_coef[0] - low_coef[0]) < max(df.iloc[i]["close"] * self.cfg.slope_tolerance_pct, 1e-9)
                else 0.7
            )
            volume_ok = self._volume_confirmed(df, breakout_idx) if breakout_idx is not None else False
            confidence, score = self._base_score(channel_quality, structure, breakout_idx is not None, volume_ok)

            prior_trend = self._prior_trend(df, pole_start)
            trend_factor = 1.0 if prior_trend == "bullish" else (0.85 if prior_trend == "neutral" else 0.7)
            confidence = max(0.0, min(1.0, confidence * trend_factor))
            score = 100.0 * confidence

            res.append(
                PatternSignal(
                    pattern="bull_flag",
                    direction="bullish",
                    confidence=confidence,
                    breakout=breakout_idx is not None,
                    score=score,
                    start_idx=pole_start,
                    end_idx=flag_end,
                    breakout_idx=breakout_idx,
                    price_level=upper_now,
                    stop_level=float(seg_lows.min()),
                    target_level=upper_now + (closes[i] - closes[pole_start]),
                    meta={
                        "pole_return_pct": pole_return,
                        "upper_slope": float(high_coef[0]),
                        "lower_slope": float(low_coef[0]),
                    },
                )
            )
        return res

    def _detect_bear_flag(self, df: pd.DataFrame) -> List[PatternSignal]:
        res: List[PatternSignal] = []
        closes = df["close"].values
        highs = df["high"].values
        lows = df["low"].values

        for i in range(12, len(df) - 5):
            pole_start = max(0, i - 12)
            pole_return = (closes[pole_start] - closes[i]) / max(closes[pole_start], 1e-9)
            if pole_return < 0.03:
                continue

            flag_end = min(len(df) - 1, i + 8)
            seg_highs = highs[i : flag_end + 1]
            seg_lows = lows[i : flag_end + 1]
            x = np.arange(len(seg_highs))
            high_coef = np.polyfit(x, seg_highs, 1)
            low_coef = np.polyfit(x, seg_lows, 1)
            parallel_ascending = high_coef[0] >= 0 and low_coef[0] >= 0
            converging_wedge = high_coef[0] < 0 and low_coef[0] > 0
            if not (parallel_ascending or converging_wedge):
                continue

            lower_now = low_coef[0] * (len(seg_lows) - 1) + low_coef[1]
            breakout_idx = None
            for j in range(flag_end + 1, len(df)):
                if self._breakout_down(df, j, lower_now):
                    breakout_idx = j
                    break

            structure = min(1.0, pole_return / 0.06)
            if converging_wedge:
                channel_quality = 0.85
            elif abs(high_coef[0] - low_coef[0]) < max(df.iloc[i]["close"] * self.cfg.slope_tolerance_pct, 1e-9):
                channel_quality = 1.0
            else:
                channel_quality = 0.7
            volume_ok = self._volume_confirmed(df, breakout_idx) if breakout_idx is not None else False
            confidence, score = self._base_score(channel_quality, structure, breakout_idx is not None, volume_ok)

            prior_trend = self._prior_trend(df, pole_start)
            trend_factor = 1.0 if prior_trend == "bearish" else (0.85 if prior_trend == "neutral" else 0.7)
            confidence = max(0.0, min(1.0, confidence * trend_factor))
            score = 100.0 * confidence

            res.append(
                PatternSignal(
                    pattern="bear_flag",
                    direction="bearish",
                    confidence=confidence,
                    breakout=breakout_idx is not None,
                    score=score,
                    start_idx=pole_start,
                    end_idx=flag_end,
                    breakout_idx=breakout_idx,
                    price_level=lower_now,
                    stop_level=float(seg_highs.max()),
                    target_level=lower_now - (closes[pole_start] - closes[i]),
                    meta={
                        "pole_return_pct": pole_return,
                        "upper_slope": float(high_coef[0]),
                        "lower_slope": float(low_coef[0]),
                    },
                )
            )
        return res

    def _detect_range_breakout(self, df: pd.DataFrame, pivots: Dict[str, List[Tuple[int, float]]]) -> List[PatternSignal]:
        res: List[PatternSignal] = []
        highs = pivots["highs"]
        lows = pivots["lows"]

        if len(highs) < 2 or len(lows) < 2:
            return res

        for start in range(0, len(df) - 20, 5):
            end = min(len(df) - 1, start + 25)
            seg = df.iloc[start : end + 1]
            resistance = float(seg["high"].quantile(0.92))
            support = float(seg["low"].quantile(0.08))
            width = (resistance - support) / max(seg["close"].mean(), 1e-9)
            if width > 0.04 or width < self.cfg.min_range_width_pct:
                continue

            pre_trend = self._prior_trend(df, start)
            breakout_idx = None
            direction = None
            for j in range(end + 1, len(df)):
                if self._breakout_up(df, j, resistance):
                    if pre_trend != "bearish":
                        breakout_idx = j
                        direction = "bullish"
                    break
                if self._breakout_down(df, j, support):
                    if pre_trend != "bullish":
                        breakout_idx = j
                        direction = "bearish"
                    break

            if breakout_idx is None:
                continue

            touches_high = int((seg["high"] >= resistance * (1.0 - self.cfg.price_tolerance_pct)).sum())
            touches_low = int((seg["low"] <= support * (1.0 + self.cfg.price_tolerance_pct)).sum())
            if touches_high < self.cfg.min_touches or touches_low < self.cfg.min_touches:
                continue

            structure = min(1.0, (touches_high + touches_low) / 8.0)
            similarity = 1.0 - min(1.0, width / 0.04)
            volume_ok = self._volume_confirmed(df, breakout_idx)
            confidence, score = self._base_score(similarity, structure, True, volume_ok)

            res.append(
                PatternSignal(
                    pattern="range_breakout",
                    direction=direction,
                    confidence=confidence,
                    breakout=True,
                    score=score,
                    start_idx=start,
                    end_idx=end,
                    breakout_idx=breakout_idx,
                    price_level=resistance if direction == "bullish" else support,
                    stop_level=support if direction == "bullish" else resistance,
                    target_level=(
                        resistance + (resistance - support)
                        if direction == "bullish"
                        else support - (resistance - support)
                    ),
                    meta={
                        "resistance": resistance,
                        "support": support,
                        "width_pct": width,
                        "touches_high": touches_high,
                        "touches_low": touches_low,
                    },
                )
            )
        return res


def build_pattern_event(signal: PatternSignal, symbol: Optional[str] = None, timeframe: Optional[str] = None) -> Dict[str, Any]:
    event = signal.to_dict()
    event["symbol"] = symbol
    event["timeframe"] = timeframe
    event["event_type"] = "chart_pattern"
    return event


def select_tradeable_patterns(
    signals: Iterable[PatternSignal],
    min_confidence: float = 0.60,
    require_breakout: bool = True,
    allowed_patterns: Optional[Iterable[str]] = None,
) -> List[PatternSignal]:
    allowed = set(allowed_patterns) if allowed_patterns is not None else None
    out: List[PatternSignal] = []
    for s in signals:
        if s.confidence < min_confidence:
            continue
        if require_breakout and not s.breakout:
            continue
        if allowed is not None and s.pattern not in allowed:
            continue
        out.append(s)
    out.sort(key=lambda x: (x.confidence, x.score), reverse=True)
    return out


def merge_pattern_bias(
    micro_direction: Optional[str],
    pattern_signals: Iterable[PatternSignal],
    min_confidence: float = 0.60,
) -> Dict[str, Any]:
    filtered = [s for s in pattern_signals if s.confidence >= min_confidence]
    bullish = sum(s.confidence for s in filtered if s.direction == "bullish")
    bearish = sum(s.confidence for s in filtered if s.direction == "bearish")

    chart_bias = "neutral"
    if bullish > bearish:
        chart_bias = "bullish"
    elif bearish > bullish:
        chart_bias = "bearish"

    aligned = False
    if micro_direction == "bid-heavy" and chart_bias == "bullish":
        aligned = True
    elif micro_direction == "ask-heavy" and chart_bias == "bearish":
        aligned = True

    return {
        "micro_direction": micro_direction,
        "chart_bias": chart_bias,
        "alignment": aligned,
        "bullish_score": bullish,
        "bearish_score": bearish,
        "pattern_count": len(filtered),
        "top_patterns": [s.to_dict() for s in sorted(filtered, key=lambda x: x.confidence, reverse=True)[:5]],
    }


class PatternEngine:
    def __init__(self, config: Optional[DetectorConfig] = None):
        self.detector = ChartPatternDetector(config)

    def analyze_symbol(
        self,
        symbol: str,
        df: pd.DataFrame,
        timeframe: str = "1min",
        min_confidence: float = 0.60,
        require_breakout: bool = False,
    ) -> Dict[str, Any]:
        signals = self.detector.latest(df)
        selected = select_tradeable_patterns(
            signals,
            min_confidence=min_confidence,
            require_breakout=require_breakout,
        )
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "signals": [build_pattern_event(s, symbol=symbol, timeframe=timeframe) for s in selected],
        }