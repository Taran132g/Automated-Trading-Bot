#!/bin/bash
# start_advisor.sh — runs the Telegram Signal Advisor as a background process on the server
# Usage: bash telegram_signal_advisor/start_advisor.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$SCRIPT_DIR/advisor.log"

# Kill any existing advisor process
pkill -f "telegram_signal_advisor/main.py" 2>/dev/null && echo "Stopped existing advisor"

cd "$SCRIPT_DIR"

# Install deps if needed
pip install -r requirements.txt -q

nohup python3 main.py >> "$LOG" 2>&1 &
echo "Signal Advisor started (PID $!)"
echo "Logs: $LOG"
