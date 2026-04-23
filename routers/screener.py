"""
routers/screener.py

REST endpoints for the Dollar-Break Screener dashboard tab.
Reads from dollar-break-screener/data/screener.db (written by the
ingestion pipeline running as a separate process).
"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/screener", tags=["screener"])

DB_PATH = Path(__file__).parent.parent / "dollar-break-screener" / "data" / "screener.db"


def _conn():
    if not DB_PATH.exists():
        return None
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


# ── Universe ──────────────────────────────────────────────────────────────────

@router.get("/universe")
def get_universe():
    conn = _conn()
    if not conn:
        return {"symbols": [], "count": 0}
    with closing(conn):
        rows = conn.execute("SELECT * FROM universe ORDER BY last_close ASC").fetchall()
    return {"symbols": [dict(r) for r in rows], "count": len(rows)}


# ── Watchlist (latest snapshot per symbol, scored + sorted) ──────────────────

@router.get("/watchlist")
def get_watchlist(
    min_score: float = Query(0, ge=0, le=100),
    min_price: float = Query(0.80),
    max_price: float = Query(1.15),
    limit: int = Query(50, le=200),
):
    conn = _conn()
    if not conn:
        return {"rows": []}
    since = (datetime.utcnow() - timedelta(minutes=15)).isoformat()
    with closing(conn):
        # Latest snapshot per symbol within last 15 min
        rows = conn.execute("""
            SELECT s.symbol, s.price, s.score, s.distance, s.ts
            FROM snapshots s
            INNER JOIN (
                SELECT symbol, MAX(ts) as max_ts
                FROM snapshots
                WHERE ts >= ?
                GROUP BY symbol
            ) latest ON s.symbol = latest.symbol AND s.ts = latest.max_ts
            WHERE s.score >= ?
              AND s.price >= ?
              AND s.price <= ?
            ORDER BY s.score DESC
            LIMIT ?
        """, (since, min_score, min_price, max_price, limit)).fetchall()
    return {"rows": [dict(r) for r in rows]}


# ── Alerts ────────────────────────────────────────────────────────────────────

@router.get("/alerts")
def get_alerts(
    limit: int = Query(50, le=200),
    alert_type: str = Query("all"),  # "all" | "APPROACHING" | "BREAK"
):
    conn = _conn()
    if not conn:
        return {"alerts": []}
    with closing(conn):
        if alert_type == "all":
            rows = conn.execute(
                "SELECT * FROM alerts ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE alert_type=? ORDER BY ts DESC LIMIT ?",
                (alert_type, limit),
            ).fetchall()
    return {"alerts": [dict(r) for r in rows]}


# ── Price history for a single symbol ────────────────────────────────────────

@router.get("/history/{symbol}")
def get_history(symbol: str, minutes: int = Query(30, le=1440)):
    conn = _conn()
    if not conn:
        return {"symbol": symbol, "points": []}
    since = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
    with closing(conn):
        rows = conn.execute(
            "SELECT ts, price FROM snapshots WHERE symbol=? AND ts>=? ORDER BY ts ASC",
            (symbol.upper(), since),
        ).fetchall()
    return {"symbol": symbol.upper(), "points": [dict(r) for r in rows]}


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
def get_status():
    if not DB_PATH.exists():
        return {"running": False, "universe_size": 0, "last_snapshot": None}
    conn = _conn()
    with closing(conn):
        count = conn.execute("SELECT COUNT(*) FROM universe").fetchone()[0]
        last = conn.execute("SELECT MAX(ts) FROM snapshots").fetchone()[0]
    # Consider "running" if we got a snapshot in the last 2 minutes
    running = False
    if last:
        try:
            age = (datetime.utcnow() - datetime.fromisoformat(last)).total_seconds()
            running = age < 120
        except Exception:
            pass
    return {"running": running, "universe_size": count, "last_snapshot": last}
