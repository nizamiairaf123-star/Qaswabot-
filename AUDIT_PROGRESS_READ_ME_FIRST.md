# ⚠️ READ THIS FIRST — if you are an AI assistant opening this zip

This is **QASWA v6.0.3-r5 (owner 17-item fix-list applied, test-sandboxed,
DB-clean)** — base for ongoing 55-section audits. This file is overwritten
each time a new audit pass completes; it reflects the CURRENT state only, not
full history (see `UPDATE_HISTORY_FIX_LOG.md` for the full change log).

## r5 (2026-09-04) — what changed in this round

Owner supplied a 17-item fix list. Each item was checked against the code
BEFORE editing; where the list's premise was wrong this is stated openly
(items 1, 4, 5 partly; 6 had a different real bug). Full per-item detail:
`UPDATE_HISTORY_FIX_LOG.md` (top entry).

- **Live tick path now exists end to end:** `dhan_live_feed.py` (hardened) →
  `bot.py` post_init starts it, subscribes open positions, 60 s sync job →
  `trade_engine.on_live_tick()` → shared `_evaluate_exit_state()` → same
  `_execute_exit()`. 3-min monitor unchanged as safety net.
- **P0 startup crash fixed:** `setup_scheduler()` was called before the event
  loop (APScheduler 3.11 → `RuntimeError: no running event loop`); moved into
  post_init. `APScheduler==3.11.3` pinned.
- **ADX = true Wilder smoothing** (`strategy.py`, alpha=1/period) — proof in
  the changelog. Golden FLAT fixture replaced (old one was degenerate).
- **Board scanner (owner delegated the call):** single scanner for batch +
  monthly refresh; dual-community names (Kamal/Parveen/Iqbal/Kabir…) are
  ambiguous and cleared only with an unmistakable Hindu/Sikh/Jain marker in
  the same name; khan/syed/hussain-type tokens are never cleared; 100+ real
  Muslim names that no list had were added. Shipped universe re-checked with
  the same scanner: **12 companies with a Muslim director removed**
  (1,069 → 1,057). See `UPDATE_HISTORY_FIX_LOG.md` (5b).
- **Fallback visibility (`fallback_monitor.py`):** 9 dynamic→static sites
  now log + count; daily report + `/botstatus` print "Aaj X baar dynamic
  fallback hua". No fallback behaviour changed.
- **Tests can no longer contaminate the release tree** (`conftest.py` +
  `test_sequence.py` temp sandbox; verified byte-identical after both suites).
  `data/trading_bot.db` rebuilt schema-only (0 rows), logs truncated, test
  snapshot CSVs removed, manifest regenerated LAST from the clean tree.

**Still open / honest notes:** `web_search_confirm_religion()` remains a
placeholder — a director whose name is doubtful and has no clarifying marker
(e.g. "Kamal Dalia", "A. Chowdhury") stays BLOCKED until the owner confirms
manually (`board_manager.update_board_status(symbol, True, verified_by="owner")`).
On the first real monthly refresh up to ~39 previously-excluded companies
may legitimately re-enter (Hindu boards the old scanner over-blocked, e.g.
"Anil Kumar Malik IAS"); the admin success alert shows the count.
Live-feed behaviour against real Dhan WebSocket is an AFTER-VPS check
(`scripts/live_feed_dry_run.py`). Earlier r4 opens (ASM/GSM pre-screen,
cosmetic dead code) unchanged.

## Previous round (r4) — what changed vs the r4_DATA002_FIXED upload


**Purification/AAOIFI mechanism — fully removed** (owner does not want it,
not even the name). Deleted from `sharia_manager.py`
(`calculate_purification`/`get_purification_report`/`PURIFICATION_FILE` +
dead `_get_haram_pct` helper), `bot.py` (`/purification` command+menu),
`build_pdf_report.py` (PDF section), `trade_logger.py` (call on
trade-close). Tests rewritten to match. Docs corrected (not just stripped)
in `feature_sequence.json`, `SYSTEM_BLUEPRINT.md`, `INSPECTION_CHECKLIST_v2.md`,
`stock_selector.py`. Zakat (a separate, unrelated calculator) is untouched
and still works. `CUSTOM_UNIVERSE_FINAL.csv` still carries 4 now-dead
Sharia-ratio columns (`haram_income_pct`, `debt_mcap_pct`, `cash_mcap_pct`,
`illiquid_asset_pct`) — confirmed zero code reads them — cosmetic cleanup,
owner's call.

**Critical fix — `data/trading_bot.db` re-contaminated with fake/test
data (2nd occurrence of this exact bug class).** Fake subscribers wired to
receive live broadcasts, a fake forever-order that `startup_recovery.py`
would have reprocessed on every boot, fake trades/workflow/backtest-results
state. Reset to clean empty defaults matching each module's own code
default (verified via grep, not guessed). Recommend a pre-package check
going forward so this doesn't recur a 3rd time.

**Real bug fixed — `regime_manager.py` `get_current_regime()`** referenced
`DEFAULT_BEHAVIOR`, a dict deliberately deleted in a prior refactor. This
threw `NameError` on every single call, silently caught, always fell back
to `SIDEWAYS` regardless of the actual detected market regime — meaning
regime-adaptive position sizing never actually worked. Fixed to read from
`PARAMS["regime_behavior_defaults"]` (the correct v5.7 single-source-of-
truth, same one the adjacent working function already used). Confirmed
firing repeatedly in the shipped logs before the fix.

**Real bug fixed — `utils.py` `calculate_dhan_friction()` fee calculator**
(the cost model feeding the live trade-viability gate) had 3 internal
unit-consistency bugs: delivery STT only charged one side (0.1%) instead
of both buy+sell (0.2% round-trip, verified against current published
rates), stamp duty was incorrectly halved, and the currently-unused
intraday-STT branch had the same halving bug. Fixed to consistently treat
`trade_value` as one leg throughout (matching the already-correct
brokerage line and the actual call site's semantics). Independently
recalculated by hand: old code underestimated a ₹10,000 delivery trade's
real cost by ₹10.15 (~0.1%) — meaning every trade looked more profitable
than it really was in the economic-viability check.

**Real bug fixed — `broker.py` no network timeout on Dhan SDK calls.**
Added `call_dhan_with_timeout()` (ThreadPoolExecutor + hard 15s deadline)
— works regardless of the `dhanhq` SDK's own unconfirmed internal timeout
(its internals aren't inspectable here, so this avoids guessing at an
unsupported constructor kwarg). Applied to live order placement (times
out cleanly, returns an honest "order status UNKNOWN, verify manually"
result rather than assuming success/failure) and the boot-time holdings
check (TimeoutError propagates, matching that function's existing
fail-as-cannot-verify contract). Verified the wrapper in isolation.

**Real safety gap fixed — network-partition circuit-breaker was inert.**
The FIX-47 heartbeat detector (`scheduler.py`) always correctly detected
a real 2+ minute API outage, but nothing ever acted on that detection —
it just logged and did nothing. Wired `is_network_partition()` into
`trade_engine.py run_market_scan()`'s early gate (alongside the existing
killswitch check) — new entries now pause during a detected outage and
automatically resume once the heartbeat recovers. Existing positions'
exits are untouched. Verified end-to-end (block → recovery → unblock).
The separate `needs_reconciliation.json` flag (meant to eventually
trigger a full broker-vs-local reconciliation pass) is still unconsumed —
a distinct, lower-priority follow-up, intentionally not built this pass.

**Documentation fix — `VPS_DEPLOYMENT_GUIDE.md`** had `deploy.sh` and
`start_bot.sh`'s roles backwards: claimed `start_bot.sh` creates `.venv`
and installs requirements, but that's actually `deploy.sh`'s job.
`start_bot.sh` only runs the bot with an already-prepared venv. Fixed
the guide to describe both scripts correctly, in the right order.

**Hygiene:** removed shipped `.pytest_cache/` + compiled `.pyc` files,
cleared test-run-contaminated `audit_log.txt`/`bot.log`.

**Additional sections independently verified this pass (Sec 39, 31, 40,
42, 45)** — all found correct, nothing to fix: position-sizing arithmetic,
SL/TP/RR formula, and the Monte Carlo drawdown formula (all independently
recalculated by hand with concrete numbers), subscription trial/expiry
renewal logic (doesn't waste paid days, fails closed on corrupt dates),
copy-trade duplicate prevention (both BUY and SELL sides), PARAMS
key-name consistency across every definition/consumption site (no
typos), universe/board data pipeline atomicity (tmp-file + os.replace),
and capital-deployment multiplier scaling (stage/health/regime all
correctly 0-1 fractions, no unit mismatch like the fee-calculator bug).

## Open items — owner decisions applied this pass

1. **Sec 15 Sharia gate — still open, no decision given yet:** no
   proactive ASM/GSM (SEBI surveillance) or suspended-stock
   pre-screening. `broker.py` only recognizes "trading
   suspended"/"delisted" reactively, after a live order is already
   rejected — never blocks pre-trade. Needs a real ASM/GSM data source.
2. **Sec 19/20 Backtest realism — owner decision: no code change, mental
   adjustment instead.** Treat backtest results as roughly 10-15%
   optimistic vs what live would actually achieve (backtest fills at the
   exact close of the signal candle; live is unaffected — confirmed
   separately, it uses real-time price + its own fill-gap-warning
   mechanism).
3. **Sec 28 Network timeout — FIXED** (see above).
4. **Sec 41/28 Network-partition circuit-breaker — FIXED** (see above).
5. **Sec 41 Dead code (cosmetic) — still open, no urgency:** all 51
   automated candidates individually hand-verified this session. 2 were
   false positives (`do_POST`/`log_message` in payment.py are live
   HTTP-framework-invoked webhook handlers, not dead). The remaining ~48
   are confirmed genuinely dead — including `calc_macd()`/
   `calc_bollinger()` (strategy.py), `save_zakat_date()`/
   `get_zakat_date()` (sharia_manager.py), `can_trade()`/
   `can_exit_trade()` (subscriber_manager.py — confirmed superseded by
   `_subscriber_status_allows()` in broker.py, not a missing gate),
   `is_trading_paused()`/`get_daily_risk_used()` (safety_manager.py —
   confirmed superseded by `bot_state_manager.get_state()` called
   directly elsewhere). No functional impact from any of these. Safe to
   ignore or clean up anytime.

## Final Verdict

🟡 **CONDITIONAL** — no P0/critical blockers remain (all found this
session are fixed and verified with zero regressions, including both
network items just closed). Sec 15 (ASM/GSM) and Sec 41 (cosmetic dead
code) are still open with no owner decision yet. Sections 47-49
(failure-injection, exhaustive false-pass audit, full runtime trace)
still need real paper/live environment testing that a static-analysis
sandbox cannot provide — an honest, disclosed limitation, not a gap
papered over.

## What was independently re-verified (not just carried over)

Every section below was actually re-checked against THIS r4 base per
Rule 0 (never trust a prior audit's claims without independent
verification) — not assumed from an earlier zip's results:

Sec 1-46 (ZIP integrity, file inventory, source/import graph,
requirements, config/secrets, numeric duplication, CSV structure, data
semantics/provenance, JSON state, database, logs, cache hygiene, Sharia
gate, liquidity, market data, look-ahead scan, exit/risk/order engines,
admin auth, scheduler locking, fail-closed sweep, network, crash
recovery, optimizer WFV isolation, subscription/copy-trading, manifest,
timezone, state machine, reconciliation wiring, cross-file PARAMS
consistency, data-pipeline atomicity, capital-deployment scaling) —
substantively checked, several with independent hand-recalculation
(fee formula, SL/TP/RR, position sizing, Monte Carlo drawdown). Sec 41
dead-code: all 51 automated candidates individually verified, not just
sampled. Sec 32/34 deployment/docs: scripts and systemd unit verified
against actual behavior. Sec 47-49 (failure-injection, false-pass,
runtime-trace) need REAL paper/live environment testing — not achievable
via static code analysis alone.

## Test baseline (unchanged through every edit this session)

`test_sequence.py`: **37 passed, 1 failed (pytz missing — sandbox-only,
not a code bug), 8 external-required (self-flagged, fail-closed)**.
Verified after every single fix above — zero regressions introduced.

## Status

Full 55-section pass complete to the extent this static-analysis sandbox
allows, including 2 of 5 flagged items now fixed per owner decision. Sec
15 and Sec 41 remain open pending owner decision; Sec 47-49 remain open
pending real-environment testing.

## FIX-Claude-1 (2026-09-01) — QUANT-002 RESOLVED, QUANT-001 PARTIALLY RESOLVED

QUANT-002: RESOLVED. New `portfolio_backtest_engine.py` replays every symbol's
candidate trades chronologically through ONE shared simulated portfolio,
applying the 4 gates that are genuinely point-in-time reconstructable:
max_slots (dynamic economics-based), max_stocks_per_sector, correlation_threshold
(PIT-safe), reentry_cooldown_days. Wired additively into
`backtester.run_full_backtest()` as `portfolio_max_dd_pct_concentration_gated`
(existing `portfolio_max_dd_pct` untouched — 5 other modules consume it).
Bonus fix in the same pass: `economics_brain.py` never imported `PARAMS`, so
its own dynamic max_slots feature always NameError'd and silently fell back
to a static value — added the missing import. Verified with
`test_portfolio_backtest_engine_QUANT002.py` (6/6 pass: correlation block,
sector-cap block, max-slots block, cooldown block, cooldown-expiry-allows,
economics_brain dynamic path runs clean).

QUANT-001: PARTIALLY RESOLVED. Checked directly — no historical
universe-eligibility archive exists anywhere in this zip. True retroactive
point-in-time correction of past backtest years is not achievable without
fabricating data that was never captured. Fixed the honestly-fixable part:
new `universe_snapshot_manager.py` captures a dated snapshot of the eligible
universe on every successful refresh, wired into
`scheduler._monthly_board_universe_update_job()`'s success branch (fail-open,
never blocks the refresh itself). `backtester.run_full_backtest()` output now
carries an explicit `universe_point_in_time_status` field stating the
limitation plainly instead of silently implying full historical accuracy.
Verified with `test_universe_snapshot_manager_QUANT001.py` (5/5 pass).
Remaining gap is a data-availability limit, not a code gap — backtest
results before the first captured snapshot date can never be made
point-in-time accurate; accuracy improves monthly as snapshots accumulate
from here forward.

Still open: DATA-001 (universe sector/industry/market_cap/liquidity fields
empty — needs real external data refresh), EXT-001 (external-only evidence,
not sandbox-testable).
