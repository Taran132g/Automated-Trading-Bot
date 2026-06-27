#!/bin/bash
# Resilient supervisor for the MAKER paper-trading run.
#
# Solves the failure mode from 2026-06-26: grok.py crashed on a websocket
# FATAL_ERROR ("no close frame") at 11:50 and, with nothing watching it, stayed
# dead for ~4 hours and lost the midday session.
#
# This script is the long-lived process. It:
#   • only runs grok.py during US cash-session hours (09:30–16:00 ET, Mon–Fri)
#   • re-runs preflight and restarts grok.py within ~30s of any crash
#   • keeps the dashboard (uvicorn) up on DASH_PORT
#   • stops cleanly when kill_switch.flag is present
# launchd (com.taranveer.paperbot) keeps THIS script alive across reboots.
set -uo pipefail
cd "$(dirname "$0")"

DASH_PORT="${DASH_PORT:-8013}"     # 8000 = PAIS, never touch it
POLL_SEC=30
PY=".venv/bin/python3"
LOG_PREFIX="supervisor"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S %Z') [$LOG_PREFIX] $*"; }

# Is the US equities cash session open right now? (ET, weekday, 09:30–16:00)
# TZ is pinned to America/New_York so this is correct whether the host clock is
# ET (Mac) or UTC (Oracle/Linux box). 10# forces base-10 (avoids octal on 09xx).
market_open() {
  local dow hm
  dow=$(TZ='America/New_York' date +%u)        # 1=Mon .. 7=Sun
  [ "$dow" -ge 6 ] && return 1                  # weekend
  hm=$(TZ='America/New_York' date +%H%M)
  [ "$((10#$hm))" -ge 930 ] && [ "$((10#$hm))" -lt 1600 ]
}

ensure_dashboard() {
  if lsof -ti:"$DASH_PORT" >/dev/null 2>&1; then return 0; fi
  log "dashboard down -> starting uvicorn on :$DASH_PORT"
  nohup .venv/bin/uvicorn api_server:app --host 127.0.0.1 --port "$DASH_PORT" \
    >> api_server.log 2>&1 &
}

start_trader() {
  if "$PY" preflight_paper.py >/tmp/paperbot_preflight.txt 2>&1; then
    rm -f kill_switch.flag
    local LOG="paper_run_$(date +%Y%m%d).log"
    nohup "$PY" grok.py >> "$LOG" 2>&1 &
    log "✓ grok.py started (PID $!) -> $LOG"
  else
    # Most common cause: stale Schwab token (expires ~7d, needs interactive login)
    log "✗ preflight NO-GO — NOT starting. Tail:"
    tail -3 /tmp/paperbot_preflight.txt | while read -r l; do log "    $l"; done
    touch token_attention.flag        # visible marker for the weekly re-login
  fi
}

log "supervisor up (dash :$DASH_PORT, poll ${POLL_SEC}s)"
while true; do
  if [ -f kill_switch.flag ]; then
    log "kill_switch.flag present — supervisor idling (no restarts)."
    sleep "$POLL_SEC"; continue
  fi

  ensure_dashboard

  if market_open; then
    if ! pgrep -f "grok.py" >/dev/null; then
      log "market open & grok.py not running -> (re)starting"
      start_trader
    fi
  else
    # Outside RTH: let grok.py exit on its own; don't thrash restarts.
    :
  fi

  sleep "$POLL_SEC"
done
