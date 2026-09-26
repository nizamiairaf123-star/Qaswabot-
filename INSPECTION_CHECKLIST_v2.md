> **SUPERSEDED — CURRENT AUTHORITY:** `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md` + `prd.md` + `SYSTEM_BLUEPRINT.md` + `docs/MASTER_ZERO_OMISSION_ZIP_INSPECTION_CONSTITUTION_55_SECTIONS.md`. This historical document is retained for audit trail only and must not be used as a current checklist or verdict.

> **SUPERSEDED / REFERENCE-ONLY — current authority: `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md`. This file is preserved only for history/evidence and must not be used as the current criteria source.**

# TRADING BOT — COMPLETE INSPECTION CHECKLIST v2.0
## For New AI Audit — NOTHING MISSED

**Date:** 2026-08-24
**Purpose:** Complete inspection of trading bot ZIP — every file, every function, every calculation
**Level:** Professional developer + trader — nothing missed, not even the smallest detail

---

## ⚠️ CRITICAL WARNINGS (READ FIRST)

### 1. Haram Pending Stocks
**975 out of 1081 stocks currently `haram_pending` flagged** (board-data empty hone ki wajah se ek purana monthly-sync issue, self-healing hai lekin action chahiye — `board_filter_auto.py` real data ke saath chalao). Ye ek Halal-trading-bot ke liye **sabse critical operational risk** hai.

**ACTION REQUIRED:** Run `board_filter_auto.py` with real data before going live.

### 2. Integration Testing Not Done
Real broker/Telegram/scheduler ke saath **poori integration testing kabhi hui hi nahi** (sandbox mein network nahi tha) — live trading se pehle VPS pe test zaroori.

**ACTION REQUIRED:** Full integration test on VPS before live trading.

### 3. Sharia Interpretation
Sharia/Board screening **owner ki apni interpretation** hai, kisi qualified Islamic-finance scholar se certified nahi.

**ACTION REQUIRED:** Confirm with qualified Islamic finance scholar before relying on religious compliance.

---

## 📋 HOW TO USE THIS DOCUMENT

1. Read this document COMPLETELY before starting
2. Check EVERY item in the checklist
3. For EACH file: read it, understand it, verify it
4. Report ALL findings (even small ones)
5. Give GO/NO-GO certificate at the end

---

## 📁 PART 1: FILE INVENTORY

### 1.1 Python Files (87 total)

**CRITICAL FILES (must inspect individually):**

| # | File | Purpose | Inspection Questions |
|---|------|---------|---------------------|
| 1 | bot.py | Telegram bot main entry | All commands registered? Error handler? Mode switching? |
| 2 | config.py | Central configuration | All params registered? Validate_config? PAPER_MODE? |
| 3 | strategy.py | Trading strategy | Signal generation? Phase detection? Macro filter? |
| 4 | strategy_tools.py | Signal generators | All 11 generators working? Parameters optimized? |
| 5 | optimizer.py | Strategy optimizer | Multiple combo? 8x fix? min_reward_risk removed? |
| 6 | backtester.py | Backtest engine | 8x fix? Parity with live? Monte Carlo? |
| 7 | exit_engine.py | Exit toolkit | SL hunt protection? 4 modes? Profit lock? |
| 8 | broker.py | Dhan API wrapper | Order type fix? Copy trading? Error handling? |
| 9 | capital_manager.py | Position sizing | Equal-weight? Slot management? Economics viable? |
| 10 | capital_drawdown_manager.py | Capital & drawdown | Half-Kelly? Daily budget? Survival circuit? |
| 11 | trade_engine.py | Trade execution | Entry chain? Exit chain? Risk gates? |
| 12 | risk_manager.py | Risk management | 19 checks? Correlation? Sector limit? |
| 13 | safety_manager.py | Safety management | Daily loss? Rapid loss? Killswitch? |
| 14 | survival_manager.py | Survival management | Circuit DD? Soft/hard tiers? |
| 15 | portfolio_health.py | Portfolio health | Health score? Multiplier? |
| 16 | regime_manager.py | Regime management | Size multiplier? Slot multiplier? |
| 17 | market_regime.py | Market regime detection | HMM? DS fusion? Multi-factor? |
| 18 | sector_strength.py | Sector strength | STRONG-only filter? Refresh? |
| 19 | correlation_tracker.py | Correlation tracking | Stock/VIX/USDINR? Thresholds? |
| 20 | economics_brain.py | Economics calculations | Breakeven with fees? Max slots? BANDS? |
| 21 | parity_engine.py | Parity engine | R1-R4? PIT-safe? Compounding fix? |
| 22 | walk_forward_validator.py | Walk-forward validation | WFE threshold? Overfit detection? |
| 23 | deployment_manager.py | Deployment management | Approve/reject? Rollback? MC gate? |
| 24 | subscriber_manager.py | Subscriber management | Register/approve/revoke? Term stacking? |
| 25 | stock_selector.py | Stock selection | Halal filter? Universe? Eligibility? |
| 26 | stock_mode_manager.py | Stock mode management | Block/unblock? Recovery? |
| 27 | board_manager.py | Non-Muslim board | Board filter? Name detection? |
| 28 | sharia_manager.py | Sharia management | Zakat? (purification/AAOIFI mechanism intentionally removed per owner instruction) |
| 29 | forever_order_manager.py | GTT order management | 3-layer GTT? Trail follow? |
| 30 | single_instance.py | Single instance guard | Double-run prevention? |
| 31 | startup_recovery.py | Startup recovery | Crash recovery? Position adopt? |
| 32 | bot_state_manager.py | Bot state management | State machine? Mode switching? |
| 33 | signal_broadcaster.py | Signal broadcasting | Admin alerts? Subscriber notify? |
| 34 | simulate_engine.py | Simulation engine | Simulation results? |
| 35 | scheduler.py | Job scheduler | All jobs? Time-aware? |
| 36 | dhan_data.py | Dhan data fetching | Daily cache? Data sanity? |
| 37 | dhan_client.py | Dhan client creation | Client creation? |
| 38 | dhan_live_feed.py | Dhan live feed | Live data? |
| 39 | per_stock_params.py | Per-stock parameters | Get/save params? |
| 40 | news_analyzer.py | News sentiment | LM lexicon? Cache? |
| 41 | fii_dii_tracker.py | FII/DII tracking | Data fetch? Sentiment? |
| 42 | macro_refresh.py | Macro data refresh | Auto-refresh? |
| 43 | liquidity_screen.py | Liquidity screening | ATVR? FoT? |
| 44 | intraday_filter.py | Intraday filter | Series restriction? |
| 45 | corporate_actions.py | Corporate actions | Action check? |
| 46 | monte_carlo.py | Monte Carlo simulation | Bootstrap? DD estimate? |
| 47 | overnight_movers.py | Overnight movers | 9 signals? Edge proof? |
| 48 | entry_follow.py | Entry follow mode | Resting order? Cancel logic? |
| 49 | shadow_log.py | Shadow logging | Signal path tracking? |
| 50 | payment.py | Payment processing | Razorpay? Webhook? |
| 51 | crypto_utils.py | Encryption utilities | Fernet? Encrypt/decrypt? |
| 52 | database.py | Database management | Init DB? Tables? |
| 53 | dd_policy.py | Drawdown policy | Recovery days? |
| 54 | risk_override_manager.py | Risk override | Override logic? |
| 55 | risk_display.py | Risk display | Risk-first block? |
| 56 | report_generator.py | Report generation | Excel report? |
| 57 | build_pdf_report.py | PDF report | PDF generation? |
| 58 | guide_text.py | Guide text | Subscriber guide? Admin guide? |
| 59 | log_setup.py | Logging setup | Telegram handler? |
| 60 | utils.py | Utility functions | JSON save/load? Timezone? |
| 61 | workflow_manager.py | Workflow management | Stage gates? |
| 62 | ruflo_ranker.py | RuFlo ranking | Portfolio ranking? |
| 63 | strategy_validator.py | Strategy validation | Drift detection? |
| 64 | trade_logger.py | Trade logging | P&L tracking? |
| 65 | sebi_manager.py | SEBI management | Fund release? |
| 66 | board_filter_auto.py | Board filter automation | Batch script? |

**MTF FILES (9 total):**

| # | File | Purpose | Inspection Questions |
|---|------|---------|---------------------|
| 67 | mtf/__init__.py | Package init | Imports correct? |
| 68 | mtf/bulk_download.py | Data download | Download logic? |
| 69 | mtf/derive.py | Derived timeframes | Resampling? |
| 70 | mtf/guards.py | Guards | G1-G4? |
| 71 | mtf/probe_depth.py | Depth probe | Depth check? |
| 72 | mtf/stats.py | Statistics | DSR? PBO? |
| 73 | mtf/timeframes.py | Timeframes | TF definitions? |
| 74 | mtf/tournament.py | Tournament | 15-pair? Winner selection? |
| 75 | mtf/warehouse.py | Data warehouse | Save/load? Holdout? |

**TEST FILES (12 total):**

| # | File | Purpose | Inspection Questions |
|---|------|---------|---------------------|
| 76 | test_db_setup.py | Database setup | DB creation? |
| 77 | test_entry_follow.py | Entry follow | Adopt/cancel/hold? |
| 78 | test_full_pipeline.py | Full pipeline | End-to-end? |
| 79 | test_golden.py | Golden tests | Exact values? |
| 80 | test_macro.py | Macro tests | Auto-refresh? |
| 81 | test_overnight.py | Overnight tests | Scanner golden? |
| 82 | test_scheduler_jobs.py | Scheduler tests | Job execution? |
| 83 | test_sequence.py | Sequence tests | Stage 0-11? |
| 84 | test_sharia_and_validation.py | Sharia tests | Halal filter? |
| 85 | test_simulate_engine.py | Simulation tests | Simulation? |
| 86 | scripts/__init__.py | Scripts package | Init? |
| 87 | scripts/live_feed_dry_run.py | Live feed dry run | Dry run? |

### 1.2 Data Files

| # | File | Purpose | Inspection Questions |
|---|------|---------|---------------------|
| 1 | data/CUSTOM_UNIVERSE_FINAL.csv | Stock universe | Halal stocks? Columns correct? |
| 2 | data/MASTER_STOCK_LIST_PERMANENT.csv | Master list | All stocks? |
| 3 | data/*.csv | Various data | Stale? Corrupt? |
| 4 | data/*.json | State files | Valid JSON? Migrated? |
| 5 | data/*.db | Database | Tables exist? |
| 6 | data/*.json.migrated | Migrated files | Dead? Corrupt? |

### 1.3 Documentation Files

| # | File | Purpose | Inspection Questions |
|---|------|---------|---------------------|
| 1 | README.md | Project overview | Accurate? |
| 2 | prd.md | Product requirement | Version correct? Features listed? |
| 3 | SYSTEM_BLUEPRINT.md | Technical architecture | All modules documented? |
| 4 | SYSTEM_MASTER_MANIFEST.json | Master manifest | All domains? |
| 5 | feature_sequence.json | Feature sequence | All features? |
| 6 | VERSION.txt | Version history | All versions? |
| 7 | requirements.txt | Dependencies | All packages? |
| 8 | .env.example | Environment template | All keys? |
| 9 | INSPECTION_CHECKLIST.md | Inspection checklist | This file |
| 10 | INSPECTION_CHECKLIST.json | Inspection checklist (JSON) | This file |

---

## 🔍 PART 2: INSPECTION CHECKLIST

### 2.1 CALCULATION ACCURACY

#### 2.1.1 Compounding Formula
- [ ] optimizer.py: `capital *= (1 + net / smax)` — CORRECT?
- [ ] backtester.py: `capital *= (1 + (net_return * combined_mult) / smax)` — CORRECT?
- [ ] parity_engine.py: `capital *= (1 + (net_pct / 100.0) * combined / smax)` — CORRECT?
- [ ] All three IDENTICAL?
- [ ] No other compounding formulas without /smax?

#### 2.1.2 Position Sizing
- [ ] Backtest qty calculation — CORRECT?
- [ ] Live qty calculation — CORRECT?
- [ ] Subscriber qty calculation — CORRECT?
- [ ] All three use SAME formula?
- [ ] Equal-weight slots (deployable / max_slots)?

#### 2.1.3 min_reward_risk
- [ ] RR contract: exactly 1.8R; not an optimizer dimension.
- [ ] optimizer.py: NOT in search space?
- [ ] PARAM_SOURCES: Registered as OWNER_POLICY?
- [ ] Any remaining min_reward_risk references must be compatibility/read-only and must resolve to exactly 1.8R.

#### 2.1.4 Breakeven Formula
- [ ] economics_brain.py: Fees included?
- [ ] Formula: `(1 + fees/risk) / (1 + R:R)` — CORRECT?
- [ ] Brokerage + statutory + subscription — ALL included?
- [ ] Guard band [30, 45] applied?

#### 2.1.5 SL Hunt Protection
- [ ] exit_engine.py: `_is_sl_hunt()` function exists?
- [ ] Body close rule implemented?
- [ ] Wick analysis implemented?
- [ ] ATR filter implemented?
- [ ] wick_multiplier optimized per stock?
- [ ] candle_body_ratio optimized?
- [ ] candle_wick_ratio optimized?

#### 2.1.6 Candle Pattern Optimization
- [ ] candle_body_ratio — optimized (0.5-3.0)?
- [ ] candle_wick_ratio — optimized (0.5-3.0)?
- [ ] candle_confirmation — optimized (1-5)?
- [ ] candle_volume_mult — optimized (1.0-3.0)?

#### 2.1.7 Order Type
- [ ] Admin entry: ENTRY_ORDER_TYPE (LMT)?
- [ ] Subscriber entry: ENTRY_ORDER_TYPE (LMT)?
- [ ] Admin exit: EXIT_ORDER_TYPE (MKT)?
- [ ] Subscriber exit: EXIT_ORDER_TYPE (MKT)?

### 2.2 WORKFLOW INTEGRITY

#### 2.2.1 Strategy Pipeline
- [ ] Signal generation → Entry → Exit → P&L — CORRECT?
- [ ] All 11 signal generators connected?
- [ ] Phase detection working?
- [ ] Macro filter working?
- [ ] Sector filter working?

#### 2.2.2 Order Execution
- [ ] Entry chain: universe → candles → phase → signal → risk → sizing → order?
- [ ] Exit chain: monitor → exit_engine → market order → fill verify → GTT cancel?
- [ ] Copy trading: admin → subscriber copy → protection order?

#### 2.2.3 Risk Management
- [ ] Daily loss limit (2%) — ACTIVE?
- [ ] Survival circuit — ACTIVE?
- [ ] Killswitch — WORKING?
- [ ] Exit-only mode — WORKING?
- [ ] Correlation check — WORKING?
- [ ] Sector limit — WORKING?
- [ ] Cooldown — WORKING?

#### 2.2.4 Subscriber Lifecycle
- [ ] /start → PAPER_TRIAL?
- [ ] /approve → LIVE_ACTIVE?
- [ ] /revoke → REVOKED?
- [ ] Term stacking working?
- [ ] Expiry → GRACE → EXPIRED?

#### 2.2.5 Mode Switching
- [ ] /paper — WORKING?
- [ ] /live — WORKING?
- [ ] /livefull — WORKING?
- [ ] Help text updated?

### 2.3 SIGNAL GENERATORS

#### 2.3.1 All Signal Generators (11 total)
- [ ] ema_cross — WORKING?
- [ ] rsi_ema — WORKING?
- [ ] breakout — WORKING?
- [ ] support_bounce — WORKING?
- [ ] vwap_bounce — WORKING?
- [ ] bollinger_reversion — WORKING?
- [ ] connors_rsi2 — WORKING?
- [ ] rsi_divergence — WORKING?
- [ ] volume_divergence — WORKING?
- [ ] candle_volume — WORKING?
- [ ] mtf_composite — WORKING?

#### 2.3.2 Multiple Combo Per Stock
- [ ] Optimizer can select any validated 1..11 tool subset; no fixed TOP-N signal cap.
- [ ] All 3 stored with params?
- [ ] Live checks all 3?

### 2.4 MTF (MULTI-TIMEFRAME)

#### 2.4.1 MTF Configuration
- [ ] MTF_ENABLED = True?
- [ ] MTF_TIMEFRAMES = ["5m", "15m", "30m", "60m", "2H", "1D"]?
- [ ] MTF_DOWNLOAD_TFS = ["5m", "15m", "60m", "1D"]?

#### 2.4.2 MTF Tournament
- [ ] 15-pair HTF/LTF tournament?
- [ ] Guards G1-G4 applied?
- [ ] Winner selection correct?

### 2.5 RISK MANAGEMENT

#### 2.5.1 Daily Limits
- [ ] daily_loss_limit_pct = 2.0?
- [ ] max_trades_per_day = 6?
- [ ] max_slots = 8?

#### 2.5.2 Survival Circuit
- [ ] calculate_survival_plan() — WORKING?
- [ ] soft/hard/circuit tiers — CORRECT?
- [ ] min_circuit_dd_pct = 3.0?

#### 2.5.3 Correlation
- [ ] correlation_threshold = 0.85?
- [ ] vix_correlation_threshold = 0.5?
- [ ] usdinr_correlation_threshold = -0.4?

### 2.6 PARITY CHECK (DEEP)

#### 2.6.1 Backtest vs Live
- [ ] Same exit_engine?
- [ ] Same position sizing?
- [ ] Same compounding formula?
- [ ] Same risk gates?
- [ ] Same sector filter?
- [ ] Same correlation check?
- [ ] Same survival circuit?
- [ ] Same stage readiness?

#### 2.6.2 Admin vs Subscriber
- [ ] Same order type?
- [ ] Same qty calculation?
- [ ] Same protection?
- [ ] Same exit logic?

#### 2.6.3 Simulation vs Live
- [ ] Same sizing chain?
- [ ] Same health multiplier?
- [ ] Same regime multiplier?

### 2.7 ERROR HANDLING

#### 2.7.1 Global Error Handler
- [ ] _global_error_handler — EXISTS?
- [ ] User notified?
- [ ] Admin alerted?

#### 2.7.2 API Failures
- [ ] Token expiry — HANDLED?
- [ ] Network failure — HANDLED?
- [ ] Rate limiting — HANDLED?

#### 2.7.3 Data Failures
- [ ] JSON parse error — HANDLED?
- [ ] Database error — HANDLED?
- [ ] File not found — HANDLED?

### 2.8 DATA INTEGRITY

#### 2.8.1 JSON Save/Load
- [ ] save_json() — WORKING?
- [ ] load_json() — WORKING?
- [ ] File existence checks?

#### 2.8.2 Database
- [ ] init_db() — WORKING?
- [ ] All tables created?

#### 2.8.3 Data Files Health
- [ ] .json.migrated files — dead or alive?
- [ ] CSV files — stale or fresh?
- [ ] Database — corrupt or healthy?

### 2.9 PARAM_SOURCES (DEEP)

#### 2.9.1 Registration
- [ ] All parameters registered?
- [ ] Source categories correct?
- [ ] No untagged numbers?

#### 2.9.2 Individual Verification
- [ ] Each number verified against code?
- [ ] Each source category correct?
- [ ] Each detail accurate?

### 2.10 DOCUMENTATION ACCURACY

#### 2.10.1 Documentation vs Code
- [ ] PRD matches code?
- [ ] Blueprint matches code?
- [ ] Manifest matches code?
- [ ] Feature sequence matches code?
- [ ] Version history matches code?

#### 2.10.2 Specific Cross-Checks
- [ ] PRD MTF_ENABLED matches config.py?
- [ ] PRD PHD-FIX status matches Blueprint changelog?
- [ ] PRD "pending" items actually pending or already done?
- [ ] Blueprint warnings included in this checklist?

#### 2.10.3 Referenced Files Check
- [ ] All files referenced in docs exist in ZIP?
- [ ] GOAL_DISCUSSION.md — exists or removed?
- [ ] CHANGELOG.md — exists or removed?
- [ ] HARDCODED_NUMBER_AUDIT.md — exists or removed?
- [ ] PHD_LEVEL_AUDIT.md — exists or removed?
- [ ] DEPLOYMENT_READY.md — exists or removed?
- [ ] deploy.sh — exists or removed?

#### 2.10.4 Comments vs Code
- [ ] All comments accurate?
- [ ] No outdated comments?
- [ ] No misleading comments?

### 2.11 DEAD CODE

#### 2.11.1 Unused Functions
- [ ] Any unused functions?
- [ ] Any unused imports?
- [ ] Any unused variables?

#### 2.11.2 Unreachable Code
- [ ] Any code after return?
- [ ] Any code in except blocks that never runs?
- [ ] Any code in if blocks that never true?

### 2.12 TESTS

#### 2.12.1 Test Execution
- [ ] All tests run?
- [ ] All tests pass?
- [ ] No test failures?

#### 2.12.2 Test Coverage
- [ ] Critical paths tested?
- [ ] Edge cases tested?
- [ ] Error paths tested?

### 2.13 CHAINED-FILE IMPACT

#### 2.13.1 File Dependencies
- [ ] Each file's dependencies identified?
- [ ] Each file's dependents identified?
- [ ] Changes propagate correctly?

#### 2.13.2 Cross-File Verification
- [ ] Changes in one file don't break another?
- [ ] Imports still valid?
- [ ] Function calls still valid?

### 2.14 SYNTAX CHECK

#### 2.14.1 All Files
- [ ] 87 Python files — ALL syntax OK?
- [ ] No import errors?
- [ ] No syntax errors?

### 2.15 SECURITY

#### 2.15.1 Credential Handling
- [ ] Tokens encrypted?
- [ ] Messages deleted after use?
- [ ] No credentials in logs?

#### 2.15.2 Access Control
- [ ] Admin-only commands protected?
- [ ] Subscriber access controlled?
- [ ] No unauthorized access?

---

## 🎯 PART 3: GO/NO-GO CERTIFICATE

### CALCULATION ACCURACY
- [ ] ✅ GO
- [ ] ❌ NO-GO

### WORKFLOW INTEGRITY
- [ ] ✅ GO
- [ ] ❌ NO-GO

### SAFETY & RELIABILITY
- [ ] ✅ GO
- [ ] ❌ NO-GO

### CODE QUALITY
- [ ] ✅ GO
- [ ] ❌ NO-GO

### DOCUMENTATION ACCURACY
- [ ] ✅ GO
- [ ] ❌ NO-GO

### TESTS
- [ ] ✅ GO
- [ ] ❌ NO-GO

### OVERALL
- [ ] ✅ GO
- [ ] ❌ NO-GO

---

## 📝 PART 4: FINDINGS

### Critical Bugs Found:
1. _______________
2. _______________
3. _______________

### Non-Critical Issues:
1. _______________
2. _______________
3. _______________

### Recommendations:
1. _______________
2. _______________
3. _______________

---

## ✅ CERTIFICATION

**Inspector:** _______________
**Date:** _______________
**Status:** _______________
**Reason:** _______________
