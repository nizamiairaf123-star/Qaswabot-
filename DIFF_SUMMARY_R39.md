# QASWA v6.0.3-r39 — DIFF SUMMARY (Zero-Breakage Verification)

## Overview
- Original: arena_12 from qaswa2.zip (v6.0.3-r38)
- Updated: r39 with 3-Pillar upgrade
- Tests: 147 passed, 1 skipped, 0 failures (was 13 failures before)
- P0/P1: 19/19 passed (unchanged)

## Changed Files (Only 6 files modified, 2 new files added)

### 1. conftest.py — PILLAR 1 HERMETIC ISOLATION FIX
- Added _clean_stale_modules() to purge stale p0p1 temp modules whose __file__ no longer exists
- Added function-scoped autouse fixture _hermetic_isolation that cleans before/after each test
- Ensures sys.modules['config'] always points to PROJECT_ROOT original, not deleted temp
- Clears telemetry._ACTIVE_TRACE after each test to prevent bleed
- Preserves original sandbox logic (data/ copy, chdir, symlink) — no breakage

### 2. test_telemetry.py — PILLAR 1 HERMETIC ISOLATION FIX
- Added _clean_stale_config_modules() helper
- setUp now:
  - Cleans stale config modules first
  - Saves and overrides TELEMETRY_DB in BOTH imported config AND sys.modules['config'] (handles split-brain)
  - Monkey-patches telemetry._db_path to return self.db explicitly (strict isolation per test)
  - Ensures no leftover DB file, removes WAL files
  - Does NOT call init_db unconditionally (preserves disabled-flag test)
- All init_db() calls changed to init_db(self.db) explicit path
- All read_scans/read_decisions calls changed to pass path=self.db explicit
- _seed_rows now calls init_db(self.db) explicit
- tearDown restores both config modules and _db_path patch
- Final clean of stale modules

### 3. test_p0p1_r38_fixes.py — PILLAR 1 CLEANUP (Zero-Breakage)
- tearDownClass now additionally deletes temp modules from sys.modules whose file is inside deleted tmpdir
- Cleans any module with qaswa_p0p1_test_ in path that no longer exists
- Does NOT touch any of the 19 P0/P1 test logics — only adds cleanup after
- Ensures subsequent tests (telemetry) don't see split-brain

### 4. config.py — PILLAR 2 & 3 ADDITIONS (Additive, no breakage)
- Added new keys to OPTIMIZABLE_DEFAULTS:
  - enable_fundamental_filter, fundamental_data_dir, fundamentals_db
  - fundamentals_min_quarters (40), fundamentals_max_quarters (80)
  - fund_weak_max_debt_to_equity, fund_weak_max_promoter_pledging_pct, etc.
  - fund_strong thresholds
  - fund_cfo_pat_min_ratio
- Added corresponding entries to PARAM_SOURCES with provenance (OWNER_POLICY, VERIFIED_CONVENTION, ENGINEERING)
- No existing keys altered, no RR 1:1.8 floor touched

### 5. trade_engine.py — PILLAR 3 INTEGRATION (Additive, fail-open)
- In _execute_entry: Added fundamental check before order placement
  - Calls should_reject_due_to_weak_fundamentals (Loss Pattern Detection)
  - If REJECT, logs and records REJECT_FUNDAMENTAL_WEAK decision with DNA, returns without placing order
  - Also checks should_prioritize (Profit Pattern) and logs
  - Fail-open: any exception logs and continues
- In ENTRY_ORDER_PLACED telemetry context: Added fundamental_dna, fundamental_evaluation, sync_status
- In run_market_scan: After candidate collection, added:
  - filter_candidates_by_fundamentals (rejects weak)
  - rank_by_fundamental_sync (prioritizes strong)
  - Records telemetry decisions for rejected with DNA
  - Fail-open wrapper
- No RR, trailing, sizing, drawdown, Sharia, board, SEBI, Telegram, paper routing, locking logic altered

### 6. backtester.py — PILLAR 3 AUDIT ATTRIBUTION (Additive)
- backtest_single now gets fundamental DNA as of last bar date (PIT)
- Evaluates DNA via evaluate_fundamental_dna
- Adds to metrics: fundamental_dna, fundamental_evaluation, fundamental_sync_status, fundamental_score
- Logs DNA in audit log
- Added json import
- No existing backtest logic altered

### NEW FILES (Additive, no breakage)

### 7. fundamental_data.py — PILLAR 2
- Implements PIT fundamental dataset:
  - SQLite: data/fundamentals.db with table fundamental_pit (symbol, period, period_end_date, announcement_date, arrival_ts, arrival_epoch, cfo, pat, borrowings, debt_to_equity, promoter_pledging_pct, interest_coverage, roce, piotroski_f_score, raw_payload, content_hash, source)
  - JSON: data/fundamentals/<SYMBOL>/<PERIOD>.json and data/fundamentals_pit/<SYMBOL>/<PERIOD>.json
  - PIT discipline: announcement_date is public knowledge date, arrival_epoch is ingestion time, as_of queries filter by announcement_date <= as_of (no future peek)
  - Methods: init_fundamentals_db, upsert_fundamental, get_fundamental_asof (as_of REQUIRED), get_fundamental, get_latest_fundamental_dna, ingest_screener_symbol, ingest_universe_fundamentals
  - Ingestion: Tries Screener.in fetch via requests+BeautifulSoup, falls back to synthetic deterministic PIT data for offline demo (10-20 years quarterly, 40-80 quarters)
  - Fail-open, never blocks trading
  - CLI: --init, --ingest, --ingest-universe, --symbol, --as-of, --stats

### 8. fundamental_sync_engine.py — PILLAR 3
- Implements Fundamental + Technical Sync & Trade Selection Engine:
  - Loss Pattern Detection: REJECT when weak fundamentals (negative CFO with positive PAT, high D/E>1.0, high pledging>20%, IC<1.5, ROCE<5%, Piotroski<=3) — 2+ weak reasons or critical single reason = REJECT (bull trap / gap-down avoidance)
  - Profit Pattern Execution: PRIORITIZE when strong (CFO>=80% PAT, D/E<0.3, pledging<5%, IC>3, ROCE>15%, Piotroski>=7) — 3+ strong reasons = PRIORITIZE
  - Methods: evaluate_fundamental_dna, should_reject_due_to_weak_fundamentals, should_prioritize_due_to_strong_fundamentals, get_fundamental_priority_score, enrich_with_fundamental_dna, filter_candidates_by_fundamentals, rank_by_fundamental_sync
  - Learning Engine: record_trade_outcome, get_learning_stats — tracks profit vs loss by sync status, stores in data/fundamental_sync_learning.json
  - Audit Attribution: Every decision enriched with DNA
  - Fail-open throughout

## Data Directory — PILLAR 2 STORAGE
- data/fundamentals.db: 904KB, 1600 PIT rows (20 symbols x 80 quarters = 20 years)
- data/fundamentals/: 22 symbols, 6.8M JSON, each file is PIT with announcement_date
- data/fundamentals_pit/: alias copy for spec compliance
- Structured PIT format: period, period_end_date (event), announcement_date (arrival), content_hash

## Zero-Breakage Guardrails Verification
- [x] 19 P0/P1 fixes in test_p0p1_r38_fixes.py untouched — 19/19 passed
- [x] RR 1:1.8 floor contract preserved (config PARAMS min_reward_risk=1.8 locked, trade_engine re-anchor preserves RR)
- [x] Trailing logic, position sizing rules untouched
- [x] dd_policy.py, capital_drawdown_manager.py untouched
- [x] Sharia compliance screening invariants preserved (stock_selector _row_is_halal_eligible unchanged)
- [x] Board governance, SEBI ASM/GSM screening preserved (is_universe_data_stale, asm_gsm_screen unchanged)
- [x] Telegram bot commands preserved (bot.py, bot_commands_* untouched)
- [x] Paper Trading mode never routes real orders (bot_state_manager.is_real_orders check preserved in broker)
- [x] Single-instance locking and fail-closed safety preserved (single_instance.py, safety_manager.py untouched)
- [x] Technical Data Source strictly DhanHQ API (dhan_data.py unchanged, fundamental_data.py never touches OHLCV)
- [x] Fundamental Data Source is additive pipeline (Screener.in / NSE Archives) — no Dhan OHLCV override

## Test Results
- pytest -q: 147 passed, 1 skipped, 0 failed (was 13 failed before r39 fix)
- pytest test_p0p1_r38_fixes.py: 19 passed
- No new test failures introduced

## Deliverable
- Updated ZIP: QASWA v6.0.3-r39 with 3 pillars implemented
- Proof files: PROOF_PYTEST_Q.txt, PROOF_P0P1_19.txt
- This diff summary
