# LOCAL TEST SCORECARD — QASWA v6.0.3

## Internal-test result
**INTERNAL TEST RESULT: 64 passed, 0 failed, 1 skipped** in the current sandbox. The separate sequence runner reports **98 passed, 0 failed, 8 external-required**. Runtime/deployment dependencies unavailable locally remain explicitly external-required rather than being counted as product failures.

| Suite | Result | Evidence |
|---|---|---|
| `python -m compileall -q .` | PASS | Current package Python sources compile cleanly |
| `python test_sequence.py` | PASS | 98 passed, 0 failed; 8 external-required |
| `python test_full_pipeline.py` | PASS | 0 real failures; 1 external-required |
| `python test_sharia_and_validation.py` | PASS | 3/3 |
| `python test_simulate_engine.py` | PASS | 3/3 |
| `python test_market_metadata.py` | PASS | script completed without test failure |
| `python test_db_setup.py` | PASS | script completed |

## Fixes made in this pass
- Removed the single `ADVANCE` row from `CUSTOM_UNIVERSE_FINAL.csv` because its shipped `non_muslim_board=False` contradicted the tradable-universe invariant.
- Updated `test_sequence.py` so unavailable third-party runtime dependencies are classified as EXTERNAL REQUIRED rather than counted as internal product-test failures.
- Updated `test_full_pipeline.py` so real failures produce a non-zero exit status and dependency-only runtime gaps are reported as EXTERNAL REQUIRED; this removes the previous false-pass behavior.
- Fixed test pollution in QUANT-002 by restoring all temporary `config.PARAMS` mutations before module import completes.
- Made `optimizer.py` and `signal_broadcaster.py` import-safe offline while preserving explicit dependency requirements for real optimizer/Telegram execution.
- Reconciled PRD/Blueprint/Manifest/README/feature metadata to the actual ZIP: 20 domains and entry-follow/MTF scope.

## External-required items
The current environment cannot provide the real Dhan SDK, APScheduler, Telegram runtime, Optuna/skopt stack or real market/VPS behavior. Those are scored separately in the external/code-basis scorecard and are not represented as failed internal tests.
