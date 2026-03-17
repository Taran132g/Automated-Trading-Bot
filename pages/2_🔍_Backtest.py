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
import ui_components

# Configuration
REFRESH_INTERVAL = 3
DB_PATH = Path("penny_basing.db").resolve()
PAPER_STATE_PATH = Path("paper_trader_state.json").resolve()

st.set_page_config(
    page_title="Paper Trading | SIMULATION",
    layout="wide",
    page_icon="🔍",
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
        
        .paper-badge {
            background: linear-gradient(135deg, #60a5fa, #3b82f6);
            color: #fff;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.8rem;
            display: inline-block;
            margin-left: 10px;
        }
        
        .position-card {
            background: linear-gradient(135deg, #111827 0%, #0B0E14 100%);
            border-radius: 8px;
            padding: 1rem;
            border: 1px solid #1F2937;
            margin-bottom: 0.5rem;
        }
        .position-symbol { font-size: 1.3rem; font-weight: 700; color: #F8FAFC; }
        .position-qty { color: #94a3b8; font-family: 'Roboto Mono', monospace; }
        .position-long { border-left: 4px solid #00FF99; }
        .position-short { border-left: 4px solid #FF3366; }
        
        /* Alert Boxes */
        .alert-box {
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 8px;
            font-weight: 500;
            font-family: 'Roboto Mono', monospace;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .alert-long {
            background-color: rgba(0, 255, 153, 0.1);
            border: 1px solid rgba(0, 255, 153, 0.3);
            color: #00FF99;
        }
        .alert-short {
            background-color: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #EF4444;
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
    </style>
""", unsafe_allow_html=True)

# --- Data Loading Helpers ---
def get_db_connection():
    return sqlite3.connect(str(DB_PATH))

def load_paper_state():
    if PAPER_STATE_PATH.exists():
        try:
            with open(PAPER_STATE_PATH, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def load_paper_data():
    data = {
        'trades': pd.DataFrame(),
        'positions': pd.DataFrame(),
        'daily_pnl': 0.0,
        'total_pnl': 0.0,
        'win_rate': 0.0,
        'alerts': pd.DataFrame()
    }
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0).timestamp()
    
    with closing(get_db_connection()) as conn:
        try:
            data['trades'] = pd.read_sql_query("SELECT * FROM paper_trades ORDER BY timestamp DESC", conn)
            if not data['trades'].empty:
                cols = ['timestamp', 'pnl', 'price', 'qty']
                for col in cols:
                    if col in data['trades'].columns:
                        data['trades'][col] = pd.to_numeric(data['trades'][col], errors='coerce')
                data['trades'] = data['trades'].dropna(subset=['timestamp'])
                data['trades']['datetime'] = pd.to_datetime(data['trades']['timestamp'], unit='s', utc=True).dt.tz_convert('US/Eastern')
        except: pass
        
        try:
            data['positions'] = pd.read_sql_query("SELECT * FROM paper_positions", conn)
        except: pass
        
        try:
            result = pd.read_sql_query(f"SELECT SUM(pnl) as total FROM paper_trades WHERE timestamp >= {today_start}", conn)
            data['daily_pnl'] = result.iloc[0]['total'] or 0.0
        except: pass
        
        try:
            result = pd.read_sql_query("SELECT SUM(pnl) as total FROM paper_trades", conn)
            data['total_pnl'] = result.iloc[0]['total'] or 0.0
        except: pass
        
        try:
            wins = pd.read_sql_query(f"SELECT COUNT(*) as count FROM paper_trades WHERE pnl > 0 AND side IN ('SELL', 'COVER') AND timestamp >= {today_start}", conn).iloc[0]['count']
            total = pd.read_sql_query(f"SELECT COUNT(*) as count FROM paper_trades WHERE side IN ('SELL', 'COVER') AND timestamp >= {today_start}", conn).iloc[0]['count']
            data['win_rate'] = (wins / total * 100) if total > 0 else 0.0
        except: pass
        
        try:
            data['alerts'] = pd.read_sql_query("SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 30", conn)
            if not data['alerts'].empty:
                data['alerts']['datetime'] = pd.to_datetime(data['alerts']['timestamp'], unit='s', utc=True).dt.tz_convert('US/Eastern')
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

    # Calculate Max Drawdown from Paper Trades (Cumulative PnL curve)
    data['max_drawdown'] = 0.0
    if not data['trades'].empty:
        try:
            # Sort by timestamp to build the equity curve
            df_curve = data['trades'].sort_values('timestamp').copy()
            df_curve['equity'] = df_curve['pnl'].cumsum() + 1000000.0  # Assumed initial cash ($1M)
            df_curve['peak'] = df_curve['equity'].cummax()
            df_curve['drawdown'] = (df_curve['peak'] - df_curve['equity']) / df_curve['peak'] * 100
            data['max_drawdown'] = round(df_curve['drawdown'].max(), 2)
        except: pass
        
    return data

data = load_paper_data()

# --- SIDEBAR ---
with st.sidebar:
    
    
    config = config_manager.load_config()
    raw_symbols = config.get("paper_symbols", "")
    if not raw_symbols:
        raw_symbols = os.getenv('SYMBOLS', '')
        
    paper_symbols = raw_symbols.split(',')
    paper_symbols = [s.strip().upper() for s in paper_symbols if s.strip()]
    
    if paper_symbols:
        st.markdown('<div class="section-header">Paper Symbols</div>', unsafe_allow_html=True)
        st.markdown(" • ".join([f"**{s}**" for s in paper_symbols]))
        st.markdown("<br>", unsafe_allow_html=True)
    
    ui_components.render_system_status()

# --- HEADER ---
st.markdown("""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h2 style="margin:0;">PAPER TRADING <span class="paper-badge">SIMULATION</span></h2>
        <div style="font-family: 'Roboto Mono', monospace; color: #94A3B8; font-size: 0.9rem;">
            Auto-refreshes every {interval}s
        </div>
    </div>
""".format(interval=REFRESH_INTERVAL), unsafe_allow_html=True)

# --- METRICS ---
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(label="Daily PnL", value=f"${data['daily_pnl']:,.2f}", delta="Today")
with col2:
    st.metric(label="Total PnL (All Time)", value=f"${data['total_pnl']:,.2f}")
with col3:
    st.metric(label="Win Rate", value=f"{data['win_rate']:.1f}%", delta="Today")
with col4:
    trades_today = len(data['trades'][data['trades']['timestamp'] >= datetime.now().replace(hour=0, minute=0, second=0).timestamp()]) if not data['trades'].empty else 0
    st.metric(label="Trades Today", value=trades_today)

st.divider()

# --- MAIN CONTENT ---
left_col, right_col = st.columns([7, 3])

with left_col:
    st.markdown('<div class="section-header">CUMULATIVE PNL TRAJECTORY</div>', unsafe_allow_html=True)
    
    if not data['trades'].empty:
        show_all = st.checkbox("Show All History", value=False, key="paper_history")
        
        df_chart = data['trades'].copy().sort_values('timestamp')
        
        if not show_all:
            today_start = datetime.now().replace(hour=0, minute=0, second=0).timestamp()
            df_chart = df_chart[df_chart['timestamp'] >= today_start].copy()
        
        if not df_chart.empty:
            df_chart['cumulative_pnl'] = df_chart['pnl'].cumsum()
            
            fig = go.Figure()
            
            if show_all:
                df_chart = df_chart.reset_index(drop=True)
                x_values = df_chart.index
                df_chart['date_str'] = df_chart['datetime'].dt.strftime('%b %d')
                tick_vals = []
                tick_text = []
                last_date = None
                
                for i, row in df_chart.iterrows():
                    curr_date = row['date_str']
                    if curr_date != last_date:
                        tick_vals.append(i)
                        tick_text.append(curr_date)
                        last_date = curr_date
            else:
                x_values = df_chart['datetime']
            
            fig.add_trace(go.Scatter(
                x=x_values,
                y=df_chart['cumulative_pnl'],
                fill='tozeroy',
                fillcolor='rgba(96, 165, 250, 0.1)',
                mode='lines',
                line=dict(color='#60A5FA', width=3),
                name='PnL',
                customdata=df_chart['datetime'].dt.strftime('%Y-%m-%d %I:%M:%S %p'),
                hovertemplate='%{customdata}<br><b>$%{y:,.2f}</b><extra></extra>'
            ))
            
            layout_args = dict(
                template='plotly_dark',
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=0, r=0, t=10, b=0),
                height=450,
                xaxis=dict(
                    showgrid=True, 
                    gridcolor='#1F2937',
                    tickformat='%I:%M',
                    hoverformat='%I:%M:%S %p',
                ),
                yaxis=dict(showgrid=True, gridcolor='#1F2937', tickprefix='$'),
                hovermode='x unified',
                showlegend=False
            )
            
            if show_all:
                layout_args['xaxis']['tickmode'] = 'array'
                layout_args['xaxis']['tickvals'] = tick_vals
                layout_args['xaxis']['ticktext'] = tick_text
                del layout_args['xaxis']['tickformat']
                del layout_args['xaxis']['hoverformat']
            
            fig.update_layout(**layout_args)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        else:
            fig = go.Figure()
            fig.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=450)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    else:
        fig = go.Figure()
        fig.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=450)
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    
    st.markdown('<div class="section-header">SYMBOL PERFORMANCE</div>', unsafe_allow_html=True)
    time_range = st.radio("Time Range", ["Today", "All Time"], horizontal=True, label_visibility="collapsed")
    
    if not data['trades'].empty:
        trades_to_show = data['trades']
        if time_range == "Today":
            today_start = datetime.now().replace(hour=0, minute=0, second=0).timestamp()
            trades_to_show = trades_to_show[trades_to_show['timestamp'] >= today_start]
            
        if not trades_to_show.empty:
            symbol_stats = []
            for symbol, group in trades_to_show.groupby('symbol'):
                total_pnl = group['pnl'].sum()
                exits = group[group['side'].isin(['SELL', 'COVER'])]
                wins = len(exits[exits['pnl'] > 0])
                total_trades = len(exits)
                win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
                
                symbol_stats.append({
                    'Symbol': symbol,
                    'Total PnL': total_pnl,
                    'Win %': win_rate,
                    'Trades': total_trades
                })
        else:
            symbol_stats = []
        
        if symbol_stats:
            df_stats = pd.DataFrame(symbol_stats)
            df_stats = df_stats.sort_values('Total PnL', ascending=False)
            df_stats['Total PnL'] = df_stats['Total PnL'].apply(lambda x: f"${x:,.2f}")
            df_stats['Win %'] = df_stats['Win %'].apply(lambda x: f"{x:.1f}%")

            st.dataframe(
                df_stats,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Symbol": st.column_config.TextColumn("Symbol", width="medium"),
                    "Total PnL": st.column_config.TextColumn("Total PnL", width="medium"),
                    "Win %": st.column_config.ProgressColumn("Win %", format="%s", min_value=0, max_value=100),
                    "Trades": st.column_config.NumberColumn("Trades", width="small"),
                }
            )

with right_col:
    # Paper Positions
    st.markdown('<div class="section-header">PAPER POSITIONS</div>', unsafe_allow_html=True)
    
    if not data['positions'].empty:
        for _, pos in data['positions'].iterrows():
            qty = pos['qty']
            if qty != 0:
                pos_class = "position-long" if qty > 0 else "position-short"
                pos_type = "LONG" if qty > 0 else "SHORT"
                st.markdown(f"""
                    <div class="position-card {pos_class}">
                        <div class="position-symbol">{pos['symbol']}</div>
                        <div class="position-qty">{abs(qty)} shares • {pos_type}</div>
                    </div>
                """, unsafe_allow_html=True)
    else:
        st.markdown('<div style="color: #64748B; font-family: \'Roboto Mono\', monospace; margin-bottom: 2rem;">No open positions</div>', unsafe_allow_html=True)
    
    # Recent Alerts
    st.markdown('<div class="section-header">RECENT ALERTS</div>', unsafe_allow_html=True)
    
    if not data['alerts'].empty:
        for _, alert in data['alerts'].head(10).iterrows():
            ts = alert['datetime'].strftime('%H:%M:%S')
            direction = alert['direction']
            
            if direction == "bid-heavy":
                alert_class = "alert-long"
                side = "LONG"
            else:
                alert_class = "alert-short"
                side = "SHRT"
                
            st.markdown(f"""
                <div class="alert-box {alert_class}">
                    <span style="width: 50px;">{side}</span>
                    <strong style="color: #F8FAFC;">{alert['symbol']}</strong>
                    <span>${alert['price']:.2f}</span>
                    <span style="color: #64748B;">{ts}</span>
                </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown('<div style="color: #64748B; font-family: \'Roboto Mono\', monospace;">No recent alerts</div>', unsafe_allow_html=True)

# --- Auto Refresh ---
time.sleep(REFRESH_INTERVAL)
st.rerun()
