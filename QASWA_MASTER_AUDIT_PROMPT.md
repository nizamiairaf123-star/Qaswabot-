> **FILE ROLE (added 2026-09-08, r20 — this note is NOT part of the original instruction; the verbatim instruction begins after this box):**
> This is the canonical **Master Audit / Governance Instruction** for QASWA, added into the ZIP itself so a future AI or developer can resolve a defect using the same standard this project has always been built/audited against — without needing it re-supplied externally each session (previously, per `QASWA_PHASE1_INVENTORY_CLASSIFICATION.md` and `QASWA_AUDIT_QA_STATUS.md` Q013, no such file existed inside the ZIP at all).
>
> **Role relative to the other governance files (do not conflate):**
> - `SYSTEM_MASTER_MANIFEST.json` = machine-readable authoritative registry/metadata.
> - `QASWA_SYSTEM_TRUTH.md` = human-readable system narrative ("what QASWA IS").
> - `QASWA_AUDIT_QA_STATUS.md` = evidence ledger ("what is PROVEN").
> - `QASWA_MASTER_QA_HANDOVER.md` = single-file AI onboarding + navigation map.
> - **This file (`QASWA_MASTER_AUDIT_PROMPT.md`) = the audit/governance *process* standard — HOW to inspect, verify, fix, and certify QASWA** (frozen-criteria discipline, evidence rules, file-classification rules, deletion rules, STOP conditions). It governs *how* work gets done; it does not itself state new trading criteria and does not override `prd.md`'s Owner Constitution or any frozen contract.
> - `QASWA_FUTURE_CHANGE_GOVERNANCE.md` is a shorter, QASWA-specific distillation of the *change-control* subset of this instruction (Proposal→Freeze for new features/criteria) — this file is the fuller, original standard it was distilled from.
>
> Content below this box is the **exact, unmodified, verbatim** instruction as supplied by the owner on 2026-09-07, governing this session's r13-r19 work. It is preserved as-is — do not edit Part A/Part B below without an explicit owner decision to revise the standard itself.

---

# QASWA — FROZEN CRITERIA / ZERO SCOPE CREEP
## MASTER BUILD + AUDIT + FIX INSTRUCTION — v2 (Base + Field-Tested Addendum)

> **How to use this file**: Part A is the original governing instruction,
> unchanged. Part B is a set of additions written after actually running
> this discipline through 12+ real inspection batches on the QASWA zip
> (r7 → r11). Nothing in Part B contradicts or loosens Part A — every
> addition either closes a gap that caused real friction, or names a
> technique that was used repeatedly but never written down. Give this
> whole file to any AI (this one, in a new session, or a different model)
> before it inspects or fixes the QASWA project.

---

# PART A — ORIGINAL FROZEN INSTRUCTION (verbatim, unchanged)

You are auditing/building/fixing the QASWA trading-bot project.

Your job is NOT to redesign the project according to your own preferences.

Your job is to make the project conform exactly and only to the supplied QASWA Criteria / Constitution / Source-of-Truth documents.

---

## 1. ABSOLUTE SOURCE OF TRUTH

The supplied QASWA Criteria are the FROZEN SPECIFICATION.

Treat them as a contractual acceptance specification.

They are not suggestions.
They are not guidelines.
They are not a starting point for your own architecture.
They are not open to interpretation based on your personal preference.

The final project must implement the supplied criteria exactly.

**HARD RULE**

«IF SOMETHING IS NOT REQUIRED, PROHIBITED, OR DEFINED BY THE FROZEN CRITERIA, DO NOT INVENT A NEW REQUIREMENT FOR IT.»

Do not convert an optional improvement, industry preference, architectural preference, or personal recommendation into a defect.

---

## 2. NO NEW BUGS / NO INVENTED REQUIREMENTS

During inspection, classify an issue as a genuine defect ONLY if you can demonstrate:

1. Which exact frozen criterion is violated.
2. What exact requirement inside that criterion is violated.
3. Where in the project the violation exists.
4. Why the current implementation contradicts that requirement.
5. What exact evidence proves the contradiction.
6. That the issue is inside the defined QASWA scope.

If you cannot establish all of the above:

DO NOT CALL IT A BUG.

Do not report:

- "I would design it differently."
- "Industry standard would be..."
- "A professional system should also..."
- "You should consider..."
- "It would be better if..."
- "This could potentially..."
- "I recommend..."
- "I expected..."
- "Normally systems should..."
- "This architecture is not ideal..."
- "This could be improved..."

None of these constitute a QASWA defect unless the frozen criteria explicitly require that behavior.

---

## 3. CRITERIA ARE FROZEN

The auditor is NOT authorized to expand the specification.

Do NOT:

- add new criteria;
- create hidden criteria;
- introduce new mandatory controls;
- impose external standards;
- impose personal coding preferences;
- redesign architecture without a criteria violation;
- change business logic because you prefer another method;
- change strategy mathematics because another method is common;
- change Sharia rules;
- change RR rules;
- change universe rules;
- change deployment rules;
- change data rules;
- change optimizer rules;
- change exit rules;
- change risk rules;
- change execution rules;
- change subscription rules;
- change state-machine behavior;

unless the supplied frozen criteria explicitly require the change.

---

## 4. IMPORTANT DISTINCTION

Every finding MUST be classified into one of these categories:

**A. SPEC VIOLATION** — The implementation directly contradicts a frozen criterion.

**B. IMPLEMENTATION BUG** — The required behavior is defined by the criteria but implemented incorrectly.

**C. INTEGRATION / WIRING BUG** — The required component exists but is not correctly connected to the required runtime path.

**D. DATA / ARTIFACT VIOLATION** — A shipped file, dataset, JSON, CSV, manifest, log, cache, database, etc. violates a frozen criterion.

**E. TEST GAP** — The criteria require proof/testing but the required proof is absent.

**F. EXTERNAL / DEFERRED** — The requirement cannot be conclusively verified locally because it depends on VPS, broker, live market data, credentials, external provider, deployment environment, etc. This is NOT automatically a bug.

**G. OUT OF SCOPE / OPTIONAL IMPROVEMENT** — Anything not required by the frozen criteria. Do NOT report this as a defect.

**H. FALSE POSITIVE** — An apparent issue that is actually permitted by the frozen criteria or already intentionally handled elsewhere.

---

## 5. ZERO SCOPE CREEP RULE

Before reporting ANY issue, ask:

«"Can I point to an exact frozen criterion that requires the opposite behavior?"»

If the answer is NO: Do not report it as a bug.

If the answer is YES: provide the exact criterion and evidence.

---

## 6. DO NOT JUDGE BY FILE EXISTENCE ALONE

For every criterion, verify the complete chain:

Criterion → Requirement → Implementation → Integration / Wiring → Invocation / Reachability → Actual Effect → Enforcement → Failure / Bypass Behavior → Evidence

A function existing is not enough. A test existing is not enough. A configuration value existing is not enough. A document claiming something is not enough.

But equally: Do NOT invent additional requirements beyond the criterion.

---

## 7. COMPLETE PROJECT INSPECTION

Inspect the COMPLETE supplied ZIP/project. Do not assume that a component is correct merely because documentation says it is correct. Do not inspect only Python source.

The inspection must include every artifact relevant to the frozen criteria, including: Python files, shell scripts, service files, configuration, JSON, CSV, databases, logs, cache, generated files, manifests, dependency files, tests, documentation, state files, deployment files, strategy files, optimizer, exit engine, risk engine, order engine, scheduler, broker integration, universe pipeline, compliance pipeline, data pipeline, runtime state, deployment configuration.

No artifact may be ignored merely because it appears unimportant.

---

## 8. CSV / DATA RULE

Do not audit only CSV schemas or code that reads them. Inspect actual contents. Check according to the frozen criteria: rows, columns, values, blanks, placeholders, duplicates, invalid values, impossible values, semantic consistency, cross-file consistency, source/provenance, freshness, runtime usage.

But do NOT create new data-quality requirements that are not present in the frozen criteria.

---

## 9. JSON / STATE RULE

Inspect actual JSON/state content. Verify: syntax, required keys, values, types, consistency, runtime consumption, fail-closed behavior where required, stale/missing handling where required.

Do not declare a JSON field "wrong" merely because you personally would store another value.

---

## 10. DATABASE RULE

Inspect database structure and actual contents where applicable. Verify only what the frozen criteria require. Do not impose a different database architecture merely because another database design is possible.

---

## 11. DOCUMENTATION RULE

Documentation is evidence, but documentation alone does not prove runtime behavior. Cross-check important claims against implementation. However, do not treat a documentation wording preference as a defect unless it contradicts a frozen requirement.

---

## 12. TEST RULE

Tests are evidence, not automatic truth. A passing test does not override an actual implementation contradiction. Likewise, absence of a test is a defect ONLY when the frozen criteria require that proof/test. Do not demand tests that the criteria do not require.

---

## 13. EXTERNAL DEPENDENCY RULE

If verification requires: VPS, broker, live Dhan API, real market data, external provider, credentials, live network, production database, real deployment, live trading environment — and those are unavailable: mark the criterion EXTERNAL / DEFERRED.

Do NOT invent a bug merely because local verification cannot prove it. Do NOT fake PASS. Do NOT fake FAIL. Do NOT fabricate external evidence.

---

## 14. FROZEN QASWA BUSINESS RULES

The following are already-decided QASWA rules and MUST be treated as frozen. Do not reinterpret them.

**RR / EXIT CONTRACT**
- RR is NOT optimizer-selected.
- RR lock is EXACTLY 1.8R.
- 1R = actual entry-to-initial-SL distance.
- Initial SL = actual entry candle low.
- Before exactly 1.8R: no BE lock; no +1R lock; no early trailing.
- At exactly 1.8R: profit protection / lock activates.
- After 1.8R: existing optimizer-selected trailing/exit combination manages the position. Profit upside remains uncapped.
- Legacy/persisted "min_reward_risk" values must not override the exact 1.8R lock.
- Optimizer MUST NOT search/select RR.

Do NOT suggest changing 1.8R. Do NOT call "minimum 1.8R" a requirement if the frozen contract says exact 1.8R.

---

## 15. ATR CONTRACT

ATR must use canonical Wilder/RMA-style smoothing. The canonical implementation is the project's defined ATR contract. Do NOT replace it with another ATR methodology merely because another implementation is common. Do NOT report legitimate EMA/MACD "ewm(span=...)" usage as an ATR bug. Only report an ATR issue if the actual ATR calculation violates the frozen ATR requirement.

---

## 16. SHARIA / CUSTOM UNIVERSE CONTRACT

The frozen QASWA compliance model is: no AAOIFI financial-ratio screening; no debt-ratio filter; no cash-ratio filter; no non-halal-income-ratio filter; no purification mechanism in trading/compliance path. Standalone zakat calculator may exist but must not act as a trade/purification gate. Custom identity/business filter. Strict sector filter. NSE only. EQ series only. Suspended stocks rejected. Explicit non-tradeable/banned/delisted statuses rejected. ASM/GSM are informational and are NOT automatic rejection criteria. Scan the NSE universe; no arbitrary pre-selection. Conventional banking, insurance, alcohol, gambling, tobacco, adult entertainment, interest-based finance, NBFC and other explicitly blocked sectors/keywords are rejected according to the frozen configuration. Board criterion is the explicitly defined QASWA owner rule. Board-data failure must be FAIL-CLOSED where the frozen rule requires it.

Do not reintroduce AAOIFI ratios. Do not invent additional Sharia filters.

---

## 17. STRATEGY TOOL CONTRACT

QASWA has exactly the defined strategy tools. A stock may use any valid non-empty subset of the defined tools. Do NOT impose: fixed TOP-3 tools; fixed number of tools; AND-only voting; a different selection mechanism — unless the frozen criteria explicitly require it. "top_n=3" used for parameter-set averaging is NOT automatically a three-tool restriction.

---

## 18. BACKTEST / PAPER / LIVE CONTRACT

The objective is approximately: Backtest ≈ Paper ≈ Live. This is a robustness/alignment objective. Exact equality is NOT required because of spread, slippage, latency, partial fills, execution differences. Do not report normal execution differences as bugs unless they violate an explicit frozen criterion. Missing samples must not be converted into fake PASS. If insufficient data exists where the frozen criteria require sample sufficiency: mark appropriately as insufficient/external.

---

## 19. FAILURE / FAIL-CLOSED CONTRACT

Where the frozen criteria require fail-closed behavior: failure must produce denial/block/pause rather than silent approval. Do not weaken fail-closed behavior. Do not replace fail-closed with fail-open. But do not demand fail-closed behavior in areas where the frozen criteria do not require it.

---

## 20. NO RETROACTIVE REQUIREMENTS

Do not judge the project against requirements introduced after the frozen specification. The question is: «"Does this implementation satisfy the supplied frozen QASWA criteria?"» NOT: «"Would I build it differently today?"»

---

## 21. NO "95% ACCURATE" VERDICT

Do NOT use vague scoring such as: 95% accurate; 97% professional; almost production ready; mostly correct; 90% compliant. The acceptance model is criterion-based. For every criterion: PASS or FAIL or EXTERNAL/DEFERRED, with evidence. A criterion is not "95% passed."

---

## 22. FINAL ACCEPTANCE STANDARD

The target is: 55/55 CRITERIA SATISFIED. A final PASS means: every frozen criterion has been checked; every applicable requirement is satisfied; no genuine criterion violation remains; no known implementation/integration/data/artifact defect remains; required tests/evidence exist; external requirements are separately identified; no scope has been expanded.

If external requirements are necessary for final release but cannot be executed locally: the engineering package may be PRE-VPS PASS, while the final LIVE RELEASE remains EXTERNAL/DEFERRED. Do not falsely label it live-ready.

---

## 23. FIXING RULE

If a genuine frozen-criteria violation is found: identify exact criterion; identify exact violation; fix ONLY that violation; do not redesign unrelated components; do not introduce new requirements; run relevant regression tests; run the complete required verification again; regenerate manifests/inventory if the package changed; re-inspect the resulting ZIP.

If no frozen-criteria violation exists: DO NOT CHANGE CODE.

---

## 24. ZIP RELEASE RULE

When the implementation is complete: package the project cleanly; preserve required root structure; remove forbidden generated artifacts; regenerate required manifests/inventory; ensure manifest consistency; ensure deterministic package identity; run the required tests; run the frozen preflight; inspect the final ZIP itself, not merely the source directory.

The ZIP must be the artifact being certified.

---

## 25. FINAL REPORT FORMAT

For each of the 55 criteria report:

| # | Criterion | Status | Evidence | Defect |
|---|---|---|---|---|

Do not hide unresolved criteria. Do not create artificial defects. Do not downgrade PASS because of personal preferences. Do not upgrade EXTERNAL to PASS without evidence.

---

## 26. DEFECT REPORT FORMAT

For every genuine defect:

**DEFECT**
- Criterion: CXX — [exact criterion]
- Requirement: [exact frozen requirement]
- Location: [file/path/function/line]
- Observed: [actual behavior]
- Expected: [required behavior]
- Evidence: [specific proof]
- Classification: SPEC VIOLATION / IMPLEMENTATION BUG / INTEGRATION BUG / DATA-ARTIFACT BUG / TEST GAP
- Fix: [minimal exact correction]

Nothing else should be called a bug.

---

## 27. OUT-OF-SCOPE FINDINGS

If you notice something that is not required by the frozen criteria, explicitly classify it: OUT OF SCOPE — NOT A BUG. Do not modify the project for it.

Examples: alternative architecture preference; additional security control not specified; additional indicator; additional filter; additional validation; additional database structure; additional logging; additional monitoring; different coding style; different naming preference; industry practice not required by QASWA; hypothetical future improvement.

---

## 28. ANTI-HALLUCINATION RULE

Never claim you inspected something you did not inspect. Never claim a test passed if you did not run it. Never claim a file contains something you did not verify. Never claim production/VPS behavior without production/VPS evidence. Never fabricate data. Never fabricate broker responses. Never fabricate market-data freshness. Never fabricate deployment success.

---

## 29. MOST IMPORTANT RULE

The AI auditor is an acceptance verifier, not a product manager. The AI does NOT get to decide what QASWA "should" be. The frozen criteria decide what QASWA should be. Therefore:

«NO CRITERION VIOLATION = NO BUG.»
«NO EXPLICIT REQUIREMENT = NO MANDATORY CHANGE.»
«NO EVIDENCE = DO NOT CLAIM PASS.»
«EXTERNAL DEPENDENCY = EXTERNAL/DEFERRED, NOT AN INVENTED BUG.»
«DO NOT EXPAND SCOPE.»
«DO NOT ADD NEW REQUIREMENTS.»
«DO NOT REDESIGN FOR PERSONAL PREFERENCE.»

---

## 30. FINAL OBJECTIVE

Build/fix and certify the QASWA project so that it matches the supplied frozen criteria exactly. At completion, another independent AI should be able to inspect the final ZIP against the SAME frozen criteria and reach the SAME criterion-based conclusion.

The desired result is not "Looks good." It is not "95% accurate." It is not "I would improve X." It is: **"55/55 FROZEN CRITERIA SATISFIED."**

If that cannot honestly be established, identify only the exact remaining criterion(s) preventing acceptance. Do not invent anything beyond the frozen specification.

**END OF ORIGINAL FROZEN INSTRUCTION**

---

# PART B — FIELD-TESTED ADDENDUM

The following items were written after actually running Part A through 12+ real
inspection batches on the QASWA zip across releases r7 through r11. Each one
below is here because it caused a real decision that Part A did not clearly
cover — not because a rule was broken. None of these override Part A; all of
them are read as extensions of Sections 1–30, in the same spirit.

## 31. SEVERITY / IMPACT MUST BE STATED, NOT JUST PASS/FAIL

Part A (Section 26) requires Observed/Expected/Evidence/Classification for
every defect, but has no field for how bad it is. In practice this mattered:
one defect found in this project (a DB-read failure silently defeating the
emergency killswitch) was safety-critical; another (naive server-timezone
usage in 4 places) was a real but low-impact inconsistency; a third
(overestimated brokerage in a cost formula) was a real provenance error that
happened to point in the SAFE direction (more conservative, not less).
Treating all three as equally "a FAIL" made it harder to prioritize which to
fix first.

**Add a Severity field to the Section 26 defect format**, using one of these
fixed values only (no free-text severity language, to avoid recreating the
banned vague-scoring problem):
- **CRITICAL** — can cause silent financial loss, a safety mechanism (killswitch, risk limit, compliance gate) to be bypassed, or fabricated/wrong data to drive a real trade decision.
- **MODERATE** — a real, evidenced violation of a frozen criterion that does not by itself cause financial loss or bypass a safety mechanism (e.g. an internal inconsistency, a cosmetic-but-real timezone mismatch).
- **LOW / SAFE-DIRECTION** — a real, evidenced violation whose only effect is to make the system MORE conservative than intended (rejects things it shouldn't, overestimates a cost, under-promises a return) — never a capital-loss or bypass risk.

State the direction explicitly when relevant: "this error makes the system
more cautious than correct" is a materially different fact than "this error
makes the system more permissive than correct," and both are more useful to
the person reading the report than "FAIL" alone.

## 32. REGRESSION-PROOF IS PART OF THE FIXING RULE, NOT OPTIONAL

Section 23 says "run relevant regression tests" and "regenerate manifests if
the package changed" but does not spell out how to prove that a fix touched
*only* what it claimed to touch. In practice, the only way to actually know
that is:

1. Keep the previous release's zip.
2. After applying a fix, diff the full file list of the new zip against the
   previous one — it must be identical (same files, same count).
3. Diff file CONTENTS (not just names) between old and new — the set of
   files that differ must exactly equal the set of files the fix said it
   would touch, no more, no less.
4. Re-run the full test suite and confirm the pass/fail/skip counts are
   unchanged from before the fix (a changed count — even a new pass — means
   something outside the claimed scope moved, and needs explaining before
   the release ships).
5. Re-hash the manifest(s) only for the files that actually changed; leave
   every other file's recorded hash untouched.
6. Re-verify the manifest against the actual delivered zip file, not the
   working directory — a bug in the packaging step itself (wrong exclude
   pattern, stale `__pycache__`, a file silently dropped) is invisible if
   you only check the folder you built it from.

This sequence is what actually makes "Fix ONLY that violation. Do not
redesign unrelated components." (Section 23) verifiable rather than just
asserted.

## 33. WEB-VERIFIABLE PUBLIC FACTS ARE NOT "EXTERNAL/DEFERRED"

Section 13 correctly marks anything needing VPS/broker/live credentials as
EXTERNAL/DEFERRED. But a distinct category exists and was easy to
mis-file into the same bucket: a PUBLICLY PUBLISHED fact (a broker's current
fee schedule, a statutory tax rate, a regulatory threshold) that the project
cites as an "EXTERNAL_FACT" parameter. These are NOT blocked on live
deployment — they can and should be checked now, e.g. via a web search
against the source's own current published page. In this project, exactly
this kind of check caught a real, non-trivial defect (a brokerage rate that
had been wrong since the file was written, not a recent change) that would
otherwise have shipped indefinitely under an unexamined "EXTERNAL_FACT"
label.

**Rule**: before marking any parameter EXTERNAL/DEFERRED, ask whether it is
blocked on *this specific deployment's* live environment, or whether it's
simply a fact about the outside world that a search can confirm right now.
Only the former is genuinely EXTERNAL/DEFERRED under Section 13.

## 34. DISTINGUISH A HISTORICAL RECORD FROM A CURRENT-STATE CLAIM

Section 34-equivalent documentation audits will run into changelogs, decision
logs, and "what we fixed and when" narratives that describe OLD, now-wrong
behavior — correctly, as history. Section 11 says documentation is evidence
but doesn't distinguish these two cases, and treating a changelog entry as
"stale documentation" because it describes a past bug is a false positive.

**Rule**: a documentation line is only a Section-34-type defect if it
describes CURRENT behavior and that description no longer matches the code.
A line that says "as of [date], X used to do Y; we changed it to Z" is
correct historical record-keeping, not staleness, no matter how old X is.
When fixing a genuine current-state staleness issue, do not touch the
historical entries that correctly describe the pre-fix state — that would
itself be introducing an inaccuracy (erasing real history) rather than
removing one.

## 35. WHEN TEST INFRASTRUCTURE CAN'T RUN, BUILD A MINIMAL HARNESS RATHER THAN SKIPPING

Section 12 treats "tests are evidence, not automatic truth" but assumes the
test suite can actually be executed. In an offline/sandboxed environment,
the real test runner (e.g. pytest) or a dependency (e.g. a broker SDK,
scheduler library) may simply not be installable. The correct response is
NOT to fall back to reading the code and asserting a verdict — that
reintroduces exactly the "claims without evidence" problem Section 28
forbids.

**Rule**: build the smallest possible offline substitute (stub the missing
package with a fake module exposing only the same function signatures used
by the target code; write a minimal test-collector if the real framework
isn't available) so the actual test files can genuinely execute and produce
a real pass/fail count. This is more work than reading the code, but it is
the difference between "I verified this" and "I read this and believe it."
Document what was stubbed and why, so a later session knows the test run
was against real logic with faked *external I/O* only, not faked logic.

## 36. WRITE TARGETED FUNCTIONAL PROOFS FOR SPECIFIC CLAIMS, NOT JUST THE EXISTING SUITE

Running the shipped test suite proves what the shipped tests check — no
more. Several real findings in this project (confirming RR resolves to
exactly 1.8 after a refactor; confirming three different ATR implementations
now produce numerically identical output; confirming a killswitch actually
fails closed when the database connection is genuinely broken, not just
when a flag is manually set) required writing a *new*, narrow, throwaway
script that exercises exactly the mechanism in question and prints the
actual number or actual boolean — not inferring the answer from reading the
function body.

**Rule**: for any defect whose fix changes a specific number or a specific
boolean outcome under a specific condition, write and run a small standalone
script that produces that number/outcome directly, under both the normal
condition and (where relevant) the failure condition being defended against
(e.g. actually break the dependency, don't just simulate the flag it would
have set). Prefer genuinely inducing the failure over faking its side
effect — a faked flag can be cleared by unrelated code before the check
runs, as happened once during this session's testing; a genuinely broken
dependency cannot.

## 37. AN AI AUDITING ITS OWN EARLIER CLAIMS MUST BE ALLOWED TO CORRECT THEM

Section 28 (Anti-Hallucination) forbids claiming untested things, but has no
explicit provision for the case where a NEW finding contradicts something
the same audit lineage asserted earlier as verified fact. In this project,
an earlier session validated a specific cost-calculation output as "the
correct number" while rebutting a third party's claim; a later, deeper check
found the underlying rate the calculation used was itself wrong, making the
earlier "correct number" wrong too.

**Rule**: when new evidence contradicts an earlier statement made in the
same audit lineage (this session or a prior one, by this AI or another),
say so plainly, state what the earlier claim was, why it's now known to be
wrong, and what the corrected fact is. Do not quietly supersede it without
flagging the correction — the person relying on the audit trail needs to
know a previously-trusted number has changed, not just see a new number
appear.

## 38. A LIVING CRITERIA TRACKER IS THE PRACTICAL FORM OF SECTIONS 52/55

Sections 52 (Mandatory Final Report) and 55 (Final Instruction to Any AI)
describe the END STATE of an audit, but Part A has no mechanism for an audit
that spans multiple sessions, multiple zip releases, and possibly multiple
different AI models — which is the QASWA project's actual real-world
process (inspect → owner fixes/approves fixes → new zip → re-inspect →
repeat, potentially handed to a different AI at any point).

**Rule**: maintain ONE persistent, updatable 55-row table (matching the
Section 25 format) as a durable artifact, not a one-time report generated
at the end. Every session that touches this project reads that table first,
updates only the rows it actually re-verified, and never restarts numbering
or re-litigates a row marked PASS-with-evidence without new cause. This
table, kept current, IS the practical, ongoing form of Section 52's
"mandatory final report" and Section 55's "final instruction to any AI" —
it removes the need to reconstruct audit state from scratch or from
memory/trust every time work resumes.

## 39. THIRD-PARTY / EXTERNAL AI CLAIMS ARE INPUT, NEVER EVIDENCE

Part A doesn't address a real scenario that came up twice in this project:
a report from an external source (another AI, another tool) describing
alleged defects, with specific file names, line numbers, and formulas. One
such report was almost entirely fabricated (functions and formulas that
don't exist anywhere in the codebase); another was genuinely correct and
led to a real fix.

**Rule**: an external claim — regardless of its confidence, formatting, or
apparent thoroughness — is a HYPOTHESIS to check, never evidence to act on.
Before agreeing with, relaying, or fixing anything an external report
claims, independently re-verify every cited function, line number, and
formula actually exists as described in the actual current codebase. A
report that turns out to be fabricated should be rejected explicitly and
specifically (which claims were checked, what was actually found instead),
not silently ignored — the person who received the external report needs to
know it was wrong and why, not just get a different answer from this audit.

---

*This file supersedes no part of Part A. If Parts A and B ever appear to
conflict, Part A (the frozen specification itself) wins — Part B exists only
to make Part A's own stated intent easier to execute consistently across
sessions and models.*

---

# PART C — ZIP CHANGE / GOVERNANCE RECONCILIATION ADDENDUM

The following sections extend Part A and Part B without overriding them. They make explicit a package-integrity requirement that applies whenever the delivered ZIP changes.

## 40. ZIP CONTENT CHANGE → DEPENDENCY RECONCILIATION RULE

Whenever ANY file, directory, configuration value, dataset, JSON/CSV content, script, test, database artifact, runtime-state artifact, documentation file, deployment file, manifest, inventory, certificate, registration record, truth index, release record, or other shipped artifact inside the QASWA ZIP is added, removed, renamed, modified, regenerated, or materially changed, the AI MUST perform a dependency-impact reconciliation before declaring the resulting ZIP complete.

A ZIP content change MUST NOT be treated as isolated merely because the changed file itself is correct.

### 40.1 Mandatory impact check

For every changed artifact, determine whether any of the following artifacts or records are affected:

- PRD / Product Requirements Document
- QASWA System Blueprint
- Frozen Criteria / Criteria Cross-Reference
- Architecture / design records
- Decision records
- Changelog / release notes
- VERSION / release identity files
- Audit reports / audit scorecards
- Audit inventory
- SHA-256 integrity manifests
- Artifact inventory / registration records
- Registration certificates
- Completion / acceptance certificates
- Canonical Truth Index / Source-of-Truth index
- Deployment / release manifests
- Dependency manifests
- Test evidence / regression records
- Configuration documentation
- Runtime-state documentation
- Any other shipped governance, certification, registration, provenance, or current-state artifact that claims facts about the project

This is an IMPACT CHECK, not an instruction to modify every document.

### 40.2 Update only what is actually affected

If the changed ZIP content makes a governance, documentation, registration, certification, inventory, provenance, version, or current-state artifact inaccurate or incomplete, that artifact MUST be updated.

If it is not affected, DO NOT modify it merely for cosmetic consistency.

The auditor MUST NOT invent documentation changes that are not justified by the actual content change.

### 40.3 Manifest / inventory registration is mandatory

Whenever a shipped artifact is added, removed, renamed, or changed:

1. Update the applicable artifact inventory.
2. Update/recalculate the applicable SHA-256 integrity manifest(s).
3. Update registration/provenance records where applicable.
4. Verify that every required shipped artifact is registered.
5. Verify that no deleted/non-shipped artifact remains falsely registered.
6. Verify file size/hash/path consistency against the ACTUAL FINAL ZIP.
7. Re-run package-integrity verification against the delivered ZIP, not only the working directory.

A file existing inside the ZIP but missing from a required manifest/inventory is a packaging/provenance defect where that manifest's scope requires registration.

### 40.4 PRD / Blueprint / certificate reconciliation

When implementation changes affect behavior, architecture, configuration, criteria coverage, release identity, or any documented current-state claim:

- Cross-check the PRD against the resulting implementation.
- Cross-check the System Blueprint against the resulting implementation.
- Cross-check relevant criteria cross-references.
- Cross-check certificates and registration records.
- Cross-check the Canonical Truth Index.
- Cross-check release/version/changelog records.

If any of these documents claim CURRENT STATE and the claim no longer matches the resulting implementation, this MUST be corrected before release.

Historical records that accurately describe previous behavior MUST NOT be rewritten merely to match the current implementation.

### 40.5 Final-ZIP reconciliation

The FINAL ZIP is the artifact being certified.

Therefore, after all fixes and documentation/registration updates:

1. Build the final ZIP.
2. Extract the final ZIP into a fresh directory.
3. Re-inventory the extracted contents.
4. Recalculate/verify applicable hashes and manifests.
5. Cross-check PRD, Blueprint, Criteria references, certificates, registrations, inventories, truth indexes, release metadata, and other current-state governance artifacts against the extracted final ZIP.
6. Confirm that no stale current-state claim remains.
7. Confirm that no shipped artifact requiring registration is unregistered.
8. Confirm that no registration points to a file/content/version that is no longer delivered.
9. Run the required tests and preflight checks again.
10. Only then issue the release/acceptance verdict.

### 40.6 No shortcut

The following are NOT sufficient by themselves:

- updating the changed source file;
- regenerating only the SHA manifest;
- updating only VERSION.txt;
- updating only the changelog;
- updating only the PRD;
- updating only the Blueprint;
- trusting a previous certificate;
- trusting a previous audit report;
- verifying only the source directory;
- verifying only the ZIP file list.

The final package must be internally coherent across:

**Implementation → Configuration → Data → Tests → PRD → Blueprint → Criteria → Audit Evidence → Inventory → Manifest → Registration/Certificate → Truth Index → Release Identity → FINAL ZIP**

### 40.7 No stale certification

No certificate, registration, acceptance record, audit statement, or release document may be presented as describing the current release if it actually describes an earlier release or earlier implementation state.

If an older certificate is intentionally historical, it must remain identifiable as historical and must not be represented as certification of the current ZIP.

### 40.8 Minimal-change principle

This section does NOT authorize redesign.

The rule is:

**Change the minimum necessary set of dependent artifacts required to keep the delivered package truthful, registered, traceable, and internally consistent.**

If no dependency is affected, no additional file should be modified.

## 41. CHANGE IMPACT RECORD

For every fix that changes shipped ZIP content, maintain a short change-impact record containing:

- Changed artifact(s)
- Exact reason for each change
- Criteria affected
- Dependent governance/documentation artifacts checked
- Artifacts actually updated
- Artifacts explicitly confirmed unaffected
- Manifest/inventory action
- Registration/certificate action, if applicable
- Regression verification performed
- Final-ZIP reconciliation performed

This record is evidence that the AI did not silently modify unrelated artifacts and did not leave dependent artifacts stale.

## 42. RELEASE GATE

A release containing content changes MUST NOT receive a final acceptance verdict until the following are all true:

- The implementation fix itself is verified.
- Relevant regression tests pass.
- Required full verification is rerun.
- Changed-file impact is reconciled.
- Required PRD/Blueprint/current-state documentation is reconciled.
- Required inventories/manifests are regenerated or verified.
- Required registration/certificate records are reconciled.
- Final ZIP is freshly extracted and audited.
- Final ZIP contents match the governance/provenance records.
- No stale current-state claim remains.
- No required shipped artifact is unregistered.
- No unsupported certification claim is present.

**Core rule:**

> **ZIP CONTENT CHANGE → IMPACT CHECK → UPDATE AFFECTED GOVERNANCE/REGISTRATION ARTIFACTS → REGENERATE/VERIFY MANIFESTS → BUILD FINAL ZIP → FRESH EXTRACT → CROSS-CHECK EVERYTHING → TEST → RELEASE VERDICT**

These sections extend the existing QASWA zero-scope-creep, complete-inspection, fixing, ZIP-release, anti-hallucination, and final-acceptance rules. They do NOT override the frozen QASWA specification.

---

# END OF QASWA MASTER INSTRUCTION v2.1
