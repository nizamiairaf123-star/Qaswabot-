#!/usr/bin/env python3
"""QASWA release preflight: fail closed on missing decision-critical artifacts/data."""
from pathlib import Path
import json
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

def run_preflight():
    errors = []

    def need(path):
        if not path.exists():
            errors.append(f"missing: {path.relative_to(ROOT)}")

    need(ROOT / "requirements.txt")
    need(ROOT / "qaswa-bot@.service")
    need(ROOT / "deploy.sh")
    need(ROOT / "start_bot.sh")
    need(DATA / "CUSTOM_UNIVERSE_FINAL.csv")
    need(DATA / "custom_universe_state.json")

    try:
        df = pd.read_csv(DATA / "CUSTOM_UNIVERSE_FINAL.csv", low_memory=False)
        required = {"symbol", "security_id", "series", "exchange", "core_business_halal", "non_muslim_board", "sector", "industry", "market_cap", "turnover_liquid_ok", "atvr_pct", "frequency_of_trading_pct"}
        errors += [f"missing column: {c}" for c in sorted(required - set(df.columns))]
        if "exchange" in df:
            non_nse_mask = df["exchange"].astype(str).str.upper() != "NSE"
            if non_nse_mask.any():
                errors.append(f"non-NSE row count: {non_nse_mask.sum()}")
        if "series" in df:
            non_eq_mask = df["series"].astype(str).str.upper() != "EQ"
            if non_eq_mask.any():
                errors.append(f"non-EQ row count: {non_eq_mask.sum()}")
        for c in ["sector", "industry", "market_cap", "turnover_liquid_ok", "atvr_pct", "frequency_of_trading_pct"]:
            if c in df and df[c].isna().any():
                errors.append(f"decision data incomplete: {c} has {int(df[c].isna().sum())} unknown rows")
    except Exception as e:
        errors.append(f"CSV validation error: {type(e).__name__}: {e}")

    try:
        state = json.loads((DATA / "custom_universe_state.json").read_text())
        pause = state.get("BOARD_DATA_STALE_PAUSE")
        if pause not in (True, False):
            errors.append("invalid BOARD_DATA_STALE_PAUSE state")
        if pause is False and not state.get("last_successful_update"):
            errors.append("BOARD_DATA_STALE_PAUSE=False without successful refresh timestamp")
    except Exception as e:
        errors.append(f"state validation error: {type(e).__name__}: {e}")

    return errors

def main():
    errors = run_preflight()
    if errors:
        print("NOT READY")
        for e in errors:
            print("-", e)
        sys.exit(2)
    print("READY: release preflight passed")

if __name__ == "__main__":
    main()
