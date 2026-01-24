import os
import json
import subprocess
import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="Self Destruct | Dashboard",
    layout="centered",
    page_icon="💀"
)

# Check main authentication first
if 'authenticated' not in st.session_state or not st.session_state.authenticated:
    st.switch_page("app.py")

# CSS
st.markdown("""
    <style>
        .block-container { 
            padding-top: 3rem;
            max-width: 500px;
        }
        .destruct-box {
            background: linear-gradient(135deg, #450a0a 0%, #1c0606 100%);
            border-radius: 16px;
            padding: 2rem;
            border: 2px solid #dc2626;
            text-align: center;
            margin-bottom: 2rem;
        }
        .destruct-title {
            font-size: 2rem;
            font-weight: 700;
            color: #ef4444;
            margin-bottom: 0.5rem;
        }
        .destruct-warning {
            color: #fca5a5;
            font-size: 0.9rem;
        }
        .position-item {
            background: rgba(30, 41, 59, 0.8);
            padding: 0.75rem 1rem;
            border-radius: 8px;
            margin-bottom: 0.5rem;
            display: flex;
            justify-content: space-between;
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
                    # Long position - sell to close
                    res = executor.submit_market(symbol=symbol, qty=qty, side="SELL")
                    if res.get("error"):
                        results.append(f"❌ Failed {symbol}: {res['error']}")
                    else:
                        results.append(f"✅ SOLD {qty} {symbol}")
                else:
                    # Short position - buy to cover
                    res = executor.submit_market(symbol=symbol, qty=abs(qty), side="BUY")
                    if res.get("error"):
                        results.append(f"❌ Failed {symbol}: {res['error']}")
                    else:
                        results.append(f"✅ COVERED {abs(qty)} {symbol}")
            except Exception as e:
                results.append(f"❌ Failed {symbol}: {str(e)}")
        
        # Clear state file
        with open(LIVE_STATE_PATH, 'w') as f:
            json.dump({"positions": {}, "last_alert_id": 0}, f)
        
        return "\n".join(results) if results else "No positions to flatten"
    except Exception as e:
        return f"Error: {str(e)}"

def kill_backend():
    """Kill the trading bot processes."""
    try:
        # Kill grok.py and related processes
        subprocess.run(["pkill", "-f", "grok.py"], capture_output=True)
        subprocess.run(["pkill", "-f", "paper_trader.py"], capture_output=True)
        subprocess.run(["pkill", "-f", "live_trader.py"], capture_output=True)
        subprocess.run(["pkill", "-f", "sup_res"], capture_output=True)
        
        # Create kill switch file
        Path("kill_switch.flag").touch()
        
        return "✅ Backend processes terminated"
    except Exception as e:
        return f"❌ Error killing backend: {str(e)}"

# Header
st.markdown("""
    <div class="destruct-box">
        <div class="destruct-title">💀 SELF DESTRUCT</div>
        <div class="destruct-warning">⚠️ This will flatten all positions and stop the trading bot</div>
    </div>
""", unsafe_allow_html=True)

# Secondary password check
if 'destruct_authorized' not in st.session_state:
    st.session_state.destruct_authorized = False

if not st.session_state.destruct_authorized:
    st.warning("🔐 Additional authorization required")
    
    destruct_pass = st.text_input(
        "Enter destruct code",
        type="password",
        placeholder="Enter code...",
        label_visibility="collapsed"
    )
    
    if st.button("Authorize", type="secondary", use_container_width=True):
        if destruct_pass == "mi bombaclat":
            st.session_state.destruct_authorized = True
            st.rerun()
        else:
            st.error("Invalid authorization code")
else:
    # Show current positions
    positions = load_live_positions()
    
    st.subheader("📊 Current Live Positions")
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
    else:
        st.info("No open positions")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Flatten button
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔴 FLATTEN ALL POSITIONS", type="primary", use_container_width=True):
            with st.spinner("Flattening positions..."):
                result = flatten_all_positions()
            st.success(result)
            st.rerun()
    
    with col2:
        if st.button("⛔ KILL BACKEND", type="secondary", use_container_width=True):
            with st.spinner("Stopping backend..."):
                result = kill_backend()
            st.warning(result)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Nuclear option
    st.divider()
    st.subheader("☢️ Nuclear Option")
    st.caption("Flatten all positions AND kill backend")
    
    if st.button("💥 EXECUTE FULL SELF DESTRUCT", type="primary", use_container_width=True):
        with st.spinner("Executing self destruct..."):
            flatten_result = flatten_all_positions()
            kill_result = kill_backend()
        
        st.error("🔥 SELF DESTRUCT EXECUTED")
        st.code(f"{flatten_result}\n\n{kill_result}")

# Sidebar nav
with st.sidebar:
    st.markdown("### 📍 Navigation")
    if st.button("📈 Live Trading", use_container_width=True):
        st.switch_page("pages/2_📈_Live_Trading.py")
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.destruct_authorized = False
        st.switch_page("app.py")
