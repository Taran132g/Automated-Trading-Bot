"""
setup_channels.py

Run this ONCE to list all Telegram groups/channels your account is in.
Copy the IDs of your signal channels into TELEGRAM_CHANNELS in .env

Usage:
    cd telegram_signal_advisor
    python setup_channels.py
"""
import asyncio
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.types import Channel, Chat

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from config import Config

SESSION_FILE = Path(__file__).parent / "session.telethon"


async def main():
    config = Config()

    if not config.telegram_api_id or not config.telegram_api_hash:
        print("\nERROR: Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env first")
        return

    print(f"\nConnecting as {config.telegram_phone} ...")
    client = TelegramClient(str(SESSION_FILE), config.telegram_api_id, config.telegram_api_hash)
    await client.start(phone=config.telegram_phone)

    print("\n" + "─" * 60)
    print(f"{'TYPE':<10} {'ID':<20} {'USERNAME':<25} TITLE")
    print("─" * 60)

    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, (Channel, Chat)):
            username = getattr(entity, "username", None)
            username_str = f"@{username}" if username else "(no username)"
            kind = "Channel" if isinstance(entity, Channel) else "Group"
            title = dialog.name or ""
            print(f"{kind:<10} {entity.id:<20} {username_str:<25} {title}")

    print("─" * 60)
    print("\nAdd the IDs or usernames of your signal channels to .env:")
    print("TELEGRAM_CHANNELS=@channel1,-1001234567890,@another")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
