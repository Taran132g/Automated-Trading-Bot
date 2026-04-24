"""
SQLite database setup and query helpers.
All writes are protected by a module-level lock for thread safety.
"""

import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "screener.db"
_lock = threading.Lock()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # allow concurrent reads while writing
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = get_conn()
        with conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS universe (
                    symbol      TEXT PRIMARY KEY,
                    last_close  REAL NOT NULL,
                    avg_vol_10d REAL,
                    updated_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trades (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol    TEXT    NOT NULL,
                    price     REAL    NOT NULL,
                    volume    REAL,
                    ts        TEXT    NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_trades_symbol_ts ON trades(symbol, ts);

                CREATE TABLE IF NOT EXISTS snapshots (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol    TEXT  NOT NULL,
                    price     REAL  NOT NULL,
                    score     REAL,
                    distance  REAL,
                    ts        TEXT  NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_snapshots_symbol_ts ON snapshots(symbol, ts);

                CREATE TABLE IF NOT EXISTS alerts (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol     TEXT NOT NULL,
                    alert_type TEXT NOT NULL,   -- 'APPROACHING' or 'BREAK'
                    price      REAL NOT NULL,
                    score      REAL,
                    ts         TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_alerts_symbol_ts ON alerts(symbol, ts);
            """)
        conn.close()


# ── Universe ──────────────────────────────────────────────────────────────────

def upsert_universe(rows: list[dict]) -> None:
    """Replace the entire universe table with fresh data."""
    with _lock:
        conn = get_conn()
        with conn:
            conn.execute("DELETE FROM universe")
            conn.executemany(
                "INSERT OR REPLACE INTO universe (symbol, last_close, avg_vol_10d, updated_at) VALUES (?,?,?,?)",
                [(r["symbol"], r["last_close"], r.get("avg_vol_10d"), r["updated_at"]) for r in rows],
            )
        conn.close()


def get_universe() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM universe").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Trades ────────────────────────────────────────────────────────────────────

def insert_trades(rows: list[dict]) -> None:
    with _lock:
        conn = get_conn()
        with conn:
            conn.executemany(
                "INSERT INTO trades (symbol, price, volume, ts) VALUES (?,?,?,?)",
                [(r["symbol"], r["price"], r.get("volume"), r["ts"]) for r in rows],
            )
        conn.close()


def get_trades_since(symbol: str, since: datetime) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trades WHERE symbol=? AND ts>=? ORDER BY ts ASC",
        (symbol, since.isoformat()),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def purge_old_trades(hours: int = 24) -> None:
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    with _lock:
        conn = get_conn()
        with conn:
            conn.execute("DELETE FROM trades WHERE ts < ?", (cutoff,))
        conn.close()


# ── Snapshots ─────────────────────────────────────────────────────────────────

def insert_snapshot(symbol: str, price: float, score: float, distance: float) -> None:
    ts = datetime.utcnow().isoformat()
    with _lock:
        conn = get_conn()
        with conn:
            conn.execute(
                "INSERT INTO snapshots (symbol, price, score, distance, ts) VALUES (?,?,?,?,?)",
                (symbol, price, score, distance, ts),
            )
        conn.close()


def get_snapshots_since(symbol: str, since: datetime) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM snapshots WHERE symbol=? AND ts>=? ORDER BY ts ASC",
        (symbol, since.isoformat()),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Alerts ────────────────────────────────────────────────────────────────────

def insert_alert(symbol: str, alert_type: str, price: float, score: float) -> None:
    ts = datetime.utcnow().isoformat()
    with _lock:
        conn = get_conn()
        with conn:
            conn.execute(
                "INSERT INTO alerts (symbol, alert_type, price, score, ts) VALUES (?,?,?,?,?)",
                (symbol, alert_type, price, score, ts),
            )
        conn.close()


def recent_alert_exists(symbol: str, alert_type: str, minutes: int = 15) -> bool:
    """Return True if the same alert type fired for this symbol within `minutes`."""
    since = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM alerts WHERE symbol=? AND alert_type=? AND ts>=? LIMIT 1",
        (symbol, alert_type, since),
    ).fetchone()
    conn.close()
    return row is not None


def get_recent_alerts(limit: int = 50) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM alerts ORDER BY ts DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
