"""
signal_parser.py

No Claude. Pure regex to extract entry and SL from signal channel messages.
If found, calculate bet size. Otherwise just forward the message as-is.
"""
import re
import logging

log = logging.getLogger("signal_parser")

# Patterns for entry price
ENTRY_PATTERNS = [
    r'(?:entry|buy|long|short|open|price)[:\s@]*([0-9]+(?:[.,][0-9]+)?)',
    r'(?:enter|entering)[:\s@]*([0-9]+(?:[.,][0-9]+)?)',
]

# Patterns for stop loss
SL_PATTERNS = [
    r'(?:sl|stop[\s\-]?loss|stop)[:\s@]*([0-9]+(?:[.,][0-9]+)?)',
    r'(?:stoploss|s\.l\.)[:\s@]*([0-9]+(?:[.,][0-9]+)?)',
]

# Patterns for take profit (optional, for display only)
TP_PATTERNS = [
    r'(?:tp\s*\d*|target\s*\d*|take[\s\-]?profit\s*\d*)[:\s@]*([0-9]+(?:[.,][0-9]+)?)',
]


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


def extract_sizing(text: str, balance: float = 10000.0, risk_pct: float = 2.0) -> dict | None:
    """
    Try to extract entry + SL and compute bet sizing.
    Returns a sizing dict or None if entry/SL not found.
    """
    entry = _find_first(text, ENTRY_PATTERNS)
    sl = _find_first(text, SL_PATTERNS)
    tps = _find_all(text, TP_PATTERNS)

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
