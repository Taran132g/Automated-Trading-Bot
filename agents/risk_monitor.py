"""
Live Risk Monitor Agent
Runs every 5 minutes on weekdays during market hours (9:25 AM – 4:05 PM ET).
All checks are rule-based — no LLM calls.
If the account hits the stop loss threshold, triggers daily_shutdown.py early.
"""

import json
import logging
import os
import subprocess
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytz

from agents.base import get_db, send_telegram

LOGGER = logging.getLogger("agents.risk_monitor")
ET = pytz.timezone("America/New_York")

PROJECT_ROOT = Path(__file__).parent.parent
STATE_PATH = PROJECT_ROOT / "live_trader_state_primary.json"
SHUTDOWN_SCRIPT = PROJECT_ROOT / "daily_shutdown.py"

STOP_LOSS_WARN_PCT = 0.95   # warn when account reaches 95% of stop loss (5% buffer)
STUCK_POSITION_MINS = 20    # open position older than this is suspicious
RATE_LIMIT_WARN_PCT = 0.80  # warn when trade rate hits 80% of hourly limit
STALE_ALERT_MINS = 10       # no new alerts for this long = possible grok outage
STALE_ACCOUNT_MINS = 5      # account_history not updated = possible live_trader outage


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    with open(STATE_PATH) as f:
        return json.load(f)


def _trigger_early_shutdown(acct_val: float, stop_loss: float):
    LOGGER.warning("Stop loss hit ($%.2f <= $%.2f) — triggering early shutdown.", acct_val, stop_loss)
    send_telegram(
        f"🚨 *STOP LOSS HIT — EMERGENCY SHUTDOWN*\n\n"
        f"Account: `${acct_val:,.2f}`\n"
        f"Stop loss: `${stop_loss:,.2f}`\n\n"
        f"Triggering daily shutdown now..."
    )
    subprocess.Popen(
        ["python", str(SHUTDOWN_SCRIPT)],
        cwd=str(PROJECT_ROOT),
    )


def run_checks():
    now = time.time()
    state = _load_state()

    # --- 1. Stop loss check (hard trigger) ---
    stop_loss = float(os.getenv("ACCOUNT_STOP_LOSS", "0") or "0")
    if stop_loss > 0:
        with closing(get_db()) as conn:
            row = pd.read_sql_query(
                "SELECT liquidation_value FROM account_history ORDER BY timestamp DESC LIMIT 1",
                conn
            )
        if not row.empty:
            acct_val = float(row.iloc[0]["liquidation_value"])
            if acct_val <= stop_loss:
                _trigger_early_shutdown(acct_val, stop_loss)
                return  # shutdown triggered — skip remaining checks
            elif acct_val <= stop_loss * STOP_LOSS_WARN_PCT:
                remaining = acct_val - stop_loss
                send_telegram(
                    f"⚠️ *Stop Loss Warning*\n\n"
                    f"Account: `${acct_val:,.2f}`\n"
                    f"Stop loss: `${stop_loss:,.2f}`\n"
                    f"Buffer remaining: `${remaining:,.2f}`"
                )

    # --- 2. Stuck open position ---
    positions = state.get("positions", {})
    position_timestamps = state.get("position_timestamps", {})
    for symbol, qty in positions.items():
        if qty == 0:
            continue
        entry_ts = position_timestamps.get(symbol)
        if entry_ts and (now - entry_ts) > STUCK_POSITION_MINS * 60:
            mins_held = round((now - entry_ts) / 60, 1)
            send_telegram(
                f"⚠️ *Stuck Position Detected*\n\n"
                f"`{symbol}` open for `{mins_held} min` (qty=`{qty}`)\n"
                f"Check live_trader — may need manual intervention."
            )

    # --- 3. Trade rate approaching limit ---
    hourly_limit = int(os.getenv("LIVE_MAX_TRADES_PER_HOUR", "60") or "60")
    with closing(get_db()) as conn:
        recent = pd.read_sql_query(
            "SELECT COUNT(*) as cnt FROM live_trades WHERE timestamp >= ?",
            conn, params=(now - 3600,)
        )
    trades_last_hour = int(recent.iloc[0]["cnt"])
    if trades_last_hour >= hourly_limit * RATE_LIMIT_WARN_PCT:
        send_telegram(
            f"⚡ *Rate Limit Warning*\n\n"
            f"`{trades_last_hour}/{hourly_limit}` trades in the last hour\n"
            f"Approaching hourly limit — trading may pause soon."
        )

    # --- 4. Stale alerts (grok may be down) ---
    with closing(get_db()) as conn:
        last_alert = pd.read_sql_query(
            "SELECT timestamp FROM alerts ORDER BY timestamp DESC LIMIT 1",
            conn
        )
    if last_alert.empty or (now - float(last_alert.iloc[0]["timestamp"])) > STALE_ALERT_MINS * 60:
        last_seen = (
            datetime.fromtimestamp(float(last_alert.iloc[0]["timestamp"]), tz=ET).strftime("%H:%M ET")
            if not last_alert.empty else "never"
        )
        send_telegram(
            f"📡 *Grok Alert Feed Stale*\n\n"
            f"No alerts for `{STALE_ALERT_MINS}+ min` (last: `{last_seen}`)\n"
            f"grok.py may be down — check backend."
        )

    # --- 5. Stale account history (live_trader may be down) ---
    with closing(get_db()) as conn:
        last_acct = pd.read_sql_query(
            "SELECT timestamp FROM account_history ORDER BY timestamp DESC LIMIT 1",
            conn
        )
    if last_acct.empty or (now - float(last_acct.iloc[0]["timestamp"])) > STALE_ACCOUNT_MINS * 60:
        last_seen = (
            datetime.fromtimestamp(float(last_acct.iloc[0]["timestamp"]), tz=ET).strftime("%H:%M ET")
            if not last_acct.empty else "never"
        )
        send_telegram(
            f"🔌 *live_trader May Be Down*\n\n"
            f"Account history not updated for `{STALE_ACCOUNT_MINS}+ min` (last: `{last_seen}`)\n"
            f"Check backend status."
        )


def run():
    LOGGER.info("Risk monitor starting.")
    run_checks()
    LOGGER.info("Risk monitor done.")
