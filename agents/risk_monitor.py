"""
Live Risk Monitor Agent
Runs every 5 minutes on weekdays during market hours (10:30 AM – 4:00 PM ET).
All checks are rule-based — no LLM calls.
Sends Telegram only when a problem first appears, then every 30 min if it persists.
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
ALERT_STATE_PATH = PROJECT_ROOT / "risk_monitor_alerts.json"
SHUTDOWN_SCRIPT = PROJECT_ROOT / "daily_shutdown.py"

STOP_LOSS_WARN_PCT = 0.95   # warn when account reaches 95% of stop loss (5% buffer)
STUCK_POSITION_MINS = 20    # open position older than this is suspicious
RATE_LIMIT_WARN_PCT = 0.80  # warn when trade rate hits 80% of hourly limit
STALE_ALERT_MINS = 10       # no new alerts for this long = possible grok outage
STALE_ACCOUNT_MINS = 5      # account_history not updated = possible live_trader outage
REPEAT_ALERT_MINS = 30      # re-notify for persisting issues every 30 min


def _load_alert_state() -> dict:
    if not ALERT_STATE_PATH.exists():
        return {}
    with open(ALERT_STATE_PATH) as f:
        return json.load(f)


def _save_alert_state(state: dict):
    with open(ALERT_STATE_PATH, "w") as f:
        json.dump(state, f)


def _should_alert(key: str, alert_state: dict) -> bool:
    """Return True if we should send a message: either new issue or 30+ min since last alert."""
    last_sent = alert_state.get(key)
    if last_sent is None:
        return True
    return (time.time() - last_sent) >= REPEAT_ALERT_MINS * 60


def _clear_alert(key: str, alert_state: dict):
    """Remove a resolved issue from state so next occurrence fires immediately."""
    alert_state.pop(key, None)


def _mark_alert(key: str, alert_state: dict):
    alert_state[key] = time.time()


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
    alert_state = _load_alert_state()

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
                _save_alert_state(alert_state)
                return  # shutdown triggered — skip remaining checks
            elif acct_val <= stop_loss * STOP_LOSS_WARN_PCT:
                if _should_alert("stop_loss_warn", alert_state):
                    remaining = acct_val - stop_loss
                    send_telegram(
                        f"⚠️ *Stop Loss Warning*\n\n"
                        f"Account: `${acct_val:,.2f}`\n"
                        f"Stop loss: `${stop_loss:,.2f}`\n"
                        f"Buffer remaining: `${remaining:,.2f}`"
                    )
                    _mark_alert("stop_loss_warn", alert_state)
            else:
                _clear_alert("stop_loss_warn", alert_state)

    # --- 2. Stuck open position ---
    positions = state.get("positions", {})
    position_timestamps = state.get("position_timestamps", {})
    active_stuck = set()
    for symbol, qty in positions.items():
        if qty == 0:
            continue
        entry_ts = position_timestamps.get(symbol)
        if entry_ts and (now - entry_ts) > STUCK_POSITION_MINS * 60:
            key = f"stuck_{symbol}"
            active_stuck.add(key)
            if _should_alert(key, alert_state):
                mins_held = round((now - entry_ts) / 60, 1)
                send_telegram(
                    f"⚠️ *Stuck Position Detected*\n\n"
                    f"`{symbol}` open for `{mins_held} min` (qty=`{qty}`)\n"
                    f"Check live_trader — may need manual intervention."
                )
                _mark_alert(key, alert_state)
    # Clear resolved stuck positions
    for key in [k for k in alert_state if k.startswith("stuck_")]:
        if key not in active_stuck:
            _clear_alert(key, alert_state)

    # --- 3. Trade rate approaching limit ---
    hourly_limit = int(os.getenv("LIVE_MAX_TRADES_PER_HOUR", "60") or "60")
    with closing(get_db()) as conn:
        recent = pd.read_sql_query(
            "SELECT COUNT(*) as cnt FROM live_trades WHERE timestamp >= ?",
            conn, params=(now - 3600,)
        )
    trades_last_hour = int(recent.iloc[0]["cnt"])
    if trades_last_hour >= hourly_limit * RATE_LIMIT_WARN_PCT:
        if _should_alert("rate_limit", alert_state):
            send_telegram(
                f"⚡ *Rate Limit Warning*\n\n"
                f"`{trades_last_hour}/{hourly_limit}` trades in the last hour\n"
                f"Approaching hourly limit — trading may pause soon."
            )
            _mark_alert("rate_limit", alert_state)
    else:
        _clear_alert("rate_limit", alert_state)

    # --- 4. Stale alerts (grok may be down) --- DISABLED: too noisy
    # with closing(get_db()) as conn:
    #     last_alert = pd.read_sql_query(
    #         "SELECT timestamp FROM alerts ORDER BY timestamp DESC LIMIT 1",
    #         conn
    #     )
    # if last_alert.empty or (now - float(last_alert.iloc[0]["timestamp"])) > STALE_ALERT_MINS * 60:
    #     if _should_alert("stale_alerts", alert_state):
    #         last_seen = (
    #             datetime.fromtimestamp(float(last_alert.iloc[0]["timestamp"]), tz=ET).strftime("%H:%M ET")
    #             if not last_alert.empty else "never"
    #         )
    #         send_telegram(
    #             f"📡 *Grok Alert Feed Stale*\n\n"
    #             f"No alerts for `{STALE_ALERT_MINS}+ min` (last: `{last_seen}`)\n"
    #             f"grok.py may be down — check backend."
    #         )
    #         _mark_alert("stale_alerts", alert_state)
    # else:
    #     _clear_alert("stale_alerts", alert_state)

    # --- 5. Stale account history (live_trader may be down) --- DISABLED: too noisy
    # with closing(get_db()) as conn:
    #     last_acct = pd.read_sql_query(
    #         "SELECT timestamp FROM account_history ORDER BY timestamp DESC LIMIT 1",
    #         conn
    #     )
    # if last_acct.empty or (now - float(last_acct.iloc[0]["timestamp"])) > STALE_ACCOUNT_MINS * 60:
    #     if _should_alert("stale_account", alert_state):
    #         last_seen = (
    #             datetime.fromtimestamp(float(last_acct.iloc[0]["timestamp"]), tz=ET).strftime("%H:%M ET")
    #             if not last_acct.empty else "never"
    #         )
    #         send_telegram(
    #             f"🔌 *live_trader May Be Down*\n\n"
    #             f"Account history not updated for `{STALE_ACCOUNT_MINS}+ min` (last: `{last_seen}`)\n"
    #             f"Check backend status."
    #         )
    #         _mark_alert("stale_account", alert_state)
    # else:
    #     _clear_alert("stale_account", alert_state)

    _save_alert_state(alert_state)


def run():
    LOGGER.info("Risk monitor starting.")
    run_checks()
    LOGGER.info("Risk monitor done.")
