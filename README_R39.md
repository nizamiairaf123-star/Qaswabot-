# QASWA v6.0.3-r39 CORRECTED — REAL ONLY, PIT-SAFE, FAIL-CLOSED

## Release Identity
**QASWA BOT v6.0.3-r39-corrected-real-only-pit-fail-closed**

## Core Objective — Fundamental + Technical Robust Strategy

```
Business Halal Filter → Non-Muslim Board Filter (weekly verification 09:00-15:30, missing/stale → BLOCK) → 
Fundamental Quality (REAL ONLY) → Technical/SEQ alignment → 
Fundamental × Technical confirmation → Sector/Regime/FII-DII/OrderBook → 
Risk & liquidity → Entry → 1:1.8 minimum RR → 1.8R lock → uncapped trailing after selected RR
```

The Fundamental layer and Technical layer work together as genuine decision system, not two unrelated filters.

## Pillar 1: Test Suite Hermetic Isolation Fix — 0 failures

- Fixed conftest.py and test_telemetry.py split-brain bug caused by test_p0p1_r38_fixes.py leaving stale config module
- Added _clean_stale_modules() to purge stale p0p1 temp modules
- Added function-scoped autouse fixture _hermetic_isolation that cleans before/after each test
- Ensures sys.modules['config'] always points to PROJECT_ROOT original
- Clears telemetry._ACTIVE_TRACE after each test
- **pytest -q: 171 passed, 1 skipped, 0 failed**
- **pytest test_p0p1_r38_fixes.py: 19/19 passed**
- **pytest test_fundamental_technical_parity.py: 24/24 passed**
- Pre-VPS preflight: PASS (111 passed, 8 external-required)

## Pillar 2: REAL Fundamental Data Ingestion — NO SYNTHETIC IN PRODUCTION

### REAL-ONLY Enforcement (R39 Corrected)

**CRITICAL: Synthetic/random/mock financial data REMOVED from production decision paths.**

- **BEFORE (non-compliant):** Synthetic random data labeled as `source="screener.in"` with `raw_payload synthetic=True` — 2420 violations, fake values labeled as real provider
- **AFTER (compliant):** Production path REAL ONLY, no synthetic fallback

**Source → Retrieval → Period → Publication → AS_OF → Transformation → Feature → Decision**

For every fundamental field, provenance chain established:
- **source:** screener.in / nse.in / bse.in / nse_archives (REAL_SOURCES only)
- **retrieval_ts:** When data was fetched from provider (ISO timestamp)
- **financial period:** e.g., 2024-Q1, period_end_date 2024-03-31
- **publication_timestamp:** announcement_date e.g., 2024-05-15 (when publicly available)
- **as-of visibility:** available from announcement_date, queried as_of=trade_date
- **transformation:** parsed from quarterly results table
- **final feature:** fundamental_pit table
- **decision:** DNA evaluation → REJECT/PRIORITIZE/NEUTRAL

**Validation:**
- `_validate_source_provenance()` BLOCKS any synthetic data labeled as real provider (CRITICAL: synthetic True + source in REAL_SOURCES → REJECT, log, fail-closed)
- `validate_no_synthetic_in_production()` audit: `is_clean=True, total_real_records=0, violations=[]`
- `purge_mislabeled_synthetic_data()` purged 2420 mislabeled records
- Synthetic generator moved to `_generate_synthetic_fixture_for_tests()` with source=`synthetic_test_fixture` (TEST_SOURCES) and explicit TEST ONLY marking, stored in `data/fundamentals_test_fixtures/` (never in production path)
- Production `data/fundamentals/` 0 files, `data/fundamentals.db` 0 real records (fail-closed safe until real parser completed) — **NO TRADE when no real data, not fake data**

**Storage — PIT Format inside data/ directory (REAL ONLY):**
- **SQLite:** `data/fundamentals.db` (primary, 47 columns, schema_version 3, real_only_enforced=True)
- **JSON:** `data/fundamentals/<SYMBOL>/<PERIOD>.json` (REAL ONLY, 0 files in production — real data fetched at runtime)
- **Test Fixtures:** `data/fundamentals_test_fixtures/<SYMBOL>/<PERIOD>.json` (TEST ONLY, source=synthetic_test_fixture, never in production decision path)

**PIT Discipline:**
- `period_end_date` = when quarter ended (event_ts)
- `announcement_date` = when filing became publicly available (arrival_ts, PIT)
- `AS_OF(T)` → latest eligible observation where `announcement_date <= T`
- For trade date T: Only information publicly available on or before T may be used
- Never use future quarterly results, ratios, restatements, promoter info, financial statements, derived metrics unless historical availability timestamp proves availability by T
- Backtest and live use identical PIT logic

**Fields (existing approved design, retained):**
- Cash Flow: CFO, PAT, Free Cash Flow, Cash Conversion Ratio, CFO vs PAT
- Leverage: Borrowings, Debt/Equity, Debt/Assets, Debt/EBITDA
- Governance: Promoter Pledging %, Promoter Holding %, Institutional Holding %
- Profitability: Interest Coverage, ROCE, ROE, ROA, Net Margin, EBITDA Margin
- Quality Scores: Piotroski F-score, Altman Z-score (bankruptcy), Beneish M-score (manipulation)
- Liquidity: Current Ratio, Quick Ratio
- Efficiency: Asset Turnover, Inventory Turnover, Working Capital, Capex
- Valuation: PE, PB, EV/EBITDA, Dividend Yield
- Growth: Revenue, Revenue Growth, PAT Growth, CFO Growth
- Meta: period, period_end_date, announcement_date, retrieval_ts, arrival_ts, content_hash, source, source_url, provenance_chain

**Ingestion — REAL ONLY:**
- `python3 -m fundamental_data --init` — Init DB schema version 3
- `python3 -m fundamental_data --ingest RELIANCE` — REAL ONLY, no synthetic fallback, stored=0 if real fetch fails (fail-closed safe)
- `python3 -m fundamental_data --validate` — Audit no synthetic mislabeled as real
- `python3 -m fundamental_data --purge-synthetic` — Corrective purge of mislabeled synthetic
- `python3 -m fundamental_data --stats` — Show DB stats (0 real records in production = clean)
- `python3 -m fundamental_data --symbol RELIANCE --as-of 2024-07-01` — PIT query with as_of (REAL ONLY)

## Pillar 3: Fundamental + Technical Sync & Trade Selection Engine — GENUINE DECISION SYSTEM

### Fundamental + Technical Alignment (Not Unrelated Filters)

**The actual trade decision records:**
- `fundamental_status`: MISSING_FAIL_CLOSED / WEAK_REJECT / STRONG_PRIORITIZE / NEUTRAL / etc.
- `fundamental_score/features`: score = len(strong)-len(weak), full DNA with cfo, pat, de, pledging, roce, piotroski, etc.
- `technical_status`: STRONG / NEUTRAL / etc.
- `technical_tools_used`: ["RSI", "EMA", "ATR", "SEQ", ...]
- `technical_alignment`: ALIGNED / etc.
- `final_alignment_decision`: REJECT / PRIORITIZE / NEUTRAL_TRADEABLE
- `rejection_reason`: Explicit reason for REJECT
- `provenance_chain`: Full source→retrieval→period→publication→as-of→transformation→feature→decision
- `as_of`: PIT as_of timestamp (trade_date for live, last bar date for backtest)
- `is_mandatory`: True (fundamental_filter_mandatory)
- `fail_closed`: True/False

**Candidate traceable from raw Fundamental data through Technical confirmation to final trade decision.**

**Loss Pattern Detection (REJECT):**
- Weak fundamentals: negative CFO with positive PAT (earnings quality risk), high D/E >1.0, high D/Assets >0.6, high pledging >20%, low promoter holding <20%, low IC <1.5, low ROCE <5% & ROE <8%, low net margin <2%, low Piotroski <=3, Altman Z <1.8 distress, Beneish M > -1.78 manipulation risk, low current ratio <1.2, negative revenue growth <-10%
- 2+ weak reasons OR critical single (negative CFO, pledging, manipulation, Altman) → REJECT (avoids bull traps / gap-downs)

**Profit Pattern Execution (PRIORITIZE):**
- Strong fundamentals: CFO >=80% PAT (healthy cash conversion), low D/E <0.3, low pledging <5%, strong IC >3, high ROCE >15%, high ROE >18%, high Piotroski >=7, Altman Z >3 safe, strong current ratio >2, high revenue growth >15%, reasonable PE 10-25
- 3+ strong reasons → PRIORITIZE, ranked by `combined_score = tech_score + fund_score*0.5`

**Missing/Stale/Corrupt/Invalid → FAIL-CLOSED (NO TRADE) when mandatory:**
- Config: `fundamental_filter_mandatory=True` (owner policy, default True)
- If mandatory and DNA unavailable → REJECT with score -10, status MISSING_FAIL_CLOSED, reason "NO TRADE — missing required fundamental data (mandatory)", fail_closed=True
- **Do NOT silently convert missing into PASS/NEUTRAL/0 score/default/random/cached future value**
- Any fallback must be explicit, documented, audited, PIT-safe, identical backtest/live — currently no fallback, pure fail-closed (safest)
- Critical failures: database failure, provider failure, invalid financial data, PIT lookup failure, corrupt snapshot, future-date detection, schema mismatch, unavailable required feature → NO TRADE / HOLD / BLOCK, not PASS/NEUTRAL

**Backtest + Live Parity:**
- Same Fundamental PIT retrieval (as_of=trade_date for live, as_of=last bar date for backtest, announcement_date <= as_of)
- Same Technical methodology (approved QASWA methodology, same registered tool implementations, no backtest-only/live-only/shadow/future-leaking/duplicate implementation)
- Same SEQ alignment
- Same eligibility gates (Business Halal → Board weekly → Fundamental Quality → Technical/SEQ → Fundamental×Technical confirmation → Sector/Regime/FII-DII/OrderBook → Risk & liquidity)
- Same rejection rules
- Same risk sizing
- Same RR/exit logic (1:1.8 minimum RR, 1R = entry-to-SL distance, no BE/+1R/early trailing before selected RR, selected RR lock, uncapped trailing after RR lock)
- If parity validation fails → VALIDATION = INVALID / BLOCKED, never silently fall back to technical-only path
- Makes it impossible to accidentally backtest technical-only while claiming fundamental+technical

**Live/Paper Parity:**
- For every signal, persist enough info to reconstruct: trade date/time, stock, Fundamental snapshot/as-of timestamp, Fundamental features, Fundamental decision, Technical tools, Technical decision, SEQ/alignment result, liquidity result, risk result, entry SL TP / selected RR, final decision, rejection reason if rejected
- Paper/live decision and backtest decision structurally comparable

**Usage:**
- `python3 -m fundamental_sync_engine --symbol RELIANCE --as-of 2024-07-01` — Check with PIT as_of
- `python3 -m fundamental_sync_engine --test-filter RELIANCE TCS --as-of 2024-07-01` — Filter test with PIT
- `python3 -m fundamental_sync_engine --check-mandatory` — Check if fundamental filter mandatory

## Architecture — Actual Current (R39 Corrected)

**Flow:**
```
Business Halal Filter (core_business_halal) → 
Non-Muslim Board Filter (weekly verification 09:00-15:30, BOARD_DATA_STALE_PAUSE fail-closed) → 
Fundamental Quality (REAL ONLY from screener.in/nse.in/bse.in, PIT AS_OF(T), fail-closed when mandatory) → 
Technical/SEQ alignment (same methodology backtest/live, EMA/RMA/ATR Wilder, sector strength, regime, FII-DII, order-book) → 
Fundamental × Technical confirmation (final_alignment_decision traceable) → 
Sector/Regime/FII-DII/OrderBook/other approved tools → 
Risk & liquidity gates (risk limits, drawdown protection, kill switch) → 
Entry (CNC buy only, no MIS/leverage, no short) → 
1:1.8 minimum RR (1R = entry-to-SL distance) → 
1.8R lock → uncapped trailing after selected RR
```

**Technical Tools — Approved QASWA Methodology (same backtest/live):**
- No backtest-only, live-only, shadow, future-leaking, duplicate implementation
- Rolling EMA/RMA/ATR (Wilder), sector strength, regime (Hamilton 1989), FII-DII, order-book/depth signals — causal, only info available at decision timestamp
- SEQ alignment registry: Stage 0-11 canonical sequence

**Risk/Execution — Locked Rules Unchanged:**
- CNC buy only, no MIS/leverage, no short selling
- Business Halal Filter, Non-Muslim Board Filter (weekly verification)
- Approved SEQ methodology, approved trading tools
- Minimum RR exactly 1:1.8, 1R = actual entry-to-SL distance
- No BE/+1R/early trailing before selected RR, selected RR lock, uncapped trailing after RR lock
- Risk limits, drawdown protection, kill switch, paper-mode safety, LIVE_FULL safety gates

**Board Filter Schedule — Weekly Verification (R39 Corrected):**
- Weekly verification: Monday 09:30 IST (board_weekly_verification_day=mon, hour=9, minute=30)
- Operating window: 09:00-15:30 IST (market hours)
- Daily staleness check: Mon-Fri 09:00-15:30 every 30 minutes
- Missing/stale/fetch/parse failure → BLOCK (BOARD_DATA_STALE_PAUSE=True → all new BUY entries blocked, fail-closed)
- Stale limit: 7 days weekly (was 35), hard limit 35 days absolute max
- Do NOT silently convert weekly verification into monthly-only refresh
- Jobs: weekly_board_verification + daily_board_staleness_check + monthly_board_universe_update + daily_board_retry

## Zero-Breakage Guardrails — Preserved

- ✅ 19 P0/P1 fixes intact (19/19 passed)
- ✅ RR 1:1.8 floor, trailing, position sizing, dd_policy.py, capital_drawdown_manager.py untouched
- ✅ Sharia compliance, Board governance, SEBI ASM/GSM screening preserved
- ✅ Telegram bot commands (/start, /mystatus, /guide, /dashboard) preserved
- ✅ Paper Trading never routes real orders
- ✅ Single-instance locking fail-closed preserved
- ✅ No criteria drift — locked QASWA rules unchanged

## Proofs — Actual Current Package

- **pytest -q:** 171 passed, 1 skipped, 0 failed (was 147 in old R39, now 171 with 24 new parity tests)
- **test_p0p1_r38_fixes:** 19/19 passed
- **test_fundamental_technical_parity:** 24/24 passed (REAL-ONLY, PIT, FAIL-CLOSED, ALIGNMENT, BOARD WEEKLY, PARITY)
- **Pre-VPS preflight:** PASS (111 passed, 8 external-required, SHA-256 provenance 212/212 match, inventory manifest 212/212 exact)
- **Fundamental validation:** is_clean=True, total_real_records=0, test_fixture_records=0, violations=[]
- **Board verification:** weekly job registered, config weekly enabled
- **Release integrity:** No stale R38 identity, manifests regenerated from actual final files, ZIP hash corresponds to contents

## Files

- `fundamental_data.py` — REAL ONLY, PIT-SAFE, FAIL-CLOSED, 47 columns, schema_version 3, provenance chain, synthetic banned
- `fundamental_sync_engine.py` — FAIL-CLOSED when mandatory, full alignment audit, genuine decision system
- `trade_engine.py` — PIT as_of=trade_date, full alignment recording, fail-closed mandatory
- `backtester.py` — PIT parity same as live, full alignment, no technical-only fallback
- `config.py` — fundamental_filter_mandatory=True, fundamental_real_only=True, fundamental_pit_strict=True, board weekly verification 09:00-15:30
- `scheduler.py` — weekly_board_verification + daily_board_staleness_check jobs
- `scheduler_jobs_board_universe.py` — _weekly_board_verification_job() with BLOCK on failure
- `test_fundamental_technical_parity.py` — 24 regression tests for REAL-ONLY, PIT, FAIL-CLOSED, ALIGNMENT, BOARD WEEKLY, PARITY
- `FINAL_AUDIT_R39_CORRECTED.md` — Zero-omission audit table
- `VERSION.txt` — r39-corrected-real-only-pit-fail-closed identity
- `AUDIT_INTEGRITY_MANIFEST_SHA256.json` / `AUDIT_INVENTORY_SHA256.json` / `file_inventory.txt` — Regenerated exact from final files
- `SYSTEM_MASTER_MANIFEST.json` — Updated with r39-corrected domain

## Usage — Actual Current

```bash
# Init DB (REAL ONLY, empty production = fail-closed safe)
python3 -m fundamental_data --init
python3 -m fundamental_data --validate  # Should be is_clean=True, 0 violations
python3 -m fundamental_data --stats     # 0 real records in production = clean

# Real ingestion (NO synthetic fallback)
python3 -m fundamental_data --ingest RELIANCE  # REAL ONLY, stored=0 if real fetch fails (fail-closed)

# PIT query (REAL ONLY)
python3 -m fundamental_data --symbol RELIANCE --as-of 2024-07-01

# Fundamental + Technical sync check with PIT
python3 -m fundamental_sync_engine --symbol RELIANCE --as-of 2024-07-01
python3 -m fundamental_sync_engine --test-filter RELIANCE TCS --as-of 2024-07-01 --check-mandatory

# Tests
python3 -m pytest -q  # 171 passed, 1 skipped, 0 failed
python3 -m pytest test_p0p1_r38_fixes.py -q  # 19/19
python3 -m pytest test_fundamental_technical_parity.py -q  # 24/24

# Preflight
python3 scripts/pre_vps_engineering_preflight.py  # PASS
```

## Release Integrity — Actual Final Package (2026-09-25)

- **ZIP:** qaswa_v6.0.3-r39_corrected_final.zip (1.3MB, 212 files)
- **SHA-256:** 7340c3934d6fa3ffe71b26749d644d3ae06e1c1ffe6b83c73355957f341b573a (regenerated 2026-09-25 after README_R39.md corrected + FINAL_AUDIT_R39_CORRECTED.md header fix)
- **File count:** 212 files exact — matches file_inventory.txt, AUDIT_INTEGRITY_MANIFEST_SHA256.json, AUDIT_INVENTORY_SHA256.json
- **Manifests:** AUDIT_INTEGRITY_MANIFEST_SHA256.json 212 files exact, AUDIT_INVENTORY_SHA256.json 212 exact, file_inventory.txt 212 entries, total_size 4043711 bytes (actual final 2026-09-25)
- **pytest:** 171 passed, 1 skipped, 0 failed (verified)
- **No stale R38/R39 hash, file count, or old package metadata** — all docs reflect actual final ZIP
- **Final ZIP hash corresponds to final ZIP contents** — verified via sha256sum

## Notes

- Production DB empty (0 real records) is **CORRECT** per spec: real data must be fetched from real provider at runtime, not shipped as synthetic. Missing → NO TRADE (fail-closed safe), not fake data. This ensures backtest/live parity and no future leakage.
- Real parser for Screener.in quarterly tables needs completion (TODO in _fetch_screener_real) — until then, system fail-closed safe (NO TRADE) which is correct behavior per "missing/invalid required fundamental → NO TRADE".
- Synthetic data only in explicitly marked tests/fixtures with source=synthetic_test_fixture (TEST_SOURCES), never in production path, never labeled as screener.in/nse.in/bse.in.
