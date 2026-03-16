import sqlite3
import json
import sys
from pathlib import Path
from contextlib import closing
from datetime import datetime

import pandas as pd
import streamlit as st
import pytz

sys.path.append(str(Path(__file__).parent.parent))
from dotenv import load_dotenv
import auth_manager

load_dotenv()

DB_PATH = Path("penny_basing.db").resolve()
ET = pytz.timezone("America/New_York")

st.set_page_config(
    page_title="Agent Reports",
    layout="wide",
    page_icon="🤖",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
        .stApp {
            background-color: #0B0E14;
            color: #E2E8F0;
            font-family: 'Inter', sans-serif;
        }
        #MainMenu, footer { visibility: hidden; }
        .block-container { padding-top: 1rem; max-width: 98%; }

        [data-testid="stMetricValue"] {
            font-size: 1.8rem !important;
            font-weight: 700 !important;
            color: #F8FAFC !important;
            font-family: 'Roboto Mono', monospace;
        }

        .report-card {
            background: #111827;
            border: 1px solid #1E293B;
            border-radius: 8px;
            padding: 1.2rem 1.5rem;
            margin-bottom: 1rem;
        }

        .report-header {
            font-size: 1rem;
            font-weight: 600;
            color: #A855F7;
            margin-bottom: 0.4rem;
        }

        .report-ts {
            font-size: 0.75rem;
            color: #64748B;
            margin-bottom: 0.8rem;
        }

        .agent-badge {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            margin-right: 8px;
        }

        .badge-post_market   { background: #1E3A5F; color: #60A5FA; }
        .badge-alert_quality { background: #1A3A2A; color: #4ADE80; }
        .badge-risk_monitor  { background: #3A1A1A; color: #F87171; }
        .badge-optimizer     { background: #2A1F3A; color: #C084FC; }
    </style>
""", unsafe_allow_html=True)

# --- Auth ---
if not auth_manager.is_authenticated():
    auth_manager.show_login()
    st.stop()


def get_db():
    return sqlite3.connect(str(DB_PATH))


def ensure_table():
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


def load_reports(agent_filter: str | None = None) -> pd.DataFrame:
    ensure_table()
    query = "SELECT id, timestamp, agent_name, report_markdown, report_data FROM agent_reports"
    params = ()
    if agent_filter and agent_filter != "All":
        query += " WHERE agent_name = ?"
        params = (agent_filter,)
    query += " ORDER BY timestamp DESC"
    with closing(get_db()) as conn:
        return pd.read_sql_query(query, conn, params=params)


AGENT_LABELS = {
    "post_market": "📊 Post-Market",
    "alert_quality": "🔬 Alert Quality",
    "risk_monitor": "🚨 Risk Monitor",
    "optimizer": "⚙️ Optimizer",
}

# --- Header ---
st.markdown("## 🤖 Agent Reports")
st.markdown("Browse Claude-generated analysis reports from all trading agents.")

col_filter, col_count = st.columns([2, 4])
with col_filter:
    filter_options = ["All"] + list(AGENT_LABELS.keys())
    selected_filter = st.selectbox(
        "Filter by agent",
        options=filter_options,
        format_func=lambda x: "All Agents" if x == "All" else AGENT_LABELS.get(x, x)
    )

df = load_reports(selected_filter if selected_filter != "All" else None)

with col_count:
    st.markdown(f"<br><span style='color:#64748B;font-size:0.9rem'>{len(df)} report(s)</span>", unsafe_allow_html=True)

if df.empty:
    st.info("No agent reports found. Run an agent to generate the first report.")
    st.stop()

# --- Report list ---
for _, row in df.iterrows():
    agent = row["agent_name"]
    label = AGENT_LABELS.get(agent, agent)
    badge_class = f"badge-{agent}"

    ts = datetime.fromtimestamp(row["timestamp"], tz=ET).strftime("%b %d, %Y at %I:%M %p ET")

    with st.container():
        st.markdown(
            f'<div class="report-card">'
            f'<div class="report-header">'
            f'<span class="agent-badge {badge_class}">{label}</span>'
            f'</div>'
            f'<div class="report-ts">{ts}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

        with st.expander(f"View report — {ts}", expanded=False):
            st.markdown(row["report_markdown"])

            raw = row["report_data"]
            if raw:
                try:
                    data = json.loads(raw)
                    with st.expander("Raw stats (JSON)", expanded=False):
                        st.json(data)
                except Exception:
                    pass

        st.markdown("---")
