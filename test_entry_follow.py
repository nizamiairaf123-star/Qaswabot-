"""
test_entry_follow.py — v5.9 Entry Follow + Shadow Log unit tests
(owner D28 execution-only rule; strategy zero-touch verify)

Tests monkeypatch broker/capital_manager calls — koi real order nahi.
Data layer SQLite-backed hai (utils.load_json/save_json → database.DB_PATH),
isliye isolation = alag test DB (prod trading_bot.db kabhi touch nahi).
"""

# [AUDIT F7 FIX, 2026-09-16] TEST_DB below is already an absolute /tmp
# path (cwd-independent), but shadow_log and any other relative "data/"
# writes this file doesn't explicitly override are not -- add the same
# blanket sandbox as defense-in-depth.
import conftest  # noqa: F401
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as config_mod
import database as database_mod
import entry_follow
import shadow_log
from utils import load_json

TMP = "/tmp/qaswa_v59_test"
os.makedirs(TMP, exist_ok=True)

TEST_DB = f"{TMP}/trading_bot_test.db"
_ORIG_DB_PATH = database_mod.DB_PATH


def _rm(f):
    if os.path.exists(f):
        os.remove(f)


class TestEntryFollow(unittest.TestCase):

    def setUp(self):
        database_mod.DB_PATH = TEST_DB
        database_mod.init_db()
        config_mod.CRASH_PENDING_ORDERS_FILE = f"{TMP}/crash_pending_orders.json"
        entry_follow._cmp_cache.clear()

    def tearDown(self):
        _rm(TEST_DB)
        database_mod.DB_PATH = _ORIG_DB_PATH
        entry_follow._cmp_cache.clear()

    def _register(self, symbol="ABC", entry=100.0, sl=98.0, tp=106.0):
        entry_follow.register_following_order(
            order_id="O1", symbol=symbol, qty=10,
            entry_price=entry, sl_price=sl, tp1_price=tp,
            security_id="SEC1")
        state = entry_follow._load()
        return state["orders"][0]

    # ── registration ──

    def test_register_persists_resting_order(self):
        rec = self._register()
        self.assertEqual(rec["order_id"], "O1")
        self.assertEqual(rec["symbol"], "ABC")
        self.assertEqual(rec["qty"], 10)
        self.assertEqual(rec["entry_price"], 100.0)
        self.assertEqual(rec["sl_price"], 98.0)
        self.assertEqual(rec["missing_price_ticks"], 0)

    # ── tick: FILLED → ADOPT ──

    def test_tick_filled_adopts(self):
        self._register()
        with mock.patch("broker.verify_order_status", return_value=("FILLED", 100.0)), \
             mock.patch("capital_manager.get_active_trades", return_value={}), \
             mock.patch("capital_manager.register_trade") as m_reg, \
             mock.patch("forever_order_manager.setup_forever_orders",
                        return_value={"ok": True}) as m_gtt, \
             mock.patch("stock_selector.get_security_id", return_value="SEC1"), \
             mock.patch("strategy.get_active_strategy", return_value=None), \
             mock.patch("entry_follow.append_log"), \
             mock.patch("entry_follow._clean_crash_pending") as m_clean:
            res = entry_follow.tick_following_orders()
        self.assertIn("O1", res)
        self.assertTrue(res["O1"].startswith("ADOPTED"))
        m_reg.assert_called_once()
        sym = m_reg.call_args[0][0]
        td = m_reg.call_args[0][1]
        self.assertEqual(sym, "ABC")
        self.assertEqual(td["phase"], "FOLLOW_ADOPT")
        m_gtt.assert_called_once()
        m_clean.assert_called_once()
        self.assertEqual(entry_follow._load()["orders"], [])

    def test_tick_adopt_skips_already_tracked(self):
        self._register()
        with mock.patch("broker.verify_order_status", return_value=("FILLED", 100.0)), \
             mock.patch("capital_manager.get_active_trades",
                        return_value={"ABC": {}}), \
             mock.patch("capital_manager.register_trade") as m_reg, \
             mock.patch("entry_follow.append_log"), \
             mock.patch("entry_follow._clean_crash_pending"):
            res = entry_follow.tick_following_orders()
        self.assertTrue(res["O1"].startswith("ADOPTED(ALREADY_TRACKED)"))
        m_reg.assert_not_called()

    # ── tick: gap logic ──

    def test_tick_hold_small_gap(self):
        self._register()  # entry 100, sl 98 → risk 2
        entry_follow.update_cmp("ABC", 101.5)  # 0.75 units < 1.0
        with mock.patch("broker.verify_order_status", return_value=("PENDING", None)), \
             mock.patch("broker.cancel_order") as m_cancel, \
             mock.patch("entry_follow.append_log"):
            res = entry_follow.tick_following_orders()
        self.assertEqual(res["O1"], "HOLD")
        m_cancel.assert_not_called()
        self.assertEqual(len(entry_follow._load()["orders"]), 1)

    def test_tick_cancel_ran_away(self):
        self._register()
        entry_follow.update_cmp("ABC", 102.5)  # 1.25 units > 1.0
        with mock.patch("broker.verify_order_status", return_value=("PENDING", None)), \
             mock.patch("broker.cancel_order", return_value=True) as m_cancel, \
             mock.patch("entry_follow.append_log"), \
             mock.patch("entry_follow._clean_crash_pending"):
            res = entry_follow.tick_following_orders()
        self.assertEqual(res["O1"], "CANCELLED(RAN_AWAY)")
        m_cancel.assert_called_once_with("O1")
        self.assertEqual(entry_follow._load()["orders"], [])

    def test_tick_race_adopt_on_cancel_fail(self):
        self._register()
        entry_follow.update_cmp("ABC", 102.5)
        with mock.patch("broker.verify_order_status",
                        side_effect=[("PENDING", None), ("FILLED", 100.0)]), \
             mock.patch("broker.cancel_order", return_value=False), \
             mock.patch("capital_manager.get_active_trades", return_value={}), \
             mock.patch("capital_manager.register_trade"), \
             mock.patch("forever_order_manager.setup_forever_orders",
                        return_value={"ok": True}), \
             mock.patch("stock_selector.get_security_id", return_value="SEC1"), \
             mock.patch("strategy.get_active_strategy", return_value=None), \
             mock.patch("entry_follow.append_log"), \
             mock.patch("entry_follow._clean_crash_pending"):
            res = entry_follow.tick_following_orders()
        self.assertTrue(res["O1"].startswith("ADOPTED_RACE"))

    def test_tick_no_price_hold_then_cancel(self):
        self._register()
        with mock.patch("broker.verify_order_status", return_value=("PENDING", None)), \
             mock.patch("entry_follow.append_log"):
            for _i in range(2):
                res = entry_follow.tick_following_orders()
                self.assertEqual(res["O1"], "HOLD(no_price)")
            # teesra tick → cancel (3 ticks missing)
            with mock.patch("broker.cancel_order", return_value=True) as m_c, \
                 mock.patch("entry_follow.append_log"), \
                 mock.patch("entry_follow._clean_crash_pending"):
                res = entry_follow.tick_following_orders()
            self.assertEqual(res["O1"], "CANCELLED(NO_PRICE)")
            m_c.assert_called_once()
            self.assertEqual(entry_follow._load()["orders"], [])

    def test_tick_cleaned_on_rejected(self):
        self._register()
        with mock.patch("broker.verify_order_status", return_value=("REJECTED", None)), \
             mock.patch("entry_follow.append_log"), \
             mock.patch("entry_follow._clean_crash_pending"):
            res = entry_follow.tick_following_orders()
        self.assertEqual(res["O1"], "CLEANED(REJECTED)")
        self.assertEqual(entry_follow._load()["orders"], [])

    def test_tick_partial_holds_for_manual(self):
        self._register()
        with mock.patch("broker.verify_order_status", return_value=("PARTIAL", None)), \
             mock.patch("entry_follow.append_log"):
            res = entry_follow.tick_following_orders()
        self.assertEqual(res["O1"], "HOLD(PARTIAL)")
        self.assertEqual(len(entry_follow._load()["orders"]), 1)

    # ── shadow log ──

    def test_shadow_record_and_path(self):
        shadow_log.record_signal("ABC", 100, 98, 106)
        shadow_log.update_cmp("ABC", 101)
        shadow_log.update_cmp("ABC", 101)  # duplicate ignore
        shadow_log.update_cmp("ABC", 103)
        data = load_json(shadow_log.SHADOW_DAY_FILE, {"day": "", "signals": {}})
        sig = data["signals"]["ABC"]
        self.assertEqual(len(sig["path"]), 2)
        self.assertEqual(sig["entry"], 100.0)

    def test_shadow_one_record_per_symbol(self):
        shadow_log.record_signal("ABC", 100, 98, 106)
        shadow_log.record_signal("ABC", 101, 99, 107)  # ignore
        data = load_json(shadow_log.SHADOW_DAY_FILE, {"day": "", "signals": {}})
        self.assertEqual(len(data["signals"]), 1)
        self.assertEqual(data["signals"]["ABC"]["entry"], 100.0)

    def test_shadow_finalize_bucket_math(self):
        shadow_log.record_signal("ABC", 100, 98, 106)
        shadow_log.update_cmp("ABC", 99)   # touch → would fill
        shadow_log.update_cmp("ABC", 106)  # TP hit
        shadow_log.record_signal("XYZ", 200, 196, 212)
        shadow_log.update_cmp("XYZ", 210)  # 2.5 units upar, kabhi wapas nahi
        with mock.patch("shadow_log.append_log"):
            out = shadow_log.finalize_day()
        self.assertEqual(out["finalized"], 2)
        day_data = load_json(shadow_log.SHADOW_DAY_FILE, {"day": "", "signals": {}})
        self.assertEqual(day_data["signals"], {})  # agle din ke liye clean
        rep = load_json(shadow_log.SHADOW_REPORT_FILE, {"days": [], "buckets": {}})
        rows = rep["days"][-1]["summary"]
        by = {r["symbol"]: r for r in rows}
        self.assertTrue(by["ABC"]["touched_entry"])
        self.assertEqual(by["ABC"]["outcome_if_filled"], "TP")
        self.assertFalse(by["XYZ"]["touched_entry"])
        self.assertGreater(by["XYZ"]["max_gap_units"], 2.0)
        self.assertIn("buckets", rep)

    def test_shadow_recommendation_insufficient(self):
        rec = shadow_log.recommend_risk_units({"<0.5": {"n": 5, "returned": 4,
                                                        "return_pct": 80.0}})
        self.assertIsNone(rec["risk_units"])
        self.assertIn("insufficient", rec["reason"])

    def test_shadow_recommendation_picks_bucket(self):
        buckets = {
            "<0.5": {"n": 40, "returned": 32, "return_pct": 80.0},
            "<1.0": {"n": 40, "returned": 28, "return_pct": 70.0},
            ">=2.0": {"n": 40, "returned": 8, "return_pct": 20.0},
        }
        rec = shadow_log.recommend_risk_units(buckets)
        self.assertEqual(rec["risk_units"], 1.0)

    def test_shadow_disabled_noop(self):
        old = config_mod.PARAMS.get("shadow_log_enabled")
        config_mod.PARAMS["shadow_log_enabled"] = False
        try:
            shadow_log.record_signal("ABC", 100, 98, 106)
            data = load_json(shadow_log.SHADOW_DAY_FILE,
                             {"day": "", "signals": {}})
            self.assertEqual(data, {"day": "", "signals": {}})
        finally:
            if old is None:
                config_mod.PARAMS.pop("shadow_log_enabled", None)
            else:
                config_mod.PARAMS["shadow_log_enabled"] = old


if __name__ == "__main__":
    unittest.main()
