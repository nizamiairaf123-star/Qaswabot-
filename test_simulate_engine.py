"""
test_simulate_engine.py — Isolated acceptance and regression test for F003 /simulate.
"""

# [AUDIT F7 FIX, 2026-09-16] Writes real relative "data/" state via
# ensure_data_dir() with no tempfile override -- unsafe if ever run
# standalone. Guarantees sandbox isolation.
import conftest  # noqa: F401
import os
import json
import unittest
import sys

# Ensure project import path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from simulate_engine import run_simulation, run_monte_carlo, format_simulation_message, format_monte_carlo_message
from utils import save_json, ensure_data_dir
from config import BACKTEST_RESULTS_FILE

class TestSimulateEngine(unittest.TestCase):

    def setUp(self):
        # Create data dir and clean slate for test
        ensure_data_dir()
        # [SECTOR-MOCK] Sandbox me data/sector_strength.json nahi hota
        # (VPS pe 09:05 refresh bhar deta hai) — sector filter ki wajah se
        # valid_stocks empty ho jaata. Test-harness patch: STRONG sector.
        from unittest.mock import patch
        self._sector_patcher = patch(
            "sector_strength.get_sector_runtime_signal",
            return_value={"sector": "Energy", "strength_score": 2.0,
                          "threshold": 0.5, "raw_status": "STRONG",
                          "allow": True, "status": "STRONG"},
        )
        self._sector_patcher.start()
        self.addCleanup(self._sector_patcher.stop)
        # [WORKFLOW-MOCK] v4.1: simulation gate = decision_engine stage done
        # (sandbox me workflow_state.json nahi hota — VPS pe /optimize ke
        # baad ye stage auto-mark hota hai). Test real workflow state ko
        # chhue bina gate pass karta hai.
        self._wf_patcher = patch(
            "workflow_manager.can_run_simulation",
            return_value=(True, "OK"),
        )
        self._wf_patcher.start()
        self.addCleanup(self._wf_patcher.stop)
        self.mock_backtest_results = {
            "strategy_name": "Halal Test Strategy",
            "source": "backtest",
            "run_date": "2026-07-28T12:00:00+05:30",
            "analysis_window_days": 365,
            "portfolio_monte_carlo_dd_pct": 12.5,
            "summary": {
                "total_trades": 50,
                "win_rate_pct": 60.0,
                "avg_win_pct": 4.5,
                "avg_loss_pct": -2.0,
                "profit_factor": 2.25,
                "recovery_factor": 3.1,
                "sharpe": 1.8,
                "portfolio_max_dd_pct": 8.5,
                "max_single_day_loss_pct": 3.2
            },
            "stocks": {
                "RELIANCE": {
                    "symbol": "RELIANCE",
                    "valid": True,
                    "win_rate_pct": 60.0,
                    "avg_return_pct": 2.5,
                    "price_max_drawdown_pct": 5.0,
                    "recovery_factor": 2.5,
                    "sharpe": 1.5,
                    "total_trades": 25,
                    "trades_list": [
                        {"net_return_pct": 4.5},
                        {"net_return_pct": -2.0},
                        {"net_return_pct": 3.0}
                    ]
                },
                "TCS": {
                    "symbol": "TCS",
                    "valid": True,
                    "win_rate_pct": 58.0,
                    "avg_return_pct": 1.8,
                    "price_max_drawdown_pct": 4.2,
                    "recovery_factor": 1.9,
                    "sharpe": 1.2,
                    "total_trades": 25,
                    "trades_list": [
                        {"net_return_pct": 3.5},
                        {"net_return_pct": -1.5},
                        {"net_return_pct": 2.0}
                    ]
                }
            }
        }
        # Save mock data
        save_json(BACKTEST_RESULTS_FILE, self.mock_backtest_results)
        
        # Prepare mock sector strength data to allow RELIANCE (Energy) and TCS (Technology) to pass the sector filter
        self.mock_sector_strength = {
            "Energy": {
                "index": "NIFTY ENERGY",
                "change_pct": 1.5,
                "advances": 10,
                "declines": 2,
                "adv_dec_ratio": 5.0,
                "strength_score": 2.5,
                "status": "STRONG"
            },
            "Technology": {
                "index": "NIFTY IT",
                "change_pct": 2.0,
                "advances": 10,
                "declines": 1,
                "adv_dec_ratio": 10.0,
                "strength_score": 3.0,
                "status": "STRONG"
            },
            "updated_at": "2026-07-28T12:00:00+05:30"
        }
        save_json("data/sector_strength.json", self.mock_sector_strength)
        
        # Prepare workflow state with deployment approved
        self.mock_workflow_state = {
            "version": 1,
            "updated_at": "2026-07-28T12:00:00+05:30",
            "current_cycle_started_at": "2026-07-28T12:00:00+05:30",
            "stages": {
                "data_collection": {"completed_at": "2026-07-28T12:00:00+05:30", "details": {}},
                "feature_calculation": {"completed_at": "2026-07-28T12:00:00+05:30", "details": {}},
                "optimization": {"completed_at": "2026-07-28T12:00:00+05:30", "details": {}},
                "validation": {"completed_at": "2026-07-28T12:00:00+05:30", "details": {}},
                "decision_engine": {"completed_at": "2026-07-28T12:00:00+05:30", "details": {}},
                "deployment_approval": {"completed_at": "2026-07-28T12:00:00+05:30", "details": {}},
                "simulation": {"completed_at": None, "details": {}},
                "paper_trading": {"completed_at": None, "details": {}},
                "live_trading": {"completed_at": None, "details": {}},
                "performance_feedback": {"completed_at": None, "details": {}}
            }
        }
        save_json("data/workflow_state.json", self.mock_workflow_state)

    def tearDown(self):
        # Clean up files created during test
        for path in [BACKTEST_RESULTS_FILE, "data/workflow_state.json", "data/sim_backtest_gap.json", "data/sector_strength.json"]:
            if os.path.exists(path):
                os.remove(path)

    def test_run_simulation_success(self):
        # Admin simulation
        res_admin = run_simulation(200000.0, is_admin=True)
        self.assertNotIn("error", res_admin)
        self.assertEqual(res_admin["capital"], 200000.0)
        self.assertEqual(res_admin["stocks_in_simulation"], 2)
        self.assertEqual(res_admin["win_rate"], 60.0)
        self.assertEqual(res_admin["profit_factor"], 2.25)
        self.assertTrue(len(res_admin["per_stock_dd"]) > 0)

        # Subscriber simulation
        res_sub = run_simulation(150000.0, is_admin=False)
        self.assertNotIn("error", res_sub)
        self.assertEqual(res_sub["capital"], 150000.0)
        self.assertEqual(res_sub["per_stock_dd"], {}) # Subscriber does not see individual stock DD

    def test_format_simulation_message(self):
        res = run_simulation(100000.0, is_admin=False)
        msg = format_simulation_message(res, is_admin=False)
        self.assertIn("SIMULATION", msg)
        self.assertIn("PROFIT PROJECTION", msg)
        self.assertIn("RISK STATS", msg)
        self.assertNotIn("Individual Stock DD", msg)

        res_admin = run_simulation(100000.0, is_admin=True)
        msg_admin = format_simulation_message(res_admin, is_admin=True)
        self.assertIn("Individual Stock DD", msg_admin)

    def test_run_monte_carlo(self):
        # Generate 20 trade returns to satisfy the len(all_returns) >= 10 constraint
        self.mock_backtest_results["stocks"]["RELIANCE"]["trades_list"] = [{"net_return_pct": i} for i in range(-5, 15)]
        save_json(BACKTEST_RESULTS_FILE, self.mock_backtest_results)

        mc_res = run_monte_carlo(100000.0, n_simulations=100)
        self.assertNotIn("error", mc_res)
        self.assertEqual(mc_res["capital"], 100000.0)
        self.assertEqual(mc_res["n_simulations"], 100)
        self.assertTrue("worst_5pct" in mc_res)
        self.assertTrue("median" in mc_res)
        self.assertTrue("best_95pct" in mc_res)

        msg = format_monte_carlo_message(mc_res)
        self.assertIn("Monte Carlo Simulation", msg)
        self.assertIn("Worst Case", msg)
        self.assertIn("Median", msg)

if __name__ == "__main__":
    unittest.main()
