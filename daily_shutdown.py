import os
import sys
import time
import subprocess
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("daily_shutdown")

# Add parent dir to path so we can import internal modules
project_root = Path(__file__).parent.resolve()
sys.path.append(str(project_root))

from telegram_notifier import TelegramNotifier
from live_trader import SchwabOrderExecutor

def main():
    logger.info("Starting scheduled daily shutdown sequence...")
    
    # 1. Trigger manage_backend.sh stop (Engages Kill Switch)
    manager_script = project_root / "manage_backend.sh"
    if not manager_script.exists():
        logger.error(f"Manager script not found at {manager_script}")
        sys.exit(1)
        
    logger.info("Running manage_backend.sh stop...")
    result = subprocess.run(
        ["bash", str(manager_script), "stop"],
        cwd=str(project_root),
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        logger.error(f"Failed to run manager.sh stop: {result.stderr}")
    else:
        logger.info(f"Manager shutdown output: {result.stdout.strip()}")
        
    # 2. Wait for positions to flatten — manage_backend.sh handles graceful shutdown
    logger.info("Waiting 10 seconds for live_trader to flatten positions and exit...")
    time.sleep(10.0)
    
    # 3. Fetch final account data from Schwab
    logger.info("Fetching final account status...")
    try:
        executor = SchwabOrderExecutor(dry_run=False, name="ShutdownPoller")
        
        # Fetch account details
        account_details = executor.fetch_account_details()
        liquidation_value = account_details.get("liquidation_value", 0.0)
        day_pnl = account_details.get("day_pnl", 0.0)
        
        # Fetch active positions
        positions = executor.fetch_positions()
        
    except Exception as exc:
        err_msg = f"Failed to fetch final account status from Schwab: {exc}"
        logger.error(err_msg)
        TelegramNotifier().notify_error("Daily Shutdown Error", err_msg)
        sys.exit(1)
        
    # 4. Format and send Telegram notification
    logger.info("Formatting Telegram notification...")
    
    # Format positions
    open_positions = {sym: qty for sym, qty in positions.items() if qty != 0}
    
    if open_positions:
        pos_str = "\n".join([f"• {sym}: {qty} shares" for sym, qty in open_positions.items()])
        pos_section = f"⚠️ *WARNING: OPEN POSITIONS REMAIN*\n{pos_str}"
    else:
        pos_section = "✅ *All Positions Flattened*"
        
    # Determine PnL emoji
    pnl_emoji = "🟢" if day_pnl >= 0 else "🔴"
    
    message = (
        f"🛑 *SYSTEM SHUTDOWN COMPLETE*\n\n"
        f"💰 *Account Value:* ${liquidation_value:,.2f}\n"
        f"{pnl_emoji} *Day PnL:* ${day_pnl:,.2f}\n\n"
        f"{pos_section}"
    )
    
    logger.info(f"Sending Telegram notification:\n{message}")
    TelegramNotifier().send_message(message)
    logger.info("Daily shutdown sequence finished successfully.")

if __name__ == "__main__":
    main()
