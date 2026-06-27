#!/usr/bin/env python3
"""Pre-flight check for tomorrow's MAKER paper-trading run.

Validates everything that can be checked WITHOUT market data, and prints a
clear GO / NO-GO. The one thing it can't do for you is the interactive Schwab
login — if the token is missing/stale it tells you the exact command to run.

    python preflight_paper.py
"""
import os
import sys
import time
import json
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

OK, WARN, BAD = "✅", "⚠️ ", "❌"
problems, warnings = [], []


def check(label, cond, fail_msg, warn=False):
    mark = OK if cond else (WARN if warn else BAD)
    print(f"  {mark} {label}")
    if not cond:
        (warnings if warn else problems).append(fail_msg)
    return cond


def main():
    load_dotenv()
    here = Path(__file__).parent
    print("\n── Pre-flight: MAKER paper trading ──\n")

    # 1. Run-mode env flags
    print("Run mode:")
    inline = os.getenv("ENABLE_INLINE_DISPATCH") == "1"
    dry = os.getenv("INLINE_DRY_RUN") == "1"
    syms_env = os.getenv("SYMBOLS", "")
    check("ENABLE_INLINE_DISPATCH=1 (inline traders on)", inline,
          "Set ENABLE_INLINE_DISPATCH=1 in .env")
    check("INLINE_DRY_RUN=1 (routes to PaperTrader simulator)", dry,
          "Set INLINE_DRY_RUN=1 in .env — otherwise it builds a LIVE trader")
    check(f"SYMBOLS streams all four ({syms_env})",
          set(s.strip() for s in syms_env.split(",")) >= {"AAL", "RIG", "F", "BBAI"},
          "Set SYMBOLS=AAL,RIG,F,BBAI in .env")

    # 2. Config + maker settings
    print("\nConfig (trading_config.json):")
    cfg = json.loads((here / "trading_config.json").read_text())
    check("maker_enabled = true", cfg.get("maker_enabled") is True,
          "Set maker_enabled: true in trading_config.json")
    check(f"paper_position_size = {cfg.get('paper_position_size')} (expect 100)",
          cfg.get("paper_position_size") == 100,
          "Set paper_position_size: 100", warn=True)
    check(f"paper_symbols = {cfg.get('paper_symbols')!r}",
          "AAL" in str(cfg.get("paper_symbols", "")), "Set paper_symbols", warn=True)
    check(f"maker_half_spread_cents = {cfg.get('maker_half_spread_cents')}, "
          f"window = {cfg.get('maker_fill_window_sec')}s",
          cfg.get("maker_half_spread_cents") and cfg.get("maker_fill_window_sec"),
          "Set maker_half_spread_cents and maker_fill_window_sec", warn=True)

    # 3. Schwab credentials + token (THE usual blocker)
    print("\nSchwab auth:")
    for k in ("SCHWAB_CLIENT_ID", "SCHWAB_APP_SECRET", "SCHWAB_REDIRECT_URI"):
        check(f"{k} present", bool(os.getenv(k)), f"{k} missing from .env")
    tok = Path(os.getenv("SCHWAB_TOKEN_PATH", "./schwab_tokens.json"))
    tok_ok = tok.exists()
    check(f"token file exists ({tok})", tok_ok,
          f"NO TOKEN — run:  python auth_login.py --force-login")
    if tok_ok:
        age_days = (time.time() - tok.stat().st_mtime) / 86400
        check(f"token age {age_days:.1f} days (Schwab refresh expires ~7d)",
              age_days < 6.5,
              "Token is stale — re-run: python auth_login.py --force-login", warn=True)

    # 4. Dependencies
    print("\nDependencies (.venv):")
    try:
        import schwab, websockets  # noqa: F401
        check("schwab + websockets importable", True, "")
    except Exception as e:
        check("schwab + websockets importable", False, f"pip install: {e}")

    # 5. DB writable
    print("\nDatabase:")
    try:
        db = here / "penny_basing.db"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE IF NOT EXISTS _preflight (x INTEGER)")
        con.execute("DROP TABLE _preflight")
        con.commit(); con.close()
        check(f"penny_basing.db writable", True, "")
    except Exception as e:
        check("penny_basing.db writable", False, f"DB not writable: {e}")

    # Verdict
    print("\n" + "─" * 40)
    if problems:
        print(f"{BAD} NO-GO — fix these:")
        for p in problems:
            print(f"     • {p}")
        if warnings:
            print(f"\n{WARN}Also review:")
            for w in warnings:
                print(f"     • {w}")
        sys.exit(1)
    print(f"{OK} GO — paper run is ready. Launch with:  ./run_paper.sh")
    if warnings:
        print(f"\n{WARN}Non-blocking warnings:")
        for w in warnings:
            print(f"     • {w}")
    sys.exit(0)


if __name__ == "__main__":
    main()
