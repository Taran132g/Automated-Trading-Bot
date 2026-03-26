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


def get_previous_reports(agent_name: str, limit: int = 5) -> list[dict]:
    """Return the last N saved reports for agent_name (most recent first).
    Call this BEFORE save_report() so the current run is not included."""
    ensure_reports_table()
    with closing(get_db()) as conn:
        rows = conn.execute(
            "SELECT timestamp, report_data, report_markdown FROM agent_reports "
            "WHERE agent_name = ? ORDER BY timestamp DESC LIMIT ?",
            (agent_name, limit),
        ).fetchall()
    return [
        {
            "timestamp": ts,
            "report_data": json.loads(data) if data else {},
            "report_markdown": md or "",
        }
        for ts, data, md in rows
    ]


def call_claude(prompt: str, max_tokens: int = 300) -> str | None:
    """Call Claude and return the response text, or None on failure."""
    import os
    try:
        import anthropic
    except ImportError:
        LOGGER.warning("anthropic package not installed; skipping Claude analysis")
        return None
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        LOGGER.warning("ANTHROPIC_API_KEY not set; skipping Claude analysis")
        return None
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as exc:
        LOGGER.warning("Claude API call failed: %s", exc)
        return None
