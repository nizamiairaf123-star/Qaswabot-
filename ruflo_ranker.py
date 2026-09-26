"""
ruflo_ranker.py — RuFlo Portfolio Ranking & Robust Optimization

CONTABU_AI_WORKFLOW_MASTER.md specifies:
- RuFlo: portfolio ranking, robust optimization, statistical optimization

This module ranks optimized stocks for portfolio selection.
Only WFV-valid stocks are ranked — overfit stocks already filtered.

Scoring components:
1. Walk-Forward Stability (WFV gap lower = better)
2. Profit Factor robustness
3. Win Rate consistency
4. Drawdown resilience
5. Stock profile diversity (volatility/sector spread)
6. Parameter stability score
"""

import logging
from utils import load_json, append_log

logger = logging.getLogger(__name__)
from config import AUDIT_LOG_FILE, PARAMS


def rank_portfolio(deployable_params: dict, all_results: dict,
                   wfv_results: dict) -> list:
    """Rank WFV-valid stocks for portfolio selection.
    
    Args:
        deployable_params: {symbol: params} — only WFV-valid stocks
        all_results: {symbol: result} — all optimization results
        wfv_results: {symbol: wfv} — walk-forward validation results
        
    Returns:
        List of dicts sorted by ruflo_score (best first)
    """
    if not deployable_params:
        return []

    ranked = []
    for symbol in deployable_params:
        result = all_results.get(symbol, {})
        wfv = wfv_results.get(symbol, {})
        profile = result.get("stock_profile", {})

        # Component 1: Walk-Forward Stability (0-25 points)
        wfv_gap = abs(wfv.get("gap", 10))
        _w = PARAMS.get("ruflo_score_weights", {"wfv": 25.0, "pf": 25.0, "wr": 20.0, "dd": 15.0, "stability": 15.0})
        _m = PARAMS.get("ruflo_multipliers", {"wfv_gap": 2.5, "pf": 12.5, "wr": 1.0, "dd": 1.5, "stability": 15.0})
        wfv_score = max(0, float(_w.get("wfv", 25.0)) - wfv_gap * float(_m.get("wfv_gap", 2.5)))

        # Component 2: Profit Factor Robustness (0-25 points)
        pf = result.get("profit_factor", 0)
        pf_score = min(float(_w.get("pf", 25.0)), max(0, (pf - 1.0) * float(_m.get("pf", 12.5))))

        # Component 3: Win Rate Consistency (0-20 points)
        wr = result.get("win_rate_pct", 0)
        wr_score = min(float(_w.get("wr", 20.0)), max(0, (wr - 40.0) * float(_m.get("wr", 1.0))))

        # Component 4: Drawdown Resilience (0-15 points)
        dd = abs(result.get("portfolio_max_dd_pct", 20))
        dd_score = max(0, float(_w.get("dd", 15.0)) - dd * float(_m.get("dd", 1.5)))

        # Component 5: Parameter Stability (0-15 points)
        stability_score = result.get("stability", {}).get("stability_score", 0)
        stability_pts = stability_score * float(_m.get("stability", 15.0))

        # Total RuFlo Score
        ruflo_score = wfv_score + pf_score + wr_score + dd_score + stability_pts

        ranked.append({
            "symbol": symbol,
            "ruflo_score": round(ruflo_score, 2),
            "wfv_score": round(wfv_score, 2),
            "pf_score": round(pf_score, 2),
            "wr_score": round(wr_score, 2),
            "dd_score": round(dd_score, 2),
            "stability_pts": round(stability_pts, 2),
            "profit_factor": pf,
            "win_rate_pct": wr,
            "total_return_pct": result.get("total_return_pct", 0),
            "wfv_gap": wfv_gap,
            "volatility": profile.get("volatility", 0),
            "signal_generator": result.get("signal_generator", "ema_cross"),
            "params_stable": result.get("params_stable", False),
        })

    # Sort by RuFlo score (best first)
    # [Method upgrade 2026-07-30] Cross-sectional z-score normalization
    # (Fama-French factor-ranking family, 1992-93): raw scores ko candidate-set
    # ke distribution me standardize karo → koi bhi ek metric scale ke wajah se
    # dominate na kare. <3 candidates → fixed-point scoring hi rahega (z-score
    # meaningful nahi hota; fail-open old behavior).
    try:
        import statistics
        if len(ranked) >= 3:
            comps = ["wfv_score", "pf_score", "wr_score", "dd_score", "stability_pts"]
            for c in comps:
                vals = [float(item.get(c, 0) or 0) for item in ranked]
                mu = statistics.mean(vals)
                sd = statistics.pstdev(vals)
                if sd > 0:
                    for item in ranked:
                        item[f"z_{c}"] = round((float(item.get(c, 0) or 0) - mu) / sd, 3)
                else:
                    for item in ranked:
                        item[f"z_{c}"] = 0.0
            # z-composite (weights proportional to existing point caps 25/25/20/15/15)
            _z = PARAMS.get("ruflo_z_weights", {"wfv": 25.0, "pf": 25.0, "wr": 20.0, "dd": 15.0, "stability": 15.0})
            for item in ranked:
                item["ruflo_z"] = round(
                    (item["z_wfv_score"] * float(_z.get("wfv", 25.0)) +
                     item["z_pf_score"] * float(_z.get("pf", 25.0)) +
                     item["z_wr_score"] * float(_z.get("wr", 20.0)) +
                     item["z_dd_score"] * float(_z.get("dd", 15.0)) +
                     item["z_stability_pts"] * float(_z.get("stability", 15.0))) / 20.0, 2)
                item["ranking_method"] = "cross-sectional z-score (Fama-French family, 1992-93)"
            ranked.sort(key=lambda x: x.get("ruflo_z", x["ruflo_score"]), reverse=True)
        else:
            for item in ranked:
                item["ranking_method"] = "fixed-point (legacy fallback — <3 candidates)"
    except Exception as _e:
        logger.warning(f"ruflo z-score failed, legacy ranking kept: {_e}")
        for item in ranked:
            item.setdefault("ranking_method", "fixed-point (z-error fallback)")
        ranked.sort(key=lambda x: x["ruflo_score"], reverse=True)
    else:
        if not any(str(item.get("ranking_method", "")).startswith("cross-sectional") for item in ranked):
            ranked.sort(key=lambda x: x["ruflo_score"], reverse=True)

    # Add rank numbers
    for i, item in enumerate(ranked, 1):
        item["rank"] = i

    # Log top 10
    for item in ranked[:10]:
        append_log(AUDIT_LOG_FILE,
                   f"RUFLO #{item['rank']} {item['symbol']}: "
                   f"score={item['ruflo_score']} "
                   f"pf={item['profit_factor']} wr={item['win_rate_pct']}% "
                   f"wfv_gap={item['wfv_gap']}%")

    return ranked


def get_top_n_stocks(n: int = None) -> list:
    """Get top N ranked stocks from latest optimization."""
    data = load_json("data/optimizer_results.json", {})
    ranking = data.get("ruflo_ranking", [])

    if not ranking:
        return []

    if n is None:
        max_slots = PARAMS.get("max_slots", 8)
        n = min(max_slots, len(ranking))

    return [r["symbol"] for r in ranking[:n]]


def get_ruflo_summary() -> str:
    """Admin: RuFlo ranking summary."""
    data = load_json("data/optimizer_results.json", {})
    ranking = data.get("ruflo_ranking", [])

    if not ranking:
        return "No RuFlo ranking yet. Run /optimize first."

    lines = [
        f"RuFlo Portfolio Ranking",
        f"Total Ranked: {len(ranking)}",
        f"",
        f"Top {min(10, len(ranking))} Stocks:",
    ]

    for r in ranking[:10]:
        stable = "✅" if r.get("params_stable") else "⚠️"
        lines.append(
            f"  #{r['rank']} {r['symbol']}: "
            f"score={r['ruflo_score']} "
            f"PF={r['profit_factor']} "
            f"WR={r['win_rate_pct']}% "
            f"Ret={r['total_return_pct']}% "
            f"WFV_gap={r['wfv_gap']}% "
            f"{stable}"
        )

    return "\n".join(lines)


def check_portfolio_diversity(selected_symbols: list) -> dict:
    """Check if selected stocks provide good portfolio diversity.
    
    Experience trader logic: Don't put all eggs in one sector/volatility basket.
    """
    if not selected_symbols:
        return {"diverse": False, "reason": "No stocks selected"}

    data = load_json("data/optimizer_results.json", {})
    results = data.get("results", {})

    volatilities = []
    sectors = set()
    generators = set()

    try:
        import pandas as pd
        from config import CUSTOM_UNIVERSE_FILE
        halal_df = pd.read_csv(CUSTOM_UNIVERSE_FILE)
    except (FileNotFoundError, OSError, ValueError) as e:
        logger.warning(f"check_portfolio_diversity: CSV load failed: {type(e).__name__}: {e}")
        halal_df = None

    for symbol in selected_symbols:
        r = results.get(symbol, {})
        profile = r.get("stock_profile", {})
        vol = profile.get("volatility", 0)
        if vol > 0:
            volatilities.append(vol)
        generators.add(r.get("signal_generator", "ema_cross"))

        if halal_df is not None:
            try:
                row = halal_df[halal_df["symbol"] == symbol]
                if not row.empty:
                    sectors.add(row["sector"].values[0])
            except (KeyError, TypeError, ValueError) as e:
                logger.debug(f"check_portfolio_diversity: Sector lookup failed for {symbol}: {type(e).__name__}: {e}")
                continue

    # Diversity checks
    issues = []

    # Check volatility spread
    if volatilities:
        vol_range = max(volatilities) - min(volatilities)
        if vol_range < 10:
            issues.append("Low volatility spread — all stocks similar risk profile")
    else:
        issues.append("No volatility data")

    # Check sector concentration
    if sectors and len(selected_symbols) > 2:
        max_sector_pct = max(
            sum(1 for s in selected_symbols
                if halal_df is not None and
                not halal_df[halal_df["symbol"] == s].empty and
                halal_df[halal_df["symbol"] == s]["sector"].values[0] == sector)
            / len(selected_symbols)
            for sector in sectors
        )
        if max_sector_pct > 0.5:
            issues.append(f"Sector concentration: {max_sector_pct:.0%} in one sector")

    # Check signal generator diversity
    if len(generators) == 1 and len(selected_symbols) > 3:
        issues.append(f"All stocks use same signal generator: {list(generators)[0]}")

    is_diverse = len(issues) == 0

    return {
        "diverse": is_diverse,
        "volatilities": volatilities,
        "sectors": list(sectors),
        "generators": list(generators),
        "issues": issues,
    }
