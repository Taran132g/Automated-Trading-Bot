"""
pattern_engine/claude_filter.py

Sends a confirmed PatternSignal to Claude for a second opinion.

Claude receives:
  - The pattern type and direction
  - A compact table of the OHLCV bars that formed the pattern
  - The indicator values at detection time (ATR, EMA20, EMA50, VWAP)
  - The mechanically-computed entry / stop / target levels

Claude returns structured JSON:
  {
    "agree":     true | false,
    "reasoning": "one sentence",
    "stop":      float,
    "target":    float,
    "verdict":   "trade" | "skip"
  }

If Claude says "skip", the signal is discarded.
If Claude says "trade", the signal is returned with Claude's stop/target
replacing the mechanical ones (Claude's levels are more contextual).

Requires:  ANTHROPIC_API_KEY in environment or .env file.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from dotenv import load_dotenv

from pattern_engine.signal import PatternSignal

load_dotenv()
LOGGER = logging.getLogger("claude_filter")

MODEL   = "claude-haiku-4-5-20251001"   # fast + cheap for signal filtering
TIMEOUT = 20                             # seconds


def _build_prompt(sig: PatternSignal) -> str:
    """
    Build the prompt sent to Claude.

    We send a compact OHLCV table (last 30 bars max), the indicator
    snapshot at detection time, and the mechanical trade levels.
    Claude's job is to validate and optionally refine the levels.
    """
    # Compact bar table — last 30 bars of the pattern
    bars = sig.bars.tail(30).copy()
    bar_lines = []
    for ts, row in bars.iterrows():
        t   = ts.strftime("%H:%M") if hasattr(ts, "strftime") else str(ts)
        d   = "G" if row["close"] >= row["open"] else "R"
        bar_lines.append(
            f"  {t}  {d}  O:{row['open']:.3f} H:{row['high']:.3f} "
            f"L:{row['low']:.3f} C:{row['close']:.3f} V:{int(row['volume']):,}"
        )

    bar_table = "\n".join(bar_lines)

    # Indicator snapshot (last bar of pattern)
    last = bars.iloc[-1]
    atr_val  = last.get("atr",   "n/a")
    ema20    = last.get("ema20", "n/a")
    ema50    = last.get("ema50", "n/a")
    vwap     = last.get("vwap",  "n/a")

    # Pattern-specific context from meta
    meta_lines = "\n".join(
        f"  {k}: {v}" for k, v in sig.meta.items()
    )

    prompt = f"""You are a quantitative trading analyst reviewing a potential trade signal.

SIGNAL DETAILS
  Symbol    : {sig.symbol}
  Pattern   : {sig.pattern_name}
  Direction : {sig.direction.upper()}
  Detected  : {sig.detected_at.strftime("%Y-%m-%d %H:%M")}
  Confidence: {sig.confidence:.2f}  (mechanical rule score, 0-1)

MECHANICAL LEVELS
  Entry     : ${sig.entry:.3f}
  Stop      : ${sig.stop:.3f}   (risk  ${sig.risk:.3f}/share)
  Target    : ${sig.target:.3f}  (reward ${sig.reward:.3f}/share)
  R/R       : 1:{sig.rr:.1f}

INDICATORS AT DETECTION
  ATR       : {atr_val if isinstance(atr_val, str) else f'${float(atr_val):.4f}'}
  EMA20     : {ema20  if isinstance(ema20,  str) else f'${float(ema20):.3f}'}
  EMA50     : {ema50  if isinstance(ema50,  str) else f'${float(ema50):.3f}'}
  VWAP      : {vwap   if isinstance(vwap,   str) else f'${float(vwap):.3f}'}

PATTERN MEASUREMENTS
{meta_lines}

BAR DATA (last {len(bar_lines)} bars, G=green R=red)
{bar_table}

TASK
Analyse the bar data and pattern measurements above. Answer these questions:

1. Do you agree this is a valid {sig.pattern_name}?
2. Are the mechanical stop and target levels reasonable given the bar data?
3. Would you trade this signal right now?

Respond ONLY with valid JSON in exactly this format (no markdown, no explanation outside JSON):
{{
  "agree": true or false,
  "reasoning": "one concise sentence explaining your view",
  "stop": <your suggested stop price as a number>,
  "target": <your suggested target price as a number>,
  "verdict": "trade" or "skip"
}}"""

    return prompt


def ask_claude(sig: PatternSignal) -> Optional[PatternSignal]:
    """
    Send signal to Claude. Returns:
      - Updated PatternSignal with Claude's stop/target if verdict = "trade"
      - None if verdict = "skip" or API unavailable
    """
    try:
        import anthropic
    except ImportError:
        LOGGER.warning("anthropic package not installed — skipping Claude filter")
        return sig   # pass through without filtering

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        LOGGER.warning("ANTHROPIC_API_KEY not set — skipping Claude filter")
        return sig

    client = anthropic.Anthropic(api_key=api_key)
    prompt = _build_prompt(sig)

    try:
        response = client.messages.create(
            model      = MODEL,
            max_tokens = 300,
            messages   = [{"role": "user", "content": prompt}],
            timeout    = TIMEOUT,
        )
        raw = response.content[0].text.strip()
        LOGGER.debug("Claude raw response: %s", raw)

        # Strip markdown code fences if Claude added them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        result = json.loads(raw)

    except Exception as exc:
        LOGGER.error("Claude API error: %s — passing signal through", exc)
        return sig   # fail open: if Claude errors, don't block the signal

    # ── Parse response ────────────────────────────────────────────────────────
    verdict   = str(result.get("verdict", "skip")).lower()
    agree     = bool(result.get("agree", False))
    reasoning = str(result.get("reasoning", ""))
    c_stop    = result.get("stop",   sig.stop)
    c_target  = result.get("target", sig.target)

    LOGGER.info(
        "[%s] %s %s — Claude: %s  |  %s",
        sig.symbol, sig.pattern_name, sig.direction.upper(),
        verdict.upper(), reasoning,
    )

    if verdict != "trade":
        return None   # Claude says skip

    # Sanity-check Claude's levels before using them
    try:
        c_stop   = float(c_stop)
        c_target = float(c_target)
        if sig.direction == "long":
            assert c_stop < sig.entry, "Claude stop above entry on long"
            assert c_target > sig.entry, "Claude target below entry on long"
    except (AssertionError, ValueError, TypeError) as exc:
        LOGGER.warning("Claude returned bad levels (%s) — using mechanical ones", exc)
        c_stop   = sig.stop
        c_target = sig.target

    # Recompute R/R with Claude's levels
    risk   = sig.entry - c_stop
    reward = c_target  - sig.entry
    c_rr   = reward / risk if risk > 0 else 0.0

    # Store Claude's output in meta
    updated_meta = dict(sig.meta)
    updated_meta["claude_agree"]     = agree
    updated_meta["claude_reasoning"] = reasoning
    updated_meta["claude_verdict"]   = verdict
    updated_meta["claude_stop"]      = round(c_stop, 4)
    updated_meta["claude_target"]    = round(c_target, 4)

    return PatternSignal(
        symbol      = sig.symbol,
        pattern     = sig.pattern,
        direction   = sig.direction,
        entry       = sig.entry,
        stop        = round(c_stop, 4),
        target      = round(c_target, 4),
        rr          = round(c_rr, 2),
        confidence  = sig.confidence,
        bars        = sig.bars,
        detected_at = sig.detected_at,
        meta        = updated_meta,
    )
