#!/bin/bash
set -euo pipefail

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Trading Bot Server Setup${NC}"
echo -e "${BLUE}========================================${NC}"

# Check if running from root
if [ ! -f "requirements.txt" ]; then
    echo -e "${YELLOW}Error: requirements.txt not found.${NC}"
    echo "Please run this script from the repository root:"
    echo "  ./deploy/setup.sh"
    exit 1
fi

# Update system
echo -e "${YELLOW}[1/5] Updating system...${NC}"
apt update && apt upgrade -y

# Install Python 3.12
echo -e "${YELLOW}[2/5] Installing Python 3.12...${NC}"
apt install -y software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt update
apt install -y python3.12 python3.12-venv python3.12-dev python3-pip

# Install other dependencies
echo -e "${YELLOW}[3/5] Installing dependencies...${NC}"
apt install -y git curl sqlite3

# Install pip packages
echo -e "${YELLOW}[4/5] Installing Python packages...${NC}"
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Set permissions
echo -e "${YELLOW}[5/5] Setting permissions...${NC}"
chmod +x start_ui.sh start_backend.sh stop_backend.sh restart_loop.sh manage_backend.sh

# Set up crontab for daily startup/shutdown (times in UTC, targeting EST)
echo -e "${YELLOW}[6/5] Setting up crontab...${NC}"
REPO_DIR=$(pwd)
(crontab -l 2>/dev/null | grep -v "daily_startup\|daily_shutdown"; \
  echo "30 15 * * 1-5 cd $REPO_DIR && ./.venv/bin/python3 daily_startup.py >> $REPO_DIR/daily_startup.log 2>&1"; \
  echo "58 20 * * 1-5 cd $REPO_DIR && ./.venv/bin/python3 daily_shutdown.py >> $REPO_DIR/daily_shutdown.log 2>&1" \
) | crontab -
echo -e "${GREEN}✓ Crontab set: startup 10:30 AM EST, shutdown 3:58 PM EST${NC}"

# Update service file with current directory
echo -e "${YELLOW}[7/5] Configuring service file...${NC}"
CURRENT_DIR=$(pwd)
sed -i "s|WorkingDirectory=/root/taranveer-singh.github.io|WorkingDirectory=$CURRENT_DIR|g" deploy/trading-ui.service
sed -i "s|ExecStart=/usr/bin/python3.11|ExecStart=$CURRENT_DIR/.venv/bin/python|g" deploy/trading-ui.service

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo "  1. Create your .env file (include SCHWAB keys and TOTP_SECRET)"
echo "  2. Access the UI to initialize Schwab tokens via Admin Controls"
echo "  3. Install UI service: sudo cp deploy/trading-ui.service /etc/systemd/system/"
echo "  4. Enable: sudo systemctl enable trading-ui"
echo "  5. Start: sudo systemctl start trading-ui"
echo ""
echo "Your dashboard will be live at http://YOUR_IP:8501"
echo "Use the Admin Controls page to manage tokens and start the backend."
