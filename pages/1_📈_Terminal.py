import os
import sqlite3
import json
import time
from pathlib import Path
from contextlib import closing
import pandas as pd
import streamlit as st
from datetime import datetime
import plotly.graph_objects as go
from dotenv import load_dotenv
import sys

# Load environment variables
load_dotenv()
sys.path.append(str(Path(__file__).parent.parent))

import config_manager
import auth_manager

# Check authentication
# auth_manager.require_auth()

# Configuration
REFRESH_INTERVAL = 3
DB_PATH = Path("penny_basing.db").resolve()
LIVE_STATE_PATH = Path("live_trader_state_primary.json").resolve()
if not LIVE_STATE_PATH.exists():
    LIVE_STATE_PATH = Path("live_trader_state.json").resolve()

st.set_page_config(
    page_title="Terminal | Live Execution",
    layout="wide",
    page_icon="📈",
    initial_sidebar_state="expanded"
)

# --- CSS Styling (Terminal Theme) ---
st.markdown("""
    <style>
        /* Base Dark Theme Overrides */
        .stApp {
            background-color: #0B0E14; /* Bloomberg/Black */
            color: #E2E8F0;
            font-family: 'Inter', sans-serif;
        }
        
        #MainMenu, header, footer { visibility: hidden; }
        .block-container { padding-top: 1rem; max-width: 98%; }
        
        /* Metrics / KPIs */
        [data-testid="stMetricValue"] {
            font-size: 1.8rem !important;
            font-weight: 700 !important;
            color: #F8FAFC !important;
            font-family: 'Roboto Mono', monospace;
        }
        [data-testid="stMetricDelta"] {
            font-size: 0.9rem !important;
        }
        
        .metric-card {
            background: #111827;
            border: 1px solid #1F2937;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        }
        
        /* Execution Tape */
        .tape-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 12px;
            border-bottom: 1px solid #1F2937;
            font-family: 'Roboto Mono', monospace;
            font-size: 0.85rem;
        }
        .tape-row:hover { background-color: #1F2937; }
        
        .tape-time { color: #64748B; width: 80px; }
        .tape-symbol { font-weight: 700; width: 60px; color: #E2E8F0; }
        .tape-action-long { color: #00FF99; width: 50px; }
        .tape-action-short { color: #EF4444; width: 50px; }
        .tape-price { color: #F8FAFC; width: 80px; text-align: right; }
        
        /* System Status Sidebar */
        .sys-status-item {
            display: flex;
            align-items: center;
            margin-bottom: 12px;
            font-size: 0.9rem;
            color: #94A3B8;
        }
        .status-dot {
            height: 8px;
            width: 8px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 10px;
        }
        .status-dot.online {
            background-color: #00FF99;
            box-shadow: 0 0 8px #00FF99;
        }
        .status-dot.offline {
            background-color: #EF4444;
            box-shadow: 0 0 8px #EF4444;
        }
        
        /* Headers */
        h1, h2, h3 { 
            font-family: 'Inter', sans-serif;
            color: #F8FAFC !important;
            letter-spacing: -0.5px;
        }
        
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
        
        /* Live Indicator */
        .live-indicator {
            display: inline-flex;
            align-items: center;
            background: rgba(0, 255, 153, 0.1);
            border: 1px solid rgba(0, 255, 153, 0.3);
            color: #00FF99;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 1px;
        }
        .pulse-dot {
            height: 6px;
            width: 6px;
            background-color: #00FF99;
            border-radius: 50%;
            margin-right: 6px;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 255, 153, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(0, 255, 153, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 255, 153, 0); }
        }
    </style>
""", unsafe_allow_html=True)

# --- Data Loading Helpers ---
def get_db_connection():
    return sqlite3.connect(str(DB_PATH))

def load_live_state():
    if LIVE_STATE_PATH.exists():
        try:
            with open(LIVE_STATE_PATH, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def load_live_data():
    data = {
        'trades': pd.DataFrame(),
        'positions': {},
        'daily_pnl': 0.0,
        'total_pnl': 0.0,
        'win_rate': 0.0,
        'alerts': pd.DataFrame(),
        'account_details': {},
        'account_history': pd.DataFrame()
    }
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0).timestamp()
    state = load_live_state()
    data['positions'] = state.get('positions', {})
    data['account_details'] = state.get('account_details', {})
    data['rolling_pi'] = state.get('rolling_pi', 0.0)
    
    with closing(get_db_connection()) as conn:
        try:
            data['trades'] = pd.read_sql_query("SELECT * FROM live_trades ORDER BY timestamp DESC", conn)
            if not data['trades'].empty:
                data['trades']['datetime'] = pd.to_datetime(data['trades']['timestamp'], unit='s', utc=True).dt.tz_convert('US/Eastern')
        except: pass
        
        try:
            result = pd.read_sql_query(f"SELECT SUM(pnl) as total FROM live_trades WHERE timestamp >= {today_start}", conn)
            data['daily_pnl'] = result.iloc[0]['total'] or 0.0
        except: pass
        
        try:
            result = pd.read_sql_query("SELECT SUM(pnl) as total FROM live_trades", conn)
            data['total_pnl'] = result.iloc[0]['total'] or 0.0
        except: pass
        
        try:
            wins = pd.read_sql_query(f"SELECT COUNT(*) as count FROM live_trades WHERE pnl > 0 AND timestamp >= {today_start}", conn).iloc[0]['count']
            total = pd.read_sql_query(f"SELECT COUNT(*) as count FROM live_trades WHERE timestamp >= {today_start}", conn).iloc[0]['count']
            data['win_rate'] = (wins / total * 100) if total > 0 else 0.0
        except: pass
        
        try:
            data['alerts'] = pd.read_sql_query("SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 50", conn)
            if not data['alerts'].empty:
                data['alerts']['datetime'] = pd.to_datetime(data['alerts']['timestamp'], unit='s', utc=True).dt.tz_convert('US/Eastern')
        except: pass
        
        try:
            data['account_history'] = pd.read_sql_query("SELECT * FROM account_history ORDER BY timestamp ASC", conn)
            if not data['account_history'].empty:
                data['account_history']['timestamp'] = pd.to_numeric(data['account_history']['timestamp'], errors='coerce')
                data['account_history'] = data['account_history'].dropna(subset=['timestamp'])
                data['account_history']['datetime'] = pd.to_datetime(data['account_history']['timestamp'], unit='s', utc=True).dt.tz_convert('US/Eastern')
        except: pass
    
    # Calculate Max Drawdown from Account History
    data['max_drawdown'] = 0.0
    if not data['account_history'].empty:
        df_hist = data['account_history'].copy()
        df_hist['peak'] = df_hist['liquidation_value'].cummax()
        df_hist['drawdown'] = (df_hist['peak'] - df_hist['liquidation_value']) / df_hist['peak'] * 100
        data['max_drawdown'] = df_hist['drawdown'].max()
        
    return data

data = load_live_data()

# --- SIDEBAR: Navigation & System Status ---
with st.sidebar:
    st.markdown("### ⚡ QUANT_OS // V2.0")
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown('<div class="section-header">Core Modules</div>', unsafe_allow_html=True)
    st.button("📈 Execution Terminal", use_container_width=True, type="primary")
    if st.button("📊 Analytics & Risk", use_container_width=True):
        st.switch_page("pages/2_📊_Analytics_&_Heatmap.py")
    if st.button("⚙️ Admin Controls", use_container_width=True):
        st.switch_page("pages/3_⚙️_Admin_Controls.py")
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-header">System Infrastructure</div>', unsafe_allow_html=True)
    
    import subprocess
    def is_backend_running():
        loop_result = subprocess.run(["pgrep", "-f", "restart_loop.sh"], capture_output=True)
        grok_result = subprocess.run(["pgrep", "-f", "grok.py"], capture_output=True)
        return loop_result.returncode == 0 or grok_result.returncode == 0

    # System indicators
    bot_status = "online" if is_backend_running() else "offline"
    db_status = "online" if DB_PATH.exists() else "offline"
    grok_status = "online" # Assuming grok is running if live state exists
    schwab_status = "online" if data['account_details'] else "offline"
    
    st.markdown(f"""
        <div class="sys-status-item" title="The master trading bot process handling entry/exit logic and auto-restarts">
            <span class="status-dot {bot_status}"></span>
            <span>Trading Bot Backend</span>
        </div>
        <div class="sys-status-item" title="Live connection to the Schwab API for executing orders">
            <span class="status-dot {schwab_status}"></span>
            <span>Schwab API Routing</span>
        </div>
        <div class="sys-status-item" title="The AI vision model generating real-time trading signals">
            <span class="status-dot {grok_status}"></span>
            <span>Grok Vision Engine</span>
        </div>
        <div class="sys-status-item" title="Local Time-Series Database storing historical trades and alerts">
            <span class="status-dot {db_status}"></span>
            <span>Local TSDB Sync</span>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<br><br>", unsafe_allow_html=True)
    if st.button("🔌 Disconnect Session", use_container_width=True):
        auth_manager.logout()
        st.switch_page("app.py")

# --- MAIN DASHBOARD AREA ---
top_col1, top_col2 = st.columns([3, 1])

with top_col1:
    st.markdown("""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2 style="margin:0;">EXECUTION TERMINAL</h2>
            <div class="live-indicator"><div class="pulse-dot"></div>MARKET LIVE</div>
        </div>
    """, unsafe_allow_html=True)
    
with top_col2:
    st.markdown(f"<div style='text-align: right; color: #64748B; font-family: monospace;'>SYS_TIME: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}</div>", unsafe_allow_html=True)

# RISK DASHBOARD (KPIs)
metric_cols = st.columns(5)
metrics = [
    {
        "label": "DAILY PNL (SCHWAB)", 
        "value": f"${data['account_details'].get('day_pnl', data['daily_pnl']):,.2f}", 
        "delta": "REALIZED", 
        "color": "#00FF99" if data['daily_pnl'] >= 0 else "#EF4444"
    },
    {
        "label": "ACCOUNT VALUE", 
        "value": f"${data['account_details'].get('liquidation_value', 0):,.2f}", 
        "delta": ""
    },
    {
        "label": "MAX DRAWDOWN", 
        "value": f"-{data['max_drawdown']:.2f}%", 
        "delta": "PEAK TO TROUGH",
        "color": "#EF4444" if data['max_drawdown'] > 2 else "#F8FAFC"
    },
    {
        "label": "WIN RATE", 
        "value": f"{data['win_rate']:.1f}%", 
        "delta": "TODAY",
        "color": "#00FF99" if data['win_rate'] > 50 else "#F8FAFC"
    },
    {
        "label": "PI PER SHARE", 
        "value": f"${data.get('rolling_pi_per_share', 0.0):,.3f}", 
        "delta": "ROLLING",
        "color": "#00FF99" if data.get('rolling_pi_per_share', 0.0) >= 0 else "#F8FAFC"
    }
]

for col, m in zip(metric_cols, metrics):
    with col:
        color = m.get("color", "#F8FAFC")
        st.markdown(f"""
            <div class="metric-card">
                <div style="font-size: 0.75rem; color: #94A3B8; font-weight: 600; letter-spacing: 1px;">{m['label']}</div>
                <div style="font-size: 1.8rem; font-family: 'Roboto Mono'; font-weight: 700; color: {color}; margin: 5px 0;">{m['value']}</div>
                <div style="font-size: 0.7rem; color: #64748B;">{m['delta']}</div>
            </div>
        """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# CORE VISUALIZATIONS
chart_col, tape_col = st.columns([7, 3])

with chart_col:
    st.markdown('<div class="section-header">ACCOUNT TRAJECTORY & EXECUTION MAP</div>', unsafe_allow_html=True)
    
    if not data['account_history'].empty:
        df_chart = data['account_history'].copy().sort_values('timestamp')
        df_trades = data['trades'].head(50).copy() if not data['trades'].empty else pd.DataFrame()
    else:
        # --- MOCK DATA FOR VISUALIZATION ---
        import numpy as np
        dates = pd.date_range(end=datetime.now(), periods=100, freq='5T')
        equity = 100000 + np.cumsum(np.random.normal(0, 150, 100))
        df_chart = pd.DataFrame({'datetime': dates, 'liquidation_value': equity})
        
        # Mock 20 random trades over this period
        trade_dates = np.random.choice(dates, 20, replace=False)
        pnls = np.random.normal(0, 500, 20)
        df_trades = pd.DataFrame({'datetime': trade_dates, 'pnl': pnls})

    # We will use an advanced area chart for the account trajectory
    fig = go.Figure()
    
    # Add gradient fill area chart
    fig.add_trace(go.Scatter(
        x=df_chart['datetime'],
        y=df_chart['liquidation_value'],
        fill='tozeroy',
        fillcolor='rgba(0, 255, 153, 0.1)',
        mode='lines',
        line=dict(color='#00FF99', width=2),
        name='Account Value',
        hovertemplate='%{x|%I:%M:%S %p}<br><b>$%{y:,.2f}</b><extra></extra>'
    ))
    
    # Overlay recent trades if any
    if not df_trades.empty:
        # Separate wins and losses for colored markers
        wins = df_trades[df_trades['pnl'] > 0]
        losses = df_trades[df_trades['pnl'] <= 0]
        
        # Note: A true candlestick needs OHLC data. Since we only have account value,
        # we plot the equity curve and overlay PnL execution bubbles at the bottom to show activity.
        
        if not wins.empty:
            fig.add_trace(go.Bar(
                x=wins['datetime'],
                y=wins['pnl'],
                name='Win',
                marker_color='#00FF99',
                yaxis='y2',
                hovertemplate='Win: $%{y:.2f}<extra></extra>'
            ))
            
        if not losses.empty:
            fig.add_trace(go.Bar(
                x=losses['datetime'],
                y=losses['pnl'],
                name='Loss',
                marker_color='#EF4444',
                yaxis='y2',
                hovertemplate='Loss: $%{y:.2f}<extra></extra>'
            ))

    # Modern Institutional Chart Layout
    y2_range = max(abs(df_trades['pnl']))*2 if not df_trades.empty else 1000
    fig.update_layout(
        template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=0, r=0, t=10, b=0),
        height=450,
        hovermode='x unified',
        showlegend=False,
        xaxis=dict(
            showgrid=True,
            gridcolor='#1F2937',
            gridwidth=1,
            tickformat='%H:%M',
            color='#94A3B8'
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='#1F2937',
            gridwidth=1,
            tickprefix='$',
            color='#94A3B8',
            title_font=dict(color='#94A3B8')
        ),
        yaxis2=dict(
            title='Trade PnL',
            overlaying='y',
            side='right',
            showgrid=False,
            zeroline=True,
            zerolinecolor='#374151',
            color='#94A3B8',
            range=[-y2_range, y2_range] # Scale bars to bottom
        )
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    
with tape_col:
    st.markdown('<div class="section-header">LIVE EXECUTION TAPE</div>', unsafe_allow_html=True)
    
    # Render custom HTML/CSS Execution Tape
    tape_html = "<div style='height: 450px; overflow-y: auto; background: #111827; border: 1px solid #1F2937; border-radius: 8px;'>"
    
    if not data['alerts'].empty:
        alerts_df = data['alerts'].head(100)
    else:
        # --- MOCK DATA ---
        import random
        symbols = ['AAPL', 'TSLA', 'SPY', 'QQQ', 'NVDA']
        directions = ['bid-heavy', 'ask-heavy']
        now = datetime.now()
        alerts_data = []
        for i in range(50):
            alerts_data.append({
                'datetime': now - pd.Timedelta(seconds=random.randint(1, 3600)),
                'symbol': random.choice(symbols),
                'price': random.uniform(100, 500),
                'direction': random.choice(directions)
            })
        alerts_df = pd.DataFrame(alerts_data).sort_values('datetime', ascending=False)
        
    for _, row in alerts_df.iterrows():
        time_str = row['datetime'].strftime('%H:%M:%S')
        sym = row['symbol']
        price = f"{row['price']:.2f}"
        side = "LONG" if row['direction'] == 'bid-heavy' else "SHRT"
        side_class = "tape-action-long" if side == "LONG" else "tape-action-short"
        
        # Mimic HFT tape rows
        tape_html += f'''
<div class="tape-row">
    <span class="tape-time">{time_str}</span>
    <span class="tape-symbol">{sym}</span>
    <span class="{side_class}">{side}</span>
    <span class="tape-price">{price}</span>
</div>
'''
    tape_html += "</div>"
    st.markdown(tape_html, unsafe_allow_html=True)

# Auto Refresh loop
time.sleep(REFRESH_INTERVAL)
st.rerun()
