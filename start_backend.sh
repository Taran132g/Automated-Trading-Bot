#!/bin/bash
set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

GROK_LOG="grok.log"
PAPER_LOG="paper_trader.log"

# Note: .env is loaded by Python's dotenv, not here

# Use Python 3.11 (same as Streamlit, with all deps installed)
PYTHON_BIN="python3.11"

echo -e "${BLUE}[BACKEND] Starting trading backend...${NC}"

# Remove kill switch if it exists
if [ -f kill_switch.flag ]; then
    echo -e "${YELLOW} • Removing kill switch...${NC}"
    rm kill_switch.flag
fi

# Start grok.py (data stream + live trader)
echo -e "${BLUE}[1/2] Starting grok.py...${NC}"
nohup $PYTHON_BIN grok.py > "$GROK_LOG" 2>&1 &
GROK_PID=$!
echo -e "${GREEN} • grok.py → $GROK_LOG (PID: $GROK_PID)${NC}"

# Start paper_trader.py (simulation)
echo -e "${BLUE}[2/2] Starting paper_trader.py...${NC}"
nohup $PYTHON_BIN paper_trader.py > "$PAPER_LOG" 2>&1 &
PAPER_PID=$!
echo -e "${GREEN} • paper_trader.py → $PAPER_LOG (PID: $PAPER_PID)${NC}"

echo ""
echo -e "${GREEN}✓ Backend services running${NC}"
echo -e "${BLUE} • grok: $GROK_PID${NC}"
echo -e "${BLUE} • paper_trader: $PAPER_PID${NC}"
echo ""
echo "To stop: ./stop_backend.sh"
