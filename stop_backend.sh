#!/bin/bash
set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}[BACKEND] Stopping trading backend...${NC}"

# Kill grok.py and paper_trader.py processes
PIDS=$(pgrep -f "grok.py|paper_trader.py" || true)

if [ -z "$PIDS" ]; then
    echo -e "${YELLOW}No backend processes found.${NC}"
else
    echo -e "${RED}Stopping processes: $PIDS${NC}"
    kill -9 $PIDS
    echo -e "${GREEN}✓ Backend processes terminated${NC}"
fi

# Create kill switch file
echo -e "${BLUE}Creating kill switch...${NC}"
touch kill_switch.flag
echo -e "${GREEN}✓ Kill switch activated${NC}"

echo ""
echo "Backend is now stopped."
echo "To restart: ./start_backend.sh"
