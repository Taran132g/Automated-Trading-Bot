"""WebSocket connection manager for broadcasting live trading data."""
import asyncio
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Set
from fastapi import WebSocket

BASE_DIR = Path(__file__).parent.resolve()
DB_PATH = BASE_DIR / "penny_basing.db"
LIVE_STATE_PATH = BASE_DIR / "live_trader_state_primary.json"
if not LIVE_STATE_PATH.exists():
    LIVE_STATE_PATH = BASE_DIR / "live_trader_state.json"
LOG_PATH = BASE_DIR / "grok.log"


class ConnectionManager:
    def __init__(self):
        self.terminal_connections: Set[WebSocket] = set()
        self.log_connections: Set[WebSocket] = set()

    async def connect_terminal(self, ws: WebSocket):
        await ws.accept()
        self.terminal_connections.add(ws)

    def disconnect_terminal(self, ws: WebSocket):
        self.terminal_connections.discard(ws)

    async def connect_log(self, ws: WebSocket):
        await ws.accept()
        self.log_connections.add(ws)

    def disconnect_log(self, ws: WebSocket):
        self.log_connections.discard(ws)

    async def broadcast_terminal(self, data: dict):
        dead = set()
        for ws in list(self.terminal_connections):
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self.terminal_connections -= dead

    async def broadcast_log(self, data: dict):
        dead = set()
        for ws in list(self.log_connections):
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self.log_connections -= dead


manager = ConnectionManager()


def _load_live_state() -> dict:
    try:
        with open(LIVE_STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _get_today_start() -> float:
    from datetime import datetime
    now = datetime.now()
    return datetime(now.year, now.month, now.day).timestamp()


def _compute_terminal_snapshot(last_trade_id: int, last_alert_id: int) -> dict:
    """Read DB + state file and return a terminal snapshot dict."""
    state = _load_live_state()
    today_start = _get_today_start()
    now = time.time()

    daily_pnl = 0.0
    win_rate = 0.0
    rolling_pi = 0.0
    max_drawdown = 0.0
    new_trades = []
    new_alerts = []
    max_trade_id = last_trade_id
    max_alert_id = last_alert_id

    if DB_PATH.exists():
        try:
            with closing(sqlite3.connect(str(DB_PATH))) as conn:
                conn.row_factory = sqlite3.Row

                # Daily PnL from DB
                row = conn.execute(
                    "SELECT COALESCE(SUM(pnl),0) as total FROM live_trades WHERE timestamp >= ?",
                    (today_start,)
                ).fetchone()
                daily_pnl = float(row["total"]) if row else 0.0

                # Win rate today
                wins = conn.execute(
                    "SELECT COUNT(*) as c FROM live_trades WHERE pnl > 0 AND side IN ('SELL','COVER') AND timestamp >= ?",
                    (today_start,)
                ).fetchone()["c"]
                total_exits = conn.execute(
                    "SELECT COUNT(*) as c FROM live_trades WHERE side IN ('SELL','COVER') AND timestamp >= ?",
                    (today_start,)
                ).fetchone()["c"]
                win_rate = (wins / total_exits * 100) if total_exits > 0 else 0.0

                # Rolling PI
                today_trades = conn.execute(
                    "SELECT qty FROM live_trades WHERE timestamp >= ?", (today_start,)
                ).fetchall()
                total_shares = sum(abs(r["qty"]) for r in today_trades)
                rolling_pi = daily_pnl / total_shares if total_shares > 0 else 0.0

                # Max drawdown (last 500 rows to avoid full table scan)
                hist = conn.execute(
                    "SELECT liquidation_value FROM (SELECT liquidation_value, timestamp FROM account_history ORDER BY timestamp DESC LIMIT 500) ORDER BY timestamp ASC"
                ).fetchall()
                if hist:
                    vals = [float(r["liquidation_value"]) for r in hist if r["liquidation_value"] is not None]
                    if vals:
                        peak = vals[0]
                        dd = 0.0
                        for v in vals:
                            peak = max(peak, v)
                            if peak > 0:
                                dd = max(dd, (peak - v) / peak * 100)
                        max_drawdown = round(dd, 2)

                # New trades since last_trade_id (today only)
                rows = conn.execute(
                    "SELECT * FROM live_trades WHERE id > ? AND timestamp >= ? ORDER BY id ASC LIMIT 50",
                    (last_trade_id, today_start)
                ).fetchall()
                for r in rows:
                    d = dict(r)
                    if d.get("timestamp"):
                        from datetime import datetime as _dt
                        d["datetime_est"] = _dt.utcfromtimestamp(float(d["timestamp"])).strftime("%H:%M:%S")
                    new_trades.append(d)
                    max_trade_id = max(max_trade_id, r["id"])

                # New alerts since last_alert_id
                rows = conn.execute(
                    "SELECT rowid, * FROM alerts WHERE rowid > ? ORDER BY rowid ASC LIMIT 20",
                    (last_alert_id,)
                ).fetchall()
                for r in rows:
                    new_alerts.append(dict(r))
                    max_alert_id = max(max_alert_id, r["rowid"])

        except Exception:
            pass

    # Cooldowns
    loss_cooldown_raw = state.get("loss_cooldown_until", 0.0)
    pi_cooldown = float(state.get("pi_cooldown_until", 0.0))
    if isinstance(loss_cooldown_raw, dict):
        active = {sym: until for sym, until in loss_cooldown_raw.items() if now < until}
        loss_cooldown = max(active.values()) if active else 0.0
        loss_cooldown_syms = list(active.keys())
    else:
        loss_cooldown = float(loss_cooldown_raw)
        loss_cooldown_syms = []

    # Use Schwab day_pnl if available (account_details.day_pnl)
    account_details = state.get("account_details", {})
    day_pnl_schwab = account_details.get("day_pnl")

    return {
        "type": "state_update",
        "ts": now,
        "data": {
            "positions": state.get("positions", {}),
            "account_details": account_details,
            "daily_pnl": day_pnl_schwab if day_pnl_schwab is not None else daily_pnl,
            "daily_pnl_db": daily_pnl,
            "win_rate": win_rate,
            "rolling_pi_per_share": rolling_pi,
            "max_drawdown": max_drawdown,
            "cooldowns": {
                "loss_cooldown_until": loss_cooldown,
                "pi_cooldown_until": pi_cooldown,
                "loss_cooldown_syms": loss_cooldown_syms,
            },
            "new_trades": new_trades,
            "new_alerts": new_alerts,
        },
        "_cursor": {
            "trade_id": max_trade_id,
            "alert_id": max_alert_id,
        }
    }


async def terminal_broadcast_loop():
    """Background task: push terminal state to all connected clients every 3s."""
    last_trade_id = 0
    last_alert_id = 0
    while True:
        try:
            if manager.terminal_connections:
                snapshot = await asyncio.to_thread(
                    _compute_terminal_snapshot, last_trade_id, last_alert_id
                )
                last_trade_id = snapshot["_cursor"]["trade_id"]
                last_alert_id = snapshot["_cursor"]["alert_id"]
                await manager.broadcast_terminal(snapshot)
        except Exception:
            pass
        await asyncio.sleep(3)
