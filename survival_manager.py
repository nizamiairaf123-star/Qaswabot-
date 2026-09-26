"""
survival_manager.py — Capital survival calculation
FIX-03: Individual investment based Soft/Hard/Circuit suggestion

Principle:
- Business pause ho sakta hai, bandh nahi.
- Circuit breaker fixed % nahi; capital + recovery ability + survival benchmark se calculate hota hai.
"""

import logging
from config import PARAMS

logger = logging.getLogger(__name__)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _fmt_inr(value: float) -> str:
    value = float(value or 0)
    sign = "-" if value < 0 else ""
    return f"{sign}Rs.{abs(value):,.0f}"


def _fmt_pct(value: float) -> str:
    value = float(value or 0)
    return f"{value:.2f}%"


def get_bot_health_pct() -> float:
    """
    Returns current bot/portfolio health score.
    100 = full health.

    FIX: previously defaulted to 100.0 (perfect health) if the health
    calculation itself failed -- meaning a bug/crash in the health-scoring
    pipeline would silently maximize Kelly position sizing exactly when
    the health system couldn't be trusted. Now fails conservatively to
    0.0, which get_health_multiplier() clamps to its existing
    MIN_HEALTH_CAPITAL_FLOOR (0.10x) rather than erroring -- reduced
    sizing on failure, not maximum sizing.
    """
    try:
        from portfolio_health import calculate_health_score
        return float(calculate_health_score())
    except (ImportError, RuntimeError, ValueError) as e:
        logger.warning(f"get_bot_health_pct: Health score failed, defaulting to 0 (conservative): {type(e).__name__}: {e}")
        return 0.0


def get_verified_monte_carlo_dd_pct() -> float:
    """
    [VERIFIED QUANT METHOD] Reads the portfolio-level Monte Carlo safe-DD
    percentage computed by backtester.run_full_backtest() -- a real
    bootstrap simulation over actual historical trade returns (see
    backtester.calculate_monte_carlo_dd_pct for method and sources).

    Returns None if no verified value is available (backtest never run,
    or insufficient trade history for the simulation to be statistically
    meaningful). Per Constitution Art. 2.4a, no fallback number is
    invented here -- the caller must handle None by failing closed, not
    by substituting a guess.
    """
    try:
        from config import BACKTEST_RESULTS_FILE
        from utils import load_json
        data = load_json(BACKTEST_RESULTS_FILE, {})
        value = data.get("portfolio_monte_carlo_dd_pct")
        return float(value) if value is not None else None
    except (TypeError, ValueError, KeyError) as e:
        logger.debug(f"get_verified_monte_carlo_dd_pct: Read failed: {type(e).__name__}: {e}")
        return None


def calculate_survival_plan(
    capital: float,
    expected_monthly_return_pct: float,
    monthly_survival_target: float = None,
    bot_health_pct: float = None,
    regime_multiplier: float = 1.0,
    monte_carlo_safe_dd_pct: float = None,
    human_max_cap_pct: float = None,
) -> dict:
    """
    Individual capital based survival plan.

    expected_monthly_return_pct:
        Latest strategy/backtest/simulation expected monthly return %.

    monthly_survival_target:
        Example Rs.20,000 benchmark. Not guaranteed profit.

    Circuit DD is calculated from:
        capital, expected monthly profit, bot health, regime, survival benchmark,
        Monte Carlo/worst DD cap, and human max cap.
    """

    capital = float(capital or 0)
    if capital <= 0:
        return {"error": "Invalid capital"}

    monthly_survival_target = float(
        monthly_survival_target
        if monthly_survival_target is not None
        else PARAMS.get("monthly_survival_target", 20000)
    )

    if human_max_cap_pct is not None:
        try:
            human_max_cap_pct = float(human_max_cap_pct)
        except (ValueError, TypeError):
            human_max_cap_pct = None

    min_circuit_pct = float(PARAMS["min_circuit_dd_pct"])
    recovery_fraction = float(PARAMS.get("survival_recovery_fraction", 0.25))
    min_recovery_months = float(PARAMS.get("min_recovery_months", 2.0))
    max_recovery_months = float(PARAMS.get("max_recovery_months", 8.0))

    bot_health_pct = float(bot_health_pct if bot_health_pct is not None else get_bot_health_pct())
    health_multiplier = _clamp(bot_health_pct / 100.0, 0.10, 1.0)

    regime_multiplier = float(regime_multiplier or 1.0)
    expected_monthly_return_pct = float(expected_monthly_return_pct or 0.0)

    # Effective realistic monthly profit after health/regime adjustment
    expected_monthly_profit = (
        capital
        * max(expected_monthly_return_pct, 0.0)
        / 100.0
        * health_multiplier
        * regime_multiplier
    )

    # Rs.20k is a benchmark, not guaranteed profit
    if expected_monthly_profit > 0:
        recovery_base = min(expected_monthly_profit, monthly_survival_target)
    else:
        recovery_base = 0.0

    # Larger capital can tolerate a little more recovery time, but capped
    survival_months = capital / monthly_survival_target if monthly_survival_target > 0 else 0
    allowed_recovery_months = _clamp(
        survival_months * recovery_fraction,
        min_recovery_months,
        max_recovery_months,
    )

    raw_circuit_loss = recovery_base * allowed_recovery_months
    raw_circuit_pct = (raw_circuit_loss / capital * 100.0) if capital > 0 else 0.0

    # Monte Carlo / worst DD cap: use the REAL verified bootstrap-simulation
    # value (backtester.run_full_backtest -> calculate_monte_carlo_dd_pct)
    # if the caller didn't explicitly supply one. Per Constitution Art.
    # 2.4a, this must never derive from daily_loss_limit_pct (a different,
    # unrelated business concept), and no number is invented if genuinely
    # unavailable.
    if monte_carlo_safe_dd_pct is None or float(monte_carlo_safe_dd_pct or 0) <= 0:
        monte_carlo_safe_dd_pct = get_verified_monte_carlo_dd_pct()

    caps = []
    if monte_carlo_safe_dd_pct is not None:
        caps.append(abs(float(monte_carlo_safe_dd_pct)))
    if human_max_cap_pct is not None and human_max_cap_pct > 0:
        caps.append(human_max_cap_pct)

    if raw_circuit_pct <= 0 and not caps:
        # Neither the economics-based recovery calculation nor a verified
        # Monte Carlo value is available -- fail closed rather than invent
        # a floor. Constitution Art. 2.4a: only daily_loss_limit_pct (2%)
        # is a permitted fixed value; this is not that value.
        return {
            "error": (
                "No verified circuit-DD basis available: economics-based "
                "recovery calculation produced no positive value, and no "
                "verified Monte Carlo backtest data exists yet. Run a "
                "full backtest to generate verified data before this "
                "capital's survival plan can be calculated."
            )
        }
    elif raw_circuit_pct <= 0:
        final_circuit_pct = min([min_circuit_pct] + caps)
    else:
        final_circuit_pct = min([raw_circuit_pct] + caps) if caps else raw_circuit_pct
        final_circuit_pct = max(final_circuit_pct, min_circuit_pct)

    # ── PHASE-3 PATCH (ADD-ONLY): machine-proposed tier multipliers ──
    # [Method: VaR quantile mapping of pooled bad-day losses — JP Morgan
    #  RiskMetrics, 1994; clipped to owner policy windows (dd_policy.py)]
    # [Design: hard floor machine can't cross — SEC Rule 15c3-5 (2010) /
    #  Knight Capital 2013 enforcement; MiFID II Art.17 kill-switch requirement]
    # SAFETY: data insufficient → None → EXISTING PARAMS mults (old behavior).
    soft_mult = float(PARAMS["survival_soft_mult"])
    hard_mult = float(PARAMS["survival_hard_mult"])
    try:
        from dd_policy import suggested_tier_multipliers
        tiers = suggested_tier_multipliers(None)  # portfolio pooled level
        if tiers and tiers.get("soft_mult") is not None and tiers.get("hard_mult") is not None:
            soft_mult = float(tiers["soft_mult"])
            hard_mult = float(tiers["hard_mult"])
    except Exception:
        pass
    soft_pct = final_circuit_pct * soft_mult
    hard_pct = final_circuit_pct * hard_mult

    recovery_months_at_circuit = (
        (capital * final_circuit_pct / 100.0) / recovery_base
        if recovery_base > 0 else None
    )

    status = "OK" if expected_monthly_profit > 0 else "STRATEGY_WEAK"

    return {
        "status": status,
        "capital": round(capital, 2),
        "monthly_survival_target": round(monthly_survival_target, 2),
        "expected_monthly_return_pct": round(expected_monthly_return_pct, 2),
        "bot_health_pct": round(bot_health_pct, 2),
        "health_multiplier": round(health_multiplier, 2),
        "regime_multiplier": round(regime_multiplier, 2),
        "expected_monthly_profit": round(expected_monthly_profit, 2),
        "recovery_base": round(recovery_base, 2),
        "survival_months": round(survival_months, 2),
        "allowed_recovery_months": round(allowed_recovery_months, 2),
        "raw_circuit_pct": round(raw_circuit_pct, 2),
        "human_max_cap_pct": (round(human_max_cap_pct, 2) if human_max_cap_pct is not None else None),
        "monte_carlo_safe_dd_pct": (
            round(monte_carlo_safe_dd_pct, 2) if monte_carlo_safe_dd_pct is not None else None
        ),
        "soft_pct": round(soft_pct, 2),
        "hard_pct": round(hard_pct, 2),
        "circuit_pct": round(final_circuit_pct, 2),
        "soft_loss_amt": round(capital * soft_pct / 100.0, 2),
        "hard_loss_amt": round(capital * hard_pct / 100.0, 2),
        "circuit_loss_amt": round(capital * final_circuit_pct / 100.0, 2),
        "recovery_months_at_circuit": (
            round(recovery_months_at_circuit, 2)
            if recovery_months_at_circuit is not None else None
        ),
    }


def format_survival_plan(plan: dict, is_admin: bool = False) -> str:
    if not plan or plan.get("error"):
        return "Capital Survival Plan: Not available"

    lines = [
        "CAPITAL SURVIVAL PLAN",
        f"Monthly Survival Benchmark: {_fmt_inr(plan['monthly_survival_target'])}",
        f"Expected Recovery Base: {_fmt_inr(plan['recovery_base'])}/month",
        f"Recovery Capacity: {plan['allowed_recovery_months']} months",
        "",
        f"Suggested Soft Brake: -{_fmt_pct(plan['soft_pct'])} = -{_fmt_inr(plan['soft_loss_amt'])}",
        f"Suggested Hard Brake: -{_fmt_pct(plan['hard_pct'])} = -{_fmt_inr(plan['hard_loss_amt'])}",
        f"Suggested Circuit Pause: -{_fmt_pct(plan['circuit_pct'])} = -{_fmt_inr(plan['circuit_loss_amt'])}",
        "",
        "If Circuit hits:",
        "No new trades. Existing trades stay protected.",
        "Bot enters recovery watch, not shutdown.",
    ]

    if plan.get("status") == "STRATEGY_WEAK" or float(plan.get("recovery_base", 0) or 0) <= 0:
        lines.insert(3, "Status: Strategy recovery weak - wait for updated strategy.")
        lines.insert(4, "Circuit shown is minimum protection floor.")

    if plan.get("recovery_months_at_circuit") is not None:
        lines.insert(
            4,
            f"Estimated Recovery Time at Circuit: {plan['recovery_months_at_circuit']} months"
        )

    if is_admin:
        lines += [
            "",
            "Admin Calc:",
            f"Expected Monthly Return: {plan['expected_monthly_return_pct']}%",
            f"Bot Health: {plan['bot_health_pct']}%",
            f"Human Max Cap: {plan['human_max_cap_pct']}%",
            f"MC/Worst DD Cap: {plan['monte_carlo_safe_dd_pct']}%",
            f"Raw Circuit: {plan['raw_circuit_pct']}%",
            f"Status: {plan['status']}",
        ]

    return "\n".join(lines)
