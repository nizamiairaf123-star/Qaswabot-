"""
stock_mode_manager.py — 4 stock modes + ek mauka + recovery system
FIX-28: DD = per trade from entry, multiple trades same stock tracked independently

Modes: PROFIT / SOFT_BLOCKED / RECOVERY / HARD_BLOCKED
"""

import logging
from utils import load_json, save_json, now_ist, append_log
from config import STOCK_MODES_FILE, BACKTEST_RESULTS_FILE, PARAMS, AUDIT_LOG_FILE

logger = logging.getLogger(__name__)

MODES = {
    "PROFIT":       "Green",
    "SOFT_BLOCKED": "Yellow",
    "RECOVERY":     "Blue",
    "HARD_BLOCKED": "Red",
}


# ─────────────────────────────────────────────
# PHASE-3 PATCH (ADD-ONLY): machine-proposed constants, owner hard caps
# [Methods: buffer → Bootstrap est. error — B. Efron, 1979 |
#           recovery days → stock's own median recovery-days (custom measurement,
#           watermark metric = fund/CTA industry standard) + 5-day policy floor |
#           confirmation-window design → Follow-Through Day — W.J. O'Neil, 1988 (4–7 din)]
# SAFETY: data insufficient → dd_policy returns None → EXISTING PARAMS constants
# use hote hain (exact old behavior). Kuch remove NAHI — sirf source swap-able.
# ─────────────────────────────────────────────
def _dd_buffer(symbol: str) -> float:
    try:
        from dd_policy import suggested_buffer_pct
        res = suggested_buffer_pct(symbol)
        if res and res.get("buffer_pct") is not None:
            return float(res["buffer_pct"])
    except Exception:
        pass
    return float(PARAMS["dd_buffer_pct"])  # fallback: existing behavior


def _recovery_days(symbol: str) -> int:
    try:
        from dd_policy import suggested_recovery_days
        res = suggested_recovery_days(symbol)
        if res and res.get("recovery_days") is not None:
            return int(res["recovery_days"])
    except Exception:
        pass
    return int(PARAMS["recovery_days_wait"])  # fallback: existing behavior


def _load() -> dict:
    return load_json(STOCK_MODES_FILE, {})


def _save(data: dict):
    save_json(STOCK_MODES_FILE, data)


def get_mode(symbol: str) -> str:
    data = _load()
    return data.get(symbol, {}).get("mode", "PROFIT")


def get_stock_state(symbol: str) -> dict:
    data = _load()
    return data.get(symbol, {
        "mode":             "PROFIT",
        "mauka_used":       False,
        "mauka_available":  True,
        "high_watermark":   None,
        "soft_block_date":  None,
        "recovery_entry_date": None,
        "hard_block_reason":   None,
        # FIX-28: DD tracked per trade from entry
        # Multiple open trades same stock = each tracked independently
        # This watermark = stock-level for mode tracking only
        # Trade-level DD tracked in trade_data snapshot
    })


def _set_state(symbol: str, state: dict):
    data = _load()
    data[symbol] = state
    _save(data)


def update_watermark(symbol: str, current_price: float):
    """
    FIX-28: Stock-level watermark for mode tracking.
    Per-trade DD tracked separately in trade snapshot.
    """
    state = get_stock_state(symbol)
    wm    = state.get("high_watermark") or current_price
    state["high_watermark"] = max(wm, current_price)
    _set_state(symbol, state)


def check_and_apply_soft_block(symbol: str, current_price: float) -> bool:
    state = get_stock_state(symbol)
    if state["mode"] in ("SOFT_BLOCKED", "RECOVERY", "HARD_BLOCKED"):
        return False

    backtest_dd = _get_backtest_dd(symbol)
    if backtest_dd is None:
        return False

    wm      = state.get("high_watermark") or current_price
    live_dd = (current_price - wm) / wm * 100
    # PHASE-3 (ADD-ONLY): machine-proposed buffer within caps; fallback = old PARAMS value
    threshold = backtest_dd - _dd_buffer(symbol)

    if live_dd <= threshold:
        state["mode"]            = "SOFT_BLOCKED"
        state["soft_block_date"] = now_ist().isoformat()
        _set_state(symbol, state)
        append_log(AUDIT_LOG_FILE,
                   f"SOFT BLOCKED: {symbol} live_dd={live_dd:.2f}% "
                   f"threshold={threshold:.2f}%")
        return True
    return False


def try_recovery_entry(symbol: str, current_price: float) -> bool:
    """
    Ek mauka system — ONE chance per soft block event.
    No loops possible.
    """
    state = get_stock_state(symbol)
    if state["mode"] != "SOFT_BLOCKED":
        return False
    if state.get("mauka_used") or not state.get("mauka_available", True):
        return False
    if not _is_at_support(symbol, current_price):
        return False

    state["mode"]                = "RECOVERY"
    state["mauka_used"]          = True
    state["mauka_available"]     = False
    state["recovery_entry_date"] = now_ist().isoformat()
    _set_state(symbol, state)
    append_log(AUDIT_LOG_FILE,
               f"RECOVERY MODE: {symbol} ek mauka at price={current_price}")
    return True


def recovery_sl_hit(symbol: str):
    """SL hit during recovery → HARD BLOCK. No more chances."""
    state = get_stock_state(symbol)
    state["mode"]              = "HARD_BLOCKED"
    state["hard_block_reason"] = "Recovery SL hit — no more chances"
    _set_state(symbol, state)
    append_log(AUDIT_LOG_FILE, f"HARD BLOCKED: {symbol} recovery SL hit")


def second_support_touch(symbol: str):
    state = get_stock_state(symbol)
    state["mode"]              = "HARD_BLOCKED"
    state["hard_block_reason"] = "Second support touch — mauka already used"
    _set_state(symbol, state)
    append_log(AUDIT_LOG_FILE, f"HARD BLOCKED: {symbol} second support touch")


def recovery_success(symbol: str):
    state = get_stock_state(symbol)
    state["mode"] = "SOFT_BLOCKED"
    _set_state(symbol, state)
    append_log(AUDIT_LOG_FILE,
               f"RECOVERY SUCCESS: {symbol} back to SOFT_BLOCKED")


def check_soft_to_profit(symbol: str, current_price: float) -> bool:
    state       = get_stock_state(symbol)
    if state["mode"] != "SOFT_BLOCKED":
        return False

    backtest_dd = _get_backtest_dd(symbol)
    if backtest_dd is None:
        return False

    wm              = state.get("high_watermark") or current_price
    dd_level_price  = wm * (1 + backtest_dd / 100)

    if current_price <= dd_level_price:
        return False

    days_above = state.get("days_above_dd_level", 0)
    state["days_above_dd_level"] = days_above + 1

    # PHASE-3 (ADD-ONLY): machine-proposed recovery window (>=5 policy floor); fallback = old PARAMS value
    wait_days = _recovery_days(symbol)
    if state["days_above_dd_level"] >= wait_days:
        state["mode"]                = "PROFIT"
        state["days_above_dd_level"] = 0
        state["mauka_used"]          = False
        state["mauka_available"]     = True
        state["high_watermark"]      = current_price
        _set_state(symbol, state)
        append_log(AUDIT_LOG_FILE,
                   f"UNBLOCKED: {symbol} recovered for "
                   f"{wait_days} days")
        return True
    else:
        _set_state(symbol, state)
    return False


def admin_unblock(symbol: str):
    state = get_stock_state(symbol)
    state["mode"]                = "PROFIT"
    state["mauka_used"]          = False
    state["mauka_available"]     = True
    state["high_watermark"]      = None
    state["hard_block_reason"]   = None
    state["days_above_dd_level"] = 0
    _set_state(symbol, state)
    append_log(AUDIT_LOG_FILE, f"ADMIN UNBLOCK: {symbol}")


def _is_at_support(symbol: str, current_price: float) -> bool:
    try:
        from dhan_data import fetch_daily_data
        df = fetch_daily_data(symbol, days=180)
        if df.empty:
            return False
        from per_stock_params import get_param
        tool = get_param(symbol, "support_tool", PARAMS.get("support_tool", "200ema"))
        support_price = _get_support_price(df, tool)
        if support_price is None:
            return False
        tolerance = 0.01
        return abs(current_price - support_price) / support_price <= tolerance
    except (TypeError, ValueError, ZeroDivisionError) as e:
        logger.debug(f"_is_near_support: Calculation failed: {type(e).__name__}: {e}")
        return False


def _get_support_price(df, tool: str):
    close = df["close"]
    try:
        if tool == "50ema":
            return float(close.ewm(span=50).mean().iloc[-1])
        elif tool == "100ema":
            return float(close.ewm(span=100).mean().iloc[-1])
        elif tool == "200ema":
            return float(close.ewm(span=200).mean().iloc[-1])
        elif tool == "50sma":
            return float(close.rolling(50).mean().iloc[-1])
        elif tool == "200sma":
            return float(close.rolling(200).mean().iloc[-1])
        elif tool == "swing_low":
            return float(df["low"].rolling(20).min().iloc[-1])
        elif tool == "vwap":
            vol_cum = df["volume"].cumsum()
            if float(vol_cum.iloc[-1]) <= 0:
                # Zero-volume window (illiquid/gap data): cumsum division
                # would silently produce inf/nan (pandas doesn't raise
                # ZeroDivisionError here) instead of a real price, which
                # would then silently no-op the near-support check that
                # calls this. Fail closed like the other branches' except.
                return None
            vwap = (df["close"] * df["volume"]).cumsum() / vol_cum
            return float(vwap.iloc[-1])
        else:
            return float(close.ewm(span=200).mean().iloc[-1])
    except (TypeError, ValueError, IndexError) as e:
        logger.debug(f"_get_support_price: Calculation failed: {type(e).__name__}: {e}")
        return None


def _get_backtest_dd(symbol: str):
    data = load_json(BACKTEST_RESULTS_FILE, {})
    return data.get("stocks", {}).get(symbol, {}).get(
        "price_max_drawdown_pct"
    )


def get_all_modes() -> dict:
    return _load()


def is_tradeable(symbol: str) -> bool:
    return get_mode(symbol) == "PROFIT"
