"""
pattern_engine/signal.py

The PatternSignal dataclass.

Every detector (bull flag, ascending triangle, double bottom) outputs this same
shape.  Nothing else in the engine cares which detector fired — it just receives
a PatternSignal and knows exactly what to do with it.

Fields
------
symbol      : ticker, e.g. "BBAI"
pattern     : "bull_flag" | "asc_triangle" | "dbl_bottom"
direction   : "long" | "short"
entry       : price at which we would enter  (the breakout level)
stop        : price at which we are wrong  (cut the loss)
target      : measured-move price target  (take the profit)
rr          : reward / risk  =  (target - entry) / (entry - stop)
confidence  : 0.0 – 1.0  how cleanly all detection rules were met
              1.0 = every threshold hit perfectly
              0.5 = borderline pass on several rules
bars        : the OHLCV DataFrame for the bars that formed the pattern
              this is what gets sent to Claude
detected_at : datetime the signal fired
meta        : dict of pattern-specific extras
              bull_flag    → pole_height, pole_bars, flag_bars, green_frac, pole_vol_ratio
              asc_triangle → resistance, low1, low2, low3, n_touches
              dbl_bottom   → bottom1, bottom2, neckline, bounce_height, b2_vol_ratio
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd


# Valid pattern names — used for validation and display
PATTERN_BULL_FLAG    = "bull_flag"
PATTERN_ASC_TRIANGLE = "asc_triangle"
PATTERN_DBL_BOTTOM   = "dbl_bottom"
PATTERN_DBL_TOP      = "dbl_top"

VALID_PATTERNS   = {PATTERN_BULL_FLAG, PATTERN_ASC_TRIANGLE, PATTERN_DBL_BOTTOM, PATTERN_DBL_TOP}
VALID_DIRECTIONS = {"long", "short"}

# Human-readable names for printing
PATTERN_DISPLAY = {
    PATTERN_BULL_FLAG    : "Bull Flag",
    PATTERN_ASC_TRIANGLE : "Ascending Triangle",
    PATTERN_DBL_BOTTOM   : "Double Bottom",
    PATTERN_DBL_TOP      : "Double Top",
}


@dataclass
class PatternSignal:
    symbol      : str
    pattern     : str
    direction   : str
    entry       : float
    stop        : float
    target      : float
    rr          : float
    confidence  : float
    bars        : pd.DataFrame
    detected_at : datetime
    meta        : dict[str, Any] = field(default_factory=dict)

    # ── Validation ────────────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        if self.pattern not in VALID_PATTERNS:
            raise ValueError(
                f"Unknown pattern '{self.pattern}'. "
                f"Must be one of: {sorted(VALID_PATTERNS)}"
            )
        if self.direction not in VALID_DIRECTIONS:
            raise ValueError(
                f"Unknown direction '{self.direction}'. Must be 'long' or 'short'."
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be 0.0–1.0, got {self.confidence}")
        if self.bars.empty:
            raise ValueError("bars DataFrame cannot be empty.")

        # Make sure stop and target are on the correct sides of entry
        if self.direction == "long":
            if self.stop >= self.entry:
                raise ValueError(
                    f"Long signal: stop ({self.stop}) must be below entry ({self.entry})"
                )
            if self.target <= self.entry:
                raise ValueError(
                    f"Long signal: target ({self.target}) must be above entry ({self.entry})"
                )
        else:  # short
            if self.stop <= self.entry:
                raise ValueError(
                    f"Short signal: stop ({self.stop}) must be above entry ({self.entry})"
                )
            if self.target >= self.entry:
                raise ValueError(
                    f"Short signal: target ({self.target}) must be below entry ({self.entry})"
                )

    # ── Computed helpers ──────────────────────────────────────────────────────

    @property
    def risk(self) -> float:
        """Dollar risk per share from entry to stop."""
        return abs(self.entry - self.stop)

    @property
    def reward(self) -> float:
        """Dollar reward per share from entry to target."""
        return abs(self.target - self.entry)

    @property
    def pattern_name(self) -> str:
        """Human-readable pattern name."""
        return PATTERN_DISPLAY.get(self.pattern, self.pattern)

    @property
    def confidence_grade(self) -> str:
        """Letter grade for confidence score — easier to read at a glance."""
        if self.confidence >= 0.70:
            return "A"
        if self.confidence >= 0.50:
            return "B"
        if self.confidence >= 0.30:
            return "C"
        return "D"

    # ── Display ───────────────────────────────────────────────────────────────

    def summary(self) -> str:
        """
        One-line summary string.

        Example:
            [10:34]  Bull Flag  BBAI  LONG   Entry $3.450  Stop $3.380  Target $3.570  R/R 1:2.8  Confidence A
        """
        time_str = self.detected_at.strftime("%H:%M")
        return (
            f"[{time_str}]  {self.pattern_name:<20} {self.symbol:<6} {self.direction.upper():<6} "
            f"Entry ${self.entry:.3f}  Stop ${self.stop:.3f}  Target ${self.target:.3f}  "
            f"R/R 1:{self.rr:.1f}  Grade {self.confidence_grade}"
        )

    def detail(self) -> str:
        """
        Multi-line detail block — everything you need to evaluate the signal.

        Example:
            ╔══════════════════════════════════════════════════════════╗
            ║  Bull Flag  |  BBAI  |  LONG  |  Grade A                ║
            ╠══════════════════════════════════════════════════════════╣
            ║  Detected : 2026-03-31 12:43                            ║
            ║  Entry    : $3.450                                       ║
            ║  Stop     : $3.380   (risk  $0.070/share)               ║
            ║  Target   : $3.570   (reward $0.120/share)              ║
            ║  R/R      : 1 : 2.8                                      ║
            ║  Confidence: 0.87                                        ║
            ╠══════════════════════════════════════════════════════════╣
            ║  Pattern details:                                        ║
            ║    pole_height    : $0.120                               ║
            ║    green_frac     : 0.88                                 ║
            ║    pole_vol_ratio : 2.58x                                ║
            ╚══════════════════════════════════════════════════════════╝
        """
        width = 58
        border_top    = "╔" + "═" * width + "╗"
        border_mid    = "╠" + "═" * width + "╣"
        border_bottom = "╚" + "═" * width + "╝"

        def row(text: str) -> str:
            padded = f"  {text}"
            return "║" + padded.ljust(width) + "║"

        lines = [
            border_top,
            row(f"{self.pattern_name}  |  {self.symbol}  |  {self.direction.upper()}  |  Grade {self.confidence_grade}"),
            border_mid,
            row(f"Detected  : {self.detected_at.strftime('%Y-%m-%d %H:%M')}"),
            row(f"Entry     : ${self.entry:.3f}"),
            row(f"Stop      : ${self.stop:.3f}   (risk   ${self.risk:.3f}/share)"),
            row(f"Target    : ${self.target:.3f}   (reward ${self.reward:.3f}/share)"),
            row(f"R/R       : 1 : {self.rr:.1f}"),
            row(f"Confidence: {self.confidence:.2f}"),
            row(f"Bars      : {len(self.bars)} bars in pattern"),
        ]

        if self.meta:
            lines.append(border_mid)
            lines.append(row("Pattern details:"))
            for k, v in self.meta.items():
                if isinstance(v, float):
                    lines.append(row(f"  {k:<20} : {v:.4g}"))
                else:
                    lines.append(row(f"  {k:<20} : {v}"))

        lines.append(border_bottom)
        return "\n".join(lines)

    def __repr__(self) -> str:
        return self.summary()


# ── Standalone test ───────────────────────────────────────────────────────────
# Run:  .venv/bin/python3 pattern_engine/signal.py

if __name__ == "__main__":
    import numpy as np

    print("Testing PatternSignal...\n")

    # Build a minimal fake bars DataFrame
    n = 20
    fake_bars = pd.DataFrame({
        "open"   : np.linspace(3.30, 3.45, n),
        "high"   : np.linspace(3.32, 3.46, n),
        "low"    : np.linspace(3.28, 3.43, n),
        "close"  : np.linspace(3.31, 3.45, n),
        "volume" : np.random.randint(50_000, 300_000, n),
    })

    sig = PatternSignal(
        symbol      = "BBAI",
        pattern     = PATTERN_BULL_FLAG,
        direction   = "long",
        entry       = 3.435,
        stop        = 3.380,
        target      = 3.555,
        rr          = round((3.555 - 3.435) / (3.435 - 3.380), 1),
        confidence  = 0.87,
        bars        = fake_bars,
        detected_at = datetime(2026, 3, 31, 12, 43),
        meta        = {
            "pole_height"    : 0.120,
            "pole_bars"      : 9,
            "flag_bars"      : 12,
            "green_frac"     : 0.88,
            "pole_vol_ratio" : 2.58,
            "flag_vol_ratio" : 0.62,
        },
    )

    print("── summary() ──────────────────────────────────────────")
    print(sig.summary())
    print()
    print("── detail() ───────────────────────────────────────────")
    print(sig.detail())
    print()

    # Test validation catches bad inputs
    print("── Validation tests ───────────────────────────────────")
    try:
        bad = PatternSignal(
            symbol="X", pattern="bull_flag", direction="long",
            entry=3.43, stop=3.50,   # stop ABOVE entry on a long — should fail
            target=3.55, rr=2.0, confidence=0.8,
            bars=fake_bars, detected_at=datetime.now(),
        )
    except ValueError as e:
        print(f"  Caught expected error: {e}")

    try:
        bad = PatternSignal(
            symbol="X", pattern="made_up_pattern", direction="long",
            entry=3.43, stop=3.38, target=3.55, rr=2.0, confidence=0.8,
            bars=fake_bars, detected_at=datetime.now(),
        )
    except ValueError as e:
        print(f"  Caught expected error: {e}")

    print("\nAll tests passed.")
