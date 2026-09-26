# QASWA PRE-VPS GATE PROFILE v1.0

## Purpose
This is the phase-scope profile for the frozen 55-section inspection constitution. It does not replace or weaken the product requirements, engineering requirements, or runtime safety rules. It defines **when evidence is required**.

## PRE-VPS definition
PRE-VPS answers one question:

> **Is the delivered QASWA engineering artifact internally coherent, implemented, wired, fail-safe, testable, reproducible, documented, and ready to be deployed into the real VPS environment for external verification?**

PRE-VPS does **not** claim that external services, real broker behavior, real market data, or real market-hours execution have already been verified.

## Evidence classification
Every S1-S55 section is still inspected. For hybrid sections, split the evidence into:

- **PRE-VPS ENGINEERING EVIDENCE:** deterministic evidence obtainable from the ZIP and offline/local execution.
- **AFTER-VPS EXTERNAL EVIDENCE:** evidence that inherently requires the VPS, real provider, broker, live service, market clock, credentials, or production-like external environment.

An external item is not a PRE-VPS failure when: (a) the required code/control exists, (b) the failure boundary is fail-closed where safety requires it, and (c) the package contains an explicit post-deployment verification procedure.

## Hard boundary
The following are intentionally AFTER-VPS when no safe offline substitute exists:

- real sector/industry/market-cap/liquidity/ATVR/FoT provider refresh;
- Dhan authentication and real API calls;
- real order/fill/rejection/cancellation behavior;
- real scheduler timing on the target VPS;
- WebSocket/network disconnect/reconnect against real services;
- crash/restart against real broker state;
- real Telegram/payment webhooks;
- production-machine installation and service execution.

The package must never fabricate these results.

## PRE-VPS PASS contract
A PRE-VPS PASS requires all applicable engineering requirements across S1-S55 to pass, with every external portion explicitly classified and deferred. It also requires:

1. no unresolved P0/P1 PRE-VPS engineering defect;
2. no dead safety-critical configuration;
3. no silent requirement substitution;
4. no bypass/fail-open path that can defeat a mandatory safety gate;
5. local executable tests that are intended to be local actually pass;
6. declared dependencies are complete and reproducible via the package's lock mechanism;
7. complete artifact/data/config/document inventory and SHA-256 provenance manifest;
8. explicit AFTER-VPS verification procedures for every deferred external item.

## PRE-VPS verdict
If the above is satisfied:

> **🟢 PRE-VPS: PASS — ZIP VERIFIED — NEXT STEP: VPS**

Otherwise:

> **🔴 PRE-VPS: FAIL — FIX REQUIRED — VPS DEPLOYMENT MAT KARO**

## Important distinction
`release_preflight.py` is the **runtime/data readiness preflight** and may correctly return NOT READY in an offline ZIP because real decision-critical data has not yet been refreshed. That output is not the PRE-VPS engineering verdict. The PRE-VPS engineering gate must use this profile plus the frozen 55-section inspection constitution.

Likewise, a PRE-VPS PASS does not imply profitable strategy performance or live-trading safety. Those require subsequent paper/live and external gates.
