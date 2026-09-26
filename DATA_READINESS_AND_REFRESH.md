# Decision-Critical Data Readiness

The package does **not** fabricate sector, industry, market-cap or liquidity values.

`data/decision_data_provider.json` must be configured with a real provider before
`python scripts/refresh_decision_data.py` can commit a universe refresh.

Refresh policy:

1. Fetch real data.
2. Validate every required field for every intended symbol.
3. Reject missing, stale, non-positive or malformed values.
4. Keep the previous live universe untouched on failure.
5. Set `BOARD_DATA_STALE_PAUSE=True` on failure.
6. Clear the pause only after a complete validated refresh is committed.

A fresh ZIP therefore remains **NOT READY** until real decision-critical data is
materialized and independently validated.

## ASM/GSM surveillance list (pre-trade screen — owner decision 2026-09-05)

`data/asm_gsm_list.json` is surveillance information only; ASM/GSM is not itself a rejection criterion. Separately verified banned/suspended/ineligible status must be an early eligibility gate.
(`asm_gsm_screen.py` → `risk_manager.can_enter_trade` master gate +
`trade_engine.run_market_scan` pre-filter). Same fail-closed policy:

1. List missing, malformed, or older than `PARAMS["asm_gsm_list_max_age_days"]` → surveillance information is stale and must not be treated as verified status. The system must not convert ASM/GSM presence into an automatic rejection.
2. Listed symbol → its entry is blocked before any order is placed (the
   earlier reactive-only behavior — broker rejection *after* ordering — is
   now preceded by this gate; exits remain always-on per constitution).
3. Refresh: `python3 scripts/refresh_decision_data.py` (NSE archives CSV +
   api JSON attempted in order). On failure the stale list is kept — no
   fabricated surveillance data. Admin may also commit a manual file:
   `python3 -c "from asm_gsm_screen import refresh_asm_gsm_list as r; r(manual_csv='asm.csv')"`.
4. Real-list fetch verification is AFTER-VPS evidence (NSE blocks datacenter
   IPs); PRE-VPS ships the mechanism, fail-closed behavior, and tests
   (`test_asm_gsm_screen.py`).
