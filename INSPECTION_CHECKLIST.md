> **SUPERSEDED — CURRENT AUTHORITY:** `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md` + `prd.md` + `SYSTEM_BLUEPRINT.md` + `docs/MASTER_ZERO_OMISSION_ZIP_INSPECTION_CONSTITUTION_55_SECTIONS.md`. This historical document is retained for audit trail only and must not be used as a current checklist or verdict.

> **SUPERSEDED / REFERENCE-ONLY — current authority: `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md`. This file is preserved only for history/evidence and must not be used as the current criteria source.**

# TRADING BOT — COMPLETE INSPECTION CHECKLIST
## For New AI Audit — Every Detail Covered

**Date:** 2026-08-24
**Purpose:** Complete inspection of trading bot ZIP — nothing should be missed
**Level:** PHD-level deep analysis — every file, every function, every calculation

---

## 📋 HOW TO USE THIS DOCUMENT

1. Read this document COMPLETELY
2. Check EVERY item in the checklist
3. Report ALL findings (even small ones)
4. Give GO/NO-GO certificate at the end

---

## 📁 FILE INVENTORY

### Python Files (87 total)

| # | File | Purpose | Critical? |
|---|------|---------|-----------|
| 1 | backtester.py | Backtest engine | ✅ CRITICAL |
| 2 | board_filter_auto.py | Board filter automation | 🟡 MEDIUM |
| 3 | board_manager.py | Non-Muslim board management | ✅ CRITICAL |
| 4 | bot.py | Telegram bot main entry | ✅ CRITICAL |
| 5 | bot_state_manager.py | Bot state management | ✅ CRITICAL |
| 6 | broker.py | Dhan API wrapper | ✅ CRITICAL |
| 7 | build_pdf_report.py | PDF report generation | 🟢 LOW |
| 8 | capital_drawdown_manager.py | Capital & drawdown management | ✅ CRITICAL |
| 9 | capital_manager.py | Position sizing & slots | ✅ CRITICAL |
| 10 | config.py | Central configuration | ✅ CRITICAL |
| 11 | corporate_actions.py | Corporate actions check | 🟡 MEDIUM |
| 12 | correlation_tracker.py | Correlation tracking | 🟡 MEDIUM |
| 13 | crypto_utils.py | Encryption utilities | ✅ CRITICAL |
| 14 | database.py | Database management | ✅ CRITICAL |
| 15 | dd_policy.py | Drawdown policy | 🟡 MEDIUM |
| 16 | deployment_manager.py | Deployment management | ✅ CRITICAL |
| 17 | dhan_client.py | Dhan client creation | ✅ CRITICAL |
| 18 | dhan_data.py | Dhan data fetching | ✅ CRITICAL |
| 19 | dhan_live_feed.py | Dhan live feed | 🟡 MEDIUM |
| 20 | economics_brain.py | Economics calculations | ✅ CRITICAL |
| 21 | entry_follow.py | Entry follow mode | ✅ CRITICAL |
| 22 | exit_engine.py | Exit toolkit | ✅ CRITICAL |
| 23 | fii_dii_tracker.py | FII/DII tracking | 🟡 MEDIUM |
| 24 | forever_order_manager.py | GTT order management | ✅ CRITICAL |
| 25 | guide_text.py | Guide text | 🟢 LOW |
| 26 | intraday_filter.py | Intraday filter | 🟡 MEDIUM |
| 27 | liquidity_screen.py | Liquidity screening | 🟡 MEDIUM |
| 28 | log_setup.py | Logging setup | 🟢 LOW |
| 29 | macro_refresh.py | Macro data refresh | 🟡 MEDIUM |
| 30 | market_regime.py | Market regime detection | ✅ CRITICAL |
| 31 | monte_carlo.py | Monte Carlo simulation | 🟡 MEDIUM |
| 32 | mtf/__init__.py | MTF package init | 🟢 LOW |
| 33 | mtf/bulk_download.py | MTF data download | 🟡 MEDIUM |
| 34 | mtf/derive.py | MTF derived timeframes | 🟡 MEDIUM |
| 35 | mtf/guards.py | MTF guards | 🟡 MEDIUM |
| 36 | mtf/probe_depth.py | MTF depth probe | 🟢 LOW |
| 37 | mtf/stats.py | MTF statistics | 🟡 MEDIUM |
| 38 | mtf/timeframes.py | MTF timeframes | 🟡 MEDIUM |
| 39 | mtf/tournament.py | MTF tournament | ✅ CRITICAL |
| 40 | mtf/warehouse.py | MTF data warehouse | 🟡 MEDIUM |
| 41 | news_analyzer.py | News sentiment analysis | 🟡 MEDIUM |
| 42 | optimizer.py | Strategy optimizer | ✅ CRITICAL |
| 43 | overnight_movers.py | Overnight movers | 🟡 MEDIUM |
| 44 | parity_engine.py | Parity engine | ✅ CRITICAL |
| 45 | payment.py | Payment processing | 🟡 MEDIUM |
| 46 | per_stock_params.py | Per-stock parameters | ✅ CRITICAL |
| 47 | portfolio_health.py | Portfolio health | ✅ CRITICAL |
| 48 | regime_manager.py | Regime management | ✅ CRITICAL |
| 49 | report_generator.py | Report generation | 🟢 LOW |
| 50 | risk_display.py | Risk display | 🟢 LOW |
| 51 | risk_manager.py | Risk management | ✅ CRITICAL |
| 52 | risk_override_manager.py | Risk override | 🟡 MEDIUM |
| 53 | ruflo_ranker.py | RuFlo ranking | 🟡 MEDIUM |
| 54 | safety_manager.py | Safety management | ✅ CRITICAL |
| 55 | scheduler.py | Job scheduler | ✅ CRITICAL |
| 56 | sebi_manager.py | SEBI management | 🟡 MEDIUM |
| 57 | sector_strength.py | Sector strength | ✅ CRITICAL |
| 58 | shadow_log.py | Shadow logging | 🟡 MEDIUM |
| 59 | sharia_manager.py | Sharia management | 🟡 MEDIUM |
| 60 | signal_broadcaster.py | Signal broadcasting | ✅ CRITICAL |
| 61 | simulate_engine.py | Simulation engine | ✅ CRITICAL |
| 62 | single_instance.py | Single instance guard | ✅ CRITICAL |
| 63 | startup_recovery.py | Startup recovery | ✅ CRITICAL |
| 64 | stock_mode_manager.py | Stock mode management | ✅ CRITICAL |
| 65 | stock_selector.py | Stock selection | ✅ CRITICAL |
| 66 | strategy.py | Trading strategy | ✅ CRITICAL |
| 67 | strategy_tools.py | Strategy tools | ✅ CRITICAL |
| 68 | strategy_validator.py | Strategy validation | 🟡 MEDIUM |
| 69 | subscriber_manager.py | Subscriber management | ✅ CRITICAL |
| 70 | survival_manager.py | Survival management | ✅ CRITICAL |
| 71 | trade_engine.py | Trade execution engine | ✅ CRITICAL |
| 72 | trade_logger.py | Trade logging | 🟡 MEDIUM |
| 73 | utils.py | Utility functions | ✅ CRITICAL |
| 74 | walk_forward_validator.py | Walk-forward validation | ✅ CRITICAL |
| 75 | workflow_manager.py | Workflow management | 🟡 MEDIUM |

### Test Files (12 total)

| # | File | Purpose |
|---|------|---------|
| 76 | test_db_setup.py | Database setup test |
| 77 | test_entry_follow.py | Entry follow test |
| 78 | test_full_pipeline.py | Full pipeline test |
| 79 | test_golden.py | Golden test |
| 80 | test_macro.py | Macro test |
| 81 | test_overnight.py | Overnight test |
| 82 | test_scheduler_jobs.py | Scheduler test |
| 83 | test_sequence.py | Sequence test |
| 84 | test_sharia_and_validation.py | Sharia test |
| 85 | test_simulate_engine.py | Simulation test |
| 86 | scripts/__init__.py | Scripts package |
| 87 | scripts/live_feed_dry_run.py | Live feed dry run |

### Data Files

| # | File | Purpose |
|---|------|---------|
| 1 | data/CUSTOM_UNIVERSE_FINAL.csv | Stock universe |
| 2 | data/MASTER_STOCK_LIST_PERMANENT.csv | Master stock list |
| 3 | data/*.csv | Various stock data |
| 4 | data/*.json | State files |
| 5 | data/*.db | Database |

### Documentation Files

| # | File | Purpose |
|---|------|---------|
| 1 | README.md | Project overview |
| 2 | prd.md | Product requirement |
| 3 | SYSTEM_BLUEPRINT.md | Technical architecture |
| 4 | SYSTEM_MASTER_MANIFEST.json | Master manifest |
| 5 | feature_sequence.json | Feature sequence |
| 6 | VERSION.txt | Version history |
| 7 | requirements.txt | Dependencies |
| 8 | .env.example | Environment template |

---

## 🔍 INSPECTION CHECKLIST

### 1. CALCULATION ACCURACY

#### 1.1 Compounding Formula
- [ ] optimizer.py: `capital *= (1 + net / smax)` — CORRECT?
- [ ] backtester.py: `capital *= (1 + (net_return * combined_mult) / smax)` — CORRECT?
- [ ] parity_engine.py: `capital *= (1 + (net_pct / 100.0) * combined / smax)` — CORRECT?
- [ ] All three IDENTICAL?

#### 1.2 Position Sizing
- [ ] Backtest qty calculation — CORRECT?
- [ ] Live qty calculation — CORRECT?
- [ ] Subscriber qty calculation — CORRECT?
- [ ] All three use SAME formula?

#### 1.3 min_reward_risk
- [ ] RR contract: exactly 1.8R; not an optimizer dimension.
- [ ] optimizer.py: NOT in search space?
- [ ] PARAM_SOURCES: Registered?

#### 1.4 Breakeven Formula
- [ ] economics_brain.py: Fees included?
- [ ] Formula: `(1 + fees/risk) / (1 + R:R)` — CORRECT?
- [ ] Brokerage + statutory + subscription — ALL included?

#### 1.5 SL Hunt Protection
- [ ] exit_engine.py: `_is_sl_hunt()` function exists?
- [ ] Body close rule implemented?
- [ ] Wick analysis implemented?
- [ ] ATR filter implemented?
- [ ] wick_multiplier optimized per stock?

#### 1.6 Candle Pattern Optimization
- [ ] candle_body_ratio — optimized?
- [ ] candle_wick_ratio — optimized?
- [ ] candle_confirmation — optimized?
- [ ] candle_volume_mult — optimized?

### 2. WORKFLOW INTEGRITY

#### 2.1 Strategy Pipeline
- [ ] Signal generation → Entry → Exit → P&L — CORRECT?
- [ ] All signal generators connected?
- [ ] Phase detection working?

#### 2.2 Order Execution
- [ ] Admin order type: ENTRY_ORDER_TYPE (LMT)?
- [ ] Subscriber order type: ENTRY_ORDER_TYPE (LMT)?
- [ ] Exit order type: EXIT_ORDER_TYPE (MKT)?

#### 2.3 Copy Trading
- [ ] Admin trade → Subscriber copy — CORRECT?
- [ ] Subscriber qty calculation — CORRECT?
- [ ] Protection order (GTT) — CORRECT?

#### 2.4 Risk Management
- [ ] Daily loss limit (2%) — ACTIVE?
- [ ] Survival circuit — ACTIVE?
- [ ] Killswitch — WORKING?
- [ ] Exit-only mode — WORKING?

### 3. SIGNAL GENERATORS

#### 3.1 All Signal Generators (11 total)
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

#### 3.2 Multiple Combo Per Stock
- [ ] Optimizer can select any validated 1..11 tool subset; no fixed TOP-N signal cap.
- [ ] All 3 stored with params?
- [ ] Live checks all 3?

### 4. MTF (MULTI-TIMEFRAME)

#### 4.1 MTF Configuration
- [ ] MTF_ENABLED = True?
- [ ] MTF_TIMEFRAMES = ["5m", "15m", "30m", "60m", "2H", "1D"]?
- [ ] MTF_DOWNLOAD_TFS = ["5m", "15m", "60m", "1D"]?

#### 4.2 MTF Tournament
- [ ] 15-pair HTF/LTF tournament?
- [ ] Guards G1-G4 applied?
- [ ] Winner selection correct?

### 5. RISK MANAGEMENT

#### 5.1 Daily Limits
- [ ] daily_loss_limit_pct = 2.0?
- [ ] max_trades_per_day = 6?
- [ ] max_slots = 8?

#### 5.2 Survival Circuit
- [ ] calculate_survival_plan() — WORKING?
- [ ] soft/hard/circuit tiers — CORRECT?
- [ ] min_circuit_dd_pct = 3.0?

#### 5.3 Correlation
- [ ] correlation_threshold = 0.85?
- [ ] vix_correlation_threshold = 0.5?
- [ ] usdinr_correlation_threshold = -0.4?

### 6. SUBSCRIBER LIFECYCLE

#### 6.1 Registration
- [ ] /start → PAPER_TRIAL?
- [ ] trial_expiry calculated?

#### 6.2 Approval
- [ ] /approve → LIVE_ACTIVE?
- [ ] Term stacking working?

#### 6.3 Revoke
- [ ] /revoke → REVOKED?
- [ ] Exit continues?

### 7. MODE SWITCHING

#### 7.1 Commands
- [ ] /paper — WORKING?
- [ ] /live — WORKING?
- [ ] /livefull — WORKING?

#### 7.2 State Management
- [ ] activate_paper() — WORKING?
- [ ] activate_live_staged() — WORKING?
- [ ] activate_live_full() — WORKING?

### 8. ERROR HANDLING

#### 8.1 Global Error Handler
- [ ] _global_error_handler — EXISTS?
- [ ] User notified?
- [ ] Admin alerted?

#### 8.2 API Failures
- [ ] Token expiry — HANDLED?
- [ ] Network failure — HANDLED?
- [ ] Rate limiting — HANDLED?

### 9. DATA INTEGRITY

#### 9.1 JSON Save/Load
- [ ] save_json() — WORKING?
- [ ] load_json() — WORKING?
- [ ] File existence checks?

#### 9.2 Database
- [ ] init_db() — WORKING?
- [ ] All tables created?

### 10. PARAM_SOURCES

#### 10.1 Registration
- [ ] All parameters registered?
- [ ] Source categories correct?
- [ ] No untagged numbers?

#### 10.2 Categories
- [ ] OWNER_POLICY — CORRECT?
- [ ] OPTIMIZER_FALLBACK — CORRECT?
- [ ] VERIFIED_CONVENTION — CORRECT?
- [ ] EXTERNAL_FACT — CORRECT?
- [ ] ENGINEERING — CORRECT?

### 11. SYNTAX CHECK

#### 11.1 All Files
- [ ] 87 Python files — ALL syntax OK?
- [ ] No import errors?
- [ ] No syntax errors?

### 12. PARITY CHECK

#### 12.1 Backtest vs Live
- [ ] Same exit_engine?
- [ ] Same position sizing?
- [ ] Same compounding formula?

#### 12.2 Admin vs Subscriber
- [ ] Same order type?
- [ ] Same qty calculation?
- [ ] Same protection?

---

## 🎯 GO/NO-GO CERTIFICATE

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

### OVERALL
- [ ] ✅ GO
- [ ] ❌ NO-GO

---

## 📝 FINDINGS

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
