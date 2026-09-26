> **SUPERSEDED — CURRENT AUTHORITY:** `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md` + `prd.md` + `SYSTEM_BLUEPRINT.md` + `docs/MASTER_ZERO_OMISSION_ZIP_INSPECTION_CONSTITUTION_55_SECTIONS.md`. This historical document is retained for audit trail only and must not be used as a current checklist or verdict.

> **SUPERSEDED / REFERENCE-ONLY — current authority: `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md`. This file is preserved only for history/evidence and must not be used as the current criteria source.**

# QASWA — FINAL MASTER INSPECTION & RELEASE CHECKLIST v3.0

**Release rule:** One unresolved P0 = NOT PRODUCTION READY. A passing smoke test is not a final certificate.

## 0. Package Integrity
- [ ] ZIP opens and extracts cleanly
- [ ] No duplicate project roots
- [ ] No `__pycache__` / `.pyc`
- [ ] No secrets, broker tokens, Telegram tokens, test credentials
- [ ] Required production files present
- [ ] Python version declared
- [ ] `requirements.txt` contains every third-party import
- [ ] Clean install succeeds
- [ ] No undeclared runtime dependency

## 1. Manifest / Documentation
- [ ] Manifest ↔ package contents audited
- [ ] No stale/missing manifest references
- [ ] README accurate
- [ ] PRD accurate
- [ ] Blueprint accurate
- [ ] AI onboarding accurate
- [ ] Changelog/version accurate
- [ ] Deployment guide accurate
- [ ] Inspection checklist accurate
- [ ] No documentation claim contradicts code

## 2. SEQ-0 — Sharia / Universe
- [ ] Complete NSE universe source available
- [ ] NSE-only execution
- [ ] BSE-only rejected
- [ ] EQ only
- [ ] BE/BL/BT/T2T/intraday-restricted rejected
- [ ] ASM/GSM not an automatic rejection criterion; separate verified suspended/banned status gate applies
- [ ] Suspended rejected
- [ ] Haram sectors rejected
- [ ] Business description checked
- [ ] Subsidiaries checked where required
- [ ] No AAOIFI financial-ratio gate unless explicitly required
- [ ] No Muslim-director rejection unless explicitly required
- [ ] Board verification mandatory
- [ ] Missing/error/unknown board data = BLOCK
- [ ] No `non_muslim_board=True` error fallback
- [ ] No scheduler bypass
- [ ] Stale board data = BLOCK
- [ ] Missing price = BLOCK
- [ ] Invalid price = BLOCK
- [ ] Missing liquidity verification = BLOCK
- [ ] ATVR/FoT calculation verified
- [ ] No claim of full MSCI implementation unless actually implemented

## 3. SEQ-1 — Startup / Recovery
- [ ] Config validation
- [ ] Environment validation
- [ ] Broker initialization
- [ ] Telegram initialization
- [ ] Database initialization
- [ ] State restoration
- [ ] Crash recovery
- [ ] Pending-order recovery
- [ ] Position adoption
- [ ] Duplicate-position protection
- [ ] Startup killswitch
- [ ] Startup stale-universe protection
- [ ] Cannot accidentally enter LIVE

## 4. SEQ-2 — Admin / Subscription
- [ ] Authentication
- [ ] Admin-only commands
- [ ] Subscriber lifecycle
- [ ] Trial/paid/grace/expired states
- [ ] Live permission explicit
- [ ] Live permission cannot bypass deployment gate
- [ ] Copy permission separate
- [ ] Unauthorized command rejection
- [ ] State transition audit

## 5. SEQ-3 — Data Engineering
- [ ] Historical OHLCV
- [ ] Live data
- [ ] Missing/duplicate candle checks
- [ ] Timestamp normalization
- [ ] Market calendar
- [ ] Corporate actions
- [ ] Retry/rate-limit handling
- [ ] Data freshness
- [ ] Corrupt/missing data = no trade
- [ ] No look-ahead

## 6. SEQ-4 — Market Analysis
- [ ] RSI
- [ ] Bollinger
- [ ] Moving averages
- [ ] Volume
- [ ] MTF alignment
- [ ] Regime detection
- [ ] Sector strength
- [ ] FII/DII
- [ ] News/economics inputs
- [ ] No future data
- [ ] Correct timeframe synchronization
- [ ] NaN/error handling

## 7. SEQ-5 — Strategy / Optimization
- [ ] Entry logic matches specification
- [ ] Exit logic matches specification
- [ ] SL/TP
- [ ] Minimum RR
- [ ] Profit side uncapped
- [ ] Parameter bounds
- [ ] Per-stock optimization
- [ ] No circular references
- [ ] Walk-forward
- [ ] Out-of-sample validation
- [ ] FDR/overfit controls
- [ ] No optimization leakage
- [ ] Optimizer cannot expand universe
- [ ] Optimizer cannot bypass Sharia gate

## 8. SEQ-6 — Backtest / Simulation
- [ ] Fees
- [ ] Slippage
- [ ] Position sizing
- [ ] Compounding
- [ ] Risk budget
- [ ] CVaR
- [ ] Drawdown
- [ ] Exposure/correlation
- [ ] Realistic fills
- [ ] No look-ahead
- [ ] No impossible fills
- [ ] Reproducible results
- [ ] Backtest/simulation sizing parity

## 9. SEQ-7 — Deployment
- [ ] Validation gate
- [ ] Deployment approval
- [ ] Configuration freeze
- [ ] Universe freeze
- [ ] Strategy freeze
- [ ] Risk freeze
- [ ] Capital stage enforcement
- [ ] LIVE_FULL cannot bypass stages
- [ ] Rollback
- [ ] Audit decision

## 10. SEQ-8 — Paper Trading
- [ ] Entry order generation
- [ ] Realistic fill simulation
- [ ] Partial/rejected fills
- [ ] Position tracking
- [ ] SL/TP/trailing
- [ ] Profit floor
- [ ] Scheduled monitoring
- [ ] Reconciliation
- [ ] Network heartbeat
- [ ] Paper/live path parity

## 11. SEQ-9 — Live Trading
- [ ] All gates evaluated before entry
- [ ] NSE-EQ gate
- [ ] Sharia gate
- [ ] Board gate
- [ ] Liquidity gate
- [ ] Strategy gate
- [ ] Risk gate
- [ ] Capital gate
- [ ] Duplicate protection
- [ ] Broker availability
- [ ] Entry acknowledgement/fill verification
- [ ] Exit acknowledgement/fill verification
- [ ] GTT protection
- [ ] Emergency exit

## 12. Exit Engine — P0 Deep Audit
- [ ] Hard profit floor cannot be suppressed by SL-hunt logic
- [ ] Floor never decreases
- [ ] Ratchet only increases
- [ ] TP/floor interaction deterministic
- [ ] Intrabar low handling deterministic
- [ ] Same-candle SL/TP deterministic
- [ ] Gap behavior defined
- [ ] Restart preserves floor
- [ ] No duplicate exit
- [ ] Golden hybrid regression passes
- [ ] Golden ratchet regression passes
- [ ] Golden fixed-TP regression passes
- [ ] Golden trail regression passes

## 13. SEQ-10 — Copy Trading
- [ ] Master position mapping
- [ ] Subscriber allocation
- [ ] Subscriber risk limits
- [ ] Entry copy
- [ ] Exit copy
- [ ] Partial fills
- [ ] Failure isolation
- [ ] Duplicate-copy prevention
- [ ] Expiry enforcement
- [ ] Audit log

## 14. SEQ-11 — Monitoring / Reconciliation
- [ ] 1-minute heartbeat
- [ ] 3-minute position monitor
- [ ] Daily reconciliation
- [ ] Broker-vs-bot mismatch
- [ ] Network partition detection
- [ ] Recovery
- [ ] Stale data detection
- [ ] Killswitch
- [ ] Alerts
- [ ] Persistent audit log
- [ ] No silent failure

## 15. Runtime Safety
- [ ] Fail-closed compliance gates
- [ ] No exception → safe-looking `True`
- [ ] No silent exception swallowing
- [ ] No stale-universe trading
- [ ] No stale-board trading
- [ ] No stale-price trading
- [ ] No broker mismatch ignored
- [ ] No accidental live activation
- [ ] No duplicate orders

## 16. Deployment
- [ ] Fresh VPS install
- [ ] `pip install -r requirements.txt`
- [ ] Zero missing imports
- [ ] Environment variables documented
- [ ] Dhan connectivity
- [ ] Telegram connectivity
- [ ] Database initialization
- [ ] Scheduler startup
- [ ] systemd service
- [ ] Restart policy
- [ ] Logging/rotation
- [ ] Deployment script
- [ ] Rollback procedure
- [ ] Health check

## 17. Testing
- [ ] AST compile all source files
- [ ] Import graph audit
- [ ] Circular import audit
- [ ] Static dangerous-fallback audit
- [ ] Unit tests
- [ ] Integration tests
- [ ] End-to-end tests
- [ ] Failure injection: network
- [ ] Failure injection: broker
- [ ] Failure injection: Telegram
- [ ] Failure injection: board source
- [ ] Failure injection: corrupt data
- [ ] Failure injection: partial fill
- [ ] Failure injection: process crash
- [ ] Failure injection: VPS restart
- [ ] Database failure test

## 18. Security / Compliance
- [ ] No secrets in package
- [ ] Credentials protected
- [ ] Admin authorization
- [ ] Order commands protected
- [ ] Sharia gate cannot be bypassed
- [ ] Universe cannot be expanded without authorization
- [ ] Configuration changes audited

## 19. Mathematical / Financial Audit
- [ ] Position sizing formula
- [ ] Risk-per-trade
- [ ] RR
- [ ] Portfolio risk
- [ ] CVaR
- [ ] Drawdown
- [ ] Exposure
- [ ] Capital deployment
- [ ] Quantity rounding
- [ ] Tick size
- [ ] Brokerage/fees/taxes
- [ ] Slippage
- [ ] Realized/unrealized P&L

## 20. FINAL RELEASE GATE
- [ ] SEQ-0 → SEQ-11 PASS
- [ ] P0 count = 0
- [ ] P1 count = 0
- [ ] Full test suite PASS
- [ ] Fresh install PASS
- [ ] Fresh VPS deployment PASS
- [ ] Manifest audit PASS
- [ ] Static audit PASS
- [ ] Runtime integration PASS
- [ ] Failure injection PASS
- [ ] Paper-trading runtime PASS
- [ ] Restart/recovery PASS
- [ ] No unresolved code/test contradiction
- [ ] No missing production artifact
- [ ] No undocumented mandatory dependency

**Certification:** FINAL only when every mandatory item is verified. Otherwise: NOT PRODUCTION READY.
