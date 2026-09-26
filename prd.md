# QASWA — MASTER PRODUCT REQUIREMENTS DOCUMENT (PRD) + ROADMAP

> **CANONICAL DATA-SOURCE POLICY:** `DATA_SOURCE_POLICY.md` — Dhan is mandatory for every trading-data and execution path; yfinance is company-information only and cannot provide OHLCV/price/volume to trading behavior.


> **CANONICAL GOVERNANCE — QASWA v6.0.3:** Product scope and intended behavior are defined by this document and the package code; inspection is governed by `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md`, using `docs/MASTER_ZERO_OMISSION_ZIP_INSPECTION_CONSTITUTION_55_SECTIONS.md` as the unchanged 55-section backbone. The authority chain is **55 Sections → Quality/Defect Gate → Evidence Classification → Release Verdict**. Framework freeze does not certify the VPS/live environment. The current phase is PRE-VPS engineering verification; AFTER-VPS external evidence remains mandatory.

**Version:** v6.0.3 | **Date:** 2026-08-29 | **Status:** RELEASE BLOCKED — production certification pending data-readiness, clean-dependency and VPS integration gates
**Owner:** AIRAF NIZAMI | **Project:** Qaswa Halal Algo Trading Bot (Telegram + Dhan)

> Ye **SINGLE SOURCE OF TRUTH** hai — pura product, har decision (D1-D26),
> har calculation, har phase, har fix. Naya AI/developer/owner ye + 
> `SYSTEM_MASTER_MANIFEST.json` + `AI_ONBOARDING.md` padhe — sab kuch milega.
> Owner ko dobara kuch explain nahi karna padega.

---

# 1. PRODUCT VISION

## 1.1 Ek line me
**Long-only, Sharia-halal, copy-trading Telegram bot** jo NSE cash-equity me per-stock
optimization se **consistency profit** kamata hai — paper → staged live →
subscriber copy-trading tak, **zero hardcoded numbers, zero jabran trade,
profit kabhi loss me nahi.**

## 1.2 Core Goals (priority order)
| # | Goal | Status |
|---|---|---|
| G1 | **Kal ke top gainers aaj pakadna** — research-verified signals se next-day movers (overnight module) | ✅ Built (paper-proof pending) |
| G2 | **Consistency profit** — uptrend/sideways/downtrend sab me, optimization-proven edge ke saath | ✅ Built |
| G3 | **Profit uncapped + lalach-safe** — trailing ke saath ride, profit reach ke baad loss me exit NAHI | ✅ Built (exit toolkit) |
| G4 | **Overfit-free** — har decision WFV/t-test/MC se out-of-sample proven | ✅ Built |
| G5 | **Backtest ≈ Paper ≈ Live** — same filters, same sizing, same exit engine | ✅ Built (F1 FIXED v5.8) |
| G6 | **Business** — ₹3105/month subscribers, copy-trading, auto-payment | ✅ Built (KYC pending) |
| G7 | **VPS deployable, self-maintaining** — auto-jobs, auto-macro, auto-reoptimize-proposal | ✅ Built |

---

# 2. OWNER CONSTITUTION (kabhi nahi badalta — 16 rules)

1. **Long-only CNC delivery (swing, not MIS)** — no short/F&O/margin/interest
   (Sharia). Product type CNC only. No 15:20 square-off. Overnight hold until
   SL/TP/trail. Entry = LIMIT CNC @ bot signal price (or better). Exit =
   MARKET CNC, **only 09:15–15:30 IST** (Dhan AMO has no MARKET). Overnight
   SL = GTT forever order. `intraday_filter` is **not** an MIS switch: BE/T2T
   (entry allowed, same-day exit banned) are skipped so SL/TP cannot get stuck.
2. **Core Business 100% Halal** — no Bank/Riba, Insurance, Alcohol, Tobacco,
   Gambling, Pork, Adult, Weapons
3. **100% Non-Muslim Board of Directors** — ek bhi Muslim mile to trade BLOCK
   (fail-closed, monthly inspection)
4. **Price > ₹100 + Liquid** (MSCI ATVR/FoT) + strict NSE-EQ execution
5. **Sirf 4 owner constants:**
   - ₹3,000 subscription fee (₹3,105 payment amount = fee + gateway ~3.5%)
   - ₹20,000 goal = **sirf benchmark, koi use nahi, trade criteria nahi**
   - 2% daily-loss cap = SOLE fixed risk constant (emergency fallback only)
   - **10% max portfolio DD = owner personal thinking** ("log apne amount ka
     10% bear kar sakte hain") — LOCKED ceiling; economics-derived DD iske
     ANDAR ghumta hai (3% floor)
6. **Zero hardcoded/magical numbers** — har number ka documented source
   (current `config.py` registers 196 PARAMS entries; exact count is audit-derived); hardcode watchdog machine-enforced
7. **Koi bhi phase/regime me trade sirf optimization-proven edge pe** —
   warna block (fail-closed)
8. **Time-aware** — heavy kaam trading window (09:15–15:30) ke bahar
   (pre-market/background + cache); trade miss = engineering failure.
   Real BUY/SELL only inside 09:15–15:30 (Dhan AMO ≠ MARKET)
9. **Exit kabhi band nahi** — expiry/revoke pe bhi sirf bot-dili (ledger)
   positions exit hoti hain; subscriber ki manual positions = unki zimmedari
10. **Profit-lock guarantee** — profit reach hone ke baad lalach me loss me
    exit = GALAT (hybrid/ratchet modes)
11. **Exit = EK tool, optimizer decide karega** — 5% pe exit ya 50% pe,
    jo WFV bole; min-RR ke baad trailing, trail fail → min profit booked
12. **RR-first priority** — comparative behtar R:R wale stock ko pehle slot
13. **Guides sirf bot ke ANDAR** (downloadable NAHI — safety); subscriber
    statement view-only (download NAHI)
14. **QASWA Remix / SEQ architecture identity** *(added 2026-09-07 — owner-supplied criteria-replacement, source of truth for naming/architecture identity; supersedes any prior unnamed/implicit framing, does NOT alter Rules 1-13's substance)*:
    - Combined end-to-end architecture name = **QASWA Remix**, owned by **AIRAF NIZAMI**.
    - Mandatory hard-gate order (non-negotiable, in sequence): **Rule 2 (Business Halal Filter) → Rule 3 (Non-Muslim Board of Directors Filter) → SEQ → trade decision/execution.** SEQ cannot bypass either gate; if either gate fails, no downstream layer may allow the trade.
    - **SEQ** = QASWA's internal shorthand for the systematic/quantitative industry-best-practice alignment layer (sector strength, regime, liquidity, signal/tool selection, optimization, risk/sizing, execution, exit — per existing Rules 6/7/11/12). SEQ is NOT a claimed pre-existing official methodology name, and no individual feature is made mandatory merely by existing (Rule 7's "optimization-proven edge or block" already governs this).
    - **Attribution rule:** where a SEQ component is based on a genuine external method (e.g. MSCI ATVR/FoT, Jegadeesh & Titman relative strength, RVOL), it must cite that verified method/creator honestly (per Rule 6's documented-source requirement) — no invented single creator, no false claim of a professional body being a "creator" when it only publishes standards.
    - **Ownership scope:** "QASWA Remix → AIRAF NIZAMI" covers the combined architecture/integration (Rules 2+3+SEQ-alignment+implementation) only. Underlying verified industry methodologies (MSCI, Jegadeesh & Titman, etc.) keep their own genuine attribution — the two ownership levels are never merged or substituted for each other.
15. **NIZAMI Data Segregation & Accumulation Protocol (NDSAP)** *(refined 2026-09-13 — owner AIRAF NIZAMI; supersedes the 2026-09-08 "Live Data Accumulation" registration in full. STATUS r27, 2026-09-13: **(C) IMPLEMENTED** under explicit owner implementation-authorization (2026-09-13) — `ndsap_archive.py` + read-only taps + `test_ndsap_archive.py` (13 tests) + `NDSAP_RETENTION_ESTIMATE.md`; **(A)** verified as pre-existing runtime (reaffirms Q014, unchanged); **(B) NOT YET IMPLEMENTED** — ToS blocker open, tap gated OFF. See `SYSTEM_BLUEPRINT.md` §9 and `QASWA_AUDIT_QA_STATUS.md` Q037)*: an owner-original method (no external methodology claimed or invented — see attribution note at end) governing how QASWA sources and archives non-trading market data, in two parts:
    - **(A) Dhan-exclusive, no-substitute, for trading-decision data (segregation).** OHLCV/price/volume used for any trade decision must come from Dhan ONLY — this reaffirms, and does not loosen, the existing frozen `DATA_SOURCE_POLICY.md` contract (Q014). If Dhan cannot supply this data at decision time, for any reason (outage, staleness, API error), the affected trade action fails closed. No other provider — not NSE, not Moneycontrol, not yfinance, not any future source — is ever substituted for price/volume, because a cross-source price mismatch between the data QASWA reasons on and the price Dhan actually executes at is an unacceptable real-money risk. This is absolute, not best-effort.
    - **(B) Broadened alternate sourcing, for non-Dhan-available fields only.** Decision-support fields Dhan genuinely does not supply (sector, industry, market_cap, and any other currently-empty field in `CUSTOM_UNIVERSE_FINAL.csv` — see Q034) may be sourced from NSE, Moneycontrol, or yfinance (broadened from the prior yfinance-only path) — Dhan is checked first per field; an alternate source is used only once Dhan is confirmed unable to supply that specific field, and never for price/volume (part A always wins).
    - **(C) Live data accumulation archive.** From the point this capability is deployed onward, every live data point QASWA actually receives (Dhan price/volume, and any field obtained from an approved alternate source under part B) that is capable of informing any current or future backtest, validation, alignment, or research use — whether or not it feeds a live trading decision today — must be preserved in an **immutable, append-only, timestamped archive**, separate from `key_value_store`, before any transformation. Each stored record must carry: (a) the exact raw provider payload, unmodified, (b) QASWA's own arrival timestamp (UTC, not the provider's claimed timestamp), (c) the provider's claimed event timestamp, kept separate, (d) symbol + exchange, (e) provider name/API version, (f) a monotonic sequence number, (g) a content hash for tamper/duplicate detection. A future backtest reading this archive must only ever access records whose arrival timestamp is ≤ the simulated date being tested — enforced structurally (a query-layer guard), not by convention. This rule does **not** retroactively create historical data for any period before deployment — that gap remains a known, disclosed limitation.
    - **Retention policy requirement:** before implementation, an explicit retention/compaction policy must be defined from an actual per-field data-volume/growth estimate for this archive (not an arbitrary duration) — producing that estimate is a required deliverable of implementation, not something this criterion presupposes.
    - **Pre-implementation blockers (must be resolved before Rule 15 moves from registered to implemented):** (i) ToS review for storage/reuse of data from yfinance, NSE, and Moneycontrol — not yet legally verified for any of the three; (ii) the retention estimate above.
    - **Implementation record (r27, 2026-09-13):** Part C implemented under explicit owner implementation-authorization (chat directive, 2026-09-13) — `ndsap_archive.py` (immutable append-only archive in its own SQLite file, structural as-of guard, SHA-256 tamper/duplicate detection), read-only fail-soft taps at `dhan_data.py` / `broker.py` / `market_metadata.py`, 13 executed tests (`test_ndsap_archive.py`), and the retention/compaction policy derived from measured per-field volume estimates (`NDSAP_RETENTION_ESTIMATE.md` — the required deliverable above; blocker (ii) RESOLVED). Blocker (i) ToS review remains OPEN: the yfinance metadata tap is structurally gated OFF (provider allowlist default `["dhan"]`) — no yfinance/NSE/Moneycontrol payload is stored until the owner clears ToS and enables the provider. The rule text above is unchanged by this implementation.
    - **Attribution:** NDSAP (the segregation-plus-accumulation approach as a named, combined protocol) is an original method authored by AIRAF NIZAMI for this project — no pre-existing external methodology is claimed. It does not change the underlying frozen `DATA_SOURCE_POLICY.md` Dhan-exclusivity contract for price/volume, which remains independently sourced and unmodified.

16. **Decision & Market-Context Telemetry ("Black Box" / Flight Data Recorder)** *(owner-side audit alias: **"PIT Telemetry"** — owner-confirmed r31 to be this same Rule 16 capability, not a separate module; the point-in-time read guard below is its structural PIT component. Added 2026-09-15 — owner-conceived concept, owner-defined protocol; implementation authorized by the owner's own spec message, 2026-09-15. This is a **NEW Rule 16, unrelated to the old Rule 16** (dual/secondary-engine requirement) fully deleted 2026-09-13 by owner decision with no historical record kept per explicit instruction — the number is reused only to keep the constitution contiguous, and the deletion is acknowledged here so no reader conflates the two. STATUS r30, 2026-09-15: **IMPLEMENTED** — `telemetry.py` + fail-open read-only taps in `trade_engine.py` + `test_telemetry.py` (21 tests, executed — 18 at r30 + 3 PIT-guard tests at r31) + `SYSTEM_BLUEPRINT.md` §11 + `QASWA_AUDIT_QA_STATUS.md` new Q038 (likewise unrelated to the deleted old Q038). Owner's one-liner: "Dhan gives price; telemetry records decisions + market mahoul.")*: four pillars:
    - **(1) Market photo the broker doesn't give.** Every scan records the market context no broker feed persists: bid-ask spread (derived from ONE budgeted market-depth call per candidate/entry — never per-universe-symbol; the raw depth payload is already PIT-archived by Rule 15 NDSAP, dataset=market_depth), sector rank/strength snapshot, market-regime (trend-vs-chop) snapshot, the SEBI ASM/GSM blocked list used by the pre-filter, gate outcomes, and universe size — one `scan_context` row per scan.
    - **(2) Decision snapshots.** Every symbol that reaches a decision point records what the bot decided and WHY — risk-gate block, news reject, duplicate-candle skip, slot-budget-full skip, blocked-at-execute, order rejection, verify status, resting-follow, safety-cancel, entry placed/failed — with the full signal JSON and the reason, so every trade taken or skipped is explainable after the fact.
    - **(3) Deterministic replay.** Candidate/entry rows carry the last N completed daily OHLCV bars actually fed to the strategy (`input_bars`) plus a version stamp {release revision, PARAMS hash, strategy name} — months later, a new strategy version can be replayed against the exact recorded market conditions with zero guessing. The replay read path is PIT-guarded structurally (r31): `read_asof(as_of,…)` / `read_scans_asof(as_of,…)` REQUIRE an explicit as-of timestamp (no default, ValueError otherwise) — a replay can only see rows recorded at or before the simulated point in time, blocking lookahead bias the same way NDSAP's `read_asof` does; CLI `--as-of`. This is a decision-context archive; it neither replaces nor duplicates the Rule 15 NDSAP raw-payload PIT archive (different layers: NDSAP = raw provider bytes; telemetry = decisions + derived context).
    - **(4) Silent watcher (hard acceptance criterion).** Telemetry is strictly passive: never in the order-placement or SL/exit path, never blocks or alters a scan, fail-OPEN everywhere — any telemetry failure (broken DB, disk full, import error) costs at most one audit-log line and zero trading impact. Every tap is exception-guarded; if the telemetry import itself fails, the scan runs against a fully inert fallback object.
    - **Documented boundaries (deliberate, not gaps):** (i) no per-symbol-per-scan rows for the full universe (~1000 symbols × 84 scans/day ≈ 88k rows/day, and Dhan rate limits forbid per-symbol depth calls) — the silent majority is captured as scan-level counts; per-symbol rows exist only for symbols that reached a decision point; (ii) spread capture gated (`TELEMETRY_SPREAD_CAPTURE`) and budgeted (`TELEMETRY_SPREAD_MAX_PER_SCAN`, default 10 depth calls/scan), candidates/entries only; (iii) exit/follow-event telemetry is future scope, not r30; (iv) storage in its own SQLite file (`data/telemetry.db` — isolated from trading_bot.db, key_value_store and ndsap_archive.db, same isolation discipline as Rule 15 (C)), append-only via SQLite triggers (DELETE/UPDATE structurally blocked), no compaction, retained forever; sizing estimate in `SYSTEM_BLUEPRINT.md` §11.
    - **Attribution:** the flight-data-recorder analogy is general; this four-pillar protocol as specified is owner-defined for this project (owner chat spec, 2026-09-15). No external methodology is claimed or invented.

## 2.1 Decision Registry (poora history — D1-D26)
| # | Decision |
|---|---|
| D1 | Legacy 145-stock list + financial-ratio screening full delete (single universe source) |
| D2 | Universe monthly inspection (Sharia→Board→Price→Liquid→Dedup) |
| D3 | Breadth feature delete (regime = Nifty HMM + 4 evidences) |
| D4 | Regime HMM Hamilton 1989 + 09:10 pre-market refresh |
| D5 | Backtest parity (parity_engine R1-R4 + sector PIT archive) |
| D6 | News = Loughran-McDonald 2011 (FinBERT cancel — zip/VPS) |
| D7 | BEAR knobs config-driven; per-stock×regime = phase-2 |
| D8 | Phase gate (per-stock per-phase t-test edge proof) |
| D9 | REPLACE not INTEGRATE (single engines, no legacy) |
| D10 | feature_sequence.json master (registry = docs = test) |
| D11 | Naya AI onboarding (manifest + sequence pehle padhe) |
| D12 | Time-aware constitution (heavy pre-market, scan fast-only) |
| D13 | Simulation → Approval order (pehle result, phir approve) |
| D14 | Sizing parity: paper = live (stage×health×regime chain) |
| D15 | Number provenance (PARAM_SOURCES + negative self-test) |
| D16 | Auto-payment: ₹3105 fixed, UPI+card, no auto-renew, T-2 dual alert, stacking |
| D17 | v5.0 batch (command lifecycle, 3-layer GTT, crash-safety, GRACE) |
| D18 | v5.1 (in-bot guides + VPS package) |
| D19 | v5.2 Overnight movers (20% sirf example; top-5 goal; exit optimizer) |
| D20 | v5.3 Robust trailing (trail params optimizer space me) |
| D21 | v5.4 Exit toolkit (lock/trail EK tool; 4 modes; lalach-safe) |
| D22 | v5.5 +2 verified signals (overnight persistence + tug-of-war) |
| D23 | v5.6 Master manifest + AI onboarding |
| D24 | v5.7 Hardcode migration (D7 TP=min-RR, D13 brokerage config, D18 untouched) |
| D25 | MC 5% = verified VaR-95 convention (judge, optimize nahi); 10% cap owner |
| D26 | Macro auto-refresh monthly (inflation khud update) |

---

# 3. PRODUCT FLOW (admin/subscriber ke perspective se)

## 3.1 Admin — poori zindagi ka cycle
```
[0] VPS deploy (deploy.sh) → .env → /start → /adminguide
[1] /settoken (Dhan) → /boardrefresh (pehla Sharia+Board sync)
[2] Market close ke baad: /optimize (2-3 ghante, thread) → /backtest
    → /walkforward → /ruflo
[3] /simulate 200000 → RESULT REVIEW (pehle dekhna, phir faisla)
[4] /deployapprove (sirf satisfied ho ke; 8-layer validation + MC gate)
    — galat laga: /deployreject ya /deployrollback
[5] PAPER TRADING 2-4 hafte (PAPER_MODE=True)
    — /result /report /pnl /botstatus roz dekho
    — overnight_enabled=True karo (paper proof collect)
[6] /overnight → edge report; /overnight optimize → exit params
[7] Paper pass → LIVE_STAGED 10% (auto-advance win-rate se) → 25 → 50 → 100
[8] Razorpay KYC → RAZORPAY_* env → webhook URL → TEST mode → LIVE
[9] Subscribers: /start → /guide → /simulate → /golive → /subscribe
    → /linkdhan → admin /approve → copy trading → /revoke (revert)
[10] Roz: automated jobs + /slippage audit + /statement (view-only)
```

## 3.2 Subscriber — journey
```
/start → PAPER_TRIAL (30 din)
→ /guide (step-by-step, status-aware)
→ /simulate 100000 (projection + subscription viability: VIABLE/NOT_VIABLE)
→ /golive (risk disclaimer ✅/❌)
→ /subscribe (₹3105 FIXED payment link — UPI+cards, partial OFF)
→ payment success → "plan activated till DATE" (stacking: purane expiry ke baad)
→ /linkdhan (Fernet encrypted, message auto-delete)
→ admin /approve → LIVE_ACTIVE (28 din)
→ trades COPY hone lagti hain (BUY + SELL, notification ke saath)
→ T-2 renewal alert (Telegram + payment link)
→ expiry → GRACE (2 din: entry band, exit chalu, daily reminder)
→ GRACE khatam → EXPIRED_EXIT_ONLY (sirf bot-dili positions exit)
→ last position close → "Plan Fully Closed" (na entry, na exit)
→ /subscribe → wapas LIVE (stacking — koi din waste nahi)
```

---

# 4. ARCHITECTURE — 20 DOMAINS (ZIP-derived baseline; verification is evidence-driven)

## 4.1 Stage 0-11 Canonical Pipeline (feature_sequence.json)
| Stage | Domain | Key files |
|---|---|---|
| 0 | Sharia Universe Foundation (monthly 08:00-08:30) | stock_selector, board_manager, liquidity_screen, sharia_manager |
| 1 | Bot Startup (boot) | bot.py, bot_state_manager, startup_recovery, single_instance |
| 2 | Admin Setup | bot.py, broker, intraday_filter |
| 3 | Daily Data Collection (08:30-09:11) | scheduler, sector_strength, fii_dii, market_regime, news_analyzer, macro_refresh |
| 4 | Market Analysis (cached reads) | market_regime, regime_manager, correlation, portfolio_health |
| 5 | Strategy + Optimization (off-market) | strategy, strategy_tools, optimizer, per_stock_params, walk_forward, ruflo |
| 6 | Validation (off-market) | backtester, parity_engine, monte_carlo, simulate_engine, strategy_validator |
| 7 | Deployment Decision | deployment_manager, workflow_manager |
| 8 | Paper Trading (fast-path) | trade_engine, risk_manager, capital_manager, forever_order_manager, exit_engine |
| 9 | Live Trading (staged) | same chain + bot_state gates |
| 10 | Copy Trading | subscriber_manager, broker, crypto_utils, payment |
| 11 | Monitoring & Compliance | trade_logger, signal_broadcaster, scheduler jobs |

## 4.2 Daily Timeline (time-aware — constitution rule)
```
08:00  subscription expiry | liquidity (monthly) | MACRO refresh (monthly)
08:30  token + scrip master | board retry (monthly sync)
08:45  corporate actions
09:05  sector + FII/DII
09:10  regime pre-market refresh | GTT re-arm (3-layer L3)
09:11  news pre-fetch (LM)
09:15-15:30  SCAN (5 min, parallel candles, fast-path ONLY, ≤3 min budget)
             internal Dhan heartbeat 1 min (market hours) — unchanged
24/7         external HEALTHCHECK_URL dead-man ping every 2 min (empty=skip)
15:35  daily report | 15:40 reconciliation | 15:45 MTF topup
16:00  stage check | 16:30 backup | Sat 09:00 auto-reoptimize PROPOSAL
```

## 4.3 Wiring — Entry Chain (order = execution order)
```
universe (halal∩deployed∩WFV-valid) → parallel candles
→ phase detect (per-stock params) → PHASE GATE (optimization edge)
→ per-phase optimizer-selected toolset (any 1..11 of 11 tools: ema_cross, rsi_ema, breakout, support_bounce, vwap_bounce, bollinger_reversion, connors_rsi2, rsi_divergence, volume_divergence, candle_volume, mtf_composite)
→ macro filter: FII T-1 → sector STRONG (PIT) → regime fallback
→ dedup (candle key) → risk manager 19 checks
  (includes same-day CNC exit possible: BE/T2T skip — not an MIS switch)
→ strategy-evidence ranking (RR is fixed at 1.8R) → sizing (stage×health×regime equal-weight slots)
→ spread check (order-book depth, finalists only)
→ ENTRY = LIMIT CNC @ bot signal price (or better), market hours only
  (Dhan AMO has no MARKET) → fill verify → crash-pending record
→ PARTIAL (q_filled≥1): adopt filled qty + GTT with the fixed 1.8R lock immediately;
  remainder timeout then cancel_order (PARAMS partial_fill_remainder_timeout_sec,
  default 10 min). Do not send q_filled≥1 PARTIAL into entry_follow HOLD.
  Extra fill before timeout is adopted (else recon Case 2 ghost shares).
→ GTT 3-layer (L1 strict SL → L2 fallback → L3 monitor+re-arm)
→ per-trade sizing_scale snapshot
```

## 4.4 Wiring — Exit Chain
```
3-min monitor / live tick → exit_engine (per-stock exit_mode)
  trail | hybrid | ratchet (optimizer-driven; legacy fixed_tp normalizes to trailing)
→ before 1.8R: no BE, no profit floor, no trailing activation
→ at exactly 1.8R: lock floor at 1.8R → thereafter trailing is uncapped
→ exit trigger = SL/TP/trail only — **no EOD / 15:20 square-off**
→ EXIT = MARKET CNC, **only 09:15–15:30 IST** (Dhan AMO has no MARKET)
  after hours: no MARKET order; GTT protects overnight; retry from next 09:15
→ FILL VERIFY
→ FILLED: GTT cancel → release → broadcast → subscriber SELL copy (ledger-only)
→ REJECTED / MARKET_CLOSED: GTT INTACT + retry next cycle + alert
→ PENDING: exit_in_progress guard (no duplicate SELL)
```

---

## 4.5 ZIP-DERIVED COMPLETENESS BASELINE (r3)

The release ZIP is the implementation inventory. The current archive contains **203 files** after extraction (as of r37, 2026-09-20 — 11 new Python files from r32/r33's ARCH-003 god-module split: `scheduler.py` → `scheduler_jobs_core.py`/`scheduler_jobs_daily_ops.py`/`scheduler_jobs_market_data.py`/`scheduler_jobs_board_universe.py`/`scheduler_jobs_research.py`, and `bot.py` → `bot_helpers.py`/`bot_commands_account.py`/`bot_commands_trading.py`/`bot_commands_admin.py`/`bot_commands_research.py`/`bot_livefeed.py` (both originals kept as thin orchestrators, unchanged registration logic); was 191 at r30 — `telemetry.py` + `test_telemetry.py` added for Rule 16; was 189 at r29, 190 at r27 — the foreign tooling artifact `ai_dos_config.json` was purged at r29 — and 168 at this section's original r3 baseline; figures corrected here, not deleted), including **122 Python files, 53 Markdown files, 8 JSON files, 6 CSV files, a SQLite database, a systemd service, shell scripts, environment/requirements/version artifacts, and the `mtf/` and `scripts/` packages**. Every material artifact is in inspection scope.

The implementation scope includes previously under-described components such as `entry_follow.py`, `shadow_log.py`, the complete `mtf/` subsystem, `scripts/`, `dhan_client.py`, `dhan_live_feed.py`, `market_metadata.py`, `corporate_actions.py`, `database.py`, `log_setup.py`, reporting/PDF modules, crypto handling, drawdown policy and risk display, plus all shipped data/DB artifacts.

### Current shipped data snapshot
- `data/MASTER_STOCK_LIST_PERMANENT.csv`: 2,158 rows.
- `data/BOARD_TRUE_100_NON_MUSLIM.csv`: 1,064 rows.
- `data/BOARD_FALSE_HAS_MUSLIM.csv`: 193 rows.
- `data/CUSTOM_UNIVERSE_FINAL.csv`: current derived candidate snapshot is 1,057 rows; this file is regenerated from the 2,158-row master seed during the monthly compliance refresh.
- In `CUSTOM_UNIVERSE_FINAL.csv`, `sector`, `industry`, `market_cap`, `turnover_liquid_ok`, `atvr_pct`, and `frequency_of_trading_pct` currently have zero populated values.
- `data/custom_universe_state.json` records `BOARD_DATA_STALE_PAUSE=true` and the release-data-readiness block.
- `data/decision_data_provider.json` requires a real provider before deployment.

### 55-section sufficiency decision
The newly identified `entry_follow`/shadow and `mtf/` components fit within the existing 55-section backbone: entry-follow maps to entry/order/scheduler/state/crash/runtime-trace sections; shadow logging maps to logs/monitoring/tests/runtime trace; MTF maps to market-data/strategy/look-ahead/backtest/optimizer/tests/wiring. **No additional section is required at this baseline.** A new section is added only if later inspection discovers an independent material risk class that cannot be represented by the existing sections.

### Domain-count reconciliation
The shipped `SYSTEM_MASTER_MANIFEST.json` contains **23 domains** (as of r30, 2026-09-15; was 22 at r27 — was 20 at this section's original baseline, corrected here not deleted). Domain 20 is `entry_follow_execution`; domain 21 (`seq_rule14_alignment`, added r14), domain 22 (`ndsap_data_segregation_accumulation_rule15`, added for Rule 15/NDSAP) and domain 23 (`decision_telemetry_rule16`, added r30 for Rule 16 telemetry) were added afterward. All current product documents must use 23 consistently.

Full list of all 22 (r29, 2026-09-15 — mirrored from `SYSTEM_BLUEPRINT.md` §1.1 so this section itself names every domain, completing r28's correction): 1. `canonical_pipeline`, 2. `workflow_gates`, 3. `sharia_universe`, 4. `data_engineering`, 5. `market_analysis`, 6. `strategy_optimization`, 7. `validation`, 8. `deployment`, 9. `order_execution`, 10. `exit_toolkit`, 11. `overnight_movers`, 12. `risk_capital`, 13. `subscriber_lifecycle`, 14. `payment_system`, 15. `command_interaction`, 16. `number_provenance`, 17. `monitoring_ops`, 18. `tests_verification`, 19. `deploy_readiness`, 20. `entry_follow_execution`, 21. `seq_rule14_alignment`, 22. `ndsap_data_segregation_accumulation_rule15`.


# 5. CALCULATIONS (sab verified — formulas exact)

## 5.1 Signal/Entry
| Formula | Where |
|---|---|
| Phase = ADX ≥ dynamic_threshold ? (EMA_fast>EMA_slow ? UP : DOWN) : SIDEWAYS | strategy.detect_market_phase |
| Dynamic threshold = base × (1 + vol_rank_adjust − trend_relief), clamp [min,max] | strategy._dynamic_phase_threshold |
| LOCK = entry + (entry − SL) × 1.8 (fixed; after lock trailing is uncapped) | strategy/strategy_tools (v6.0) |
| SL = entry candle LOW (floor, kabhi nahi ghat-ta) | strategy (Override-1) |
| RSI Divergence: Price LL + RSI HL = bullish reversal | strategy_tools.opt_rsi_divergence |
| Volume Divergence: Price LL + Volume decreasing = accumulation | strategy_tools.opt_volume_divergence |
| Candle-Volume: Small candle + High volume = smart money buying | strategy_tools.opt_candle_volume |
| MTF Composite: 5-criteria combined (trend + RSI div + vol div + candle-vol + RSI OS) | strategy_tools.opt_mtf_composite |
| Per-stock Tool Parity: optimizer may select any valid 1..11 tool subset per stock; no fixed TOP-N cap | optimizer.optimize_single_stock |
| SL Hunt: Body close rule + wick analysis + ATR filter (optimized wick_multiplier) | exit_engine._is_sl_hunt |

## 5.2 Exit Toolkit (exit_engine — backtest==live ek hi math)
| Mode | Math |
|---|---|
| trail | optimized RR lock (RR ≥ 1.8R) → close−ATR×mult trailing, monotonic ↑, uncapped |
| hybrid | optimized RR lock (RR ≥ 1.8R) → trailing floor upar hi le jata hai, uncapped |
| ratchet | optimized RR lock (RR ≥ 1.8R) → progressive trailing/ratchet, monotonic ↑, uncapped |

## 5.3 Economics
| Formula | Where |
|---|---|
| Deployable = balance × stage × health × regime − SEBI_blocked | capital_manager |
| Qty = deployable / max_slots / price (equal-weight slots) | capital_manager |
| Daily budget = Half-Kelly dynamic (2% sirf emergency fallback) | capital_drawdown_manager |
| Hurdle = risk_free + inflation × 0.5 | capital_drawdown_manager |
| Circuit DD = economics-derived (recovery_base×months/capital), clamp [3%, 10%] | survival_manager |
| min_wr = (1 + fees/risk) / (1 + R:R) with brokerage + statutory + subscription fees | economics_brain (v6.0) |
| Gate A/B = gross − (brokerage 0% [delivery, r10-fixed] + statutory 0.25%) − sub_cost | capital_manager |
| Rapid-loss k* = ln(p_cap)/ln(1−WR) | safety_manager |

## 5.4 Statistical Proof (judge layer — optimize nahi hote)
| Gate | Value | Source |
|---|---|---|
| One-sided t-test | alpha 0.10, df≥2, mean>0 | research convention |
| Walk-Forward Efficiency | ≥ 0.5 | Pardo + industry consensus |
| Monte Carlo worst-path | 5th percentile (VaR-95) | Boyle/Efron |
| MC deploy DD cap | 10% owner LOCKED | owner personal |
| Correlation caps | 0.85 / VIX 0.5 / USDINR −0.4 | verified bands |

---

# 6. NON-FUNCTIONAL REQUIREMENTS

| NFR | Spec |
|---|---|
| Fail-closed | har uncertainty → BLOCK (kam trade), kabhi zyada risk |
| Parity | backtest==optimizer==live (same filters/sizing/exit engine) |
| Provenance | `config.py` currently registers 196 PARAMS entries; exact count is audit-derived |
| Time budget | scan cycle ≤3 min (5-min interval); heavy pre-market |
| Crash safety | pending-order adopt, GTT broker-side, double-run PID lock |
| Security | Fernet subscriber creds, Razorpay HMAC webhook, guides non-downloadable |
| Self-maintenance | monthly macro auto-refresh, GTT re-arm, auto-reoptimize PROPOSAL |
| Observability | audit log, alert taxonomy (dedup), reconciliation matrix, slippage audit, external dead-man ping (`HEALTHCHECK_URL`, empty=skip) |
| State Storage | Dual: SQLite (general) + JSON (specific state) — by design |
| Token Refresh | Daily manual refresh required (Dhan API limitation) |
| Payment | Semi-automated: Razorpay webhook + manual renewal |
| News Sentiment | Loughran-McDonald 2011 verified method (not limitation) |

---

# 7. VERIFICATION SUITE (aaj ka state)

| Suite | Count | Status |
|---|---|---|
| test_sequence.py | 117 PASS / 0 FAIL / 7 EXTERNAL-REQUIRED | ✅ PRE-VPS verified (2026-09-04 fix-list run); external items deferred |
| test_golden.py | Covered by full pytest in current audit environment | ✅ PASS |
| test_overnight.py | Covered by full pytest in current audit environment | ✅ PASS |
| test_macro.py | Covered by full pytest in current audit environment | ✅ PASS |
| pytest local suite | 64 passed / 1 skipped | ✅ PRE-VPS verified |
| phase_tests (offline phase-gate regression) | not shipped in this release | ⚪ NOT INCLUDED |

---

# 8. KNOWN OPEN ITEMS (PhD audit — honest, priority order)

| # | Finding | Severity | Status |
|---|---|---|---|
| F1 | Parity compounding missing /smax (backtest return ~8x inflated → /simulate projections) | 🔴 HIGH | ✅ FIXED v5.8 (per-slot compounding + golden exact test) |
| F2 | Multiple-testing FDR correction (22k t-tests @0.10) | 🔴 HIGH | ✅ FIXED v5.8 (Benjamini-Hochberg 1995, config-driven) |
| F3 | Survivorship bias (current-universe-only backtest) | 🟡 MED | 📋 Phase-2 (PIT universe archive) |
| F4 | RSI/ADX Wilder deviation (SMA vs smoothing; DM compare missing) | 🟡 MED | ✅ FIXED v5.8 (canonical Wilder + test data fix) |
| F5 | Live forming-candle vs backtest closed-bar divergence | 🟡 MED | ✅ FIXED v5.8 (completed-bar signals + live entry re-anchor) |
| F6 | SL fill optimism (gap-down floor-pe fill; label "conservative" ulta) | 🟡 MED | ✅ FIXED v5.8 (honest label + MC severity buffer) |
| F7-9 | Sharpe mislabel, WFE coverage, Kelly label | 🟢 LOW | ✅ FIXED v5.8 (labels + coverage report) |
| F10 | Overnight ka historical backtest nahi (forward paper only) | ℹ️ INFO | accepted (paper proof) |
| F11 | Dead legacy module `paper_trade_manager.py` (v1 subscriber paper-trial, alag formula — confusion "do paper systems") | 🟢 LOW | ✅ FIXED v5.8.1 (DELETE + dead-code watchdog test_sequence me) |
| F12 | Order-pending wait hardcoded (entry 10+10=20s, race 2s, broker default 30s) — owner: "optimization se aana chahiye na?" | 🟢 LOW | ✅ FIXED v5.8.2 (config-driven, ENGINEERING category — broker latency infra hai, optimizer ka ispe koi backtest data nahi; fake precision avoid. Owner tune kar sakta hai) |
| F13 | Entry pending order 20s baad CANCEL hota tha — trade miss (owner: "cancel ke baad market wapas aayi to?") | 🟡 MED | ✅ FIXED v5.9 (ENTRY FOLLOW — order RESTING, broker touch pe fill; cancel level = optimizer geometry × risk_units; SHADOW LOG se data-refined. Sirf execution rule — strategy zero touch) |

---

# 9. ROADMAP

## ✅ DONE (v1.0 → v6.0)
- Poore system ka buildup: sharia universe, phase gates, exit toolkit,
  overnight movers, payment, lifecycle, hardcode migration, macro refresh,
  manifest + onboarding, VPS package.
- v6.0: RSI Divergence, Volume Divergence, Candle-Volume Analysis, MTF
  Composite Signal, Multiple Combo Per Stock, SL Hunt Protection, Mode
  Switching, Help System, MTF Enabled, 8x Bug Fix, Subscriber Order Fix,
  Breakeven with Fees; min_reward_risk fixed at exactly 1.8R; not an optimizer dimension; after lock trailing is uncapped.

## ✅ PHASE A — PHD-FIX (DONE v5.8)
1. F1 parity /smax — **DONE** (per-slot compounding + golden test)
2. F2 FDR correction — **DONE** (Benjamini-Hochberg 1995)
3. F4 Wilder-correct RSI/ADX — **DONE** (canonical Wilder)
4. F5 closed-bar live policy — **DONE** (completed-bar signals)
5. F6 SL fill honest modeling — **DONE** (honest label + MC buffer)
6. F7-9 labels + F10 docs — **DONE** (labels + coverage report)

## 🔜 PHASE B — PAPER TRADING (VPS pe)
1. deploy.sh → /settoken → /boardrefresh → /optimize → /simulate → /deployapprove
2. Paper-trading evidence window is derived at certification time from actual strategy trade/event frequency and the frozen inspection standard; no arbitrary calendar duration is imposed.
3. /overnight edge report → proof ya honest "no edge"

## 🔜 PHASE C — LIVE STAGED
Staged-live capital progression follows the configured deployment/risk policy and must be justified by the frozen release evidence; fixed percentages are not treated as proof by themselves.

## 🔜 PHASE D — BUSINESS
Razorpay KYC → webhook → subscribers → copy trading → P&L statements

## 🔜 PHASE E — ADVANCED (bade phase-2 kaam)
- F3 survivorship PIT universe archive
- Per-stock × per-regime (BULL/SIDEWAYS/BEAR) optimization
- MTF enable (warehouse ready, MTF_ENABLED=True — v6.0)

---

# 10. DELIVERABLE
**Release artifact:** the exact hashed ZIP under certification.
**Deploy:** `bash deploy.sh` only after the release gates and external evidence permit deployment.
**Pehla kaam VPS pe:** `/adminguide` (runbook) → paper trading shuru.

---
*Ye PRD owner ke bataye goal ka final structured roop hai. Koi ambiguity ho
to owner ke GOAL_DISCUSSION.md (D1-D26) ko supreme maana jayega.*

# 11. AUDIT CLOSURE & RE-INSPECTION GOVERNANCE

QASWA uses evidence-linked audit closure so later AI/auditors can preserve valid decisions without confusing implementation preference with defect. The canonical lifecycle is `OPEN → FIXED → TESTED-PASS → CLOSED`; contradictory evidence may move an item to `REOPENED` and then through fix/retest back to `CLOSED`. `DONE` alone has no evidentiary meaning.

A receiving AI must inspect the relevant current ZIP implementation at code/data level and independently evaluate it against the locked criterion. A prior CLOSED result is evidence to verify, not a substitute for inspection. If the logic satisfies the criterion and the evidence remains valid, the receiving AI issues its own PASS/CLOSED result. If actual contradictory evidence or a real defect is found, it issues its own FAIL/REOPENED result with evidence.

A different architecture, refactoring preference, library choice, naming convention, or audit style is not a defect when the locked criterion is already satisfied. Genuinely new independent risks remain reportable and follow the existing section mapping or S56+ gate where applicable. Canonical detail: `docs/CERTIFICATION_CLOSURE_AND_REINSPECTION_GOVERNANCE_v1.0.md`.
