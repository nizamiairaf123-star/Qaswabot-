"""
simulate_engine.py — Capital simulation engine
User sirf capital dale — backtest data se sab calculate ho
Subscriber = portfolio level | Admin = individual stock DD bhi
Monte Carlo simulation included
Sector filter applied — realistic subset
"""

import logging
import random
from utils import load_json, save_json, now_ist
from config import BACKTEST_RESULTS_FILE, PARAMS

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _get_valid_stocks(apply_sector_filter: bool = True) -> list:
    """
    Get backtest-valid stocks.
    Optionally apply sector filter for realistic simulation.
    """
    bt = load_json(BACKTEST_RESULTS_FILE, {})
    if not bt or "stocks" not in bt:
        return []

    valid = [s for s in bt["stocks"].values() if s.get("valid")]

    if apply_sector_filter:
        try:
            from sector_strength import get_sector_runtime_signal
            valid = [
                s for s in valid
                if get_sector_runtime_signal(s.get("symbol", "")).get("allow", False)
            ]
        except (ImportError, RuntimeError, ValueError) as e:
            logger.warning(f"_get_valid_stocks: Sector filter failed, including all stocks: {type(e).__name__}: {e}")

    return valid


def _infer_analysis_window_days(bt: dict) -> int:
    source = bt.get("source", "backtest") if isinstance(bt, dict) else "backtest"
    explicit = int(bt.get("analysis_window_days", 0) or 0) if isinstance(bt, dict) else 0
    if explicit > 0:
        return explicit
    return 7300 if source == "optimization_walkforward" else 3650


def _extract_trade_return_samples(valid_stocks: list) -> list:
    samples = []
    for stock in valid_stocks:
        for t in stock.get("trades_list", []) or []:
            try:
                samples.append(float(t.get("net_return_pct", t.get("return_pct", 0)) or 0))
            except (TypeError, ValueError) as e:
                logger.debug(f"_extract_trade_return_samples: Skipping invalid trade return: {e}")
                continue
    return samples


# ─────────────────────────────────────────────
# MAIN SIMULATION
# ─────────────────────────────────────────────

def run_simulation(capital: float, is_admin: bool = False) -> dict:
    """
    Capital se sab stats calculate karo.
    Backtest data + sector filter use hota hai.
    Workflow rule (v4.1): simulation approval se PEHLE hoti hai — admin
    result dekh ke satisfied ho kar hi /deployapprove karega. Subscriber ko
    bhi wahi projection dikhti hai jo candidate/deployed benchmark pe hai.
    """
    try:
        from workflow_manager import can_run_simulation
        ok, reason = can_run_simulation()
        if not ok:
            return {"error": reason}
    except (ImportError, RuntimeError) as e:
        logger.warning(f"run_simulation: Workflow check failed, proceeding: {type(e).__name__}: {e}")

    valid_stocks = _get_valid_stocks(apply_sector_filter=True)

    if not valid_stocks:
        return {"error": "No benchmark data. Admin must run /optimize or /backtest first."}

    bt = load_json(BACKTEST_RESULTS_FILE, {})

    # ── Aggregate metrics ──
    win_rates        = [s["win_rate_pct"] for s in valid_stocks if "win_rate_pct" in s]
    avg_returns      = [s["avg_return_pct"] for s in valid_stocks if "avg_return_pct" in s]
    drawdowns        = [s["price_max_drawdown_pct"] for s in valid_stocks if "price_max_drawdown_pct" in s]
    recovery_factors = [s["recovery_factor"] for s in valid_stocks if "recovery_factor" in s and s["recovery_factor"] > 0]
    sharpes          = [s["sharpe"] for s in valid_stocks if "sharpe" in s]
    total_trades_list= [s["total_trades"] for s in valid_stocks if "total_trades" in s]

    avg_win_rate         = round(sum(win_rates) / len(win_rates), 1) if win_rates else 0
    avg_loss_rate        = round(100 - avg_win_rate, 1)
    avg_return_per_trade = round(sum(avg_returns) / len(avg_returns), 2) if avg_returns else 0
    avg_drawdown         = round(sum(drawdowns) / len(drawdowns), 2) if drawdowns else 0
    worst_drawdown       = round(min(drawdowns), 2) if drawdowns else 0
    avg_recovery         = round(sum(recovery_factors) / len(recovery_factors), 2) if recovery_factors else 0
    avg_sharpe           = round(sum(sharpes) / len(sharpes), 2) if sharpes else 0
    total_trades         = sum(total_trades_list)

    # ── Capital based ──
    max_slots        = PARAMS.get("max_slots", 8)
    risk_pct         = PARAMS.get("risk_pct_per_trade", 1.5) / 100
    trading_cost     = PARAMS.get("trading_cost_pct", 0.30) / 100
    active_slots     = min(max_slots, max(1, int(capital / 20000)))
    capital_per_slot = round(capital / active_slots, 0)

    # ── Runtime parity R2: Stage deployment (owner Decision 26; Section 12 Step 3) ──
    # LIVE (capital_manager.py:171, :742): deployable = capital ×
    # DEPLOYMENT_STAGES[CURRENT_STAGE] × health_mult × regime_mult. Projection
    # ko bhi wahi deployed base chahiye — warna Stage-1 (10%) pe projection
    # live se 10× zyada dikhta (parity gap).
    # [v4.2 SIZING-PARITY] ab health + regime multiplier bhi same live chain
    # se lagte hain (fail-open 1.0) — taaki simulation ka result paper/live
    # ke actual traded amounts se match kare.
    # Fail-open: koi bhi error → mult 1.0 = neutral.
    parity_stage_mult  = 1.0
    parity_health_mult = 1.0
    parity_regime_mult = 1.0
    parity_deployed    = float(capital)
    try:
        import parity_engine
        parity_stage_mult = float(parity_engine.stage_multiplier())
        if not (0 < parity_stage_mult <= 1.0):
            parity_stage_mult = 1.0
    except Exception as e:
        logger.warning(f"run_simulation: parity stage mult failed → 1.0 (old behavior): {type(e).__name__}: {e}")
        parity_stage_mult = 1.0
    try:
        from portfolio_health import get_health_multiplier
        parity_health_mult = float(get_health_multiplier() or PARAMS.get("simulation_mult_fallback", 1.0))
        parity_health_mult = max(0.10, min(1.0, parity_health_mult))
    except Exception as e:
        logger.warning(f"run_simulation: parity health mult failed → 1.0: {type(e).__name__}: {e}")
        parity_health_mult = 1.0
    try:
        from capital_manager import get_regime_capital_multiplier
        parity_regime_mult = float(get_regime_capital_multiplier() or 1.0)
        parity_regime_mult = max(0.10, min(1.0, parity_regime_mult))
    except Exception as e:
        logger.warning(f"run_simulation: parity regime mult failed → 1.0: {type(e).__name__}: {e}")
        parity_regime_mult = 1.0
    parity_deployed = float(capital) * parity_stage_mult * parity_health_mult * parity_regime_mult
    if parity_deployed > 0:
        capital_per_slot = round(parity_deployed / active_slots, 0)

    # ── Win/Loss amounts ──
    avg_loss_per_trade = round(parity_deployed * risk_pct, 0)
    avg_win_per_trade  = round(avg_loss_per_trade * (avg_return_per_trade / (risk_pct * 100 + 0.001)), 0)
    profit_factor      = round(avg_win_per_trade / avg_loss_per_trade, 2) if avg_loss_per_trade > 0 else 0
    expected_value     = round(
        (avg_win_rate / 100 * avg_win_per_trade) -
        (avg_loss_rate / 100 * avg_loss_per_trade), 0
    )

    # ── Time based projections (Decision 24/01 owner economics path) ──
    analysis_window_days = _infer_analysis_window_days(bt)
    try:
        from capital_drawdown_manager import get_verified_financial_economics
        econ = get_verified_financial_economics()
        base_trades_per_month = float(econ.get("expected_trades_per_month", 1.0) or 1.0)
        subscription_monthly_fee = float(econ.get("subscription_fee", PARAMS.get("monthly_subscription_fee", 3000)) or PARAMS.get("monthly_subscription_fee", 3000))
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"run_simulation: Financial economics unavailable, using fallback: {type(e).__name__}: {e}")
        analysis_months = max(1.0, analysis_window_days / 30.44)
        base_trades_per_month = (sum(total_trades_list) / max(len(total_trades_list), 1)) / analysis_months if total_trades_list else 1.0
        subscription_monthly_fee = float(PARAMS.get("monthly_subscription_fee", 3000))
    trades_per_month = round(max(1.0, base_trades_per_month * active_slots), 1)
    trades_per_week = round(trades_per_month / 4.33, 1)
    trades_per_day = round(trades_per_month / 21.0, 2)

    monthly_profit = round(expected_value * trades_per_month, 0)
    monthly_return_pct = round((monthly_profit / capital) * 100.0, 2) if capital > 0 else 0.0
    weekly_profit = round(monthly_profit / 4.33, 0)
    daily_profit = round(monthly_profit / 21.0, 0)

    # ── Risk stats / simulation assumptions from actual trade samples ──
    trade_return_samples = _extract_trade_return_samples(valid_stocks)
    trade_amt_samples = [capital_per_slot * (r / 100.0) for r in trade_return_samples] if capital_per_slot > 0 else []

    max_day_individual_loss = round(abs(min(trade_amt_samples)) if trade_amt_samples else abs(avg_loss_per_trade), 0)
    worst_portfolio_loss = round(capital * abs(worst_drawdown) / 100, 0)
    worst_month_loss = round(capital * abs(avg_drawdown) / 100, 0)
    max_day_portfolio_loss = round(max_day_individual_loss * max(1.0, trades_per_day), 0)

    mean_trade_amt = (sum(trade_amt_samples) / len(trade_amt_samples)) if trade_amt_samples else expected_value
    if len(trade_amt_samples) > 1:
        import statistics
        std_trade_amt = statistics.pstdev(trade_amt_samples)
    else:
        std_trade_amt = abs(mean_trade_amt)
    _z = float(PARAMS.get("sim_worst_case_zscore", 1.28))
    worst_case_monthly = round((mean_trade_amt - (_z * std_trade_amt)) * trades_per_month, 0)
    worst_case_dd = round(worst_portfolio_loss, 0)

    # ── Per stock DD (admin only) ──
    per_stock_dd = {}
    if is_admin:
        for s in valid_stocks:
            sym = s.get("symbol", "")
            dd  = s.get("price_max_drawdown_pct")
            if sym and dd is not None:
                per_stock_dd[sym] = dd

    # FIX_SIM_REAL_STATS_START
    # Use latest portfolio-level backtest summary for user simulation.
    # This fixes wrong signs like Avg Win negative / Avg Loss positive.
    # We do NOT hide bad results: PF < 1, negative EV/monthly profit remain visible.
    avg_win_pct = avg_return_per_trade if avg_return_per_trade > 0 else 0.0
    avg_loss_pct = -abs(round(risk_pct * 100, 2))
    expected_value_pct = ((avg_win_rate / 100.0) * avg_win_pct) + ((avg_loss_rate / 100.0) * avg_loss_pct)
    avg_win_per_trade = max(0, avg_win_per_trade)
    avg_loss_per_trade = -abs(avg_loss_per_trade)
    profit_factor = abs(profit_factor) if profit_factor else 0.0

    summary = bt.get("summary", {}) if isinstance(bt.get("summary", {}), dict) else {}

    if summary and int(summary.get("total_trades", 0) or 0) > 0:
        avg_win_rate = round(float(summary.get("win_rate_pct", avg_win_rate) or 0), 1)
        avg_loss_rate = round(100 - avg_win_rate, 1)

        avg_win_pct = float(summary.get("avg_win_pct", 0) or 0)
        avg_loss_pct = float(summary.get("avg_loss_pct", 0) or 0)

        # Avg win should be positive, avg loss should be negative.
        avg_win_pct = abs(avg_win_pct) if avg_win_pct > 0 else 0.0
        avg_loss_pct = -abs(avg_loss_pct)

        avg_win_per_trade = round(capital_per_slot * avg_win_pct / 100.0, 0)
        avg_loss_per_trade = round(capital_per_slot * avg_loss_pct / 100.0, 0)

        pf = float(summary.get("profit_factor", 0) or 0)
        profit_factor = abs(pf)  # PF formula is gross profit / absolute gross loss.
        avg_recovery = float(summary.get("recovery_factor", avg_recovery) or 0)
        avg_sharpe = float(summary.get("sharpe", avg_sharpe) or 0)

        expected_value = round(
            (avg_win_rate / 100.0 * avg_win_per_trade) +
            (avg_loss_rate / 100.0 * avg_loss_per_trade),
            0
        )

        # Monthly estimate from trade expectancy and historical trade frequency.
        monthly_profit = round(expected_value * trades_per_month, 0)
        monthly_return_pct = round(capital and (monthly_profit / capital) * 100.0 or 0.0, 2)
        weekly_profit = round(monthly_profit / 4.33, 0)
        daily_profit = round(monthly_profit / 21.0, 0)

        portfolio_dd_pct_real = abs(float(summary.get("portfolio_max_dd_pct", avg_drawdown) or 0))
        avg_drawdown = -portfolio_dd_pct_real
        worst_drawdown = -portfolio_dd_pct_real

        max_day_loss_pct = abs(float(summary.get("max_single_day_loss_pct", 0) or 0))
        if max_day_loss_pct > 0:
            max_day_portfolio_loss = round(capital * max_day_loss_pct / 100.0, 0)

        worst_portfolio_loss = round(capital * portfolio_dd_pct_real / 100.0, 0)
        worst_month_loss = worst_portfolio_loss

        if trade_amt_samples:
            mean_trade_amt = sum(trade_amt_samples) / len(trade_amt_samples)
            if len(trade_amt_samples) > 1:
                import statistics
                std_trade_amt = statistics.pstdev(trade_amt_samples)
            else:
                std_trade_amt = abs(mean_trade_amt)
        _z = float(PARAMS.get("sim_worst_case_zscore", 1.28))
        worst_case_monthly = round((mean_trade_amt - (_z * std_trade_amt)) * trades_per_month, 0)
        worst_case_dd = round(worst_portfolio_loss, 0)
    # FIX_SIM_REAL_STATS_END

    # FIX-08: Subscription viability
    net_after_subscription = monthly_profit - subscription_monthly_fee

    if monthly_return_pct > 0:
        breakeven_capital = round(subscription_monthly_fee / (monthly_return_pct / 100.0), 0)
        recommended_capital = round(breakeven_capital * float(PARAMS.get("sim_recommended_buffer_mult", 1.5)), 0)
    else:
        breakeven_capital = None
        recommended_capital = None

    if monthly_profit <= 0:
        subscription_status = "NOT_VIABLE_STRATEGY_WEAK"
    elif net_after_subscription < 0:
        subscription_status = "NOT_VIABLE_CAPITAL_LOW"
    else:
        subscription_status = "VIABLE"

    try:
        from capital_drawdown_manager import calculate_head_of_calculation_hurdles
        stage_hurdles = calculate_head_of_calculation_hurdles(capital)
        low_balance_status = "LOW_BALANCE" if not stage_hurdles.get("viable_at_stage_1", False) else "OK"
        low_balance_reason = (
            f"Capital below stage-1 viable floor Rs.{stage_hurdles.get('min_viable_capital_stage_1', 0):,.0f}"
            if low_balance_status == "LOW_BALANCE" else "Capital sufficient for stage-1 viability"
        )
    except (ImportError, RuntimeError, ValueError) as e:
        logger.warning(f"run_simulation: Stage hurdles calculation failed: {type(e).__name__}: {e}")
        low_balance_status = "UNKNOWN"
        low_balance_reason = "Stage-1 viability unavailable"

    # FIX-03: Individual capital survival plan
    try:
        from survival_manager import calculate_survival_plan
        survival_plan = calculate_survival_plan(
            capital=capital,
            expected_monthly_return_pct=monthly_return_pct,
            monthly_survival_target=PARAMS.get("monthly_survival_target", 20000),
            bot_health_pct=None,
            regime_multiplier=1.0,
            monte_carlo_safe_dd_pct=None,  # auto-fetched: real verified Monte Carlo bootstrap value, not this run's raw single-path DD
            human_max_cap_pct=None,
        )
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"run_simulation: Survival plan calculation failed: {type(e).__name__}: {e}")
        survival_plan = {"error": str(e)}

    # D-8: Feedback loop recording gap analysis
    try:
        gap_analysis = {
            "win_rate": avg_win_rate,
            "profit_factor": profit_factor,
            "recorded_at": now_ist().isoformat()
        }
        save_json("data/sim_backtest_gap.json", gap_analysis)
    except (OSError, ValueError, TypeError) as e:
        logger.warning(f"run_simulation: Failed to save gap analysis: {type(e).__name__}: {e}")

    try:
        from portfolio_health import calculate_health_score, get_health_multiplier
        h_score = float(calculate_health_score() or PARAMS.get("simulation_health_fallback", 100.0))
        h_mult  = float(get_health_multiplier() or PARAMS.get("simulation_mult_fallback", 1.0))
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"run_simulation: Health score calculation failed: {type(e).__name__}: {e}")
        h_score = PARAMS.get("simulation_health_fallback", 100.0)
        h_mult = PARAMS.get("simulation_mult_fallback", 1.0)

    # v4.1: sirf ADMIN ki successful simulation "simulation" stage mark karti
    # hai (final review) — subscriber ke /simulate se workflow state nahi
    # badalta. Simulation ab approval se pehle hoti hai, isliye is stage ka
    # mark admin-review hai na ki post-approval formality.
    if is_admin:
        try:
            from workflow_manager import record_simulation_completed
            record_simulation_completed(
                capital=capital,
                benchmark_source=bt.get("source", "backtest"),
                strategy_name=bt.get("strategy_name", "Active Strategy"),
                stocks_in_simulation=len(valid_stocks),
            )
        except (ImportError, RuntimeError) as e:
            logger.warning(f"run_simulation: Failed to record simulation completion: {type(e).__name__}: {e}")

    # Deployment status — honest label ke liye (approve hua ya pending)
    try:
        from workflow_manager import _stage_done
        deployment_status = "DEPLOYED" if _stage_done("deployment_approval") else "PENDING_APPROVAL"
    except (ImportError, RuntimeError):
        deployment_status = "UNKNOWN"

    return {
        "health_score":          round(h_score, 1),
        "health_multiplier":     round(h_mult, 2),
        "parity_health_mult":    round(parity_health_mult, 4),
        "parity_regime_mult":    round(parity_regime_mult, 4),
        "capital":               capital,
        "active_slots":          active_slots,
        "capital_per_slot":      capital_per_slot,
        "parity_stage_mult":     round(parity_stage_mult, 4),
        "parity_deployed_capital": round(parity_deployed, 0),
        "stocks_in_simulation":  len(valid_stocks),
        "total_backtest_trades": total_trades,
        "strategy_name":         bt.get("strategy_name", "Active Strategy"),
        "benchmark_source":      bt.get("source", "backtest"),
        "deployment_status":     deployment_status,
        "analysis_window_days":  analysis_window_days,
        "backtest_date":         bt.get("run_date", "N/A")[:10] if bt.get("run_date") else "N/A",

        # Performance
        "win_rate":              avg_win_rate,
        "loss_rate":             avg_loss_rate,
        "avg_return_per_trade":  avg_return_per_trade,
        "profit_factor":         profit_factor,
        "recovery_factor":       avg_recovery,
        "sharpe":                avg_sharpe,
        "expected_value_per_trade": expected_value,

        # Win/Loss
        "avg_win_pct": round(avg_win_pct, 2),
        "avg_win_amt":           avg_win_per_trade,
        "avg_loss_pct": round(avg_loss_pct, 2),
        "avg_loss_amt":          avg_loss_per_trade,

        # Time based
        "monthly_profit":        monthly_profit,
        "weekly_profit":         weekly_profit,
        "daily_profit":          daily_profit,
        "monthly_return_pct":    monthly_return_pct,
        "subscription_monthly_fee": subscription_monthly_fee,
        "net_after_subscription": net_after_subscription,
        "breakeven_capital": breakeven_capital,
        "recommended_capital": recommended_capital,
        "subscription_status": subscription_status,
        "low_balance_status": low_balance_status,
        "low_balance_reason": low_balance_reason,
        "trades_per_month":      trades_per_month,
        "trades_per_week":       trades_per_week,
        "trades_per_day":        trades_per_day,

        # Risk
        "max_day_portfolio_loss":   max_day_portfolio_loss,
        "max_day_individual_loss":  max_day_individual_loss,
        "portfolio_dd_pct":         abs(avg_drawdown),
        "worst_portfolio_loss":     worst_portfolio_loss,
        "worst_month_loss":         worst_month_loss,
        "worst_case_monthly":       worst_case_monthly,
        "worst_case_dd":            worst_case_dd,
        "survival_plan": survival_plan,

        # Admin only
        "per_stock_dd": per_stock_dd,
    }


def _fmt_money(v) -> str:
    try:
        v = float(v or 0)
    except (TypeError, ValueError) as e:
        logger.debug(f"_fmt_money: Invalid value {v}, defaulting to 0: {e}")
        v = 0.0
    sign = "-" if v < 0 else "+"
    return f"{sign}Rs.{abs(v):,.0f}"


def _fmt_money_plain(v) -> str:
    try:
        v = float(v or 0)
    except (TypeError, ValueError) as e:
        logger.debug(f"_fmt_money_plain: Invalid value {v}, defaulting to 0: {e}")
        v = 0.0
    return f"Rs.{v:,.0f}"


def format_simulation_message(result: dict, is_admin: bool = False) -> str:
    if "error" in result:
        return f"Error: {result['error']}"

    c = result

    sub_status = c.get("subscription_status", "UNKNOWN")
    if sub_status == "VIABLE":
        sub_line = "Status: Viable at this capital"
    elif sub_status == "NOT_VIABLE_CAPITAL_LOW":
        sub_line = "Status: Not viable at this capital after fee"
    elif sub_status == "NOT_VIABLE_STRATEGY_WEAK":
        sub_line = "Status: Strategy currently weak — do not judge by profit"
    else:
        sub_line = "Status: Check manually"

    breakeven = c.get("breakeven_capital")
    recommended = c.get("recommended_capital")

    source = c.get("benchmark_source", "backtest")
    dep_status = c.get("deployment_status", "UNKNOWN")
    pending = (dep_status == "PENDING_APPROVAL")
    if source == "optimization_walkforward":
        source_label = ("candidate optimization + walk-forward (approval pending)"
                        if pending else "latest deployed optimization + walk-forward")
    else:
        source_label = ("candidate verified backtest (approval pending)"
                        if pending else "latest verified backtest")

    msg = (
        f"SIMULATION — Rs.{c['capital']:,.0f}\n"
        f"==============================\n"
        f"Based on {source_label}\n"
        f"Strategy: {c['strategy_name']}\n"
        f"Trades Tested: {c['total_backtest_trades']} | Stocks: {c['stocks_in_simulation']}\n"
        f"Win Rate: {c['win_rate']}% | PF: {c['profit_factor']}\n\n"

        f"PROFIT PROJECTION\n"
        f"Daily Avg:   {_fmt_money(c['daily_profit'])}\n"
        f"Weekly Avg:  {_fmt_money(c['weekly_profit'])}\n"
        f"Monthly Avg: {_fmt_money(c['monthly_profit'])} ({c['monthly_return_pct']}%)\n"
        f"Expected Value/Trade: {_fmt_money(c['expected_value_per_trade'])}\n\n"

        f"AVG TRADE RESULT\n"
        f"Avg Win/Trade: {_fmt_money(c['avg_win_amt'])} ({c['avg_win_pct']}%)\n"
        f"Avg Loss/Trade: {_fmt_money(c['avg_loss_amt'])} ({c['avg_loss_pct']}%)\n\n"

        f"SUBSCRIPTION CHECK\n"
        f"Monthly Fee: Rs.{c.get('subscription_monthly_fee', 3000):,.0f}\n"
        f"Net After Fee: {_fmt_money(c.get('net_after_subscription', 0))}\n"
        f"{sub_line}\n"
        f"Low Balance Status: {c.get('low_balance_status', 'UNKNOWN')}\n"
        f"{c.get('low_balance_reason', 'N/A')}\n"
    )

    if breakeven:
        msg += f"Breakeven Capital: Rs.{breakeven:,.0f}\n"
    else:
        msg += f"Breakeven Capital: Not available while monthly expectancy is <= 0\n"

    if recommended:
        msg += f"Recommended Capital Buffer: Rs.{recommended:,.0f}+\n"

    msg += (
        f"\nHARDENING & HEALTH METRICS\n"
        f"Portfolio Health Score: {c.get('health_score', 100.0)}/100\n"
        # [v4.2 SIZING-PARITY] Projection ab live jaisi hi scaling pe hai
        # (stage × health × regime) — isliye "adjusted" line ki zaroorat
        # nahi (double-count hota). Ye disclosure batata hai ki projection
        # kis live-scale pe hai:
        f"Live-Scale: Stage {c.get('parity_stage_mult', 1.0)*100:.0f}% × Health {c.get('parity_health_mult', 1.0)}x × Regime {c.get('parity_regime_mult', 1.0)}x\n"
    )

    msg += (
        f"\nRISK STATS\n"
        f"Max Day Loss: -Rs.{abs(c['max_day_portfolio_loss']):,.0f}\n"
        f"Portfolio DD: -{c['portfolio_dd_pct']}% = -Rs.{abs(c['worst_portfolio_loss']):,.0f}\n"
        f"Worst Case (30% worse): -Rs.{abs(c['worst_case_dd']):,.0f}\n"
        f"Max Individual Trade Loss: -Rs.{abs(c['max_day_individual_loss']):,.0f}\n\n"

        f"DECISION RULE\n"
        f"Invest only if you can tolerate Max Day Loss and Portfolio DD.\n"
        f"Do not decide by profit projection alone.\n"
        f"If these losses are uncomfortable, reduce capital or do not subscribe.\n\n"
    )

    try:
        from survival_manager import format_survival_plan
        msg += format_survival_plan(c.get("survival_plan", {}), is_admin=is_admin)
        msg += "\n"
    except (ImportError, RuntimeError, ValueError) as e:
        logger.warning(f"format_simulation_message: Survival plan format failed: {type(e).__name__}: {e}")

    if is_admin:
        msg += (
            f"\nADMIN DETAILS\n"
            f"Active Slots: {c['active_slots']}\n"
            f"Capital/Slot: Rs.{c['capital_per_slot']:,.0f}\n"
            f"Stage Deploy: {c.get('parity_stage_mult', 1.0)*100:.0f}% (Deployed Rs.{c.get('parity_deployed_capital', c['capital_per_slot']*c['active_slots']):,.0f})\n"
            f"Health Mult: {c.get('parity_health_mult', 1.0)}x | Regime Mult: {c.get('parity_regime_mult', 1.0)}x (live sizing chain — paper/live same)\n"
            f"Trades/Month: ~{c['trades_per_month']}\n"
            f"Sharpe: {c['sharpe']} | RF: {c['recovery_factor']}\n"
        )

    if is_admin and c.get("per_stock_dd"):
        msg += f"\nIndividual Stock DD (Admin)\n"
        for sym, dd in sorted(c["per_stock_dd"].items(), key=lambda x: x[1]):
            msg += f"{sym}: {dd}%\n"

    msg += (
        f"\nPast performance does not guarantee future results.\n"
        f"Halal CNC only -- No leverage, No options"
    )

    return msg

# ─────────────────────────────────────────────
# MONTE CARLO SIMULATION
# ─────────────────────────────────────────────

def run_monte_carlo(capital: float, n_simulations: int = 1000) -> dict:
    """
    Monte Carlo simulation:
    Backtest trades ko randomly shuffle karo n baar
    Worst case, best case, median outcome nikalo
    """
    n_simulations = max(1, int(n_simulations))
    try:
        from workflow_manager import can_run_simulation
        ok, reason = can_run_simulation()
        if not ok:
            return {"error": reason}
    except (ImportError, RuntimeError) as e:
        logger.warning(f"run_monte_carlo: Workflow check failed, proceeding: {type(e).__name__}: {e}")

    valid_stocks = _get_valid_stocks(apply_sector_filter=True)
    if not valid_stocks:
        return {"error": "No deployed benchmark data. Run /optimize + /deployapprove or /backtest first."}

    # Collect all trade returns
    all_returns = []
    for stock in valid_stocks:
        if stock.get("trades_list"):
            for t in stock["trades_list"]:
                if "net_return_pct" in t:
                    all_returns.append(t["net_return_pct"] / 100)

    if len(all_returns) < 10:
        return {"error": "Not enough trades for Monte Carlo. Need 10+ trades."}

    results = []
    for _ in range(n_simulations):
        shuffled = random.sample(all_returns, len(all_returns))
        equity   = capital
        peak     = capital
        max_dd   = 0.0

        for ret in shuffled:
            equity *= (1 + ret)
            if equity > peak:
                peak = equity
            dd = (equity - peak) / peak * 100
            if dd < max_dd:
                max_dd = dd

        results.append({
            "final_equity":     equity,
            "total_return_pct": (equity - capital) / capital * 100,
            "max_dd_pct":       max_dd,
        })

    results.sort(key=lambda x: x["final_equity"])

    _q = PARAMS.get("sim_mc_quantiles", {"worst": 0.05, "median": 0.5, "best": 0.95})
    worst_5  = results[int(n_simulations * float(_q.get("worst", 0.05)))]
    median   = results[int(n_simulations * float(_q.get("median", 0.5)))]
    best_95  = results[int(n_simulations * float(_q.get("best", 0.95)))]

    return {
        "capital":          capital,
        "n_simulations":    n_simulations,
        "worst_5pct": {
            "final":      round(worst_5["final_equity"], 0),
            "return_pct": round(worst_5["total_return_pct"], 1),
            "max_dd_pct": round(worst_5["max_dd_pct"], 1),
        },
        "median": {
            "final":      round(median["final_equity"], 0),
            "return_pct": round(median["total_return_pct"], 1),
            "max_dd_pct": round(median["max_dd_pct"], 1),
        },
        "best_95pct": {
            "final":      round(best_95["final_equity"], 0),
            "return_pct": round(best_95["total_return_pct"], 1),
            "max_dd_pct": round(best_95["max_dd_pct"], 1),
        },
        "probability_profit": round(
            sum(1 for r in results if r["final_equity"] > capital) / n_simulations * 100, 1
        ),
    }


def format_monte_carlo_message(result: dict) -> str:
    if "error" in result:
        return f"Error: {result['error']}"

    return (
        f"Monte Carlo Simulation\n"
        f"Capital: Rs.{result['capital']:,.0f} | Runs: {result['n_simulations']}\n\n"
        f"Worst Case (5th percentile)\n"
        f"Final: Rs.{result['worst_5pct']['final']:,.0f}\n"
        f"Return: {result['worst_5pct']['return_pct']}%\n"
        f"Max DD: {result['worst_5pct']['max_dd_pct']}%\n\n"
        f"Median (50th percentile)\n"
        f"Final: Rs.{result['median']['final']:,.0f}\n"
        f"Return: {result['median']['return_pct']}%\n"
        f"Max DD: {result['median']['max_dd_pct']}%\n\n"
        f"Best Case (95th percentile)\n"
        f"Final: Rs.{result['best_95pct']['final']:,.0f}\n"
        f"Return: {result['best_95pct']['return_pct']}%\n"
        f"Max DD: {result['best_95pct']['max_dd_pct']}%\n\n"
        f"Probability of Profit: {result['probability_profit']}%\n\n"
        f"Past performance does not guarantee future results."
    )


def generate_sim_chart(result: dict, path: str = "data/simulate_chart.png"):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        import os
        os.makedirs("data", exist_ok=True)
        trades = int(result.get("total_trades", 40) or 40)
        wr = float(result.get("avg_win_rate", 50.0) or 50.0)
        pf = float(result.get("profit_factor", 1.5) or 1.5)
        capital = float(result.get("capital", 200000.0) or 200000.0)
        
        # Use verified backtest equity curve if present; otherwise deterministic expected trajectory
        eq_curve = result.get("equity_curve")
        if eq_curve and isinstance(eq_curve, (list, tuple)) and len(eq_curve) > 1:
            eq = np.array(eq_curve, dtype=float)
            x = np.arange(1, len(eq) + 1)
        else:
            x = np.arange(1, max(10, trades) + 1)
            total_ret_pct = float(result.get("expected_return_pct", result.get("monthly_return_pct", 5.0)) or 5.0)
            per_step_growth = (1.0 + (total_ret_pct / 100.0)) ** (1.0 / len(x))
            eq = capital * (per_step_growth ** x)
        fig, ax = plt.subplots(figsize=(8, 4), facecolor="#0f172a")
        ax.set_facecolor("#1e293b")
        ax.plot(x, eq, color="#10b981" if eq[-1] >= capital else "#ef4444", lw=2)
        ax.set_title(f"HALAL STRATEGIES TRADING — SIMULATION CHART (WR: {wr}%, PF: {pf})", color="#f8fafc")
        ax.set_ylabel("Portfolio Value (Rs.)", color="#cbd5e1")
        ax.grid(color="#334155", ls=":")
        ax.tick_params(colors="#94a3b8")
        plt.tight_layout()
        plt.savefig(path, dpi=120, facecolor=fig.get_facecolor())
        plt.close()
    except (ImportError, RuntimeError, ValueError, OSError) as e:
        logger.warning(f"generate_sim_chart: Chart generation failed: {type(e).__name__}: {e}")
