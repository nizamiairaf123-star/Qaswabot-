"""
dhan_data.py — Dhan Historical + Intraday Data API wrapper
DhanHQ v2.2.0 compatible
Uses token saved by Telegram /settoken in data/dhan_token.json
"""

import logging
import pandas as pd
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

from config import AUDIT_LOG_FILE, TOKEN_FILE
from utils import load_json, append_log, now_ist


def get_exchange_segment(symbol: str) -> str:
    """Return NSE_EQ/BSE_EQ from the single tradable universe CSV."""
    try:
        from config import CUSTOM_UNIVERSE_FILE
        df = pd.read_csv(CUSTOM_UNIVERSE_FILE)
        row = df[df["symbol"].astype(str).str.upper() == str(symbol).upper()]
        if not row.empty:
            exchange = str(row["exchange"].values[0]).upper()
            if exchange == "BSE":
                return "BSE_EQ"
    except (KeyError, TypeError, ValueError, IndexError) as e:
        logger.debug(f"_get_exchange_segment: Exchange lookup failed for {symbol}: {type(e).__name__}: {e}")
    return "NSE_EQ"


def get_security_id(symbol: str) -> str:
    """Get Dhan security_id from the single tradable universe CSV."""
    try:
        from config import CUSTOM_UNIVERSE_FILE
        df = pd.read_csv(CUSTOM_UNIVERSE_FILE)
        row = df[df["symbol"].astype(str).str.upper() == str(symbol).upper()]
        if not row.empty:
            return str(int(float(row["security_id"].values[0])))
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"SECURITY_ID ERROR {symbol}: {e}")
    return None


def _get_dhan():
    """Lazy Dhan client; broker SDK loads only when a real Dhan call is made."""
    from dhan_client import create_dhan_client
    token_data = load_json(TOKEN_FILE, {})
    if not token_data:
        raise ValueError("Dhan token not found. Run /settoken CLIENT_ID ACCESS_TOKEN first.")

    return create_dhan_client(
        token_data["client_id"],
        token_data["access_token"]
    )



def _is_rate_limit_response(result) -> bool:
    try:
        if not isinstance(result, dict):
            return False
        remarks = result.get("remarks", {})
        if isinstance(remarks, dict):
            return remarks.get("error_code") == "DH-904"
        return "rate" in str(remarks).lower()
    except (TypeError, ValueError, AttributeError) as e:
        logger.debug(f"_is_rate_limit_error: Check failed: {type(e).__name__}: {e}")
        return False


def _call_with_retry(api_func, max_retries: int = 3, base_sleep: float = 1.25, **kwargs):
    """
    Dhan rate-limit safe wrapper.
    Retries DH-904 with exponential backoff + jitter.
    """
    import random
    last = None
    for attempt in range(max_retries):
        result = api_func(**kwargs)
        last = result
        if not _is_rate_limit_response(result):
            return result

        # Exponential backoff with jitter
        sleep_for = base_sleep * (2 ** attempt) + random.uniform(0, 1)
        append_log(AUDIT_LOG_FILE, f"DHAN RATE LIMIT: retry {attempt+1}/{max_retries} sleeping {sleep_for:.1f}s")
        time.sleep(sleep_for)

    return last

def _standardize(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize Dhan response to OHLCV with IST datetime index."""
    if df is None or df.empty:
        return pd.DataFrame()

    required = ["open", "high", "low", "close", "volume"]

    for col in required:
        if col not in df.columns:
            return pd.DataFrame()

    df[required] = df[required].apply(pd.to_numeric, errors="coerce")

    if "timestamp" in df.columns:
        try:
            dt = pd.to_datetime(df["timestamp"], unit="s", utc=True)
            df.index = dt.dt.tz_convert("Asia/Kolkata")
            df = df.drop(columns=["timestamp"], errors="ignore")
        except (TypeError, ValueError, KeyError) as e:
            logger.debug(f"_parse_ohlcv: Timestamp conversion failed: {type(e).__name__}: {e}")

    return df[required].dropna().sort_index()


# ═════════════════════════════════════════════════════════════════════════
# v5.0 — DAILY CACHE + DATA SANITY (Tier 2: optimizer 10x fast, bad data block)
# ═════════════════════════════════════════════════════════════════════════
DAILY_CACHE_DIR = "data/daily_cache"


def _sanity_check_df(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    v5.0 data sanity: zero/negative close drop; absurd gap (>25% ek din me)
    warn (corporate action adjust nahi hua ho sakta hai — log only, block nahi).
    """
    if df is None or df.empty:
        return df
    try:
        df = df[df["close"] > 0]
        closes = df["close"].astype(float)
        gaps = (closes.pct_change().abs() * 100.0).dropna()
        bad = gaps[gaps > 25.0]
        if len(bad) > 0:
            append_log(AUDIT_LOG_FILE,
                       f"DATA SANITY: {symbol} has {len(bad)} day(s) with >25% single-day move — "
                       f"corporate action adjustment verify karo")
    except (KeyError, TypeError, ValueError) as e:
        append_log(AUDIT_LOG_FILE, f"DATA SANITY ERROR {symbol}: {type(e).__name__}: {e}")
    return df


def _cache_path(symbol: str) -> str:
    import os
    os.makedirs(DAILY_CACHE_DIR, exist_ok=True)
    return os.path.join(DAILY_CACHE_DIR, f"{symbol.upper()}.csv")


def _cache_fresh(symbol: str, max_stale_days: int) -> bool:
    import os
    from datetime import date
    path = _cache_path(symbol)
    if not os.path.exists(path):
        return False
    try:
        mdate = date.fromtimestamp(os.path.getmtime(path))
        return (date.today() - mdate).days < max(1, max_stale_days)
    except (OSError, ValueError):
        return False


def fetch_daily_data(symbol: str, days: int = 7300) -> pd.DataFrame:
    """Fetch daily OHLCV data from Dhan (v5.0: local cache + sanity). Returns whatever Dhan has."""
    from config import PARAMS
    try:
        use_cache = bool(PARAMS.get("enable_daily_cache", True))
        stale_days = int(PARAMS.get("daily_cache_stale_days", 1))
    except (TypeError, ValueError):
        use_cache, stale_days = True, 1

    # Cache hit (current trading day ka data pehle se hai) → no network
    if use_cache and _cache_fresh(symbol, stale_days):
        try:
            cached = pd.read_csv(_cache_path(symbol), parse_dates=["timestamp"])
            cached = cached.set_index("timestamp").sort_index()
            if not cached.empty and "close" in cached.columns:
                return cached
        except (FileNotFoundError, OSError, ValueError, KeyError) as e:
            append_log(AUDIT_LOG_FILE, f"DATA CACHE READ FAILED {symbol}: {type(e).__name__}: {e}")

    security_id = get_security_id(symbol)
    exchange_seg = get_exchange_segment(symbol)

    if not security_id:
        append_log(AUDIT_LOG_FILE, f"DATA: {symbol} security_id not found")
        return pd.DataFrame()

    # [PHD-FIX Section-43] was datetime.today() (naive, server-local) — now
    # uses the project's own single-source IST time convention.
    end_date = now_ist()
    start_date = end_date - timedelta(days=days)

    try:
        dhan = _get_dhan()
        result = _call_with_retry(
            dhan.historical_daily_data,
            security_id=security_id,
            exchange_segment=exchange_seg,
            instrument_type="EQUITY",
            from_date=start_date.strftime("%Y-%m-%d"),
            to_date=end_date.strftime("%Y-%m-%d"),
        )

        if not result or result.get("status") != "success":
            append_log(AUDIT_LOG_FILE, f"DATA: {symbol} daily failed: {result}")
            return pd.DataFrame()

        # NDSAP Part C tap (prd.md Rule 15) — archive the raw payload BEFORE
        # any transformation. Read-only, fail-soft; never alters this path.
        from ndsap_archive import archive_record
        archive_record(result, provider="dhan", dataset="historical_daily",
                       symbol=symbol, exchange=exchange_seg,
                       security_id=security_id)

        df = pd.DataFrame(result["data"])
        df = _standardize(df)
        df = _sanity_check_df(df, symbol)

        if not df.empty:
            append_log(AUDIT_LOG_FILE, f"DATA: {symbol} daily {len(df)} candles")
            if use_cache:
                try:
                    out = df.copy()
                    out = out.reset_index().rename(columns={"index": "timestamp"})
                    if "timestamp" not in out.columns and "date" in out.columns:
                        out = out.rename(columns={"date": "timestamp"})
                    out.to_csv(_cache_path(symbol), index=False)
                except (OSError, KeyError, ValueError) as e:
                    append_log(AUDIT_LOG_FILE, f"DATA CACHE WRITE FAILED {symbol}: {type(e).__name__}: {e}")

        return df

    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"DATA ERROR {symbol}: {e}")
        return pd.DataFrame()


def fetch_intraday_data(symbol: str, interval: str = "1min", days: int = 1825) -> pd.DataFrame:
    """
    Fetch intraday minute data from Dhan.
    Dhan gives up to 5 years intraday, 90 days per API call.
    Auto-chunks into 90-day windows. Returns whatever Dhan has.
    """
    security_id = get_security_id(symbol)
    exchange_seg = get_exchange_segment(symbol)

    if not security_id:
        append_log(AUDIT_LOG_FILE, f"INTRADAY: {symbol} security_id not found")
        return pd.DataFrame()

    # Dhan max 90 days per intraday call — chunk it
    CHUNK_DAYS = 90
    # [PHD-FIX Section-43] was datetime.today() (naive, server-local) — now
    # uses the project's own single-source IST time convention.
    end_date = now_ist()
    start_date = end_date - timedelta(days=days)

    all_dfs = []
    chunk_end = end_date

    while chunk_end > start_date:
        chunk_start = max(start_date, chunk_end - timedelta(days=CHUNK_DAYS))

        try:
            dhan = _get_dhan()
            result = _call_with_retry(
                dhan.intraday_minute_data,
                security_id=security_id,
                exchange_segment=exchange_seg,
                instrument_type="EQUITY",
                from_date=chunk_start.strftime("%Y-%m-%d"),
                to_date=chunk_end.strftime("%Y-%m-%d"),
            )

            if result and result.get("status") == "success" and result.get("data"):
                # NDSAP Part C tap — raw chunk payload, pre-transformation.
                from ndsap_archive import archive_record
                archive_record(result, provider="dhan", dataset="intraday_minute",
                               symbol=symbol, exchange=exchange_seg,
                               security_id=security_id)
                chunk_df = pd.DataFrame(result["data"])
                chunk_df = _standardize(chunk_df)
                if not chunk_df.empty:
                    all_dfs.append(chunk_df)
        except Exception as e:
            append_log(AUDIT_LOG_FILE, f"INTRADAY CHUNK ERROR {symbol}: {e}")

        chunk_end = chunk_start - timedelta(days=1)  # Avoid overlap
        time.sleep(0.2)  # Rate limit courtesy

    if not all_dfs:
        append_log(AUDIT_LOG_FILE, f"INTRADAY: {symbol} no data for {days} days")
        return pd.DataFrame()

    # Combine all chunks, remove duplicates, sort
    combined = pd.concat(all_dfs).sort_index()
    combined = combined[~combined.index.duplicated(keep='first')]

    append_log(AUDIT_LOG_FILE, f"INTRADAY: {symbol} {interval} {len(combined)} candles ({days} days, {len(all_dfs)} chunks)")
    return combined


def fetch_data(symbol: str, timeframe: str = "1d", bars: int = 500) -> pd.DataFrame:
    """Smart fetch wrapper. Returns whatever Dhan gives — no cap."""
    if timeframe in ("1d", "D", "daily"):
        df = fetch_daily_data(symbol, days=7300)
    else:
        df = fetch_intraday_data(symbol, interval=timeframe, days=1825)

    if df.empty:
        return df

    return df.tail(bars) if len(df) > bars else df


def get_live_price(symbol: str) -> float:
    """Get live/last traded price from Dhan OHLC API.

    Raises on any failure to fetch/parse a price -- callers MUST treat a
    failed fetch as 'cannot verify price', never silently as a real price
    of 0.0 (a genuine API error and a fabricated zero price are otherwise
    indistinguishable to any downstream sizing/exit logic that reads this
    return value). No caller currently uses this function -- live callers
    derive current_price from candle data via _fetch_candles(), which
    already returns None on failure and is guarded at every call site --
    but this was still a fail-open landmine for any future caller.
    """
    security_id = get_security_id(symbol)
    exchange_seg = get_exchange_segment(symbol)

    if not security_id:
        raise ValueError(f"get_live_price: no security_id found for {symbol}")

    dhan = _get_dhan()
    result = dhan.ohlc_data(
        securities={exchange_seg: [int(security_id)]}
    )

    # NDSAP Part C tap — raw live OHLC payload, pre-transformation.
    if result:
        from ndsap_archive import archive_record
        archive_record(result, provider="dhan", dataset="ohlc_live",
                       symbol=symbol, exchange=exchange_seg,
                       security_id=security_id)

    if result and isinstance(result, dict):
        data = result.get("data", {})
        for val in data.values():
            price = float(val.get("last_price", 0))
            if price > 0:
                return price
            raise ValueError(f"get_live_price: Dhan returned non-positive last_price for {symbol}")

    raise RuntimeError(f"get_live_price: Dhan OHLC response missing/invalid for {symbol}: {result!r}")
