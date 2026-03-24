"""Paper trading router."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter()

BASE_DIR = Path(__file__).parent.parent.resolve()
DB_PATH = BASE_DIR / "penny_basing.db"
PAPER_STATE_PATH = BASE_DIR / "paper_trader_state.json"


def _get_today_start() -> float:
    now = datetime.now()
    return datetime(now.year, now.month, now.day).timestamp()


def _load_paper_state() -> dict:
    try:
        with open(PAPER_STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


@router.get("/state")
def get_paper_state():
    state = _load_paper_state()
    today_start = _get_today_start()
    daily_pnl = 0.0
    total_pnl = 0.0
    win_rate = 0.0
    trades_today = 0

    if DB_PATH.exists():
        try:
            with closing(sqlite3.connect(str(DB_PATH))) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT COALESCE(SUM(pnl),0) FROM paper_trades WHERE timestamp >= ?",
                    (today_start,)
                ).fetchone()
                daily_pnl = float(row[0]) if row else 0.0

                row = conn.execute("SELECT COALESCE(SUM(pnl),0) FROM paper_trades").fetchone()
                total_pnl = float(row[0]) if row else 0.0

                wins = conn.execute(
                    "SELECT COUNT(*) FROM paper_trades WHERE pnl > 0 AND side IN ('SELL','COVER') AND timestamp >= ?",
                    (today_start,)
                ).fetchone()[0]
                exits = conn.execute(
                    "SELECT COUNT(*) FROM paper_trades WHERE side IN ('SELL','COVER') AND timestamp >= ?",
                    (today_start,)
                ).fetchone()[0]
                win_rate = (wins / exits * 100) if exits > 0 else 0.0
                trades_today = conn.execute(
                    "SELECT COUNT(*) FROM paper_trades WHERE timestamp >= ?", (today_start,)
                ).fetchone()[0]
        except Exception:
            pass

    # Read open positions from DB (paper_trader writes to paper_positions table, not state JSON)
    positions = {}
    if DB_PATH.exists():
        try:
            with closing(sqlite3.connect(str(DB_PATH))) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT symbol, qty FROM paper_positions").fetchall()
                for r in rows:
                    if r["qty"] != 0:
                        positions[r["symbol"]] = r["qty"]
        except Exception:
            pass

    return {
        "daily_pnl": round(daily_pnl, 2),
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 1),
        "trades_today": trades_today,
        "positions": positions,
    }


@router.get("/trades")
def get_paper_trades(
    range: str = Query("today"),
    limit: int = Query(200),
):
    trades = []
    if not DB_PATH.exists():
        return {"trades": trades}
    today_start = _get_today_start()
    try:
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            conn.row_factory = sqlite3.Row
            if range == "today":
                rows = conn.execute(
                    "SELECT * FROM paper_trades WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
                    (today_start, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM paper_trades ORDER BY timestamp DESC LIMIT ?", (limit,)
                ).fetchall()
            for r in rows:
                d = dict(r)
                d["datetime_est"] = datetime.utcfromtimestamp(float(d["timestamp"])).strftime("%H:%M:%S")
                trades.append(d)
    except Exception:
        pass
    return {"trades": trades}


@router.get("/equity-curve")
def get_paper_equity_curve(
    range: str = Query("today"),
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
                    "SELECT * FROM paper_trades WHERE timestamp >= ? ORDER BY timestamp ASC", (today_start,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM paper_trades ORDER BY timestamp ASC"
                ).fetchall()
            cumulative = 0.0
            for r in rows:
                pnl = float(r["pnl"]) if r["pnl"] else 0.0
                cumulative += pnl
                points.append({
                    "timestamp": float(r["timestamp"]),
                    "value": round(cumulative, 2),
                    "pnl": round(pnl, 2),
                    "datetime_est": datetime.utcfromtimestamp(float(r["timestamp"])).strftime("%m/%d %H:%M")
                })
    except Exception:
        pass
    return {"points": points}


@router.get("/performance")
def get_paper_performance():
    rows_out = []
    if not DB_PATH.exists():
        return {"rows": rows_out}
    today_start = _get_today_start()
    try:
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT symbol,
                          SUM(pnl) as total_pnl,
                          SUM(ABS(qty)) as total_shares,
                          COUNT(*) as trades,
                          SUM(CASE WHEN pnl > 0 AND side IN ('SELL','COVER') THEN 1 ELSE 0 END) as wins,
                          SUM(CASE WHEN side IN ('SELL','COVER') THEN 1 ELSE 0 END) as exits,
                          SUM(CASE WHEN timestamp >= ? THEN pnl ELSE 0 END) as today_pnl,
                          SUM(CASE WHEN timestamp >= ? THEN ABS(qty) ELSE 0 END) as today_shares,
                          SUM(CASE WHEN pnl > 0 AND side IN ('SELL','COVER') AND timestamp >= ? THEN 1 ELSE 0 END) as today_wins,
                          SUM(CASE WHEN side IN ('SELL','COVER') AND timestamp >= ? THEN 1 ELSE 0 END) as today_exits
                   FROM paper_trades GROUP BY symbol ORDER BY total_pnl DESC""",
                (today_start, today_start, today_start, today_start)
            ).fetchall()
            for r in rows:
                exits = r["exits"] or 0
                wins = r["wins"] or 0
                today_exits = r["today_exits"] or 0
                today_wins = r["today_wins"] or 0
                total_shares = r["total_shares"] or 0
                today_shares = r["today_shares"] or 0
                total_pnl = float(r["total_pnl"])
                today_pnl = float(r["today_pnl"])
                rows_out.append({
                    "symbol": r["symbol"],
                    "total_pnl": round(total_pnl, 2),
                    "trades": r["trades"],
                    "win_rate": round(wins / exits * 100, 1) if exits > 0 else 0.0,
                    "today_win_rate": round(today_wins / today_exits * 100, 1) if today_exits > 0 else 0.0,
                    "today_pi": round(today_pnl / today_shares, 4) if today_shares > 0 else 0.0,
                    "alltime_pi": round(total_pnl / total_shares, 4) if total_shares > 0 else 0.0,
                })
    except Exception:
        pass
    return {"rows": rows_out}
