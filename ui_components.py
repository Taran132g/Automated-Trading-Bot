import streamlit as st
import subprocess
from pathlib import Path
import json
import time

DB_PATH = Path("penny_basing.db").resolve()
PAPER_STATE_PATH = Path("paper_trader_state.json").resolve()

# Live state path
LIVE_STATE_PATH = Path("live_trader_state.json").resolve()

def is_backend_running():
    loop_result = subprocess.run(["pgrep", "-f", "restart_loop.sh"], capture_output=True)
    grok_result = subprocess.run(["pgrep", "-f", "grok.py"], capture_output=True)
    return loop_result.returncode == 0 or grok_result.returncode == 0

def load_live_state():
    if LIVE_STATE_PATH.exists():
        try:
            with open(LIVE_STATE_PATH, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def load_paper_state():
    if PAPER_STATE_PATH.exists():
        try:
            with open(PAPER_STATE_PATH, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def has_live_position():
    state = load_live_state()
    positions = state.get('positions', {})
    # Return true if any position qty is != 0
    return positions and any(qty != 0 for qty in positions.values())

def render_system_status():
    # Hide Admin Controls from auto-generated sidebar nav (we have a button for it)
    # Also prevent sidebar from being collapsed
    st.markdown("""
        <style>
            [data-testid="stSidebarNav"] li:last-child { display: none; }
            [data-testid="collapsedControl"] { display: none !important; }
            [data-testid="stSidebarCollapseButton"] { display: none !important; }
            section[data-testid="stSidebar"] {
                min-width: 300px !important;
                width: 300px !important;
                transform: none !important;
                visibility: visible !important;
            }
            section[data-testid="stSidebar"] > div { width: 300px !important; }
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="section-header">System Infrastructure</div>', unsafe_allow_html=True)
    
    bot_status = "online" if is_backend_running() else "offline"
    db_status = "online" if DB_PATH.exists() else "offline"
    
    paper_state = load_paper_state()
    paper_status = "online" if paper_state else "offline"
    
    live_pos_status = "online" if has_live_position() else "offline"
    live_pos_text = "Live Position Held" if live_pos_status == "online" else "Flat / No Live Position"
    
    st.markdown(f"""
        <style>
        .sys-status-item {{
            display: flex;
            align-items: center;
            margin-bottom: 12px;
            font-size: 0.9rem;
            color: #94A3B8;
        }}
        .status-dot {{
            height: 8px;
            width: 8px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 10px;
        }}
        .status-dot.online {{
            background-color: #00FF99;
            box-shadow: 0 0 8px #00FF99;
        }}
        .status-dot.offline {{
            background-color: #EF4444;
            box-shadow: 0 0 8px #EF4444;
        }}
        </style>
        <div class="sys-status-item" title="The master trading bot process handling entry/exit logic and auto-restarts">
            <span class="status-dot {bot_status}"></span>
            <span>Trading Bot Backend</span>
        </div>
        <div class="sys-status-item" title="Current state of live trading positions">
            <span class="status-dot {live_pos_status}"></span>
            <span>{live_pos_text}</span>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-header">Core Modules</div>', unsafe_allow_html=True)
    
    # Unified Navigation
    st.page_link("pages/1_📈_Terminal.py", label="Execution Terminal", icon="📈", use_container_width=True)
    st.page_link("pages/2_📊_Analytics_&_Heatmap.py", label="Analytics & Risk", icon="📊", use_container_width=True)
    st.page_link("pages/2_🔍_Backtest.py", label="Paper Trading", icon="🔍", use_container_width=True)
    st.page_link("pages/5_⚙️_Admin_Controls.py", label="Admin Controls", icon="⚙️", use_container_width=True)
        
    st.markdown("<br><br>", unsafe_allow_html=True)
    if st.button("🔌 Disconnect Session", use_container_width=True):
        import auth_manager
        auth_manager.logout()
        st.switch_page("app.py")
