"""
strategy.py — Strategy framework + concrete implementation
3-phase system: UPTREND / SIDEWAYS / DOWNTREND
All indicators available — optimizer picks best combo per stock
"""

import logging
from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
from config import PARAMS, AUDIT_LOG_FILE
from utils import append_log, now_ist, safe_div

logger = logging.getLogger(__name__)
from per_stock_params import get_param
from strategy_tools import make_live_signals, TOOL_NAMES, get_optimizer_signal_generators, calc_rsi


# ─────────────────────────────────────────────
# BASE STRATEGY
# ─────────────────────────────────────────────

class BaseStrategy(ABC):
    name: str    = "BaseStrategy"
    version: str = "1.0"

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame, symbol: str, is_backtest: bool = False, **kwargs) -> list:
        pass

    @abstractmethod
    def backtest_on_data(self, data: pd.DataFrame, symbol: str) -> dict:
        pass


# ─────────────────────────────────────────────
# PHASE DETECTION
# ─────────────────────────────────────────────

def detect_market_phase(data: pd.DataFrame, symbol: str = None, params_override: dict = None) -> str:
    """
    Detect: UPTREND / SIDEWAYS / DOWNTREND
    Uses per-stock optimized params if available.

    [PHASE-FIX] Engineering corrections:
    - params missing → "SIDEWAYS" (fail-closed STRING) return hota hai,
      pehle `return []` (list) hota tha jo callers me .lower()/== checks
      crash karta tha.
    - append_log/AUDIT_LOG_FILE imports ab present hain (pehle NameError
      hota tha is branch me).
    - int()/float() conversions try/except se safe.
    """
    params_override = params_override or {}
    try:
        if symbol:
            fast = params_override.get("phase_ema_fast") or get_param(symbol, "phase_ema_fast", None) or PARAMS.get("phase_ema_fast")
            slow = params_override.get("phase_ema_slow") or get_param(symbol, "phase_ema_slow", None) or PARAMS.get("phase_ema_slow")
            adx_thresh = params_override.get("phase_adx_threshold") or get_param(symbol, "phase_adx_threshold", None) or PARAMS.get("phase_adx_threshold")
            if fast is None or slow is None or adx_thresh is None:
                append_log(AUDIT_LOG_FILE, f"PHASE PARAMS MISSING: {symbol} — phase defaults to SIDEWAYS (fail-closed)")
                return "SIDEWAYS"
            fast = int(fast)
            slow = int(slow)
            adx_thresh = float(adx_thresh)
        else:
            fast = params_override.get("phase_ema_fast") or PARAMS.get("phase_ema_fast")
            slow = params_override.get("phase_ema_slow") or PARAMS.get("phase_ema_slow")
            if fast is None or slow is None:
                return "SIDEWAYS"
            fast = int(fast)
            slow = int(slow)
            # [FIX] phase_adx_threshold no longer lives in PARAMS (fail-closed
            # contract — see config.py). This no-symbol branch is dead on the
            # live path (real callers always pass symbol), but use a literal
            # TA-convention fallback here instead of PARAMS[...] to avoid a
            # KeyError if it's ever reached.
            adx_thresh = float(params_override.get("phase_adx_threshold") or 25.0)
    except (TypeError, ValueError) as e:
        append_log(AUDIT_LOG_FILE, f"PHASE PARAM PARSE ERROR: {symbol or 'global'} — {type(e).__name__}: {e} → SIDEWAYS (fail-closed)")
        return "SIDEWAYS"

    if fast >= slow:
        append_log(AUDIT_LOG_FILE, f"PHASE PARAMS INVALID: {symbol} — fast={fast} >= slow={slow} → SIDEWAYS (fail-closed)")
        return "SIDEWAYS"

    if len(data) < slow + 5:
        return "SIDEWAYS"

    ema_fast_val = float(data["close"].ewm(span=fast).mean().iloc[-1])
    ema_slow_val = float(data["close"].ewm(span=slow).mean().iloc[-1])
    adx = _calculate_adx(data, 14)
    phase_threshold = _dynamic_phase_threshold(data, adx_thresh, symbol=symbol,
                                                ema_fast_val=ema_fast_val,
                                                ema_slow_val=ema_slow_val,
                                                params_override=params_override)

    if adx >= phase_threshold:
        return "UPTREND" if ema_fast_val > ema_slow_val else "DOWNTREND"
    return "SIDEWAYS"


def _calculate_adx(data: pd.DataFrame, period: int = 14) -> float:
    try:
        high  = data["high"]
        low   = data["low"]
        close = data["close"]

        # [PHD-FIX F4] Wilder DM rule: ek bar me sirf BADA directional
        # movement count hota hai (+DM aur -DM kabhi dono positive nahi).
        up_move   = high.diff()
        down_move = -low.diff()
        plus_dm  = ((up_move > down_move) & (up_move > 0)) * up_move
        minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move

        # Raw True Range per Wilder (1978): max(H-L, |H-Cprev|, |L-Cprev|).
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low  - close.shift()).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # [FIX-LIST 2026-09-04 item 4] ADX smoothing bug fix.
        # Previous code used ewm(span=period) (alpha = 2/(period+1), i.e. a
        # standard EMA with pandas' default adjust=True weighting) for ATR,
        # +DI/-DI AND the final DX→ADX step. Wilder's ADX uses his own
        # smoothing (RMA, alpha = 1/period, recursive/adjust=False) at each of
        # those steps. With span-EMA the result over-reacts: independently
        # recalculated against a textbook Wilder loop on 30 random series the
        # old code was off by ~6.9 ADX points on average (0.000 after this fix),
        # which shifts the UPTREND/DOWNTREND-vs-SIDEWAYS phase decision.
        # The DX→ADX step itself is NOT removed: ADX is by definition the
        # Wilder-smoothed DX (dropping it would return DX, a different, far
        # noisier indicator). Same canonical Wilder alpha the RSI already uses
        # (PHD-FIX F4) — indicators now agree with each other.
        alpha    = 1.0 / period
        atr      = true_range.ewm(alpha=alpha, adjust=False).mean()
        plus_di  = 100 * (plus_dm.ewm(alpha=alpha, adjust=False).mean()  / (atr + 1e-10))
        minus_di = 100 * (minus_dm.ewm(alpha=alpha, adjust=False).mean() / (atr + 1e-10))
        dx       = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10))
        adx      = dx.ewm(alpha=alpha, adjust=False).mean().iloc[-1]
        return float(adx)
    except (TypeError, ValueError, IndexError, AttributeError, ZeroDivisionError) as e:
        # AI-DOS LOGIC-001 fix: ZeroDivisionError (period=0 caller bug) was
        # not previously caught here — added to the existing fail-soft contract.
        logger.debug(f"calculate_adx: ADX calculation failed: {type(e).__name__}: {e}")
        return 0.0



def _dynamic_phase_threshold(data: pd.DataFrame, base_threshold: float,
                              symbol: str = None, ema_fast_val: float = None,
                              ema_slow_val: float = None,
                              params_override: dict = None) -> float:
    """
    Decision 17 — dynamic market phase (ADX) threshold, calibrated per-stock.

    [VERIFIED QUANT METHOD] Rolling-percentile regime calibration, per the
    RegimeFolio methodology (arxiv 2510.14986): rather than comparing every
    stock's realized volatility against one fixed universal baseline (which
    penalizes/rewards stocks unevenly depending on how their typical
    volatility compares to that arbitrary constant), this stock's CURRENT
    realized volatility is expressed as a percentile rank within its OWN
    trailing historical distribution. A stock that is unusually volatile
    *for itself right now* (high percentile) requires a stronger ADX signal
    to confirm a trend; a stock that is unusually calm *for itself* (low
    percentile) is allowed a slightly weaker ADX signal to still count.
    This is self-calibrating and per-stock, not a one-size-fits-all cutoff.

    Trend-strength relief uses the SAME EMA fast/slow values the caller
    already computed with this stock's own optimized phase_ema_fast/slow
    periods -- no separate hardcoded EMA(20)/EMA(50) recomputation.

    [PHASE-FIX] params_override: optimizer ke candidate/optimized params ko
    bhi accept karta hai — taaki optimize hote waqt (jab per-stock params
    file me abhi saved nahi hain) classification LIVE jaise hi values use
    kare, defaults nahi.
    """
    try:
        params_override = params_override or {}

        def _pv(key: str, default):
            if key in params_override and params_override.get(key) is not None:
                return params_override.get(key)
            if symbol:
                return get_param(symbol, key, default)
            return default

        returns = data["close"].pct_change().dropna()
        history_lookback = int(_pv("vol_regime_history_days", 252))
        roll_period = int(_pv("vol_lookback", 20))

        history = returns.tail(history_lookback)
        if len(history) < max(30, roll_period * 2):
            return float(base_threshold)  # not enough history for a meaningful percentile rank

        rolling_vol = history.rolling(roll_period).std().dropna() * (252 ** 0.5) * 100
        if len(rolling_vol) < 10:
            return float(base_threshold)

        current_vol = float(rolling_vol.iloc[-1])
        vol_percentile = float((rolling_vol < current_vol).mean())  # this stock's own historical rank, 0-1

        low_q = float(_pv("vol_regime_low_quantile", 0.33))
        high_q = float(_pv("vol_regime_high_quantile", 0.67))
        max_adj = float(_pv("phase_threshold_adj_range", 0.20))

        if vol_percentile >= high_q:
            vol_norm = max_adj * (vol_percentile - high_q) / max(1e-6, 1.0 - high_q)
        elif vol_percentile <= low_q:
            vol_norm = -max_adj * (low_q - vol_percentile) / max(1e-6, low_q)
        else:
            vol_norm = 0.0

        if ema_fast_val is not None and ema_slow_val is not None and ema_slow_val:
            trend_distance_pct = abs((ema_fast_val - ema_slow_val) / (ema_slow_val + 1e-10)) * 100
        else:
            trend_distance_pct = 0.0
        trend_relief = max(0.0, min(float(_pv("phase_threshold_relief_cap", 0.15)), trend_distance_pct / 100.0))

        adjusted = float(base_threshold) * (1.0 + vol_norm - trend_relief)
        phase_min = float(_pv("phase_threshold_min", 12.0))
        phase_max = float(_pv("phase_threshold_max", 45.0))
        return max(phase_min, min(phase_max, round(adjusted, 2)))
    except (TypeError, ValueError, AttributeError) as e:
        logger.debug(f"_dynamic_phase_threshold: Calculation failed: {type(e).__name__}: {e}")
        return float(base_threshold)


# ─────────────────────────────────────────────
# OPTIMIZATION-DRIVEN PHASE GATE
# ─────────────────────────────────────────────

VALID_PHASES = ("UPTREND", "SIDEWAYS", "DOWNTREND")

_GATE_AUDIT_LOGGED = set()


def _log_phase_gate_once(symbol: str, phase: str, reason: str):
    """Phase-gate block ko audit me din me ek baar (per symbol+phase) log karo
    — har 3-5 min scan cycle me spam na ho."""
    try:
        day = now_ist().date().isoformat()
        key = (day, symbol, phase)
        if key in _GATE_AUDIT_LOGGED:
            return
        _GATE_AUDIT_LOGGED.add(key)
        if len(_GATE_AUDIT_LOGGED) > 5000:
            _GATE_AUDIT_LOGGED.clear()
        append_log(AUDIT_LOG_FILE, f"PHASE GATE {symbol}: {phase} BLOCKED — {reason}")
    except Exception as e:
        logger.debug(f"_log_phase_gate_once failed: {e}")


def is_phase_trade_allowed(symbol: str, phase: str,
                           params_override: dict = None) -> tuple:
    """
    [PHASE-FIX — OPTIMIZATION-DRIVEN PHASE ENABLEMENT]

    Har stock, har phase (UPTREND/SIDEWAYS/DOWNTREND) ka trade decision ab
    optimizer ke per-stock params (`phase_allow_<phase>`) se aata hai —
    koi hardcoded "sirf uptrend" rule nahi:

    - Flag True   → phase ka edge optimizer ne statistically prove kiya
                    (one-sided t-test, OOS trades) → trades allowed.
    - Flag False  → optimizer ne measure kiya aur edge NAHI mila
                    → trades blocked (fail-closed, "warna trade nahi").
    - Flag missing→ stock ki is phase ka optimization abhi nahi hua
                    (insufficient sample etc.) → LEGACY default:
                    UPTREND allowed, SIDEWAYS/DOWNTREND blocked
                    (purana production behavior preserved; sirf proven
                    optimization hi unlock karta hai).

    params_override (optimizer measurement context) me flags nahi hote to
    gate bypass hota hai — measurement kabhi apne aap ko gate na kare.

    Returns (allowed: bool, reason: str)
    """
    phase = str(phase or "").strip().upper()
    if phase not in VALID_PHASES:
        return False, f"unknown phase '{phase}'"

    key = f"phase_allow_{phase.lower()}"
    val = None
    if params_override:
        val = params_override.get(key)
        if val is None:
            return True, "optimizer measurement context (no gate)"
    else:
        try:
            val = get_param(symbol, key, None)
        except (TypeError, ValueError) as e:
            logger.debug(f"is_phase_trade_allowed: param lookup failed for {symbol}: {e}")
            val = None

    if val is None:
        legacy_allow = (phase == "UPTREND")
        return legacy_allow, (
            f"{phase} gate not optimized yet — legacy default "
            f"({'ALLOWED' if legacy_allow else 'BLOCKED'}; per-stock phase "
            f"optimization run needed to prove edge)"
        )

    try:
        allowed = bool(val)
    except (TypeError, ValueError):
        return False, f"invalid optimized flag for {key}"

    return allowed, (
        f"{phase} {'ENABLED' if allowed else 'BLOCKED'} by per-stock "
        f"optimization (phase_allow_{phase.lower()}={bool(val)})"
    )


def get_phase_gate_report(symbol: str) -> str:
    """Admin: stock ke per-phase gate status ka readable summary."""
    lines = [f"Phase Gate — {symbol}"]
    for phase in VALID_PHASES:
        allowed, reason = is_phase_trade_allowed(symbol, phase)
        lines.append(f"  {phase:<10} → {'ALLOWED' if allowed else 'BLOCKED'} | {reason}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# INDICATORS LIBRARY
# ─────────────────────────────────────────────

def calc_ema(data: pd.DataFrame, period: int) -> pd.Series:
    return data["close"].ewm(span=period).mean()


def calc_sma(data: pd.DataFrame, period: int) -> pd.Series:
    """[OVERRIDE 4] Simple Moving Average — needed for Minervini's Trend
    Template (SMA50/150/200), which is defined in terms of SMAs, not EMAs."""
    return data["close"].rolling(period).mean()


# [ATR-FIX-followup] calc_rsi() used to be defined here as a byte-identical
# duplicate of strategy_tools.calc_rsi(). Removed to keep exactly ONE
# canonical RSI implementation in the codebase (same duplication risk
# pattern that caused the ATR bug — see optimizer.py FIXES APPLIED, BUG #9).
# calc_rsi is now imported above from strategy_tools.


def calc_macd(data: pd.DataFrame, fast: int = 12,
              slow: int = 26, signal: int = 9) -> tuple:
    ema_fast   = data["close"].ewm(span=fast).mean()
    ema_slow   = data["close"].ewm(span=slow).mean()
    macd_line  = ema_fast - ema_slow
    signal_line= macd_line.ewm(span=signal).mean()
    histogram  = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
    # [PHD-FIX F4 completion] Wilder smoothing (alpha=1/period) — canonical
    # ATR (Wilder 1978), same standard already applied to calc_rsi and the
    # ADX-internal ATR in calculate_adx(). Was previously ewm(span=period),
    # a plain EMA that reacts faster/noisier than Wilder's RMA — inconsistent
    # with this codebase's own declared standard.
    tr = pd.concat([
        data["high"] - data["low"],
        (data["high"] - data["close"].shift()).abs(),
        (data["low"]  - data["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


def calc_bollinger(data: pd.DataFrame, period: int = 20,
                   std: float = 2.0) -> tuple:
    """[AUDIT note, 2026-09-17] Unused dead code — no caller anywhere in the
    codebase. opt_bollinger_reversion() (strategy_tools.py) computes its own
    bollinger bands inline rather than calling this. Also previously flagged
    in AUDIT_PROGRESS_READ_ME_FIRST.md as confirmed dead alongside
    calc_macd(). Kept for potential future use; not wired into any live path.
    """
    mid    = data["close"].rolling(period).mean()
    stddev = data["close"].rolling(period).std()
    upper  = mid + std * stddev
    lower  = mid - std * stddev
    return upper, mid, lower


def calc_vwap(data: pd.DataFrame) -> pd.Series:
    """[AUDIT F4 note, 2026-09-16] Unused dead code (no caller in this
    file or elsewhere) -- the live signal path uses
    strategy_tools.calc_vwap() instead. Same "not a real session VWAP"
    caveat applies if this is ever wired up; see that function's
    docstring."""
    return (data["close"] * data["volume"]).cumsum() / data["volume"].cumsum()


def calc_volume_ma(data: pd.DataFrame, period: int = 20) -> pd.Series:
    return data["volume"].rolling(period).mean()


def is_volume_confirmed(data: pd.DataFrame, idx: int,
                         mult: float = 1.5) -> bool:
    """Check if current volume is above average × mult."""
    vol_ma = calc_volume_ma(data).iloc[idx]
    curr   = data["volume"].iloc[idx]
    return curr > vol_ma * mult if vol_ma > 0 else False


def calc_swing_low(data: pd.DataFrame, lookback: int = 20) -> pd.Series:
    return data["low"].rolling(lookback).min()


def calc_recent_high(data: pd.DataFrame, lookback: int = 20) -> pd.Series:
    return data["high"].rolling(lookback).max()


# ─────────────────────────────────────────────
# SECTOR + REGIME + FII FILTER
# ─────────────────────────────────────────────

def _coerce_trade_date(value):
    try:
        from fii_dii_tracker import _parse_trade_date
        return _parse_trade_date(value)
    except (ImportError, RuntimeError, TypeError) as e:
        logger.debug(f"_coerce_trade_date: Parse failed: {type(e).__name__}: {e}")
        return None



def _trade_date_from_data(data: pd.DataFrame, idx: int = None):
    try:
        if data is None or len(data) == 0:
            return None
        idx = len(data) - 1 if idx is None else int(idx)
        if idx < 0 or idx >= len(data):
            return None
        return _coerce_trade_date(data.index[idx])
    except (TypeError, ValueError, IndexError, AttributeError) as e:
        logger.debug(f"_trade_date_from_data: Date extraction failed: {type(e).__name__}: {e}")
        return None



def _get_sector_context(symbol: str, trade_date=None) -> dict:
    """
    [VERIFIED CALCULATION CHAIN] Sector filter is primary only when a real
    point-in-time sector snapshot exists for the same trade date. If historical
    sector snapshot does not exist, hierarchy falls back to regime + lagged
    FII/DII + signal instead of silently using future sector data.
    """
    from utils import load_json

    sector_data = load_json("data/sector_strength.json", {})
    sector_name = "Unknown"
    try:
        from sector_strength import get_stock_sector
        sector_name = get_stock_sector(symbol)
    except (ImportError, RuntimeError) as e:
        logger.debug(f"_get_sector_context: Sector lookup failed: {type(e).__name__}: {e}")

    sector_info = sector_data.get(sector_name, {}) if isinstance(sector_data, dict) else {}
    updated_at = sector_data.get("updated_at") if isinstance(sector_data, dict) else None
    updated_date = None
    if updated_at:
        try:
            updated_date = _coerce_trade_date(str(updated_at)[:10])
        except (TypeError, ValueError) as e:
            logger.debug(f"_get_sector_context: Date parse failed: {type(e).__name__}: {e}")
            updated_date = None

    as_of_date = _coerce_trade_date(trade_date)
    same_day_snapshot = bool(updated_date and as_of_date and updated_date == as_of_date)
    available = bool(sector_name and sector_name != "Unknown" and sector_info and same_day_snapshot)
    status = sector_info.get("status", "UNKNOWN") if isinstance(sector_info, dict) else "UNKNOWN"

    # [BACKTEST-PARITY PIT] Same-day snapshot nahi → sector_history.json
    # archive se point-in-time reconstruct: strictly dated ≤ trade_date
    # (look-ahead impossible). Archive change_pct rakhta hai; momentum blend
    # PIT available nahi (honest note) — status sirf change_pct + owner
    # thresholds se. Live (today) pe bhi T-1 archive use hota hai jab aaj ka
    # snapshot missing ho — ab sector filter stale-data days pe bhi same
    # hierarchy me kaam karta hai, backtest aur live dono me.
    pit_used = False
    if not available and sector_name and sector_name != "Unknown":
        try:
            hist = load_json("data/sector_history.json", {"days": []})
            days = hist.get("days", []) if isinstance(hist, dict) else []
            candidate = None
            for day in days:
                if not isinstance(day, dict):
                    continue
                d = _coerce_trade_date(day.get("date"))
                if d is None or (as_of_date is not None and d > as_of_date):
                    continue
                chg = (day.get("sectors") or {}).get(sector_name)
                if chg is None:
                    continue
                if candidate is None or d > candidate[0]:
                    candidate = (d, float(chg))
            if candidate is not None:
                from sector_strength import _get_status
                pit_date, pit_chg = candidate
                status = _get_status(pit_chg)
                updated_date = pit_date
                available = True
                pit_used = True
        except (ImportError, RuntimeError, TypeError, ValueError) as e:
            logger.debug(f"_get_sector_context: PIT archive fallback failed: {type(e).__name__}: {e}")

    return {
        "available": available,
        "sector": sector_name,
        "status": status,
        "pit_archive": pit_used,
        # [AUDIT FIX — item 6/5] previously "status != WEAK" let NEUTRAL sectors
        # pass here, disagreeing with sector_strength.get_sector_runtime_signal()'s
        # rule. Both now require STRONG specifically (user-confirmed: long-only bot
        # should only take new entries in sectors with confirmed outperformance).
        "is_strong": status == "STRONG" if available else False,
        "updated_date": updated_date.isoformat() if updated_date else None,
    }



def get_macro_context(symbol: str, trade_date=None, phase: str = None, params_override: dict = None) -> dict:
    """
    [VERIFIED QUANT METHOD] Macro chain hierarchy:
    1) Use lagged point-in-time FII/DII record (T-1 for day T) to avoid look-ahead.
    2) Use sector strength as first preference ONLY when same-day snapshot exists.
    3) If sector snapshot is absent, fallback to regime/phase + lagged FII/DII + signal.
    Strictly Fail-Closed on unexpected errors.
    """
    try:
        params_override = params_override or {}
        use_sector_filter = bool(params_override.get(
            "use_sector_filter",
            get_param(symbol, "use_sector_filter", PARAMS.get("use_sector_filter", True))
        ))

        from fii_dii_tracker import is_market_bearish
        if is_market_bearish(as_of_date=trade_date, publication_lag_trading_days=1):
            return {
                "allow": False,
                "path": "FII_POINT_IN_TIME_BLOCK",
                "phase": phase,
                "trade_date": str(trade_date) if trade_date is not None else None,
                "reason": "Lagged FII point-in-time record is bearish",
            }

        if not use_sector_filter:
            return {
                "allow": True,
                "path": "REGIME_FALLBACK",
                "phase": phase,
                "trade_date": str(trade_date) if trade_date is not None else None,
                "reason": "Sector filter explicitly disabled by optimized/admin parameter",
            }

        sector_ctx = _get_sector_context(symbol, trade_date=trade_date)
        if sector_ctx["available"]:
            if sector_ctx["is_strong"]:
                return {
                    "allow": True,
                    "path": "SECTOR_PRIMARY",
                    "phase": phase,
                    "trade_date": str(trade_date) if trade_date is not None else None,
                    "reason": f"Sector {sector_ctx['sector']} status={sector_ctx['status']} and lagged FII not bearish",
                }
            return {
                "allow": False,
                "path": "SECTOR_PRIMARY_BLOCK",
                "phase": phase,
                "trade_date": str(trade_date) if trade_date is not None else None,
                "reason": f"Sector {sector_ctx['sector']} status={sector_ctx['status']} blocks entry",
            }

        return {
            "allow": True,
            "path": "REGIME_FALLBACK",
            "phase": phase,
            "trade_date": str(trade_date) if trade_date is not None else None,
            "reason": "Sector snapshot unavailable for point-in-time date; fallback to regime + lagged FII/DII + signal",
        }
    except Exception as e:
        from utils import append_log
        from config import AUDIT_LOG_FILE
        append_log(AUDIT_LOG_FILE, f"MACRO FILTER ERROR ({symbol}): {e} (Fail-Closed)")
        return {
            "allow": False,
            "path": "ERROR_FAIL_CLOSED",
            "phase": phase,
            "trade_date": str(trade_date) if trade_date is not None else None,
            "reason": str(e),
        }



def is_macro_ok(symbol: str, trade_date=None, phase: str = None, params_override: dict = None) -> bool:
    return bool(get_macro_context(symbol, trade_date=trade_date, phase=phase, params_override=params_override).get("allow"))



def filter_signals_by_macro_context(data: pd.DataFrame, symbol: str, signals: list,
                                    is_backtest: bool = False, phase_hint: str = None,
                                    params_override: dict = None) -> list:
    if not signals:
        return []

    filtered = []
    params_override = params_override or {}

    for signal in signals:
        try:
            sig = dict(signal)
            idx = sig.get("entry_idx", sig.get("idx", len(data) - 1))
            idx = int(idx)
            if idx < 0 or idx >= len(data):
                continue

            trade_date = _trade_date_from_data(data, idx)
            phase = sig.get("phase") or phase_hint
            if is_backtest:
                lookback = max(100, int(params_override.get("phase_ema_slow", PARAMS.get("phase_ema_slow", 50))) + 5)
                segment = data.iloc[max(0, idx - lookback):idx + 1]
                phase = detect_market_phase(segment, symbol, params_override=params_override)
            elif not phase:
                phase = detect_market_phase(data.iloc[:idx + 1], symbol, params_override=params_override)

            macro_ctx = get_macro_context(symbol, trade_date=trade_date, phase=phase, params_override=params_override)
            if not macro_ctx.get("allow"):
                continue

            sig["phase"] = phase or sig.get("phase", "SIDEWAYS")
            sig["macro_path"] = macro_ctx.get("path")
            filtered.append(sig)
        except (TypeError, ValueError, KeyError) as e:
            logger.debug(f"_apply_macro_filter: Signal filter failed: {type(e).__name__}: {e}")
            continue

    return filtered


# ─────────────────────────────────────────────
# MAIN STRATEGY — HALAL MULTI-PHASE
# ─────────────────────────────────────────────

class HalalMultiPhaseStrategy(BaseStrategy):
    """
    3-phase strategy:
    - UPTREND: EMA cross + volume + RSI
    - SIDEWAYS: Support bounce + RSI oversold
    - DOWNTREND: Very selective or no trade

    Per-stock params from optimizer.
    All params optimizable — nothing hardcoded.
    """

    name    = "HalalMultiPhase"
    version = "1.0"

    def generate_signals(self, data: pd.DataFrame, symbol: str, is_backtest: bool = False, **kwargs) -> list:
        if len(data) < 50:
            return []

        phase = detect_market_phase(data, symbol)
        if not isinstance(phase, str) or phase not in VALID_PHASES:
            phase = "SIDEWAYS"

        # [PHASE-FIX] Optimization-driven phase gate: is phase me trade karna
        # is stock ke liye optimizer-proven hai ya nahi. Block hua to signal
        # generate hi nahi hote — har cycle ka audit spam rokne ke liye din
        # me ek baar log hota hai.
        allowed, gate_reason = is_phase_trade_allowed(symbol, phase)
        if not allowed:
            logger.debug(f"{symbol}: {phase} phase gated — {gate_reason}")
            _log_phase_gate_once(symbol, phase, gate_reason)
            return []

        # Per-stock params
        ema_fast    = get_param(symbol, "ema_fast",       20)
        ema_slow    = get_param(symbol, "ema_slow",       50)
        rsi_period  = get_param(symbol, "rsi_period",     14)
        rsi_os      = get_param(symbol, "rsi_oversold",   35)
        vol_mult       = get_param(symbol, "volume_mult",    1.5)
        phase_tool_key = f"tool_{phase.lower()}"
        signal_gen     = get_param(symbol, phase_tool_key, get_param(symbol, "signal_generator", "ema_cross"))

        signals = []

        # FIX-09: Optimized tool-based signal path
        # Optimizer decides which tool works best.
        # If no recent signal from optimized tool, fallback to old phase logic.
        try:
            if signal_gen in get_optimizer_signal_generators():
                params = {
                    "ema_fast": get_param(symbol, "ema_fast", 20),
                    "ema_slow": get_param(symbol, "ema_slow", 50),
                    "rsi_period": get_param(symbol, "rsi_period", 14),
                    "rsi_oversold": get_param(symbol, "rsi_oversold", 35),
                    "volume_mult": get_param(symbol, "volume_mult", 1.5),
                    "breakout_lookback": get_param(symbol, "breakout_lookback", 20),
                    "support_lookback": get_param(symbol, "support_lookback", 20),
                    "bb_period": get_param(symbol, "bb_period", 20),
                    "bb_std": get_param(symbol, "bb_std", 2.0),
                    # [PHASE-FIX] Connors RSI-2 tool params — defaults are
                    # the verified method's canonical constants (Connors &
                    # Alvarez 2009); optimizer tunes these per stock.
                    "connors_rsi2_oversold": get_param(symbol, "connors_rsi2_oversold", PARAMS.get("connors_rsi2_oversold", 10.0)),
                    "connors_crash_sma_period": get_param(symbol, "connors_crash_sma_period", PARAMS.get("connors_crash_sma_period", 200)),
                    "support_band_mult": get_param(symbol, "support_band_mult", PARAMS.get("support_band_mult", 1.01)),
                    "vwap_rsi_max": get_param(symbol, "vwap_rsi_max", PARAMS.get("vwap_rsi_max", 60.0)),
                    # [TOOL-PARITY FIX] Advanced tools (rsi_divergence, volume_divergence,
                    # candle_volume, mtf_composite) ke optimizer-tuned params — live path
                    # me pass (backtest == live parity; pehle sirf defaults milte the)
                    "divergence_lookback": get_param(symbol, "divergence_lookback", PARAMS.get("divergence_lookback", 10)),
                    "rsi_tolerance": get_param(symbol, "rsi_tolerance", PARAMS.get("rsi_tolerance", 5.0)),
                    "volume_lookback": get_param(symbol, "volume_lookback", PARAMS.get("volume_lookback", 10)),
                    "volume_threshold": get_param(symbol, "volume_threshold", PARAMS.get("volume_threshold", 0.7)),
                    "candle_size_threshold": get_param(symbol, "candle_size_threshold", PARAMS.get("candle_size_threshold", 0.5)),
                    "volume_spike_threshold": get_param(symbol, "volume_spike_threshold", PARAMS.get("volume_spike_threshold", 1.5)),
                    "mtf_min_score": get_param(symbol, "mtf_min_score", PARAMS.get("mtf_min_score", 3)),
                    "selected_tools": get_param(symbol, "selected_tools", [signal_gen]),
                    "tool_vote_threshold": get_param(symbol, "tool_vote_threshold", 1),
                }
                opt_signals = make_live_signals(data, symbol, params, signal_gen, phase, is_backtest=is_backtest)
                for s in opt_signals:
                    s["phase"] = phase
                return filter_signals_by_macro_context(
                    data, symbol, opt_signals,
                    is_backtest=is_backtest,
                    phase_hint=phase,
                )
        except Exception as e:
            from utils import append_log
            from config import AUDIT_LOG_FILE
            append_log(AUDIT_LOG_FILE, f"SIGNAL GEN ERROR ({symbol}): {e} (Fail-Closed)")
            return []

        if phase == "UPTREND":
            signals = self._uptrend_signals(data, symbol, ema_fast, ema_slow,
                                             rsi_period, rsi_os, vol_mult)
        elif phase == "SIDEWAYS":
            signals = self._sideways_signals(data, symbol, rsi_period, rsi_os)
        elif phase == "DOWNTREND":
            signals = self._downtrend_signals(data, symbol, rsi_period, rsi_os)

        # Add phase info
        for s in signals:
            s["phase"] = phase

        return filter_signals_by_macro_context(
            data, symbol, signals,
            is_backtest=is_backtest,
            phase_hint=phase,
        )

    def _uptrend_signals(self, data, symbol, ema_fast, ema_slow,
                          rsi_period, rsi_os, vol_mult) -> list:
        """
        [OVERRIDE 4 — user-authorized architectural pivot] UPTREND engine:
        Mark Minervini's Trend Template (source: "Trade Like a Stock Market
        Wizard", 2013) as the QUALIFYING FILTER — a stock must pass all 8
        criteria before any entry is even considered — with an EMA-cross +
        volume-expansion breakout as the specific ENTRY TRIGGER within
        qualified stocks. This mirrors how Minervini himself describes using
        the template: it identifies WHICH stocks are candidates for a
        proper base breakout, it is not itself an entry signal.

        The 8 Trend Template criteria (all must be true):
          1. Price > 150-day SMA AND Price > 200-day SMA
          2. 150-day SMA > 200-day SMA
          3. 200-day SMA trending up for at least the last month (~21 trading days)
          4. 50-day SMA > 150-day SMA > 200-day SMA
          5. Price > 50-day SMA
          6. Price is at least 30% above its 52-week low
          7. Price is within 25% of its 52-week high
          8. Relative Strength proxy (see honest limitation note below)

        [Honest limitation, documented per this audit's own standard of not
        overclaiming method fidelity]: criterion 8 in Minervini's own
        practice is an IBD-style RS Rating — a percentile rank of a stock's
        price performance against the ENTIRE market (thousands of stocks).
        This function only has one stock's own OHLCV data available, not a
        cross-sectional universe, so true percentile ranking isn't
        computable here. As a documented proxy, this uses the stock's own
        trailing 6-month (126 trading day) return against a minimum
        threshold (`min_rs_return_pct`, owner-adjustable) — a reasonable
        but NOT equivalent substitute for genuine cross-sectional RS
        ranking. If true RS ranking is wanted later, it would need a
        separate universe-wide scoring pass (similar to how
        sector_strength.py already ranks sectors), not a per-symbol change.

        Needs ~200+ trading days of history for SMA200/52-week calculations
        — returns no signals (fails closed) if insufficient history exists,
        same convention as this codebase's other "insufficient data" gates.
        """
        if len(data) < 210:
            return []

        sma50  = calc_sma(data, 50)
        sma150 = calc_sma(data, 150)
        sma200 = calc_sma(data, 200)
        fast = calc_ema(data, ema_fast)
        slow = calc_ema(data, ema_slow)
        rsi  = calc_rsi(data, rsi_period)

        min_rs_return_pct = float(get_param(symbol, "min_rs_return_pct", 15.0))

        signals = []
        for i in range(200, len(data)):
            price = float(data["close"].iloc[i])

            # Criteria 1, 2, 4, 5 — moving average stack
            crit_1 = price > sma150.iloc[i] and price > sma200.iloc[i]
            crit_2 = sma150.iloc[i] > sma200.iloc[i]
            crit_4 = sma50.iloc[i] > sma150.iloc[i] > sma200.iloc[i]
            crit_5 = price > sma50.iloc[i]

            # Criterion 3 — 200-day SMA trending up for ~1 month
            crit_3 = sma200.iloc[i] > sma200.iloc[i - 21]

            # Criteria 6, 7 — 52-week (252 trading day) range position
            lookback_252 = data["close"].iloc[max(0, i - 251):i + 1]
            week52_low = float(lookback_252.min())
            week52_high = float(lookback_252.max())
            crit_6 = price >= week52_low * float(PARAMS.get("minervini_52w_low_mult", 1.30))
            crit_7 = price >= week52_high * float(PARAMS.get("minervini_52w_high_mult", 0.75))

            # Criterion 8 — RS proxy (documented limitation above)
            lookback_start_idx = max(0, i - 126)
            trailing_return_pct = ((price - float(data["close"].iloc[lookback_start_idx])) /
                                    float(data["close"].iloc[lookback_start_idx]) * 100.0) if data["close"].iloc[lookback_start_idx] > 0 else 0.0
            crit_8 = trailing_return_pct >= min_rs_return_pct

            trend_template_pass = crit_1 and crit_2 and crit_3 and crit_4 and crit_5 and crit_6 and crit_7 and crit_8
            if not trend_template_pass:
                continue

            # Entry trigger: EMA-cross breakout + volume expansion, WITHIN
            # trend-template-qualified stocks only.
            ema_cross  = fast.iloc[i] > slow.iloc[i] and fast.iloc[i-1] <= slow.iloc[i-1]
            rsi_ok     = rsi.iloc[i] < float(get_param(symbol, "rsi_overbought", 60))
            vol_ok     = is_volume_confirmed(data, i, vol_mult)

            if ema_cross and rsi_ok and vol_ok:
                entry = round(float(data["close"].iloc[i]), 2)  # [OVERRIDE 2 precision fix] round BEFORE computing risk/reward, else RR drifts off exactly-1.5
                # [OVERRIDE 1 — user-authorized architectural pivot] SL is now
                # STRICTLY the low of the entry candle — no ATR-based SL, no
                # trailing-stop logic downstream (see forever_order_manager.py).
                sl = round(float(data["low"].iloc[i]), 2)
                # OWNER CONTRACT: TP/lock target is fixed at exactly 1.8R; RR is not optimized. Exit toolkit ke hybrid/
                # ratchet isko lock karke trail karta hai (uncapped profit);
                # trail na ho paye to min profit yahi booked rehta hai.
                risk = entry - sl
                rr = float(get_param(symbol, "min_reward_risk", PARAMS.get("min_reward_risk", 1.8)))
                tp1 = round(entry + risk * rr, 2) if risk > 0 else None
                if tp1 is None:
                    continue  # entry candle's low == entry price, no valid risk to size off — skip
                signals.append({
                    "action":      "BUY",
                    "entry_price": entry,
                    "sl_price":    sl,
                    "tp1_price":   tp1,
                    "reason":      f"UPTREND MINERVINI_TREND_TEMPLATE+BREAKOUT RSI={rsi.iloc[i]:.0f} RS_RET={trailing_return_pct:.1f}%",
                    "entry_idx":   i,
                    "signal_score": round(min(1.0, max(0.3, trailing_return_pct / 100.0)), 2),
                })
        return signals

    def _sideways_signals(self, data, symbol,
                           rsi_period, rsi_os) -> list:
        """
        [OVERRIDE 4 — user-authorized architectural pivot] SIDEWAYS/mild-
        downtrend engine: Larry Connors' 2-period RSI pullback method
        (source: Connors & Alvarez, "Short Term Trading Strategies That
        Work", 2009) — buys extreme oversold dips, but ONLY above a
        long-term crash-protection SMA (200-day), so this never fires
        during a genuine structural downtrend, only a pullback within a
        market that's still fundamentally intact.

        Rules (literal Connors method):
          1. Price > 200-day SMA (long-term crash-protection filter)
          2. 2-period RSI < oversold threshold (extreme short-term oversold
             — Connors' own research used <5 for the strict "power" variant
             and up to <10 for a more frequent variant; owner-adjustable)

        Entry/exit pricing (SL/TP) follows this pivot's global Override
        1+2 rules (candle-low SL, 1:1.8 RR lock then uncapped trailing) rather than Connors'
        own original exit rule (RSI(2) crossing back above ~65-70) — per
        the global QASWA exit contract: candle-low SL and optimizer-selected
        RR with a hard minimum of 1.8R, followed by uncapped trailing.

        Needs 200+ days of history for the crash-protection SMA — fails
        closed (no signals) if insufficient, same convention as elsewhere.
        """
        if len(data) < 200:
            return []

        rsi2 = calc_rsi(data, 2)  # literal Connors 2-period RSI
        sma200 = calc_sma(data, 200)
        rsi2_oversold = float(get_param(symbol, "connors_rsi2_oversold", 10.0))

        signals = []
        for i in range(200, len(data)):
            price = float(data["close"].iloc[i])
            above_crash_protection_sma = price > sma200.iloc[i]
            extreme_oversold = rsi2.iloc[i] < rsi2_oversold

            if above_crash_protection_sma and extreme_oversold:
                entry = round(price, 2)  # [OVERRIDE 2 precision fix] round BEFORE computing risk/reward
                # [OVERRIDE 1] SL = low of entry candle (strict, no ATR/trailing)
                sl = round(float(data["low"].iloc[i]), 2)
                # v5.7: TP = min-RR target (fixed 1.8R)
                risk = entry - sl
                rr = float(get_param(symbol, "min_reward_risk", PARAMS.get("min_reward_risk", 1.8)))
                tp1 = round(entry + risk * rr, 2) if risk > 0 else None
                if tp1 is None:
                    continue
                signals.append({
                    "action":      "BUY",
                    "entry_price": entry,
                    "sl_price":    sl,
                    "tp1_price":   tp1,
                    "reason":      f"SIDEWAYS CONNORS_RSI2={rsi2.iloc[i]:.1f} (above SMA200)",
                    "entry_idx":   i,
                    # AI-DOS LOGIC-001 fix: connors_rsi2_oversold is owner/per-stock
                    # configurable (get_param); a 0 setting must not crash signal scoring.
                    "signal_score": round(min(1.0, max(0.3, safe_div(rsi2_oversold - rsi2.iloc[i], rsi2_oversold, default=0.3))), 2),
                })
        return signals

    def _downtrend_signals(self, data, symbol,
                            rsi_period, rsi_os) -> list:
        """
        [OVERRIDE 4 — user-authorized architectural pivot] DOWNTREND engine.
        Per the pivot spec, this phase splits into two distinct behaviors:

          - "Severe Crash / Extreme Downtrend": blocks ALL new entries
            completely (Cash Preservation Mode) — implemented here as the
            market-wide HMM regime (market_regime.py, Hamilton 1989) being
            BEAR. This is a MARKET-wide signal, distinct from this
            function's own per-stock DOWNTREND phase classification
            (ADX-based, see detect_market_phase()) — a single stock can be
            in its own "downtrend phase" while the overall market regime is
            not BEAR, and vice versa.
          - "Mild Downtrend": everything else — delegates to the exact same
            literal Larry Connors 2-period RSI method as _sideways_signals()
            (single source of truth, not a duplicated copy), since the
            pivot spec explicitly groups "Sideways / Mild Downtrend" under
            the same Priority 2 engine.

        Fails closed (no signals) if the regime check itself fails — a
        genuine market crash is exactly the wrong moment to silently keep
        trading on missing/broken regime data.
        """
        try:
            from market_regime import get_market_regime
            regime = get_market_regime(force_refresh=False)
            regime_label = regime.get("regime") if isinstance(regime, dict) else regime
        except (ImportError, RuntimeError, ValueError, TypeError) as e:
            logger.warning(f"_downtrend_signals: regime check failed for {symbol}: {type(e).__name__}: {e} — Fail-Closed (blocking, treating as severe crash)")
            return []

        if regime_label == "BEAR" and bool(PARAMS.get("downtrend_bear_regime_block", True)):
            # Severe Crash / Extreme Downtrend — Cash Preservation Mode.
            # Config-driven policy: downtrend_bear_regime_block=False pe
            # per-stock phase gate (optimization edge proof) hi decide karega.
            return []

        # Mild Downtrend — same literal Connors 2-period RSI method as sideways.
        return self._sideways_signals(data, symbol, rsi_period, rsi_os)

    def backtest_on_data(self, data: pd.DataFrame, symbol: str) -> dict:
        """Full backtest for this strategy on historical data."""
        from config import PARAMS
        cost_pct   = PARAMS["trading_cost_pct"] / 100
        sl_raw  = get_param(symbol, "sl_pct", None)
        tp1_raw = get_param(symbol, "tp1_pct", None)
        if sl_raw is None or tp1_raw is None:
            return {"symbol": symbol, "valid": False, "error": "Optimized sl_pct or tp1_pct missing"}
        sl_pct  = sl_raw / 100
        tp1_pct = tp1_raw / 100
        trail_mult = get_param(symbol, "trail_multiplier", 1.5)

        signals     = self.generate_signals(data, symbol, is_backtest=True)
        buy_signals = [s for s in signals if s["action"] == "BUY"]

        if not buy_signals:
            return {"symbol": symbol, "valid": False, "error": "No signals"}

        trades  = []
        # Owner engine: validator_reference_capital (capital_drawdown_manager)
        capital = float(PARAMS["validator_reference_capital"])  # Strict owner value — no fallback
        equity  = []

        for sig in buy_signals:
            entry_idx   = sig.get("entry_idx", 0)
            entry_price = sig["entry_price"]
            sl_price    = sig["sl_price"]
            tp1_price   = sig["tp1_price"]

            if entry_idx >= len(data) - 1:
                continue

            # v5.4 UNIFIED EXIT TOOLKIT — backtest == optimizer == live ek hi
            # engine (exit_engine). exit_mode per-stock optimizer select karta
            # hai; profit-lock guarantee (lalach-safe).
            from exit_engine import init_state, step
            st = init_state({
                             "exit_mode": get_param(symbol, "exit_mode", "hybrid"),
                             "tp1_pct": get_param(symbol, "tp1_pct", 3.0),
                             "trail_multiplier": trail_mult,
                             "trail_activation_pct": get_param(symbol, "trail_activation_pct", 2.0),
                             "profit_lock_pct": get_param(symbol, "profit_lock_pct", 1.0),
                             "ratchet_step_pct": get_param(symbol, "ratchet_step_pct", 1.5)},
                            entry_price, sl_price)
            exit_price= None
            actual_exit_idx = None

            for j in range(entry_idx + 1, min(entry_idx + 60, len(data))):
                bar_high = float(data["high"].iloc[j])
                bar_low  = float(data["low"].iloc[j])
                bar_close= float(data["close"].iloc[j])

                atr_period = int(get_param(symbol, "atr_period", 14))
                atr_v     = float(calc_atr(data, atr_period).iloc[j])

                if step(st, bar_high, bar_low, bar_close, atr_v):
                    exit_price = st["exit_price"]
                    actual_exit_idx = j
                    break

            if exit_price is None:
                actual_exit_idx = min(entry_idx + 60, len(data) - 1)
                exit_price = float(data["close"].iloc[actual_exit_idx])

            # AI-DOS LOGIC-001 fix: guard against a zero/corrupted entry_price
            # in backtest replay data.
            gross = safe_div(exit_price - entry_price, entry_price, default=0.0)
            net   = gross - cost_pct
            capital *= (1 + net)
            equity.append(capital)

            trade_bars = data.iloc[entry_idx:actual_exit_idx + 1]
            price_dd   = calculate_price_dd_during_trade(trade_bars, entry_price)

            trades.append({
                "entry_price":   entry_price,
                "exit_price":    exit_price,
                "return_pct":    round(gross * 100, 2),
                "net_return_pct":round(net * 100, 2),
                "price_dd":      price_dd,
                "entry_idx":     entry_idx,
                "exit_idx":      actual_exit_idx,
                "phase":         sig.get("phase", "UNKNOWN"),
            })

        # [BACKTEST-PARITY] Live-identical parity chain (R1 vol-mult, R2 stage,
        # R3 Gate A/B economics, R4 survival circuit) — backtest results live
        # ke close rehne ke liye. Fail-open: helper error → exact old behavior.
        try:
            from parity_engine import run_parity_equity
            _parity = run_parity_equity(
                trades, data, symbol,
                start_capital=float(PARAMS["validator_reference_capital"]),
                max_slots=int(PARAMS.get("max_slots", 8)),
                tp_return_pct=float(get_param(symbol, "tp1_pct", 3.0) or 3.0),
            )
            if _parity is not None:
                kept = _parity.get("kept_trades", trades)
                if len(kept) != len(trades):
                    append_log(AUDIT_LOG_FILE,
                               f"PARITY {symbol}: {len(trades) - len(kept)}/{len(trades)} "
                               f"trades excluded (Gate A/B / circuit) — metrics on kept trades only")
                trades = kept
                capital = _parity["final_capital"]
                equity = _parity["equity"]
        except Exception as e:
            logger.debug(f"backtest_on_data: parity skipped for {symbol}: {type(e).__name__}: {e}")

        if not trades:
            return {"symbol": symbol, "valid": False, "error": "No completed trades"}

        wins     = [t for t in trades if t["net_return_pct"] > 0]
        losses   = [t for t in trades if t["net_return_pct"] <= 0]
        win_rate = round(len(wins) / len(trades) * 100, 1)

        avg_win  = np.mean([t["net_return_pct"] for t in wins])  if wins   else 0
        avg_loss = np.mean([t["net_return_pct"] for t in losses]) if losses else 0
        pf       = round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0

        equity_s = pd.Series(equity)
        roll_max = equity_s.cummax()
        dd_s     = (equity_s - roll_max) / roll_max * 100
        max_dd   = round(float(dd_s.min()), 2)

        price_dd_vals = [t["price_dd"] for t in trades]
        price_max_dd  = round(float(min(price_dd_vals)), 2) if price_dd_vals else 0

        ref_cap = float(PARAMS["validator_reference_capital"])  # Strict owner value — no fallback
        total_return = round((capital - ref_cap) / ref_cap * 100, 2)
        recovery_f   = round(total_return / abs(max_dd), 2) if max_dd != 0 else 0

        avg_ret = round(float(np.mean([t["net_return_pct"] for t in trades])), 2)

        returns = pd.Series([t["net_return_pct"] for t in trades])
        sharpe  = round(float(returns.mean() / (returns.std() + 1e-10)), 2)

        return {
            "symbol":                  symbol,
            "valid":                   True,
            "win_rate_pct":            win_rate,
            "total_trades":            len(trades),
            "avg_return_pct":          avg_ret,
            "profit_factor":           pf,
            "recovery_factor":         recovery_f,
            "sharpe":                  sharpe,
            "price_max_drawdown_pct":  price_max_dd,
            "portfolio_max_drawdown_pct": max_dd,
            "trades_list":             trades,
        }


# ─────────────────────────────────────────────
# PRICE-BASED DD CALCULATOR
# Same formula in backtest AND live — apples to apples
# ─────────────────────────────────────────────

def calculate_price_dd_during_trade(bars: pd.DataFrame,
                                     entry_price: float) -> float:
    high_watermark = entry_price
    worst_dd       = 0.0

    for _, bar in bars.iterrows():
        high_watermark = max(high_watermark, bar["high"])
        # AI-DOS LOGIC-001 fix: entry_price (the initial high_watermark) could
        # be 0 on corrupted replay data.
        dd             = safe_div(bar["low"] - high_watermark, high_watermark, default=0.0) * 100
        worst_dd       = min(worst_dd, dd)

    return worst_dd


# ─────────────────────────────────────────────
# STRATEGY REGISTRY
# ─────────────────────────────────────────────

STRATEGY_REGISTRY: dict  = {}
ACTIVE_STRATEGY: BaseStrategy = None


def register_strategy(strategy: BaseStrategy):
    STRATEGY_REGISTRY[strategy.name] = strategy


def set_active_strategy(name: str):
    global ACTIVE_STRATEGY
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"Strategy '{name}' not registered.")
    ACTIVE_STRATEGY = STRATEGY_REGISTRY[name]
    # New strategy = fresh backtest compulsory
    import os
    from config import BACKTEST_RESULTS_FILE
    if os.path.exists(BACKTEST_RESULTS_FILE):
        os.remove(BACKTEST_RESULTS_FILE)


def get_active_strategy() -> BaseStrategy:
    global ACTIVE_STRATEGY
    if ACTIVE_STRATEGY is None:
        # Auto-register and set default
        default = HalalMultiPhaseStrategy()
        register_strategy(default)
        ACTIVE_STRATEGY = default
    return ACTIVE_STRATEGY


# Auto-register default strategy on import
_default_strategy = HalalMultiPhaseStrategy()
register_strategy(_default_strategy)
ACTIVE_STRATEGY = _default_strategy
