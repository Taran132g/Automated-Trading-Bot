"""Paper trading router."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    _ET = None

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
            elif range == "2days":
                two_days_start = today_start - 86400
                rows = conn.execute(
                    "SELECT * FROM paper_trades WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
                    (two_days_start, limit)
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
            elif range == "2days":
                two_days_start = today_start - 86400
                rows = conn.execute(
                    "SELECT * FROM paper_trades WHERE timestamp >= ? ORDER BY timestamp ASC", (two_days_start,)
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
                    "today_pnl": round(today_pnl, 2),
                    "today_shares": int(today_shares),
                    "trades": r["trades"],
                    "win_rate": round(wins / exits * 100, 1) if exits > 0 else 0.0,
                    "today_win_rate": round(today_wins / today_exits * 100, 1) if today_exits > 0 else 0.0,
                    "today_pi": round(today_pnl / today_shares, 4) if today_shares > 0 else 0.0,
                    "alltime_pi": round(total_pnl / total_shares, 4) if total_shares > 0 else 0.0,
                })
    except Exception:
        pass
    return {"rows": rows_out}


# ============================================================
# Deep analytics: round-trip pairing → hour-of-day, conviction,
# direction, symbol, and maker miss diagnostics.
# ============================================================
def _et_hour(ts: float) -> int:
    """Hour-of-day (0-23) in US/Eastern for a unix timestamp."""
    if _ET is not None:
        return datetime.fromtimestamp(float(ts), _ET).hour
    return datetime.utcfromtimestamp(float(ts)).hour


def _conviction_bucket(ratio) -> str:
    if ratio is None:
        return "untagged"
    r = float(ratio)
    if r < 3:
        return "<3"
    if r < 5:
        return "3-5"
    if r < 7:
        return "5-7"
    if r < 10:
        return "7-10"
    return "10+"


def _build_round_trips(rows):
    """Pair each entry (BUY/SHORT) with its closing leg (SELL/COVER) per symbol.
    Flip-only means no stacking, so a simple per-symbol open slot is sufficient.
    The realized PnL lands on the exit; we attach the ENTRY's time + conviction
    so 'when/under what conviction did we make money' is answerable."""
    open_by_sym = {}
    trips = []
    for r in rows:
        side = r["side"]
        if side in ("BUY", "SHORT"):
            open_by_sym[r["symbol"]] = r
        elif side in ("SELL", "COVER"):
            entry = open_by_sym.pop(r["symbol"], None)
            direction = "long" if side == "SELL" else "short"
            trips.append({
                "symbol": r["symbol"],
                "direction": direction,
                "pnl": float(r["pnl"] or 0.0),
                "entry_ts": float(entry["timestamp"]) if entry else float(r["timestamp"]),
                "exit_ts": float(r["timestamp"]),
                "ratio": (entry["imbalance_ratio"] if entry else None),
                "duration": (entry["imbalance_duration"] if entry else None),
                "venues": (entry["heavy_venues"] if entry else None),
                "drift": (entry["drift_60s"]
                          if entry and "drift_60s" in entry.keys() else None),
            })
    return trips


def _trend_bucket(t) -> str:
    """Counter-trend vs trend-aligned entry, from the 60s drift at alert time.

    A long after a dip / short after a pop is 'counter' — the bucket both the
    Jun-15 backtest and the Jul-06 log replay found carries the edge. Zero or
    missing drift can't be classified either way."""
    d = t.get("drift")
    if d is None or d == 0:
        return "untagged"
    if (t["direction"] == "long") == (d < 0):
        return "counter"
    return "aligned"


def _agg(trips, keyfn):
    """Group round-trips by keyfn → pnl / count / win-rate."""
    buckets = {}
    for t in trips:
        k = keyfn(t)
        b = buckets.setdefault(k, {"pnl": 0.0, "trades": 0, "wins": 0})
        b["pnl"] += t["pnl"]
        b["trades"] += 1
        if t["pnl"] > 0:
            b["wins"] += 1
    out = []
    for k, b in buckets.items():
        out.append({
            "key": k,
            "pnl": round(b["pnl"], 2),
            "trades": b["trades"],
            "win_rate": round(b["wins"] / b["trades"] * 100, 1) if b["trades"] else 0.0,
        })
    return out


@router.get("/analytics")
def get_paper_analytics(range: str = Query("all")):
    """All the instrumentation in one payload for the Paper Lab UI."""
    empty = {"by_hour": [], "by_direction": [], "by_symbol": [],
             "by_conviction": [], "by_trend": [], "misses": {}, "range": range, "trips": 0}
    if not DB_PATH.exists():
        return empty
    today_start = _get_today_start()
    try:
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            conn.row_factory = sqlite3.Row
            where = "WHERE timestamp >= ?" if range == "today" else ""
            args = (today_start,) if range == "today" else ()
            rows = conn.execute(
                f"SELECT * FROM paper_trades {where} ORDER BY timestamp ASC", args
            ).fetchall()

            mwhere = "WHERE timestamp >= ?" if range == "today" else ""
            misses = conn.execute(
                f"SELECT * FROM paper_misses {mwhere} ORDER BY timestamp ASC", args
            ).fetchall()
    except Exception:
        return empty

    trips = _build_round_trips(rows)

    # by_hour: keep all market hours present so the chart has a clean axis.
    hour_map = {h["key"]: h for h in _agg(trips, lambda t: _et_hour(t["entry_ts"]))}
    by_hour = []
    for h in range_hours():
        b = hour_map.get(h)
        by_hour.append({
            "hour": h,
            "label": f"{h:02d}:00",
            "pnl": b["pnl"] if b else 0.0,
            "trades": b["trades"] if b else 0,
            "win_rate": b["win_rate"] if b else 0.0,
        })

    by_direction = sorted(_agg(trips, lambda t: t["direction"]), key=lambda x: x["key"])
    by_symbol = sorted(_agg(trips, lambda t: t["symbol"]), key=lambda x: -x["pnl"])
    conv_order = {"<3": 0, "3-5": 1, "5-7": 2, "7-10": 3, "10+": 4, "untagged": 5}
    by_conviction = sorted(
        _agg(trips, lambda t: _conviction_bucket(t["ratio"])),
        key=lambda x: conv_order.get(x["key"], 9),
    )
    trend_order = {"counter": 0, "aligned": 1, "untagged": 2}
    by_trend = sorted(
        _agg(trips, _trend_bucket),
        key=lambda x: trend_order.get(x["key"], 9),
    )

    # Miss diagnostics
    n_miss = len(misses)
    miss_by_sym = {}
    miss_dist = []
    for m in misses:
        mb = float(m["missed_by_cents"] or 0.0)
        miss_dist.append(mb)
        s = miss_by_sym.setdefault(m["symbol"], {"count": 0, "sum_cents": 0.0})
        s["count"] += 1
        s["sum_cents"] += mb
    miss_stats = {
        "total": n_miss,
        "avg_missed_cents": round(sum(miss_dist) / n_miss, 2) if n_miss else 0.0,
        "near_miss_pct": round(sum(1 for d in miss_dist if d <= 1.0) / n_miss * 100, 1) if n_miss else 0.0,
        "by_symbol": [
            {"symbol": k, "count": v["count"],
             "avg_cents": round(v["sum_cents"] / v["count"], 2)}
            for k, v in sorted(miss_by_sym.items(), key=lambda kv: -kv[1]["count"])
        ],
    }

    return {
        "range": range,
        "trips": len(trips),
        "by_hour": by_hour,
        "by_direction": by_direction,
        "by_symbol": by_symbol,
        "by_conviction": by_conviction,
        "by_trend": by_trend,
        "misses": miss_stats,
    }


def range_hours():
    """Market-relevant hours to display on the hour-of-day chart (ET)."""
    return list(range(7, 20))  # 7am pre-market → 7pm after-hours, ET
