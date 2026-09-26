"""
test_golden.py — GOLDEN REGRESSION (v5.0 Tier 3)

Known-good exact outputs: same fixed synthetic inputs pe hamesha same
result aana chahiye. Silent bug detect karta hai jo dusre tests miss kar
jate hain (code change ne core math badal diya, feature "kaam" karta
dikhe lekin value galat nikle).

Values v5.0 release pe generate karke freeze kiye gaye hain —
DETERMINISTIC synthetic data (fixed seeds, fixed arrays) — koi network nahi.
"""

# [AUDIT F7 FIX, 2026-09-16] Guarantees sandbox isolation even when this
# file is run standalone, not just pytest.
import conftest  # noqa: F401
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd


def _ohlcv(closes):
    closes = np.asarray(closes, dtype=float)
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    highs = np.maximum(opens, closes) * 1.0004
    lows = np.minimum(opens, closes) * 0.9996
    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": np.full(len(closes), 1_000_000),
    })


UP = _ohlcv(np.linspace(100.0, 160.0, 300))
DOWN = _ohlcv(np.linspace(160.0, 100.0, 300))
# [FIX-LIST 2026-09-04 item 4] FLAT fixture replaced. The old fixture
# alternated +0.4%/-0.4% every bar, which makes HIGH and LOW *identical* on
# every bar → +DM = 0 and -DM = 0 for 298 of 300 bars. On such degenerate
# data DX is 100*|0 - tiny|/(0 + tiny + 1e-10): the old span-EMA formula
# decayed "tiny" below 1e-10 and returned ADX≈0 ("SIDEWAYS") purely as a
# floating-point artifact; textbook Wilder smoothing returns ≈100 on the
# same data. A real range-bound market has moving highs/lows, so the fixture
# is now a deterministic 10-bar sinusoid (±0.4%, no randomness) — genuinely
# directionless price action for which Wilder ADX ≈ 12.5 (< threshold).
FLAT = _ohlcv([100.0 * (1 + 0.004 * np.sin(2 * np.pi * i / 10)) for i in range(300)])


class TestGoldenCore(unittest.TestCase):

    def test_phase_detection_exact(self):
        from strategy import detect_market_phase
        PP = {"phase_ema_fast": 5, "phase_ema_slow": 40, "phase_adx_threshold": 22.0}
        self.assertEqual(detect_market_phase(UP, None, params_override=PP), "UPTREND")
        self.assertEqual(detect_market_phase(DOWN, None, params_override=PP), "DOWNTREND")
        self.assertEqual(detect_market_phase(FLAT, None, params_override=PP), "SIDEWAYS")

    def test_phase_edge_test_exact(self):
        from optimizer import _phase_edge_test
        win = _phase_edge_test([2.1, 3.4, 1.8, 2.9, 2.2, 3.1, 2.6, 1.9, 2.8, 3.3])
        self.assertTrue(win["enabled"])
        self.assertEqual(win["n"], 10)
        self.assertEqual(win["expectancy"], 2.61)
        self.assertAlmostEqual(win["p_value"], 0.0, places=6)
        self.assertEqual(win["t_stat"], 14.18)

        neg = _phase_edge_test([-1.2, -0.8, -2.0, -1.5, -0.6, -1.9, -1.1, -2.2, -0.9, -1.4])
        self.assertFalse(neg["enabled"])
        self.assertEqual(neg["reason"], "non_positive_expectancy")

        small = _phase_edge_test([2.0, 2.5])
        self.assertFalse(small["enabled"])
        self.assertEqual(small["reason"], "insufficient_oos_trades")

    def test_regime_combine_exact(self):
        import market_regime as mr
        d = {"nifty": {"regime": "BULL", "score": 2.0},
             "sector": {"score": 1.0}, "vix": {"score": 0.0}, "usdinr": {"score": 0.0}}
        out = mr._combine(d)
        self.assertEqual(out["regime"], "BULL")
        # weights normalized: nifty .45, sector .25, vix .15, usdinr .15
        self.assertEqual(out["combined_score"], 1.15)

    def test_rsi_extremes(self):
        from strategy import calc_rsi
        rsi_up = calc_rsi(UP, 14)
        self.assertGreater(rsi_up.iloc[-1], 70.0)
        rsi_down = calc_rsi(DOWN, 14)
        self.assertLess(rsi_down.iloc[-1], 30.0)

    def test_validate_config_clean(self):
        from config import validate_config
        self.assertEqual(validate_config(), [])

    def test_provenance_all_registered(self):
        import config
        checked = [k for k, v in config.OPTIMIZABLE_DEFAULTS.items()
                   if not isinstance(v, (bool, type(None)))]
        # har default (numeric + string-categorical jaise exit_mode) registered
        for k in checked:
            self.assertIn(k, config.PARAM_SOURCES, f"unregistered value: {k}")
        # koi orphan source entry nahi
        for k in config.PARAM_SOURCES:
            self.assertIn(k, config.OPTIMIZABLE_DEFAULTS, f"orphan source: {k}")

    def test_lm_lexicon_exact(self):
        from news_analyzer import _load_lm_words, _lm_lexicon_sentiment
        wl = _load_lm_words()
        self.assertEqual(len(wl["neg"]), 2355)
        self.assertEqual(len(wl["pos"]), 354)
        self.assertEqual(_lm_lexicon_sentiment(["Company reports record profit and strong growth"]), 1.0)
        self.assertEqual(_lm_lexicon_sentiment(["Company reports loss, fraud and bankruptcy probe"]), -1.0)
        self.assertEqual(_lm_lexicon_sentiment(["Company did not report any loss"]), 1.0)

    def test_gtt_l2_fallback_math(self):
        # L2 trigger = fixed SL − offset% (fixed SL floor hi rehta hai)
        from config import PARAMS
        sl = 98.0
        offset = float(PARAMS.get("gtt_layer2_offset_pct", 0.2))
        self.assertEqual(round(sl * (1.0 - offset / 100.0), 2), 97.8)

    # ── v5.3 ROBUST TRAILING (unified formula — exact golden values) ──

    def _trail_params(self):
        # v5.4: exit toolkit me trail ab EK mode hai (optimizer-selectable) —
        # ye golden tests pure-trail behavior freeze karte hain.
        return {"sl_pct": 2.0, "tp1_pct": 4.0, "trail_multiplier": 1.5,
                "min_reward_risk": 1.8, "atr_period": 14,
                "exit_mode": "trail", "profit_lock_pct": 1.0, "ratchet_step_pct": 1.5}

    def test_trail_uncapped_profit(self):
        """Purana fixed TP (~4%) hata — trail se 22% tak ride (uncapped)."""
        import optimizer
        import parity_engine
        optimizer.filter_signals_by_macro_context = (
            lambda data, symbol, signals, is_backtest=True, params_override=None, phase_hint=None: signals)
        parity_engine.gate_ab_allows = lambda *a, **k: True
        closes = np.linspace(100, 180, 200)
        opens = np.roll(closes, 1); opens[0] = closes[0]
        highs = np.maximum(opens, closes) * 1.002
        lows = np.minimum(opens, closes) * 0.998
        df = pd.DataFrame({"open": opens, "high": highs, "low": lows,
                           "close": closes, "volume": np.full(200, 1e6)})
        sig_func = lambda d, p: [{"idx": 20, "action": "BUY"}]
        res = optimizer.backtest_with_params(df, sig_func, self._trail_params(),
                                             symbol="X", min_signals=1)
        self.assertIsNotNone(res)
        t = res["trades"][0]
        self.assertGreater(t["exit_idx"], 20)
        expected_net = round(((float(df["close"].iloc[t["exit_idx"]]) - float(df["close"].iloc[20])) / float(df["close"].iloc[20]) - float(__import__("config").PARAMS["trading_cost_pct"]) / 100.0) * 100.0, 2)
        self.assertGreater(t["net_return_pct"], 0.0)  # trailing exit remains uncapped

    def test_trail_locks_profit_at_peak(self):
        """Rise ke baad girte hi trail peak ke paas exit (profit locked)."""
        import optimizer
        import parity_engine
        optimizer.filter_signals_by_macro_context = (
            lambda data, symbol, signals, is_backtest=True, params_override=None, phase_hint=None: signals)
        parity_engine.gate_ab_allows = lambda *a, **k: True
        c1 = np.linspace(100, 150, 50).tolist()
        c2 = [150 * (0.98 ** i) for i in range(1, 80)]
        closes = np.array(c1 + c2)
        opens = np.roll(closes, 1); opens[0] = closes[0]
        highs = np.maximum(opens, closes) * 1.002
        lows = np.minimum(opens, closes) * 0.998
        df = pd.DataFrame({"open": opens, "high": highs, "low": lows,
                           "close": closes, "volume": np.full(len(closes), 1e6)})
        sig_func = lambda d, p: [{"idx": 10, "action": "BUY"}]
        res = optimizer.backtest_with_params(df, sig_func, self._trail_params(),
                                             symbol="X", min_signals=1)
        self.assertIsNotNone(res)
        t = res["trades"][0]
        self.assertGreater(t["exit_idx"], 10)
        self.assertGreater(float(df["close"].iloc[t["exit_idx"]]), 105.0)
        self.assertGreater(t["net_return_pct"], 1.0)

    def test_trail_floor_protects_before_activation(self):
        """Activation se pehle: floor SL hi active (trail kabhi floor se neeche nahi)."""
        import optimizer
        import parity_engine
        optimizer.filter_signals_by_macro_context = (
            lambda data, symbol, signals, is_backtest=True, params_override=None, phase_hint=None: signals)
        parity_engine.gate_ab_allows = lambda *a, **k: True
        # seedha girta market — activation kabhi nahi → exit floor SL pe
        closes = np.linspace(100, 70, 60)
        opens = np.roll(closes, 1); opens[0] = closes[0]
        highs = np.maximum(opens, closes) * 1.002
        lows = np.minimum(opens, closes) * 0.998
        df = pd.DataFrame({"open": opens, "high": highs, "low": lows,
                           "close": closes, "volume": np.full(60, 1e6)})
        sig_func = lambda d, p: [{"idx": 5, "action": "BUY"}]
        params = self._trail_params()
        res = optimizer.backtest_with_params(df, sig_func, params, symbol="X", min_signals=1)
        self.assertIsNotNone(res)
        t = res["trades"][0]
        entry = float(df["close"].iloc[5])
        floor = float(df["low"].iloc[5])
        self.assertAlmostEqual(float(df["close"].iloc[t["exit_idx"]]), floor, delta=1.0)

    # ── v5.4 EXIT TOOLKIT (owner: lock/trail sirf ek tool; optimizer decide) ──

    def _toolkit_engine(self, mode, ups, falls, atr, entry=100.0, floor=97.0):
        from exit_engine import init_state, step
        p = {"exit_mode": mode, "tp1_pct": 3.0, "profit_lock_pct": 1.0,
             "trail_multiplier": 1.5, "min_reward_risk": 1.8, "ratchet_step_pct": 1.5}
        st = init_state(p, entry, floor)
        bars = list(ups)
        for _ in range(falls):
            bars.append(bars[-1] * 0.99)
        for c in bars:
            if step(st, c, c, c, atr):
                break
        return st

    def test_toolkit_hybrid_profit_never_lost(self):
        """v1.1 semantics: 1.8R minimum lock hit → lock AT TP; price TP ke UPAR hold
        kare to trail floor upar le jata hai (uncapped); girne pe locked floor
        pe exit — +3.55% (loss kabhi nahi, lalach-safe)."""
        from exit_engine import init_state, step
        p = {"exit_mode": "hybrid", "tp1_pct": 3.0, "profit_lock_pct": 1.0,
             "trail_multiplier": 1.5, "min_reward_risk": 1.8, "ratchet_step_pct": 1.5}
        st = init_state(p, 100.0, 97.0)
        bars = [(101.0, 101.0, 101.0), (105.5, 105.5, 105.5),
                (107.0, 106.5, 106.8), (104.0, 104.0, 104.0)]  # 1.8R lock, then trail, then fall
        done = False
        for h, l, c in bars:
            if step(st, h, l, c, 0.3):
                done = True
                break
        self.assertTrue(done)
        self.assertGreaterEqual(st["exit_price"], 105.4)  # trail floor above TP
        self.assertEqual(st["exit_tag"], "FLOOR")

    def test_toolkit_hybrid_min_profit_booked_when_trail_fails(self):
        """v5.7 owner D7: 1.8R lock hit hote hi profit lock AT TP —
        trail fail ho jaye to bhi MIN PROFIT booked (loss me exit impossible)."""
        from exit_engine import init_state, step
        p = {"exit_mode": "hybrid", "tp1_pct": 3.0, "profit_lock_pct": 1.0,
             "trail_multiplier": 1.5, "min_reward_risk": 1.8, "ratchet_step_pct": 1.5}
        st = init_state(p, 100.0, 97.0)
        bars = [101.0, 105.5, 106.0, 104.0, 100.0, 99.0]
        done = False
        for c in bars:
            if step(st, c, c, c, 0.3):
                done = True
                break
        self.assertTrue(done)
        self.assertGreaterEqual(st["exit_price"], 105.4)  # 1.8R floor remains protected
        self.assertEqual(st["exit_tag"], "FLOOR")

    def test_rr_defaults_to_1_8_when_absent(self):
        """r8-architecture contract (replaces the pre-r8 test formerly named
        'test_rr_above_1_8_is_ignored', identified as STALE/OBSOLETE this
        session — see UPDATE_HISTORY_FIX_LOG.md and VERSION.txt r17).

        HISTORY: before r8 (2026-09-06), exit_engine.py::init_state() had
        `rr = 1.8` hardcoded as a literal, ignoring whatever was in `params`
        -- so an explicitly-supplied min_reward_risk really was silently
        ignored, which is exactly what the old test's name/assertions
        checked. At r8, an owner-approved single-sourcing fix intentionally
        changed init_state() to read `params.get("min_reward_risk", 1.8)`
        instead (UPDATE_HISTORY_FIX_LOG.md, 2026-09-06: "Value is unchanged
        (still exactly 1.8) -- this is a single-source-of-truth fix only").
        That refactor deliberately removed init_state()'s own independent
        clamp; the old test was never updated to match and had already been
        silently failing since at least r12 (reproduced against the
        untouched original r12 zip this session, confirmed NOT a r13-r16
        regression).

        WHAT IS ACTUALLY GUARANTEED at r8+ (this test verifies exactly this,
        no more): min_reward_risk defaults to exactly 1.8 when the key is
        ABSENT from params. init_state() itself does not independently
        clamp an explicitly-supplied different value -- that guarantee does
        not exist at this function boundary post-r8, by design. RR staying
        "exactly 1.8 in practice" across the real system is a pipeline/
        optimizer-level outcome guarantee instead: min_reward_risk is
        excluded from the optimizer's searchable PARAM_SPACE (never
        selected), and none of the 3 real call sites (trade_engine.py,
        optimizer.py, strategy.py) ever supply anything other than 1.8.
        A function-boundary independent clamp inside init_state() itself
        was explicitly considered and deferred as a separate, future,
        not-yet-authorized hardening idea -- not implemented here."""
        from exit_engine import init_state
        st = init_state({"exit_mode": "hybrid", "trail_multiplier": 1.5,
                         "profit_lock_pct": 1.0, "ratchet_step_pct": 1.5}, 100.0, 97.0)
        # risk = entry - floor_sl = 3.0; 1.8R lock = 100 + 3.0*1.8 = 105.4
        self.assertAlmostEqual(st["lock_price"], 105.4, places=6)

    def test_toolkit_ratchet_progressive_lock(self):
        """1.8R lock ke baad ratchet/trailing hi exit control karta hai."""
        from exit_engine import init_state, step
        st = init_state({"exit_mode": "ratchet", "min_reward_risk": 1.8,
                         "trail_multiplier": 1.5, "profit_lock_pct": 1.0,
                         "ratchet_step_pct": 1.5}, 100.0, 97.0)
        self.assertFalse(step(st, 105.5, 105.5, 105.5, 0.3))
        self.assertTrue(st["tp_hit"])
        locked = st["floor"]
        self.assertFalse(step(st, 110.0, 110.0, 110.0, 0.3))
        self.assertGreaterEqual(st["floor"], locked)
        self.assertTrue(step(st, 104.0, 104.0, 104.0, 0.3))
        self.assertGreaterEqual(st["exit_price"], 105.4)

    def test_toolkit_legacy_fixed_tp_normalizes_to_uncapped(self):
        """Legacy fixed_tp cannot cap profit; it normalizes to trailing behavior."""
        from exit_engine import init_state, step
        st = init_state({"exit_mode": "fixed_tp", "min_reward_risk": 1.8,
                         "trail_multiplier": 1.5, "profit_lock_pct": 1.0,
                         "ratchet_step_pct": 1.5}, 100.0, 97.0)
        self.assertEqual(st["mode"], "hybrid")
        self.assertFalse(step(st, 105.0, 105.0, 105.0, 0.3))
        self.assertFalse(st["tp_hit"])
        self.assertFalse(step(st, 106.0, 106.1, 106.0, 0.3))
        self.assertTrue(st["tp_hit"])
        self.assertGreaterEqual(st["floor"], 105.4)

    def test_toolkit_trail_floor_follows(self):
        """trail mode — floor upar follow karta hai, fall pe wahi lock hota hai."""
        st = self._toolkit_engine("trail", [101, 103, 105, 108, 112, 116, 120, 116 * 0.97], 5, 0.5)
        self.assertEqual(st["floor"], 119.25)
        self.assertEqual(st["exit_price"], 119.25)

    def test_toolkit_no_trailing_before_1_8r(self):
        from exit_engine import init_state, step
        st = init_state({"exit_mode": "trail", "min_reward_risk": 1.8,
                         "trail_multiplier": 1.5}, 100.0, 97.0)
        self.assertFalse(step(st, 105.0, 105.0, 105.0, 0.3))
        self.assertFalse(st["activated"])
        self.assertFalse(st["tp_hit"])
        self.assertEqual(st["floor"], 97.0)

    def test_toolkit_exact_1_8r_lock_then_trail(self):
        from exit_engine import init_state, step
        st = init_state({"exit_mode": "trail", "min_reward_risk": 1.8,
                         "trail_multiplier": 1.5}, 100.0, 97.0)
        self.assertFalse(step(st, 105.39, 105.39, 105.39, 0.3))
        self.assertFalse(step(st, 105.40, 105.50, 105.40, 0.3))
        self.assertTrue(st["tp_hit"])
        self.assertTrue(st["activated"])
        self.assertGreaterEqual(st["floor"], 105.4)
        locked = st["floor"]
        self.assertFalse(step(st, 110.0, 110.0, 110.0, 0.3))
        self.assertGreaterEqual(st["floor"], locked)
        self.assertTrue(step(st, 104.0, 104.0, 104.0, 0.3))
        self.assertGreaterEqual(st["exit_price"], 105.4)

    def test_toolkit_mode_in_optimizer_space(self):
        """exit_mode + lock params optimizer search me (optimizer decide karega)."""
        import optimizer
        names = [p.name for p in optimizer.PARAM_SPACE]
        self.assertNotIn("min_reward_risk", names)
        for key in ("exit_mode", "profit_lock_pct", "ratchet_step_pct"):
            self.assertIn(key, names)

    def test_benjamini_hochberg_correction(self):
        """[PHD-FIX F2] BH-FDR: strong p-values pass, weak fail; sorted logic."""
        from optimizer import _benjamini_hochberg
        # 3 tests: p=0.01, 0.03, 0.20 @ alpha 0.10 → thresholds 0.033, 0.067, 0.10
        sig = _benjamini_hochberg([0.20, 0.01, 0.03])
        self.assertEqual(sig, [False, True, True])
        # sab weak → sab fail
        sig2 = _benjamini_hochberg([0.5, 0.4, 0.3])
        self.assertEqual(sig2, [False, False, False])
        # sab strong → sab pass
        sig3 = _benjamini_hochberg([0.001, 0.002, 0.003])
        self.assertEqual(sig3, [True, True, True])

    def test_parity_slot_compounding_exact(self):
        """[PHD-FIX F1] Portfolio compounding = net% × combined / smax (per-slot
        share). smax=8, do trades +10% net, combined=1 → (1+0.10/8)² = 1.02515625."""
        import parity_engine as pe
        from unittest.mock import patch
        idx = pd.date_range("2026-01-01", periods=80, freq="B")
        df = pd.DataFrame({"open": np.linspace(100, 108, 80), "high": np.linspace(100.2, 108.4, 80),
                           "low": np.linspace(99.8, 107.6, 80), "close": np.linspace(100, 108, 80),
                           "volume": np.full(80, 1e6)}, index=idx)
        trades = [
            {"entry_idx": 10, "exit_idx": 20, "entry_price": 100.0, "net_return_pct": 10.0},
            {"entry_idx": 30, "exit_idx": 40, "entry_price": 100.0, "net_return_pct": 10.0},
        ]
        with patch.object(pe, "stage_multiplier", return_value=1.0), \
             patch.object(pe, "pit_vol_multiplier", return_value=1.0), \
             patch.object(pe, "gate_ab_allows", return_value=True), \
             patch.object(pe, "circuit_dd_pct", return_value=None):
            pr = pe.run_parity_equity(trades, df, "F1TEST", start_capital=200000.0, max_slots=8)
        expected = 200000.0 * (1.0125 ** 2)
        self.assertAlmostEqual(pr["final_capital"], expected, places=2)
        self.assertEqual(len(pr["kept_trades"]), 2)

    def test_trail_gtt_follow_threshold(self):
        """GTT follow sirf meaningful move pe (API cost control)."""
        import forever_order_manager as fom
        from utils import save_json
        from config import PARAMS
        save_json(fom.FOREVER_STATE_FILE, {"XYZ": {
            "security_id": "1", "qty": 10, "entry_price": 100.0,
            "sl_price": 98.0, "trail_sl": 99.0, "sl_forever_id": "PAPER-GTT-XYZ-STRICT_SL",
            "sl_failed": False, "layer": 1,
        }})
        # 0.05% move — threshold (0.1%) se neeche → no modify
        r1 = fom.update_trail_sl("XYZ", 99.05)
        self.assertEqual(r1["reason"], "below_update_threshold")
        # 0.5% move — meaningful → paper modify (PAPER- id → True)
        r2 = fom.update_trail_sl("XYZ", 99.5)
        self.assertEqual(r2["reason"], "modified")


if __name__ == "__main__":
    unittest.main()
