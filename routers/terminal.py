"""Terminal router: live state, trades, equity curve, alerts."""
import json
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from ws_manager import manager, terminal_broadcast_loop, _load_live_state, _get_today_start, DB_PATH

router = APIRouter()

BASE_DIR = Path(__file__).parent.parent.resolve()
LIVE_STATE_PATH = BASE_DIR / "live_trader_state_primary.json"
if not LIVE_STATE_PATH.exists():
    LIVE_STATE_PATH = BASE_DIR / "live_trader_state.json"


@router.get("/state")
def get_terminal_state():
    state = _load_live_state()
    today_start = _get_today_start()
    now = time.time()

    daily_pnl = 0.0
    win_rate = 0.0
    rolling_pi = 0.0
    max_drawdown = 0.0

    if DB_PATH.exists():
        try:
            with closing(sqlite3.connect(str(DB_PATH))) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT COALESCE(SUM(pnl),0) as total FROM live_trades WHERE timestamp >= ?",
                    (today_start,)
                ).fetchone()
                daily_pnl = float(row["total"]) if row else 0.0

                wins = conn.execute(
                    "SELECT COUNT(*) as c FROM live_trades WHERE pnl > 0 AND side IN ('SELL','COVER') AND timestamp >= ?",
                    (today_start,)
                ).fetchone()["c"]
                total_exits = conn.execute(
                    "SELECT COUNT(*) as c FROM live_trades WHERE side IN ('SELL','COVER') AND timestamp >= ?",
                    (today_start,)
                ).fetchone()["c"]
                win_rate = (wins / total_exits * 100) if total_exits > 0 else 0.0

                today_rows = conn.execute(
                    "SELECT qty FROM live_trades WHERE timestamp >= ?", (today_start,)
                ).fetchall()
                total_shares = sum(abs(r["qty"]) for r in today_rows)
                rolling_pi = daily_pnl / total_shares if total_shares > 0 else 0.0

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
        except Exception:
            pass

    account_details = state.get("account_details", {})
    loss_cooldown_raw = state.get("loss_cooldown_until", 0.0)
    pi_cooldown = float(state.get("pi_cooldown_until", 0.0))
    if isinstance(loss_cooldown_raw, dict):
        active = {sym: until for sym, until in loss_cooldown_raw.items() if now < until}
        loss_cooldown = max(active.values()) if active else 0.0
        loss_cooldown_syms = list(active.keys())
    else:
        loss_cooldown = float(loss_cooldown_raw)
        loss_cooldown_syms = []

    day_pnl_schwab = account_details.get("day_pnl")
    return {
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
    }


@router.get("/trades")
def get_trades(
    date: str = Query("today", description="'today' or 'all'"),
    limit: int = Query(200),
):
    trades = []
    if not DB_PATH.exists():
        return {"trades": trades}
    today_start = _get_today_start()
    try:
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            conn.row_factory = sqlite3.Row
            if date == "today":
                rows = conn.execute(
                    "SELECT * FROM live_trades WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
                    (today_start, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM live_trades ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            for r in rows:
                d = dict(r)
                d["datetime_est"] = datetime.utcfromtimestamp(float(d["timestamp"])).strftime("%H:%M:%S") if d.get("timestamp") else ""
                trades.append(d)
    except Exception:
        pass
    return {"trades": trades}


@router.get("/equity-curve")
def get_equity_curve(
    range: str = Query("today", description="'today' or 'alltime'"),
):
    points = []
    if not DB_PATH.exists():
        return {"points": points}
    today_start = _get_today_start()
    try:
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            conn.row_factory = sqlite3.Row
            if range == "today":
                rows = conn.execute(
                    "SELECT timestamp, pnl FROM live_trades WHERE timestamp >= ? ORDER BY timestamp ASC",
                    (today_start,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT timestamp, pnl FROM live_trades ORDER BY timestamp ASC"
                ).fetchall()
            cumulative = 0.0
            for r in rows:
                pnl = float(r["pnl"]) if r["pnl"] else 0.0
                cumulative += pnl
                ts = float(r["timestamp"])
                points.append({
                    "timestamp": ts,
                    "value": round(cumulative, 2),
                    "datetime_est": datetime.utcfromtimestamp(ts).strftime("%m/%d %H:%M")
                })
    except Exception:
        pass
    return {"points": points}


@router.get("/alerts")
def get_alerts(
    limit: int = Query(50),
):
    alerts = []
    if not DB_PATH.exists():
        return {"alerts": alerts}
    try:
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT rowid, * FROM alerts ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            for r in rows:
                alerts.append(dict(r))
    except Exception:
        pass
    return {"alerts": alerts}


@router.websocket("/ws")
async def terminal_ws(ws: WebSocket):
    await manager.connect_terminal(ws)
    try:
        while True:
            # Keep connection alive; data pushed by terminal_broadcast_loop
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_terminal(ws)
    except Exception:
        manager.disconnect_terminal(ws)
