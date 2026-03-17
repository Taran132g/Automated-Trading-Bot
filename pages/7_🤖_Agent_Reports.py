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

load_dotenv()

from agents.post_market_csv import run_from_upload, extract_date_from_filename

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

# --- Post-Market Upload ---
if "last_report" not in st.session_state:
    st.session_state.last_report = None

with st.expander("📤 Upload Post-Market Trade Activity", expanded=True):
    st.markdown(
        "<span style='color:#94A3B8;font-size:0.85rem'>"
        "Upload a Schwab trade activity export (HTML). "
        "Filename must contain the date, e.g. <code>2026-03-16-TradeActivity.html</code>."
        "</span>",
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader(
        "Drop file here", type=["html", "htm", "csv", "txt"],
        label_visibility="collapsed",
    )
    if uploaded is not None:
        date_str = extract_date_from_filename(uploaded.name)
        if not date_str:
            st.error(f"Could not find a YYYY-MM-DD date in filename: `{uploaded.name}`")
        else:
            st.markdown(
                f"<span style='color:#64748B;font-size:0.85rem'>Detected date: <b>{date_str}</b></span>",
                unsafe_allow_html=True,
            )
            if st.button("Generate Report", type="primary"):
                with st.spinner("Parsing trades and generating report…"):
                    try:
                        report_md, report_data = run_from_upload(
                            uploaded.getvalue(), uploaded.name
                        )
                        st.session_state.last_report = (report_md, report_data)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Error: {exc}")
                        st.session_state.last_report = None

# Show last generated report (persists across rerun via session_state)
if st.session_state.last_report is not None:
    _report_md, _report_data = st.session_state.last_report
    _tg_ok = _report_data.get("telegram_sent", False)
    if _tg_ok:
        st.success("Report saved and sent to Telegram.")
    else:
        st.warning("Report saved. Telegram notification failed — check bot token/chat ID in logs.")
    st.markdown("---")
    st.markdown(_report_md)

    _trips = _report_data.get("trip_stats", {})

    def _fmt_row(r):
        aps = r.get("avg_pnl_per_share")
        return {
            "Trips":      r["count"],
            "Wins":       r.get("wins", ""),
            "Win Rate":   f"{r['win_rate']}%" if r.get("win_rate") is not None else "N/A",
            "Total PnL":  f"${r['total_pnl']:+.4f}",
            "PnL/Share":  f"${aps:+.4f}" if aps is not None else "N/A",
        }

    _by_sym = _trips.get("by_symbol", [])
    if _by_sym:
        st.markdown("**By Symbol**")
        st.dataframe(
            pd.DataFrame([{"Symbol": s["symbol"], **_fmt_row(s)} for s in _by_sym]),
            use_container_width=True, hide_index=True,
        )

    _by_bucket = _trips.get("by_bucket", [])
    if _by_bucket:
        st.markdown("**By Pattern Bucket**")
        _BEMOJI = {"aligned": "✅", "countertrend": "❌", "neutral": "⚪"}
        st.dataframe(
            pd.DataFrame([{
                "Bucket": f"{_BEMOJI.get(b['bucket'], '⚪')} {b['bucket']}",
                **_fmt_row(b),
            } for b in _by_bucket]),
            use_container_width=True, hide_index=True,
        )

    _by_sb = _trips.get("by_symbol_bucket", [])
    if _by_sb:
        st.markdown("**By Symbol × Pattern Bucket**")
        _BEMOJI = {"aligned": "✅", "countertrend": "❌", "neutral": "⚪"}
        _BORDER = ["aligned", "countertrend", "neutral"]
        _rows_sb = sorted(
            _by_sb,
            key=lambda x: (x["symbol"], _BORDER.index(x["bucket"]) if x["bucket"] in _BORDER else 99)
        )
        st.dataframe(
            pd.DataFrame([{
                "Symbol": r["symbol"],
                "Bucket": f"{_BEMOJI.get(r['bucket'], '⚪')} {r['bucket']}",
                **_fmt_row(r),
            } for r in _rows_sb]),
            use_container_width=True, hide_index=True,
        )

st.markdown("---")
st.markdown("**Report History**")

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

                    # --- Round-trip tables for post_market reports ---
                    trip_stats = data.get("trip_stats", {})
                    if trip_stats and agent == "post_market":
                        BEMOJI = {"aligned": "✅", "countertrend": "❌", "neutral": "⚪"}
                        BORDER = ["aligned", "countertrend", "neutral"]

                        def _row(r):
                            aps = r.get("avg_pnl_per_share")
                            return {
                                "Trips":     r["count"],
                                "Wins":      r.get("wins", ""),
                                "Win Rate":  f"{r['win_rate']}%" if r.get("win_rate") is not None else "N/A",
                                "Total PnL": f"${r['total_pnl']:+.4f}",
                                "PnL/Share": f"${aps:+.4f}" if aps is not None else "N/A",
                            }

                        by_sym = trip_stats.get("by_symbol", [])
                        if by_sym:
                            st.markdown("**By Symbol**")
                            st.dataframe(
                                pd.DataFrame([{"Symbol": s["symbol"], **_row(s)} for s in by_sym]),
                                use_container_width=True, hide_index=True,
                            )

                        by_bucket = trip_stats.get("by_bucket", [])
                        if by_bucket:
                            st.markdown("**By Pattern Bucket**")
                            st.dataframe(
                                pd.DataFrame([{
                                    "Bucket": f"{BEMOJI.get(b['bucket'], '⚪')} {b['bucket']}",
                                    **_row(b),
                                } for b in by_bucket]),
                                use_container_width=True, hide_index=True,
                            )

                        by_sym_bucket = trip_stats.get("by_symbol_bucket", [])
                        if by_sym_bucket:
                            st.markdown("**By Symbol × Pattern Bucket**")
                            sorted_sb = sorted(
                                by_sym_bucket,
                                key=lambda x: (x["symbol"], BORDER.index(x["bucket"]) if x["bucket"] in BORDER else 99)
                            )
                            st.dataframe(
                                pd.DataFrame([{
                                    "Symbol": r["symbol"],
                                    "Bucket": f"{BEMOJI.get(r['bucket'], '⚪')} {r['bucket']}",
                                    **_row(r),
                                } for r in sorted_sb]),
                                use_container_width=True, hide_index=True,
                            )

                    with st.expander("Raw stats (JSON)", expanded=False):
                        st.json(data)
                except Exception:
                    pass

        st.markdown("---")
