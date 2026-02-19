#!/bin/bash
set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}[BACKEND] Starting via restart loop (auto-restart on crash)...${NC}"
chmod +x restart_loop.sh
nohup ./restart_loop.sh > /dev/null 2>&1 &
LOOP_PID=$!
echo -e "${GREEN}✓ Restart loop running (PID: $LOOP_PID)${NC}"

echo ""
echo -e "Logs:"
echo -e "  • grok.log"
echo -e "  • loop_manager.log"
echo -e "${BLUE}To stop:${NC} ./stop_backend.sh"
