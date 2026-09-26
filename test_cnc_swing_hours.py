"""
test_cnc_swing_hours.py — Owner CNC-swing freeze (2026-09-04)

Rules locked:
- ORDER_PRODUCT is CNC (never MIS)
- ENTRY = LIMIT, EXIT = MARKET
- Real BUY/SELL blocked when market is closed (Dhan AMO has no MARKET)
- Paper orders still simulate after hours (tests/sim)
- BE/T2T filter is a same-day-exit gate, not an MIS switch
"""
# [AUDIT F7 FIX, 2026-09-16] Guarantees sandbox isolation even when this
# file is run standalone (python3 test_cnc_swing_hours.py), not just pytest.
import conftest  # noqa: F401
import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


class TestCncSwingFreeze(unittest.TestCase):

    def test_product_and_order_types(self):
        from config import ORDER_PRODUCT, ENTRY_ORDER_TYPE, EXIT_ORDER_TYPE
        self.assertEqual(ORDER_PRODUCT, "CNC")
        self.assertEqual(ENTRY_ORDER_TYPE, "LMT")
        self.assertEqual(EXIT_ORDER_TYPE, "MKT")

    @patch("bot_state_manager.is_real_orders", return_value=True)
    @patch("utils.is_market_open", return_value=False)
    def test_real_market_exit_blocked_when_closed(self, *_):
        from broker import place_order
        r = place_order("1333", "RELIANCE", 1, order_type="MKT",
                        transaction_type="SELL")
        self.assertFalse(r["success"])
        self.assertEqual(r["rejection_type"], "MARKET_CLOSED")
        self.assertEqual(r["skip_reason"], "MARKET_CLOSED")
        self.assertIsNone(r["order_id"])

    @patch("bot_state_manager.is_real_orders", return_value=True)
    @patch("utils.is_market_open", return_value=False)
    def test_real_limit_buy_blocked_when_closed(self, *_):
        from broker import place_order
        r = place_order("1333", "RELIANCE", 1, order_type="LMT", price=100.0,
                        transaction_type="BUY")
        self.assertFalse(r["success"])
        self.assertEqual(r["rejection_type"], "MARKET_CLOSED")

    @patch("bot_state_manager.is_real_orders", return_value=False)
    @patch("utils.is_market_open", return_value=False)
    def test_paper_orders_still_simulate_after_hours(self, *_):
        from broker import place_order
        r = place_order("1333", "RELIANCE", 1, order_type="MKT",
                        transaction_type="SELL")
        self.assertTrue(r["success"])
        self.assertTrue(str(r["order_id"]).startswith("PAPER-"))

    def test_intraday_filter_is_exit_possibility_not_mis(self):
        import inspect
        import intraday_filter
        src = inspect.getsource(intraday_filter)
        self.assertIn("YE MIS / INTRADAY PRODUCT NAHI HAI", src)
        self.assertIn("is_intraday_allowed", src)

    def test_risk_gate_mentions_exit_ban_not_mis_mode(self):
        import inspect
        import risk_manager
        src = inspect.getsource(risk_manager.can_enter_trade)
        self.assertIn("is_intraday_allowed", src)
        self.assertIn("same-day CNC exit not possible", src)


if __name__ == "__main__":
    unittest.main()
