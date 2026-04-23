"""
Dollar Break Screener — Streamlit Dashboard

Reads from SQLite and renders:
  - Active alerts panel
  - Top watchlist table (sortable by score)
  - 30-min price chart for a selected symbol

Optionally runs the ingestion pipeline in a background thread for
single-process mode (set RUN_PIPELINE=1 in environment).

Run:  streamlit run app.py
"""

import os
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Add project root to path so imports work when launched from any CWD
sys.path.insert(0, str(Path(__file__).parent))

from db.database import init_db, get_recent_alerts, get_snapshots_since, get_universe
from transform.scorer import Scorer
from transform.tracker import Tracker
from transform.alerts import AlertEngine

REFRESH_SECONDS = 10

# ── Optional: embedded pipeline thread ───────────────────────────────────────

def _start_pipeline():
    """Start ingestion + scoring in background threads (single-process mode)."""
    from ingestion.universe import refresh_universe, start_background_refresh
    from ingestion.stream import PriceStream

    stream = PriceStream()
    t = threading.Thread(target=stream.run, daemon=True, name="pipeline")
    t.start()


# ── Shared scorer instance (Streamlit re-runs the script — use session state) ─

@st.cache_resource
def get_scorer():
    return Scorer()


@st.cache_resource
def get_tracker():
    return Tracker()


@st.cache_resource
def get_alert_engine():
    return AlertEngine()


# ── Dashboard ─────────────────────────────────────────────────────────────────

def render_alerts(alert_filter: str):
    alerts = get_recent_alerts(limit=20)
    if not alerts:
        st.info("No alerts yet. Waiting for market data…")
        return

    rows = []
    for a in alerts:
        if alert_filter != "Both" and a["alert_type"] != alert_filter:
            continue
        icon = "🔴" if a["alert_type"] == "BREAK" else "🟡"
        rows.append({
            "": icon,
            "Type": a["alert_type"],
            "Symbol": a["symbol"],
            "Price": f"${a['price']:.4f}",
            "Score": f"{a['score']:.0f}" if a["score"] else "—",
            "Time (UTC)": a["ts"][:19],
        })

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No alerts match the current filter.")


def render_watchlist(ranked: list[dict], min_score: float, min_price: float, max_price: float) -> str | None:
    filtered = [
        r for r in ranked
        if r["score"] >= min_score
        and min_price <= r["current_price"] <= max_price
    ]

    if not filtered:
        st.info("No stocks match the current filters.")
        return None

    rows = []
    for r in filtered[:50]:
        rows.append({
            "Symbol": r["symbol"],
            "Price": f"${r['current_price']:.4f}",
            "Distance": f"${r['distance_to_dollar']:.4f}",
            "Score": round(r["score"], 1),
            "Trend": r["trend_arrow"],
            "Vel (¢/min)": round(r["velocity"] * 100, 2),
        })

    df = pd.DataFrame(rows)
    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    selected = event.selection.get("rows", []) if event else []
    if selected:
        return filtered[selected[0]]["symbol"]
    return None


def render_chart(symbol: str):
    since = datetime.utcnow() - timedelta(minutes=30)
    snaps = get_snapshots_since(symbol, since)

    if not snaps:
        st.warning(f"No recent snapshot data for {symbol}.")
        return

    df = pd.DataFrame(snaps)
    df["ts"] = pd.to_datetime(df["ts"])

    # Get alert moments for this symbol
    all_alerts = get_recent_alerts(limit=200)
    break_times = [
        pd.to_datetime(a["ts"]) for a in all_alerts
        if a["symbol"] == symbol and a["alert_type"] == "BREAK"
    ]

    fig = go.Figure()

    # Price line
    fig.add_trace(go.Scatter(
        x=df["ts"], y=df["price"],
        mode="lines",
        name=symbol,
        line=dict(color="#00b4d8", width=2),
    ))

    # $1.00 reference line
    fig.add_hline(
        y=1.00,
        line_dash="dash",
        line_color="red",
        annotation_text="$1.00",
        annotation_position="top right",
    )

    # BREAK alert dots
    for bt in break_times:
        closest = df.iloc[(df["ts"] - bt).abs().argsort().iloc[0]]
        fig.add_trace(go.Scatter(
            x=[closest["ts"]],
            y=[closest["price"]],
            mode="markers",
            marker=dict(color="red", size=10, symbol="circle"),
            name="BREAK",
            showlegend=False,
        ))

    fig.update_layout(
        title=f"{symbol} — last 30 min",
        xaxis_title="Time (UTC)",
        yaxis_title="Price ($)",
        template="plotly_dark",
        height=350,
        margin=dict(l=40, r=20, t=40, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="Dollar Break Screener",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    init_db()

    # Optionally start pipeline in-process
    if os.environ.get("RUN_PIPELINE") == "1":
        if "pipeline_started" not in st.session_state:
            _start_pipeline()
            st.session_state.pipeline_started = True

    # ── Sidebar filters ───────────────────────────────────────────────────────
    with st.sidebar:
        st.header("Filters")
        price_range = st.slider("Price range ($)", 0.80, 1.50, (0.90, 1.15), step=0.01)
        min_score = st.slider("Min score", 0, 100, 50)
        alert_filter = st.radio("Alert type", ["Both", "APPROACHING", "BREAK"])
        st.markdown("---")
        st.caption("Auto-refresh every 10s")

    # ── Header ────────────────────────────────────────────────────────────────
    col_title, col_status = st.columns([4, 1])
    with col_title:
        st.title("Dollar Break Screener")
    with col_status:
        st.markdown("<br>", unsafe_allow_html=True)
        universe = get_universe()
        if universe:
            st.success(f"Live — {len(universe)} symbols")
        else:
            st.warning("No universe loaded")

    st.markdown("---")

    # ── Alerts panel ─────────────────────────────────────────────────────────
    st.subheader("Active Alerts")
    render_alerts(alert_filter)

    st.markdown("---")

    # ── Watchlist ─────────────────────────────────────────────────────────────
    st.subheader("Top Watchlist")

    scorer = get_scorer()
    ranked = scorer.get_last_ranked()

    selected_symbol = render_watchlist(
        ranked,
        min_score=min_score,
        min_price=price_range[0],
        max_price=price_range[1],
    )

    # ── Chart ─────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Price Chart (30 min)")

    # Persist selection across reruns
    if selected_symbol:
        st.session_state.selected_symbol = selected_symbol

    chart_symbol = st.session_state.get("selected_symbol")
    if chart_symbol:
        st.caption(f"Showing: **{chart_symbol}**  ·  click a row above to change")
        render_chart(chart_symbol)
    else:
        st.info("Click a symbol in the watchlist to view its chart.")

    # ── Auto-refresh ──────────────────────────────────────────────────────────
    time.sleep(REFRESH_SECONDS)
    st.rerun()


if __name__ == "__main__":
    main()
