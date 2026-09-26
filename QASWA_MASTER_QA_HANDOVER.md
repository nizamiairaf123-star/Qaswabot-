# QASWA_MASTER_QA_HANDOVER.md

**Read this file first.** It consolidates `QASWA_SYSTEM_TRUTH.md` (system narrative), `QASWA_AUDIT_QA_STATUS.md` (evidence ledger), and this session's operational-readiness verification into one portable document. A new AI should be able to understand, navigate, and safely continue work on QASWA from this file alone, without reading every source file first.

**Authority hierarchy (unchanged, do not invert):**
```
SYSTEM_MASTER_MANIFEST.json  →  machine-readable authoritative registry/metadata/integrity layer
This file + QASWA_SYSTEM_TRUTH.md + QASWA_AUDIT_QA_STATUS.md  →  human-readable narrative/evidence (subordinate)
Source code / configs / tests / runtime data  →  final authority. Documentation never overrides implementation.
```

Base evidence: `QASWA_v6_0_3-r17_stale-test-r8-reconcile.zip` + this session's Q034/operational-verification pass (would ship as r18, see VERSION.txt).

---

## 1. Identity & Ownership

QASWA ("Qaswabot"/"Contabu") — Halal algorithmic trading bot for **NSE equities** (verified: `data/CUSTOM_UNIVERSE_FINAL.csv`, 1,057 rows, 100% `exchange=NSE`; no BSE row exists in the shipped universe, though `dhan_data.py`/`correlation_tracker.py` contain unused BSE-handling code). Owner: **AIRAF NIZAMI** (`prd.md` header, `SYSTEM_MASTER_MANIFEST.json`).

**QASWA Remix** — combined architecture identity, `prd.md` Rule 14: "QASWA Remix → AIRAF NIZAMI." Ownership covers the combined architecture/integration only; genuine external methodologies (§8 below) keep their own separate attribution — never merged.

## 2. Architecture & Mandatory Gate Order

```
Business Halal Filter (Rule 2)  →  Non-Muslim Board Filter (Rule 3)  →  SEQ  →  Trade Decision/Execution
```
- **Business Halal Filter / Non-Muslim Board Filter** — mandatory, fail-closed hard gates. Evidence: `stock_selector.py::_row_is_halal_eligible()` checks `core_business_halal` then `non_muslim_board`, both required True.
- **Structural enforcement (traced, not just documented):** `trade_engine.run_market_scan()` gets its symbol list from `stock_selector.get_tradeable_universe()` → `load_halal_symbols()`, which cannot return a non-eligible symbol. Verified for this specific path only — not an exhaustive whole-codebase claim.
- **SEQ** — QASWA's internal label for the systematic/quant alignment layer (Rule 14). **Not** an external methodology, **not** a new trade-veto gate — it aligns already-existing components to their methodological role. Implementation: `seq_alignment_registry.py` (zero decision logic — pure data + logging). Wired at boot (`startup_recovery.py`, one-time trace) and per-scan (`trade_engine.py`, `SEQ_STAGE_ENTRY` log line right after `get_tradeable_universe()`). Both traces are non-blocking/fail-open; this does **not** mean the eligibility gates are fail-open — those remain fail-closed. **Naming collision note:** this "SEQ" is unrelated to the pre-existing "SEQ_FILE"/"SEQ MATCH" shorthand elsewhere in the codebase for `feature_sequence.json` (coincidental namesake). `alignment_engine.py` is **NOT** the SEQ layer — it's a separate Backtest/Paper/Live parity monitor (`docs/CROSS_ENVIRONMENT_ALIGNMENT.md`).

## 3. Universe & Data

- Universe file: `data/CUSTOM_UNIVERSE_FINAL.csv` (1,057 rows, NSE-only).
- Data-source contract (`DATA_SOURCE_POLICY.md`, enforced by `test_data_source_policy.py`, executed this session — 4/4 pass): **Dhan** = mandatory source for all trading/price/volume data; **yfinance** = information-only (sector/industry/market-cap/board data), never trading data.
- **CURRENT STATE (this session, verified): universe data-refresh is BLOCKED.** `data/custom_universe_state.json` → `BOARD_DATA_STALE_PAUSE=True`. Root cause directly verified: all 1,057 rows have empty `sector`/`industry`/`market_cap`/`turnover_liquid_ok`/`atvr_pct`/`frequency_of_trading_pct`. The refresh mechanism (`scripts/refresh_decision_data.py`) is correctly designed to refuse fabricating this data — it requires `data/decision_data_provider.json`'s `"provider"` field to be configured (currently `null`) and a real, externally-materialized candidate CSV. **This is EXTERNAL-DEFERRED, not a code defect** — fixing it requires a real deployment with live Dhan/yfinance access, not further code changes.

## 4. Strategy / Signal Generation / Optimization

- Signal/strategy tools: `strategy_tools.py`, `strategy.py`. Look-ahead protection confirmed present (4 `[PHD-FIX look-ahead]` markers, `strategy_tools.py`).
- Optimizer: `optimizer.py`. `min_reward_risk` is excluded from the optimizer's searchable `PARAM_SPACE` (`config.py`) — never selected/searched.
- Attribution for genuine external methods (Half-Kelly/Kelly 1956, MSCI ATVR/FoT, Jegadeesh & Titman, etc.): `SYSTEM_BLUEPRINT.md` §3 — single consolidated table, not duplicated here.
- Config numeric constants: systematically swept this session (`config.py`, 958 lines) — all documented at per-line or block-header level; zero genuinely undocumented constants found.

## 5. Risk / Capital Allocation

- `risk_manager.py::can_enter_trade()` — multi-point gate chain.
- `capital_manager.py::get_health_capital_multiplier()` → `portfolio_health.py::get_health_multiplier()` = `max(health/100, floor)`, verified formula.
- `capital_manager.py::get_regime_capital_multiplier()` → `regime_manager.py` reads current regime's `size_mult` (BULL 1.00/SIDEWAYS 0.60/BEAR 0.25/RECOVERY 0.40); fails closed to BEAR 0.25 on error.
- `get_stage_readiness_decision()` — composite gate, fails closed (`allow: False`) on any exception.

## 6. Order Generation / Position Management / SL-GTT / Exit

- **Order generation:** `broker.py::place_order()` — gates on `is_real_orders()` first (paper mode returns a fake `PAPER-...` id immediately); real path goes through `_live_order_session_gate()` (market-hours check) + minimum-qty check before any real Dhan SDK call.
- **Position monitoring:** `trade_engine.py::monitor_positions()` (called by `scheduler.py::_position_monitor_job()`) — killswitch-gated, handles partial-fill remainders and entry-follow ticking, fail-open only on non-critical sub-steps.
- **GTT (Forever Order) / overnight SL:** `forever_order_manager.py` — L1 strict-SL GTT + retry, L2 offset-fallback GTT + retry, L3 daily re-arm job, loud admin alert if both layers fail (position never silently unprotected), trail-follow never lowers the floor. `broker.py`'s `place/modify/cancel_forever_order()` all correctly paper-gate and exception-safe.
- **RR / Exit contract (FROZEN — do not change without explicit owner decision):** exactly **1:1.8**. `config.py` line 72: `"min_reward_risk": 1.8`. 1R = actual entry-to-initial-SL distance. No breakeven/+1R/early-trailing before the 1.8R lock. At 1.8R, protection locks; after that, **uncapped, optimizer-selected trailing/exit** takes over (`config.py::trail_activation_pct` marked LEGACY, ignored by the canonical engine).
  - **Important nuance found this session (r17):** the "exactly 1.8" guarantee is a **pipeline/outcome** guarantee (RR is not an optimizer dimension, never selected differently) — it is **not** an independent input-clamp inside `exit_engine.py::init_state()` itself. `init_state()` reads `params.get("min_reward_risk", 1.8)` — if a params dict ever supplied something other than 1.8, `init_state()` would use it as-is. All 3 real call sites (`trade_engine.py`, `optimizer.py`, `strategy.py`) verified this session to never supply anything but 1.8 in practice (two omit the key, relying on the 1.8 default; one reads `config.PARAMS` directly). An independent defense-in-depth clamp was explicitly considered and **deliberately NOT added** — deferred as a separate, not-yet-authorized future hardening decision, not a current defect.
  - `test_golden.py` was found this session to have a **stale test** (`test_rr_above_1_8_is_ignored`, written for pre-r8 architecture, predating this session, reproduced on the untouched original r12 zip) — fixed and renamed to `test_rr_defaults_to_1_8_when_absent`, testing the actual current guarantee. History recorded in the test's own docstring.

## 7. Scheduler / Heartbeat / Reconciliation / Startup-Recovery

- `scheduler.py` — **34 unique, all-defined jobs** (verified this session: zero duplicates, zero dangling references). Includes `_market_scan_job`, `_position_monitor_job`, `_heartbeat_job`, board/liquidity/metadata monthly-refresh jobs, etc.
- Heartbeat: `scheduler.py::_heartbeat_job()` → `utils.py::record_heartbeat_success/failure()` → `is_network_partition()` → genuinely consumed as a scan-blocking gate in `trade_engine.py` (traced end-to-end this session).
- **Known vestigial item (not new, disclosed since batch 24 of this project's history):** `utils.py::clear_network_partition()` has zero callers in this specific ZIP lineage — dead code, zero live impact, a deletion decision (out of scope for this pass).
- Startup/recovery: `startup_recovery.py::run_startup_recovery()` — reconciles local state against real broker holdings on crash recovery, fails closed (reconciliation hold + admin alert) if the holdings-fetch itself fails.

## 8. Paper / Live Routing

Single centralized gate: `broker.py::place_order()` (and the GTT equivalents) check `bot_state_manager.py::is_real_orders()` before any real Dhan SDK call. `config.py::PAPER_MODE = True` is the current shipped default.

## 9. PRD / Blueprint Relationship

`prd.md` = Owner Constitution (16 rules, frozen, "never changes silently") + product requirements. `SYSTEM_BLUEPRINT.md` = architecture narrative + the single consolidated method-attribution table (§3). `SYSTEM_MASTER_MANIFEST.json` = machine-readable registry (domains, owner_constitution mirror, integrity-adjacent metadata). This handover file + `QASWA_SYSTEM_TRUTH.md` + `QASWA_AUDIT_QA_STATUS.md` sit below all of these — narrative/evidence only, never authoritative over code.

## 10. Tests & Verification (this session's baseline)

- `test_sequence.py` — canonical regression runner. **This session's result: 118 passed, 0 failed, 7 external-required — but this is specific to this sandbox's environment** (no network access; `pytz`/`dhanhq`/`telegram`/`apscheduler` are hand-built minimal local stubs, not the real packages). A different environment (real packages installed, or a different subset available) can legitimately produce a different pass/external-required split — this is not a claim of a universal, environment-independent number. Re-verified this session as reproducible against both the untouched original r12 zip and every r13-r18 release using this same stub setup.
- `scripts/release_preflight.py` — run directly this session: returns **`NOT READY`**, citing the exact same 6 empty decision-critical fields as Q034/§3 above (`sector`, `industry`, `market_cap`, `turnover_liquid_ok`, `atvr_pct`, `frequency_of_trading_pct`, all 1,057 rows unknown). This independently confirms the Q034 finding via a different, dedicated script.
- All 18 `test_*.py` files individually reviewed/executed this session (not just counted) — see `QASWA_AUDIT_QA_STATUS.md` Q029 for the full account, including the one genuine defect found and fixed (§6 above).
- `test_data_source_policy.py` — 4/4 pass, executed in isolation, proves the Dhan/yfinance contract at the AST level.

## 11. Evidence Ledger Summary (see `QASWA_AUDIT_QA_STATUS.md` for the full 36-question detail)

PASS: 30 · FAIL: 1 (Q034, data-readiness, not a code defect) · NOT PROVEN: 1 (Q037 Rule 15/NDSAP — Part B ToS-blocked, by design; Parts C+A PASS r27) · EXTERNAL-DEFERRED: 3 (real broker/live conditions, real package resolution, real universe refresh) · N/A: 3 (a rejected hypothesis, Master Prompt absence, out-of-scope Phase-1 conflicts). Total: 38 (the old Q038/old Rule 16 were fully deleted 2026-09-13 by owner decision — no historical record kept, per explicit instruction; the NEW Q038, added r30 2026-09-15, tracks the NEW Rule 16 Decision & Market-Context Telemetry "Black Box" (owner-side audit alias "PIT Telemetry" — same capability, owner-confirmed r31) — PASS with documented boundaries — and is unrelated to the deleted one).

## 12. Known Limitations / Pending External Evidence

- **Rule 15 / NDSAP (NIZAMI Data Segregation & Accumulation Protocol) — registered 2026-09-08, refined 2026-09-13 (owner AIRAF NIZAMI); PART C IMPLEMENTED r27 2026-09-13 under explicit owner implementation-authorization (`ndsap_archive.py` + read-only taps + 13 executed tests + `NDSAP_RETENTION_ESTIMATE.md`); Part A verified pre-existing; PART B still NOT IMPLEMENTED (ToS blocker open).** Governance-only: `prd.md` Rule 15, `SYSTEM_BLUEPRINT.md` §9, `QASWA_AUDIT_QA_STATUS.md` Q037. Three parts: (A) Dhan-exclusive no-substitute for trading-decision data (OHLCV/price/volume) — reaffirms `DATA_SOURCE_POLICY.md` (Q014) unchanged, fails closed if Dhan can't supply, never substituted from elsewhere; (B) broadened alternate sourcing (NSE, Moneycontrol, yfinance — was yfinance-only) for non-Dhan-available decision-support fields only (sector/industry/market_cap, Q034), Dhan checked first, never for price/volume; (C) immutable append-only archive of live data actually received, for future backtest/validation use. Archive code now EXISTS for Part C (r27: `ndsap_archive.py`, own SQLite file, structural as-of guard + immutability triggers, taps in `dhan_data.py`/`broker.py`/`market_metadata.py`, retention estimate delivered in `NDSAP_RETENTION_ESTIMATE.md` — owner implementation-authorization given 2026-09-13). No source-router code exists — Part B remains blocked on the ToS review for yfinance/NSE/Moneycontrol storage/reuse; until the owner clears ToS and adds a provider to `ndsap_archive_providers` (config.py), the non-Dhan taps are structurally gated OFF and write nothing. Criterion-approval and implementation-authorization remain two separate decisions for any further part.

- **Q034 — universe/board data refresh is blocked**, needs a real deployment with a configured Dhan/yfinance provider (`data/decision_data_provider.json`).
- **EXTERNAL-DEFERRED items (Q031-Q033):** real broker network behavior (rate limits, partial fills, latency), real non-stubbed package resolution, real live-trading performance — none of these can be proven by static code inspection.
- **Purification/AAOIFI-removal claim** — historically stated as removed per owner decision (r4 era); not re-verified against this exact ZIP this session.
- Exact scheduler job *timing* correctness (each `CronTrigger` firing at its intended wall-clock time in a real running process) — job *inventory completeness* is proven (§7), live timing is not (that's an EXTERNAL-DEFERRED runtime claim).
- Governance-doc clusters flagged in `QASWA_PHASE1_INVENTORY_CLASSIFICATION.md` (scorecards, verdict docs, "current status" docs) remain unresolved — informational only, do not affect trading-readiness.

## 13. Important Frozen Decisions (do not silently reopen)

- RR exactly 1.8, uncapped trailing after lock (§6).
- Business Halal Filter + Non-Muslim Board Filter are non-negotiable hard gates (§2).
- SEQ is explicitly NOT a new trade-veto gate and must never become one without an explicit new-criterion decision (§2, and see Task 3 process below).
- Purification/AAOIFI mechanism was removed per an explicit prior owner decision — do not reintroduce without a fresh decision.
- No independent `init_state()` clamp was added for RR (§6) — an intentional deferral, not an oversight; do not silently add one without an explicit hardening decision.
- CVaR is **not** a current QASWA criterion (confirmed: appears nowhere in `prd.md`/`SYSTEM_BLUEPRINT.md`/`config.py`; the only ZIP mention is an unchecked box in a self-marked-SUPERSEDED checklist) — do not treat it as a pending requirement.

## 14. Repair / Navigation Map — "I need to investigate/fix X, where do I look?"

| If the question is about... | Look at |
|---|---|
| Owner rules / constitution / Rule 14 (Remix/SEQ identity) | `prd.md` |
| System architecture / method attribution | `SYSTEM_BLUEPRINT.md` |
| Machine-readable registry / domains | `SYSTEM_MASTER_MANIFEST.json` |
| Pipeline stages / SEQ role mapping | `feature_sequence.json`, `seq_alignment_registry.py` |
| Halal/Board eligibility logic or data | `stock_selector.py`, `data/CUSTOM_UNIVERSE_FINAL.csv`, `data/BOARD_TRUE_100_NON_MUSLIM.csv` |
| Universe refresh / data staleness | `scripts/refresh_decision_data.py`, `data/custom_universe_state.json`, `data/decision_data_provider.json` |
| Data-source contract (Dhan vs yfinance) | `DATA_SOURCE_POLICY.md`, `test_data_source_policy.py` |
| Signal/strategy tools, look-ahead | `strategy_tools.py`, `strategy.py` |
| Optimizer, parameter space | `optimizer.py`, `config.py::PARAM_SPACE` |
| Risk gating | `risk_manager.py` |
| Capital/position sizing | `capital_manager.py`, `capital_drawdown_manager.py`, `portfolio_health.py`, `regime_manager.py` |
| RR / exit / trailing contract | `config.py` (`min_reward_risk`), `exit_engine.py` |
| Order placement, GTT | `broker.py`, `dhan_client.py`, `forever_order_manager.py` |
| Position monitoring | `trade_engine.py::monitor_positions()` |
| Paper/live state | `bot_state_manager.py` |
| Scheduler jobs | `scheduler.py` |
| Startup/crash-recovery | `startup_recovery.py` |
| Backtest/Paper/Live parity (NOT SEQ) | `alignment_engine.py`, `docs/CROSS_ENVIRONMENT_ALIGNMENT.md` |
| Storage | `database.py`, `utils.py::load_json()`, `data/trading_bot.db` |
| Regression tests | `test_sequence.py` |
| Integrity manifests | `AUDIT_INTEGRITY_MANIFEST_SHA256.json`, `AUDIT_INVENTORY_SHA256.json`, `docs/AUDIT_ARTIFACT_INVENTORY.csv` |
| Change history | `VERSION.txt` |
| Full evidence ledger (36 Q&A) | `QASWA_AUDIT_QA_STATUS.md` |
| Full system narrative | `QASWA_SYSTEM_TRUTH.md` |
| **How to audit/verify/fix/certify QASWA (the governing process standard itself)** | `QASWA_MASTER_AUDIT_PROMPT.md` |
| Governance file classification / redundancy candidates | `QASWA_PHASE1_INVENTORY_CLASSIFICATION.md`, `QASWA_REDUNDANCY_IDENTIFICATION_REPORT.md` |
| Future-change process | `QASWA_FUTURE_CHANGE_GOVERNANCE.md` |

---

**Standing disclaimer:** this file is a narrative/index. It cannot override source code, configs, tests, runtime data, or the integrity manifests. Any discrepancy must be resolved in favor of the implementation, and this file corrected — never the reverse.
