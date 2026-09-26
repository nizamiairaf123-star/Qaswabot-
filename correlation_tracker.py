"""
correlation_tracker.py — Block correlated stocks + VIX/USDINR correlation
"""

import logging
import os
import pandas as pd
from capital_manager import get_active_trades
from config import AUDIT_LOG_FILE
from utils import append_log, now_ist

logger = logging.getLogger(__name__)


def is_correlated_with_active(symbol: str) -> bool:
    """
    Check if symbol is highly correlated with any active position.
    Returns True if correlated (block entry).
    Uses Dhan API — no yfinance.
    """
    from config import PARAMS
    active = get_active_trades()
    if not active:
        return False

    threshold = PARAMS["correlation_threshold"]

    try:
        from dhan_data import fetch_daily_data
        active_symbols = list(active.keys())

        # Fetch returns for new symbol
        df_new = fetch_daily_data(symbol, days=90)
        if df_new.empty:
            # Constitution Art. 3.4: cannot verify correlation without data
            # -- fail closed (block) rather than silently allow.
            append_log(AUDIT_LOG_FILE,
                       f"CORRELATION CHECK BLOCKED: {symbol} -- no price data available, failing closed")
            return True
        sym_returns = df_new["close"].pct_change().dropna()

        for active_sym in active_symbols:
            df_active = fetch_daily_data(active_sym, days=90)
            if df_active.empty:
                continue

            active_returns = df_active["close"].pct_change().dropna()

            # Align on common index
            combined = pd.concat([sym_returns, active_returns],
                                  axis=1, join="inner").dropna()
            if len(combined) < 20:
                continue

            corr = combined.iloc[:, 0].corr(combined.iloc[:, 1])
            if corr >= threshold:
                append_log(AUDIT_LOG_FILE,
                           f"CORRELATION BLOCK: {symbol} corr={corr:.2f} with {active_sym}")
                return True
        return False
    except Exception as e:
        # Constitution Art. 3.4: fail closed on any error -- block rather
        # than silently allow an unverified-risk entry.
        append_log(AUDIT_LOG_FILE,
                   f"CORRELATION CHECK ERROR (fail-closed, blocking): {symbol}: {e}")
        return True


# ─────────────────────────────────────────────
# VIX + USDINR CORRELATION
# Block entries when stock is positively correlated with rising VIX
# or negatively correlated with rising USDINR
# Source: Cross-asset correlation — institutional risk management
# ─────────────────────────────────────────────

def _fetch_index_data(security_id: str, exchange_segment: str,
                      instrument_type: str, days: int = 90) -> pd.DataFrame:
    """Fetch daily data for VIX/USDINR by security ID."""
    if not security_id:
        return pd.DataFrame()
    try:
        from dhan_client import create_dhan_client
        from config import TOKEN_FILE
        from utils import load_json
        token_data = load_json(TOKEN_FILE, {})
        if not token_data:
            return pd.DataFrame()
        dhan = create_dhan_client(token_data["client_id"], token_data["access_token"])

        from datetime import timedelta
        # [PHD-FIX Section-43] was datetime.today() (naive, server-local
        # timezone — not guaranteed IST); now uses the project's own
        # single-source IST time convention, same as everywhere else.
        end = now_ist()
        start = end - timedelta(days=days)
        result = dhan.historical_daily_data(
            security_id=security_id,
            exchange_segment=exchange_segment,
            instrument_type=instrument_type,
            from_date=start.strftime("%Y-%m-%d"),
            to_date=end.strftime("%Y-%m-%d"),
        )
        if not result or result.get("status") != "success":
            return pd.DataFrame()

        df = pd.DataFrame(result.get("data", []))
        if df.empty or "close" not in df.columns:
            return pd.DataFrame()
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        return df.dropna(subset=["close"]).sort_index()
    except (TypeError, ValueError, KeyError) as e:
        logger.debug(f"_clean_price_data: Data cleaning failed: {type(e).__name__}: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# USDINR AUTO-DISCOVERY
# Finds current month's USDINR futures from Dhan scrip master
# ─────────────────────────────────────────────

_usdinr_cache = {"id": None, "updated": None}

def _discover_usdinr_security_id() -> tuple:
    """Auto-discover current month USDINR futures from Dhan scrip master.
    Returns (security_id, exchange_segment, instrument_type) or (None, None, None).
    """
    from utils import now_ist
    now = now_ist().replace(tzinfo=None)
    
    # Cache for 1 day
    if _usdinr_cache["id"] and _usdinr_cache["updated"]:
        updated = _usdinr_cache["updated"]
        if (now - updated).total_seconds() < 86400:
            return _usdinr_cache["id"]
    
    try:
        from dhan_client import create_dhan_client
        from config import TOKEN_FILE
        from utils import load_json
        import pandas as pd
        token_data = load_json(TOKEN_FILE, {})
        if not token_data:
            return (None, None, None)
        dhan = create_dhan_client(token_data["client_id"], token_data["access_token"])
        df = dhan.fetch_security_list("compact")
        
        # Month abbreviations for current and next month
        months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
        curr_month = months[now.month - 1]
        next_month = months[now.month % 12]
        year_str = str(now.year)
        
        # Find current or next month USDINR futures on NSE
        for search_month in [curr_month, next_month]:
            matches = df[df.apply(lambda r: 
                'USDINR' in str(r.values).upper() and 
                'FUTCUR' in str(r.values).upper() and 
                search_month in str(r.values) and 
                year_str in str(r.values) and
                'NSE' in str(r.values).upper(), 
                axis=1)]
            
            if len(matches) > 0:
                row = matches.iloc[0]
                sid = str(row.get('SEM_SMST_SECURITY_ID', ''))
                result = (sid, "NSE_CURRENCY", "CURRENCY")
                _usdinr_cache["id"] = result
                _usdinr_cache["updated"] = now
                append_log(AUDIT_LOG_FILE, 
                           f"USDINR AUTO-DISCOVERED: id={sid} month={search_month}")
                return result
        
        # Fallback: try BSE
        for search_month in [curr_month, next_month]:
            matches = df[df.apply(lambda r: 
                'USDINR' in str(r.values).upper() and 
                'FUTCUR' in str(r.values).upper() and 
                search_month in str(r.values) and 
                year_str in str(r.values), 
                axis=1)]
            
            if len(matches) > 0:
                row = matches.iloc[0]
                sid = str(row.get('SEM_SMST_SECURITY_ID', ''))
                seg = "BSE_CURRENCY" if str(row.get('SEM_EXM_EXCH_ID','')) == 'BSE' else "NSE_CURRENCY"
                result = (sid, seg, "CURRENCY")
                _usdinr_cache["id"] = result
                _usdinr_cache["updated"] = now
                append_log(AUDIT_LOG_FILE, 
                           f"USDINR AUTO-DISCOVERED (BSE): id={sid} month={search_month}")
                return result
        
        return (None, None, None)
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"USDINR DISCOVERY ERROR: {e}")
        return (None, None, None)


def check_vix_correlation(symbol: str) -> dict:
    """
    Check if stock is positively correlated with VIX (bad — stock falls when VIX rises).
    Returns: {correlated: bool, corr: float, reason: str}
    """
    from config import PARAMS
    vix_id = os.getenv("INDIA_VIX_SECURITY_ID", "")
    if not vix_id:
        return {"correlated": False, "corr": 0, "reason": "VIX not configured"}

    threshold = PARAMS["vix_correlation_threshold"]

    try:
        from dhan_data import fetch_daily_data
        df_stock = fetch_daily_data(symbol, days=90)
        df_vix = _fetch_index_data(vix_id, "IDX_I", "INDEX", days=90)

        if df_stock.empty or df_vix.empty:
            # Constitution Art. 3.4: cannot verify -- fail closed (block).
            append_log(AUDIT_LOG_FILE,
                       f"VIX CORRELATION CHECK BLOCKED: {symbol} -- data unavailable, failing closed")
            return {"correlated": True, "corr": 0, "reason": "Data unavailable -- fail closed"}

        stock_ret = df_stock["close"].pct_change().dropna()
        vix_ret = df_vix["close"].pct_change().dropna()

        combined = pd.concat([stock_ret, vix_ret], axis=1, join="inner").dropna()
        if len(combined) < 20:
            return {"correlated": True, "corr": 0, "reason": "Insufficient overlap -- fail closed"}

        corr = combined.iloc[:, 0].corr(combined.iloc[:, 1])

        # Positive VIX correlation = stock rises with VIX = unusual for equities
        # We block if correlation reaches at least the "moderate" convention
        # boundary (stock moves WITH fear, atypical for equities).
        if corr > threshold:
            return {"correlated": True, "corr": round(corr, 2),
                    "reason": f"Stock corr={corr:.2f} with VIX — risk-on/fear mismatch"}

        return {"correlated": False, "corr": round(corr, 2), "reason": "VIX correlation OK"}
    except Exception as e:
        # Constitution Art. 3.4: fail closed on error.
        append_log(AUDIT_LOG_FILE, f"VIX CORRELATION CHECK ERROR (fail-closed, blocking): {symbol}: {e}")
        return {"correlated": True, "corr": 0, "reason": f"VIX check error (fail closed): {e}"}


def check_usdinr_correlation(symbol: str) -> dict:
    """
    Check if stock is negatively correlated with USDINR (bad — stock falls when rupee weakens).
    Auto-discovers current USDINR futures contract.
    Returns: {correlated: bool, corr: float, reason: str}
    """
    from config import PARAMS
    threshold = PARAMS["usdinr_correlation_threshold"]

    # Auto-discover USDINR contract
    usdinr_id, usdinr_seg, usdinr_type = _discover_usdinr_security_id()
    if not usdinr_id:
        # Fallback to .env if auto-discovery fails
        usdinr_id = os.getenv("USDINR_SECURITY_ID", "")
        usdinr_seg = os.getenv("USDINR_EXCHANGE_SEGMENT", "NSE_CURRENCY")
        usdinr_type = os.getenv("USDINR_INSTRUMENT_TYPE", "CURRENCY")
        if not usdinr_id:
            return {"correlated": False, "corr": 0, "reason": "USDINR not configured"}

    try:
        from dhan_data import fetch_daily_data
        df_stock = fetch_daily_data(symbol, days=90)
        df_usdinr = _fetch_index_data(usdinr_id, usdinr_seg, usdinr_type, days=90)

        if df_stock.empty or df_usdinr.empty:
            # Constitution Art. 3.4: cannot verify -- fail closed (block).
            append_log(AUDIT_LOG_FILE,
                       f"USDINR CORRELATION CHECK BLOCKED: {symbol} -- data unavailable, failing closed")
            return {"correlated": True, "corr": 0, "reason": "Data unavailable -- fail closed"}

        stock_ret = df_stock["close"].pct_change().dropna()
        usdinr_ret = df_usdinr["close"].pct_change().dropna()

        combined = pd.concat([stock_ret, usdinr_ret], axis=1, join="inner").dropna()
        if len(combined) < 20:
            return {"correlated": True, "corr": 0, "reason": "Insufficient overlap -- fail closed"}

        corr = combined.iloc[:, 0].corr(combined.iloc[:, 1])

        # Negative USDINR correlation = stock falls when rupee weakens
        if corr < threshold:
            return {"correlated": True, "corr": round(corr, 2),
                    "reason": f"Stock corr={corr:.2f} with USDINR — FX risk"}

        return {"correlated": False, "corr": round(corr, 2), "reason": "USDINR correlation OK"}
    except Exception as e:
        # Constitution Art. 3.4: fail closed on error.
        append_log(AUDIT_LOG_FILE, f"USDINR CORRELATION CHECK ERROR (fail-closed, blocking): {symbol}: {e}")
        return {"correlated": True, "corr": 0, "reason": f"USDINR check error (fail closed): {e}"}
