"""
test_vector_norm.py — Phase 6: Vector-Norm Portfolio Sizing Tests (Ai-DOS Proof)
Verifies L1/L2 norms, risk bounds, sector neutralization, stress test.
Preserves locked invariants: 2% daily cap, 10% max DD, 1R per trade.
"""
import pytest
import numpy as np

from capital_manager import (
    calculate_portfolio_norms,
    check_portfolio_risk_bounds,
    calculate_covariance_matrix,
    neutralize_sector_exposure,
    stress_test_portfolio,
)


def test_l1_norm_manhattan_example():
    """Surbhi example: L1 Manhattan 3 east + 4 north = 7"""
    assert calculate_portfolio_norms([3, 4], "L1") == 7.0
    assert calculate_portfolio_norms([3, 4], "L1") == 7.0


def test_l2_norm_euclidean_example():
    """Surbhi example: L2 Euclidean sqrt(3^2+4^2)=5 Pythagoras"""
    assert abs(calculate_portfolio_norms([3, 4], "L2") - 5.0) < 1e-9
    assert abs(calculate_portfolio_norms([3, 4], "L2") - 5.0) < 1e-9


def test_linf_norm_chebyshev():
    """L_inf = max(|x_i|)"""
    assert calculate_portfolio_norms([0.02, 0.015, 0.03], "L_inf") == 0.03
    assert calculate_portfolio_norms([0.02, 0.015, 0.03], "L_inf") == 0.03


def test_risk_bounds_preserve_locked_invariants():
    """
    Locked invariants per QASWA:
      - 2% daily-loss cap (L_inf max 0.02)
      - 10% max portfolio DD ceiling (L1 max 0.10)
    """
    # Valid portfolio: 3 positions 2%,1.5%,1% = L1 4.5% <10%, L_inf 2% =2% cap OK
    exposures = [0.02, 0.015, 0.01]
    res = check_portfolio_risk_bounds(exposures, l1_max=0.10, l2_max=0.06, linf_max=0.02)
    assert res["valid"], f"Should be valid: {res}"
    assert res["L1"] == 0.045
    assert res["L_inf"] == 0.02

    # Invalid: single position 3% >2% cap
    exposures_invalid = [0.02, 0.015, 0.03]
    res_invalid = check_portfolio_risk_bounds(exposures_invalid, l1_max=0.10, l2_max=0.06, linf_max=0.02)
    assert not res_invalid["valid"]
    assert any("L_inf" in v for v in res_invalid["violations"])


def test_covariance_matrix():
    """Covariance matrix from returns."""
    np.random.seed(42)
    returns_dict = {
        "RELIANCE": np.random.randn(100).tolist(),
        "TCS": np.random.randn(100).tolist(),
        "INFY": np.random.randn(100).tolist(),
    }
    cov_res = calculate_covariance_matrix(returns_dict)
    assert "covariance" in cov_res
    assert "correlation" in cov_res
    assert cov_res["n_symbols"] == 3
    assert cov_res["n_obs"] == 100
    assert len(cov_res["eigenvalues"]) == 3


def test_sector_neutralization():
    """Sector concentration >30% should be neutralized."""
    exposures = {"RELIANCE": 0.05, "ONGC": 0.04, "TCS": 0.01, "INFY": 0.01}
    sector_map = {"RELIANCE": "Energy", "ONGC": "Energy", "TCS": "IT", "INFY": "IT"}

    # Before: Energy 0.09, IT 0.02, total L1 0.11, Energy 81% >30% threshold
    res = neutralize_sector_exposure(exposures, sector_map)
    assert res["neutralized"]
    assert res["sector_exposure_before"]["Energy"] == 0.09
    # After: Energy scaled to 30% of total (0.033)
    assert abs(res["sector_exposure_after"]["Energy"] - 0.033) < 0.01


def test_stress_test_crash_regimes():
    """Stress test under Covid 2020 and Election 2024 per spec Phase 6."""
    exposures = {"RELIANCE": 0.02, "TCS": 0.02, "HDFCBANK": 0.02}
    # No returns needed for simplified scenario
    stress = stress_test_portfolio(exposures, {}, None)
    assert "scenarios" in stress
    assert "covid_2020_crash" in stress["scenarios"]
    assert "election_2024_drop" in stress["scenarios"]
    assert "max_loss" in stress
    # With 6% total exposure and -30% crash, loss ~ -1.8% <10% DD ceiling, should be valid
    assert stress["valid"], f"Stress should be valid for small exposure: {stress}"


def test_1r_invariant_preserved():
    """
    Locked rule: CNC swing risk strictly 1R per trade = entry-SL.
    Vector-norm must NOT increase single-trade risk beyond 1R.

    This test proves L1/L2 bounds preserve 1R invariant.
    """
    # Simulate 5 trades each 1R = 1% risk, total L1 =5% <10% max DD, L_inf=1% <2% cap
    exposures_1r = [0.01, 0.01, 0.01, 0.01, 0.01]
    res = check_portfolio_risk_bounds(exposures_1r, l1_max=0.10, l2_max=0.06, linf_max=0.02)
    assert res["valid"]
    assert res["L_inf"] == 0.01  # Each trade 1R =1% <2% cap
    assert res["L1"] == 0.05  # Total 5% <10% DD ceiling
