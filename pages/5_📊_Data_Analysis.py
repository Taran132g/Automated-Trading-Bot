import sys
from pathlib import Path
import pandas as pd
import streamlit as st

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))
import config_manager
from trade_analyzer import analyze_trades

st.set_page_config(
    page_title="Data Analysis | Dashboard",
    layout="wide",
    page_icon="📊"
)

# --- Sidebar ---
with st.sidebar:
    config = config_manager.load_config()
    st.markdown("### 📍 Navigation")
    if st.button("📈 Live Trading", use_container_width=True):
        st.switch_page("pages/2_📈_Live_Trading.py")
    if st.button("🔬 Paper Trading", use_container_width=True):
        st.switch_page("pages/3_🔬_Backtest.py")
    st.divider()
    if st.button("⚙️ Admin Controls", use_container_width=True):
        st.switch_page("pages/4_⚙️_Admin_Controls.py")
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.switch_page("app.py")

# --- CSS ---
st.markdown("""
<style>
    .block-container { padding-top: 1rem; }
    .stMetric {
        background-color: #1e293b;
        padding: 10px;
        border-radius: 8px;
        border: 1px solid #334155;
    }
    .analysis-badge {
        background: linear-gradient(135deg, #a78bfa, #7c3aed);
        color: #fff;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.8rem;
        display: inline-block;
        margin-left: 10px;
    }
    .symbol-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border-radius: 12px;
        padding: 1rem;
        border: 1px solid #334155;
        margin-bottom: 0.5rem;
    }
    .symbol-name { font-size: 1.3rem; font-weight: 700; color: #e2e8f0; }
    .symbol-detail { color: #94a3b8; font-size: 0.9rem; margin-top: 4px; }
    .positive { color: #00FF99; }
    .negative { color: #FF3366; }
</style>
""", unsafe_allow_html=True)

# --- Header ---
st.markdown("""
    <h1>📊 Data Analysis <span class="analysis-badge">TRADE DATA</span></h1>
""", unsafe_allow_html=True)
st.caption("Paste Schwab filled-orders text to analyze price improvement & PnL")

st.divider()

# --- Input ---
raw_data = st.text_area(
    "Paste Filled Orders data from Schwab",
    height=250,
    placeholder="Paste the filled orders rows here (the comma-separated lines starting with ,,date ...)",
)

analyze_btn = st.button("🔍 Analyze", type="primary", use_container_width=True)

if analyze_btn and raw_data.strip():
    result = analyze_trades(raw_data)

    if result['total_fills'] == 0:
        st.warning("No valid filled orders found. Make sure you pasted the filled-orders section.")
    else:
        st.divider()

        # --- Metric Cards ---
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Total Fills", f"{result['total_fills']}")
        with c2:
            pi_color = "normal"
            st.metric("Total Price Improvement", f"${result['total_pi']:.2f}")
        with c3:
            pnl_val = result['total_pnl']
            st.metric("Total PnL", f"${pnl_val:,.2f}", delta=f"{'profit' if pnl_val >= 0 else 'loss'}")
        with c4:
            st.metric("PnL / Share", f"${result['total_pnl_per_share']:.4f}")

        st.divider()

        # --- Two-column layout ---
        left, right = st.columns([1, 1])

        with left:
            st.subheader("💰 Price Improvement")

            pi_rows = []
            for sym, info in result['symbol_summaries'].items():
                pi_rows.append({
                    'Symbol': sym,
                    'Fills': info['fills'],
                    'Price Improvement': f"${info['pi']:.2f}",
                })
            pi_rows.append({
                'Symbol': 'TOTAL',
                'Fills': result['total_fills'],
                'Price Improvement': f"${result['total_pi']:.2f}",
            })
            df_pi = pd.DataFrame(pi_rows)
            st.dataframe(df_pi, use_container_width=True, hide_index=True)

            st.markdown(f"**Orders WITH PI:** {result['pi_with']}  •  **WITHOUT PI:** {result['pi_without']}")

        with right:
            st.subheader("📈 PnL Breakdown")

            pnl_rows = []
            for sym, info in result['symbol_summaries'].items():
                pnl_rows.append({
                    'Symbol': sym,
                    'PnL': f"${info['pnl']:,.2f}",
                    'Shares': f"{info['shares_traded']:,}",
                    'PnL/Share': f"${info['pnl_per_share']:.4f}",
                })
            pnl_rows.append({
                'Symbol': 'TOTAL',
                'PnL': f"${result['total_pnl']:,.2f}",
                'Shares': f"{result['total_shares']:,}",
                'PnL/Share': f"${result['total_pnl_per_share']:.4f}",
            })
            df_pnl = pd.DataFrame(pnl_rows)
            st.dataframe(df_pnl, use_container_width=True, hide_index=True)

        # --- Detailed Trades Table ---
        st.divider()
        with st.expander("📋 All Parsed Trades", expanded=False):
            if result['trades']:
                df_trades = pd.DataFrame(result['trades'])
                df_trades.columns = ['Time', 'Side', 'Qty', 'Pos Effect', 'Symbol', 'Price', 'PI', 'Order Type']
                st.dataframe(df_trades, use_container_width=True, hide_index=True)

elif analyze_btn:
    st.warning("Please paste some trade data first.")
