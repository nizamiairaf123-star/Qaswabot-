# QASWA — MASTER ZERO-OMISSION ZIP INSPECTION CONSTITUTION

This is the mandatory 55-section inspection list for the complete ZIP package.

## Purpose
The auditor MUST inspect the entire ZIP and everything materially contained in it. No file, directory, dataset, column, JSON key, configuration, script, document, service file, test, database, log, cache, manifest, dependency, or generated artifact may be ignored.

## 0. Absolute Auditor Rules
## 0.1 Implementation-to-Operation PASS Contract (MANDATORY FOR EVERY APPLICABLE SECTION)
A section is **not PASS merely because code, a function, setting, class, file, test, or document exists**.
For every criterion that has runtime/implementation relevance, the auditor MUST verify this chain:

**Criterion → Implementation → Integration/Wiring → Invocation/Reachability → Actual Effect → Enforcement → Failure/Bypass Analysis → Evidence**

- [ ] The required implementation exists and actually matches the criterion.
- [ ] The implementation is connected to the intended caller/workflow; an orphaned implementation is not PASS.
- [ ] The relevant execution path can reach and invoke it under the conditions covered by the criterion.
- [ ] The result/output is actually consumed by the system and changes the intended behavior; merely calculating a value is not enough.
- [ ] Required enforcement is effective at the decision point; a later fallback, override, duplicate path, default, exception handler, or alternate implementation cannot silently defeat it.
- [ ] Dead code, dead configuration, unreachable gates, unused functions/classes, unused settings, shadowed configuration, bypasses, and fallback paths are explicitly checked.
- [ ] Where execution is possible, the auditor runs the relevant path and records actual evidence.
- [ ] Where execution is impossible in the current environment, the item is classified as UNVERIFIABLE/EXTERNAL REQUIRED as applicable; static inspection is not converted into runtime proof.
- [ ] For criteria that are purely documentary/package-structure criteria, runtime linkage is marked NOT APPLICABLE rather than fabricated.

**Definition of PASS:** the criterion is satisfied by the actual artifact and, where applicable, its real execution path and enforcement.
**Definition of FAIL:** the criterion is contradicted, missing, dead, disconnected, bypassed, ineffective, or defeated by an unsafe alternate/fallback path.
**Definition of UNVERIFIABLE:** the evidence needed to establish the criterion cannot be obtained in the current environment; do not silently upgrade it to PASS.

This rule applies to **S1–S55 and any genuinely independent S56+ section**. It is a universal gate in addition to each section's own criterion.

- [ ] Do not trust previous audits, README claims, manifests, or test results without independent verification.
- [ ] Do not inspect only Python/source files.
- [ ] Do not stop after finding bugs.
- [ ] Do not assume zero/empty/default/fallback is safe.
- [ ] Do not fabricate missing data.
- [ ] Inspect first; fix only when explicitly instructed.
- [ ] After fixes, re-inspect affected areas.
- [ ] After all fixes, perform a fresh full inspection from the beginning.

## 1. ZIP Integrity
- [ ] ZIP opens and extracts completely.
- [ ] No corrupted/truncated/unreadable entries.
- [ ] No duplicate paths/case collisions.
- [ ] No unexplained nested archives.
- [ ] No hidden/unimportant-looking files skipped.

## 2. Complete File Inventory
For every file record:
- [ ] Path, type, purpose, references, runtime relevance, production relevance.
- [ ] Required/obsolete/generated/test-only status.
- [ ] Safe-to-ship status.
- [ ] Disposition: KEEP / FIX / REMOVE / REPLACE / DOCUMENT / UNKNOWN.
- [ ] No unexplained file remains.

## 3. Source Code — All Files
Inspect every source file individually:
- [ ] Imports, functions, classes, constants, globals, defaults.
- [ ] Environment/config usage, paths, DB/network/API access.
- [ ] Auth/authz, exceptions, retries, timeouts, logging.
- [ ] State, side effects, threading/async/scheduling.
- [ ] Persistence/serialization.
- [ ] Input/output validation and boundary cases.
- [ ] Numeric precision/rounding.
- [ ] Timezone/date/market-hours handling.
- [ ] Recovery/failure/security/compliance behavior.

## 4. Import / Dependency Graph
- [ ] All internal imports resolve.
- [ ] No circular imports.
- [ ] No undeclared runtime dependency.
- [ ] No hidden runtime-only dependency.
- [ ] Optional/mandatory dependencies correctly classified.
- [ ] Requirements match actual imports.
- [ ] Version/Python compatibility checked.
- [ ] Clean-install import test performed.

## 5. Requirements / Package Installation
Inspect requirements, pyproject/setup/lock/Docker/environment metadata.
- [ ] No missing/incorrect/incompatible/unnecessary production dependency.
- [ ] Fresh installation works.
- [ ] Application starts after fresh installation.

## 6. Configuration Audit
Inspect every config source.
For every setting:
- [ ] Name, type, default, allowed range, unit, source, consumer, runtime effect, failure behavior.
- [ ] No dangerous default/silent fallback/contradictory duplicate.
- [ ] No unused setting or hardcoded runtime bypass.
- [ ] No hardcoded secret.

## 7. Every Numeric Value Audit
Inspect all meaningful numbers:
- [ ] Thresholds, percentages, ratios, prices, quantities, timeouts, retries, intervals.
- [ ] Risk, RR, SL, TP, exposure, liquidity, deployment, subscription, scheduler values.
- [ ] Intent, units, configurability, source, duplication, conflicts, runtime effect verified.

## 8. CSV / Tabular Data — Complete Content Audit
Every CSV must be inspected:
- [ ] Rows/columns, encoding, delimiter, headers.
- [ ] Duplicate/empty/malformed rows.
- [ ] Unexpected/missing columns.
For every column:
- [ ] Meaning, type, allowed values, missing representation, default, unit, source, runtime use.
Content:
- [ ] Null/zero/negative/duplicate/impossible/out-of-range/placeholder/fake/default/suspicious values checked.
- [ ] Never assume 0 or empty has a safe meaning.

## 9. Data Semantic Audit
For every decision-critical field:
- [ ] Value meaning verified, not merely column existence.
- [ ] Real, current, correctly sourced and interpreted.
- [ ] Sector, industry, market cap, price, volume, turnover, ATVR, compliance, board, liquidity, rank/score/status checked where present.

## 10. Data Provenance
For every decision-critical field:
- [ ] Source real/documented/reachable.
- [ ] Retrieval and transformation verified.
- [ ] Timestamp/freshness/update schedule verified.
- [ ] Failure/historical fallback behavior verified.
- [ ] No fabricated or silently stale data.

## 11. JSON / State File Audit
Inspect every JSON/key:
- [ ] Purpose, type, defaults, valid values, consumer, timestamps, persistence.
- [ ] Invalid/missing/extra keys and impossible/contradictory states.
- [ ] Stale approval/universe/liquidity/board/deployment/subscription/live state checked.

## 12. Database Audit
Inspect every DB:
- [ ] Tables, columns, types, keys, indexes, constraints, defaults, triggers, migrations, schema version.
- [ ] Test/production/stale/orphan/duplicate/impossible records.
- [ ] Sensitive data and old trades/positions/approvals/workflow state.
- [ ] Determine whether DB should ship.

## 13. Logs / Audit Files
- [ ] No secrets/tokens/passwords/unnecessary PII.
- [ ] No fake or misleading production history.
- [ ] Timestamp/timezone correctness.
- [ ] Rotation/error levels.
- [ ] Critical/security/trading/reconciliation events logged.

## 14. Cache / Generated / Temporary Files
Inspect __pycache__, .pyc, test/build/cache/temp/editor/backup/old ZIP/report/dataset artifacts.
- [ ] Required/safe/stale/runtime-impact assessed.
- [ ] Remove unless explicitly required.

## 15. Sharia / Custom Compliance Audit
- [ ] Haram sectors rejected.
- [ ] Business description/subsidiaries/principal business checked.
- [ ] Ambiguous/unknown business blocked.
- [ ] Board missing/unknown/fetch/parse/stale errors blocked.
- [ ] No bypass.
- [ ] Entire intended universe scanned.
- [ ] NSE-only and required series enforced.
- [ ] Suspended rejected; ASM/GSM handled according to mandate.

## 16. Liquidity Audit
- [ ] Market-cap source/freshness/units/zero/missing handling.
- [ ] Turnover/OHLCV source.
- [ ] ATVR/FoT formula, lookback, trading-day count, threshold.
- [ ] Liquidity state persistence/freshness/missing/stale/calculation failure/exception path.
- [ ] Any liquidity uncertainty = BLOCK.

## 17. Market Data Audit
- [ ] Source/authentication/history/live/OHLC/volume/timestamps/timezone.
- [ ] Missing/duplicate/out-of-order candles.
- [ ] Corporate actions, splits, bonuses, bad ticks.
- [ ] Zero/negative/impossible OHLC.
- [ ] Stale data, API failure, retry, timeout, rate-limit behavior.

## 18. Strategy Mathematics
Independently verify:
- [ ] Indicators, RSI, Bollinger Bands, moving averages, volume.
- [ ] Entry, SL, TP, RR, trailing stop, profit floor.
- [ ] Position sizing, risk, exposure, compounding, drawdown, CVaR, deployment.
- [ ] Normal/zero/negative/extreme/boundary/missing/rounding cases.

## 19. Look-Ahead / Data Leakage
- [ ] Future candle/close/volume/corporate action/universe/liquidity/board information.
- [ ] Train/test/validation contamination.
- [ ] Survivorship and selection bias.

## 20. Backtest Audit
- [ ] Realistic entry/exit.
- [ ] Spread, slippage, brokerage, taxes/fees.
- [ ] Partial fills, gaps, market hours, capital constraints.
- [ ] Simultaneous positions, portfolio constraints, rejected orders, unavailable liquidity.

## 21. Optimizer Audit
- [ ] Parameter bounds/objective.
- [ ] Train/validation/test/walk-forward.
- [ ] Minimum calls/reproducibility/seed.
- [ ] Overfitting/leakage/multiple testing/FDR.
- [ ] Per-stock/universe isolation.
- [ ] Circular references/failure/timeout/invalid output.

## 22. Exit Engine — Zero-Omission
- [ ] SL, TP, trail, profit floor, emergency/time/broker/manual/network/restart exits.
- [ ] Explicit priority.
- [ ] Hard floor cannot be suppressed/decrease/disappear after restart.
- [ ] No duplicate exit.
- [ ] Same-candle/gap/intrabar behavior deterministic.
- [ ] Broker rejection/failure retry/reconciliation safe.

## 23. Risk Engine
- [ ] Per-trade/portfolio/max-position/sector/correlation/drawdown/CVaR/daily-loss limits.
- [ ] Emergency stop and capital deployment.
- [ ] Quantity/tick/broker restrictions.
- [ ] Every limit actually enforced at runtime.

## 24. Order Engine
- [ ] Exchange/symbol/series/quantity/order type/price/trigger/product/validity.
- [ ] Broker response/order ID/fill/partial fill/rejection/cancellation/retry.
- [ ] Duplicate prevention.

## 25. Live / Paper Separation
- [ ] Paper cannot send live.
- [ ] Live cannot silently fall back to paper.
- [ ] Explicit state transitions.
- [ ] LIVE_FULL requires all gates.
- [ ] Capital deployment/admin/broker/config-freeze/audit requirements enforced.

## 26. Scheduler Audit
For every job:
- [ ] Frequency, market hours, timezone.
- [ ] Duplicate prevention, failure/retry/timeout/overlap.
- [ ] Restart/missed-job behavior.
Verify position monitor, heartbeat, reconciliation, board/universe refresh, optimization, backups, cleanup.

## 27. Failure / Fail-Closed Audit
Search all:
- [ ] except, fallback, default, placeholder, return True, continue, pass, retry, bypass, skip, disable, override.
For each:
- [ ] Determine whether unsafe trade can result.
- [ ] Critical failures = BLOCK / PAUSE / KILL, never unsafe CONTINUE.

## 28. Network Failure Audit
Simulate Dhan, Telegram, data, board, DB unavailable; partial response; timeout; malformed response; rate limit; DNS; connection reset.
- [ ] No unsafe trade occurs.

## 29. Crash / Restart Audit
Kill process before/after entry, acknowledgement, fill, exit, trailing, reconciliation, persistence.
Restart:
- [ ] Positions/orders/floor/state recovered.
- [ ] No duplicate/lost trade/order/position.
- [ ] Capital correct and reconciliation performed.

## 30. Telegram / Admin Control Audit
- [ ] Authentication/authorization.
- [ ] Admin/subscriber/invalid/malformed/unauthorized/duplicate/replay commands.
- [ ] Sensitive-data leakage and safe errors.

## 31. Subscription / Copy Trading
- [ ] Trial/paid duration/expiry/live/copy permission.
- [ ] Allocation/sizing/risk.
- [ ] Master/subscriber position and exit synchronization.
- [ ] Failed/expired/duplicate-copy handling.

## 32. Deployment Audit
Inspect deploy.sh, start_bot.sh, systemd, Docker, deployment guide, environment, permissions, working directory, Python executable, user, restart policy, logs, service dependencies, network.
- [ ] Fresh machine: ZIP → install → configure → validate → start → health check.

## 33. Production Package Hygiene
Remove unless required:
- [ ] Caches, compiled Python, temp/test artifacts, old logs/DB/runtime state, backups, previous ZIPs, developer-specific config.
- [ ] Do not remove required seed/static data without verifying.

## 34. Documentation Audit
Read every document.
- [ ] Architecture, workflow, features, sequence numbers, config, deployment, risk, Sharia, liquidity, subscription, live/paper/copy, monitoring.
- [ ] Every claim matches implementation.

## 35. Version / Release Audit
- [ ] ZIP name, VERSION, README, manifest, CHANGELOG, deployment guide, reports, bot version, DB schema, API metadata agree.
- [ ] Conflicts explicitly explained.

## 36. Manifest Audit
Two-way:
- [ ] Manifest → ZIP: every declared artifact exists.
- [ ] ZIP → Manifest: every production-relevant artifact declared.
- [ ] Missing/extra/renamed/obsolete/wrong-path/version/hash issues checked.

## 37. Security Audit
Search:
- [ ] API keys, tokens, passwords, broker/Telegram secrets, private keys, cookies, credentials.
Inspect:
- [ ] Permissions, command/path/SQL injection, unsafe deserialization, arbitrary execution, subprocess safety.

## 38. Test Audit
For every test:
- [ ] Purpose, real behavior, production path vs mock.
- [ ] Meaningful assertions.
- [ ] Failure/boundary coverage.
- [ ] Skip/xfail/weak assertions/empty assertions.
- [ ] Realistic fixtures.
- [ ] No test-only bypass.

## 39. Independent Recalculation
Independently recalculate:
- [ ] Entry, SL, TP, RR, quantity, risk, P&L, fees, drawdown, exposure, liquidity, capital deployment.

## 40. Cross-File Consistency
Trace:
Definition → Configuration → Data → Function → Caller → Runtime → Output → Persistence → Documentation.
- [ ] Sharia, board, liquidity, universe, strategy, risk, capital, LIVE_FULL, paper, copy, reconciliation.
- [ ] No orphan/dead/bypass gate.

## 41. Dead Code / Dead Configuration
Find:
- [ ] Never-called functions/classes.
- [ ] Unread settings/files.
- [ ] Obsolete flags/old/duplicate implementations.
Classify required/intentional/obsolete/dangerous.

## 42. Data Update Pipeline
Verify:
Source → Fetch → Validate → Transform → Store → Refresh → Freshness → Runtime.
- [ ] First load/normal/partial/failed/stale/corrupt/recovery/persistence.

## 43. Time / Date / Timezone
- [ ] UTC/IST/exchange/DB/scheduler/log timezone.
- [ ] Market hours/DST/date boundaries/midnight/weekend/holiday/expiry.
- [ ] No unsafe implicit timezone.

## 44. State Machine
Enumerate every state:
- [ ] Entry/exit conditions.
- [ ] Allowed/forbidden transitions.
- [ ] Persistence/recovery/admin override/failure behavior.
- [ ] Impossible states prevented.

## 45. Capital Deployment
- [ ] Stage definitions/transitions.
- [ ] Risk budget/CVaR/drawdown/capital availability.
- [ ] Broker balance/deployed/reserved/available/full deployment.
- [ ] Restart behavior.

## 46. Reconciliation
Compare:
Bot ↔ DB ↔ Broker ↔ Orders ↔ Positions ↔ Trades.
Test missing/extra/wrong quantity/average price/order/trade/P&L.
- [ ] Every mismatch has defined action.

## 47. Failure-Injection Matrix
Mandatory:
- [ ] Board API down → BLOCK.
- [ ] Liquidity missing → BLOCK.
- [ ] Market data missing → BLOCK.
- [ ] Broker unavailable → BLOCK.
- [ ] Unknown stock/compliance → BLOCK.
- [ ] Stale universe/board/liquidity → BLOCK.
- [ ] DB failure → SAFE STOP.
- [ ] Crash → RECOVER.
- [ ] Duplicate order → PREVENT.
- [ ] Broker rejection → HANDLE.
- [ ] Partial fill → RECONCILE.
- [ ] Telegram failure → trading safety preserved.
- [ ] Missing/invalid config → BLOCK.

## 48. False-Pass Audit
Search for:
- [ ] Swallowed exception, return True, continue, placeholder, default success.
- [ ] Empty result/zero/missing/stale data treated as valid.
- [ ] Failed/partial refresh treated as successful.

## 49. Complete Runtime Trace
Trace accepted trade:
Universe → Compliance → Board → Liquidity → Market Data → Signal → Strategy → Validation → Risk → Capital → Order → Broker → Fill → Position → SL/TP → Exit → Reconciliation → Log.
- [ ] Trace rejected trade through same gates.
- [ ] Exact block reason verified.

## 50. Final Release Audit
- [ ] Entire ZIP inspected.
- [ ] Every artifact/data/key/config/dependency/document/deployment/test/runtime-state accounted for.
- [ ] Critical calculations/workflows/failures independently verified.
- [ ] P0/P1 resolved.
- [ ] No unexplained artifact/data/config/manifest/version/secret/stale production state.
- [ ] Clean package/install/start/recovery/reconciliation verified.

## 51. Final Verdict Rule
Only:
- 🟢 FINAL / PRODUCTION-READY
- 🟡 CONDITIONAL
- 🔴 NOT READY

NOT READY if any critical code/compliance/calculation/risk/exit/data/deployment/manifest/reconciliation/P0 issue remains.

## 52. Mandatory Final Report
Report:
- [ ] ZIP inventory counts.
- [ ] Every finding: ID, severity, file/location, problem, impact, fix, verification, status.
- [ ] Decision-critical data audit.
- [ ] Dependency audit.
- [ ] Documentation audit.
- [ ] Deployment audit.
- [ ] Runtime audit.
- [ ] P0/P1/P2/Unresolved/Unknown.
- [ ] Files inspected X/X.
- [ ] Data X/X.
- [ ] Tests executed/passed/failed/skipped.
- [ ] Final verdict and exact reason.

## 53. Zero-Omission Completion Certificate
Before completion, auditor must honestly confirm:

“I inspected the complete extracted ZIP inventory rather than only the source-code subset. I inspected source code, configuration, dependencies, documentation, CSV/tabular data contents, JSON/state files, databases, logs, tests, deployment files, generated/cache files, runtime-state files, manifests, version metadata and cross-file/runtime relationships. I did not rely solely on existing test results or previous audit claims. Every discovered artifact was accounted for, and every unresolved item is listed.”

If this cannot be honestly confirmed, inspection is NOT COMPLETE.

## 54. No Shortcut Rule
Not acceptable as proof:
- All tests passed.
- Code compiles.
- Main files look correct.
- Manifest looks correct.
- README says complete.
- Previous AI audited it.
- ZIP extracted.
- Major modules checked.
- No obvious bugs.
- Smoke test passed.
- Architecture looks good.

Complete inspection requires artifact-level + data-level + runtime-level + cross-system-level verification.

## 55. Final Instruction to Any AI Receiving This ZIP
DO NOT FIX FIRST. INSPECT FIRST.

1. Extract entire ZIP.
2. Generate complete inventory.
3. Account for every artifact.
4. Inspect every artifact category.
5. Inspect actual data.
6. Trace decision-critical fields into runtime.
7. Trace critical runtime outputs back to source.
8. Independently verify critical mathematics.
9. Run tests.
10. Inspect tests.
11. Perform failure injection.
12. Perform clean-install/deployment verification.
13. Compare documentation with implementation.
14. Compare manifest with package.
15. Compare package with runtime requirements.
16. Record every finding.
17. Do not stop after finding bugs.
18. Reinspect after fixes.
19. Perform complete inspection again after all fixes.
20. Only then issue FINAL / CONDITIONAL / NOT READY.

The phrase “complete inspection” means the entire ZIP, not merely the code.
If even one material artifact has not been inspected or accounted for, inspection is incomplete.
