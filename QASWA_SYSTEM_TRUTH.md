# QASWA_SYSTEM_TRUTH.md

**Status: canonical human-readable narrative/index. This document does NOT compete with or replace `SYSTEM_MASTER_MANIFEST.json` (machine-readable authoritative registry/metadata layer), and it can NEVER override actual source code, configs, tests, runtime data, or the integrity manifests. Where this document and implementation evidence disagree, implementation evidence wins — treat any such conflict as a bug in this document, not in the code.**

Authority hierarchy:
```
SYSTEM_MASTER_MANIFEST.json  →  machine-readable authoritative registry/metadata/integrity layer
QASWA_SYSTEM_TRUTH.md        →  human-readable canonical narrative/index (THIS FILE)
Source code / configs / tests / runtime data  →  implementation truth/evidence (final authority)
```

Base evidence: `QASWA_v6_0_3-r15_seq-stage-entry-trace.zip`, cross-checked against `QASWA_PHASE1_INVENTORY_CLASSIFICATION.md`.

---

## 1. Identity, Owner, QASWA Remix

- **QASWA** ("Qaswabot"/"Contabu") — a Halal algorithmic trading bot for NSE equities. *(Evidence: `prd.md`, `README.md` both reference "NSE"; BSE-handling capability in code and the NSE-only status of the current shipped universe are documented in §6, not repeated here.)*
- **Owner:** AIRAF NIZAMI. *(Evidence: `prd.md` header, `SYSTEM_MASTER_MANIFEST.json`)*
- **QASWA Remix** — the combined architecture identity registered in `prd.md` Rule 14: "QASWA Remix → AIRAF NIZAMI." Ownership scope covers the combined architecture/integration (the two mandatory gates + SEQ alignment + implementation) only — underlying genuine external methodologies (see §8) keep their own separate attribution; the two ownership levels are never merged. *(Evidence: `prd.md` Rule 14, `SYSTEM_BLUEPRINT.md` intro cross-reference, `SYSTEM_MASTER_MANIFEST.json` owner_constitution entry)*

## 2. Owner Constitution / Governing Principles

`prd.md`'s "OWNER CONSTITUTION" — **16 rules, never changes silently.** Selected rules most relevant to system behavior (not a full restatement — see `prd.md` for exact text):
- Rule 2: Business Halal Filter — mandatory.
- Rule 3: Non-Muslim Board of Directors Filter — mandatory.
- Rule 6: zero hardcoded numbers without a documented source (drives §8's attribution requirement).
- Rule 7: trade only optimization-proven edge, else block (drives §9's robustness principle).
- Rule 14: QASWA Remix / SEQ architecture identity (added 2026-09-07, r13 work).
- Rule 15: NIZAMI Data Segregation & Accumulation Protocol / NDSAP (refined 2026-09-13, r25-27 work — Part C implemented).
- Rule 16: Decision & Market-Context Telemetry / "Black Box" (added 2026-09-15, r30 — implemented; PIT-guarded replay reads at r31; owner-side audit alias "PIT Telemetry" = this same capability; NEW Rule 16, unrelated to the old Rule 16 deleted 2026-09-13).
*(Evidence: `prd.md` §2, "OWNER CONSTITUTION (kabhi nahi badalta — 16 rules)")*

## 3-4. QASWA Remix Architecture and Gate Ordering

Mandatory hard-gate order, non-negotiable:

```
Business Halal Filter  →  Non-Muslim Board of Directors Filter  →  SEQ  →  Trade Decision/Execution
     (Rule 2)                    (Rule 3)                    (Rule 14)
```

- **Layer 1 — Business Halal Filter (mandatory hard gate).** Evidence: `stock_selector.py::_row_is_halal_eligible()` evaluates `core_business_halal` first.
- **Layer 2 — Non-Muslim Board of Directors Filter (mandatory hard gate).** Same function evaluates `non_muslim_board` immediately after Layer 1. Both are fail-closed (a missing/ambiguous value blocks, does not default to eligible).
- **Structural enforcement on the inspected market-scan path (not a whole-codebase bypass-impossibility claim):** `trade_engine.run_market_scan()` obtains its symbol list via `stock_selector.get_tradeable_universe()`, which returns `load_halal_symbols()`. On this specific, traced call path, the function returns only symbols that have already passed both gates, and `run_market_scan()`'s downstream signal/optimization/risk/execution logic does not re-fetch or substitute a different, unfiltered symbol source. This has been verified for the `run_market_scan()` entry path only — it is **not** a claim that every code path in the entire codebase (e.g. any diagnostic/manual/admin script that might independently query the broker or another data source) is provably incapable of bypassing the gates; no such exhaustive whole-codebase scan was performed. *(Evidence: `trade_engine.py` `symbols = get_tradeable_universe()`; `stock_selector.py::get_tradeable_universe()`)*
- **Layer 3 — SEQ.** See §5.
- **Existing QASWA trading process.** Everything downstream of the gates (§7-§15).

## 5. SEQ — What It Is and Is Not

- SEQ = QASWA's **internal shorthand** for the "Systematic/Quantitative Best-Practice Alignment Layer" (Rule 14, `prd.md`). It is **not** a claimed pre-existing official external methodology, and it is **not** an additional trade-veto gate with its own decision/blocking logic.
- SEQ's role: aligning QASWA's *existing* components (universe/eligibility, market & data context, signal/strategy research, optimization, validation, risk/capital, execution, exit, reconciliation) to their correct methodological role — a labeling/organizing concept over already-correctly-sequenced existing code, not new logic.
- Implementation: `seq_alignment_registry.py` — a declarative, read-only registry (hard-gate order + a mapping of `feature_sequence.json` Stage 0-11 to SEQ methodological roles). Contains zero `if`/`allow`/`block` statements.
- Runtime wiring (traceability, not enforcement): `startup_recovery.run_startup_recovery()` logs a one-time SEQ registry trace at boot; `trade_engine.run_market_scan()` logs a per-scan `SEQ_STAGE_ENTRY` line immediately after `get_tradeable_universe()` confirming how many symbols entered SEQ-stage processing. Both trace calls are observational/non-blocking and add zero new decision logic — **the trace mechanism itself is fail-open** (a failure in the logging call is caught and does not stop the scan/boot), but this fail-open handling applies only to the trace/logging call, not to the underlying Halal/Board eligibility decision. The eligibility gates themselves (`_row_is_halal_eligible`, `is_universe_data_stale`) remain fail-closed as documented in §6/§3-4; a trace-logging failure cannot change or weaken that eligibility decision. *(Evidence: `startup_recovery.py`, `trade_engine.py`, functional proof recorded in `VERSION.txt` r14/r15 entries — real `data/audit_log.txt` writes confirmed this session)*
- **Naming-collision note (deliberately documented to avoid future confusion):** this "SEQ" is unrelated to the pre-existing "SEQ_FILE"/"SEQ MATCH" shorthand already used elsewhere in this codebase (`test_sequence.py`, `SYSTEM_MASTER_MANIFEST.json` domain 1) as an abbreviation for "SEQUENCE" (i.e., `feature_sequence.json`). Coincidental namesake, different meaning, both real usages coexist in the codebase.
- **`alignment_engine.py` is NOT the SEQ layer.** It is a Backtest ↔ Paper ↔ Live *performance-parity* monitor (see `docs/CROSS_ENVIRONMENT_ALIGNMENT.md` for its actual contract) — confirmed unrelated during this session's r14 investigation.
- Genuine external methodologies used within SEQ-stage components keep their own real attribution (§8) — SEQ itself does not claim to be their creator.

## 6. Sharia / Custom Universe Rules

- Universe source: `data/CUSTOM_UNIVERSE_FINAL.csv` — 1,057 data rows, directly verified this pass via CSV-aware parse (Python `csv.reader`, header row excluded) — not a raw `wc -l` count. All 1,057 rows have `exchange = NSE`; no BSE row is present in this file. Code elsewhere contains BSE-handling logic (`dhan_data.py` line 26: `if exchange == "BSE":`; `correlation_tracker.py` line 185: BSE_CURRENCY segment handling) — this capability exists in code but is not exercised by the current shipped universe, which is NSE-only.
- Supporting eligibility data files: `data/BOARD_TRUE_100_NON_MUSLIM.csv`, `data/BOARD_FALSE_HAS_MUSLIM.csv`, `data/MASTER_STOCK_LIST_PERMANENT.csv`, `data/lm_finance_wordlists.csv`.
- Eligibility check: `stock_selector.py::_row_is_halal_eligible()` — `core_business_halal` AND `non_muslim_board` both required True; fail-closed on missing/ambiguous data (confirmed in prior-session audits, not re-verified line-by-line this pass — see Phase 1 report §B for what was and wasn't freshly re-scanned).
- Purification/AAOIFI-style profit-purification mechanism: **removed** per an explicit prior owner decision (r4 era, per project history recorded in earlier session memory — not independently re-verified against this exact ZIP this pass). **NOT PROVEN this pass** — should be confirmed against current `stock_selector.py`/`config.py` if this fact is relied upon.
- Data-currency gate: `stock_selector.py::is_universe_data_stale()` — if board/universe data is stale, `get_tradeable_universe()` fails closed (returns empty), confirmed via this session's own functional test (`BOARD_DATA_STALE_PAUSE=True` observed live in the shipped snapshot, correctly triggering the empty-list fail-closed path).

## 7. Data Sources, Flow, Storage

Per `DATA_SOURCE_POLICY.md` (owner-approved, treated as authoritative):
- **Dhan** = mandatory, single source of truth for all trading data: instrument mapping, OHLCV, volume, indicators, signals, backtest, optimization, simulation, paper, live, orders, fills, positions, reconciliation.
- **yfinance** = information-only: sector/industry/market-cap/business-description inputs to the Halal filter, and board/director information. Must never supply OHLCV/price/volume to any trading/strategy path.
- If Dhan data is missing/stale/invalid, the affected calculation/trade is blocked — yfinance never silently substitutes.
- Liquidity ATVR/FoT computed by QASWA from Dhan historical price/volume + yfinance market-cap.
- Enforcement regression named in the policy doc itself: `test_data_source_policy.py` (existence not independently re-opened this pass; taken as REQUIRED_TEST per Phase 1's bulk classification).
- **Storage:** state has been migrated from flat JSON into a single SQLite `key_value_store` table (`data/trading_bot.db`), accessed via `database.py::db_load()`/`utils.py::load_json()`. `data/audit_log.txt` and `data/bot.log` ship at 0 bytes by design.

## 8. Strategy Components and Attribution

`SYSTEM_BLUEPRINT.md` Section 3 is the single consolidated table of every verified method used, with creator/year/source — this table is what satisfies Rule 14's SEQ attribution requirement (genuine method/creator cited, no invented single creator). Position-sizing example verified this pass: Half-Kelly criterion, attributed to J.L. Kelly Jr. (1956), implemented in `capital_drawdown_manager.py` (`kelly = ...`, `half_kelly = kelly / 2.0`). Full component-by-component attribution list: see `SYSTEM_BLUEPRINT.md` §3 directly rather than duplicating it here (per this document's own no-duplication mandate).

## 9. Optimization

- Robustness principle (Rule 7, `prd.md`): trade only an optimization-proven edge, else block — feature count is not treated as a proxy for robustness, and highest historical backtest profit is not automatically treated as "best."
- `min_reward_risk` is explicitly excluded from the optimizer's searchable parameter space (`PARAM_SPACE` never includes it) — the optimizer cannot select or alter the frozen RR contract (§12). *(Evidence: `config.py` line 869 comment: "OWNER CONTRACT: optimizer output can never alter the exact 1.8R lock"; independently re-verified in this project's prior-session history across all 3 real `init_state()` call sites — not re-opened line-by-line this pass.)*
- Look-ahead protection: a genuine look-ahead defect in 3 of 11 optimizer signal-tools (swing-low detection using a future bar) was found and fixed in this project's history (r9-lookahead-fix lineage); confirmed still fixed in the current r15 lineage per this session's independent re-check (loop-bound fix present in `strategy_tools.py`).

## 10. Validation / Backtest / Paper / Live Alignment

- `docs/CROSS_ENVIRONMENT_ALIGNMENT.md` defines the Backtest↔Paper↔Live parity contract; `alignment_engine.py` implements it (see §5 for the important clarification that this is NOT the SEQ layer).
- A same-bar-fill backtest-realism gap is a known, owner-accepted limitation (owner decision: mentally adjust ~10-15% optimistic; no code change made) — carried forward as a documented limitation, not re-litigated this pass.

## 11. Risk and Capital Architecture

- `risk_manager.py::can_enter_trade()` — a 14-point gate chain (per this project's prior-session line-by-line trace; not re-walked this pass).
- Duplicate-position prevention: currently achieved as a side-effect of the correlation gate (an already-held symbol self-correlates ≈1.0, exceeding the 0.85 threshold) rather than an explicit dedicated guard — a documented, previously-accepted "OUT OF SCOPE" note (Sec 47's outcome requirement is satisfied; the *mechanism* is fragile/implicit, flagged as a professional-preference note, not a criterion violation).
- Position sizing: Half-Kelly (see §8); `capital_drawdown_manager.py::calculate_kelly_position_size()`/related functions. Capital multipliers exist for health (`get_health_capital_multiplier()`), regime (`get_regime_capital_multiplier()`), and stage-based deployment readiness (`get_stage_readiness_decision()`), in `capital_manager.py`.
- DB-read-failure handling: `database.py::db_load()` — a genuine prior fail-open defect (silently returning caller defaults on any DB read exception, contradicting the project's own fail-closed philosophy) was found and fixed (r9 fail-closed-hardening lineage: an out-of-band flag file now gates new entries on a DB read failure). Independently re-confirmed present in the current r12→r15 lineage this session (batch 24 finding + this session's own code re-checks).

## 12. Frozen RR / Exit Contract

**Exact, hardcoded, non-negotiable:** `min_reward_risk = 1.8` (`config.py` line 72, explicitly commented `[OWNER CONTRACT] Fixed exactly 1.8R lock. After lock, profit is uncapped via trailing`). Defense-in-depth confirmed across this project's history: (1) hardcoded global constant, (2) excluded from optimizer's searchable parameter space, (3) `per_stock_params.py` forces exactly 1.8 regardless of any stored legacy value. `trail_activation_pct` is explicitly marked LEGACY COMPATIBILITY ONLY, ignored by the canonical 1.8R lock-then-uncapped-trailing exit engine (`config.py` line 97, 575).

## 13. Execution / Broker / GTT

- Broker: Dhan (`broker.py`, `dhan_client.py`). Order-placement timeout is hard-enforced independent of the SDK's own internal timeout; on timeout the order status is recorded as "UNKNOWN, verify manually" (never assumed success or failure) — matches the project's fail-closed-on-ambiguity contract.
- Overnight stop-loss protection uses a separate GTT (Good-Till-Triggered) "Forever Order" path, distinct from AMO (`broker.py` line 302, 549-557).
- Paper vs. live: a single centralized gate — `broker.place_order()` checks `is_real_orders()` (from `bot_state_manager.py`, per-state `orders_real` rule) before any real Dhan SDK call. `config.py::PAPER_MODE = True` is the current shipped default. PAPER mode returns a fake `PAPER-{symbol}-...`/`PAPER-GTT-{symbol}-...` id and never reaches the real order path.

## 14. Scheduler, Monitoring, Startup/Recovery, Reconciliation

- `scheduler.py` registers multiple `AsyncIOScheduler` cron jobs (IST timezone) — market-hours scans (Mon-Fri), a periodic heartbeat job, and fixed-time daily jobs (observed job times include 08:30, 09:00, and 09:10 IST plus a configurable heartbeat interval; a full job-by-job inventory was not exhaustively re-derived this pass — see `scheduler.py` directly for the complete list).
- Startup/recovery: `startup_recovery.py::run_startup_recovery()` — on boot, logs a start marker, runs the SEQ registry boot-trace (§5), performs a token-validity check, and (on crash-recovery) reconciles local `active_trades` state against real Dhan holdings; if the holdings-fetch itself fails, activates a reconciliation hold and alerts admin (fail-closed) rather than assuming clean state. If broker shows a position closed during downtime (e.g. a GTT triggered while the bot was down), local state is cleaned without fabricating a fake fill price (a previously-fixed defect, re-confirmed still fixed).
- Monitoring/heartbeat: implemented across `bot_state_manager.py`, `broker.py`, `dhan_live_feed.py`, `forever_order_manager.py`, `portfolio_health.py`, `safety_manager.py`, `scheduler.py` (per this pass's grep for heartbeat/reconciliation references — exact per-file role not individually re-verified this pass).
- Network-partition handling: a dedicated gate blocks `run_market_scan()` during a detected partition, auto-clears via heartbeat-success signal (confirmed in prior-session history; a since-cleaned-up vestigial parallel mechanism, `clear_network_partition()`, was found to be genuinely dead/unreachable with zero live impact and removed in the r9 fail-closed-hardening release).

## 15. Paper → Live Workflow

Governed by `bot_state_manager.py`'s state machine (`STATE_RULES`, `orders_real` per state) and the capital/stage-readiness logic in `capital_manager.py` (`get_stage_readiness_decision()`). The exact deployment-stage progression criteria (what evidence is required to advance from paper to live, or between capital stages) were not independently re-derived line-by-line this pass — **NOT PROVEN in full detail this pass; see `capital_manager.py` directly and `docs/PRE_VPS_GATE_PROFILE_v1.0.md` / `docs/PRE_VPS_VERIFICATION_GATE_v1.0.md` for the governance-level gate contract.**

## 16. Governance / Audit Architecture

- Authoritative governance files (per Phase 1 classification): `prd.md`, `SYSTEM_BLUEPRINT.md`, `SYSTEM_MASTER_MANIFEST.json`, `feature_sequence.json`, `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md` (55-section audit-process framework, distinct from this document's system-facts role), `docs/MASTER_ZERO_OMISSION_ZIP_INSPECTION_CONSTITUTION_55_SECTIONS.md`, `DATA_SOURCE_POLICY.md`, `docs/CANONICAL_RELEASE_AND_AUDIT_TRUTH_INDEX.md`, `docs/CROSS_ENVIRONMENT_ALIGNMENT.md`, `docs/DATA_READINESS_AND_REFRESH.md`, `ZIP_DERIVED_REQUIREMENTS_AND_BLUEPRINT_RULES_v1.1.md`, `docs/CERTIFICATION_CLOSURE_AND_REINSPECTION_GOVERNANCE_v1.0.md`, `docs/AI_INSPECTION_TRIGGER_AND_RESULT_CONTRACT_v1.0.md`, `docs/PRE_VPS_GATE_PROFILE_v1.0.md`, `docs/PRE_VPS_VERIFICATION_GATE_v1.0.md`, `AI_ONBOARDING.md`, `VERSION.txt`.
- Integrity: `AUDIT_INTEGRITY_MANIFEST_SHA256.json`, `AUDIT_INVENTORY_SHA256.json`, `docs/AUDIT_ARTIFACT_INVENTORY.csv` — three parallel per-file hash inventories (see §18 for a known defect between them).
- Regression evidence: `test_sequence.py` (canonical runner; current baseline 118 passed / 0 failed / 7 external-required).
- A large number of additional derived/reference/point-in-time governance documents exist (audit reports, scorecards, verdict notes, checklists) — their individual currency and consolidation status is tracked in `QASWA_PHASE1_INVENTORY_CLASSIFICATION.md`, not restated here.

## 17. External Dependencies / Evidence Limitations

Cannot be proven from a static ZIP alone:
- Real broker (Dhan) behavior under live network/rate-limit/partial-fill conditions.
- Real-package cross-check of all import dependencies (sandbox-only stub verification was used in this project's own prior audits; a real VPS with real `pip install`s is required for full confirmation — Sec 4 EXTERNAL-DEFERRED).
- Live capital track record — no live-trading performance evidence exists in this ZIP; everything provable here is via backtest/paper/code-level evidence only.
- Current board/universe data freshness — **at inspection time this session**, the shipped snapshot was observed to be in a `BOARD_DATA_STALE_PAUSE=True` state (in `data/custom_universe_state.json`), meaning `get_tradeable_universe()` returned an empty list when exercised during this pass. This is a **point-in-time observation of the shipped snapshot, not a claim about a permanent or inherent system state** — the flag is data-driven and would change on a real data refresh; this document does not assert what its value will be at any other time.

## 18. Known Limitations / Currently NOT PROVEN (this document's own honest boundary)

- Purification/AAOIFI-removal claim (§6) — not re-verified against this exact ZIP this pass.
- Exact scheduler job inventory (§14) and paper→live stage-advancement criteria (§15) — not exhaustively re-derived this pass; read the named source files directly for full detail.
- `.py` orphan/duplicate-code re-scan — relies on prior-session import-graph work, not a fresh independent re-scan this pass (see Phase 1 report §B).
- All Phase-1 open governance conflicts are **carried forward, not resolved, by this document**:
  - Master Prompt is currently absent from the ZIP entirely (no canonicalization performed).
  - `AUDIT_INVENTORY_SHA256.json` / `docs/AUDIT_ARTIFACT_INVENTORY.csv` carry stale `size` fields for 15 files (pre-existing since r12; hashes agree, sizes don't — root cause not identified).
  - Two "current status" files conflict at different frozen revisions (r5 vs. r11); neither reflects r12-r15.
  - A 4-way scorecard cluster exists with at least one file (`LOCAL_TEST_SCORECARD_v1.1.md`) carrying stale test-count numbers.
  - A 3-way release-verdict document cluster exists with unverified individual currency.
  - Multiple point-in-time audit-report files are candidates for consolidation into one chronological log — not yet content-diffed for uniqueness.
  - `DEFECT_FINDING_REGISTER_v1.1.md` and `docs/CERTIFICATION_CLOSURE_REGISTER.md` are confirmed not updated for the r13-r15 findings/fixes made this session.
  - `FRAMEWORK_FREEZE_UPDATE_v1.1.md`'s recorded hash of the certification standard is likely stale relative to that document's own later change-note — not independently re-verified.

## 19. Compact Authoritative File Map

| Component | Authoritative implementation/governance file(s) |
|---|---|
| Owner Constitution / Rules | `prd.md` |
| System architecture narrative + attribution table | `SYSTEM_BLUEPRINT.md` |
| Machine-readable registry/metadata | `SYSTEM_MASTER_MANIFEST.json` |
| Pipeline stage registry + SEQ role mapping | `feature_sequence.json`, `seq_alignment_registry.py` |
| Halal/Board eligibility | `stock_selector.py` (`_row_is_halal_eligible`, `get_tradeable_universe`, `is_universe_data_stale`), `data/CUSTOM_UNIVERSE_FINAL.csv`, `data/BOARD_TRUE_100_NON_MUSLIM.csv`, `data/BOARD_FALSE_HAS_MUSLIM.csv` |
| Data-source contract | `DATA_SOURCE_POLICY.md` |
| Signal generation / optimizer tools | `strategy_tools.py`, `strategy.py` |
| Optimization parameter space / contract | `config.py` (`PARAM_SPACE`), `per_stock_params.py` |
| Risk gating | `risk_manager.py` (`can_enter_trade`) |
| Position sizing / capital | `capital_drawdown_manager.py`, `capital_manager.py` |
| RR / exit contract | `config.py` (`min_reward_risk`), exit engine module |
| Broker / execution / GTT | `broker.py`, `dhan_client.py` |
| Paper/live state machine | `bot_state_manager.py` |
| Scheduler | `scheduler.py` |
| Startup / recovery | `startup_recovery.py` |
| Backtest↔Paper↔Live parity | `alignment_engine.py`, `docs/CROSS_ENVIRONMENT_ALIGNMENT.md` |
| Storage | `database.py`, `utils.py` (`load_json`), `data/trading_bot.db` |
| Regression tests | `test_sequence.py` |
| Integrity manifests | `AUDIT_INTEGRITY_MANIFEST_SHA256.json`, `AUDIT_INVENTORY_SHA256.json`, `docs/AUDIT_ARTIFACT_INVENTORY.csv` |
| Change history | `VERSION.txt` |
| Governance-consolidation classification | `QASWA_PHASE1_INVENTORY_CLASSIFICATION.md` |

## 20. Standing Disclaimer

This document is a **narrative/index**, produced by reading and cross-referencing the files named throughout it. It is **not** authoritative over, and cannot override, the actual source code, configuration values, test results, runtime data, or the integrity manifests. Any future discrepancy between this document and the shipped implementation must be resolved in favor of the implementation, and this document corrected — never the reverse.

---

**No existing file, runtime logic, trading contract, or governance document was modified, merged, renamed, or deleted in the creation of this document. No hash/manifest was regenerated.**
