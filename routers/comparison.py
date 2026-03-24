"""Comparison/Filter Effectiveness router."""
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter()

BASE_DIR = Path(__file__).parent.parent.resolve()
BASELINE_DB = BASE_DIR / "penny_basing.db"
PATTERN_DB = BASE_DIR / "penny_basing_patterns.db"

EXIT_SIDES = ("SELL", "COVER")
ENTRY_SIDES = ("BUY", "SHORT", "SELL SHORT")


def _get_today_start() -> float:
    now = datetime.now()
    return datetime(now.year, now.month, now.day).timestamp()


def _load_trades(db_path: Path, since: float = 0.0) -> list[dict]:
    if not db_path.exists():
        return []
    trades = []
    try:
        with closing(sqlite3.connect(str(db_path))) as conn:
            conn.row_factory = sqlite3.Row
            if since > 0:
                rows = conn.execute(
                    "SELECT * FROM paper_trades WHERE timestamp >= ? ORDER BY timestamp ASC", (since,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM paper_trades ORDER BY timestamp ASC"
                ).fetchall()
            for r in rows:
                trades.append(dict(r))
    except Exception:
        pass
    return trades


def _compute_stats(exits: list[dict]) -> dict:
    if not exits:
        return {
            "win_rate": 0.0, "pnl_per_share": 0.0, "profit_factor": 0.0,
            "max_consec_loss": 0, "total_trades": 0, "total_pnl": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0,
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
    }


def _find_filtered_trades(baseline_exits: list[dict], pattern_exits: list[dict]) -> list[dict]:
    """Baseline exits with no matching pattern exit (same symbol within 120s)."""
    if not baseline_exits:
        return []
    if not pattern_exits:
        return baseline_exits[:]
    pattern_lookup = [(r["symbol"], float(r["timestamp"])) for r in pattern_exits]
    filtered = []
    for row in baseline_exits:
        sym = row["symbol"]
        ts = float(row["timestamp"])
        matched = any(p_sym == sym and abs(p_ts - ts) <= 120 for p_sym, p_ts in pattern_lookup)
        if not matched:
            filtered.append(row)
    return filtered


def _rolling_pnl_per_share(all_trades: list[dict], days: int = 7) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).timestamp()
    exits = [r for r in all_trades if r.get("side") in EXIT_SIDES and float(r.get("timestamp", 0)) >= cutoff]
    if not exits:
        return []
    by_date: dict[str, dict] = {}
    for r in exits:
        dt = datetime.utcfromtimestamp(float(r["timestamp"])).strftime("%Y-%m-%d")
        if dt not in by_date:
            by_date[dt] = {"pnl": 0.0, "shares": 0.0}
        by_date[dt]["pnl"] += float(r.get("pnl") or 0)
        by_date[dt]["shares"] += abs(float(r.get("qty") or 0))
    result = []
    for dt in sorted(by_date):
        d = by_date[dt]
        result.append({
            "date": dt,
            "pnl_per_share": round(d["pnl"] / d["shares"], 4) if d["shares"] > 0 else 0.0,
        })
    return result


@router.get("/stats")
def get_comparison_stats(
    range: str = Query("all", description="'today' or 'all'"),
):
    since = _get_today_start() if range == "today" else 0.0

    baseline_all = _load_trades(BASELINE_DB, since)
    pattern_all = _load_trades(PATTERN_DB, since)

    baseline_exits = [r for r in baseline_all if r.get("side") in EXIT_SIDES]
    pattern_exits = [r for r in pattern_all if r.get("side") in EXIT_SIDES]
    baseline_entries = [r for r in baseline_all if r.get("side") in ENTRY_SIDES]
    pattern_entries = [r for r in pattern_all if r.get("side") in ENTRY_SIDES]

    b_stats = _compute_stats(baseline_exits)
    p_stats = _compute_stats(pattern_exits)

    b_entry_count = len(baseline_entries)
    p_entry_count = len(pattern_entries)
    reject_rate = (b_entry_count - p_entry_count) / b_entry_count * 100 if b_entry_count > 0 else 0.0

    filtered = _find_filtered_trades(baseline_exits, pattern_exits)
    filtered_total = len(filtered)
    filtered_losers = len([r for r in filtered if float(r.get("pnl") or 0) <= 0])
    filtered_winners = filtered_total - filtered_losers
    loss_prevention_rate = filtered_losers / filtered_total * 100 if filtered_total > 0 else 0.0

    # Rolling PnL/share from all-time data (regardless of range filter)
    baseline_all_time = _load_trades(BASELINE_DB)
    pattern_all_time = _load_trades(PATTERN_DB)
    b_rolling = _rolling_pnl_per_share(baseline_all_time)
    p_rolling = _rolling_pnl_per_share(pattern_all_time)

    # Symbol breakdown
    def _symbol_breakdown(exits: list[dict]) -> list[dict]:
        by_sym: dict[str, dict] = {}
        for r in exits:
            sym = r.get("symbol", "?")
            if sym not in by_sym:
                by_sym[sym] = {"pnl": 0.0, "trades": 0, "wins": 0}
            by_sym[sym]["pnl"] += float(r.get("pnl") or 0)
            by_sym[sym]["trades"] += 1
            if float(r.get("pnl") or 0) > 0:
                by_sym[sym]["wins"] += 1
        rows = []
        for sym, d in by_sym.items():
            rows.append({
                "symbol": sym,
                "total_pnl": round(d["pnl"], 2),
                "trades": d["trades"],
                "win_rate": round(d["wins"] / d["trades"] * 100, 1) if d["trades"] > 0 else 0.0,
            })
        return sorted(rows, key=lambda x: x["total_pnl"], reverse=True)

    return {
        "baseline_stats": b_stats,
        "pattern_stats": p_stats,
        "reject_rate": round(reject_rate, 1),
        "wr_lift": round((p_stats["win_rate"] - b_stats["win_rate"]), 1),
        "pps_lift": round((p_stats["pnl_per_share"] - b_stats["pnl_per_share"]), 4),
        "filtered_total": filtered_total,
        "filtered_losers": filtered_losers,
        "filtered_winners": filtered_winners,
        "loss_prevention_rate": round(loss_prevention_rate, 1),
        "baseline_rolling": b_rolling,
        "pattern_rolling": p_rolling,
        "baseline_symbol_breakdown": _symbol_breakdown(baseline_exits),
        "pattern_symbol_breakdown": _symbol_breakdown(pattern_exits),
    }
