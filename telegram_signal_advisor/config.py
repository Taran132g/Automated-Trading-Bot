"""Load all configuration from environment variables / .env file."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass


@dataclass
class Config:
    # ── Telegram user account ────────────────────────────────────────────────
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_phone: str = ""

    # ── Anthropic ────────────────────────────────────────────────────────────
    anthropic_api_key: str = ""

    # ── Twilio SMS ───────────────────────────────────────────────────────────
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_to_number: str = ""

    # ── Groups/channels to monitor ───────────────────────────────────────────
    channel_names: List[str] = field(default_factory=list)

    # ── Your Yubit account balance (update manually when it changes) ─────────
    account_balance_usdt: float = 1000.0

    # ── Risk parameters ──────────────────────────────────────────────────────
    max_risk_per_trade_pct: float = 2.0
    max_leverage: int = 20

    def __post_init__(self):
        self.telegram_api_id = int(os.getenv("TELEGRAM_API_ID", 0) or 0)
        self.telegram_api_hash = os.getenv("TELEGRAM_API_HASH", "")
        self.telegram_phone = os.getenv("TELEGRAM_PHONE", "")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_from_number = os.getenv("TWILIO_FROM_NUMBER", "")
        self.twilio_to_number = os.getenv("TWILIO_TO_NUMBER", "")
        self.account_balance_usdt = float(os.getenv("ACCOUNT_BALANCE_USDT", 1000.0))
        self.max_risk_per_trade_pct = float(os.getenv("MAX_RISK_PCT", 2.0))
        self.max_leverage = int(os.getenv("MAX_LEVERAGE", 20))

        channels_str = os.getenv("TELEGRAM_CHANNELS", "")
        if channels_str:
            self.channel_names = [c.strip() for c in channels_str.split(",") if c.strip()]

    def validate(self) -> list[str]:
        errors = []
        if not self.telegram_api_id:
            errors.append("TELEGRAM_API_ID")
        if not self.telegram_api_hash:
            errors.append("TELEGRAM_API_HASH")
        if not self.telegram_phone:
            errors.append("TELEGRAM_PHONE")
        if not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY")
        if not self.channel_names:
            errors.append("TELEGRAM_CHANNELS")
        return errors
