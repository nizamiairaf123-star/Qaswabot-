# QASWA — PRE-VPS VERIFICATION GATE v1.0

## Purpose
This gate gives a non-technical owner a deterministic answer about whether the ZIP has passed the complete pre-VPS inspection. It does **not** claim that VPS, broker, market-hours, or live execution has already been verified.

## One-line trigger
> **Inspection karo ZIP ka.**

The receiving AI must treat that sentence as a command to perform the complete zero-omission inspection defined by the package, including all applicable S1–S55 criteria and any genuinely independent S56+ sections.

## Section PASS contract
For every applicable section, the AI must verify the section's own criterion plus the universal operational-reality chain:

**Criterion → Implementation → Integration/Wiring → Invocation/Reachability → Actual Effect → Enforcement → Failure/Bypass Analysis → Evidence**

Code presence alone is never sufficient. A function that is never called, a setting that is never consumed, a gate that is bypassed, a fallback that defeats the required method, or an implementation that does not affect the actual decision path cannot receive PASS.

For non-runtime/package-structure criteria, the operational chain is marked NOT APPLICABLE; this must not be treated as an excuse to skip the section.

## Required per-section result
For S1–S55 (and any justified S56+), report: 

- Criterion: the exact locked criterion being judged.
- Artifact evidence: file/path/data/code location.
- Implementation: PRESENT / MISSING.
- Integration: CONNECTED / DISCONNECTED / N/A.
- Invocation/reachability: VERIFIED / NOT VERIFIED / N/A.
- Actual effect/enforcement: VERIFIED / NOT VERIFIED / N/A.
- Dead/bypass/fallback check: CLEAR / ISSUE FOUND / N/A.
- Execution evidence: TESTED / EXTERNAL REQUIRED / N/A.
- Section verdict: **PASS / FAIL / UNVERIFIABLE**.
- Reason: one concise evidence-based explanation.

A section may be PASS only when every applicable required field supports PASS.

## Final deterministic gate
The percentage is a secondary summary metric only. It cannot hide a failed mandatory or critical criterion.

### GREEN
If all required pre-VPS sections PASS, all critical pre-VPS gates PASS, no unresolved critical pre-VPS defect remains, and no required pre-VPS proof is missing. Items explicitly classified as EXTERNAL/AFTER-VPS are not counted as pre-VPS failures; they must instead have a defined post-deployment test and a fail-closed boundary where relevant:

> **🟢 PRE-VPS: PASS — ZIP VERIFIED — NEXT STEP: VPS**

### RED
If any required/critical pre-VPS section FAILS, or required evidence is unresolved/unverifiable for a mandatory pre-VPS criterion:

> **🔴 PRE-VPS: FAIL — FIX REQUIRED — VPS DEPLOYMENT MAT KARO**

### External boundary
A PRE-VPS PASS does not mean the VPS/broker/live environment has passed. Real VPS deployment, broker connectivity, market-hours behavior, real fills/rejections, production scheduler behavior, and other genuinely external checks remain environment-level verification items when applicable.

## Required owner-facing summary
```text
PRE-VPS VERIFICATION

Sections PASS: XX / XX
Sections FAIL: XX
Sections UNVERIFIABLE/EXTERNAL: XX
Critical Gates: PASS / FAIL
Overall Verification: XX% / NOT CALCULABLE UNDER LOCKED SCORING RULE

🟢 PRE-VPS: PASS — ZIP VERIFIED — NEXT STEP: VPS
```

or

```text
PRE-VPS VERIFICATION

Sections PASS: XX / XX
Sections FAIL: XX
Sections UNVERIFIABLE/EXTERNAL: XX
Critical Gates: PASS / FAIL
Overall Verification: XX% / NOT CALCULABLE UNDER LOCKED SCORING RULE

🔴 PRE-VPS: FAIL — FIX REQUIRED — VPS DEPLOYMENT MAT KARO
```


## Explicit PRE-VPS / AFTER-VPS boundary

The pre-VPS gate evaluates the engineering artifact and everything that can be deterministically verified from the ZIP/sandbox: requirements mapping, implementation, wiring, invocation, enforcement, safety logic, configuration semantics, data-schema/readiness controls, tests that are locally executable, dependency declaration, package integrity, provenance, and failure/bypass analysis.

The following are **AFTER-VPS / EXTERNAL VERIFICATION** items when the ZIP deliberately requires live infrastructure or a real provider: Dhan connectivity, VPS environment, real market-data refresh, real sector/industry/market-cap/liquidity/ATVR/FoT population, broker order/fill/rejection behavior, market-hours scheduler execution, and other environment-dependent evidence. Their absence in an offline ZIP is not itself a PRE-VPS engineering failure when the code contains the required fail-closed boundary and an explicit external test procedure.

An external item must never be converted into a fake PASS by inserting placeholder data. It is marked EXTERNAL REQUIRED / DEFERRED and becomes a release decision at the appropriate post-VPS gate.

## Operational Warnings

The following additional controls are SHOULD PASS warnings, not critical PRE-VPS blockers. Their implementation standard remains subject to actual code inspection and executable verification.

- [ ] GATE 13 (SHOULD PASS - Warning): Automated EOD Atomic Database Backup (scheduler.py using SQLite backup API).
- [ ] GATE 14 (SHOULD PASS - Warning): Rotating Audit Log Handler (trade_logger.py 10MB RotatingFileHandler).

### GATE 13 (Warning): Automated EOD Database Backup

**Check:** Verify that `scheduler.py` schedules `_job_eod_summary_and_backup` for 15:35 IST on weekdays, uses the actual QASWA SQLite database path, creates `data/backups/` safely, and uses SQLite `Connection.backup()` to create a transactionally consistent online snapshot. The resulting backup must pass SQLite `PRAGMA integrity_check` before it is reported as complete.

**Failure/Warning Conditions:** Source database missing, backup directory/destination failure, backup operation exception, integrity check failure, or a scheduler wiring/reachability failure. A failed or incomplete backup must never be reported as successful.

### GATE 14 (Warning): Rotating Audit Log Handler

**Check:** Verify that the actual QASWA trade-audit logging path in `trade_logger.py` uses `RotatingFileHandler` with `maxBytes=10 * 1024 * 1024`, `backupCount=5`, UTF-8 encoding, and duplicate-handler protection. Rotation must preserve continued logging after rollover.

**Failure/Warning Conditions:** Handler missing or disconnected from the trade-audit path, incorrect rotation/retention configuration, duplicate handlers, rotation failure, or logging that stops after rollover. Multi-process writers require separate deployment-level verification because the standard handler is not a general multi-process coordination mechanism.
