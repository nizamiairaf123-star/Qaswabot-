"""
mtf/stats.py — Overfitting-detection statistics (Phase-2, ADD-ONLY).

[Method: Deflated Sharpe Ratio — Bailey & López de Prado, "The Deflated Sharpe Ratio:
         Correcting for Selection Bias, Backtest Overfitting and Non-Normality", 2014]
[Method: Probability of Backtest Overfitting (CSCV) — Bailey, Borwein, López de Prado & Zhu,
         "Pseudo-Mathematics and Financial Charlatanism", 2014]
[Method: Purged K-Fold CV + Embargo — López de Prado, "Advances in Financial Machine
         Learning", 2018]
"""

from __future__ import annotations

import itertools
import numpy as np
from scipy.stats import norm

_EULER_GAMMA = 0.5772156649


def expected_max_sharpe(n_trials: int, var_sharpe: float) -> float:
    """
    Bailey & López de Prado (2014): n_trials independent attempts hone par
    random luck se expected maximum Sharpe. Ye "luck benchmark" hai —
    best strategy isko beat kare tabhi skill maano.
    """
    if n_trials <= 1 or var_sharpe <= 0:
        return 0.0
    z1 = norm.ppf(1 - 1.0 / n_trials)
    z2 = norm.ppf(1 - 1.0 / (n_trials * np.e))
    return float(np.sqrt(var_sharpe) * ((1 - _EULER_GAMMA) * z1 + _EULER_GAMMA * z2))


def deflated_sharpe_ratio(sr_hat: float, n_obs: int, skew: float, kurt: float,
                          n_trials: int, var_sharpe: float = None) -> float:
    """
    DSR (Bailey & López de Prado 2014): probability ki observed Sharpe > luck benchmark.
    Returns 0..1 (higher = overfit hone ki sambhavna KAM). >=0.95 standard pass bar.
    var_sharpe na mile to cross-sectional me estimate nahi ho sakta → 1/T fallback.
    """
    if n_obs < 3 or n_trials < 1:
        return 0.0
    vs = (1.0 / (n_obs - 1)) if var_sharpe is None else max(var_sharpe, 1e-12)
    e_max = expected_max_sharpe(n_trials, vs)
    denom = np.sqrt(max(1e-12, 1 - skew * sr_hat + ((kurt - 1) / 4.0) * sr_hat ** 2))
    z = ((sr_hat - e_max) * np.sqrt(n_obs - 1)) / denom
    return float(norm.cdf(z))


def pbo_cscv(perf_matrix: np.ndarray, n_partitions: int = 8) -> float:
    """
    PBO via Combinatorially Symmetric Cross-Validation (Bailey et al. 2014).
    perf_matrix: shape (T, N_strategies) — aligned per-period performance (e.g. per-trade returns).
    Returns PBO in 0..1 — probability ki IS-best strategy OOS me below-median rahe.
    Higher = zyada overfit risk. Industry rule-of-thumb: PBO > 0.5 dangerous.
    """
    X = np.asarray(perf_matrix, dtype=float)
    T, N = X.shape
    if n_partitions < 2 or n_partitions > 16 or n_partitions % 2 != 0:
        raise ValueError("n_partitions must be even, 2..16")
    part_size = T // n_partitions
    if part_size < 1:
        raise ValueError("not enough rows for partitions")
    X = X[: part_size * n_partitions]
    parts = np.array_split(X, n_partitions, axis=0)

    omegas = []
    combos = list(itertools.combinations(range(n_partitions), n_partitions // 2))
    # all symmetric combos is 2^(S-1)*C(S, S/2)-ish heavy for S=8 (70) — fine
    for is_combo in combos:
        oos_combo = tuple(i for i in range(n_partitions) if i not in is_combo)
        is_mat = np.vstack([parts[i] for i in is_combo])
        oos_mat = np.vstack([parts[i] for i in oos_combo])
        is_perf = np.nanmean(is_mat, axis=0)
        oos_perf = np.nanmean(oos_mat, axis=0)
        best_is = int(np.nanargmax(is_perf))
        # relative OOS rank of the IS-winner
        oos_rank = int((oos_perf > oos_perf[best_is]).sum())  # 0 = best in OOS
        rel_rank = oos_rank / max(1, (N - 1))                  # 0..1 (0 best, 1 worst)
        omegas.append(rel_rank)
    if not omegas:
        return float("nan")
    return float(np.mean([1.0 if r > 0.5 else 0.0 for r in omegas]))


def purged_kfold_indices(n_samples: int, n_splits: int = 5,
                         embargo: int = 0):
    """
    Purged K-Fold CV + Embargo (López de Prado 2018, ch. 7).
    Trades ka time-overlap financial data me information leak karta hai:
    test fold ke adjacent train samples "purge" + embargo ke baad wale bhi exclude.
    NOTE: yeh utility hai — Phase-2 tournament rolling WFV (Pardo) use karta hai;
    purged-CV future tune-up ke liye ready rakha gaya hai (design doc Sec 3.4).
    Yields (train_idx, test_idx) arrays.
    """
    n_splits = max(1, int(n_splits))
    fold_sizes = np.full(n_splits, n_samples // n_splits)
    fold_sizes[: n_samples % n_splits] += 1
    bounds = np.concatenate([[0], np.cumsum(fold_sizes)])
    indices = np.arange(n_samples)
    for i in range(n_splits):
        test_idx = indices[bounds[i]: bounds[i + 1]]
        test_start, test_end = bounds[i], bounds[i + 1]
        train_mask = (indices < test_start) | (indices >= test_end)
        # purge: test ke theek pehle ke embargo samples bhi hatao
        if embargo > 0:
            train_mask &= ~((indices >= test_start - embargo) & (indices < test_start))
            train_mask &= ~((indices >= test_end) & (indices < test_end + embargo))
        yield indices[train_mask], test_idx
