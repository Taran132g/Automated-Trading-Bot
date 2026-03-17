"""Agent reports router."""
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, File, Form, Query, UploadFile

router = APIRouter()
BASE_DIR = Path(__file__).parent.parent.resolve()
DB_PATH = BASE_DIR / "penny_basing.db"
sys.path.insert(0, str(BASE_DIR))


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
