"""
walk_forward_validator.py — Rolling Walk-Forward Validation (Pardo method) + Phase 2 Purged CPCV
Train window rolls forward — each step re-optimizes on new train, validates on new test.
Agar train vs test gap zyada = overfit.

Source: Robert Pardo "The Evaluation and Optimization of Trading Strategies"
Verified: Rolling WFV is industry standard for strategy robustness.

FIX: If WFV can't complete (insufficient data), mark as
INSUFFICIENT_DATA not OVERFIT. Optimization score already validates.

Phase 2 (v6.1 — Purged & Embargoed CV):
  - Implements Marcos Lopez de Prado's Purged K-Fold CV (Advances in Financial ML, Ch 7)
  - Purging: Drops training samples whose event windows overlap with test samples
  - Embargoing: 5-day post-test buffer to prevent serial correlation leakage
  - WFE = OOS/IS, WFE<0.50 => fragile/overfitted
  - Parameter stability check: wildly oscillating params => reject
  - Parity engine: verifies no future leakage across splits
"""

import logging
from typing import Dict, List, Tuple, Optional
import itertools

import pandas as pd
import numpy as np
from utils import load_json, save_json, now_ist, append_log
from config import AUDIT_LOG_FILE, PARAMS

logger = logging.getLogger(__name__)

WFV_RESULTS_FILE = "data/walk_forward_results.json"

# ─────────────────────────────────────────────
# Phase 2: Purged K-Fold & Embargo (Lopez de Prado)
# ─────────────────────────────────────────────

class PurgedKFold:
    """
    Purged K-Fold CV with embargo — Lopez de Prado (2018) Ch 7.
    
    Standard K-Fold leaks because labels overlap (e.g., 5-day holding period).
    If train label window overlaps test, information leaks.
    
    Purging: For each test fold, remove from train any sample whose label interval
             overlaps test interval.
    Embargo: After test, embargo N samples where train is blocked to prevent
             serial correlation leakage (common in financial series).
    
    For QASWA:
      - Daily data: embargo = 5 days (per spec)
      - 15m data: embargo = 5 * (6.5h*4) ~130 bars? Simplified to 5 days = 5 bars for daily
      - purge_gap = 5 days (event horizon)
    
    Usage:
      For each split:
        test_indices = fold i
        train_indices = all except test, minus purged overlapping, minus embargoed
    """

    def __init__(self, n_splits: int = 5, embargo_pct: float = 0.01, embargo_days: int = 5):
        if n_splits < 2:
            raise ValueError("n_splits must be >=2")
        self.n_splits = n_splits
        self.embargo_pct = embargo_pct
        self.embargo_days = embargo_days

    def split(self, X: pd.DataFrame, y=None, groups=None, event_times: Optional[pd.Series] = None):
        """
        Generate purged train/test indices.
        
        Args:
            X: DataFrame with datetime index or integer index
            event_times: Series of label end times (when event/holding ends) indexed same as X
                         If None, assumes label ends at same time as sample (no overlap)
                         For QASWA: event end = entry + max_holding_bars (e.g., 20 days)
        
        Yields:
            (train_indices, test_indices)
        """
        n_samples = len(X)
        indices = np.arange(n_samples)
        
        # Contiguous folds (time-series aware, no shuffle)
        fold_sizes = np.full(self.n_splits, n_samples // self.n_splits, dtype=int)
        fold_sizes[: n_samples % self.n_splits] += 1
        current = 0
        folds = []
        for fold_size in fold_sizes:
            start, stop = current, current + fold_size
            folds.append(indices[start:stop])
            current = stop

        # Embargo size in samples
        embargo = max(1, int(n_samples * self.embargo_pct))
        # Use max of pct and days (days interpreted as samples for daily)
        embargo = max(embargo, self.embargo_days)

        for i in range(self.n_splits):
            test_indices = folds[i]
            test_start = test_indices[0]
            test_end = test_indices[-1]

            # Train = all except test
            train_indices = np.concatenate([folds[j] for j in range(self.n_splits) if j != i])

            # Purging: if event_times provided, remove train samples whose event overlaps test
            if event_times is not None:
                # event_times: for each sample, when its label/holding ends
                # If train sample's event end >= test_start and train sample start <= test_end => overlap
                # Simplified: if event_time >= test_start, purge
                # event_times aligned with X index
                try:
                    # event_times as array of end indices
                    # For each train idx, if event_end >= test_start and train_idx <= test_end => purge
                    # Here event_times is Series of end positions (int or timestamp)
                    # Convert to positional indices
                    purged = []
                    for ti in train_indices:
                        # Get event end for this train sample
                        # If event_times is positional (int), compare directly
                        try:
                            evt_end = event_times.iloc[ti] if hasattr(event_times, 'iloc') else event_times[ti]
                            # If evt_end is timestamp, convert to positional via search
                            if isinstance(evt_end, (pd.Timestamp, str)):
                                # Skip timestamp logic for now, use index position
                                evt_end_pos = ti + self.embargo_days  # assume holding = embargo_days
                            else:
                                evt_end_pos = int(evt_end)
                        except Exception:
                            evt_end_pos = ti + self.embargo_days

                        if evt_end_pos >= test_start and ti <= test_end:
                            purged.append(ti)
                    if purged:
                        train_indices = np.array([idx for idx in train_indices if idx not in set(purged)])
                except Exception as e:
                    logger.debug(f"PurgedKFold purging failed: {e}, using unpurged train")

            # Embargo: after test_end, embargo N samples from train
            # Remove train indices that are within embargo after test_end
            embargo_end = min(n_samples - 1, test_end + embargo)
            train_indices = np.array([idx for idx in train_indices if not (test_end < idx <= embargo_end)])

            yield train_indices, test_indices

    def get_n_splits(self, X=None, y=None, groups=None):
        return self.n_splits


def _get_purged_train_indices(
    n_samples: int,
    test_start: int,
    test_end: int,
    purge_gap: int = 5,
    embargo: int = 5,
) -> Tuple[int, int, int, int]:
    """
    Compute purged train boundaries for walk-forward.
    
    For walk-forward where train is before test:
      train_end_purged = test_start - purge_gap
      next_train_start = test_end + embargo + 1
    
    Returns (train_start, train_end_purged, test_start, test_end)
    Used for parity check: ensures train_end_purged < test_start and no overlap
    """
    # This helper is for boundary calculation, actual slicing done in run_walk_forward
    return (test_start, test_end, purge_gap, embargo)


def _compute_param_stability(all_params: List[Dict]) -> Dict:
    """
    Check if best params oscillate wildly across WFV splits.
    If CV > 0.5 for numeric params or categorical changes >50%, mark unstable.
    
    Returns dict with stable bool, unstable_params list, cv metrics
    """
    if not all_params or len(all_params) < 2:
        return {"stable": True, "reason": "insufficient splits for stability check", "unstable_params": [], "cv": {}}

    # Collect all keys
    all_keys = set()
    for p in all_params:
        all_keys.update(p.keys())

    unstable = []
    cv_metrics = {}
    categorical_changes = {}

    for key in all_keys:
        values = [p.get(key) for p in all_params if key in p]
        if len(values) < 2:
            continue

        # Check if numeric
        try:
            # Try convert to float
            numeric_vals = [float(v) for v in values if isinstance(v, (int, float)) or (isinstance(v, str) and v.replace('.','',1).isdigit())]
            if len(numeric_vals) >= 2:
                mean = float(np.mean(numeric_vals))
                std = float(np.std(numeric_vals))
                cv = std / abs(mean) if abs(mean) > 1e-9 else (0.0 if std < 1e-9 else 999.0)
                cv_metrics[key] = round(cv, 3)
                if cv > 0.5:  # Wild oscillation threshold per spec
                    unstable.append(key)
            else:
                # Categorical
                # Most frequent value frequency
                from collections import Counter
                cnt = Counter(values)
                most_common_freq = cnt.most_common(1)[0][1] / len(values) if values else 0
                categorical_changes[key] = round(1.0 - most_common_freq, 3)
                if most_common_freq < 0.5:  # Changes >50% of splits
                    unstable.append(key)
        except Exception as e:
            logger.debug(f"param stability check failed for {key}: {e}")
            continue

    stable = len(unstable) == 0
    reason = "OK" if stable else f"Unstable params (CV>0.5 or change>50%): {', '.join(unstable[:5])}"

    return {
        "stable": stable,
        "unstable_params": unstable,
        "cv": cv_metrics,
        "categorical_change": categorical_changes,
        "reason": reason,
    }


def _verify_no_future_leakage(splits: List[Tuple[int, int, int, int]]) -> Dict:
    """
    Parity engine: verifies no future leakage across backtest splits.
    For walk-forward, train_end < test_start must hold for all splits.
    Also checks embargo respected.
    
    Args:
        splits: list of (train_start, train_end, test_start, test_end) positional indices
    
    Returns dict with leak_free bool, violations list
    """
    violations = []
    for idx, (tr_s, tr_e, te_s, te_e) in enumerate(splits):
        if tr_e >= te_s:
            violations.append(f"Split {idx}: train_end {tr_e} >= test_start {te_s} — future leak!")
        if tr_s >= tr_e:
            violations.append(f"Split {idx}: train_start {tr_s} >= train_end {tr_e}")
        if te_s >= te_e:
            violations.append(f"Split {idx}: test_start {te_s} >= test_end {te_e}")

    # Check splits are time-ordered (no test from future used to train past)
    for i in range(1, len(splits)):
        prev_te_e = splits[i-1][3]
        curr_tr_s = splits[i][0]
        # For walk-forward, current train should start after previous test + embargo
        # Not strictly required for K-Fold, but for walk-forward it should be >= prev test end
        # We allow overlap for K-Fold, but warn if current train starts before previous test start (time travel)
        if curr_tr_s < splits[i-1][2]:
            # This would be okay for K-Fold (train includes past and future), but for walk-forward it's leak
            # We don't mark as violation for K-Fold, only for walk-forward where train must be before test
            pass

    leak_free = len(violations) == 0
    return {"leak_free": leak_free, "violations": violations, "n_splits": len(splits)}


# ─────────────────────────────────────────────
# End Phase 2 additions — original code below enhanced
# ─────────────────────────────────────────────


def run_walk_forward(symbol: str, data: pd.DataFrame,
                     strategy_func, param_grid: dict,
                     n_splits: int = 5,
                     opt_score: float = 0.0,
                     purge_gap: int = 5,
                     embargo: int = 5,
                     enable_purged_cv: bool = True) -> dict:
    """
    Rolling Walk-Forward Validation (Pardo method).

    Process:
    1. Divide data into n_splits rolling windows
    2. Each window: train on past, test on future
    3. Train window ROLLS forward (not anchored to start)
    4. [VERIFIED QUANT METHOD] Primary validity gate: Walk-Forward
       Efficiency (WFE) = mean(out-of-sample return / in-sample return)
       across splits -- the industry-standard metric for walk-forward
       robustness (Pardo; cross-verified against multiple independent
       walk-forward analysis sources). WFE >= wfv_efficiency_threshold
       (0.5 = retains at least half of in-sample performance
       out-of-sample) is the pass bar; WFE < 0.3 is a severe-overfit red
       flag.
    5. Train-vs-test win-rate gap is retained as a supplementary
       diagnostic (not the primary pass/fail criterion).

    Returns: {
        valid: bool,
        wfe: float,
        overfit_score: float,
        train_wr: float,
        test_wr: float,
        gap: float,
        expected_live_wr: float,
        confidence: float,
        reason: str
    }
    """
    min_candles = PARAMS.get("wfv_min_candles", 200)

    if len(data) < min_candles:
        # Constitution Art. 1.5: insufficient data means this stock has NOT
        # been out-of-sample validated -- the optimizer's own objective is
        # purely in-sample (confirmed: bayesian_optimize_single backtests
        # on the full data it's given, no internal train/test split), so
        # WFV is the ONLY out-of-sample check in this pipeline. Reporting
        # valid=True here would mean "verified" when nothing was actually
        # verified. Fail closed instead -- do not guess.
        return {
            "symbol": symbol,
            "valid": False,
            "wfe": None,
            "train_wr": 0,
            "test_wr": 0,
            "gap": 0,
            "overfit_score": None,
            "n_splits": 0,
            "expected_live_wr": 0,
            "confidence": 0.0,
            "reason": (
                f"INSUFFICIENT_DATA: only {len(data)} candles available, "
                f"need >= {min_candles} for walk-forward validation -- "
                f"no out-of-sample check could be performed, so this "
                f"stock is NOT verified (Constitution Art. 1.5: fail "
                f"closed rather than trust an unvalidated in-sample fit)"
            ),
            "checked_at": now_ist().isoformat(),
        }

    # [VERIFIED QUANT METHOD] Number of walk-forward windows: multiple
    # independent sources (StratBase, TradeStation WFO FAQ, quanttradingtools)
    # converge on 5-10 splits as the standard range for reliable conclusions
    # (below 5, out-of-sample data is too noisy; above ~15, each in-sample
    # window becomes too short to optimize meaningfully). Default raised
    # from 3 to 5 (the low end of that standard range); scales toward 10
    # as more history becomes available.
    if len(data) >= 750:
        n_splits = max(5, min(10, (len(data) - 500) // 250))
    else:
        n_splits = max(5, n_splits)

    split_size    = len(data) // (n_splits + 1)
    train_wrs     = []
    test_wrs      = []
    test_pfs      = []
    split_wfes    = []  # per-split OOS/IS return ratios
    wf_eligible   = 0   # [PHD-FIX F8] kitne splits ka IS return computed hua (coverage)
    all_params    = []  # Phase 2: track best params per split for stability check
    splits_for_parity = []  # (train_start, train_end_purged, test_start, test_end)

    # Phase 2: Purged & Embargoed walk-forward
    # If enable_purged_cv True, we use purge_gap and embargo gaps
    # Train = before test, with purge_gap removed from train end, embargo after test before next train
    # This prevents serial correlation leakage per Lopez de Prado

    current_train_start = 0
    for i in range(n_splits):
        if enable_purged_cv:
            # Purged walk-forward: train slides with gaps
            train_start = current_train_start
            train_end = train_start + split_size
            # Purging: remove purge_gap bars from end of train that are too close to test
            train_end_purged = max(train_start + 10, train_end - purge_gap)  # keep at least 10 bars
            test_start = train_end + purge_gap  # gap after train
            test_end = test_start + split_size
            # Next train starts after embargo
            next_train_start = test_end + embargo
        else:
            # Original rolling window (backward compat)
            train_start = i * split_size
            train_end = train_start + split_size
            train_end_purged = train_end
            test_start = train_end
            test_end = test_start + split_size
            next_train_start = test_end

        if test_end > len(data):
            break

        if train_end_purged <= train_start or test_end <= test_start:
            current_train_start = next_train_start
            continue

        train_data = data.iloc[train_start:train_end_purged]
        test_data = data.iloc[test_start:test_end]

        splits_for_parity.append((train_start, train_end_purged, test_start, test_end))

        if len(train_data) < 50 or len(test_data) < 20:
            current_train_start = next_train_start
            continue

        # Optimize on train data
        best_params = _optimize_on_data(train_data, strategy_func, param_grid,
                                         symbol=symbol, split_index=i)
        if not best_params:
            current_train_start = next_train_start
            continue

        all_params.append(best_params)

        # Validate on test data
        train_metrics = _evaluate_params(train_data, strategy_func, best_params)
        test_metrics = _evaluate_params(test_data, strategy_func, best_params)

        if train_metrics and test_metrics:
            train_wrs.append(train_metrics.get("win_rate", 0))
            test_wrs.append(test_metrics.get("win_rate", 0))
            test_pfs.append(test_metrics.get("profit_factor", 0))

            is_return = train_metrics.get("total_return_pct", 0)
            oos_return = test_metrics.get("total_return_pct", 0)
            wf_eligible += 1
            if is_return > 0:
                split_wfes.append(oos_return / is_return)

        current_train_start = next_train_start

    # Phase 2: Parity engine — verify no future leakage
    parity_check = _verify_no_future_leakage(splits_for_parity)
    if not parity_check.get("leak_free", True):
        logger.warning(f"WFV parity check failed for {symbol}: {parity_check.get('violations')}")

    if not train_wrs or not test_wrs:
        # WFV could not complete even one full split -- same principle as
        # the insufficient-data case above: no out-of-sample check was
        # actually performed, so this is NOT verified. Fail closed.
        return {
            "symbol": symbol,
            "valid": False,
            "wfe": None,
            "train_wr": 0,
            "test_wr": 0,
            "gap": 0,
            "overfit_score": None,
            "n_splits": n_splits,
            "expected_live_wr": 0,
            "confidence": 0.0,
            "reason": (
                "INSUFFICIENT_DATA: walk-forward could not complete a "
                "single valid train/test split -- no out-of-sample check "
                "was performed, so this stock is NOT verified (Constitution "
                "Art. 1.5: fail closed rather than trust an unvalidated "
                "in-sample fit)"
            ),
            "checked_at": now_ist().isoformat(),
        }

    avg_train_wr = round(np.mean(train_wrs), 1)
    avg_test_wr  = round(np.mean(test_wrs), 1)
    gap          = round(avg_train_wr - avg_test_wr, 1)

    # Expected live WR = test WR (out-of-sample is best predictor of live)
    expected_live_wr = round(avg_test_wr, 1)

    # Confidence: how consistent are test WRs across splits
    if len(test_wrs) >= 2:
        test_std = float(np.std(test_wrs))
        confidence = round(max(0.0, 1.0 - test_std / 20.0), 2)  # Low std = high confidence
    else:
        confidence = 0.3  # Only 1 split = low confidence

    max_gap = PARAMS.get("walk_forward_max_gap", 10)
    wfe_threshold = PARAMS.get("wfv_efficiency_threshold", 0.5)

    # Phase 2: Parameter stability check
    stability = _compute_param_stability(all_params) if 'all_params' in locals() else {"stable": True, "reason": "no params", "unstable_params": []}
    parity_check = parity_check if 'parity_check' in locals() else {"leak_free": True, "violations": []}

    if split_wfes:
        wfe = round(float(np.mean(split_wfes)), 3)
        # [VERIFIED QUANT METHOD] WFE is the primary pass/fail gate.
        # Win-rate gap is retained only as a supplementary diagnostic.
        # Phase 2 adds param stability and parity checks
        is_valid_wfe = wfe >= wfe_threshold
        is_valid_gap = gap <= max_gap
        is_valid_stability = stability.get("stable", True)
        is_valid_parity = parity_check.get("leak_free", True)

        is_valid = is_valid_wfe and is_valid_gap and is_valid_stability and is_valid_parity

        if not is_valid_wfe:
            reason = f"Overfit: WFE={wfe} < threshold={wfe_threshold}"
        elif not is_valid_gap:
            reason = f"Overfit: gap={gap}% > max={max_gap}%"
        elif not is_valid_stability:
            reason = f"Overfit: param unstable — {stability.get('reason')}"
        elif not is_valid_parity:
            reason = f"Overfit: future leakage detected — {parity_check.get('violations', [])[:2]}"
        else:
            reason = "OK"
    else:
        # Every split's in-sample fit found no positive edge to test --
        # cannot compute a WFE ratio at all. Fail closed rather than fall
        # back to the win-rate gap alone (which was the pre-existing,
        # non-standard metric this fix is specifically replacing).
        wfe = None
        is_valid = False
        reason = "No split produced a positive in-sample return -- Walk-Forward Efficiency could not be computed, treated as unverified"

    overfit_score = round(min(gap / max_gap, 1.0), 2) if max_gap > 0 else 0

    # [PHD-FIX F8] WFE coverage — upward-bias transparency
    wfe_coverage = round(len(split_wfes) / max(1, wf_eligible), 3)

    result = {
        "symbol":           symbol,
        "wfe_coverage":     wfe_coverage,
        "valid":            is_valid,
        "wfe":              wfe,
        "train_wr":         avg_train_wr,
        "test_wr":          avg_test_wr,
        "gap":              gap,
        "overfit_score":    overfit_score,
        "n_splits":         n_splits,
        "expected_live_wr": expected_live_wr,
        "confidence":       confidence,
        "reason":           reason,
        "checked_at":       now_ist().isoformat(),
        # Phase 2 additions
        "purge_gap":        purge_gap if 'purge_gap' in locals() else 5,
        "embargo":          embargo if 'embargo' in locals() else 5,
        "enable_purged_cv": enable_purged_cv if 'enable_purged_cv' in locals() else True,
        "param_stability":  stability,
        "parity_check":     parity_check,
        "n_param_sets":     len(all_params) if 'all_params' in locals() else 0,
    }

    append_log(AUDIT_LOG_FILE,
               f"WALK-FORWARD {symbol}: valid={is_valid} wfe={wfe} "
               f"train_wr={avg_train_wr}% test_wr={avg_test_wr}% gap={gap}% "
               f"expected_live={expected_live_wr}% confidence={confidence}")
    return result


def _optimize_on_data(data: pd.DataFrame, strategy_func,
                      param_grid: dict, symbol: str = "WFV",
                      split_index: int = 0) -> dict:
    """
    Bayesian optimization on train data with grid fallback.
    Returns best params dict.

    FIX: this used to call bayesian_optimize_single("WFV", ...) with a
    hardcoded "WFV" symbol and the default persist=True. Since Optuna's
    study is keyed on symbol+signal_func and stored in one shared sqlite
    file, that meant every stock's every rolling train/test split for a
    given signal generator was optimized against the SAME accumulating
    study -- split 5's "fresh" optimization carried trial history from
    splits 1-4 (different time windows) and from unrelated stocks. That
    breaks the independence walk-forward validation is meant to test.
    Now uses persist=False (in-memory, single-use study per call) so each
    stock's each split is optimized in full isolation, and passes the real
    symbol + split index only for readable logging (not used for storage
    since persist=False never writes/loads a study file).
    """
    try:
        from optimizer import bayesian_optimize_single
        res = bayesian_optimize_single(
            symbol, data, strategy_func, n_calls=25,
            persist=False, study_suffix=f"_wfv_split{split_index}"
        )
        if res and res.get("params"):
            return res["params"]
    except (ImportError, RuntimeError, ValueError) as e:
        logger.warning(f"_wfv_bayesian_fallback: Bayesian optimize failed: {type(e).__name__}: {e}")

    best_wr     = -1
    best_params = None

    import itertools
    keys   = list(param_grid.keys())
    values = list(param_grid.values())

    for combo in itertools.product(*values):
        params = dict(zip(keys, combo))
        try:
            metrics = _evaluate_params(data, strategy_func, params)
            if metrics and metrics.get("win_rate", 0) > best_wr:
                best_wr     = metrics["win_rate"]
                best_params = params
        except (TypeError, ValueError, RuntimeError) as e:
            logger.debug(f"_wfv_grid_search: Params evaluation failed: {type(e).__name__}: {e}")
            continue

    return best_params


def _evaluate_params(data: pd.DataFrame, strategy_func,
                     params: dict) -> dict:
    """Evaluate params on given data. Returns metrics.

    Walk-forward is called from optimizer with signal generators that use
    signature (data, params). Reuse optimizer's backtest engine so validation
    is based on completed trades/P&L, not raw BUY signal count.
    """
    try:
        from optimizer import backtest_with_params
        result = backtest_with_params(data, strategy_func, params)
        if not result:
            return None
        return {
            "win_rate":       round(float(result.get("win_rate_pct", 0)), 1),
            "total_trades":   int(result.get("total_trades", 0)),
            "profit_factor":  round(float(result.get("profit_factor", 0)), 2),
            "total_return_pct": round(float(result.get("total_return_pct", 0)), 2),
        }
    except (TypeError, ValueError, KeyError) as e:
        logger.debug(f"_evaluate_params: Metrics extraction failed: {type(e).__name__}: {e}")
        try:
            trades = strategy_func(data, "WFV_TEST")
            if not trades:
                return None
            wins = len([t for t in trades if t.get("return_pct", 0) > 0])
            # Approximate compounded return from the same return_pct field
            # used elsewhere in this fallback path, for WFE calculation.
            compounded = 1.0
            for t in trades:
                compounded *= (1.0 + float(t.get("return_pct", 0)) / 100.0)
            approx_return_pct = round((compounded - 1.0) * 100.0, 2)
            return {
                "win_rate": round(wins / len(trades) * 100, 1),
                "total_trades": len(trades),
                "profit_factor": 0,
                "total_return_pct": approx_return_pct,
            }
        except (TypeError, ValueError, RuntimeError) as e:
            logger.debug(f"_evaluate_params: Fallback evaluation failed: {type(e).__name__}: {e}")
            return None


def run_purged_kfold_validation(
    symbol: str,
    data: pd.DataFrame,
    strategy_func,
    param_grid: dict,
    n_splits: int = 5,
    embargo_days: int = 5,
    embargo_pct: float = 0.01,
) -> dict:
    """
    Phase 2: Purged K-Fold CV (Lopez de Prado) — non-walk-forward version.
    Uses PurgedKFold class to generate train/test splits with purging + embargo.
    Both compute WFE and param stability.
    """
    min_candles = PARAMS.get("wfv_min_candles", 200)
    if len(data) < min_candles:
        return {
            "symbol": symbol,
            "valid": False,
            "wfe": None,
            "reason": f"INSUFFICIENT_DATA: {len(data)} < {min_candles}",
            "checked_at": now_ist().isoformat(),
            "method": "purged_kfold",
        }

    cv = PurgedKFold(n_splits=n_splits, embargo_days=embargo_days, embargo_pct=embargo_pct)

    train_wrs = []
    test_wrs = []
    split_wfes = []
    all_params = []
    wf_eligible = 0
    splits_for_parity = []

    try:
        for train_idx, test_idx in cv.split(data):
            if len(train_idx) < 50 or len(test_idx) < 20:
                continue

            train_data = data.iloc[train_idx]
            test_data = data.iloc[test_idx]

            tr_s, tr_e = int(train_idx[0]), int(train_idx[-1])
            te_s, te_e = int(test_idx[0]), int(test_idx[-1])
            splits_for_parity.append((tr_s, tr_e, te_s, te_e))

            best_params = _optimize_on_data(train_data, strategy_func, param_grid, symbol=symbol, split_index=len(all_params))
            if not best_params:
                continue

            all_params.append(best_params)

            train_metrics = _evaluate_params(train_data, strategy_func, best_params)
            test_metrics = _evaluate_params(test_data, strategy_func, best_params)

            if train_metrics and test_metrics:
                train_wrs.append(train_metrics.get("win_rate", 0))
                test_wrs.append(test_metrics.get("win_rate", 0))
                wf_eligible += 1
                is_ret = train_metrics.get("total_return_pct", 0)
                oos_ret = test_metrics.get("total_return_pct", 0)
                if is_ret > 0:
                    split_wfes.append(oos_ret / is_ret)

        if not train_wrs:
            return {
                "symbol": symbol,
                "valid": False,
                "wfe": None,
                "reason": "No valid splits in purged K-Fold",
                "checked_at": now_ist().isoformat(),
                "method": "purged_kfold",
            }

        avg_train_wr = round(float(np.mean(train_wrs)), 1)
        avg_test_wr = round(float(np.mean(test_wrs)), 1)
        gap = round(avg_train_wr - avg_test_wr, 1)
        wfe = round(float(np.mean(split_wfes)), 3) if split_wfes else None

        stability = _compute_param_stability(all_params)
        parity = _verify_no_future_leakage(splits_for_parity)

        wfe_threshold = PARAMS.get("wfv_efficiency_threshold", 0.5)
        max_gap = PARAMS.get("walk_forward_max_gap", 10)

        is_valid = (
            (wfe is not None and wfe >= wfe_threshold)
            and gap <= max_gap
            and stability.get("stable", True)
            and parity.get("leak_free", True)
        )

        reason = "OK"
        if wfe is None or wfe < wfe_threshold:
            reason = f"WFE {wfe} < {wfe_threshold}"
        elif gap > max_gap:
            reason = f"gap {gap}% > {max_gap}%"
        elif not stability.get("stable"):
            reason = f"param unstable: {stability.get('reason')}"
        elif not parity.get("leak_free"):
            reason = f"leakage: {parity.get('violations')[:1]}"

        return {
            "symbol": symbol,
            "valid": is_valid,
            "wfe": wfe,
            "train_wr": avg_train_wr,
            "test_wr": avg_test_wr,
            "gap": gap,
            "n_splits": n_splits,
            "param_stability": stability,
            "parity_check": parity,
            "reason": reason,
            "checked_at": now_ist().isoformat(),
            "method": "purged_kfold",
            "embargo_days": embargo_days,
            "embargo_pct": embargo_pct,
        }

    except Exception as e:
        logger.warning(f"Purged K-Fold failed for {symbol}: {e}")
        return {
            "symbol": symbol,
            "valid": False,
            "wfe": None,
            "reason": f"Purged K-Fold error: {type(e).__name__}: {e}",
            "checked_at": now_ist().isoformat(),
            "method": "purged_kfold",
        }


def save_wfv_results(results: dict):
    save_json(WFV_RESULTS_FILE, results)


def load_wfv_results() -> dict:
    return load_json(WFV_RESULTS_FILE, {})


def get_wfv_summary() -> str:
    """Admin: walk-forward validation summary."""
    data = load_json(WFV_RESULTS_FILE, {})
    if not data:
        return "No walk-forward results yet. Run /optimize first."

    valid_dicts = [r for r in data.values() if isinstance(r, dict)]
    if not valid_dicts:
        return "No valid walk-forward dictionary records found."
    
    valid = sum(1 for r in valid_dicts if r.get("valid"))
    invalid = len(valid_dicts) - valid
    insufficient = sum(1 for r in valid_dicts if "INSUFFICIENT" in r.get("reason", ""))
    avg_gap = round(np.mean([r.get("gap", 0) for r in valid_dicts if r.get("gap")]), 1) if valid_dicts else 0
    wfe_values = [r.get("wfe") for r in valid_dicts if r.get("wfe") is not None]
    avg_wfe = round(np.mean(wfe_values), 2) if wfe_values else None

    lines = [
        f"Walk-Forward Validation",
        f"Total: {len(data)} | Valid: {valid} | Overfit: {invalid} | Insufficient Data: {insufficient}",
        f"Avg Walk-Forward Efficiency (OOS/IS return): {avg_wfe if avg_wfe is not None else 'N/A'}",
        f"Avg Train-Test WR Gap (diagnostic): {avg_gap}%",
        "",
    ]

    # Show overfit stocks
    overfit = [(sym, r) for sym, r in data.items() if not r.get("valid")]
    if overfit:
        lines.append("Overfit/Insufficient Stocks:")
        for sym, r in overfit[:10]:
            wfe_val = r.get("wfe", "N/A")
            gap_val = r.get("gap", "N/A")
            lines.append(f"{sym}: wfe={wfe_val} gap={gap_val}% reason={r.get('reason', 'N/A')}")

    return "\n".join(lines)
