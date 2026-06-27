"""Short-only L2-imbalance scalping backtest with latency sweep.

Faithful to the live scalper:
  - Signal = `alert==1` rows in training_data.csv (sustained venue imbalance,
    Lee-Ready tape-filtered — already baked into the alert flag).
  - Direction: heavy_venues < 0  => ask-heavy => SHORT entry.
               heavy_venues > 0  => bid-heavy => COVER (exit a short).
  - Flip-only, ONE position at a time. LONG side disabled (shorts only).
    Enter short on an ask-heavy alert while flat; cover on the next
    bid-heavy alert. Holding time is purely signal-driven (real behavior).

Latency is applied to BOTH fills: the fill price is the market price
`L` seconds after the signal timestamp (we react late, so the move has
already partly happened).

Assumptions (per request / repo):
  - price_improvement = 0.5 cents/share, applied to the ENTRY fill only
    (the limit side we control). Matches Schwab PI of ~$0.005/sh observed
    in calc_pi.py.  Toggle PI_PER_FILL to apply on both fills.
  - fees = $0.25 / 1000 shares per fill (calculate_fees.py).
  - position size = 100 shares (live_position_size).
"""
import csv
import datetime as dt
from bisect import bisect_left

SYMBOL = "AAL"
POSITION_SIZE = 100
PI_CENTS = 0.5          # cents/share price improvement
PI_PER_FILL = False     # False = entry only; True = both fills
FEE_PER_1000 = 0.25     # $/1000 shares per fill
MAX_FILL_GAP = 5.0      # s: if no tick within this of (signal+L), skip trade
LATENCIES = [0.0, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
WINDOW_DAYS = 14        # most recent N days of available data


def load():
    rows = []
    with open("training_data.csv") as f:
        for r in csv.DictReader(f):
            if r["symbol"] != SYMBOL:
                continue
            try:
                ts = float(r["timestamp"])
                price = float(r["price"])
                alert = int(float(r["alert"]))
                hv = float(r["heavy_venues"])
            except (ValueError, TypeError):
                continue
            rows.append((ts, price, alert, hv))
    rows.sort(key=lambda x: x[0])
    return rows


def price_at(times, prices, t):
    """Market price at-or-after time t (first tick >= t), within MAX_FILL_GAP."""
    i = bisect_left(times, t)
    if i >= len(times):
        return None
    if times[i] - t > MAX_FILL_GAP:
        return None
    return prices[i]


def run(rows, latency):
    times = [r[0] for r in rows]
    prices = [r[1] for r in rows]
    pi = PI_CENTS / 100.0
    fee_share = FEE_PER_1000 / 1000.0

    in_short = False
    entry_fill = 0.0
    trades = []  # (entry_fill, exit_fill, pnl_per_share_net)

    for ts, price, alert, hv in rows:
        if alert != 1:
            continue
        if hv < 0 and not in_short:                 # ask-heavy -> SHORT
            f = price_at(times, prices, ts + latency)
            if f is None:
                continue
            entry_fill = f
            in_short = True
        elif hv > 0 and in_short:                   # bid-heavy -> COVER
            f = price_at(times, prices, ts + latency)
            if f is None:
                continue
            exit_fill = f
            # short pnl/share = sold at entry_fill, bought back at exit_fill
            gross = entry_fill - exit_fill
            pi_total = pi * (2 if PI_PER_FILL else 1)
            fees = fee_share * 2
            net = gross + pi_total - fees
            trades.append((entry_fill, exit_fill, net))
            in_short = False

    n = len(trades)
    if n == 0:
        return None
    net_ps = [t[2] for t in trades]
    wins = sum(1 for x in net_ps if x > 0)
    gross_ps = [t[0] - t[1] for t in trades]
    total_net = sum(net_ps) * POSITION_SIZE
    total_gross = sum(gross_ps) * POSITION_SIZE
    return {
        "latency": latency,
        "trades": n,
        "win_rate": wins / n * 100,
        "avg_net_ps": sum(net_ps) / n,           # $/share
        "avg_net_trade": total_net / n,          # $/trade @ pos size
        "total_net": total_net,
        "total_gross": total_gross,
    }


def main():
    rows = load()
    last = rows[-1][0]
    cut = last - WINDOW_DAYS * 86400
    rows = [r for r in rows if r[0] >= cut]
    d0 = dt.datetime.fromtimestamp(rows[0][0]).date()
    d1 = dt.datetime.fromtimestamp(rows[-1][0]).date()
    days = sorted({dt.datetime.fromtimestamp(r[0]).date() for r in rows})
    print(f"Symbol: {SYMBOL}  | SHORTS ONLY | window {d0} -> {d1} "
          f"({len(days)} trading days, {len(rows):,} ticks)")
    print(f"PI={PI_CENTS}c/share ({'both fills' if PI_PER_FILL else 'entry only'}), "
          f"fees=${FEE_PER_1000}/1k/fill, size={POSITION_SIZE}sh\n")
    print(f"{'Latency':>8} | {'Trades':>6} | {'Win%':>6} | "
          f"{'$/share':>9} | {'$/trade':>9} | {'GrossTot':>10} | {'NetTot':>10}")
    print("-" * 78)
    prev_net = None
    breakeven = None
    for L in LATENCIES:
        s = run(rows, L)
        if not s:
            continue
        print(f"{L:>7.2f}s | {s['trades']:>6} | {s['win_rate']:>5.1f}% | "
              f"{s['avg_net_ps']:>+9.4f} | {s['avg_net_trade']:>+9.2f} | "
              f"{s['total_gross']:>+10.2f} | {s['total_net']:>+10.2f}")
        if prev_net is not None and prev_net > 0 >= s["total_net"] and breakeven is None:
            # linear interp for break-even latency
            f = prev_net / (prev_net - s["total_net"])
            breakeven = prev_L + f * (L - prev_L)
        prev_net, prev_L = s["total_net"], L
    print("-" * 78)
    if breakeven is not None:
        print(f"\n>> Break-even latency (net PnL crosses 0): ~{breakeven:.2f}s")
    else:
        print("\n>> Net PnL did not cross zero across the swept latency range.")


if __name__ == "__main__":
    main()
