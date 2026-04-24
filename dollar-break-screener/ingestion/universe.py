"""
Stock universe builder — Charles Schwab edition.

Strategy: enumerate all 2–4 letter symbol combinations + a curated 5-letter
seed list, batch through Schwab's get_quotes API (500 symbols per call),
and filter to stocks with close price between $0.80 and $1.50.

Schwab returns data only for valid, tradeable symbols — invalid combos are
silently omitted, so no pre-filtering of the generated list is needed.

First-time setup:
  1. Register an app at developer.schwab.com — get App Key + App Secret.
  2. Set SCHWAB_CLIENT_ID (or SCHWAB_APP_KEY), SCHWAB_APP_SECRET in .env.
  3. Existing schwab_tokens.json in the repo root is auto-detected.
"""

import itertools
import logging
import os
import string
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
CHUNK_SIZE = 500

# ── Curated 5-letter penny stock seeds (biotech, energy, tech micro-caps) ─────
FIVE_LETTER_SEEDS = [
    "SNDL","CLOV","NKLA","GEVO","IMPP","INDO","PROG","XELA","COSM","ATER",
    "WKHS","RIDE","SOLO","SPRT","NEGG","TLGA","GOVX","XSPA","NAKD","SHIP",
    "IDEX","INPX","IZEA","JAGX","RMBL","SURF","TAOP","TXMD","UXIN","YTEN",
    "BYFC","CIDM","DLPN","ENZC","GHSI","OPTI","PAVS","PHUN","RDVT","RNXT",
    "NTRP","OGEN","PSTR","KOSS","MFON","MTIX","TPVG","ZKIN","XSPA","IMVT",
    "CUEN","CLFD","ACST","AMPIO","PBTS","CSTE","MDJM","ACB","TLRY","BYFC",
    "NLSP","ATNX","BOXL","COHN","DBGI","EFHT","FAMI","GFAI","HOLO","IINN",
    "JZXN","KLXE","LIZI","MEGL","NCTY","OXBR","PALI","QNRX","RCAT","SOBR",
    "TPST","UTSI","VCNX","WALD","XBRT","YCBD","ZEST","AEYE","BFRI","CNTX",
    "DJCO","ENVB","FPAY","GLBS","HUMA","ILUS","JNCE","KNDI","LPCN","MNPR",
    "NFYS","OCGN","PFNX","QURE","RAVE","SYTX","TNXP","UVXY","VBIV","WISA",
    "XCUR","YGTY","ZIVO","ABCL","BHAT","COEP","DPSI","EVGN","FWAC","GRTS",
    "HLBZ","IONI","JOFF","KPTI","LASE","MULN","NTRB","OUST","PNTM","RELI",
    "SOPA","TRVG","UAMY","VLON","WSBF","XFOR","YRIV","ZYNE","APXI","BIOR",
    "CLXT","DATS","EDTK","FRLN","GXII","HYMC","IGMS","JFIN","LIQT","MRAI",
    "NRXP","OVID","PHBI","QBTS","RETO","STEM","TGNA","UONE","VTSI","WINT",
    "XRTX","YELL","ZFOX","ABSI","BTTX","CALT","DRIO","EBON","FCEL","GLMD",
    "HSCS","ILUS","JMIA","KZIA","LCTX","MRNS","NRIX","OTRK","PRPB","QMCO",
    "RLAY","SPKL","TRIL","UPWK","VERU","WORX","XBIO","YMAB","ZING","ATXI",
    "BIPH","CFSB","DFLI","EMKR","FWWW","GNPX","HAPP","INVO","JOBY","LMND",
]

# Remove duplicates while preserving order
FIVE_LETTER_SEEDS = list(dict.fromkeys(FIVE_LETTER_SEEDS))


def _get_client() -> schwab.client.Client:
    # Support both naming conventions (SCHWAB_CLIENT_ID used on server)
    app_key = os.environ.get("SCHWAB_APP_KEY") or os.environ["SCHWAB_CLIENT_ID"]
    app_secret = os.environ["SCHWAB_APP_SECRET"]

    # Resolve token path — env var wins, then check sibling repo root (server),
    # then fall back to local data/ directory.
    _here = Path(__file__).parent.parent  # dollar-break-screener/
    _candidates = [
        os.environ.get("SCHWAB_TOKEN_PATH"),          # explicit override
        str(_here.parent / "schwab_tokens.json"),     # server: repo-root/schwab_tokens.json
        str(_here / "data" / "schwab_token.json"),    # local dev default
    ]
    token_path = next(
        (Path(p) for p in _candidates if p and Path(p).exists()),
        Path(_here / "data" / "schwab_token.json"),
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
        log.info("No token file found — opening browser for Schwab OAuth…")
        return schwab.auth.client_from_login_flow(
            api_key=app_key,
            app_secret=app_secret,
            callback_url="https://127.0.0.1",
            token_path=str(token_path),
        )


def _generate_symbols() -> list[str]:
    """Generate all 1–4 letter combinations + 5-letter seeds."""
    letters = string.ascii_uppercase
    syms: list[str] = []
    for length in range(1, 5):  # 1, 2, 3, 4-letter
        syms.extend(''.join(p) for p in itertools.product(letters, repeat=length))
    syms.extend(FIVE_LETTER_SEEDS)
    return syms


def _price_from_quote(q: dict) -> float | None:
    """Extract the best available price from a Schwab quote dict."""
    # Prefer regular market close, fall back to last/mark
    close = q.get("quote", {}).get("closePrice")
    if close and close > 0:
        return float(close)
    last = q.get("quote", {}).get("lastPrice")
    if last and last > 0:
        return float(last)
    mark = q.get("quote", {}).get("mark")
    if mark and mark > 0:
        return float(mark)
    return None


def _build_universe() -> list[dict]:
    client = _get_client()
    now = datetime.utcnow().isoformat()
    candidates = _generate_symbols()

    log.info("Querying prices for %d candidate symbols in chunks of %d…",
             len(candidates), CHUNK_SIZE)

    universe = []
    for i in range(0, len(candidates), CHUNK_SIZE):
        chunk = candidates[i: i + CHUNK_SIZE]
        try:
            resp = client.get_quotes(symbols=chunk)
        except Exception as e:
            log.warning("get_quotes error at chunk %d: %s", i // CHUNK_SIZE, e)
            continue

        if resp.status_code != 200:
            log.debug("get_quotes HTTP %d for chunk %d", resp.status_code, i // CHUNK_SIZE)
            continue

        for symbol, q in resp.json().items():
            if not isinstance(q, dict):
                continue
            if q.get("assetMainType") != "EQUITY":
                continue
            price = _price_from_quote(q)
            if price is None or not (PRICE_LOW <= price <= PRICE_HIGH):
                continue
            avg_vol = (
                q.get("fundamental", {}).get("avg10DaysVolume")
                or q.get("quote", {}).get("totalVolume")
                or 0.0
            )
            universe.append({
                "symbol": symbol,
                "last_close": price,
                "avg_vol_10d": float(avg_vol),
                "updated_at": now,
            })

    log.info("Universe after price filter ($%.2f–$%.2f): %d symbols",
             PRICE_LOW, PRICE_HIGH, len(universe))
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
    """Daemon thread that refreshes universe every 30 min."""
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
    print(symbols[:30])
