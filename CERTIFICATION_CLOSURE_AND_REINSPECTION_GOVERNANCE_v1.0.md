# QASWA — CERTIFICATION CLOSURE & RE-INSPECTION GOVERNANCE v1.0

## Purpose

This governance rule prevents a completed audit item from being repeatedly reopened merely because a later AI/auditor prefers a different implementation style.

It does **not** protect defective code. It protects the audit decision from methodology drift while keeping independent verification intact.

## Canonical lifecycle

Every material finding/criterion follows:

`OPEN → FIXED → TESTED-PASS → CLOSED`

If later contradictory evidence appears:

`CLOSED → REOPENED → FIXED → TESTED-PASS → CLOSED`

`DONE` alone is not a certification state and has no evidentiary meaning.

## Definition of CLOSED

A finding or criterion may be marked **CLOSED** only when all applicable conditions are satisfied:

1. The exact criterion/requirement ID is recorded.
2. The implementation location (file/function/config/data) is recorded.
3. The required inspection was actually performed.
4. Any locally executable regression test actually ran and passed.
5. External requirements are explicitly separated and are not falsely represented as local PASS.
6. The evidence identifier, command/procedure, result, date, and release identity/hash are recorded.
7. The affected dependency/chain was checked where the change could propagate.
8. No contradictory evidence is known at closure time.

For a testable defect, the preferred proof is:

`reproduce failure → apply fix → regression PASS → affected-chain retest → evidence recorded → CLOSED`

## Re-inspection rule

A new AI/auditor must **verify CLOSED items, not redesign them**.

Verification asks:

- Does the current ZIP still contain the implementation recorded in the closure evidence?
- Does the evidence correspond to this release/version/hash or to an explicitly linked predecessor whose change scope is unchanged?
- Did the required test actually execute and pass?
- Is the evidence stale, false, contradictory, or non-executable?
- Did a later change touch the same file/function/chain?

If the answers are consistent, the item remains **CLOSED**.

## Valid reopen triggers

A CLOSED item may be reopened only when independent evidence shows at least one of:

- closure evidence is false or cannot be reproduced;
- closure evidence is stale for the inspected release;
- the test claimed as PASS never actually executed;
- actual test output contradicts the recorded result;
- the current ZIP no longer matches the closed implementation;
- a later change affects the closed item or its safety-critical dependency chain;
- a higher-authority locked requirement is violated;
- a new runtime/data observation demonstrates that the original closure was materially incomplete;
- a previously external requirement has now become testable and the new evidence fails.

## Invalid reopen reasons

The following are **not defects** by themselves:

- "I would implement it differently."
- "I prefer another architecture."
- "This could be cleaner/refactored."
- "A different library/method could also be used."
- "I would name the function differently."
- "I would add another check even though the locked criterion is already satisfied."
- "A newer AI has a different audit style."

These are methodology or implementation preferences, not evidence of non-compliance.

## New findings are still allowed

This governance rule does **not** create a false-completeness shield.

A later auditor must still report a genuinely new independent defect or risk discovered in the current ZIP. If it fits an existing criterion, it is recorded there. If it is a genuinely independent material risk class outside the frozen 55-section scope, it follows the S56+ gate rather than being hidden.

## Evidence hierarchy

When deciding whether to keep or reopen a CLOSED item, use this order:

1. Current ZIP implementation/data reality.
2. Actual executable test output.
3. Evidence must be linked to the exact inspected release identity/hash.
4. Locked inspection criteria and governing protocol.
5. Historical reports and narrative claims.

A historical report never overrides current ZIP reality.

## Release identity rule

A closure record must identify the release it applies to. Any material file change invalidates closure evidence for that affected chain until the change is re-inspected and retested. Unaffected CLOSED items do not need to be reinvented merely because another file changed.

## AI handoff rule

A receiving AI must read the governing PRD/Blueprint, the inspection framework, this governance rule, and the available evidence records before inspecting the actual ZIP. It must then inspect the relevant code/data at implementation level and independently determine PASS/FAIL against the locked criterion.

A prior CLOSED result is a starting evidence point, not a substitute for verification. If the current implementation still satisfies the criterion and the closure evidence is valid, the receiving AI may issue its **own PASS/CLOSED result**. If actual contradictory evidence or a real defect is found, it must issue its **own FAIL/reopen result** with evidence.

A new session does not justify redesigning a correct implementation. The receiving AI should preserve a valid closure and challenge it only through the evidence-based reopen triggers above.

## Core principle

> **CLOSED + valid evidence → VERIFY, DON'T REINVENT.**
>
> **Contradictory evidence → REOPEN.**
>
> **Implementation preference alone → NO REOPEN.**
