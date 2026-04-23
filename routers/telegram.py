"""
routers/telegram.py

REST + WebSocket endpoints for the raw Telegram channel feed.
Reads from the same signals.db written by telegram_signal_advisor.
Exposes all messages (not just parsed buy orders) with channel filtering.
"""

import asyncio
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/api/telegram", tags=["telegram"])

DB_PATH = Path(__file__).parent.parent / "signals.db"
IMAGES_DIR = Path(__file__).parent.parent / "signal_images"


def _conn():
    if not DB_PATH.exists():
        return None
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def _row_to_dict(r) -> dict:
    d = dict(r)
    d["tp_levels"] = json.loads(d.get("tp_levels") or "[]")
    return d


def _get_messages(
    limit: int = 100,
    after_id: int = 0,
    channel: str = "all",
) -> list[dict]:
    conn = _conn()
    if not conn:
        return []
    with closing(conn):
        if channel == "all":
            rows = conn.execute(
                "SELECT * FROM signals WHERE id > ? ORDER BY id DESC LIMIT ?",
                (after_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM signals WHERE id > ? AND channel = ? ORDER BY id DESC LIMIT ?",
                (after_id, channel, limit),
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _get_channels() -> list[str]:
    conn = _conn()
    if not conn:
        return []
    with closing(conn):
        rows = conn.execute(
            "SELECT DISTINCT channel FROM signals ORDER BY channel"
        ).fetchall()
    # Filter out numeric-only channel IDs (duplicates of named channels)
    return [r["channel"] for r in rows if not str(r["channel"]).lstrip("-").isdigit()]


def _max_id() -> int:
    conn = _conn()
    if not conn:
        return 0
    with closing(conn):
        row = conn.execute("SELECT MAX(id) FROM signals").fetchone()
    return row[0] or 0


# ── REST ──────────────────────────────────────────────────────────────────────

@router.get("/channels")
def get_channels():
    return {"channels": _get_channels()}


@router.get("/messages")
def get_messages(
    limit: int = Query(100, le=500),
    channel: str = Query("all"),
    after_id: int = Query(0),
):
    return {"messages": _get_messages(limit=limit, after_id=after_id, channel=channel)}


# ── WebSocket ─────────────────────────────────────────────────────────────────

@router.websocket("/ws")
async def telegram_ws(ws: WebSocket):
    await ws.accept()
    channel_filter = "all"

    # Send init payload
    messages = await asyncio.to_thread(_get_messages, 100, 0, channel_filter)
    channels = await asyncio.to_thread(_get_channels)
    await ws.send_json({
        "type": "init",
        "messages": messages,
        "channels": channels,
    })

    try:
        last_id = _max_id()
        while True:
            # Check for client filter changes (non-blocking)
            try:
                data = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
                if data.get("type") == "filter":
                    channel_filter = data.get("channel", "all")
                    # Re-send full set for new filter
                    messages = await asyncio.to_thread(_get_messages, 100, 0, channel_filter)
                    await ws.send_json({"type": "init", "messages": messages})
                    last_id = _max_id()
                    continue
            except asyncio.TimeoutError:
                pass

            # Poll for new messages
            new = await asyncio.to_thread(_get_messages, 20, last_id, channel_filter)
            if new:
                last_id = new[0]["id"]
                await ws.send_json({"type": "new_messages", "messages": new})

    except (WebSocketDisconnect, Exception):
        pass
