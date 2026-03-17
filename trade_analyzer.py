"""
Trade data analyzer — reusable module.

Parses Schwab "Filled Orders" text and returns price-improvement + PnL metrics.
Handles the full Schwab paste (headers, Canceled Orders, Rolling Strategies, etc.)
and single-line pastes where rows are space-separated.
"""
import re


def _extract_filled_orders(raw_text: str) -> list[str]:
    """Pull out only the Filled Orders rows from a raw Schwab paste.

    Handles:
      - Full multi-section paste (Working Orders / Filled Orders / Canceled / Rolling)
      - Single-line paste where rows are separated by spaces instead of newlines
      - Bare filled-order rows with no headers
    """
    text = raw_text.strip()

    # --- 1. Extract just the Filled Orders section if other sections exist ---
    # Find "Filled Orders" marker and cut off at "Canceled Orders" / "Rolling Strategies"
    filled_start = re.search(r'Filled Orders', text, re.IGNORECASE)
    if filled_start:
        text = text[filled_start.end():]

    # Cut off at Canceled Orders or Rolling Strategies
    for stop_marker in ('Canceled Orders', 'Rolling Strategies'):
        stop = re.search(stop_marker, text, re.IGNORECASE)
        if stop:
            text = text[:stop.start()]

    # --- 2. Split into individual rows ---
    # If the text has real newlines, split normally
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]

    # If we only got 1-2 lines, the paste may be space-joined.
    # Re-split on the  "  ,," pattern that starts each data row.
    if len(lines) <= 2:
        # Split on ",," that starts a new trade record (preceded by whitespace or start)
        parts = re.split(r'\s+(?=,,)', text)
        lines = [p.strip() for p in parts if p.strip()]

    return lines


def analyze_trades(raw_text: str) -> dict:
    """Analyze pasted Schwab filled-orders text.

    Returns a dict with keys:
        total_fills, fills_by_symbol,
        pi_with, pi_without, pi_by_symbol, total_pi,
        pnl_by_symbol  (each: {pnl, shares_traded, pnl_per_share}),
        total_pnl, total_shares, total_pnl_per_share,
        trades  (list of parsed trade dicts for detailed view)
    """
    lines = _extract_filled_orders(raw_text)

    total_pi = 0.0
    total_fills = 0
    no_pi_count = 0

    pnl_by_symbol: dict[str, float] = {}
    shares_by_symbol: dict[str, int] = {}
    exit_shares_by_symbol: dict[str, int] = {}
    pi_by_symbol: dict[str, float] = {}
    fills_by_symbol: dict[str, int] = {}
    trades: list[dict] = []

    for line in lines:
        parts = line.split(',')
        if len(parts) < 15:
            continue

        side_raw = parts[4].strip()
        side = side_raw.upper()
        qty_str = parts[5].strip()
        pos_effect = parts[6].strip()
        symbol = parts[7].strip()
        price_str = parts[11].strip()
        pi_str = parts[13].strip()
        order_type = parts[14].strip() if len(parts) > 14 else ''
        exec_time = parts[2].strip()

        if side not in ('BUY', 'SELL', 'SELL SHORT', 'BUY TO COVER', 'SHORT', 'COVER'):
            continue

        try:
            qty = abs(int(qty_str))
            price = float(price_str)
        except (ValueError, TypeError):
            continue

        total_fills += 1

        # Price improvement
        if pi_str in ('-', ''):
            no_pi_count += 1
            pi_val = 0.0
        else:
            try:
                pi_val = float(pi_str)
            except (ValueError, TypeError):
                no_pi_count += 1
                pi_val = 0.0

        total_pi += pi_val

        # Per-symbol accumulators
        pi_by_symbol[symbol] = pi_by_symbol.get(symbol, 0.0) + pi_val
        fills_by_symbol[symbol] = fills_by_symbol.get(symbol, 0) + 1

        # PnL via cash flow
        pnl_by_symbol.setdefault(symbol, 0.0)
        shares_by_symbol.setdefault(symbol, 0)

        cash = qty * price
        if side in ('BUY', 'BUY TO COVER', 'COVER'):
            pnl_by_symbol[symbol] -= cash
        else:
            pnl_by_symbol[symbol] += cash
            exit_shares_by_symbol[symbol] = exit_shares_by_symbol.get(symbol, 0) + qty
        shares_by_symbol[symbol] += qty

        trades.append({
            'time': exec_time,
            'side': side,
            'qty': qty,
            'pos_effect': pos_effect,
            'symbol': symbol,
            'price': price,
            'pi': pi_val,
            'order_type': order_type,
        })

    # Build per-symbol summary list
    symbol_summaries = {}
    for sym in sorted(pnl_by_symbol):
        pnl = pnl_by_symbol[sym]
        shares = shares_by_symbol[sym]
        exit_shares = exit_shares_by_symbol.get(sym, 0)
        symbol_summaries[sym] = {
            'pnl': pnl,
            'shares_traded': shares,
            'pnl_per_share': pnl / exit_shares if exit_shares else 0,
            'fills': fills_by_symbol.get(sym, 0),
            'pi': pi_by_symbol.get(sym, 0.0),
        }

    total_pnl = sum(pnl_by_symbol.values())
    total_shares = sum(shares_by_symbol.values())
    total_exit_shares = sum(exit_shares_by_symbol.values())

    # Win rate: per-symbol, any non-zero PnL counts
    wins = sum(1 for info in symbol_summaries.values() if info['pnl'] > 0)
    losses = sum(1 for info in symbol_summaries.values() if info['pnl'] < 0)
    total_decisive = wins + losses
    win_rate = (wins / total_decisive * 100) if total_decisive > 0 else 0.0

    return {
        'total_fills': total_fills,
        'fills_by_symbol': fills_by_symbol,
        'pi_with': total_fills - no_pi_count,
        'pi_without': no_pi_count,
        'pi_by_symbol': pi_by_symbol,
        'total_pi': total_pi,
        'symbol_summaries': symbol_summaries,
        'total_pnl': total_pnl,
        'total_shares': total_shares,
        'total_pnl_per_share': total_pnl / total_exit_shares if total_exit_shares else 0,
        'trades': trades,
        'win_rate': win_rate,
        'wins': wins,
        'losses': losses,
    }
