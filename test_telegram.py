from dotenv import load_dotenv
from telegram_notifier import TelegramNotifier
import os
import time

def test_notifier():
    print("🚀 Initializing Telegram Notifier...")
    load_dotenv()
    
    notifier = TelegramNotifier()
    
    if not notifier.enabled:
        print("❌ Telegram Notifier is DISABLED. Check your .env for TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
        return

    print("✅ Notifier Enabled. Sending test messages...")
    
    # Test 1: Generic Message
    print("📤 Sending generic message...")
    notifier.send_message("⚡ *Bot Test*: System integration active.")
    
    # Test 2: Account Update
    print("📤 Sending account update...")
    test_details = {
        "liquidation_value": 25000.50,
        "day_pnl": 125.75
    }
    notifier.notify_account_update(test_details)
    
    # Test 3: Cooldown
    print("📤 Sending cooldown alert...")
    notifier.notify_cooldown("Loss Cooldown (Test)", 120)
    
    print("\n🎉 Test cycle complete. Check your Telegram!")

if __name__ == "__main__":
    test_notifier()
