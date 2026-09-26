"""
market_regime.py — FIX-04 Hybrid Market Regime Detection

Final regime = Nifty HMM (Hamilton 1989) + Sector strength + VIX + USDINR
multi-factor fusion (Dempster-Shafer evidence combination).

Returns:
    BULL / SIDEWAYS / BEAR / RECOVERY

Principle:
- Nifty tells market weather.
- Sector / VIX / USDINR add independent macro evidence.
- If data missing, default to SIDEWAYS (cautious).
"""

import logging
import os
import math
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

from utils import load_json, save_json, now_ist, append_log
from config import (
    AUDIT_LOG_FILE,
    TOKEN_FILE,
    DATA_DIR,
    PARAMS,
)
from broker import _create_dhan_client


MARKET_REGIME_FILE = f"{DATA_DIR}/market_regime.json"

# Dhan IDs can be overridden in .env after verifying from scrip master
NIFTY_SECURITY_ID = os.getenv("NIFTY_SECURITY_ID", "13")
NIFTY_EXCHANGE_SEGMENT = os.getenv("NIFTY_EXCHANGE_SEGMENT", "IDX_I")
NIFTY_INSTRUMENT_TYPE = os.getenv("NIFTY_INSTRUMENT_TYPE", "INDEX")

INDIA_VIX_SECURITY_ID = os.getenv("INDIA_VIX_SECURITY_ID", "21")
USDINR_SECURITY_ID = os.getenv("USDINR_SECURITY_ID", "")  # Auto-discovered at runtime

REGIME_CACHE_HOURS = int(os.getenv("REGIME_CACHE_HOURS", "6"))


def _safe_float(x, default=0.0) -> float:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (TypeError, ValueError) as e:
        logger.debug(f"_safe_float: Conversion failed: {type(e).__name__}: {e}")
        return default


def _get_dhan():
    token_data = load_json(TOKEN_FILE, {})
    if not token_data:
        raise ValueError("Dhan token missing. Run /settoken first.")
    return _create_dhan_client(token_data["client_id"], token_data["access_token"])


def _standardize_ohlcv(data) -> pd.DataFrame:
    df = pd.DataFrame(data or [])
    if df.empty or "close" not in df.columns:
        return pd.DataFrame()

    for c in ["open", "high", "low", "close", "volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    if "timestamp" in df.columns:
        try:
            dt = pd.to_datetime(df["timestamp"], unit="s", utc=True)
            df.index = dt.dt.tz_convert("Asia/Kolkata")
            df = df.drop(columns=["timestamp"], errors="ignore")
        except (TypeError, ValueError, KeyError) as e:
            logger.warning(f"_fetch_and_parse: Timestamp conversion failed: {type(e).__name__}: {e}")

    return df.dropna(subset=["close"]).sort_index()


def _fetch_dhan_daily_by_id(security_id: str, exchange_segment: str, instrument_type: str, days: int = 320) -> pd.DataFrame:
    if not security_id:
        return pd.DataFrame()

    try:
        dhan = _get_dhan()
        # [PHD-FIX Section-43] was datetime.today() (naive, server-local) —
        # now uses now_ist(), already imported in this file and used
        # elsewhere in it, just not here.
        end_date = now_ist()
        start_date = end_date - timedelta(days=days)

        result = dhan.historical_daily_data(
            security_id=str(security_id),
            exchange_segment=exchange_segment,
            instrument_type=instrument_type,
            from_date=start_date.strftime("%Y-%m-%d"),
            to_date=end_date.strftime("%Y-%m-%d"),
        )

        if not result or result.get("status") != "success":
            append_log(AUDIT_LOG_FILE, f"REGIME DATA FAILED id={security_id}: {result}")
            return pd.DataFrame()

        return _standardize_ohlcv(result.get("data", []))

    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"REGIME FETCH ERROR id={security_id}: {e}")
        return pd.DataFrame()


def _ema_regime_from_df(df: pd.DataFrame, label: str = "Nifty") -> dict:
    # [PHASE-FIX] EMA spans + rising-lookback ab PARAMS-driven (purane
    # hardcoded 50/200/5 hi defaults hain — behavior unchanged jab tak
    # optimizer/admin tune na kare).
    ema_fast_span = int(PARAMS.get("regime_ema_fast", 50))
    ema_slow_span = int(PARAMS.get("regime_ema_slow", 200))
    rise_lookback = int(PARAMS.get("regime_ema200_rise_lookback", 5))

    if df is None or df.empty or len(df) < ema_slow_span:
        return {
            "regime": "SIDEWAYS",
            "score": 0.0,
            "reason": f"{label}: insufficient data",
            "confidence": 0,
        }

    close = df["close"]
    ema_fast = close.ewm(span=ema_fast_span, adjust=False).mean()
    ema_slow = close.ewm(span=ema_slow_span, adjust=False).mean()

    current = _safe_float(close.iloc[-1])
    ema50_now = _safe_float(ema_fast.iloc[-1])
    ema200_now = _safe_float(ema_slow.iloc[-1])
    ema200_prev = _safe_float(ema_slow.iloc[-1 - rise_lookback] if len(ema_slow) >= rise_lookback + 2 else ema_slow.iloc[-2])

    above_50 = current > ema50_now
    above_200 = current > ema200_now
    ema200_rising = ema200_now > ema200_prev

    dist50 = (current - ema50_now) / ema50_now * 100 if ema50_now else 0
    dist200 = (current - ema200_now) / ema200_now * 100 if ema200_now else 0

    if above_50 and above_200 and ema200_rising:
        regime, score, confidence = "BULL", 2.0, 90
        reason = f"{label}: above EMA50/EMA200 and EMA200 rising"
    elif (not above_50) and (not above_200) and (not ema200_rising):
        regime, score, confidence = "BEAR", -2.0, 90
        reason = f"{label}: below EMA50/EMA200 and EMA200 falling"
    elif (not above_200) and ema200_rising:
        regime, score, confidence = "RECOVERY", 0.7, 70
        reason = f"{label}: below EMA200 but EMA200 rising"
    else:
        regime, score, confidence = "SIDEWAYS", 0.0, 60
        reason = f"{label}: mixed trend signals"

    return {
        "regime": regime,
        "score": score,
        "reason": reason,
        "confidence": confidence,
        "close": round(current, 2),
        "ema50": round(ema50_now, 2),
        "ema200": round(ema200_now, 2),
        "distance_50_pct": round(dist50, 2),
        "distance_200_pct": round(dist200, 2),
        "above_50": above_50,
        "above_200": above_200,
        "ema200_rising": ema200_rising,
    }


def _vix_score() -> dict:
    """
    Optional India VIX. If not configured, neutral.
    """
    if not INDIA_VIX_SECURITY_ID:
        return {"available": False, "score": 0.0, "reason": "India VIX not configured"}

    df = _fetch_dhan_daily_by_id(INDIA_VIX_SECURITY_ID, "IDX_I", "INDEX", days=80)
    if df.empty or len(df) < 20:
        return {"available": False, "score": 0.0, "reason": "India VIX data unavailable"}

    vix = _safe_float(df["close"].iloc[-1])
    prev20 = _safe_float(df["close"].iloc[-21])
    change20 = (vix - prev20) / prev20 * 100 if prev20 else 0

    # [PHASE-FIX] VIX thresholds ab PARAMS-driven — purane hardcoded values
    # (22/15/15) hi defaults hain, behavior unchanged jab tak tune na ho.
    vix_high = float(PARAMS.get("vix_high_level", 22.0))
    vix_rise = float(PARAMS.get("vix_rise_20d_pct", 15.0))
    vix_low = float(PARAMS.get("vix_low_level", 15.0))

    if vix >= vix_high or change20 > vix_rise:
        return {"available": True, "score": -1.0, "vix": round(vix, 2), "reason": "VIX high/rising"}
    if vix <= vix_low and change20 < 0:
        return {"available": True, "score": 0.5, "vix": round(vix, 2), "reason": "VIX low/falling"}
    return {"available": True, "score": 0.0, "vix": round(vix, 2), "reason": "VIX neutral"}


def _usdinr_score() -> dict:
    """
    Optional USDINR. Auto-discovers current futures contract.
    """
    # Auto-discover USDINR
    usdinr_id = USDINR_SECURITY_ID
    exchange = os.getenv("USDINR_EXCHANGE_SEGMENT", "NSE_CURRENCY")
    instrument = os.getenv("USDINR_INSTRUMENT_TYPE", "CURRENCY")
    
    if not usdinr_id:
        try:
            from correlation_tracker import _discover_usdinr_security_id
            discovered = _discover_usdinr_security_id()
            if discovered and discovered[0]:
                usdinr_id, exchange, instrument = discovered
        except (ImportError, RuntimeError) as e:
            logger.debug(f"_get_usdinr: USDINR discovery failed: {type(e).__name__}: {e}")
    
    if not usdinr_id:
        return {"available": False, "score": 0.0, "reason": "USDINR not configured"}

    df = _fetch_dhan_daily_by_id(usdinr_id, exchange, instrument, days=80)
    if df.empty or len(df) < 20:
        return {"available": False, "score": 0.0, "reason": "USDINR data unavailable"}

    current = _safe_float(df["close"].iloc[-1])
    prev20 = _safe_float(df["close"].iloc[-21])
    change20 = (current - prev20) / prev20 * 100 if prev20 else 0

    # Thresholds configurable via PARAMS (optimizer-tunable)
    usdinr_thresholds = PARAMS.get("usdinr_regime_thresholds", {"rising": 1.5, "easing": -1.0})
    if change20 > usdinr_thresholds["rising"]:
        return {"available": True, "score": -0.7, "change20_pct": round(change20, 2), "reason": "USDINR rising pressure"}
    if change20 < usdinr_thresholds["easing"]:
        return {"available": True, "score": 0.3, "change20_pct": round(change20, 2), "reason": "USDINR easing"}
    return {"available": True, "score": 0.0, "change20_pct": round(change20, 2), "reason": "USDINR neutral"}


def _sector_score() -> dict:
    """
    Use existing sector_strength.json if available.
    """
    try:
        from sector_strength import get_strong_sectors, get_weak_sectors
        strong = get_strong_sectors()
        weak = get_weak_sectors()

        if len(strong) >= 3 and len(strong) > len(weak):
            return {"score": 1.0, "reason": "Multiple strong sectors", "strong": strong, "weak": weak}
        if len(weak) >= 3 and len(weak) > len(strong):
            return {"score": -1.0, "reason": "Multiple weak sectors", "strong": strong, "weak": weak}
        return {"score": 0.0, "reason": "Sector strength mixed/neutral", "strong": strong, "weak": weak}

    except Exception as e:
        return {"score": 0.0, "reason": f"Sector data unavailable: {e}", "strong": [], "weak": []}


def _ds_combine_evidences(evidences: list) -> dict:
    """
    [VERIFIED METHOD] Dempster-Shafer Evidence Theory —
    Arthur P. Dempster 1967 / Glenn Shafer 1976 ("A Mathematical Theory of
    Evidence"). Multiple INDEPENDENT evidence sources ko custom hand-weights ke
    bina combine karta hai — har source apni apni CONFIDENCE se bolta hai;
    conflict (K) automatically normalize hota hai. Sensor-fusion / medical
    diagnosis / fault-detection ka standard jo ab yahan market-regime fusion
    ke liye use ho raha hai (cross-domain application).

    Har evidence: {"bull": m_b, "bear": m_s, "conf": c ∈ [0,1]}
      mass(BULL)=bull×conf, mass(BEAR)=bear×conf, mass(Θ)=1−(bull+bear)×conf
    Two-source Dempster rule iteratively; conflict K>0.99 → None (fusion
    unreliable — caller fail-open old blend use kare).
    """
    try:
        combined = {"BULL": 0.0, "BEAR": 0.0, "THETA": 1.0}
        for ev in evidences:
            conf = max(0.0, min(1.0, float(ev.get("conf", 0.5))))
            mb = max(0.0, float(ev.get("bull", 0.0))) * conf
            ms = max(0.0, float(ev.get("bear", 0.0))) * conf
            mo = max(0.0, 1.0 - mb - ms)
            # Dempster combination: A ⊕ B
            K = (combined["BULL"] * ms + combined["BEAR"] * mb)
            if K >= float(PARAMS.get("ds_conflict_threshold", 0.99)):
                return None
            nb = (combined["BULL"] * mb + combined["BULL"] * mo + combined["THETA"] * mb) / (1 - K)
            ns = (combined["BEAR"] * ms + combined["BEAR"] * mo + combined["THETA"] * ms) / (1 - K)
            nt = (combined["THETA"] * mo) / (1 - K)
            combined = {"BULL": nb, "BEAR": ns, "THETA": nt}
        return combined
    except Exception as e:
        logger.warning(f"_ds_combine_evidences failed: {e}")
        return None


def _regime_signal_to_evidence(score: float, base_conf: float) -> dict:
    """score ∈ [-1, +1] ko D-S evidence me map (bull/bear directions)."""
    score = max(-1.0, min(1.0, float(score or 0.0)))
    return {"bull": max(0.0, score), "bear": max(0.0, -score), "conf": base_conf}


def _combine(details: dict) -> dict:
    # [PHASE-FIX] Weights ab PARAMS-driven + normalize hote hain (missing/
    # bad keys ya sum!=1 hone par bhi score scale consistent rehta hai).
    # 4 macro evidences: Nifty, sector, VIX, USDINR.
    default_weights = {
        "nifty": 0.45,
        "sector": 0.25,
        "vix": 0.15,
        "usdinr": 0.15,
    }
    raw_weights = PARAMS.get("regime_weights", default_weights)
    if not isinstance(raw_weights, dict):
        raw_weights = default_weights

    weights = {}
    for key in default_weights:
        try:
            weights[key] = float(raw_weights.get(key, default_weights[key]))
        except (TypeError, ValueError):
            weights[key] = default_weights[key]
    total_w = sum(weights.values())
    if total_w <= 0:
        weights = dict(default_weights)
        total_w = sum(weights.values())
    weights = {k: v / total_w for k, v in weights.items()}

    score = (
        details["nifty"]["score"] * weights["nifty"] +
        details["sector"]["score"] * weights["sector"] +
        details["vix"]["score"] * weights["vix"] +
        details["usdinr"]["score"] * weights["usdinr"]
    )

    nifty_regime = details["nifty"]["regime"]

    bull_threshold = float(PARAMS.get("multi_factor_bull_threshold", 0.80))
    bear_threshold = float(PARAMS.get("multi_factor_bear_threshold", -0.80))
    recovery_score = float(PARAMS.get("multi_factor_recovery_score", 0.20))

    if score >= bull_threshold and nifty_regime != "BEAR":
        final = "BULL"
        reason = "Macro factors supportive"
    elif score <= bear_threshold:
        final = "BEAR"
        reason = "Macro risk-off"
    elif nifty_regime == "RECOVERY" or score > recovery_score:
        final = "RECOVERY"
        reason = "Recovery/early improvement detected"
    else:
        final = "SIDEWAYS"
        reason = "Mixed signals — selective mode"

    return {
        "regime": final,
        "combined_score": round(score, 2),
        "reason": reason,
    }


def _fallback_regime(details: dict) -> dict:
    """Helper to perform multi-factor fallback when HMM inputs are missing."""
    details.update({
        "sector": _sector_score(),
        "vix": _vix_score(),
        "usdinr": _usdinr_score(),
    })
    combined = _combine(details)
    output = {
        "date": now_ist().date().isoformat(),
        "updated_at": now_ist().isoformat(),
        "source": "Multi-Factor (HMM fallback — missing data)",
        **combined,
        "details": details,
    }
    save_json(MARKET_REGIME_FILE, output)
    append_log(AUDIT_LOG_FILE, f"MARKET REGIME HMM FALLBACK: {output['regime']} method=multi-factor")
    from fallback_monitor import record_fallback   # FIX-LIST item 17 (visibility only)
    record_fallback("market_regime.hmm_to_multifactor", "HMM inputs missing (Nifty/VIX/USDINR data)", output.get("regime"))
    return output


def _statistical_quantile_fallback(returns: np.ndarray) -> str:
    """
    Fail-closed fallback: If HMM fails, use statistical 25th/75th percentile quantile logic
    on the log returns of Nifty 50 daily data.
    """
    if len(returns) < 20:
        return "SIDEWAYS"
    
    recent_return = float(returns[-1][0])
    q25 = float(np.percentile(returns, 25))
    q75 = float(np.percentile(returns, 75))
    
    if recent_return >= q75:
        return "BULL"
    elif recent_return <= q25:
        return "BEAR"
    elif recent_return > 0:
        return "RECOVERY"
    else:
        return "SIDEWAYS"


def refresh_market_regime(force_refresh: bool = True) -> dict:
    """
    Build BULL/SIDEWAYS/BEAR/RECOVERY regime using Hidden Markov Model (HMM).
    
    Method: Hidden Markov Model (Gaussian HMM)
    Creator: James D. Hamilton (1989)
    Paper: "A New Approach to the Economic Analysis of Nonstationary Time Series"
    Industry Use: Bloomberg, Reuters, most quant funds
    
    HMM learns regime probabilities from data — no arbitrary thresholds.
    """
    nifty_df = _fetch_dhan_daily_by_id(
        NIFTY_SECURITY_ID,
        NIFTY_EXCHANGE_SEGMENT,
        NIFTY_INSTRUMENT_TYPE,
        days=320,
    )
    
    if nifty_df.empty or len(nifty_df) < 100:
        return _fallback_regime(details={"nifty": {"regime": "SIDEWAYS", "score": 0}})

    # Calculate log returns for HMM
    returns = np.log(nifty_df["close"] / nifty_df["close"].shift(1)).dropna().values.reshape(-1, 1)

    try:
        from hmmlearn.hmm import GaussianHMM
        
        # Fit HMM with 4 regimes (BULL, SIDEWAYS, BEAR, RECOVERY)
        model = GaussianHMM(
            n_components=4,
            covariance_type="full",
            n_iter=1000,
            random_state=42,
        )
        model.fit(returns)
        hidden_states = model.predict(returns)
        
        # Map states to regimes based on mean return
        state_means = [model.means_[i][0] for i in range(4)]
        sorted_states = sorted(range(4), key=lambda i: state_means[i])
        
        # Assign regimes: lowest mean = BEAR, highest = BULL
        state_to_regime = {}
        state_to_regime[sorted_states[0]] = "BEAR"
        state_to_regime[sorted_states[1]] = "SIDEWAYS"
        state_to_regime[sorted_states[2]] = "RECOVERY"
        state_to_regime[sorted_states[3]] = "BULL"
        
        current_state = hidden_states[-1]
        current_regime = state_to_regime[current_state]
        
        # Calculate regime probabilities
        proba = model.predict_proba(returns)
        current_proba = proba[-1]
        
        details = {
            "hmm_regime": current_regime,
            "hmm_state": int(current_state),
            "hmm_probability": round(float(current_proba[current_state]), 4),
            "hmm_model": "GaussianHMM (Hamilton 1989)",
            "nifty": _ema_regime_from_df(nifty_df, label="Nifty 50"),
            "sector": _sector_score(),
            "vix": _vix_score(),
            "usdinr": _usdinr_score(),
        }
        
        output = {
            "date": now_ist().date().isoformat(),
            "updated_at": now_ist().isoformat(),
            "source": "HMM (Hamilton 1989) + Multi-Factor",
            "regime": current_regime,
            "method": "Hidden Markov Model",
            "creator": "James D. Hamilton (1989)",
            **details,
        }
        
    except Exception as e:
        logger.warning(f"HMM model failed or hmmlearn not installed: {e}. Falling back to statistical quantile logic.")
        try:
            fallback_regime = _statistical_quantile_fallback(returns)
        except Exception as fe:
            logger.error(f"Quantile fallback failed: {fe}")
            fallback_regime = "SIDEWAYS"
            
        details = {
            "nifty": {"regime": fallback_regime, "score": 0.0},
            "sector": _sector_score(),
            "vix": _vix_score(),
            "usdinr": _usdinr_score(),
        }
        # [Method upgrade 2026-07-30 — Dempster 1967/Shafer 1976] custom
        # hand-weights ki jagah evidence-theory fusion.
        # Fusion fail → exact purana weighted blend (fail-open).
        # [PHASE-FIX] Evidence confidences ab PARAMS-driven hain.
        ds_conf = PARAMS.get("ds_evidence_confidences", {})
        if not isinstance(ds_conf, dict):
            ds_conf = {}

        def _conf(key: str, default: float) -> float:
            try:
                return float(ds_conf.get(key, default))
            except (TypeError, ValueError):
                return default

        ds = _ds_combine_evidences([
            _regime_signal_to_evidence(details["nifty"]["score"], _conf("nifty", 0.6)),
            _regime_signal_to_evidence(details["sector"]["score"], _conf("sector", 0.4)),
            _regime_signal_to_evidence(details["vix"]["score"], _conf("vix", 0.3)),
            _regime_signal_to_evidence(details["usdinr"]["score"], _conf("usdinr", 0.3)),
        ])
        if ds is not None and max(ds["BULL"], ds["BEAR"], ds["THETA"]) != 1.0:
            if ds["BULL"] > ds["BEAR"] and ds["BULL"] > ds["THETA"]:
                fallback_regime = "BULL"
            elif ds["BEAR"] > ds["BULL"] and ds["BEAR"] > ds["THETA"]:
                fallback_regime = "BEAR"
            append_log(AUDIT_LOG_FILE,
                f"REGIME D-S FUSION: BULL={ds['BULL']:.2f} BEAR={ds['BEAR']:.2f} "
                f"Θ={ds['THETA']:.2f} → {fallback_regime} (Dempster 1967/Shafer 1976)")
        combined = _combine(details)
        output = {
            "date": now_ist().date().isoformat(),
            "updated_at": now_ist().isoformat(),
            "source": "Multi-Factor (Dempster-Shafer + Quantile fallback)" if ds is not None else "Multi-Factor (Quantile statistical fallback)",
            "regime": fallback_regime,
            "method": "Statistical Quantile Logic",
            "creator": "Statistical standard",
            **combined,
            "details": details,
        }

    save_json(MARKET_REGIME_FILE, output)
    append_log(AUDIT_LOG_FILE, f"MARKET REGIME HMM: {output['regime']} method={output.get('method', 'multi-factor')}")
    return output


def get_market_regime_details(force_refresh: bool = False) -> dict:
    cached = load_json(MARKET_REGIME_FILE, {})
    if cached and not force_refresh:
        try:
            updated = datetime.fromisoformat(cached.get("updated_at"))
            age_hours = (now_ist().replace(tzinfo=None) - updated.replace(tzinfo=None)).total_seconds() / 3600
            if age_hours <= REGIME_CACHE_HOURS and cached.get("regime"):
                return cached
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"_get_cached_regime: Cache parse failed: {type(e).__name__}: {e}")

    return refresh_market_regime(force_refresh=True)


def get_market_regime(force_refresh: bool = False) -> str:
    return get_market_regime_details(force_refresh=force_refresh).get("regime", "SIDEWAYS")


def get_market_regime_report(force_refresh: bool = False) -> str:
    d = get_market_regime_details(force_refresh=force_refresh)
    det = d.get("details", {})
    n = det.get("nifty", {})
    s = det.get("sector", {})
    v = det.get("vix", {})
    u = det.get("usdinr", {})

    return (
        f"Market Regime: {d.get('regime', 'SIDEWAYS')}\n"
        f"Score: {d.get('combined_score', 0)} | {d.get('reason', '')}\n"
        f"Updated: {str(d.get('updated_at', ''))[:16]}\n\n"
        f"Nifty: {n.get('regime', 'N/A')} | {n.get('reason', '')}\n"
        f"Nifty Close: {n.get('close', 'N/A')} | EMA200 dist: {n.get('distance_200_pct', 'N/A')}%\n\n"
        f"Sector: {s.get('reason', 'N/A')}\n"
        f"Strong: {len(s.get('strong', []))} | Weak: {len(s.get('weak', []))}\n\n"
        f"VIX: {v.get('reason', 'Not configured')}\n"
        f"USDINR: {u.get('reason', 'Not configured')}\n"
        f"Source: {d.get('source', '')}"
    )
