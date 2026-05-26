# TNFund — Automated Trading Bot

An end-to-end intraday trading stack built around a Schwab L2 order-book imbalance scalper, with a React/FastAPI control plane (TNFund / internal codename QUANT_OS), a Telegram signal-advisor sidecar, a dollar-break screener, and a small bench of Claude-powered analyst agents.

The bot streams Schwab market data, detects bid/ask imbalances, sizes positions with a Kelly + price-impact model, executes flip-only entries via Schwab REST (or IBKR), monitors itself for drawdown / staleness / stuck positions, and reports daily and weekly results to Telegram.

> **Disclaimer.** This software places real orders on real brokerage accounts. Run paper-mode first. Read every config flag. Trading is your risk.

---

## Architecture at a glance

```
┌────────────────────┐   L2 imbalance   ┌─────────────────┐
│  Schwab streaming  │ ───────────────► │  grok.py        │
│  (L1 + L2 + bars)  │                  │  alert engine   │
└────────────────────┘                  └────────┬────────┘
                                                 │ in-process callback
                                                 │ (or SQLite alerts table)
                                                 ▼
                              ┌───────────────────────────────────┐
                              │  LiveTrader (live_trader.py)      │
                              │  PaperTrader (paper_trader.py)    │
                              │  flip-only, Kelly-sized           │
                              │  Schwab REST or IBKR executor     │
                              └────────────┬──────────────────────┘
                                           │
                                           ▼
                              ┌───────────────────────────────────┐
                              │  penny_basing.db (SQLite)         │
                              │  alerts │ live_trades │ positions │
                              └────────────┬──────────────────────┘
                                           │
                         ┌─────────────────┼─────────────────────┐
                         ▼                 ▼                     ▼
                ┌────────────────┐ ┌────────────────┐  ┌──────────────────┐
                │ Risk Monitor   │ │ Scalper        │  │ Weekly Review    │
                │ (5-min watch)  │ │ Analyst (4:15) │  │ (Sun 6 PM)       │
                └────────┬───────┘ └────────┬───────┘  └────────┬─────────┘
                         │                  │                   │
                         └────────► Telegram │ Claude reports ◄─┘

           ┌──────────────────────┐    ┌────────────────────────┐
           │ FastAPI (api_server) │ ◄──┤ React UI (quant-os-ui) │
           │ + WebSockets         │    │ Vite + Tailwind        │
           └──────────────────────┘    └────────────────────────┘
```

---

## What's in the repo

### Core trading loop
| File | Role |
|---|---|
| `grok.py` | Stream processor. Subscribes to Schwab L1/L2/bars, computes imbalance, writes `alerts`, dispatches in-process to the trader. |
| `live_trader.py` | Bridges alerts → real Schwab orders. Flip-only sizing, Kelly position multiplier, kill-switch aware. |
| `paper_trader.py` | Same flip-only logic against a simulated fill model. Reads alerts from SQLite. |
| `config_manager.py` | Single source of truth for runtime config (`trading_config.json`). Hot-reloadable via the UI. |
| `data.py` | Schwab quote / history / account helpers. |
| `sql.py` | DB connection helper for `penny_basing.db`. |
| `ws_manager.py` | WebSocket fan-out for the terminal page (live trades, positions, equity). |

### Order execution
| File | Role |
|---|---|
| `live_trader.py` (`SchwabOrderExecutor`) | Default executor — uses `schwab-py` REST. |
| `executors/ibkr.py` (`IBKROrderExecutor`) | Drop-in alternative via `ib_insync`. Switch with `ORDER_EXECUTOR=ibkr`. |

### Control plane (TNFund / QUANT_OS)
| Path | Role |
|---|---|
| `api_server.py` | FastAPI app. Mounts every router under `/api/*`. Serves the built React app from `quant-os-ui/dist`. Boots a WebSocket broadcast loop on startup. |
| `routers/` | Auth (TOTP), terminal (live trades), analytics, paper, comparison, logs, admin, agents, market, signals, screener, telegram, config. |
| `quant-os-ui/` | React + Vite + TypeScript dashboard. Pages: Scalper, Backtest, Comparison, Grok Monitor, AI Agents, Signals, Screener, Admin. |
| `auth_login.py` | Schwab OAuth handshake — refreshes `schwab_tokens.json`. |
| `generate_totp.py` | Generates a TOTP secret for the admin login flow. |

### Reporting agents (Claude-backed)
| File | Cadence | What it does |
|---|---|---|
| `agents/scalper_analyst.py` | Weekdays 4:15 PM ET | Round-trip PnL by symbol / time window / alert direction. Writes a report and Telegrams the summary. |
| `agents/weekly_review.py` | Sunday 6 PM ET | End-of-week review combining trades, alerts, and account equity. |
| `agents/risk_monitor.py` | Every 5 min during market hours | Rule-based watchdog. Stop-loss buffer, stuck positions, stale alerts, rate-limit warnings. Triggers `daily_shutdown.py` if the account stop-loss is breached. |
| `agents/post_market_csv.py` | EOD | Exports trade tape for offline analysis. |
| `agents/base.py` | shared | DB access, report storage, Telegram, Claude call helpers. |
| `run_agent.py` | CLI | `python run_agent.py scalper_analyst|weekly_review|risk_monitor` (used by cron). |

### Sidecar services
- **`telegram_signal_advisor/`** — Telethon client that mirrors messages from monitored Telegram signal channels, auto-appends a 2%-risk position-size footer when a signal contains an entry + stop, persists everything to `signals.db`, and forwards via the same `TelegramNotifier` bot used elsewhere.
- **`dollar-break-screener/`** — Independent Streamlit-based screener with its own SQLite + ingestion pipeline (`dollar-break-screener/ingestion/`, `transform/`, `db/`). Exposes a tab in the TNFund UI via `routers/screener.py`.

### Lifecycle scripts
| Script | What it does |
|---|---|
| `manager.sh start|stop|restart|status` | Top-level backend control. |
| `restart_loop.sh` | Long-running supervisor: relaunches `grok.py`, `paper_trader.py`, `live_trader.py` if they exit. Honors `kill_switch.flag` for clean shutdown. Env-gated by `RUN_PAPER_TRADER`, `RUN_LIVE_TRADER`, `ENABLE_INLINE_DISPATCH`. |
| `start_api.sh` | Starts FastAPI alone on a chosen port. |
| `start_backend.sh` | Wraps `restart_loop.sh` with `nohup`. |
| `stop_backend.sh` | Drops `kill_switch.flag` and kills processes. |
| `start_dev.sh` | Local dev: API on `:8000` + Vite on `:5173` concurrently. |
| `start_ui.sh` | UI only. |
| `daily_shutdown.py` | EOD cleanup — flatten positions, snapshot state. |
| `deploy/setup.sh` | One-shot Ubuntu provisioner: installs Python 3.12, deps, sets cron entries for daily startup/shutdown, installs the `trading-ui.service` systemd unit. |

### Analysis / utilities
`trade_analyzer.py`, `simulate_trailing.py`, `calculate_fees.py`, `extract_training_data.py`, `train_model.py`, `analyze_historical_data.py`, `log_parser.py`, `generate_weekly_report.py`, `latency_check.py`, `remote_check*.py`, `check_cooldowns.py`, `fix_schema.py`, `calc_pi.py`.

---

## Quickstart

### 1. Clone + install
```bash
git clone https://github.com/Taran132g/Automated-Trading-Bot.git
cd Automated-Trading-Bot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd quant-os-ui && npm install && npm run build && cd ..
```

### 2. Configure `.env`

Minimum required:

```bash
# Schwab API
SCHWAB_CLIENT_ID=...
SCHWAB_CLIENT_SECRET=...
SCHWAB_REDIRECT_URI=https://127.0.0.1:8182/
SCHWAB_ACCOUNT_ID=...          # paper account hash to start
TOTP_SECRET=...                # generate with generate_totp.py

# Telegram (optional but recommended)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# Claude (only needed for agent reports)
ANTHROPIC_API_KEY=...

# Runtime flags
RUN_PAPER_TRADER=1
RUN_LIVE_TRADER=0              # leave 0 until you've validated paper
ENABLE_INLINE_DISPATCH=1       # grok calls trader in-process (lower latency)
LIVE_DRY_RUN=true              # extra safety belt — logs orders, doesn't submit

# Optional: IBKR instead of Schwab for execution
# ORDER_EXECUTOR=ibkr
# IBKR_HOST=127.0.0.1
# IBKR_PORT=7497                # 7497=paper TWS, 7496=live, 4002=paper Gateway, 4001=live
# IBKR_CLIENT_ID=10
```

`trading_config.json` controls the strategy parameters (symbols, position sizes, Kelly settings, account stop-loss). It is editable from the UI's Admin page.

### 3. First-time Schwab auth
```bash
python auth_login.py
```
This opens the OAuth flow and writes `schwab_tokens.json`. The UI's Admin page can re-trigger this later.

### 4. Run

**Local development:**
```bash
./start_dev.sh
# API → http://localhost:8000
# UI  → http://localhost:5173
```

**Production-style on a server:**
```bash
./manager.sh start          # starts grok + paper/live traders under restart loop
./start_api.sh 8000 &       # starts FastAPI + built UI
```

**Cron-driven schedule (set up by `deploy/setup.sh`):**
- 10:30 AM ET — `daily_startup.py`
- 3:58 PM ET — `daily_shutdown.py`
- Plus the three reporting agents at their cadences above.

---

## Safety

- **Kill switch.** Drop `kill_switch.flag` in the repo root; the supervisor stops relaunching and `live_trader` will refuse new entries.
- **`LIVE_DRY_RUN=true`.** Executor logs orders without submitting them. Use this for the first full session in live mode.
- **Risk Monitor agent.** Watches account equity vs `account_stop_loss` (configurable in `trading_config.json`). If the account hits the threshold, it calls `daily_shutdown.py` to flatten and stop.
- **Telegram alerts.** Every fill, every stuck position, every staleness condition pings the configured chat.

---

## The UI (TNFund dashboard)

Served at `http://localhost:8000` in production, `http://localhost:5173` in dev.

| Route | Page |
|---|---|
| `/scalper` | Live scalping trades, positions, equity curve |
| `/backtest` | Strategy backtests on historical alerts |
| `/comparison` | Scalper analytics (round-trip stats by direction, symbol, time) |
| `/grok` | Grok stream monitor — alert flow, latency |
| `/agents` | Trigger / view agent reports |
| `/signals` | Telegram signal advisor — raw messages, parsed entries, bet sizing |
| `/screener` | Dollar-break screener output |
| `/admin` | Schwab token refresh, config edits, backend start/stop, logs |

Login uses TOTP (`TOTP_SECRET` from `.env`, set up with `generate_totp.py`).

---

## Configuration reference (`trading_config.json`)

| Key | Meaning |
|---|---|
| `live_symbols`, `paper_symbols` | Comma-separated tickers per environment |
| `live_position_size`, `paper_position_size` | Base share count per trade |
| `live_max_trades_per_hour` | Hard cap; risk monitor warns at 80% |
| `account_stop_loss` | Equity floor; risk monitor flattens below this |
| `kelly_enabled`, `kelly_fraction`, `kelly_min_trades`, `kelly_lookback_days` | Kelly sizing parameters |
| `kelly_min_multiplier`, `kelly_max_multiplier` | Bounds on the Kelly multiplier |
| `pi_neutral`, `pi_kelly_weight` | Price-impact dampening of Kelly size |
| `time_stop_seconds` | Per-trade max hold |

Pattern-strategy keys (`pattern_*`) are present in the config object but the pattern engine itself was removed in commit `16e8933`. They are harmless leftovers and the comparison page now reads pure scalper data.

---

## Tech stack

- **Backend:** Python 3.12, FastAPI, `schwab-py`, `ib_insync`, `pandas`, `pytz`, `pyotp`, SQLite, `anthropic`
- **Frontend:** React 18, TypeScript, Vite, TailwindCSS, lucide-react
- **Sidecars:** Telethon (Telegram client), Streamlit (screener dashboard)
- **Infra:** systemd (`deploy/trading-ui.service`), cron-driven daily lifecycle, restart-loop supervisor

---

## Repo conventions

- Anything in `.gitignore` is local-only — most notably `.env`, `*.db`, `*.log`, `schwab_tokens.json`, `*_state.json`, `kill_switch.flag`, and CSV/HTML/PNG exports. The `training_data.csv` in the tree is the one tracked exception.
- `.old_live_trader.py` is the legacy single-file trader kept for reference; the live system uses `live_trader.py`.
- `CHANGES.md` documents the (since-removed) pattern strategy build-out — useful as an architectural reference, not as a current spec.

---

## License

No license file is currently included — treat as all rights reserved. Add one before sharing.
