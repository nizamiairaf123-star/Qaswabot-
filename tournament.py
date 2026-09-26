"""
mtf/tournament.py — 15-pair HTF/LTF tournament (Phase-2, ADD-ONLY).

[Method: Multiple Time Frame Analysis — Dr. Alexander Elder, 1986]
  Grammar: HTF sirf TREND batata hai, LTF sirf ENTRY timing deta hai.
[Method: Walk-Forward tournament selection — Robert Pardo, 2008]
  Rolling WFV loop repo ke existing walk_forward_validator (Pardo) ki
  split-math mirror karta hai — difference sirf itna: hum per-split OOS
  trade-count bhi capture karte hain (G2 guard ke liye).
[Point-in-Time standard] HTF bar tabhi dikhega jab wo COMPLETE ho chuka ho
  (T-1 lock daily ke liye) — lookahead bias structurally impossible.

User directive honored: kaun pair jeet-ta hai yeh MACHINE/data decide karta hai
("tum decide nahi kar sakte") — human sirf grammar + guard thresholds deta hai.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import MTF_TIMEFRAMES, MTF_WAREHOUSE_DIR
from utils import save_json, now_ist, append_log
from mtf.timeframes import htf_ltf_pairs, tf_rank
from mtf import warehouse

import os

TOURNAMENT_DIR = f"{MTF_WAREHOUSE_DIR}/../mtf_tournament"

# HTF bar ka "available-at" offset — kitni der baad info trader ke paas hoti hai
_MIN_DUR = {"5m": 5, "15m": 15, "30m": 30, "60m": 60, "2H": 120}

DEFAULT_PARAM_GRID = {
    "sl_pct":   [2.0, 3.0, 4.0],
    "tp1_pct":  [2.0, 3.0, 4.0],
    "ema_fast": [8, 13, 21],
    "ema_slow": [21, 34, 55],
}


def _htf_available_at(htf_index: pd.DatetimeIndex, htf_tf: str) -> pd.DatetimeIndex:
    """PIT lock: HTF bar kab 'available' hua (complete hone ke baad)."""
    if htf_tf == "1D":
        # T-1 lock: daily bar ka close NEXT business day 09:15 pe usable
        days = pd.DatetimeIndex(htf_index).normalize() + pd.offsets.BDay(1)
        return days + pd.Timedelta(hours=9, minutes=15)
    dur = _MIN_DUR.get(htf_tf)
    if dur is None:
        raise ValueError(f"unknown htf_tf={htf_tf}")
    return pd.DatetimeIndex(htf_index) + pd.Timedelta(minutes=dur)


def attach_htf_trend(ltf_df: pd.DataFrame, htf_df: pd.DataFrame,
                     htf_tf: str, ema_period: int = 20) -> pd.DataFrame:
    """
    LTF bars pe HTF trend columns attach karta hai — STRICT PIT locked.
    Columns added: htf_close, htf_ema, htf_up (bool: htf_close > htf_ema).
    [Method: HTF EMA trend filter — classic practice, Elder Triple-Screen family]
    """
    if ltf_df.empty:
        return ltf_df.copy()
    ltf = ltf_df.copy()
    ltf["ts"] = ltf.index
    ltf = ltf.sort_values("ts")

    if htf_df.empty:
        ltf["htf_close"] = np.nan
        ltf["htf_ema"] = np.nan
        ltf["htf_up"] = pd.Series([pd.NA] * len(ltf), index=ltf.index, dtype="boolean")
        return ltf.drop(columns=["ts"])

    h = pd.DataFrame(index=htf_df.index)
    h["htf_close"] = htf_df["close"]
    h["htf_ema"] = htf_df["close"].ewm(span=ema_period, adjust=False).mean()
    h = h.dropna()
    h["avail"] = _htf_available_at(h.index, htf_tf)
    h = h.sort_values("avail")

    merged = pd.merge_asof(ltf, h, left_on="ts", right_on="avail",
                           direction="backward")
    merged["htf_up"] = (merged["htf_close"] > merged["htf_ema"]).astype("boolean")
    merged = merged.set_index("ts").sort_index()
    return merged.drop(columns=["avail"], errors="ignore")


def make_pair_signal(base_signal_func, require_htf_up: bool = True):
    """
    Existing optimizer signal generator ko HTF filter se wrap karta hai.
    [Grammar: Elder 1986 — LTF signal sirf tab jab HTF trend favor me ho]
    htf_up missing (pd.NA) ho to signal BLOCK (fail-closed — bina trend info ke entry nahi).
    """
    def gen(data: pd.DataFrame, params: dict) -> list:
        signals = base_signal_func(data, params)
        if not require_htf_up or "htf_up" not in data.columns:
            return signals
        out = []
        for s in signals:
            i = s.get("idx")
            if i is None or i >= len(data):
                continue
            up = data["htf_up"].iloc[i]
            if up is pd.NA or pd.isna(up):
                continue  # fail-closed
            if bool(up):
                out.append(s)
        return out
    return gen


def rolling_oos_eval(symbol: str, data: pd.DataFrame, signal_func,
                     param_grid: dict = None, n_splits: int = 5) -> dict:
    """
    Pardo (2008) rolling walk-forward — repo ke walk_forward_validator ke
    _optimize_on_data/_evaluate_params reuse karke, PLUS OOS trade count.
    (Same split math: split_size = len/(n_splits+1), train rolls forward.)
    """
    from walk_forward_validator import _optimize_on_data, _evaluate_params

    grid = param_grid or DEFAULT_PARAM_GRID
    n = len(data)
    min_candles = 200
    if n < min_candles:
        return {"ok": False, "reason": f"INSUFFICIENT_DATA: {n} < {min_candles}",
                "wfe": None, "oos_trades": 0, "score": 0.0}

    split_size = n // (n_splits + 1)
    split_wfes, is_rets, oos_rets, oos_trades_total = [], [], [], 0
    best_params_last = None

    for i in range(n_splits):
        tr_start = i * split_size
        tr_end = tr_start + split_size
        te_end = tr_end + split_size
        if te_end > n:
            break
        train_df = data.iloc[tr_start:tr_end]
        test_df = data.iloc[tr_end:te_end]
        if len(train_df) < 50 or len(test_df) < 20:
            continue

        bp = _optimize_on_data(train_df, signal_func, grid, symbol=symbol, split_index=i)
        if not bp:
            continue
        best_params_last = bp
        tm = _evaluate_params(train_df, signal_func, bp)
        sm = _evaluate_params(test_df, signal_func, bp)
        if not tm or not sm:
            continue
        isr = tm.get("total_return_pct", 0)
        osr = sm.get("total_return_pct", 0)
        is_rets.append(isr)
        oos_rets.append(osr)
        oos_trades_total += int(sm.get("total_trades", 0))
        if isr > 0:
            split_wfes.append(osr / isr)

    if not split_wfes:
        return {"ok": False, "reason": "no positive in-sample split → WFE n/a (fail-closed)",
                "wfe": None, "oos_trades": oos_trades_total, "score": 0.0,
                "best_params": best_params_last, "oos_rets_list": oos_rets}

    wfe = round(float(np.mean(split_wfes)), 3)
    mean_oos = float(np.mean(oos_rets))
    score = round(mean_oos * min(1.0, max(0.0, wfe)), 3)  # Pardo-weighted OOS score
    return {"ok": True, "wfe": wfe, "oos_trades": oos_trades_total,
            "mean_oos_return_pct": round(mean_oos, 2),
            "mean_is_return_pct": round(float(np.mean(is_rets)), 2),
            "score": score, "best_params": best_params_last, "n_splits_done": len(split_wfes),
            "oos_rets_list": oos_rets}


def _load_tf(symbol: str, tf: str) -> pd.DataFrame:
    """Warehouse se TF load; derived TF ho to derive karke (cache-first chain)."""
    from mtf.timeframes import is_derived_tf, source_tf
    from mtf.derive import derive_tf
    df = warehouse.load_bars(symbol, tf)
    if not df.empty:
        return df
    if is_derived_tf(tf):
        src = warehouse.load_bars(symbol, source_tf(tf))
        if not src.empty:
            return derive_tf(src, tf)
    return df


def run_tournament(symbol: str, base_signal_name: str = "ema_cross",
                   n_splits: int = 5, param_grid: dict = None,
                   wfe_threshold: float = 0.5, min_trades: int = 30) -> dict:
    """
    COMPLETE tournament: 15 pairs × guards G1–G4 + 6 single-TF baselines.
    Winner = eligible pairs me highest score (Occam G4: baseline se behtar hona zaroori).
    Kuch bhi eligible na ho → winner=None, 'stay single-TF' recommendation (fail-closed honesty).
    """
    from optimizer import SIGNAL_GENERATORS, check_parameter_stability
    from mtf.guards import apply_all_guards
    from mtf.stats import deflated_sharpe_ratio
    from scipy.stats import skew as _skew, kurtosis as _kurt

    if base_signal_name not in SIGNAL_GENERATORS:
        return {"ok": False, "reason": f"unknown signal '{base_signal_name}'"}
    base_func = SIGNAL_GENERATORS[base_signal_name]

    # ── Baselines: har single-TF ka raw score (G4 ke liye best baseline) ──
    baselines = {}
    for tf in sorted(MTF_TIMEFRAMES, key=tf_rank):
        df = _load_tf(symbol, tf)
        if df.empty:
            continue
        r = rolling_oos_eval(symbol, df, base_func, param_grid, n_splits)
        baselines[tf] = r
    baseline_score = max([r["score"] for r in baselines.values() if r.get("ok")] or [0.0])

    # ── 15 pairs ──
    results = []
    grid = param_grid or DEFAULT_PARAM_GRID
    pairs_tried = htf_ltf_pairs()
    # AUDIT ADD: n_trials = every independent combination this tournament
    # actually evaluates (baselines + pairs) -- this is exactly the count
    # DSR needs to correct for the selection bias of "tried many, picked
    # the best" (Bailey & López de Prado, 2014).
    n_trials = max(1, len(baselines) + len(pairs_tried))
    for htf, ltf in pairs_tried:
        ltf_df = _load_tf(symbol, ltf)
        htf_df = _load_tf(symbol, htf)
        if ltf_df.empty or htf_df.empty:
            results.append({"pair": [htf, ltf], "ok": False,
                            "reason": "warehouse data missing", "eligible": False})
            continue
        frame = attach_htf_trend(ltf_df, htf_df, htf)
        sig = make_pair_signal(base_func, require_htf_up=True)
        r = rolling_oos_eval(f"{symbol}:{htf}/{ltf}", frame, sig, param_grid, n_splits)
        entry = {"pair": [htf, ltf], **r}
        if r.get("ok") and r.get("best_params"):
            stab = check_parameter_stability(symbol, r["best_params"], frame, sig)
            cand = {"wfe": r["wfe"], "oos_trades": r["oos_trades"],
                    "stability": stab, "score": r["score"]}
            # AUDIT ADD: compute DSR from this pair's own OOS split returns.
            # NOTE (honest limitation): n_splits is typically ~5, so
            # skew/kurtosis estimated from only ~5 points are statistically
            # noisy -- this is a real approximation, not a robust estimate;
            # still valuable as an extra discipline check, not a precise one.
            oos_list = r.get("oos_rets_list") or []
            dsr = None
            if len(oos_list) >= 3:
                arr = np.asarray(oos_list, dtype=float)
                std = float(np.std(arr))
                sr_hat = float(np.mean(arr) / std) if std > 1e-9 else 0.0
                dsr = round(deflated_sharpe_ratio(
                    sr_hat=sr_hat, n_obs=len(arr),
                    skew=float(_skew(arr)), kurt=float(_kurt(arr, fisher=False)),
                    n_trials=n_trials,
                ), 4)
            cand["dsr"] = dsr
            g = apply_all_guards(cand, baseline_score, wfe_threshold, min_trades)
            entry.update(g)
            entry["dsr"] = dsr
        else:
            entry["eligible"] = False
        results.append(entry)

    eligible = [e for e in results if e.get("ok") and e.get("eligible")]
    winner = max(eligible, key=lambda e: e["score"]) if eligible else None

    out = {
        "symbol": symbol, "signal": base_signal_name,
        "baseline_score": baseline_score, "baselines": baselines,
        "results": results,
        "winner": winner,
        "recommendation": (
            f"PAIR {winner['pair'][0]}/{winner['pair'][1]} score={winner['score']}"
            if winner else
            "NO PAIR PASSED ALL GUARDS → single-TF baseline hi rakho (Occam: simple is safer)"
        ),
        "method_attribution": (
            "Elder 1986 (MTF grammar) | Pardo 2008 (WFE, plateau, tournament selection) | "
            "Harvey & Liu 2014-15 (min trades) | Ockham c.1320 (Occam baseline) | "
            "Bailey & López de Prado 2014 (Deflated Sharpe Ratio -- G5 guard, actively used) | "
            "López de Prado 2018 (Purged K-Fold+Embargo) and Bailey et al. 2014 (PBO-CSCV) are "
            "available in mtf/stats.py but NOT yet used by this tournament (rolling Pardo WFV "
            "is the active OOS method here) -- honest note, not a claim of use."
        ),
        "decided_by": "data+tournament (machine) — human ne sirf grammar/thresholds diye",
        "ran_at": now_ist().isoformat(),
    }
    os.makedirs(TOURNAMENT_DIR, exist_ok=True)
    save_json(f"{TOURNAMENT_DIR}/{symbol.upper()}.json", out)
    try:
        append_log(f"{MTF_WAREHOUSE_DIR}/warehouse_log.txt",
                   f"TOURNAMENT {symbol}: winner={out['recommendation']}")
    except Exception:
        pass
    return out
