"""
bot_state_manager.py — Formal Bot State Machine
FIX-06 + FIX-48

States:
- PAPER              : Paper trading mode (default)
- LIVE_STAGED        : Live trading, staged capital
- LIVE_FULL          : Live trading, full capital
- TOKEN_INVALID_PAUSE: Dhan token expired, no new orders
- RAPID_LOSS_PAUSE   : 3 SL hits in 30 min, paused 1 hour
- KILLSWITCH_STOP    : Admin killswitch activated
- RECONCILIATION_HOLD: Mismatch detected, manual review needed
- COLD_START         : First boot, no state file
- EXIT_ONLY          : No new entries, existing positions exit normally
"""

import logging
from utils import load_json, save_json, now_ist, append_log
from config import AUDIT_LOG_FILE

logger = logging.getLogger(__name__)

STATE_FILE = "data/bot_state.json"

# Valid states
STATES = [
    "PAPER",
    "LIVE_STAGED",
    "LIVE_FULL",
    "TOKEN_INVALID_PAUSE",
    "RAPID_LOSS_PAUSE",
    "KILLSWITCH_STOP",
    "RECONCILIATION_HOLD",
    "COLD_START",
    "EXIT_ONLY",
]

# Per state: what is allowed
STATE_RULES = {
    "PAPER": {
        "new_entries":    True,
        "new_gtt":        True,
        "monitor":        True,
        "exit":           True,
        "orders_real":    False,   # Paper = no real orders
        "description":    "Paper trading — no real orders",
    },
    "LIVE_STAGED": {
        "new_entries":    True,
        "new_gtt":        True,
        "monitor":        True,
        "exit":           True,
        "orders_real":    True,
        "description":    "Live trading — staged capital",
    },
    "LIVE_FULL": {
        "new_entries":    True,
        "new_gtt":        True,
        "monitor":        True,
        "exit":           True,
        "orders_real":    True,
        "description":    "Live trading — full capital",
    },
    "TOKEN_INVALID_PAUSE": {
        "new_entries":    False,
        "new_gtt":        False,
        "monitor":        True,    # Monitor only — existing GTTs safe at broker
        "exit":           False,   # Bot cannot exit — GTTs protect
        "orders_real":    False,
        "description":    "Token expired — only /settoken accepted",
    },
    "RAPID_LOSS_PAUSE": {
        "new_entries":    False,
        "new_gtt":        False,
        "monitor":        True,
        "exit":           True,
        "orders_real":    True,
        "description":    "Rapid loss detected — paused 1 hour",
    },
    "KILLSWITCH_STOP": {
        "new_entries":    False,
        "new_gtt":        False,
        "monitor":        False,
        "exit":           False,
        "orders_real":    False,
        "description":    "Killswitch active — all stopped",
    },
    "RECONCILIATION_HOLD": {
        "new_entries":    False,
        "new_gtt":        False,
        "monitor":        True,
        "exit":           False,   # Do NOT auto-correct — admin review
        "orders_real":    False,
        "description":    "Reconciliation mismatch — manual review needed",
    },
    "COLD_START": {
        "new_entries":    False,
        "new_gtt":        False,
        "monitor":        True,
        "exit":           False,
        "orders_real":    False,
        "description":    "Cold start — recovery in progress",
    },
    "EXIT_ONLY": {
        "new_entries":    False,
        "new_gtt":        False,
        "monitor":        True,
        "exit":           True,    # Existing positions exit normally
        "orders_real":    True,
        "description":    "Exit only — no new entries, existing positions monitored",
    },
}


# ─────────────────────────────────────────────
# STATE MANAGEMENT
# ─────────────────────────────────────────────

def get_state() -> str:
    data = load_json(STATE_FILE, {"state": "COLD_START"})
    return data.get("state", "COLD_START")


def set_state(new_state: str, reason: str = ""):
    if new_state not in STATES:
        raise ValueError(f"Invalid state: {new_state}")

    old_state = get_state()
    save_json(STATE_FILE, {
        "state":      new_state,
        "previous":   old_state,
        "reason":     reason,
        "changed_at": now_ist().isoformat(),
    })
    append_log(AUDIT_LOG_FILE,
               f"STATE CHANGE: {old_state} → {new_state} | {reason}")


def get_rules() -> dict:
    state = get_state()
    return STATE_RULES.get(state, STATE_RULES["KILLSWITCH_STOP"])


# ─────────────────────────────────────────────
# PERMISSION CHECKS
# ─────────────────────────────────────────────

def can_enter() -> bool:
    return get_rules().get("new_entries", False)


def can_place_gtt() -> bool:
    return get_rules().get("new_gtt", False)


def can_monitor() -> bool:
    return get_rules().get("monitor", False)


def can_exit() -> bool:
    return get_rules().get("exit", False)


def is_real_orders() -> bool:
    base = get_rules().get("orders_real", False)
    if not base:
        return False
    try:
        from workflow_manager import can_run_live_trading
        ok, _ = can_run_live_trading()
        return ok
    except (ImportError, RuntimeError) as e:
        logger.warning(f"is_live_trading_allowed: Workflow check failed: {type(e).__name__}: {e}")
        return False


# ─────────────────────────────────────────────
# STATE TRANSITIONS
# ─────────────────────────────────────────────

def activate_paper():
    set_state("PAPER", "Paper trading mode activated")


def activate_live_staged():
    set_state("LIVE_STAGED", "Live staged trading activated by admin")


def activate_live_full():
    """Activate F073 LIVE_FULL only after workflow and capital-chain checks.

    LIVE_FULL means the full approved deployment envelope is unlocked; it must
    not merely change the state label while capital_manager remains on a
    partial deployment stage.
    """
    from workflow_manager import can_activate_live_full
    ok, reason = can_activate_live_full()
    if not ok:
        append_log(AUDIT_LOG_FILE, f"LIVE_FULL ACTIVATION BLOCKED: {reason}")
        raise RuntimeError(reason)

    from capital_manager import enforce_full_deployment_stage, get_current_stage
    previous_stage = get_current_stage("admin")
    full_stage = enforce_full_deployment_stage("admin")

    set_state(
        "LIVE_FULL",
        f"Full capital live trading activated by admin | stage {previous_stage} -> {full_stage}"
    )


def activate_token_pause(reason: str = "Token expired"):
    set_state("TOKEN_INVALID_PAUSE", reason)
    _alert_admin_state("TOKEN_INVALID_PAUSE", reason)


def activate_rapid_loss_pause(reason: str = "3 SL hits in 30 min"):
    set_state("RAPID_LOSS_PAUSE", reason)
    _alert_admin_state("RAPID_LOSS_PAUSE", f"Rapid loss detected: {reason}")


def activate_killswitch():
    set_state("KILLSWITCH_STOP", "Admin killswitch")


def activate_reconciliation_hold(reason: str = "Mismatch detected — manual review"):
    set_state("RECONCILIATION_HOLD", reason)
    _alert_admin_state("RECONCILIATION_HOLD", reason)


def check_and_clear_rapid_loss_pause():
    """FIX: RAPID_LOSS_PAUSE previously never auto-expired -- nothing ever
    reverted the state after the configured rapid_loss_pause_min window.
    Call periodically (wired into scheduler.py) to auto-revert to whatever
    state was active immediately before the pause, once the window elapses.
    """
    data = load_json(STATE_FILE, {"state": "COLD_START"})
    if data.get("state") != "RAPID_LOSS_PAUSE":
        return

    from safety_manager import get_pause_until
    pause_until = get_pause_until()
    if not pause_until:
        return

    from datetime import datetime
    if now_ist() < datetime.fromisoformat(pause_until):
        return

    previous = data.get("previous", "PAPER")
    if previous not in STATES:
        previous = "PAPER"
    set_state(previous, f"Rapid-loss pause window elapsed — reverted to {previous}")
    _alert_admin_state(previous, "Rapid-loss pause window elapsed — trading resumed")


def activate_exit_only(reason: str = "Admin /exitonly command"):
    set_state("EXIT_ONLY", reason)


def resume_from_pause():
    """Resume to previous trading state."""
    data = load_json(STATE_FILE, {})
    previous = data.get("previous", "PAPER")
    # Only resume to valid trading states
    if previous in ("LIVE_STAGED", "LIVE_FULL", "PAPER"):
        set_state(previous, "Resumed from pause")
    else:
        set_state("PAPER", "Resumed — defaulting to PAPER")


def get_status_text() -> str:
    state = get_state()
    rules = get_rules()
    data  = load_json(STATE_FILE, {})
    text = (
        f"Bot State: {state}\n"
        f"Description: {rules['description']}\n"
        f"New Entries: {'Yes' if rules['new_entries'] else 'No'}\n"
        f"Monitoring: {'Yes' if rules['monitor'] else 'No'}\n"
        f"Exit Allowed: {'Yes' if rules['exit'] else 'No'}\n"
        f"Real Orders: {'Yes' if is_real_orders() else 'No'}\n"
        f"Changed: {data.get('changed_at', 'N/A')[:16]}\n"
        f"Reason: {data.get('reason', 'N/A')}"
    )
    try:
        from workflow_manager import get_workflow_status_text
        text += "\n\n" + get_workflow_status_text()
    except (ImportError, RuntimeError) as e:
        logger.warning(f"get_status_text: Workflow status failed: {type(e).__name__}: {e}")
    return text


def _alert_admin_state(state: str, reason: str):
    try:
        from signal_broadcaster import alert_admin
        import asyncio
        _msg = (
            f"BOT STATE CHANGE\n"
            f"New State: {state}\n"
            f"Reason: {reason}\n\n"
            f"{STATE_RULES[state]['description']}"
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(alert_admin(_msg))
        except RuntimeError:
            # No running event loop (e.g. called from a sync context like
            # broker.get_dhan()) -- deliver via the sync wrapper instead of
            # silently dropping this state-change alert.
            from signal_broadcaster import alert_admin_sync
            alert_admin_sync(_msg)
    except (ImportError, RuntimeError) as e:
        logger.warning(f"activate_killswitch: Alert failed: {type(e).__name__}: {e}")
