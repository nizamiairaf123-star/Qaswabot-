# QASWA_FUTURE_CHANGE_GOVERNANCE.md

**This is a governance/change-control process, not a trading decision gate, and not a new trading criterion.** It does not add, imply, or authorize any new trading rule (no CVaR, no new Sharia/financial-ratio filter, no new gate) — it defines the *process* any future proposal must go through before it can become one.

## The Process

```
1. Proposal / Problem
        ↓
2. Existing Criterion Check
        ↓ (covered?)  →  YES → use existing criterion, STOP (no new criterion needed)
        ↓ NO
3. New Criterion Decision (explicit owner decision required)
        ↓
4. PRD update (prd.md — exact requirement, acceptance/PASS-FAIL/evidence definition)
        ↓
5. Blueprint update (SYSTEM_BLUEPRINT.md — architecture placement, attribution if external method)
        ↓
6. Architecture / SEQ registration if applicable (seq_alignment_registry.py / feature_sequence.json —
   only if the change is a genuine new methodological-alignment component; do NOT force a new
   criterion into SEQ's stage-role mapping merely to complete the diagram)
        ↓
7. Manifest / Registry sync (SYSTEM_MASTER_MANIFEST.json — new domain entry if warranted)
        ↓
8. Implementation (source code — only after steps 1-7, never before)
        ↓
9. Tests (new/updated test_*.py — executed, not just written)
        ↓
10. Evidence (concrete: code read + functional execution + data check, not a documentation claim)
        ↓
11. Q&A / Audit status update (QASWA_AUDIT_QA_STATUS.md — new/updated question, real status)
        ↓
12. Certification (regression suite re-run, fresh-extract verification)
        ↓
13. Version / Changelog (VERSION.txt — full before/after/evidence trail, like every r13-r17 entry)
        ↓
14. Freeze
```

## Rules

1. **Step 2 is mandatory and comes first.** If an existing criterion (in `prd.md`'s 16 rules, `SYSTEM_BLUEPRINT.md`, or an existing frozen contract) already covers the proposal, no new criterion is created — the existing one is cited and the process stops there.
2. **A genuinely new requirement gets an explicit criterion**, stated with: exact requirement text, what PASS/FAIL/NOT PROVEN/EXTERNAL-DEFERRED look like for it, and what evidence would prove it — matching the discipline already used for Rule 14 (r13) and every Q001-Q036 entry in `QASWA_AUDIT_QA_STATUS.md`.
3. **Every location that describes the system must move together.** A change that touches `prd.md` but not `SYSTEM_BLUEPRINT.md`, or touches code but not `QASWA_AUDIT_QA_STATUS.md`, leaves the ZIP internally out-of-sync — the exact problem Phase 1-3 of this project's own history was created to prevent. Use `QASWA_MASTER_QA_HANDOVER.md`'s navigation map (§14) to find every file a given component touches.
4. **Frozen contracts (RR 1.8, Halal/Board hard gates, fail-closed data policy, no fabricated data, SEQ-is-not-a-gate) are never silently changed by this process.** Changing one of them requires the same explicit-decision step (3) as adding a brand-new criterion — it is not a lighter-weight path.
5. **This process itself does not retroactively introduce anything.** It does not reopen CVaR (confirmed this session: not a current criterion — see `QASWA_MASTER_QA_HANDOVER.md` §13), the deferred `init_state()` RR clamp (§6 of the handover, explicitly deferred, not forgotten), or any Phase-1 governance cluster (`QASWA_PHASE1_INVENTORY_CLASSIFICATION.md` §D) as an automatic to-do — each of those stays exactly where this session left it (open, disclosed, not actioned) until someone explicitly starts step 1 for it.
6. **"Safe Removal & No-Breakage Verification"** (the renamed, optional Phase-4 governance-cleanup idea) is a separate track from this process — this document governs *adding/changing* system behavior or criteria; that other one governs *removing* redundant documentation. Do not conflate the two.

## When This Process Does NOT Apply

- Routine documentation typo fixes, cross-reference corrections, or stale-number updates that don't change any criterion's meaning (e.g. the README rule-count fix, r13) — still gets a VERSION.txt entry, but doesn't need the full 14-step cycle.
- Read-only audits/inspections that find and report a defect without fixing it — that's evidence-gathering, not a change; the actual fix, when it happens, goes through this process.
