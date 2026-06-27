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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
