# Schwab Trading Bot - System Documentation

This project is an automated trading system that connects to the Charles Schwab API to trade stocks based on order book imbalances. It consists of four main components running in parallel.

## 🚀 Quick Start

To start the entire system (Data Stream, Paper Trader, Live Trader, and UI):

```bash
./run_both.sh
```

To stop the system, press `CTRL+C` in the terminal.

---

## 🏗 System Architecture

The system is composed of four Python scripts managed by `run_both.sh`:

1.  **`grok.py` (The Brain)**:
    *   Connects to Schwab's streaming API.
    *   Monitors Level 1 (Quotes) and Level 2 (Order Book) data.
    *   Detects "Ask-Heavy" (Bearish) or "Bid-Heavy" (Bullish) imbalances.
    *   Generates alerts and saves them to `penny_basing.db`.
    *   Dispatches alerts directly to the trader.

2.  **`paper_trader.py` (Simulation)**:
    *   Simulates trading based on alerts without using real money.
    *   Tracks a virtual cash balance and positions.
    *   Useful for verifying strategy performance safely.

3.  **`live_trader.py` (Execution)**:
    *   Receives alerts from `grok.py`.
    *   Executes **Real Money** trades on your Schwab account.
    *   Manages orders (Buy, Sell, Short, Cover).

4.  **`app.py` (Dashboard)**:
    *   A Streamlit-based web dashboard.
    *   Displays live PnL, active positions, and trade history.
    *   Accessible at `http://localhost:8501`.

---

## 🧠 How It Works (The Brain)

The core logic lives in `grok.py`. It uses **Level 2 (Order Book)** data to detect supply/demand imbalances across multiple exchanges.

### Imbalance Detection Algorithm
1.  **Venue Validation**: The system looks at every exchange (NYSE, NASDAQ, MEMX, etc.) individually.
    *   A venue is considered **"Valid"** only if its Bid-Ask spread is tight (default: **≤ 1 cent**).
    *   If the spread is too wide, that exchange is ignored.
2.  **Venue Voting**: For each valid venue, it compares Bid Volume vs. Ask Volume.
    *   **Bid-Heavy**: Bid Volume > Ask Volume.
    *   **Ask-Heavy**: Ask Volume > Bid Volume.
3.  **Consensus**: It counts how many venues are Bid-Heavy vs. Ask-Heavy.
    *   **Threshold**: It requires a net difference of **4 venues** (or **3 venues** between 3 PM - 4 PM).
    *   *Example*: If 6 venues are Bid-Heavy and 1 is Ask-Heavy, the difference is 5. Since 5 ≥ 4, it triggers a **Bid-Heavy (Buy)** signal.

---

## 🛡 System Constraints & Safety Checks

The system enforces strict constraints to ensure trade quality and safety.

### 1. `grok.py` (Signal Quality)
*   **Minimum Volume**: The stock must be trading at least **100,000 shares/minute**.
*   **Imbalance Duration**: The imbalance must persist for at least **10 seconds** before alerting.
*   **Minimum Venues**: At least **4 valid exchanges** must be participating.
*   **Throttle**: Limits alerts to **one per 60 seconds** per symbol to prevent spamming.

### 2. `live_trader.py` (Execution Safety)
*   **Flip-Only Logic**:
    *   **No Stacking**: If you are already Long, it ignores new Buy signals. It only acts on Sell signals to flip Short.
    *   **Always in the Market**: It flips from Long → Short or Short → Long.
*   **Bad Fill Protection**:
    *   **Kill Switch**: If a Buy fills at `x.99` or a Sell fills at `x.01`, the bot **immediately shuts down**. This protects against trading against market makers who pin prices.
*   **Time Stops**:
    *   Any position held for more than **10 minutes** is automatically closed (Market Sell/Cover).
*   **Rate Limiting**:
    *   Maximum **60 trades per hour**. If exceeded, the system performs an emergency shutdown (closes all positions and exits).

---

## ⚙️ Configuration & Parameters

The system is configured via environment variables in `run_both.sh` and your `.env` file.

### 1. `run_both.sh` (Main Config)
Modify these variables in the `run_both.sh` file to change trading behavior:

*   **`SYMBOLS`**: A comma-separated list of stock tickers to trade.
    *   *Example*: `export SYMBOLS="F,AAL,BBAI"`
*   **`POSITION_SIZE`**: The number of shares to trade per signal.
    *   *Example*: `export POSITION_SIZE=1666` (Trades 1666 shares per buy/short).
*   **`LIVE_DRY_RUN`**: Safety switch for live trading.
    *   `1`: **Dry Run Mode**. Logs what it *would* do but sends NO orders to Schwab.
    *   `0`: **Live Mode**. Sends REAL orders with REAL money.

### 2. `.env` (Credentials)
This file (not committed to git) holds your secrets. **Do not share this file.**

*   `SCHWAB_CLIENT_ID`: Your Schwab App Key.
*   `SCHWAB_APP_SECRET`: Your Schwab App Secret.
*   `SCHWAB_REDIRECT_URI`: The callback URL set in your Schwab Developer Portal (usually `https://127.0.0.1:8182/`).
*   `SCHWAB_ACCOUNT_ID`: The encrypted Account Hash ID for the account you want to trade in.

---

## 🛠 Helper Scripts

*   **`auth_login.py`**:
    *   Run this manually if your token expires (every 7 days).
    *   Command: `python3 auth_login.py`
    *   Follow the prompts to log in via browser and authorize the app.

*   **`calculate_fees.py`**:
    *   Analyzes your trade history to estimate fees and calculate hourly PnL.
    *   Command: `python3 calculate_fees.py`

---

## ⚠️ Important Notes

1.  **Token Expiration**: Schwab tokens expire every 7 days. If the app crashes with a "401 Unauthorized" error, run `python3 auth_login.py` to refresh your token.
2.  **Market Hours**: The bot is designed for active market hours. Liquidity and spreads can be volatile pre/post-market.
3.  **Risk Warning**: This is an automated trading system. Always monitor it when running in Live Mode (`LIVE_DRY_RUN=0`).
