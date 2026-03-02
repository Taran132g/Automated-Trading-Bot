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
    
    # Test 2: Cooldown Message with Account Value
    print("📤 Sending cooldown alert (PI)...")
    notifier.notify_cooldown("PI Cooldown", 25000.50)
    
    # Test 3: Cooldown Message with Account Value
    print("📤 Sending cooldown alert (Loss)...")
    notifier.notify_cooldown("Loss Cooldown", 24980.25)
    
    print("\n🎉 Test cycle complete. Check your Telegram!")

if __name__ == "__main__":
    test_notifier()
