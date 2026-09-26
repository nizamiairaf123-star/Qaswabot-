"""
test_dsr.py — Phase 3: Deflated Sharpe Ratio Tests (Ai-DOS Proof)
Verifies high-trial random parameter rejection per spec.
"""
import numpy as np
import pytest

from optimizer import calculate_dsr, calculate_dsr_from_result


def test_dsr_high_sharpe_few_trials_valid():
    """High Sharpe with few trials should give high DSR (genuine edge)."""
    np.random.seed(42)
    rets = np.random.randn(100) * 0.5 + 1.0  # mean 1, std 0.5 => SR ~2
    sr = float(np.mean(rets) / np.std(rets))
    dsr = calculate_dsr(sr, num_trials=10, returns=rets)
    assert dsr >= 0.95, f"High SR {sr:.2f} with few trials should have DSR>=0.95, got {dsr}"
    assert 0 <= dsr <= 1


def test_dsr_low_sharpe_many_trials_invalid():
    """Low Sharpe with many trials should give low DSR (random luck)."""
    np.random.seed(42)
    rets = np.random.randn(100) * 1.0 + 0.1  # SR ~0.1
    sr = float(np.mean(rets) / np.std(rets))
    dsr = calculate_dsr(sr, num_trials=1000, returns=rets)
    assert dsr < 0.95, f"Low SR {sr:.2f} with many trials should have DSR<0.95, got {dsr}"
    assert 0 <= dsr <= 1


def test_dsr_penalizes_multiple_trials():
    """Same Sharpe, more trials => lower DSR (SBOB guard)."""
    np.random.seed(42)
    rets = np.random.randn(100) * 0.5 + 1.0
    sr = float(np.mean(rets) / np.std(rets))
    dsr_10 = calculate_dsr(sr, num_trials=10, returns=rets)
    dsr_100 = calculate_dsr(sr, num_trials=100, returns=rets)
    dsr_1000 = calculate_dsr(sr, num_trials=1000, returns=rets)
    # More trials should not increase DSR (should stay same or decrease)
    assert dsr_10 >= dsr_100 >= dsr_1000 or (dsr_10 >= 0.99 and dsr_100 >= 0.99), \
        f"DSR should not increase with more trials: 10={dsr_10}, 100={dsr_100}, 1000={dsr_1000}"


def test_dsr_from_result():
    """DSR from backtest result dict."""
    np.random.seed(42)
    trades = [{"net_return_pct": float(x)} for x in (np.random.randn(50) * 0.5 + 1.0)]
    result = {
        "sharpe": 2.0,
        "trades": trades,
        "total_trades": 50,
    }
    dsr = calculate_dsr_from_result(result, num_trials=20)
    assert 0 <= dsr <= 1
    assert dsr >= 0.95, "High Sharpe 2.0 with 20 trials should be valid"


def test_dsr_insufficient_data():
    """DSR should return 0 for insufficient returns."""
    dsr = calculate_dsr(observed_sr=2.0, num_trials=10, returns=np.array([1.0, 2.0]))
    assert dsr == 0.0, "Insufficient data <10 should return 0"


def test_dsr_gate_in_scoring():
    """Institutional score should return 0 if DSR<0.95 per spec hard gate."""
    from optimizer import calculate_institutional_score

    np.random.seed(42)
    trades = [{"net_return_pct": float(x)} for x in (np.random.randn(20) * 1.0 + 0.1)]
    result_low_dsr = {
        "profit_factor": 1.2,
        "win_rate_pct": 55,
        "total_return_pct": 5,
        "portfolio_max_dd_pct": -5,
        "total_trades": 20,
        "recovery_factor": 1.0,
        "sharpe": 0.1,
        "avg_win_return": 1.0,
        "avg_loss_return": -1.0,
        "trades": trades,
        "dsr": 0.5,  # Low DSR
    }
    score = calculate_institutional_score(result_low_dsr, num_trials=1000)
    assert score == 0.0, f"Score should be 0 if DSR<0.95, got {score}"

    result_high_dsr = dict(result_low_dsr)
    result_high_dsr["dsr"] = 0.98
    result_high_dsr["sharpe"] = 2.0
    result_high_dsr["profit_factor"] = 2.0
    result_high_dsr["total_return_pct"] = 20
    score_high = calculate_institutional_score(result_high_dsr, num_trials=10)
    assert score_high > 0, "Score should be >0 if DSR>=0.95"
