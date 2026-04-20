"""
signal_parser.py

Two Claude calls:
  1. parse_signal()   — is this a new trade signal? Extract structured data.
  2. analyze_update() — for everything else: what does this message mean and
                        what should the trader do right now?
"""
import json
import logging
import anthropic

log = logging.getLogger("signal_parser")

# ── 1. Signal parser ──────────────────────────────────────────────────────────

SIGNAL_PROMPT = """You are a trade signal parser for crypto trading channels.

Return ONLY valid JSON — no markdown, no explanation.

If the message IS a new trade signal (entry + direction posted for the first time),
extract it into this schema:
{
  "valid": true,
  "symbol": "BTCUSDT",
  "side": "long",
  "entry": 65000.0,
  "entry_low": 64800.0,
  "entry_high": 65200.0,
  "tp": [66000.0, 67000.0],
  "sl": 63000.0,
  "leverage_suggested": 10,
  "timeframe": "4h",
  "notes": "..."
}

If it is NOT a new signal (update, close, cancel, move SL, TP hit, news, commentary,
motivational post, or anything else), return:
{
  "valid": false,
  "reason": "one line"
}"""


async def parse_signal(raw_text: str, api_key: str) -> dict:
    client = anthropic.AsyncAnthropic(api_key=api_key)
    try:
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=SIGNAL_PROMPT,
            messages=[{"role": "user", "content": raw_text}],
        )
        raw_json = resp.content[0].text.strip()
        if raw_json.startswith("```"):
            raw_json = raw_json.split("```")[1]
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]
        return json.loads(raw_json)
    except json.JSONDecodeError as e:
        log.error("parse_signal JSON error: %s", e)
        return {"valid": False, "reason": "JSON parse error"}
    except Exception as e:
        log.error("parse_signal failed: %s", e)
        return {"valid": False, "reason": str(e)}


# ── 2. Update analyzer ────────────────────────────────────────────────────────

UPDATE_PROMPT = """You are a personal trading assistant watching signal channels on behalf of a crypto trader.

The trader follows these channels and acts on their calls. When a channel posts any message
(update, close alert, TP hit, SL move, cancel, market commentary, warning, or anything),
you must read it and tell the trader what to do RIGHT NOW with any active position.

Reply in plain Telegram Markdown (*bold*, `code`). Keep it short — 3-5 lines max.

Format:
📢 *[Channel Name] — [one-line summary of what the message says]*

[1-2 sentences: what action the trader should take right now, if any.
If no action needed, say "No action needed — monitor." Be direct.]

If the message is totally irrelevant (meme, joke, off-topic chat with no trading content),
reply with exactly: SKIP

Do not invent prices. Only use what is in the message."""


async def analyze_update(raw_text: str, source_channel: str, api_key: str) -> str | None:
    """
    Analyze a non-signal message and return an action alert, or None if it should be skipped.
    """
    client = anthropic.AsyncAnthropic(api_key=api_key)
    try:
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            system=UPDATE_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Channel: {source_channel}\n\nMessage:\n{raw_text}"
            }],
        )
        text = resp.content[0].text.strip()
        if text == "SKIP":
            return None
        return text
    except Exception as e:
        log.error("analyze_update failed: %s", e)
        return None
