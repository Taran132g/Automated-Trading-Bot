"""
main.py — Telegram Signal Advisor

Listens to configured Telegram groups/channels, parses each message with Claude,
calculates personalized risk parameters, and sends trade cards to your own
Telegram Saved Messages — no bot required.

First-time setup:
    1. Copy .env.example → .env and fill in your credentials
    2. pip install -r requirements.txt
    3. python setup_channels.py    ← find your trading group's ID
    4. python main.py              ← enter SMS code once, then it runs forever

When your Yubit balance changes, update ACCOUNT_BALANCE_USDT in .env and restart.
"""
import asyncio
import logging
import sys
from pathlib import Path

from telethon import TelegramClient, events

from config import Config
from signal_parser import parse_signal
from risk_manager import assess_risk
from notifier import send_message, send_error
from signals_db import save_signal, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path(__file__).parent / "advisor.log"),
    ],
)
log = logging.getLogger("main")

SESSION_FILE = Path(__file__).parent / "session.telethon"


async def process_message(event, config: Config, client: TelegramClient):
    raw_text = event.raw_text or ""
    if not raw_text.strip():
        return

    source = getattr(event.chat, "title", None) or str(event.chat_id)
    log.info("[%s] New message (%d chars)", source, len(raw_text))

    # ── 1. Parse with Claude ──────────────────────────────────────────────────
    signal = await parse_signal(raw_text, config.anthropic_api_key)

    if not signal.get("valid"):
        log.debug("[%s] Not a trade signal: %s", source, signal.get("reason", ""))
        return  # silently ignore non-signal messages

    log.info(
        "[%s] Signal: %s %s | Entry: %s | SL: %s | TP: %s",
        source,
        signal.get("side", "?").upper(),
        signal.get("symbol", "?"),
        signal.get("entry"),
        signal.get("sl"),
        signal.get("tp"),
    )

    # ── 2. Risk calculation + trade card ─────────────────────────────────────
    result = await assess_risk(
        signal=signal,
        config=config,
        source_channel=source,
        raw_signal_text=raw_text,
    )

    # ── 3. Save to DB (powers the dashboard UI) ──────────────────────────────
    save_signal(
        channel=source,
        sizing=result["sizing"],
        trade_card=result["message"],
        approved=result["sizing"].get("approved", False),
    )

    # ── 4. Send to your Saved Messages ───────────────────────────────────────
    await send_message(result["message"], client)
    log.info("[%s] Trade card sent for %s", source, signal.get("symbol"))


async def main():
    config = Config()

    missing = config.validate()
    if missing:
        print(f"\nERROR: Missing required config: {', '.join(missing)}")
        print("Copy .env.example → .env and fill in all values.\n")
        sys.exit(1)

    init_db()
    log.info(
        "Balance: $%.2f USDT | Max risk: %.1f%% per trade | Max leverage: %dx",
        config.account_balance_usdt,
        config.max_risk_per_trade_pct,
        config.max_leverage,
    )

    # Connect as your Telegram user account
    client = TelegramClient(
        str(SESSION_FILE),
        config.telegram_api_id,
        config.telegram_api_hash,
    )
    await client.start(phone=config.telegram_phone)
    me = await client.get_me()
    log.info("Connected as: %s (@%s)", me.first_name, me.username)

    # Resolve channels by iterating your dialogs — works for private channels too
    # Config can contain usernames (@foo) or numeric IDs (1228412803 or -1001228412803)
    def normalize_id(val: str) -> int | None:
        val = val.strip().lstrip("-")
        # Strip the -100 supergroup prefix if present
        if val.startswith("100") and len(val) > 10:
            val = val[3:]
        try:
            return int(val)
        except ValueError:
            return None

    wanted_ids = set()
    wanted_usernames = set()
    for ch in config.channel_names:
        ch = ch.strip()
        if ch.startswith("@"):
            wanted_usernames.add(ch.lstrip("@").lower())
        else:
            nid = normalize_id(ch)
            if nid:
                wanted_ids.add(nid)

    channel_entities = []
    log.info("Scanning your dialogs to find the configured channels...")
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        eid = entity.id
        username = getattr(entity, "username", None)
        title = getattr(entity, "title", "")
        if eid in wanted_ids or (username and username.lower() in wanted_usernames):
            channel_entities.append(entity)
            log.info("Monitoring: %s (id=%s)", title, eid)

    if not channel_entities:
        log.error("No channels matched. Check TELEGRAM_CHANNELS in .env — use the raw IDs from setup_channels.py without the -100 prefix.")
        sys.exit(1)

    @client.on(events.NewMessage(chats=channel_entities))
    async def handler(event):
        try:
            await process_message(event, config, client)
        except Exception as e:
            log.exception("Unhandled error: %s", e)
            await send_error("Message processing", str(e), client)

    # Startup confirmation in Saved Messages
    titles = [getattr(e, "title", str(e)) for e in channel_entities]
    await send_message(
        f"✅ *Signal Advisor started*\n"
        f"Balance: `${config.account_balance_usdt:,.2f} USDT`\n"
        f"Risk per trade: `{config.max_risk_per_trade_pct}%`  |  Max leverage: `{config.max_leverage}x`\n"
        f"Monitoring {len(channel_entities)} group(s):\n"
        + "\n".join(f"• _{t}_" for t in titles),
        client,
    )

    log.info("Listening on %d group(s)... (Ctrl+C to stop)", len(channel_entities))
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Stopped by user")
