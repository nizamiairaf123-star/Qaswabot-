"""
regime_manager.py — FIX-05 Market Regime Behavior

Same strategy, different aggression level.
Regime resizes trades; does not blindly block trades.
Circuit/health can still override.
"""

from config import PARAMS
from utils import append_log
from config import AUDIT_LOG_FILE


def get_current_regime() -> str:
    try:
        from market_regime import get_market_regime
        regime = get_market_regime(force_refresh=False)
        # v5.7: validate against config PARAMS (single source of truth) —
        # NOT a local DEFAULT_BEHAVIOR dict (that legacy dict was deleted
        # in the v5.7 refactor below; this line still referenced it,
        # raising NameError on every call and silently falling back to
        # SIDEWAYS regardless of actual detected regime).
        valid_regimes = PARAMS.get("regime_behavior_defaults", {})
        return regime if regime in valid_regimes else "SIDEWAYS"
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"REGIME MANAGER ERROR: {e}")
        from fallback_monitor import record_fallback   # FIX-LIST item 17 (visibility only)
        record_fallback("regime_manager.get_current_regime", e, "SIDEWAYS")
        return "SIDEWAYS"


def get_regime_behavior(regime: str = None) -> dict:
    regime = regime or get_current_regime()

    # v5.7: SINGLE SOURCE — regime behavior sirf config (PARAMS) se.
    # Legacy DEFAULT_BEHAVIOR dict DELETE (duplicate maintenance khatam).
    behavior = None
    cfg_defaults = PARAMS.get("regime_behavior_defaults", {})
    if isinstance(cfg_defaults, dict) and isinstance(cfg_defaults.get(regime), dict):
        behavior = dict(cfg_defaults[regime])
    if behavior is None:
        # conservative safe fallback (config miss ho to bhi fail-closed neutral)
        behavior = {"size_mult": 1.0, "max_slots_mult": 1.0, "min_slots": 1,
                    "tp1_full_exit": False, "trail_tightness": "NORMAL",
                    "description": "Safe neutral fallback (config missing)"}
        from fallback_monitor import record_fallback   # FIX-LIST item 17 (visibility only)
        record_fallback("regime_manager.get_regime_behavior", f"no config behavior for regime={regime}", "neutral 1.0x")

    # Allow optimizer/admin override later via PARAMS
    overrides = PARAMS.get("regime_behavior_overrides", {})
    if isinstance(overrides, dict) and regime in overrides:
        behavior.update(overrides[regime])

    behavior["regime"] = regime
    return behavior


def get_regime_size_multiplier() -> float:
    return float(get_regime_behavior().get("size_mult", 1.0))


def get_regime_max_slots(base_slots: int = None) -> int:
    base_slots = int(base_slots or PARAMS.get("max_slots", 8))
    b = get_regime_behavior()
    slots = int(round(base_slots * float(b.get("max_slots_mult", 1.0))))
    return max(int(b.get("min_slots", 1)), slots)


def should_full_exit_at_tp1() -> bool:
    """
    [OVERRIDE 1 — user-authorized architectural pivot] No longer called —
    the selected RR target is the profit-lock threshold; after that threshold
    the existing trailing/exit toolkit remains active and profit is uncapped.
    Left defined, not deleted, in case a future decision revisits this.
    """
    return bool(get_regime_behavior().get("tp1_full_exit", False))


def get_regime_report() -> str:
    b = get_regime_behavior()
    return (
        f"Regime Behavior — {b['regime']}\n"
        f"{b.get('description', '')}\n"
        f"Size Multiplier: {b.get('size_mult')}x\n"
        f"Max Slots Multiplier: {b.get('max_slots_mult')}x\n"
        f"Adjusted Max Slots: {get_regime_max_slots()}/{PARAMS.get('max_slots', 8)}\n"
        f"TP1 Full Exit: {'Yes' if b.get('tp1_full_exit') else 'No'}\n"
        f"Trail: {b.get('trail_tightness')}"
    )
