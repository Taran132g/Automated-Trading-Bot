"""
signal_parser.py

No Claude. Pure regex to extract entry and SL from signal channel messages.
If found, calculate bet size. Otherwise just forward the message as-is.
"""
import re
import logging

log = logging.getLogger("signal_parser")

# Patterns for entry price — order matters: most specific first
ENTRY_PATTERNS = [
    # "Entry Point: 0.9757" / "Entry Zone: 1.23"
    r'entry\s+(?:point|zone|price)[:\s@]*([0-9]+(?:[.,][0-9]+)?)',
    # "Entry: 1.23" / "Buy: 1.23" / "Open: 1.23" / "Price: 1.23"
    r'(?:entry|buy|open|price)[:\s@]+([0-9]+(?:[.,][0-9]+)?)',
    # "Enter at 1.23" / "Entering 1.23"
    r'(?:enter(?:ing)?)[:\s@]*([0-9]+(?:[.,][0-9]+)?)',
]

# Patterns for stop loss
SL_PATTERNS = [
    r'(?:sl|stop[\s\-]?loss|stoploss|s\.l\.)[:\s@]*([0-9]+(?:[.,][0-9]+)?)',
]

# Patterns for take profit on the SAME line as the keyword
_TP_INLINE = r'(?:tp\s*\d*|take[\s\-]?profit\s*\d*)[:\s@]*([0-9]+(?:[.,][0-9]+)?)'

# "Targets:" / "Target:" followed by numbers on subsequent lines
_TP_TARGETS_LABEL = r'(?:targets?)[:\s]*'


def _find_first(text: str, patterns: list[str]) -> float | None:
    t = text.lower()
    for pat in patterns:
        m = re.search(pat, t)
        if m:
            try:
                return float(m.group(1).replace(',', ''))
            except ValueError:
                continue
    return None


def _find_all(text: str, patterns: list[str]) -> list[float]:
    t = text.lower()
    results = []
    for pat in patterns:
        for m in re.finditer(pat, t):
            try:
                results.append(float(m.group(1).replace(',', '')))
            except ValueError:
                continue
    return results


def _find_tps(text: str) -> list[float]:
    """Extract TP levels from both inline and multi-line Targets: blocks."""
    t = text.lower()
    results = []

    # Inline: "TP1: 1.23" / "Take Profit: 1.23"
    for m in re.finditer(_TP_INLINE, t):
        try:
            results.append(float(m.group(1).replace(',', '')))
        except ValueError:
            pass

    # Multi-line targets block: "Targets:\n0.96\n0.95\n..."
    for block_m in re.finditer(_TP_TARGETS_LABEL, t):
        # Grab everything after the label until a non-number line
        rest = t[block_m.end():]
        for line in rest.split('\n'):
            line = line.strip()
            m = re.fullmatch(r'([0-9]+(?:[.,][0-9]+)?)', line)
            if m:
                try:
                    results.append(float(m.group(1).replace(',', '')))
                except ValueError:
                    pass
            elif line:  # non-empty non-number line ends the block
                break

    # Deduplicate preserving order
    seen: set[float] = set()
    deduped = []
    for v in results:
        if v not in seen:
            seen.add(v)
            deduped.append(v)
    return deduped


def extract_sizing(text: str, balance: float = 10000.0, risk_pct: float = 2.0) -> dict | None:
    """
    Try to extract entry + SL and compute bet sizing.
    Returns a sizing dict or None if entry/SL not found.
    """
    entry = _find_first(text, ENTRY_PATTERNS)
    sl = _find_first(text, SL_PATTERNS)
    tps = _find_tps(text)

    if not entry or not sl or entry == sl:
        return None

    sl_distance_pct = abs(entry - sl) / entry
    if sl_distance_pct == 0:
        return None

    risk_amount = balance * risk_pct / 100       # $200
    position_size = risk_amount / sl_distance_pct
    quantity = position_size / entry

    return {
        "entry": entry,
        "sl": sl,
        "sl_distance_pct": round(sl_distance_pct * 100, 2),
        "tps": tps,
        "risk_amount": round(risk_amount, 2),
        "position_size_usdt": round(position_size, 2),
        "quantity": round(quantity, 4),
        "balance": balance,
        "risk_pct": risk_pct,
    }


def build_sizing_footer(sizing: dict) -> str:
    """Build the bet size block appended to the forwarded message."""
    lines = [
        "",
        "─────────────────",
        "💰 *Your Bet (Yubit)*",
        f"Entry: `{sizing['entry']}` | SL: `{sizing['sl']}` ({sizing['sl_distance_pct']}% away)",
        f"Qty: `{sizing['quantity']} coins`",
        f"Position: `${sizing['position_size_usdt']:,.0f} USDT`",
        f"Risk: `${sizing['risk_amount']:,.0f}` ({sizing['risk_pct']}% of ${sizing['balance']:,.0f})",
    ]
    if sizing['tps']:
        lines.append("TPs: " + "  ".join(f"`{tp}`" for tp in sizing['tps']))
    return "\n".join(lines)
