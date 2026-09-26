# QASWA v6.0.3 — FRESH FULL 55-SECTION ZERO-OMISSION AUDIT REPORT

**Inspection type:** fresh extracted-ZIP inspection after prior checkpoint; no reliance on previous PASS claims.

## A. ZIP Inventory

- Total files inspected: **140**
- Python source files: **91**
- CSV files: **5**
- JSON files: **6**
- SQLite databases: **1**
- Markdown/text documents: **26**
- Shell deployment scripts: **3**
- systemd service files: **1**
- Nested archives: **0**
- Generated Python/cache artifacts in final package: **0**

Every extracted artifact was enumerated and classified. The SHA-256 inventory was regenerated after the inspection.

## B. Confirmed Findings

### F-001 — P0 — Decision-critical universe data is not ready
- **File:** `data/CUSTOM_UNIVERSE_FINAL.csv`
- **Location:** all 1,074 rows
- **Problem:** `sector`, `industry`, `market_cap`, `turnover_liquid_ok`, `atvr_pct`, `frequency_of_trading_pct` are completely unknown/missing.
- **Impact:** the universe cannot safely pass decision-critical sector/liquidity/market-cap gates.
- **Required action:** real provider refresh; never substitute zeros/placeholders/guesses.
- **Status:** OPEN / RELEASE BLOCKER.

### F-002 — P1 — Local environment lacks declared runtime dependencies
- **Evidence:** full pytest collection is blocked by missing `dhanhq`, `telegram`, `apscheduler`, `skopt`.
- **Impact:** broker, Telegram, scheduler, optimizer and dependent integration suites cannot be executed here.
- **Required action:** install from declared requirements in a clean environment and rerun.
- **Status:** EXTERNAL TEST REQUIRED.

### F-003 — P1 — Decision-critical economics fallback was fail-open (FIXED)
- **File:** `capital_manager.py`
- **Problem:** verified economics failure previously substituted static fallback values and could continue the economic gate.
- **Fix:** verified economics failure now returns `False`/BLOCK; verified friction calculation failure also BLOCKS.
- **Verification:** source updated and compilation passes.
- **Status:** FIXED; dependency-backed regression still required.

### F-004 — P1 — Parity economics gate was fail-open (FIXED)
- **File:** `parity_engine.py`
- **Problem:** economics gate helper failure previously returned ALLOW.
- **Fix:** helper failure now returns REJECT/fail-closed.
- **Verification:** source updated and compilation passes.
- **Status:** FIXED; full optimizer/backtest regression requires `scikit-optimize`/broker dependencies.

### F-005 — P2 — Legacy financial-ratio columns remain in the custom CSV
- **Fields:** `debt_mcap_pct`, `cash_mcap_pct`, `haram_income_pct`, `illiquid_asset_pct`.
- **Observation:** all 1,074 rows are zero-valued; active selector comments say balance-sheet ratios are not part of the current eligibility gate.
- **Risk:** future AI/operator may misinterpret these as verified screening data.
- **Action:** retain only if explicitly required for backward compatibility; otherwise remove in a separate owner-authorized schema cleanup.
- **Status:** DOCUMENTED, not silently repurposed.

### F-006 — P1 — Board invariant data contains one rejected row
- **File:** `CUSTOM_UNIVERSE_FINAL.csv`
- **Observation:** `non_muslim_board=False` for 1 row and True for 1,073 rows.
- **Impact:** the current all-True invariant test fails and the row is correctly blocked.
- **Action:** real board refresh; do not manually flip the value.
- **Status:** OPEN / DATA BLOCKER.

### F-007 — P2 — Dependency versions are unpinned
- **File:** `requirements.txt`
- **Observation:** packages are declared without exact versions; file explicitly defers freezing to deployment.
- **Impact:** reproducibility is not proven.
- **Action:** after a successful clean install, generate and ship a verified lock file.
- **Status:** EXTERNAL/DEPLOYMENT TASK.

## C. Local Verification Scorecard

- **ZIP integrity:** PASS
- **Python compile:** 91/91 PASS
- **JSON parse:** 6/6 PASS
- **CSV content:** 5/5 inspected; blocker found
- **DB:** 1/1 inspected
- **test_sequence:** 67 PASS / 7 FAIL
- **targeted pytest:** 8 PASS / 0 FAIL (3 suites)
- **release preflight:** NOT READY
- **known fail-open fixes:** 2 confirmed and updated
- **secrets static scan:** No confirmed credential found
- **nested archives:** 0
- **generated caches in final package:** 0

## D. External / Untested Confidence Scorecard

| Area | Code-level confidence | Current evidence | Required proof |
|---|---|---|---|
| Dhan API/auth | Medium-High | UNKNOWN | Real Dhan credentials + authenticated API smoke test on VPS |
| Decision-critical market metadata | Low until refreshed | BLOCKED | Populate sector/industry/market_cap/liquidity from real provider; validate all 1,074 rows |
| Board-data freshness | Medium | UNKNOWN/BLOCKED | Run real board refresh and prove source/timestamp/freshness |
| Liquidity freshness | Medium | UNKNOWN/BLOCKED | Run historical OHLCV refresh; independently recompute ATVR/FoT |
| Order placement/fill/reject | Medium-High | UNKNOWN | Controlled paper/sandbox or broker execution test |
| WebSocket reconnect | High code confidence | UNKNOWN | Force disconnect and observe resubscribe/watchdog |
| Scheduler timing | High code confidence | UNKNOWN | VPS observation across market clock and missed/overlap jobs |
| Crash/restart recovery | High code confidence | UNKNOWN | Kill at entry/ack/fill/exit/persistence and reconcile after restart |
| Telegram/admin lifecycle | Medium-High | UNKNOWN | Real command auth/replay/unauthorized tests |
| Payment webhook | Medium | UNKNOWN | Sandbox signature/duplicate/replay/invalid payload tests |
| Clean deployment | High code confidence | UNKNOWN | Fresh VPS: install→configure→validate→start→health→restart |
| Broker reconciliation | High code confidence | UNKNOWN | Controlled position/order mismatches and expected actions |

## E. 55-Section Ledger

| Sec | Area | Class | Status | Evidence |
|---:|---|---|---|---|
| 1 | ZIP Integrity | LOCAL | **PASS** | Archive extracted completely; no corrupt entries or nested archives. |
| 2 | Complete File Inventory | LOCAL | **PASS** | All extracted artifacts enumerated; generated caches removed before packaging. |
| 3 | Source Code — All Files | LOCAL | **PASS** | 91 Python files AST/compile checked; individual source surfaces included in static audit. |
| 4 | Import / Dependency Graph | LOCAL/HYBRID | **CONDITIONAL** | Internal imports resolve statically; runtime imports blocked locally by absent third-party packages. |
| 5 | Requirements / Package Installation | HYBRID/EXTERNAL | **UNKNOWN** | requirements.txt declares required packages but clean install cannot be proven in this offline environment. |
| 6 | Configuration Audit | LOCAL | **PASS** | Config and provenance registry inspected; manifest/sequence consistency checks pass. |
| 7 | Every Numeric Value Audit | LOCAL/HYBRID | **CONDITIONAL** | 193 registered values verified by watchdog; remaining semantic/external validation is not fully executable here. |
| 8 | CSV / Tabular Data — Complete Content Audit | LOCAL | **PASS WITH BLOCKER** | All 5 CSVs inspected; CUSTOM_UNIVERSE_FINAL has 1,074 unknown decision-critical metadata rows. |
| 9 | Data Semantic Audit | HYBRID/EXTERNAL | **UNKNOWN** | Column meaning/wiring inspected; live source truth/freshness requires external evidence. |
| 10 | Data Provenance | HYBRID/EXTERNAL | **UNKNOWN** | Provider contract exists; provider is intentionally unconfigured and real provenance cannot be proven locally. |
| 11 | JSON / State File Audit | LOCAL | **PASS WITH BLOCKER** | All JSON parsed; custom universe state correctly remains paused. |
| 12 | Database Audit | LOCAL | **PASS** | SQLite schema/table/index and 17 key-value rows inspected; runtime reconciliation remains external. |
| 13 | Logs / Audit Files | LOCAL | **CONDITIONAL** | Local logs inspected; live rotation/runtime behavior needs VPS evidence. |
| 14 | Cache / Generated / Temporary Files | LOCAL | **PASS** | Generated caches removed from release package; no nested archive found. |
| 15 | Sharia / Custom Compliance Audit | HYBRID/EXTERNAL | **CONDITIONAL** | Runtime gate is fail-closed and custom criteria are wired; live source freshness cannot be proven. |
| 16 | Liquidity Audit | HYBRID/EXTERNAL | **BLOCKED** | Formula/wiring inspected; actual 1,074-row liquidity fields are unpopulated. |
| 17 | Market Data Audit | HYBRID/EXTERNAL | **UNKNOWN/BLOCKED** | Adapter paths inspected; live market-data source, timestamps and failure behavior require external run. |
| 18 | Strategy Mathematics | LOCAL/HYBRID | **CONDITIONAL** | Core formula paths and existing tests inspected; full dependency-backed numerical suite not executable locally. |
| 19 | Look-Ahead / Data Leakage | LOCAL/HYBRID | **CONDITIONAL** | Closed-bar/PIT patterns and shift usage inspected; complete empirical backtest evidence requires full runtime dependencies. |
| 20 | Backtest Audit | LOCAL/HYBRID | **CONDITIONAL** | Backtest code and friction path inspected; full execution blocked by missing dhanhq dependency. |
| 21 | Optimizer Audit | LOCAL/HYBRID | **CONDITIONAL** | Optimizer source and watchdogs inspected; skopt dependency prevents full runtime execution. |
| 22 | Exit Engine — Zero-Omission | LOCAL/HYBRID | **CONDITIONAL** | Exit implementation/tests inspected; broker-side behavior remains external. |
| 23 | Risk Engine | LOCAL/HYBRID | **CONDITIONAL** | Risk source and tests inspected; broker/margin integration remains external. |
| 24 | Order Engine | HYBRID/EXTERNAL | **UNKNOWN** | Order construction/rejection handling inspected; no real broker execution evidence. |
| 25 | Live / Paper Separation | HYBRID/EXTERNAL | **CONDITIONAL** | State/gate wiring inspected; real broker safety separation requires controlled runtime test. |
| 26 | Scheduler Audit | HYBRID/EXTERNAL | **UNKNOWN** | Scheduler source inspected; APScheduler missing locally and real timing/restart needs VPS. |
| 27 | Failure / Fail-Closed Audit | LOCAL/HYBRID | **PASS WITH FIX** | Confirmed economics/parity fail-open paths were changed to BLOCK/REJECT; recompiled successfully. |
| 28 | Network Failure Audit | HYBRID/EXTERNAL | **UNKNOWN** | Code paths inspected; injected network failures require live/integration environment. |
| 29 | Crash / Restart Audit | HYBRID/EXTERNAL | **UNKNOWN** | Recovery code inspected; controlled kill/restart evidence requires VPS/broker state. |
| 30 | Telegram / Admin Control Audit | HYBRID/EXTERNAL | **UNKNOWN** | Command/auth code inspected; python-telegram-bot unavailable locally and live command evidence absent. |
| 31 | Subscription / Copy Trading | HYBRID/EXTERNAL | **UNKNOWN** | Lifecycle code inspected; payment/Dhan linked-account integration requires external tests. |
| 32 | Deployment Audit | HYBRID/EXTERNAL | **UNKNOWN** | Scripts/service inspected; clean-machine install/start/restart cannot be proven locally. |
| 33 | Production Package Hygiene | LOCAL | **PASS** | Caches removed; no nested archives; release artifacts categorized. |
| 34 | Documentation Audit | LOCAL | **PASS WITH HISTORICAL NOTES** | Canonical docs and audit docs inspected; historical reports are explicitly non-authoritative. |
| 35 | Version / Release Audit | LOCAL | **PASS** | QASWA v6.0.3 consistent across VERSION, manifest, sequence and canonical docs. |
| 36 | Manifest Audit | LOCAL | **PASS** | Manifest↔package inventory checked; read-order and audit references exist. |
| 37 | Security Audit | LOCAL/HYBRID | **CONDITIONAL** | Static secret scan and dangerous-call review performed; filesystem/runtime permissions require deployment evidence. |
| 38 | Test Audit | LOCAL | **PASS WITH FAILURES** | Tests inspected and executed where possible; 67 sequence passes/7 expected blockers, plus dependency-blocked suites. |
| 39 | Independent Recalculation | LOCAL | **CONDITIONAL** | Data/statistical calculations independently inspected; complete financial execution suite blocked by dependencies. |
| 40 | Cross-File Consistency | LOCAL | **PASS WITH FINDINGS** | Canonical chain and lifecycle references checked; decision-data readiness mismatch is correctly exposed as blocker. |
| 41 | Dead Code / Dead Configuration | LOCAL | **CONDITIONAL** | Dead-code watchdog passes for known removed module; full semantic dead-code proof is not complete. |
| 42 | Data Update Pipeline | HYBRID/EXTERNAL | **BLOCKED** | Refresh pipeline is fail-closed but real provider is not configured and candidate data absent. |
| 43 | Time / Date / Timezone | LOCAL/HYBRID | **CONDITIONAL** | IST/UTC patterns inspected; real scheduler/market-clock observation requires VPS. |
| 44 | State Machine | LOCAL/HYBRID | **CONDITIONAL** | State transitions/guards inspected; runtime transition injection remains external. |
| 45 | Capital Deployment | LOCAL/HYBRID | **CONDITIONAL** | Deployment stage and risk wiring inspected; live capital/broker reconciliation requires external evidence. |
| 46 | Reconciliation | HYBRID/EXTERNAL | **UNKNOWN** | Reconciliation code exists; controlled broker-vs-bot mismatch test not executable here. |
| 47 | Failure-Injection Matrix | HYBRID/EXTERNAL | **UNKNOWN** | Matrix documented; real service failures need integration environment. |
| 48 | False-Pass Audit | LOCAL/HYBRID | **PASS WITH FIX** | Fail-open economics paths identified and corrected; remaining exception sites are classified by impact. |
| 49 | Complete Runtime Trace | HYBRID/EXTERNAL | **CONDITIONAL** | Static end-to-end chain traced; live broker/external evidence absent. |
| 50 | Final Release Audit | LOCAL/HYBRID | **NOT READY** | Gate cannot close while decision-critical data and external evidence remain missing. |
| 51 | Final Verdict Rule | LOCAL | **PASS** | Current verdict follows constitution: NOT READY due blockers. |
| 52 | Mandatory Final Report | LOCAL | **PASS** | Fresh report includes inventory, findings, data, dependencies, deployment/runtime and separate scorecards. |
| 53 | Zero-Omission Completion Certificate | LOCAL/HYBRID | **NOT COMPLETE** | Cannot honestly certify external/runtime portions without external evidence. |
| 54 | No Shortcut Rule | LOCAL | **PASS** | Audit did not treat compile/tests/README as sufficient proof. |
| 55 | Final Instruction to Any AI Receiving This ZIP | LOCAL | **PASS** | Onboarding/read-order/inspection execution contract bundled and references current evidence. |

## F. Independent Data Audit

| Dataset | Rows | Cols | Critical observations |
|---|---:|---:|---|
| `data/CUSTOM_UNIVERSE_FINAL.csv` | 1,074 | 27 | six decision-critical fields completely missing; one board flag false |
| `data/MASTER_STOCK_LIST_PERMANENT.csv` | 2,158 | 13 | populated reference data; freshness/source still external |
| `data/BOARD_TRUE_100_NON_MUSLIM.csv` | 1,080 | 2 | reference dataset; current freshness external |
| `data/BOARD_FALSE_HAS_MUSLIM.csv` | 181 | 4 | reference rejection dataset; current freshness external |
| `data/lm_finance_wordlists.csv` | 3,716 | 5 | populated static wordlist; no nulls detected |
| `data/trading_bot.db` | 17 | 2 | key-value store; runtime state reconciliation external |

## G. Test Results

- `python -m compileall -q .`: **PASS (91/91 Python files)**.
- `python test_sequence.py`: **67 PASS / 7 FAIL**; failures are data-readiness/current-environment blockers, not hidden PASS.
- Targeted `pytest`: **8 PASS / 0 FAIL** for `test_market_metadata.py`, `test_sharia_and_validation.py`, `test_simulate_engine.py`.
- Full pytest collection cannot complete because declared third-party runtime packages are absent in this environment.
- `scripts/release_preflight.py`: **NOT READY**, correctly blocking on six missing decision-critical fields.

## H. Fix Verification

- `capital_manager.py` fail-open economics fallback changed to explicit BLOCK.
- `parity_engine.py` fail-open economics gate changed to explicit REJECT.
- Both files compile after modification.
- Full dependency-backed regression is still required before these fixes can be considered production-proven.

## I. Canonical Consistency

- Release identity remains **QASWA v6.0.3**.
- PRD, Blueprint, Manifest, Feature Sequence, 55-section Constitution, Audit Execution Contract and current Scorecard reference the same release and current NOT READY truth.
- Historical audit documents are retained as historical evidence and are not authoritative for current readiness.
- No new trading functionality was added by this audit/fix pass.

## J. Final Verdict

**🔴 NOT READY**

**Reason:** the package is substantially inspected and the confirmed fail-open economics defects were fixed, but the release cannot be certified because decision-critical universe data is incomplete and required dependency-backed/VPS/external runtime evidence is not available in this environment.

## K. Zero-Omission Completion Certificate

**NOT ISSUED.** The local extracted ZIP inventory and local artifact categories were inspected, but the auditor cannot honestly certify the complete external/runtime portions without real provider, broker, scheduler, network, deployment and recovery evidence.

