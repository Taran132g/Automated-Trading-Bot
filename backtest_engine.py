"""Generic L2-imbalance scalping backtest — long &/or short, any symbol.

Faithful to the live scalper (grok.py + live_trader.py):
  - Signal = `alert==1` rows (sustained venue imbalance, Lee-Ready tape-filtered).
  - heavy_venues < 0  => ask-heavy  => SHORT entry / LONG exit.
    heavy_venues > 0  => bid-heavy  => LONG entry  / SHORT exit.
  - Flip-only, ONE position at a time. Direction restricted by `side`.
  - Latency applied to BOTH fills (fill price = market price L sec after signal).
  - Price improvement credited on the entry fill; fees per fill.

Outputs a results dict per (symbol, side) with a latency sweep, hold stats,
and a spread-sensitivity table. Writes backtest_report/data.json.
"""
import csv
import json
import os
import statistics as st
import datetime as dt
from bisect import bisect_left

PI_CENTS = 0.5          # cents/share price improvement (entry fill)
FEE_PER_1000 = 0.25     # $/1000 shares per fill
POSITION_SIZE = 100
MAX_FILL_GAP = 5.0
LATENCIES = [0.0, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
SPREADS = [0.0, 0.005, 0.01, 0.015, 0.02]   # extra round-trip crossing cost ($/sh)
WINDOW_DAYS = 14
CSV_PATH = "training_data.csv"
OUT_DIR = "backtest_report"

# ---- Worst-case live cost model ($/share) ----
# Full quoted spread paid vs mid on a round trip (these are penny-tick names;
# 2c is the wide end seen during the volatile moments the scalper trades).
SPREAD_WC = {"AAL": 0.02, "RIG": 0.02, "F": 0.02, "BBAI": 0.02, "SOXS": 0.02}
ADVERSE_WC = 0.005      # extra slippage: quote steps away before you cross
BORROW_WC = 0.002       # short-only locate / hard-to-borrow friction per share
LATENCY_WC = 2.0        # realistic reaction latency, not 0

FILL_WINDOW = 30.0      # s: how long a passive limit rests before you give up

# scenario -> dict(pi, spread_fn, adverse, borrow_short, latency, label)
SCENARIOS = {
    "optimistic": dict(pi=PI_CENTS / 100.0, spread=lambda s: 0.0, adverse=0.0,
                       borrow=0.0, latency=1.0, maker=False,
                       label="Mid fills + 0.5c PI (backtest-perfect)"),
    "worst_case": dict(pi=0.0, spread=lambda s: SPREAD_WC.get(s, 0.02),
                       adverse=ADVERSE_WC, borrow=BORROW_WC, latency=LATENCY_WC,
                       maker=False,
                       label="Full spread + slippage, no PI, +borrow (worst-case live)"),
    "maker": dict(pi=0.0, spread=lambda s: SPREAD_WC.get(s, 0.02), adverse=0.0,
                  borrow=BORROW_WC, latency=1.0, maker=True,
                  label="Passive limits: earn half-spread, but only fill on adverse paths"),
}


def _scan_cross(times, prices, t0, t1, target, up):
    """First price in (t0, t1] that crosses target. up=True -> price>=target."""
    i = bisect_left(times, t0)
    while i < len(times) and times[i] <= t1:
        p = prices[i]
        if (up and p >= target) or (not up and p <= target):
            return p, times[i]
        i += 1
    return None


def simulate_maker(rows, side, latency, symbol="", spread_rt=0.02, borrow=0.0):
    """Passive-limit fills reconstructed from the price path.

    Short entry posts a SELL at the offer (mid + h); it only fills if price
    trades UP to it within FILL_WINDOW -> you miss clean drops (negative
    selection) but capture +h when filled. Short exit posts a BUY at the bid
    (mid - h); if it doesn't fill in the window you cross (market cover) at the
    window-end price. Long side mirrors. h = half the quoted spread.
    """
    times = [r[0] for r in rows]
    prices = [r[1] for r in rows]
    h = spread_rt / 2.0
    fee = FEE_PER_1000 / 1000.0 * 2
    enter_short = side == "short"
    borrow_cost = borrow if enter_short else 0.0

    in_pos = False
    entry_fill = entry_ts = 0.0
    nets, holds = [], []
    signals = fills = 0

    for ts, price, alert, hv in rows:
        if alert != 1:
            continue
        is_ask = hv < 0
        is_bid = hv > 0
        if not in_pos:
            if (is_ask if enter_short else is_bid):
                signals += 1
                t0 = ts + latency
                mid = _price_at(times, prices, t0)
                if mid is None:
                    continue
                if enter_short:                       # SELL limit at offer
                    target = mid + h
                    cross = _scan_cross(times, prices, t0, t0 + FILL_WINDOW, target, up=True)
                else:                                 # BUY limit at bid
                    target = mid - h
                    cross = _scan_cross(times, prices, t0, t0 + FILL_WINDOW, target, up=False)
                if cross is None:
                    continue                          # passive entry never filled -> miss
                entry_fill, entry_ts, in_pos = target, cross[1], True
                fills += 1
        else:
            if (is_bid if enter_short else is_ask):
                t0 = ts + latency
                mid = _price_at(times, prices, t0)
                if mid is None:
                    continue
                if enter_short:                       # BUY-to-cover limit at bid
                    target = mid - h
                    cross = _scan_cross(times, prices, t0, t0 + FILL_WINDOW, target, up=False)
                else:                                 # SELL limit at offer
                    target = mid + h
                    cross = _scan_cross(times, prices, t0, t0 + FILL_WINDOW, target, up=True)
                if cross is not None:
                    exit_fill = target                # passive exit filled (earn h)
                else:                                 # didn't fill -> cross the spread
                    fallback = _price_at(times, prices, t0 + FILL_WINDOW)
                    if fallback is None:
                        continue
                    exit_fill = (fallback - h) if enter_short else (fallback + h)
                gross = (entry_fill - exit_fill) if enter_short else (exit_fill - entry_fill)
                nets.append(gross - fee - borrow_cost)
                holds.append(t0 - entry_ts)
                in_pos = False
    fill_rate = (fills / signals * 100.0) if signals else 0.0
    return nets, holds, fill_rate


def load_symbol(symbol):
    rows = []
    with open(CSV_PATH) as f:
        for r in csv.DictReader(f):
            if r["symbol"] != symbol:
                continue
            try:
                rows.append((float(r["timestamp"]), float(r["price"]),
                             int(float(r["alert"])), float(r["heavy_venues"])))
            except (ValueError, TypeError):
                continue
    rows.sort(key=lambda x: x[0])
    if not rows:
        return rows
    cut = rows[-1][0] - WINDOW_DAYS * 86400
    return [r for r in rows if r[0] >= cut]


def _price_at(times, prices, t):
    i = bisect_left(times, t)
    if i >= len(times) or times[i] - t > MAX_FILL_GAP:
        return None
    return prices[i]


def simulate(rows, side, latency, symbol="", spread_rt=0.0, pi=None,
             adverse=0.0, borrow=0.0):
    """side='short' or 'long'. Returns (trades_net_per_share[], holds[]).

    pi defaults to the global PI credit; pass 0.0 to disable (market orders).
    spread_rt/adverse/borrow are extra $/share round-trip frictions.
    """
    times = [r[0] for r in rows]
    prices = [r[1] for r in rows]
    if pi is None:
        pi = PI_CENTS / 100.0
    fee = FEE_PER_1000 / 1000.0 * 2

    # entry trigger sign: short enters on ask-heavy(hv<0); long on bid-heavy(hv>0)
    enter_short = side == "short"
    borrow_cost = borrow if enter_short else 0.0
    in_pos = False
    entry_fill = entry_ts = 0.0
    nets, holds = [], []

    for ts, price, alert, hv in rows:
        if alert != 1:
            continue
        is_ask = hv < 0
        is_bid = hv > 0
        if not in_pos:
            trigger = is_ask if enter_short else is_bid
            if trigger:
                f = _price_at(times, prices, ts + latency)
                if f is None:
                    continue
                entry_fill, entry_ts, in_pos = f, ts, True
        else:
            exit_trig = is_bid if enter_short else is_ask
            if exit_trig:
                f = _price_at(times, prices, ts + latency)
                if f is None:
                    continue
                gross = (entry_fill - f) if enter_short else (f - entry_fill)
                net = gross + pi - fee - spread_rt - adverse - borrow_cost
                nets.append(net)
                holds.append(ts - entry_ts)
                in_pos = False
    return nets, holds


def summarize(rows, symbol, side, scenario):
    cfg = SCENARIOS[scenario]
    sp = cfg["spread"](symbol)
    is_maker = cfg.get("maker", False)
    fee_rt = FEE_PER_1000 / 1000.0 * 2

    def run_sim(L):
        if is_maker:
            nets, holds, _ = simulate_maker(rows, side, L, symbol=symbol,
                                            spread_rt=sp, borrow=cfg["borrow"])
            return nets, holds
        return simulate(rows, side, L, symbol=symbol, spread_rt=sp, pi=cfg["pi"],
                        adverse=cfg["adverse"], borrow=cfg["borrow"])

    sweep = []
    for L in LATENCIES:
        nets, holds = run_sim(L)
        if not nets:
            continue
        n = len(nets)
        sweep.append({
            "latency": L,
            "trades": n,
            "win_rate": round(sum(1 for x in nets if x > 0) / n * 100, 1),
            "avg_net_ps": round(sum(nets) / n, 5),
            "avg_net_trade": round(sum(nets) / n * POSITION_SIZE, 2),
            "net_total": round(sum(nets) * POSITION_SIZE, 2),
        })
    Lh = cfg["latency"]
    nets_h, holds_h = run_sim(Lh)
    # pure directional edge (mid fills, no costs) for reference
    gross_h, _ = simulate(rows, side, Lh, symbol=symbol, spread_rt=0.0, pi=0.0,
                          adverse=0.0, borrow=0.0)
    gross_edge = (st.mean(gross_h) + fee_rt) if gross_h else None
    borrow_s = cfg["borrow"] if side == "short" else 0.0
    if is_maker:
        _, _, fill_rate = simulate_maker(rows, side, Lh, symbol=symbol,
                                         spread_rt=sp, borrow=cfg["borrow"])
        costs = {
            "spread": round(-sp / 2, 4),     # credit: earn ~half-spread per leg
            "adverse": 0.0,
            "borrow": round(borrow_s, 4),
            "fees": round(fee_rt, 4),
            "pi_credit": 0.0,
            "fill_rate": round(fill_rate, 1),
            "total_friction": round(fee_rt + borrow_s - sp / 2, 4),
        }
    else:
        costs = {
            "spread": round(sp, 4),
            "adverse": round(cfg["adverse"], 4),
            "borrow": round(borrow_s, 4),
            "fees": round(fee_rt, 4),
            "pi_credit": round(cfg["pi"], 4),
            "fill_rate": 100.0,
            "total_friction": round(sp + cfg["adverse"] + borrow_s + fee_rt - cfg["pi"], 4),
        }
    be = None
    for i in range(1, len(sweep)):
        a, b = sweep[i - 1], sweep[i]
        if a["net_total"] > 0 >= b["net_total"]:
            f = a["net_total"] / (a["net_total"] - b["net_total"])
            be = round(a["latency"] + f * (b["latency"] - a["latency"]), 2)
            break
    days = sorted({dt.datetime.fromtimestamp(r[0]).date().isoformat() for r in rows})
    headline = next((s for s in sweep if s["latency"] == Lh), sweep[0]) if sweep else None
    return {
        "symbol": symbol,
        "side": side,
        "scenario": scenario,
        "scenario_label": cfg["label"],
        "headline_latency": Lh,
        "window": [days[0], days[-1]] if days else [None, None],
        "trading_days": len(days),
        "ticks": len(rows),
        "avg_hold_s": round(st.mean(holds_h), 1) if holds_h else None,
        "median_hold_s": round(st.median(holds_h), 1) if holds_h else None,
        "gross_edge_ps": round(gross_edge, 5) if gross_edge is not None else None,
        "breakeven_latency_s": be,
        "costs": costs,
        "headline": headline,
        "sweep": sweep,
    }


def run(symbols, sides=("short", "long"),
        scenarios=("optimistic", "worst_case", "maker")):
    results = []
    for sym in symbols:
        rows = load_symbol(sym)
        if len(rows) < 100:
            print(f"  [skip] {sym}: only {len(rows)} ticks")
            continue
        for side in sides:
            for sc in scenarios:
                r = summarize(rows, sym, side, sc)
                results.append(r)
                h = r["headline"]
                if h:
                    flag = "✓" if h["net_total"] >= 0 else "✗"
                    print(f"  {sym:>5} {side:<5} [{sc:<10}]: {h['trades']:>4} tr | "
                          f"win {h['win_rate']:>5.1f}% | ${h['avg_net_trade']:>+6.2f}/tr | "
                          f"net ${h['net_total']:>+9.2f} {flag}")
    return results


def write_report(results):
    os.makedirs(OUT_DIR, exist_ok=True)
    meta = {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "position_size": POSITION_SIZE,
        "pi_cents": PI_CENTS,
        "fee_per_1000": FEE_PER_1000,
        "window_days": WINDOW_DAYS,
        "results": results,
    }
    with open(os.path.join(OUT_DIR, "data.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"\nWrote {OUT_DIR}/data.json ({len(results)} symbol/side runs)")


if __name__ == "__main__":
    import sys
    syms = sys.argv[1:] or ["AAL", "RIG"]
    print(f"Backtesting {syms} (long & short)...")
    res = run(syms)
    write_report(res)
