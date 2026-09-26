"""
strategy_tools.py — FIX-09 Optimizable signal tools

Tools are not final strategy by themselves.
Optimizer compares tools and chooses best per stock/phase later.

All tools are long-only and CNC-compatible.
"""

import logging
import pandas as pd

logger = logging.getLogger(__name__)



TOOL_NAMES = [
    "ema_cross",
    "rsi_ema",
    "breakout",
    "support_bounce",
    "vwap_bounce",
    "bollinger_reversion",
    "connors_rsi2",
    "rsi_divergence",
    "volume_divergence",
    "candle_volume",
    "mtf_composite",
]


def _get(params: dict, key: str, default):
    try:
        return params.get(key, default)
    except (TypeError, AttributeError) as e:
        logger.debug(f"_get: Param lookup failed for {key}: {type(e).__name__}: {e}")
        return default


def calc_rsi(data: pd.DataFrame, period: int = 14) -> pd.Series:
    # [PHD-FIX F4] Wilder smoothing — canonical RSI (Wilder 1978);
    # Connors RSI-2 isi definition pe based hai.
    delta = data["close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    return 100 - (100 / (1 + rs))


def calc_atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
    # [PHD-FIX F4 completion] Wilder smoothing (alpha=1/period) — canonical
    # ATR (Wilder 1978), same standard already applied to calc_rsi and the
    # ADX-internal ATR in strategy.calculate_adx(). Was previously
    # ewm(span=period) — inconsistent with this codebase's own standard.
    tr = pd.concat([
        data["high"] - data["low"],
        (data["high"] - data["close"].shift()).abs(),
        (data["low"] - data["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


def calc_vwap(data: pd.DataFrame) -> pd.Series:
    """[AUDIT F4 CORRECTION, 2026-09-16] Despite the name, this is NOT a
    session VWAP (which resets its cumulative sum every trading day).
    `data` here is a multi-bar (daily-candle) window with no per-day
    reset, so this is a cumulative volume-weighted average over the
    whole window passed in -- i.e. a slow-moving anchored average, not
    genuine intraday VWAP mean-reversion. `opt_vwap_bounce()` below is
    therefore more accurately a slow-MA crossover signal than a VWAP
    bounce. Left as-is (not renamed / not behavior-changed): the
    "vwap_bounce" tool name is referenced by saved per-stock optimizer
    state and TOOL_NAMES, and this signal's math itself is unaffected
    by the naming -- only the docstring/comment was wrong."""
    return (data["close"] * data["volume"]).cumsum() / (data["volume"].cumsum() + 1e-10)


def _append_live_signal(signals: list, data: pd.DataFrame, i: int, params: dict, reason: str):
    entry = round(float(data["close"].iloc[i]), 2)  # [OVERRIDE 2 precision fix] round BEFORE computing risk/reward, preserving exact configured RR lock
    # [OVERRIDE 1 — user-authorized architectural pivot] SL is now STRICTLY
    # the low of the entry candle. The optimizer's sl_pct/tp1_pct/
    # min_reward_risk params are intentionally NOT used for risk sizing
    # anymore — Optuna only tunes entry conditions (which tool/params
    # trigger a signal), never SL or R:R. This is the single choke-point
    # used by every optimizer-selected tool (breakout, support-bounce,
    # Bollinger, etc. — see TOOL_NAMES), so fixing it here covers all of them.
    sl = round(float(data["low"].iloc[i]), 2)
    # OWNER CONTRACT: TP/lock target is fixed at exactly 1.8R; RR is not optimized.
    rr = 1.8
    risk = entry - sl
    if risk <= 0:
        return  # entry candle's low == entry price, no valid risk to size off
    tp1 = round(entry + risk * rr, 2)

    signals.append({
        "action": "BUY",
        "entry_price": entry,
        "sl_price": sl,
        "tp1_price": tp1,
        "reason": reason,
        "entry_idx": i,
    })


# ─────────────────────────────────────────────
# Optimizer signal generators: return idx only
# ─────────────────────────────────────────────

def opt_ema_cross(data: pd.DataFrame, params: dict) -> list:
    fast_n = int(_get(params, "ema_fast", 20))
    slow_n = int(_get(params, "ema_slow", 50))
    fast = data["close"].ewm(span=fast_n).mean()
    slow = data["close"].ewm(span=slow_n).mean()
    signals = []
    for i in range(1, len(data)):
        if fast.iloc[i] > slow.iloc[i] and fast.iloc[i-1] <= slow.iloc[i-1]:
            signals.append({"idx": i, "action": "BUY"})
    return signals


def opt_rsi_ema(data: pd.DataFrame, params: dict) -> list:
    slow_n = int(_get(params, "ema_slow", 50))
    rsi_n = int(_get(params, "rsi_period", 14))
    rsi_os = float(_get(params, "rsi_oversold", 35))
    ema = data["close"].ewm(span=slow_n).mean()
    rsi = calc_rsi(data, rsi_n)
    signals = []
    for i in range(1, len(data)):
        if data["close"].iloc[i] > ema.iloc[i] and rsi.iloc[i] < rsi_os:
            signals.append({"idx": i, "action": "BUY"})
    return signals


def opt_breakout(data: pd.DataFrame, params: dict) -> list:
    lookback = int(_get(params, "breakout_lookback", 20))
    vol_mult = float(_get(params, "volume_mult", 1.5))
    signals = []
    for i in range(lookback, len(data)):
        recent_high = data["high"].iloc[i-lookback:i].max()
        avg_vol = data["volume"].iloc[i-lookback:i].mean()
        if data["close"].iloc[i] > recent_high and data["volume"].iloc[i] > avg_vol * vol_mult:
            signals.append({"idx": i, "action": "BUY"})
    return signals


def opt_support_bounce(data: pd.DataFrame, params: dict) -> list:
    lookback = int(_get(params, "support_lookback", 20))
    rsi_n = int(_get(params, "rsi_period", 14))
    rsi_os = float(_get(params, "rsi_oversold", 35))
    rsi = calc_rsi(data, rsi_n)
    support = data["low"].rolling(lookback).min()
    signals = []
    for i in range(lookback, len(data)):
        near_support = data["close"].iloc[i] <= support.iloc[i] * float(_get(params, "support_band_mult", 1.01))
        if near_support and rsi.iloc[i] < rsi_os:
            signals.append({"idx": i, "action": "BUY"})
    return signals


def opt_vwap_bounce(data: pd.DataFrame, params: dict) -> list:
    """See calc_vwap()'s docstring above [AUDIT F4]: this crosses price
    over a cumulative multi-day volume-weighted average, not a genuine
    session VWAP -- name kept for optimizer/state backward-compatibility."""
    rsi_n = int(_get(params, "rsi_period", 14))
    rsi = calc_rsi(data, rsi_n)
    vwap = calc_vwap(data)
    signals = []
    for i in range(1, len(data)):
        crossed_up = data["close"].iloc[i] > vwap.iloc[i] and data["close"].iloc[i-1] <= vwap.iloc[i-1]
        if crossed_up and rsi.iloc[i] < float(_get(params, "vwap_rsi_max", 60.0)):
            signals.append({"idx": i, "action": "BUY"})
    return signals


def opt_bollinger_reversion(data: pd.DataFrame, params: dict) -> list:
    period = int(_get(params, "bb_period", None))
    std_mult = float(_get(params, "bb_std", None))
    rsi_n = int(_get(params, "rsi_period", None))
    rsi_os = float(_get(params, "rsi_oversold", None))
    
    if period is None or std_mult is None or rsi_n is None or rsi_os is None:
        return []  # Block trade if optimized params missing

    mid = data["close"].rolling(period).mean()
    std = data["close"].rolling(period).std()
    lower = mid - std_mult * std
    rsi = calc_rsi(data, rsi_n)

    signals = []
    for i in range(period, len(data)):
        if data["close"].iloc[i] <= lower.iloc[i] and rsi.iloc[i] < rsi_os:
            signals.append({"idx": i, "action": "BUY"})
    return signals


def opt_connors_rsi2(data: pd.DataFrame, params: dict) -> list:
    """
    [PHASE-FIX] Connors 2-period RSI pullback tool — verified long-only
    method for SIDEWAYS / mild-DOWNTREND phases
    (Connors & Alvarez, "Short Term Trading Strategies That Work", 2009).

    Rules (literal method):
      1. Price > crash-protection SMA (`connors_crash_sma_period`,
         canonical 200 — long-term intact filter)
      2. RSI(2) < oversold line (`connors_rsi2_oversold`,
         canonical < 10; optimizer tunes 5-15 per stock)

    Fail-closed: optimized params missing → no signals.
    """
    oversold = _get(params, "connors_rsi2_oversold", None)
    sma_period = _get(params, "connors_crash_sma_period", None)
    if oversold is None or sma_period is None:
        return []  # Block trade if optimized params missing

    oversold = float(oversold)
    sma_period = int(sma_period)
    rsi2 = calc_rsi(data, 2)  # literal Connors 2-period RSI
    sma_crash = data["close"].rolling(sma_period).mean()

    signals = []
    for i in range(sma_period, len(data)):
        above_crash_protection = data["close"].iloc[i] > sma_crash.iloc[i]
        extreme_oversold = rsi2.iloc[i] < oversold
        if above_crash_protection and extreme_oversold:
            signals.append({"idx": i, "action": "BUY"})
    return signals


def opt_rsi_divergence(data: pd.DataFrame, params: dict) -> list:
    """
    RSI Divergence — Industry verified reversal signal.
    
    Bullish Divergence:
      Price makes Lower Low, RSI makes Higher Low
      → Sellers weak, reversal likely
    
    Sources:
    - TradingView: "RSI Divergence Pro+ Volume"
    - MQL5: "The Real RSI Divergence Hunter"
    - SaintQuant: "AI crypto trading bots incorporate RSI-based features"
    
    Optimized parameters:
    - rsi_period: RSI calculation period
    - divergence_lookback: Bars to look back for divergence
    - rsi_tolerance: RSI difference tolerance
    """
    rsi_n = int(_get(params, "rsi_period", 14))
    lookback = int(_get(params, "divergence_lookback", 10))
    tolerance = float(_get(params, "rsi_tolerance", 5.0))
    
    rsi = calc_rsi(data, rsi_n)
    signals = []
    
    for i in range(lookback * 2, len(data)):
        # Find swing lows in price
        price_lows = []
        rsi_lows = []
        
        # [PHD-FIX look-ahead] upper bound is i (exclusive), not i+1 — a swing
        # low at bar j needs bar j+1's low to confirm; if j==i ("today") that
        # would require tomorrow's data, which doesn't exist yet at decision
        # time. Backtest previously had the full future array loaded so this
        # silently leaked; live was accidentally safe because "today" is
        # always the last row and the len(data)-1 guard already excluded it.
        for j in range(max(0, i - lookback * 2), i):
            if j > 0 and j < len(data) - 1:
                if data["low"].iloc[j] < data["low"].iloc[j-1] and data["low"].iloc[j] < data["low"].iloc[j+1]:
                    price_lows.append((j, data["low"].iloc[j]))
                    rsi_lows.append((j, rsi.iloc[j]))
        
        # Check for bullish divergence
        if len(price_lows) >= 2:
            # Price: Lower Low
            if price_lows[-1][1] < price_lows[-2][1]:
                # RSI: Higher Low (divergence)
                if rsi_lows[-1][1] > rsi_lows[-2][1] + tolerance:
                    signals.append({"idx": i, "action": "BUY"})
    
    return signals


def opt_volume_divergence(data: pd.DataFrame, params: dict) -> list:
    """
    Volume Divergence — Smart money tracking.
    
    Bullish Volume Divergence:
      Price makes Lower Low, Volume decreases
      → Sellers weak, institutional accumulation
    
    Sources:
    - TradingView: "RSI Divergence Pro+ Volume"
    - Professional trading bots: Volume confirmation
    
    Optimized parameters:
    - volume_lookback: Bars to look back for volume analysis
    - volume_threshold: Volume decrease threshold
    """
    lookback = int(_get(params, "volume_lookback", 10))
    threshold = float(_get(params, "volume_threshold", 0.7))
    
    signals = []
    
    for i in range(lookback * 2, len(data)):
        # Find swing lows in price
        price_lows = []
        volume_lows = []
        
        # [PHD-FIX look-ahead] see opt_rsi_divergence for full explanation —
        # exclude j==i ("today") since confirming it as a swing low needs
        # tomorrow's low, unavailable at real decision time.
        for j in range(max(0, i - lookback * 2), i):
            if j > 0 and j < len(data) - 1:
                if data["low"].iloc[j] < data["low"].iloc[j-1] and data["low"].iloc[j] < data["low"].iloc[j+1]:
                    price_lows.append((j, data["low"].iloc[j]))
                    volume_lows.append((j, data["volume"].iloc[j]))
        
        # Check for bullish volume divergence
        if len(price_lows) >= 2:
            # Price: Lower Low
            if price_lows[-1][1] < price_lows[-2][1]:
                # Volume: Decreasing (divergence)
                if volume_lows[-1][1] < volume_lows[-2][1] * threshold:
                    signals.append({"idx": i, "action": "BUY"})
    
    return signals


def opt_candle_volume(data: pd.DataFrame, params: dict) -> list:
    """
    Candle-Volume Analysis — Accumulation detection.
    
    Small Candle + High Volume:
      → Accumulation, smart money buying
      → Breakout likely
    
    Large Candle + Low Volume:
      → Weak move, fake breakout possible
    
    Sources:
    - Professional trading: Volume-price analysis
    - Institutional trading: Smart money tracking
    
    Optimized parameters:
    - candle_size_threshold: Candle size relative to ATR
    - volume_spike_threshold: Volume spike multiplier
    """
    atr_period = int(_get(params, "atr_period", 14))
    size_threshold = float(_get(params, "candle_size_threshold", 0.5))
    volume_threshold = float(_get(params, "volume_spike_threshold", 1.5))
    
    atr = calc_atr(data, atr_period)
    signals = []
    
    for i in range(atr_period, len(data)):
        candle_body = abs(data["close"].iloc[i] - data["open"].iloc[i])
        candle_range = data["high"].iloc[i] - data["low"].iloc[i]
        avg_volume = data["volume"].iloc[i-atr_period:i].mean()
        
        # Small candle (body < threshold * ATR)
        is_small_candle = candle_body < atr.iloc[i] * size_threshold
        
        # High volume (current > threshold * average)
        is_high_volume = data["volume"].iloc[i] > avg_volume * volume_threshold
        
        # Small candle + High volume = accumulation
        if is_small_candle and is_high_volume:
            signals.append({"idx": i, "action": "BUY"})
    
    return signals


def opt_mtf_composite(data: pd.DataFrame, params: dict) -> list:
    """
    MTF Composite Signal — Multi-Timeframe Analysis + All Advanced Concepts.
    
    Combines:
    1. RSI Divergence (reversal detection)
    2. Volume Divergence (smart money tracking)
    3. Candle-Volume (accumulation detection)
    4. Trend confirmation (EMA structure)
    5. Momentum confirmation (RSI levels)
    
    This is the MOST ADVANCED signal generator — uses multiple criteria
    for high-probability entries. Optimizer finds best combination per stock.
    
    Sources:
    - Dr. Alexander Elder: Multiple Time Frame Analysis (1986)
    - Professional trading: Multi-criteria confirmation
    - Institutional trading: Smart money tracking
    
    Optimized parameters:
    - All RSI Divergence params
    - All Volume Divergence params
    - All Candle-Volume params
    - Plus: trend_confirmation_period, momentum_threshold
    """
    # Get all optimized parameters
    rsi_n = int(_get(params, "rsi_period", 14))
    ema_fast = int(_get(params, "ema_fast", 20))
    ema_slow = int(_get(params, "ema_slow", 50))
    rsi_os = float(_get(params, "rsi_oversold", 35))
    
    # Divergence params
    div_lookback = int(_get(params, "divergence_lookback", 10))
    rsi_tol = float(_get(params, "rsi_tolerance", 5.0))
    
    # Volume params
    vol_lookback = int(_get(params, "volume_lookback", 10))
    vol_threshold = float(_get(params, "volume_threshold", 0.7))
    
    # Candle-Volume params
    atr_period = int(_get(params, "atr_period", 14))
    size_threshold = float(_get(params, "candle_size_threshold", 0.5))
    vol_spike = float(_get(params, "volume_spike_threshold", 1.5))
    
    # Calculate indicators
    rsi = calc_rsi(data, rsi_n)
    ema_f = data["close"].ewm(span=ema_fast).mean()
    ema_s = data["close"].ewm(span=ema_slow).mean()
    atr = calc_atr(data, atr_period)
    
    signals = []
    
    for i in range(max(ema_slow, div_lookback * 2, atr_period), len(data)):
        score = 0
        reasons = []
        
        # ── CRITERION 1: Trend Confirmation (EMA structure) ──
        # Price above slow EMA = uptrend
        if data["close"].iloc[i] > ema_s.iloc[i]:
            score += 1
            reasons.append("TREND_UP")
        
        # Fast EMA above slow EMA = bullish structure
        if ema_f.iloc[i] > ema_s.iloc[i]:
            score += 1
            reasons.append("EMA_BULLISH")
        
        # ── CRITERION 2: RSI Divergence ──
        # Find swing lows
        price_lows = []
        rsi_lows = []
        # [PHD-FIX look-ahead] see opt_rsi_divergence — exclude j==i ("today").
        for j in range(max(0, i - div_lookback * 2), i):
            if j > 0 and j < len(data) - 1:
                if data["low"].iloc[j] < data["low"].iloc[j-1] and data["low"].iloc[j] < data["low"].iloc[j+1]:
                    price_lows.append((j, data["low"].iloc[j]))
                    rsi_lows.append((j, rsi.iloc[j]))
        
        # Check for bullish divergence
        if len(price_lows) >= 2:
            if price_lows[-1][1] < price_lows[-2][1]:  # Price: Lower Low
                if rsi_lows[-1][1] > rsi_lows[-2][1] + rsi_tol:  # RSI: Higher Low
                    score += 2  # Divergence is strong signal
                    reasons.append("RSI_DIVERGENCE")
        
        # ── CRITERION 3: Volume Divergence ──
        if len(price_lows) >= 2:
            if price_lows[-1][1] < price_lows[-2][1]:  # Price: Lower Low
                vol_lows = []
                # [PHD-FIX look-ahead] see opt_rsi_divergence — exclude j==i ("today").
                for j in range(max(0, i - vol_lookback * 2), i):
                    if j > 0 and j < len(data) - 1:
                        if data["low"].iloc[j] < data["low"].iloc[j-1] and data["low"].iloc[j] < data["low"].iloc[j+1]:
                            vol_lows.append((j, data["volume"].iloc[j]))
                if len(vol_lows) >= 2:
                    if vol_lows[-1][1] < vol_lows[-2][1] * vol_threshold:  # Volume: Decreasing
                        score += 1
                        reasons.append("VOL_DIVERGENCE")
        
        # ── CRITERION 4: Candle-Volume Accumulation ──
        candle_body = abs(data["close"].iloc[i] - data["open"].iloc[i])
        avg_vol = data["volume"].iloc[i-atr_period:i].mean()
        
        if candle_body < atr.iloc[i] * size_threshold:  # Small candle
            if data["volume"].iloc[i] > avg_vol * vol_spike:  # High volume
                score += 1
                reasons.append("ACCUMULATION")
        
        # ── CRITERION 5: RSI Oversold ──
        if rsi.iloc[i] < rsi_os:
            score += 1
            reasons.append("RSI_OVERSOLD")
        
        # ── ENTRY DECISION ──
        # Minimum score threshold (optimized per stock)
        min_score = int(_get(params, "mtf_min_score", 3))
        
        if score >= min_score:
            signals.append({"idx": i, "action": "BUY", "score": score, "reasons": reasons})
    
    return signals


def get_optimizer_signal_generators() -> dict:
    return {
        "ema_cross": opt_ema_cross,
        "rsi_ema": opt_rsi_ema,
        "breakout": opt_breakout,
        "support_bounce": opt_support_bounce,
        "vwap_bounce": opt_vwap_bounce,
        "bollinger_reversion": opt_bollinger_reversion,
        "connors_rsi2": opt_connors_rsi2,
        "rsi_divergence": opt_rsi_divergence,
        "volume_divergence": opt_volume_divergence,
        "candle_volume": opt_candle_volume,
        "mtf_composite": opt_mtf_composite,
    }


# ─────────────────────────────────────────────
# Live signal generator: returns full trade signal
# ─────────────────────────────────────────────

def make_live_signals(data: pd.DataFrame, symbol: str, params: dict, tool: str, phase: str = "", is_backtest: bool = False) -> list:
    """Generate live/backtest trade signals from the optimizer-selected tool set.

    ``tool`` may be a single tool name or a comma-separated/list-style selection
    supplied through ``params['selected_tools']``.  The optimizer is allowed to
    select any non-empty subset of the 11 registered tools independently per
    stock/phase.  A signal is emitted when the selected tools reach the stored
    vote threshold.  This preserves the existing single-tool path when only one
    tool is selected.
    """
    if data is None or data.empty or len(data) < 50:
        return []

    registry = get_optimizer_signal_generators()
    selected = params.get("selected_tools") if isinstance(params, dict) else None
    if isinstance(selected, str):
        selected = [x.strip() for x in selected.split(",") if x.strip()]
    elif not isinstance(selected, (list, tuple)):
        selected = [tool] if tool else []
    selected = [t for t in selected if t in registry]
    if not selected:
        return []

    # Consensus threshold is optimizer output; default preserves one-tool behavior.
    try:
        threshold = int(params.get("tool_vote_threshold", 1))
    except (TypeError, ValueError):
        threshold = 1
    threshold = max(1, min(threshold, len(selected)))

    idx_votes = {}
    idx_reasons = {}
    for name in selected:
        raw = registry[name](data, params)
        for sig in raw:
            idx = sig.get("idx")
            if idx is None:
                continue
            idx_votes[idx] = idx_votes.get(idx, 0) + 1
            idx_reasons.setdefault(idx, []).append(name)

    chosen = sorted(idx for idx, votes in idx_votes.items() if votes >= threshold)
    if not is_backtest:
        last_idx = len(data) - 1
        chosen = [i for i in chosen if i in (last_idx, last_idx - 1)]

    signals = []
    tool_label = "+".join(selected)
    for i in chosen:
        _append_live_signal(
            signals, data, int(i), params,
            f"{phase} TOOLSET[{tool_label}] vote={idx_votes[i]}/{len(selected)} "
            f"contributors={','.join(idx_reasons.get(i, []))} for {symbol}".strip()
        )
    return signals
