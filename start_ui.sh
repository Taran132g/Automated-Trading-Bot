#!/bin/bash
set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

UI_LOG="ui.log"
UI_PORT=8501

echo -e "${BLUE}[UI] Starting Streamlit dashboard...${NC}"

# Start Streamlit
nohup streamlit run app.py \
    --server.port=$UI_PORT \
    --server.headless=true \
    --server.enableCORS=false \
    > "$UI_LOG" 2>&1 &

UI_PID=$!

echo -e "${GREEN}✓ UI running on http://localhost:$UI_PORT${NC}"
echo -e "${BLUE} • Logs: $UI_LOG${NC}"
echo -e "${BLUE} • PID: $UI_PID${NC}"
echo ""
echo "To stop: kill $UI_PID"
