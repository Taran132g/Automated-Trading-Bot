#!/bin/bash

# Log file for the loop itself
LOOP_LOG="loop_manager.log"

# Force correct working directory
cd "$(dirname "$0")"
source .env

echo "Starting Auto-Restart Loop in $(pwd)..." >> "$LOOP_LOG"

# Trap to kill background processes on exit
trap "pkill -P $$; exit" SIGINT SIGTERM EXIT

echo "Starting Auto-Restart Loop in $(pwd)..." >> "$LOOP_LOG"

while true; do
    # Check for kill switch to terminate the auto-restart loop
    if [ -f "kill_switch.flag" ]; then
        echo "Kill switch detected at $(date). Exiting auto-restart loop." >> "$LOOP_LOG"
        break
    fi

    # Source env to get latest config flags
    [ -f .env ] && source .env

    # 1. Start Grok
    if ! pgrep -f "grok.py" > /dev/null; then
        echo "Starting Grok at $(date)..." >> "$LOOP_LOG"
        .venv/bin/python3 grok.py >> grok.log 2>&1 &
        echo "Grok started (PID: $!)" >> "$LOOP_LOG"
    fi

    # 2. Start Paper Trader
    GROK_PAPER_INLINE=0
    if [ "$ENABLE_INLINE_DISPATCH" = "1" ]; then
        if [ "$INLINE_DRY_RUN" = "1" ] || [ "$LIVE_DRY_RUN" = "1" ] || [ "$INLINE_LIVE_DRY_RUN" = "1" ]; then
            GROK_PAPER_INLINE=1
        fi
    fi

    if [ "$RUN_PAPER_TRADER" = "1" ] && [ "$GROK_PAPER_INLINE" = "0" ]; then
        if ! pgrep -f "paper_trader.py" > /dev/null; then
            echo "Starting Paper Trader at $(date)..." >> "$LOOP_LOG"
            .venv/bin/python3 paper_trader.py >> paper_trader.log 2>&1 &
            echo "Paper Trader started (PID: $!)" >> "$LOOP_LOG"
        fi
    fi

    # 3. Start Live Trader
    if [ "$RUN_LIVE_TRADER" = "1" ] && [ "$ENABLE_INLINE_DISPATCH" != "1" ]; then
        if ! pgrep -f "live_trader.py" > /dev/null; then
            echo "Starting Live Trader at $(date)..." >> "$LOOP_LOG"
            .venv/bin/python3 live_trader.py >> live_trader.log 2>&1 &
            echo "Live Trader started (PID: $!)" >> "$LOOP_LOG"
        fi
    fi

    sleep 10
done
