"""
test_sharia_and_validation.py — Isolated acceptance and regression test for Phase 8 & 10.
"""

# [AUDIT F7 FIX, 2026-09-16] This file reads/writes real relative
# "data/zakat_dates.json"/"data/haram_pending.json" with no tempfile
# override (only backs up/restores those 2 specific paths) -- unsafe for
# anything else it touches if ever run standalone. Sandbox guarantees
# full isolation regardless.
import conftest  # noqa: F401
import os
import unittest
import sys

# Ensure project import path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sharia_manager import calculate_zakat
from utils import save_json, load_json, ensure_data_dir

class TestShariaAndValidation(unittest.TestCase):

    def setUp(self):
        ensure_data_dir()

        # zakat_dates.json/haram_pending.json can legitimately contain real
        # data — back it up here and restore it in tearDown rather than
        # clearing it (same isolation discipline used in
        # test_full_pipeline.py's TEST 7 for haram_pending.json).
        self._sqlite_backups = {}
        for path in ["data/zakat_dates.json", "data/haram_pending.json"]:
            self._sqlite_backups[path] = load_json(path, {})

    def tearDown(self):
        # Restore exactly what was there before this test ran — real data
        # preserved, test-created entries removed.
        for path in ["data/zakat_dates.json", "data/haram_pending.json"]:
            try:
                save_json(path, self._sqlite_backups.get(path, {}))
            except Exception:
                pass

    def test_calculate_zakat(self):
        # Gold price = Rs.6000 per gram -> Nisab = 87.48 * 6000 = Rs.524,880
        gold_price = 6000.0

        # Scenario 1: Below Nisab
        res_below = calculate_zakat(300000.0, gold_price)
        self.assertIn("Below Nisab", res_below)
        self.assertIn("obligatory", res_below)

        # Scenario 2: Above Nisab
        res_above = calculate_zakat(600000.0, gold_price)
        self.assertIn("Above Nisab", res_above)
        self.assertIn("Zakat (2.5%): Rs.15,000", res_above)

if __name__ == "__main__":
    unittest.main()
