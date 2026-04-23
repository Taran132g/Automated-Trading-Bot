"""
Stock universe builder — Charles Schwab edition.

On startup (and every 30 min), uses the Schwab REST API to find all
tradeable US equities with a last price between $0.80 and $1.50, then
persists that universe to SQLite.

First-time setup:
  1. Register an app at developer.schwab.com — get App Key + App Secret.
  2. Set SCHWAB_APP_KEY, SCHWAB_APP_SECRET, SCHWAB_TOKEN_PATH in .env.
  3. Run `python -m ingestion.universe` once; a browser window will open
     for OAuth. After you authenticate, the token is saved to the file
     specified by SCHWAB_TOKEN_PATH and reused automatically going forward.
"""

import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path

import schwab
from dotenv import load_dotenv

from db.database import upsert_universe, get_universe

load_dotenv()
log = logging.getLogger(__name__)

PRICE_LOW = 0.80
PRICE_HIGH = 1.50
REFRESH_INTERVAL = 1800  # 30 min

# Schwab's API lets you screen by exchange — keep major US equity venues
US_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "BATS"}


def _get_client() -> schwab.client.Client:
    # Support both naming conventions (SCHWAB_CLIENT_ID used on server)
    app_key = os.environ.get("SCHWAB_APP_KEY") or os.environ["SCHWAB_CLIENT_ID"]
    app_secret = os.environ["SCHWAB_APP_SECRET"]

    # Resolve token path — env var wins, then check sibling repo root (server layout),
    # then fall back to local data/ directory.
    _here = Path(__file__).parent.parent  # dollar-break-screener/
    _candidates = [
        os.environ.get("SCHWAB_TOKEN_PATH"),          # explicit override
        str(_here.parent / "schwab_tokens.json"),     # server: repo-root/schwab_tokens.json
        str(_here / "data" / "schwab_token.json"),    # local dev default
    ]
    token_path = next(
        (Path(p) for p in _candidates if p and Path(p).exists()),
        Path(_here / "data" / "schwab_token.json"),   # final fallback (may not exist yet)
    )
    token_path.parent.mkdir(parents=True, exist_ok=True)
    log.info("Using Schwab token: %s", token_path)

    if token_path.exists():
        return schwab.auth.client_from_token_file(
            token_path=str(token_path),
            api_key=app_key,
            app_secret=app_secret,
        )
    else:
        # Interactive browser auth — only needed once per machine
        log.info("No token file found — opening browser for Schwab OAuth…")
        return schwab.auth.client_from_login_flow(
            api_key=app_key,
            app_secret=app_secret,
            callback_url="https://127.0.0.1",
            token_path=str(token_path),
        )


def _build_universe() -> list[dict]:
    client = _get_client()
    now = datetime.utcnow().isoformat()

    # Schwab's instrument search: use a broad screener via fundamentals
    # Strategy: fetch fundamentals for a pre-built list of penny/low-cap symbols,
    # or use the screener if available. schwab-py exposes get_instruments() for
    # symbol lookup and get_quotes() for bulk price checks.
    #
    # Because Schwab's REST API doesn't have a true universe screener endpoint,
    # we use a two-step approach:
    #   1. Use screener via instruments search with symbol patterns (A-Z prefixes)
    #   2. Filter by quote price
    #
    # Note: Schwab limits bulk quote requests to 500 symbols per call.

    # Step 1: Collect candidate symbols via broad search
    candidates: set[str] = set()
    # Common low-priced stock prefixes — cast a wide net
    for prefix in list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        try:
            resp = client.get_instruments(
                symbols=f"{prefix}*",
                projection=schwab.client.Client.Instrument.Projection.SYMBOL_REGEX,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            instruments = data.get("instruments", [])
            for inst in instruments:
                sym = inst.get("symbol", "")
                # Keep plain equity symbols only (no slashes, options suffixes, etc.)
                if (
                    inst.get("assetType") == "EQUITY"
                    and sym
                    and "/" not in sym
                    and len(sym) <= 5
                    and sym.isalpha()
                ):
                    candidates.add(sym)
        except Exception as e:
            log.debug("Instrument search error for prefix %s: %s", prefix, e)

    log.info("Raw candidate pool: %d symbols", len(candidates))

    # Step 2: Batch quote requests — filter by price
    universe = []
    candidate_list = sorted(candidates)
    chunk_size = 500

    for i in range(0, len(candidate_list), chunk_size):
        chunk = candidate_list[i : i + chunk_size]
        try:
            resp = client.get_quotes(symbols=chunk)
            if resp.status_code != 200:
                log.warning("Quotes request failed (status %d) for chunk %d", resp.status_code, i // chunk_size)
                continue
            quotes = resp.json()
        except Exception as e:
            log.warning("Quotes fetch error for chunk %d: %s", i // chunk_size, e)
            continue

        for symbol, q in quotes.items():
            try:
                # Schwab quote structure: q["quote"]["lastPrice"] or q["regular"]["regularMarketLastPrice"]
                quote_data = q.get("quote", {})
                last = quote_data.get("lastPrice") or quote_data.get("mark") or 0.0
                volume = quote_data.get("totalVolume") or 0.0
                exchange = q.get("reference", {}).get("exchange", "")

                if PRICE_LOW <= float(last) <= PRICE_HIGH:
                    universe.append({
                        "symbol": symbol,
                        "last_close": float(last),
                        "avg_vol_10d": float(volume),
                        "updated_at": now,
                    })
            except Exception:
                continue

    log.info("Universe after price filter: %d symbols", len(universe))
    return universe


def refresh_universe() -> list[str]:
    """Rebuild universe, persist to DB, return list of symbols."""
    rows = _build_universe()
    if rows:
        upsert_universe(rows)
    return [r["symbol"] for r in rows]


def get_symbols() -> list[str]:
    """Return current universe symbols from DB (no API call)."""
    return [r["symbol"] for r in get_universe()]


def start_background_refresh(callback=None) -> None:
    """
    Daemon thread that refreshes universe every 30 min.
    `callback(symbols)` is called after each refresh.
    """
    def _loop():
        while True:
            try:
                symbols = refresh_universe()
                if callback:
                    callback(symbols)
            except Exception as e:
                log.error("Universe refresh failed: %s", e)
            time.sleep(REFRESH_INTERVAL)

    t = threading.Thread(target=_loop, daemon=True, name="universe-refresh")
    t.start()
    log.info("Universe refresh thread started (interval=%ds)", REFRESH_INTERVAL)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    symbols = refresh_universe()
    print(f"Universe built: {len(symbols)} symbols")
    print(symbols[:20])
