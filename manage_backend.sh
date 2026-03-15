#!/bin/bash

LOOP_SCRIPT="restart_loop.sh"
LOG_FILE="loop_manager.log"

start_backend() {
    if pgrep -f "$LOOP_SCRIPT" > /dev/null; then
        echo "Backend is already running."
    else
        echo "Starting Backend (Auto-Restart Active)..."
        rm -f kill_switch.flag
        chmod +x "$LOOP_SCRIPT"
        nohup ./"$LOOP_SCRIPT" > /dev/null 2>&1 &
        echo "Backend Started."
    fi
}

stop_backend() {
    echo "Stopping Backend..."
    # 1. Engage kill switch so live_trader can detect it and self-flatten positions
    touch kill_switch.flag
    # 2. Stop the restart loop so nothing gets restarted
    pkill -f "$LOOP_SCRIPT" 2>/dev/null
    # 3. Stop paper trader (no real positions to close)
    pkill -f "python3 paper_trader.py" 2>/dev/null
    # 4. Let live_trader detect the kill switch and flatten positions on its own.
    #    Wait up to 30s for it to exit gracefully before force-killing.
    echo "Waiting for live_trader to flatten positions..."
    for i in $(seq 1 30); do
        if ! pgrep -f "python3 live_trader.py" > /dev/null; then
            echo "live_trader exited cleanly."
            break
        fi
        sleep 1
    done
    # Force-kill if still running after timeout
    if pgrep -f "python3 live_trader.py" > /dev/null; then
        echo "WARNING: live_trader did not exit in time — force killing."
        pkill -f "python3 live_trader.py" 2>/dev/null
    fi
    # 5. Now kill grok (no longer needed for pricing)
    pkill -f "python3 grok.py" 2>/dev/null
    echo "Backend Stopped."
}

status_backend() {
    echo "--- Backend Status ---"
    if pgrep -f "$LOOP_SCRIPT" > /dev/null; then
        echo "Manager Loop: RUNNING ($(pgrep -f "$LOOP_SCRIPT" | head -n 1))"
    else
        echo "Manager Loop: STOPPED"
    fi
    
    if pgrep -f "python3 grok.py" > /dev/null; then
        echo "Grok Backend: RUNNING ($(pgrep -f "python3 grok.py" | head -n 1))"
    else
        echo "Grok Backend: STOPPED"
    fi
}

case "$1" in
    start)
        start_backend
        ;;
    stop)
        stop_backend
        ;;
    restart)
        stop_backend
        sleep 2
        start_backend
        ;;
    status)
        status_backend
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
esac
