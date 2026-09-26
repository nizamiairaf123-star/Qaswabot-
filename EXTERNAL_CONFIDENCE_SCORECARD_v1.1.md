# EXTERNAL CODE-BASIS SCORECARD — QASWA v6.0.3-r3

**Important:** these are code/evidence confidence scores, not real-world test results. An unavailable external test never becomes a PASS merely because code confidence is high.

| Area | Code-basis confidence | External evidence still required | Release impact |
|---|---:|---|---|
| Decision-data provider / universe refresh | 95% | Real provider refresh populating sector/industry/market-cap/ATVR/FoT and dated validation | BLOCKING |
| Dhan authentication/order lifecycle | 95% | Real controlled auth, order, rejection, partial/timeout/fill tests | BLOCKING |
| Live market data / WebSocket | 90% | Actual market-hours freshness and reconnect evidence | BLOCKING |
| VPS deployment/restart/scheduler | 95% | Real VPS install, restart, scheduler and recovery evidence | BLOCKING |
| Broker reconciliation | 95% | Controlled real mismatch/orphan scenarios | BLOCKING |
| Telegram/admin runtime | 95% | Real auth/replay/delivery/outage evidence | Blocking if enabled |
| Payment/webhook | 90% | Real/sandbox signature, replay and duplicate-event evidence | Blocking if enabled |
| Backup/restore | 90% | Actual restore + reconciliation evidence | BLOCKING |

These values are the static/evidence confidence of the inspected implementation baseline; they are deliberately kept separate from the internal test score and do not certify production behavior.
