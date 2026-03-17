import unittest
import time
import os
from unittest.mock import MagicMock, patch

# Fake Env
os.environ["SCHWAB_API_KEY"] = "fake"
os.environ["SCHWAB_APP_SECRET"] = "fake"
os.environ["SCHWAB_REDIRECT_URI"] = "https://127.0.0.1"
os.environ["SCHWAB_TOKEN_PATH"] = "fake_tokens.json"

import grok
from live_trader import LiveTrader
from collections import deque

class TestRecentChanges(unittest.TestCase):

    def setUp(self):
        # Create a temp file for the DB so connections share state
        import tempfile
        self.db_fd, self.db_path = tempfile.mkstemp()
        os.close(self.db_fd) 
        
        # Patch DB_PATH 
        self.db_patcher = patch("live_trader.os.getenv", side_effect=lambda k, d=None: self.db_path if k == "DB_PATH" else os.environ.get(k, d))
        self.db_patcher.start()
        
        # MOCK GROK DB CONNECTION to avoid NameError
        grok.conn = MagicMock()
        
        # Reset Grok State Leakage
        grok.last_imbalance.clear()
        
        # Save original Grok constants
        self.orig_min_vol = grok.MIN_VOLUME
        self.orig_ask_heavy = grok.MIN_ASK_HEAVY
        self.orig_bid_heavy = grok.MIN_BID_HEAVY
        self.orig_duration = grok.MIN_IMBALANCE_DURATION_SEC
        
    def tearDown(self):
        self.db_patcher.stop()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        # Restore Grok constants
        grok.MIN_VOLUME = self.orig_min_vol
        grok.MIN_ASK_HEAVY = self.orig_ask_heavy
        grok.MIN_BID_HEAVY = self.orig_bid_heavy
        grok.MIN_IMBALANCE_DURATION_SEC = self.orig_duration

    # ------------------------------------------------------------------
    # 1. Position-Aware Fast Exit (Grok)
    # ------------------------------------------------------------------
    @patch("grok.time")
    def test_grok_fast_exit(self, mock_time):
        print("\n[TEST] Grok Position-Aware Fast Exit")
        # Reset Grok State
        grok.SYMBOLS = ["TEST"]
        grok.last_alert = {}
        grok.traders = []
        grok.trades.clear() # Clear deque
        grok.trades["TEST"] = deque()
        
        # Relax thresholds for test
        grok.MIN_VOLUME = 0
        grok.MIN_ASK_HEAVY = 0
        grok.MIN_BID_HEAVY = 0
        grok.MIN_IMBALANCE_DURATION_SEC = 2.0 
        
        # Mock Trader with Position
        mock_trader = MagicMock()
        mock_trader.positions = {"TEST": 100} # LONG
        grok.traders.append(("mock", mock_trader))
        
        # Mock BookMetrics
        ask_metrics = grok.BookMetrics(
            symbol="TEST", total_bids=10, total_asks=100, 
            ask_to_bid_ratio=10.0, bid_to_ask_ratio=0.1,
            ask_heavy_venues=5, bid_heavy_venues=0, 
            per_venue={}, valid_exchanges=5
        )
        
        with patch("grok.process_book", return_value=ask_metrics):
                # T=0
                mock_time.return_value = 1000.0
                grok.on_book({"content": [{"key": "TEST"}]})
                
                # T=2 (Should Trigger Fast Exit)
                mock_time.return_value = 1002.0
                grok.on_book({"content": [{"key": "TEST"}]})
                
                self.assertIn("TEST", grok.last_alert, "Should trigger fast exit at 2s for LONG position")
                self.assertEqual(grok.last_alert["TEST"], 1002.0)
                print("   -> Fast Exit Verified")

    @patch("grok.time")
    def test_grok_standard_entry(self, mock_time):
        print("\n[TEST] Grok Standard Entry (Flat)")
        # Reset Grok State
        grok.SYMBOLS = ["TEST"]
        grok.last_alert = {}
        grok.traders = []
        grok.trades.clear()
        grok.trades["TEST"] = deque()
        
        # Relax thresholds but Keep Duration DEFAULT (10s)
        grok.MIN_VOLUME = 0
        grok.MIN_ASK_HEAVY = 0
        grok.MIN_BID_HEAVY = 0
        grok.MIN_IMBALANCE_DURATION_SEC = 10.0 # FORCE SET TO 10.0
        print(f"DEBUG: Standard Entry Duration Threshold: {grok.MIN_IMBALANCE_DURATION_SEC}")
        
        # Mock Trader with NO Position
        mock_trader = MagicMock()
        mock_trader.positions = {"TEST": 0} # FLAT
        grok.traders.append(("mock", mock_trader))
        
        # Mock BookMetrics (Ask Heavy = Entry Signal)
        ask_metrics = grok.BookMetrics(
            symbol="TEST", total_bids=10, total_asks=100, 
            ask_to_bid_ratio=10.0, bid_to_ask_ratio=0.1,
            ask_heavy_venues=5, bid_heavy_venues=0, 
            per_venue={}, valid_exchanges=5
        )
        
        with patch("grok.process_book", return_value=ask_metrics):
                 # T=0
                 mock_time.return_value = 2000.0
                 grok.on_book({"content": [{"key": "TEST"}]})
                 
                 # T=2 (Should NOT Trigger)
                 mock_time.return_value = 2002.0
                 grok.on_book({"content": [{"key": "TEST"}]})
                 self.assertNotIn("TEST", grok.last_alert, "Should NOT trigger fast entry when FLAT")
                 
                 # T=10 (Should Trigger)
                 mock_time.return_value = 2010.0
                 grok.on_book({"content": [{"key": "TEST"}]})
                 self.assertIn("TEST", grok.last_alert, "Should trigger standard entry at 10s")
                 print("   -> Standard Entry Verified")

    # ------------------------------------------------------------------
    # 2. Penalty Box (message "lockout behavior")
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # 2. Penalty Box (Cumulative Loss Logic)
    # ------------------------------------------------------------------
    @patch("live_trader.SchwabOrderExecutor")
    def test_penalty_box_logic(self, MockExecutor):
        print("\n[TEST] Penalty Box & Lockout logic")
        trader = LiveTrader(dry_run=True, executor=MockExecutor.return_value)
        trader._init_db_schema() 
        trader.live_symbols = {"TEST"}
        
        # Scenario 1: Cumulative Loss Trigger (Two small losses)
        # Trade 1: Lose $0.01
        trader.positions["TEST"] = 100
        trader.position_entry_prices["TEST"] = 100.00 
        trader._record_fill(symbol="TEST", side="SELL", qty=100, price=99.99) # Loss $0.01
        self.assertLess(trader.loss_cooldown_until.get("TEST", 0.0), time.time(), "Should NOT be locked out yet (Loss $0.01)")
        self.assertAlmostEqual(trader.consecutive_loss_cents.get("TEST", 0.0), 0.01)

        # Trade 2: Lose another $0.01 (Total $0.02)
        trader.positions["TEST"] = 100
        trader.position_entry_prices["TEST"] = 100.00
        trader._record_fill(symbol="TEST", side="SELL", qty=100, price=99.99) # Loss $0.01

        self.assertGreater(trader.loss_cooldown_until.get("TEST", 0.0), time.time(), "Penalty box should be active (Total Loss $0.02)")
        self.assertEqual(trader.consecutive_loss_cents.get("TEST", 0.0), 0.0, "Bucket should reset after trigger")
        
        # 2. Verify Lockout for NEW ENTRY (Position=0)
        trader.positions["TEST"] = 0
        with patch.object(trader, "_submit_order") as mock_submit:
            trader._handle_alert(1, "TEST", "ask-heavy", 100.0)
            mock_submit.assert_not_called()
            print("   -> New Entry BLOCKED during penalty")
            
        # 3. Verify ALLOWED Exit (Position!=0)
        trader.positions["TEST"] = 100
        with patch.object(trader, "_submit_order") as mock_submit:
            trader._handle_alert(2, "TEST", "ask-heavy", 100.0)
            mock_submit.assert_called()
            print("   -> Exit ALLOWED during penalty")

    # ------------------------------------------------------------------
    # 3. Shutdown Logic (Boxed Position Fix)
    # ------------------------------------------------------------------
    @patch("live_trader.SchwabOrderExecutor")
    def test_shutdown_sequence(self, MockExecutor):
        print("\n[TEST] Shutdown Sequence")
        executor = MockExecutor.return_value
        executor.dry_run = False 
        executor.get_quote.return_value = 100.0 
        executor.submit_market.return_value = {"order_id": 123, "status_code": 200} # Mock return dict
        
        # MUST set dry_run=False so _reconcile calls fetch_positions
        trader = LiveTrader(dry_run=False, executor=executor)
        trader._init_db_schema()
        
        # Setup: Local says 0, Schwab says 100 (Simulate Desync)
        trader.positions = {"TEST": 0} 
        executor.fetch_positions.return_value = {"TEST": 100}
        
        # Mock time.sleep to run fast
        with patch("time.sleep"):
             with self.assertRaises(SystemExit):
                 trader._engage_emergency_shutdown("UnitTest")
            
        # Verify Sequence
        # 1. Cancel All
        executor.cancel_all_orders.assert_called()
        
        # 2. Reconcile (Fetch positions)
        executor.fetch_positions.assert_called()
        # Position should be 0 because we FLATTENED it
        self.assertEqual(trader.positions.get("TEST", 0), 0, "Should have flattened position")
        
        # 3. Flatten
        self.assertTrue(getattr(executor, 'submit_market').called or getattr(executor, 'place_order').called)
        # Verify we sold 100 shares
        executor.submit_market.assert_called_with(
             symbol="TEST", side="SELL", qty=100
        )
        print("   -> Shutdown Sequence Verified (Cancel -> Reconcile -> Flatten)")

if __name__ == "__main__":
    unittest.main()
