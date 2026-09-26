# CURRENT AUTHORITY (FROZEN)

- Governing standard: `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md` (internal framework version v1.3-FROZEN)
- Inspection backbone: `docs/MASTER_ZERO_OMISSION_ZIP_INSPECTION_CONSTITUTION_55_SECTIONS.md`
- Authority chain: **55 Sections → Quality/Defect Gate → Evidence Classification → Release Verdict → CLOSED/REOPENED continuity governance**
- Product sources: `prd.md`, `SYSTEM_BLUEPRINT.md`, code/config/data in this exact ZIP
- Current phase: **PRE-VPS ENGINEERING GATE**. AFTER-VPS external/runtime certification remains pending. Historical production-release reports are evidence only.

# QASWA v6.0.3 — CANONICAL RELEASE & AUDIT TRUTH INDEX

This file prevents PRD, Blueprint, ZIP, inspection criteria and scorecards from drifting apart. It adds no runtime functionality.

## Canonical order
1. `prd.md` — product requirements and owner decisions.
2. `SYSTEM_MASTER_MANIFEST.json` — system/domain source-of-truth registry.
3. `feature_sequence.json` — canonical Stage 0–11 runtime pipeline.
4. `SYSTEM_BLUEPRINT.md` — architecture and implementation explanation.
5. `docs/MASTER_ZERO_OMISSION_ZIP_INSPECTION_CONSTITUTION_55_SECTIONS.md` — **normative 55-section inspection checklist**.
6. `MASTER_AUDIT_EXECUTION_AND_SCORECARD.md` — how an auditor must execute and classify evidence.
7. `docs/AUDIT_55_EXECUTION_SCORECARD.md` — baseline/current evidence ledger.
8. `docs/PRE_VPS_GATE_PROFILE_v1.0.md` — canonical phase boundary for PRE-VPS vs AFTER-VPS evidence.
9. `docs/FRESH_FULL_55_SECTION_AUDIT_REPORT.md` — historical/fresh extracted-ZIP inspection evidence and findings.

## ZIP-first reconstruction
The current ZIP is the implementation source for completeness. PRD and Blueprint are updated from the ZIP before section-by-section inspection. The current baseline (as of r11, 2026-09-06) contains 177 input files (105 `.py`); `entry_follow`, `shadow_log`, and `mtf/` are explicitly mapped. The 55-section backbone remains sufficient at this baseline. *(Prior round's count of 151 files, retained as history, reflected an earlier package snapshot — not an omission in this one.)*

## Non-negotiable audit lenses
- Artifact & Code Integrity
- Data, Mathematics & Economics
- Pipeline, Workflow & Wiring
- Safety, Security & Compliance
- Runtime, Recovery & Release

## Evidence rule
Local code/data evidence and external/runtime evidence are **never merged into one score**. An untestable external dependency remains UNKNOWN until real evidence is supplied.

## Number/formula rule
Every decision-critical numeric value must have an identified meaning, unit, source/derivation and runtime consumer. Arbitrary, unexplained, duplicated, contradictory or bypassing numbers are findings. Financial calculations must be independently recalculated.

## No feature-addition rule
Inspection does not authorize new functionality. Confirmed defects may be fixed only when authorized, and the affected chain plus the complete 55-section inspection must be re-run after fixes.

## Current package truth
**Release identity:** QASWA v6.0.3

**PRE-VPS engineering verdict:** **PASS CANDIDATE** after the current reinspection, subject to the final zero-omission S1-S55 phase-gate report.

**AFTER-VPS status:** External provider data, broker/VPS/runtime evidence remain pending by design. The offline release preflight may therefore remain NOT READY without contradicting the PRE-VPS engineering gate.

**This status supersedes any older “PASS”, “production-ready”, or “verified clean” wording found in historical audit reports. Historical reports are preserved for audit trail only.**

## CLOSED-ITEM CONTINUITY

`docs/CERTIFICATION_CLOSURE_AND_REINSPECTION_GOVERNANCE_v1.0.md` is the canonical handoff rule. Later AIs verify CLOSED items against current ZIP reality and evidence; they do not reopen them for implementation preference. Reopening requires defined contradictory/stale/non-executable evidence, changed code/chain, higher-authority conflict, or new material runtime/data evidence. Genuine new independent risks remain reportable and follow the S56+ gate where necessary.
