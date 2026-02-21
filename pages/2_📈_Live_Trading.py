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
LIVE_STATE_PATH = Path("live_trader_state_primary.json").resolve()
if not LIVE_STATE_PATH.exists():
    LIVE_STATE_PATH = Path("live_trader_state.json").resolve()

st.set_page_config(
    page_title="Live Trading | Dashboard",
    layout="wide",
    page_icon="📈"
)

# Check authentication
# if 'authenticated' not in st.session_state or not st.session_state.authenticated:
#     st.switch_page("app.py")

# Sidebar navigation
with st.sidebar:
    # Show trading symbols - try config first, then env
    config = config_manager.load_config()
    raw_symbols = config.get("live_symbols", "")
    if not raw_symbols:
        raw_symbols = os.getenv('LIVE_SYMBOLS', '')
        
    live_symbols = raw_symbols.split(',')
    live_symbols = [s.strip().upper() for s in live_symbols if s.strip()]
    
    # Fallback: get from live_trades table
    if not live_symbols:
        try:
            with closing(get_db_connection()) as conn:
                result = pd.read_sql_query("SELECT DISTINCT symbol FROM live_trades", conn)
                live_symbols = result['symbol'].tolist() if not result.empty else []
        except:
            live_symbols = []
    
    if live_symbols:
        st.markdown("### 📊 Live Symbols")
        st.markdown(" • ".join([f"**{s}**" for s in live_symbols]))
        st.divider()
    
    st.markdown("### 📍 Navigation")
    if st.button("🔬 Backtesting", use_container_width=True):
        st.switch_page("pages/3_🔬_Backtest.py")
    st.divider()
    if st.button("🚪 Logout", use_container_width=True):
        auth_manager.logout()
        st.rerun()


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
        .live-badge {
            background: linear-gradient(135deg, #00FF99, #00cc7a);
            color: #000;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.8rem;
            display: inline-block;
            margin-left: 10px;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
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
        .cooldown-banner {
            background: linear-gradient(135deg, rgba(255, 165, 0, 0.15), rgba(255, 69, 0, 0.15));
            border: 1px solid #FF6B35;
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 10px;
            color: #FF6B35;
            font-weight: 500;
        }
        .cooldown-banner.critical {
            background: linear-gradient(135deg, rgba(255, 51, 102, 0.15), rgba(220, 20, 60, 0.15));
            border-color: #FF3366;
            color: #FF3366;
        }
        .cooldown-reason { font-weight: 700; font-size: 1rem; }
        .cooldown-detail { font-size: 0.85rem; opacity: 0.85; }
        .cooldown-timer { font-size: 0.9rem; font-weight: 600; float: right; }
    </style>
""", unsafe_allow_html=True)

def get_db_connection():
    return sqlite3.connect(str(DB_PATH))

def load_live_state():
    """Load live trader positions from state file."""
    if LIVE_STATE_PATH.exists():
        try:
            with open(LIVE_STATE_PATH, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def load_live_data():
    """Load all live trading data."""
    data = {
        'trades': pd.DataFrame(),
        'positions': {},
        'daily_pnl': 0.0,
        'total_pnl': 0.0,
        'win_rate': 0.0,
        'alerts': pd.DataFrame(),
        'win_rate': 0.0,
        'alerts': pd.DataFrame(),
        'account_details': {},
        'account_history': pd.DataFrame()
    }

    
    today_start = datetime.now().replace(hour=0, minute=0, second=0).timestamp()
    
    # Load positions from state file
    state = load_live_state()
    data['positions'] = state.get('positions', {})
    data['account_details'] = state.get('account_details', {})
    data['active_cooldowns'] = state.get('active_cooldowns', [])
    
    with closing(get_db_connection()) as conn:
        # Live trades
        try:
            data['trades'] = pd.read_sql_query(
                "SELECT * FROM live_trades ORDER BY timestamp DESC",
                conn
            )
            if not data['trades'].empty:
                data['trades']['datetime'] = pd.to_datetime(
                    data['trades']['timestamp'], unit='s', utc=True
                ).dt.tz_convert('US/Eastern')
        except Exception as e:
            pass
        
        # Daily PnL
        try:
            result = pd.read_sql_query(
                f"SELECT SUM(pnl) as total FROM live_trades WHERE timestamp >= {today_start}",
                conn
            )
            data['daily_pnl'] = result.iloc[0]['total'] or 0.0
        except:
            pass
        
        # Total PnL (all time)
        try:
            result = pd.read_sql_query("SELECT SUM(pnl) as total FROM live_trades", conn)
            data['total_pnl'] = result.iloc[0]['total'] or 0.0
        except:
            pass
        
        # Win rate (today)
        try:
            wins = pd.read_sql_query(
                f"SELECT COUNT(*) as count FROM live_trades WHERE pnl > 0 AND timestamp >= {today_start}",
                conn
            ).iloc[0]['count']
            total = pd.read_sql_query(
                f"SELECT COUNT(*) as count FROM live_trades WHERE timestamp >= {today_start}",
                conn
            ).iloc[0]['count']
            data['win_rate'] = (wins / total * 100) if total > 0 else 0.0
        except:
            pass
        
        # Recent alerts (for live symbols only)
        try:
            config = config_manager.load_config()
            raw_symbols = config.get("live_symbols", "")
            if not raw_symbols:
                raw_symbols = os.getenv('LIVE_SYMBOLS', '')
            live_symbols = raw_symbols.split(',')
            live_symbols = [s.strip().upper() for s in live_symbols if s.strip()]
            if live_symbols:
                placeholders = ','.join(['?' for _ in live_symbols])
                data['alerts'] = pd.read_sql_query(
                    f"SELECT * FROM alerts WHERE symbol IN ({placeholders}) ORDER BY timestamp DESC LIMIT 30",
                    conn,
                    params=live_symbols
                )
            else:
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
            
        # Account History
        try:
            data['account_history'] = pd.read_sql_query(
                "SELECT * FROM account_history ORDER BY timestamp ASC",
                conn
            )
            if not data['account_history'].empty:
                 # Ensure timestamp is numeric
                data['account_history']['timestamp'] = pd.to_numeric(data['account_history']['timestamp'], errors='coerce')
                data['account_history'] = data['account_history'].dropna(subset=['timestamp'])

                data['account_history']['datetime'] = pd.to_datetime(
                    data['account_history']['timestamp'], unit='s', utc=True
                ).dt.tz_convert('US/Eastern')
        except:
            pass
    
    return data

# --- Load Data ---
data = load_live_data()

# --- Header ---
st.markdown("""
    <h1>📈 Live Trading Dashboard <span class="live-badge">● LIVE</span></h1>
""", unsafe_allow_html=True)
st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')} • Auto-refreshes every {REFRESH_INTERVAL}s")

st.divider()

# --- Metrics Row ---
col1, col2, col3, col4 = st.columns(4)

with col1:
    # Use real PnL from Schwab if available
    real_pnl = data['account_details'].get('day_pnl')
    if real_pnl is not None:
        pnl_val = real_pnl
        pnl_label = "Daily PnL (Schwab)"
    else:
        pnl_val = data['daily_pnl']
        pnl_label = "Daily PnL (Est.)"

    st.metric(
        label=pnl_label,
        value=f"${pnl_val:,.2f}",
        delta="Today"
    )

with col2:
    # Show Account Value if available, else Total PnL
    acct_val = data['account_details'].get('liquidation_value')
    if acct_val:
        st.metric(
            label="Account Value",
            value=f"${acct_val:,.2f}"
        )
    else:
        st.metric(
            label="Total PnL (All Time)",
            value=f"${data['total_pnl']:,.2f}"
        )

with col3:
    buying_power = data['account_details'].get('buying_power')
    if buying_power:
        st.metric(
            label="Buying Power",
            value=f"${buying_power:,.2f}"
        )
    else:
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
    # Account Value Chart
    st.subheader("📊 Account Value (Liquidation)")
    
    if not data['account_history'].empty:
        show_all = st.checkbox("Show All History", value=False, key="live_history")
        
        df_chart = data['account_history'].copy().sort_values('timestamp')
        
        if not show_all:
            today_start = datetime.now().replace(hour=0, minute=0, second=0).timestamp()
            df_chart = df_chart[df_chart['timestamp'] >= today_start].copy()
        
        if not df_chart.empty:
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
            
            # Main Value Line (No Fill)
            fig.add_trace(go.Scatter(
                x=x_values,
                y=df_chart['liquidation_value'],
                mode='lines',
                name='Value',
                line=dict(color='#00FF99', width=3),
                customdata=df_chart['datetime'].dt.strftime('%Y-%m-%d %I:%M:%S %p'),
                hovertemplate='<b>Date:</b> %{customdata}<br><b>Value:</b> $%{y:,.2f}<extra></extra>'
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
            st.info("No account history yet today.")
    else:
        st.info("No account history recorded yet.")
    


with right_col:
    # --- Active Cooldowns ---
    if data.get('active_cooldowns'):
        st.subheader("⚠️ Active Cooldowns")
        for cd in data['active_cooldowns']:
            remaining = cd.get('remaining_seconds', 0)
            if remaining > 0:
                mins = remaining // 60
                secs = remaining % 60
                timer_text = f"{mins}m {secs}s remaining"
            elif remaining == -1:
                timer_text = "Until restart"
            else:
                timer_text = "Expiring..."
            
            is_critical = cd.get('reason') == 'Account Stop Loss'
            css_class = 'cooldown-banner critical' if is_critical else 'cooldown-banner'
            
            st.markdown(f"""
                <div class="{css_class}">
                    <span class="cooldown-timer">⏱ {timer_text}</span>
                    <div class="cooldown-reason">🚫 {cd['reason']}</div>
                    <div class="cooldown-detail">{cd.get('detail', '')}</div>
                </div>
            """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    # Live Positions
    st.subheader("💼 Live Positions")
    
    if data['positions']:
        for symbol, qty in data['positions'].items():
            pos_class = "position-long" if qty > 0 else "position-short"
            pos_type = "LONG" if qty > 0 else "SHORT"
            st.markdown(f"""
                <div class="position-card {pos_class}">
                    <div class="position-symbol">{symbol}</div>
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
