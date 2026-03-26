# Session Changes — Pattern Strategy Build-Out

All changes made during this session. Read this file to understand the full architecture of the pattern strategy and what was modified.

---

## 1. Pattern Strategy Separated from Scalping (`pattern_trader.py` — NEW FILE)

The pattern strategy was fully separated from the scalping strategy into an independent file. Two strategies now run side by side:

| | Scalping | Pattern |
|---|---|---|
| Signal source | L2 order book imbalance | Chart pattern breakout (1-min bars) |
| Entry trigger | L2 imbalance alert | Bar-close confirmation |
| Position sizing | Kelly + PI/share adjustment | Kelly only (no PI) |
| Exits | Flip-only on opposing signal | Multi-stop cascade |
| DB tables | `live_trades`, `live_positions` | `pattern_trades`, `pattern_positions` |
| State file | `live_trader_state.json` | `pattern_trader_state.json` (live), `pattern_trader_paper_state.json` (paper) |

### PatternPosition dataclass fields
```
symbol, direction (+1/-1), qty, entry_price, entry_time, pattern,
target_level, stop_level, atr_stop, breakout_level, hold_seconds,
trailing_active, trailing_stop, partial_taken, best_price
```

### Exit cascade (checked in order)
1. **Pattern failure stop** — price retreats through `stop_level` (geometric stop from signal)
2. **ATR stop** — fixed level computed at entry: `entry ± (1.5 × ATR)`, never moves
3. **Trailing stop** — activates after partial profit OR after 0.5% move in favor; anchored at `breakout_level`, ratchets 0.3% behind best price
4. **Partial profit** — closes 50% at midpoint to target, activates trailing stop for free trade on remainder
5. **Price target** — measured-move `target_level` from `PatternSignal`
6. **Time stop** — pattern-derived hold: `(end_idx - start_idx) × 60s`, capped by `pattern_hold_seconds` config, floored at 5 min

### ATR dual-purpose
- **Entry filter**: if `ATR / price > pattern_atr_entry_max_pct` (default 0.5%), tape is noisy → skip entry
- **Exit stop**: fixed level at entry ± (1.5 × ATR) — supplements geometric stops with a volatility floor

### Kelly without PI
Plain Kelly criterion using win rate + reward/risk from `pattern_trades` DB. No PI/share adjustment (scalping keeps PI).

### 0.5-second live exit polling
- Background daemon thread polls every 0.5s
- `_fetch_live_price()` reads from `_last_price` dict (populated from stream via `update_live_price()`) — zero HTTP cost
- Falls back to `executor.fetch_quote()` HTTP only on cold start before stream data arrives
- When stop level hit: calls `executor.submit_market(symbol, qty, side)` — real Schwab market order
- Telegram notification fired in daemon thread on full close (live mode only, zero latency impact)

### Live vs paper mode
- `PatternTrader(mode="live")` — uses `pattern_trades`/`pattern_positions`, fires real orders
- `PatternTrader(mode="paper")` — uses `pattern_trades_paper`/`pattern_positions_paper`, simulates fills
- Both run simultaneously; only live gets executor attached

### Cooldown
- 5 minutes (`COOLDOWN_AFTER_EXIT = 300`) after any full exit before re-entering same symbol

---

## 2. `config_manager.py` — Pattern Config Keys Added

```python
"pattern_symbols": "",                   # symbols for pattern strategy
"pattern_live_position_size": 100,       # shares per live trade
"pattern_paper_position_size": 1000,     # shares per paper trade
"pattern_min_confidence": 0.60,          # min breakout confidence to enter
"pattern_hold_seconds": 1800,            # MAX hold time cap (actual is pattern-derived)
"pattern_atr_period": 14,
"pattern_atr_entry_max_pct": 0.005,      # 0.5% max ATR/price ratio at entry
"pattern_atr_stop_multiplier": 1.5,
"pattern_kelly_enabled": True,
"pattern_kelly_fraction": 0.5,
"pattern_kelly_min_trades": 10,
"pattern_kelly_lookback_days": 30,
"pattern_kelly_min_multiplier": 0.25,
"pattern_kelly_max_multiplier": 2.0,
```

---

## 3. `grok.py` — Pattern Trader Wiring + Latency Fixes

### Pattern trader wiring
- Two globals: `PATTERN_TRADER` (live) and `PATTERN_TRADER_PAPER` (paper)
- Both initialized at startup via `PatternTrader(mode=...)`
- Executor wired to live instance only: `PATTERN_TRADER.set_executor(executor_for_backfill)`
- Both called on every bar close in **parallel threads** (fire-and-forget, no blocking wait)
- L1 stream prices fed to both traders via `update_live_price(sym, price)` on every tick — eliminates HTTP polling for price

### Latency fixes applied
| Fix | Before | After |
|---|---|---|
| `ThreadPoolExecutor` per alert | New pool created on every alert | `_TRADER_POOL` created once at startup |
| `ThreadPoolExecutor` per bar close | New pool every minute per symbol | `_PATTERN_BAR_POOL` created once, fire-and-forget |
| `ThreadPoolExecutor` in profit monitor | New pool every **0.5s** | Reuses `_TRADER_POOL` |
| `import concurrent.futures` | Inside hot loops | Top-level import |
| `import datetime as _dt` + 4× `datetime.now()` | Inside `check_imbalance()`, every L2 update | `datetime.now(ET_TZ)` using module-level pytz timezone |
| `IMBALANCE_DEBUG` log | Unconditional on every L2 event | Gated behind `if DEBUG` |
| Alert ID | `SELECT MAX(rowid) FROM alerts` per alert | In-memory counter initialized from DB at startup |
| `import json` / `from pathlib import Path` inside `on_book()` | Redundant re-imports in hot path | Removed (already top-level) |

---

## 4. `routers/config_router.py` — Pattern Config Endpoint

```
GET  /api/config/pattern   → returns PatternConfig
PUT  /api/config/pattern   → saves pattern config fields
```

`PatternConfig` Pydantic model fields:
```
pattern_symbols, pattern_live_position_size, pattern_paper_position_size,
pattern_kelly_enabled, pattern_kelly_fraction, pattern_kelly_min_trades,
pattern_kelly_lookback_days, pattern_kelly_min_multiplier, pattern_kelly_max_multiplier
```

Both scalping and pattern `PUT` endpoints now **merge** with existing config (not overwrite) so saving one doesn't wipe the other's keys.

---

## 5. `routers/patterns.py` — Mode-Aware Endpoints

All three endpoints accept `?mode=live` (default) or `?mode=paper`:

```
GET /api/patterns/state?mode=live|paper
GET /api/patterns/equity-curve?range=today|all&mode=live|paper
GET /api/patterns/performance?mode=live|paper
```

Internal `_resolve_tables(mode)` helper returns `(trades_table, positions_table, state_path)` based on mode.

---

## 6. Frontend Pages (`quant-os-ui/src/`)

### Route map (after changes)
| Route | Page | Data source |
|---|---|---|
| `/scalper` | Scalper (was Terminal) | Live scalping trades |
| `/pattern` | Pattern Strategy (NEW) | Live pattern trades |
| `/patterns` | Pattern Lab | Paper pattern simulation |
| `/backtest` | Backtest | unchanged |
| `/comparison` | Comparison | unchanged |
| `/grok` | Grok Monitor | unchanged |
| `/agents` | AI Agents | unchanged |
| `/admin` | Admin | unchanged |

### `PatternPage.tsx` (NEW — `/pattern`)
- Live pattern data via `patternService.getState('live')` etc.
- Purple accent `#A855F7`
- "LIVE" green badge in header

### `PatternLabPage.tsx` (UPDATED — `/patterns`)
- Now uses paper data: `patternService.getState('paper')` etc.
- Blue accent `#3B82F6` to visually distinguish from live
- Title changed to "PATTERN LAB"

### `TerminalPage.tsx` (UPDATED)
- Page header renamed from "EXECUTION TERMINAL" to "SCALPER"
- No logic changes

### `Sidebar.tsx` (UPDATED)
- "Terminal" → "Scalper" (`/scalper`)
- Added "Pattern" nav item with `BarChart2` icon (`/pattern`)
- "Pattern Lab" stays with `FlaskConical` icon (`/patterns`)

### `services/api.ts` (UPDATED)
- `patternService` now accepts `mode` param on all three methods
- `patternConfigService` for pattern admin config (GET/PUT `/config/pattern`)

---

## 7. `telegram_notifier.py` — Used by Pattern Trader

`TelegramNotifier` already existed. Pattern trader now uses it to send on full position close (live mode only):

```
✅/🔴 Pattern Trade Closed
Symbol: AAL (LONG)
Pattern: cup_and_handle
Entry: $14.2300 → Exit: $14.5100
Qty: 100 | PnL: +$28.00
Reason: target
Daily PnL: +$43.50
Cooldown: 5 min on AAL
```

Telegram call runs in daemon thread — zero latency impact on exit path.

---

## 8. Pattern Hold Time — Pattern-Derived

`pattern_hold_seconds` config is now a **cap**, not a fixed value.

Each trade's time stop is computed from the signal's formation width:
```python
pattern_bars = sig.end_idx - sig.start_idx
hold_secs = max(300, min(pattern_bars * 60, max_hold_secs))
```

- Min: 5 minutes
- Max: `pattern_hold_seconds` config (default 1800 = 30 min)
- A 23-bar pattern → 23-minute hold

Logged on every entry: `[PatternTrader:live] AAL pattern_bars=23 → hold=1380s (cap=1800s)`

---

## Key Files Reference

| File | Role |
|---|---|
| `pattern_trader.py` | Standalone pattern breakout trader (live + paper) |
| `chart_pattern_detector.py` | Emits `PatternSignal` with breakout/confidence/target/stop/levels |
| `live_trader.py` | Scalping strategy (L2 imbalance, flip-only) — unchanged |
| `grok.py` | Main stream processor — wires both strategies, latency-optimized |
| `config_manager.py` | All config keys including pattern-specific ones |
| `routers/patterns.py` | API for Pattern/PatternLab UI pages |
| `routers/config_router.py` | Admin config API for scalping + pattern |
| `telegram_notifier.py` | Telegram alerts (pre-existing, now used by pattern trader) |
| `quant-os-ui/src/pages/PatternPage.tsx` | Live pattern UI page |
| `quant-os-ui/src/pages/PatternLabPage.tsx` | Paper pattern simulation UI |
| `quant-os-ui/src/pages/TerminalPage.tsx` | Scalper (live scalping trades) |
