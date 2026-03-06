import streamlit as st
import pandas as pd
import time
from datetime import datetime
from log_parser import tail_log_file, categorize_logs
import os

# Page Config
st.set_page_config(
    page_title="Grok Log Monitor",
    page_icon="🔍",
    layout="wide"
)

# Custom CSS for a premium look
st.markdown("""
    <style>
    .stApp {
        background-color: #0e0e0e;
    }
    .metric-card {
        background-color: #1a1a1a;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #00ff00;
        margin-bottom: 20px;
    }
    .alert-bid { color: #00ff00; font-weight: bold; }
    .alert-ask { color: #ff4b4b; font-weight: bold; }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #1a1a1a;
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #262626;
        border-bottom: 2px solid #00ff00;
    }
    </style>
""", unsafe_allow_html=True)

# Sidebar Filters
st.sidebar.title("🔍 Monitor Filters")
LOG_PATH = "grok.log"
NUM_LINES = st.sidebar.slider("Lines to tail", 100, 5000, 1000)
REFRESH_RATE = st.sidebar.slider("Refresh rate (sec)", 1, 10, 2)
SYMBOL_FILTER = st.sidebar.text_input("Filter by Symbol").upper()
LEVEL_FILTER = st.sidebar.multiselect("Log Levels", ["INFO", "WARNING", "ERROR"], default=["INFO", "WARNING", "ERROR"])

# Main Title
st.title("🔍 Grok Log Monitor")

# Data Loading
def load_data():
    raw_logs = tail_log_file(LOG_PATH, num_lines=NUM_LINES)
    if SYMBOL_FILTER:
        raw_logs = [l for l in raw_logs if SYMBOL_FILTER in str(l.get("symbol", "")).upper()]
    if LEVEL_FILTER:
        raw_logs = [l for l in raw_logs if l.get("level") in LEVEL_FILTER]
    return raw_logs

logs = load_data()
categories = categorize_logs(logs)

# Top Metrics
m1, m2, m3, m4 = st.columns(4)

last_heartbeat = "N/A"
if categories["SYSTEM"]:
    hb = [l for l in categories["SYSTEM"] if l.get("event") == "HEARTBEAT"]
    if hb:
        last_ts = hb[-1].get("timestamp")
        last_heartbeat = last_ts

total_alerts = len(categories["ALERT"])
error_count = len(categories["ERROR"])

with m1:
    st.metric("Total Alerts (Tail)", total_alerts)
with m2:
    st.metric("Errors/Warnings", error_count, delta=-1 if error_count == 0 else 1, delta_color="inverse")
with m3:
    st.metric("Last Heartbeat", last_heartbeat.split(" ")[1] if " " in last_heartbeat else last_heartbeat)
with m4:
    st.metric("Sync Status", "LIVE 🟢" if (time.time() % 2 < 1) else "LIVE ⚪")

# Tabs
tab_alerts, tab_market, tab_imbalance, tab_system = st.tabs([
    "🚨 Alerts", 
    "📊 Market Flux", 
    "⚡ Imbalance Logs", 
    "💻 System & Raw"
])

with tab_alerts:
    if categories["ALERT"]:
        df_alerts = pd.DataFrame(categories["ALERT"])
        cols = ["timestamp", "symbol", "direction", "price", "ratio", "heavy_venues"]
        display_cols = [c for c in cols if c in df_alerts.columns]
        st.dataframe(df_alerts[display_cols].sort_values("timestamp", ascending=False), use_container_width=True)
    else:
        st.info("No alerts found in the current log tail.")

with tab_market:
    col_rolls, col_book = st.columns(2)
    market_logs = categories["MARKET"]
    
    with col_rolls:
        st.subheader("Volume Rolls")
        rolls = [l for l in market_logs if l.get("event") == "ROLL"]
        if rolls:
            st.dataframe(pd.DataFrame(rolls).sort_values("timestamp", ascending=False), use_container_width=True)
    
    with col_book:
        st.subheader("Book Summaries")
        books = [l for l in market_logs if l.get("event") == "BOOK_SUMMARY"]
        if books:
            st.dataframe(pd.DataFrame(books).sort_values("timestamp", ascending=False), use_container_width=True)

with tab_imbalance:
    st.subheader("Detailed Imbalance Debugging")
    imbalances = [l for l in categories["MARKET"] if l.get("event") == "IMBALANCE_DEBUG"]
    if imbalances:
        st.dataframe(pd.DataFrame(imbalances).sort_values("timestamp", ascending=False), use_container_width=True)
    else:
        st.write("No imbalance debug logs found.")

with tab_system:
    st.subheader("Raw Log History")
    st.dataframe(pd.DataFrame(logs).sort_values("timestamp", ascending=False), use_container_width=True)

# Auto-refresh
time.sleep(REFRESH_RATE)
st.rerun()
