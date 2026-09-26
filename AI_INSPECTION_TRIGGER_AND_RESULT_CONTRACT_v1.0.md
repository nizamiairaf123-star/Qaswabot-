# QASWA — AI INSPECTION TRIGGER & RESULT CONTRACT v1.0

## Purpose
A receiving AI must be able to start the complete QASWA inspection from one short user instruction without losing the zero-omission inspection requirement.

## Universal one-line trigger
> **Inspection karo ZIP ka.**

This instruction means: perform the complete independent ZIP re-verification governed by the package's canonical Audit Protocol, Inspection Constitution, Inspection Certification Standard, PRD, Blueprint and manifest; extract and inventory the complete ZIP; inspect code, data, configuration, tests, dependencies, state, logs, deployment/runtime artifacts and cross-file wiring; execute all locally executable checks; classify non-executable checks correctly; independently verify prior CLOSED/PASS evidence rather than blindly copying it; and produce the evidence-based score and verdict below.

## Mandatory operational-reality check
For every applicable section, the AI must distinguish **code presence from operational implementation**. PASS requires verification of the chain:

**Criterion → Implementation → Integration/Wiring → Invocation/Reachability → Actual Effect → Enforcement → Failure/Bypass Analysis → Evidence**

The AI must actively look for never-called functions, unused settings, orphan gates, disconnected modules, shadowed configuration, bypasses, fallback/override paths, exception paths that defeat enforcement, and alternate implementations that replace the required method. If the required mechanism is present but not actually used or enforced, the section is FAIL, not PASS.

## Mandatory interpretation
The receiving AI must:
1. Inspect the actual extracted ZIP, not only reports or README files.
2. Apply the canonical zero-omission inventory and 55-section backbone; add S56+ only for genuinely independent findings required by the existing gate.
3. Understand the implementation logic before judging whether a criterion is satisfied.
4. Give its own PASS/CLOSED when the inspected logic satisfies the locked criterion and the supporting evidence is valid.
5. Give FAIL/REOPENED when actual contradictory evidence, a genuine defect, stale/invalid evidence, changed implementation, or other defined reopening trigger is found.
6. Never treat a different implementation preference, refactoring preference, naming preference, library preference, or audit-style preference as a defect when the locked criterion is satisfied.
7. Never convert an unexecuted external check into a runtime PASS. Report code/evidence confidence separately and identify required external proof.
8. Never invent percentages or use arbitrary scoring weights. Percentages must follow the canonical scoring rules and any owner-ratified weights already present in the package.
9. If a canonical percentage cannot legitimately be calculated because its required weight/rule is not ratified, say **NOT CALCULABLE UNDER LOCKED SCORING RULE** rather than inventing one.
10. Base the final conclusion on current ZIP evidence, not on the user's expected answer.

## Pre-VPS decision gate
After completing the section-level inspection, apply `docs/PRE_VPS_VERIFICATION_GATE_v1.0.md`. The owner-facing result must resolve to exactly one of:

- **🟢 PRE-VPS: PASS — ZIP VERIFIED — NEXT STEP: VPS**
- **🔴 PRE-VPS: FAIL — FIX REQUIRED — VPS DEPLOYMENT MAT KARO**

A percentage is supporting information only and must never override a failed mandatory/critical criterion.

## Mandatory final result format
The receiving AI must finish with a concise summary in this form:

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

The detailed evidence, section matrix, executed-test results, external-required matrix and defects remain part of the full inspection report. The five displayed percentages are summary views only and must not override the canonical scoring rules or mandatory release gates.

## Completion meaning
`MISSION STATUS: COMPLETE` is appropriate only when the receiving AI's independent inspection supports that conclusion. A high percentage alone is never sufficient. A mandatory failed gate, unresolved critical defect, or required external proof that is still absent must be reflected in the verdict.
