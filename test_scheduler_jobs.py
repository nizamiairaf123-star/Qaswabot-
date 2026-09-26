"""
test_scheduler_jobs.py — Isolated acceptance and regression test for:
- F061 (Subscription Expiry Job)
- F066 (Auto Stage Check Job)
"""

# [AUDIT F7 FIX, 2026-09-16] This file writes real relative "data/" state
# (subscribers, stage flags) via ensure_data_dir() with no tempfile
# override -- unsafe if ever run standalone. Guarantees sandbox isolation.
import conftest  # noqa: F401
import os
import json
import unittest
import sys
from datetime import timedelta

# Ensure project import path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from subscriber_manager import auto_expire_subscriptions
from capital_manager import check_and_update_stage
from utils import save_json, load_json, ensure_data_dir, today_ist
from config import SUBSCRIBERS_FILE, TRADES_FILE

class TestSchedulerJobs(unittest.TestCase):

    def setUp(self):
        ensure_data_dir()
        
        # Setup subscribers state
        self.mock_subscribers = {
            "version": 1,
            "subscribers": {
                "111111111": {
                    "chat_id": 111111111,
                    "name": "Active User",
                    "status": "LIVE_ACTIVE",
                    "live_expiry": (today_ist() + timedelta(days=5)).isoformat(), # Not expired
                    "dhan_linked": True
                },
                "222222222": {
                    "chat_id": 222222222,
                    "name": "Expiring Soon User",
                    "status": "LIVE_ACTIVE",
                    "live_expiry": (today_ist() + timedelta(days=2)).isoformat(), # Within warning window (T-3)
                    "dhan_linked": True
                },
                "333333333": {
                    "chat_id": 333333333,
                    "name": "Expired User (1 din — GRACE)",
                    "status": "LIVE_ACTIVE",
                    "live_expiry": (today_ist() - timedelta(days=1)).isoformat(), # v5.0: GRACE window me
                    "dhan_linked": True
                },
                "555555555": {
                    "chat_id": 555555555,
                    "name": "Expired User (4 din — full expire)",
                    "status": "LIVE_ACTIVE",
                    "live_expiry": (today_ist() - timedelta(days=4)).isoformat(), # v5.0: GRACE (2) khatam
                    "dhan_linked": True
                },
                "444444444": {
                    "chat_id": 444444444,
                    "name": "Paper Trial User",
                    "status": "PAPER_TRIAL",
                    "trial_expiry": (today_ist() - timedelta(days=1)).isoformat(),
                    "dhan_linked": False
                }
            }
        }
        save_json(SUBSCRIBERS_FILE, self.mock_subscribers)

        # Setup mock trades
        self.mock_trades = {
            "trades": [
                {"trade_id": "T1", "symbol": "RELIANCE", "status": "CLOSED", "pnl": 500.0},
                {"trade_id": "T2", "symbol": "RELIANCE", "status": "CLOSED", "pnl": 300.0},
                {"trade_id": "T3", "symbol": "RELIANCE", "status": "CLOSED", "pnl": -100.0},
                {"trade_id": "T4", "symbol": "RELIANCE", "status": "CLOSED", "pnl": 400.0},
                {"trade_id": "T5", "symbol": "RELIANCE", "status": "CLOSED", "pnl": 600.0},
                {"trade_id": "T6", "symbol": "RELIANCE", "status": "CLOSED", "pnl": -200.0},
                {"trade_id": "T7", "symbol": "RELIANCE", "status": "CLOSED", "pnl": 700.0},
                {"trade_id": "T8", "symbol": "RELIANCE", "status": "CLOSED", "pnl": 500.0},
                {"trade_id": "T9", "symbol": "RELIANCE", "status": "CLOSED", "pnl": -100.0},
                {"trade_id": "T10", "symbol": "RELIANCE", "status": "CLOSED", "pnl": 800.0}, # Last 10 trades have 7 wins -> 70% win rate
            ]
        }
        save_json(TRADES_FILE, self.mock_trades)

        # Setup initial portfolio/user stage
        self.mock_portfolio_state = {
            "admin": {
                "stage": 2
            },
            "111111111": {
                "stage": 2
            },
            "222222222": {
                "stage": 2
            }
        }
        save_json("data/staged_state.json", self.mock_portfolio_state)

    def tearDown(self):
        for path in [SUBSCRIBERS_FILE, TRADES_FILE, "data/staged_state.json"]:
            if os.path.exists(path):
                os.remove(path)

    def test_auto_expire_subscriptions(self):
        # Run expiry job
        auto_expire_subscriptions()

        # Reload updated subscriber data
        updated_data = load_json(SUBSCRIBERS_FILE)
        subs = updated_data["subscribers"]

        # 111111111 should remain LIVE_ACTIVE
        self.assertEqual(subs["111111111"]["status"], "LIVE_ACTIVE")

        # 222222222 should remain LIVE_ACTIVE (it is just expiring soon, which sends reminder)
        self.assertEqual(subs["222222222"]["status"], "LIVE_ACTIVE")

        # v5.0: 333333333 (1 din overdue) → GRACE (entry band, exit chalu)
        self.assertEqual(subs["333333333"]["status"], "GRACE")

        # v5.0: 555555555 (4 din overdue, grace 2 khatam) → EXPIRED_EXIT_ONLY
        self.assertEqual(subs["555555555"]["status"], "EXPIRED_EXIT_ONLY")

        # 444444444 (PAPER_TRIAL) should remain PAPER_TRIAL (expiry job only handles LIVE_ACTIVE)
        self.assertEqual(subs["444444444"]["status"], "PAPER_TRIAL")

    def test_check_and_update_stage_up(self):
        # Initial stage of 111111111 is 2
        check_and_update_stage("111111111")

        # Win rate is 70% (>= 55% threshold). Stage should upgrade from 2 to 3.
        updated_state = load_json("data/staged_state.json")
        self.assertEqual(updated_state["111111111"]["stage"], 3)

    def test_check_and_update_stage_down(self):
        # Override mock trades to simulate high loss rate (e.g. 8 losses, 2 wins -> 20% win rate)
        self.mock_trades["trades"] = [
            {"trade_id": f"T{i}", "symbol": "RELIANCE", "status": "CLOSED", "pnl": -100.0 if i > 2 else 100.0}
            for i in range(1, 11)
        ]
        save_json(TRADES_FILE, self.mock_trades)

        # Run check
        check_and_update_stage("111111111")

        # Win rate is 20% (<= 40% threshold). Stage should demote from 2 to 1.
        updated_state = load_json("data/staged_state.json")
        self.assertEqual(updated_state["111111111"]["stage"], 1)

if __name__ == "__main__":
    unittest.main()
