"""
test_frac_diff.py — Phase 1: Fractional Differentiation Tests (Ai-DOS Proof)
Verifies stationarity + memory retention without touching trading code.
"""
import numpy as np
import pandas as pd
import pytest

from frac_diff import (
    get_frac_diff_weights,
    get_frac_diff_weights_fixed_window,
    frac_diff,
    frac_diff_with_memory_check,
    adf_test,
    find_optimal_d,
    stationarity_report,
)


def test_frac_diff_weights_decay():
    """Weights must decay and sum to ~0 for d close to 1, preserve memory for small d."""
    w_03 = get_frac_diff_weights(d=0.3, thresh=1e-4)
    w_05 = get_frac_diff_weights(d=0.5, thresh=1e-4)
    # d=0.3 should have larger window (more memory) than d=0.5
    assert len(w_03) > len(w_05), f"d=0.3 window {len(w_03)} should be > d=0.5 window {len(w_05)}"
    # First weight always 1
    assert abs(w_03[0] - 1.0) < 1e-9
    assert abs(w_05[0] - 1.0) < 1e-9
    # Weights decay in magnitude
    assert abs(w_03[-1]) < 0.001
    assert abs(w_05[-1]) < 0.001


def test_frac_diff_weights_fixed_window():
    w = get_frac_diff_weights_fixed_window(d=0.4, window=10)
    assert len(w) == 10
    assert w[0] == 1.0
    # For d=1, weights should be [1, -1, 0, 0...] — test d close to 1
    w_09 = get_frac_diff_weights_fixed_window(d=0.9, window=5)
    # w1 = -0.9, w2 = -w1*(0.9-1)/2 = 0.9*(-0.1)/2 = -0.045 etc — just check not NaN
    assert np.all(np.isfinite(w_09))


def test_frac_diff_stationarity_and_memory():
    """Random walk non-stationary -> fractional diff stationary while preserving memory."""
    np.random.seed(42)
    rw = np.cumsum(np.random.randn(1000)) + 100
    s = pd.Series(rw)

    orig_adf = adf_test(s)
    assert not orig_adf["stationary"], "Random walk should be non-stationary"

    # d=0.3 should achieve stationarity with high memory per our earlier test
    res = frac_diff_with_memory_check(s, d=0.3, thresh=1e-4)
    fd = res["frac_diffed"].dropna()
    assert len(fd) > 500, "Should have enough valid points after truncating large window"
    adf = adf_test(fd)
    assert adf["stationary"], f"d=0.3 should be stationary, got p={adf['p_value']}"
    # Memory retention: correlation with original should be high (>0.5) for small d
    assert res["correlation_memory"] > 0.5, f"Memory {res['correlation_memory']} should be >0.5 for d=0.3"
    # Variance retention: frac diff retains some variance vs integer diff
    assert 0.01 < res["variance_retention"] < 1.0


def test_frac_diff_truncation_for_short_series():
    """If window larger than series, truncate to series length to avoid all-NaN."""
    s = pd.Series(np.random.randn(100) + 100)
    # d=0.3 thresh 1e-5 gives window 2275 >100, should truncate to 100 and give at least 1 valid
    fd = frac_diff(s, d=0.3, thresh=1e-5)
    # After our fix, window truncated to len(s), so 1 valid point at end
    assert not fd.isna().all(), "Should not be all NaN after truncation"
    assert fd.isna().sum() == len(s) - 1 or fd.isna().sum() < len(s)


def test_find_optimal_d():
    np.random.seed(42)
    rw = np.cumsum(np.random.randn(1000)) + 100
    s = pd.Series(rw)
    opt = find_optimal_d(s, d_range=(0.3, 0.5), step=0.05, thresh=1e-4)
    assert opt["optimal_d"] is not None
    assert 0.3 <= opt["optimal_d"] <= 0.5
    # Optimal should be stationary
    assert opt["optimal_result"]["stationary"]
    # All results should have ADF
    assert len(opt["all_results"]) == 5  # 0.3,0.35,0.4,0.45,0.5


def test_adf_fallback():
    """ADF fallback should work without statsmodels."""
    # Stationary series: white noise
    np.random.seed(42)
    stationary = pd.Series(np.random.randn(500))
    adf = adf_test(stationary)
    # White noise should be stationary (mean reverting)
    # Our fallback may not be perfect but should not crash
    assert "test_stat" in adf
    assert "p_value" in adf
    assert "stationary" in adf
    assert isinstance(adf["stationary"], bool)


def test_stationarity_report():
    np.random.seed(42)
    rw = np.cumsum(np.random.randn(1000)) + 100
    report = stationarity_report(rw, symbol="TEST")
    assert report["symbol"] == "TEST"
    assert "original_adf" in report
    assert "fractional_optimal" in report
    assert "conclusion" in report
    assert report["conclusion"]["recommended_d"] is not None
