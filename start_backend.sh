#!/bin/bash
set -euo pipefail

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}[BACKEND] Starting Data Feed (Grok)...${NC}"
./.venv/bin/python3 grok.py > grok.log 2>&1 &
GROK_PID=$!
echo -e "${GREEN}✓ Grok running (PID: $GROK_PID)${NC}"

# echo -e "${BLUE}[BACKEND] Starting Live Trader...${NC}"
# ./.venv/bin/python3 live_trader.py > live_trader.log 2>&1 &
# LIVE_PID=$!
# echo -e "${GREEN}✓ Live Trader running (PID: $LIVE_PID)${NC}"

echo ""
echo -e "Logs:"
echo -e "  • grok.log"
echo -e "  • live_trader.log"
echo -e "${BLUE}To stop:${NC} kill $GROK_PID"
