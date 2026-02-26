import streamlit as st
import auth_manager
import os

st.set_page_config(
    page_title="Terminal Login",
    layout="centered",
    page_icon="⚡",
    initial_sidebar_state="collapsed"
)

# Hide sidebar for login page and apply V2 institutional styling
st.markdown("""
    <style>
        [data-testid="stSidebar"] { display: none; }
        [data-testid="stSidebarNav"] { display: none; }
        .stApp {
            background-color: #0B0E14; 
            color: #E2E8F0;
            font-family: 'Inter', sans-serif;
        }
        .block-container { 
            padding-top: 5rem;
            max-width: 400px;
        }
        .login-box {
            background: linear-gradient(180deg, #111827 0%, #0B0E14 100%);
            border-radius: 8px;
            padding: 2.5rem;
            border: 1px solid #1F2937;
            text-align: center;
        }
        .login-title {
            font-size: 2rem;
            font-weight: 700;
            color: #F8FAFC;
            margin-bottom: 0.5rem;
            letter-spacing: -0.5px;
        }
        .login-subtitle {
            font-size: 0.9rem;
            color: #94A3B8;
            margin-bottom: 2rem;
            font-family: 'Roboto Mono', monospace;
        }
        .stTextInput > div > div > input {
            text-align: center;
            font-size: 1.5rem;
            letter-spacing: 0.2em;
            font-family: 'Roboto Mono', monospace;
            background-color: #0B0E14;
            color: #00FF99;
            border: 1px solid #1F2937;
        }
        .stTextInput > div > div > input:focus {
            border-color: #00FF99;
            box-shadow: 0 0 0 1px #00FF99;
        }
        .stButton>button {
            background-color: #00FF99;
            color: #0B0E14;
            font-weight: 600;
            border-radius: 4px;
        }
        .stButton>button:hover {
            background-color: #00cc7a;
        }
    </style>
""", unsafe_allow_html=True)

# Default routing
# If the user explicitly requested login (e.g. from Admin page), show login screen
if not st.session_state.get("login_requested", False):
    st.switch_page("pages/1_📈_Terminal.py")

# --- The Login UI below is now only reachable if login_requested is True ---

# If no secret is set, show setup instructions
if not os.getenv("TOTP_SECRET"):
    st.warning("⚠️ TOTP Secret not found in .env")
    st.info("Run `python generate_totp.py` to generate one.")
    st.stop()

# Login UI
st.markdown("""
    <div class="login-box">
        <div class="login-title">⚡ QUANT_OS</div>
        <div class="login-subtitle">AWAITING TOTP AUTHORIZATION</div>
    </div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

code = st.text_input(
    "Authenticator Code",
    type="password",
    placeholder="000000",
    label_visibility="collapsed",
    max_chars=6
)

if st.button("VERIFY SESSION", use_container_width=True):
    if auth_manager.login(code):
        st.session_state.login_requested = False
        st.success("Authorization granted.")
        time.sleep(0.5)
        st.switch_page("pages/3_⚙️_Admin_Controls.py")
    else:
        st.error("Invalid TOTP signature.")

