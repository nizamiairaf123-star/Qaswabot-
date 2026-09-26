# QASWA Pre-VPS Reinspection Run — 2026-09-03

## Scope
This record documents the next verification pass after the operational-reality requirement was added. It records only actions and evidence from this run; it is not itself a product certification.

## Operational-reality rule applied
For every applicable criterion, inspection must trace:

**Criterion → Implementation → Integration/Wiring → Invocation/Reachability → Actual Effect → Enforcement → Failure/Bypass Analysis → Evidence**

Code presence alone is not a PASS. Dead/orphan code, unused settings, disconnected gates, bypasses, fallback paths that defeat the required method, and alternate paths that replace the required mechanism must be identified.

## Code-quality fixes applied in this run
1. Broker SDK imports were made lazy in `dhan_data.py`, `subscriber_manager.py`, `broker.py`, `capital_manager.py`, and `market_regime.py`. This does not remove the declared Dhan dependency or make broker execution available offline; it prevents unrelated non-broker logic from becoming unimportable solely because the external SDK is absent in an audit sandbox.
2. `test_full_pipeline.py` is now explicitly import-safe as a script-style audit runner; test discovery no longer executes its top-level audit actions or terminates the collector.
3. `test_portfolio_backtest_engine_QUANT002.py` no longer overwrites `data/CUSTOM_UNIVERSE_FINAL.csv`. Its synthetic sector map is supplied directly to the tested function, so test order cannot corrupt production evidence used by unrelated tests.
4. `optimizer.py` now treats `scikit-optimize` as an optional import for module-level/testability purposes. Bayesian/ensemble optimization explicitly BLOCKS when `skopt` is unavailable rather than crashing during import or silently substituting an optimizer.
5. `signal_broadcaster.py` now lazy-loads the Telegram SDK. Non-Telegram tests can import the module offline; actual Telegram sending still requires the declared dependency and real runtime credentials.
6. `test_portfolio_backtest_engine_QUANT002.py` now restores every temporary `config.PARAMS` mutation before module import completes, eliminating cross-test configuration pollution.
7. Golden trailing tests were rechecked against the current owner-approved `trading_cost_pct=0.30` path. The prior 0.20 percentage-point mismatch was traced to test contamination from QUANT-002 changing the global cost to 0.10, not to an exit-engine defect.

## Verification evidence
- Python compile check: PASS for all modified Python files.
- Targeted data-source tests: 4/4 PASS.
- Scheduler tests: PASS after lazy broker import changes.
- QUANT-001 snapshot tests: PASS.
- QUANT-002 portfolio concentration tests: 6/6 assertions PASS.
- Full pytest run in this sandbox after the fixes: **64 PASS, 0 FAIL, 1 SKIPPED**.
- Direct `python test_full_pipeline.py`: **0 real failures, 1 external-required** (`apscheduler` unavailable).
- Direct `python test_sequence.py`: **98 PASS, 0 FAIL, 8 external-required**.
- The earlier 11 pytest failures were traced to import-time dependency availability plus one test-isolation defect; after fixing those, no internal pytest failure remains in the current sandbox.
- `scripts/release_preflight.py`: correctly remains FAIL-CLOSED because the shipped universe snapshot has no verified decision-critical sector/industry/market-cap/liquidity/ATVR/FoT values.

## External boundary
Real Dhan/yfinance refresh and broker/VPS integration cannot be truthfully simulated as completed without the required external environment/data. No placeholder market metadata is introduced.

## Current disposition
This run improves testability and evidence integrity but does **not** claim PRE-VPS PASS. The next valid step is to run the package in its declared dependency environment, execute the real decision-data refresh, then repeat the complete S1–S55 inspection and PRE-VPS gate.
