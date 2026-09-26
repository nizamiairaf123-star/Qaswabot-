"""
risk_override_manager.py — FIX-03 Capital Survival Override

Purpose:
- Health weak ho to capital reduce already hota hai.
- Health/circuit dangerous ho to new entries block.
- Circuit hit => EXIT_ONLY state: existing positions monitored/protected.
- Business pause, not shutdown.
"""

import logging

logger = logging.getLogger(__name__)

from utils import load_json, save_json, now_ist, append_log
from config import AUDIT_LOG_FILE

STATE_FILE = "data/capital_survival_override.json"


def _load() -> dict:
    return load_json(STATE_FILE, {
        "last_status": "OK",
        "last_alert": None,
        "updated": None,
    })


def _save(data: dict):
    save_json(STATE_FILE, data)


def _safe_alert(msg: str):
    try:
        from signal_broadcaster import alert_admin
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(alert_admin(msg))
        except RuntimeError:
            # No running event loop — deliver via sync wrapper
            from signal_broadcaster import alert_admin_sync
            alert_admin_sync(msg)
    except (ImportError, RuntimeError) as e:
        logger.warning(f"_alert_admin: Alert failed: {type(e).__name__}: {e}")


def get_capital_survival_override_status() -> dict:
    """
    Returns:
    {
      status: OK / HARD_BRAKE / CIRCUIT,
      allow_new_entries: bool,
      reason: str,
      health_score: float,
      mode: str
    }
    """
    try:
        from portfolio_health import calculate_health_score, get_portfolio_mode, get_health_multiplier

        health = float(calculate_health_score())
        mode = get_portfolio_mode()
        mult = float(get_health_multiplier())

        # Decision 06 owner: consume survival-plan + stage-readiness outputs, not static health thresholds.
        try:
            from capital_manager import get_deployable_balance, get_stage_readiness_decision
            from survival_manager import calculate_survival_plan
            capital = get_deployable_balance()
            stage_ready = get_stage_readiness_decision(capital=capital)
            if capital <= 0:
                return {
                    "status": "ERROR",
                    "allow_new_entries": False,
                    "reason": "Capital survival check: no deployable balance available",
                    "health_score": health,
                    "mode": mode,
                    "multiplier": mult,
                }
            from capital_drawdown_manager import get_verified_financial_economics
            econ_ctx = get_verified_financial_economics(symbol=None)
            expected_monthly_return_pct = max(
                0.0,
                econ_ctx.get("avg_net_return_per_trade_pct", 0.0) * econ_ctx.get("expected_trades_per_month", 0.0)
            )
            plan = calculate_survival_plan(
                capital=capital,
                expected_monthly_return_pct=expected_monthly_return_pct,
                monthly_survival_target=econ_ctx.get("monthly_benchmark"),
                bot_health_pct=health,
            )
            if plan.get("error") or "circuit_pct" not in plan or "hard_pct" not in plan:
                return {
                    "status": "ERROR",
                    "allow_new_entries": False,
                    "reason": f"Capital survival check: verified survival plan unavailable ({plan.get('error', 'incomplete result')})",
                    "health_score": health,
                    "mode": mode,
                    "multiplier": mult,
                }
            circuit_dd_limit = float(plan["circuit_pct"])
            hard_dd_limit = float(plan["hard_pct"])
            from safety_manager import _load as load_safety
            sdata = load_safety()
            daily_risk_pct = float(sdata.get("daily_risk_used_pct", 0.0))
            if daily_risk_pct >= circuit_dd_limit or mode == "FAILED" or not stage_ready.get("allow", True):
                return {
                    "status": "CIRCUIT",
                    "allow_new_entries": False,
                    "reason": f"Capital survival CIRCUIT: daily risk={daily_risk_pct:.1f}% | stage_ready={stage_ready.get('allow')} | {stage_ready.get('reason')}",
                    "health_score": health,
                    "mode": mode,
                    "multiplier": mult,
                }
            if daily_risk_pct >= hard_dd_limit or mode == "WARNING":
                return {
                    "status": "HARD_BRAKE",
                    "allow_new_entries": False,
                    "reason": f"Capital survival HARD BRAKE: daily risk={daily_risk_pct:.1f}% >= limit={hard_dd_limit:.1f}%",
                    "health_score": health,
                    "mode": mode,
                    "multiplier": mult,
                }
        except Exception as e:
            append_log(AUDIT_LOG_FILE, f"SURVIVAL PLAN INTEGRATION ERROR: {e}")
            return {
                "status": "ERROR",
                "allow_new_entries": False,
                "reason": f"Capital survival check error during integration: {e}",
                "health_score": health,
                "mode": mode,
                "multiplier": mult,
            }

        return {
            "status": "OK",
            "allow_new_entries": True,
            "reason": f"Capital survival OK: health={health}/100, multiplier={mult}x",
            "health_score": health,
            "mode": mode,
            "multiplier": mult,
        }

    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"CAPITAL SURVIVAL OVERRIDE ERROR: {e}")
        return {
            "status": "ERROR",
            "allow_new_entries": False,
            "reason": f"Capital survival check error: {e}",
            "health_score": 100.0,
            "mode": "UNKNOWN",
            "multiplier": 1.0,
        }


def check_capital_survival_override(apply_state: bool = True) -> tuple:
    """
    Entry gate helper.
    Returns: (allowed, reason)

    If CIRCUIT and apply_state=True:
    - switches bot to EXIT_ONLY if not already there.
    """
    status = get_capital_survival_override_status()
    data = _load()

    current_status = status["status"]
    previous_status = data.get("last_status", "OK")

    data["last_status"] = current_status
    data["updated"] = now_ist().isoformat()
    _save(data)

    if current_status == "CIRCUIT":
        if apply_state:
            try:
                from bot_state_manager import get_state, activate_exit_only

                state = get_state()
                if state not in ("EXIT_ONLY", "KILLSWITCH_STOP", "TOKEN_INVALID_PAUSE"):
                    activate_exit_only(status["reason"])
                    append_log(AUDIT_LOG_FILE, f"CAPITAL SURVIVAL CIRCUIT -> EXIT_ONLY: {status['reason']}")

            except Exception as e:
                append_log(AUDIT_LOG_FILE, f"CAPITAL SURVIVAL CIRCUIT STATE ERROR: {e}")

        if previous_status != "CIRCUIT":
            _safe_alert(
                "CAPITAL SURVIVAL CIRCUIT\n\n"
                f"{status['reason']}\n\n"
                "No new trades. Existing trades stay protected.\n"
                "Bot is in recovery watch, not shutdown."
            )

        return False, status["reason"]

    if current_status == "HARD_BRAKE":
        if previous_status != "HARD_BRAKE":
            append_log(AUDIT_LOG_FILE, f"CAPITAL SURVIVAL HARD BRAKE: {status['reason']}")
            _safe_alert(
                "CAPITAL SURVIVAL HARD BRAKE\n\n"
                f"{status['reason']}\n\n"
                "No new entries until health improves or admin reviews."
            )

        return False, status["reason"]

    if current_status == "ERROR" or not status.get("allow_new_entries", True):
        if previous_status != "ERROR":
            append_log(AUDIT_LOG_FILE, f"CAPITAL SURVIVAL ERROR (fail-closed, blocking new entries): {status['reason']}")
        return False, status["reason"]

    return True, status["reason"]
