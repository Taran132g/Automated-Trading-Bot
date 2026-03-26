"""Strategy Comparison router."""
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter()

BASE_DIR = Path(__file__).parent.parent.resolve()
DB_PATH = BASE_DIR / "penny_basing.db"

EXIT_SIDES = ("SELL", "COVER")


def _get_today_start() -> float:
    now = datetime.now()
    return datetime(now.year, now.month, now.day).timestamp()


def _load_exits(table: str, since: float = 0.0) -> list[dict]:
    if not DB_PATH.exists():
        return []
    exits = []
    try:
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            conn.row_factory = sqlite3.Row
            if since > 0:
                rows = conn.execute(
                    f"SELECT * FROM {table} WHERE side IN ('SELL','COVER') AND timestamp >= ? ORDER BY timestamp ASC",
                    (since,)
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT * FROM {table} WHERE side IN ('SELL','COVER') ORDER BY timestamp ASC"
                ).fetchall()
            for r in rows:
                exits.append(dict(r))
    except Exception:
        pass
    return exits


def _compute_stats(exits: list[dict]) -> dict:
    if not exits:
        return {
            "win_rate": 0.0, "pnl_per_share": 0.0, "profit_factor": None,
            "max_consec_loss": 0, "total_trades": 0, "total_pnl": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0, "avg_pnl_per_trade": 0.0,
        }
    pnls = [float(r.get("pnl") or 0) for r in exits]
    qtys = [abs(float(r.get("qty") or 0)) for r in exits]
    wins = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p < 0]
    total = len(pnls)
    total_pnl = sum(pnls)
    total_shares = sum(qtys)

    gross_profit = sum(wins)
    gross_loss = sum(losses)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    max_consec = 0
    current = 0
    for p in pnls:
        if p < 0:
            current += 1
            max_consec = max(max_consec, current)
        else:
            current = 0

    return {
        "win_rate": round(len(wins) / total * 100, 1) if total > 0 else 0.0,
        "pnl_per_share": round(total_pnl / total_shares, 4) if total_shares > 0 else 0.0,
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else None,
        "max_consec_loss": max_consec,
        "total_trades": total,
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "avg_pnl_per_trade": round(total_pnl / total, 2) if total > 0 else 0.0,
    }


def _cumulative_curve(exits: list[dict]) -> list[dict]:
    result = []
    cumulative = 0.0
    for r in exits:
        pnl = float(r.get("pnl") or 0)
        cumulative += pnl
        result.append({
            "label": datetime.utcfromtimestamp(float(r["timestamp"])).strftime("%m/%d %H:%M"),
            "value": round(cumulative, 2),
        })
    return result


def _symbol_breakdown(exits: list[dict]) -> list[dict]:
    by_sym: dict[str, dict] = {}
    for r in exits:
        sym = r.get("symbol", "?")
        if sym not in by_sym:
            by_sym[sym] = {"pnl": 0.0, "trades": 0, "wins": 0, "shares": 0.0}
        by_sym[sym]["pnl"] += float(r.get("pnl") or 0)
        by_sym[sym]["trades"] += 1
        by_sym[sym]["shares"] += abs(float(r.get("qty") or 0))
        if float(r.get("pnl") or 0) > 0:
            by_sym[sym]["wins"] += 1
    rows = []
    for sym, d in by_sym.items():
        rows.append({
            "symbol": sym,
            "total_pnl": round(d["pnl"], 2),
            "trades": d["trades"],
            "win_rate": round(d["wins"] / d["trades"] * 100, 1) if d["trades"] > 0 else 0.0,
            "pnl_per_share": round(d["pnl"] / d["shares"], 4) if d["shares"] > 0 else 0.0,
        })
    return sorted(rows, key=lambda x: x["total_pnl"], reverse=True)


@router.get("/stats")
def get_comparison_stats(
    range: str = Query("all", description="'today' or 'all'"),
):
    since = _get_today_start() if range == "today" else 0.0

    scalp_exits = _load_exits("live_trades", since)
    pattern_exits = _load_exits("pattern_trades", since)

    s_stats = _compute_stats(scalp_exits)
    p_stats = _compute_stats(pattern_exits)

    # Curves always use all-time data for full context
    scalp_all = _load_exits("live_trades") if since > 0 else scalp_exits
    pattern_all = _load_exits("pattern_trades") if since > 0 else pattern_exits
    s_curve = _cumulative_curve(scalp_all)
    p_curve = _cumulative_curve(pattern_all)

    return {
        "scalp_stats": s_stats,
        "pattern_stats": p_stats,
        "scalp_curve": s_curve,
        "pattern_curve": p_curve,
        "scalp_symbol_breakdown": _symbol_breakdown(scalp_exits),
        "pattern_symbol_breakdown": _symbol_breakdown(pattern_exits),
    }
