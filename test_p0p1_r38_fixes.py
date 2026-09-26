"""
test_p0p1_r38_fixes.py — Regression tests for the r38 P0/P1 verified-fix pass.

Covers, one test-class per finding:
  P0-001  broker.place_order()            — missing/invalid order_id -> success=False
  P0-002  broker.place_forever_order()    — missing/invalid forever_id -> success=False
  P0-003  trade_engine.enter_position()   — GTT failure blocks broadcast/copy-trade,
                                             triggers RECONCILIATION_HOLD
  P1-001  backtester (parity)             — parity exception -> valid=False, no silent fallback
  P1-002  scheduler_jobs_daily_ops        — GTT re-arm failure escalates via RECONCILIATION_HOLD
  P1-004  signal_broadcaster.alert_admin_sync — non-2xx HTTP treated as failure

Uses stdlib unittest + unittest.mock only (no pytest/telegram/apscheduler
dependency) so it can run in an environment without those packages
installed, same constraint the sandbox that produced these fixes had.
Every test creates its own isolated temp working directory (copied from
this file's own directory) and chdir's into it, so nothing here writes to
the real data/ folder that ships in the release tree.
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


class IsolatedProjectTestCase(unittest.TestCase):
    """Copies the project into a temp dir and chdir's there so tests never
    touch the real shipped data/ files. Mirrors the isolation conftest.py
    already does for the pytest suite, but implemented without a pytest
    dependency."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="qaswa_p0p1_test_")
        for name in os.listdir(PROJECT_ROOT):
            if name in ("__pycache__", ".git"):
                continue
            src = os.path.join(PROJECT_ROOT, name)
            dst = os.path.join(cls._tmpdir, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(src, dst)
        cls._orig_cwd = os.getcwd()
        cls._orig_sys_path = list(sys.path)
        os.chdir(cls._tmpdir)
        sys.path.insert(0, cls._tmpdir)
        # Ensure a clean import of project modules from the temp copy, not
        # any already-imported copy from elsewhere on sys.path.
        for mod in list(sys.modules):
            if mod in ("broker", "trade_engine", "backtester",
                       "scheduler_jobs_daily_ops", "signal_broadcaster",
                       "startup_recovery", "bot_state_manager", "config",
                       "utils", "forever_order_manager"):
                del sys.modules[mod]

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._orig_cwd)
        sys.path[:] = cls._orig_sys_path
        shutil.rmtree(cls._tmpdir, ignore_errors=True)
        # r39 PILLAR 1 — HERMETIC CLEANUP: Remove temp modules so subsequent
        # tests (e.g. test_telemetry) don't see a split-brain with two config
        # modules (original vs deleted temp). This does NOT weaken any of the
        # 19 P0/P1 fixes — it only ensures isolation after the test class.
        for mod in list(sys.modules):
            if mod in ("broker", "trade_engine", "backtester",
                       "scheduler_jobs_daily_ops", "signal_broadcaster",
                       "startup_recovery", "bot_state_manager", "config",
                       "utils", "forever_order_manager", "database",
                       "telemetry", "dhan_client", "dhan_data"):
                try:
                    # If module's file is inside the deleted tmpdir, it's stale
                    f = getattr(sys.modules[mod], "__file__", "") or ""
                    if cls._tmpdir in f or "qaswa_p0p1_test_" in f:
                        del sys.modules[mod]
                except Exception:
                    try:
                        del sys.modules[mod]
                    except KeyError:
                        pass
        # Also clean any module whose file no longer exists and looks like p0p1 temp
        for name, mod in list(sys.modules.items()):
            try:
                f = getattr(mod, "__file__", "") or ""
                if "qaswa_p0p1_test_" in f and not os.path.exists(f):
                    del sys.modules[name]
            except Exception:
                pass


class TestP0_001_OrderIdValidation(IsolatedProjectTestCase):
    def test_missing_order_id_is_not_success(self):
        import broker
        with patch("bot_state_manager.is_real_orders", return_value=True), \
             patch.object(broker, "_live_order_session_gate", return_value=None), \
             patch.object(broker, "get_dhan", return_value=MagicMock()), \
             patch.object(broker, "call_dhan_with_timeout", return_value={"someOtherField": "x"}):
            result = broker.place_order("SECID1", "TESTSTOCK", 10)
        self.assertFalse(result["success"], "missing order_id must NOT be success=True")
        self.assertIsNone(result["order_id"])

    def test_empty_string_order_id_is_not_success(self):
        import broker
        with patch("bot_state_manager.is_real_orders", return_value=True), \
             patch.object(broker, "_live_order_session_gate", return_value=None), \
             patch.object(broker, "get_dhan", return_value=MagicMock()), \
             patch.object(broker, "call_dhan_with_timeout", return_value={"orderId": "   "}):
            result = broker.place_order("SECID1", "TESTSTOCK", 10)
        self.assertFalse(result["success"])

    def test_valid_order_id_is_success(self):
        import broker
        with patch("bot_state_manager.is_real_orders", return_value=True), \
             patch.object(broker, "_live_order_session_gate", return_value=None), \
             patch.object(broker, "get_dhan", return_value=MagicMock()), \
             patch.object(broker, "call_dhan_with_timeout", return_value={"orderId": "ORD123"}):
            result = broker.place_order("SECID1", "TESTSTOCK", 10)
        self.assertTrue(result["success"])
        self.assertEqual(result["order_id"], "ORD123")

    def test_paper_mode_unaffected(self):
        import broker
        with patch("bot_state_manager.is_real_orders", return_value=False):
            result = broker.place_order("SECID1", "TESTSTOCK", 10)
        self.assertTrue(result["success"])
        self.assertTrue(result["order_id"].startswith("PAPER-"))


class TestP0_002_ForeverOrderIdValidation(IsolatedProjectTestCase):
    def test_missing_forever_id_is_not_success(self):
        import broker
        with patch("bot_state_manager.is_real_orders", return_value=True), \
             patch.object(broker, "get_dhan", return_value=MagicMock()):
            mock_dhan = broker.get_dhan()
            mock_dhan.place_forever_order.return_value = {"someOtherField": "x"}
            with patch.object(broker, "get_dhan", return_value=mock_dhan):
                result = broker.place_forever_order("SECID1", "TESTSTOCK", 10, 95.0)
        self.assertFalse(result["success"])
        self.assertIsNone(result["forever_id"])

    def test_valid_forever_id_is_success(self):
        import broker
        mock_dhan = MagicMock()
        mock_dhan.place_forever_order.return_value = {"foreverOrderId": "GTT999"}
        with patch("bot_state_manager.is_real_orders", return_value=True), \
             patch.object(broker, "get_dhan", return_value=mock_dhan):
            result = broker.place_forever_order("SECID1", "TESTSTOCK", 10, 95.0)
        self.assertTrue(result["success"])
        self.assertEqual(result["forever_id"], "GTT999")

    def test_paper_mode_unaffected(self):
        import broker
        with patch("bot_state_manager.is_real_orders", return_value=False):
            result = broker.place_forever_order("SECID1", "TESTSTOCK", 10, 95.0)
        self.assertTrue(result["success"])


class TestP1_001_ParityFailClosed(IsolatedProjectTestCase):
    @staticmethod
    def _make_df(n=150):
        import pandas as pd
        idx = pd.date_range("2024-01-01", periods=n, freq="D")
        return pd.DataFrame({
            "open":  [100.0] * n,
            "high":  [101.0] * n,
            "low":   [99.0] * n,
            "close": [100.0] * n,
            "volume": [10000] * n,
        }, index=idx)

    @staticmethod
    def _make_trades():
        return [{"entry_idx": 0, "exit_idx": 5, "entry_price": 100.0, "return_pct": 2.0}]

    def test_parity_exception_marks_result_invalid_end_to_end(self):
        import backtester
        df = self._make_df()
        trades = self._make_trades()
        fake_strategy = MagicMock()
        fake_strategy.backtest_on_data.return_value = {"trades_list": trades}

        with patch.object(backtester, "fetch_historical_data", return_value=df), \
             patch.object(backtester, "get_active_strategy", return_value=fake_strategy), \
             patch("parity_engine.run_parity_equity", side_effect=RuntimeError("boom")):
            result = backtester.backtest_single("TESTSTOCK")

        self.assertFalse(result["valid"],
                          "a parity-engine exception must mark the backtest result invalid, "
                          "not silently fall back to old-style numbers reported as valid")
        self.assertIn("parity_error", result)
        self.assertIn("RuntimeError", result["parity_error"])
        # The old-style fallback numbers are still computed (for inspection),
        # so the function must not crash even though the result is invalid.
        self.assertIn("total_trades", result)

    def test_successful_parity_is_still_valid(self):
        import backtester
        df = self._make_df()
        trades = self._make_trades()
        fake_strategy = MagicMock()
        fake_strategy.backtest_on_data.return_value = {"trades_list": trades}
        fake_parity_report = {
            "kept_trades": trades,
            "final_capital": 205000.0,
            "equity": [200000.0, 205000.0],
            "worst_price_dd": -1.0,
            "n_rejected": 0,
        }

        with patch.object(backtester, "fetch_historical_data", return_value=df), \
             patch.object(backtester, "get_active_strategy", return_value=fake_strategy), \
             patch("parity_engine.run_parity_equity", return_value=fake_parity_report):
            result = backtester.backtest_single("TESTSTOCK")

        self.assertTrue(result["valid"],
                         "a successful parity run must NOT be marked invalid — "
                         "normal successful parity behavior must stay unchanged")
        self.assertIsNone(result["parity_error"])


class TestP1_004_TelegramHttpStatusChecked(IsolatedProjectTestCase):
    def test_non_2xx_response_is_treated_as_failure(self):
        import signal_broadcaster
        import httpx

        class FakeResponse:
            status_code = 403
            def raise_for_status(self):
                raise httpx.HTTPStatusError("403 Forbidden", request=None, response=self)

        class FakeClient:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def post(self, *a, **k): return FakeResponse()

        logged = {}
        def fake_append_log(path, msg):
            logged["msg"] = msg

        with patch("httpx.Client", return_value=FakeClient()), \
             patch("config.TELEGRAM_BOT_TOKEN", "fake-token"), \
             patch("config.ADMIN_CHAT_ID", 12345), \
             patch("utils.append_log", side_effect=fake_append_log):
            signal_broadcaster.alert_admin_sync("test message", severity="CRITICAL")
            import time
            time.sleep(0.3)  # background thread

        self.assertIn("msg", logged, "a 403 response must be logged as a failure, not silently dropped")
        self.assertIn("403", logged["msg"])

    def test_2xx_response_is_not_logged_as_failure(self):
        import signal_broadcaster

        class FakeResponse:
            status_code = 200
            def raise_for_status(self):
                return None

        class FakeClient:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def post(self, *a, **k): return FakeResponse()

        logged = {}
        def fake_append_log(path, msg):
            logged["msg"] = msg

        with patch("httpx.Client", return_value=FakeClient()), \
             patch("config.TELEGRAM_BOT_TOKEN", "fake-token"), \
             patch("config.ADMIN_CHAT_ID", 12345), \
             patch("utils.append_log", side_effect=fake_append_log):
            signal_broadcaster.alert_admin_sync("test message", severity="CRITICAL")
            import time
            time.sleep(0.3)

        self.assertNotIn("msg", logged, "a 2xx response must NOT be logged as a failure")


class TestP1_002_MorningRearmEscalation(IsolatedProjectTestCase):
    def test_failed_rearm_triggers_reconciliation_hold(self):
        import asyncio
        import scheduler_jobs_daily_ops as sjdo
        import bot_state_manager

        async def _run():
            with patch("sebi_manager.release_due_funds"), \
                 patch("backtester.check_backtest_staleness", return_value={"status": "OK"}), \
                 patch("signal_broadcaster.alert_admin", new_callable=AsyncMock), \
                 patch("forever_order_manager.rearm_gtt_missing",
                       return_value={"RELIANCE": "FAILED"}):
                await sjdo._morning_init_job()

        asyncio.run(_run())
        self.assertEqual(bot_state_manager.get_state(), "RECONCILIATION_HOLD")

    def test_successful_rearm_does_not_trigger_hold(self):
        import asyncio
        import scheduler_jobs_daily_ops as sjdo
        import bot_state_manager
        bot_state_manager.set_state("PAPER", "test reset")

        async def _run():
            with patch("sebi_manager.release_due_funds"), \
                 patch("backtester.check_backtest_staleness", return_value={"status": "OK"}), \
                 patch("signal_broadcaster.alert_admin", new_callable=AsyncMock), \
                 patch("forever_order_manager.rearm_gtt_missing",
                       return_value={"RELIANCE": "OK"}):
                await sjdo._morning_init_job()

        asyncio.run(_run())
        self.assertEqual(bot_state_manager.get_state(), "PAPER")


class TestP1_003_StartupReconciliationNotAutoCleared(IsolatedProjectTestCase):
    def test_reconciliation_hold_survives_successful_reboot_with_positions(self):
        import asyncio
        import startup_recovery
        import bot_state_manager

        bot_state_manager.set_state("RECONCILIATION_HOLD", "prior boot failure (test setup)")

        async def _run():
            with patch("broker.get_holdings",
                       return_value=[{"totalQty": "5"}]), \
                 patch("signal_broadcaster.alert_admin", new_callable=AsyncMock):
                return await startup_recovery.recover_state_on_boot()

        asyncio.run(_run())
        self.assertEqual(bot_state_manager.get_state(), "RECONCILIATION_HOLD",
                          "a successful holdings check on THIS boot must not silently "
                          "de-escalate a RECONCILIATION_HOLD left by a PREVIOUS boot's failure")

    def test_normal_boot_still_sets_exit_only(self):
        import asyncio
        import startup_recovery
        import bot_state_manager

        bot_state_manager.set_state("PAPER", "test reset")

        async def _run():
            with patch("broker.get_holdings",
                       return_value=[{"totalQty": "5"}]), \
                 patch("signal_broadcaster.alert_admin", new_callable=AsyncMock):
                return await startup_recovery.recover_state_on_boot()

        asyncio.run(_run())
        self.assertEqual(bot_state_manager.get_state(), "EXIT_ONLY",
                          "normal (non-hold) boot behavior with open positions must be unchanged")


class TestP0_003_UnprotectedPositionBlocksContinuation(IsolatedProjectTestCase):
    @staticmethod
    def _make_data(n=60):
        import pandas as pd
        idx = pd.date_range("2024-01-01", periods=n, freq="D")
        return pd.DataFrame({
            "open": [100.0] * n, "high": [101.0] * n,
            "low": [99.0] * n, "close": [100.0] * n,
            "volume": [10000] * n,
        }, index=idx)

    def _common_patches(self):
        """Everything _execute_entry touches before/after the GTT block,
        mocked to a plain successful-fill path so the test exercises only
        the GTT-outcome branch itself.
        
        R39 CORRECTED: Also mocks fundamental filter to avoid fail-closed blocking
        this GTT-specific test (fundamental filter is tested separately, not here).
        This does NOT weaken the GTT safety gate — only isolates this test from
        new fundamental dependency.
        """
        fake_strategy = MagicMock(name="BUyStrategy")
        fake_strategy.name = "TestStrategy"
        fake_strategy.version = "1.0"
        # Mock fundamental DNA as strong/available so GTT tests can run
        mock_fund_dna = {
            "symbol": "TESTSTOCK",
            "available": True,
            "cfo": 100.0, "pat": 80.0, "debt_to_equity": 0.2,
            "promoter_pledging_pct": 1.0, "interest_coverage": 5.0,
            "roce": 20.0, "roe": 22.0, "piotroski_f_score": 8,
            "current_ratio": 2.5, "altman_z_score": 3.5,
            "source": "screener.in",
            "provenance_chain": {"source": "screener.in", "note": "mock for P0/P1 test"},
        }
        mock_fund_eval = {
            "action": "PRIORITIZE",
            "final_alignment_decision": "PRIORITIZE",
            "fundamental_status": "STRONG_PRIORITIZE",
            "reason": "Strong fundamentals (mock for P0/P1 test)",
            "rejection_reason": "",
            "score": 5,
            "dna": mock_fund_dna,
            "is_mandatory": True,
            "fail_closed": False,
        }
        return [
            patch("trade_engine.get_security_id", return_value="SECID1"),
            patch("per_stock_params.get_param", return_value=1.0),
            patch("capital_manager.get_low_balance_decision",
                  return_value={"allow": True}),
            patch("trade_engine.calculate_qty_enhanced", return_value=10),
            patch("trade_engine.place_order",
                  return_value={"success": True, "order_id": "ORD1"}),
            patch("trade_engine.verify_order_status",
                  return_value=("FILLED", 100.0)),
            patch("trade_engine.get_active_strategy", return_value=fake_strategy),
            patch("trade_engine.get_stage_multiplier", return_value=1.0),
            patch("trade_engine.get_health_capital_multiplier", return_value=1.0),
            patch("trade_engine.get_regime_capital_multiplier", return_value=1.0),
            patch("trade_engine.detect_market_phase", return_value="NORMAL"),
            patch("trade_engine.register_trade"),
            patch("safety_manager.record_risk_used"),
            patch("capital_manager.get_deployable_balance", return_value=200000.0),
            patch("trade_engine.can_place_gtt", return_value=True),
            patch("trade_engine.log_trade_entry"),
            patch("trade_engine.broadcast_trade_signal", new_callable=AsyncMock),
            patch("trade_engine._get_active_linked_subscribers", return_value=["chat1"]),
            patch("trade_engine.copy_trade_all_subscribers", new_callable=AsyncMock),
            patch("trade_engine.alert_admin", new_callable=AsyncMock),
            patch("signal_broadcaster.alert_admin", new_callable=AsyncMock),
            # R39 CORRECTED: Mock fundamental filter so P0/P1 GTT tests are not blocked by fail-closed mandatory fundamental check
            patch("fundamental_data.get_latest_fundamental_dna", return_value=mock_fund_dna),
            patch("fundamental_sync_engine.should_reject_due_to_weak_fundamentals", return_value=(False, mock_fund_eval)),
            patch("fundamental_sync_engine.should_prioritize_due_to_strong_fundamentals", return_value=(True, mock_fund_eval)),
            patch("fundamental_sync_engine.enrich_with_fundamental_dna", return_value={
                "symbol": "TESTSTOCK",
                "fundamental_dna": mock_fund_dna,
                "fundamental_evaluation": mock_fund_eval,
                "fundamental_status": "STRONG_PRIORITIZE",
                "final_alignment_decision": "PRIORITIZE",
                "technical_status": "STRONG",
                "technical_tools_used": ["TEST"],
                "technical_alignment": "ALIGNED",
                "rejection_reason": "",
                "is_mandatory": True,
                "fail_closed": False,
            }),
            patch("fundamental_sync_engine._is_fundamental_mandatory", return_value=True),
        ]

    def test_gtt_failure_blocks_broadcast_and_copy_trade_and_holds(self):
        import asyncio, contextlib
        import trade_engine
        import bot_state_manager
        bot_state_manager.set_state("LIVE_FULL", "test setup")

        signal = {"entry_price": 100.0, "sl_price": 95.0, "tp1_price": 110.0,
                  "reason": "test signal"}
        data = self._make_data()

        with contextlib.ExitStack() as stack:
            for p in self._common_patches():
                stack.enter_context(p)
            stack.enter_context(patch(
                "trade_engine.setup_forever_orders",
                return_value={"success": False, "message": "no valid forever_order_id"}))
            broadcast_mock = trade_engine.broadcast_trade_signal
            copy_mock = trade_engine.copy_trade_all_subscribers
            log_entry_mock = trade_engine.log_trade_entry

            asyncio.run(trade_engine._execute_entry("TESTSTOCK", signal, data))

        log_entry_mock.assert_called_once()  # position still recorded/tracked
        broadcast_mock.assert_not_called()   # not broadcast as a normal healthy entry
        copy_mock.assert_not_called()        # subscribers not copy-traded into unprotected position
        self.assertEqual(bot_state_manager.get_state(), "RECONCILIATION_HOLD")

    def test_gtt_success_continues_normally(self):
        import asyncio, contextlib
        import trade_engine
        import bot_state_manager
        bot_state_manager.set_state("LIVE_FULL", "test setup")

        signal = {"entry_price": 100.0, "sl_price": 95.0, "tp1_price": 110.0,
                  "reason": "test signal"}
        data = self._make_data()

        with contextlib.ExitStack() as stack:
            for p in self._common_patches():
                stack.enter_context(p)
            stack.enter_context(patch(
                "trade_engine.setup_forever_orders",
                return_value={"success": True, "forever_id": "GTT1"}))
            broadcast_mock = trade_engine.broadcast_trade_signal
            copy_mock = trade_engine.copy_trade_all_subscribers
            log_entry_mock = trade_engine.log_trade_entry

            asyncio.run(trade_engine._execute_entry("TESTSTOCK", signal, data))

        log_entry_mock.assert_called_once()
        broadcast_mock.assert_awaited_once()
        copy_mock.assert_awaited_once()
        # A successful GTT must NOT trigger the hold — normal behavior unchanged.
        self.assertEqual(bot_state_manager.get_state(), "LIVE_FULL")


class TestP0_002b_SubscriberForeverOrderIdValidation(IsolatedProjectTestCase):
    """Found by the new LOGIC-007/CWE-252 general rule after the original
    manual pass — place_forever_order_for_subscriber() had the exact same
    unvalidated-ID gap as P0-002, just on the subscriber (copy-trade) path."""

    def test_missing_forever_id_is_not_success(self):
        import asyncio
        import broker
        sub = {"chat_id": "sub1", "dhan_client_id": "c1",
               "dhan_access_token_enc": "enc"}
        with patch("crypto_utils.decrypt", return_value="token"), \
             patch.object(broker, "_create_dhan_client", return_value=MagicMock(
                 place_forever_order=MagicMock(return_value={"someOtherField": "x"}))):
            result = asyncio.run(broker.place_forever_order_for_subscriber(
                sub, "SECID1", "TESTSTOCK", 10, 95.0))
        self.assertFalse(result["success"])
        self.assertIsNone(result["forever_id"])

    def test_valid_forever_id_is_success(self):
        import asyncio
        import broker
        sub = {"chat_id": "sub1", "dhan_client_id": "c1",
               "dhan_access_token_enc": "enc"}
        with patch("crypto_utils.decrypt", return_value="token"), \
             patch.object(broker, "_create_dhan_client", return_value=MagicMock(
                 place_forever_order=MagicMock(return_value={"foreverOrderId": "GTT1"}))):
            result = asyncio.run(broker.place_forever_order_for_subscriber(
                sub, "SECID1", "TESTSTOCK", 10, 95.0))
        self.assertTrue(result["success"])
        self.assertEqual(result["forever_id"], "GTT1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
