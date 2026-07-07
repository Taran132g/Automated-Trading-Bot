"""Offline validation of the PaperTrader maker (passive-limit) fill model.

Runs without Schwab/market data: drives process_alert() with synthetic
alert sequences and asserts the resting-limit fills/misses/crosses correctly.
"""
import os
import sys
import time
import sqlite3
import tempfile
import importlib

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def _fresh_trader(tmpdir, half_spread_cents=1.0, window=30.0):
    """Build a PaperTrader wired to a throwaway DB with maker mode on."""
    db = os.path.join(tmpdir, "t.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE alerts (rowid INTEGER PRIMARY KEY, symbol TEXT, "
                 "direction TEXT, price REAL, timestamp REAL)")
    conn.commit()
    conn.close()

    import config_manager
    config_manager.load_config = lambda *a, **k: {
        "paper_position_size": 100,
        "maker_enabled": True,
        "maker_half_spread_cents": half_spread_cents,
        "maker_fill_window_sec": window,
    }
    import paper_trader
    importlib.reload(paper_trader)
    return paper_trader.PaperTrader(
        db_path=db, state_file=os.path.join(tmpdir, "s.json"))


def _trades(pt):
    with sqlite3.connect(pt.db_path) as c:
        return c.execute("SELECT side, qty, price, pnl FROM paper_trades "
                         "ORDER BY id").fetchall()


def test_short_entry_fills_only_when_price_trades_up_to_offer():
    with tempfile.TemporaryDirectory() as d:
        pt = _fresh_trader(d)
        # ask-heavy at mid 10.00 -> rest SHORT at offer 10.01
        pt.process_alert(1, "AAL", "ask-heavy", 10.00)
        assert "AAL" in pt.pending
        assert pt.pending["AAL"]["limit"] == pytest.approx(10.01)
        # price ticks up through the offer -> filled at the limit (we sold high)
        pt.process_alert(2, "AAL", "ask-heavy", 10.02)
        assert "AAL" not in pt.pending
        assert pt.positions["AAL"]["qty"] == -100
        assert pt.positions["AAL"]["entry_price"] == pytest.approx(10.01)


def test_short_entry_missed_when_price_runs_away_then_expires():
    with tempfile.TemporaryDirectory() as d:
        pt = _fresh_trader(d, window=5.0)
        pt._register_pending("AAL", "SHORT", 100, 10.00, is_exit=False)  # limit 10.01
        dl = pt.pending["AAL"]["deadline"]
        # price falls (the move we wanted) but never reaches our offer -> still resting
        pt._check_pending("AAL", 9.90, now=dl - 1)
        assert "AAL" in pt.pending
        # deadline passes, still below offer -> entry MISSED, no trade
        pt._check_pending("AAL", 9.85, now=dl + 1)
        assert "AAL" not in pt.pending
        assert "AAL" not in pt.positions
        assert _trades(pt) == []


def test_short_exit_crosses_spread_on_timeout():
    with tempfile.TemporaryDirectory() as d:
        pt = _fresh_trader(d)
        # establish a short: rest SHORT @ 10.01, price ticks up -> filled
        pt._register_pending("AAL", "SHORT", 100, 10.00, is_exit=False)
        pt._check_pending("AAL", 10.02)
        assert pt.positions["AAL"]["qty"] == -100
        # rest a passive COVER at the bid 9.49 (mid 9.50)
        pt._register_pending("AAL", "COVER", 100, 9.50, is_exit=True)
        dl = pt.pending["AAL"]["deadline"]
        # price never drops to 9.49; deadline passes -> cross up to cover (9.60 + h)
        pt._check_pending("AAL", 9.60, now=dl + 1)
        assert "AAL" not in pt.positions  # flat again
        rows = _trades(pt)
        assert [r[0] for r in rows] == ["SHORT", "COVER"]
        # realized PnL on the short: sold 10.01, covered ~9.61 -> profit ~ $40
        assert rows[-1][3] > 0


def test_expired_entry_does_not_fill_against_stale_price():
    """Fix #2: a resting entry whose window lapsed must MISS, never fill —
    even if the next observed price would have crossed it. Guards against
    filling against a quote that arrived minutes/hours after the deadline."""
    with tempfile.TemporaryDirectory() as d:
        pt = _fresh_trader(d, window=5.0)
        pt._register_pending("AAL", "SHORT", 100, 10.00, is_exit=False)  # limit 10.01
        dl = pt.pending["AAL"]["deadline"]
        # Deadline has passed AND the price now crosses the offer (10.02 >=
        # 10.01). Old code filled here; correct behavior is a MISS.
        pt._check_pending("AAL", 10.02, now=dl + 1)
        assert "AAL" not in pt.pending
        assert "AAL" not in pt.positions
        assert _trades(pt) == []
        with sqlite3.connect(pt.db_path) as c:
            n_miss = c.execute("SELECT COUNT(*) FROM paper_misses").fetchone()[0]
        assert n_miss == 1


def test_live_order_fills_at_expiry_boundary_still_works():
    """A cross that happens WHILE the order is live (now < deadline) still
    fills passively at the limit — the reorder must not break the happy path."""
    with tempfile.TemporaryDirectory() as d:
        pt = _fresh_trader(d, window=5.0)
        pt._register_pending("AAL", "SHORT", 100, 10.00, is_exit=False)  # limit 10.01
        dl = pt.pending["AAL"]["deadline"]
        pt._check_pending("AAL", 10.02, now=dl - 1)  # still live, crosses
        assert pt.positions["AAL"]["qty"] == -100
        assert pt.positions["AAL"]["entry_price"] == pytest.approx(10.01)


def test_injected_clock_drives_deadline_and_trade_timestamp():
    """Fix (replay support): with _now_override set, deadlines and logged
    trade timestamps use the sim clock, not wall time."""
    with tempfile.TemporaryDirectory() as d:
        pt = _fresh_trader(d, window=30.0)
        base = 1_000_000.0  # arbitrary sim epoch
        pt._now_override = base
        pt._register_pending("AAL", "SHORT", 100, 10.00, is_exit=False)
        assert pt.pending["AAL"]["deadline"] == pytest.approx(base + 30.0)
        # advance sim clock, cross the offer -> fill, trade stamped at sim time
        pt._now_override = base + 10.0
        pt._check_pending("AAL", 10.02)
        rows = pt._open_conn().execute(
            "SELECT timestamp FROM paper_trades ORDER BY id DESC LIMIT 1").fetchone()
        assert rows[0] == pytest.approx(base + 10.0)


def test_real_touch_rest_price_is_used_verbatim():
    """Fix #4: when grok forwards target_limit_price, the order rests exactly
    there instead of rebuilding the touch from mid +/- half_spread."""
    with tempfile.TemporaryDirectory() as d:
        pt = _fresh_trader(d)
        # mid 10.00 would give 10.01; real offer is 10.05 -> rest at 10.05
        pt.process_alert(1, "AAL", "ask-heavy", 10.00, target_limit_price=10.05)
        assert pt.pending["AAL"]["limit"] == pytest.approx(10.05)


def test_zero_touch_falls_back_to_half_spread():
    """A bogus 0.0 touch (grok's empty-book default) must be ignored."""
    with tempfile.TemporaryDirectory() as d:
        pt = _fresh_trader(d)
        pt.process_alert(1, "AAL", "ask-heavy", 10.00, target_limit_price=0.0)
        assert pt.pending["AAL"]["limit"] == pytest.approx(10.01)


def test_maker_cash_reconciles_with_realized_pnl():
    """Fix #5: in maker mode there is no slippage, so the cash delta over a
    round-trip must equal the realized PnL (the two books can reconcile)."""
    import paper_trader
    with tempfile.TemporaryDirectory() as d:
        pt = _fresh_trader(d)
        start_cash = pt.cash
        # short fill @ 10.01
        pt._register_pending("AAL", "SHORT", 100, 10.00, is_exit=False)
        pt._check_pending("AAL", 10.02)
        # cover fill @ 9.49 (price trades down through the bid)
        pt._register_pending("AAL", "COVER", 100, 9.50, is_exit=True)
        pt._check_pending("AAL", 9.48)
        realized = sum(r[3] for r in _trades(pt))
        assert pt.cash - start_cash == pytest.approx(realized)
        assert realized == pytest.approx((10.01 - 9.49) * 100)


def test_state_roundtrip_persists_positions_and_cash():
    """Fix #1: positions AND cash survive a save/reload so a restart with an
    open position doesn't strand its cash movement as a phantom drawdown."""
    import importlib, paper_trader
    with tempfile.TemporaryDirectory() as d:
        pt = _fresh_trader(d)
        pt._register_pending("AAL", "SHORT", 100, 10.00, is_exit=False)
        pt._check_pending("AAL", 10.02)  # now short 100
        cash_before = pt.cash
        pt.save_state()
        # New trader on the same state file resumes the position + cash.
        importlib.reload(paper_trader)
        pt2 = paper_trader.PaperTrader(db_path=pt.db_path, state_file=pt.state_file)
        assert pt2.cash == pytest.approx(cash_before)
        assert pt2.positions.get("AAL", {}).get("qty") == -100


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


def test_drift_60s_stamped_on_trade_and_miss():
    with tempfile.TemporaryDirectory() as d:
        pt = _fresh_trader(d, window=5.0)
        # entry with drift tag -> fills -> exit; drift lands on the trade rows
        pt.process_alert(1, "AAL", "ask-heavy", 10.00, ratio=4.0,
                         imbalance_duration=12.0, heavy_venues=5, drift_60s=0.03)
        pt.process_alert(2, "AAL", "ask-heavy", 10.02)   # trades through offer
        assert pt.positions["AAL"]["qty"] == -100
        with sqlite3.connect(pt.db_path) as c:
            drift = c.execute(
                "SELECT drift_60s FROM paper_trades WHERE side='SHORT'"
            ).fetchone()[0]
        assert drift == pytest.approx(0.03)

        # entry that misses -> drift lands on the miss row
        d2 = os.path.join(d, "second")
        os.makedirs(d2)
        pt2 = _fresh_trader(d2, window=5.0)
        pt2._register_pending("F", "BUY", 100, 10.00, is_exit=False,
                              conviction={"drift_60s": -0.02})
        dl = pt2.pending["F"]["deadline"]
        pt2._check_pending("F", 10.50, now=dl + 1)   # ran away -> miss
        with sqlite3.connect(pt2.db_path) as c:
            drift = c.execute("SELECT drift_60s FROM paper_misses").fetchone()[0]
        assert drift == pytest.approx(-0.02)
