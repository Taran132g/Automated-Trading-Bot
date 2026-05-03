"""
pattern_engine/indicators.py

Pure indicator functions.  Each takes a DataFrame and returns a new DataFrame
with extra columns added.  No state, no side effects.

All functions expect columns: open, high, low, close, volume (lowercase).

Usage:
    from pattern_engine.indicators import add_all
    df = add_all(df)
    # df now has: atr, ema20, ema50, vwap, vol_avg20
"""

from __future__ import annotations
import pandas as pd
import numpy as np


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Average True Range — how much the stock normally moves per bar.

    True Range = max of:
        (a) high - low                         current bar range
        (b) abs(high - previous close)         gap up into bar
        (c) abs(low  - previous close)         gap down into bar

    ATR = exponential moving average of True Range over `period` bars.

    High ATR = volatile / noisy → patterns unreliable → skip entry.
    Low ATR  = calm / smooth   → patterns reliable   → enter.
    """
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"]  - prev_close).abs(),
    ], axis=1).max(axis=1)
    df = df.copy()
    df["atr"] = tr.ewm(span=period, adjust=False).mean()
    return df


def add_ema(df: pd.DataFrame, span: int, col: str = "close") -> pd.DataFrame:
    """
    Exponential Moving Average.

    Gives more weight to recent bars than older ones — reacts faster than SMA.

    EMA20 (span=20): short-term trend.
        Price above EMA20 → short-term bullish bias.
    EMA50 (span=50): medium-term trend.
        EMA20 above EMA50 → uptrend confirmed.

    Rule we use:
        Only take LONG signals when close > EMA20.
        Only take SHORT signals when close < EMA20.
    """
    df = df.copy()
    col_name = f"ema{span}"
    df[col_name] = df[col].ewm(span=span, adjust=False).mean()
    return df


def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """
    Volume Weighted Average Price — resets each trading day.

    VWAP = sum(typical_price × volume) / sum(volume)
    where typical_price = (high + low + close) / 3

    VWAP is the average price paid, weighted by how many shares traded.
    Institutions use it as a benchmark.

    Price above VWAP → bullish bias (buyers paying above average).
    Price below VWAP → bearish bias (sellers accepting below average).

    Rule we use:
        Prefer LONG signals when close > VWAP.
        Prefer SHORT signals when close < VWAP.
    """
    df = df.copy()
    typical = (df["high"] + df["low"] + df["close"]) / 3

    # Group by date so VWAP resets each trading day
    dates = df.index.date
    vwap  = pd.Series(index=df.index, dtype=float)

    for day in pd.unique(dates):
        mask         = dates == day
        tp_day       = typical[mask]
        vol_day      = df.loc[mask, "volume"]
        cum_tp_vol   = (tp_day * vol_day).cumsum()
        cum_vol      = vol_day.cumsum()
        vwap[mask]   = cum_tp_vol / cum_vol.replace(0, np.nan)

    df["vwap"] = vwap
    return df


def add_vol_avg(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """
    Rolling average volume over `period` bars.

    Used to judge whether a breakout bar has above-average participation.
    vol_ratio = bar_volume / vol_avg  →  >1.3 = above average.
    """
    df = df.copy()
    df["vol_avg"] = df["volume"].rolling(period, min_periods=1).mean()
    return df


def add_all(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply every indicator in one call.
    Returns df with columns: atr, ema20, ema50, vwap, vol_avg.
    """
    df = add_atr(df)
    df = add_ema(df, span=20)
    df = add_ema(df, span=50)
    df = add_vwap(df)
    df = add_vol_avg(df)
    return df


# ── Standalone test ───────────────────────────────────────────────────────────
# Run:  .venv/bin/python3 pattern_engine/indicators.py

if __name__ == "__main__":
    import yfinance as yf

    print("Fetching BBAI 1-min bars to test indicators...")
    raw = yf.Ticker("BBAI").history(period="2d", interval="1m")
    raw.columns = [c.lower() for c in raw.columns]
    df = raw[["open", "high", "low", "close", "volume"]].copy()
    df = df.between_time("09:30", "16:00").dropna()

    df = add_all(df)

    print(f"  Bars loaded : {len(df)}")
    print(f"  Columns     : {list(df.columns)}")
    print()

    last = df.iloc[-1]
    print("Last bar values:")
    print(f"  close    : ${last['close']:.3f}")
    print(f"  atr      : ${last['atr']:.4f}  ({last['atr']/last['close']*100:.3f}% of price)")
    print(f"  ema20    : ${last['ema20']:.3f}  ({'above' if last['close'] > last['ema20'] else 'below'} price)")
    print(f"  ema50    : ${last['ema50']:.3f}  ({'above' if last['close'] > last['ema50'] else 'below'} price)")
    print(f"  vwap     : ${last['vwap']:.3f}  ({'above' if last['close'] > last['vwap'] else 'below'} price)")
    print(f"  vol_avg  : {last['vol_avg']:,.0f}")
    print(f"  vol_ratio: {last['volume']/last['vol_avg']:.2f}x  (last bar vs average)")

    trend = "UPTREND" if last["ema20"] > last["ema50"] else "DOWNTREND"
    vwap_bias = "BULLISH" if last["close"] > last["vwap"] else "BEARISH"
    print()
    print(f"  EMA trend  : {trend}  (EMA20 {'>' if last['ema20'] > last['ema50'] else '<'} EMA50)")
    print(f"  VWAP bias  : {vwap_bias}")
    print()
    print("indicators.py OK")
