"""
test_overnight.py — OVERNIGHT MOVERS module golden/regression tests (v5.2)

Offline deterministic tests: scoring components fail-closed, weights
normalize, outcome tracking, TP/SL grid optimizer, edge report. Koi network
nahi — synthetic data fixed values (golden freeze).
"""

import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# [AUDIT F7 FIX, 2026-09-16] `python3 test_overnight.py` (unittest.main()
# below) never loads conftest.py's pytest-only sandbox -- the
# save_json(om.OVERNIGHT_TRACK_FILE,...)/save_json("data/trades.json",...)
# calls in this file's tests would hit the real release-tree data/ files.
# `import conftest` activates the same temp-dir sandbox standalone.
import conftest  # noqa: E402,F401

import numpy as np
import pandas as pd


def _snapshot(closes, vols):
    n = len(closes)
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    highs = np.maximum(opens, closes) * 1.002
    lows = np.minimum(opens, closes) * 0.998
    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": np.asarray(vols, dtype=float),
    })


class TestOvernight(unittest.TestCase):

    def test_disabled_by_default(self):
        import overnight_movers as om
        self.assertFalse(om.is_overnight_enabled())

    def test_weights_normalized(self):
        import overnight_movers as om
        from config import PARAMS
        orig = PARAMS.get("overnight_score_weights")
        PARAMS["overnight_score_weights"] = {"volume_surge": 2, "price_strength": 2}
        w = om._score_weights()
        self.assertAlmostEqual(sum(w.values()), 1.0, places=6)
        self.assertAlmostEqual(w["volume_surge"], 0.5, places=6)
        PARAMS["overnight_score_weights"] = orig

    def test_components_fail_closed(self):
        import overnight_movers as om
        self.assertEqual(om._component_volume_surge("X", pd.DataFrame()), 0.0)
        self.assertEqual(om._component_price_strength("X", pd.DataFrame()), 0.0)
        self.assertEqual(om._component_earnings_event("X", {}), 0.0)
        self.assertEqual(om._component_bulk_deal("X", {}), 0.0)
        self.assertEqual(om._component_depth_imbalance("NO_SUCH_SYM"), 0.0)
        self.assertEqual(om._component_news_sentiment("NO_SUCH_SYM"), 0.0)
        self.assertEqual(om._component_fii_dii(), 0.0)  # no fii data offline
        from unittest.mock import patch
        with patch("dhan_data.fetch_daily_data", return_value=pd.DataFrame()):
            self.assertEqual(om._component_overnight_persistence("X"), 0.0)
            self.assertEqual(om._component_tug_of_war("X"), 0.0)

    def _bar_df(self, n, gap, intra):
        """Direct bar-to-bar construction: overnight = +gap%, intraday = +intra%."""
        closes = [100.0]
        opens = [100.0]
        for i in range(1, n):
            opens.append(round(closes[i - 1] * (1 + gap), 4))
            closes.append(round(opens[i] * (1 + intra), 4))
        return pd.DataFrame({"open": opens,
                             "high": np.maximum(opens, closes) * 1.001,
                             "low": np.minimum(opens, closes) * 0.999,
                             "close": closes, "volume": np.full(n, 1e6)})

    def test_overnight_persistence_exact(self):
        """[Lou/Polk/Skouras 2019] trailing 5-din avg gap +0.6% → 0.6."""
        import overnight_movers as om
        from unittest.mock import patch
        with patch("dhan_data.fetch_daily_data",
                   return_value=self._bar_df(25, gap=0.006, intra=-0.004)):
            self.assertEqual(om._component_overnight_persistence("X"), 0.6)
            self.assertEqual(om._component_tug_of_war("X"), 1.0)

    def test_tug_of_war_neutral_pattern(self):
        """No tug pattern (overnight aur intraday dono positive) → 0."""
        import overnight_movers as om
        from unittest.mock import patch
        with patch("dhan_data.fetch_daily_data",
                   return_value=self._bar_df(25, gap=0.006, intra=0.004)):
            self.assertEqual(om._component_tug_of_war("X"), 0.0)
            # overnight persistence to is pattern me 0.6 hi rahega
            self.assertEqual(om._component_overnight_persistence("X"), 0.6)

    def test_new_signals_in_weights(self):
        """Naye verified signals default weights me registered hain."""
        import overnight_movers as om
        w = om._score_weights()
        for key in ("overnight_persistence", "tug_of_war"):
            self.assertIn(key, w)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=6)

    def test_price_strength_exact(self):
        import overnight_movers as om
        # +2% close near high → ret_norm 0.4, close_pos ~1 → 0.6*0.4+0.4*1 = 0.64
        closes = [100.0, 100.5, 101.0, 101.5, 102.0]
        vols = [1000] * 5
        snap = _snapshot(closes, vols)
        s = om._component_price_strength("X", snap)
        self.assertAlmostEqual(s, 0.64, places=1)

    def test_outcome_tracking_roundtrip(self):
        import overnight_movers as om
        from utils import save_json
        save_json(om.OVERNIGHT_TRACK_FILE, {"trades": []})
        om.record_overnight_entry("ABC", 100.0, 99.0, 101.5, 0.7)
        om.record_overnight_outcome("ABC", 101.5, "TP", day_high=102.0, day_low=99.5)
        rep = om.overnight_edge_report()
        self.assertEqual(rep["closed_trades"], 1)
        self.assertEqual(rep["avg_net_pct"], 1.5)
        # 1 trade < min_paper_trades → edge not proven (fail-closed)
        self.assertFalse(rep["edge_enabled"])

    def test_exit_optimizer_grid_exact(self):
        import overnight_movers as om
        from utils import save_json
        # 30 synthetic trades: sab TP-friendly (day_high hamesha +3% pe,
        # day_low sirf -0.1%) → optimizer ko highest TP pasand aana chahiye
        # (SL grid ka koi effect nahi — low kabhi SL touch nahi karta).
        trades = []
        for i in range(30):
            trades.append({
                "symbol": f"S{i}", "entry_price": 100.0, "exit_price": 102.0,
                "day_high": 103.0, "day_low": 99.9, "status": "CLOSED",
                "net_pct": 2.0,
            })
        save_json(om.OVERNIGHT_TRACK_FILE, {"trades": trades})
        res = om.optimize_overnight_exit_params()
        self.assertEqual(res["status"], "optimized")
        self.assertEqual(res["tp_pct"], 2.75)   # grid ka highest TP jeetega
        self.assertEqual(res["trades_evaluated"], 30)

    def test_edge_report_enables_with_positive_data(self):
        import overnight_movers as om
        from utils import save_json
        trades = []
        for i in range(30):
            net = 1.1 if i % 2 == 0 else 1.3  # slight variance (zero-variance fail nahi)
            trades.append({
                "symbol": f"S{i}", "entry_price": 100.0, "exit_price": 100.0 + net,
                "day_high": 101.5, "day_low": 99.8, "status": "CLOSED",
                "net_pct": net,
            })
        save_json(om.OVERNIGHT_TRACK_FILE, {"trades": trades})
        rep = om.overnight_edge_report()
        self.assertTrue(rep["edge_enabled"])
        self.assertEqual(rep["win_rate_pct"], 100.0)

    def test_sync_outcomes_from_trades(self):
        import overnight_movers as om
        from utils import save_json
        save_json(om.OVERNIGHT_TRACK_FILE, {"trades": []})
        save_json("data/trades.json", {"trades": [
            {"symbol": "XYZ", "mode": "OVERNIGHT", "status": "CLOSED",
             "entry_price": 100.0, "exit_price": 101.0,
             "entry_time": "2026-08-18T15:20:00", "exit_time": "2026-08-19T09:30:00"},
            {"symbol": "NORMAL", "mode": "NORMAL", "status": "CLOSED",
             "entry_price": 100.0, "exit_price": 99.0,
             "entry_time": "2026-08-18T10:00:00", "exit_time": "2026-08-19T10:00:00"},
        ]})
        synced = om.sync_outcomes_from_trades()
        self.assertEqual(synced, 1)  # sirf OVERNIGHT wala sync hota hai
        rep = om.overnight_edge_report()
        self.assertEqual(rep["closed_trades"], 1)


if __name__ == "__main__":
    unittest.main()
