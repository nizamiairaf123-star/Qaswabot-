# QASWA — FINAL MASTER INSPECTION & CERTIFICATION STANDARD (v1.1-CORRECTED — FROZEN)
### 55-Section Backbone + Quality/Defect Gate + Evidence Classification (LOCAL/HYBRID/EXTERNAL) + Regulatory/Compliance Review + Release Verdict

**This file replaces the prior content of `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md` in this project.** The filename is unchanged (so every existing cross-reference in `prd.md`, `SYSTEM_BLUEPRINT.md`, `README.md`, `SYSTEM_MASTER_MANIFEST.json`, and `docs/CANONICAL_RELEASE_AND_AUDIT_TRUTH_INDEX.md` still points correctly to this file) but the *content* is corrected — see change note below.

**FRAMEWORK VERSION: v1.4-FROZEN** (v1.3 plus implementation-registration
note for Layer 2.9 partial-fill and Layer 7/ops dead-man heartbeat — not a
criteria rewrite. See v1.3→v1.4 change note. Replaces v1.3-FROZEN, hash
`ece1a8091cd694fa7ac0159b0205d0c585c87d133f80cdb4b74a829980e4bc1f`)
**Hash of this file at freeze (v1.4, including Appendix A): `fe80ed4da1d0a567d38a817160078f77e863736b85f0704b7f258c727436b0d7` (SHA-256, computed on this file with this hash line blanked — re-verify the same way)**
Any future edit to this document changes its hash and must bump the version
label (v1.1, v2.0, etc.) — silent edits are not permitted. Freezing this
framework is **not** a QASWA certification. QASWA is certified only when a
specific, hashed QASWA ZIP/version has actually been inspected and tested
against this exact frozen framework version, with evidence produced per the
scorecards in Appendix A.

**v1.0 → v1.1 change note:** three contradictions in v1.0 were identified
and corrected before adoption: (1) Layer 5.1's PASS definition referenced
"EXTERNAL item TESTED-PASS or owner-accepted," directly contradicting Layer
3's "EXTERNAL REQUIRED never PASS" — fixed via the release-blocking/
non-blocking classification in 3.4 and a rewritten 5.1. (2) CONDITIONAL and
BLOCKED were under-distinguished — missing mandatory/safety-critical
evidence is now always BLOCKED for the scope claimed, never softened to
CONDITIONAL; CONDITIONAL is now defined strictly as a named, narrower
operating scope (e.g. paper-only). (3) Layer 7's "one market cycle" trigger
is now required to be derived and documented at certification time, not
defined afterward for convenience. Layer 4 also gained an explicit LEGAL
REVIEW REQUIRED status, distinct from EXTERNAL REQUIRED, for items needing
actual legal interpretation.

**v1.1 → v1.2 change note (additions, not corrections — no prior contradiction found):**
(1) Layer 1 gained a mandatory file-to-section mapping / orphan-file check —
every file in `AUDIT_INVENTORY_SHA256.json` must map to at least one of the
55 sections; an unmapped file is itself a finding (enforces existing Section
0 zero-omission intent, not a new inspection area). (2) Layer 2 gained:
2.2 dependency hash-locking, 2.5 portfolio correlation/sector-concentration
invariant, 2.10 audit-log tamper-evidence, and new 2.13 Performance &
Capacity. (3) Layer 5 gained: 5.0 Professional 12-Criteria Decision
Dashboard with priority hierarchy, 5.6 Two-Gate Deployment Rule (VPS
paper-mode vs real-money live are separate, independently-gated
milestones), 5.7 Mandatory Owner Summary Card (a fixed-shape, one-page
plain-language result every inspection must produce). (4) Layer 7 gained
mandatory incident-postmortem discipline for any production P0/P1. None of
this authorizes new product scope — see the frozen-scope rule above; these
are depth-additions within the existing declared scope, requested directly
by the project owner to close specific real gaps.

**v1.2 → v1.3 change note (governance clarification):** added mandatory CLOSED/reopened continuity governance. A CLOSED item is evidence-linked and a later AI/auditor must verify it against current ZIP reality rather than reopen it because of implementation preference. Reopening requires defined contradictory, stale, non-executable, changed, superseded, or new material runtime/data evidence. This prevents audit-methodology drift without suppressing genuine new findings. The detailed rule is canonicalized in `docs/CERTIFICATION_CLOSURE_AND_REINSPECTION_GOVERNANCE_v1.0.md`.

**This supersedes every prior criteria document in this project**, including
`QASWA_CERTIFICATION_FRAMEWORK_v2.md`, the earlier `WORLD_CLASS_BOT_CERTIFICATION_STANDARD.md`
draft, and the older `INSPECTION_CHECKLIST*`, `FINAL_MASTER_INSPECTION_CHECKLIST_v3.md`,
`FINAL_INSPECTION_REPORT_v4.md`, `COMPLETE_ANALYSIS.md` files. Those files should
be marked `SUPERSEDED — see QASWA_NO_KNOWN_CRITICAL_DEFECTS_STANDARD.md` at the
top, not deleted (audit trail).

**Frozen-scope rule:** this document is not to be endlessly expanded. New
criteria are added only when QASWA's own declared scope changes — e.g.
options/futures trading, a new broker, a new payment system, a new
jurisdiction. A finding that only reinforces existing criteria more strongly
gets folded into the relevant existing layer, not appended as a new one.

**No new functionality rule:** this framework is inspection, testing, and
certification only. It never authorizes adding product features. Any
confirmed defect is fixed only after explicit owner approval, and the
affected chain plus a fresh full Layer 1 inspection is re-run after any fix.

**Honest claim, always:** this standard never certifies "100% bug-free."
The only claim it ever produces is:

> *"For release version X / configuration Y, no known P0 or safety-critical
> P1 defect remains open after the Layer 1–3 checks below. Remaining
> EXTERNAL REQUIRED items and lower-severity findings are listed and
> owner-acknowledged."*

---

## LAYER 1 — 55-Section Master Inspection (Backbone, unchanged)

This is `docs/MASTER_ZERO_OMISSION_ZIP_INSPECTION_CONSTITUTION_55_SECTIONS.md`
in full — every file/artifact, data/CSV content, JSON/state, database,
config/numbers, dependencies, Sharia/compliance, liquidity, market data,
strategy mathematics, look-ahead, backtest, optimizer, exit/risk/order,
paper/live separation, scheduler, failure paths, crash/recovery,
Telegram/admin, subscription/copy, deployment, documentation,
version/manifest, security, tests, cross-file wiring, dead code/config, data
pipeline, timezone, state machine, capital, reconciliation, failure
injection, false-pass audit, complete runtime trace, final release audit.
Not restated here — that file remains the one place this checklist lives.

**1.1 File-to-section mapping (orphan-file check):** every file listed in
`AUDIT_INVENTORY_SHA256.json` is mapped to at least one of the 55 sections
before any section is marked complete. A file that cannot be mapped to any
section is itself a finding — it means either the 55-section checklist has
a genuine gap, or the file was never actually inspected. This does not
replace section-by-section inspection; it is a completeness cross-check
run alongside it, specifically to catch the failure mode of a file being
silently skipped while its section is marked PASS.

---

## LAYER 2 — Quality & Defect Gate

**2.1 Derivation rule (governs every requirement below — no exceptions):**
For each check, derive the needed depth/sample size from: (a) worst realistic
consequence if wrong, (b) whether it sits on the accepted-trade path
(universe→compliance→board→liquidity→data→signal→strategy→risk→capital→order→broker→fill→position→exit→reconciliation)
— if yes, it is safety-critical by definition, (c) the strategy's own actual
trade/event frequency and data volume — never a round number borrowed from
another domain. A numeric claim (a percentage, a duration, a trade count)
without its derivation shown is itself a finding, not a valid requirement.

**2.2 Static & structural:** compile/syntax, import graph, dead/duplicate/
conflicting implementations, unsafe broad exceptions and silent
default-success paths, hardcoded secrets, injection/unsafe deserialization
risk — every instance traced to actual behavior, not pattern-matched.
Dependency supply-chain: third-party packages pinned to exact versions
**and** hash-locked (e.g. `pip-compile --generate-hashes`), not just
version-pinned — a version pin alone does not stop a compromised package
republish under the same version/different hash.

**2.3 Automated tests (depth per 2.1):** unit tests for every accepted-
trade-path function (normal/boundary/zero/negative/missing/NaN/exception
cases); integration tests for every hand-off on the accepted-trade path;
end-to-end tests for fresh-install→startup, paper entry→fill→monitor→exit,
restart-mid-trade, daily reconciliation, kill switch, subscription-expiry-
with-open-position.

**2.4 Coverage as diagnostic, not a target number:** used to find untested
accepted-trade-path code; any such line with zero coverage needs a test or a
written justification, regardless of the overall percentage.

**2.5 Property/invariant tests (safety-critical invariants):** quantity never
negative; exposure never exceeds capital; no entry after daily-loss limit;
no trade on missing/stale decision-critical data; exit protection never
loosens/disappears; no duplicate order execution; one subscriber's failure
never affects another; risk parameters never increase without owner
approval; live mode never activates by accident. Portfolio-level
concentration: the live position count/slot limit alone is not sufficient —
sector/correlation concentration is also checked (e.g. all occupied slots
in one sector, or in stocks with historically high mutual correlation,
defeats the diversification the slot limit implies). This extends the
already-open portfolio-drawdown-model finding (FIX-Q) rather than opening a
new area.

**2.6 Independent/differential recalculation:** every accepted-trade-path
formula (fees, sizing, SL/TP, drawdown, returns, Sharpe/Sortino, subscriber
allocation) recalculated independently against real sample data, rounding
tolerance stated up front.

**2.7 State machine & concurrency:** every state/transition enumerated and
adversarially tested — duplicate events, out-of-order events, late broker
response, simultaneous entry/exit, scheduler overlap, two instances, DB
locked mid-write, restart between an API call and its DB save. Pass = no
duplicate trade, no corrupted state, no silent mismatch.

**2.8 Failure-injection:** every mandatory scenario from Layer 1 Section 47
actually triggered wherever the local environment allows, evidence recorded.

**2.9 Broker/order edge cases:** accepted, rejected, partial fill, zero
fill, delayed ack, timeout-but-accepted, duplicate callback, cancel/modify/
exit rejected, gap beyond stop, circuit limits, no counterparty, manual
broker trade, orphan GTT, insufficient funds, invalid security ID,
market-closed/special session — each with a predefined safe action and
evidence.

**2.10 Security & privacy:** secret scan, dependency vulnerability scan,
static security scan, authentication/authorization tests, Telegram
spoofing/replay protection, input validation, encryption/key handling,
least-privilege access, withdrawal permission disabled where applicable,
backup security, log redaction of secrets/PII, session/token revocation.
Zero unresolved Critical/High findings. Audit/decision logs (the trade,
risk, and reconciliation logs specifically) are append-only and
tamper-evident (e.g. hash-chained or write-once) — a log that can be
silently edited after the fact, even by the system's own owner/developer,
cannot serve as evidence for anything in Layer 3 or Layer 5.

**2.11 Regression discipline:** every confirmed fix gets a test that
reproduces the bug (fails before, passes after), the affected chain is
retested, the test stays in the suite permanently. Any fix to core
strategy/risk/order logic invalidates prior paper-trading evidence for that
path — a fresh window is required, sized per 2.1, not resumed.

**2.12 Independent review:** safety-critical modules (risk, order, exit,
reconciliation, compliance gates) get a genuinely separate, adversarial
second pass that doesn't inherit the first pass's assumptions. No finding
dismissed as false-positive without a written reason.

**2.13 Performance & Capacity:** behavior under the system's actual
expected load, not just single-symbol/single-user testing — full universe
scan (current filtered-universe size, per Layer 1 Section 8/16 data, not a
fixed number restated here since the universe size itself is a data value
that changes), maximum concurrent subscribers, maximum concurrent open
positions, broker/data API rate limits under that load. Checked: response
latency for time-sensitive actions (entry/exit signal to order placement),
memory/CPU growth over a realistic multi-day run, and behavior at the
system's stated capacity ceiling (does it fail closed gracefully, or
degrade silently). Depth derived per 2.1 — from the strategy's own
trade/signal frequency and the declared subscriber-capacity target, not a
borrowed number.

---

## LAYER 3 — External Evidence Gate (Reality Check)

**3.1 Two categories only:**
- **TESTED** — an actual run happened, evidence attached (command output,
  log, report). Gets PASS/FAIL/CONDITIONAL.
- **EXTERNAL REQUIRED** — cannot be genuinely proven without the real
  broker, real market hours, real VPS, real network, or real subscriber
  population. Gets EXTERNAL REQUIRED, never PASS, plus a separate
  code-based confidence note. These two fields are never blended into one
  score.

**3.2 Typical EXTERNAL REQUIRED items:** live Dhan API auth/behavior, real
WebSocket feed behavior, real VPS deploy+restart, real network
failure/reconnect, real broker fill/rejection behavior, scheduler timing in
production, real market-data freshness during actual market hours, real
paper-trading execution.

**3.3 Closing rule:** an EXTERNAL REQUIRED item closes only with real
evidence (logs, statements, dated observation) — never by re-reading code
more carefully, never by elapsed time alone. How much evidence is enough is
derived per 2.1 (the strategy's own frequency/data — not a round number),
stated explicitly per item.

**3.4 Release-blocking classification:** every EXTERNAL REQUIRED item is
tagged, at the time it's raised, as either **release-blocking** (a
production/live PASS cannot be issued while this is open — e.g. real broker
fill behavior, real kill-switch trigger) or **non-blocking** (can remain
open with owner acknowledgment without preventing PASS — e.g. a cosmetic
Telegram formatting detail only observable live). An EXTERNAL REQUIRED item
never itself becomes PASS, regardless of tag — closing it means real
evidence was supplied and it moved to TESTED, not that the requirement was
waived.

---

## LAYER 4 — Regulatory & Compliance Review

- [ ] SEBI framing intact: software-sale framing preserved, no stock-name
  disclosure to subscribers where the project's own constitution requires
  this (`PROJECT_CONSTITUTION.md` remains the source rule; this layer checks
  the code/docs actually honor it, doesn't restate it).
- [ ] Sharia compliance gates (Layer 1 Section 15) independently re-affirmed
  as fail-closed with no bypass path found anywhere in the codebase.
- [ ] Subscriber-facing documents/disclosures reviewed for accuracy against
  actual system behavior (no promised feature that isn't wired, no risk
  understated).
- [ ] Data-privacy handling of subscriber/personal data reviewed (storage,
  access, retention) — flagged for owner legal review if anything is unclear;
  this framework does not substitute for actual legal advice.

**4.1 Status rule:** Layer 4 items that require actual legal interpretation
(not just "does the code match the stated rule") are never marked PASS on
the strength of code inspection alone. They are marked **LEGAL REVIEW
REQUIRED** — a distinct status, not a variant of EXTERNAL REQUIRED — and
stay open until a qualified legal review actually happens. A LEGAL REVIEW
REQUIRED item bearing on the operating scope being certified blocks PASS
for that scope per Layer 5.1.

---

## LAYER 5 — Release Certification (Final Decision)

**5.0 Professional Decision Dashboard (12 criteria — a summary lens over
Layers 1–4, not a duplicate of them):** a genuinely experienced software
engineer + systematic/quant trader judges a production trading system
across these 12 areas. Each maps to specific Layer 1–4 sections; detail
lives there, tthing is unclear;
  this framework does not substitute for actual legal advice.

**4.1 Status rule:** Layer 4 items that require actual legal interpretation
(not just "does the code match the stated rule") are never marked PASS on
the strength of code inspection alone. They are marked **LEGAL REVIEW
REQUIRED** — a distinct status, not a variant of EXTERNAL REQUIRED — and
stay open until a qualified legal review actually happens. A LEGAL REVIEW
REQUIRED item bearing on the operating scope being certified blocks PASS
for that scope per Layer 5.1.

---

## LAYER 5 — Release Certification (Final Decision)

**5.0 Professional Decision Dashboard (12 criteria — a summary lens over
Layers 1–4, not a duplicate of them):** a genuinely experienced software
engineer + systematic/quant trader judges a production trading system
across these 12 areas. Each maps to specific Layer 1–4 sections; detail
lives there, this is the executive view.

| # | Criterion | Primarily assessed in |
|---|---|---|
| 1 | Functional Correctness — does it do what spec says | Layer 1 (all sections) |
| 2 | Strategy/Quant Correctness — math, signal logic, backtest methodology, overfitting/look-ahead | Layer 1 §18-21, Layer 2.6 |
| 3 | Risk Correctness — sizing, exposure, loss limits, SL/TP, capital protection | Layer 1 risk sections, Layer 2.5 |
| 4 | Execution Correctness — order lifecycle, fills, rejections, partial fills, duplicates | Layer 2.7, 2.9 |
| 5 | Data Integrity — market data, freshness, missing/stale/corrupt data, universe | Layer 1 §8,10,16,17 |
| 6 | State & Recovery Integrity — restart, crash, persistence, reconciliation, state-machine | Layer 2.7 |
| 7 | Reliability & Fault Tolerance — network, broker/API, scheduler, timeout, dependency failures | Layer 2.8 |
| 8 | Security — credentials, permissions, authentication, secrets, isolation | Layer 2.10 |
| 9 | Performance & Capacity — latency, throughput, resource usage, concurrency, scaling | Layer 2.13 |
| 10 | Operational Readiness — deployment, monitoring, alerting, backups, rollback, kill switch | Layer 1 §monitoring/DR, Layer 7 |
| 11 | Compliance & Governance — Sharia rules, regulatory constraints, audit trail, change control | Layer 4 |
| 12 | Real-World Evidence — paper/live execution, broker/VPS/market validation | Layer 3 |

**Professional decision rule — no averaging, ever:** a verdict is never
computed by averaging or weighting these 12 areas into one score. Any
single critical failure in #3 (Risk), #4 (Execution), #6 (Recovery), or
#12 (Evidence) overrides an otherwise-clean scorecard. Decision priority
order:

> **Correctness → Risk → Execution → Recovery → Evidence → Operational
> Readiness → Release**

An 11-of-12 "excellent" scorecard with one critical reconciliation failure
is BLOCKED, not "92% ready." A system with excellent code and excellent
backtests but untested real-broker execution is not approved for live
deployment, regardless of how the other 11 areas score.

**5.1 Verdicts (only these three) — scoped to a named operating scope
(e.g. "full production/live" vs "paper-trading-only") stated explicitly in
every verdict:**
- 🟢 **PASS** — for the named scope: Layer 1 complete, zero open P0, zero
  open safety-critical P1, Layer 2 complete for the accepted-trade path,
  every release-blocking Layer 3 item (per 3.4) actually closed as TESTED
  with real evidence, and Layer 4 has no open LEGAL REVIEW REQUIRED item
  bearing on that scope. Non-blocking EXTERNAL REQUIRED items may remain
  open with owner acknowledgment — they are listed, not hidden, but they do
  not themselves carry a PASS status.
- 🟡 **CONDITIONAL** — a **restricted, explicitly named, narrower operating
  scope** than full production is certified (e.g. paper-trading-only, or a
  reduced-capital staged-live scope), with the exact limitations that keep
  it out of full-production PASS listed by ID. CONDITIONAL is never used to
  paper over missing mandatory evidence for the scope actually being
  claimed — if the claim is "ready for live," and live-relevant mandatory
  evidence is missing, that is BLOCKED, not CONDITIONAL, regardless of how
  confident the code review is.
- 🔴 **BLOCKED** — for the scope being claimed: any open P0, any open
  safety-critical P1, any Layer 1/2 area not yet inspected, any
  release-blocking Layer 3 item still open, or any Layer 4 item marked
  LEGAL REVIEW REQUIRED that bears on that scope. High code-based
  confidence never substitutes for closing these.

**5.2 Severity scale (shared across all layers):**
- **P0 catastrophic:** unlimited/wrong order quantity, kill switch failure,
  wrong account/side, duplicate live orders, loss-limit bypass, exposed
  credentials, ignored broker mismatch. Zero tolerance, no risk acceptance.
- **P1 high:** wrong fee/sizing/exit calc, unreliable recovery, mishandled
  partial fills, unverified critical-data freshness, reconciliation failure.
  Safety-related P1 must be zero for PASS.
- **P2 medium:** no direct financial/security risk, workaround exists, owner
  accepts in writing with a fix deadline.
- **P3 low:** documentation/UI/minor inconvenience, backlog is fine.

**5.3 Version/hash-based certification:** every PASS or CONDITIONAL verdict
is bound to an exact, frozen release identity — version string, file
inventory, and a checksum/hash of the certified ZIP — recorded together.
A single file change (even one line) invalidates that specific
certification; re-certification (not a full restart from Section 1 unless
the change is broad) is required, scoped to the affected chain.

**5.4 Mandatory report content:** what was inspected section-by-section
(not a single "done" flag); which exact criterion was used per judgment;
what was tested vs. only reasoned about; the EXTERNAL REQUIRED list with
reasons; code-based confidence kept separate from test evidence; every
defect (ID/severity/location/fix status/verification); every contradiction/
duplicate/dead implementation and its resolution; the final verdict with
cited reasons; and an explicit diff from the previous report (new findings,
closed findings, regressions — nothing silently dropped).

**5.5 Forbidden language:** "100% bug-free," "fully tested," "production
ready," "verified clean" — never unqualified. Use the honest claim at the
top of this document instead.

**5.6 Two-Gate Deployment Rule:** "deployable" is not one milestone — it is
two, independently gated, so the non-technical owner has one clear,
achievable finish line for starting deployment without being told (falsely)
that nothing will ever need to change again.

- **GATE 1 — VPS deploy, paper mode (fake money, real broker/data
  connection):** clears when the LOCAL Test Scorecard (Appendix A.1) has
  zero open rows for anything that was actually testable without a VPS —
  every applicable local test PASS, zero open P0, zero open safety-critical
  P1 among locally-testable items. HYBRID and EXTERNAL scorecards are not
  required to be closed for Gate 1 — they cannot be, without a VPS, and
  waiting for them here would be a category error, not rigor.
- **GATE 2 — real-money live trading:** clears only after Gate 1 has been
  running on the VPS in paper mode and the release-blocking EXTERNAL items
  (per 3.4) are closed as TESTED with real evidence gathered from that
  paper-mode run.
- Passing Gate 1 is a legitimate starting point, not a temporary or
  provisional state to be embarrassed about. Ordinary post-Gate-1 changes
  (bug fixes, evidence collection, minor tuning) are expected and are not a
  sign the process failed — see Layer 7. What Gate 1 guarantees is that no
  *known* critical defect was shipped; it was never meant to guarantee that
  nothing will ever need attention again.

**5.7 Mandatory Owner Summary Card:** every inspection report — regardless
of who or what AI produces it — must lead with this fixed-shape,
one-page, plain-language card before any detailed scorecards. This is what
the non-technical owner reads first and re-reads before deciding to
deploy; the detailed Appendix A scorecards remain available behind it for
anyone who wants to verify the claims.

```
═══════════════════════════════════════════
  QASWA INSPECTION RESULT
═══════════════════════════════════════════
ZIP inspected:       <filename>
ZIP hash:             <sha256>
Framework used:       <this file's name + hash>
Date:                 <date>

───────────────────────────────────────────
  OVERALL VERDICT:  🟢 PASS / 🟡 CONDITIONAL / 🔴 BLOCKED
───────────────────────────────────────────

GATE 1 — VPS Paper-Mode Deploy:   ✅ CLEARED / ❌ NOT CLEARED
GATE 2 — Real-Money Live:         ✅ CLEARED / ❌ NOT CLEARED

───────────────────────────────────────────
  ISME AAPKE LIYE MATLAB:
  <one plain sentence, no jargon>
───────────────────────────────────────────

Open CRITICAL issues (P0/P1):        <count>
  → if >0: <name, one line each>
Open non-critical issues (P2/P3):    <count>
VPS-only pending items (external):   <count>

───────────────────────────────────────────
  BOTTOM LINE:  [ Deploy karo / Mat karo /
                  Ye fix hone ka wait karo ]
───────────────────────────────────────────
```

A report missing this card, for any inspection pass claiming any of the
three verdicts, is itself non-compliant with this framework — regardless of
how thorough the underlying detail is.

---

## LAYER 5.8 — CLOSED / REOPENED GOVERNANCE (MANDATORY)

This layer preserves evidence-linked audit continuity across AI/auditor handoffs without preventing independent verification or discovery of real defects.

**Receiving-AI rule:** inspect the relevant current ZIP implementation at code/data level and independently evaluate it against the locked criterion. A prior CLOSED result is evidence to verify, not a command to copy. If the logic still satisfies the criterion and the evidence is valid, the receiving AI issues its own **PASS/CLOSED** result. If actual contradictory evidence or a real defect exists, it issues its own **FAIL/REOPENED** result with evidence.

**Do not reopen for implementation preference:** a different architecture, library, naming convention, refactor, or audit style is not a defect when the locked criterion is already satisfied.

**Reopen only on evidence:** false/stale/non-executable/contradictory evidence; changed implementation or affected safety-critical chain; higher-authority requirement conflict; or new material runtime/data evidence demonstrating a real gap.

Genuinely new independent risks remain reportable and follow the existing section mapping or S56+ gate where applicable. Detailed state/evidence rules: `docs/CERTIFICATION_CLOSURE_AND_REINSPECTION_GOVERNANCE_v1.0.md`.

---

## LAYER 6 — Owner Governance (this is your job, non-technical is fine)

You do not need to read code. You need to ask these and refuse vague
answers.

**Before accepting any "audit/inspection complete" claim, ask:**
- "Kitne Layer-1 sections deeply verified hain, kitne sirf table-row/shallow
  pass hain?" — reject an answer that conflates the two.
- "Konse P0/P1 abhi open hain?" — there must be a specific list.
- "Ye claim run karke dikhao" — for any "tests pass," ask for the actual
  command output.

**Before accepting any "bot is ready" claim, ask:**
- "Layer 3 EXTERNAL REQUIRED list mein kya-kya abhi bhi open hai?"
- "Worst-case ek din ka maximum possible loss kya hai?" — must be a specific
  number, not "low risk."
- "Emergency stop kaise kaam karta hai, aur kya wo actually test hua hai?"
- "Iss paper/live evidence ka sample size kis calculation se aaya — 2.1 ke
  hisaab se derive hua hai, ya ek guessed round number hai?"

**Red flags — pause and demand proof if you hear:**
- "Sab sahi hai" / "production ready" with no findings list attached.
- A new report that doesn't mention previously-open issues at all (silently
  dropped ≠ fixed).
- "Tests passed" without showing which, how many, what failed/skipped.
- Any claim that data was "filled in" without naming the real source.
- A filename/title claiming completeness ("FULL," "FINAL," "CERTIFIED")
  without a dated, itemized report matching that exact claim.
- Any fixed-percentage or fixed-duration requirement (e.g. "90% coverage,"
  "30 trades," "72-hour soak") presented without its 2.1 derivation shown.

**Sign-off:** before scaling from paper→staged-live→full-live, you should be
able to answer the Layer 5.4 questions yourself, from memory, without asking
the auditor again.

---

## LAYER 7 — Post-Launch Monitoring & Recertification

A PASS is a snapshot of one frozen version/hash (5.3) — not a permanent
state. Ongoing obligations after launch:
- [ ] Routine log/reconciliation review at a cadence the owner and auditor
  agree fits the strategy's own trading frequency (not a borrowed number).
- [ ] Board/Sharia and liquidity data refresh freshness re-confirmed on the
  schedule the system itself defines (Layer 1 Section 10/16), not assumed.
- [ ] Kill-switch and recovery drills actually re-triggered periodically —
  frequency derived the same way (2.1), not fixed generically.
- [ ] Any production P0 or safety-critical P1 gets a written postmortem
  before being closed — what happened, root cause (not just the symptom
  fixed), why local/paper testing didn't catch it, and what changed in the
  process (test, invariant, or check) so the same class of defect is
  caught pre-deployment next time. This is a short, mandatory record, not
  a new test suite — it feeds the decision log below and is what turns a
  post-launch surprise into a permanent process improvement instead of a
  one-off patch.
- [ ] A running, dated decision log of every owner-approved change/accepted
  risk — this is the audit trail for whoever touches the project next.

**Mandatory full recertification (fresh Layer 1–5 pass, not a partial patch)
triggers on any of:**
- Any change to core strategy/risk/order/exit logic.
- Any change to the declared trading scope (new instrument type, new
  broker, new payment system, new jurisdiction) — this is also the only
  trigger for adding new criteria to this document itself (frozen-scope
  rule above).
- Any P0 found in production.
- A gap longer than one full market cycle since the last certification.
  "One market cycle" must be derived from the system's own decision-critical
  data refresh/change cycle (Layer 1 Section 10/16 — e.g. board/Sharia
  refresh interval, liquidity recalculation interval) and **documented at
  certification time, before the gap is measured** — it may not be defined
  or redefined afterward to conveniently extend a certification's validity.

---

## THE NINE QUESTIONS
Any AI or auditor handed only the ZIP and this standard must answer all
nine, explicitly, per section, before a verdict is accepted:

1. Kya inspect kiya? (exact scope)
2. Kis criterion se? (cite the exact layer/section)
3. Kya actually test hua? (evidence attached)
4. Kya test nahi ho saka? (named, with reason)
5. Code-based confidence kya hai external item ka? (kept separate from real evidence)
6. Kya defect mila? (ID, severity, location)
7. Fix zaroori hai ya current implementation acceptable? (explicit call)
8. Koi contradiction/duplicate/dead implementation mila?
9. Final verdict kya hai aur kyun? (PASS/CONDITIONAL/BLOCKED, cited)

An answer that skips any of these nine, for any section claimed complete,
means that section is not actually certified — no matter what the report's
headline says.

---

## APPENDIX A — Frozen Execution Rules & Mandatory Scorecards

**Authoritative hierarchy for every inspection pass:**
> 55-Section Master Inspection (with 1.1 file-to-section mapping) →
> Quality/Defect Gate → Evidence Classification (LOCAL/HYBRID/EXTERNAL) →
> Regulatory/Compliance Review → 12-Criteria Decision Dashboard (5.0) →
> Release Verdict (Two-Gate scoped, 5.6) → Owner Summary Card (5.7)

**Frozen execution rules (apply to every pass, no exceptions):**
1. Anything locally verifiable is actually inspected/tested — evidence recorded, not assumed.
2. Anything that cannot execute in the local environment is classified EXTERNAL — never silently skipped.
3. An EXTERNAL item's code-based confidence is always kept separate from real proof.
4. A check that is part-local, part-external is HYBRID — never a full PASS.
5. A failed mandatory test is FAIL/BLOCKED — never downgraded.
6. A test that was never executed is never marked PASS.
7. A correctly implemented item gets NO CHANGE REQUIRED — not silence, not a rewrite.
8. A confirmed defect follows: FIX → regression test → affected-chain retest → updated evidence.
9. Inspection never becomes an excuse to add features or refactor beyond the fix itself.
10. Every threshold has a documented source, derivation, unit, assumption, and consumer.
11. If a derivation isn't available, the value is UNKNOWN/NOT DERIVABLE — never invented.
12. Historical evidence is preserved for audit trail; only one current authoritative standard exists at a time.
13. "100% bug-free" is never claimed.
14. Freezing/adopting this framework is never itself reported as a product certification.
15. A file present in the inventory but mapped to no section (per 1.1) is a finding, not a silent omission.
16. The Owner Summary Card (5.7) is never omitted, and never overstates a scorecard number into a plain-language claim the underlying data doesn't support.
17. CLOSED + valid evidence is verified, not reinvented. Reopen only under Layer 5.8 triggers; implementation preference is not a defect.

**Six mandatory outputs for any inspection pass (replace narrative-only reporting) — A.0 always comes first:**

### A.0 Owner Summary Card (mandatory, see 5.7 for the exact template)
The fixed-shape one-page card — verdict, both Gate statuses, plain-language
meaning, critical-issue count, bottom line. Every other output below exists
to support and evidence what this card claims.

### A.1 LOCAL Test Scorecard
| Test ID | Section | Command/Procedure | Expected | Actual | PASS/FAIL | Evidence | Date/Version |

### A.2 HYBRID Scorecard
| Item | Locally-verified portion | External dependency | Local result | Remaining uncertainty | Required external procedure | Status (partial/conditional) |

### A.3 EXTERNAL Confidence Scorecard
| System/Service | Relevant code/wiring | Failure-path assessment | Code-based confidence | Why this isn't proof | Exact external test required | Release-blocking? |

### A.4 Defect/Finding Register
| Finding ID | Section/Requirement | File/Function | Description & Impact | Severity | Evidence class | FIX / NO CHANGE REQUIRED / EXTERNAL TEST REQUIRED / LEGAL REVIEW REQUIRED | Fix status | Regression/retest result | Owner decision |

### A.5 Final Release Verdict
🟢 PASS / 🟡 CONDITIONAL / 🔴 BLOCKED — with named operating scope, Gate 1/Gate 2
status, exact reasons, unresolved findings, and external/legal limitations
listed.

**Standard operating sequence going forward:**
> Identify frozen framework version/hash → freeze/hash the QASWA ZIP under
> test → run the file-to-section mapping (1.1) → execute inspection →
> produce all scorecards (A.0-A.5) → fix/regression-test confirmed defects
> → complete release-blocking external evidence → issue final verdict with
> named scope and Gate status.
