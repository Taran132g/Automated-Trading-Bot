import os
import json
import subprocess
import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="Admin Controls | Dashboard",
    layout="centered",
    page_icon="⚙️"
)

# Check main authentication first
if 'authenticated' not in st.session_state or not st.session_state.authenticated:
    st.switch_page("app.py")

# CSS
st.markdown("""
    <style>
        .block-container { 
            padding-top: 2rem;
            max-width: 600px;
        }
        .admin-header {
            background: linear-gradient(135deg, #1e40af 0%, #1e3a5f 100%);
            border-radius: 16px;
            padding: 1.5rem;
            border: 1px solid #3b82f6;
            text-align: center;
            margin-bottom: 1.5rem;
        }
        .admin-title {
            font-size: 1.8rem;
            font-weight: 700;
            color: #60a5fa;
            margin-bottom: 0.25rem;
        }
        .admin-subtitle {
            color: #93c5fd;
            font-size: 0.85rem;
        }
        .status-box {
            padding: 1rem;
            border-radius: 12px;
            margin-bottom: 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .status-running {
            background: rgba(0, 255, 153, 0.1);
            border: 1px solid #00FF99;
        }
        .status-stopped {
            background: rgba(255, 51, 102, 0.1);
            border: 1px solid #FF3366;
        }
        .position-item {
            background: rgba(30, 41, 59, 0.8);
            padding: 0.75rem 1rem;
            border-radius: 8px;
            margin-bottom: 0.5rem;
            display: flex;
            justify-content: space-between;
        }
        .destruct-box {
            background: linear-gradient(135deg, #450a0a 0%, #1c0606 100%);
            border-radius: 16px;
            padding: 1.5rem;
            border: 2px solid #dc2626;
            text-align: center;
            margin-top: 1rem;
        }
    </style>
""", unsafe_allow_html=True)

# Load live positions
LIVE_STATE_PATH = Path("live_trader_state.json").resolve()

def load_live_positions():
    if LIVE_STATE_PATH.exists():
        try:
            with open(LIVE_STATE_PATH, 'r') as f:
                state = json.load(f)
                return state.get('positions', {})
        except:
            return {}
    return {}

def is_backend_running():
    """Check if backend processes are running."""
    result = subprocess.run(["pgrep", "-f", "grok.py"], capture_output=True)
    return result.returncode == 0

def start_backend():
    """Start the backend processes."""
    try:
        # Get project root (parent of pages/)
        project_root = Path(__file__).parent.parent.resolve()
        
        # Remove kill switch if exists
        kill_switch = project_root / "kill_switch.flag"
        if kill_switch.exists():
            kill_switch.unlink()
        
        # Start backend via script with proper cwd
        script_path = project_root / "start_backend.sh"
        subprocess.Popen(
            [str(script_path)], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            cwd=str(project_root),
            start_new_session=True
        )
        return "✅ Backend starting..."
    except Exception as e:
        return f"❌ Error: {str(e)}"

def stop_backend():
    """Stop the backend processes."""
    try:
        subprocess.run(["pkill", "-f", "grok.py"], capture_output=True)
        subprocess.run(["pkill", "-f", "paper_trader.py"], capture_output=True)
        subprocess.run(["pkill", "-f", "live_trader.py"], capture_output=True)
        
        Path("kill_switch.flag").touch()
        return "✅ Backend stopped"
    except Exception as e:
        return f"❌ Error: {str(e)}"

def flatten_all_positions():
    """Close all live positions by placing opposite orders."""
    positions = load_live_positions()
    
    if not positions:
        return "No positions to flatten"
    
    try:
        from live_trader import SchwabOrderExecutor
        executor = SchwabOrderExecutor(dry_run=False)
        
        results = []
        for symbol, qty in positions.items():
            if qty == 0:
                continue
                
            try:
                if qty > 0:
                    res = executor.submit_market(symbol=symbol, qty=qty, side="SELL")
                    if res.get("error"):
                        results.append(f"❌ Failed {symbol}: {res['error']}")
                    else:
                        results.append(f"✅ SOLD {qty} {symbol}")
                else:
                    res = executor.submit_market(symbol=symbol, qty=abs(qty), side="BUY")
                    if res.get("error"):
                        results.append(f"❌ Failed {symbol}: {res['error']}")
                    else:
                        results.append(f"✅ COVERED {abs(qty)} {symbol}")
            except Exception as e:
                results.append(f"❌ Failed {symbol}: {str(e)}")
        
        with open(LIVE_STATE_PATH, 'w') as f:
            json.dump({"positions": {}, "last_alert_id": 0}, f)
        
        return "\n".join(results) if results else "No positions to flatten"
    except Exception as e:
        return f"Error: {str(e)}"

# Header
st.markdown("""
    <div class="admin-header">
        <div class="admin-title">⚙️ Admin Controls</div>
        <div class="admin-subtitle">Backend management and emergency controls</div>
    </div>
""", unsafe_allow_html=True)

# Secondary password check
if 'admin_authorized' not in st.session_state:
    st.session_state.admin_authorized = False

if not st.session_state.admin_authorized:
    st.warning("🔐 Additional authorization required")
    
    admin_pass = st.text_input(
        "Enter admin code",
        type="password",
        placeholder="Enter code...",
        label_visibility="collapsed"
    )
    
    if st.button("Authorize", type="secondary", use_container_width=True):
        if admin_pass == "mi bombaclat":
            st.session_state.admin_authorized = True
            st.rerun()
        else:
            st.error("Invalid authorization code")
else:
    # --- Backend Status ---
    st.subheader("🖥️ Backend Status")
    backend_running = is_backend_running()
    
    if backend_running:
        st.markdown("""
            <div class="status-box status-running">
                <span style="font-weight: bold; color: #00FF99;">🟢 RUNNING</span>
                <span style="color: #94a3b8;">Backend processes active</span>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
            <div class="status-box status-stopped">
                <span style="font-weight: bold; color: #FF3366;">🔴 STOPPED</span>
                <span style="color: #94a3b8;">Backend processes inactive</span>
            </div>
        """, unsafe_allow_html=True)
    
    # Backend control buttons
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("▶️ START BACKEND", type="primary", use_container_width=True, disabled=backend_running):
            result = start_backend()
            st.success(result)
            st.rerun()
    
    with col2:
        if st.button("⏹️ STOP BACKEND", type="secondary", use_container_width=True, disabled=not backend_running):
            result = stop_backend()
            st.warning(result)
            st.rerun()
    
    st.divider()
    
    # --- Live Positions ---
    st.subheader("📊 Current Live Positions")
    positions = load_live_positions()
    
    if positions:
        for symbol, qty in positions.items():
            if qty != 0:
                pos_type = "LONG" if qty > 0 else "SHORT"
                color = "#00FF99" if qty > 0 else "#FF3366"
                st.markdown(f"""
                    <div class="position-item">
                        <span style="font-weight: bold;">{symbol}</span>
                        <span style="color: {color};">{abs(qty)} shares ({pos_type})</span>
                    </div>
                """, unsafe_allow_html=True)
        
        if st.button("🔴 FLATTEN ALL POSITIONS", type="primary", use_container_width=True):
            with st.spinner("Flattening positions..."):
                result = flatten_all_positions()
            st.success(result)
            st.rerun()
    else:
        st.info("No open positions")
    
    st.divider()
    
    # --- Nuclear Option ---
    st.markdown("""
        <div class="destruct-box">
            <div style="font-size: 1.3rem; font-weight: 700; color: #ef4444; margin-bottom: 0.5rem;">☢️ Nuclear Option</div>
            <div style="color: #fca5a5; font-size: 0.85rem;">Flatten all positions AND kill backend</div>
        </div>
    """, unsafe_allow_html=True)
    
    if st.button("💥 EXECUTE FULL SHUTDOWN", type="primary", use_container_width=True):
        with st.spinner("Executing shutdown..."):
            flatten_result = flatten_all_positions()
            kill_result = stop_backend()
        
        st.error("🔥 SHUTDOWN EXECUTED")
        st.code(f"{flatten_result}\n\n{kill_result}")

# Sidebar nav
with st.sidebar:
    st.markdown("### 📍 Navigation")
    if st.button("📈 Live Trading", use_container_width=True):
        st.switch_page("pages/2_📈_Live_Trading.py")
    if st.button("🔬 Backtesting", use_container_width=True):
        st.switch_page("pages/3_🔬_Backtest.py")
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.admin_authorized = False
        st.switch_page("app.py")
