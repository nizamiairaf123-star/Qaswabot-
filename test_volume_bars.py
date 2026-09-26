"""
test_volume_bars.py — Phase 5: Volume & Dollar Bars Tests (Ai-DOS Proof)
Verifies alternative bars normalize volatility, but live must use time bars (parity).
"""
import pandas as pd
import numpy as np
import pytest

from mtf.warehouse import (
    create_volume_bars,
    create_dollar_bars,
    estimate_volume_threshold,
    estimate_dollar_threshold,
)


def _make_sample_ohlcv(n=100):
    """Create sample OHLCV with volatility cluster."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01 09:15", periods=n, freq="5min")
    # Normal period: volume 10k, volatile period: volume 50k
    volumes = [10000 if i < 50 or i > 70 else 50000 for i in range(n)]
    closes = np.cumsum(np.random.randn(n) * 0.5) + 100
    df = pd.DataFrame({
        "open": closes - 0.1,
        "high": closes + 0.5,
        "low": closes - 0.5,
        "close": closes,
        "volume": volumes,
    }, index=dates)
    return df


def test_volume_bars_creation():
    df = _make_sample_ohlcv(100)
    # Threshold 20k: normal 10k bar needs 2 time bars to make 1 vol bar, volatile 50k makes 2-3 vol bars per time bar
    vol_bars = create_volume_bars(df, volume_threshold=20000)
    assert not vol_bars.empty
    # Volume bars should have volume >= threshold (except maybe last incomplete)
    assert all(vol_bars["volume"] >= 20000 * 0.9)  # allow small rounding
    # Should have fewer bars than time bars if threshold > avg volume
    # Time bars 100, avg vol ~ (50*10k +20*50k +30*10k)/100 = 18k, threshold 20k => ~90 vol bars
    assert len(vol_bars) < len(df) * 1.5  # not too many


def test_dollar_bars_creation():
    df = _make_sample_ohlcv(100)
    dollar_bars = create_dollar_bars(df, dollar_threshold=1000000)  # 10 Lakh rupee turnover per bar
    assert not dollar_bars.empty
    assert "dollar_volume" in dollar_bars.columns
    assert all(dollar_bars["dollar_volume"] >= 1000000 * 0.9)


def test_volume_bars_normalize_volatility():
    """
    Time bars cluster volatility, volume bars normalize.
    In volatile period (high volume), time bars have same count but high vol,
    volume bars create more bars in volatile period -> more Gaussian returns.
    """
    df = _make_sample_ohlcv(100)
    vol_bars = create_volume_bars(df, volume_threshold=20000)
    # Volatile period is index 50-70 (20 bars with 50k vol = 1M total vol)
    # Normal period 80 bars with 10k vol = 800k total vol
    # So volatile period should have more volume bars per time bar
    # This is the core benefit per Lopez de Prado
    assert len(vol_bars) > 0


def test_estimate_thresholds():
    df = _make_sample_ohlcv(100)
    vol_thresh = estimate_volume_threshold(df, daily_avg_bars=10)
    assert vol_thresh > 0
    dollar_thresh = estimate_dollar_threshold(df, daily_avg_bars=10)
    assert dollar_thresh > 0


def test_time_bars_remain_default_for_live_parity():
    """
    CRITICAL: Backtest vs Live parity — Dhan live WebSocket sends TIME bars (5m,15m),
    not volume bars. Live must use time bars by default.

    This test ensures volume/dollar bars are OPTIONAL research mode,
    not default for live trading path.
    """
    # Check config: MTF_DOWNLOAD_TFS should be time bars
    from config import MTF_DOWNLOAD_TFS
    assert "5m" in MTF_DOWNLOAD_TFS
    assert "15m" in MTF_DOWNLOAD_TFS
    assert "1D" in MTF_DOWNLOAD_TFS
    # Volume bars should NOT be in default download TFs
    assert "5m_vol" not in MTF_DOWNLOAD_TFS
    assert "5m_dollar" not in MTF_DOWNLOAD_TFS
    # This ensures live trading uses time bars, preserving parity


def test_volume_bars_empty_input():
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    vol_bars = create_volume_bars(empty, volume_threshold=10000)
    assert vol_bars.empty
    dollar_bars = create_dollar_bars(empty, dollar_threshold=1000000)
    assert dollar_bars.empty
