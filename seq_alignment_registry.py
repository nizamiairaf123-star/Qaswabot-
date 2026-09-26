"""
seq_alignment_registry.py — QASWA Remix "SEQ" (systematic/quantitative
industry-best-practice alignment layer) registry. See prd.md Rule 14.

NAMING NOTE (important — do not confuse the two): this "SEQ" is the
Rule 14 / QASWA Remix term. It is UNRELATED to the pre-existing
"SEQ_FILE" / "SEQ MATCH" shorthand used elsewhere in this codebase
(test_sequence.py, SYSTEM_MASTER_MANIFEST.json domain 1) for
feature_sequence.json — that older usage is short for "SEQUENCE" and
was already in the codebase before Rule 14 existed. The two are
coincidental namesakes with different meanings.

SCOPE (per Rule 14 / Remix prompt Section 10 — what this file does
NOT do): it adds no new indicators, makes no existing tool newly
mandatory, and introduces zero new decision/trading logic. It is a
declarative, read-only registry that:
  1. States the mandatory hard-gate order (Business Halal Filter ->
     Non-Muslim Board Filter -> SEQ -> trade decision/execution),
     matching prd.md Rule 14 exactly.
  2. Maps QASWA's existing pipeline stages (feature_sequence.json
     Stage 0-11) to the SEQ methodological role each already fulfills.
     No stage's actual behavior changes because of this file.
  3. Is imported and invoked once at boot (startup_recovery.py ->
     run_startup_recovery()) so this registration is a real, reachable,
     executed runtime component — not a dormant/dead file that exists
     only on paper (the same class of gap flagged and fixed for
     broker.py's dead state-name earlier in this project's history).

The two mandatory hard gates (Business Halal Filter, Non-Muslim Board
Filter) are enforced where they always were — stock_selector.py's
_row_is_halal_eligible() — and are NOT reimplemented or duplicated
here. This registry documents/traces that order; it does not gate
anything itself, and a failure in this module must never block or
alter a trade decision (see log_seq_boot_trace()'s fail-open design).
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

# Rule 14 mandatory hard-gate order (non-negotiable, sequence fixed).
HARD_GATE_ORDER = [
    "business_halal_filter",    # Rule 2 — stock_selector.py: core_business_halal check
    "non_muslim_board_filter",  # Rule 3 — stock_selector.py: non_muslim_board check
    "seq",                      # this layer — systematic/quant alignment (Rule 14)
    "trade_decision_execution",
]

# Maps feature_sequence.json Stage id -> SEQ methodological role.
# Stage 0 is where Rules 2/3 (the two mandatory gates) are actually
# enforced, upstream of SEQ. Stages 1-2 are bot/admin infra (neither a
# gate nor SEQ). Stages 3-11 are SEQ — existing, already-shipped
# components aligned to their methodological role; nothing here is a
# new feature or newly made mandatory (Rules 6/7/11/12 already govern
# this and predate this registry).
SEQ_STAGE_ROLES = {
    0: "PRE_SEQ_HARD_GATES — Business Halal Filter -> Non-Muslim Board Filter (Rule 2/3)",
    1: "INFRA — bot startup (not a gate, not SEQ)",
    2: "INFRA — admin setup (not a gate, not SEQ)",
    3: "SEQ: Market & Data Context (universe/eligibility, daily data collection)",
    4: "SEQ: Signal / Strategy Research (market_analysis)",
    5: "SEQ: Strategy/Tool Combination Selection + Optimization (strategy_optimization)",
    6: "SEQ: Robustness & Validation (validation)",
    7: "SEQ: Risk & Capital decision gate (deployment_decision)",
    8: "SEQ: Execution / Position Management, dry-run (paper_trading)",
    9: "SEQ: Execution / Position Management / Exit (live_trading)",
    10: "SEQ: Capital Allocation replication (copy_trading)",
    11: "SEQ: Reconciliation / Performance Feedback (monitoring_compliance)",
}


def get_seq_status() -> dict:
    """Read-only status snapshot. No side effects, no decision logic."""
    return {
        "identity": "QASWA Remix -> AIRAF NIZAMI (prd.md Rule 14)",
        "hard_gate_order": HARD_GATE_ORDER,
        "seq_stage_roles": SEQ_STAGE_ROLES,
        "note": ("SEQ is QASWA's internal alignment label only — not a claimed "
                 "pre-existing official methodology name (Rule 14)."),
    }


def log_seq_boot_trace(append_log_fn=None, audit_log_file=None) -> dict:
    """
    Called once at boot so this registry is a real, executed runtime
    component. Purely additive/observational: writes one audit-log line
    (or a plain logger.info if no audit-log function is supplied) and
    returns the status dict. Never raises — any internal error is
    caught and logged, and must never block or alter startup/trading.
    """
    status = get_seq_status()
    try:
        msg = ("SEQ REGISTRY (Rule 14 QASWA Remix systematic/quant alignment "
               "layer) loaded at boot — hard-gate order: "
               + " -> ".join(HARD_GATE_ORDER))
        if append_log_fn and audit_log_file:
            append_log_fn(audit_log_file, msg)
        else:
            logger.info(msg)
    except Exception as e:
        logger.warning(
            f"seq_alignment_registry: boot-trace log failed (non-blocking): "
            f"{type(e).__name__}: {e}"
        )
    return status
