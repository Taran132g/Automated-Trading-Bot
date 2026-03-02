import os
import requests
import logging

LOGGER = logging.getLogger("TelegramNotifier")

class TelegramNotifier:
    def __init__(self):
        self.enabled = False
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if self.bot_token and self.chat_id:
            self.enabled = True
            LOGGER.info("Telegram Notifier enabled.")
        else:
            LOGGER.warning("Telegram Notifier disabled: Missing TOKEN or CHAT_ID in .env")

    def send_message(self, text: str):
        if not self.enabled:
            return
        
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        
        try:
            response = requests.post(url, json=payload, timeout=5)
            response.raise_for_status()
        except Exception as e:
            LOGGER.error("Failed to send telegram message: %s", e)

    def notify_cooldown(self, cooldown_type: str, account_value: float):
        if not self.enabled:
            return
        
        emoji = "❄️" if "PI" in cooldown_type else "🚨"
        msg = (
            f"{emoji} *Cooldown Triggered*\n"
            f"Type: `{cooldown_type}`\n"
            f"Account Value: `${account_value:,.2f}`"
        )
        self.send_message(msg)
