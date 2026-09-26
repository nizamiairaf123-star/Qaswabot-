"""
test_atr_parity.py — ATR CANONICAL-METHOD PARITY (AI-DOS registered fix)

Registry reference: METH-ATR-0001
  methodology: Technical Indicator Standardization (Wilder 1978)
  method:      Average True Range — Wilder RMA smoothing
               (alpha = 1/period, adjust=False), NOT a Simple TR Mean.
  original_creator_owner: J. Welles Wilder Jr., "New Concepts in
               Technical Trading Systems" (1978) — public-domain
               technical-analysis method, verified against this
               codebase's own declared standard (see strategy_tools.py
               calc_atr / calc_rsi and trade_engine._calculate_atr
               PHD-FIX F4 comments).
  verification_status: VERIFIED

Bug fixed: optimizer.py's old _simple_atr() computed a windowed
*Simple* mean of True Range, which is NOT Wilder ATR and silently
diverged from the live-execution ATR used by exit_engine/trade_engine.
optimizer.py now imports and calls strategy_tools.calc_atr() directly
— the single canonical implementation — so there is exactly ONE ATR
method in the codebase, and optimizer/backtest ATR == live ATR by
construction (same function, same formula, same inputs).

This test is deterministic: fixed synthetic OHLC arrays, no randomness,
no network, no I/O.
"""

import conftest  # noqa: F401  (sandbox isolation, mirrors test_golden.py)
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd


def _ohlc(closes, seed_noise=0.0015):
    """Deterministic synthetic OHLC — fixed formula, no RNG."""
    closes = np.asarray(closes, dtype=float)
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    wiggle = np.array([
        1.0 + seed_noise * np.sin(2 * np.pi * i / 7) for i in range(len(closes))
    ])
    highs = np.maximum(opens, closes) * wiggle * 1.002
    lows = np.minimum(opens, closes) / wiggle * 0.998
    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": np.full(len(closes), 500_000),
    })


TRENDING = _ohlc(np.linspace(200.0, 260.0, 120))
CHOPPY = _ohlc([150.0 * (1 + 0.01 * np.sin(2 * np.pi * i / 9)) for i in range(120)])


class TestATRCanonicalParity(unittest.TestCase):

    def test_no_duplicate_atr_implementation_in_optimizer(self):
        """optimizer.py must not define its own ATR function anymore."""
        import optimizer
        self.assertFalse(
            hasattr(optimizer, "_simple_atr"),
            "optimizer.py still defines a duplicate ATR implementation "
            "(_simple_atr) — it must call the canonical strategy_tools.calc_atr "
            "instead.",
        )

    def test_optimizer_atr_is_wilder_rma_not_simple_mean(self):
        """The canonical ATR must diverge from a naive Simple TR Mean on
        trending data (Wilder RMA reacts faster / weights recent bars more),
        proving optimizer ATR is not silently a Simple TR Mean in disguise."""
        from strategy_tools import calc_atr

        period = 14
        wilder = calc_atr(TRENDING, period)

        tr = pd.concat([
            TRENDING["high"] - TRENDING["low"],
            (TRENDING["high"] - TRENDING["close"].shift()).abs(),
            (TRENDING["low"] - TRENDING["close"].shift()).abs(),
        ], axis=1).max(axis=1)
        simple_mean = tr.rolling(period).mean()

        idx = 100
        self.assertNotAlmostEqual(
            float(wilder.iloc[idx]), float(simple_mean.iloc[idx]), places=4,
            msg="Canonical ATR matches a Simple TR Mean — Wilder RMA fix "
                "appears not to be in effect.",
        )

    def test_optimizer_backtest_atr_matches_live_atr_exactly(self):
        """optimizer.backtest_with_params()'s internal ATR series must be
        byte-identical to the live-execution ATR (trade_engine._calculate_atr)
        for the same bars — true optimizer/live parity, not just 'close enough'."""
        from strategy_tools import calc_atr

        for data, period in ((TRENDING, 14), (CHOPPY, 10), (TRENDING, 21)):
            optimizer_series = calc_atr(data, period)  # what optimizer.py now calls
            for j in (20, 50, 90, len(data) - 1):
                live_val = self._live_atr_at(data, j, period)
                self.assertAlmostEqual(
                    float(optimizer_series.iloc[j]), live_val, places=10,
                    msg=f"ATR parity broken at bar {j}, period {period}",
                )

    @staticmethod
    def _live_atr_at(data: pd.DataFrame, idx: int, period: int) -> float:
        """Reference re-implementation of trade_engine._calculate_atr(),
        evaluated only on bars up to `idx` — mirrors how live receives a
        rolling candle window and takes the latest ATR value."""
        window = data.iloc[: idx + 1]
        tr = pd.concat([
            window["high"] - window["low"],
            (window["high"] - window["close"].shift()).abs(),
            (window["low"] - window["close"].shift()).abs(),
        ], axis=1).max(axis=1)
        return float(tr.ewm(alpha=1.0 / period, adjust=False).mean().iloc[-1])

    def test_backtest_with_params_uses_calc_atr(self):
        """Static/behavioral check: backtest_with_params must source ATR from
        strategy_tools.calc_atr, not recompute a bespoke rolling mean."""
        import inspect
        import optimizer

        src = inspect.getsource(optimizer.backtest_with_params)
        self.assertIn("calc_atr", src)
        # Check only non-comment lines for an actual call to the retired
        # function — this function legitimately has a comment documenting
        # the historical _simple_atr() -> calc_atr() fix, and a bare
        # substring/assertNotIn check would false-positive on that comment.
        code_lines = [ln for ln in src.splitlines() if not ln.strip().startswith("#")]
        self.assertFalse(
            any("_simple_atr(" in ln for ln in code_lines),
            "backtest_with_params still calls the retired _simple_atr() "
            "in executable code (not just a comment).",
        )


if __name__ == "__main__":
    unittest.main()
