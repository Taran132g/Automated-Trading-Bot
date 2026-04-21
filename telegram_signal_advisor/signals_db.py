"""
signals_db.py — stores every forwarded message + sizing into SQLite.
"""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "signals.db"
IMAGES_DIR = Path(__file__).parent.parent / "signal_images"
IMAGES_DIR.mkdir(exist_ok=True)


def init_db():
    with closing(sqlite3.connect(str(DB_PATH))) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
                channel              TEXT,
                raw_text             TEXT,
                image_path           TEXT,
                entry                REAL,
                sl                   REAL,
                sl_distance_pct      REAL,
                tp_levels            TEXT,
                quantity             REAL,
                position_size_usdt   REAL,
                risk_amount_usdt     REAL,
                risk_pct             REAL,
                balance_usdt         REAL,
                has_sizing           INTEGER DEFAULT 0
            )
        """)
        conn.commit()


def save_signal(
    channel: str,
    raw_text: str,
    sizing: dict | None = None,
    image_bytes: bytes | None = None,
    signal_id_hint: int | None = None,
) -> int:
    init_db()

    # Save image to disk if present
    image_path = None
    if image_bytes:
        # Use a temp name first, update after we get the row ID
        import time
        tmp = IMAGES_DIR / f"tmp_{int(time.time()*1000)}.jpg"
        tmp.write_bytes(image_bytes)
        image_path = str(tmp.name)  # just filename, served via /api/signals/image/<name>

    with closing(sqlite3.connect(str(DB_PATH))) as conn:
        conn.execute("""
            INSERT INTO signals (
                channel, raw_text, image_path,
                entry, sl, sl_distance_pct, tp_levels,
                quantity, position_size_usdt, risk_amount_usdt,
                risk_pct, balance_usdt, has_sizing
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            channel,
            raw_text,
            image_path,
            sizing["entry"] if sizing else None,
            sizing["sl"] if sizing else None,
            sizing["sl_distance_pct"] if sizing else None,
            json.dumps(sizing["tps"] if sizing else []),
            sizing["quantity"] if sizing else None,
            sizing["position_size_usdt"] if sizing else None,
            sizing["risk_amount"] if sizing else None,
            sizing["risk_pct"] if sizing else None,
            sizing["balance"] if sizing else None,
            1 if sizing else 0,
        ))
        conn.commit()
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Rename image file to use the actual row ID
    if image_bytes and image_path:
        old = IMAGES_DIR / image_path
        new_name = f"signal_{row_id}.jpg"
        new = IMAGES_DIR / new_name
        old.rename(new)
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            conn.execute("UPDATE signals SET image_path=? WHERE id=?", (new_name, row_id))
            conn.commit()

    return row_id


def get_recent_signals(limit: int = 100, after_id: int = 0) -> list[dict]:
    init_db()
    with closing(sqlite3.connect(str(DB_PATH))) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM signals WHERE id > ? ORDER BY id DESC LIMIT ?",
            (after_id, limit)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["tp_levels"] = json.loads(d.get("tp_levels") or "[]")
            result.append(d)
        return result
