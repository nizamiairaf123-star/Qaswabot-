# QASWA ZIP-DERIVED REQUIREMENTS & BLUEPRINT RULES v1.1

## Rule
ZIP first. The actual archive determines implementation scope; old PRD/Blueprint text cannot hide or omit shipped artifacts.

## Required sequence
1. Inventory every artifact.
2. Reconstruct/update PRD from actual ZIP.
3. Reconstruct/update Blueprint from actual modules, data, configuration, state and wiring.
4. Reconcile against the 55-section inspection backbone.
5. Add a section only for a genuinely independent uncovered risk class.
6. Apply inspection criteria.
7. Run locally executable tests; fix confirmed defects and retest.
8. Score externally untestable behavior from code/evidence separately; do not treat unavailable runtime as a failed product test.
9. Issue a release verdict only after all mandatory gates are satisfied.

## Current baseline decision
The new `entry_follow`, `shadow_log` and `mtf/` areas fit within the existing 55 sections. No new section is required at this baseline.

## Current blockers
- Decision-critical custom-universe provider fields are empty.
- Several runtime dependencies are unavailable in the current local environment (`dhanhq`, `apscheduler`, `telegram`, `skopt`).
- `MTF_ENABLED=True` exists in config; actual standalone MTF warehouse consumption must be traced.
- Historical audit documents contain stale counts/claims and are evidence-only.

## Artifact inventory
- `.env.example`
- `AI_ONBOARDING.md`
- `AUDIT_INVENTORY_SHA256.json`
- `AUDIT_PROGRESS_READ_ME_FIRST.md`
- `AUDIT_REINSPECTION_REPORT.md`
- `CANONICAL_DOCUMENT_SYNC_REPORT_v1.1.md`
- `COMPLETE_ANALYSIS.md`
- `DATA_SOURCE_POLICY.md`
- `DEFECT_FINDING_REGISTER_v1.1.md`
- `EXTERNAL_CONFIDENCE_SCORECARD_v1.1.md`
- `FINAL_INSPECTION_REPORT_v4.md`
- `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md`
- `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.sha256`
- `FINAL_MASTER_INSPECTION_CHECKLIST_v3.md`
- `FINAL_RELEASE_VERDICT_v1.1.md`
- `FRAMEWORK_FREEZE_UPDATE_v1.1.md`
- `HYBRID_SCORECARD_v1.1.md`
- `INSPECTION_CHECKLIST.md`
- `INSPECTION_CHECKLIST_v2.md`
- `LOCAL_AUDIT_EXECUTION_REPORT_v1.1.md`
- `LOCAL_TEST_SCORECARD_v1.1.md`
- `MASTER_AUDIT_EXECUTION_AND_SCORECARD.md`
- `README.md`
- `RELEASE_ARTIFACT_STATUS.md`
- `SYSTEM_BLUEPRINT.md`
- `SYSTEM_MASTER_MANIFEST.json`
- `UPDATE_HISTORY_FIX_LOG.md`
- `UPDATE_R2_REPORT.md`
- `UPDATE_V5_REPORT.md`
- `VERSION.txt`
- `VPS_DEPLOYMENT_GUIDE.md`
- `backtester.py`
- `board_filter_auto.py`
- `board_manager.py`
- `bot.py`
- `bot_state_manager.py`
- `broker.py`
- `build_pdf_report.py`
- `capital_drawdown_manager.py`
- `capital_manager.py`
- `config.py`
- `corporate_actions.py`
- `correlation_tracker.py`
- `crypto_utils.py`
- `data/BOARD_FALSE_HAS_MUSLIM.csv`
- `data/BOARD_TRUE_100_NON_MUSLIM.csv`
- `data/CUSTOM_UNIVERSE_FINAL.csv`
- `data/MASTER_STOCK_LIST_PERMANENT.csv`
- `data/audit_log.txt`
- `data/board_members_yfinance.json`
- `data/bot.log`
- `data/custom_universe_state.json`
- `data/decision_data_provider.json`
- `data/lm_finance_wordlists.csv`
- `data/trading_bot.db`
- `database.py`
- `dd_policy.py`
- `deploy.sh`
- `deployment_manager.py`
- `dhan_client.py`
- `dhan_data.py`
- `dhan_live_feed.py`
- `docs/AUDIT_55_EXECUTION_SCORECARD.md`
- `docs/AUDIT_ARTIFACT_INVENTORY.csv`
- `docs/CANONICAL_RELEASE_AND_AUDIT_TRUTH_INDEX.md`
- `docs/CURRENT_INSPECTION_STATUS.md`
- `docs/DATA_READINESS_AND_REFRESH.md`
- `docs/FRESH_FULL_55_SECTION_AUDIT_REPORT.md`
- `docs/MASTER_ZERO_OMISSION_ZIP_INSPECTION_CONSTITUTION_55_SECTIONS.md`
- `docs/PRODUCTION_AUDIT_REPORT_55_SECTIONS.md`
- `economics_brain.py`
- `entry_follow.py`
- `exit_engine.py`
- `feature_sequence.json`
- `fii_dii_tracker.py`
- `file_inventory.txt`
- `forever_order_manager.py`
- `guide_text.py`
- `intraday_filter.py`
- `liquidity_screen.py`
- `log_setup.py`
- `macro_refresh.py`
- `market_metadata.py`
- `market_regime.py`
- `monte_carlo.py`
- `mtf/__init__.py`
- `mtf/bulk_download.py`
- `mtf/derive.py`
- `mtf/guards.py`
- `mtf/probe_depth.py`
- `mtf/stats.py`
- `mtf/timeframes.py`
- `mtf/tournament.py`
- `mtf/warehouse.py`
- `news_analyzer.py`
- `optimizer.py`
- `overnight_movers.py`
- `parity_engine.py`
- `payment.py`
- `per_stock_params.py`
- `portfolio_health.py`
- `prd.md`
- `qaswa-bot@.service`
- `regime_manager.py`
- `report_generator.py`
- `requirements-lock.txt`
- `requirements.txt`
- `risk_display.py`
- `risk_manager.py`
- `risk_override_manager.py`
- `ruflo_ranker.py`
- `safety_manager.py`
- `scheduler.py`
- `scripts/__init__.py`
- `scripts/freeze_requirements.sh`
- `scripts/live_feed_dry_run.py`
- `scripts/refresh_decision_data.py`
- `scripts/release_preflight.py`
- `sebi_manager.py`
- `sector_strength.py`
- `shadow_log.py`
- `sharia_manager.py`
- `signal_broadcaster.py`
- `simulate_engine.py`
- `single_instance.py`
- `start_bot.sh`
- `startup_recovery.py`
- `stock_mode_manager.py`
- `stock_selector.py`
- `strategy.py`
- `strategy_tools.py`
- `strategy_validator.py`
- `subscriber_manager.py`
- `survival_manager.py`
- `test_data_source_policy.py`
- `test_db_setup.py`
- `test_entry_follow.py`
- `test_full_pipeline.py`
- `test_golden.py`
- `test_macro.py`
- `test_market_metadata.py`
- `test_overnight.py`
- `test_scheduler_jobs.py`
- `test_sequence.py`
- `test_sharia_and_validation.py`
- `test_simulate_engine.py`
- `trade_engine.py`
- `trade_logger.py`
- `utils.py`
- `walk_forward_validator.py`
- `workflow_manager.py`


## v1.1 RR Exit Contract Registration — 1.8R

- RR lock: **exactly 1.8R**; RR is not an optimizer dimension; optimizer does not select RR.
- 1R is the actual entry-to-SL distance.
- Before 1.8R: no breakeven, no +1R lock, and no early trailing activation.
- At exactly 1.8R: profit protection locks; before that threshold there is no BE/+1R lock or early trailing.
- After the fixed 1.8R lock, the existing optimizer-selected exit/trailing combination remains active with uncapped upside; the protected floor may only move upward.
- Broker-side GTT architecture is unchanged.
