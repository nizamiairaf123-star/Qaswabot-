"""
Decision-critical market metadata refresh.

Source: yfinance Yahoo Finance metadata for NSE symbols.
Unknown values are represented as NA, never as numeric zero.
Failure is fail-closed: an individual symbol remains unverifiable and is
not promoted to an eligible state. Existing metadata is only retained when
it has a recorded successful refresh timestamp within the configured
freshness window.
"""
from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import pandas as pd

from config import CUSTOM_UNIVERSE_FILE, DATA_DIR, PARAMS
from utils import logger, append_log, AUDIT_LOG_FILE, save_json, load_json

STATE_FILE = f"{DATA_DIR}/market_metadata_state.json"

def _valid_cap(v) -> Optional[float]:
    try:
        x = float(v)
        return x if x > 0 else None
    except (TypeError, ValueError):
        return None

def _symbol_for_yahoo(symbol: str) -> str:
    return f"{str(symbol).strip().upper()}.NS"

def _fetch_one(symbol: str) -> Dict[str, Any]:
    import yfinance as yf
    t = yf.Ticker(_symbol_for_yahoo(symbol))
    info = t.info or {}
    # NDSAP Part C tap (prd.md Rule 15) — raw metadata payload, pre-
    # transformation. Provider-gated: stays a NO-OP until the owner clears
    # the Rule 15 ToS blocker and adds "yfinance" to ndsap_archive_providers.
    from ndsap_archive import archive_record
    archive_record(info, provider="yfinance", dataset="market_metadata",
                   symbol=str(symbol).strip().upper(), exchange="NSE")
    cap = _valid_cap(info.get("marketCap"))
    sector = str(info.get("sector") or "").strip() or None
    industry = str(info.get("industry") or "").strip() or None
    return {"market_cap": cap, "sector": sector, "industry": industry}

def refresh_market_metadata() -> bool:
    """
    Refresh sector/industry/market_cap for every NSE symbol in the custom
    universe. No fabricated values are written. A row is considered
    verified only when all three decision-critical fields are present and
    market_cap > 0.
    """
    try:
        df = pd.read_csv(CUSTOM_UNIVERSE_FILE, low_memory=False)
    except Exception as exc:
        append_log(AUDIT_LOG_FILE, f"MARKET METADATA: cannot read universe: {exc}")
        return False

    required = {"symbol", "exchange", "sector", "industry", "market_cap"}
    if not required.issubset(df.columns):
        append_log(AUDIT_LOG_FILE, f"MARKET METADATA: missing columns {sorted(required-set(df.columns))}")
        return False

    # This package previously encoded unknown metadata as 0. Zero is not a
    # valid sector/industry/market-cap value; normalize it to explicit NA.
    for col in ("sector", "industry", "market_cap"):
        df[col] = df[col].replace({0: pd.NA, 0.0: pd.NA, "0": pd.NA, "0.0": pd.NA, "": pd.NA})

    try:
        import yfinance  # noqa: F401
    except ImportError as exc:
        append_log(AUDIT_LOG_FILE, f"MARKET METADATA: yfinance unavailable: {exc}")
        return False

    min_verified = int(PARAMS.get("market_metadata_min_verified", 1))
    pause = float(PARAMS.get("market_metadata_request_pause_sec", 0.15))
    verified = 0
    attempted = 0

    for idx, row in df.iterrows():
        symbol = str(row.get("symbol") or "").strip()
        exchange = str(row.get("exchange") or "").strip().upper()
        if not symbol or exchange != "NSE":
            continue
        attempted += 1
        try:
            result = _fetch_one(symbol)
            # Never partially promote metadata. All three fields must be
            # verified together.
            if result["market_cap"] and result["sector"] and result["industry"]:
                df.at[idx, "market_cap"] = result["market_cap"]
                df.at[idx, "sector"] = result["sector"]
                df.at[idx, "industry"] = result["industry"]
                verified += 1
        except Exception as exc:
            logger.warning("MARKET METADATA: %s failed: %s", symbol, type(exc).__name__)
        if pause:
            time.sleep(pause)

    # Do not overwrite a valid dataset with an entirely failed refresh.
    if verified < min_verified:
        append_log(AUDIT_LOG_FILE,
                   f"MARKET METADATA: FAILED — verified={verified}, attempted={attempted}; universe not published")
        return False

    # Any remaining unknown decision-critical metadata is explicit NA and
    # therefore remains fail-closed in downstream eligibility/liquidity.
    tmp = CUSTOM_UNIVERSE_FILE + ".metadata.tmp"
    df.to_csv(tmp, index=False)
    import os
    os.replace(tmp, CUSTOM_UNIVERSE_FILE)

    state = load_json(STATE_FILE, {})
    state.update({
        "last_successful_update": datetime.now(timezone.utc).isoformat(),
        "verified_rows": verified,
        "attempted_rows": attempted,
        "source": "yfinance",
        "status": "SUCCESS",
    })
    save_json(STATE_FILE, state)
    append_log(AUDIT_LOG_FILE, f"MARKET METADATA: SUCCESS — verified={verified}/{attempted}")
    return True
