"""
risk_manager.py

Two steps:
  1. calculate_sizing()  — pure Python math, deterministic
  2. format_trade_card() — Claude writes the personalized Telegram message
                           including reasoning and risk assessment

Risk model:
  - Risk amount  = balance * max_risk_pct / 100
  - SL distance% = |entry - sl| / entry
  - Position size USDT = risk_amount / sl_distance_pct
  - Leverage = min(signal suggestion, max_leverage config)
  - Margin required = position_size / leverage
"""
import json
import logging
import anthropic

from config import Config

log = logging.getLogger("risk_manager")


def calculate_sizing(signal: dict, config: Config) -> dict:
    """
    Pure math — returns a sizing dict.
    `approved` is False if the signal is missing critical data.
    """
    entry = float(signal.get("entry", 0))
    sl = float(signal.get("sl", 0))
    balance = config.account_balance_usdt

    if entry <= 0:
        return {"approved": False, "reason": "Signal is missing an entry price"}
    if sl <= 0:
        return {"approved": False, "reason": "Signal is missing a stop loss"}
    if balance <= 0:
        return {"approved": False, "reason": "ACCOUNT_BALANCE_USDT is not set in .env"}

    # ── SL distance ───────────────────────────────────────────────────────────
    sl_distance_pct = abs(entry - sl) / entry
    if sl_distance_pct == 0:
        return {"approved": False, "reason": "Entry and SL are the same price"}

    # ── Position sizing ───────────────────────────────────────────────────────
    risk_amount_usdt = balance * config.max_risk_per_trade_pct / 100
    position_size_usdt = risk_amount_usdt / sl_distance_pct
    actual_risk_pct = risk_amount_usdt / balance * 100

    # ── Quantity (coins/contracts to buy) ─────────────────────────────────────
    # This is the number you enter directly into Yubit's order form.
    quantity = position_size_usdt / entry

    # ── Leverage ──────────────────────────────────────────────────────────────
    leverage_suggested = int(signal.get("leverage_suggested") or 10)
    leverage = min(leverage_suggested, config.max_leverage)
    margin_required_usdt = position_size_usdt / leverage

    # ── Risk/Reward per TP level ──────────────────────────────────────────────
    tp_levels = [float(t) for t in signal.get("tp", [])]
    rr_ratios = []
    for tp in tp_levels:
        profit = abs(tp - entry)
        rr = round(profit / abs(entry - sl), 2) if entry != sl else 0
        rr_ratios.append(rr)

    return {
        "approved": True,
        "symbol": signal.get("symbol", "UNKNOWN"),
        "side": signal.get("side", "unknown"),
        "entry": entry,
        "entry_low": signal.get("entry_low"),
        "entry_high": signal.get("entry_high"),
        "sl": sl,
        "sl_distance_pct": round(sl_distance_pct * 100, 2),
        "tp_levels": tp_levels,
        "rr_ratios": rr_ratios,
        "leverage": leverage,
        "quantity": round(quantity, 4),          # coins/contracts to enter on Yubit
        "position_size_usdt": round(position_size_usdt, 2),
        "margin_required_usdt": round(margin_required_usdt, 2),
        "risk_amount_usdt": round(risk_amount_usdt, 2),
        "risk_pct": round(actual_risk_pct, 2),
        "balance_usdt": round(balance, 2),
        "signal_timeframe": signal.get("timeframe"),
        "signal_notes": signal.get("notes", ""),
    }


CARD_SYSTEM = """You are a personal crypto risk manager and trading assistant.

You receive JSON with:
- The parsed trade signal (symbol, side, entry, TP levels, SL, timeframe, notes)
- The calculated risk parameters (position size in USDT, quantity in coins, leverage, margin, risk %, R:R ratios)
- The trader's account balance on Yubit
- The source group/channel and a snippet of the original raw message

Write a Telegram trade card using Markdown (*bold*, `code`). Structure it exactly like this:

[Side emoji: 🟢 for long, 🔴 for short] *SYMBOL — SIDE*
*Source:* _group/channel name_

*📐 Entry*
`X` *(or `Low: X  High: X` if a range is given)*

*🎯 Targets*
`TP1: X` → R:R `1:Y`
`TP2: X` → R:R `1:Y`
*(list all TPs with R:R)*

*🛑 Stop Loss:* `X` *(SL distance: X%)*

*💰 Your Order (Yubit)*
Qty to buy: `X coins`
Position value: `$X USDT`  |  Leverage: `Xx`
Margin required: `$X USDT`
Risk: `$X` (`X%` of your $X balance)

*🧠 Claude's Take*
Write 3-5 sentences of honest, specific reasoning:
- Summarise what the signal is saying and why the group may have posted it.
- Is the R:R attractive or poor? Be specific about the numbers.
- Does the SL distance make sense — is it tight (quick stop-out risk) or wide (larger loss if wrong)?
- One concrete thing to watch that could invalidate the trade.
Do NOT hype the trade. If the R:R is poor or the SL is dangerously tight, say so plainly.

Be direct and specific. No generic advice. Only use numbers from the JSON — do not invent anything."""


async def format_trade_card(sizing: dict, source_channel: str, raw_signal_text: str, api_key: str) -> str:
    """Use Claude to write the trade card with genuine reasoning."""
    client = anthropic.AsyncAnthropic(api_key=api_key)

    payload = {
        "source_channel": source_channel,
        "sizing": sizing,
        "raw_signal_excerpt": raw_signal_text[:500],
    }

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=700,
            system=CARD_SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, indent=2)}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        log.error("Failed to format trade card: %s", e)
        # Fallback plain card if Claude call fails
        s = sizing
        tp_str = "  ".join(f"`TP{i+1}: {t}`" for i, t in enumerate(s["tp_levels"])) or "Not given"
        rr_str = " / ".join(f"1:{r}" for r in s["rr_ratios"]) or "N/A"
        lines = [
            f"{'🟢' if s['side'] == 'long' else '🔴'} *{s['symbol']} — {s['side'].upper()}*",
            f"*Source:* _{source_channel}_",
            f"Entry: `{s['entry']}`  |  SL: `{s['sl']}` ({s['sl_distance_pct']}%)",
            tp_str,
            f"R:R: {rr_str}",
            f"*Qty to buy:* `{s['quantity']} coins`",
            f"Position: `${s['position_size_usdt']:,.0f}` USDT  |  Leverage: `{s['leverage']}x`",
            f"Margin: `${s['margin_required_usdt']:,.0f}` USDT",
            f"Risk: `${s['risk_amount_usdt']:,.0f}` ({s['risk_pct']:.1f}% of ${s['balance_usdt']:,.0f})",
        ]
        return "\n".join(lines)


async def assess_risk(
    signal: dict,
    config: Config,
    source_channel: str,
    raw_signal_text: str,
) -> dict:
    """Full pipeline: size the trade, then generate the trade card with reasoning."""
    sizing = calculate_sizing(signal, config)

    if not sizing["approved"]:
        message = (
            f"⚠️ *Signal Skipped — {signal.get('symbol', 'Unknown')}*\n"
            f"Source: _{source_channel}_\n"
            f"Reason: {sizing['reason']}"
        )
        return {"message": message, "sizing": sizing}

    message = await format_trade_card(
        sizing=sizing,
        source_channel=source_channel,
        raw_signal_text=raw_signal_text,
        api_key=config.anthropic_api_key,
    )
    return {"message": message, "sizing": sizing}
