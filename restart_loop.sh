#!/bin/bash

# Log file for the loop itself
LOOP_LOG="loop_manager.log"

echo "Starting Auto-Restart Loop..." >> "$LOOP_LOG"

while true; do
    # If Grok is NOT running, start it
    if ! pgrep -f "python3 grok.py" > /dev/null; then
        echo "Starting Grok at $(date)..." >> "$LOOP_LOG"
        .venv/bin/python3 grok.py >> grok.log 2>&1 &
        GROK_PID=$!
        echo "Grok started (PID: $GROK_PID)" >> "$LOOP_LOG"

        # Wait for it to exit
        wait $GROK_PID
        EXIT_CODE=$?
        echo "Grok stopped with code $EXIT_CODE at $(date). Restarting in 5s..." >> "$LOOP_LOG"
        sleep 5
    else
        sleep 10
    fi
done
