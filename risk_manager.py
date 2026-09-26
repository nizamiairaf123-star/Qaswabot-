"""
risk_manager.py — DD blocking, portfolio health gate, all risk checks
Single entry point for "can we trade this stock?"
"""

from config import PARAMS, AUDIT_LOG_FILE
from utils import append_log, is_killswitch_active
from stock_mode_manager import get_mode, is_tradeable, check_and_apply_soft_block
from portfolio_health import get_portfolio_mode
from safety_manager import is_daily_limit_hit, is_max_trades_hit, is_daily_risk_budget_hit
from backtester import check_backtest_staleness
from capital_manager import has_free_slot


def can_enter_trade(symbol: str, current_price: float) -> tuple:
    """
    Master gate — ALL checks in one place.
    Returns: (allowed: bool, reason: str)
    
    Order of checks (first fail = reject):
    1. Killswitch
    2. Market hours (handled by scheduler)
    3. Backtest staleness
    4. Daily loss limit
    5. Max trades per day
    6. Rapid loss pause
    7. Free slot available
    8. Portfolio health mode
    9. Stock mode (PROFIT only)
    10. ASM/GSM / suspended-stock pre-screen (fail-closed stale pause)
    11. DD check (update watermark + check soft block)
    12. Sector exposure
    13. Correlation check
    14. Re-entry cooldown
    """

    # 1. Killswitch
    if is_killswitch_active():
        return False, "⛔ Killswitch active"

    # v3.2 Fail-Closed: BOARD DATA STALE PAUSE — Monthly board update pending/failed
    # [DESIGN: AIRAF NIZAMI] Blocks all new BUY entries if monthly board universe update failed
    try:
        from stock_selector import is_universe_data_stale
        if is_universe_data_stale():
            return False, "⛔ BOARD DATA STALE PAUSE — Monthly board update pending/failed"
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"BOARD STALE CHECK ERROR ({symbol}): {e} (Fail-Closed)")
        return False, f"⛔ BOARD DATA STALE PAUSE — Stale check failed (Fail-Closed): {e}"

    # [OWNER DECISION 2026-09-05 — STATUS PRE-SCREEN] Hard-rejected/banned/suspended
    # status ko scan se pehle identify karo. ASM/GSM membership khud rejection
    # criterion nahi hai. Missing/stale status data → new BUY entries fail-closed
    # blocked because hard status cannot be verified. Exit par koi asar nahi.
    try:
        from asm_gsm_screen import check_entry
        _bl, _rsn = check_entry(symbol)
        if _bl:
            return False, _rsn
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"ASM/GSM CHECK ERROR ({symbol}): {e} (Fail-Closed)")
        return False, f"⛔ ASM/GSM SCREEN UNAVAILABLE (Fail-Closed): {e}"

    # F074/v3.2: Defense-in-depth halal universe gate with Non-Muslim Board enforcement
    # The universe selector is the primary filter (core_business_halal + non_muslim_board + price>100 + liquid + strict NSE-EQ)
    # Master entry gate must also fail closed if any future path bypasses get_tradeable_universe().
    try:
        from stock_selector import is_in_halal_universe, is_deployed_strategy_valid
        if not is_in_halal_universe(symbol):
            return False, f"⛔ {symbol}: Not in validated halal tradeable universe (Core Halal + 100% Non-Muslim Board + Price>100 + Liquid + NSE-EQ)"
        # Full-universe scanning is intentionally broader than deployed strategy
        # eligibility. Only a symbol with a valid deployed/backtest strategy may
        # cross the final capital-entry boundary.
        if not is_deployed_strategy_valid(symbol):
            return False, f"⛔ {symbol}: No valid deployed/backtest strategy"
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"HALAL GATE CHECK ERROR ({symbol}): {e}")
        return False, f"⛔ {symbol}: Halal universe check failed (Fail-Closed)"

    # FIX-03: Capital survival hard brake / circuit override
    try:
        from risk_override_manager import check_capital_survival_override
        survival_ok, survival_reason = check_capital_survival_override(apply_state=True)
        if not survival_ok:
            return False, survival_reason
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"CAPITAL SURVIVAL CHECK ERROR: {e}")
        return False, f"⛔ Capital survival check failed (Fail-Closed): {e}"

    # Decision 08: No-trade gate consumes stage readiness owner output.
    try:
        from capital_manager import get_stage_readiness_decision
        stage_ready = get_stage_readiness_decision(symbol=symbol)
        if not stage_ready.get("allow", False):
            return False, f"⛔ Stage readiness block: {stage_ready.get('reason')}"
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"STAGE READINESS CHECK ERROR ({symbol}): {e}")
        return False, f"⛔ Stage readiness check failed: {e}"

    # 2. Backtest staleness
    staleness = check_backtest_staleness()
    if staleness["status"] == "BLOCK":
        return False, staleness["message"]

    # 3. Daily loss limit
    if is_daily_limit_hit():
        return False, "⛔ Daily loss limit reached — no new trades today"

    # 4. Max trades per day
    if is_max_trades_hit():
        return False, f"⛔ Max {PARAMS['max_trades_per_day']} trades/day reached"

    # 5. Daily risk budget
    if is_daily_risk_budget_hit():
        return False, f"⛔ Daily risk budget exhausted"

    # 5c. Spread check — block if bid-ask spread too wide
    spread_ok, spread_reason = _check_spread(symbol)
    if not spread_ok:
        return False, spread_reason

    # 6. Free slot
    if not has_free_slot():
        return False, f"⛔ Max {PARAMS['max_slots']} positions open"

    # 7. Portfolio health
    portfolio_mode = get_portfolio_mode()
    if portfolio_mode == "WARNING":
        return False, "⛔ Portfolio in WARNING mode — no new entries"
    if portfolio_mode == "FAILED":
        return False, "⛔ Portfolio FAILED — strategy re-optimization needed"

    # 8. Stock mode check + DD update
    check_and_apply_soft_block(symbol, current_price)
    if not is_tradeable(symbol):
        mode = get_mode(symbol)
        return False, f"BLOCKED {symbol}: mode={mode}"

    # 9. Same-day CNC exit possible? (NOT an MIS switch)
    # BE/T2T: entry allowed, same-day exit banned → SL hit pe nikal nahi paoge.
    from intraday_filter import is_intraday_allowed
    from stock_selector import get_security_id
    security_id = get_security_id(symbol)
    if not is_intraday_allowed(security_id, symbol):
        return False, (f"⛔ {symbol}: same-day CNC exit not possible "
                       f"(BE/T2T/series) — entry skip, SL/TP stuck ho jaayega")

    # 10. Sector exposure
    sector_ok, sector_reason = check_sector_exposure(symbol)
    if not sector_ok:
        return False, sector_reason

    # 10b. [AUDIT FIX — item 5/6] Sector strength (defense-in-depth): the
    # STRONG-only entry filter is applied at signal-generation time
    # (strategy.generate_signals -> get_macro_context), but this final gate did
    # not independently re-check it — matching the same double-layer pattern
    # already used for the halal/board check (checked at signal time AND here).
    try:
        from sector_strength import is_stock_sector_strong, get_sector_runtime_signal
        if not is_stock_sector_strong(symbol):
            ctx = get_sector_runtime_signal(symbol)
            return False, f"⛔ {symbol}: sector '{ctx.get('sector')}' not STRONG (status={ctx.get('status')}) — long-only entries require a confirmed-strong sector"
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        append_log(AUDIT_LOG_FILE, f"can_enter_trade: sector-strength check failed for {symbol}: {type(e).__name__}: {e} — Fail-Closed (blocking entry)")
        return False, f"⛔ {symbol}: sector-strength check failed, blocking as a precaution"

    # 10. Correlation check
    corr_ok, corr_reason = check_correlation(symbol)
    if not corr_ok:
        return False, corr_reason

    # 10b. VIX + USDINR cross-asset correlation
    try:
        from correlation_tracker import check_vix_correlation, check_usdinr_correlation
        vix_result = check_vix_correlation(symbol)
        if vix_result.get("correlated"):
            return False, f"⛔ {symbol}: {vix_result['reason']}"
        usdinr_result = check_usdinr_correlation(symbol)
        if usdinr_result.get("correlated"):
            return False, f"⛔ {symbol}: {usdinr_result['reason']}"
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"VIX/USDINR CHECK ERROR ({symbol}): {e} (Fail-Closed)")
        return False, f"⛔ {symbol}: VIX/USDINR check failed (Fail-Closed)"

    # 11. Re-entry cooldown
    cooldown_ok, cooldown_reason = check_reentry_cooldown(symbol)
    if not cooldown_ok:
        return False, cooldown_reason

    return True, "✅ All checks passed"


# ─────────────────────────────────────────────
# SECTOR EXPOSURE
# ─────────────────────────────────────────────

def check_sector_exposure(symbol: str) -> tuple:
    """Max stocks per sector check — v3.2 uses CUSTOM universe only (single source)"""
    try:
        from capital_manager import get_active_trades
        import pandas as pd
        csv_path = "data/CUSTOM_UNIVERSE_FINAL.csv"
        halal_df = pd.read_csv(csv_path)
        symbol_sector = halal_df[halal_df["symbol"] == symbol]["sector"].values
        if len(symbol_sector) == 0:
            return False, f"⛔ Sector exposure check failed: no sector data for {symbol}"

        sector = symbol_sector[0]
        if pd.isna(sector) or str(sector).strip() in {"", "0", "nan", "None"}:
            return False, f"⛔ Sector exposure check failed: invalid sector data for {symbol}"
        active = get_active_trades()
        sector_count = 0

        for sym in active:
            sym_sector = halal_df[halal_df["symbol"] == sym]["sector"].values
            if len(sym_sector) > 0 and sym_sector[0] == sector:
                sector_count += 1

        if sector_count >= PARAMS["max_stocks_per_sector"]:
            return False, f"⛔ Sector '{sector}' limit reached ({sector_count} stocks)"
        return True, ""
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"SECTOR CHECK ERROR ({symbol}): {e}")
        return False, f"⛔ Sector check failed due to error: {e}"


def check_correlation(symbol: str) -> tuple:
    """Block if highly correlated stock already in portfolio."""
    try:
        from correlation_tracker import is_correlated_with_active
        if is_correlated_with_active(symbol):
            return False, f"⛔ {symbol} correlated with existing position"
        return True, ""
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"CORRELATION CHECK ERROR ({symbol}): {e}")
        return False, f"⛔ Correlation check failed due to error: {e}"


def check_reentry_cooldown(symbol: str) -> tuple:
    """Block re-entry if SL hit recently."""
    try:
        from trade_logger import get_last_sl_hit_date
        from utils import trading_days_between, today_ist
        last_sl = get_last_sl_hit_date(symbol)
        if last_sl is None:
            return True, ""
        days_since = trading_days_between(last_sl, today_ist())
        cooldown = PARAMS["reentry_cooldown_days"]
        if days_since < cooldown:
            return False, f"⛔ {symbol} SL cooldown: {cooldown - days_since} trading days remaining"
        return True, ""
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"COOLDOWN CHECK ERROR ({symbol}): {e}")
        return False, f"⛔ Re-entry cooldown check failed due to error: {e}"


# ─────────────────────────────────────────────
# SPREAD CHECK
# Verified: Institutional execution — wide spread = bad fill quality
# Uses Dhan get_market_depth for real bid-ask
# ─────────────────────────────────────────────

def _check_spread(symbol: str) -> tuple:
    """Block entry if bid-ask spread > max_spread_pct."""
    try:
        max_spread_pct = PARAMS.get("max_spread_pct", 0.5)
        if max_spread_pct <= 0:
            return True, ""  # Disabled

        from stock_selector import get_security_id
        security_id = get_security_id(symbol)
        if not security_id:
            return False, f"⛔ {symbol}: Security ID missing for spread check"

        from broker import get_dhan
        dhan = get_dhan()
        depth = dhan.get_market_depth(
            security_id=security_id,
            exchange_segment="NSE_EQ",
        )
        if not depth or not isinstance(depth, dict):
            return False, f"⛔ {symbol}: Market depth data unavailable for spread check"

        # Extract best bid/ask from depth
        bids = depth.get("bids", depth.get("buy", []))
        asks = depth.get("asks", depth.get("sell", []))
        if not bids or not asks:
            return False, f"⛔ {symbol}: Empty order book in depth check"

        best_bid = float(bids[0].get("price", 0)) if isinstance(bids[0], dict) else 0
        best_ask = float(asks[0].get("price", 0)) if isinstance(asks[0], dict) else 0

        if best_bid <= 0 or best_ask <= 0:
            return False, f"⛔ {symbol}: Invalid bid/ask prices in depth check"

        mid = (best_bid + best_ask) / 2
        spread_pct = (best_ask - best_bid) / mid * 100

        if spread_pct > max_spread_pct:
            return False, f"⛔ {symbol} spread={spread_pct:.2f}% > max={max_spread_pct}%"
        return True, ""
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"SPREAD CHECK ERROR ({symbol}): {e}")
        return False, f"⛔ Spread check failed due to error: {e}"
