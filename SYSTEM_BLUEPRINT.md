# QASWA v6.0.3 — Halal Algorithmic Trading Bot — Complete System Blueprint (ZIP-DERIVED r3)

> **CANONICAL DATA-SOURCE POLICY:** `DATA_SOURCE_POLICY.md` — Dhan is mandatory for every trading-data and execution path; yfinance is company-information only and cannot provide OHLCV/price/volume to trading behavior.


> **CANONICAL GOVERNANCE — QASWA v6.0.3:** Product scope and intended behavior are defined by this document and the package code; inspection is governed by `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md`, using `docs/MASTER_ZERO_OMISSION_ZIP_INSPECTION_CONSTITUTION_55_SECTIONS.md` as the unchanged 55-section backbone. The authority chain is **55 Sections → Quality/Defect Gate → Evidence Classification → Release Verdict**. Framework freeze does not certify the VPS/live environment. The current phase is PRE-VPS engineering verification; AFTER-VPS external evidence remains mandatory.


**Purpose of this document:** This is a full technical specification of the bot — every module, what it does, how it connects to every other module, and which parts implement a named, sourced, industry-verified method vs. an owner-designed custom rule. It is written so that if the codebase is ever lost, corrupted, or needs to be handed to a new developer (or a new AI session with no memory of prior work), this document alone is enough to understand the system deeply enough to rebuild it, debug it, or extend it correctly — the *logic and reasoning*, not just a file listing.

**Architecture identity (added 2026-09-07, owner-supplied, see `prd.md` Rule 14):** the combined architecture is named **QASWA Remix** (owner: AIRAF NIZAMI). Rules 2-3 (Business Halal Filter, Non-Muslim Board Filter) are the two mandatory hard gates; everything below in this Blueprint is **SEQ** — QASWA's internal label for the systematic/quant industry-alignment layer, not a claimed pre-existing methodology name.

**How to read this:** Section 1 gives the big picture (what happens, start to end, in one trading day). Section 2 goes module-by-module. Section 3 is a single consolidated table of every verified method used, with creator/year/source — this table is what satisfies Rule 14's SEQ attribution requirement (genuine method/creator cited, no invented single creator). Section 4 is the configuration reference. Section 5 is the bug-fix changelog across all audit rounds (what was broken, why, and how it was fixed — critical context for any future maintainer). Section 6 is setup/rebuild instructions. Section 7 states this document's own limits honestly.

**Audit context (supersedes all earlier versions of this document):** This is Round 8 of a multi-session audit. Round 1: 56 files, 8 bugs (5.1). Round 2: 74-file zip with the Sharia+Board subsystem, 11 fixes (5.2). Round 3: turnover-liquidity screen (MSCI ATVR) + critical backtest/live parity fix (5.3), codebase now 75 files. Round 4: removed financial-ratio screening entirely per an explicit user scope decision (5.4). Round 5: dedicated audit of `bot.py`, the admin/user command-and-interaction layer (5.5). Round 6: dedicated audit of the subscriber/copy-trading business layer (5.6). Round 7: user questioned whether the liquidity screen (ATVR/FoT) and the volume-confirmation filter (`is_volume_confirmed`) were redundant, and whether MSCI's own methodology actually specifies monthly review — researched and clarified both, honestly disclosed a cadence deviation from MSCI's literal methodology (5.7). **Round 8 (v6.0):** Advanced signal generators (RSI Divergence, Volume Divergence, Candle-Volume, MTF Composite), Per-stock Tool Parity (any 1..11 selected tools), SL Hunt Protection (body close rule + wick analysis), Mode Switching (/paper, /live, /livefull), Help System update, MTF composite/warehouse, 8x Bug Fix, Subscriber Order Fix, Breakeven with Fees, min_reward_risk Fixed. **Every previous version of this blueprint (and the smaller `blueprint.md`/`architecture.md` stub docs) is now stale — this file is the only one to trust.**

## ⚠️ CURRENT ZIP DATA READINESS — 1,074-row custom universe is not deployment-ready

The current ZIP snapshot contains **2,158 master rows**, **1,966 board-positive rows**, **192 board-negative rows**, and **1,057 custom-universe rows**. The current `CUSTOM_UNIVERSE_FINAL.csv` contains the decision-critical columns `sector`, `industry`, `market_cap`, `turnover_liquid_ok`, `atvr_pct`, and `frequency_of_trading_pct`, but all six are currently unpopulated. `data/custom_universe_state.json` records `BOARD_DATA_STALE_PAUSE=true` and the release-data-readiness block.

The historical **975/1081 haram_pending** statement belongs to an older snapshot and is not the current ZIP baseline. It remains historical evidence only and must not be used as a current universe count.

Missing decision data must be populated from the declared real provider; it must never be fabricated. Until the refresh succeeds and is evidenced, trading remains blocked.

## 1. Big-Picture Architecture: A Trading Day, Start to End

```
  ┌─────────────────────────────────────────────────────────────────────┐
  │  MORNING (scheduler.py jobs)                                        │
  │  release_due_funds (sebi_manager) → check_corporate_actions          │
  │  → _market_data_refresh_job (sector_strength + fii_dii_tracker,      │
  │    9:05 AM — now alerts admin on failure/staleness, see 2.5)         │
  │  → _monthly_board_universe_update_job (1st of month 08:30 IST —      │
  │    refreshes the Sharia+Board-screened universe; on failure sets     │
  │    BOARD_DATA_STALE_PAUSE=True which blocks ALL new BUYs until fixed,│
  │    retries daily 08:30) → subscription auto-expiry check             │
  │  → heartbeat job starts                                              │
  └───────────────────────────┬───────────────────────────────────────┘
                              ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  MARKET SCAN LOOP (trade_engine.run_market_scan, every N minutes)    │
  │  1. Get tradeable universe (stock_selector.py) — a stock must be:    │
  │     Sharia-compliant AND 100% confirmed Non-Muslim board AND         │
  │     price>₹100 AND liquid AND strict NSE-EQ AND board data not stale │
  │  2. Per stock: fetch candles (dhan_data.py, Dhan only — never yfinance│
  │     — yfinance is used ONLY for board-of-directors names, verified   │
  │     via full-codebase grep, see 2.6)                                 │
  │  3. Generate signal (strategy.py, using per-stock optimized params)  │
  │     — this step ALSO applies the macro-context filter                │
  │     (get_macro_context): FII/DII bearish → block; sector NOT STRONG  │
  │     → block (long-only bot, see 2.5 — NEUTRAL sectors are now        │
  │     blocked too, only STRONG passes)                                 │
  │  4. Pass signal through the RISK GATE CHAIN (risk_manager.py) —      │
  │     a signal only becomes a trade if EVERY gate below says "allow":  │
  │       a. Halal + Board universe membership (defense-in-depth,        │
  │          checked again here even though stock_selector already did)  │
  │       b. Capital-survival override (survival_manager.py CIRCUIT)     │
  │       c. Stage-readiness (capital_manager.py, workflow-linked)       │
  │       d. Backtest freshness (backtester.py staleness check)          │
  │       e. Daily loss limit (safety_manager.is_daily_limit_hit)        │
  │       f. Max concurrent trades / free slot — max_slots now comes     │
  │          from a real economics formula (capital vs brokerage/        │
  │          subscription-fee-per-trade costs), not just a static number │
  │          (capital_manager.py, economics_brain.py — see 2.2)          │
  │       g. Daily risk BUDGET, not just loss (safety_manager, 2% cap)   │
  │       h. Rapid-loss-streak pause (safety_manager, geometric method)  │
  │       i. Strategy health circuit-breaker (strategy_validator.py)     │
  │       j. Sector exposure/concentration cap (max 2 stocks/sector)     │
  │       j2. Sector STRENGTH (defense-in-depth re-check — same STRONG-  │
  │          only rule as step 3, fails closed on any error)             │
  │       k. News sentiment (news_analyzer.py)                           │
  │       l. Economic viability after costs (capital_manager.py)         │
  │       m. Stock's own mode: not SOFT/HARD-BLOCKED (stock_mode_manager)│
  │       n. Same-day CNC exit possible (intraday_filter — BE/T2T skip;  │
  │          not an MIS switch. Entry allowed + exit banned → no entry)  │
  │  5. If ALL pass: size the position (Half-Kelly + health + regime +   │
  │     confidence multipliers, capital_manager.py) → place order        │
  │     (broker.py, real or paper depending on bot_state_manager state)  │
  │     → immediately place 2 broker-side GTT stop-loss orders (Hard SL  │
  │     + Trail SL, forever_order_manager.py) with retry+admin-alert if  │
  │     either fails to place — a position is never left unprotected     │
  │     silently                                                         │
  └───────────────────────────┬───────────────────────────────────────┘
                              ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  POSITION MONITORING (trade_engine.py, forever_order_manager.py)     │
  │  Track price vs SL/TP1 → breakeven shift after TP1 → trailing SL →   │
  │  exit on SL/TP/trail only (MARKET CNC, 09:15–15:30; Dhan AMO has no  │
  │  MARKET). No EOD/15:20 square-off. Overnight hold via CNC + GTT.     │
  │  On exit: cancel both GTT orders — retry+admin-alert if a cancel     │
  │  fails, and keep the local record (flagged) instead of silently      │
  │  losing track of a possibly-still-live broker-side order             │
  └───────────────────────────┬───────────────────────────────────────┘
                              ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  EXIT & BOOKKEEPING                                                  │
  │  trade_logger.py: P&L calc (net of brokerage) → sharia_manager.py:   │
  │  Zakat calc → safety_manager: record win/loss for                    │
  │  streak & daily-budget tracking → capital_manager: release slot      │
  └───────────────────────────┬───────────────────────────────────────┘
                              ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  CONTINUOUS BACKGROUND SYSTEMS (run in parallel throughout the day)  │
  │  • Reconciliation vs broker (trade_engine.run_reconciliation)        │
  │  • Heartbeat / network-partition detection (scheduler.py)            │
  │  • External dead-man ping (HEALTHCHECK_URL, 24/7; empty=skip)        │
  │  • Portfolio health scoring (portfolio_health.py)                     │
  │  • Regime detection (market_regime.py HMM + regime_manager.py)       │
  │  • Sector-strength + FII/DII daily refresh with failure/staleness    │
  │    alerting (scheduler._market_data_refresh_job, see 2.5)            │
  │  • Monthly board-universe refresh with fail-closed pause (see above) │
  │  • Stage-deployment progression (capital_manager, workflow_manager)  │
  │  • Subscriber copy-trading + billing state (subscriber_manager, bot) │
  │  • MTF (multi-timeframe) data warehouse + tournament framework —     │
  │    configured enabled in the shipped configuration (`MTF_ENABLED=True`), but the     │
  │    affect live trading unless explicitly turned on (see 2.11)        │
  └─────────────────────────────────────────────────────────────────────┘
```

**The one sentence version:** the bot never lets a single "this looks profitable" signal become a trade — it must clear the Sharia+100%-Non-Muslim-board screen, a long-only sector-strength STRONG-only filter, an FII/DII macro check, and roughly a dozen more independent, mostly fail-closed safety checks, each its own module with its own verified method, wrapped in a 10-stage manual-approval pipeline (`workflow_manager.py`) that a human (the owner) must move forward at each major milestone.

---

## 1.1 ZIP-DERIVED COMPLETE IMPLEMENTATION SCOPE

The current archive contains **203 files** (as of r37, 2026-09-20 — 11 new Python files added at r32/r33's ARCH-003 god-module split: `scheduler.py` (1336→387 lines) split into `scheduler_jobs_core.py`, `scheduler_jobs_daily_ops.py`, `scheduler_jobs_market_data.py`, `scheduler_jobs_board_universe.py`, `scheduler_jobs_research.py`; `bot.py` (1682→546 lines) split into `bot_helpers.py`, `bot_commands_account.py`, `bot_commands_trading.py`, `bot_commands_admin.py`, `bot_commands_research.py`, `bot_livefeed.py` — both original files kept as thin orchestrators (`setup_scheduler()`/`main()` unchanged, still own all job/command registration); was 191 at r30 — `telemetry.py` + `test_telemetry.py` added for Rule 16; was 189 at r29, 190 at r27 — the foreign tooling artifact `ai_dos_config.json` was purged at r29 — and 168 at an earlier r3 baseline; figures corrected, not deleted, per this project's own no-silent-drift convention): **122 Python, 53 Markdown, 8 JSON, 6 CSV**, plus SQLite, service, shell, environment/requirements/version and package artifacts. Every material artifact is in inspection scope.

### 22 runtime domains represented by the shipped manifest
1. canonical_pipeline
2. workflow_gates
3. sharia_universe
4. data_engineering
5. market_analysis
6. strategy_optimization
7. validation
8. deployment
9. order_execution
10. exit_toolkit
11. overnight_movers
12. risk_capital
13. subscriber_lifecycle
14. payment_system
15. command_interaction
16. number_provenance
17. monitoring_ops
18. tests_verification
19. deploy_readiness
20. entry_follow_execution
21. seq_rule14_alignment
22. ndsap_data_segregation_accumulation_rule15

### New / previously under-described implementation areas
- `entry_follow.py` + `shadow_log.py` — resting-entry execution and observation-only shadow path.
- `mtf/` — timeframe warehouse, derivation, guards, statistics, tournament and depth probing.
- `scripts/` — release preflight, live-feed dry run, decision-data refresh and dependency freeze.
- Supporting runtime modules — Dhan client/feed, market metadata, corporate actions, DB/log setup, reporting/PDF, crypto, drawdown policy and risk display.
- Shipped decision data — universe/board CSVs, finance wordlists, board-members JSON, state/provider JSON and SQLite DB.

### 55-section sufficiency decision
The newly identified components fit the existing 55-section backbone. No new section is required at this baseline. New sections are permitted only for a genuinely independent material risk class introduced by declared scope.

## 2. Module-by-Module Reference

Each entry: **what it does**, **what it depends on / feeds into**, **verified method used (if any)**.

### 2.1 Risk & Safety Layer

**`safety_manager.py`** — Daily-level circuit breakers.
- `is_daily_limit_hit()`: blocks new entries if today's realized P&L drop hits the configured max (`daily_loss_limit_pct`, default 2%, but see 2.2 — the *real* enforced ceiling is dynamic).
- `is_daily_risk_budget_hit()` / `record_risk_used()`: tracks *cumulative allocated risk* (not just realized loss) across all of today's trades against the same dynamic daily budget.
- `is_max_trades_hit()`: caps trades/day regardless of outcome.
- Rapid-loss-streak pause: after *k* consecutive losses, pause trading. *k* is derived per-stock from that stock's own verified win rate (Geometric Run-Length Tail probability — see Section 3).

**`risk_manager.py`** — The entry gatekeeper. `can_enter_trade(symbol, price)` chains together the checks in Section 1's diagram — every one must return "allow" or the trade doesn't happen. **[Round 2 addition]** now also independently re-checks sector strength (defense-in-depth, matching the pattern already used for the halal/board check) — fails closed on any error.

**`risk_override_manager.py`**, **`survival_manager.py`**, **`capital_drawdown_manager.py`**, **`portfolio_health.py`**, **`correlation_tracker.py`** — unchanged from Round 1 (see Section 3 for their verified methods); no issues found in Round 2 re-audit.

**`stock_mode_manager.py`** — Per-stock PROFIT → SOFT_BLOCKED → RECOVERY / HARD_BLOCKED state machine, buffer/recovery-days from `dd_policy.py`. Re-audited in Round 2: clean, no bug. New/unseen stocks default to PROFIT (untriggered starting state, not an error-driven fail-open).

**`dd_policy.py`** — Supplies per-stock recovery-day estimates (Follow-Through Day method, O'Neil 1988). Re-audited in Round 2: clean — every "insufficient data" path returns `None` so the caller uses its safe static fallback, never a fabricated number.

**`intraday_filter.py`** — **Not an MIS / intraday-product switch.** Bot is CNC swing (delivery, overnight hold). This filter only blocks symbols where **same-day CNC exit is impossible** (BE / T2T / non-EQ series: entry may be allowed, exit banned). If SL/TP hits, the bot could not sell — so it never enters. EQ series = same-day CNC sell possible → allow. Fails closed on every missing-data or error path.

### 2.2 Capital & Position Sizing

**`capital_manager.py`** — Given a risk-approved trade, computes exact quantity and position sizing multipliers (Half-Kelly + health + regime + confidence, unchanged from Round 1 — see Section 3).
- `is_trade_economically_viable()`: rejects a trade if expected net profit after realistic transaction costs isn't positive. Cost formula: `brokerage = min(brokerage_min_inr, trade_value × brokerage_rate_pct)` + `statutory = trade_value × 0.25%` + `subscription_fee ÷ trades_per_month`. **[r10 Section-10 fix, 2026-09-06]** `brokerage_min_inr`/`brokerage_rate_pct` are now `0.0`/`0.0` — Dhan charges ₹0 brokerage on equity DELIVERY (verified against 8+ current sources incl. Dhan's own pricing page, true since Dhan's 2021 launch; this bot trades delivery/CNC exclusively). The previous `₹40 / 0.06%` values were Dhan's INTRADAY rate, wrongly applied here — see `UPDATE_HISTORY_FIX_LOG.md` r10 entry. **This exact cost model is now reused (not reinvented) by the new `max_slots` economics calculation below.**
- `has_free_slot()` / `get_portfolio_allocation_fraction()`: **[Round 2 fix, Gap #11]** `max_slots` is no longer a purely static owner-picked number — it's now computed by `economics_brain.get_recommended_max_slots(current_capital)`, which answers the exact question "given my capital and a fixed 2%-daily-risk budget split across N slots, how many slots can I run before the per-trade fixed subscription-fee cost eats too much of a shrinking trade size?" Falls back to the static `PARAMS["max_slots"]` on any failure (never blocks trading due to an economics-calc bug). Still clamped inside the owner's approved 5-12 band.
- `get_sector_strength_multiplier()`: **[Round 2 fix]** now fails to a conservative 0.3 floor (not a neutral 1.0) on any error — consistent with the new hard-gate philosophy for sector strength (see 2.5).

**`economics_brain.py`** — Owns:
  1. `min_reward_risk` (fixed exactly 1.8R; after the lock, trailing handles uncapped profit).
  2. **[Round 2 addition]** `calculate_max_slots_candidate()` / `get_recommended_max_slots()` — the real max_slots formula described above.
  3. **[Round 2 documentation fix]** An honest doc-comment now states plainly: of the 14 parameters in this file's `BANDS` framework, only `max_slots` and `min_live_win_rate` are actually calibrated from data today. The other 12 (`target_portfolio_vol`, `health_active/caution/warning_min`, `stage_up/down_win_rate`, `max_wr_gap_vs_backtest`, `max_consecutive_losses_validator`, `profit_degradation_alert_pct`, `max_idle_trading_days`, `backtest_warn/block_days`, `mc_robustness_min`) remain static at their owner-approved fallback values — genuinely calibrating them from live/paper trade history is a bigger feature that has NOT been built. **Do not assume or claim otherwise in future work — check `resolve_param()`'s actual callers before trusting a "live-cal" tag in this file.**

### 2.3 Strategy & Signal Generation

**`strategy.py`** — Generates BUY-only signals (confirmed long-only design) using per-stock optimized parameters.
- **[Round 2 fix]** `get_macro_context()` / `_get_sector_context()`: previously allowed a NEUTRAL-status sector to pass ("status != WEAK"); now requires "status == STRONG" specifically, matching the user-confirmed design decision that a long-only strategy should only take new positions in sectors showing confirmed relative-strength outperformance (see 2.5 for the full reasoning and citations).
- FII/DII bearish check (`is_market_bearish`, point-in-time T-1 lagged, no look-ahead bias) — unchanged, confirmed a genuine hard block.

**`strategy_tools.py`** — **[Round 8, v6.0]** Now contains 11 signal generators:
1. `ema_cross` — EMA crossover (trend following)
2. `rsi_ema` — RSI + EMA (momentum)
3. `breakout` — Price breakout (breakout)
4. `support_bounce` — Support + RSI (mean-reversion)
5. `vwap_bounce` — VWAP crossover (volume-price)
6. `bollinger_reversion` — Bollinger Bands (mean-reversion)
7. `connors_rsi2` — Connors RSI-2 (pullback)
8. `rsi_divergence` — **[NEW v6.0]** Price Lower Low + RSI Higher Low = bullish reversal (TradingView, MQL5, SaintQuant verified)
9. `volume_divergence` — **[NEW v6.0]** Price Lower Low + Volume Decreasing = smart money accumulation
10. `candle_volume` — **[NEW v6.0]** Small candle + High volume = accumulation, breakout likely
11. `mtf_composite` — **[NEW v6.0]** 5-criteria combined signal (trend + RSI divergence + volume divergence + candle-volume + RSI oversold)

**`strategy_validator.py`** — unchanged from Round 1.

### 2.4 Optimization & Validation

**`optimizer.py`** — **[Round 8, v6.0]** Now supports **Multiple Combo Per Stock** — optimizer selects a per-stock toolset from all 11 registered signal generators using OOS/FDR evidence; the selected set may contain 1..11 tools, with no fixed TOP-N cap. The live strategy consumes the selected toolset with its stored vote threshold. `top_combos` is retained only as a compatibility field and is not a governing criterion. Also includes:
- **8x Bug Fix**: Compounding formula corrected — `capital *= (1 + net / smax)` (was missing `/smax`)
- **min_reward_risk**: Fixed 1.8R lock; optimizer does not select RR (floor-lock constraint)
- **New parameters**: wick_multiplier, candle_body_ratio, candle_wick_ratio, candle_confirmation, candle_volume_mult, divergence_lookback, rsi_tolerance, volume_lookback, volume_threshold, candle_size_threshold, volume_spike_threshold, mtf_min_score

**`walk_forward_validator.py`**, **`parity_engine.py`**, **`monte_carlo.py`** — unchanged from Round 1 (see Section 3).

**`backtester.py`** — **[Round 3 fix, critical parity bug]** `load_halal_symbols()` previously returned EVERY symbol in the universe CSV, completely ignoring the per-row eligibility flags (`core_business_halal`, `non_muslim_board`, `price_gt_100`, `is_liquid`) that `stock_selector._row_is_halal_eligible()` enforces live — meaning backtests could silently include haram stocks, Muslim-board stocks, sub-₹100 stocks, or illiquid stocks that would never actually be traded live. This was found while implementing the turnover-liquidity screen (Section 2.5) and fixed as the necessary foundation first: `load_halal_symbols()` now calls the exact same `stock_selector.load_halal_universe()` + `_row_is_halal_eligible()` used live — single source of truth, so ANY future universe-eligibility change (including the new liquidity screen) automatically applies identically to both backtest and live, with no separate backtester-side maintenance ever needed again.
- **[Round 8, v6.0]** **8x Bug Fix**: Compounding formula corrected — `capital *= (1 + (net_return * combined_mult) / smax)` (was missing `/smax`)

### 2.5 Market Data & Context


**`dhan_data.py`**, **`market_regime.py`**, **`regime_manager.py`**, **`corporate_actions.py`**, **`news_analyzer.py`** — unchanged from Round 1.

**`sector_strength.py`** — **[Major Round 2 rework]** Fetches NSE sector-index breadth data (advance/decline, % change) daily, NOT from Dhan (Dhan doesn't provide sector-index breadth) and NOT from yfinance. Classifies each sector STRONG/NEUTRAL/WEAK.
  - **Method: Relative Strength sector rotation.** Creators: **Jegadeesh & Titman (1993)**, "Returns to Buying Winners and Selling Losers," *Journal of Finance* (the foundational momentum/relative-strength result); applied to sector rotation per **William O'Neil**'s and **Mebane Faber**'s sector-rotation writing. **[Round 2 design change, user-confirmed]**: for a long-only bot, established practice is to fully avoid non-outperforming sectors for new entries, not merely downsize into them — there is no verified edge in going long specifically because a sector is weak. `get_sector_runtime_signal()` now requires BOTH the dynamic regime/correlation-adjusted threshold check AND the raw classification being exactly STRONG (previously NEUTRAL could pass).
  - **[Round 2 fix, Gap #12]** `refresh_sector_data()` now returns True/False so a total NSE-scraper-block failure (a real, common risk) is detectable — previously it failed completely silently (no exception, no return value).
  - **[Round 2 fix]** This is now the single source of truth for "is this sector tradeable" — `strategy.py`'s signal-generation filter and `risk_manager.py`'s defense-in-depth gate both defer to it, closing a previous bug where two independently-scored mechanisms could disagree.

**`fii_dii_tracker.py`** — Tracks FII/DII (Foreign/Domestic Institutional Investor) net flow, from NSE + a Groww scrape fallback (not Dhan, not yfinance). Point-in-time correct (T-1 publication lag applied before use, verified no look-ahead bias). Is a genuine hard block on new signals when bearish (`is_market_bearish`, checked in `strategy.get_macro_context()`).
  - **[Round 2 fix, Gap #12]** `refresh_fii_dii_data()` now returns True/False on every path (previously silent on failure).

**`stock_selector.py`** — Owns the tradeable universe: Sharia-compliant AND 100%-confirmed-Non-Muslim-board AND price>₹100 AND liquid AND strict NSE-EQ.
  - **[Round 2 fix, Bug #9]** `is_universe_data_stale()` was docstringed "Fail-Closed" but its exception handlers actually fell through to "not stale" (fail-open) on any read/parse error or unparseable timestamp — meaning a genuinely broken board-refresh could go undetected instead of pausing trading. Now genuinely fails closed: any read/parse failure → treated as stale → `BOARD_DATA_STALE_PAUSE` engages → all new BUYs blocked until fixed. Only a truly-missing state file (first ever run) returns "not stale."
  - `_row_is_halal_eligible()`: confirmed fail-closed on missing board data or any exception — no change needed, already solid.

**`scheduler._market_data_refresh_job()`** — **[Round 2 fix, Gap #12]** Previously a sector/FII refresh failure only wrote to a local log file nobody watches live — unlike the board subsystem's monthly-retry-and-alert pattern, there was NO admin notification if NSE blocked the scraper for weeks. Now tracks consecutive-failure counts and last-success timestamps persistently (`data/market_data_health.json` via the existing SQLite-backed `load_json`/`save_json`), and sends an admin Telegram alert on first failure, again daily while unresolved, and a recovery alert once it succeeds again. This is **visibility only, not a hard trading pause** — sector-strength's own STRONG-only gate already degrades conservatively when data is stale.

**`liquidity_screen.py`** — **[New, Round 3]** Answers a different question than `_is_liquid()` in `stock_selector.py` (which is the Sharia illiquid-*assets* balance-sheet ratio) — this is real trading-*volume* liquidity: does this stock always have an active buyer/seller, sized relative to its own market cap, so exit is reliably easy and not just entry? User's own words: "entry ho jati hai lekin exit ke waqt buyer nahi milta" (can get in, but no buyer at exit).
  - **Method: ATVR (Annualized Traded Value Ratio) + Frequency of Trading.** Source: **MSCI Global Investable Market Indices Methodology** (msci.com) — a published, industry-standard, size-normalized liquidity screen used for index-inclusion eligibility. ATVR = annualized average daily traded value ÷ market cap (bigger companies need proportionally more absolute turnover to count as liquid). Frequency of Trading = % of days in the lookback window with at least one actual trade (directly answers "is a buyer/seller always present"). MSCI's own Emerging-Markets minimums (India is EM) are used as defaults: ~15% 3-month ATVR, ~80% 3-month Frequency of Trading, 63-trading-day (~3 month) lookback — all owner-adjustable in `config.py`.
  - **[Round 6, honest cadence disclosure — user asked directly]** MSCI's own methodology reviews this as part of **Quarterly/Semi-Annual Index Reviews** (confirmed via MSCI's published GIMI methodology docs), and requires the minimum to hold over **4 consecutive quarters** (~1 year of persistence) before a security qualifies — not a single snapshot. This bot's refresh cadence is **monthly**, checking only the latest 63-day window each time, with no multi-quarter persistence requirement. **User confirmed (owner decision): keep monthly** — more frequent than MSCI's own cadence, so liquidity deterioration is caught faster; this is an intentional deviation, not an oversight. The ATVR/FoT *ratio formulas and threshold values* are MSCI's; the *review schedule* is this bot's own choice.
  - **[Round 6] Volume confirmation is a separate, complementary filter, not a duplicate.** `strategy.py`'s `is_volume_confirmed()` (today's volume > 1.5× its own 20-day average) implements **Relative Volume (RVOL)**, a widely-used, industry-recognized technical-analysis indicator (documented by StockCharts ChartSchool and other TA references) — used to confirm a *specific day's* price signal has real backing, checked per-trade-signal. This answers a different question than ATVR/FoT (which is a *monthly, structural* "is this stock chronically liquid" universe-eligibility gate): even a chronically-liquid stock has some days with below-average volume, and a breakout signal on such a day is considered weaker. The commonly-cited RVOL breakout-confirmation threshold in retail trading education is also ~1.5× — matching this bot's existing `vol_mult` default, so it isn't an arbitrary number. Unlike ATVR (one specific MSCI-published formula), RVOL is a broadly-adopted convention documented by multiple sources rather than tied to one single named creator/paper.
  - `calculate_atvr_and_fot(candles, market_cap, lookback_days)`: fails closed (not eligible) on missing data, missing market cap, or insufficient history (e.g. a recent IPO with too few trading days to trust the ratio).
  - `refresh_liquidity_data()`: scores every universe symbol using Dhan historical data (NOT yfinance — same data-source discipline as the rest of the bot) and writes `turnover_liquid_ok`/`atvr_pct`/`frequency_of_trading_pct` columns back into `CUSTOM_UNIVERSE_FINAL.csv`. Returns True/False so the scheduler can detect a total failure (mirrors the Gap #12 pattern).
  - `is_liquidity_data_stale()`: same fail-closed staleness design as Bug #9's fix — any parse/read failure is treated as stale; only a genuinely-never-run state returns "not stale" (bootstrap case). Folded into `stock_selector.is_universe_data_stale()` (the SAME single choke-point the board subsystem already uses) so every one of that function's existing callers automatically inherits this protection with no per-call-site changes needed.
  - Wired into `stock_selector._row_is_halal_eligible()` as `_is_turnover_liquid()` — fails closed (blocks) if a symbol has never been scored. **Bootstrap requirement**: `refresh_liquidity_data()` must run at least once (like `board_filter_auto.py`) before any symbol can pass this check — see Section 6 setup instructions.
  - **Scheduling**: monthly, 30 minutes BEFORE the board/universe sync job (not after) — order matters, since the sync job's own eligibility filter depends on `turnover_liquid_ok` already being fresh. Daily retry mirrors the board pattern.
  - Because `risk_manager.can_enter_trade()`'s defense-in-depth check already calls `stock_selector.is_in_halal_universe()` → `_eligible_halal_universe()` → `_row_is_halal_eligible()`, this new filter is automatically covered there too — **no separate risk_manager code was needed**, a direct benefit of wiring into the single-source-of-truth function rather than adding a parallel check.

### 2.6 Sharia / Regulatory Compliance

**`sharia_manager.py`**, **`sebi_manager.py`** — post-Oct-2024 SEBI intraday rule unchanged. **[Round 4 fix]** Financial-ratio screening is **NOT USED** (owner criteria only) — see the box immediately below.

**[Round 4, user-directed scope decision] Financial-ratio screening REMOVED from the live eligibility gate.** User's explicit reasoning: ratio-based screening is a scholarly financial-industry framework (interpretation about how much incidental impermissible exposure is tolerable) — not core Sharia law directly from the primary texts. The two religious criteria this bot now enforces are: **(a) core business activity halal** (`core_business_halal` — the company's primary business isn't alcohol/gambling/pork/adult/conventional interest-based banking, a fundamental Sharia prohibition) and **(b) 100% Non-Muslim board of directors** (see below). `core_business_halal` is a separate pre-populated flag, so removing the ratio check doesn't affect it. **[Update, this round] Purification/AAOIFI mechanism removed entirely per owner instruction** — not just excluded from the eligibility gate, the `calculate_purification()`/`get_purification_report()` functions, `/purification` command, PDF report line, and `data/purification.json` were deleted from the codebase. `sharia_manager.calculate_zakat()` (unrelated, universal 2.5%-above-Nisab calculator) is retained and unaffected.
  - `stock_selector._is_liquid()` (the balance-sheet illiquid-assets-ratio check, reading `illiquid_asset_pct`/`net_liquid_ok`) is no longer called from `_row_is_halal_eligible()`. Left defined but unused (not deleted) in case of a future decision to re-enable it.
  - `debt_mcap_pct`/`cash_mcap_pct` columns were already confirmed unused anywhere in the live decision logic even before this change (dead/informational columns).
  - Fixed a subscriber/admin-facing report (`build_pdf_report.py`) that inaccurately claimed the bot's Sharia screening was "based on modern financial-ratio standards" — now accurately describes the core-business-activity + board criteria actually used.
  - **Chained-file verification done for this change**: `risk_manager.py` and `backtester.py` both call the same `_row_is_halal_eligible()`/`is_in_halal_universe()` functions (single source of truth, per the Round 2/3 architecture decisions) so they automatically inherited this change with zero additional code — verified via a 4-scenario functional test (ratio-only failing alone now passes; core_business_halal/board/turnover-liquidity failing still correctly blocks). Full `test_full_pipeline.py` re-run afterward showed no new failures (same pre-existing sandbox-only gaps as Round 3, nothing new).

**`board_manager.py`** — **[New subsystem, Round 2 audit]** Implements the customer's own bespoke requirement — **100% confirmed Non-Muslim board of directors** — which is NOT a standard Sharia screening criterion (board-member religion isn't tracked by any financial data vendor; this is the owner's own additional requirement, layered on top of standard Sharia screening). Fetches director names via `yfinance` (confirmed via full-codebase grep: yfinance is used ONLY here, nowhere near price/volume/trading data — Dhan is used for everything else), then classifies each name against a curated Muslim-name pattern list.
  - **[Round 2 fix, Gap #10]** The high-confidence name list was expanded from ~150 to 195 entries to reduce false negatives (real Muslim names outside the old list — e.g. Fatima, Ayesha, Naeem — were previously auto-classified "non_muslim" with zero verification). **This can never be made 100% automatically certain** — there is no religion-verification data source; a broader blocklist is the practical ceiling on this approach. The "web search confirmation" step for ambiguous surnames (Khan, Malik, Sheikh, Gupta, Sharma, Singh, etc.) is a stub that never actually searches — it always returns "not found," which means ambiguous names are always conservatively excluded (safe direction, matches the "don't trade if not confirmed" rule, but does over-exclude some legitimately non-Muslim companies with ambiguous surnames).
  - **[Round 2 fix, board risk item A]** `is_board_100_non_muslim()` previously defaulted to `True` (unsafe) when no data existed for a symbol — the opposite of this module's own stated fail-safe design. Now defaults to `False`. Confirmed this function is not called by the live trade gate today (only by a test), but was a landmine for future wiring.

**`board_filter_auto.py`** — **[Round 2 fix, board risk item B]** A one-off batch SCRIPT (fetches yfinance data for ~1261 symbols, overwrites `data/CUSTOM_UNIVERSE_FINAL.csv`) that was written as top-level executing module code — meaning `import board_filter_auto` from anywhere would silently re-run the whole batch job and destroy the live universe file. Now wrapped in `if __name__ == "__main__":` so it only runs when executed directly (`python3 board_filter_auto.py`), never on import.

**Universe data flow, end to end**: `data/MASTER_STOCK_LIST_PERMANENT.csv` (canonical seed universe) → monthly Sharia/business + owner Board criteria → `data/CUSTOM_UNIVERSE_FINAL.csv` (has a `non_muslim_board` column per symbol) → `stock_selector._row_is_halal_eligible()` reads this column directly as the live gate (fails closed on missing column or error) → `risk_manager.can_enter_trade()` re-checks via `is_in_halal_universe()` as defense-in-depth → `scheduler._monthly_board_universe_update_job()` refreshes this monthly and sets `BOARD_DATA_STALE_PAUSE=True` (blocking all new BUYs, retrying daily) if the refresh fails.

### 2.7 Execution

**`trade_engine.py`**, **`broker.py`**, **`dhan_client.py`** — **[Round 8, v6.0]** Subscriber order type fixed — now uses `ENTRY_ORDER_TYPE` (LMT) for BUY orders, same as admin order flow. Previously used `ORDER_TYPE` (MKT) which caused slippage for subscribers.
  - **[r6 CNC-swing freeze, 2026-09-04]** Product type is CNC only (never MIS). Entry = LIMIT CNC at bot signal price (or better). Exit = MARKET CNC on SL/TP/trail only — no 15:20 square-off. Dhan AMO does not support MARKET, so `broker._live_order_session_gate` refuses real BUY/SELL outside 09:15–15:30 IST. Overnight protection = GTT forever order (not AMO). Live-tick MARKET exit is skipped after hours; monitor retries from next open. Subscriber SELL uses `EXIT_ORDER_TYPE` (MKT) and the same session gate.
  - **[Partial-fill protection]** `broker.get_order_fill_snapshot` (qty-aware; `verify_order_status` stays a 2-tuple). On PARTIAL with `q_filled≥1`, `trade_engine` adopts filled qty, arms GTT/1:1.8 floor lock on that qty, and cancels the unfilled remainder after `PARAMS["partial_fill_remainder_timeout_sec"]` (default 600s). Extra fill before timeout is adopted. `q_filled≥1` PARTIAL is never sent into `entry_follow` HOLD.

**`forever_order_manager.py`** — Manages GTT (Good-Till-Triggered) broker-side stop-loss orders.
  - `setup_forever_orders()` (on entry): retries once + sends a loud admin alert if either the Hard-SL or Trail-SL GTT order fails to place (fixed in Round 1) — unchanged, still correct.
  - **[Round 2 fix, Gap #13]** `close_forever_orders()` (on exit) previously had NO equivalent protection — if the Dhan cancel-order API call failed, the local record was deleted unconditionally regardless, risking an orphaned live stop-order on the real Dhan account that the bot no longer tracks. Now mirrors the entry-side pattern: retries once, sends a loud admin alert on continued failure, and — critically — keeps the local record (flagged `pending_cancel_failed_legs`) instead of deleting it, so a later reconciliation pass or the admin can still find and clean up the orphaned order.

### 2.8 Orchestration & State Management

**`scheduler.py`**, **`workflow_manager.py`**, **`bot_state_manager.py`**, **`deployment_manager.py`**, **`startup_recovery.py`** — unchanged from Round 1 except the `_market_data_refresh_job()` rework described in 2.5, and the monthly board-universe job (pre-existing from an earlier session, re-verified sound in Round 2). **[r32 update, 2026-09-17]**: `scheduler.py`'s 37 job function bodies (including `_market_data_refresh_job()` and the monthly board-universe job referenced here) were physically split into 5 domain files (`scheduler_jobs_core.py`, `scheduler_jobs_daily_ops.py`, `scheduler_jobs_market_data.py`, `scheduler_jobs_board_universe.py`, `scheduler_jobs_research.py`) as an AI-DOS ARCH-003 god-module remediation — same functions, same logic, different files. `scheduler.py` itself (387 lines, was 1336) kept as the thin orchestrator: `setup_scheduler()` (all cron-trigger registration) is unchanged. See `VERSION.txt` r32 for details.
  - **[External heartbeat]** `scheduler._external_healthcheck_job` GETs `HEALTHCHECK_URL` every `PARAMS["healthcheck_interval_min"]` minutes, 24/7, while the process is alive (dead-man). Empty URL = skip, never error. Does **not** replace the existing 1-min Dhan `_heartbeat_job`.

### 2.9 Subscriber / Business Layer

**`crypto_utils.py`** — Fernet symmetric encryption for subscriber Dhan credentials. Re-audited Round 6: clean, fails closed (raises rather than using a weak default) if `ENCRYPTION_KEY` isn't set. No bug.

**`subscriber_manager.py`** — **[Round 6, dedicated audit]** Subscriber registration, live-upgrade/payment flow, Dhan account linking, and the copy-trading eligibility gates. Much of this module was already carefully engineered before this round (named invariants in comments — F013, F014, F079, FIX-12 — suggest earlier deliberate hardening): `link_dhan()`/`unlink_dhan()` validate against the real Dhan API and correctly fail closed on an unknown/unverifiable open-position-check result (`_has_open_copy_positions()` returning `None` on error is explicitly treated as "cannot unlink safely," not as "no positions"). `can_trade()`/`can_enter_trade()`/`can_exit_trade()` all default to blocked for any unrecognized status. `approve_subscriber()`'s term-stacking (rollover) logic is fair — renewing before expiry extends from the current expiry date, not from today.
  - **[Round 6 fix]** `auto_expire_subscriptions()`: a corrupt/malformed `live_expiry` date previously hit a bare `except ValueError: continue`, silently skipping that subscriber forever — they would stay `LIVE_ACTIVE` indefinitely (never auto-expiring) since this ran once a day and always took the same silent skip. Now fails closed (forces `EXPIRED_EXIT_ONLY`) and alerts the admin so the underlying bad data gets investigated. Live-tested: a corrupt-date subscriber and a genuinely-expired subscriber both now correctly end up `EXPIRED_EXIT_ONLY`.

**`paper_trade_manager.py`** — **[REMOVED v5.8.1 — legacy v1 subscriber paper-trial module; koi import/call nahi tha, current paper = broker PAPER mode (same chain as live). Ye Round-6 note history ke liye preserved hai.]** — **[Round 6 fix]** `get_paper_summary()`'s "Total P&L" was computed as `balance - capital` — but `balance` only reflects cash, not open-position value, so buying a paper stock (converting cash to a position of equal value) showed up as a fake loss equal to the entire trade cost, before the price even moved. Live-tested: buying ₹10,000 of a stock immediately showed "-10.0%" with zero price movement. Fixed to show **realized P&L only** (from closed trades — the only P&L this module can show truthfully without live mark-to-market pricing) plus "capital in open positions" shown separately and clearly labeled as not mark-to-market. Also guarded a latent `ZeroDivisionError` in `execute_paper_exit()` if `entry_price` were ever `0`.

**`bot.py`** — **[Round 5, dedicated audit]** The admin/user Telegram command-and-interaction layer (37 commands, Q&A-style flows like `/golive` → risk disclaimer → payment → admin `/approve`). Previously only had a shallow Round-1 pass; Round 5 did a dedicated audit specifically because the trading-logic core had received far more scrutiny than this layer.
  - **Admin-protection audit**: systematically verified all 49 command→function registrations resolve to real functions (no typo-crashes) and every command that should be admin-only actually is (via `@admin_only` decorator, `admin_only()` wrapping at registration, or both — some commands are double-wrapped, redundant but harmless). The 11 commands without admin protection are all intentionally public subscriber commands (`/start`, `/golive`, `/help`, `/simulate`, `/mystatus`, `/status`, `/zakat`, `/link`, `/linkdhan`, `/unlink`) — confirmed correct, not a gap. `is_admin()` compares `chat_id` directly against `config.ADMIN_CHAT_ID` (defaults to `0` if the env var isn't set) — fails closed (locks out everyone, including the owner, rather than opening access) if left unconfigured; a setup-completeness item, not a security bug.
  - **Crash-safety audit**: checked every direct indexed `context.args[N]` access (a user sending a command with missing arguments) — all are properly guarded with try/except or explicit length checks; no crash-on-missing-argument risk found.
  - **Money-path audit**: `/golive` → risk disclaimer → `LIVE_PENDING_PAYMENT` → admin manually `/approve`s after confirming real payment → `LIVE_ACTIVE`. No auto-bypass found — a human always approves before real trading access is granted. `approve_deployment()` (the production go-live gate, `/deployapprove`) uses a prepare→validate→commit pattern with an exclusive lock (blocks concurrent approvals) and fails closed on missing walk-forward-validation data ("never deploy all proposed symbols as a legacy fallback" — a past bug, already fixed before this round). `/settoken`/`/linkdhan` validate credentials against the real Dhan API before confirming, and delete the message containing the raw credentials afterward for security.
  - **[Round 5 fix] Global error handler added**: previously NO `app.add_error_handler()` was registered — python-telegram-bot itself wouldn't crash the whole bot process on an unhandled exception in one command, but neither the user NOR the admin would ever find out that command had failed (same "logged to a file nobody watches live" pattern as Gap #12). Now the user gets a plain message and the admin gets an alert with the actual error.
  - **[Round 5 fix] Stale hardcoded universe count**: `/optimize`'s status message had a leftover legacy universe count. Now reflects the real current tradeable-universe count dynamically.
  - **[r32 update, 2026-09-17] File-structure change (findings above unaffected)**: the 60 command handlers this Round-5 audit covers were physically split out of `bot.py` into `bot_helpers.py` (the `admin_only`/`check_command_access` shared decorator+helpers this audit references) and 5 domain files (`bot_commands_account.py`, `bot_commands_trading.py`, `bot_commands_admin.py`, `bot_commands_research.py`, `bot_livefeed.py`) as an AI-DOS ARCH-003 god-module remediation — every finding/fix documented above still applies to the same functions, they just live in different files now. `bot.py` itself (546 lines, was 1682) kept as the thin orchestrator: `main()`/`_main_guarded()` (all `CommandHandler` registration, the global error handler, the admin-protection wiring this audit verified) is unchanged. See `VERSION.txt` r32-r35 for the full split + 2 self-caught defects (a decorator-extraction bug, 2 stale tests) found and fixed during that work.

### 2.10 Reporting & Alerting

**`trade_logger.py`**, **`signal_broadcaster.py`**, **`report_generator.py`**, **`build_pdf_report.py`**, **`risk_display.py`**, **`ruflo_ranker.py`** — unchanged from Round 1.

### 2.11 Multi-Timeframe (MTF) Subsystem — dormant by default

**`mtf/timeframes.py`, `mtf/derive.py`, `mtf/warehouse.py`, `mtf/bulk_download.py`, `mtf/stats.py`, `mtf/tournament.py`, `mtf/guards.py`** — A self-contained data-warehousing + strategy-tournament framework for testing strategies across multiple candle timeframes, isolated from live trading. **Configured enabled** (`MTF_ENABLED=True` in the shipped `config.py`). The audit must still trace whether the standalone warehouse/tournament package is actually consumed by the live decision path; configuration presence alone is not proof. The MTF composite signal in `strategy_tools.py` is a separate implementation and must not be conflated with the `mtf/` warehouse package. Re-audited fully in Round 2: clean, no new bugs, honest method-attribution (the tournament's guard-rail comments correctly state which statistical guards — e.g. Deflated Sharpe Ratio, wired in an earlier round — are actually active vs. available-but-unused, e.g. Purged K-Fold/PBO).

**`per_stock_params.py`** — Simple per-stock parameter storage/retrieval used across several modules above. Re-audited in Round 2: clean, no bug.

**`dhan_client.py`** — Thin wrapper constructing the Dhan SDK client from stored credentials. Unchanged.

---

## 3. Consolidated Table — Every Verified Method, Creator, and Where It's Used

| Method | Creator(s) / Year | Source | Used in |
|---|---|---|---|
| Half-Kelly Criterion | John L. Kelly Jr., 1956 (fractional variant: academic consensus / E. Thorp) | "A New Interpretation of Information Rate," Bell System Technical Journal | `capital_drawdown_manager.py`, `capital_manager.py` |
| Modern Portfolio Theory / Diversification | Harry Markowitz, 1952 (Nobel Prize in Economics, 1990) | "Portfolio Selection," Journal of Finance | `capital_manager.py` (`max_slots`), `risk_manager.py` (`max_stocks_per_sector` concentration cap) |
| Diversification saturation count | Evans & Archer, 1968 | (empirical study) | `capital_manager.py` (`max_slots` justification) |
| Value-at-Risk (VaR) quantile mapping | JP Morgan | RiskMetrics, 1994 | `survival_manager.py`, `capital_drawdown_manager.py` |
| Hard risk-ceiling design precedent | U.S. SEC | Rule 15c3-5 ("Market Access Rule"), 2010 | `survival_manager.py` |
| CPPI / cushion-scaled sizing | Grossman & Zhou, 1993; Black & Jones, 1987; Perold & Sharpe, 1988 | "Optimal investment strategies for controlling drawdowns," Mathematical Finance | `capital_manager.py`, `capital_drawdown_manager.py` |
| Ulcer Index | Peter G. Martin, 1987 | The Investor's Guide to Fidelity Funds | `portfolio_health.py` |
| Follow-Through Day (recovery confirmation window) | William J. O'Neil, 1988 | How to Make Money in Stocks | `dd_policy.py` |
| Geometric Run-Length Tail probability | (standard math; owner-designed application) | — | `safety_manager.py` (rapid-loss-streak threshold) |
| Walk-Forward Analysis / Efficiency | Robert Pardo, 1992 & 2008 | Design, Testing, and Optimization of Trading Systems | `walk_forward_validator.py` |
| Tree-structured Parzen Estimator (Bayesian optimization) | Bergstra et al. (Optuna library) | Optuna framework | `optimizer.py` |
| Hidden Markov Model regime-switching | James D. Hamilton, 1989 | Econometrica | `market_regime.py` |
| Monte Carlo simulation | Ulam & Metropolis, 1946 | Los Alamos National Laboratory | `monte_carlo.py` |
| **Relative-Strength sector rotation (long-only)** | **Jegadeesh & Titman, 1993; O'Neil; Faber** | **"Returns to Buying Winners and Selling Losers," Journal of Finance** | **`sector_strength.py`, `strategy.py` (Round 2: now a hard STRONG-only entry filter)** |
| **ATVR (Annualized Traded Value Ratio) + Frequency of Trading** | **MSCI** | **MSCI Global Investable Market Indices Methodology (msci.com)** | **`liquidity_screen.py` (Round 3: trading-volume liquidity screen, distinct from the Sharia illiquid-assets ratio below; Round 6: monthly cadence is an intentional owner deviation from MSCI's own quarterly/4-consecutive-quarter cadence — see 2.5) |
| **Relative Volume (RVOL)** | Broadly-adopted retail/professional TA convention (no single named creator, unlike ATVR) | StockCharts ChartSchool and other TA references; commonly-cited 1.5× breakout-confirmation threshold matches this bot's default | `strategy.py` `is_volume_confirmed()` — per-signal daily confirmation, complementary to (not a duplicate of) the ATVR/FoT structural liquidity screen |
| Implementation Shortfall (net-of-cost profit framing) | André Perold, 1988 | "The Implementation Shortfall: Paper vs Reality" | `capital_manager.is_trade_economically_viable`, `economics_brain.py` (Round 2: `max_slots` formula) |
| Staged model-validation lifecycle | Robert Pardo; Federal Reserve | SR 11-7, 2011 | `workflow_manager.py` |
| ~~Financial-ratio screening standard~~ | (removed) | Financial Papers & Shares standard | **[Round 4: REMOVED from live eligibility gate — user scope decision, see Section 2.6]** |
| Dow Jones Islamic Market screening methodology | DJIM | (index-methodology family) | `sharia_manager.py`, `stock_selector.py` |
| SEBI intraday fund-blocking rule (post-Oct-2024) | SEBI | SEBI circular, Oct 2024 | `sebi_manager.py` |
| Loughran-McDonald financial sentiment lexicon | Loughran & McDonald | (finance-specific sentiment word lists) | `news_analyzer.py` |
| **Non-Muslim board of directors screen** | **Owner's own bespoke requirement — NOT a standard Sharia criterion** | **name-pattern heuristic, best-effort (no data vendor tracks director religion)** | **`board_manager.py`, `stock_selector.py`** |
| **RSI Divergence** | **Industry verified (TradingView, MQL5, SaintQuant)** | **Price Lower Low + RSI Higher Low = bullish reversal** | **`strategy_tools.py` (v6.0)** |
| **Volume Divergence** | **Industry verified** | **Price Lower Low + Volume Decreasing = smart money accumulation** | **`strategy_tools.py` (v6.0)** |
| **Candle-Volume Analysis** | **Professional trading** | **Small candle + High volume = accumulation, breakout likely** | **`strategy_tools.py` (v6.0)** |
| **SL Hunt Protection** | **EdgeFlo, Trade2Win, AlphaEx Capital** | **Body close rule + wick analysis + ATR filter** | **`exit_engine.py` (v6.0)** |
| **Multiple Combo Per Stock** | **Owner design** | **Any 1..11 optimizer-selected tools per stock — evidence-driven tool parity; no fixed TOP-N cap** | **`optimizer.py` (v6.0)** |

**Owner-designed (not from an external paper, but engineering-sound applications of standard math), credited to "AIRAF NIZAMI" in code comments:**
- The exact 5%-crossing-probability geometric run-length formula for the loss-streak pause threshold.
- The capital-survival "hurdle" calculation (`calculate_head_of_calculation_hurdles`).
- The `economics_brain.py` BANDS/owner-band-constitution framework (only `max_slots` and `min_live_win_rate` are actually data-calibrated as of Round 2 — see 2.2).

---

## 4. Configuration Reference (`config.py` — `PARAMS` dict, key entries)

| Key | Default | Meaning |
|---|---|---|
| `max_slots` | 8 (owner band 5-12) | **[Round 2]** Now a starting point only — `economics_brain.get_recommended_max_slots()` computes the real value from current capital; this static value is the fallback if that calculation fails |
| `risk_pct_per_trade` | 0.5 | Default per-trade capital-risk % (Half-Kelly-derived, per-stock overridable) |
| `daily_loss_limit_pct` | 2.0 | Hard ceiling on daily risk (always enforced) |
| `trading_cost_pct` | 0.30 | Combined brokerage + statutory cost assumption (SEBI/Dhan rate card) |
| `max_stocks_per_sector` | 2 | Sector-concentration cap (Markowitz-style diversification) — independent of, and still applies alongside, the new sector-STRENGTH hard filter |
| `require_non_muslim_board` | True | **[New]** Master switch for the board-of-directors screen |
| `board_update_cron_day/hour/minute` | 1 / 8 / 30 | **[New]** Monthly board-universe refresh schedule (1st of month, 08:30 IST) |
| `sector_status_thresholds` | strong=1.0, neutral=0.0 | **[New]** Score cutoffs for STRONG/NEUTRAL/WEAK sector classification |
| `enable_turnover_liquidity_filter` | True | **[Round 3]** Master switch for the MSCI ATVR/Frequency-of-Trading screen |
| `liquidity_lookback_trading_days` | 63 | **[Round 3]** ~3 months, matches MSCI's own 3-month ATVR/FoT window |
| `min_atvr_pct` | 15.0 | **[Round 3]** MSCI Emerging-Markets minimum (owner band 10-25) |
| `min_frequency_of_trading_pct` | 80.0 | **[Round 3]** MSCI minimum — % of days a symbol must have at least one trade |
| `liquidity_data_stale_days_limit` | 45 | **[Round 3]** Fail-closed staleness limit, mirrors board's 35-day limit |
| `wfv_min_candles` | 200 | Minimum out-of-sample sample size for walk-forward validation |
| `wfv_efficiency_threshold` | 0.5 | Minimum acceptable Walk-Forward Efficiency |
| `runs_test_streak_p_cap_pct` | 5.0 | Target crossing-probability for the geometric loss-streak threshold |
| `min_health_capital_floor` | 0.10 | Conservative floor for health-linked position-size multipliers |
| `stage_up_trades` | 10 | Number of most-recent trades' win-rate used to decide stage-up/down |
| `MTF_ENABLED` | `True` | Shipped configuration flag; standalone warehouse runtime consumption still requires trace verification |

*(Not exhaustive — see `config.py` directly; every entry has an inline comment noting `[VERIFIED QUANT METHOD]`, `[OWNER VALUE — approved <date>]`, or plain operational default.)*

---

## 4.1 Current ZIP Data Snapshot

| Artifact | Current content |
|---|---:|
| `data/MASTER_STOCK_LIST_PERMANENT.csv` | 2,158 rows |
| `data/BOARD_TRUE_100_NON_MUSLIM.csv` | 1,064 rows |
| `data/BOARD_FALSE_HAS_MUSLIM.csv` | 193 rows |
| `data/CUSTOM_UNIVERSE_FINAL.csv` | 1,057 rows (derived candidate universe) |
| `data/lm_finance_wordlists.csv` | 3,716 rows |
| `data/trading_bot.db` | 24,576 bytes |

Decision-critical custom-universe fields `sector`, `industry`, `market_cap`, `turnover_liquid_ok`, `atvr_pct`, and `frequency_of_trading_pct` are currently 0% populated in the shipped snapshot. This is a data-readiness blocker and is not repaired by documentation.

## 5. Bug-Fix Changelog (all audit rounds, for future maintainers)

### 5.1 Round 1 (56 files, trading-bot-v3_1_3.zip → v3_1_8-fixed.zip) — 8 bugs

All 8 shared one root cause: **an except-block defaulting to a falsely-safe value instead of failing toward caution.**

| # | File | Was (buggy) | Now (fixed) |
|---|---|---|---|
| 1 | `safety_manager.py` | Balance-fetch failure → `False` ("limit not hit") | Fails closed → `True` |
| 2 | `scheduler.py` | Heartbeat API failure masked as success | New explicit-failure balance getter; failure recorded correctly |
| 3 | `news_analyzer.py` | Fetch failure → neutral (0.0), entry allowed | Fetch failure → `None`, entry blocked |
| 4 | `strategy_validator.py` | Health-calc failure → "perfect health" | Failure → worst-case, correctly trips circuit-breaker |
| 5 | `broker.py` | `get_available_balance()` silently returns 0.0 on error | Added explicit-failure `get_available_balance_or_none()` for safety-critical callers |
| 6 | `capital_drawdown_manager.py` | No ceiling on dynamic daily risk budget | Hard-clamped at 2% |
| 7 | `trade_engine.py` | Recorded raw SL% instead of true capital-weighted risk% | Now computes true risk % correctly |
| 8 | `capital_manager.py` | 5 locations defaulted to 1.0/100.0 (max size) on failure | Each falls back to its own conservative floor |

### 5.2 Round 2 (74 files, FINAL_COMPLETE_BOT_1081_PURE_SHARIA_BOARD.zip) — 11 items

| # | File | Was (buggy/missing) | Now (fixed) |
|---|---|---|---|
| 9 | `stock_selector.py` | `is_universe_data_stale()` docstringed "Fail-Closed" but fell through to "not stale" on parse/read errors | Genuinely fails closed (stale/paused) on any error; only a truly-missing state file returns "not stale" |
| 10 | `board_manager.py` | Muslim-name detection list (~150 words) missed many real names entirely, with zero fallback verification | Expanded to 195 names; documented that 100% automated certainty isn't achievable (no data source tracks religion) — this is the practical ceiling |
| — | `board_manager.py` | `is_board_100_non_muslim()` defaulted `True` (unsafe) on missing data | Defaults `False` (fail-safe) |
| — | `board_filter_auto.py` | Top-level executing script code — importing it would silently re-run a destructive batch job | Wrapped in `if __name__ == "__main__":` |
| — | `sector_strength.py`, `strategy.py`, `capital_manager.py` | Two disagreeing sector-strength mechanisms; NEUTRAL sectors could pass; multiplier fail-open on error | Unified into one STRONG-only hard filter (user-confirmed design change, long-only-strategy literature); multiplier now fails to a conservative floor |
| — | `risk_manager.py` | Sector strength never re-checked at the final entry gate | Added as a defense-in-depth check, fails closed |
| 12 | `sector_strength.py`, `fii_dii_tracker.py`, `scheduler.py` | A total data-refresh failure was completely silent (no exception, no admin alert), unlike the board subsystem | Refresh functions now return True/False; scheduler tracks failure streaks + staleness and alerts admin (not a hard trading pause — visibility only) |
| 13 | `forever_order_manager.py` | Exit-side GTT cancel failures were silent, local record deleted regardless | Retry + admin alert + record kept (flagged) if cancel genuinely fails, mirroring the entry-side pattern |
| 11 | `economics_brain.py`, `capital_manager.py` | `max_slots` claimed to be "live-calibrated" but was actually a static number; user asked directly whether brokerage/subscription economics justified the slot count | Built a real formula reusing the existing cost model, wired into both real call sites; honestly documented that 12 of 14 "live-cal" params in this file remain unwired (not overclaiming otherwise) |

**How Round 2 issues were found:** systematic module-by-module reading of all 74 files (prioritized by the user's explicit interest areas — board/Sharia filter, sector strength, FII/DII, order depth), cross-referenced with grep-based verification of claims (e.g. "is this function actually called anywhere?", "is yfinance used anywhere besides board data?"). Several were surfaced by the user's own pointed questions (the `max_slots` economics question directly led to finding Gap #11; a question about the ambiguous-name web-search logic led to finding Gap #10's real scope). One fix (the sector-strength `max_slots` formula) was corrected mid-session after live-testing revealed the first version modeled the wrong cost driver (assumed the ₹40 brokerage cap was the issue; testing showed it's actually the fixed subscription-fee-per-trade term) — kept in this changelog as an example of self-caught error, not hidden.

**What this changelog itself implies:** the same root-cause pattern (fail-open defaults in safety-critical code) that drove all 8 Round 1 bugs also produced roughly half of Round 2's findings (#9, board risk item A, the sector-strength multiplier, Gap #12) — this is evidently a recurring blind spot in how this codebase's exception handling gets written, not a one-time issue. Future maintainers should specifically scrutinize any new `except:` block for what it defaults to.

### 5.3 Round 3 (75 files) — turnover-liquidity screen + parity fix

User asked whether the "illiquid" filter had a verified method behind it. Investigation found `illiquid_asset_pct`/`net_liquid_ok` is actually the balance-sheet illiquid-assets ratio, not a trading-volume concept — no genuine trading-liquidity gate existed anywhere. User clarified their real concern ("entry ho jati hai lekin exit ke waqt buyer nahi milta") and the work below followed.

| # | File | Was (missing/buggy) | Now (fixed/added) |
|---|---|---|---|
| — | `backtester.py` | **Critical, found first**: `load_halal_symbols()` ignored ALL per-row eligibility flags, returning every symbol in the universe CSV regardless of Sharia/board/price/liquidity status — backtest and live ran on silently different universes | Now calls the same `stock_selector` eligibility function live trading uses — single source of truth |
| 12 | `liquidity_screen.py` (new), `stock_selector.py`, `risk_manager.py` (automatic), `scheduler.py`, `config.py` | No trading-volume liquidity screen existed at all | Added MSCI ATVR + Frequency-of-Trading screen (Section 2.5), wired as a fail-closed universe-eligibility check |
| 13 | `scheduler._sync_custom_universe_logic()` | **Found while testing #12**: this function would silently overwrite the live universe file with a near-empty result if an upstream filter's data wasn't populated yet (e.g. `turnover_liquid_ok` before its first refresh) — a real production risk of wiping the tradeable universe to ~0 stocks with no alert (the job would report "success" since it "worked", just with 0 rows) | Added a safety guard: refuses to write if the new result drops >50% vs the previous universe size (or is 0 on what should be a populated run) — treated as a sync FAILURE instead, which correctly engages `BOARD_DATA_STALE_PAUSE` and alerts the admin |
| — | (scheduling order) | N/A | New liquidity-refresh job scheduled 30 min BEFORE the board/universe sync job (not after) so the sync's own filter has fresh data in the common case, with item 13's guard as the safety net either way |
| — | (data quality, root cause found) | `data/haram_pending.json` has 975/1081 symbols flagged — found while testing the above | Root cause confirmed: `sharia_manager.handle_haram_reclassification()` correctly marked these during a past monthly-update run when `board_status.json` was still empty; self-healing via `_sync_custom_universe_logic()`'s auto-restore once real board data exists — see warning box near the top of this document |

**How Round 3 issues were found:** the backtest/live parity bug and the universe-wipe risk were both found not by directly looking for them, but as *necessary consequences* of correctly implementing the user's actual request — wiring a new eligibility filter into the shared `_row_is_halal_eligible()` function immediately exposed that backtester didn't use that function at all, and then exposed that the monthly sync job had no defense against a temporarily-incomplete filter column. This is a useful pattern for future maintainers: adding a new gate to the single-source-of-truth function is a good way to surface exactly which other parts of the system were quietly *not* using that function.

### 5.4 Round 4 — financial-ratio screening removed (user scope decision)

User's reasoning: ratio-based screening is scholarly financial-industry interpretation, not core Sharia law from the primary texts — only core business-activity halal + 100% Non-Muslim board should gate trades religiously. [Update, this round] Purification itself has since been removed entirely (owner does not want it); Zakat (separate, unrelated calculator) is retained.

| File | Change |
|---|---|
| `stock_selector.py` | Removed the `_is_liquid()` (balance-sheet illiquid-assets ratio) call from `_row_is_halal_eligible()`. Function left defined but unused. Docstring updated. |
| `build_pdf_report.py` | Fixed a subscriber-facing report that inaccurately claimed screening was "based on modern financial-ratio standards" — now describes the actual core-business + board criteria. |
| `sharia_manager.py` | [Update, this round] `calculate_purification()`/`get_purification_report()` deleted entirely per owner instruction. `calculate_zakat()` (separate, unrelated calculator) retained, unaffected. |
| `risk_manager.py`, `backtester.py` | No change needed — both call the same shared `_row_is_halal_eligible()`/`is_in_halal_universe()` functions, so this change propagated automatically (the single-source-of-truth architecture from Rounds 2-3 paying off directly). |

**Chained-file verification methodology used** (per user's explicit question about how cross-file impact gets checked): (1) grep every call site of the function being changed across the whole codebase before touching it; (2) make the change; (3) write a small functional test exercising the specific new/old behavior boundary (here: a row failing only the ratio check now passes, a row failing any other check still correctly blocks); (4) re-run the full `test_full_pipeline.py` suite and diff its output against the last known-good run to confirm no *new* failures appeared (only the same pre-existing sandbox-only gaps already documented in Section 7); (5) grep for any *documentation/report-text* that referenced the old behavior (`build_pdf_report.py` was found this way) — code correctness alone isn't enough if a report still tells subscribers something false.

### 5.5 Round 5 — dedicated audit of bot.py (the command/interaction layer)

User's question: is the full admin/user workflow — every command, every sequential step, every Q&A interaction — verified, not just the trading logic? Honest answer given: no, not to the same depth as the trading/safety core, since every prior round's work was driven by the user's specific trading-logic questions. This round did that dedicated pass.

| Area checked | Result |
|---|---|
| All 49 command→function registrations | All resolve to real functions — no typo-crashes |
| Admin-protection coverage | All commands that should be admin-only are (decorator and/or registration-wrap); the 11 unprotected ones are intentionally public subscriber commands — correct as designed |
| Crash-safety (missing command arguments) | Every `context.args[N]` access is properly guarded — no crash-on-missing-argument risk found |
| Money path (`/golive` → payment → `/approve`) | Correct human-approval gate, no auto-bypass found |
| Production deploy gate (`/deployapprove`) | Well-engineered: prepare→validate→commit, exclusive lock, fails closed on missing WFV data |
| Credential handling (`/settoken`, `/linkdhan`) | Validates against real Dhan API before confirming, deletes the raw-credential message afterward |
| Global error handler | **Was missing — fixed.** No command failure was ever surfaced to the user or admin before this round. |
| Stale legacy-count message in `/optimize` | **Found — fixed.** Leftover from the pre-v3.2 universe size, now dynamic. |

**Not yet done**: a dedicated re-audit of `subscriber_manager.py`, `crypto_utils.py`, `paper_trade_manager.py` themselves (the business-logic functions bot.py's commands call into) — this round covered the command/interaction layer, not what's underneath it. **Done in Round 6, see 5.6.**

### 5.6 Round 6 — subscriber/copy-trading business layer

User asked whether anything was left unaudited after Round 5; this was the remaining known gap.

| Area checked | Result |
|---|---|
| `crypto_utils.py` | Clean, fails closed if `ENCRYPTION_KEY` unset — no bug |
| `link_dhan()`/`unlink_dhan()` | Well-engineered (pre-existing named invariants F013/F014/F079/FIX-12) — validates real API, fails closed on an unknown open-position check, no bug |
| `can_trade()`/`can_enter_trade()`/`can_exit_trade()` | All default to blocked for any unrecognized status — no bug |
| `approve_subscriber()` term-stacking | Fair rollover logic — no bug |
| `auto_expire_subscriptions()` | **Found — fixed.** A corrupt `live_expiry` date silently skipped that subscriber forever (bare `except ValueError: continue`), meaning they'd stay `LIVE_ACTIVE` indefinitely instead of expiring. Now fails closed + alerts admin. |
| `paper_trade_manager.get_paper_summary()` | **Found — fixed.** Showed a fake loss (e.g. "-10.0%") immediately after any paper BUY, before the price moved at all — conflated cash-spent-on-a-still-open-position with an actual loss. Now shows realized P&L only (truthful) plus open-position capital shown separately. |
| `execute_paper_exit()` | **Found — fixed.** Latent `ZeroDivisionError` if `entry_price` were ever 0 — now guarded. |

### 5.7 Round 7 — liquidity-filter method fidelity questioned by user

User asked: are the liquidity screen (ATVR/FoT) and volume-confirmation (`is_volume_confirmed`) redundant? Is there a verified method behind volume-confirmation instead of an arbitrary number? Does MSCI itself review monthly, or did we just choose that?

- **Not redundant, confirmed and documented** (see 2.5): ATVR/FoT is a monthly, structural "is this stock chronically liquid" universe gate; `is_volume_confirmed()` (Relative Volume / RVOL) is a per-signal "does today's specific move have real volume behind it" confirmation — different questions, both legitimate.
- **RVOL's 1.5× threshold is not arbitrary** — it matches a commonly-cited industry breakout-confirmation convention (documented by StockCharts ChartSchool and other TA sources), though RVOL (unlike MSCI's ATVR) doesn't have one single named creator/paper — it's a broadly-adopted convention.
- **Honest correction, researched via MSCI's own published methodology docs**: MSCI itself reviews liquidity as part of Quarterly/Semi-Annual Index Reviews, requiring the minimum to hold over 4 CONSECUTIVE quarters — not the monthly, single-snapshot check this bot uses. **User's explicit decision: keep monthly** (more frequent/conservative than MSCI's own cadence) — documented in both `liquidity_screen.py`'s docstring and here as an intentional deviation, not a misrepresentation.

### 5.8 r32-r37 (2026-09-17 to 2026-09-20) — AI-DOS-driven reliability pass + owner-requested hardening

A separate session, driven by a real AI-DOS static-analysis run (1299 raw findings triaged, not blind-fixed) plus several owner-reported/requested items. Full detail in `VERSION.txt`'s r32-r37 entries; summary for future maintainers:
- **r32**: 11 genuine division-by-zero fixes (`utils.safe_div()`, new); race-condition (14 findings) and circular-dependency (12 findings) review — both came back 0 genuine issues, already safe by existing design; `bot.py`/`scheduler.py` ARCH-003 god-module split (see 5.8's own file list in §1, or `VERSION.txt` r32) — a self-caught decorator-extraction bug (an AST lineno/decorator-line mismatch that would have silently dropped `@admin_only` from 45 commands) was found and fixed before delivery, not shipped blind.
- **r33**: merged 5 genuine fixes from a separately-cleaned sibling ZIP the owner also had (`economics_brain.py`, `stock_mode_manager.py`, `mtf/stats.py`, `simulate_engine.py`) that this session's own r32 pass had missed — found by full diff, not assumed.
- **r34**: owner-reported `test_atr_parity.py` false-fail (an `assertNotIn("_simple_atr", src)` tripped by an explanatory *comment*, not an actual retired-function call) — fixed to a comment-aware check; trading logic (`calc_atr`) was never wrong.
- **r35-r37**: owner-requested credential/IP redaction layer (`utils.redact_secrets()`, wired into `append_log()`, the `logging` module via a custom `Formatter`, `print()` sites that embed exception text, and `sys.excepthook` for uncaught crashes) — because the owner is non-technical and routinely pastes terminal/journalctl output into AI chats. Two rounds of self-caught bugs during this work (a too-narrow env-var-name pattern at r35, then a false-positive-prone pattern at r37 that would have mis-redacted ordinary words like "monkey"/"turkey") — both found via this session's own verification testing before shipping, not left for the owner to discover. **Known, disclosed, non-fixable-in-code limit**: this cannot protect against the owner manually running `cat .env` or `echo $VARNAME` and pasting that raw output themselves — no application-level layer can intercept a command the code itself never runs.

---

## 6. Setup / Rebuild Instructions (if starting from this blueprint + a fresh code copy)

1. **Environment**: Python 3.12, install `requirements.txt` (APScheduler, dhanhq, python-telegram-bot, pandas, numpy, cryptography, python-dotenv, hmmlearn, optuna, scikit-optimize, beautifulsoup4, httpx, matplotlib, reportlab, pyarrow, pytz, requests, yfinance — yfinance is ONLY needed for board-of-directors lookups, confirm this stays true if you add features).
2. **`.env` file**: needs `ENCRYPTION_KEY` (generate once, back up separately/securely), plus Dhan API credentials for the admin account.
3. **First run**: `startup_recovery.py` runs automatically; `bot_state_manager` starts cold.
4. **Admin sets up broker access**: Telegram `/settoken`.
5. **Populate the board-screened universe**: run `board_filter_auto.py` directly (`python3 board_filter_auto.py`) — this is a manual/periodic batch script, never import it. It builds `data/CUSTOM_UNIVERSE_FINAL.csv`. After this, the monthly scheduler job keeps it refreshed automatically.
5b. **[Round 3] Populate the turnover-liquidity screen**: run `python3 -c "from liquidity_screen import refresh_liquidity_data; refresh_liquidity_data()"` once, AFTER step 5 (needs `market_cap` from the board-screened CSV). Same bootstrap requirement as step 5 — every symbol fails closed (blocked) until this has run at least once. The monthly scheduler job keeps it refreshed automatically after this. **Also review the `data/haram_pending.json` data-quality item flagged at the top of this document before going live.**
6. **Run the optimizer on real historical data**: `/optimize` — populates `per_stock_params.json` and `backtest_results.json`. Multi-hour background job. **Note**: `economics_brain.get_recommended_max_slots()`'s formula depends on real `expected_trades_per_month` data from this — before a real backtest has ever run, it conservatively defaults to a very low trade-frequency assumption, which may floor `max_slots` at the band minimum (5) even for large capital. This resolves itself once real backtest history exists.
7. **Admin approves deployment**: `/deployapprove`.
8. **Paper trade for an extended period** before considering `LIVE_STAGED`.
9. **Run the full test suite once on the real VPS** (`python3 test_full_pipeline.py`) with all real dependencies installed — some tests could not be fully verified in the audit sandbox (no network access there to install dhanhq/telegram/apscheduler), though the code paths were verified via targeted stub-based testing.
10. **Only after a real, multi-week paper track record**, consider `LIVE_STAGED` then `LIVE_FULL`.

---

## 8. Design Decisions & Known Limitations

### 8.1 State Storage (By Design)
Bot uses **dual state storage**: SQLite (trading_bot.db) for general database + JSON files for specific state (board members, universe). This is **by design**, not a bug. Different modules use different storage for performance and simplicity.

### 8.2 Token Refresh (Dhan API Limitation)
Dhan API requires **daily manual token refresh**. Bot has alert jobs (08:30, 09:00, 09:10) to remind admin. **Auto-refresh is NOT possible** due to Dhan API limitation.

### 8.3 Payment (Semi-Automated)
Razorpay webhook is implemented for payment verification. However, **auto-renewal is NOT possible** — subscriber must manually click payment link. This is by design for user control.

### 8.4 News Sentiment (Verified Method)
News analysis uses **Loughran-McDonald 2011** wordlist — this is an **industry-verified academic method**, not a limitation. Deep NLP/LLM is overkill for this use case.

### 8.5 Data Refresh (Scheduled)
All data refreshes are **scheduled via APScheduler**:
- Daily: sector, FII/DII, regime, news
- Monthly: board, macro, liquidity
- Auto-retry on failure with admin alerts

---

## 7. This Document's Own Limits (read this before trusting anything above)

- This blueprint reflects **code-reading and targeted-live-testing** across two audit rounds, not a production track record.
- The Round 2 audit sandbox had **no network access** — dependencies like `dhanhq`, `python-telegram-bot`, `APScheduler`, `optuna`, `scikit-optimize`, `hmmlearn`, `textblob`, `pyarrow`, and `yfinance` could not be installed. Fixes were verified via (a) `ast`-based syntax checking of every modified file, (b) minimal hand-written offline stub modules to unblock direct function-level testing of the changed logic, and (c) running the existing `test_full_pipeline.py` suite as far as it would go without those dependencies. **Full integration testing with the real broker/Telegram/scheduler stack has NOT happened — do this on the real VPS before trusting this in live trading.**
- Both audit rounds' changelogs (Section 5) show the same "fail-open default" root-cause pattern recurring — there is no guarantee this round found the last instance of it.
- **Nothing in this document is a substitute for**: (a) an independent human developer reviewing this codebase, and (b) a real, multi-week (at minimum) paper-trading track record on live market data before deploying real capital.
- The Non-Muslim-board screening methodology reflects the repo owner's own stated interpretation/requirement choice, not an independent religious ruling — confirm with a qualified Islamic finance scholar before relying on it for religious compliance. It can never be made 100%-automatically-certain (no data source tracks director religion) — see Section 2.6 for what "best effort" means here concretely. Note: the purification/AAOIFI mechanism has been removed entirely from this codebase per owner instruction (not a religious ruling either way — an explicit scope choice).

## 9. NIZAMI Data Segregation & Accumulation Protocol — NDSAP (Rule 15 — (C) IMPLEMENTED r27 2026-09-13; (B) REGISTERED, ToS-blocked)

**Status: refined 2026-09-13 (owner AIRAF NIZAMI), supersedes the 2026-09-08 registration in full. UPDATED r27 (2026-09-13): Part C is IMPLEMENTED under explicit owner implementation-authorization — `ndsap_archive.py` (own SQLite file, separate from key_value_store), read-only fail-soft taps at `dhan_data.py`, `broker.py`, `market_metadata.py` exactly at the placement described below, 13 executed tests (`test_ndsap_archive.py`), retention/compaction policy per `NDSAP_RETENTION_ESTIMATE.md`. Part A needed no new code (reaffirms the frozen `DATA_SOURCE_POLICY.md` runtime — Q014 PASS stands). Part B remains NOT IMPLEMENTED — ToS blocker open; its tap exists but is structurally gated OFF (provider allowlist defaults to Dhan-only, so no third-party payload is ever written until the owner enables it).**

**Attribution:** NDSAP is an original method authored by AIRAF NIZAMI for this project (segregation + accumulation as one named, combined protocol) — no pre-existing external methodology is claimed or invented.

**Part A — Dhan-exclusive, no-substitute (segregation), for trading-decision data.** OHLCV/price/volume used for any trade decision comes from Dhan ONLY, per the existing frozen `DATA_SOURCE_POLICY.md` (Q014) — NDSAP reaffirms this, it does not loosen it. If Dhan cannot supply this data at decision time, the affected trade action fails closed; no other source (NSE, Moneycontrol, yfinance, or any future provider) is ever substituted for price/volume, to eliminate cross-source price-mismatch risk.

**Part B — broadened alternate sourcing, non-Dhan fields only.** Fields Dhan genuinely does not supply (sector, industry, market_cap, and the other currently-empty `CUSTOM_UNIVERSE_FINAL.csv` fields — Q034) may be sourced from NSE, Moneycontrol, or yfinance (broadened from yfinance-only) — Dhan checked first per field, alternate used only once Dhan is confirmed unable to supply that field. Never applies to price/volume (Part A always wins).

**Part C — live data accumulation archive.** Current backtesting is limited to whatever historical data the shipped snapshot/provider already has. This archive would let QASWA build its *own* point-in-time historical record going forward, for future backtests — it does not create any historical data retroactively.

**Placement in the pipeline:** a read-only tap at the existing live-data ingestion points (`dhan_data.py`, `market_metadata.py`, and any new NSE/Moneycontrol integration added under Part B) — additive, does not sit in or alter the trade-decision path (Business Halal Filter → Non-Muslim Board Filter → SEQ → trade decision, Rule 14, unaffected).

```
Live data received under Part A (Dhan) or Part B (Dhan-first, NSE/Moneycontrol/yfinance fallback for non-Dhan fields only)
  → raw payload + QASWA arrival_timestamp(UTC) + provider event_timestamp + symbol/exchange
    + provider/API-version + sequence number + content hash
  → immutable, append-only archive table (separate from key_value_store)
  → validation (reuses existing DATA_SOURCE_POLICY.md fail-closed-on-missing philosophy)
  → feature computation, stamped with both data-version and feature-code-version
  → historical dataset, queryable "as of" any past date
  → future backtest/optimizer may only read rows with arrival_timestamp ≤ simulated date
    (a structural query-layer guard — the same class of discipline that produced the
    existing [PHD-FIX look-ahead] fixes in strategy_tools.py, Section 5)
```

**Required fields (Rule 15):** raw unmodified payload, QASWA arrival timestamp, provider event timestamp (kept separate), symbol+exchange, provider name/API version, monotonic sequence number, content hash.

**Pre-implementation blockers (must clear before this moves from registered to implemented — see `QASWA_AUDIT_QA_STATUS.md` Q037):**
1. ToS review for storage/reuse of data from yfinance, NSE, and Moneycontrol — not yet legally verified for any of the three.
2. A real per-field data-volume/growth estimate, from which the retention/compaction policy must be derived — not an arbitrary duration chosen in advance.

**Explicitly out of scope for this rule:** retroactively fabricating or backfilling any pre-deployment historical data; any change to the existing trade-decision path or frozen contracts (RR 1.8, Halal/Board gates, SEQ); any loosening of Part A's Dhan-exclusivity for price/volume.

## 10. CERTIFICATION CLOSURE / RE-INSPECTION CONTRACT

The architecture is governed by evidence continuity across maintenance and AI handoffs. Audit findings use the lifecycle `OPEN → FIXED → TESTED-PASS → CLOSED`; `CLOSED` is valid only when implementation, actual test/evidence, release identity, and affected-chain verification are recorded.

A new AI must **verify CLOSED, not redesign CLOSED**. It must inspect the relevant implementation at code/data level and independently issue PASS/CLOSED when the logic satisfies the locked criterion and the evidence is valid. It must issue FAIL/REOPENED when actual contradictory evidence or a real defect is found.

A different implementation preference is not a defect when the locked criterion is already satisfied. Genuinely new independent risk classes remain discoverable through the existing section mapping or S56+ gate. Canonical state/evidence rules: `docs/CERTIFICATION_CLOSURE_AND_REINSPECTION_GOVERNANCE_v1.0.md`.


## 11. DECISION & MARKET-CONTEXT TELEMETRY — "BLACK BOX" (Rule 16 — IMPLEMENTED r30 2026-09-15)

Owner-conceived flight-data-recorder (owner chat spec, 2026-09-15; implementation authorized by the same message). Owner-side audit alias: **"PIT Telemetry"** (owner-confirmed r31 = this same capability; the PIT component is the structural as-of read guard below). One-liner: **Dhan gives price; telemetry records decisions + market mahoul.** This is a NEW Rule 16 — unrelated to the old Rule 16 deleted 2026-09-13 (dual/secondary-engine requirement, no historical record kept per owner instruction); the number is reused only to keep the constitution contiguous.

**Module:** `telemetry.py` — own SQLite file `data/telemetry.db` (isolated from `trading_bot.db`, `key_value_store` and `ndsap_archive.db`; same isolation discipline as Rule 15 (C)). Two tables:

- `scan_context` — ONE row per `run_market_scan` call, including skipped scans: outcome (`COMPLETED` / `SKIP_<gate>` for killswitch, network partition, DB failure, bot state, workflow, trading time, strategy-invalid, ASM/GSM stale, prefilter error), gate detail, duration, universe + post-filter sizes, per-scan counts (fetch failures, no-buy-signal, mode skips, duplicate skips, risk rejects, news rejects, candidates, slot-full, execute errors), fields JSON (ASM/GSM rejected list, candidates_ranked with rank + sector/signal scores, strategy name), regime snapshot (read from the cached `market_regime.json` via `get_market_regime_details(force_refresh=False)` — zero extra API calls), sector snapshot (cached `data/sector_strength.json`), and version stamp.
- `decision_snapshot` — one row per decision-reached symbol per scan: decision enum (`REJECT_RISK_GATE`, `REJECT_NEWS`, `EXECUTE_ATTEMPT`, `SKIP_SLOT_FULL`, `BLOCKED_AT_EXECUTE`, `RECOVERY_ENTRY_OK/DECLINED`, `ENTRY_SKIP_NO_SECURITY_ID/PARAMS_MISSING/LOW_BALANCE/LOW_BALANCE_ERROR/QTY_ZERO`, `ENTRY_ORDER_PLACED`, `ENTRY_ORDER_REJECTED`, `ENTRY_VERIFY`, `ENTRY_RESTING_FOLLOW`, `ENTRY_SAFETY_CANCEL`) + reason + full signal JSON + context JSON (prices, qty, order id, rejection type, spread) + `input_bars` (last N completed daily OHLCV bars actually fed to the strategy, default 120, `TELEMETRY_INPUT_BARS`) + version stamp {revision, params_hash, strategy}.

**Pillar mapping (owner's four):** (1) market photo → scan_context regime/sectors/ASM-GSM list + budgeted spread capture at candidates/entries (ONE `get_market_depth` call each, gated `TELEMETRY_SPREAD_CAPTURE`, hard budget `TELEMETRY_SPREAD_MAX_PER_SCAN`=10/scan; the raw depth payload is already PIT-archived by NDSAP — telemetry stores only the derived bid/ask/spread). (2) decision snapshots → decision_snapshot rows. (3) deterministic replay → `input_bars` + signal JSON + version stamps; CLI `python3 telemetry.py --replay SYMBOL [--date YYYY-MM-DD] [--as-of TS]`; PIT read guard STRUCTURAL (r31): `read_asof(as_of,…)` / `read_scans_asof(as_of,…)` require an explicit as-of (no default — ValueError otherwise), only rows recorded ≤ as-of are visible, so replay analysis cannot peek at future decisions (lookahead-bias block, mirrors NDSAP `read_asof`; fail-open applies to the RECORDING side — the read-side guard deliberately raises: it is analysis tooling, never a trading-path call). (4) silent watcher → every public function fail-open (never raises; failures cost one audit-log line), all `trade_engine.py` taps exception-guarded read-only collectors, inert `_NullTrace`/`_TelInert` fallbacks when disabled or unimportable; buffered writes land in ONE atomic transaction at scan end — zero mid-scan DB load, never in the order/SL path.

**Immutability:** append-only by SQLite triggers — DELETE and UPDATE structurally blocked on BOTH tables (flight-recorder semantics; stricter than NDSAP, which allows documented payload-expiry compaction). No compaction, retain forever. Sizing estimate (measured pattern, same discipline as `NDSAP_RETENTION_ESTIMATE.md`): scan rows ≈ 288/day worst case (5-min cadence incl. gate skips) × ~1-4 KB ≈ 0.3-1.2 MB/day; decision rows typically 0-50/day (decision-reached symbols only), worst-case burst a few hundred × up to ~15 KB (input_bars-dominated) ≈ <4 MB/day; realistic steady state <1 MB/day → <400 MB/year worst case, typically <100 MB/year. If the owner ever wants pruning, that is a NEW governance decision, not a silent feature.

**Config surface (`config.py`, ADD-ONLY block):** `TELEMETRY_DB`, `TELEMETRY_ENABLED_DEFAULT=True`, `TELEMETRY_SPREAD_CAPTURE_DEFAULT=True`, `TELEMETRY_SPREAD_MAX_PER_SCAN_DEFAULT=10`, `TELEMETRY_INPUT_BARS_DEFAULT=120`; env overrides `TELEMETRY_ENABLED`, `TELEMETRY_SPREAD_CAPTURE`, `TELEMETRY_SPREAD_MAX_PER_SCAN`, `TELEMETRY_INPUT_BARS`.

**r31 inventory-integrity note:** the r30 release regenerated `AUDIT_INTEGRITY_MANIFEST_SHA256.json` + the CSV but missed the SECOND shipped inventory manifest `AUDIT_INVENTORY_SHA256.json` (stale: 12 mismatched hashes + 2 missing entries — found by the owner-side forensic audit, not by the certified gate, because the gate's SHA-provenance check deliberately skips the two self-referential manifests and no test covered the second one). Fixed at r31: manifest regenerated exact + NEW structural preflight check `inventory manifest` (full-tree hash+size verification of `AUDIT_INVENTORY_SHA256.json`) so this class of staleness can never ship silently again.

**Documented boundaries:** no per-symbol-per-scan full-universe rows (~88k rows/day + rate limits — silent majority lives in scan-level counts); exit/follow-event telemetry = future scope, not r30; SEQ registration deliberately NOT added (governance step 6: telemetry is observability, not a methodological-alignment stage — forcing it into SEQ's stage-role mapping is exactly what the governance doc forbids).

**Evidence:** `test_telemetry.py` 21/21 executed (18 at r30 + 3 PIT-guard at r31) (schema/triggers, immutability DELETE+UPDATE blocked, scan/decision persistence + version stamps, input-bar tail serialization, disabled-flag inertness, broken-DB fail-open with audit line, no-active-trace no-op, spread parse + budget, read/replay/stats, CLI subprocess, static fail-open guard check on `trade_engine._execute_entry` taps, PIT guard: as_of-required ValueError, future-row invisibility + boundary inclusivity + date-only normalization, scans as-of + CLI --as-of). Governance trail: `QASWA_AUDIT_QA_STATUS.md` new Q038 (PASS with boundaries), `prd.md` Rule 16, VERSION.txt r30.
