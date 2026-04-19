"""
notifier.py

Sends trade cards to your own Saved Messages in Telegram using the same
Telethon client that reads the signal groups. No bot required.
"""
import logging

log = logging.getLogger("notifier")


async def send_message(text: str, client) -> bool:
    """Send a message to your own Saved Messages (me = yourself)."""
    try:
        await client.send_message("me", text, parse_mode="md")
        return True
    except Exception as e:
        log.error("Failed to send message to Saved Messages: %s", e)
        return False


async def send_error(context: str, detail: str, client):
    await send_message(f"❌ *Error — {context}*\n`{detail}`", client)


async def send_skipped(symbol: str, reason: str, source: str, client):
    await send_message(
        f"ℹ️ *Signal Skipped — {symbol}*\nSource: _{source}_\nReason: {reason}",
        client,
    )
