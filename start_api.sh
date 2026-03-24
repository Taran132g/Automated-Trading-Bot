#!/bin/bash
# Start the QUANT_OS FastAPI server (serves React UI + API + WebSockets)
# Usage: ./start_api.sh [port]
#
# For local development, run TWO terminals:
#   Terminal 1: ./start_api.sh          (FastAPI backend on :8000)
#   Terminal 2: cd quant-os-ui && npm run dev   (React dev server on :5173 with HMR)
#
# For production (after build): ./start_api.sh
#   FastAPI serves the built React app at http://localhost:8000

set -e
PORT=${1:-8000}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting QUANT_OS API server on port $PORT..."
cd "$SCRIPT_DIR"

exec .venv/bin/uvicorn api_server:app --host 0.0.0.0 --port "$PORT" --reload
