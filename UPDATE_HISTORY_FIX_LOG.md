# QASWA Fix History Log

## 2026-09-16 — Independent audit report P1/P2 items fixed (F10, F12, F11, F3, F4, F6, F7, F16)

Fixed all remaining findings from `QASWA_Independent_Audit_Report.md` except the P3/P4 minor/cosmetic items (F2, F13-already-fixed-above, F17, and the P4 hygiene list), in order:

- **F10 (event-loop freeze risk)**: 4 synchronous Dhan/network call-sites in `trade_engine.py` ran directly on the asyncio event loop with no timeout — `_monitor_single()`'s `_fetch_candles()`, both `can_enter_trade()` call sites (Phase-1 scan loop + `_execute_candidate`), and `on_live_tick()`'s `_cached_atr()` (same class, found during this fix, not in the original 3-site list). All 4 now wrapped in `asyncio.to_thread()`, matching the pattern already used for the Phase-0 scan fetch. Verified: AST-clean, existing `test_cnc_swing_hours.py` 6/6 pass.
- **F12 (Telegram log handler blocking)**: `log_setup.py::TelegramLogHandler.emit()` made a synchronous `requests.post()` on the root logger — any `logger.error()`/`critical()` anywhere could block the event loop up to 5s. Now spawns a background daemon thread, same pattern `signal_broadcaster.py::alert_admin_sync()` already used.
- **F11 (subscriber saw admin's P&L/positions)**: `get_pnl_summary(chat_id=...)` never actually filtered (master `TRADES_FILE` has no per-subscriber field at all). `/positions`, `/pnl`, `/result` in `bot.py` now branch on `subscriber_manager.is_admin()`: admin behavior unchanged; a subscriber now sees their own `data/copy_trades.json` ledger rows via new `trade_logger.get_subscriber_copy_summary()`. Note: the copy ledger records order IDs/status, not fill price, so an exact ₹ P&L isn't fabricated for subscribers — they're pointed to their own Dhan statement for that (their fills/slippage genuinely differ from admin's). Verified with synthetic ledger data.
- **F3 (false "Monte Carlo covers gap-slippage" claim)**: `exit_engine.py` comment corrected — traced and confirmed `monte_carlo.py` (the module with `severity_mult`) is only ever imported by the display-only `risk_display.py`, never by sizing/decision code. Doc-only fix, no behavior change.
- **F4 (`calc_vwap()` misleading name)**: docstrings added to `strategy_tools.py`/`strategy.py` clarifying it's a cumulative multi-day volume-weighted average, not a real session VWAP — `opt_vwap_bounce()` is more accurately a slow-MA crossover. Left the name/behavior unchanged (referenced by saved per-stock optimizer state) — doc-only fix.
- **F6 (no missed-job watchdog)**: `scheduler.py`'s `AsyncIOScheduler` now sets `job_defaults` (`misfire_grace_time=120`, `max_instances=1` explicit, `coalesce=True`) instead of relying on APScheduler's tight built-in 1s default, plus an `EVENT_JOB_MISSED` listener that fires `logger.error()` (→ Telegram, now non-blocking per F12) so a genuinely missed job cycle is visible instead of silently dropped.
- **F7 (tests can contaminate the real DB/data files when run standalone)**: `conftest.py`'s pytest-only sandbox never activated for `python3 test_X.py` runs (bypasses pytest entirely). Added an idempotent `atexit`-registered cleanup so the sandbox is safe to activate standalone, then added `import conftest` as the first import in every test file with a standalone/`__main__` execution path and no pre-existing tempfile-based isolation of its own (16 files — the 3 originally named plus `test_universe_snapshot_manager_QUANT001.py` and `test_portfolio_backtest_engine_QUANT002.py`, the latter being the exact file previously documented as having overwritten the real `CUSTOM_UNIVERSE_FINAL.csv` 3× across sessions). `test_ndsap_archive.py`/`test_telemetry.py`/`test_sequence.py` left untouched — already self-contained (own tempfile DB override / own separate sandbox mechanism) or intentionally outside pytest. Verified: planted a real marker in `data/universe_snapshots/` and confirmed a standalone run of the QUANT001 test no longer deletes it; planted a hash snapshot of the real `CUSTOM_UNIVERSE_FINAL.csv` and confirmed a standalone run of the QUANT002 test leaves it byte-identical; ran all 16 files (individually, standalone and/or via unittest) with before/after hashing of `data/trading_bot.db` — 0 pollution; full existing test bodies still pass (72+ assertions across the unittest-style files, all `OK`).
- **F16 (board heuristic treated as a definitive verdict)**: added `board_manager.get_boards_needing_manual_review()` — a purely additive, read-only function that does NOT change any accept/reject logic (still exactly as fail-closed as before). It surfaces every symbol whose current board status came from the automated heuristic (`verified_by == "monthly_refresh"`) rather than manual confirmation, split into `heuristic_allowed` (no keyword hit — the higher-risk false-negative direction, since it's what currently lets a stock trade) and `heuristic_excluded_ambiguous` (blocked pending confirmation). Wired up as a new admin-only `/boardreview` Telegram command. Verified with synthetic mixed board-status data (manual/refresh-failed records correctly excluded from the review list).

## 2026-09-16 — F13: holiday list now fails loud past its covered years + special-session override added

`utils.py::NSE_HOLIDAYS` only ever covered 2025-2026 by hand — from Jan 2027 it would have silently treated real holidays as trading days (F13). No live NSE calendar fetch used (NSE datacenter-IP blocking, same issue already disclosed for `asm_gsm_screen.py`), so this stays a maintained static list, but now: (1) `_warn_if_holiday_list_stale()` fires one `logger.error()` (→ existing Telegram alert path) per day once `today.year` isn't in the list's covered years, so a stale list is now visible instead of silent; (2) added `NSE_SPECIAL_SESSIONS` — an explicit `date -> (open, close)` override table for non-standard sessions (e.g. Diwali Muhurat trading), checked by `is_market_open()` before falling back to the default 09:15-15:30. Empty by default — zero behavior change until entries are added. Verified: existing `test_cnc_swing_hours.py` 6/6 still pass; manually verified special-session override opens/closes at the overridden times and the stale-year warning fires exactly once/day.

## 2026-09-16 — F15 re-fix: `_create_dhan_client` NameError was NOT actually fixed at r6 despite this log's 09-04 entry claiming it

Independent audit found the r6 log entry below ("Fixed `_create_dhan_client` NameError") was doc-only — the code still crashed. Root cause: each of `subscriber_manager.py`, `capital_manager.py`, `market_regime.py` had its own dead local wrapper (`__create_dhan_client`) that itself called the never-imported name `_create_dhan_client` — and the real call sites (`subscriber_manager.py:527,592`, `capital_manager.py:388`, `market_regime.py:69`) call `_create_dhan_client` directly, bypassing that dead wrapper entirely. Real fix this time: removed the 3 dead wrappers, added `from broker import _create_dhan_client` (the actual working definition) at module level in all 3 files. No circular-import risk (`capital_manager.py` already imported `broker.get_available_balance`; `broker.py`'s own imports of these 3 modules are all local/in-function, not top-level). Verified: `grep` shows zero remaining references to the dead wrapper name anywhere in the codebase; AST-parses clean on all 4 touched files.

## 2026-09-04 — CNC swing freeze (owner) — v6.0.3-r6

Bot was already CNC (not MIS). Locked the remaining owner rules:

- `broker._live_order_session_gate`: real BUY/SELL refused when market closed (Dhan AMO has no MARKET). CNC product lock (MIS never allowed). Overnight SL stays on GTT forever orders.
- Subscriber copy path uses the same session gate + `EXIT_ORDER_TYPE` for SELL.
- `trade_engine.on_live_tick` skips MARKET exit after hours (GTT protects; retry from 09:15).
- `intraday_filter` / `risk_manager`: BE/T2T filter kept, renamed in comments to “same-day CNC exit possible” — not an MIS switch. Entry skipped if exit would be banned (SL/TP stuck).
- Fixed `_create_dhan_client` NameError (was `__create_dhan_client` calling undefined name).
- Tests: `test_cnc_swing_hours.py`.

---

## 2026-09-04 — Owner fix-list round (17 items) — v6.0.3-r5

**A. Code**
- (1) `dhan_live_feed.py` — premise "skeleton" was wrong: a real dhanhq `MarketFeed` wrapper already existed. Hardened: thread-safe queued `subscribe_tick()`/`unsubscribe_tick()` (works before connect and re-applies after reconnect), normalised `parse_tick()` output (`security_id`, `ltp`, `open/high/low/close`), `Disconnection` packet → backoff reconnect, socket closed in `finally`, `stats{ticks,reconnects,last_error}`, `is_running()`.
- (2) `bot.py` — feed was genuinely NOT wired. `startup_monitor` (post_init) now: `setup_scheduler()` → `run_startup_recovery()` → `_start_live_feed_task()`. Feed subscribes the open-position watchlist and routes every tick to `trade_engine.on_live_tick`; `live_feed_watchlist_sync` job (60 s) subscribes new / unsubscribes closed positions; `post_shutdown` stops the feed; `/botstatus` shows feed + fallback-monitor lines. Fail-open: no Dhan token → feed skipped, 3-min monitor unchanged.
- (3) `trade_engine.py` — `on_live_tick()` (throttle, per-symbol lock, killswitch/can_monitor/can_exit gates, `exit_in_progress` guard) and `_evaluate_exit_state()` = ONE shared exit math used by both the 3-min monitor and the tick path; exits go through the same `_execute_exit()`.
- (4) ADX — premise inaccurate (ADX lives in `strategy.py`, already raw True Range). Real defect: `ewm(span=period)` ≠ Wilder smoothing. Fixed to `ewm(alpha=1/period, adjust=False)`; verified mean|err| 0.000 vs textbook Wilder over 30 random series (was 6.89). `test_golden.py` FLAT fixture replaced (old fixture had identical highs/lows → degenerate ADX).
- (5b) **Board scanner — owner-delegated decision ("jo behtar hai wo karo"):** ONE scanner now (`board_filter_auto.py` delegates to `board_manager.is_potential_muslim_name`). Dual-community given names (Kamal, Parveen, Iqbal, Kabir, Tanveer, Gulzar, Shamsher, Shehnaz, Reshma…) moved from high-confidence to ambiguous and are cleared ONLY when the same full name carries an unmistakable non-Muslim marker (`NON_MUSLIM_MARKERS`, 550+ Hindu/Sikh/Jain surnames & given names; e.g. "Kamal Kumar Jain" clears, "Kamal Dalia" stays blocked). Never-clear set (khan/syed/hussain/…) can never be cleared by context. 100+ Muslim names found in the real board data but absent from every list were added (begum, kidwai, zaman, khorakiwala, kachwala, zubair, suhail, naheed, rehan…). **Data corrected with the same scanner:** 12 companies that had a Muslim director but were shipped as approved were REMOVED from `CUSTOM_UNIVERSE_FINAL.csv` (1,069 → 1,057): ANGELONE, BALUFORGE, DIVGIITTS, HERANBA, KCP, LOTUSDEV, NEPHROPLUS, POONAWALLA, REFEX, TEMBO, TVTODAY, WOCKPHARMA (master list, board side-lists, board JSON and state synced; nothing else in those files changed). Previously-excluded companies were NOT re-admitted by hand (39 would now pass, e.g. "Anil Kumar Malik IAS", "Sameer Gupta" — they re-enter only through the next real monthly refresh). `test_sequence.py` guards all of this (must-block / must-clear name sets + shipped-universe ↔ scanner consistency).
- (5) Board filter — premise false (`board_filter_auto.py` already complete; no `MuslimNameScanner` class exists). `board_manager.py`: real Screener.in director scrape fallback, honorific/punctuation normalisation before whole-word match, runtime HIGH_CONF list now merged with the batch list (93 names were missing at runtime), and `gupta/sharma/singh/kumar` removed from AMBIGUOUS (with the placeholder web-confirm they alone would have fail-closed 715/1069 approved companies at the first monthly refresh). Sharia policy unchanged: high-conf name or genuinely ambiguous name still blocks.
- (6) `requirements.txt` — `APScheduler==3.11.3` pinned. No fallback timer existed; the real P0 was `setup_scheduler()` being called BEFORE the event loop (`RuntimeError: no running event loop` on APScheduler 3.11) → moved into post_init. `test_sequence.py` guards the order.
- (17) NEW `fallback_monitor.py` — `record_fallback()` wired at 9 dynamic→static sites (`economics_brain` ×2, `capital_manager` ×3, `regime_manager` ×2, `market_regime` ×1, `trade_engine` ×1); daily report + `/botstatus` show "Aaj X baar dynamic fallback hua". Visibility only — no fallback value/flow changed.

**B. Data & packaging**
- (7) `data/trading_bot.db` rebuilt schema-only (0 rows; all 17 rows were test writes). (8) `audit_log.txt`/`bot.log` truncated. (9) NEW `conftest.py` + `test_sequence.py` sandbox: suites run in a temp copy of `data/`, release tree verified byte-identical after `pytest` + `test_sequence`. (10/15) manifest regenerated LAST from the clean tree. (11) test snapshot CSVs, caches removed. (12/13) README/PRD/BLUEPRINT/MANIFEST counts + 4 owner constants synced.

**C. Verification** — see `AUDIT_PROGRESS_READ_ME_FIRST.md` for the exact run counts of this round.

---


## Critical fixes

- Board refresh now fails closed on fetch failure, missing verification, missing board column, or incomplete board status.
- Scheduler no longer continues without the board filter and no longer synthesizes `non_muslim_board=True`.
- Unknown board status is non-tradeable by default.
- Hybrid/ratch­et/trailing profit floors above entry are hard floors; SL-hunt heuristics cannot suppress a locked-profit exit.
- `yfinance` is explicitly declared in `requirements.txt` because it is required for board data.
- Runtime execution universe is strict NSE cash-equity EQ; BSE-only symbols are rejected.
- Full eligible-universe scanning is separated from deployed strategy validity. Signal collection scans the full eligible universe; the final risk gate requires a valid deployed/backtest strategy before capital can be committed.
- VPS deployment scripts and deployment documentation are included.

## Verification

- All Python source files compile successfully with `py_compile`.
- Hybrid exit golden regression tests pass, including the locked-profit floor case.
- NSE-EQ eligibility passes and BSE-series eligibility is rejected by the centralized row gate.

---

## 2026-09-06 — Independent deep-inspection round — v6.0.3-r8

**Context**: Full re-verification of all 55 constitution sections against this exact zip, done by direct execution/hash/grep rather than trusting the shipped audit reports (some of which — e.g. AUDIT_55_EXECUTION_SCORECARD.md — carried stale file counts from an earlier round). ~52 of 55 sections independently confirmed clean with real evidence (manifest hash re-verified file-by-file, offline test suites re-run, orphan/wiring sweep across all 105 .py files, fail-closed gates traced end-to-end, crash-recovery chain traced end-to-end, all 59 Telegram commands confirmed registered, MASTER_STOCK_LIST_PERMANENT.csv validated). Exactly 2 real numeric-provenance defects found; both fixed here, no other code defects found at this depth.

**A. Fixes**
- **RR single-sourcing**: `min_reward_risk` value (1.8, fixed, not optimizer-selected — owner rule unchanged) was independently hardcoded in `exit_engine.py::init_state()` (`rr = 1.8`) and `strategy.py` (`_uptrend_signals`/`_sideways_signals`, `rr = 1.8` x2), instead of reading from the `params`/`PARAMS` dict already being passed around. Fixed all 3 sites to read `params.get("min_reward_risk", 1.8)` / `get_param(symbol, "min_reward_risk", PARAMS.get("min_reward_risk", 1.8))`. `trade_engine.py`'s `_evaluate_exit_state()` dict-literal site changed from `"min_reward_risk": 1.8` to `"min_reward_risk": PARAMS.get("min_reward_risk", 1.8)`. Value is unchanged (still exactly 1.8) — this is a single-source-of-truth fix only, so a future config change actually takes effect everywhere instead of silently not reaching 3 of 4 consumption sites.
- **ATR Wilder-smoothing completion**: the r5 fix (`ewm(span=period)` → `ewm(alpha=1/period, adjust=False)`, documented in this file under 2026-09-04 item (4)) was only applied inside `calculate_adx()`'s local ATR variable. The shared `calc_atr()` in `strategy.py` and `strategy_tools.py`, and `_calculate_atr()` in `trade_engine.py` — the functions that actually feed `exit_engine.step()`'s trailing-stop distance, SL-hunt wick-multiplier detection, and strategy_tools' candle-size entry signals — were still on the old `ewm(span=period)` method. All 3 now use the same Wilder alpha. Live and backtest were already consistent with each other before this fix (no parity break existed), so this changes the ATR magnitude itself, not live/backtest agreement — but it removes the internal inconsistency with the codebase's own declared standard (same alpha `calc_rsi` and `calculate_adx` already used).
- **Log hygiene**: cleared 1 stray line from `data/audit_log.txt` (`OPTIMIZER TEST: wr=55%...`), a leftover artifact from a prior test run, not real production history.

**B. Verification**
- `py_compile` clean on all 4 touched files.
- `test_sequence.py`: 118 passed, 0 failed, 7 external-required (unchanged from pre-fix baseline — same 7 items, all genuinely external universe-data-refresh dependencies, not code).
- pytest-style suites: 6 passed, 0 failed (unchanged).
- Functional smoke test: `exit_engine.init_state(entry=100, sl=95)` → lock_price=109.0 → RR recomputed = exactly 1.8 (unchanged). `strategy.calc_atr`, `strategy_tools.calc_atr`, `trade_engine._calculate_atr` run on the same synthetic OHLC series now return numerically identical values (previously all three already agreed with each other, just on the old formula — now they agree on the corrected one).
- Manifests (`AUDIT_INTEGRITY_MANIFEST_SHA256.json`, `AUDIT_INVENTORY_SHA256.json`) re-hashed for the changed files only; all other file hashes carried forward unchanged.

---

## 2026-09-06 — Look-ahead leak fix (backtest/optimizer only) — v6.0.3-r9

**Context**: Externally-reported finding (independently re-verified line-by-line before acting, per standing policy of never trusting a third-party report's claims without confirming them against the actual code first) — this one checked out as genuinely correct.

**Defect**: `opt_rsi_divergence()`, `opt_volume_divergence()`, and both inline swing-low blocks inside `opt_mtf_composite()` (4 sites in `strategy_tools.py`) detected a "swing low" at bar `j` by checking `data["low"].iloc[j] < data["low"].iloc[j-1]` AND `data["low"].iloc[j] < data["low"].iloc[j+1]`. The inner loop allowed `j` to reach `i` (the bar currently being evaluated for a signal), which means confirming "today is a swing low" required `iloc[i+1]` — tomorrow's low. In a backtest, the entire historical array (including all future bars) is loaded upfront, so this check silently used real future price data to decide whether "today" qualified as a confirmed swing low, artificially improving these 3 tools' apparent win rate/backtest performance relative to what would actually be achievable live. This could bias the optimizer toward selecting these 3 tools for a stock over the other 8 registered tools, which do not have this issue.

**Why live was never at risk**: in live scanning, "today" is always the last row of the data array actually available at decision time — there is no bar `i+1` to read. The existing guard `j < len(data) - 1` (already present, unrelated to this fix) happens to exclude the last row from ever being checked as `j`, so the live path was accidentally leak-free — not because of an explicit look-ahead safeguard, but as an incidental consequence of live data never containing unrealized future bars.

**Fix**: changed the inner loop's upper bound from `i + 1` to `i` at all 4 sites, so `j` can never equal `i` — a swing low can only be confirmed using bars strictly before today, never today itself. This does not reduce genuine signal quality: swing lows that are already 1+ bars old (the entire basis for a divergence signal) are still detected exactly as before; only the invalid "confirm today using tomorrow" case is removed.

**Verification**: `py_compile` clean. `test_sequence.py`: 118 passed, 0 failed (unchanged from r8 baseline). pytest-style suites: 6 passed, 0 failed (unchanged). Structural proof: with the new loop `range(max(0, i - lookback*2), i)`, the maximum value `j` can take is `i - 1`, so `j + 1` can reach at most `i` (today, already known) and never `i + 1` (tomorrow) — the leak is mathematically closed, not just less likely.

---

## 2026-09-06 — Frozen-criteria-tracker fixes (Section 47 critical, 43, 10) — v6.0.3-r10

**Context**: These 3 defects were found under a strict frozen-criteria audit discipline — every finding required an exact criterion citation, exact violation, exact location, and exact evidence before being classified as a defect (no scope creep, no invented requirements). All 3 met that bar.

**A. Section 47 — Failure-Injection Matrix (CRITICAL)**: `database.py::db_load()` caught every exception and silently returned the caller's `default` — its own log message literally said "fail-open". Two safety-critical callers inherited this: `utils.is_killswitch_active()` defaults to `{"active": False}` (a genuine DB failure during an active emergency stop would silently read as OFF, and trading would continue) and `capital_manager.get_active_trades()` defaults to `{"active_trades": {}}` (a DB failure would make the bot believe it had zero open positions). Fix: `db_load()`/`db_save()` now record any genuine failure out-of-band via a plain marker file (`data/db_failure_state.txt`, deliberately NOT written through the DB itself, since the DB is what's failing) and clear it on the next success. `is_killswitch_active()` now fails CLOSED — a recent DB failure makes it return `True` (treat as active) rather than silently reading OFF. `trade_engine.run_market_scan()` gained one new entry-gate check, at the same point as the existing killswitch/network-partition checks, that blocks new entries whenever a DB failure was recorded recently — this single check covers active-trades, SEBI-blocked-list, crash-pending-orders and network-state reads without needing to patch every one of their ~9 call sites individually. Existing position monitoring/exits are untouched.

**B. Section 43 — Time/Date/Timezone**: `datetime.today()` (naive, server-local timezone) was used instead of the project's own `now_ist()` at 4 sites: `correlation_tracker.py:91`, `dhan_data.py:189`, `dhan_data.py:245`, `market_regime.py:98` (the last of which already imports `now_ist` for other uses in the same file). All 4 switched to `now_ist()`.

**C. Section 10 — Data Provenance**: independently web-verified `brokerage_rate_pct`/`brokerage_min_inr` (config.py) against 8+ current published sources — Dhan's equity DELIVERY brokerage has been ₹0 since its 2021 launch, unchanged through 2026; the previous 0.06%/₹40-cap values were Dhan's INTRADAY rate, wrongly applied to this bot which trades delivery/CNC exclusively. Fixed both the config defaults (which feed `economics_brain.py`'s trade-viability calculations at 2 sites) and `utils.calculate_dhan_friction()`'s delivery branch (`is_intraday=False`) to charge ₹0 brokerage; the intraday branch is untouched. Real total friction corrected from an overestimated ~0.25-0.28% to a verified-accurate ~0.207%. Direction was always safety-conservative (overestimating cost, never underestimating it — no capital-loss exposure existed), but the EXTERNAL_FACT was genuinely incorrect, not merely stale.

**Verification**: `py_compile` clean on all 7 touched files. `test_sequence.py`: 118 passed, 0 failed (unchanged). pytest-style suites: 6 passed, 0 failed (unchanged). Functional tests: (1) brokerage — delivery friction on a ₹50k trade confirmed at exactly 0.207%, intraday friction unchanged; (2) DB-failure handling — genuinely broke the DB connection (not a faked flag) and confirmed `is_killswitch_active()` returns `True`, `is_db_failure_recent()` returns `True`, `get_active_trades()` degrades gracefully to `{}` without crashing, and everything self-clears correctly once the DB is restored.

---

## 2026-09-06 — Documentation Audit (Section 34) — v6.0.3-r11

Targeted, grep-based audit of all 44 shipped `.md` files for stale claims — specifically searched for the numeric/behavioral facts touched by r8/r9/r10 (brokerage rate, ATR smoothing method, RR "exact" wording, fail-open pattern mentions) to see if any documentation still described pre-fix behavior as current. Historical changelog entries (UPDATE_HISTORY_FIX_LOG.md itself, prd.md's numbered decision log D1-D26, SYSTEM_BLUEPRINT.md's round-by-round changelog) were correctly left untouched — they are past-tense records, not current-state claims, and describing what USED to be true before a fix is accurate history, not staleness.

**Found 2 genuine current-state staleness issues, both fixed**:
- `SYSTEM_BLUEPRINT.md` (§2.2, capital & position sizing): described `is_trade_economically_viable()`'s cost formula using the old `min(₹40, trade_value × 0.06%)` delivery brokerage — now corrected to reference the actual `brokerage_min_inr`/`brokerage_rate_pct` params (both `0.0` since r10) with a note explaining the r10 fix.
- `prd.md` (calculations table): same stale formula in the "Gate A/B" row — corrected to `brokerage 0%`.

No code touched this release. `py_compile` n/a (docs only). `test_sequence.py`: 118/118 (unchanged). pytest-style suites: 6/6 (unchanged).

---

## 2026-09-06 — Documentation/certification-artifact sync — v6.0.3-r12

User asked directly: the audit *process* document (external, not shipped in this ZIP) was updated, but does that mean the ZIP's own internal certification/status artifacts stay in sync too? Answer: not automatically — checked, and 5 files inside the ZIP were still reflecting an earlier round's numbers.

Updated, all as corrections-with-history (old figures kept inline, explicitly marked as prior-round, never deleted):
- `docs/CERTIFICATION_CLOSURE_REGISTER.md`: added 8 closure records for every fix made in r8-r11 (RR provenance, ATR smoothing, look-ahead leak, DB-failure/killswitch fail-open, timezone, brokerage provenance, documentation staleness), in the same evidence-linked format as the pre-existing 3 records.
- `docs/AUDIT_55_EXECUTION_SCORECARD.md`: top verdict/counts corrected (91/91→105/105 files, 1,074→1,057 universe rows, 67 passed/7 failed→118 passed/0 failed, "NOT READY"→"PRE-VPS ENGINEERING PASS"). The file's own detailed 55-row ledger was deliberately left as a category reference rather than hand-duplicated into current per-row statuses a second time, since maintaining the same information in two different table formats is itself a drift risk — it now points to the closure register as the authoritative source.
- `docs/CANONICAL_RELEASE_AND_AUDIT_TRUTH_INDEX.md`: stale "151 input files" corrected to 177.
- `docs/CURRENT_INSPECTION_STATUS.md`: new current-as-of-r11 section added above the existing 2026-08-26 round, which stays below unchanged.
- `SYSTEM_MASTER_MANIFEST.json`: `meta.date` updated (confirmed `test_sequence.py`'s manifest check reads `meta.version` and `domains`, not `date` — this change cannot break that test).

No code touched. `test_sequence.py`: 118/118 (unchanged). pytest-style suites: 6/6 (unchanged).
