#!/usr/bin/env python3
"""Refresh decision-critical market metadata/liquidity fields.

Fail-closed design: a refresh only replaces the live universe when every required
field is populated and validated. Network/API failures leave the existing
universe untouched and keep BOARD_DATA_STALE_PAUSE=True.
"""
from pathlib import Path
import json
from datetime import datetime, timezone
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
UNIVERSE = DATA / "CUSTOM_UNIVERSE_FINAL.csv"
STATE = DATA / "custom_universe_state.json"
REQUIRED = ["sector", "industry", "market_cap", "turnover_liquid_ok", "atvr_pct", "frequency_of_trading_pct"]


def fail(msg):
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    state["BOARD_DATA_STALE_PAUSE"] = True
    state["last_attempt"] = datetime.now(timezone.utc).isoformat()
    state["last_error"] = msg
    STATE.write_text(json.dumps(state, indent=2) + "\n")
    raise SystemExit(msg)


def validate(df):
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        fail("missing decision-critical columns: " + ", ".join(missing))
    for c in REQUIRED:
        if df[c].isna().any():
            fail(f"refresh incomplete: {c} has {int(df[c].isna().sum())} unknown rows")
    if (df["market_cap"] <= 0).any():
        fail("refresh invalid: market_cap contains non-positive values")
    for c in ["atvr_pct", "frequency_of_trading_pct"]:
        if (~pd.to_numeric(df[c], errors="coerce").notna()).any():
            fail(f"refresh invalid: {c} contains non-numeric values")
    if not df["turnover_liquid_ok"].astype(bool).isin([True, False]).all():
        fail("refresh invalid: turnover_liquid_ok contains invalid boolean values")


def main():
    # This package deliberately does not fabricate values. The actual provider
    # adapter is selected/configured by deployment. Refuse to mutate until a
    # provider implementation is available rather than writing placeholders.
    provider = (ROOT / "data" / "decision_data_provider.json")
    if not provider.exists():
        fail("no configured decision-data provider; refusing to fabricate market metadata/liquidity")
    cfg = json.loads(provider.read_text())
    if not cfg.get("provider"):
        fail("decision-data provider is not configured")
    # Provider adapters are intentionally external to this package; deployment
    # must materialize a complete candidate CSV at the configured path.
    candidate = ROOT / cfg.get("candidate_csv", "data/CUSTOM_UNIVERSE_REFRESHED.csv")
    if not candidate.exists():
        fail(f"configured provider candidate not found: {candidate.relative_to(ROOT)}")
    df = pd.read_csv(candidate, low_memory=False)
    validate(df)
    # Atomic replacement: keep a backup and only clear the pause after validation.
    backup = UNIVERSE.with_suffix(".csv.pre_refresh")
    if UNIVERSE.exists():
        UNIVERSE.replace(backup)
    df.to_csv(UNIVERSE, index=False)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    state.update({"last_successful_update": datetime.now(timezone.utc).isoformat(),
                  "last_attempt": datetime.now(timezone.utc).isoformat(),
                  "BOARD_DATA_STALE_PAUSE": False,
                  "last_error": None,
                  "total_symbols": int(len(df))})
    STATE.write_text(json.dumps(state, indent=2) + "\n")
    print(f"REFRESHED: {len(df)} rows validated and committed")

    # [ASM/GSM PRE-SCREEN — OWNER DECISION 2026-09-05] NSE surveillance list
    # refresh (fail-closed: fetch fail → list stale rehti hai → new entries
    # blocked; koi fabricated list NAHI). Admin manual placement bhi possible:
    #   python3 -c "from asm_gsm_screen import refresh_asm_gsm_list as r; r(manual_csv='asm.csv')"
    import sys
    sys.path.insert(0, str(ROOT))
    try:
        from asm_gsm_screen import refresh_asm_gsm_list
        n = refresh_asm_gsm_list(root=ROOT)
        print(f"ASM/GSM REFRESHED: {n} surveillance symbols committed")
    except Exception as e:
        print(f"ASM/GSM REFRESH FAILED: {e} — new entries stay fail-closed blocked until refresh succeeds")
        raise SystemExit(1)

if __name__ == "__main__":
    main()
