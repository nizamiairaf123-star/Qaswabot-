# QASWA — CERTIFICATION CLOSURE REGISTER

**Purpose:** evidence-linked continuity across AI/auditor handoffs.

**Canonical governance:** `docs/CERTIFICATION_CLOSURE_AND_REINSPECTION_GOVERNANCE_v1.0.md`

## Required closure record

| Field | Required |
|---|---|
| Finding / Criterion ID | Yes |
| Section | Yes |
| File / Function / Data artifact | Yes |
| Release ZIP hash | Yes |
| Status | OPEN / FIXED / TESTED-PASS / CLOSED / REOPENED |
| Inspection evidence | Yes |
| Test command/procedure | Yes, where applicable |
| Actual output/result | Yes |
| Affected-chain check | Yes, where applicable |
| External dependency status | Explicit if applicable |
| Closure date | Yes |
| Owner decision | Yes where owner action is required |

## Continuity rule

A later AI must verify a CLOSED record against the current ZIP and evidence. It must not reopen the item merely because it prefers a different implementation. Reopening requires one of the defined evidence-based triggers in the canonical governance document.

## Use of this register

This register is an evidence template for recording independent closure decisions. A record is not authoritative merely because its status says CLOSED; the receiving AI must verify the implementation and evidence before relying on it.

---

## Closure Records

### DATA-002 — Board data fail-open bug
| Field | Value |
|---|---|
| Finding / Criterion ID | DATA-002 |
| Section | Sharia/board compliance |
| File / Function / Data artifact | `board_manager.check_board_100_non_muslim_with_confirmation()`; `CUSTOM_UNIVERSE_FINAL.csv`; `board_members_yfinance.json` |
| Release ZIP hash | (carried from prior r4_DATA002_FIXED release — see `DEFECT_FINDING_REGISTER_v1.1.md` for full narrative) |
| Status | CLOSED |
| Inspection evidence | 4 symbols (ELPROINTL, JSWDULUX, MAFATIND, VAML) had empty director data but were fail-open marked `non_muslim_board=True` — no guard existed for an empty directors list |
| Test command/procedure | `py_compile`; isolated unit check of empty-directors path; `test_sequence.py`/`test_full_pipeline.py`/`test_sharia_and_validation.py` |
| Actual output/result | Empty-directors now returns False + `verification_status: unverified_no_director_data_fail_closed`; all 3 test files pass clean |
| Affected-chain check | Universe eligibility (`CUSTOM_UNIVERSE_FINAL.csv`), `BOARD_TRUE_100_NON_MUSLIM.csv` — both corrected |
| External dependency status | None |
| Closure date | Prior session (see DEFECT_FINDING_REGISTER_v1.1.md) |
| Owner decision | None required |

### QUANT-002 — Portfolio drawdown does not prove real concentration risk
| Field | Value |
|---|---|
| Finding / Criterion ID | QUANT-002 |
| Section | Backtest / risk engine |
| File / Function / Data artifact | New `portfolio_backtest_engine.py` (`run_portfolio_backtest`, `_replay_candidates`); wired into `backtester.run_full_backtest()`; bonus fix in `economics_brain.py` (`calculate_max_slots_candidate`) |
| Release ZIP hash | f6c6c9bf39d5fa02a463d20f0d3e23bf47bcc208a5065bb8be836f9ac6eb61d8 (pre_vps_FIXED.zip) |
| Status | CLOSED |
| Inspection evidence | Grep confirmed zero calls to `can_enter_trade`/concentration checks in backtester.py/parity_engine.py/strategy.py — every symbol backtested in isolation |
| Test command/procedure | `python3 test_portfolio_backtest_engine_QUANT002.py` |
| Actual output/result | 6/6 assertions pass: correlation-block, sector-cap-block, max-slots-block, cooldown-block, cooldown-expiry-allows-reentry, economics_brain dynamic path runs without NameError |
| Affected-chain check | `backtester.run_full_backtest()` output (additive field, existing `portfolio_max_dd_pct` untouched — 5 other modules that read it unaffected); `economics_brain.get_recommended_max_slots()` now actually executes instead of always NameError-fallback |
| External dependency status | None — fully sandbox-testable with synthetic data |
| Closure date | 2026-09-01 |
| Owner decision | None required. OWNER-PENDING note: `deployment_manager.py`'s separate pooled-Monte-Carlo gate (`_mc_gate_core`) also does not apply concentration constraints — left untouched (bigger/riskier change), flagged for owner if they want it addressed too |

### QUANT-001 — Backtest universe eligibility has no historical archive (survivorship/look-ahead bias)
| Field | Value |
|---|---|
| Finding / Criterion ID | QUANT-001 |
| Section | Backtest / universe eligibility |
| File / Function / Data artifact | New `universe_snapshot_manager.py`; wired into `scheduler._monthly_board_universe_update_job()`; `backtester.run_full_backtest()` output field `universe_point_in_time_status` |
| Release ZIP hash | f6c6c9bf39d5fa02a463d20f0d3e23bf47bcc208a5065bb8be836f9ac6eb61d8 (pre_vps_FIXED.zip) |
| Status | CLOSED (forward-looking fix) — see note below, this is NOT the same as "fully resolved" |
| Inspection evidence | Checked directly: no historical eligibility archive exists anywhere in this codebase (no snapshot files, no history table in `custom_universe_state.json`, nothing in the DB) |
| Test command/procedure | `python3 test_universe_snapshot_manager_QUANT001.py` |
| Actual output/result | 5/5 assertions pass: empty-state honesty, save/round-trip, asof-before-any-snapshot correctly returns None (not a silent substitute), asof-after returns nearest-prior snapshot |
| Affected-chain check | `backtester.run_full_backtest()` output (additive field); `scheduler._monthly_board_universe_update_job()` success branch (fail-open — snapshot-save failure never blocks the refresh itself) |
| External dependency status | **Explicit limitation, not external-blocked**: retroactive correction of past backtest years is genuinely impossible — that history was never captured and fabricating it would violate the no-fabrication rule. This is a data-availability ceiling, not a code gap. From the date this fix ships forward, point-in-time accuracy will improve monthly as snapshots accumulate. |
| Closure date | 2026-09-01 |
| Owner decision | None required for the fix itself. Owner may decide whether to also snapshot on the daily retry job (currently monthly-only) |

**Note on QUANT-001's CLOSED status**: this is closed as "the honestly-fixable part is fixed and the limitation is now disclosed instead of hidden" — a receiving AI verifying this record should NOT reopen it merely because backtest results still aren't retroactively point-in-time accurate for years before the snapshot-capture start date. That is a known, documented, permanent characteristic of this fix, not a defect. It should only be reopened if evidence shows the snapshot mechanism itself is broken, or if a historical archive is somehow discovered to actually exist somewhere it wasn't found.

### FROZEN-TRACKER-C06/C07 — min_reward_risk hardcoded in 5 places instead of single-sourced
| Field | Value |
|---|---|
| Finding / Criterion ID | Frozen-criteria tracker rows #6/#7 (Configuration Audit / Every Numeric Value Audit) |
| Section | Exit engine / RR contract |
| File / Function / Data artifact | `exit_engine.py::init_state()`; `strategy.py` (`_uptrend_signals`, `_sideways_signals`); `trade_engine.py::_evaluate_exit_state()` |
| Release ZIP hash | See `AUDIT_INTEGRITY_MANIFEST_SHA256.json` at r8 |
| Status | CLOSED |
| Inspection evidence | `rr = 1.8` hardcoded independently at 4 sites instead of reading `config.PARAMS["min_reward_risk"]`; value was correct (1.8) everywhere but not single-sourced |
| Test command/procedure | `test_sequence.py`; functional smoke test recomputing `exit_engine.init_state(entry=100, floor_sl=95)` |
| Actual output/result | `lock_price=109.0` → RR recomputed = exactly 1.8 (unchanged); `test_sequence.py` 118/118 unchanged before/after |
| Affected-chain check | Backtest (`strategy.py`) and live (`trade_engine.py`/`exit_engine.py`) now read the same source — no drift risk if the value is ever changed in one place |
| External dependency status | None |
| Closure date | 2026-09-06 (r8) |
| Owner decision | Owner explicitly confirmed RR must stay fixed at exactly 1.8, never optimizer-selected — this fix does not change that, only removes duplication |

### FROZEN-TRACKER-C18 — ATR Wilder-smoothing fix was incomplete
| Field | Value |
|---|---|
| Finding / Criterion ID | Frozen-criteria tracker row #18 (Strategy Mathematics) |
| Section | ATR contract |
| File / Function / Data artifact | `strategy.py::calc_atr()`; `strategy_tools.py::calc_atr()`; `trade_engine.py::_calculate_atr()` |
| Release ZIP hash | See manifest at r8 |
| Status | CLOSED |
| Inspection evidence | An earlier round's ADX Wilder-smoothing fix (`ewm(span=period)`→`ewm(alpha=1/period, adjust=False)`) was applied only inside `calculate_adx()`'s local scope. The 3 shared ATR functions that actually feed the exit engine (trailing-stop distance, SL-hunt detection, candle-size signals) still used the old `ewm(span=period)` method |
| Test command/procedure | Functional smoke test running all 3 ATR functions on identical synthetic OHLC data |
| Actual output/result | All 3 now return numerically identical values (previously all 3 already agreed with each other, just on the pre-Wilder formula — now they agree on the corrected one; no live/backtest drift existed before or after) |
| Affected-chain check | Exit engine trailing-stop distance, SL-hunt wick-multiplier threshold, strategy_tools candle-size entry signals |
| External dependency status | None |
| Closure date | 2026-09-06 (r8) |
| Owner decision | None required |

### FROZEN-TRACKER-C19 — Look-ahead leak in 3 backtest optimizer tools
| Field | Value |
|---|---|
| Finding / Criterion ID | Frozen-criteria tracker row #19 (Look-Ahead/Data Leakage) |
| Section | Optimizer / backtest integrity |
| File / Function / Data artifact | `strategy_tools.py::opt_rsi_divergence()`, `opt_volume_divergence()`, `opt_mtf_composite()` (4 code sites) |
| Release ZIP hash | See manifest at r9 |
| Status | CLOSED |
| Inspection evidence | Externally reported, then independently re-verified line-by-line before acting (per continuity governance — never trust a report without re-checking). Swing-low confirmation allowed `j == i` ("today"), requiring bar `j+1` ("tomorrow") — genuinely available in backtest's fully-loaded array, not available in live's real-time array |
| Test command/procedure | Structural proof (loop bound `i+1`→`i` mathematically excludes `j==i`) plus `test_sequence.py`/pytest-suite regression re-run |
| Actual output/result | `test_sequence.py` 118/118 unchanged, pytest-suite 6/6 unchanged |
| Affected-chain check | Optimizer tool selection/scoring for these 3 tools only; the other 8 registered tools were unaffected and were independently confirmed not to share this pattern |
| External dependency status | None |
| Closure date | 2026-09-06 (r9) |
| Owner decision | None required |

### FROZEN-TRACKER-C47 — DB-read failure silently fail-open on killswitch and active-trades (CRITICAL)
| Field | Value |
|---|---|
| Finding / Criterion ID | Frozen-criteria tracker row #47 (Failure-Injection Matrix) |
| Section | Safety / fail-closed contract |
| File / Function / Data artifact | `database.py::db_load()`/`db_save()`; `utils.is_killswitch_active()`; `capital_manager.get_active_trades()`; `trade_engine.run_market_scan()` |
| Release ZIP hash | See manifest at r10 |
| Status | CLOSED |
| Inspection evidence | `db_load()` self-labeled its own behavior "fail-open" in its log message — any DB exception silently returned the caller's default. `is_killswitch_active()` defaulted to `{"active": False}` (a DB failure during an active emergency stop would silently read as OFF); `get_active_trades()` defaulted to zero positions |
| Test command/procedure | Genuinely broke the DB connection (renamed the sqlite file, replaced it with a directory to force a real `OperationalError`) rather than faking a flag — a first attempt using a faked flag was caught as invalid by this same discipline and redone properly |
| Actual output/result | Under a genuine DB failure: `is_killswitch_active()` → `True` (fail-closed), `is_db_failure_recent()` → `True`, `get_active_trades()` → `{}` without crashing. After restoring the DB: all three return to normal, self-clearing, no manual reset needed |
| Affected-chain check | `trade_engine.run_market_scan()` gained one new entry-gate check (same pattern/location as the existing killswitch and network-partition checks) — this single check also covers `SEBI_BLOCKED_FILE`, `CRASH_PENDING_ORDERS_FILE`, and `NETWORK_STATE_FILE` reads without needing to patch each of their ~9 combined call sites individually. Existing position monitoring/exits are untouched |
| External dependency status | None — fully reproducible locally by breaking the DB file |
| Closure date | 2026-09-06 (r10) |
| Owner decision | None required — user approved the fix after being shown the exact mechanism and impact |

### FROZEN-TRACKER-C43 — Naive server-timezone datetime used instead of project's own IST convention
| Field | Value |
|---|---|
| Finding / Criterion ID | Frozen-criteria tracker row #43 (Time/Date/Timezone) |
| Section | Data-fetch consistency |
| File / Function / Data artifact | `correlation_tracker.py:91`, `dhan_data.py:189`, `dhan_data.py:245`, `market_regime.py:98` |
| Release ZIP hash | See manifest at r10 |
| Status | CLOSED |
| Inspection evidence | `datetime.today()` (naive, server-local) used instead of `utils.now_ist()`, the project's single-source time convention used everywhere else in production code |
| Test command/procedure | `py_compile`; `test_sequence.py` regression re-run |
| Actual output/result | 118/118 unchanged |
| Affected-chain check | Historical-data fetch date ranges in 3 modules |
| External dependency status | None locally reproducible; actual runtime severity depends on the deployment VPS's system timezone, which cannot be verified until real deployment |
| Closure date | 2026-09-06 (r10) |
| Owner decision | None required |

### FROZEN-TRACKER-C10 — Delivery brokerage rate wrong (used Dhan's intraday rate)
| Field | Value |
|---|---|
| Finding / Criterion ID | Frozen-criteria tracker row #10 (Data Provenance) |
| Section | Economics / cost-model provenance |
| File / Function / Data artifact | `config.py` (`brokerage_rate_pct`, `brokerage_min_inr` PARAMS defaults + EXTERNAL_FACT labels); `utils.calculate_dhan_friction()` |
| Release ZIP hash | See manifest at r10 |
| Status | CLOSED |
| Inspection evidence | Independently web-verified against 8+ current published sources (incl. Dhan's own pricing page): Dhan equity DELIVERY brokerage has been ₹0 continuously since its 2021 launch. The previous `0.06%`/`₹40 cap` values are Dhan's INTRADAY rate, wrongly applied here — this bot trades delivery/CNC exclusively |
| Test command/procedure | `calculate_dhan_friction(50000, is_intraday=False)` before/after |
| Actual output/result | Corrected from ~0.278% (overestimated) to exactly 0.207% (verified-accurate); intraday branch unchanged |
| Affected-chain check | `economics_brain.py`'s trade-viability calculations (2 sites) also consume the same config defaults, corrected automatically |
| External dependency status | None — this is a publicly-verifiable fact, not blocked on live deployment (see governing addendum note on this distinction) |
| Closure date | 2026-09-06 (r10) |
| Owner decision | None required. Direction was always safety-conservative (overestimating cost, not underestimating it) — no capital-loss exposure existed before this fix either |

### FROZEN-TRACKER-C34 — Two documentation files described the pre-fix brokerage formula as current
| Field | Value |
|---|---|
| Finding / Criterion ID | Frozen-criteria tracker row #34 (Documentation Audit) |
| Section | Documentation accuracy |
| File / Function / Data artifact | `SYSTEM_BLUEPRINT.md` §2.2; `prd.md` calculations table |
| Release ZIP hash | See manifest at r11 |
| Status | CLOSED |
| Inspection evidence | Both files described `is_trade_economically_viable()`'s cost formula using the pre-r10 `₹40/0.06%` delivery brokerage values, now stale after FROZEN-TRACKER-C10 above. Historical changelog/decision-log entries describing the same old values were correctly left untouched — they are accurate past-tense records, not current-state claims |
| Test command/procedure | Grep-based targeted search across all 44 shipped `.md` files for every claim touched by r8/r9/r10 fixes |
| Actual output/result | 2 genuine current-state staleness issues found and corrected; no others found within the searched scope |
| Affected-chain check | None (documentation-only change, no code touched) |
| External dependency status | None |
| Closure date | 2026-09-06 (r11) |
| Owner decision | None required |

**Scope note on this batch of closures**: these 8 records close every defect found under the frozen-criteria tracking discipline through r11. The tracker itself (external to this ZIP, maintained by the auditing AI across sessions) shows 49/55 criteria PASS-with-evidence, 2/55 correctly EXTERNAL/DEFERRED (rows 17 and 42 — real market-data-provider and broker/VPS access), 0 open defects. This is a PRE-VPS engineering closure — AFTER-VPS/live evidence for rows 17 and 42 remains separately gated per this project's own Section 22, not upgraded to PASS without real deployment evidence.
