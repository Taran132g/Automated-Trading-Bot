import streamlit as st
import auth_manager
import os

st.set_page_config(
    page_title="Trading Dashboard",
    layout="centered",
    page_icon="🔒",
    initial_sidebar_state="collapsed"
)

# Hide sidebar for login page
st.markdown("""
    <style>
        [data-testid="stSidebar"] { display: none; }
        [data-testid="stSidebarNav"] { display: none; }
        .block-container { 
            padding-top: 5rem;
            max-width: 400px;
        }
        .login-box {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border-radius: 16px;
            padding: 2.5rem;
            border: 1px solid #334155;
            text-align: center;
        }
        .login-title {
            font-size: 2rem;
            font-weight: 700;
            color: white;
            margin-bottom: 0.5rem;
        }
        .login-subtitle {
            font-size: 0.9rem;
            color: #64748b;
            margin-bottom: 2rem;
        }
        .stTextInput > div > div > input {
            text-align: center;
            font-size: 1.2rem;
            letter-spacing: 0.1em;
        }
    </style>
""", unsafe_allow_html=True)

# Public Landing Logic
# If authenticated, go to Admin (optional, but good UX)
if auth_manager.check_auth():
    st.switch_page("pages/4_⚙️_Admin_Controls.py")

# If NOT authenticated, check if we should show login UI
# We use session_state 'login_requested' to force showing the login UI
# If NOT authenticated, check if we should show login UI
# We use session_state 'login_requested' to force showing the login UI
if not st.session_state.get("login_requested", False):
    st.switch_page("pages/2_📈_Live_Trading.py")

# --- The Login UI below is now only reachable if a page explicitly redirects here ---
# (e.g. if Admin Controls calls st.switch_page("app.py"))


# If no secret is set, show setup instructions
if not os.getenv("TOTP_SECRET"):
    st.warning("⚠️ TOTP Secret not found in .env")
    st.info("Run `python generate_totp.py` to generate one.")
    st.stop()

# Login UI
st.markdown("""
    <div class="login-box">
        <div class="login-title">🔒 Trading Dashboard</div>
        <div class="login-subtitle">Enter 6-digit Authenticator Code</div>
    </div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

code = st.text_input(
    "Authenticator Code",
    type="password",  # Hide input for privacy
    placeholder="000000",
    label_visibility="collapsed",
    max_chars=6
)

if st.button("Verify", type="primary", use_container_width=True):
    if auth_manager.login(code):
        st.success("Login successful!")
        st.session_state.login_requested = False  # Clear the flag
        time.sleep(0.5)
        st.switch_page("pages/4_⚙️_Admin_Controls.py")
    else:
        st.error("Invalid code")

import time

