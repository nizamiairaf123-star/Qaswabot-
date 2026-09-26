# QASWA — Halal Algo Trading Bot (v6.0.3)

> **CANONICAL DATA-SOURCE POLICY:** `DATA_SOURCE_POLICY.md` — Dhan is mandatory for every trading-data and execution path; yfinance is company-information only and cannot provide OHLCV/price/volume to trading behavior.


> **CURRENT FROZEN INSPECTION AUTHORITY:** `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md` (framework v1.3-FROZEN) governs how the unchanged 55-section backbone is executed, classified, and judged. Freezing the framework does **not** certify the VPS/live environment. PRE-VPS engineering verification is a separate phase; AFTER-VPS external evidence remains mandatory.


> **CANONICAL GOVERNANCE — QASWA v6.0.3:** Product scope and intended behavior are defined by this document and the package code; inspection is governed by `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md`, using `docs/MASTER_ZERO_OMISSION_ZIP_INSPECTION_CONSTITUTION_55_SECTIONS.md` as the unchanged 55-section backbone. The authority chain is **55 Sections → Quality/Defect Gate → Evidence Classification → Release Verdict**. Framework freeze does not certify the VPS/live environment. The current phase is PRE-VPS engineering verification; AFTER-VPS external evidence remains mandatory.

Current phase: **PRE-VPS ENGINEERING VERIFICATION**. Real market metadata/provider, VPS, broker and live-runtime evidence are intentionally AFTER-VPS and must be verified there.



Long-only (CNC delivery) halal copy-trading bot — NSE cash-equity (EQ), Dhan broker,
Telegram interface. Per-stock optimization, walk-forward validation,
paper → staged live → subscriber copy-trading.

## Files Jo Sabse Pehle Padho

| File | Kiske liye | Kya |
|---|---|---|
| `FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md` | **Owner / auditor** | **Current frozen authority** — 55-section backbone ko kaise inspect, test, classify aur judge karna hai |
| `docs/MASTER_ZERO_OMISSION_ZIP_INSPECTION_CONSTITUTION_55_SECTIONS.md` | **Auditor** | Complete 55-section WHAT-to-inspect backbone; frozen standard iske upar HOW/evidence/verdict rules apply karta hai |
| `prd.md` | **Owner / product** | **MASTER PRD + ROADMAP** — poora product: vision, constitution (16 rules), decisions D1-D26, admin/subscriber flow, 23 domains, calculations, NFRs, tests, open items, roadmap |
| `SYSTEM_MASTER_MANIFEST.json` | **Naya AI/owner** | Single source of truth — 20 system domains + har ek ka verification + VPS checklist + lifecycle/revert map |
| `AI_ONBOARDING.md` | **Naya AI** | 5-minute read — rules + file map + test kaise chalana |
| `feature_sequence.json` | Developer | Canonical pipeline Stage 0-11 (chained files + methods + time-budget) |
| `VPS_DEPLOYMENT_GUIDE.md` | **Owner (VPS deploy)** | Server setup + first-run checklist |
| `UPDATE_HISTORY_FIX_LOG.md` | Owner | v5.0-v5.5 changes ka pura record |
| `test_sequence.py` | Developer | Top-to-bottom auto-test (Stage 0-11 + constitution + manifest cross-check) |
| `docs/PRE_VPS_GATE_PROFILE_v1.0.md` | **Owner / auditor** | PRE-VPS vs AFTER-VPS evidence boundary |
| `docs/PRE_VPS_FINAL_INSPECTION_REPORT_v1.0.md` | **Owner / auditor** | Final 55-section PRE-VPS engineering gate evidence |
| `AUDIT_INTEGRITY_MANIFEST_SHA256.json` | **Auditor** | SHA-256 integrity/provenance for shipped artifacts |

## Bot ke ANDAR guides (Telegram messages — downloadable NAHI, safety policy)

- Subscriber: `/start` → `/guide` (step-by-step, status ke hisaab se)
- Admin: `/adminguide` (poora runbook)

## Quick Start (VPS)

```bash
cp .env.example .env   # values bharo
./deploy.sh             # create venv + install pinned requirements
./start_bot.sh         # start bot using the prepared venv
sudo systemctl enable --now qaswa-bot@YOUR_USER.service   # 24/7 (install the template unit first)
```

## Tests

```bash
python3 scripts/pre_vps_engineering_preflight.py  # deterministic PRE-VPS engineering gate
python3 test_sequence.py          # Stage 0-11 sequence + constitution
# Tests run inside a throw-away temp copy of data/ (conftest.py + test_sequence.py
# sandbox) — production data/trading_bot.db / audit_log.txt are never touched.
python3 -m unittest discover      # unit tests
python3 -m unittest test_golden   # golden regression (known-good outputs)
```

## Owner Constitution (machine-enforced)

1. Sirf 4 owner constants: ₹3000 fee (₹3105 payment amount), ₹20,000 goal (benchmark only), 2% daily-loss cap, 10% max portfolio DD ceiling (owner personal limit)
2. Har number ka source documented (`PARAM_SOURCES`) — bina source ka number = test FAIL
3. Koi bhi phase/regime me trade sirf optimization-proven edge pe (t-test + WFE + paper)
4. Exit kabhi band nahi; sirf bot-dili positions exit hoti hain
5. Heavy kaam trading window ke bahar (pre-market/background + cache)

## AI HANDOFF — SINGLE INSPECTION COMMAND

Give the ZIP to the receiving AI and say only:

> **Inspection karo ZIP ka.**

This invokes the complete zero-omission independent re-verification defined by `docs/AI_INSPECTION_TRIGGER_AND_RESULT_CONTRACT_v1.0.md`, including full artifact inspection, 55-section execution, code/logic verification, executable-test evidence, external-check classification, CLOSED/PASS re-verification, and evidence-derived percentage reporting.
