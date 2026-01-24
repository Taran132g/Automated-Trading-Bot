import streamlit as st

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

# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

# Check if already authenticated
if st.session_state.authenticated:
    st.switch_page("pages/2_📈_Live_Trading.py")

# Login UI
st.markdown("""
    <div class="login-box">
        <div class="login-title">🔒 Trading Dashboard</div>
        <div class="login-subtitle">Enter passcode to continue</div>
    </div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

passcode = st.text_input(
    "Passcode",
    type="password",
    placeholder="Enter passcode...",
    label_visibility="collapsed"
)

if st.button("Enter", type="primary", use_container_width=True):
    if passcode == "bombaclat":
        st.session_state.authenticated = True
        st.switch_page("pages/2_📈_Live_Trading.py")
    else:
        st.error("Incorrect passcode")

# Also allow enter key to submit
if passcode == "bombaclat":
    st.session_state.authenticated = True
    st.switch_page("pages/2_📈_Live_Trading.py")
