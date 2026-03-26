"""Pattern Lab router."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter()

BASE_DIR = Path(__file__).parent.parent.resolve()
PATTERN_DB = BASE_DIR / "penny_basing.db"


def _get_today_start() -> float:
    now = datetime.now()
    return datetime(now.year, now.month, now.day).timestamp()


def _resolve_tables(mode: str) -> tuple[str, str, Path]:
    if mode == "paper":
        return "pattern_trades_paper", "pattern_positions_paper", BASE_DIR / "pattern_trader_paper_state.json"
    return "pattern_trades", "pattern_positions", BASE_DIR / "pattern_trader_state.json"


def _load_pattern_state(state_path: Path) -> dict:
    try:
        with open(state_path) as f:
            return json.load(f)
    except Exception:
        return {}


def _get_db():
    if not PATTERN_DB.exists():
        return None
    return sqlite3.connect(str(PATTERN_DB))


@router.get("/state")
def get_pattern_state(mode: str = Query("live")):
    trades_table, positions_table, state_path = _resolve_tables(mode)
    state = _load_pattern_state(state_path)
    today_start = _get_today_start()
    daily_pnl = total_pnl = win_rate = 0.0
    trades_today = 0

    db = _get_db()
    if db:
        try:
            with closing(db) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    f"SELECT COALESCE(SUM(pnl),0) FROM {trades_table} WHERE timestamp >= ?", (today_start,)
                ).fetchone()
                daily_pnl = float(row[0]) if row else 0.0

                row = conn.execute(f"SELECT COALESCE(SUM(pnl),0) FROM {trades_table}").fetchone()
                total_pnl = float(row[0]) if row else 0.0

                wins = conn.execute(
                    f"SELECT COUNT(*) FROM {trades_table} WHERE pnl > 0 AND side IN ('SELL','COVER') AND timestamp >= ?",
                    (today_start,)
                ).fetchone()[0]
                exits = conn.execute(
                    f"SELECT COUNT(*) FROM {trades_table} WHERE side IN ('SELL','COVER') AND timestamp >= ?",
                    (today_start,)
                ).fetchone()[0]
                win_rate = (wins / exits * 100) if exits > 0 else 0.0
                trades_today = conn.execute(
                    f"SELECT COUNT(*) FROM {trades_table} WHERE timestamp >= ?", (today_start,)
                ).fetchone()[0]
        except Exception:
            pass

    positions = {}
    db2 = _get_db()
    if db2:
        try:
            with closing(db2) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(f"SELECT symbol, qty FROM {positions_table}").fetchall()
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


@router.get("/equity-curve")
def get_pattern_equity_curve(
    range: str = Query("today"),
    mode: str = Query("live"),
):
    trades_table, _, _ = _resolve_tables(mode)
    points = []
    db = _get_db()
    if not db:
        return {"points": points}
    today_start = _get_today_start()
    try:
        with closing(db) as conn:
            conn.row_factory = sqlite3.Row
            if range == "today":
                rows = conn.execute(
                    f"SELECT * FROM {trades_table} WHERE timestamp >= ? ORDER BY timestamp ASC", (today_start,)
                ).fetchall()
            else:
                rows = conn.execute(f"SELECT * FROM {trades_table} ORDER BY timestamp ASC").fetchall()
            cumulative = 0.0
            for r in rows:
                pnl = float(r["pnl"]) if r["pnl"] else 0.0
                cumulative += pnl
                points.append({
                    "timestamp": float(r["timestamp"]),
                    "value": round(cumulative, 2),
                    "datetime_est": datetime.utcfromtimestamp(float(r["timestamp"])).strftime("%m/%d %H:%M")
                })
    except Exception:
        pass
    return {"points": points}


@router.get("/performance")
def get_pattern_performance(mode: str = Query("live")):
    trades_table, _, _ = _resolve_tables(mode)
    rows_out = []
    db = _get_db()
    if not db:
        return {"rows": rows_out}
    today_start = _get_today_start()
    try:
        with closing(db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""SELECT symbol,
                          SUM(pnl) as total_pnl,
                          COUNT(*) as trades,
                          SUM(CASE WHEN pnl > 0 AND side IN ('SELL','COVER') THEN 1 ELSE 0 END) as wins,
                          SUM(CASE WHEN side IN ('SELL','COVER') THEN 1 ELSE 0 END) as exits,
                          SUM(CASE WHEN timestamp >= ? THEN pnl ELSE 0 END) as today_pnl,
                          SUM(CASE WHEN pnl > 0 AND side IN ('SELL','COVER') AND timestamp >= ? THEN 1 ELSE 0 END) as today_wins,
                          SUM(CASE WHEN side IN ('SELL','COVER') AND timestamp >= ? THEN 1 ELSE 0 END) as today_exits
                   FROM {trades_table} GROUP BY symbol ORDER BY total_pnl DESC""",
                (today_start, today_start, today_start)
            ).fetchall()
            for r in rows:
                exits = r["exits"] or 0
                wins = r["wins"] or 0
                today_exits = r["today_exits"] or 0
                today_wins = r["today_wins"] or 0
                total_pnl = float(r["total_pnl"])
                today_pnl = float(r["today_pnl"])
                rows_out.append({
                    "symbol": r["symbol"],
                    "total_pnl": round(total_pnl, 2),
                    "trades": r["trades"],
                    "win_rate": round(wins / exits * 100, 1) if exits > 0 else 0.0,
                    "today_win_rate": round(today_wins / today_exits * 100, 1) if today_exits > 0 else 0.0,
                    "today_pnl": round(today_pnl, 2),
                    "avg_pnl_per_trade": round(total_pnl / exits, 2) if exits > 0 else 0.0,
                })
    except Exception:
        pass
    return {"rows": rows_out}
