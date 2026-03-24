"""Grok log router: tail + WebSocket streaming."""
import asyncio
import subprocess
from pathlib import Path

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from ws_manager import manager

router = APIRouter()
BASE_DIR = Path(__file__).parent.parent.resolve()
LOG_PATH = BASE_DIR / "grok.log"


def _tail_log(n: int = 1000) -> list[str]:
    if not LOG_PATH.exists():
        return []
    try:
        result = subprocess.run(
            ["tail", "-n", str(n), str(LOG_PATH)],
            capture_output=True, text=True, errors="replace", timeout=10
        )
        return [l.rstrip() for l in result.stdout.splitlines()]
    except Exception:
        return []


def _parse_line(raw: str) -> dict | None:
    """Parse a grok log line into a structured dict."""
    import json as _json
    if not raw.strip():
        return None
    # Format: "YYYY-MM-DD HH:MM:SS,mmm - LEVEL - {...json...}"
    parts = raw.split(" - ", 2)
    if len(parts) < 3:
        return {"raw": raw, "level": "INFO", "event": "RAW", "ts": ""}
    ts_str, level, rest = parts[0], parts[1].strip(), parts[2].strip()
    try:
        data = _json.loads(rest)
    except Exception:
        data = {"message": rest}
    data["ts"] = ts_str
    data["level"] = level
    if "event" not in data:
        data["event"] = "SYSTEM"
    return data


@router.get("/tail")
def tail_logs(
    lines: int = Query(1000, ge=10, le=5000),
    symbol: str = Query(""),
    levels: str = Query("INFO,WARNING,ERROR"),
):
    raw_lines = _tail_log(lines)
    level_filter = {l.strip().upper() for l in levels.split(",") if l.strip()}
    parsed = []
    for raw in raw_lines:
        entry = _parse_line(raw)
        if not entry:
            continue
        if entry.get("level", "").upper() not in level_filter:
            continue
        if symbol and entry.get("symbol", "").upper() != symbol.upper():
            continue
        parsed.append(entry)
    return {"logs": parsed}


@router.websocket("/ws")
async def log_ws(ws: WebSocket):
    await manager.connect_log(ws)
    try:
        # Stream tail -f output
        if LOG_PATH.exists():
            proc = await asyncio.create_subprocess_exec(
                "tail", "-f", str(LOG_PATH),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                async for raw in proc.stdout:
                    line = raw.decode("utf-8", errors="replace").rstrip()
                    entry = _parse_line(line)
                    if entry:
                        await ws.send_json(entry)
            finally:
                proc.kill()
        else:
            await ws.send_json({"event": "SYSTEM", "message": "grok.log not found", "level": "WARNING"})
            # Keep connection alive
            while True:
                await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect_log(ws)
