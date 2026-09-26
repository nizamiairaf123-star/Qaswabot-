"""
strategy_validator.py — FIX-07 Auto Strategy Health Signal

Validator does NOT create strategy.
Optimizer creates/selects strategy.
Validator checks if currently deployed strategy is healthy.

Status:
    GREEN  = healthy, continue
    YELLOW = mild degradation, monitor/reduce
    RED    = strategy weak, optimize required
    BLACK  = capital survival danger / exit-only logic should remain

Uses:
- latest backtest summary
- live closed trades if available
- portfolio health
- profit degradation
- idle trading days
"""

import logging
from datetime import date
from utils import load_json, save_json, now_ist, append_log, trading_days_between, today_ist
from config import TRADES_FILE, BACKTEST_RESULTS_FILE, AUDIT_LOG_FILE, PARAMS

logger = logging.getLogger(__name__)

VALIDATOR_STATE_FILE = "data/validator_state.json"
OPTIMIZER_REQUEST_FILE = "data/optimizer_request.json"


def _display_min_wr():
    """Display-only min WR: R:R-derived floor from economics_brain, else static fallback.
    Any failure → PARAMS static value (production display unchanged)."""
    try:
        from economics_brain import min_win_rate_floor
        v = min_win_rate_floor()
        return round(float(v), 2)
    except Exception:
        return PARAMS.get("min_live_win_rate", 40)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_state() -> dict:
    return load_json(VALIDATOR_STATE_FILE, {
        "status": "INSUFFICIENT_DATA",
        "last_checked": None,
        "consecutive_losses": 0,
        "trades_since_optimize": 0,
        "peak_profit": 0.0,
        "last_trade_date": None,
        "idle_trading_days": 0,
        "last_strategy_stats": None,
        "last_alert_status": None,
    })


def _save_state(data: dict):
    save_json(VALIDATOR_STATE_FILE, data)


def _safe_admin_alert(msg: str):
    try:
        from signal_broadcaster import alert_admin
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(alert_admin(msg))
        except RuntimeError:
            # No running event loop (sync context) — deliver via sync wrapper
            from signal_broadcaster import alert_admin_sync
            alert_admin_sync(msg)
    except (ImportError, RuntimeError) as e:
        logger.warning(f"_safe_admin_alert: Failed: {type(e).__name__}: {e}")


def _get_backtest_summary() -> dict:
    bt = load_json(BACKTEST_RESULTS_FILE, {})
    source = bt.get("source", "backtest") if isinstance(bt, dict) else "backtest"
    summary = bt.get("summary", {})
    if isinstance(summary, dict) and summary:
        summary = summary.copy()
        summary["source"] = source
        return summary

    valid = [s for s in bt.get("stocks", {}).values() if s.get("valid")]
    if not valid:
        return {}

    total_trades = sum(int(s.get("total_trades", 0)) for s in valid)
    wins = sum(int(s.get("winning_trades", 0)) for s in valid)
    losses = sum(int(s.get("losing_trades", 0)) for s in valid)

    profit_sum = sum(max(0, _safe_float(s.get("avg_win_pct"))) * int(s.get("winning_trades", 0)) for s in valid)
    loss_sum = sum(min(0, _safe_float(s.get("avg_loss_pct"))) * int(s.get("losing_trades", 0)) for s in valid)

    return {
        "total_trades": total_trades,
        "win_rate_pct": round(wins / total_trades * 100, 2) if total_trades else 0,
        "profit_factor": round(profit_sum / abs(loss_sum), 2) if loss_sum < 0 else (99.0 if profit_sum > 0 else 0),
        "recovery_factor": round(sum(_safe_float(s.get("recovery_factor")) for s in valid) / len(valid), 2),
        "total_return_pct": round(sum(_safe_float(s.get("total_return_pct")) for s in valid) / len(valid), 2),
        "portfolio_max_dd_pct": round(sum(abs(_safe_float(s.get("portfolio_max_drawdown_pct"))) for s in valid) / len(valid), 2),
        "max_idle_days": max(int(s.get("max_idle_days", 0) or 0) for s in valid),
        "max_consecutive_losses": max(int(s.get("max_consecutive_losses", 0) or 0) for s in valid),
    }


def _get_closed_trades() -> list:
    data = load_json(TRADES_FILE, {"trades": []})
    return [t for t in data.get("trades", []) if t.get("status") == "CLOSED"]


def get_idle_trading_days() -> int:
    closed = _get_closed_trades()
    if not closed:
        return 0

    exit_time = closed[-1].get("exit_time", "")
    if not exit_time:
        return 0

    try:
        last_date = date.fromisoformat(exit_time[:10])
        return trading_days_between(last_date, today_ist())
    except (ValueError, TypeError, IndexError) as e:
        logger.warning(f"get_idle_trading_days: Date parse failed: {type(e).__name__}: {e}")
        return 0


def check_profit_degradation(state: dict, current_total_pnl: float) -> dict:
    peak = _safe_float(state.get("peak_profit", 0.0))

    if current_total_pnl > peak:
        state["peak_profit"] = current_total_pnl
        peak = current_total_pnl

    threshold = _safe_float(PARAMS.get("profit_degradation_alert_pct", 20.0), 20.0)

    if peak <= 0:
        return {"degraded": False, "drop_pct": 0, "state": state}

    drop_pct = ((peak - current_total_pnl) / peak) * 100

    if drop_pct >= threshold:
        return {
            "degraded": True,
            "peak": peak,
            "current": current_total_pnl,
            "drop_pct": round(drop_pct, 1),
            "threshold": threshold,
            "state": state,
        }

    return {"degraded": False, "drop_pct": round(drop_pct, 1), "state": state}


def _live_metrics(closed: list) -> dict:
    min_live = int(PARAMS.get("health_min_live_trades", 5))

    if not closed:
        return {
            "has_live_sample": False,
            "live_win_rate": None,
            "live_profit_factor": None,
            "live_pnl": 0.0,
            "consecutive_losses": 0,
            "live_trades": 0,
            "recent_trades": 0,
            "min_live_trades": min_live,
        }

    recent_n = int(PARAMS.get("health_recent_trades", 20))
    recent = closed[-recent_n:]

    live_pnl = sum(_safe_float(t.get("pnl", 0)) for t in closed)

    wins = [t for t in recent if _safe_float(t.get("pnl", 0)) > 0]
    losses = [t for t in recent if _safe_float(t.get("pnl", 0)) <= 0]

    gross_profit = sum(_safe_float(t.get("pnl", 0)) for t in wins)
    gross_loss = sum(_safe_float(t.get("pnl", 0)) for t in losses)
    pf = gross_profit / abs(gross_loss) if gross_loss < 0 else 0.0

    consec_losses = 0
    for t in reversed(closed):
        if _safe_float(t.get("pnl", 0)) <= 0:
            consec_losses += 1
        else:
            break

    return {
        "has_live_sample": len(recent) >= min_live,
        "live_win_rate": round(len(wins) / len(recent) * 100, 2) if recent else None,
        "live_profit_factor": round(pf, 2),
        "live_pnl": round(live_pnl, 2),
        "consecutive_losses": consec_losses,
        "live_trades": len(closed),
        "recent_trades": len(recent),
        "min_live_trades": min_live,
    }


def _benchmark_quality(summary: dict) -> tuple:
    """
    Benchmark must be at least breakeven after costs.
    Worst/minimum = net breakeven or better.
    """
    issues = []

    wr = _safe_float(summary.get("win_rate_pct"))
    pf = _safe_float(summary.get("profit_factor"))
    rf = _safe_float(summary.get("recovery_factor"))
    ret = _safe_float(summary.get("total_return_pct"))
    dd = abs(_safe_float(summary.get("portfolio_max_dd_pct")))

    try:
        from economics_brain import min_win_rate_floor
        min_wr = _safe_float(min_win_rate_floor(), 40)
    except Exception:
        min_wr = _safe_float(PARAMS.get("min_live_win_rate", 40), 40)
    min_pf = _safe_float(PARAMS.get("min_profit_factor", 1.0), 1.0)
    min_rf = _safe_float(PARAMS.get("min_recovery_factor", 1.0), 1.0)
    try:
        from broker import get_available_balance
        from capital_drawdown_manager import get_validator_max_drawdown_pct
        max_dd_result = get_validator_max_drawdown_pct(capital=float(get_available_balance() or 200000.0))
        if isinstance(max_dd_result, dict):
            # Owner engine explicitly signaled it has no verified value
            # (see capital_drawdown_manager.get_validator_max_drawdown_pct's
            # error-dict return branches) -- do not substitute any number.
            max_dd = None
        else:
            max_dd = float(max_dd_result)
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"_benchmark_quality: Max DD check failed: {type(e).__name__}: {e}")
        max_dd = None
    # Constitution Art. 2.4a: 2% daily_loss_limit_pct is the ONLY admin-
    # approved fixed value in this system. There is no admin-approved
    # fallback max-drawdown percentage. If the verified owner engine
    # cannot produce one, that is itself a validation failure, not a
    # number to be invented.

    if wr < min_wr:
        issues.append(f"Backtest WR {wr}% < min {min_wr}%")
    if pf < min_pf:
        issues.append(f"Backtest PF {pf} < breakeven {min_pf}")
    if rf < min_rf:
        issues.append(f"Backtest RF {rf} < min {min_rf}")
    if ret <= 0:
        issues.append(f"Backtest return {ret}% <= 0")
    if max_dd is None:
        issues.append("Could not verify max-drawdown benchmark from owner engine (capital_drawdown_manager/survival_manager) -- deployment blocked pending verified data")
    elif dd > max_dd:
        issues.append(f"Backtest DD {dd}% > max {max_dd}%")

    score = 100.0
    if wr < min_wr:
        score -= min(30, (min_wr - wr) * 1.0)
    if pf < min_pf:
        score -= min(float(PARAMS.get("validator_pf_penalty_cap", 35.0)),
                    (min_pf - pf) * float(PARAMS.get("validator_pf_penalty_mult", 60.0)))
    if rf < min_rf:
        score -= min(float(PARAMS.get("validator_rf_penalty_cap", 20.0)),
                    (min_rf - rf) * float(PARAMS.get("validator_rf_penalty_mult", 20.0)))
    if ret <= 0:
        score -= 25
    if max_dd is None:
        score = 0  # fail-closed: cannot score DD quality without a verified benchmark
    elif dd > max_dd:
        score -= min(30, (dd - max_dd) * 2)

    score = max(0, min(100, score))
    return round(score, 2), issues


def _request_reoptimization(result: dict):
    """
    Save optimizer request. Heavy optimizer run remains admin controlled unless enabled later.
    """
    save_json(OPTIMIZER_REQUEST_FILE, {
        "requested": True,
        "requested_at": now_ist().isoformat(),
        "reason": result.get("reason"),
        "status": result.get("status"),
        "old_stats": {
            "win_rate": result.get("live_win_rate"),
            "profit_factor": result.get("profit_factor"),
            "total_pnl": result.get("total_pnl"),
            "backtest_wr": result.get("backtest_win_rate"),
            "backtest_pf": result.get("backtest_profit_factor"),
            "benchmark_quality": result.get("benchmark_quality_score"),
        },
        "next_action": "Run /optimize, compare OLD vs NEW, then /deployapprove or /deployreject.",
    })


def validate_strategy(alert: bool = False) -> dict:
    closed = _get_closed_trades()
    bt = _get_backtest_summary()
    state = _load_state()

    if not bt:
        result = {
            "status": "BLACK",
            "reason": "No valid benchmark summary found. Run /optimize + /deployapprove or /backtest first.",
            "checked_at": now_ist().isoformat(),
        }
        state["status"] = result["status"]
        state["last_checked"] = result["checked_at"]
        _save_state(state)
        return result

    live = _live_metrics(closed)
    try:
        from alignment_engine import run_alignment_report
        alignment = run_alignment_report()
    except Exception as e:
        logger.warning(f"validate_strategy: alignment report failed: {type(e).__name__}: {e}")
        alignment = {"status": "UNAVAILABLE", "error": type(e).__name__}
    idle_days = get_idle_trading_days()
    degradation = check_profit_degradation(state, live["live_pnl"])
    state = degradation["state"]

    try:
        from portfolio_health import calculate_health_score, get_health_multiplier
        health_score = float(calculate_health_score())
        health_mult = float(get_health_multiplier())
    except (ImportError, RuntimeError, ValueError) as e:
        # AUDIT FIX (Bug #4, fail-open): used to default to 100.0/1.0
        # ("perfect health") on a calculation failure -- a value that can
        # never trip the BLACK circuit-breaker below, defeating the health
        # check exactly when its input couldn't be verified. Fail closed
        # instead (0.0), matching survival_manager.get_bot_health_pct()'s
        # own already-fixed conservative default.
        logger.warning(f"validate_strategy: Health score failed: {type(e).__name__}: {e}")
        health_score = 0.0
        health_mult = 0.0

    bq_score, benchmark_issues = _benchmark_quality(bt)

    issues = []
    warnings = []

    # Backtest result itself weak = strategy should not be considered healthy.
    issues.extend(benchmark_issues)

    # Live comparison only after enough live trades.
    if live["has_live_sample"]:
        bt_wr = _safe_float(bt.get("win_rate_pct"))
        live_wr = _safe_float(live.get("live_win_rate"))
        wr_gap = round(bt_wr - live_wr, 2)
        max_gap = _safe_float(PARAMS.get("max_wr_gap_vs_backtest", 15), 15)

        try:
            from economics_brain import min_win_rate_floor
            min_live_wr = _safe_float(min_win_rate_floor(), 40)
        except Exception:
            min_live_wr = _safe_float(PARAMS.get("min_live_win_rate", 40), 40)
        min_pf = _safe_float(PARAMS.get("min_profit_factor", 1.0), 1.0)

        if live_wr < min_live_wr:
            issues.append(f"Live WR {live_wr}% < min {min_live_wr}%")
        if wr_gap > max_gap:
            issues.append(f"Live WR gap vs benchmark {wr_gap}% > max {max_gap}%")
        if _safe_float(live.get("live_profit_factor")) < min_pf:
            issues.append(f"Live PF {live.get('live_profit_factor')} < min {min_pf}")
    else:
        warnings.append(
            f"No live sample yet ({live['live_trades']} closed trades, need {live['min_live_trades']}). Using backtest/minimum-quality health."
        )
        wr_gap = 0

    max_consec_loss = int(PARAMS.get("max_consecutive_losses_validator", 5))
    if live["consecutive_losses"] >= max_consec_loss and live["live_trades"] > 0:
        issues.append(f"{live['consecutive_losses']} consecutive losses")

    max_idle_days = int(PARAMS.get("max_idle_trading_days", 10))
    if idle_days > max_idle_days:
        issues.append(f"Strategy idle {idle_days} trading days > max {max_idle_days}")

    if degradation.get("degraded"):
        issues.append(
            f"Profit degraded {degradation['drop_pct']}% from peak "
            f"(Rs.{degradation['peak']:,.0f} -> Rs.{degradation['current']:,.0f})"
        )

    # Status rules (Decision 12 consumes stage-readiness + economics owner outputs)
    try:
        from broker import get_available_balance
        from capital_manager import get_stage_readiness_decision
        stage_ready = get_stage_readiness_decision(capital=float(get_available_balance() or 200000.0))
        circuit_health_min = _safe_float(stage_ready.get("dynamic_health_floor_pct", 30), 30)
    except (ImportError, RuntimeError, ValueError) as e:
        logger.warning(f"validate_strategy: Stage readiness failed: {type(e).__name__}: {e}")
        stage_ready = {"allow": False, "reason": f"stage readiness check failed: {e}"}
        circuit_health_min = PARAMS.get("strategy_circuit_health_min", 30)

    # Validation thresholds (optimizer-configurable)
    validation_thresholds = PARAMS.get("strategy_validation_thresholds", {
        "black_bq_score": 30,
        "red_bq_score": 50,
        "yellow_bq_score": 70,
        "red_issues_count": 2,
    })

    if health_score < circuit_health_min or bq_score < validation_thresholds["black_bq_score"] or not stage_ready.get("allow", True):
        status = "BLACK"
    elif len(issues) >= validation_thresholds["red_issues_count"] or bq_score < validation_thresholds["red_bq_score"]:
        status = "RED"
    elif len(issues) == 1 or warnings or bq_score < validation_thresholds["yellow_bq_score"]:
        status = "YELLOW"
    else:
        status = "GREEN"

    reason_parts = issues + warnings
    reason = " | ".join(reason_parts) if reason_parts else "Strategy healthy"

    result = {
        "status": status,
        "reason": reason,
        "benchmark_quality_score": bq_score,
        "health_score": round(health_score, 2),
        "health_multiplier": round(health_mult, 2),

        "backtest_win_rate": round(_safe_float(bt.get("win_rate_pct")), 2),
        "backtest_profit_factor": round(_safe_float(bt.get("profit_factor")), 2),
        "backtest_recovery_factor": round(_safe_float(bt.get("recovery_factor")), 2),
        "backtest_return_pct": round(_safe_float(bt.get("total_return_pct")), 2),
        "backtest_dd_pct": round(abs(_safe_float(bt.get("portfolio_max_dd_pct"))), 2),
        "benchmark_source": bt.get("source", "backtest"),

        "has_live_sample": live["has_live_sample"],
        "live_win_rate": live.get("live_win_rate"),
        "live_profit_factor": live.get("live_profit_factor"),
        "live_trades": live["live_trades"],
        "recent_trades": live.get("recent_trades", 0),
        "total_pnl": live["live_pnl"],
        "consecutive_losses": live["consecutive_losses"],
        "alignment": alignment,

        "idle_trading_days": idle_days,
        "peak_profit": round(state.get("peak_profit", 0), 2),
        "profit_drop_pct": degradation.get("drop_pct", 0),
        "checked_at": now_ist().isoformat(),
    }

    state["status"] = status
    state["last_checked"] = result["checked_at"]
    state["consecutive_losses"] = live["consecutive_losses"]
    state["idle_trading_days"] = idle_days
    state["last_trade_date"] = closed[-1].get("exit_time", "")[:10] if closed else None

    if status in ("RED", "BLACK"):
        state["last_strategy_stats"] = result
        _request_reoptimization(result)

    _save_state(state)

    append_log(
        AUDIT_LOG_FILE,
        f"STRATEGY VALIDATOR: {status} health={health_score} bq={bq_score} | {reason}"
    )

    if alert and status in ("RED", "BLACK") and state.get("last_alert_status") != status:
        _safe_admin_alert(
            f"STRATEGY HEALTH — {status}\n\n"
            f"Reason: {reason}\n\n"
            f"Backtest WR: {result.get('backtest_win_rate', result.get('benchmark_win_rate', 'N/A'))}% | PF: {result.get('backtest_profit_factor', result.get('benchmark_profit_factor', 'N/A'))}\n"
            f"Health: {result['health_score']}/100 | Multiplier: {result['health_multiplier']}x\n\n"
            f"Next: run /optimize, compare OLD vs NEW, then /deployapprove or /deployreject."
        )
        state["last_alert_status"] = status
        _save_state(state)

    return result


def get_validation_report() -> str:
    result = validate_strategy(alert=True)
    status = result.get("status", "UNKNOWN")

    if status == "GREEN":
        label = "GREEN - Strategy healthy"
        action = "Action: continue normal trading within current health/regime limits."
    elif status == "YELLOW":
        label = "YELLOW - Monitor / reduced confidence"
        action = "Action: monitor closely; health/regime multipliers reduce size automatically."
    elif status == "RED":
        label = "RED - Re-optimization required"
        action = "Action: run /optimize, compare OLD vs NEW, admin approve before resume."
    elif status == "BLACK":
        label = "BLACK - Circuit / exit-only protection"
        action = "Action: no new entries. Optimize + approve + resume only after health improves."
    else:
        label = status
        action = "Action: review manually."

    source = result.get("benchmark_source", "backtest")
    benchmark_label = "Optimization/WFV" if source == "optimization_walkforward" else "Backtest"

    return (
        f"Strategy Health Validator\n"
        f"Status: {label}\n"
        f"Benchmark Source: {benchmark_label}\n"
        f"Reason: {result.get('reason', 'N/A')}\n\n"

        f"Strategy Quality vs Minimum: {result.get('benchmark_quality_score', 'N/A')}/100\n"
        f"Bot Health: {result.get('health_score', 'N/A')}/100\n"
        f"Capital Multiplier: {result.get('health_multiplier', 'N/A')}x\n\n"

        f"{benchmark_label} WR: {result.get('backtest_win_rate', 'N/A')}%\n"
        f"{benchmark_label} PF: {result.get('backtest_profit_factor', 'N/A')}\n"
        f"{benchmark_label} RF: {result.get('backtest_recovery_factor', 'N/A')}\n"
        f"{benchmark_label} Return: {result.get('backtest_return_pct', 'N/A')}%\n"
        f"{benchmark_label} DD: {result.get('backtest_dd_pct', 'N/A')}%\n"
        f"Minimum Required: WR {_display_min_wr()}% | PF {PARAMS.get('min_profit_factor', 1.0)} | RF {PARAMS.get('min_recovery_factor', 1.0)}\n\n"

        f"Live Sample: {'Yes' if result.get('has_live_sample') else 'No'}\n"
        f"Live Trades: {result.get('live_trades', 0)}\n"
        f"Live WR: {result.get('live_win_rate', 'N/A')}\n"
        f"Live PF: {result.get('live_profit_factor', 'N/A')}\n"
        f"Live P&L: Rs.{result.get('total_pnl', 0):,.0f}\n"
        f"Consecutive Losses: {result.get('consecutive_losses', 0)}\n"
        f"Idle Trading Days: {result.get('idle_trading_days', 0)}\n"
        f"Profit Drop from Peak: {result.get('profit_drop_pct', 0)}%\n\n"

        f"{action}\n"
        f"Checked: {str(result.get('checked_at', ''))[:16]}"
    )


def is_strategy_valid() -> bool:
    result = validate_strategy(alert=False)
    return result.get("status") in ("GREEN", "YELLOW")
