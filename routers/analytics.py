"""Analytics router: historical performance metrics."""
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from ws_manager import DB_PATH

router = APIRouter()
BASE_DIR = Path(__file__).parent.parent.resolve()


@router.get("/summary")
def get_analytics_summary():
    result = {
        "profit_factor": 0.0,
        "win_rate": 0.0,
        "risk_reward": 0.0,
        "total_round_trips": 0,
        "wins": 0,
        "losses": 0,
        "total_pnl": 0.0,
    }
    if not DB_PATH.exists():
        return result
    try:
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            conn.row_factory = sqlite3.Row
            exits = conn.execute(
                "SELECT pnl FROM live_trades WHERE side IN ('SELL','COVER')"
            ).fetchall()
            if not exits:
                return result
            pnls = [float(r["pnl"]) for r in exits]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p < 0]
            total = len(pnls)
            gross_profit = sum(wins)
            gross_loss = abs(sum(losses))
            avg_win = sum(wins) / len(wins) if wins else 0.0
            avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
            result["profit_factor"] = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")
            result["win_rate"] = round(len(wins) / total * 100, 1) if total > 0 else 0.0
            result["risk_reward"] = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0
            result["total_round_trips"] = total
            result["wins"] = len(wins)
            result["losses"] = len(losses)
            result["total_pnl"] = round(sum(pnls), 2)
    except Exception:
        pass
    return result


@router.get("/daily-pnl")
def get_daily_pnl():
    bars = []
    if not DB_PATH.exists():
        return {"bars": bars}
    try:
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT date(datetime(timestamp,'unixepoch','localtime')) as trade_date,
                          SUM(pnl) as daily_pnl,
                          COUNT(*) as trade_count
                   FROM live_trades
                   WHERE side IN ('SELL','COVER')
                   GROUP BY trade_date
                   ORDER BY trade_date ASC"""
            ).fetchall()
            for r in rows:
                bars.append({
                    "date": r["trade_date"],
                    "daily_pnl": round(float(r["daily_pnl"]), 2),
                    "trade_count": r["trade_count"],
                })
    except Exception:
        pass
    return {"bars": bars}


@router.get("/win-loss")
def get_win_loss():
    if not DB_PATH.exists():
        return {"wins": 0, "losses": 0, "win_rate": 0.0}
    try:
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            conn.row_factory = sqlite3.Row
            exits = conn.execute(
                "SELECT pnl FROM live_trades WHERE side IN ('SELL','COVER')"
            ).fetchall()
            pnls = [float(r["pnl"]) for r in exits]
            wins = len([p for p in pnls if p > 0])
            losses = len([p for p in pnls if p <= 0])
            total = len(pnls)
            return {
                "wins": wins,
                "losses": losses,
                "win_rate": round(wins / total * 100, 1) if total > 0 else 0.0
            }
    except Exception:
        return {"wins": 0, "losses": 0, "win_rate": 0.0}


class ParseHistoryRequest(BaseModel):
    raw_text: str


@router.post("/parse-history")
def parse_history(req: ParseHistoryRequest):
    sys.path.insert(0, str(BASE_DIR))
    try:
        import trade_analyzer
        result = trade_analyzer.analyze_trades(req.raw_text)
        return result
    except Exception as e:
        return {"error": str(e)}
