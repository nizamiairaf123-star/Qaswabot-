"""Regression tests for the owner-approved canonical data-source policy.

Dhan is mandatory for all trading OHLCV/live/order data. yfinance is allowed
only for company-information enrichment (metadata, business/board inputs).
"""
# [AUDIT F7 FIX, 2026-09-16] Guarantees sandbox isolation even when this
# file is run standalone, not just pytest.
import conftest  # noqa: F401
import ast
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


class TestDataSourcePolicy(unittest.TestCase):
    def test_trading_modules_do_not_import_yfinance(self):
        trading_modules = [
            "backtester.py", "optimizer.py", "strategy.py", "strategy_tools.py",
            "simulate_engine.py", "trade_engine.py", "broker.py", "dhan_data.py",
            "dhan_live_feed.py", "liquidity_screen.py", "exit_engine.py",
            "risk_manager.py", "capital_manager.py",
        ]
        violations = []
        for name in trading_modules:
            tree = ast.parse(Path(name).read_text(encoding="utf-8"), filename=name)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    if any(alias.name == "yfinance" or alias.name.startswith("yfinance.") for alias in node.names):
                        violations.append(name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module and (node.module == "yfinance" or node.module.startswith("yfinance.")):
                        violations.append(name)
        self.assertEqual(violations, [], f"yfinance prohibited in trading path: {violations}")

    def test_backtest_optimizer_and_liquidity_use_dhan(self):
        required = {
            "backtester.py": "from dhan_data import fetch_daily_data",
            "optimizer.py": "from dhan_data import fetch_daily_data",
            "liquidity_screen.py": "from dhan_data import fetch_daily_data",
        }
        for name, marker in required.items():
            self.assertIn(marker, Path(name).read_text(encoding="utf-8"))

    def test_yfinance_is_confined_to_information_modules(self):
        allowed = {"board_manager.py", "board_filter_auto.py", "market_metadata.py"}
        actual = set()
        for path in Path(".").glob("*.py"):
            if "yfinance" in path.read_text(encoding="utf-8", errors="ignore"):
                # Comments/tests can mention the policy; imports are what matter.
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                imported = any(
                    (isinstance(n, ast.Import) and any(a.name.startswith("yfinance") for a in n.names))
                    or (isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("yfinance"))
                    for n in ast.walk(tree)
                )
                if imported:
                    actual.add(path.name)
        self.assertTrue(actual.issubset(allowed), f"unexpected yfinance importer(s): {actual-allowed}")

    def test_liquidity_refresh_bootstraps_while_selector_is_paused(self):
        import liquidity_screen
        candles = pd.DataFrame({"close": [100.0] * 63, "volume": [1_000_000] * 63})
        with tempfile.TemporaryDirectory() as td:
            universe = os.path.join(td, "candidate.csv")
            pd.DataFrame([{
                "symbol": "TEST", "exchange": "NSE", "market_cap": 1_000_000_000,
                "core_business_halal": True, "non_muslim_board": True,
            }]).to_csv(universe, index=False)
            state = os.path.join(td, "liquidity_state.json")
            with patch.object(liquidity_screen, "CUSTOM_UNIVERSE_FILE", universe), \
                 patch.object(liquidity_screen, "LIQUIDITY_STATE_FILE", state), \
                 patch("dhan_data.fetch_daily_data", return_value=candles):
                self.assertTrue(liquidity_screen.refresh_liquidity_data())
            result = pd.read_csv(universe)
            self.assertIn("turnover_liquid_ok", result.columns)
            self.assertTrue(bool(result.loc[0, "turnover_liquid_ok"]))


if __name__ == "__main__":
    unittest.main()
