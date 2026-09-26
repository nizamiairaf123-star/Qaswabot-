"""
frac_diff.py — Phase 1: Fractional Differentiation & ADF Stationarity (R40 / v6.1)
================================================================================
Governance: AI-DOS Strict Incremental Protocol
Impact Level: Lowest Risk — Standalone Additive Module, no trading code touched
Spec: QASWA v6.1 Universe Data Sync & Phased Evolution — Phase 1

Purpose:
  - Compute fractional difference of order d (0.3 <= d <= 0.5) using binomial expansion
  - Preserve long-term memory vs integer diff d=1 which destroys memory
  - Verify stationarity via Augmented Dickey-Fuller (ADF) p<0.05

Design:
  - Binomial weights: w0=1, w_k = -w_{k-1} * (d - k + 1)/k
  - Threshold cutoff: stop when |w_k| < thresh (e.g. 1e-5) or max_len reached
  - No dependency on broker.py / trade_engine.py / dd_policy.py (frozen)
  - Pure numpy/pandas/scipy — optional statsmodels if present, else fallback ADF

References (Surbhi methodology mapping):
  - Fractional Differentiation: Marcos Lopez de Prado — preserves memory while achieving stationarity
  - ADF test: stationarity gate p<0.05
  - Memory retention: correlation between original and frac-diffed series

Provenance:
  source -> retrieval -> period -> publication -> as_of -> transformation -> feature -> decision
  This module is transformation only — input is Dhan OHLCV (Dhan-exclusive per DATA_SOURCE_POLICY),
  output is stationary feature for downstream optimizer (Phase 2/3 gates).
  No synthetic data generated, no external fetch.

Verification Gate (per spec):
  - Standalone unit tests proving stationarity + memory retention without touching trading code
  - py_compile must return 0
  - pytest -q must remain 0 failures
  - Manifests regenerated, locked files untouched
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

# Optional statsmodels — if present use it, else fallback
try:
    from statsmodels.tsa.stattools import adfuller as _sm_adfuller
    _HAS_STATSMODELS = True
except Exception:
    _sm_adfuller = None
    _HAS_STATSMODELS = False

# ─────────────────────────────────────────────
# 1. Fractional Differentiation Weights
# ─────────────────────────────────────────────

def get_frac_diff_weights(d: float, thresh: float = 1e-4, max_len: int = 10000) -> np.ndarray:
    """
    Compute fractional differencing weights using binomial expansion.

    (1 - B)^d = sum_{k=0}^{inf} (-1)^k * binom(d, k) * B^k
    Recurrence: w0=1, w_k = -w_{k-1} * (d - k + 1)/k

    Args:
        d: fractional order 0 < d < 1, spec requires 0.3 <= d <= 0.5 for Phase 1
        thresh: cutoff threshold for |w_k|, stops when weight magnitude < thresh
        max_len: hard cap to avoid infinite loop

    Returns:
        np.ndarray of weights w0..w_{k-1}

    Example:
        d=0.4 -> weights decay slowly, preserving memory vs d=1 -> [1, -1, 0, 0...]
    """
    if not (0 < d < 1):
        raise ValueError(f"d must be in (0,1), got {d}")
    if thresh <= 0:
        raise ValueError("thresh must be >0")
    weights = [1.0]
    k = 1
    while k < max_len:
        w_k = -weights[-1] * (d - k + 1) / k
        if abs(w_k) < thresh:
            # Include last small weight? Spec says threshold cutoff — stop when < thresh
            # We exclude it to keep series finite, but keep history of cutoff
            break
        weights.append(w_k)
        k += 1
    return np.array(weights, dtype=np.float64)


def get_frac_diff_weights_fixed_window(d: float, window: int) -> np.ndarray:
    """
    Fixed-window weights (no threshold) — useful for memory analysis.
    """
    if not (0 < d < 1):
        raise ValueError(f"d must be in (0,1), got {d}")
    if window < 1:
        raise ValueError("window must be >=1")
    weights = [1.0]
    for k in range(1, window):
        w_k = -weights[-1] * (d - k + 1) / k
        weights.append(w_k)
    return np.array(weights, dtype=np.float64)


# ─────────────────────────────────────────────
# 2. Fractional Differentiation Transform
# ─────────────────────────────────────────────

def frac_diff(
    series: Union[pd.Series, np.ndarray, List[float]],
    d: float,
    thresh: float = 1e-4,
    max_len: Optional[int] = None,
) -> pd.Series:
    """
    Apply fractional differentiation to a price series.

    For each t: y_t = sum_{k=0}^{window-1} w_k * x_{t-k}
    where w_k are fractional weights.

    Preserves memory: unlike integer diff (d=1) which does x_t - x_{t-1} and loses long memory,
    fractional diff with d=0.3-0.5 keeps weighted history.

    Args:
        series: price series (close prices)
        d: fractional order 0.3-0.5 recommended
        thresh: weight cutoff
        max_len: optional max window override (default uses thresh)

    Returns:
        pd.Series of same index, with NaN for initial window where not enough history
    """
    if isinstance(series, list):
        series = pd.Series(series)
    elif isinstance(series, np.ndarray):
        series = pd.Series(series)
    elif not isinstance(series, pd.Series):
        series = pd.Series(series)

    if len(series) < 10:
        return pd.Series([np.nan] * len(series), index=series.index)

    if max_len is not None:
        weights = get_frac_diff_weights_fixed_window(d, max_len)
    else:
        weights = get_frac_diff_weights(d, thresh=thresh)

    # Truncate weights if window larger than series to avoid all-NaN (memory fix for short series)
    if len(weights) > len(series):
        weights = weights[: len(series)]

    window = len(weights)
    result = np.full(len(series), np.nan, dtype=np.float64)
    values = series.values.astype(np.float64)

    for t in range(window - 1, len(values)):
        window_vals = values[t - window + 1 : t + 1]
        result[t] = np.dot(window_vals[::-1], weights)

    return pd.Series(result, index=series.index)


def frac_diff_with_memory_check(
    series: Union[pd.Series, np.ndarray, List[float]],
    d: float,
    thresh: float = 1e-4,
) -> Dict:
    """
    Fractional diff + memory retention analysis.
    Returns dict with frac_diffed series, weights, correlation (memory), variance retention.
    """
    fd = frac_diff(series, d=d, thresh=thresh)
    orig = pd.Series(series) if not isinstance(series, pd.Series) else series

    # Align non-NaN
    valid_mask = ~fd.isna()
    if valid_mask.sum() < 10:
        corr = 0.0
        var_ret = 0.0
    else:
        orig_valid = orig[valid_mask]
        fd_valid = fd[valid_mask]
        # Correlation as memory proxy — higher corr = more memory retained
        try:
            corr = float(np.corrcoef(orig_valid.values, fd_valid.values)[0, 1])
            if np.isnan(corr):
                corr = 0.0
        except Exception:
            corr = 0.0
        # Variance retention: var(fd)/var(orig) — integer diff loses variance, frac retains some
        try:
            var_orig = float(np.var(orig_valid.values))
            var_fd = float(np.var(fd_valid.values))
            var_ret = var_fd / var_orig if var_orig > 1e-12 else 0.0
        except Exception:
            var_ret = 0.0

    weights = get_frac_diff_weights(d, thresh=thresh)

    return {
        "d": d,
        "weights": weights,
        "window": len(weights),
        "frac_diffed": fd,
        "correlation_memory": corr,
        "variance_retention": var_ret,
        "thresh": thresh,
    }


# ─────────────────────────────────────────────
# 3. ADF Stationarity Test (with statsmodels fallback)
# ─────────────────────────────────────────────

def _adf_fallback(series: Union[pd.Series, np.ndarray], autolag: int = 1) -> Dict:
    """
    Fallback ADF implementation when statsmodels not available.
    Simple ADF: Δy_t = α + γ*y_{t-1} + ε_t (no trend, 1 lag for simplicity)
    Test H0: γ=0 (unit root, non-stationary) vs H1: γ<0 (stationary)
    Returns approx test statistic and p-value via normal approximation + critical values.

    This is simplified — for production gate we use statsmodels if present.
    Fallback uses critical value -2.86 for 5% (no trend, ~500 obs) as gate.
    """
    try:
        y = pd.Series(series).dropna().values.astype(np.float64)
        if len(y) < 20:
            return {"test_stat": 0.0, "p_value": 1.0, "stationary": False, "method": "fallback_insufficient"}

        # Δy
        dy = np.diff(y)
        y_lag = y[:-1]

        # Align for autolag
        if autolag > 0:
            # Include lagged Δy terms: Δy_t = α + γ*y_{t-1} + sum_{i=1}^{autolag} δ_i*Δy_{t-i} + ε
            # Build X matrix
            # For simplicity, if len insufficient, reduce autolag
            max_lag = min(autolag, len(dy) // 3)
            # Prepare data
            # y_lag for Δy regression: y_{t-1} corresponds to dy_t
            # dy_lags: dy_{t-1}, dy_{t-2}, ...
            n = len(dy) - max_lag
            if n < 10:
                max_lag = 0
                n = len(dy)

            if max_lag == 0:
                X = np.column_stack([np.ones(len(dy)), y_lag[: len(dy)]])
                Y = dy
            else:
                # Y = dy[max_lag:]
                Y = dy[max_lag:]
                # X: const, y_lag, dy_lags
                y_lag_aligned = y_lag[max_lag : max_lag + len(Y)]
                X_cols = [np.ones(len(Y)), y_lag_aligned]
                for lag in range(1, max_lag + 1):
                    X_cols.append(dy[max_lag - lag : -lag if lag > 0 else None][: len(Y)])
                X = np.column_stack(X_cols)
        else:
            X = np.column_stack([np.ones(len(dy)), y_lag[: len(dy)]])
            Y = dy

        # OLS: beta = (X'X)^-1 X'Y
        try:
            XtX = X.T @ X
            XtY = X.T @ Y
            beta = np.linalg.solve(XtX, XtY)
            residuals = Y - X @ beta
            s2 = np.sum(residuals**2) / (len(Y) - X.shape[1])
            var_beta = s2 * np.linalg.inv(XtX)
            se_beta = np.sqrt(np.diag(var_beta))
            # gamma is coefficient of y_{t-1} which is at index 1
            gamma = beta[1]
            se_gamma = se_beta[1]
            if se_gamma < 1e-12:
                t_stat = 0.0
            else:
                t_stat = gamma / se_gamma
        except Exception:
            return {"test_stat": 0.0, "p_value": 1.0, "stationary": False, "method": "fallback_linalg_fail"}

        # Critical values for ADF (approx, no trend):
        # 1% ~ -3.43, 5% ~ -2.86, 10% ~ -2.57 (for large samples)
        # We use 5% = -2.86 as gate per spec p<0.05
        # Approx p-value via normal: very rough, but for gate we use test_stat threshold
        # More accurate p via: if t_stat < -3.43 => p<0.01, < -2.86 => p<0.05, < -2.57 => p<0.10 else >0.10
        if t_stat < -3.43:
            p_approx = 0.01
        elif t_stat < -2.86:
            p_approx = 0.03
        elif t_stat < -2.57:
            p_approx = 0.08
        else:
            p_approx = 0.20

        stationary = t_stat < -2.86  # 5% gate

        return {
            "test_stat": float(t_stat),
            "p_value": float(p_approx),
            "stationary": bool(stationary),
            "critical_5pct": -2.86,
            "method": "fallback_ols",
            "gamma": float(gamma),
        }
    except Exception as e:
        return {"test_stat": 0.0, "p_value": 1.0, "stationary": False, "method": f"fallback_error:{type(e).__name__}", "error": str(e)}


def adf_test(series: Union[pd.Series, np.ndarray, List[float]], autolag: int = 1) -> Dict:
    """
    Augmented Dickey-Fuller test wrapper.
    Uses statsmodels if available, else fallback OLS.

    Returns dict: test_stat, p_value, stationary (p<0.05), method
    """
    try:
        s = pd.Series(series).dropna()
        if len(s) < 20:
            return {"test_stat": 0.0, "p_value": 1.0, "stationary": False, "method": "insufficient_data", "n": len(s)}

        if _HAS_STATSMODELS and _sm_adfuller is not None:
            try:
                # adfuller returns (test_stat, p_value, lags, nobs, crit_values, icbest)
                res = _sm_adfuller(s.values, autolag=autolag, regression='c')  # constant, no trend
                test_stat, p_value = float(res[0]), float(res[1])
                crit = res[4] if len(res) > 4 else {}
                stationary = p_value < 0.05
                return {
                    "test_stat": test_stat,
                    "p_value": p_value,
                    "stationary": stationary,
                    "critical_values": crit,
                    "method": "statsmodels",
                    "n": len(s),
                }
            except Exception as e:
                # Fall back
                fb = _adf_fallback(s, autolag=autolag)
                fb["statsmodels_error"] = str(e)
                return fb
        else:
            return _adf_fallback(s, autolag=autolag)
    except Exception as e:
        return {"test_stat": 0.0, "p_value": 1.0, "stationary": False, "method": f"error:{type(e).__name__}", "error": str(e)}


# ─────────────────────────────────────────────
# 4. Optimal d Finder (0.3-0.5)
# ─────────────────────────────────────────────

def find_optimal_d(
    series: Union[pd.Series, np.ndarray, List[float]],
    d_range: Tuple[float, float] = (0.3, 0.5),
    step: float = 0.05,
    thresh: float = 1e-4,
    autolag: int = 1,
) -> Dict:
    """
    Find minimal d in [0.3,0.5] that achieves stationarity (ADF p<0.05)
    while maximizing memory retention.

    Spec: 0.3 <= d <= 0.5
    - Iterate d from low to high (preserve max memory)
    - First d that passes ADF is optimal (lowest d that achieves stationarity)

    Returns dict with optimal_d, all_results, best_memory
    """
    if isinstance(series, list):
        series = pd.Series(series)
    elif isinstance(series, np.ndarray):
        series = pd.Series(series)

    d_min, d_max = d_range
    d_values = np.arange(d_min, d_max + 1e-9, step)
    results = []
    optimal = None

    for d in d_values:
        d = round(float(d), 4)
        try:
            fd_res = frac_diff_with_memory_check(series, d=d, thresh=thresh)
            fd_series = fd_res["frac_diffed"].dropna()
            if len(fd_series) < 20:
                adf_res = {"stationary": False, "p_value": 1.0, "test_stat": 0.0}
            else:
                adf_res = adf_test(fd_series, autolag=autolag)

            entry = {
                "d": d,
                "window": fd_res["window"],
                "correlation_memory": fd_res["correlation_memory"],
                "variance_retention": fd_res["variance_retention"],
                "adf_stat": adf_res.get("test_stat"),
                "adf_p": adf_res.get("p_value"),
                "stationary": adf_res.get("stationary", False),
            }
            results.append(entry)

            if optimal is None and entry["stationary"]:
                optimal = entry
                # Don't break — we want all results for analysis, but optimal is first stationary
        except Exception as e:
            results.append({"d": d, "error": str(e), "stationary": False})

    # If no d achieves stationarity in range, pick highest d (closest to stationary)
    if optimal is None and results:
        # Pick with lowest p-value
        try:
            optimal = min(results, key=lambda x: x.get("adf_p", 1.0) if "adf_p" in x else 1.0)
            optimal = {**optimal, "note": "no d achieved p<0.05 in range, best effort"}
        except Exception:
            optimal = results[-1]

    return {
        "optimal_d": optimal["d"] if optimal else None,
        "optimal_result": optimal,
        "all_results": results,
        "d_range": d_range,
        "thresh": thresh,
        "method": "first_stationary_min_d",
    }


# ─────────────────────────────────────────────
# 5. Utility: Stationarity Report
# ─────────────────────────────────────────────

def stationarity_report(
    series: Union[pd.Series, np.ndarray, List[float]],
    symbol: str = "UNKNOWN",
    d_range: Tuple[float, float] = (0.3, 0.5),
) -> Dict:
    """
    Full report for a single symbol: original ADF + fractional diff scan + optimal d.
    """
    s = pd.Series(series) if not isinstance(series, pd.Series) else series
    orig_adf = adf_test(s.dropna())

    # Integer diff for comparison (d=1)
    int_diff = s.diff().dropna()
    int_adf = adf_test(int_diff) if len(int_diff) >= 20 else {"stationary": False, "p_value": 1.0}

    optimal = find_optimal_d(s, d_range=d_range)

    return {
        "symbol": symbol,
        "n_original": len(s.dropna()),
        "original_adf": orig_adf,
        "integer_diff_adf": int_adf,
        "fractional_optimal": optimal,
        "conclusion": {
            "original_stationary": orig_adf.get("stationary", False),
            "integer_diff_stationary": int_adf.get("stationary", False),
            "fractional_stationary": optimal["optimal_result"].get("stationary", False) if optimal.get("optimal_result") else False,
            "memory_preserved": optimal["optimal_result"].get("correlation_memory", 0) if optimal.get("optimal_result") else 0,
            "recommended_d": optimal.get("optimal_d"),
        },
    }


# ─────────────────────────────────────────────
# CLI for manual testing
# ─────────────────────────────────────────────

def _cli():
    import argparse
    parser = argparse.ArgumentParser(description="QASWA Phase 1: Fractional Differentiation & ADF")
    parser.add_argument("--test", action="store_true", help="Run self-test with synthetic random walk")
    parser.add_argument("--symbol", type=str, default="TEST", help="Symbol label")
    args = parser.parse_args()

    if args.test:
        print("=== Phase 1 Self-Test: Fractional Differentiation ===")
        np.random.seed(42)
        # Random walk (non-stationary)
        rw = np.cumsum(np.random.randn(1000)) + 100
        s = pd.Series(rw)
        print(f"Original series len={len(s)}, mean={s.mean():.2f}, std={s.std():.2f}")

        orig_adf = adf_test(s)
        print(f"Original ADF: stat={orig_adf['test_stat']:.4f}, p={orig_adf['p_value']:.4f}, stationary={orig_adf['stationary']}, method={orig_adf['method']}")

        for d in [0.3, 0.35, 0.4, 0.45, 0.5]:
            res = frac_diff_with_memory_check(s, d=d)
            adf = adf_test(res["frac_diffed"].dropna())
            print(
                f"d={d:.2f} window={res['window']:4d} corr_mem={res['correlation_memory']:.4f} "
                f"var_ret={res['variance_retention']:.4f} ADF p={adf['p_value']:.4f} stat={adf['test_stat']:.4f} stationary={adf['stationary']}"
            )

        opt = find_optimal_d(s)
        print(f"\nOptimal d: {opt['optimal_d']} -> {opt['optimal_result']}")
        print("Phase 1 self-test DONE — if at least one d achieves stationary, PASS")


if __name__ == "__main__":
    _cli()
