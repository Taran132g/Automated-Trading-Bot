import sqlite3
import time
from pathlib import Path
from contextlib import closing
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import plotly.graph_objects as go
import sys

sys.path.append(str(Path(__file__).parent.parent))
import ui_components

REFRESH_INTERVAL = 5
BASELINE_DB = Path("penny_basing.db").resolve()
PATTERN_DB = Path("penny_basing_patterns.db").resolve()

st.set_page_config(
    page_title="Comparison | Filter Analysis",
    layout="wide",
    page_icon="🔬",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
        .stApp {
            background-color: #0B0E14;
            color: #E2E8F0;
            font-family: 'Inter', sans-serif;
        }
        #MainMenu, footer { visibility: hidden; }
        .block-container { padding-top: 1rem; max-width: 98%; }

        [data-testid="stMetricValue"] {
            font-size: 1.8rem !important;
            font-weight: 700 !important;
            color: #F8FAFC !important;
            font-family: 'Roboto Mono', monospace;
        }
        [data-testid="stMetricDelta"] { font-size: 0.9rem !important; }

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
        .adv-metric {
            background: linear-gradient(180deg, #111827 0%, #0B0E14 100%);
            border: 1px solid #1F2937;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }
        .adv-metric-title {
            color: #94A3B8;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 10px;
        }
        .adv-metric-value {
            font-family: 'Roboto Mono', monospace;
            font-size: 2rem;
            font-weight: 700;
        }
        .color-green { color: #00FF99; }
        .color-red { color: #EF4444; }
        .color-blue { color: #3B82F6; }
        .color-yellow { color: #F59E0B; }
        .color-white { color: #F8FAFC; }
        h1, h2, h3 {
            font-family: 'Inter', sans-serif;
            color: #F8FAFC !important;
            letter-spacing: -0.5px;
        }
        .filter-badge {
            background: linear-gradient(135deg, #a855f7, #6b21a8);
            color: #fff;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.8rem;
            display: inline-block;
            margin-left: 10px;
        }
        .baseline-badge {
            background: linear-gradient(135deg, #60a5fa, #3b82f6);
            color: #fff;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.8rem;
            display: inline-block;
            margin-left: 10px;
        }
    </style>
""", unsafe_allow_html=True)

with st.sidebar:
    ui_components.render_system_status()


# --- Data Loading ---

def load_trades(db_path: Path) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    try:
        with closing(sqlite3.connect(str(db_path))) as conn:
            df = pd.read_sql_query("SELECT * FROM paper_trades ORDER BY timestamp", conn)
            if not df.empty:
                for col in ['timestamp', 'pnl', 'qty', 'price']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                df = df.dropna(subset=['timestamp'])
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='s', utc=True).dt.tz_convert('US/Eastern')
                df['date'] = df['datetime'].dt.date
            return df
    except:
        return pd.DataFrame()


def compute_stats(exits_df: pd.DataFrame) -> dict:
    if exits_df.empty:
        return {
            'win_rate': 0.0, 'pnl_per_share': 0.0, 'profit_factor': 0.0,
            'max_consec_loss': 0, 'total_trades': 0, 'total_pnl': 0.0,
            'avg_win': 0.0, 'avg_loss': 0.0
        }

    wins_df = exits_df[exits_df['pnl'] > 0]
    losses_df = exits_df[exits_df['pnl'] < 0]
    total = len(exits_df)

    win_rate = len(wins_df) / total * 100 if total > 0 else 0.0
    total_pnl = exits_df['pnl'].sum()
    total_exit_shares = exits_df['qty'].abs().sum()
    pnl_per_share = total_pnl / total_exit_shares if total_exit_shares > 0 else 0.0

    gross_profit = wins_df['pnl'].sum()
    gross_loss = abs(losses_df['pnl'].sum())
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = float('inf')
    else:
        profit_factor = 0.0

    # Max consecutive losses (time-ordered)
    pnl_series = exits_df.sort_values('timestamp')['pnl'].tolist()
    max_consec = 0
    current = 0
    for p in pnl_series:
        if p < 0:
            current += 1
            max_consec = max(max_consec, current)
        else:
            current = 0

    avg_win = wins_df['pnl'].mean() if len(wins_df) > 0 else 0.0
    avg_loss = abs(losses_df['pnl'].mean()) if len(losses_df) > 0 else 0.0

    return {
        'win_rate': win_rate,
        'pnl_per_share': pnl_per_share,
        'profit_factor': profit_factor,
        'max_consec_loss': max_consec,
        'total_trades': total,
        'total_pnl': total_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
    }


def find_filtered_trades(baseline_exits: pd.DataFrame, pattern_exits: pd.DataFrame) -> pd.DataFrame:
    """Return baseline exits that have no matching pattern exit (same symbol within 120s)."""
    if baseline_exits.empty:
        return pd.DataFrame()
    if pattern_exits.empty:
        return baseline_exits.copy()

    pattern_lookup = list(zip(pattern_exits['symbol'], pattern_exits['timestamp']))
    filtered = []
    for _, row in baseline_exits.iterrows():
        matched = any(
            p_sym == row['symbol'] and abs(p_ts - row['timestamp']) <= 120
            for p_sym, p_ts in pattern_lookup
        )
        if not matched:
            filtered.append(row)
    return pd.DataFrame(filtered) if filtered else pd.DataFrame()


def compute_rolling_pnl_per_share(trades_df: pd.DataFrame, days: int = 7) -> pd.DataFrame:
    """Return daily PnL/share for the last N days."""
    if trades_df.empty:
        return pd.DataFrame()
    exits = trades_df[trades_df['side'].isin(['SELL', 'COVER'])].copy()
    if exits.empty:
        return pd.DataFrame()
    cutoff = (datetime.now() - timedelta(days=days)).date()
    exits = exits[exits['date'] >= cutoff]
    if exits.empty:
        return pd.DataFrame()
    daily = exits.groupby('date').apply(
        lambda g: pd.Series({
            'pnl': g['pnl'].sum(),
            'exit_shares': g['qty'].abs().sum()
        })
    ).reset_index()
    daily['pnl_per_share'] = daily.apply(
        lambda r: r['pnl'] / r['exit_shares'] if r['exit_shares'] > 0 else 0, axis=1
    )
    return daily[['date', 'pnl_per_share']]


# --- Load all data ---
baseline_all = load_trades(BASELINE_DB)
pattern_all = load_trades(PATTERN_DB)

today_start = datetime.now().replace(hour=0, minute=0, second=0).timestamp()

# --- HEADER ---
st.markdown("""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h2 style="margin:0;">FILTER EFFECTIVENESS
            <span class="baseline-badge">BASELINE</span>
            <span style="color:#94A3B8; font-size:1.2rem; margin: 0 8px;">vs</span>
            <span class="filter-badge">PATTERN</span>
        </h2>
        <div style="font-family: 'Roboto Mono', monospace; color: #94A3B8; font-size: 0.9rem;">
            Auto-refreshes every {interval}s
        </div>
    </div>
""".format(interval=REFRESH_INTERVAL), unsafe_allow_html=True)

# --- Time range selector ---
time_range = st.radio("Time Range", ["Today", "All Time"], horizontal=True, label_visibility="collapsed")

if time_range == "Today":
    baseline = baseline_all[baseline_all['timestamp'] >= today_start] if not baseline_all.empty else pd.DataFrame()
    pattern = pattern_all[pattern_all['timestamp'] >= today_start] if not pattern_all.empty else pd.DataFrame()
else:
    baseline = baseline_all.copy()
    pattern = pattern_all.copy()

ENTRY_SIDES = ['BUY', 'SHORT', 'SELL SHORT']
EXIT_SIDES = ['SELL', 'COVER']

baseline_exits = baseline[baseline['side'].isin(EXIT_SIDES)] if not baseline.empty else pd.DataFrame()
pattern_exits = pattern[pattern['side'].isin(EXIT_SIDES)] if not pattern.empty else pd.DataFrame()
baseline_entries = baseline[baseline['side'].isin(ENTRY_SIDES)] if not baseline.empty else pd.DataFrame()
pattern_entries = pattern[pattern['side'].isin(ENTRY_SIDES)] if not pattern.empty else pd.DataFrame()

b_stats = compute_stats(baseline_exits)
p_stats = compute_stats(pattern_exits)

# --- Derived metrics ---
b_entry_count = len(baseline_entries)
p_entry_count = len(pattern_entries)
reject_rate = (b_entry_count - p_entry_count) / b_entry_count * 100 if b_entry_count > 0 else 0.0

wr_lift = p_stats['win_rate'] - b_stats['win_rate']
pps_lift = p_stats['pnl_per_share'] - b_stats['pnl_per_share']

filtered_df = find_filtered_trades(baseline_exits, pattern_exits)
if not filtered_df.empty:
    filtered_total = len(filtered_df)
    filtered_losers = len(filtered_df[filtered_df['pnl'] <= 0])
    filtered_winners = len(filtered_df[filtered_df['pnl'] > 0])
    loss_prevention_rate = filtered_losers / filtered_total * 100
else:
    filtered_total = 0
    filtered_losers = 0
    filtered_winners = 0
    loss_prevention_rate = 0.0

# --- TOP KPI ROW ---
st.markdown('<div class="section-header">FILTER SUMMARY</div>', unsafe_allow_html=True)
k1, k2, k3, k4 = st.columns(4)

reject_color = "color-yellow" if reject_rate > 0 else "color-white"
with k1:
    st.markdown(f"""
        <div class="adv-metric">
            <div class="adv-metric-title">Filter Reject Rate</div>
            <div class="adv-metric-value {reject_color}">{reject_rate:.1f}%</div>
        </div>
    """, unsafe_allow_html=True)

wr_color = "color-green" if wr_lift > 0 else ("color-red" if wr_lift < 0 else "color-white")
with k2:
    sign = "+" if wr_lift >= 0 else ""
    st.markdown(f"""
        <div class="adv-metric">
            <div class="adv-metric-title">Win Rate Lift</div>
            <div class="adv-metric-value {wr_color}">{sign}{wr_lift:.1f}%</div>
        </div>
    """, unsafe_allow_html=True)

pps_color = "color-green" if pps_lift > 0 else ("color-red" if pps_lift < 0 else "color-white")
with k3:
    sign = "+" if pps_lift >= 0 else ""
    st.markdown(f"""
        <div class="adv-metric">
            <div class="adv-metric-title">PnL/Share Lift</div>
            <div class="adv-metric-value {pps_color}">{sign}${pps_lift:.4f}</div>
        </div>
    """, unsafe_allow_html=True)

lpr_color = "color-green" if loss_prevention_rate >= 50 else ("color-red" if loss_prevention_rate < 40 else "color-yellow")
with k4:
    st.markdown(f"""
        <div class="adv-metric">
            <div class="adv-metric-title">Loss Prevention Rate</div>
            <div class="adv-metric-value {lpr_color}">{loss_prevention_rate:.1f}%</div>
        </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- SIDE-BY-SIDE COMPARISON TABLE ---
st.markdown('<div class="section-header">SIDE-BY-SIDE COMPARISON</div>', unsafe_allow_html=True)

def fmt_pf(val):
    return "∞" if val == float('inf') else f"{val:.2f}"

comparison_rows = [
    {
        'Metric': 'Win Rate',
        'Baseline (Unfiltered)': f"{b_stats['win_rate']:.1f}%",
        'Pattern (Filtered)': f"{p_stats['win_rate']:.1f}%",
        'Delta': f"{'+' if wr_lift >= 0 else ''}{wr_lift:.1f}%",
        '_delta_val': wr_lift
    },
    {
        'Metric': 'PnL / Share',
        'Baseline (Unfiltered)': f"${b_stats['pnl_per_share']:.4f}",
        'Pattern (Filtered)': f"${p_stats['pnl_per_share']:.4f}",
        'Delta': f"{'+' if pps_lift >= 0 else ''}${pps_lift:.4f}",
        '_delta_val': pps_lift
    },
    {
        'Metric': 'Profit Factor',
        'Baseline (Unfiltered)': fmt_pf(b_stats['profit_factor']),
        'Pattern (Filtered)': fmt_pf(p_stats['profit_factor']),
        'Delta': f"{'+' if p_stats['profit_factor'] - b_stats['profit_factor'] >= 0 else ''}{fmt_pf(p_stats['profit_factor'] - b_stats['profit_factor']) if p_stats['profit_factor'] != float('inf') and b_stats['profit_factor'] != float('inf') else '—'}",
        '_delta_val': 0
    },
    {
        'Metric': 'Avg Win',
        'Baseline (Unfiltered)': f"${b_stats['avg_win']:.2f}",
        'Pattern (Filtered)': f"${p_stats['avg_win']:.2f}",
        'Delta': f"{'+' if p_stats['avg_win'] - b_stats['avg_win'] >= 0 else ''}${p_stats['avg_win'] - b_stats['avg_win']:.2f}",
        '_delta_val': p_stats['avg_win'] - b_stats['avg_win']
    },
    {
        'Metric': 'Avg Loss',
        'Baseline (Unfiltered)': f"${b_stats['avg_loss']:.2f}",
        'Pattern (Filtered)': f"${p_stats['avg_loss']:.2f}",
        'Delta': f"{'+' if p_stats['avg_loss'] - b_stats['avg_loss'] >= 0 else ''}${p_stats['avg_loss'] - b_stats['avg_loss']:.2f}",
        '_delta_val': -(p_stats['avg_loss'] - b_stats['avg_loss'])  # lower avg loss = better
    },
    {
        'Metric': 'Max Consec. Losses',
        'Baseline (Unfiltered)': str(b_stats['max_consec_loss']),
        'Pattern (Filtered)': str(p_stats['max_consec_loss']),
        'Delta': f"{'+' if p_stats['max_consec_loss'] - b_stats['max_consec_loss'] >= 0 else ''}{p_stats['max_consec_loss'] - b_stats['max_consec_loss']}",
        '_delta_val': -(p_stats['max_consec_loss'] - b_stats['max_consec_loss'])  # lower = better
    },
    {
        'Metric': 'Total Trades',
        'Baseline (Unfiltered)': str(b_stats['total_trades']),
        'Pattern (Filtered)': str(p_stats['total_trades']),
        'Delta': f"{'+' if p_stats['total_trades'] - b_stats['total_trades'] >= 0 else ''}{p_stats['total_trades'] - b_stats['total_trades']}",
        '_delta_val': 0
    },
    {
        'Metric': 'Total PnL',
        'Baseline (Unfiltered)': f"${b_stats['total_pnl']:,.2f}",
        'Pattern (Filtered)': f"${p_stats['total_pnl']:,.2f}",
        'Delta': f"{'+' if p_stats['total_pnl'] - b_stats['total_pnl'] >= 0 else ''}${p_stats['total_pnl'] - b_stats['total_pnl']:,.2f}",
        '_delta_val': p_stats['total_pnl'] - b_stats['total_pnl']
    },
]

df_comparison = pd.DataFrame(comparison_rows)[['Metric', 'Baseline (Unfiltered)', 'Pattern (Filtered)', 'Delta']]
st.dataframe(
    df_comparison,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Metric": st.column_config.TextColumn("Metric", width="medium"),
        "Baseline (Unfiltered)": st.column_config.TextColumn("Baseline (Unfiltered)", width="medium"),
        "Pattern (Filtered)": st.column_config.TextColumn("Pattern (Filtered)", width="medium"),
        "Delta": st.column_config.TextColumn("Delta", width="small"),
    }
)

st.markdown("<br>", unsafe_allow_html=True)

# --- ROLLING PNL/SHARE CHART (7-day) ---
chart_col, loss_col = st.columns([3, 2])

with chart_col:
    st.markdown('<div class="section-header">7-DAY ROLLING PNL/SHARE</div>', unsafe_allow_html=True)

    b_rolling = compute_rolling_pnl_per_share(baseline_all, days=7)
    p_rolling = compute_rolling_pnl_per_share(pattern_all, days=7)

    if not b_rolling.empty or not p_rolling.empty:
        fig = go.Figure()
        if not b_rolling.empty:
            fig.add_trace(go.Scatter(
                x=b_rolling['date'],
                y=b_rolling['pnl_per_share'],
                mode='lines+markers',
                name='Baseline',
                line=dict(color='#60A5FA', width=2),
                marker=dict(size=6),
                hovertemplate='%{x}<br>Baseline: $%{y:.4f}/share<extra></extra>'
            ))
        if not p_rolling.empty:
            fig.add_trace(go.Scatter(
                x=p_rolling['date'],
                y=p_rolling['pnl_per_share'],
                mode='lines+markers',
                name='Pattern',
                line=dict(color='#A855F7', width=2),
                marker=dict(size=6),
                hovertemplate='%{x}<br>Pattern: $%{y:.4f}/share<extra></extra>'
            ))
        fig.update_layout(
            template='plotly_dark',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            height=300,
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis=dict(showgrid=True, gridcolor='#1F2937'),
            yaxis=dict(showgrid=True, gridcolor='#1F2937', tickprefix='$'),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
            hovermode='x unified'
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    else:
        st.info("No trade history available for rolling chart.")

with loss_col:
    st.markdown('<div class="section-header">FILTERED TRADE OUTCOMES</div>', unsafe_allow_html=True)

    if not filtered_df.empty:
        st.markdown(f"""
            <p style="color: #94A3B8; font-size: 0.9rem; margin-bottom: 1rem;">
                Of <b style="color:#F8FAFC">{filtered_total}</b> trades the pattern filter blocked:
            </p>
        """, unsafe_allow_html=True)

        outcome_fig = go.Figure(data=[go.Pie(
            labels=['Would-be Losers', 'Would-be Winners'],
            values=[filtered_losers, filtered_winners],
            hole=0.65,
            marker_colors=['#00FF99', '#EF4444'],
            hoverinfo='label+value+percent',
            textinfo='none'
        )])
        outcome_fig.update_layout(
            template='plotly_dark',
            paper_bgcolor='rgba(0,0,0,0)',
            height=260,
            margin=dict(l=0, r=0, t=10, b=0),
            showlegend=True,
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5),
            annotations=[dict(
                text=f'{loss_prevention_rate:.0f}%<br><span style="font-size:0.6em">prevented</span>',
                x=0.5, y=0.5, font_size=28, showarrow=False, font_color='#F8FAFC',
                align='center'
            )]
        )
        st.plotly_chart(outcome_fig, use_container_width=True, config={'displayModeBar': False})

        st.markdown(f"""
            <div style="display:flex; gap:1rem; justify-content:center; font-family:'Roboto Mono',monospace; font-size:0.85rem;">
                <span style="color:#00FF99;">✓ {filtered_losers} losers blocked</span>
                <span style="color:#EF4444;">✗ {filtered_winners} winners missed</span>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.info("No filtered trade data available. Both baseline and pattern may be empty, or all baseline trades were also taken by the pattern filter.")

st.markdown("<br>", unsafe_allow_html=True)

# --- SYMBOL-LEVEL BREAKDOWN ---
st.markdown('<div class="section-header">SYMBOL-LEVEL BREAKDOWN</div>', unsafe_allow_html=True)

sym_col1, sym_col2 = st.columns(2)

def symbol_stats_table(exits_df: pd.DataFrame, label: str) -> pd.DataFrame:
    if exits_df.empty:
        return pd.DataFrame()
    rows = []
    for sym, grp in exits_df.groupby('symbol'):
        w = len(grp[grp['pnl'] > 0])
        t = len(grp)
        rows.append({
            'Symbol': sym,
            'Win %': round(w / t * 100, 1) if t > 0 else 0.0,
            'PnL': grp['pnl'].sum(),
            'Trades': t,
        })
    df = pd.DataFrame(rows).sort_values('PnL', ascending=False)
    df['PnL'] = df['PnL'].apply(lambda x: f"${x:,.2f}")
    df['Win %'] = df['Win %'].apply(lambda x: f"{x:.1f}%")
    return df

with sym_col1:
    st.markdown('<span class="baseline-badge" style="margin-left:0;">BASELINE</span>', unsafe_allow_html=True)
    df_b_sym = symbol_stats_table(baseline_exits, "Baseline")
    if not df_b_sym.empty:
        st.dataframe(df_b_sym, use_container_width=True, hide_index=True,
            column_config={
                "Symbol": st.column_config.TextColumn("Symbol"),
                "Win %": st.column_config.TextColumn("Win %"),
                "PnL": st.column_config.TextColumn("PnL"),
                "Trades": st.column_config.NumberColumn("Trades"),
            })
    else:
        st.info("No baseline trades yet.")

with sym_col2:
    st.markdown('<span class="filter-badge" style="margin-left:0;">PATTERN</span>', unsafe_allow_html=True)
    df_p_sym = symbol_stats_table(pattern_exits, "Pattern")
    if not df_p_sym.empty:
        st.dataframe(df_p_sym, use_container_width=True, hide_index=True,
            column_config={
                "Symbol": st.column_config.TextColumn("Symbol"),
                "Win %": st.column_config.TextColumn("Win %"),
                "PnL": st.column_config.TextColumn("PnL"),
                "Trades": st.column_config.NumberColumn("Trades"),
            })
    else:
        st.info("No pattern trades yet.")

# --- Auto Refresh ---
time.sleep(REFRESH_INTERVAL)
st.rerun()
