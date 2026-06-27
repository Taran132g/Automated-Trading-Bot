#!/bin/bash
# One-shot deploy of the MAKER paper-trading bot to a DEDICATED Oracle micro.
#
#   ./deploy/oracle_deploy.sh <NEW_INSTANCE_IP>
#
# Run from the Mac repo root. Pushes code + secrets to the new box, builds the
# venv, installs the systemd unit, and starts it. Idempotent — safe to re-run.
#
# IMPORTANT (Schwab token): the same token CANNOT refresh on two machines — they
# invalidate each other. After this deploy succeeds, the Oracle box owns the
# token; DISABLE the Mac runner so it stops refreshing:
#     launchctl unload ~/Library/LaunchAgents/com.taranveer.paperbot.plist
# Weekly re-login stays a Mac task (needs a browser): mint with
#     .venv/bin/python auth_login.py --force-login
# then re-run this script to push the fresh schwab_tokens.json to Oracle.
set -euo pipefail
cd "$(dirname "$0")/.."

IP="${1:?usage: ./deploy/oracle_deploy.sh <NEW_INSTANCE_IP>}"
KEY="$HOME/.ssh/oracle_pais.key"
REMOTE="ubuntu@$IP"
DEST="/home/ubuntu/Automated-Trading-Bot"
SSH="ssh -i $KEY -o StrictHostKeyChecking=accept-new"

echo "── 1/4  rsync code + secrets → $REMOTE ──"
# Exclude local-only heavy/derived files; .env + schwab_tokens.json ARE sent
# (the box needs Schwab creds + token; transit is over SSH to your own host).
rsync -az --delete \
  -e "ssh -i $KEY -o StrictHostKeyChecking=accept-new" \
  --exclude='.git/' --exclude='.venv/' --exclude='__pycache__/' \
  --exclude='*.pyc' --exclude='.pytest_cache/' --exclude='*.log' \
  --exclude='backtest_report/' --exclude='*.bundle' --exclude='.env.bak.*' \
  --exclude='kill_switch.flag' --exclude='token_attention.flag' \
  ./ "$REMOTE:$DEST/"

echo "── 2/4  build venv + deps on box ──"
$SSH "$REMOTE" bash -se <<'REMOTE_SETUP'
set -euo pipefail
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-pip lsof >/dev/null
cd /home/ubuntu/Automated-Trading-Bot
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
chmod +x supervisor_paper.sh
echo "  venv ready: $(.venv/bin/python --version)"
REMOTE_SETUP

echo "── 3/4  install + (re)start systemd unit ──"
$SSH "$REMOTE" bash -se <<'REMOTE_SVC'
set -euo pipefail
sudo cp /home/ubuntu/Automated-Trading-Bot/deploy/paperbot.service /etc/systemd/system/paperbot.service
sudo systemctl daemon-reload
sudo systemctl enable paperbot.service >/dev/null 2>&1 || true
sudo systemctl restart paperbot.service
sleep 2
systemctl --no-pager --lines=0 status paperbot.service | head -4
REMOTE_SVC

echo "── 4/4  preflight on box (verifies token landed) ──"
$SSH "$REMOTE" "cd $DEST && .venv/bin/python preflight_paper.py" || \
  echo "  ⚠️ preflight NO-GO on box — usually the Schwab token; re-mint on Mac and re-run this script."

echo ""
echo "✓ Deploy done. Dashboard (tunnel to view):"
echo "    ssh -i $KEY -L 8013:127.0.0.1:8013 $REMOTE   # then open http://127.0.0.1:8013/paper.html"
echo "  Logs:   $SSH $REMOTE 'tail -f $DEST/supervisor.log'"
echo ""
echo "  ⚠️ CUTOVER: disable the Mac runner so the two don't clobber the Schwab token:"
echo "      launchctl unload ~/Library/LaunchAgents/com.taranveer.paperbot.plist"
