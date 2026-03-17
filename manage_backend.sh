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
    # 1. Engage kill switch so traders can detect it and self-flatten positions
    touch kill_switch.flag
    # 2. Stop the restart loop so nothing gets restarted
    pkill -f "$LOOP_SCRIPT" 2>/dev/null
    # 3. Wait up to 15s for grok, live_trader, and paper_trader to exit gracefully
    echo "Waiting up to 15s for traders to detect kill switch and exit gracefully..."
    for i in $(seq 1 15); do
        grok_running=0
        live_running=0
        paper_running=0
        pgrep -f "python3 grok.py" > /dev/null && grok_running=1
        pgrep -f "python3 live_trader.py" > /dev/null && live_running=1
        pgrep -f "python3 paper_trader.py" > /dev/null && paper_running=1
        if [ $grok_running -eq 0 ] && [ $live_running -eq 0 ] && [ $paper_running -eq 0 ]; then
            echo "All processes exited cleanly."
            break
        fi
        sleep 1
    done
    # 4. Force-kill anything still running
    if pgrep -f "python3 grok.py" > /dev/null; then
        echo "WARNING: grok.py did not exit in time — force killing."
        pkill -f "python3 grok.py" 2>/dev/null
    fi
    if pgrep -f "python3 live_trader.py" > /dev/null; then
        echo "WARNING: live_trader.py did not exit in time — force killing."
        pkill -f "python3 live_trader.py" 2>/dev/null
    fi
    if pgrep -f "python3 paper_trader.py" > /dev/null; then
        echo "WARNING: paper_trader.py did not exit in time — force killing."
        pkill -f "python3 paper_trader.py" 2>/dev/null
    fi
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
