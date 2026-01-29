import os
import time
import pyotp
import streamlit as st
import extra_streamlit_components as stx
from dotenv import load_dotenv

load_dotenv()

COOKIE_NAME = "trading_dashboard_auth"
COOKIE_EXPIRY_DAYS = 30

def _get_cookie_manager():
    # Singleton pattern for cookie manager to avoid re-initialization issues
    if 'cookie_manager' not in st.session_state:
        st.session_state.cookie_manager = stx.CookieManager()
    return st.session_state.cookie_manager

def check_auth() -> bool:
    """
    Check if user is authenticated via session state or valid cookie.
    Returns True if authenticated, False otherwise.
    """
    # 1. Check Session State (fastest)
    if st.session_state.get('authenticated', False):
        return True

    # 2. Check Cookie (persistent)
    cookie_manager = _get_cookie_manager()
    # Wait a moment for cookies to load on first run
    time.sleep(0.1) 
    auth_cookie = cookie_manager.get(COOKIE_NAME)
    
    totp_secret = os.getenv("TOTP_SECRET")
    if not totp_secret:
        # If no secret configured, fail open or closed? 
        # For security, let's fail closed but log it.
        # Actually, for first run setup, maybe we should allow?
        # Let's assume if no secret, auth is disabled (or handled by app.py logic)
        return False

    if auth_cookie == "valid":
        st.session_state.authenticated = True
        return True

    return False

def login(code: str) -> bool:
    """
    Verify TOTP code and set session/cookie if valid.
    """
    totp_secret = os.getenv("TOTP_SECRET")
    if not totp_secret:
        return False

    totp = pyotp.TOTP(totp_secret)
    if totp.verify(code):
        st.session_state.authenticated = True
        
        # Set persistent cookie
        cookie_manager = _get_cookie_manager()
        cookie_manager.set(
            COOKIE_NAME, 
            "valid", 
            expires_at=datetime.now() + timedelta(days=COOKIE_EXPIRY_DAYS)
        )
        return True
    
    return False

def logout():
    """
    Clear session and delete cookie.
    """
    st.session_state.authenticated = False
    cookie_manager = _get_cookie_manager()
    cookie_manager.delete(COOKIE_NAME)

def require_auth():
    """
    Enforce authentication on pages. Redirects to app.py if not logged in.
    """
    if not check_auth():
        st.session_state.login_requested = True
        st.switch_page("app.py")
        st.stop()

# Need datetime for cookie expiry
from datetime import datetime, timedelta
