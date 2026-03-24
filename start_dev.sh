#!/bin/bash
# Start QUANT_OS in LOCAL DEV mode
# Runs FastAPI (port 8000) + React dev server (port 5173) concurrently
# Open: http://localhost:5173

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================"
echo "  QUANT_OS  Local Dev Mode"
echo "  API  → http://localhost:8000"
echo "  UI   → http://localhost:5173"
echo "  Open: http://localhost:5173"
echo "======================================"

# Kill children on exit
trap 'kill $(jobs -p) 2>/dev/null' EXIT

# Start FastAPI in background
.venv/bin/uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!
echo "API PID: $API_PID"

# Give API a moment to start
sleep 1

# Start React dev server in foreground
cd "$SCRIPT_DIR/quant-os-ui"
npm run dev
