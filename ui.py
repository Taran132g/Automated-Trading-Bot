import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path
import pandas as pd
import streamlit as st
from datetime import datetime

# Configuration
REFRESH_INTERVAL = 3
DB_PATH = Path("penny_basing.db").resolve()
PAGE_TITLE = "Penny Basing | Paper Trader"

st.set_page_config(page_title=PAGE_TITLE, layout="wide", page_icon="📈")

# --- CSS Styling ---
st.markdown("""
    <style>
        .block-container { padding-top: 1rem; padding-bottom: 1rem; }
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
    </style>
""", unsafe_allow_html=True)

# --- Data Loading Functions ---

def get_db_connection():
    return sqlite3.connect(str(DB_PATH))

def load_data():
    """Load all necessary data in one go to ensure consistency."""
    data = {}
    
    with closing(get_db_connection()) as conn:
        # 1. Alerts
        try:
            data['alerts'] = pd.read_sql_query(
                "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 50", conn
            )
            if not data['alerts'].empty:
                data['alerts']["timestamp"] = pd.to_datetime(
                    data['alerts']["timestamp"], unit="s", utc=True
                ).dt.tz_convert("US/Eastern")
        except Exception:
            data['alerts'] = pd.DataFrame()

        # 2. Paper Positions
        try:
            data['positions'] = pd.read_sql_query("SELECT * FROM paper_positions", conn)
        except Exception:
            data['positions'] = pd.DataFrame()

        # 3. Realized PnL (Summary)
        try:
            data['realized'] = pd.read_sql_query(
                "SELECT symbol, SUM(pnl) as realized_pnl FROM paper_trades GROUP BY symbol", conn
            )
        except Exception:
            data['realized'] = pd.DataFrame()

        # 4. Trade History (for Graph)
        try:
            data['trades'] = pd.read_sql_query(
                "SELECT timestamp, pnl, side, symbol FROM paper_trades ORDER BY timestamp ASC", conn
            )
            if not data['trades'].empty:
                data['trades']["timestamp"] = pd.to_datetime(
                    data['trades']["timestamp"], unit="s", utc=True
                ).dt.tz_convert("US/Eastern")
        except Exception:
            data['trades'] = pd.DataFrame()

    return data

# --- Main UI Layout ---

# st.title(f"🚀 {PAGE_TITLE}") # Moved down

# Load Data
data = load_data()

# Calculate Data
configured_symbols = [s.strip() for s in os.getenv("SYMBOLS", "").split(",") if s.strip()]
all_symbols = set(configured_symbols)
if not data['positions'].empty:
    all_symbols.update(data['positions']['symbol'].unique())
if not data['realized'].empty:
    all_symbols.update(data['realized']['symbol'].unique())

summary_rows = []
total_unrealized = 0.0
total_realized = 0.0

for sym in sorted(all_symbols):
    # Get Position Data
    pos = data['positions'][data['positions']['symbol'] == sym]
    qty = pos.iloc[0]['qty'] if not pos.empty else 0
    unrealized = pos.iloc[0]['pnl'] if not pos.empty else 0.0
    entry_price = pos.iloc[0]['entry_price'] if not pos.empty and 'entry_price' in pos.columns else 0.0
    
    # Get Realized Data
    real = data['realized'][data['realized']['symbol'] == sym]
    realized_val = real.iloc[0]['realized_pnl'] if not real.empty else 0.0
    
    total_unrealized += unrealized
    total_realized += realized_val
    
    summary_rows.append({
        "Symbol": sym,
        "Qty": qty,
        "Entry Price": entry_price,
        "Unrealized PnL": unrealized,
        "Realized PnL": realized_val,
        "Total PnL": unrealized + realized_val
    })

total_pnl = total_unrealized + total_realized

# --- Main UI Layout (Header) ---
h_col1, h_col2 = st.columns([3, 1])
with h_col1:
    current_date = datetime.now().strftime("%b %-d, %Y")
    st.title(f"🚀 {PAGE_TITLE} - {current_date}")
with h_col2:
    st.markdown(f"<div style='text-align: right; font-size: 1.5em; font-weight: bold; padding-top: 35px;'>Portfolio PnL: <span style='color: {'#00FF99' if total_realized >= 0 else '#FF3366'}'>${total_realized:,.2f}</span></div>", unsafe_allow_html=True)

st.divider()

# ROW 1: Unified Positions & PnL
st.subheader("📊 Portfolio Overview")


if summary_rows:
    df_summary = pd.DataFrame(summary_rows)
    
    # Calculate Totals (Removed as per user request)
    # total_row = pd.DataFrame([{ ... }])
    
    # Prepend Total Row (Removed)
    df_display = df_summary.copy()
    
    # Format for display (Removed manual string conversion to allow Styler to work)
    # def format_currency(x): ...
    
    # Remove Total PnL column if it exists
    if "Total PnL" in df_display.columns:
        df_display = df_display.drop(columns=["Total PnL"])

    # Styling with Pandas Styler
    def style_dataframe(styler):
        styler.format({
            "Qty": "{:.0f}",
            "Entry Price": "${:,.2f}",
            "Unrealized PnL": "${:,.2f}",
            "Realized PnL": "${:,.2f}",
        }, na_rep="")
        
        # Bold specific columns
        styler.set_properties(subset=["Symbol", "Realized PnL"], **{'font-weight': 'bold'})
        
        # Color code PnL columns
        def color_pnl(val):
            if isinstance(val, (int, float)):
                if val > 0:
                    return 'color: #00FF99'
                elif val < 0:
                    return 'color: #FF3366'
            return 'color: white'

        styler.map(color_pnl, subset=["Unrealized PnL", "Realized PnL"])

        return styler

    st.dataframe(
        style_dataframe(df_display.style), 
        use_container_width=True, 
        hide_index=True,
        column_config={
            "Symbol": st.column_config.TextColumn("Symbol", width="small"),
            "Qty": st.column_config.NumberColumn("Qty", format="%d"),
        }
    )
else:
    st.info("No data.")

st.divider()

# ROW 2
r2_c1, r2_c2 = st.columns(2)

with r2_c1:
    # PnL Graph
    if not data['trades'].empty:
        import plotly.graph_objects as go
        
        st.subheader("📈 Cumulative PnL")
        
        show_history = st.checkbox("Show All History", value=False)
        
        df_chart = data['trades'].copy()
        
        if not show_history:
            # Filter to today only
            today_midnight = pd.Timestamp.now(tz="US/Eastern").normalize()
            df_chart = df_chart[df_chart['timestamp'] >= today_midnight].copy()
            
            if not df_chart.empty:
                # Recalculate PnL from 0 for today
                df_chart['cumulative_pnl'] = df_chart['pnl'].cumsum()
        else:
            # Full history
            df_chart['cumulative_pnl'] = df_chart['pnl'].cumsum()

        if not df_chart.empty:
            fig = go.Figure()
            
            # Prepare X-axis data
            if show_history:
                # Use index-based X-axis to remove gaps
                df_chart = df_chart.sort_values('timestamp').reset_index(drop=True)
                x_values = df_chart.index
                
                # Generate ticks: Show date label only when day changes
                df_chart['date_str'] = df_chart['timestamp'].dt.strftime('%b %d')
                tick_vals = []
                tick_text = []
                last_date = None
                
                # Simple logic: Add tick for the first trade of each new day
                for i, row in df_chart.iterrows():
                    curr_date = row['date_str']
                    if curr_date != last_date:
                        tick_vals.append(i)
                        tick_text.append(curr_date)
                        last_date = curr_date
            else:
                # Standard time-based X-axis for intraday
                x_values = df_chart['timestamp']

            # Main PnL Line (No Fill)
            fig.add_trace(go.Scatter(
                x=x_values,
                y=df_chart['cumulative_pnl'],
                mode='lines',
                name='PnL',
                line=dict(color='#00FF99', width=3),
                hovertemplate='%{y:$.2f}<extra></extra>' # Simple hover
            ))
            
            # Buy Markers
            buys = df_chart[df_chart['side'] == 'long']
            if not buys.empty:
                buy_x = buys.index if show_history else buys['timestamp']
                fig.add_trace(go.Scatter(
                    x=buy_x,
                    y=buys['cumulative_pnl'],
                    mode='markers+text',
                    name='Buy',
                    marker=dict(symbol='triangle-up', color='#00FF99', size=12, line=dict(color='white', width=1)),
                    text=["BUY"] * len(buys),
                    textposition="top center",
                    textfont=dict(color='#00FF99', size=10),
                    hoverinfo='skip'
                ))
                
            # Sell Markers
            sells = df_chart[df_chart['side'] == 'short']
            if not sells.empty:
                sell_x = sells.index if show_history else sells['timestamp']
                fig.add_trace(go.Scatter(
                    x=sell_x,
                    y=sells['cumulative_pnl'],
                    mode='markers+text',
                    name='Sell',
                    marker=dict(symbol='triangle-down', color='#FF3366', size=12, line=dict(color='white', width=1)),
                    text=["SELL"] * len(sells),
                    textposition="bottom center",
                    textfont=dict(color='#FF3366', size=10),
                    hoverinfo='skip'
                ))

            # Default Range: Today (Only apply if showing history, otherwise auto-scale is fine)
            layout_args = dict(
                template="plotly_dark",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=10, r=10, t=30, b=10),
                height=350,
                xaxis=dict(
                    showgrid=True, 
                    gridcolor='rgba(255,255,255,0.1)',
                    tickformat='%H:%M:%S',
                    hoverformat='%H:%M:%S',
                ),
                yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)', tickprefix="$"),
                hovermode="x unified",
                showlegend=False
            )
            
            if show_history:
                 # Override for "Show All History" - Index based
                 layout_args['yaxis']['range'] = [0, 5000]
                 layout_args['xaxis']['tickmode'] = 'array'
                 layout_args['xaxis']['tickvals'] = tick_vals
                 layout_args['xaxis']['ticktext'] = tick_text
                 # Remove time formatting since X is now an integer index
                 if 'tickformat' in layout_args['xaxis']: del layout_args['xaxis']['tickformat']
                 if 'hoverformat' in layout_args['xaxis']: del layout_args['xaxis']['hoverformat']
            else:
                 # Default "Today" view - Auto-scale
                 pass

            fig.update_layout(**layout_args)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No trades today.")
    else:
        st.info("No trades yet.")

with r2_c2:
    st.subheader("🔔 Recent Alerts")
    if not data['alerts'].empty:
        # Create tabs for each symbol + All
        sorted_syms = sorted(list(all_symbols))
        tabs = st.tabs(["All"] + sorted_syms)
        
        # "All" Tab
        with tabs[0]:
            alerts_display = data['alerts'][["timestamp", "symbol", "direction", "price"]].copy()
            alerts_display["timestamp"] = alerts_display["timestamp"].dt.strftime("%H:%M:%S")
            alerts_display["price"] = alerts_display["price"].apply(lambda x: f"${x:.3f}")
            st.dataframe(alerts_display, use_container_width=True, hide_index=True, height=300)
            
        # Per-Symbol Tabs
        for i, sym in enumerate(sorted_syms):
            with tabs[i+1]:
                sym_alerts = data['alerts'][data['alerts']['symbol'] == sym].copy()
                if not sym_alerts.empty:
                    sym_alerts["timestamp"] = sym_alerts["timestamp"].dt.strftime("%H:%M:%S")
                    sym_alerts["price"] = sym_alerts["price"].apply(lambda x: f"${x:.3f}")
                    st.dataframe(sym_alerts[["timestamp", "direction", "price"]], use_container_width=True, hide_index=True, height=300)
                else:
                    st.info(f"No alerts for {sym}.")
    else:
        st.info("No alerts yet.")

# --- Auto Refresh ---
time.sleep(REFRESH_INTERVAL)
st.rerun()
