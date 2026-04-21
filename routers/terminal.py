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


@router.get("/positions")
def get_positions():
    """Return live open positions directly from state file — no caching."""
    state = _load_live_state()
    raw = state.get("positions", {})
    # Only non-zero quantities
    positions = {sym: qty for sym, qty in raw.items() if qty != 0}
    return {"positions": positions}


@router.get("/equity-curve")
def get_equity_curve(
    range: str = Query("today", description="'today' or 'alltime'"),
):
    """
    Today: reads account_history snapshots only during windows when the
    trader had an open position (entry → exit). Flat idle periods are
    excluded so the chart only shows meaningful trade activity.

    Alltime: chains daily (last - first) liquidation_value per day.
    """
    points = []
    if not DB_PATH.exists():
        return {"points": points}
    today_start = _get_today_start()
    try:
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            conn.row_factory = sqlite3.Row

            if range == "today":
                # Build trade windows: (entry_ts, exit_ts) for each closed trade today
                trade_rows = conn.execute(
                    """
                    SELECT e.timestamp AS entry_ts, x.timestamp AS exit_ts
                    FROM live_trades e
                    JOIN live_trades x ON x.symbol = e.symbol
                    WHERE e.side IN ('BUY','SHORT','SELL SHORT')
                      AND x.side IN ('SELL','COVER')
                      AND x.timestamp >= e.timestamp
                      AND e.timestamp >= ?
                    GROUP BY x.rowid
                    ORDER BY entry_ts ASC
                    """,
                    (today_start,)
                ).fetchall()

                if not trade_rows:
                    # No closed trades yet — show nothing
                    return {"points": points}

                # Build set of active windows
                windows = [(float(r["entry_ts"]), float(r["exit_ts"])) for r in trade_rows]

                # Fetch all account_history for today
                hist = conn.execute(
                    "SELECT timestamp, liquidation_value FROM account_history"
                    " WHERE timestamp >= ? ORDER BY timestamp ASC",
                    (today_start,)
                ).fetchall()
                if not hist:
                    return {"points": points}

                baseline = float(hist[0]["liquidation_value"])

                def in_trade_window(ts: float) -> bool:
                    for entry_ts, exit_ts in windows:
                        if entry_ts <= ts <= exit_ts + 5:  # 5s grace
                            return True
                    return False

                for r in hist:
                    ts = float(r["timestamp"])
                    if in_trade_window(ts):
                        val = float(r["liquidation_value"])
                        points.append({
                            "timestamp": ts,
                            "value": round(val - baseline, 2),
                            "datetime_est": datetime.utcfromtimestamp(ts).strftime("%H:%M"),
                        })

            else:
                rows = conn.execute(
                    "SELECT timestamp, liquidation_value FROM account_history"
                    " ORDER BY timestamp ASC"
                ).fetchall()
                from collections import defaultdict
                by_day: dict = defaultdict(list)
                for r in rows:
                    day_key = datetime.utcfromtimestamp(float(r["timestamp"])).strftime("%Y-%m-%d")
                    by_day[day_key].append(float(r["liquidation_value"]))
                cumulative = 0.0
                from datetime import datetime as dt
                for day in sorted(by_day):
                    vals = by_day[day]
                    day_pnl = vals[-1] - vals[0]
                    cumulative += day_pnl
                    ts = dt.strptime(day, "%Y-%m-%d").timestamp() + 43200
                    points.append({
                        "timestamp": ts,
                        "value": round(cumulative, 2),
                        "datetime_est": day,
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
