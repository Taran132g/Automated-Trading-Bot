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

# Load environment variables
load_dotenv()
import sys
# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))
import config_manager
import auth_manager

# Check authentication
# auth_manager.require_auth()
# Configuration
REFRESH_INTERVAL = 3
DB_PATH = Path("penny_basing.db").resolve()
PAPER_STATE_PATH = Path("paper_trader_state.json").resolve()

st.set_page_config(
    page_title="Paper Trading | Dashboard",
    layout="wide",
    page_icon="🔬"
)

# Check authentication
# if 'authenticated' not in st.session_state or not st.session_state.authenticated:
#     st.switch_page("app.py")

# Sidebar navigation
with st.sidebar:
    # Show trading symbols from config
    config = config_manager.load_config()
    raw_symbols = config.get("paper_symbols", "")
    if not raw_symbols:
        raw_symbols = os.getenv('SYMBOLS', '')
        
    paper_symbols = raw_symbols.split(',')
    paper_symbols = [s.strip().upper() for s in paper_symbols if s.strip()]
    
    if paper_symbols:
        st.markdown("### 📊 Paper Symbols")
        st.markdown(" • ".join([f"**{s}**" for s in paper_symbols]))
        st.divider()
    
    st.markdown("### 📍 Navigation")
    if st.button("📈 Live Trading", use_container_width=True):
        st.switch_page("pages/2_📈_Live_Trading.py")
    st.divider()
    if st.button("⚙️ Admin Controls", use_container_width=True):
        st.switch_page("pages/4_⚙️_Admin_Controls.py")
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.switch_page("app.py")

# --- CSS Styling ---
st.markdown("""
    <style>
        .block-container { padding-top: 1rem; }
        .stMetric {
            background-color: #1e293b;
            padding: 10px;
            border-radius: 8px;
            border: 1px solid #334155;
        }
        [data-testid="stDataFrame"] {
            border: 1px solid #334155;
            border-radius: 8px;
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
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border-radius: 12px;
            padding: 1rem;
            border: 1px solid #334155;
            margin-bottom: 0.5rem;
        }
        .position-symbol { font-size: 1.3rem; font-weight: 700; }
        .position-qty { color: #94a3b8; }
        .position-long { border-left: 4px solid #00FF99; }
        .position-short { border-left: 4px solid #FF3366; }
        
        /* Alert Boxes */
        .alert-box {
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 8px;
            font-weight: 500;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .alert-long {
            background-color: rgba(0, 255, 153, 0.1);
            border: 1px solid #00FF99;
            color: #00FF99;
        }
        .alert-short {
            background-color: rgba(255, 51, 102, 0.1);
            border: 1px solid #FF3366;
            color: #FF3366;
        }
    </style>
""", unsafe_allow_html=True)

def get_db_connection():
    return sqlite3.connect(str(DB_PATH))

def load_paper_state():
    """Load paper trader positions from state file."""
    if PAPER_STATE_PATH.exists():
        try:
            with open(PAPER_STATE_PATH, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def load_paper_data():
    """Load all paper trading data."""
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
        # Paper trades
        try:
            data['trades'] = pd.read_sql_query(
                "SELECT * FROM paper_trades ORDER BY timestamp DESC",
                conn
            )
            if not data['trades'].empty:
                # Ensure numeric columns
                cols = ['timestamp', 'pnl', 'price', 'qty']
                for col in cols:
                    if col in data['trades'].columns:
                        data['trades'][col] = pd.to_numeric(data['trades'][col], errors='coerce')
                
                data['trades'] = data['trades'].dropna(subset=['timestamp'])

                data['trades']['datetime'] = pd.to_datetime(
                    data['trades']['timestamp'], unit='s', utc=True
                ).dt.tz_convert('US/Eastern')
        except Exception as e:
            pass
        
        # Paper positions
        try:
            data['positions'] = pd.read_sql_query("SELECT * FROM paper_positions", conn)
        except:
            pass
        
        # Daily PnL
        try:
            result = pd.read_sql_query(
                f"SELECT SUM(pnl) as total FROM paper_trades WHERE timestamp >= {today_start}",
                conn
            )
            data['daily_pnl'] = result.iloc[0]['total'] or 0.0
        except:
            pass
        
        # Total PnL (all time)
        try:
            result = pd.read_sql_query("SELECT SUM(pnl) as total FROM paper_trades", conn)
            data['total_pnl'] = result.iloc[0]['total'] or 0.0
        except:
            pass
        
        # Win rate (today)
        try:
            wins = pd.read_sql_query(
                f"SELECT COUNT(*) as count FROM paper_trades WHERE pnl > 0 AND timestamp >= {today_start}",
                conn
            ).iloc[0]['count']
            total = pd.read_sql_query(
                f"SELECT COUNT(*) as count FROM paper_trades WHERE timestamp >= {today_start}",
                conn
            ).iloc[0]['count']
            data['win_rate'] = (wins / total * 100) if total > 0 else 0.0
        except:
            pass
        
        # Recent alerts
        try:
            data['alerts'] = pd.read_sql_query(
                "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 30",
                conn
            )
            if not data['alerts'].empty:
                data['alerts']['datetime'] = pd.to_datetime(
                    data['alerts']['timestamp'], unit='s', utc=True
                ).dt.tz_convert('US/Eastern')
        except:
            pass
    
    return data

# --- Load Data ---
data = load_paper_data()

# --- Header ---
st.markdown("""
    <h1>🔬 Paper Trading <span class="paper-badge">SIMULATION</span></h1>
""", unsafe_allow_html=True)
st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')} • Auto-refreshes every {REFRESH_INTERVAL}s")

st.divider()

# --- Metrics Row ---
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="Daily PnL",
        value=f"${data['daily_pnl']:,.2f}",
        delta="Today"
    )

with col2:
    st.metric(
        label="Total PnL (All Time)",
        value=f"${data['total_pnl']:,.2f}"
    )

with col3:
    st.metric(
        label="Win Rate",
        value=f"{data['win_rate']:.1f}%",
        delta="Today"
    )

with col4:
    trades_today = len(data['trades'][data['trades']['timestamp'] >= datetime.now().replace(hour=0, minute=0, second=0).timestamp()]) if not data['trades'].empty else 0
    st.metric(
        label="Trades Today",
        value=trades_today
    )

st.divider()

# --- Main Content ---
left_col, right_col = st.columns([2, 1])

with left_col:
    # PnL Chart
    st.subheader("📊 Cumulative PnL")
    
    if not data['trades'].empty:
        show_all = st.checkbox("Show All History", value=False, key="paper_history")
        
        df_chart = data['trades'].copy().sort_values('timestamp')
        
        if not show_all:
            today_start = datetime.now().replace(hour=0, minute=0, second=0).timestamp()
            df_chart = df_chart[df_chart['timestamp'] >= today_start].copy()
        
        if not df_chart.empty:
            df_chart['cumulative_pnl'] = df_chart['pnl'].cumsum()
            
            fig = go.Figure()
            
            # Prepare X-axis data
            if show_all:
                # Use index-based X-axis to remove gaps
                df_chart = df_chart.reset_index(drop=True)
                x_values = df_chart.index
                
                # Generate ticks: Show date label only when day changes
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
                # Standard time-based X-axis for intraday
                x_values = df_chart['datetime']
            
            # Main PnL Line
            fig.add_trace(go.Scatter(
                x=x_values,
                y=df_chart['cumulative_pnl'],
                mode='lines',
                name='PnL',
                line=dict(color='#60a5fa', width=3),
                customdata=df_chart['datetime'].dt.strftime('%Y-%m-%d %I:%M:%S %p'),
                hovertemplate='<b>Date:</b> %{customdata}<br><b>PnL:</b> $%{y:,.2f}<extra></extra>'
            ))
            
            # Long Markers with text
            longs = df_chart[df_chart['side'] == 'long']
            if not longs.empty:
                long_x = longs.index if show_all else longs['datetime']
                fig.add_trace(go.Scatter(
                    x=long_x,
                    y=longs['cumulative_pnl'],
                    mode='markers+text',
                    name='Long',
                    marker=dict(symbol='triangle-up', color='#00FF99', size=12, line=dict(color='white', width=1)),
                    text=["BUY"] * len(longs),
                    textposition="top center",
                    textfont=dict(color='#00FF99', size=10),
                    hoverinfo='skip'
                ))
            
            # Short Markers with text
            shorts = df_chart[df_chart['side'] == 'short']
            if not shorts.empty:
                short_x = shorts.index if show_all else shorts['datetime']
                fig.add_trace(go.Scatter(
                    x=short_x,
                    y=shorts['cumulative_pnl'],
                    mode='markers+text',
                    name='Short',
                    marker=dict(symbol='triangle-down', color='#FF3366', size=12, line=dict(color='white', width=1)),
                    text=["SELL"] * len(shorts),
                    textposition="bottom center",
                    textfont=dict(color='#FF3366', size=10),
                    hoverinfo='skip'
                ))
            
            # Layout
            layout_args = dict(
                template='plotly_dark',
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=10, r=10, t=30, b=10),
                height=350,
                xaxis=dict(
                    showgrid=True, 
                    gridcolor='rgba(255,255,255,0.1)',
                    tickformat='%I:%M:%S %p',
                    hoverformat='%I:%M:%S %p',
                ),
                yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)', tickprefix='$'),
                hovermode='x unified',
                showlegend=False
            )
            
            if show_all:
                # Override for "Show All History" - Index based
                layout_args['xaxis']['tickmode'] = 'array'
                layout_args['xaxis']['tickvals'] = tick_vals
                layout_args['xaxis']['ticktext'] = tick_text
                del layout_args['xaxis']['tickformat']
                del layout_args['xaxis']['hoverformat']
            
            fig.update_layout(**layout_args)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No trades yet today.")
    else:
        st.info("No paper trades recorded yet.")
    
    # --- Per-Symbol Performance ---
    st.subheader("🏆 Symbol Performance")
    
    # Time Range Toggle
    time_range = st.radio("Time Range", ["All Time", "Today"], horizontal=True, label_visibility="collapsed")
    
    if not data['trades'].empty:
        # Filter trades based on selection
        trades_to_show = data['trades']
        if time_range == "Today":
            today_start = datetime.now().replace(hour=0, minute=0, second=0).timestamp()
            trades_to_show = trades_to_show[trades_to_show['timestamp'] >= today_start]
            
        if not trades_to_show.empty:
            # Calculate per-symbol metrics
            symbol_stats = []
            for symbol, group in trades_to_show.groupby('symbol'):
                total_pnl = group['pnl'].sum()
                wins = len(group[group['pnl'] > 0])
                total_trades = len(group)
                win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
                
                symbol_stats.append({
                    'Symbol': symbol,
                    'Total PnL': total_pnl,
                    'Win Rate': win_rate,
                    'Trades': total_trades
                })
        else:
            symbol_stats = []
            st.info("No trades found for this time range.")
        
        if symbol_stats:
            df_stats = pd.DataFrame(symbol_stats)
            # Sort by PnL descending
            df_stats = df_stats.sort_values('Total PnL', ascending=False)
            
            # Format for display
            df_stats['Total PnL'] = df_stats['Total PnL'].apply(lambda x: f"${x:,.2f}")
            df_stats['Win Rate'] = df_stats['Win Rate'].apply(lambda x: f"{x:.1f}%")
            
            st.dataframe(
                df_stats,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Symbol": st.column_config.TextColumn("Symbol", width="medium"),
                    "Total PnL": st.column_config.TextColumn("Total PnL", width="medium"),
                    "Win Rate": st.column_config.ProgressColumn("Win Rate", format="%s", min_value=0, max_value=100),
                    "Trades": st.column_config.NumberColumn("Trades", width="small"),
                }
            )
    
with right_col:
    # Paper Positions
    st.subheader("💼 Paper Positions")
    
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
        st.info("No open positions")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Recent Alerts
    st.subheader("🔔 Recent Alerts")
    
    if not data['alerts'].empty:
        for _, alert in data['alerts'].head(10).iterrows():
            ts = alert['datetime'].strftime('%I:%M:%S %p')
            direction = alert['direction']
            
            if direction == "bid-heavy":
                alert_class = "alert-long"
                icon = "🟢"
                side = "LONG"
            else:
                alert_class = "alert-short"
                icon = "🔴"
                side = "SHORT"
                
            st.markdown(f"""
                <div class="alert-box {alert_class}">
                    <span>{icon} <strong>{alert['symbol']}</strong> ({side})</span>
                    <span>${alert['price']:.3f} • {ts}</span>
                </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No recent alerts")

# --- Auto Refresh ---
time.sleep(REFRESH_INTERVAL)
st.rerun()
