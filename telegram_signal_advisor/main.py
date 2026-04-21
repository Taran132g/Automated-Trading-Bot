"""
main.py — Telegram Signal Advisor (no Claude, pure forward + sizing)

Every message from monitored channels is forwarded to you exactly as-is.
If the message contains an entry price and stop loss, your bet size is
appended automatically (2% risk on $10,000 = $200 risked per trade).

Setup:
    1. Fill in .env
    2. pip install -r requirements.txt
    3. python setup_channels.py  ← find channel IDs
    4. python main.py            ← enter SMS code once, then runs forever
"""
import asyncio
import logging
import sys
from pathlib import Path

# Ensure imports work regardless of where the script is launched from
sys.path.insert(0, str(Path(__file__).parent))

from telethon import TelegramClient, events

from config import Config
from signal_parser import extract_sizing, build_sizing_footer
from signals_db import save_signal, init_db

# Existing Trading Bot notifier (sends to the same bot as your trading alerts)
sys.path.insert(0, str(Path(__file__).parent.parent))
from telegram_notifier import TelegramNotifier
_tg_bot = TelegramNotifier()

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
    raw_text = (event.raw_text or "").strip()
    source = getattr(event.chat, "title", None) or str(event.chat_id)

    # Check if this message has a photo attached
    has_photo = bool(getattr(event.message, "photo", None))

    if not raw_text and not has_photo:
        return

    log.info("[%s] Message (%d chars, photo=%s)", source, len(raw_text), has_photo)

    # ── Try to extract entry/SL and compute bet size ──────────────────────────
    sizing = extract_sizing(
        raw_text,
        balance=config.account_balance_usdt,
        risk_pct=config.max_risk_per_trade_pct,
    ) if raw_text else None

    # ── Build caption: exact channel text + optional sizing footer ────────────
    header = f"📡 *{source}*\n\n"
    body = raw_text or ""
    if sizing:
        body += build_sizing_footer(sizing)
        log.info("[%s] Sizing: entry=%s sl=%s qty=%s", source, sizing['entry'], sizing['sl'], sizing['quantity'])
    else:
        log.info("[%s] Forwarding as-is", source)

    message = header + body

    # ── Save to DB for dashboard ──────────────────────────────────────────────
    if sizing:
        save_signal(
            channel=source,
            sizing={
                "approved": True,
                "symbol": "",
                "side": "",
                "entry": sizing["entry"],
                "entry_low": None,
                "entry_high": None,
                "sl": sizing["sl"],
                "sl_distance_pct": sizing["sl_distance_pct"],
                "tp_levels": sizing["tps"],
                "rr_ratios": [],
                "leverage": 1,
                "quantity": sizing["quantity"],
                "position_size_usdt": sizing["position_size_usdt"],
                "margin_required_usdt": sizing["position_size_usdt"],
                "risk_amount_usdt": sizing["risk_amount"],
                "risk_pct": sizing["risk_pct"],
                "balance_usdt": sizing["balance"],
            },
            trade_card=message,
            approved=True,
        )

    # ── Send via Trading Bot (text) ───────────────────────────────────────────
    _tg_bot.send_message(message)

    # ── If there's a photo, download it and send via bot separately ───────────
    if has_photo:
        try:
            import os, tempfile, requests as req
            photo_bytes = await client.download_media(event.message, bytes)
            bot_token = _tg_bot.bot_token
            chat_id = _tg_bot.chat_id
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            caption = f"📡 *{source}* — chart/image"
            req.post(url, data={"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"},
                     files={"photo": ("signal.jpg", photo_bytes, "image/jpeg")}, timeout=15)
            log.info("[%s] Photo sent", source)
        except Exception as e:
            log.error("[%s] Failed to send photo: %s", source, e)


async def main():
    config = Config()

    missing = config.validate()
    if missing:
        print(f"\nERROR: Missing config: {', '.join(missing)}")
        sys.exit(1)

    init_db()
    log.info("Balance: $%.2f | Risk: %.1f%% ($%.2f) per trade",
             config.account_balance_usdt,
             config.max_risk_per_trade_pct,
             config.account_balance_usdt * config.max_risk_per_trade_pct / 100)

    client = TelegramClient(str(SESSION_FILE), config.telegram_api_id, config.telegram_api_hash)
    await client.start(phone=config.telegram_phone)
    me = await client.get_me()
    log.info("Connected as: %s", me.first_name)

    # Resolve channels by scanning dialogs
    def normalize_id(val: str) -> int | None:
        val = val.strip().lstrip("-")
        if val.startswith("100") and len(val) > 10:
            val = val[3:]
        try:
            return int(val)
        except ValueError:
            return None

    wanted_ids, wanted_usernames = set(), set()
    for ch in config.channel_names:
        ch = ch.strip()
        if ch.startswith("@"):
            wanted_usernames.add(ch.lstrip("@").lower())
        else:
            nid = normalize_id(ch)
            if nid:
                wanted_ids.add(nid)

    channel_entities = []
    log.info("Scanning dialogs...")
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        username = getattr(entity, "username", None)
        if entity.id in wanted_ids or (username and username.lower() in wanted_usernames):
            channel_entities.append(entity)
            log.info("Monitoring: %s", getattr(entity, "title", entity.id))

    if not channel_entities:
        log.error("No channels resolved. Run setup_channels.py.")
        sys.exit(1)

    @client.on(events.NewMessage(chats=channel_entities))
    async def handler(event):
        try:
            await process_message(event, config, client)
        except Exception as e:
            log.exception("Error processing message: %s", e)

    titles = [getattr(e, "title", str(e)) for e in channel_entities]
    startup = (
        f"✅ *Signal Advisor started*\n"
        f"Balance: `${config.account_balance_usdt:,.0f}` | Risk/trade: `${config.account_balance_usdt * config.max_risk_per_trade_pct / 100:,.0f}`\n"
        f"Monitoring {len(channel_entities)} channel(s):\n"
        + "\n".join(f"• _{t}_" for t in titles)
    )
    _tg_bot.send_message(startup)

    log.info("Listening on %d channel(s)...", len(channel_entities))
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Stopped")
