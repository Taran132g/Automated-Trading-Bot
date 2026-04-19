"""
routers/signals.py

REST + WebSocket endpoints for the Signal Advisor dashboard.
Reads from signals.db written by the telegram_signal_advisor process.
"""
import asyncio
import sqlite3
import json
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set

router = APIRouter(prefix="/api/signals", tags=["signals"])

DB_PATH = Path(__file__).parent.parent / "signals.db"

# WebSocket connections for live push
_signal_connections: Set[WebSocket] = set()


def _db_get_signals(limit: int = 50, after_id: int = 0) -> list[dict]:
    if not DB_PATH.exists():
        return []
    with closing(sqlite3.connect(str(DB_PATH))) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM signals WHERE id > ? ORDER BY id DESC LIMIT ?",
            (after_id, limit),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["tp_levels"] = json.loads(d.get("tp_levels") or "[]")
            d["rr_ratios"] = json.loads(d.get("rr_ratios") or "[]")
            result.append(d)
        return result


def _db_max_id() -> int:
    if not DB_PATH.exists():
        return 0
    with closing(sqlite3.connect(str(DB_PATH))) as conn:
        row = conn.execute("SELECT MAX(id) FROM signals").fetchone()
        return row[0] or 0


@router.get("")
def get_signals(limit: int = 50):
    return _db_get_signals(limit=limit)


@router.websocket("/ws")
async def signals_ws(ws: WebSocket):
    await ws.accept()
    _signal_connections.add(ws)
    # Send all existing signals on connect
    signals = await asyncio.to_thread(_db_get_signals, 100, 0)
    await ws.send_json({"type": "init", "signals": signals})
    try:
        last_id = _db_max_id()
        while True:
            await asyncio.sleep(2)
            new = await asyncio.to_thread(_db_get_signals, 20, last_id)
            if new:
                last_id = new[0]["id"]  # DB returns DESC so first is newest
                await ws.send_json({"type": "new_signals", "signals": new})
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _signal_connections.discard(ws)
