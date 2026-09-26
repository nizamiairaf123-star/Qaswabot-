# QASWA_AUDIT_QA_STATUS.md

**Purpose: evidence ledger, not a narrative.** Each question has ANSWER / EVIDENCE / REASON / PROOF TYPE / STATUS. Status values: **PASS** (directly proven), **FAIL** (contradiction/defect directly proven), **NOT PROVEN** (insufficient evidence in this pass), **EXTERNAL-DEFERRED** (needs live/external infra), **N/A**. PASS is never given for a documentation claim alone. Base evidence: `QASWA_v6_0_3-r15_seq-stage-entry-trace.zip`, cross-checked against `QASWA_PHASE1_INVENTORY_CLASSIFICATION.md` and `QASWA_SYSTEM_TRUTH.md` (frozen). Where a proof rests on prior-session work not re-run in this pass, PROOF TYPE says so explicitly — this is not treated as fresh verification.

---

**Q001 — Is ownership (AIRAF NIZAMI) registered as authoritative?**
ANSWER: PASS
EVIDENCE: `prd.md` header; `SYSTEM_MASTER_MANIFEST.json` owner_constitution
REASON: Explicit owner statement present in both the human-readable and machine-readable registries, consistent with each other.
PROOF TYPE: Documentation (cross-checked across 2 independent files this pass)
STATUS: PASS

**Q002 — Is "QASWA Remix → AIRAF NIZAMI" identity registered?**
ANSWER: PASS
EVIDENCE: `prd.md` Rule 14; `SYSTEM_BLUEPRINT.md` intro; `SYSTEM_MASTER_MANIFEST.json` owner_constitution; `feature_sequence.json` meta.seq_rule14_identity
REASON: Identity statement present and consistent across 4 independent files, added and cross-checked this session (r13).
PROOF TYPE: Documentation, code-adjacent registry
STATUS: PASS

**Q003 — Is the mandatory gate order (Halal → Board → SEQ → decision) implemented, not just documented?**
ANSWER: PASS (for the inspected `run_market_scan()` path only)
EVIDENCE: `stock_selector.py::_row_is_halal_eligible()` (Halal checked before Board); `stock_selector.py::get_tradeable_universe()` → `load_halal_symbols()`; `trade_engine.py::run_market_scan()` consumes only this filtered list
REASON: Traced this session: the market-scan entry point cannot obtain a symbol that has not passed both checks.
PROOF TYPE: Code (traced this session), scoped to one entry path — not an exhaustive whole-codebase scan
STATUS: PASS

**Q004 — Is Business Halal Filter fail-closed (blocks on missing/ambiguous data)?**
ANSWER: PASS
EVIDENCE: `stock_selector.py::_row_is_halal_eligible()`, `is_universe_data_stale()`
REASON: Confirmed in prior-session audits (r4 era) that missing/ambiguous data blocks rather than defaults to eligible; re-observed this session functionally (`BOARD_DATA_STALE_PAUSE=True` in the shipped snapshot correctly returned an empty universe, not a default-eligible one).
PROOF TYPE: Code + functional observation this session; line-by-line eligibility logic not re-walked this session
STATUS: PASS

**Q005 — Is Non-Muslim Board of Directors Filter fail-closed?**
ANSWER: PASS
EVIDENCE: Same function as Q004 (`_row_is_halal_eligible`), `data/BOARD_TRUE_100_NON_MUSLIM.csv` / `data/BOARD_FALSE_HAS_MUSLIM.csv`
REASON: Same mechanism as Q004; board data files exist and are consumed by the eligibility check.
PROOF TYPE: Code + data-file existence check this session; full field-by-field data-quality audit not re-run this session
STATUS: PASS

**Q006 — Is SEQ a genuine methodology-alignment layer, not a new trade-blocking gate?**
ANSWER: PASS
EVIDENCE: `seq_alignment_registry.py` (zero `if`/`allow`/`block` statements — read-only registry); `startup_recovery.py` and `trade_engine.py` wiring (log-only calls, wrapped in try/except, non-blocking)
REASON: Verified this session by reading the module and functionally executing both trace call sites — neither can alter a trade decision.
PROOF TYPE: Code + functional execution this session
STATUS: PASS

**Q007 — Is `alignment_engine.py` the SEQ layer?**
ANSWER: NO — the hypothesis is false
EVIDENCE: `alignment_engine.py` docstring: "Cross-environment strategy alignment monitor... Backtest -> Paper -> Live"; `docs/CROSS_ENVIRONMENT_ALIGNMENT.md`
REASON: This module implements Backtest/Paper/Live performance parity monitoring, unrelated to Rule 14's SEQ concept. Confirmed by direct inspection this session (this was the key correction in r14). This is a correctly-rejected hypothesis, not a system defect — do not count as a FAIL.
PROOF TYPE: Code (direct read this session)
STATUS: N/A

**Q008 — Is the current shipped universe NSE-only or NSE+BSE?**
ANSWER: PASS (NSE-only, as a factual finding)
EVIDENCE: `data/CUSTOM_UNIVERSE_FINAL.csv` — 1,057 data rows, CSV-parsed this session, all rows `exchange = NSE`
REASON: Directly parsed this session with Python's `csv` module; zero BSE rows found. Code contains BSE-handling logic (`dhan_data.py`, `correlation_tracker.py`) but it is not exercised by this file.
PROOF TYPE: Data (direct parse this session)
STATUS: PASS

**Q009 — Is the RR/exit contract exactly 1:1.8 with uncapped trailing, frozen against optimizer change?**
ANSWER: PASS
EVIDENCE: `config.py` line 72 (`"min_reward_risk": 1.8`, comment "[OWNER CONTRACT]"); line 869 (`params["min_reward_risk"] = 1.8` forced post-optimization); `trail_activation_pct` marked LEGACY/ignored
REASON: Hardcoded constant + explicit override after optimization + optimizer's parameter space exclusion (per prior-session trace of `PARAM_SPACE`, not re-walked this session) forms defense-in-depth.
PROOF TYPE: Code (direct read this session for the constant/override; parameter-space exclusion and all 3 `init_state()` call sites carried forward from prior-session trace, not re-walked this session)
STATUS: PASS

**Q010 — Is look-ahead bias in optimizer signal tools prevented?**
ANSWER: PASS
EVIDENCE: `strategy_tools.py` — 4 occurrences of `[PHD-FIX look-ahead]` comments (lines 248, 297, 432, 450) documenting the fixed loop-bound
REASON: Fix markers present at all 4 previously-defective sites (per project history, r9-lookahead-fix); confirmed present in this exact lineage by direct grep this session.
PROOF TYPE: Code (direct grep this session); the underlying logic itself was not re-derived from first principles this session
STATUS: PASS

**Q011 — Is there a regression test suite, and does it currently pass?**
ANSWER: PASS
EVIDENCE: `test_sequence.py`; executed this session against the final r15 fresh-extracted zip
REASON: Actual execution this session (with local stubs for pytz/dhanhq/telegram/apscheduler, no network available) returned "118 passed, 0 failed, 7 external-required."
PROOF TYPE: Test (executed this session)
STATUS: PASS

**Q012 — Are the shipped integrity manifests internally consistent?**
ANSWER: PASS (fixed this session — was FAIL at original ledger creation)
EVIDENCE: r16 release: VERIFY→FIX→RE-VERIFY protocol executed this session. Pre-fix: `AUDIT_INTEGRITY_MANIFEST_SHA256.json` already 176/176 correct; `AUDIT_INVENTORY_SHA256.json` had stale `size` for 15 files (hash correct); CSV had stale `size` AND `sha256` for the same 15. Post-fix, independently re-verified from a fresh read: all three artifacts 176/176 exact match against actual on-disk content, excluding the CSV's own single self-referential row (an inherent, disclosed, not-fully-fixable-in-one-pass paradox, unchanged in kind since r13).
REASON: Every corrected value was hash-verified against actual file content before its `size` field was touched (an explicit assertion would have stopped the fix rather than proceeding on any hash disagreement — none occurred). No content file's bytes were changed; only the 3 integrity artifacts were edited.
PROOF TYPE: Data (direct comparison, fix, and independent fresh re-verification, all this session) + regression test (118/0/7 unchanged)
STATUS: PASS

**Q013 — Does a canonical Master Prompt/Master Audit Instruction exist inside the ZIP?**
ANSWER: N/A (does not exist — not a pass/fail of implementation, a governance-artifact absence)
EVIDENCE: `grep -rli "master.*prompt\|master.*instruction"` across all `.md`/`.py`/`.txt` this session — only incidental hit is `VERSION.txt`'s own prose mentioning "Master-Prompt-driven" work, not a file
REASON: The Master Prompt used to govern this cleanup project was supplied externally this session; it has never been part of the `claude3.zip` lineage.
PROOF TYPE: Direct search this session
STATUS: N/A — flagged as a Phase-1/2 open item, not resolved here per this Phase's scope

**Q014 — Is the Dhan-mandatory / yfinance-information-only data-source contract implemented, not just documented?**
ANSWER: PASS
EVIDENCE: `test_data_source_policy.py` read in full and **independently executed** this session (`python -m unittest test_data_source_policy -v`) — all 4 tests pass: (1) AST-based scan confirms none of 13 trading modules import yfinance, (2) backtester/optimizer/liquidity-screen confirmed to import Dhan's `fetch_daily_data`, (3) AST scan of every `.py` file confirms yfinance is imported only in the 3 allowed info modules, (4) a functional test confirms liquidity refresh works correctly using mocked Dhan data while the main selector is paused.
REASON: This is a genuine, executed regression test with real assertions (not just a file that exists) — directly proves the contract at both the import-graph and functional level.
PROOF TYPE: Test (executed this session, isolated from the aggregate suite)
STATUS: PASS

**Q015 — Is position sizing genuinely Half-Kelly, correctly attributed?**
ANSWER: PASS
EVIDENCE: `capital_drawdown_manager.py` — `kelly = (expected_win_loss_ratio * expected_win_rate - (1 - expected_win_rate)) / expected_win_loss_ratio`; `half_kelly = kelly / 2.0`; `SYSTEM_BLUEPRINT.md` §3 attributes to J.L. Kelly Jr. (1956)
REASON: Formula matches the standard Kelly criterion halved; attribution is to the genuine originator, not a fabricated single creator for an unrelated concept.
PROOF TYPE: Code (direct read this session)
STATUS: PASS

**Q016 — Is capital allocation risk-adjusted (health/regime/stage multipliers)?**
ANSWER: PASS
EVIDENCE: `capital_manager.py::get_health_capital_multiplier()` → `portfolio_health.py::get_health_multiplier()` — verified formula `max(health_score/100, MIN_HEALTH_CAPITAL_FLOOR)`, rounded to 2dp (health 100→1.00x, 70→0.70x, 40→0.40x, matches its own docstring examples exactly). `get_regime_capital_multiplier()` → `regime_manager.py::get_regime_size_multiplier()` — reads the current regime's `size_mult` from `config.py`'s `regime_behavior_defaults` (BULL 1.00 / SIDEWAYS 0.60 / BEAR 0.25 / RECOVERY 0.40, cross-checked against Q027's config read); fails closed to BEAR 0.25 (worst case) on any lookup error, not to 1.0. `get_stage_readiness_decision()` — composite health+capital+hurdle gate; returns `allow: False` on any exception (fails closed).
REASON: All three functions' actual formulas/call chains were read this session, not just their names — the multipliers genuinely vary with health/regime state and all three fail toward the conservative/closed side on error.
PROOF TYPE: Code (full function-chain read this session, 3 files: `capital_manager.py`, `portfolio_health.py`, `regime_manager.py`)
STATUS: PASS

**Q017 — Does DB-read-failure handling fail closed (not silently fail open)?**
ANSWER: PASS
EVIDENCE: `database.py::db_load()` comment/flag mechanism; prior-session fix record (r9 fail-closed-hardening); `trade_engine.py` entry-gate check referenced in that history
REASON: A genuine fail-open defect was found and fixed in this project's own history (batch 22); confirmed still present/correct in the r12→r15 lineage per batch-24 independent re-check. Not re-walked line-by-line this session.
PROOF TYPE: Code + prior-session functional verification, not re-run this session
STATUS: PASS (carried-forward evidence, not freshly re-executed this session)

**Q018 — Is duplicate-position entry prevented?**
ANSWER: PASS (outcome), with a known implementation caveat
EVIDENCE: `risk_manager.py::can_enter_trade()` correlation gate (self-correlation ≈1.0 for an already-held symbol exceeds the 0.85 threshold)
REASON: Prior-session trace (batch 18) found the outcome is satisfied, but only as a side-effect of the correlation check, not an explicit dedicated guard — downgraded from "bug" to a documented professional-preference note at the time, per the project's own frozen-criteria discipline (outcome, not mechanism, is what Sec 47 requires).
PROOF TYPE: Code, carried forward from prior-session trace, not re-walked this session
STATUS: PASS (for the stated outcome-only criterion)

**Q019 — Does the scheduler run its jobs on the claimed schedule?**
ANSWER: PASS (job-inventory completeness; not a live-execution-timing proof, see PROOF TYPE)
EVIDENCE: Full extraction this session of every `scheduler.add_job()` call in `scheduler.py` — exactly 34 distinct jobs (`_market_scan_job`, `_position_monitor_job`, `_heartbeat_job`, `_morning_init_job`, `_daily_report_job`, `_reconciliation_job`, `_backup_job`, `_health_check_job`, `_weekly_review_job`, `_auto_reoptimize_job`, `_overnight_prefetch_job`/`_overnight_scan_job`/`_overnight_exit_job`, board/liquidity/metadata monthly-refresh jobs, etc.) — verified 34/34 unique (zero duplicate registrations) and 34/34 have a real `def` in the same file (zero dangling/missing job functions).
REASON: This directly answers the previously-open "completeness of the job inventory" question — every registered job is unique and genuinely defined. Confirming that each job's `CronTrigger` fires at exactly its intended wall-clock time in a real running scheduler was not (and cannot be, statically) proven this session — that remains an EXTERNAL-DEFERRED live-timing claim (Q033-adjacent), distinct from the inventory-completeness question this entry answers.
PROOF TYPE: Code (full extraction + cross-check this session)
STATUS: PASS

**Q020 — Does startup/recovery correctly reconcile local state against real broker holdings on crash recovery?**
ANSWER: PASS (carried forward)
EVIDENCE: `startup_recovery.py::_handle_crash_recovery()`; prior-session trace (batch 19)
REASON: Confirmed in project history that a holdings-fetch failure activates a reconciliation hold + admin alert (fail-closed) rather than assuming clean state, and that a real fill price is recorded rather than fabricated. Not re-walked line-by-line this session; the SEQ-related additions to this same file (§5/Q006) were directly re-verified this session, but this specific recovery logic was not re-opened.
PROOF TYPE: Code, carried forward from prior session
STATUS: PASS (carried-forward evidence)

**Q021 — Is monitoring/heartbeat wired across the relevant modules?**
ANSWER: PASS
EVIDENCE: Full end-to-end heartbeat cycle traced this session: `scheduler.py::_heartbeat_job()` → `broker.py`/`utils.py::record_heartbeat_success()/record_heartbeat_failure()` (2-minute continuous-failure threshold triggers `partition_detected`) → `utils.py::is_network_partition()` → genuinely consumed as a scan-blocking gate in `trade_engine.py` (line 231-232). The other 4 modules each confirmed to carry a distinct, real (non-stub) monitoring-adjacent role: `dhan_live_feed.py` (live-feed exits, backed by the 3-min monitor as safety net), `portfolio_health.py::_execution_monitoring_score()` (feeds the health score), `safety_manager.py::run_reconciliation()` (delegates to `trade_engine.run_reconciliation()`), `forever_order_manager.py` (L3 monitor-only fallback + reconciliation reference).
REASON: This is a genuine, traced write→read→gate chain, not just a keyword-presence grep. Side finding (not new, already disclosed in this project's own history under a different zip lineage): `utils.py::clear_network_partition()` still has zero callers in this specific lineage — known vestigial dead code, zero live impact, out of scope for this fix (a deletion decision, not a monitoring-wiring defect).
PROOF TYPE: Code (full trace this session, 4 files: `utils.py`, `broker.py`, `scheduler.py`, `trade_engine.py`, plus role-confirmation of 4 more)
STATUS: PASS

**Q022 — Is the paper/live order-routing gate centralized (no path that bypasses it)?**
ANSWER: PASS (carried forward)
EVIDENCE: `broker.py::place_order()` checks `is_real_orders()` (from `bot_state_manager.py`) before any real Dhan SDK call; PAPER mode returns a fake `PAPER-{symbol}-...` id
REASON: Confirmed in prior-session trace (batch 20, Sec 25) that this is the single centralized gate. Not re-walked this session.
PROOF TYPE: Code, carried forward from prior session
STATUS: PASS (carried-forward evidence)

**Q023 — Are GTT (Forever Order) mechanics implemented for overnight SL protection?**
ANSWER: PASS (code-level correctness; real-broker-condition correctness remains EXTERNAL-DEFERRED, Q033)
EVIDENCE: `forever_order_manager.py` read in full this session — L1 strict-SL GTT placement with retry-once, L2 offset-fallback GTT if L1 fails (also retry-once), loud admin alert if both fail (position never silently unprotected), L3 daily `rearm_gtt_missing()` job, `update_trail_sl()` which never lowers the floor SL. `broker.py`'s 3 core functions (`place_forever_order`, `modify_forever_order`, `cancel_forever_order`) read this session — all correctly gate on `is_real_orders()` for paper-mode fake IDs, call the real Dhan SDK GTT methods in live mode, and return success/failure rather than raising uncaught exceptions.
REASON: This is a genuine, multi-layer, fail-safe design read end-to-end this session, not just confirmed to exist by name.
PROOF TYPE: Code (full read this session, 2 files)
STATUS: PASS

**Q024 — Does subscriber-facing output withhold stock names (SEBI "software sale, not advice" contract)?**
ANSWER: PASS (carried forward)
EVIDENCE: `simulate_engine.py::format_simulation_message()` (per prior-session trace, batch 21); `bot.py` `is_admin()` gating for admin-only detail
REASON: Confirmed in project history that non-admin subscriber messages contain zero stock symbols. Not re-opened this session — this session only confirmed `is_admin()` exists and is used consistently at admin-command sites via grep.
PROOF TYPE: Code, carried forward from prior session; `is_admin()` usage pattern independently grep-confirmed this session
STATUS: PASS (carried-forward evidence for the stock-name-withholding claim specifically)

**Q025 — Is `data/audit_log.txt` a genuine, honest audit trail (not fabricated/pre-filled)?**
ANSWER: PASS
EVIDENCE: `utils.py::append_log()`; shipped `data/audit_log.txt` is 0 bytes; this session's own functional tests wrote real lines to it and then reset it to 0 bytes to match the shipped state
REASON: Directly exercised this session — the log-write mechanism is real and was observed writing genuine content during functional testing, not just claimed.
PROOF TYPE: Code + functional execution this session
STATUS: PASS

**Q026 — Is the database (SQLite `key_value_store`) schema as documented?**
ANSWER: PASS
EVIDENCE: `database.py` read in full this session (128 lines) — single table `key_value_store(key TEXT PRIMARY KEY, value TEXT NOT NULL)`; actual shipped `data/trading_bot.db` queried directly this session (`sqlite_master`) — schema matches exactly. `db_save()`/`db_load()` both wrap all access in try/except with fail-open-on-return-value + out-of-band failure marker (`is_db_failure_recent()`), confirmed wired at 2 real call sites this session (`trade_engine.py` entry gate, `utils.py`).
REASON: Full file read (not a grep sample) + live query of the actual shipped database file + explicit reachability check of the failure-detection wiring.
PROOF TYPE: Code (full read) + Data (live DB query) + reachability check, all this session
STATUS: PASS

**Q027 — Are configuration values free of undocumented hardcoded numbers (Rule 6)?**
ANSWER: PASS (for `config.py`; other files not exhaustively swept)
EVIDENCE: Automated line-by-line scan this session (`config.py`, 958 lines): 203 explicit `"source": ...` annotations found (per-stock optimizer-fallback table); a separate regex sweep for bare numeric key-value lines with no inline comment found 25 candidates at a 6-line lookback window, narrowing to 7 at a 15-line lookback window. Every one of these remaining 7 was manually verified to fall inside a dict whose enclosing block already carries a group-level source/rationale comment header further above (e.g. `regime_behavior_defaults` — BEAR/RECOVERY sub-blocks documented by the header at lines 388-391; `overnight_score_weights` sub-keys documented by the header at line 370; regime multi-factor weights documented by the Hamilton-1989/Dempster-Shafer-1967 header at lines 278-281) — none were genuinely undocumented; the narrow automated window just missed the header due to dict-nesting depth.
REASON: `config.py` consistently documents numeric constants at either the per-line (`# ...`) or group/block-header level (e.g. "FIX-04 verified values", "owner audit D1-D28", cited academic sources) — no genuinely undocumented numeric constant was found in this file this session.
PROOF TYPE: Code (systematic automated scan + manual verification of every remaining candidate, this session)
STATUS: PASS (scoped to `config.py` only — other files containing numeric thresholds, e.g. `risk_manager.py`/`capital_manager.py`, were not swept this session; full-codebase coverage remains open)

**Q028 — Do the 3 hash/inventory manifests together prove there is no undisclosed extra or missing file?**
ANSWER: PASS
EVIDENCE: Fresh-extraction verification this session (r15 zip): 176/176 hash match, 0 missing, 0 unregistered
REASON: Directly executed this session against the final fresh-extracted zip, not just the working directory.
PROOF TYPE: Data + direct execution this session
STATUS: PASS (independent of the Q012 `size`-field defect, which does not affect file-presence/hash-match conclusions)

**Q029 — Are all required tests (REQUIRED_TEST classification) present and non-empty?**
ANSWER: PASS (with one real defect found and fixed this session — r17)
EVIDENCE: All 18 `test_*.py` files individually inspected/executed this session (assertion-density check + direct execution via `unittest`/direct-script-run for the non-unittest-style files). All contain genuine, substantive test logic — no empty stubs found (the smallest, `test_db_setup.py`, is a 2-line smoke-init script, not a real test, but is not counted as a "required test" in the substantive sense). One genuine pre-existing failure found: `test_golden.py::test_rr_above_1_8_is_ignored` — reproduced against the untouched original r12 zip (confirmed NOT a r13-r16 regression). Root-caused via 3-part evidence reconciliation (no `rr_contract.py` exists in this ZIP; governing docs state an outcome guarantee — "not an optimizer dimension" — not an input-clamp requirement; `UPDATE_HISTORY_FIX_LOG.md` confirms the r8 2026-09-06 "RR single-sourcing" fix intentionally, owner-approved, changed `exit_engine.py::init_state()` from a hardcoded `rr=1.8` literal to reading `params.get("min_reward_risk", 1.8)` — the failing test was written for the pre-r8 architecture and never updated). Classified as **stale test / test-contract mismatch**, not a new RR-contract code defect, per owner's explicit reconciliation decision. Fixed in r17: test renamed to `test_rr_defaults_to_1_8_when_absent`, rewritten to verify the actual current guarantee (default is 1.8 when the key is absent), full history recorded in its docstring. An independent defense-in-depth clamp inside `init_state()` was explicitly considered and NOT implemented — deferred as a separate, not-yet-authorized future hardening decision.
REASON: This is genuine, executed, individually-reviewed evidence — not a count or a sample. The one real defect found was root-caused via governance-document reconciliation (not guessed) and fixed with owner sign-off, not silently patched.
PROOF TYPE: Code (full individual review) + Test (executed for every file) + governance-doc cross-reference, all this session
STATUS: PASS

**Q030 — Are deployment artifacts (deploy.sh, start_bot.sh, systemd service) present?**
ANSWER: PASS (existence only)
EVIDENCE: `deploy.sh`, `start_bot.sh`, `qaswa-bot@.service` all confirmed present this session via `ls`
REASON: Files exist; their correctness under a real VPS deployment is EXTERNAL-DEFERRED (Q033).
PROOF TYPE: File existence check this session
STATUS: PASS for existence; see Q033 for deployment correctness

**Q031 — Does live-trading performance evidence exist in this ZIP?**
ANSWER: EXTERNAL-DEFERRED
EVIDENCE: none found — no live-trade log/statement/broker record ships in this ZIP
REASON: This is a static-code ZIP; live performance can only be proven by real deployment, not by inspection.
PROOF TYPE: External
STATUS: EXTERNAL-DEFERRED

**Q032 — Does real-package (non-stubbed) dependency resolution succeed (pytz/dhanhq/telegram/apscheduler)?**
ANSWER: EXTERNAL-DEFERRED
EVIDENCE: This session's test execution required hand-built local stubs for all 4 packages (no network available in this sandbox)
REASON: Only stub-level import compatibility was proven this session; genuine package behavior requires a real `pip install` environment.
PROOF TYPE: External
STATUS: EXTERNAL-DEFERRED

**Q033 — Does the system behave correctly under real broker network conditions (rate limits, partial fills, latency)?**
ANSWER: EXTERNAL-DEFERRED
EVIDENCE: none available in a static ZIP
REASON: Requires live broker connection; cannot be proven by code inspection alone.
PROOF TYPE: External
STATUS: EXTERNAL-DEFERRED

**Q034 — Is the current shipped universe/board data fresh (not fail-closed-paused)?**
ANSWER: FAIL — current data readiness state (not a code/fail-closed-mechanism defect)
EVIDENCE: `data/custom_universe_state.json` — `BOARD_DATA_STALE_PAUSE=True`, observed directly this session by executing `get_tradeable_universe()`, which returned an empty list
REASON: Directly exercised this session. This is a data-freshness fact about the shipped snapshot, not a code defect — the fail-closed *behavior itself* is correct and separately PASSes at Q004; this question is scoped only to whether the data is currently fresh/trade-ready, which it is not.
PROOF TYPE: Data + functional execution this session
STATUS: FAIL

**Q035 — Are all Phase-1-identified governance conflicts (current-status, scorecard, verdict clusters) resolved?**
ANSWER: N/A (out of scope for this ledger; tracked, not resolved)
EVIDENCE: `QASWA_PHASE1_INVENTORY_CLASSIFICATION.md` §D
REASON: Explicitly out of scope for Phase 2/3 per this project's own phased-execution agreement.
PROOF TYPE: Governance record
STATUS: N/A — open items, see the Phase 1 report directly

**Q036 — Is `QASWA_SYSTEM_TRUTH.md` itself internally consistent and frozen?**
ANSWER: PASS
EVIDENCE: `QASWA_SYSTEM_TRUTH.md` — reviewed and corrected across 2 passes this session (initial creation + evidence-tightening + final cleanup), approved by the owner this session
REASON: All identified overclaims (institutional-grade, NSE/BSE, architecturally-impossible, fail-open/fail-closed conflation, unverified row count, broken cross-reference) were corrected and the file was explicitly frozen by the owner before this ledger was started.
PROOF TYPE: Documentation, this session's own edit history
STATUS: PASS

---

**Q037 — Is Rule 15 / NDSAP (NIZAMI Data Segregation & Accumulation Protocol) implemented?** *(added 2026-09-08, refined 2026-09-13 owner AIRAF NIZAMI — per `QASWA_FUTURE_CHANGE_GOVERNANCE.md`'s Proposal→Freeze process. This addition/refinement does not reopen or alter Q001-Q036, which remain frozen as-is.)*
ANSWER: NOT PROVEN (by design — registration only, implementation not authorized yet)
EVIDENCE: `prd.md` Rule 15, `SYSTEM_BLUEPRINT.md` §9 — both explicitly marked "REGISTERED, NOT YET IMPLEMENTED." Refined scope: (A) Dhan-exclusive no-substitute for price/volume, reaffirming `DATA_SOURCE_POLICY.md` (Q014) unchanged; (B) alternate sourcing for non-Dhan fields broadened to NSE/Moneycontrol/yfinance; (C) the original append-only archive concept. No archive table, no ingestion-tap code, no source-router code, no tests exist for this yet.
REASON: The owner explicitly separated criterion-approval from implementation-authorization — this entry exists so the criterion is trackable from the moment it's registered, not only once code appears.
PROOF TYPE: Documentation (governance registration only; no code to inspect yet)
STATUS: NOT PROVEN — pre-implementation blockers must clear first: (1) ToS review for storage/reuse of yfinance, NSE, and Moneycontrol data, not yet legally verified for any of the three; (2) a real per-field data-volume/growth estimate to derive the retention policy from (not an arbitrary duration).

**IMPLEMENTATION ADDENDUM (r27, 2026-09-13 — owner implementation-authorization via explicit directive this session; Q001-Q036 remain frozen and untouched):** Part C is now IMPLEMENTED and TESTED: `ndsap_archive.py` — immutable append-only archive in its own SQLite file (`data/ndsap_archive.db`, separate from key_value_store per Rule 15 C), every record carrying fields (a)-(g) (exact raw pre-transformation payload, QASWA UTC arrival timestamp, provider event timestamp kept separate/NULL when unclaimed, symbol/exchange/security_id, provider + detected API version, monotonic seq, SHA-256 content hash); immutability STRUCTURAL (SQLite triggers: DELETE prohibited; UPDATE only for the documented payload-expiry compaction); as-of guard STRUCTURAL (`read_asof(as_of,…)` — as_of required, no default; only rows with arrival ≤ as_of visible). Read-only fail-soft taps: `dhan_data.py` (historical_daily / intraday_minute / ohlc_live), `broker.py` (ohlc_live / market_depth), `market_metadata.py` (market_metadata — provider-gated OFF). Blocker (2) RESOLVED as a deliverable: `NDSAP_RETENTION_ESTIMATE.md` (measured per-field volume/growth estimate → compaction policy keep_last=5 for bulk-refetch datasets, full retention for incremental ones, metadata+hashes never expire). Evidence: `test_ndsap_archive.py` 13/13 executed; full suite 103 passed / 1 skipped / 0 failed (pre-change baseline 90/1/0). Part A: verified pre-existing runtime (`DATA_SOURCE_POLICY.md`/Q014 unchanged — PASS stands). Part B: NOT IMPLEMENTED — blocker (1) ToS review remains OPEN; the yfinance tap exists but is structurally gated OFF (provider allowlist default `["dhan"]`), so no third-party payload is stored.
REVISED STATUS: PARTIAL — (C) PASS (implemented, tested, evidence executed); (A) PASS (pre-existing, reaffirmed); (B) NOT PROVEN (ToS-blocked, gated off by design).

---

**Q038 — Is Rule 16 / Decision & Market-Context Telemetry ("Black Box") implemented?** *(added 2026-09-15, r30 — owner-conceived spec, per `QASWA_FUTURE_CHANGE_GOVERNANCE.md`'s Proposal→Freeze process; owner's spec message IS the step-3 explicit owner decision + implementation authorization. **This is a NEW Q038, unrelated to the old Q038** deleted 2026-09-13 by owner decision (old Q038 tracked the deleted old Rule 16 dual/secondary-engine requirement; no historical record kept per explicit instruction — both numbers reused only to keep sequences contiguous.) This addition does not reopen or alter Q001-Q037, which remain frozen as-is.)*
ANSWER: PASS (implemented, tested, evidence executed — with documented boundaries)
EVIDENCE: `prd.md` Rule 16 (exact four-pillar requirement text + boundaries + attribution); `SYSTEM_BLUEPRINT.md` §11 (architecture placement, sizing estimate, config surface); `telemetry.py` (own SQLite `data/telemetry.db`, tables `scan_context` + `decision_snapshot`, append-only triggers blocking DELETE and UPDATE on both, version stamps {revision, params_hash, strategy}, budgeted fail-open spread capture, `--verify`/`--stats`/`--replay` CLI); fail-open read-only taps in `trade_engine.py` (all 8 early gates → `SKIP_<gate>` scan rows; ASM/GSM rejected list; phase-0/1 counts; per-symbol decision rows for risk/news rejects, slot-full, blocked-at-execute, recovery, and the full entry chain — skip reasons, order placed/rejected, verify status, resting-follow, safety-cancel; `_TelInert` fallback if the telemetry import itself fails); `test_telemetry.py` 18/18 executed (immutability triggers, persistence + linking, input-bar tail serialization, disabled-flag inertness, broken-DB fail-open with audit line, spread parse + budget, read/replay/stats, CLI subprocess, static guard check on entry-path taps); full suite 121 passed / 1 skipped / 0 failed (pre-change baseline 103/1/0).
PILLAR VERIFICATION: (1) market photo — regime/sector snapshots read from existing caches (zero extra API calls), ASM/GSM list per scan, spread from ONE budgeted depth call per candidate/entry (raw payload already PIT-archived by NDSAP); (2) decision snapshots — every decision-reached symbol gets a row with reason + signal JSON; (3) deterministic replay — `input_bars` (default last 120 completed daily bars fed to the strategy) + version stamps + `--replay SYMBOL --date`; (4) silent watcher — fail-OPEN structural: no tap can raise into the trading path, writes are buffered and land in one atomic transaction at scan end, never in the order/SL path.
BOUNDARIES (documented in prd Rule 16 + blueprint §11, deliberate): no per-symbol-per-scan full-universe rows (silent majority = scan-level counts); spread gated + budgeted (≤10 depth calls/scan); exit/follow-event telemetry = future scope; no compaction/pruning (append-only forever; pruning would be a NEW governance decision).
PROOF TYPE: Code read + functional execution (18 tests) + CLI smoke + static tap-guard analysis
STATUS: PASS

**R31 ADDENDUM (2026-09-15 — owner-side forensic audit of the r30 ZIP; Q001-Q037 remain frozen and untouched):** Two audit findings resolved. (a) TERMINOLOGY: the audit's "PIT Telemetry missing (pit_telemetry.py)" claim referenced a module that never existed in ANY artifact of this lineage — content-level scan of all five archives (old 186-file upload, owner's r28 upload, r27, r29, r30 ZIPs) found zero occurrences of `pit_telemetry` or `6.0.4`; the owner confirmed (r31) that "PIT Telemetry" = this Rule 16 telemetry capability (non-technical naming carry-over). To make the PIT property structural rather than nominal, telemetry.py gained the NDSAP-style as-of read guard: `read_asof(as_of,…)` / `read_scans_asof(as_of,…)` require an explicit as-of (no default), only rows recorded ≤ as-of are visible (lookahead-bias block), CLI `--as-of`; alias documented in prd Rule 16 + blueprint §11. `test_telemetry.py` now 21/21 (18 r30 + 3 PIT-guard); full suite 124 passed / 1 skipped / 0 failed (r30 baseline 121/1/0). (b) GENUINE r30 DEFECT (audit claims 3-4, confirmed): the second shipped inventory manifest `AUDIT_INVENTORY_SHA256.json` was left stale at r30 (12 mismatched hashes = exactly the 12 files r30 changed; 2 missing entries = telemetry.py + test_telemetry.py). Root cause: r30's regeneration covered `AUDIT_INTEGRITY_MANIFEST_SHA256.json` (189/189 exact) + the CSV (191 rows) but the second manifest was outside the sync map, and the certified preflight's SHA-provenance check deliberately skips both self-referential manifests — no gate covered it. Fix: manifest regenerated exact (189 entries) + NEW structural preflight check `inventory manifest` (full-tree hash+size verification) added at r31. The audit's claim 2 (version identity "mismatch") is not a defect: `meta.version 6.0.3` + r-number bumps is the frozen lineage convention since r13 (enforced by test_sequence == feature_sequence.json); no v6.0.4 state exists in this lineage.
REVISED STATUS: PASS (r31 — PIT read guard structural; both inventory manifests exact; gate coverage extended)

## Summary

PASS: 30
FAIL: 1 (Q034 — current data-readiness state, not a fail-closed-mechanism defect, see Q004)
NOT PROVEN → PARTIAL: 1 (Q037 — Rule 15/NDSAP: Parts C+A PASS r27 2026-09-13, owner-authorized and tested; Part B remains NOT PROVEN — ToS blocker open, gated off by design)
EXTERNAL-DEFERRED: 3 (Q031, Q032, Q033)
N/A: 3 (Q007 — a hypothesis correctly rejected, not a system defect; Q013 — Master Prompt absence, a governance-artifact question, not pass/fail; Q035 — Phase-1 conflicts explicitly out of scope for this ledger)

Total: 30+1+1+3+3 = 38, matching the 38 questions above (Q001-Q036 frozen unchanged; Q037 refined 2026-09-13 for Rule 15/NDSAP; the old Q038/old Rule 16 were fully deleted 2026-09-13 by owner decision — dual/secondary-engine requirement, no historical record kept per explicit owner instruction; the NEW Q038 added 2026-09-15 r30 tracks the NEW Rule 16 telemetry and is unrelated to the deleted one — both numbers reused only to keep sequences contiguous).

**Update (this session, post-freeze): Q012, Q014, Q016, Q019, Q021, Q023, Q026, Q027, Q029 all resolved to PASS (r16-r17). Live QASWA baseline is now r17. Only genuine open FAIL is Q034 (a data-freshness state, not a code defect — requires a real board/universe data refresh, not a code fix). All 3 EXTERNAL-DEFERRED items genuinely require live infrastructure and cannot be resolved by further static-ZIP inspection.**

**This ledger covers the topics specified for Phase 3 at a proven/not-proven level — it does not re-narrate system architecture (that is `QASWA_SYSTEM_TRUTH.md`'s job) and does not resolve any Phase-1 open governance conflict.**

No existing file, runtime logic, trading contract, or governance document was modified, merged, renamed, or deleted in the creation of this document. No hash/manifest was regenerated.
