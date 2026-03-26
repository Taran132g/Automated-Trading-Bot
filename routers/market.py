"""Market data router — fetches live quotes from Yahoo Finance (60s cache)."""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from fastapi import APIRouter

router = APIRouter()

# Top ticker: BTC, S&P 500, GLD, SLV, DXY, WTI Oil, MAG7
TOP_SYMBOLS = [
    ("BTC-USD",  "BTC"),
    ("^GSPC",    "S&P500"),
    ("GLD",      "GLD"),
    ("SLV",      "SLV"),
    ("DX-Y.NYB", "DXY"),
    ("CL=F",     "WTI Oil"),
    ("AAPL",     "AAPL"),
    ("MSFT",     "MSFT"),
    ("GOOGL",    "GOOGL"),
    ("AMZN",     "AMZN"),
    ("NVDA",     "NVDA"),
    ("META",     "META"),
    ("TSLA",     "TSLA"),
]

# Bottom ticker: international markets that most affect the above
BOTTOM_SYMBOLS = [
    ("^N225",    "Nikkei 225"),   # Japan — TSLA/NVDA supply chain, JPY/USD dynamics
    ("^GDAXI",   "DAX"),          # Germany — Europe's largest economy, EUR is 57.6% of DXY
    ("^SSEC",    "Shanghai"),     # China — MAG7 supply chain, global commodities demand
    ("^HSI",     "Hang Seng"),    # Hong Kong — China tech proxy, US-China tension gauge
    ("^KS11",    "KOSPI"),        # South Korea — Samsung/SK Hynix, NVDA semiconductor supply
    ("^FTSE",    "FTSE 100"),     # UK — major financial hub, GBP is 11.9% of DXY
    ("EURUSD=X", "EUR/USD"),      # largest DXY component (57.6%), moves inverse to DXY
    ("JPY=X",    "USD/JPY"),      # yen safe-haven, risk-off visible here
    ("BZ=F",     "Brent"),        # international oil benchmark, correlates with WTI/GLD
    ("^AXJO",    "ASX 200"),      # Australia — world's #2 gold producer, top silver miner → GLD/SLV
    ("^GSPTSE",  "TSX"),          # Canada — #3 oil exporter to US, major gold miner → WTI/GLD
    ("CNH=X",    "USD/CNH"),      # offshore yuan — MAG7 manufacturing costs, largest BTC trading pair
    ("^FCHI",    "CAC 40"),       # France — DXY/oil sensitive via LVMH/TotalEnergies
]

_CACHE: dict = {"data": None, "ts": 0.0}
CACHE_TTL = 60  # seconds

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; quantos-ticker/1.0)"}


def _fetch_one(yahoo_sym: str, display: str) -> dict | None:
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}",
            params={"interval": "1d", "range": "1d"},
            timeout=6,
            headers=_HEADERS,
        )
        r.raise_for_status()
        meta = r.json()["chart"]["result"][0]["meta"]
        price = float(meta.get("regularMarketPrice") or 0)
        prev = float(meta.get("chartPreviousClose") or meta.get("previousClose") or price)
        change_pct = ((price - prev) / prev * 100) if prev else 0.0
        return {
            "symbol": display,
            "price": round(price, 4),
            "change_pct": round(change_pct, 2),
        }
    except Exception:
        return None


@router.get("/quotes")
def get_quotes():
    global _CACHE
    if _CACHE["data"] is not None and time.time() - _CACHE["ts"] < CACHE_TTL:
        return _CACHE["data"]

    top_results: list[dict | None] = [None] * len(TOP_SYMBOLS)
    bot_results: list[dict | None] = [None] * len(BOTTOM_SYMBOLS)

    def _work(bucket: str, idx: int, sym: str, name: str):
        return bucket, idx, _fetch_one(sym, name)

    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = (
            [pool.submit(_work, "top", i, s, n) for i, (s, n) in enumerate(TOP_SYMBOLS)] +
            [pool.submit(_work, "bot", i, s, n) for i, (s, n) in enumerate(BOTTOM_SYMBOLS)]
        )
        for fut in as_completed(futs):
            bucket, idx, data = fut.result()
            if bucket == "top":
                top_results[idx] = data
            else:
                bot_results[idx] = data

    result = {
        "top": [q for q in top_results if q],
        "bottom": [q for q in bot_results if q],
    }
    _CACHE = {"data": result, "ts": time.time()}
    return result
