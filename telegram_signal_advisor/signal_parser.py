"""
signal_parser.py

Sends a raw Telegram message to Claude and extracts a structured trade signal.
Handles the wild variety of formats that paid signal channels use.
"""
import json
import logging
import anthropic

log = logging.getLogger("signal_parser")

SYSTEM_PROMPT = """You are a trade signal parser. Your job is to extract structured data
from raw Telegram messages posted by crypto trading signal channels.

You must return ONLY valid JSON — no markdown, no explanation, just the JSON object.

If the message is NOT a trade signal (e.g. it's news, commentary, a meme, or a update
on an existing call), set "valid" to false and stop.

If it IS a trade signal, extract every field you can find. Common formats vary widely:
some use "TP", some use "Target", some use emojis, some give leverage, some don't.
Normalize everything to the output schema below.

Output schema:
{
  "valid": true,
  "symbol": "BTCUSDT",          // Always append USDT if missing. Uppercase.
  "side": "long",               // "long" or "short"
  "entry": 65000.0,             // Use midpoint if a range is given
  "entry_low": 64800.0,         // Optional: low end of entry range
  "entry_high": 65200.0,        // Optional: high end of entry range
  "tp": [66000.0, 67000.0],     // Take profit levels, ascending for long, descending for short
  "sl": 63000.0,                // Stop loss
  "leverage_suggested": 10,     // Leverage from the signal, or null if not mentioned
  "timeframe": "4h",            // Signal timeframe, or null if not mentioned
  "exchange_hint": "bybit",     // Exchange mentioned in signal, or null
  "notes": "..."                // Any extra context worth keeping (brief)
}

If the message is not a trade signal:
{
  "valid": false,
  "reason": "brief explanation"
}"""


async def parse_signal(raw_text: str, api_key: str) -> dict:
    """
    Call Claude to parse a Telegram message into a structured signal.
    Returns a dict. Check signal["valid"] before using.
    """
    client = anthropic.AsyncAnthropic(api_key=api_key)

    try:
        response = await client.messages.create(
            model="claude-opus-4-6",
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": raw_text}],
        )
        raw_json = response.content[0].text.strip()

        # Strip markdown code fences if Claude adds them despite instructions
        if raw_json.startswith("```"):
            raw_json = raw_json.split("```")[1]
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]

        return json.loads(raw_json)

    except json.JSONDecodeError as e:
        log.error("Claude returned invalid JSON: %s", e)
        return {"valid": False, "reason": "JSON parse error from Claude"}
    except Exception as e:
        log.error("Signal parsing failed: %s", e)
        return {"valid": False, "reason": str(e)}
