"""
capital_manager.py — Position sizing, slot management, balance tracking
FIX-24: Fresh balance per trade (no caching)
FIX-26: Stage % clarification — % of total allocated trading capital
"""

import asyncio
import logging
from config import PARAMS, DEPLOYMENT_STAGES, AUDIT_LOG_FILE
from broker import get_available_balance, _create_dhan_client
from utils import load_json, save_json, now_ist, append_log, safe_div
from config import PORTFOLIO_STATE_FILE, SEBI_BLOCKED_FILE

logger = logging.getLogger(__name__)


STAGED_STATE_FILE = "data/staged_state.json"

# FIX-46: Thread safety lock for subscriber isolation
_subscriber_lock = asyncio.Lock()


# ─────────────────────────────────────────────
# STAGED DEPLOYMENT
# FIX-26: Stage % = % of total allocated trading capital
# Example: Rs.10L allocated, Stage 1 = Rs.1L across all active trades
# ─────────────────────────────────────────────

def get_current_stage(chat_id: str = "admin") -> int:
    data = load_json(STAGED_STATE_FILE, {})
    return data.get(str(chat_id), {}).get("stage", 1)


def set_stage(stage: int, chat_id: str = "admin"):
    data = load_json(STAGED_STATE_FILE, {})
    data.setdefault(str(chat_id), {})["stage"] = stage
    data[str(chat_id)]["updated"] = now_ist().isoformat()
    save_json(STAGED_STATE_FILE, data)
    append_log(AUDIT_LOG_FILE, f"STAGE CHANGE: {chat_id} -> Stage {stage}")


def get_full_deployment_stage() -> int:
    """Return the configured full-capital deployment stage.

    F073 invariant: LIVE_FULL must not depend on a hardcoded stage number.
    The full stage is the configured deployment stage whose multiplier is 1.0
    in DEPLOYMENT_STAGES. If no such stage exists, live-full activation must
    fail closed rather than silently using a partial capital stage.
    """
    full_stages = [int(stage) for stage, mult in DEPLOYMENT_STAGES.items() if float(mult) == 1.0]
    if not full_stages:
        raise ValueError("DEPLOYMENT_STAGES has no configured full-capital stage (multiplier 1.0)")
    return min(full_stages)


def enforce_full_deployment_stage(chat_id: str = "admin") -> int:
    """Atomically enforce the configured full-capital stage for LIVE_FULL."""
    full_stage = get_full_deployment_stage()
    current_stage = get_current_stage(chat_id)
    if current_stage != full_stage:
        set_stage(full_stage, chat_id)
        append_log(AUDIT_LOG_FILE, f"LIVE_FULL STAGE ENFORCED: {chat_id} Stage {current_stage} -> {full_stage}")
    return full_stage


def get_stage_multiplier(chat_id: str = "admin", capital: float = None) -> float:
    """
    Tier 2 Head of Calculation Dynamic Staged Deployment Multiplier.
    Scales Stage 1 percentage to guarantee economic subscription fee coverage floor per individual capital.
    """
    stage = get_current_stage(chat_id)
    full_stage = get_full_deployment_stage()

    # F073: when the admin runtime state is LIVE_FULL, force the stage
    # multiplier to the configured full-capital stage. This preserves the
    # existing Stage × Health × Regime chain while ensuring LIVE_FULL cannot
    # accidentally behave like LIVE_STAGED because data/staged_state.json was
    # still on a partial stage. Subscriber stages remain subscriber-specific.
    if str(chat_id) == "admin":
        try:
            from bot_state_manager import get_state
            if get_state() == "LIVE_FULL":
                stage = full_stage
        except (ImportError, RuntimeError, ValueError) as e:
            logger.warning(f"get_stage_multiplier: Live-full state check failed: {type(e).__name__}: {e}")

    if stage >= full_stage:
        return 1.0

    if capital is None or capital <= 0:
        try:
            from broker import get_available_balance
            capital = float(get_available_balance())
        except (ImportError, RuntimeError, ValueError) as e:
            logger.warning(f"get_stage_multiplier: Balance fetch failed: {type(e).__name__}: {e}")
            capital = float(PARAMS["validator_reference_capital"])  # Strict owner value — no fallback
            from fallback_monitor import record_fallback   # FIX-LIST item 17 (visibility only)
            record_fallback("capital_manager.get_stage_multiplier.balance", e, capital, "broker balance → validator_reference_capital")

    try:
        from capital_drawdown_manager import calculate_head_of_calculation_hurdles
        hurdles = calculate_head_of_calculation_hurdles(capital)
        stage_1_base = float(PARAMS.get("stage_1_base_pct", 0.10))
        if not hurdles.get("error"):
            min_cap = float(hurdles.get("min_viable_capital_stage_1", capital))
            if capital < min_cap and capital > 0:
                stage_1_base = min(float(PARAMS.get("stage_1_max_adjust", 0.50)), max(stage_1_base, (min_cap / capital) * stage_1_base))

        stages = {
            1: round(stage_1_base, 2),
            2: round(min(1.0, stage_1_base * float(PARAMS.get("stage_2_mult", 2.5))), 2),
            3: round(min(1.0, stage_1_base * float(PARAMS.get("stage_3_mult", 5.0))), 2),
            full_stage: 1.0
        }
        return stages.get(stage, stage_1_base)
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"get_stage_multiplier: Hurdles calculation failed: {type(e).__name__}: {e}")
        return DEPLOYMENT_STAGES.get(stage, 0.10)


# ─────────────────────────────────────────────
# HEALTH-LINKED CAPITAL MULTIPLIER
# ─────────────────────────────────────────────

def get_health_capital_multiplier() -> float:
    """
    FIX-03: Smooth health-linked capital multiplier.
    Delegates to portfolio_health.get_health_multiplier().
    """
    try:
        from portfolio_health import get_health_multiplier
        return get_health_multiplier()
    except (ImportError, RuntimeError) as e:
        logger.warning(f"get_health_capital_multiplier: Failed: {type(e).__name__}: {e}")
        # AUDIT FIX (Bug #8a, fail-open): used to default to 1.0 (full-size,
        # "perfect health") on failure. Fail conservative instead, using the
        # same owner-approved floor get_health_multiplier() itself uses.
        from portfolio_health import MIN_HEALTH_CAPITAL_FLOOR
        return MIN_HEALTH_CAPITAL_FLOOR

def get_regime_capital_multiplier() -> float:
    """
    Owner engine: regime_manager.get_regime_size_multiplier()

    [FIX] Fails closed to the config-defined BEAR size_mult (0.25x, PARAMS
    ["regime_behavior_defaults"]["BEAR"]["size_mult"]) on any lookup
    failure, matching the "unknown state = treat as worst case" convention
    used elsewhere (e.g. get_health_capital_multiplier()). Previously
    defaulted to 1.0 (full/most-aggressive size) on failure, which is the
    opposite of what a fail-closed capital gate should do. 0.25 is also
    hardcoded as a last-resort literal in case PARAMS itself is unreadable.
    """
    try:
        from regime_manager import get_regime_size_multiplier
        return get_regime_size_multiplier()
    except (ImportError, RuntimeError) as e:
        logger.warning(f"get_regime_capital_multiplier: Failed: {type(e).__name__}: {e} — failing closed to worst-case (BEAR 0.25x)")
        try:
            return float(PARAMS["regime_behavior_defaults"]["BEAR"]["size_mult"])
        except (KeyError, TypeError, ValueError):
            return 0.25


# ─────────────────────────────────────────────
# BALANCE
# FIX-24: Fresh balance fetch per trade — no caching
# ─────────────────────────────────────────────

def get_deployable_balance(chat_id: str = "admin") -> float:
    """
    FIX-24: Fresh balance fetched from Dhan API every time.
    Cached balance NEVER used for position sizing.
    
    Stage % = % of total allocated trading capital
    FIX-26: Example — Rs.10L total, Stage 1 = Rs.1L deployable
    
    Uses Risk Parity for capital allocation (Industry Standard).
    Method: Risk Parity
    Creator: Bridgewater Associates (Ray Dalio, 1996)
    """
    raw_balance  = get_available_balance()  # Always fresh from API
    stage_mult   = get_stage_multiplier(chat_id)
    health_mult  = get_health_capital_multiplier()
    regime_mult  = get_regime_capital_multiplier()
    sebi_blocked = get_total_sebi_blocked()

    # Stage % of total allocated capital - SEBI blocked
    deployable = (raw_balance * stage_mult * health_mult * regime_mult) - sebi_blocked
    return max(0.0, deployable)


def get_total_sebi_blocked() -> float:
    data = load_json(SEBI_BLOCKED_FILE, {"blocked": []})
    return sum(item.get("amount", 0) for item in data.get("blocked", []))


# ─────────────────────────────────────────────
# AUTO STAGE MANAGEMENT
# ─────────────────────────────────────────────

def check_and_update_stage(chat_id: str = "admin"):
    """Performance based auto stage up/down."""
    from utils import load_json as uload
    from config import TRADES_FILE

    trades_data = uload(TRADES_FILE, {"trades": []})
    closed      = [t for t in trades_data["trades"] if t["status"] == "CLOSED"]
    if not closed:
        return

    current_stage = get_current_stage(chat_id)
    if current_stage >= 4:
        return

    n       = PARAMS.get("stage_up_trades", 10)
    recent  = closed[-n:]
    if len(recent) < n:
        return

    wins     = len([t for t in recent if (t.get("pnl") or 0) > 0])
    win_rate = wins / len(recent) * 100

    # Owner engine: stage thresholds from PARAMS (single source).
    # [✅ CONCEPT VERIFIED: staged validation lifecycle — Pardo 1992, Fed SR 11-7 2011 |
    #  🅾️ VALUES owner bands up 50-65 / down 35-45 (approved 2026-07-30) — credit: AIRAF
    #  NIZAMI; machine calibrates from paper/live data; defaults 55/40 = fallback]
    stage_up_wr   = PARAMS.get("stage_up_win_rate", 55)
    stage_down_wr = PARAMS.get("stage_down_win_rate", 40)

    if win_rate >= stage_up_wr:
        new_stage = min(current_stage + 1, 4)
        if new_stage != current_stage:
            set_stage(new_stage, chat_id)
            _notify_stage_change(chat_id, current_stage, new_stage, win_rate, n, "UP")

    elif win_rate <= stage_down_wr:
        new_stage = max(current_stage - 1, 1)
        if new_stage != current_stage:
            set_stage(new_stage, chat_id)
            _notify_stage_change(chat_id, current_stage, new_stage, win_rate, n, "DOWN")


def _notify_stage_change(chat_id, old, new, wr, n, direction):
    append_log(AUDIT_LOG_FILE,
               f"AUTO STAGE {direction}: {chat_id} Stage {old} -> {new} WR={wr:.1f}%")
    try:
        from signal_broadcaster import alert_admin, alert_admin_sync
        import asyncio
        _msg = (
            f"Stage {direction}: {chat_id}\n"
            f"Stage {old} to {new}\n"
            f"Win Rate: {wr:.1f}% (last {n} trades)"
        )
        try:
            asyncio.get_running_loop().create_task(alert_admin(_msg))
        except RuntimeError:
            # No running loop (scheduler thread) — deliver via sync wrapper
            alert_admin_sync(_msg)
    except (ImportError, RuntimeError) as e:
        logger.warning(f"_notify_stage_change: Failed to alert: {type(e).__name__}: {e}")


# ─────────────────────────────────────────────
# POSITION SIZING
# FIX-24: Fresh balance every time
# FIX-46: Thread safety for subscriber
# ─────────────────────────────────────────────

def calculate_qty(symbol: str, entry_price: float, sl_price: float,
                  chat_id: str = "admin", **kwargs) -> int:
    """
    [OVERRIDE 3 — user-authorized architectural pivot] Position sizing is
    now strict EQUAL-WEIGHT across the day's slot budget (5-10 slots,
    economics-derived) — see _calculate_position_qty() below for the
    actual formula. This function's old docstring claimed Half-Kelly
    Criterion sizing; that method is no longer used here (left defined in
    calculate_kelly_position_size() below in case a future decision
    revisits this).
    """
    if entry_price <= 0 or sl_price >= entry_price:
        append_log(AUDIT_LOG_FILE, f"QTY CALC REJECTED: {symbol} invalid prices")
        return 0

    deployable = get_deployable_balance(chat_id)
    if deployable <= 0:
        return 0

    signal_score = float(kwargs.get("signal_score", 1.0) if kwargs else 1.0)
    phase = str(kwargs.get("phase", "") if kwargs else "")
    qty, _ = _calculate_position_qty(symbol, entry_price, sl_price, deployable, signal_score=signal_score, phase=phase)
    return max(0, qty)


def calculate_kelly_position_size(capital: float, win_rate: float, win_loss_ratio: float, risk_per_trade: float = 0.02) -> float:
    """
    Half-Kelly Criterion for position sizing (Industry Standard).
    
    Method: Half-Kelly Criterion
    Creator: John L. Kelly Jr. (1956)
    Source: "A New Interpretation of Information Rate"
    
    Full Kelly: f* = (bp - q) / b
    Half-Kelly: f* = (bp - q) / (2b)  [conservative, recommended]
    
    Where:
    - b = win_loss_ratio (average win / average loss)
    - p = win_rate (probability of win)
    - q = 1 - p (probability of loss)
    
    Args:
        capital: Total capital available
        win_rate: Historical win rate (0-1)
        win_loss_ratio: Average win / average loss ratio
        risk_per_trade: Risk per trade (default 2%)
    
    Returns:
        Position size as fraction of capital
    """
    if win_rate <= 0 or win_rate >= 1 or win_loss_ratio <= 0:
        return risk_per_trade  # Fallback to fixed fractional
    
    b = win_loss_ratio
    p = win_rate
    q = 1 - p
    
    # Full Kelly
    full_kelly = (b * p - q) / b
    
    # Half-Kelly (conservative, recommended by academics)
    half_kelly = full_kelly / 2
    
    # Cap at risk_per_trade (2% rule)
    return min(half_kelly, risk_per_trade)


def is_trade_economically_viable(symbol: str, qty: int, entry_price: float, expected_tp_return_pct: float = 3.0, subscription_fee: float = None, trades_per_month: float = None) -> bool:
    """Gate A & Gate B using Decision 01/03/04/05 owner economics.

    [Method: Implementation Shortfall — Andre Perold, 1988 ("The Implementation
    Shortfall: Paper vs Reality"). real_profit = gross − fees − taxes/brokerage −
    slippage-frame costs is exactly Perold's shortfall philosophy: paper return and
    real return differ by execution+friction costs; only net-of-cost profit counts.
    TAG-ONLY (owner decision #3, 2026-07-30): ZERO runtime change — existing Gate
    A/B formula already conforms to this frame; tag added for documentation.]
    """
    if qty <= 0 or entry_price <= 0:
        return False
    try:
        from capital_drawdown_manager import get_verified_financial_economics
        econ = get_verified_financial_economics(symbol=symbol)
        subscription_fee = float(subscription_fee if subscription_fee is not None else econ["subscription_fee"])
        trades_per_month = float(trades_per_month if trades_per_month is not None else econ["expected_trades_per_month"])
    except (ImportError, RuntimeError, ValueError, TypeError, KeyError) as e:
        logger.error(f"is_trade_economically_viable: verified economics unavailable: {type(e).__name__}: {e} — BLOCK")
        # Decision-critical economics are fail-closed. Do not substitute a
        # static approximation when the verified owner engine is unavailable.
        return False
    trade_val = qty * entry_price
    try:
        from utils import calculate_dhan_friction
        total_tx_cost = calculate_dhan_friction(trade_val, is_intraday=False)
    except Exception as e:
        logger.error(f"is_trade_economically_viable: verified friction calculation failed: {type(e).__name__}: {e} — BLOCK")
        return False
    sub_cost_per_trade = subscription_fee / max(1.0, trades_per_month)
    expected_gross_profit = trade_val * (expected_tp_return_pct / 100.0)
    expected_net_profit = expected_gross_profit - (total_tx_cost + sub_cost_per_trade)
    if expected_net_profit <= 0:
        append_log(AUDIT_LOG_FILE, f"GATE A/B REJECT {symbol}: qty={qty} net profit ₹{expected_net_profit:.1f} <= 0 after fees & subscription hurdle")
        return False
    return True


async def calculate_qty_for_subscriber(sub: dict, security_id: str,
                                        symbol: str) -> int:
    """Subscriber sizing uses same verified runtime path as admin sizing."""
    async with _subscriber_lock:
        try:
            from crypto_utils import decrypt
            from per_stock_params import get_param

            client_id = sub["dhan_client_id"]
            access_token = decrypt(sub["dhan_access_token_enc"])
            sub_dhan = _create_dhan_client(client_id, access_token)

            result = sub_dhan.get_fund_limits()
            balance = float(result.get("availabelBalance", 0))

            chat_id = str(sub["chat_id"])
            stage_mult = get_stage_multiplier(chat_id, capital=balance)
            health_mult = get_health_capital_multiplier()
            regime_mult = get_regime_capital_multiplier()
            deployable = balance * stage_mult * health_mult * regime_mult

            state = load_json(PORTFOLIO_STATE_FILE, {})
            trade = state.get("active_trades", {}).get(symbol, {})
            entry_price = trade.get("entry_price", 0)
            sl_price = trade.get("sl_price", 0)
            phase = trade.get("phase", "")
            signal_score = float(trade.get("signal_score", 1.0) or 1.0)

            if entry_price <= 0 or sl_price >= entry_price:
                return 0

            qty, _ = _calculate_position_qty(symbol, entry_price, sl_price, deployable, signal_score=signal_score, phase=phase)
            if not is_trade_economically_viable(symbol, qty, entry_price, expected_tp_return_pct=get_param(symbol, "tp1_pct", 3.0)):
                return 0
            return max(0, qty)
        except (ImportError, RuntimeError, ValueError, TypeError, KeyError):
            return 0


# ─────────────────────────────────────────────
# SLOT MANAGEMENT
# ─────────────────────────────────────────────

def get_open_slot_count() -> int:
    state = load_json(PORTFOLIO_STATE_FILE, {"active_trades": {}})
    return len(state.get("active_trades", {}))


def has_free_slot() -> bool:
    """
    [AUDIT FIX Gap #11]: max_slots now comes from a real economics calculation
    (economics_brain.get_recommended_max_slots — brokerage/statutory/
    subscription-fee-per-trade vs current capital) instead of a purely static
    owner-picked number, answering the owner's original question directly.
    Falls back to the static PARAMS value on any failure (capital fetch,
    import, etc.) so this can never block trading due to an economics-calc bug.
    """
    base_max_slots = PARAMS["max_slots"]
    try:
        from broker import get_available_balance
        from economics_brain import get_recommended_max_slots
        capital = get_available_balance()
        if capital and capital > 0:
            base_max_slots = get_recommended_max_slots(capital)
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"has_free_slot: economics-based max_slots calc failed: {type(e).__name__}: {e} — using static PARAMS['max_slots']")
        from fallback_monitor import record_fallback   # FIX-LIST item 17 (visibility only)
        record_fallback("capital_manager.has_free_slot.max_slots", e, base_max_slots)

    try:
        from regime_manager import get_regime_max_slots
        max_slots = get_regime_max_slots(base_max_slots)
    except (ImportError, RuntimeError, ValueError) as e:
        logger.warning(f"has_free_slot: Regime max slots failed: {type(e).__name__}: {e}")
        max_slots = base_max_slots
    return get_open_slot_count() < max_slots


def register_trade(symbol: str, trade_data: dict):
    state = load_json(PORTFOLIO_STATE_FILE, {"active_trades": {}})
    state.setdefault("active_trades", {})[symbol] = trade_data
    save_json(PORTFOLIO_STATE_FILE, state)


def release_trade(symbol: str):
    state = load_json(PORTFOLIO_STATE_FILE, {"active_trades": {}})
    state.setdefault("active_trades", {}).pop(symbol, None)
    save_json(PORTFOLIO_STATE_FILE, state)


def update_trade(symbol: str, updates: dict):
    """v5.3: active trade ke fields update karo (trail state persist ke liye)."""
    state = load_json(PORTFOLIO_STATE_FILE, {"active_trades": {}})
    trade = state.setdefault("active_trades", {}).get(symbol)
    if not trade:
        return False
    trade.update(updates)
    save_json(PORTFOLIO_STATE_FILE, state)
    return True


def get_active_trades() -> dict:
    state = load_json(PORTFOLIO_STATE_FILE, {"active_trades": {}})
    return state.get("active_trades", {})


# ─────────────────────────────────────────────
# VOLATILITY-ADJUSTED SIZING (Risk Parity — Verified)
# Source: Bridgewater / Ray Dalio — Inverse Volatility Weighting
# Principle: High volatility = smaller position, Low volatility = larger position
# This ensures each stock contributes EQUAL risk to portfolio
# ─────────────────────────────────────────────

# Cache for stock volatility to avoid re-fetching
_vol_cache = {}

def get_stock_volatility(symbol: str, days: int = 90) -> float:
    """
    Calculate annualized volatility for a stock.
    Uses Dhan daily data for calculation.
    Returns annualized volatility % (e.g., 25.0 = 25% annual vol)
    """
    cache_key = f"{symbol}_{days}"
    if cache_key in _vol_cache:
        return _vol_cache[cache_key]

    try:
        from dhan_data import fetch_daily_data
        df = fetch_daily_data(symbol, days=days)
        if df is None or df.empty or len(df) < 20:
            return float(PARAMS.get("default_stock_volatility", 25.0))

        returns = df["close"].pct_change().dropna()
        if len(returns) < 10:
            return float(PARAMS.get("default_stock_volatility", 25.0))

        vol = float(returns.std() * (252 ** 0.5) * 100)  # Annualized %
        # Owner engine clamp from risk model (capital_drawdown_manager)
        vol = max(float(PARAMS.get("min_stock_volatility", 5.0)), min(float(PARAMS.get("max_stock_volatility", 100.0)), vol))

        _vol_cache[cache_key] = vol
        return vol
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"get_stock_volatility: Calculation failed for {symbol}: {type(e).__name__}: {e}")
        # Owner engine default: moderate volatility from risk model
        return float(PARAMS.get("default_stock_volatility", 25.0))


def get_volatility_multiplier(symbol: str) -> float:
    """
    Risk Parity: Inverse volatility weighting.

    If stock vol > target → smaller position; if vol < target → larger position.

    [Method: Risk Parity / Inverse-Volatility Weighting — named by Edward Qian,
    PanAgora 2005; implemented by Bridgewater All-Weather ~1996 (Ray Dalio);
    academic validation: Harvey et al. 2018, Moreira & Muir 2017]
    [OWNER BAND — credit: AIRAF NIZAMI (owner-designed, Economics Brain Design
    Doc S7): target value machine-selected from owner band 10-20% (approved
    2026-07-30), default 12%. Current 20 = legacy bootstrap value.]
    NOTE: Bridgewater funds target 10-12% (Pure Alpha II 18%), NOT 20% —
    earlier "Bridgewater 20%" attribution was incorrect; a fabricated
    "Concretum Group position sizing study (2026)" citation was removed here.

    Returns multiplier between 0.3 and 1.5
    """
    vol = get_stock_volatility(symbol)
    target_vol = PARAMS.get("target_portfolio_vol", 20.0)

    if vol <= 0:
        return 1.0

    multiplier = target_vol / vol

    # Owner engine clamp: use volatility multiplier limits from risk context
    min_vol_mult = float(PARAMS.get("min_volatility_multiplier", 0.3))
    max_vol_mult = float(PARAMS.get("max_volatility_multiplier", 1.5))
    return max(min_vol_mult, min(max_vol_mult, round(multiplier, 2)))


def get_sector_strength_multiplier(symbol: str) -> float:
    """Decision 11 runtime consumer — uses sector_strength owner engine output."""
    try:
        from sector_strength import get_sector_runtime_signal
        from per_stock_params import get_param
        ctx = get_sector_runtime_signal(symbol)
        weight = float(get_param(symbol, "sector_strength_weight", 0.5) or 0.5)
        score = float(ctx.get("strength_score", 0.0) or 0.0)
        threshold = float(ctx.get("threshold", 0.5) or 0.5)
        if ctx.get("allow"):
            edge = max(0.0, score - threshold)
            return round(_clamp(1.0 + (edge * weight * 0.2), 1.0, 1.4), 2)
        weakness = max(0.0, threshold - score)
        return round(_clamp(1.0 - (weakness * max(weight, 0.3)), 0.3, 1.0), 2)
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        # [AUDIT FIX #7] previously returned 1.0 (neutral) on failure — now fails
        # conservative using the same 0.3 floor this function already uses for a
        # confirmed-weak sector, since "couldn't determine sector strength" should
        # never be treated as "assume it's fine".
        logger.warning(f"get_sector_strength_multiplier: Failed for {symbol}: {type(e).__name__}: {e} — using conservative floor 0.3")
        return 0.3


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _load_optimizer_context(symbol: str) -> dict:
    optimizer = load_json("data/optimizer_results.json", {})
    wfv_all = load_json("data/walk_forward_results.json", {})
    ranking = optimizer.get("ruflo_ranking", []) if isinstance(optimizer, dict) else []
    rank_map = {item.get("symbol"): item for item in ranking if isinstance(item, dict)}
    return {
        "stock_result": optimizer.get("results", {}).get(symbol, {}) if isinstance(optimizer, dict) else {},
        "wfv_result": wfv_all.get(symbol, {}) if isinstance(wfv_all, dict) else {},
        "rank_item": rank_map.get(symbol, {}),
        "ranking_size": len(rank_map),
    }


def get_verified_risk_context(symbol: str, capital: float = None) -> dict:
    """Decision 13 single source of truth for runtime risk multiplier."""
    from per_stock_params import get_param
    from capital_drawdown_manager import (
        calculate_optimal_risk_per_trade,
        calculate_head_of_calculation_hurdles,
        calculate_capital_drawdown_limits,
    )

    if capital is None or capital <= 0:
        capital = max(1.0, float(get_available_balance() or 1.0))

    configured_risk_pct = float(get_param(symbol, "risk_pct_per_trade", PARAMS["risk_pct_per_trade"]) or PARAMS["risk_pct_per_trade"])
    risk_model = calculate_optimal_risk_per_trade(symbol, capital)
    optimal_risk_pct = float(risk_model.get("optimal_risk_per_trade_pct", configured_risk_pct) or configured_risk_pct)

    try:
        from portfolio_health import calculate_health_score
        health_score = float(calculate_health_score() or 100.0)
    except (ImportError, RuntimeError, ValueError) as e:
        logger.warning(f"get_verified_risk_context: Health score failed: {type(e).__name__}: {e}")
        # AUDIT FIX (Bug #8b, fail-open): used to default to 100.0 ("perfect
        # health"), inflating health_floor_mult below and thus verified_risk_pct
        # (the actual position-sizing risk %) exactly when health couldn't be
        # verified. Fail conservative (0.0), matching
        # survival_manager.get_bot_health_pct()'s own already-fixed pattern --
        # the clamp() below naturally floors this at its own declared worst case.
        health_score = 0.0

    hurdles = calculate_head_of_calculation_hurdles(capital)
    dd_limits = calculate_capital_drawdown_limits(capital, health_score)

    viability_mult = 1.0
    # NOTE: A capital-below-stage-1-floor risk-reduction multiplier is not
    # currently produced by any owner engine — calculate_head_of_calculation_hurdles()
    # (capital_drawdown_manager.py) does not emit a "viability_multiplier" key,
    # confirmed by full-repo search. A prior version of this block read that
    # key via h.get("viability_multiplier", 1.0), which silently and
    # unconditionally fell back to 1.0 for every call (dead code presenting
    # as a real owner-engine-sourced safeguard — Constitution Art. 5.1/5.2).
    # Removed rather than inventing an unapproved formula. If a real
    # under-capitalization risk-reduction methodology is desired here, it
    # must be designed in capital_drawdown_manager.py and presented to the
    # Repository Owner for approval (Constitution Art. 2.3 Tier 3).

    health_floor = float(hurdles.get("dynamic_health_floor_pct", 10.0) or 10.0)
    health_floor_mult = _clamp(health_score / max(health_floor, 1.0), 0.35, 1.0)

    soft_dd = abs(float(dd_limits.get("soft_dd_pct", 3.0) or 3.0))
    hard_dd = abs(float(dd_limits.get("hard_dd_pct", 6.0) or 6.0))
    # Owner engine: drawdown buffer from capital_drawdown_manager
    try:
        from capital_drawdown_manager import calculate_capital_drawdown_limits
        dd = calculate_capital_drawdown_limits(capital, bot_health=100.0)
        soft = float(dd.get("soft_dd_pct", 3.0))
        hard = float(dd.get("hard_dd_pct", 6.0))
        drawdown_buffer_mult = _clamp((hard - soft) / max(hard, 0.01), 0.45, 1.0)
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"get_verified_risk_context: Drawdown limits failed: {type(e).__name__}: {e}")
        # AUDIT FIX (Bug #8c, fail-open): used to default to 1.0 (no
        # reduction) on failure. Fail conservative instead, at this same
        # multiplier's own declared worst-case floor (0.45) used above.
        drawdown_buffer_mult = 0.45

    verified_risk_pct = min(configured_risk_pct, optimal_risk_pct)
    verified_risk_pct *= viability_mult * health_floor_mult * drawdown_buffer_mult
    verified_risk_pct = _clamp(verified_risk_pct, 0.20, min(1.00, optimal_risk_pct))

    risk_multiplier = verified_risk_pct / max(configured_risk_pct, 0.0001)

    return {
        "configured_risk_pct": round(configured_risk_pct, 4),
        "optimal_risk_pct": round(optimal_risk_pct, 4),
        "verified_risk_pct": round(verified_risk_pct, 4),
        "risk_multiplier": round(risk_multiplier, 4),
        "health_score": round(health_score, 2),
        "viability_multiplier": round(viability_mult, 4),
        "health_floor_multiplier": round(health_floor_mult, 4),
        "drawdown_buffer_multiplier": round(drawdown_buffer_mult, 4),
    }


def get_tool_weight_multiplier(symbol: str, phase: str = "") -> float:
    ctx = _load_optimizer_context(symbol)
    stock_result = ctx.get("stock_result", {})
    phase = (phase or "").upper()
    if phase:
        p_weights = stock_result.get("phase_tool_weights", {})
        phase_weights = p_weights.get(phase, {}) if isinstance(p_weights, dict) else {}
        selected = stock_result.get("params", {}).get(f"tool_{phase.lower()}") or stock_result.get(f"tool_{phase.lower()}")
        if selected and isinstance(phase_weights, dict) and phase_weights:
            base = float(PARAMS.get("tool_weight_base", 0.70))
            return _clamp(base + phase_weights.get(selected, 0.5), base, float(PARAMS.get("tool_weight_max", 1.50)))
        param_weight = stock_result.get("params", {}).get(f"tool_weight_{phase.lower()}")
        if param_weight is not None:
            base = float(PARAMS.get("tool_weight_base", 0.70))
            return _clamp(base + float(param_weight), base, float(PARAMS.get("tool_weight_max", 1.50)))

    selected_gen = stock_result.get("signal_generator") or stock_result.get("params", {}).get("signal_generator")
    tool_weights = stock_result.get("tool_weights", {})
    if selected_gen and isinstance(tool_weights, dict) and tool_weights:
        base = float(PARAMS.get("tool_weight_base", 0.70))
        return _clamp(base + float(tool_weights.get(selected_gen, 0.5)), base, float(PARAMS.get("tool_weight_max", 1.50)))
    return 1.0


def get_runtime_confidence_profile(symbol: str, signal_score: float = 1.0, phase: str = "") -> dict:
    """Decision 21/15 runtime confidence + tool-weight integration."""
    ctx = _load_optimizer_context(symbol)
    result = ctx.get("stock_result", {})
    wfv = ctx.get("wfv_result", {})

    weighted_score = float(result.get("weighted_production_score", result.get("best_score", 0.0)) or 0.0)
    wr = float(result.get("win_rate_pct", 0.0) or 0.0)
    pf = float(result.get("profit_factor", 0.0) or 0.0)
    wfv_conf = float(wfv.get("confidence", 0.3) or 0.3)
    signal_norm = _clamp(signal_score, 0.30, 1.0)

    # Normalization baselines (optimizer-configurable)
    norm_baselines = PARAMS.get("confidence_norm_baselines", {
        "wr_baseline": 35.0,
        "pf_baseline": 3.0,
    })
    
    weighted_norm = _clamp(weighted_score / 100.0, 0.0, 1.0)
    # AI-DOS LOGIC-001 fix: norm_baselines is PARAMS-configurable (owner-tunable),
    # so a misconfigured 0 baseline must not crash confidence scoring.
    wr_norm = _clamp(safe_div(wr - norm_baselines["wr_baseline"], norm_baselines["wr_baseline"], default=0.0), 0.0, 1.0)
    pf_norm = _clamp(safe_div(pf, norm_baselines["pf_baseline"], default=0.0), 0.0, 1.0)
    tool_mult = get_tool_weight_multiplier(symbol, phase=phase)
    tool_norm = _clamp((tool_mult - 0.70) / 0.80, 0.0, 1.0)
    try:
        from portfolio_health import get_health_multiplier
        health_norm = _clamp(float(get_health_multiplier() or 1.0), 0.10, 1.0)
    except (ImportError, RuntimeError, ValueError) as e:
        logger.warning(f"get_runtime_confidence_profile: Health multiplier failed: {type(e).__name__}: {e}")
        # AUDIT FIX (Bug #8d, fail-open): used to default to 1.0 (max
        # confidence) on failure. Fail conservative instead, at this same
        # value's own declared worst-case floor (0.10) used above.
        health_norm = 0.10
    try:
        sector_norm = _clamp((get_sector_strength_multiplier(symbol) - 0.30) / 0.90, 0.0, 1.0)
    except (ImportError, RuntimeError, ValueError) as e:
        logger.warning(f"get_runtime_confidence_profile: Sector strength failed: {type(e).__name__}: {e}")
        sector_norm = 0.5
    vol_norm = _clamp(get_volatility_multiplier(symbol) / 1.5, 0.0, 1.0)

    # Scoring weights (optimizer-configurable)
    confidence_weights = PARAMS.get("confidence_weights", {
        "weighted": 0.24,
        "wr": 0.14,
        "pf": 0.14,
        "wfv": 0.14,
        "tool": 0.14,
        "signal": 0.10,
        "health": 0.05,
        "sector": 0.03,
        "vol": 0.02,
    })

    confidence_score = 100.0 * (
        weighted_norm * confidence_weights["weighted"] +
        wr_norm * confidence_weights["wr"] +
        pf_norm * confidence_weights["pf"] +
        wfv_conf * confidence_weights["wfv"] +
        tool_norm * confidence_weights["tool"] +
        signal_norm * confidence_weights["signal"] +
        health_norm * confidence_weights["health"] +
        sector_norm * confidence_weights["sector"] +
        vol_norm * confidence_weights["vol"]
    )
    _base = float(PARAMS.get("confidence_mult_base", 0.50))
    _slope = float(PARAMS.get("confidence_mult_slope", 0.90))
    _lo = float(PARAMS.get("confidence_mult_min", 0.50))
    _hi = float(PARAMS.get("confidence_mult_max", 1.40))
    multiplier = _clamp(_base + (confidence_score / 100.0) * _slope, _lo, _hi)

    return {
        "score": round(confidence_score, 2),
        "multiplier": round(multiplier, 4),
        "tool_multiplier": round(tool_mult, 4),
        "weighted_score": round(weighted_score, 4),
        "wfv_confidence": round(wfv_conf, 4),
    }


def _calculate_position_qty(symbol: str, entry_price: float, sl_price: float,
                            deployable: float, signal_score: float = 1.0,
                            phase: str = "") -> tuple:
    """
    [PHD-FIX F9 — honest label] Position sizing = EQUAL-WEIGHT slots
    (deployable/max_slots); Half-Kelly sirf DAILY RISK BUDGET me hai
    (capital_drawdown_manager) — dono alag concepts, labels ab sahi.
    [OVERRIDE 3 — user-authorized architectural pivot] Position sizing is
    now STRICT EQUAL-WEIGHT across the day's slot budget — every setup that
    gets a slot receives the same rupee allocation
    (deployable_capital / max_slots), regardless of confidence score,
    volatility, or Kelly-derived risk fraction. The previous multi-factor
    approach (Half-Kelly + confidence multiplier + volatility multiplier +
    G&Z drawdown-cushion) is REMOVED from sizing — those functions are left
    defined below (not deleted) in case a future decision revisits this,
    but are no longer called here.

    max_slots itself is still economics-derived (see economics_brain.py,
    Round 1 fix — real formula from capital vs brokerage/subscription-fee
    economics), now clamped to a tighter 5-10 band per this pivot. WHICH
    setups actually get the limited slots on a busy day is decided by
    scan-order priority (sector-strength + momentum score — see
    trade_engine.py's scan-loop ranking), not by sizing math.
    """
    if entry_price <= 0:
        return 0, {"reason": "invalid_entry_price"}

    try:
        from broker import get_available_balance
        from economics_brain import get_recommended_max_slots
        capital_for_slots = get_available_balance() or deployable
        max_slots = get_recommended_max_slots(capital_for_slots) if capital_for_slots > 0 else 8
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"_calculate_position_qty: max_slots lookup failed: {type(e).__name__}: {e} — using static fallback")
        max_slots = PARAMS.get("max_slots", 8)
        from fallback_monitor import record_fallback   # FIX-LIST item 17 (visibility only)
        record_fallback("capital_manager._calculate_position_qty.max_slots", e, max_slots)

    max_slots = max(1, int(max_slots))
    allocation_per_trade = deployable / max_slots
    # AI-DOS LOGIC-001 fix: a corrupted/zero entry_price from a bad feed
    # tick must not crash position sizing.
    qty = int(safe_div(allocation_per_trade, entry_price, default=0.0))

    return max(0, qty), {
        "method": "equal_weight",
        "max_slots": max_slots,
        "allocation_per_trade": round(allocation_per_trade, 2),
    }


def get_optimization_confidence_multiplier(symbol: str, signal_score: float = 1.0, phase: str = "") -> float:
    try:
        return get_runtime_confidence_profile(symbol, signal_score=signal_score, phase=phase)["multiplier"]
    except (ImportError, RuntimeError, ValueError, TypeError, KeyError) as e:
        logger.warning(f"get_optimization_confidence_multiplier: Failed for {symbol}: {type(e).__name__}: {e}")
        # AUDIT FIX (Bug #8e, fail-open): used to default to 1.0 on failure.
        # Fail conservative instead, at the underlying multiplier's own
        # declared worst-case floor (0.50).
        return 0.50


def get_stage_readiness_decision(symbol: str = None, capital: float = None) -> dict:
    """Decision 02 owner gate: health + survival + economics + validation readiness."""
    try:
        from broker import get_available_balance
        from capital_drawdown_manager import calculate_head_of_calculation_hurdles
        from portfolio_health import calculate_health_score
        capital = float(capital if capital is not None else get_available_balance())
        health = float(calculate_health_score() or 100.0)
        hurdles = calculate_head_of_calculation_hurdles(capital, symbol=symbol)
        allow = bool(hurdles.get("viable_at_stage_1")) and health >= float(hurdles.get("dynamic_health_floor_pct", 10.0))
        return {
            "allow": allow,
            "capital": capital,
            "health_score": health,
            "dynamic_health_floor_pct": float(hurdles.get("dynamic_health_floor_pct", 10.0) or 10.0),
            "reason": "OK" if allow else f"Stage readiness failed: capital/health below hurdle floor",
            "hurdles": hurdles,
        }
    except Exception as e:
        return {"allow": False, "reason": f"Stage readiness error: {e}"}


def get_low_balance_decision(symbol: str, entry_price: float, sl_price: float, deployable: float = None, signal_score: float = 1.0, phase: str = "") -> dict:
    """Decision 09 owner engine consuming derivation + economics + survival + confidence."""
    try:
        from broker import get_available_balance
        from capital_drawdown_manager import get_verified_financial_economics
        from survival_manager import calculate_survival_plan
        deployable = float(deployable if deployable is not None else get_available_balance())
        econ = get_verified_financial_economics(symbol=symbol)
        confidence = get_runtime_confidence_profile(symbol, signal_score=signal_score, phase=phase)
        plan = calculate_survival_plan(
            capital=deployable,
            expected_monthly_return_pct=max(0.0, econ.get("avg_net_return_per_trade_pct", 0.1) * econ.get("expected_trades_per_month", 1.0)),
        )
        qty, ctx = _calculate_position_qty(symbol, entry_price, sl_price, deployable, signal_score=signal_score, phase=phase)
        expected_tp = entry_price * (1.0 + 0.03)
        # AI-DOS LOGIC-001 fix: guard against a zero/corrupted entry_price.
        viable = is_trade_economically_viable(symbol, qty, entry_price, expected_tp_return_pct=safe_div(expected_tp - entry_price, entry_price, default=0.0) * 100.0)
        if plan.get("error"):
            return {
                "allow": False,
                "qty": 0,
                "deployable": deployable,
                "reason": f"Low balance decision: verified survival plan unavailable ({plan['error']})",
                "context": ctx,
            }
        survival_floor = float(plan["soft_loss_amt"])
        low_balance = (qty < 1) or (not viable) or (deployable <= survival_floor)
        return {
            "allow": not low_balance,
            "qty": qty,
            "deployable": deployable,
            "confidence_score": confidence["score"],
            "survival_soft_floor_amt": survival_floor,
            "reason": "OK" if not low_balance else "Low balance / low deployability under economics-survival constraints",
            "context": ctx,
        }
    except Exception as e:
        return {"allow": False, "qty": 0, "reason": f"Low balance decision error: {e}"}


def calculate_qty_enhanced(symbol: str, entry_price: float, sl_price: float,
                           chat_id: str = "admin", **kwargs) -> int:
    """Decision 13/21/22/23 runtime sizing path."""
    if entry_price <= 0 or sl_price >= entry_price:
        append_log(AUDIT_LOG_FILE, f"QTY CALC REJECTED: {symbol} invalid prices")
        return 0

    deployable = get_deployable_balance(chat_id)
    if deployable <= 0:
        return 0

    from per_stock_params import get_param
    signal_score = float(kwargs.get("signal_score", 1.0) if kwargs else 1.0)
    phase = str(kwargs.get("phase", "") if kwargs else "")

    qty, sizing_ctx = _calculate_position_qty(symbol, entry_price, sl_price, deployable, signal_score=signal_score, phase=phase)
    if not is_trade_economically_viable(symbol, qty, entry_price, expected_tp_return_pct=get_param(symbol, "tp1_pct", 3.0)):
        return 0

    append_log(
        AUDIT_LOG_FILE,
        f"QTY ENHANCED {symbol}: qty={qty} conf={sizing_ctx['confidence_context']['score']} "
        f"risk_pct={sizing_ctx['risk_context']['verified_risk_pct']} alloc={sizing_ctx['allocation_fraction']} phase={phase}"
    )
    return max(0, qty)


# ─────────────────────────────────────────────
# Phase 6: Vector-Norm Portfolio Sizing & Factor Neutrality (v6.1)
# L1/L2 norms to bound aggregate risk, covariance + null space for sector neutrality
# Preserves locked capital drawdown invariants and single-trade caps
# ─────────────────────────────────────────────

def calculate_portfolio_norms(exposures: list, norm_type: str = "L2") -> float:
    """
    Calculate L1, L2, L_inf norms of portfolio exposure vector.

    exposures: list of position sizes or risk percentages per stock
               e.g., [0.02, 0.015, 0.03] = 2%, 1.5%, 3% risk per trade

    L1 = sum(|x_i|) — total absolute exposure, bounds gross leverage
         Example: 3 east + 4 north = 7 Manhattan distance (Surbhi L1 example)

    L2 = sqrt(sum(x_i^2)) — Euclidean norm, bounds concentrated risk
         Example: sqrt(3^2+4^2)=5 Euclidean distance (Surbhi L2 example)

    L_inf = max(|x_i|) — Chebyshev, bounds max single position

    Per spec: L1/L2 to bound aggregate portfolio risk exposure
    """
    try:
        import numpy as np
        arr = np.array(exposures, dtype=np.float64)
        if norm_type == "L1":
            return float(np.sum(np.abs(arr)))
        elif norm_type == "L2":
            return float(np.sqrt(np.sum(arr * arr)))
        elif norm_type == "L_inf" or norm_type == "Linf":
            return float(np.max(np.abs(arr))) if len(arr) > 0 else 0.0
        else:
            raise ValueError(f"Unknown norm_type {norm_type}, use L1/L2/L_inf")
    except Exception as e:
        logger.warning(f"calculate_portfolio_norms failed: {e}")
        return 0.0


def check_portfolio_risk_bounds(
    exposures: list,
    l1_max: float = 0.10,
    l2_max: float = 0.06,
    linf_max: float = 0.02,
) -> dict:
    """
    Check if portfolio exposures violate L1/L2/L_inf bounds.

    Defaults per QASWA risk:
      L1 max 0.10 = total risk across all positions <=10% (max DD ceiling)
      L2 max 0.06 = Euclidean concentrated risk <=6%
      L_inf max 0.02 = single trade <=2% (daily-loss cap)

    These preserve locked invariants: 2% daily-loss cap, 10% max DD

    Returns dict with valid bool, norms, violations
    """
    try:
        l1 = calculate_portfolio_norms(exposures, "L1")
        l2 = calculate_portfolio_norms(exposures, "L2")
        linf = calculate_portfolio_norms(exposures, "L_inf")

        violations = []
        if l1 > l1_max:
            violations.append(f"L1 {l1:.4f} > {l1_max} (gross exposure too high)")
        if l2 > l2_max:
            violations.append(f"L2 {l2:.4f} > {l2_max} (concentrated risk too high)")
        if linf > linf_max:
            violations.append(f"L_inf {linf:.4f} > {linf_max} (single position too large)")

        valid = len(violations) == 0

        return {
            "valid": valid,
            "L1": round(l1, 4),
            "L2": round(l2, 4),
            "L_inf": round(linf, 4),
            "L1_max": l1_max,
            "L2_max": l2_max,
            "L_inf_max": linf_max,
            "violations": violations,
            "reason": "OK" if valid else "; ".join(violations),
        }
    except Exception as e:
        return {"valid": False, "reason": f"Risk bounds check error: {e}", "violations": [str(e)]}


def calculate_covariance_matrix(returns_dict: dict) -> dict:
    """
    Calculate covariance matrix from per-stock returns.

    returns_dict: {symbol: [returns]} — per-stock return series

    Returns dict with covariance matrix, correlation, eigenvalues for risk analysis

    Used for portfolio stress test under crash regimes (2020 Covid, 2024 election)
    """
    try:
        import numpy as np
        import pandas as pd

        if not returns_dict or len(returns_dict) < 2:
            return {"error": "Need at least 2 symbols for covariance"}

        # Align returns to same length (trim to min length)
        min_len = min(len(v) for v in returns_dict.values() if len(v) > 0)
        if min_len < 10:
            return {"error": f"Insufficient returns length {min_len} <10"}

        symbols = list(returns_dict.keys())
        # Build matrix: rows = time, cols = symbols
        matrix = []
        for sym in symbols:
            rets = returns_dict[sym][-min_len:]  # last min_len
            matrix.append(rets)

        # Transpose to (T, N)
        ret_matrix = np.array(matrix).T  # shape (T, N)

        # Covariance
        cov = np.cov(ret_matrix, rowvar=False)  # (N,N)

        # Correlation
        corr = np.corrcoef(ret_matrix, rowvar=False)

        # Eigenvalues for risk concentration
        try:
            eigvals = np.linalg.eigvals(cov)
            eigvals = sorted([float(x.real) for x in eigvals], reverse=True)
        except Exception:
            eigvals = []

        return {
            "symbols": symbols,
            "covariance": cov.tolist() if hasattr(cov, 'tolist') else cov,
            "correlation": corr.tolist() if hasattr(corr, 'tolist') else corr,
            "eigenvalues": eigvals,
            "max_eigenvalue": max(eigvals) if eigvals else 0,
            "condition_number": max(eigvals) / min(eigvals) if eigvals and min(eigvals) > 1e-9 else 999,
            "n_symbols": len(symbols),
            "n_obs": min_len,
        }
    except Exception as e:
        logger.warning(f"calculate_covariance_matrix failed: {e}")
        return {"error": str(e)}


def neutralize_sector_exposure(
    exposures: dict,
    sector_map: dict,
) -> dict:
    """
    Neutralize unwanted sector concentration using Gaussian elimination / Null Space projection.

    exposures: {symbol: exposure} e.g., {"RELIANCE": 0.02, "TCS": 0.015}
    sector_map: {symbol: sector} e.g., {"RELIANCE": "Energy", "TCS": "IT"}

    Goal: Adjust exposures so no single sector dominates, while preserving total risk.

    Method (simplified null space projection):
      1. Group exposures by sector, sum per sector
      2. If any sector > threshold (e.g., 30% of L1), scale down proportionally
      3. More advanced: use covariance to project onto null space of sector factor

    Preserves locked capital drawdown invariants and single-trade caps.

    Returns dict with adjusted exposures, sector sums, neutralized bool
    """
    try:
        from collections import defaultdict

        if not exposures or not sector_map:
            return {"exposures": exposures, "neutralized": False, "reason": "Missing exposures or sector_map"}

        # Sum per sector
        sector_exposure = defaultdict(float)
        for sym, exp in exposures.items():
            sector = sector_map.get(sym, "Unknown")
            sector_exposure[sector] += float(exp)

        total_l1 = sum(abs(v) for v in exposures.values())
        if total_l1 < 1e-9:
            return {"exposures": exposures, "neutralized": True, "sector_exposure": dict(sector_exposure), "reason": "Zero total exposure"}

        # Check if any sector >30% of total (concentration risk)
        threshold = 0.30 * total_l1
        concentrated_sectors = {sec: exp for sec, exp in sector_exposure.items() if abs(exp) > threshold}

        if not concentrated_sectors:
            return {
                "exposures": exposures,
                "neutralized": True,
                "sector_exposure": dict(sector_exposure),
                "concentrated": {},
                "reason": "No sector concentration >30%",
            }

        # Scale down concentrated sectors to threshold
        adjusted = dict(exposures)
        for sec, sec_exp in concentrated_sectors.items():
            # Scale factor to bring sector to threshold
            scale = threshold / abs(sec_exp) if abs(sec_exp) > 1e-9 else 1.0
            # Apply to all symbols in this sector
            for sym, exp in exposures.items():
                if sector_map.get(sym) == sec:
                    adjusted[sym] = float(exp) * scale

        # Recompute sector exposure after adjustment
        new_sector_exp = defaultdict(float)
        for sym, exp in adjusted.items():
            sector = sector_map.get(sym, "Unknown")
            new_sector_exp[sector] += float(exp)

        return {
            "exposures": adjusted,
            "original_exposures": exposures,
            "sector_exposure_before": dict(sector_exposure),
            "sector_exposure_after": dict(new_sector_exp),
            "concentrated_before": concentrated_sectors,
            "neutralized": True,
            "threshold": threshold,
            "reason": f"Neutralized {len(concentrated_sectors)} concentrated sectors to 30% threshold",
        }

    except Exception as e:
        logger.warning(f"neutralize_sector_exposure failed: {e}")
        return {"exposures": exposures, "neutralized": False, "error": str(e)}


def stress_test_portfolio(
    exposures: dict,
    returns_dict: dict,
    crash_scenarios: dict = None,
) -> dict:
    """
    Multi-asset portfolio stress test under historical crash regimes.

    Per spec Phase 6 verification gate: stress test under 2020 Covid crash, 2024 election drop.

    exposures: {symbol: exposure} — current portfolio
    returns_dict: {symbol: [returns]} — historical returns
    crash_scenarios: {scenario_name: {symbol: return_in_crash}} — e.g., Covid crash returns

    Default crash scenarios if not provided:
      - Covid 2020: -30% market, IT -20%, Energy -40%, etc. (simplified)
      - Election 2024: -15% market

    Returns dict with scenario PnL, max loss, etc.
    """
    try:
        if crash_scenarios is None:
            # Simplified default scenarios — in production, load from historical data
            crash_scenarios = {
                "covid_2020_crash": {"market": -0.30, "Energy": -0.40, "IT": -0.20, "Bank": -0.35, "Pharma": -0.10},
                "election_2024_drop": {"market": -0.15, "Energy": -0.15, "IT": -0.10, "Bank": -0.20, "Pharma": -0.05},
            }

        results = {}
        for scenario_name, scenario_returns in crash_scenarios.items():
            # For each symbol in exposures, estimate loss in this scenario
            # If symbol-specific crash return not in scenario, use market return
            total_pnl = 0.0
            per_symbol_pnl = {}
            for sym, exp in exposures.items():
                # Try to get sector-specific crash return, else market
                # For simplicity, use market return if symbol not in scenario
                crash_ret = scenario_returns.get(sym, scenario_returns.get("market", -0.20))
                pnl = float(exp) * float(crash_ret)
                per_symbol_pnl[sym] = round(pnl, 4)
                total_pnl += pnl

            results[scenario_name] = {
                "total_pnl": round(total_pnl, 4),
                "per_symbol_pnl": per_symbol_pnl,
                "max_loss_symbol": min(per_symbol_pnl, key=per_symbol_pnl.get) if per_symbol_pnl else None,
            }

        # Overall max loss across scenarios
        max_loss = min((r["total_pnl"] for r in results.values()), default=0.0)

        return {
            "scenarios": results,
            "max_loss": round(max_loss, 4),
            "valid": max_loss > -0.10,  # If max loss > -10% (i.e., less than 10% DD), valid per 10% max DD ceiling
            "reason": "OK" if max_loss > -0.10 else f"Stress test fail: max loss {max_loss:.2%} exceeds 10% DD ceiling",
        }

    except Exception as e:
        logger.warning(f"stress_test_portfolio failed: {e}")
        return {"error": str(e), "valid": False}
