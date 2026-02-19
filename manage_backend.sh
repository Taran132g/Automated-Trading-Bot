#!/bin/bash

LOOP_SCRIPT="restart_loop.sh"
LOG_FILE="loop_manager.log"

start_backend() {
    if pgrep -f "$LOOP_SCRIPT" > /dev/null; then
        echo "Backend is already running."
    else
        echo "Starting Backend (Auto-Restart Active)..."
        chmod +x "$LOOP_SCRIPT"
        nohup ./"$LOOP_SCRIPT" > /dev/null 2>&1 &
        echo "Backend Started."
    fi
}

stop_backend() {
    echo "Stopping Backend..."
    pkill -f "$LOOP_SCRIPT" 2>/dev/null
    pkill -f "python3 grok.py" 2>/dev/null
    pkill -f "python3 live_trader.py" 2>/dev/null
    pkill -f "python3 paper_trader.py" 2>/dev/null
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
