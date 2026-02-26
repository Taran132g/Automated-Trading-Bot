import os
import json
import subprocess
import time
import streamlit as st
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))
import config_manager
import auth_manager
import schwab.auth
from datetime import datetime

# Check authentication
auth_manager.require_auth()

st.set_page_config(
    page_title="Admin Controls | Dashboard",
    layout="wide",
    page_icon="⚙️",
    initial_sidebar_state="expanded"
)

# CSS Styling (Terminal Theme)
st.markdown("""
    <style>
        .stApp {
            background-color: #0B0E14; 
            color: #E2E8F0;
            font-family: 'Inter', sans-serif;
        }
        #MainMenu, header, footer { visibility: hidden; }
        .block-container { padding-top: 1rem; max-width: 98%; }
        
        .section-header {
            font-weight: 600;
            font-size: 1.1rem;
            color: #94A3B8;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 1rem;
            border-bottom: 1px solid #1F2937;
            padding-bottom: 5px;
        }
        
        /* Admin Controls Styling */
        .admin-header {
            background: linear-gradient(90deg, #111827 0%, #1F2937 100%);
            border-radius: 8px;
            padding: 1.5rem;
            border-left: 4px solid #3b82f6;
            margin-bottom: 1.5rem;
        }
        .admin-title {
            font-family: 'Inter', sans-serif;
            font-size: 1.8rem;
            font-weight: 700;
            color: #F8FAFC;
            margin-bottom: 0.25rem;
            letter-spacing: -0.5px;
        }
        .admin-subtitle {
            color: #94A3B8;
            font-size: 0.9rem;
            font-family: 'Roboto Mono', monospace;
        }
        .status-box {
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-family: 'Roboto Mono', monospace;
        }
        .status-running {
            background: rgba(0, 255, 153, 0.05);
            border: 1px solid rgba(0, 255, 153, 0.3);
            color: #00FF99;
        }
        .status-stopped {
            background: rgba(239, 68, 68, 0.05);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #EF4444;
        }
        .position-item {
            background: #111827;
            padding: 0.75rem 1rem;
            border-radius: 4px;
            margin-bottom: 0.5rem;
            display: flex;
            justify-content: space-between;
            border: 1px solid #1F2937;
            font-family: 'Roboto Mono', monospace;
        }
        .destruct-box {
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(28, 6, 6, 0.5) 100%);
            border-radius: 8px;
            padding: 1.5rem;
            border: 1px solid #EF4444;
            text-align: center;
            margin-top: 1rem;
        }
    </style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ⚡ QUANT_OS // V2.0")
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-header">Core Modules</div>', unsafe_allow_html=True)
    if st.button("📈 Execution Terminal", use_container_width=True):
        st.switch_page("pages/1_📈_Terminal.py")
    if st.button("📊 Analytics & Risk", use_container_width=True):
        st.switch_page("pages/2_📊_Analytics_&_Heatmap.py")
    st.button("⚙️ Admin Controls", use_container_width=True, type="primary")
    
    st.markdown("<br><br>", unsafe_allow_html=True)
    if st.button("🔌 Disconnect Session", use_container_width=True):
        # auth_manager.logout()
        st.switch_page("app.py")

# Load live positions
LIVE_STATE_PATH = Path("live_trader_state.json").resolve()
PRIMARY_STATE = Path("live_trader_state_primary.json").resolve()
if PRIMARY_STATE.exists():
    LIVE_STATE_PATH = PRIMARY_STATE

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
    # Check for either the restart loop or grok.py directly
    loop_result = subprocess.run(["pgrep", "-f", "restart_loop.sh"], capture_output=True)
    grok_result = subprocess.run(["pgrep", "-f", "grok.py"], capture_output=True)
    return loop_result.returncode == 0 or grok_result.returncode == 0

def start_backend():
    """Start the backend via restart loop (auto-restarts on crash)."""
    try:
        project_root = Path(__file__).parent.parent.resolve()
        
        # Remove kill switch if exists
        kill_switch = project_root / "kill_switch.flag"
        if kill_switch.exists():
            kill_switch.unlink()
        
        # Start via manage_backend.sh which launches the restart loop
        loop_script = project_root / "restart_loop.sh"
        loop_script.chmod(0o755)
        
        subprocess.Popen(
            ["bash", str(loop_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(project_root),
            start_new_session=True
        )
        return "✅ Backend starting (auto-restart enabled)..."
    except Exception as e:
        return f"❌ Error: {str(e)}"

def stop_backend():
    """Stop the backend — kills restart loop + all processes."""
    try:
        # Kill the restart loop first
        subprocess.run(["pkill", "-f", "restart_loop.sh"], capture_output=True)
        # Then kill grok and paper trader
        subprocess.run(["pkill", "-f", "grok.py"], capture_output=True)
        subprocess.run(["pkill", "-f", "paper_trader.py"], capture_output=True)
        
        Path("kill_switch.flag").touch()
        return "✅ Backend stopped"
    except Exception as e:
        return f"❌ Error: {str(e)}"

def flatten_all_positions():
    """Close all live positions by placing opposite orders."""
    if is_backend_running():
        return "❌ Error: Backend is running. Stop it first to avoid state corruption."

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
                    res = executor.submit_market(symbol=symbol, qty=abs(qty), side="COVER")
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

# Secondary password check removed
if True:
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
        
        if st.button("🔴 FLATTEN ALL POSITIONS", type="primary", use_container_width=True, disabled=backend_running):
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
            # 1. Stop backend first to release state file
            kill_result = stop_backend()
            time.sleep(2) # Wait for shutdown
            
            # 2. Now safe to flatten
            flatten_result = flatten_all_positions()
        
        st.error("🔥 SHUTDOWN EXECUTED")
        st.code(f"{kill_result}\n\n{flatten_result}")

    st.divider()
    
    # --- Schwab Token Management ---
    st.subheader("🔑 Schwab Token Management")
    
    token_path = Path("schwab_tokens.json")
    if token_path.exists():
        mtime = datetime.fromtimestamp(token_path.stat().st_mtime)
        st.info(f"✅ **Token File Found**: Last updated {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        st.warning("⚠️ **Token File Missing**: Backend will not start without valid tokens.")

    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Step 1: Generate Link")
        if st.button("🔗 Generate Auth Link", use_container_width=True):
            try:
                api_key = os.getenv("SCHWAB_CLIENT_ID")
                redirect_uri = os.getenv("SCHWAB_REDIRECT_URI")
                if not api_key or not redirect_uri:
                    st.error("Missing SCHWAB_CLIENT_ID or SCHWAB_REDIRECT_URI in .env")
                else:
                    auth_context = schwab.auth.get_auth_context(api_key, redirect_uri)
                    st.session_state.schwab_auth_context = auth_context
                    st.success("Link generated! Click below to log in:")
                    st.markdown(f"[Login to Schwab]({auth_context.authorization_url})")
            except Exception as e:
                st.error(f"Error generating link: {e}")

    with col2:
        st.markdown("### Step 2: Paste Callback")
        callback_url = st.text_input("Paste the full URL you were redirected to:", key="schwab_callback_input")
        if st.button("💾 Save New Tokens", type="primary", use_container_width=True):
            if not callback_url:
                st.error("Please paste the URL first.")
            elif 'schwab_auth_context' not in st.session_state:
                st.error("Please generate the auth link first (Step 1).")
            else:
                try:
                    api_key = os.getenv("SCHWAB_CLIENT_ID")
                    app_secret = os.getenv("SCHWAB_APP_SECRET")
                    auth_context = st.session_state.schwab_auth_context
                    
                    # This function exchanges the URL for tokens and writes them to the path
                    # we provide in a custom write function.
                    def token_writer(token):
                        with open("schwab_tokens.json", "w") as f:
                            json.dump(token, f, indent=4)
                    
                    schwab.auth.client_from_received_url(
                        api_key=api_key,
                        app_secret=app_secret,
                        auth_context=auth_context,
                        received_url=callback_url,
                        token_write_func=token_writer
                    )
                    st.success("✅ Tokens saved successfully! You can now start the backend.")
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving tokens: {e}")

    st.divider()

    # --- Configuration ---
    st.subheader("🛠️ Configuration")
    
    config = config_manager.load_config()
    
    with st.form("config_form"):
        new_live_symbols = st.text_input("Live Symbols (comma-separated)", value=config.get("live_symbols", ""))
        new_paper_symbols = st.text_input("Paper Symbols (comma-separated)", value=config.get("paper_symbols", ""))
        
        c1, c2 = st.columns(2)
        with c1:
            new_live_size = st.number_input("Live Position Size", value=config.get("live_position_size", 100))
            new_live_max_trades = st.number_input("Max Live Trades/Hour", value=config.get("live_max_trades_per_hour", 60))
        with c2:
            new_paper_size = st.number_input("Paper Position Size", value=config.get("paper_position_size", 1000))
            new_stop_loss = st.number_input("Account Stop Loss ($) (0 to disable)", value=float(config.get("account_stop_loss", 0.0)))
            
        if st.form_submit_button("💾 Save Configuration", type="primary", use_container_width=True):
            new_config = {
                "live_symbols": new_live_symbols,
                "paper_symbols": new_paper_symbols,
                "live_position_size": int(new_live_size),
                "paper_position_size": int(new_paper_size),
                "live_max_trades_per_hour": int(new_live_max_trades),
                "account_stop_loss": float(new_stop_loss)
            }
            if config_manager.save_config(new_config):
                st.success("Configuration saved successfully!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Failed to save configuration.")

# End of script
