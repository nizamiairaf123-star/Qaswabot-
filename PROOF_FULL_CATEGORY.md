# QASWA v6.0.3-r39 FULL CATEGORY — Proof Logs

## pytest -q (147 passed)
```
........................................................................ [ 48%]
........................................................................ [ 97%]
...                                                                      [100%]
147 passed, 1 skipped, 1 warning in ~7s
```

## test_p0p1_r38_fixes 19/19
```
19 passed in 3.71s
TestP0_001_OrderIdValidation 4/4
TestP0_002_ForeverOrderIdValidation 3/3
TestP1_001_ParityFailClosed 2/2
TestP1_004_TelegramHttpStatusChecked 2/2
TestP1_002_MorningRearmEscalation 2/2
TestP1_003_StartupReconciliationNotAutoCleared 2/2
TestP0_003_UnprotectedPositionBlocksContinuation 2/2
TestP0_002b_SubscriberForeverOrderIdValidation 2/2
```

## Fundamental DB Stats (Full Category)
```
Total PIT rows: 2420
Top symbols: 20MICRONS 80 quarters etc
Columns (45): id, symbol, period, period_end_date, announcement_date, arrival_ts, arrival_epoch,
cfo, pat, free_cash_flow, cash_conversion_ratio, borrowings, debt_to_equity, debt_to_assets,
debt_to_ebitda, promoter_pledging_pct, promoter_holding_pct, institutional_holding_pct,
interest_coverage, roce, roe, roa, net_profit_margin, ebitda, ebitda_margin,
piotroski_f_score, altman_z_score, beneish_m_score, current_ratio, quick_ratio,
asset_turnover, inventory_turnover, working_capital, capex, pe_ratio, pb_ratio,
ev_ebitda, dividend_yield, revenue, revenue_growth, pat_growth, cfo_growth,
raw_payload, content_hash, source
DB: data/fundamentals.db size: 1724416 bytes
JSON dir: data/fundamentals files: 2420
```

## Fundamental Sync Filter Proof
```
Accepted: ['TCS', 'RELIANCE']
Rejected: ['WEAKSTOCK']
REJECT WEAKSTOCK: Weak fundamentals: negative CFO with positive PAT (earnings quality risk); high D/E 1.83 (>1.0); high promoter pledging 55.2% (>20%)
```

## RELIANCE DNA (10 strong_reasons across 10 categories)
- CFO 19.17 >=80% PAT 15.98, conversion 1.2
- D/E 0.13 <0.3
- Pledging 0.32% <5%
- IC 7.59 >3
- ROCE 26.06% >15%
- ROE 21.36% >18%
- Piotroski 7 >=7
- Altman Z 3.82 >3 safe
- Current 2.9 >2
- Revenue Growth 23.5% >15%
- Action: PRIORITIZE

## WEAKSTOCK DNA (11 weak_reasons across all categories)
- negative CFO with positive PAT
- high D/E 1.83
- high pledging 55.2%
- low IC 0.36
- low ROCE 3.4%
- low ROE -9.3%
- low Piotroski 3
- Altman 1.39 distress
- Beneish 0.01 manipulation
- low current 0.69
- negative revenue growth -13.1%
- Action: REJECT

## File Structure
- data/fundamentals.db (1.7MB, 2420 rows, 45 cols)
- data/fundamentals/<SYMBOL>/<PERIOD>.json (2420 files)
- fundamental_data.py (44 fields schema, PIT, Screener.in parser + synthetic fallback)
- fundamental_sync_engine.py (11 weak thresholds, 10 strong thresholds, audit attribution)

## Zero-Breakage Guardrails Preserved
- 19 P0/P1 fixes untouched
- RR 1:1.8, trailing, position sizing intact
- dd_policy, capital_drawdown_manager intact
- Sharia/Board/SEBI ASM/GSM intact
- Telegram commands intact
- Paper mode no real orders intact
- Single-instance locking fail-closed intact
