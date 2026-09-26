# QASWA v6.0.3 — AUDIT HANDOFF / AI ONBOARDING

## Purpose
This ZIP is a **full codebase + audit package**. The receiving AI must inspect the actual extracted ZIP, not merely read the audit reports.

## Mandatory reading order
1. `prd.md`
2. `docs/PRE_VPS_GATE_PROFILE_v1.0.md`
3. `SYSTEM_BLUEPRINT.md`
4. `SYSTEM_MASTER_MANIFEST.json`
5. `docs/MASTER_ZERO_OMISSION_ZIP_INSPECTION_CONSTITUTION_55_SECTIONS.md`
6. `MASTER_AUDIT_EXECUTION_AND_SCORECARD.md`
7. `docs/AUDIT_55_EXECUTION_SCORECARD.md`
8. `docs/FRESH_FULL_55_SECTION_AUDIT_REPORT.md`
9. Run `python3 scripts/pre_vps_engineering_preflight.py` for the PRE-VPS engineering gate, then inspect **every artifact in the ZIP** independently.

## Mandatory answers the receiving AI must provide
- Was the **entire extracted ZIP** inspected, or only source code?
- How many files/directories were discovered, and how many were inspected?
- Were all **55 sections** actually executed against the package?
- Which checks were **locally executable** and what were their actual results?
- Which checks require external/VPS/broker/live-data execution?
- For each externally untestable item, what is the **code/evidence-based confidence score**, and exactly what evidence supports it?
- What external test must be performed, with procedure and expected result?
- Are there P0/P1/P2 findings, UNKNOWNs, owner decisions, or blockers?
- Are there fail-open paths, bypasses, dead gates, dead configuration, stale data, fabricated/default decision-critical data, or contradictory calculations?
- Are PRD, Blueprint, Manifest, code, configuration, workflow and audit constitution mutually consistent?
- Are canonical definitions actually used by downstream files, or are duplicate implementations present?
- Are formulas/economic calculations correct, unit-consistent, and derived from declared inputs rather than arbitrary/magic/hardcoded values?
- Is the command lifecycle correct end-to-end?
- Did any fix change another chained component and therefore require re-inspection?
- Is the ZIP **FINAL / CONDITIONAL / NOT READY**, and why?

## Non-technical owner requirement — operational reality
The inspection must not confuse “code exists” with “the system uses and enforces that code.” For every applicable criterion, independently trace:

**Criterion → Implementation → Integration/Wiring → Invocation/Reachability → Actual Effect → Enforcement → Failure/Bypass Analysis → Evidence**

Specifically search for dead code, unused configuration, disconnected functions, orphaned gates, shadowed settings, fallback/alternate paths, swallowed exceptions, bypasses, and later overrides that defeat the required method. A component that exists but is not actually used by the relevant system path is not a PASS.

The final owner-facing pre-VPS decision must use `docs/PRE_VPS_GATE_PROFILE_v1.0.md` together with `docs/PRE_VPS_VERIFICATION_GATE_v1.0.md` and must end with either:

> **🟢 PRE-VPS: PASS — ZIP VERIFIED — NEXT STEP: VPS**

or

> **🔴 PRE-VPS: FAIL — FIX REQUIRED — VPS DEPLOYMENT MAT KARO**

## Scorecard rules
### A. LOCAL VERIFIED SCORECARD
Only claim PASS when the check was actually executed in the available environment. Include command/test, evidence, result and scope.

### B. CODE/EVIDENCE CONFIDENCE SCORECARD
For checks that cannot be executed externally, score confidence from static/code/config/data/wiring evidence. This is **not a runtime PASS**. Explain evidence, assumptions, unknowns and residual risk. Never convert confidence into proof.

### C. EXTERNAL TEST REQUIRED MATRIX
For every external item list: test name, environment, prerequisites, procedure, expected result, failure action and whether it is a release blocker.

## Critical instruction
Do not add new trading functionality merely to satisfy an audit. Inspect first. If a defect exists, report it. If a fix is explicitly requested, update the affected individual and chained files together, then re-run the affected checks and finally perform a fresh full 55-section inspection.

## ONE-LINE INSPECTION TRIGGER — MANDATORY
The user may start the complete inspection with only:

> **Inspection karo ZIP ka.**

The receiving AI must interpret this as the full zero-omission independent re-verification defined in `docs/AI_INSPECTION_TRIGGER_AND_RESULT_CONTRACT_v1.0.md`. It must extract/inventory the complete ZIP, inspect every material artifact and cross-file chain, execute locally executable checks, separately classify external checks, understand code logic before judging it, verify prior CLOSED/PASS evidence independently, and issue its own PASS/CLOSED or FAIL/REOPENED result based on evidence. It must not reopen a correctly satisfying implementation merely because it prefers another implementation.

### Required user-facing summary
The final inspection must include:

```text
ZIP RE-VERIFICATION RESULT

ZIP Completeness:         XX%
Criteria Compliance:      XX%
Code/Logic Correctness:   XX%
Functional Verification:  XX%
Evidence/Certification:   XX%

OVERALL ZIP SCORE:        XX% / NOT CALCULABLE UNDER LOCKED SCORING RULE

FINAL VERDICT: PASS/CLOSED / CONDITIONAL / FAIL/REOPENED
MISSION STATUS: COMPLETE / NOT COMPLETE / EXTERNAL VERIFICATION PENDING
```

Percentages must be evidence-derived under the package's locked scoring rules. No arbitrary weighting may be invented.
