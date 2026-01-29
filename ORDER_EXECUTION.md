# Execution Strategy: Market Orders Only

This document explains the bot's execution strategy, which prioritizes **speed and certainty of execution** over price improvement.

## Strategy Overview

The bot uses **Market Orders** exclusively.

1.  **Signal Detection**: `grok.py` detects an order book imbalance (e.g., "bid-heavy").
2.  **Instant Dispatch**: The signal is passed directly to `LiveTrader` in the same process (no database polling delay).
3.  **Immediate Execution**: `LiveTrader` immediately submits a Market Order to Schwab.
    *   **Buy/Cover**: Pays the current Ask price.
    *   **Sell/Short**: Accepts the current Bid price.

## Why Market Orders?

*   **Speed**: Market orders are executed instantly. In fast-moving markets (like penny stocks), waiting for a limit order to fill often means missing the move entirely.
*   **Certainty**: A market order guarantees a fill (as long as there is liquidity). Limit orders can be left behind if the price moves away.
*   **Simplicity**: Removes complex logic for repricing, timeout handling, and race conditions, making the bot more robust and less prone to bugs.

## Operational Guardrails

Even with market orders, safety mechanisms are in place:

*   **Kill Switch**: If the file `kill_switch.flag` is detected, the bot cancels all pending actions (if any) and stops immediately.
*   **Rate Limiting**: `LIVE_MAX_TRADES_PER_HOUR` (default: 60) prevents a runaway algorithm from draining your account.
*   **Bad Fill Detection**: The bot monitors fill prices. If it detects "bad fills" (e.g., buying at x.99 or selling at x.01) consecutively, it alerts you.
*   **State Persistence**: Position state is saved to disk (`live_trader_state.json`) after every trade, ensuring the bot remembers its positions even after a restart.

## Configuration

Relevant settings in your `.env` file:

*   `LIVE_DRY_RUN`: Set to `1` or `true` to simulate trades without using real money.
*   `LIVE_POSITION_SIZE`: Number of shares to trade per signal.
*   `LIVE_MAX_TRADES_PER_HOUR`: Safety cap on trading frequency.
