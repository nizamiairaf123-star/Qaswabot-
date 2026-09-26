"""
mtf/guards.py — Tournament ke 4 Guards (Gate-keeping), Phase-2, ADD-ONLY.

User directive: winner MACHINE decide kare — human sirf grammar/threshold define karta hai.
Har guard industry-verified method ka named implementation hai:

  G1  WFE >= 0.5            [Method: Walk-Forward Efficiency — Robert Pardo, 2008]
  G2  OOS trades >= 30      [Method: min sample for significance — Harvey & Liu,
                            "Backtesting"/multiple-testing work, 2014–2015]
  G3  Parameter Plateau     [Method: Parameter Stability — Pardo, 2008]
                            (repo ka existing optimizer.check_parameter_stability reuse)
  G4  Occam baseline beat   [Principle: Occam's Razor — William of Ockham, c.1320;
                            applied rule = custom engineering: pair ko SINGLE-TF
                            baseline se BEHTAR hona zaroori hai, warna simple rakh]
"""

from __future__ import annotations


def guard_wfe(wfe, threshold: float = 0.5) -> dict:
    """G1 — Pardo (2008): OOS/IS efficiency kam se kam 0.5 honi chahiye."""
    ok = (wfe is not None) and (wfe >= threshold)
    return {"guard": "G1_WFE", "pass": ok, "value": wfe,
            "method": "Walk-Forward Efficiency — R. Pardo, 2008",
            "reason": f"wfe={wfe} {'>=':s}".replace(":s", "") + f" {threshold}" if ok
                      else f"wfe={wfe} < {threshold} (overfit suspect)"}


def guard_min_trades(oos_trades: int, minimum: int = 30) -> dict:
    """G2 — Harvey & Liu (2014-15): significance ke liye min sample size."""
    ok = oos_trades >= minimum
    return {"guard": "G2_MIN_TRADES", "pass": ok, "value": oos_trades,
            "method": "min OOS sample — Harvey & Liu, 2014–15",
            "reason": f"oos_trades={oos_trades} >= {minimum}" if ok
                      else f"oos_trades={oos_trades} < {minimum} (statistically weak)"}


def guard_plateau(stability_result: dict) -> dict:
    """
    G3 — Pardo (2008) Parameter Plateau. Repo ke EXISTING
    optimizer.check_parameter_stability() ka result le-ta hai (koi re-implementation nahi).
    """
    ok = bool(stability_result and stability_result.get("stable"))
    return {"guard": "G3_PLATEAU", "pass": ok,
            "value": (stability_result or {}).get("stability_score"),
            "method": "Parameter Plateau — R. Pardo, 2008 (existing optimizer.check_parameter_stability reuse)",
            "reason": (stability_result or {}).get("reason", "no result")}


def guard_occam(pair_score: float, baseline_score: float) -> dict:
    """G4 — Occam: complex (pair) tabhi jab simple (single-TF) se score behtar ho."""
    ok = pair_score > baseline_score
    return {"guard": "G4_OCCAM", "pass": ok,
            "value": {"pair": pair_score, "baseline": baseline_score},
            "method": "Occam's Razor — W. of Ockham, c.1320 (applied: custom rule)",
            "reason": f"pair_score={pair_score:.2f} > baseline={baseline_score:.2f}" if ok
                      else f"pair_score={pair_score:.2f} <= baseline={baseline_score:.2f} → simple baseline better"}


def guard_dsr(dsr: float, threshold: float = 0.95) -> dict:
    """
    G5 — Deflated Sharpe Ratio (Bailey & López de Prado, 2014). Corrects for
    the exact selection bias this tournament itself creates (many pairs +
    baselines tried, best one picked) -- >=0.95 is the paper's own standard
    pass bar for "probably not just luck." AUDIT ADD: previously computed in
    mtf/stats.py but never actually called from the tournament despite being
    named in its own method_attribution string; this guard makes that claim
    true instead of aspirational.
    """
    ok = (dsr is not None) and (dsr >= threshold)
    return {"guard": "G5_DSR", "pass": ok, "value": dsr,
            "method": "Deflated Sharpe Ratio — Bailey & López de Prado, 2014",
            "reason": f"dsr={dsr} >= {threshold}" if ok
                      else f"dsr={dsr} < {threshold} (likely selection-bias luck, not skill)"}


def apply_all_guards(candidate: dict, baseline_score: float,
                     wfe_threshold: float = 0.5, min_trades: int = 30,
                     dsr_threshold: float = 0.95) -> dict:
    """
    candidate = {"wfe": ..., "oos_trades": ..., "stability": {...}, "score": ...,
                 "dsr": ... (optional)}
    Returns guard results + final PASS/FAIL (sabhi guards pass = eligible winner).
    G5 (DSR) is included only when candidate provides a "dsr" value -- callers
    that don't compute it yet are completely unaffected (backward compatible).
    """
    g = [
        guard_wfe(candidate.get("wfe"), wfe_threshold),
        guard_min_trades(int(candidate.get("oos_trades", 0)), min_trades),
        guard_plateau(candidate.get("stability")),
        guard_occam(float(candidate.get("score", 0.0)), float(baseline_score)),
    ]
    if candidate.get("dsr") is not None:
        g.append(guard_dsr(candidate["dsr"], dsr_threshold))
    return {"guards": g, "eligible": all(x["pass"] for x in g)}
