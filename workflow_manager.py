"""
workflow_manager.py — Runtime system execution flow gatekeeper

This module turns the documented execution order into actual runtime checks.

Mandatory flow (v4.1 — owner decision 2026-08-17):
    Data Collection -> Feature Calculation -> Optimization -> Validation
    -> Decision Engine -> SIMULATION (admin result dekhe, satisfied ho)
    -> DEPLOYMENT APPROVAL (simulation se satisfied hone ke baad hi approve)
    -> Paper Trading -> Live Trading -> Performance Feedback

Owner's explicit reasoning: "Simulation karne se hi result pata chalega. Jab
result se satisfied milega tab approval dena sahi decision hoga. Pehle
approval fir simulation me result sahi nahi hue to galat decision hoga."
Isliye simulation ab deployment approval se PEHLE hai — admin pehle
/simulate result dekhta hai, satisfied ho kar /deployapprove karta hai.

It does NOT replace existing engines. It coordinates readiness between them.

[Method: CRISP-DM (Chapman et al., 2000 — data mining lifecycle) + Google ML
Readiness/Test Score (Breck et al., 2017, "The ML Test Score"). The 10-stage
mandatory flow above (data → features → train/optimize → validate → decide →
simulate → approve → paper → live → feedback) matches a standards-grade
production ML pipeline: gated stages, out-of-sample validation before release,
shadow/simulation before the release decision, staged rollout, and
post-release monitoring fed back into the loop.]
"""

from utils import load_json, save_json, now_ist, append_log
from config import AUDIT_LOG_FILE

WORKFLOW_STATE_FILE = "data/workflow_state.json"

STAGE_ORDER = [
    "data_collection",
    "feature_calculation",
    "optimization",
    "validation",
    "decision_engine",
    "simulation",
    "deployment_approval",
    "paper_trading",
    "live_trading",
    "performance_feedback",
]


def _blank_state() -> dict:
    return {
        "version": 1,
        "updated_at": None,
        "current_cycle_started_at": None,
        "stages": {
            stage: {
                "completed_at": None,
                "details": {},
            } for stage in STAGE_ORDER
        }
    }


def _load_state() -> dict:
    data = load_json(WORKFLOW_STATE_FILE, {})
    state = _blank_state()
    if isinstance(data, dict):
        state.update({k: v for k, v in data.items() if k != "stages"})
        if isinstance(data.get("stages"), dict):
            for stage in STAGE_ORDER:
                if isinstance(data["stages"].get(stage), dict):
                    state["stages"][stage].update(data["stages"][stage])
    return state


def _save_state(state: dict):
    state["updated_at"] = now_ist().isoformat()
    save_json(WORKFLOW_STATE_FILE, state)


def _reset_from(state: dict, stage_name: str):
    if stage_name not in STAGE_ORDER:
        return
    idx = STAGE_ORDER.index(stage_name)
    for stage in STAGE_ORDER[idx:]:
        state["stages"][stage] = {"completed_at": None, "details": {}}


def _mark_stage(stage_name: str, **details):
    state = _load_state()
    if not state.get("current_cycle_started_at"):
        state["current_cycle_started_at"] = now_ist().isoformat()
    state["stages"][stage_name] = {
        "completed_at": now_ist().isoformat(),
        "details": details,
    }
    _save_state(state)
    append_log(AUDIT_LOG_FILE, f"WORKFLOW STAGE COMPLETE: {stage_name} | {details}")


def start_optimization_cycle(total_symbols: int = 0, trigger: str = "optimizer"):
    state = _load_state()
    state["current_cycle_started_at"] = now_ist().isoformat()
    _reset_from(state, "optimization")
    # upstream stages are required for the cycle; mark them as part of the data/feature prep path
    if not state["stages"]["data_collection"]["completed_at"]:
        state["stages"]["data_collection"] = {
            "completed_at": now_ist().isoformat(),
            "details": {"trigger": trigger, "total_symbols": total_symbols},
        }
    if not state["stages"]["feature_calculation"]["completed_at"]:
        state["stages"]["feature_calculation"] = {
            "completed_at": now_ist().isoformat(),
            "details": {"trigger": trigger, "total_symbols": total_symbols},
        }
    _save_state(state)
    append_log(AUDIT_LOG_FILE, f"WORKFLOW CYCLE RESET FROM OPTIMIZATION: trigger={trigger} total={total_symbols}")


def record_data_collection(source: str = "unknown", **details):
    _mark_stage("data_collection", source=source, **details)


def record_feature_calculation(source: str = "unknown", **details):
    _mark_stage("feature_calculation", source=source, **details)


def record_optimization_completed(**details):
    _mark_stage("optimization", **details)


def record_validation_completed(**details):
    _mark_stage("validation", **details)


def record_decision_engine_ready(**details):
    _mark_stage("decision_engine", **details)


def record_deployment_approved(**details):
    state = _load_state()
    _reset_from(state, "deployment_approval")
    state["stages"]["deployment_approval"] = {
        "completed_at": now_ist().isoformat(),
        "details": details,
    }
    _save_state(state)
    append_log(AUDIT_LOG_FILE, f"WORKFLOW DEPLOYMENT APPROVED: {details}")


def record_simulation_completed(**details):
    _mark_stage("simulation", **details)


def record_paper_trading_started(**details):
    state = _load_state()
    if not state["stages"]["paper_trading"]["completed_at"]:
        state["stages"]["paper_trading"] = {
            "completed_at": now_ist().isoformat(),
            "details": details,
        }
        _save_state(state)
        append_log(AUDIT_LOG_FILE, f"WORKFLOW PAPER TRADING STARTED: {details}")


def record_live_trading_started(**details):
    state = _load_state()
    if not state["stages"]["live_trading"]["completed_at"]:
        state["stages"]["live_trading"] = {
            "completed_at": now_ist().isoformat(),
            "details": details,
        }
        _save_state(state)
        append_log(AUDIT_LOG_FILE, f"WORKFLOW LIVE TRADING STARTED: {details}")


def record_performance_feedback(**details):
    _mark_stage("performance_feedback", **details)


def _stage_done(stage_name: str) -> bool:
    state = _load_state()
    return bool(state["stages"].get(stage_name, {}).get("completed_at"))


def can_run_simulation() -> tuple:
    # v4.1: simulation ab approval se PEHLE — decision engine (optimization +
    # validation done) hone ke baad hi result dikh sakta hai. Admin result
    # dekh ke satisfied ho kar /deployapprove karega.
    if not _stage_done("decision_engine"):
        return False, "Simulation blocked: decision engine (optimization + validation) not completed yet. Run /optimize first."
    return True, "OK"


def can_run_paper_trading() -> tuple:
    # Paper trading ke liye dono chahiye: admin ne simulation dekh kar
    # deployapprove kiya ho, AUR simulation final review complete ho.
    if not _stage_done("deployment_approval"):
        return False, "Paper trading blocked: deployment approval not completed yet."
    if not _stage_done("simulation"):
        return False, "Paper trading blocked: simulation final review not completed yet."
    return True, "OK"


def can_run_live_trading() -> tuple:
    ok, reason = can_run_paper_trading()
    if not ok:
        return False, reason
    if not _stage_done("paper_trading"):
        return False, "Live trading blocked: paper trading stage has not started yet."
    return True, "OK"


def can_activate_live_full() -> tuple:
    """F073 production-readiness gate for full live activation.

    LIVE_FULL is allowed only after the existing workflow proves the system has
    passed deployment approval, simulation, and paper-trading readiness. This
    keeps the runtime sequence unchanged and fail-closed.
    """
    ok, reason = can_run_live_trading()
    if not ok:
        return False, f"Live full activation blocked: {reason}"
    return True, "OK"


def can_execute_trade_cycle(real_orders: bool = False) -> tuple:
    if real_orders:
        return can_run_live_trading()
    return can_run_paper_trading()


def get_workflow_status_text() -> str:
    state = _load_state()
    lines = ["System Execution Workflow", ""]
    for stage in STAGE_ORDER:
        row = state["stages"].get(stage, {})
        stamp = row.get("completed_at")
        status = "DONE" if stamp else "PENDING"
        lines.append(f"{stage}: {status}" + (f" ({stamp[:16]})" if stamp else ""))
    return "\n".join(lines)
