"""
test_macro.py — India macro auto-refresh golden tests (v5.7.2)
Offline deterministic: fail-open (no source → unchanged), parser validation
(out-of-range reject), override apply fresh vs stale.
"""

import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# [AUDIT F7 FIX, 2026-09-16] Guarantees sandbox isolation even when this
# file is run standalone, not just pytest.
import conftest  # noqa: F401

from unittest.mock import patch


class TestMacroRefresh(unittest.TestCase):

    def test_no_source_fail_open(self):
        """Source nahi set → refresh kuch nahi badalta (purani values intact)."""
        import macro_refresh as mr
        with patch.object(mr, "SOURCE_URL", ""):
            res = mr.refresh_india_macro()
        self.assertFalse(res["updated"])
        self.assertEqual(res["reason"], "no_source")

    def test_invalid_values_rejected(self):
        """Out-of-range CPI (fake source) → reject, kuch update nahi."""
        import macro_refresh as mr
        fake = {"cpi_inflation_pct": 99.0, "gdp_growth_pct": 6.8,
                "risk_free_rate_pct": 7.0, "as_of": "2026-07"}
        with patch.object(mr, "_fetch_macro_data", return_value=fake):
            res = mr.refresh_india_macro()
        self.assertFalse(res["updated"])
        self.assertEqual(res["reason"], "invalid_values")

    def test_valid_values_apply(self):
        """Valid data → override file + runtime PARAMS update."""
        import macro_refresh as mr
        from config import PARAMS
        from utils import save_json
        save_json(mr.MACRO_OVERRIDE_FILE, {})
        fake = {"cpi_inflation_pct": 4.6, "gdp_growth_pct": 6.5,
                "risk_free_rate_pct": 6.8, "as_of": "2026-07"}
        with patch.object(mr, "_fetch_macro_data", return_value=fake), \
             patch("signal_broadcaster.alert_admin_sync") as _alert:
            res = mr.refresh_india_macro()
        self.assertTrue(res["updated"])
        self.assertEqual(PARAMS["india_inflation_pct"], 4.6)
        self.assertEqual(PARAMS["india_gdp_growth_pct"], 6.5)
        self.assertEqual(PARAMS["india_risk_free_rate_pct"], 6.8)

    def test_apply_override_fresh(self):
        """Fresh override boot pe apply hota hai."""
        import macro_refresh as mr
        from config import PARAMS
        from utils import save_json, now_ist
        save_json(mr.MACRO_OVERRIDE_FILE, {
            "india_inflation_pct": 4.7, "india_gdp_growth_pct": 6.9,
            "india_risk_free_rate_pct": 7.1, "as_of": "2026-08",
            "saved_at": now_ist().isoformat()})
        mr.apply_macro_override()
        self.assertEqual(PARAMS["india_inflation_pct"], 4.7)
        self.assertEqual(PARAMS["india_gdp_growth_pct"], 6.9)

    def test_apply_override_stale_rejected(self):
        """Stale override (>warn_days) apply NAHI hota — alert + purana intact."""
        import macro_refresh as mr
        from config import PARAMS
        from utils import save_json
        before = PARAMS["india_inflation_pct"]
        save_json(mr.MACRO_OVERRIDE_FILE, {
            "india_inflation_pct": 9.9, "india_gdp_growth_pct": 9.9,
            "india_risk_free_rate_pct": 9.9, "as_of": "2025-01",
            "saved_at": "2025-01-01T00:00:00+05:30"})
        with patch("signal_broadcaster.alert_admin_sync") as _alert:
            mr.apply_macro_override()
        self.assertNotEqual(PARAMS["india_inflation_pct"], 9.9)
        self.assertEqual(PARAMS["india_inflation_pct"], before)  # intact


if __name__ == "__main__":
    unittest.main()
