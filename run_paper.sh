#!/bin/bash
# Launch the MAKER paper-trading run (grok.py inline -> PaperTrader simulator).
# Streams AAL,RIG,F,BBAI, simulates passive-limit fills, records PnL to
# penny_basing.db (paper_trades / paper_positions) and daily_pnl.txt.
set -euo pipefail
cd "$(dirname "$0")"

# Dedicated dashboard port — :8000 belongs to PAIS (~/agentic_os), never touch it.
DASH_PORT="${DASH_PORT:-8011}"

echo "── Pre-flight ──"
.venv/bin/python preflight_paper.py || { echo "Pre-flight failed; aborting."; exit 1; }

# Don't double-run
if pgrep -f "grok.py" >/dev/null; then
  echo "grok.py already running (PID $(pgrep -f grok.py | head -1)). Stop it first: ./stop_backend.sh"
  exit 1
fi

rm -f kill_switch.flag
LOG="paper_run_$(date +%Y%m%d).log"
echo "── Starting paper run → $LOG ──"
nohup .venv/bin/python3 grok.py >> "$LOG" 2>&1 &
echo "✓ grok.py started (PID $!) in MAKER paper mode."

# Dashboard API server (reads the DB; no Schwab token needed) on :$DASH_PORT.
# NOTE: :8000 is PAIS — we run on our own port and only manage our own.
if lsof -ti:"$DASH_PORT" >/dev/null 2>&1; then
  echo "• dashboard already serving on :$DASH_PORT."
else
  nohup .venv/bin/uvicorn api_server:app --host 127.0.0.1 --port "$DASH_PORT" >> api_server.log 2>&1 &
  echo "✓ dashboard server started (PID $!) on :$DASH_PORT."
fi
sleep 2

URL="http://127.0.0.1:$DASH_PORT/paper.html"
echo ""
echo "📊 DASHBOARD:  $URL"
echo "   Tail log:   tail -f $LOG"
echo "   Stop all:   touch kill_switch.flag   (graceful flatten)  then  pkill -f grok.py; pkill -f 'uvicorn api_server'"
command -v open >/dev/null && open "$URL" || true
