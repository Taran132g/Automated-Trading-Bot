import json
import sqlite3
import logging
import time
from contextlib import closing
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(__file__).parent.parent / "penny_basing.db"
LOGGER = logging.getLogger("agents.base")


def get_db():
    return sqlite3.connect(str(DB_PATH))


def ensure_reports_table():
    with closing(get_db()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                agent_name TEXT,
                report_markdown TEXT,
                report_data TEXT
            )
        """)
        conn.commit()


def save_report(agent_name: str, report_markdown: str, report_data: dict):
    ensure_reports_table()
    with closing(get_db()) as conn:
        conn.execute(
            "INSERT INTO agent_reports (timestamp, agent_name, report_markdown, report_data) VALUES (?, ?, ?, ?)",
            (time.time(), agent_name, report_markdown, json.dumps(report_data))
        )
        conn.commit()


def send_telegram(text: str) -> bool:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from telegram_notifier import TelegramNotifier
    return TelegramNotifier().send_message(text)
