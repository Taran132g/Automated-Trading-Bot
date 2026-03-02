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

    def notify_account_update(self, details: dict):
        if not self.enabled:
            return
        
        liq = details.get("liquidation_value", 0.0)
        pnl = details.get("day_pnl", 0.0)
        pnl_str = f"+${pnl:,.2f}" if pnl >= 0 else f"-${abs(pnl):,.2f}"
        
        msg = (
            f"💰 *Account Update*\n"
            f"Liquidation: `${liq:,.2f}`\n"
            f"Daily PnL: `{pnl_str}`"
        )
        self.send_message(msg)

    def notify_cooldown(self, cooldown_type: str, duration_sec: int):
        if not self.enabled:
            return
        
        emoji = "❄️" if "PI" in cooldown_type else "🚨"
        msg = (
            f"{emoji} *Cooldown Triggered*\n"
            f"Type: `{cooldown_type}`\n"
            f"Duration: `{duration_sec}s`"
        )
        self.send_message(msg)
