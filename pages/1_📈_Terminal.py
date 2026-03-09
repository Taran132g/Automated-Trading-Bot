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
import plotly.graph_objects as go
from dotenv import load_dotenv
import sys
import pytz

# Load environment variables
load_dotenv()
sys.path.append(str(Path(__file__).parent.parent))

import config_manager
import auth_manager
import ui_components

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
        
        #MainMenu, footer { visibility: hidden; }
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
    data['daily_pnl_persistent'] = state.get('daily_pnl', 0.0)
    data['start_day_liquidation'] = state.get('start_day_liquidation', 0.0)
    
    with closing(get_db_connection()) as conn:
        try:
            # Optimize: Only load today's trades for individual list view to save memory
            data['trades'] = pd.read_sql_query(f"SELECT * FROM live_trades WHERE timestamp >= {today_start} ORDER BY timestamp DESC", conn)
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
            wins = pd.read_sql_query(f"SELECT COUNT(*) as count FROM live_trades WHERE pnl > 0 AND side IN ('SELL', 'COVER') AND timestamp >= {today_start}", conn).iloc[0]['count']
            total = pd.read_sql_query(f"SELECT COUNT(*) as count FROM live_trades WHERE side IN ('SELL', 'COVER') AND timestamp >= {today_start}", conn).iloc[0]['count']
            data['win_rate'] = (wins / total * 100) if total > 0 else 0.0
        except: pass
        
        try:
            data['alerts'] = pd.read_sql_query("SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 1000", conn)
            if not data['alerts'].empty:
                data['alerts']['datetime'] = pd.to_datetime(data['alerts']['timestamp'], unit='s', utc=True).dt.tz_convert('US/Eastern')
                
                # --- Filter Alerts by Live Symbols ---
                config = config_manager.load_config()
                raw_live = config.get("live_symbols", "")
                if raw_live:
                    live_list = [s.strip().upper() for s in raw_live.split(",") if s.strip()]
                    data['alerts'] = data['alerts'][data['alerts']['symbol'].isin(live_list)].copy()
        except: pass
        
        try:
            # Optimize: Load detailed data for today, and heavily downsample historical data to prevent OOM
            hist_query = f"""
                SELECT * FROM account_history WHERE timestamp >= {today_start}
                UNION ALL
                SELECT * FROM (
                    SELECT * FROM account_history 
                    WHERE timestamp < {today_start} AND rowid % 50 = 0
                )
                ORDER BY timestamp ASC
            """
            data['account_history'] = pd.read_sql_query(hist_query, conn)
            if not data['account_history'].empty:
                data['account_history']['timestamp'] = pd.to_numeric(data['account_history']['timestamp'], errors='coerce')
                # FIX: Explicitly cast liquidation_value to numeric as it is loaded from string in SQLite
                data['account_history']['liquidation_value'] = pd.to_numeric(data['account_history']['liquidation_value'], errors='coerce')
                data['account_history'] = data['account_history'].dropna(subset=['timestamp', 'liquidation_value'])
                data['account_history']['datetime'] = pd.to_datetime(data['account_history']['timestamp'], unit='s', utc=True).dt.tz_convert('US/Eastern')
        except: pass
    
    # Calculate Rolling PI per share (Daily PnL / Total Volume today)
    data['rolling_pi_per_share'] = 0.0
    if not data['trades'].empty:
        try:
            today_trades = data['trades'][data['trades']['timestamp'] >= today_start]
            total_shares = abs(today_trades['qty']).sum()
            if total_shares > 0:
                data['rolling_pi_per_share'] = data['daily_pnl'] / total_shares
        except: pass

    # Calculate Max Drawdown from Account History
    data['max_drawdown'] = 0.0
    if not data['account_history'].empty:
        df_hist = data['account_history'].copy()
        df_hist['liquidation_value'] = pd.to_numeric(df_hist['liquidation_value'], errors='coerce')
        df_hist['peak'] = df_hist['liquidation_value'].cummax()
        df_hist['drawdown'] = (df_hist['peak'] - df_hist['liquidation_value']) / df_hist['peak'] * 100
        data['max_drawdown'] = round(df_hist['drawdown'].max(), 2) if not df_hist['drawdown'].empty else 0.0
        
    return data

data = load_live_data()

# --- SIDEBAR: Navigation & System Status ---
with st.sidebar:
    
    
    config = config_manager.load_config()
    raw_symbols = config.get("live_symbols", "")
    if not raw_symbols:
        raw_symbols = os.getenv('LIVE_SYMBOLS', '')
        
    live_symbols = raw_symbols.split(',')
    live_symbols = [s.strip().upper() for s in live_symbols if s.strip()]
    
    if live_symbols:
        st.markdown('<div class="section-header">Live Symbols</div>', unsafe_allow_html=True)
        st.markdown(" • ".join([f"**{s}**" for s in live_symbols]))
        st.markdown("<br>", unsafe_allow_html=True)
        
    ui_components.render_system_status()

# --- MAIN DASHBOARD AREA ---
top_col1, top_col2 = st.columns([3, 1])

with top_col1:
    now_est = datetime.now(pytz.timezone('US/Eastern'))
    is_market_open = (
        now_est.weekday() < 5 and 
        ((now_est.hour == 9 and now_est.minute >= 30) or (9 < now_est.hour < 16))
    )
    
    if is_market_open:
        indicator_html = '<div class="live-indicator"><div class="pulse-dot"></div>MARKET LIVE</div>'
    else:
        indicator_html = '<div class="live-indicator" style="color: #64748B; border-color: #334155; background: rgba(0,0,0,0);"><div style="height:6px;width:6px;background-color:#64748B;border-radius:50%;margin-right:6px;"></div>MARKET CLOSED</div>'

    st.markdown(f"""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2 style="margin:0;">EXECUTION TERMINAL</h2>
            {indicator_html}
        </div>
    """, unsafe_allow_html=True)

    # --- Active Cooldown Banners ---
    now = time.time()
    state = load_live_state()
    loss_cooldown = state.get("loss_cooldown_until", 0.0)
    pi_cooldown = state.get("pi_cooldown_until", 0.0)
    
    if now < loss_cooldown:
        remaining = int(loss_cooldown - now)
        st.error(f"⚠️ **LOSS COOLDOWN ACTIVE**: Trading paused for {remaining}s due to consecutive losses.", icon="🚨")
    elif now < pi_cooldown:
        remaining = int(pi_cooldown - now)
        st.warning(f"🕒 **PI COOLDOWN ACTIVE**: Skipping entries for {remaining}s due to low fill quality.", icon="⏳")
    
with top_col2:
    st.markdown(f"<div style='text-align: right; color: #64748B; font-family: monospace;'>SYS_TIME: {datetime.now(pytz.timezone('US/Eastern')).strftime('%H:%M:%S.%f')[:-3]}</div>", unsafe_allow_html=True)

# RISK DASHBOARD (KPIs)
metric_cols = st.columns(5)
metrics = [
    {
        "label": "DAILY PNL (SCHWAB)", 
        "value": f"${data.get('daily_pnl_persistent') if data.get('daily_pnl_persistent') is not None else data.get('daily_pnl', 0.0):,.2f}", 
        "delta": "REALIZED + UNREALIZED", 
        "color": "#00FF99" if (data.get('daily_pnl_persistent') if data.get('daily_pnl_persistent') is not None else data.get('daily_pnl', 0.0)) >= 0 else "#EF4444"
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
    st.markdown('<div class="section-header">ACCOUNT VALUE TRAJECTORY (VERIFIED)</div>', unsafe_allow_html=True)
    
    time_range = st.radio("Time Range", ["Today", "All Time"], horizontal=True, label_visibility="collapsed")
    
    if not data['account_history'].empty:
        df_chart = data['account_history'].copy().sort_values('timestamp')
        df_trades = data['trades'].head(50).copy() if not data['trades'].empty else pd.DataFrame()
        
        if time_range == "Today":
            today_start = datetime.now().replace(hour=0, minute=0, second=0).timestamp()
            df_chart = df_chart[df_chart['timestamp'] >= today_start].copy()
            if not df_trades.empty:
                df_trades = df_trades[df_trades['timestamp'] >= today_start].copy()
    else:
        df_chart = pd.DataFrame(columns=['datetime', 'liquidation_value'])
        df_trades = pd.DataFrame(columns=['datetime', 'pnl'])

    # We will use an advanced area chart for the account trajectory
    fig = go.Figure()
    
    # Use actual datetimes, we will hide weekends and overnights natively with Plotly layout
    if time_range == "All Time" and not df_chart.empty:
        df_chart = df_chart.reset_index(drop=True)
        x_values = df_chart['datetime']
    else:
        x_values = df_chart['datetime'] if not df_chart.empty else []

    # Add gradient fill area chart
    fig.add_trace(go.Scatter(
        x=x_values,
        y=df_chart['liquidation_value'],
        fill='tozeroy',
        fillcolor='rgba(0, 255, 153, 0.1)',
        mode='lines',
        line=dict(color='#00FF99', width=2),
        name='Account Value',
        customdata=df_chart['datetime'].dt.strftime('%Y-%m-%d %I:%M:%S %p') if not df_chart.empty else [],
        hovertemplate='%{customdata}<br><b>$%{y:,.2f}</b><extra></extra>'
    ))
    
    # Modern Institutional Chart Layout
    # Dynamically scale Y-Axis to fit the graph
    y_min, y_max = 0, 100000
    if not df_chart.empty:
        min_val = df_chart['liquidation_value'].min()
        max_val = df_chart['liquidation_value'].max()
        pad = (max_val - min_val) * 0.1
        if pad == 0: pad = max_val * 0.005 # Fallback if flat
        y_min = min_val - pad
        y_max = max_val + pad

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
            tickformat='%H:%M' if time_range == "Today" else '%b %d',
            rangebreaks=[
                dict(bounds=["sat", "mon"]),  # hide weekends
                dict(bounds=[16.5, 9.5], pattern="hour"),  # hide 4:30 PM to 9:30 AM
            ] if time_range == "All Time" else None,
            color='#94A3B8'
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='#1F2937',
            gridwidth=1,
            tickprefix='$',
            color='#94A3B8',
            title_font=dict(color='#94A3B8'),
            range=[y_min, y_max]
        )
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    
with tape_col:
    st.markdown('<div class="section-header">LIVE EXECUTION TAPE</div>', unsafe_allow_html=True)
    
    # Render custom HTML/CSS Execution Tape
    tape_html = "<div style='height: 450px; overflow-y: auto; background: #111827; border: 1px solid #1F2937; border-radius: 8px;'>"
    
    if not data['alerts'].empty:
        alerts_df = data['alerts'].head(20)
    else:
        alerts_df = pd.DataFrame(columns=['datetime', 'symbol', 'price', 'direction'])
        
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
