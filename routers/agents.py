"""Agent reports router."""
import importlib
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pyotp
from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile, status

load_dotenv()

router = APIRouter()
BASE_DIR = Path(__file__).parent.parent.resolve()
DB_PATH = BASE_DIR / "penny_basing.db"
sys.path.insert(0, str(BASE_DIR))

# Agents that can be manually triggered (risk_monitor is excluded — live watchdog only)
_RUNNABLE_AGENTS = {"post_market", "pattern_analyst", "weekly_review"}


@router.get("/reports")
def get_reports(
    agent: str = Query("all"),
    limit: int = Query(50),
):
    reports = []
    if not DB_PATH.exists():
        return {"reports": reports}
    try:
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            conn.row_factory = sqlite3.Row
            if agent == "all":
                rows = conn.execute(
                    "SELECT rowid,* FROM agent_reports ORDER BY timestamp DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT rowid,* FROM agent_reports WHERE agent_name = ? ORDER BY timestamp DESC LIMIT ?",
                    (agent, limit)
                ).fetchall()
            for r in rows:
                d = dict(r)
                if isinstance(d.get("report_data"), str):
                    try:
                        d["report_data"] = json.loads(d["report_data"])
                    except Exception:
                        pass
                reports.append(d)
    except Exception:
        pass
    return {"reports": reports}


@router.post("/run-agent")
def run_agent(
    background_tasks: BackgroundTasks,
    agent_name: str = Form(...),
    totp_code: str = Form(...),
):
    """Manually trigger a report agent. Requires a valid TOTP code."""
    totp_secret = os.getenv("TOTP_SECRET")
    if not totp_secret:
        raise HTTPException(status_code=500, detail="TOTP_SECRET not configured on server")
    if not pyotp.TOTP(totp_secret).verify(totp_code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid TOTP code")
    if agent_name not in _RUNNABLE_AGENTS:
        raise HTTPException(
            status_code=400,
            detail=f"'{agent_name}' is not manually triggerable. Valid: {sorted(_RUNNABLE_AGENTS)}",
        )
    module = importlib.import_module(f"agents.{agent_name}")
    background_tasks.add_task(module.run)
    return {"success": True, "agent": agent_name, "message": f"{agent_name} started in background"}


@router.post("/upload-post-market")
async def upload_post_market(
    file: UploadFile = File(...),
):
    content = await file.read()
    filename = file.filename or ""
    try:
        from agents.post_market_csv import run_from_upload
        report_md, report_data = run_from_upload(content, filename)
        return {"success": True, "report_markdown": report_md, "report_data": report_data}
    except Exception as e:
        return {"success": False, "error": str(e)}
