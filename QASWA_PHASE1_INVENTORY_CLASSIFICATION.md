# QASWA — PHASE 1: COMPLETE FILE INVENTORY + CLASSIFICATION

**Scope of this document:** read-only audit. **Zero files modified, renamed, merged, or deleted.** Base package: `QASWA_v6_0_3-r15_seq-stage-entry-trace.zip` (178 files total: 176 registered in the integrity manifest + 2 self-referential manifest files).

**Method:** every file opened/inspected (title line, purpose statement, or content sample) — classification is evidence-based, not filename-guessed.

---

## A. TOTAL FILE COUNT BY TYPE

| Ext | Count | Category (bulk) |
|---|---:|---|
| .py | 106 | mostly CORE_RUNTIME + REQUIRED_TEST + REQUIRED_DEPLOYMENT |
| .md | 44 | governance-heavy — main consolidation target |
| .json | 8 | mixed: 2 manifests + 1 sequence registry + 1 self-inventory + 4 runtime data files |
| .csv | 6 | 5 runtime data + 1 governance inventory |
| .txt | 5 | mixed |
| .sh | 3 | REQUIRED_DEPLOYMENT |
| .sha256, .service, .ini, .example, .db, .log | 6 | REQUIRED_DEPLOYMENT / CORE_RUNTIME (data) |
| **TOTAL** | **178** | |

---

## B. BULK CLASSIFICATION — RUNTIME / TEST / DEPLOYMENT (unambiguous, not individually schema'd)

These 106 `.py` files plus deployment artifacts are classified in bulk because their category is unambiguous from their role (import graph / test-runner registration / deployment role), not because they weren't inspected — file names, one per line, are in the raw inventory already produced this session (see chat history `find . -type f`).

| Category | Count | Basis |
|---|---:|---|
| CORE_RUNTIME | 85 | All root `.py` files that are imported by `trade_engine.py`, `bot.py`, `stock_selector.py`, `scheduler.py`, or each other, per prior sessions' import-graph audit (Sec 4, batch 20) — zero circular-import issues found, all reachable |
| REQUIRED_TEST | 18 | All `test_*.py` files + `conftest.py` + `pytest.ini`; `test_sequence.py` is the canonical runner (118/0/7 baseline this release) |
| REQUIRED_DEPLOYMENT | 8 | `scripts/*.py` (preflight/refresh utilities), `deploy.sh`, `start_bot.sh`, `freeze_requirements.sh`, `qaswa-bot@.service`, `.env.example`, `requirements.txt`, `requirements-lock.txt` |
| CORE_RUNTIME (data) | 11 | `data/*.csv`, `data/*.json`, `data/trading_bot.db`, `data/*.log` — the actual shipped universe/board/state data. Two are 0-byte by design (`audit_log.txt`, `bot.log`) |

**No ORPHAN or DUPLICATE candidate identified from the dependency, test, deployment and reference evidence examined this pass** (import-graph reachability + `test_sequence.py` registration + prior-session dead-function scans) — this is not a fresh independent re-scan of all 106 files' call graphs; it relies on this project's own repeated prior-session findings (only 2 genuinely dead functions were ever found across the whole history: `clear_network_partition()`, `is_trading_paused()` — both already known/accepted vestigial, zero live impact, out of this cleanup's scope per the master instruction's own Section 14). **NOT PROVEN / NEEDS VERIFICATION** if a fresh independent re-scan is required before Phase 4 treats any `.py` file as a deletion candidate — none currently are.

---

## C. FULL SCHEMA CLASSIFICATION — GOVERNANCE `.md` / `.json` / `.csv` FILES (44 + 4 = 48 files)

This is the actual target of the consolidation project. Each file below is classified per the requested schema. **Proposed action is a recommendation for Phase 2-4 review — nothing has been acted on.**

### C.1 — Root-level `.md` (27 files)

| # | File | Purpose (from content) | Auth/Derived/Ref | Duplicate of / conflicts | Runtime dep | Governance dep | Stale/conflicting | Proposed action |
|---|---|---|---|---|---|---|---|---|
| 1 | `prd.md` | Master PRD — 14-rule Owner Constitution, decisions D1-D26, domains | **AUTHORITATIVE** | — | No | Yes (read_first) | No | KEEP — feeds System Truth |
| 2 | `SYSTEM_BLUEPRINT.md` | System architecture narrative + Section-3 method/creator attribution table | **AUTHORITATIVE** | — | No | Yes | No | KEEP — feeds System Truth |
| 3 | `README.md` | File-index table for humans | REFERENCE | Overlaps prd.md's file list | No | Yes | No (r13-fixed) | KEEP, shrink to pointer in Phase 2 |
| 4 | `AI_ONBOARDING.md` | Mandatory reading order for a new AI | REQUIRED_GOVERNANCE | — | No | Yes (test_sequence.py checks its existence) | No | KEEP — becomes entry-point alongside new System Truth |
| 5 | `VPS_DEPLOYMENT_GUIDE.md` | Deployment/package-layout instructions | REQUIRED_DEPLOYMENT | — | No | No | Not checked this pass | KEEP |
| 6 | `DATA_SOURCE_POLICY.md` | Dhan=trading-data, yfinance=info-only contract | **AUTHORITATIVE** (short, unique) | — | No | Yes | No | KEEP — unique contract, feeds System Truth |
| 7 | `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md` | The 55-section inspection **framework** itself (process definition, not a result) | **AUTHORITATIVE** | — | No | Yes (many docs point to it) | No | KEEP — this is a process-standard, distinct from System Truth (system-facts) |
| 8 | `COMPLETE_ANALYSIS.md` | Old "single source of truth" combined PRD+Blueprint+Inspection | **STALE** (self-marked "HISTORICAL/REFERENCE-ONLY") | Superseded by prd.md + SYSTEM_BLUEPRINT.md + the cert standard | No | No | **Yes, self-declared** | DELETE candidate — self-marked non-authoritative, content already lives in current prd.md/Blueprint |
| 9 | `FINAL_INSPECTION_REPORT_v4.md` | Old inspection report | **STALE** (self-marked "HISTORICAL/REFERENCE-ONLY") | Superseded by current audit docs | No | No | Yes, self-declared | DELETE candidate |
| 10 | `INSPECTION_CHECKLIST.md` | v1 inspection checklist | **STALE** (self-marked "SUPERSEDED") | Superseded by FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md | No | No | Yes, self-declared | DELETE candidate |
| 11 | `INSPECTION_CHECKLIST_v2.md` | v2 inspection checklist | **STALE** (self-marked "SUPERSEDED") | Same as above | No | No | Yes, self-declared | DELETE candidate |
| 12 | `FINAL_MASTER_INSPECTION_CHECKLIST_v3.md` | v3 inspection checklist | **STALE** (self-marked "SUPERSEDED") | Same as above | No | No | Yes, self-declared | DELETE candidate |
| 13 | `AUDIT_PROGRESS_READ_ME_FIRST.md` | Snapshot of state as of r5 (overwritten each pass per its own text) | STALE-BY-DESIGN (says so itself: "reflects CURRENT state only") | Overlaps `docs/CURRENT_INSPECTION_STATUS.md` (which is at r11, this file frozen at r5) | No | Yes, historically | **Yes — two "current status" files disagree (r5 vs r11)** | **CONFLICT — needs Phase-2 resolution, do not silently merge** |
| 14 | `AUDIT_REINSPECTION_REPORT.md` | One dated re-inspection snapshot (2026-08-29) | REFERENCE (point-in-time) | Overlaps later audit reports | No | No | Superseded by later runs, not self-marked | CONSOLIDATE into a single dated audit-history log |
| 15 | `CANONICAL_DOCUMENT_SYNC_REPORT_v1.1.md` | 18-line sync-confirmation note | REFERENCE | Overlaps `docs/CANONICAL_RELEASE_AND_AUDIT_TRUTH_INDEX.md` | No | No | No | CONSOLIDATE (short, foldable into truth index) |
| 16 | `DEFECT_FINDING_REGISTER_v1.1.md` | Table of resolved defect IDs | REQUIRED_GOVERNANCE (evidence) | — | No | Yes | No — but **not updated for r13-r15 findings** | KEEP, flag for update (out of this pass's scope) |
| 17 | `EXTERNAL_CONFIDENCE_SCORECARD_v1.1.md` | Code-confidence vs external-evidence scorecard | REFERENCE | Overlaps `HYBRID_SCORECARD_v1.1.md`, `docs/AUDIT_55_EXECUTION_SCORECARD.md` | No | No | Not verified this pass | **3-way scorecard duplication — Phase-2 decision needed** |
| 18 | `HYBRID_SCORECARD_v1.1.md` | Internal+external combined score table | REFERENCE | Same cluster as #17 | No | No | Not verified this pass | Same as #17 |
| 19 | `LOCAL_TEST_SCORECARD_v1.1.md` | Local test pass-count scorecard | REFERENCE | Overlaps VERSION.txt's own test-result reporting | No | No | **Stale numbers** (says "64 passed... 98 passed, 0 failed, 8 external" — actual current baseline is 118/0/7) | **STALE — numbers contradict current reality, flagged not silently fixed** |
| 20 | `MASTER_AUDIT_EXECUTION_AND_SCORECARD.md` | Points to the cert standard + required reading order | REFERENCE (pointer-only) | Large overlap with `AI_ONBOARDING.md`'s own reading order | No | No | No | CONSOLIDATE |
| 21 | `RELEASE_ARTIFACT_STATUS.md` | 14-line release-status note ("NOT CERTIFIED") | REFERENCE | Overlaps `FINAL_RELEASE_VERDICT_v1.1.md`, `docs/PRE_VPS_ENGINEERING_VERDICT.md` | No | No | Not verified this pass — likely stale (pre-r13) | **Verdict-doc cluster — Phase-2 decision needed** |
| 22 | `FINAL_RELEASE_VERDICT_v1.1.md` | 15-line release-verdict note | REFERENCE | Same cluster as #21 | No | No | Same | Same as #21 |
| 23 | `FRAMEWORK_FREEZE_UPDATE_v1.1.md` | Freeze-date + hash of the cert standard | REQUIRED_GOVERNANCE (integrity evidence) | — | No | Yes | **Hash likely stale** (cert standard has been edited since freeze date per its own change-note) | KEEP, flag hash for regeneration in Phase 4 |
| 24 | `UPDATE_HISTORY_FIX_LOG.md` | Dated fix log across audit rounds | REQUIRED_GOVERNANCE | Overlaps VERSION.txt's own changelog | Yes (`test_sequence.py` checks this file exists) | Yes | Not fully in sync with VERSION.txt r13-r15 entries | KEEP (test-required), flag for sync |
| 25 | `UPDATE_R2_REPORT.md` | Old dated update report (r2) | STALE (superseded by later rounds) | Content absorbed into UPDATE_HISTORY_FIX_LOG.md | No | No | Yes | CONSOLIDATE/DELETE candidate |
| 26 | `UPDATE_V5_REPORT.md` | Old dated update report (v5) | STALE (superseded) | Same as #25 | No | No | Yes | CONSOLIDATE/DELETE candidate |
| 27 | `ZIP_DERIVED_REQUIREMENTS_AND_BLUEPRINT_RULES_v1.1.md` | "ZIP is ground truth" governance rule | REQUIRED_GOVERNANCE (unique rule) | — | No | Yes | No | KEEP |

### C.2 — `docs/` folder `.md` + `.csv` (17 files)

| # | File | Purpose | Auth/Derived/Ref | Duplicate of / conflicts | Runtime dep | Governance dep | Stale/conflicting | Proposed action |
|---|---|---|---|---|---|---|---|---|
| 28 | `docs/MASTER_ZERO_OMISSION_ZIP_INSPECTION_CONSTITUTION_55_SECTIONS.md` | The 55-section checklist itself (backbone) | **AUTHORITATIVE** | — | No | Yes (referenced everywhere) | No | KEEP |
| 29 | `docs/AUDIT_55_EXECUTION_SCORECARD.md` | Current evidence ledger against the 55 sections | **AUTHORITATIVE** (evidence) | Overlaps scorecard cluster (#17/#18) | No | Yes | **Yes — known internal contradiction already found (batch 24: Section 1 says PASS, Section 10 says NOT READY, verbatim-copied stale addendum)** | KEEP but **flag: internal self-contradiction still unresolved from a prior session — carries into System Truth as a known limitation, not silently fixed here** |
| 30 | `docs/CANONICAL_RELEASE_AND_AUDIT_TRUTH_INDEX.md` | Authority-chain pointer document | **AUTHORITATIVE** (pointer) | Overlaps #15 (`CANONICAL_DOCUMENT_SYNC_REPORT_v1.1.md`) | No | Yes | Not verified this pass | KEEP — natural merge target for #15 |
| 31 | `docs/CERTIFICATION_CLOSURE_AND_REINSPECTION_GOVERNANCE_v1.0.md` | CLOSED/REOPENED governance rule | REQUIRED_GOVERNANCE (unique rule) | — | No | Yes | No | KEEP |
| 32 | `docs/CERTIFICATION_CLOSURE_REGISTER.md` | Evidence-linked closure log | REQUIRED_GOVERNANCE (evidence) | — | No | Yes | Not updated for r13-r15 | KEEP, flag for update |
| 33 | `docs/CROSS_ENVIRONMENT_ALIGNMENT.md` | Backtest/Paper/Live parity contract — this is what `alignment_engine.py` actually implements | **AUTHORITATIVE** | — | Yes (`alignment_engine.py`) | Yes | No | KEEP — important: this is the doc that correctly explains why `alignment_engine.py` ≠ SEQ (already confirmed in this session's r14/r15 work) |
| 34 | `docs/CURRENT_INSPECTION_STATUS.md` | Current status as of r11 | REFERENCE (dated snapshot) | **Conflicts with #13** (`AUDIT_PROGRESS_READ_ME_FIRST.md`, frozen at r5) | No | Yes | **Yes — both files claim to be "current status" at different revisions; neither updated for r12-r15** | **CONFLICT — Phase-2 decision: one canonical "current status" pointer, likely folded into System Truth itself** |
| 35 | `docs/DATA_READINESS_AND_REFRESH.md` | "no fabricated data" contract + provider-config requirement | **AUTHORITATIVE** (unique) | — | Yes (`data/decision_data_provider.json`) | Yes | No | KEEP |
| 36 | `docs/FRESH_FULL_55_SECTION_AUDIT_REPORT.md` | One full audit run's report (dated) | REFERENCE (point-in-time) | Overlaps `docs/PRODUCTION_AUDIT_REPORT_55_SECTIONS.md`, `docs/AUDIT_55_EXECUTION_SCORECARD.md` | No | No | Numbers older than current baseline | CONSOLIDATE into audit-history log |
| 37 | `docs/PRODUCTION_AUDIT_REPORT_55_SECTIONS.md` | Older audit report | **STALE, self-marked**: "This report's PASS verdicts were NOT independently verified... and have since been disproven" | Explicitly superseded by #36 | No | No | **Yes, self-declared disproven** | DELETE candidate — file itself says not to trust it |
| 38 | `docs/AI_INSPECTION_TRIGGER_AND_RESULT_CONTRACT_v1.0.md` | One-instruction trigger-phrase contract for a new AI session | REQUIRED_GOVERNANCE (unique, short) | — | No | Yes | No | KEEP |
| 39 | `docs/PRE_VPS_GATE_PROFILE_v1.0.md` | Defines when pre-VPS evidence is required (phase-scope) | REQUIRED_GOVERNANCE (unique rule) | — | No | Yes | No | KEEP |
| 40 | `docs/PRE_VPS_VERIFICATION_GATE_v1.0.md` | Deterministic pre-VPS pass/fail contract for a non-technical owner | REQUIRED_GOVERNANCE (unique) | — | No | Yes | No | KEEP |
| 41 | `docs/PRE_VPS_FINAL_INSPECTION_REPORT_v1.0.md` | One phase-gate evidence report (dated) | REFERENCE (point-in-time) | Overlaps #40's evidence role | No | No | Superseded by later runs (r9-r12 not reflected) | CONSOLIDATE into audit-history log |
| 42 | `docs/PRE_VPS_REINSPECTION_RUN_2026-09-03.md` | One verification-pass record (dated) | REFERENCE (point-in-time) | Same cluster as #41 | No | No | Same | CONSOLIDATE |
| 43 | `docs/PRE_VPS_ENGINEERING_VERDICT.md` | Scope-limited verdict note | REFERENCE | Overlaps verdict cluster (#21/#22) | No | No | Not verified this pass | Same cluster as #21 |
| 44 | `docs/AUDIT_ARTIFACT_INVENTORY.csv` | Machine-readable per-file hash/size inventory | **AUTHORITATIVE** (integrity data) | Overlaps `AUDIT_INTEGRITY_MANIFEST_SHA256.json` + `AUDIT_INVENTORY_SHA256.json` (3-way hash redundancy, already noted r13-r15) | No | Yes | Known pre-existing self-reference quirk (already disclosed r13) | KEEP all 3 — **redundant but each independently machine-checked this session; do not delete without deciding which is canonical (out of scope for a doc-only cleanup — flag for owner decision)** |

### C.3 — Root-level `.json` manifests (4 files, 4 more are runtime data already covered in section B)

| # | File | Purpose | Auth/Derived/Ref | Runtime dep | Governance dep | Stale/conflicting | Proposed action |
|---|---|---|---|---|---|---|---|
| 45 | `SYSTEM_MASTER_MANIFEST.json` | Machine-readable domain/lifecycle registry — **claims "single source of truth"** | **AUTHORITATIVE** | Yes (`test_sequence.py` reads it) | Yes | No | KEEP — becomes the machine-readable layer beneath the new `QASWA_SYSTEM_TRUTH.md`, per the hierarchy agreed this session |
| 46 | `feature_sequence.json` | Stage 0-11 canonical pipeline + SEQ role mapping | **AUTHORITATIVE** | Yes (`test_sequence.py`) | Yes | No | KEEP |
| 47 | `AUDIT_INTEGRITY_MANIFEST_SHA256.json` | Per-file hash manifest (176 files) | **AUTHORITATIVE** (integrity) | No | Yes | No | KEEP |
| 48 | `AUDIT_INVENTORY_SHA256.json` | Second, parallel per-file hash manifest | **AUTHORITATIVE** (integrity) | No | Yes | **YES — genuine, previously-unverified staleness confirmed this pass** | See correction below |
| — | `VERSION.txt` | Full changelog, r2 through r15 | **AUTHORITATIVE** (history) | No | Yes | No | KEEP — canonical change history |

**CORRECTION to row #48 (this section originally, in error, described `AUDIT_INVENTORY_SHA256.json` as a full duplicate of `AUDIT_INTEGRITY_MANIFEST_SHA256.json` without running the actual byte-level comparison). A direct comparison of all three integrity artifacts was performed this pass; corrected finding:**

- `AUDIT_INTEGRITY_MANIFEST_SHA256.json` (#47) and `AUDIT_INVENTORY_SHA256.json` (#48) register the identical 176-file set (key-for-key), but **their `sha256` values agree on all 176 files while their recorded `size`/`size_bytes` values disagree on 15 of them** (`UPDATE_HISTORY_FIX_LOG.md`, `config.py`, `correlation_tracker.py`, `data/audit_log.txt`, `database.py`, `dhan_data.py`, `docs/AUDIT_55_EXECUTION_SCORECARD.md`, `docs/CANONICAL_RELEASE_AND_AUDIT_TRUTH_INDEX.md`, `docs/CERTIFICATION_CLOSURE_REGISTER.md`, `docs/CURRENT_INSPECTION_STATUS.md`, `exit_engine.py`, `market_regime.py`, `strategy.py`, `strategy_tools.py`, `utils.py`).
- For every one of these 15, the **current actual on-disk file matches `AUDIT_INTEGRITY_MANIFEST_SHA256.json`'s recorded size exactly**; `AUDIT_INVENTORY_SHA256.json`'s recorded size is smaller (stale) in all 15 cases, even though its `sha256` value is the current, correct one.
- **Verified pre-existing, not introduced by r13-r15**: the same 15-file size-staleness is already present in the original `claude3.zip` (r12), checked directly against that untouched archive (e.g. `config.py`: r12 `AUDIT_INVENTORY_SHA256.json` records size 77726, actual r12 file size is 78309). None of the 15 files were touched by this session's r13/r14/r15 changes.
- `docs/AUDIT_ARTIFACT_INVENTORY.csv` (#44) shows the **same 15 files with stale size AND stale hash** (i.e. more stale than #48, not less) — plus its own known self-referential row (already disclosed in VERSION.txt r13).
- **Corrected classification: not a duplicate-for-deletion candidate.** This is a **latent integrity-manifest defect** (a `size` field silently going stale independent of a correctly-updated `sha256` field, in two of the three parallel inventories) that predates this cleanup project and was not caught by any prior session's audit. It does not indicate file-content tampering (hashes agree with actual content in #47; #48's hash also agrees, only its size field is wrong) — sizes and hashes must both be re-derived from the current tree in any regeneration, not copy-forwarded.
- **NOT PROVEN / NEEDS VERIFICATION:** whether these three artifacts are meant to be independently-maintained redundant copies (in which case this is a real defect to fix) or whether one is supposed to mechanically derive from another (in which case the derivation step itself is broken). Owner decision required before Phase 4 touches any of the three.

---

## D. CONFLICT / DUPLICATE CLUSTERS IDENTIFIED (Phase-2 decisions needed — NOT resolved here)

1. **"Current status" conflict:** `AUDIT_PROGRESS_READ_ME_FIRST.md` (frozen at r5) vs `docs/CURRENT_INSPECTION_STATUS.md` (frozen at r11) — neither reflects r12-r15. Two files both claiming to be "the current state."
2. **Scorecard cluster (4-way):** `EXTERNAL_CONFIDENCE_SCORECARD_v1.1.md`, `HYBRID_SCORECARD_v1.1.md`, `LOCAL_TEST_SCORECARD_v1.1.md`, `docs/AUDIT_55_EXECUTION_SCORECARD.md` — overlapping purpose, at least one (`LOCAL_TEST_SCORECARD_v1.1.md`) has stale numbers vs current 118/0/7 baseline.
3. **Verdict cluster (3-way):** `RELEASE_ARTIFACT_STATUS.md`, `FINAL_RELEASE_VERDICT_v1.1.md`, `docs/PRE_VPS_ENGINEERING_VERDICT.md` — overlapping "is it certified" claims.
4. **Point-in-time audit-report cluster (5 files):** `AUDIT_REINSPECTION_REPORT.md`, `docs/FRESH_FULL_55_SECTION_AUDIT_REPORT.md`, `docs/PRE_VPS_FINAL_INSPECTION_REPORT_v1.0.md`, `docs/PRE_VPS_REINSPECTION_RUN_2026-09-03.md`, `UPDATE_R2_REPORT.md`/`UPDATE_V5_REPORT.md` — natural candidates for a single chronological audit-history log (not deletion — these are evidence).
5. **Hash-manifest latent defect (3-way, corrected this pass):** all 3 register the same 176-file set, but `AUDIT_INVENTORY_SHA256.json` and `docs/AUDIT_ARTIFACT_INVENTORY.csv` carry stale `size` fields for 15 files (pre-existing since r12, confirmed against the untouched original zip — see correction note in Section C.3). This is **not** a simple "which one do we delete" duplication question; it's a maintenance-integrity defect in whichever process updates #48/#44 that needs a decision on root cause before any consolidation.
6. **Master Prompt canonicalization (new this pass):** no file matching "Master Prompt" / "Master Audit Instruction" exists anywhere inside the shipped ZIP (`grep -rli "master.*prompt\|master.*instruction"` across all `.md`/`.py`/`.txt` returns only one incidental hit — `VERSION.txt`'s own r14 changelog text referring to "Master-Prompt-driven" work, not a file). The actual Master Prompt used to govern this session (`QASWA_FROZEN_CRITERIA_MASTER_INSTRUCTION_v2_1_COMPLETE.md`) was supplied by the owner as a separate upload this session — it is not, and has never been, part of the `claude3.zip` lineage. The closest existing in-ZIP analogues, none of which are the same artifact: `docs/MASTER_ZERO_OMISSION_ZIP_INSPECTION_CONSTITUTION_55_SECTIONS.md` (the 55-section technical-audit framework), `docs/AI_INSPECTION_TRIGGER_AND_RESULT_CONTRACT_v1.0.md` (a short trigger-phrase contract), and `AI_ONBOARDING.md` (reading order). None of these is an AI-operating/governance-consolidation instruction of the kind the current Master Prompt is. **Decision needed for Phase 2:** should the current Master Prompt be canonicalized into the ZIP as `QASWA_MASTER_AUDIT_PROMPT.md` (a new governance artifact — a Phase-2/4 action, not done in this read-only Phase 1)?
6. **Self-marked stale, already disclaimed by the documents themselves (safe DELETE candidates, highest confidence):** `COMPLETE_ANALYSIS.md`, `FINAL_INSPECTION_REPORT_v4.md`, `INSPECTION_CHECKLIST.md`, `INSPECTION_CHECKLIST_v2.md`, `FINAL_MASTER_INSPECTION_CHECKLIST_v3.md`, `docs/PRODUCTION_AUDIT_REPORT_55_SECTIONS.md`.

---

## D.1 — DELETION-CANDIDATE REFERENCE SCAN (self-marked-stale files, verified this pass)

Ran an explicit filename-reference grep (`.py`, `.sh`, `.json`, `.md`, `.ini`, `.service`) for each of the 6 self-marked-stale files proposed for deletion in Section C.1/C.2:

| File | Runtime (`.py`/`.sh`/`.ini`/`.service`) reference | Governance (`.md`/`.json`) reference |
|---|---|---|
| `COMPLETE_ANALYSIS.md` | **NONE found** | Named in `AUDIT_INTEGRITY_MANIFEST_SHA256.json`, `AUDIT_INVENTORY_SHA256.json` (inventory listing, expected), `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md`, `ZIP_DERIVED_REQUIREMENTS_AND_BLUEPRINT_RULES_v1.1.md` (referenced by name as superseded-history) |
| `FINAL_INSPECTION_REPORT_v4.md` | **NONE found** | Same pattern as above |
| `INSPECTION_CHECKLIST.md` | **NONE found** | Same pattern; also named in `INSPECTION_CHECKLIST_v2.md` |
| `INSPECTION_CHECKLIST_v2.md` | **NONE found** | Same pattern; also named in `COMPLETE_ANALYSIS.md`, `AUDIT_PROGRESS_READ_ME_FIRST.md` |
| `FINAL_MASTER_INSPECTION_CHECKLIST_v3.md` | **NONE found** | Same pattern; also named in `AUDIT_REINSPECTION_REPORT.md` |
| `docs/PRODUCTION_AUDIT_REPORT_55_SECTIONS.md` | **NONE found** | Same pattern (inventories only) |

**Finding:** zero runtime/test/deployment dependency confirmed for all 6 (satisfies part of the Section-13 deletion-rule requirement). However, **governance-level name-references DO exist** — several authoritative documents mention these files by name (as superseded-history pointers). This is not itself a reason to keep them, but it means Phase-4 deletion of any of these 6 must **also** update the referencing document's pointer text (or accept a dangling filename reference), and the two hash-manifest inventories must be re-generated to drop the removed entries. **NOT PROVEN / NEEDS VERIFICATION beyond this pass:** whether any of these 6 files' prose contains a uniquely-stated historical fact (a specific number, date, or decision) that is not also recorded in `VERSION.txt`, `UPDATE_HISTORY_FIX_LOG.md`, or the current authoritative docs — a full content diff against those wasn't performed this pass and should precede actual deletion.

---

## E. WHAT WAS **NOT** DONE THIS PASS (by design)

- No file merged, moved, renamed, or deleted.
- No conflict in Section D resolved — each is flagged for explicit Phase-2 review/owner decision, per the master instruction's Section 12 rule ("do not guess which is correct").
- No code file's classification individually schema'd — all 106 `.py` files confirmed reachable/required via the existing import-graph and test-registration evidence already produced in this project's own history; re-litigating that here would duplicate work already done, not add safety.
- No hash/manifest regenerated (nothing changed to regenerate for).

## F. RECOMMENDED NEXT STEP

Review Section D's 6 clusters + Section D.1's reference-scan. Once you confirm which files are safe to fold/point/retire, **Phase 2** (`QASWA_SYSTEM_TRUTH.md`) can begin.

---

## G. PHASE-1 OPEN VERIFICATION ITEMS (must be resolved or explicitly deferred before Phase 4 deletion)

1. **Master Prompt canonicalization** — no Master Prompt file exists in the ZIP at all (Section D.6). Decision needed: canonicalize the owner-supplied Master Prompt into the ZIP as `QASWA_MASTER_AUDIT_PROMPT.md`, and if so, with what authority relation to `SYSTEM_MASTER_MANIFEST.json` / `QASWA_SYSTEM_TRUTH.md` (both are governance-instruction vs. system-fact layers respectively — should not compete).
2. **Hash-manifest latent defect** — `AUDIT_INVENTORY_SHA256.json` and `docs/AUDIT_ARTIFACT_INVENTORY.csv` carry stale `size` fields for 15 files, pre-existing since r12 (Section C.3 correction). Root cause of the staleness (manual edit vs. broken regeneration script) is NOT PROVEN this pass. Needs decision: fix in place, or decide these two are meant to be manually-maintained-independent (in which case the staleness itself is the defect to accept-and-monitor, not fix).
3. **"Current status" conflict** — `AUDIT_PROGRESS_READ_ME_FIRST.md` (frozen r5) vs `docs/CURRENT_INSPECTION_STATUS.md` (frozen r11); neither reflects r12-r15. No resolution attempted (per Master Prompt Section 12 — do not guess).
4. **Scorecard cluster (4-way)** — `EXTERNAL_CONFIDENCE_SCORECARD_v1.1.md`, `HYBRID_SCORECARD_v1.1.md`, `LOCAL_TEST_SCORECARD_v1.1.md` (confirmed stale test-count numbers vs. current 118/0/7), `docs/AUDIT_55_EXECUTION_SCORECARD.md` (confirmed self-contradictory verdict from a prior session, batch 24). Not resolved.
5. **Verdict cluster (3-way)** — `RELEASE_ARTIFACT_STATUS.md`, `FINAL_RELEASE_VERDICT_v1.1.md`, `docs/PRE_VPS_ENGINEERING_VERDICT.md`. Currency of each not individually re-verified this pass. Not resolved.
6. **Historical audit-evidence retention** — 5 point-in-time audit-report files flagged for possible consolidation into one chronological log (Section D.4). No content-uniqueness diff performed yet — must confirm no dated evidence is lost before any consolidation.
7. **Deletion-candidate reference scan** — completed this pass for the 6 highest-confidence candidates (Section D.1): zero runtime/test/deployment reference confirmed; governance-doc name-references DO exist and must be handled at deletion time; a full prose-content-uniqueness diff against current authoritative docs was NOT performed.
8. **`.py` file re-scan scope** — the "no orphan/duplicate" finding for the 106 `.py` files relies on prior-session import-graph/dead-code work, not a fresh independent re-scan this pass (Section B correction). No `.py` file is currently proposed for deletion, so this is lower urgency, but should be explicitly re-run if Phase 4 ever considers a code-file removal.
9. **`DEFECT_FINDING_REGISTER_v1.1.md` / `docs/CERTIFICATION_CLOSURE_REGISTER.md`** — both confirmed not updated for r13-r15 findings/fixes. Out of this pass's scope (doc-content authoring, not classification) but flagged so Phase 2/3 doesn't treat them as currently-complete.
10. **`FRAMEWORK_FREEZE_UPDATE_v1.1.md`'s recorded hash** of the cert standard — likely stale relative to that document's own later change-note, not independently re-verified this pass.

No item in this section has been resolved. Each requires either an explicit owner decision or a dedicated verification pass before Phase 4 acts on it.
