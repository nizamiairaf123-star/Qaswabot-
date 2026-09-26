"""
capital_drawdown_manager.py — Macro-adjusted Risk & Daily Budget
FIX #12 & FIX #13
"""

import logging
from datetime import datetime
from utils import load_json
from config import PARAMS

logger = logging.getLogger(__name__)

# v5.7: macro values config-driven (EXTERNAL_FACT) — single source config.PARAMS
INDIA_MACRO = {
    "gdp_growth_pct": float(PARAMS.get("india_gdp_growth_pct", 6.8)),
    "inflation_pct": float(PARAMS.get("india_inflation_pct", 4.45)),
    "risk_free_rate_pct": float(PARAMS.get("india_risk_free_rate_pct", 7.0)),
    "updated_at": "CONFIG_DRIVEN",
    "warn_days": int(PARAMS.get("macro_warn_days", 90)),
}

def _check_macro_staleness():
    """
    Warn if INDIA_MACRO data is stale (config-driven values → skip).

    [NOTE] This local check is intentionally a no-op in the current v5.7
    single-source design — INDIA_MACRO["updated_at"] is a hardcoded literal
    "CONFIG_DRIVEN" and nothing in this module ever changes it, so the
    warning below never fires. The REAL staleness escalation (with an
    admin alert, not just a log line) lives in macro_refresh.py's
    apply_macro_override(), which runs at boot (see bot.py) and checks the
    actual override file's saved_at age. Left here only for defensive
    completeness in case a future change starts writing updated_at.
    """
    from utils import now_ist
    if INDIA_MACRO.get("updated_at") == "CONFIG_DRIVEN":
        return
    try:
        updated = datetime.fromisoformat(INDIA_MACRO.get("updated_at", "2020-01-01"))
        age_days = (now_ist().replace(tzinfo=None) - updated.replace(tzinfo=None)).days
        if age_days > INDIA_MACRO.get("warn_days", 90):
            logger.warning(f"INDIA_MACRO data is {age_days} days old. Consider updating.")
    except (ValueError, TypeError):
        pass


def calculate_minimum_return_hurdle() -> float:
    _check_macro_staleness()
    return INDIA_MACRO["risk_free_rate_pct"] + (INDIA_MACRO["inflation_pct"] * float(PARAMS.get("hurdle_inflation_weight", 0.5)))


def calculate_optimal_risk_per_trade(symbol: str = None, capital: float = None) -> dict:
    hurdle = calculate_minimum_return_hurdle()

    # Strict owner-engine only — no hardcoded defaults
    expected_win_rate = None
    expected_win_loss_ratio = None

    if symbol:
        try:
            wfv = load_json("data/walk_forward_results.json", {})
            opt = load_json("data/optimizer_results.json", {})
            if symbol in wfv and isinstance(wfv[symbol], dict) and wfv[symbol].get("test_wr"):
                expected_win_rate = float(wfv[symbol]["test_wr"]) / 100.0
            elif isinstance(opt, dict) and symbol in opt.get("results", {}):
                s_opt = opt["results"][symbol]
                if s_opt.get("win_rate_pct"):
                    expected_win_rate = float(s_opt["win_rate_pct"]) / 100.0
                if s_opt.get("profit_factor") and float(s_opt["profit_factor"]) > 0:
                    expected_win_loss_ratio = float(s_opt["profit_factor"])
        except (TypeError, ValueError, KeyError) as e:
            logger.debug(f"_get_symbol_economics: Symbol data parse failed: {type(e).__name__}: {e}")

    if expected_win_rate is None or expected_win_loss_ratio is None:
        # Portfolio-level owner-engine fallback (Tier 1, same source file this
        # module already reads in get_verified_financial_economics()).
        # Activates when no symbol is given (e.g. calculate_daily_risk_budget)
        # or when per-symbol WFV/optimizer data is unavailable.
        try:
            backtest = load_json("data/backtest_results.json", {})
            summary = backtest.get("summary", {}) if isinstance(backtest, dict) else {}
            if summary.get("win_rate_pct"):
                expected_win_rate = float(summary["win_rate_pct"]) / 100.0
            # Kelly's formula needs b = avg_win/avg_loss ("win_loss_ratio"), NOT the
            # conventional aggregate profit_factor (gross_profit/gross_loss) — these
            # only coincide at exactly 50% win rate. backtester.py writes both fields
            # correctly into this same summary; prefer the correct one.
            if summary.get("win_loss_ratio") and float(summary["win_loss_ratio"]) > 0:
                expected_win_loss_ratio = float(summary["win_loss_ratio"])
            elif summary.get("profit_factor") and float(summary["profit_factor"]) > 0:
                expected_win_loss_ratio = float(summary["profit_factor"])
        except (TypeError, ValueError, KeyError) as e:
            logger.debug(f"_get_portfolio_economics: Summary parse failed: {type(e).__name__}: {e}")

    if expected_win_rate is None or expected_win_loss_ratio is None:
        return {"error": "No verified WFV/optimizer/backtest data available"}

    if expected_win_loss_ratio <= 0:
        return {"error": "Invalid verified win_loss_ratio from owner data"}

    kelly = (expected_win_loss_ratio * expected_win_rate - (1.0 - expected_win_rate)) / expected_win_loss_ratio
    half_kelly = kelly / 2.0

    inflation = INDIA_MACRO["inflation_pct"]
    _base = float(PARAMS.get("macro_adj_inflation_base", 4.0))
    _slope = float(PARAMS.get("macro_adj_inflation_slope", 0.02))
    macro_adjustment = 1.0 + (inflation - _base) * _slope

    optimal_risk = half_kelly * macro_adjustment * 100.0

    return {
        "kelly_pct": round(kelly * 100, 2),
        "half_kelly_pct": round(half_kelly * 100, 2),
        "macro_adjustment": round(macro_adjustment, 3),
        "optimal_risk_per_trade_pct": round(optimal_risk, 2),
        "basis": f"True Institutional Half-Kelly (WR={expected_win_rate*100:.1f}%, R:R={expected_win_loss_ratio:.2f}) + India macro",
    }



def _gz_cushion(daily_risk_amt: float) -> tuple:
    """
    [VERIFIED FRAME + OUR IMPLEMENTATION] DD-control cushion scaling.
    Frame (verified): Grossman & Zhou 1993 — risky allocation ∝ cushion above
    floor. Implementation: LINEAR cushion scaling = CPPI family — Black & Jones
    1987 (CPPI with multiplier 1.0). G&Z ka exact optimal formula (exponential
    utility) yahan NAHI hai — uska frame, CPPI ka simple roop. Honest tag.
    Ye implementation: aaj ka realized loss jitna zyada,
    din ka bacha risk budget utna kam — smooth, banayem binary-only cap ke saath.
    Returns (ratio_in_[0,1], remaining_amt). Koi bhi data missing → (1.0, full)
    = exact old behavior (fail-open, kuch band nahi).
    """
    try:
        from safety_manager import _load as _safety_load, _reset_if_new_day
        from config import PARAMS as _P  # noqa
        sd = _reset_if_new_day(_safety_load()) or {}
        day_pnl = float(sd.get("day_pnl", 0) or 0)
        if daily_risk_amt <= 0:
            return 1.0, float(daily_risk_amt)
        if day_pnl >= 0:
            return 1.0, float(daily_risk_amt)
        ratio = max(0.0, 1.0 + day_pnl / float(daily_risk_amt))
        return round(ratio, 3), round(float(daily_risk_amt) * ratio, 2)
    except Exception as e:
        logger.debug(f"_gz_cushion failed (neutral): {e}")
        return 1.0, float(daily_risk_amt) if daily_risk_amt else 0.0

def calculate_daily_risk_budget(capital: float, bot_health: float = 100.0) -> dict:
    if capital <= 0:
        return {"error": "Invalid capital"}

    risk_ctx = calculate_optimal_risk_per_trade(capital=capital)
    base_risk_pct = float(risk_ctx.get("optimal_risk_per_trade_pct") or 0)
    if base_risk_pct <= 0:
        return {"error": "No verified optimal risk from owner engine"}

    # Owner engine: health and regime multipliers only
    try:
        from portfolio_health import get_health_multiplier
        health_mult = float(get_health_multiplier())
    except (ImportError, RuntimeError, ValueError) as e:
        logger.warning(f"calculate_optimal_risk_per_trade: Health multiplier failed: {type(e).__name__}: {e}")
        return {"error": "No verified health multiplier from owner engine"}

    try:
        from regime_manager import get_regime_size_multiplier
        regime_mult = float(get_regime_size_multiplier())
    except (ImportError, RuntimeError, ValueError) as e:
        logger.warning(f"calculate_optimal_risk_per_trade: Regime multiplier failed: {type(e).__name__}: {e}")
        return {"error": "No verified regime multiplier from owner engine"}

    adjusted_risk_pct = base_risk_pct * health_mult * regime_mult
    # OWNER DECISION (approved): hard ceiling at daily_loss_limit_pct (2%).
    # The dynamic Half-Kelly/health/regime budget above had no upper clamp --
    # under strong health/regime conditions it could compute a daily risk
    # budget ABOVE the owner's stated max risk appetite. The owner has now
    # explicitly approved capping it here: the dynamic calc may still produce
    # a LOWER (more conservative) budget when health/regime warrant it, but
    # it can never exceed this ceiling.
    max_daily_risk_pct = float(PARAMS.get("daily_loss_limit_pct", 2.0))
    adjusted_risk_pct = min(adjusted_risk_pct, max_daily_risk_pct)
    daily_risk_amt = capital * adjusted_risk_pct / 100.0

    # ── [Method upgrade 2026-07-30] Cushion-scaled remaining risk (ADD-ONLY) ──
    # [Method: Grossman & Zhou, "Optimal investment strategies for controlling
    #  drawdowns", Mathematical Finance 1993 — risky allocation ∝ cushion above
    #  floor; cushion-scaling family: CPPI — Black & Jones 1987, Perold & Sharpe 1988]
    # Cushion = din ka bacha budget (full cap − aaj ka realized loss). Ye sirf
    # NAYE keys deta hai; max_daily_loss (full-day cap) UNCHANGED → purane
    # consumers (is_daily_limit_hit etc.) ka behavior bilkul same. Fail→ratio 1.0.
    gz_ratio, gz_remaining = _gz_cushion(daily_risk_amt)

    return {
        "capital": capital,
        "base_risk_pct": round(base_risk_pct, 4),
        "health_multiplier": round(health_mult, 2),
        "regime_multiplier": round(regime_mult, 2),
        "adjusted_risk_pct": round(adjusted_risk_pct, 4),
        "daily_risk_amount": round(daily_risk_amt, 2),
        "max_daily_loss": round(daily_risk_amt, 2),
        "gz_cushion_ratio":    round(gz_ratio, 3),     # NEW (G&Z 1993)
        "gz_remaining_amount": round(gz_remaining, 2), # NEW (G&Z 1993)
    }


def calculate_capital_drawdown_limits(capital: float, bot_health: float = 100.0, symbol: str = None) -> dict:
    if capital <= 0:
        return {"error": "Invalid capital"}

    # Owner engine: survival_manager is the single source for drawdown limits
    try:
        from survival_manager import calculate_survival_plan
        ctx = get_verified_financial_economics(symbol=symbol)
        expected_monthly_return_pct = max(0.0, ctx["avg_net_return_per_trade_pct"] * ctx["expected_trades_per_month"])
        plan = calculate_survival_plan(
            capital=capital,
            expected_monthly_return_pct=expected_monthly_return_pct,
            monthly_survival_target=ctx["monthly_benchmark"],
            bot_health_pct=bot_health,
        )
        if not plan.get("error"):
            return {
                "soft_dd_pct": float(plan["soft_pct"]),
                "hard_dd_pct": float(plan["hard_pct"]),
                "circuit_dd_pct": float(plan["circuit_pct"]),
                "soft_dd_amt": float(plan["soft_loss_amt"]),
                "hard_dd_amt": float(plan["hard_loss_amt"]),
                "circuit_dd_amt": float(plan["circuit_loss_amt"]),
                "source": "survival_manager"
            }
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"calculate_capital_drawdown_limits: Plan parse failed: {type(e).__name__}: {e}")

    return {"error": "No verified survival owner data"}


def get_verified_financial_economics(symbol: str = None) -> dict:
    """Decision 01/03/04/05 owner engine using existing verified repository data only."""
    optimizer = load_json("data/optimizer_results.json", {})
    backtest = load_json("data/backtest_results.json", {})
    summary = backtest.get("summary", {}) if isinstance(backtest, dict) else {}
    source = backtest.get("source", "backtest") if isinstance(backtest, dict) else "backtest"

    stock_result = {}
    if symbol and isinstance(optimizer, dict):
        stock_result = optimizer.get("results", {}).get(symbol, {})

    analysis_window_days = int(backtest.get("analysis_window_days", 0) or 0)
    if analysis_window_days <= 0:
        # Owner engine: use maximum available data from optimizer/backtest results
        analysis_window_days = int(backtest.get("max_historical_days", 7300) or 7300)
    analysis_months = max(1.0, analysis_window_days / 30.44)

    if stock_result:
        trades = float(stock_result.get("total_trades", 0) or 0)
        expected_trades_per_month = trades / analysis_months if trades > 0 else 1.0
        avg_net_return_per_trade_pct = float(stock_result.get("avg_return_pct", 0) or 0)
    else:
        total_trades = float(summary.get("total_trades", 0) or 0)
        tested_symbols = max(1.0, float(backtest.get("successful", 0) or backtest.get("total_symbols", 1) or 1))
        expected_trades_per_month = (total_trades / tested_symbols) / analysis_months if total_trades > 0 else 1.0
        avg_net_return_per_trade_pct = float(summary.get("avg_return_pct", 0) or 0)

    if avg_net_return_per_trade_pct <= 0:
        avg_net_return_per_trade_pct = max(0.1, float(summary.get("total_return_pct", 0) or 0) / max(1.0, float(summary.get("total_trades", 1) or 1)))

    subscription_fee = float(PARAMS.get("monthly_subscription_fee", 3000.0) or 3000.0)
    monthly_benchmark = max(subscription_fee, float(PARAMS.get("monthly_survival_target", subscription_fee) or subscription_fee))

    return {
        "subscription_fee": round(subscription_fee, 2),
        "monthly_benchmark": round(monthly_benchmark, 2),
        "expected_trades_per_month": round(max(1.0, expected_trades_per_month), 2),
        "avg_net_return_per_trade_pct": round(max(0.1, avg_net_return_per_trade_pct), 4),
        "analysis_window_days": analysis_window_days,
        "source": source,
    }


def get_validator_max_drawdown_pct(capital: float = None, bot_health: float = 100.0, symbol: str = None) -> float:
    if capital is None or capital <= 0:
        capital = float(PARAMS["validator_reference_capital"])
    limits = calculate_capital_drawdown_limits(capital, bot_health, symbol=symbol)
    if limits.get("error"):
        return {"error": "No verified survival data for validator max drawdown"}
    hard_dd = limits.get("hard_dd_pct")
    if hard_dd is None:
        return {"error": "No verified hard drawdown from owner engine"}
    return round(abs(float(hard_dd)), 2)


def calculate_head_of_calculation_hurdles(capital: float, subscription_fee: float = None, expected_trades_per_month: int = None, avg_net_return_per_trade_pct: float = None, symbol: str = None) -> dict:
    """Decision 01/03/04/05 single source of truth for stage-readiness economics."""
    if capital <= 0:
        return {"error": "Invalid calculation inputs"}

    ctx = get_verified_financial_economics(symbol=symbol)
    subscription_fee = float(subscription_fee if subscription_fee is not None else ctx["subscription_fee"])
    expected_trades_per_month = float(expected_trades_per_month if expected_trades_per_month is not None else ctx["expected_trades_per_month"])
    avg_net_return_per_trade_pct = float(avg_net_return_per_trade_pct if avg_net_return_per_trade_pct is not None else ctx["avg_net_return_per_trade_pct"])

    if expected_trades_per_month <= 0 or avg_net_return_per_trade_pct <= 0:
        return {"error": "Invalid calculation inputs"}

    # Owner engine: stage multiplier and health floor are derived from this calculation (no PARAMS defaults)
    stage_1_mult = 0.10
    monthly_earning_rate = stage_1_mult * expected_trades_per_month * (avg_net_return_per_trade_pct / 100.0)
    min_viable_capital_stage_1 = subscription_fee / monthly_earning_rate if monthly_earning_rate > 0 else 0.0

    current_stage_1_earnings_at_100_health = capital * monthly_earning_rate
    if current_stage_1_earnings_at_100_health > 0:
        min_health_floor_pct = max(10.0, min(100.0, (subscription_fee / current_stage_1_earnings_at_100_health) * 100.0))
    else:
        min_health_floor_pct = 100.0

    return {
        "capital": round(capital, 2),
        "subscription_fee": round(subscription_fee, 2),
        "expected_trades_per_month": round(expected_trades_per_month, 2),
        "avg_net_return_per_trade_pct": round(avg_net_return_per_trade_pct, 4),
        "monthly_benchmark": ctx["monthly_benchmark"],
        "analysis_window_days": ctx["analysis_window_days"],
        "min_viable_capital_stage_1": round(min_viable_capital_stage_1, 2),
        "dynamic_health_floor_pct": round(min_health_floor_pct, 1),
        "viable_at_stage_1": capital >= min_viable_capital_stage_1,
        "source": "Tier 2 Head of Calculation Chain Math",
    }
