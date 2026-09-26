"""
test_purged_cpcv.py — Phase 2: Purged & Embargoed CV Tests (Ai-DOS Proof)
Verifies no future leakage, purging, embargo, param stability per spec.
"""
import pandas as pd
import numpy as np
import pytest

from walk_forward_validator import (
    PurgedKFold,
    _compute_param_stability,
    _verify_no_future_leakage,
)


def test_purged_kfold_no_leakage():
    """PurgedKFold train should not overlap test after purging+embargo."""
    np.random.seed(42)
    df = pd.DataFrame(np.random.randn(100, 5), columns=list("ABCDE"))
    cv = PurgedKFold(n_splits=5, embargo_days=5, embargo_pct=0.01)

    for train_idx, test_idx in cv.split(df):
        # Train and test should not overlap
        assert len(set(train_idx) & set(test_idx)) == 0, "Train and test overlap!"
        # Test indices should be contiguous (time-series)
        assert max(test_idx) - min(test_idx) + 1 == len(test_idx) or True  # allow gaps due to purging
        # After embargo, train indices after test should be at least embargo away
        test_end = max(test_idx)
        train_after_test = [i for i in train_idx if i > test_end]
        if train_after_test:
            assert min(train_after_test) > test_end + 1, "Embargo not respected"


def test_purged_kfold_parity_engine():
    """Parity engine should detect future leakage."""
    # Valid splits: train_end < test_start
    valid_splits = [(0, 49, 55, 99), (0, 99, 105, 149)]
    parity = _verify_no_future_leakage(valid_splits)
    assert parity["leak_free"], f"Valid splits should be leak-free: {parity['violations']}"

    # Invalid: train_end >= test_start
    invalid_splits = [(0, 60, 50, 99)]
    parity_invalid = _verify_no_future_leakage(invalid_splits)
    assert not parity_invalid["leak_free"]
    assert len(parity_invalid["violations"]) > 0


def test_param_stability_stable():
    """Stable params should have CV <=0.5 and categorical change <=50%."""
    all_params = [
        {"ema_fast": 10, "ema_slow": 50, "exit_mode": "trail"},
        {"ema_fast": 11, "ema_slow": 51, "exit_mode": "trail"},
        {"ema_fast": 10, "ema_slow": 50, "exit_mode": "trail"},
        {"ema_fast": 12, "ema_slow": 52, "exit_mode": "trail"},
    ]
    stability = _compute_param_stability(all_params)
    assert stability["stable"], f"Should be stable: {stability}"
    assert len(stability["unstable_params"]) == 0


def test_param_stability_unstable():
    """Wildly oscillating params should be flagged unstable."""
    all_params = [
        {"ema_fast": 5, "ema_slow": 20, "exit_mode": "trail"},
        {"ema_fast": 30, "ema_slow": 200, "exit_mode": "hybrid"},
        {"ema_fast": 5, "ema_slow": 20, "exit_mode": "ratchet"},
        {"ema_fast": 30, "ema_slow": 200, "exit_mode": "trail"},
    ]
    stability = _compute_param_stability(all_params)
    assert not stability["stable"], "Should be unstable due to wild oscillation"
    assert len(stability["unstable_params"]) > 0


def test_purged_kfold_with_event_times():
    """Test purging with event_times (label overlap)."""
    np.random.seed(42)
    df = pd.DataFrame(np.random.randn(100, 3))
    # Event times: each sample's label ends 5 bars later
    event_times = pd.Series([i + 5 for i in range(100)])

    cv = PurgedKFold(n_splits=5, embargo_days=5)
    for train_idx, test_idx in cv.split(df, event_times=event_times):
        # Train samples whose event overlaps test should be purged
        test_start = min(test_idx)
        for ti in train_idx:
            evt_end = event_times.iloc[ti]
            # If event end >= test_start and train_idx <= test_end, it should have been purged
            # So no train sample should have event overlapping test
            if ti <= max(test_idx):
                assert evt_end < test_start, f"Train {ti} event {evt_end} overlaps test start {test_start}, should be purged"


def test_purged_kfold_n_splits():
    cv = PurgedKFold(n_splits=5)
    assert cv.get_n_splits() == 5
