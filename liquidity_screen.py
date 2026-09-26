"""
liquidity_screen.py — Turnover-based trading-liquidity screen.

[AUDIT ADD] Distinct from illiquid_asset_pct/net_liquid_ok (a Sharia
balance-sheet ratio, see sharia screening columns) — this is a real
TRADING-volume liquidity screen: does this stock always have active
buyers/sellers, sized relative to the company's own market cap, so exit
is reliably easy (not just entry)?

Method: MSCI Global Investable Market Indices Methodology's ATVR (63-Day Rolling Screen, ~3 Months)
(Annualized Traded Value Ratio) + Frequency of Trading — a published,
industry-standard, size-normalized liquidity screen used for index
inclusion eligibility (source: MSCI GIMI Methodology, msci.com). Adapted
here for NSE using Dhan historical data (NOT yfinance, NOT a third-party
index feed — same data source as all other price/volume data in this bot).

  ATVR = (average daily traded value over a lookback window, annualized)
         ÷ market capitalization, expressed as a %.
         A bigger company needs proportionally more absolute rupee volume
         to count as "liquid" — this ratio is fair across company sizes.

  Frequency of Trading = % of days in the lookback window where the stock
         actually had at least one trade (volume > 0). Directly answers
         "does this stock always have a buyer/seller present" — a stock
         that only trades 60% of days has no counterparty 40% of the time.

MSCI's own published minimums for Emerging Markets (India is EM): ~15% of
3-month ATVR and ~80% of 3-month Frequency of Trading. This module uses
those as defaults (config.py PARAMS, owner-adjustable within a band).

[AUDIT NOTE — honest cadence disclosure] MSCI's own methodology reviews
this as part of Quarterly/Semi-Annual Index Reviews, NOT monthly, and
requires the minimum to be met over 4 CONSECUTIVE quarters (a ~1-year
persistence/stability requirement) before a security qualifies — not just
the latest snapshot. This module's refresh cadence is MONTHLY with only
the latest 63-day window checked each time (no multi-period persistence
requirement) — an intentional owner decision (more frequent than MSCI's
own cadence, so liquidity deterioration is caught faster), NOT a literal
implementation of MSCI's full review cadence. The ATVR/FoT ratio formulas
and threshold values are MSCI's; the review schedule is this bot's own.
"""

from utils import load_json, save_json, logger, now_ist, append_log
from config import PARAMS, CUSTOM_UNIVERSE_FILE, AUDIT_LOG_FILE, DATA_DIR

LIQUIDITY_STATE_FILE = f"{DATA_DIR}/liquidity_data_state.json"


def calculate_atvr_and_fot(candles, market_cap: float,
                            lookback_days: int = None) -> dict:
    """
    Compute ATVR % and Frequency-of-Trading % from a daily OHLCV DataFrame.

    Fails closed (eligible=False) on any missing/insufficient data — a
    stock we can't verify as liquid is treated as NOT liquid, matching
    the same fail-safe philosophy used for the board/Sharia screen.
    """
    lookback_days = lookback_days or int(PARAMS.get("liquidity_lookback_trading_days", 63))
    min_atvr = float(PARAMS.get("min_atvr_pct", 15.0))
    min_fot = float(PARAMS.get("min_frequency_of_trading_pct", 80.0))

    result = {"atvr_pct": 0.0, "frequency_of_trading_pct": 0.0,
              "eligible": False, "reason": ""}

    try:
        if candles is None or candles.empty:
            result["reason"] = "no candle data"
            return result
        if not market_cap or market_cap <= 0:
            result["reason"] = "no/invalid market cap"
            return result

        window = candles.tail(lookback_days)
        if len(window) < max(20, lookback_days // 3):
            # Too little history to trust the ratio — fail closed rather
            # than judge liquidity off a handful of days (e.g. a recent IPO).
            result["reason"] = f"insufficient history ({len(window)} days < minimum)"
            return result

        daily_traded_value = (window["close"] * window["volume"]).fillna(0)
        avg_daily_traded_value = float(daily_traded_value.mean())
        annualized_traded_value = avg_daily_traded_value * float(PARAMS.get("trading_days_per_year", 252))
        atvr_pct = (annualized_traded_value / market_cap) * 100.0

        days_traded = int((window["volume"] > 0).sum())
        frequency_of_trading_pct = (days_traded / len(window)) * 100.0

        eligible = (atvr_pct >= min_atvr) and (frequency_of_trading_pct >= min_fot)
        result.update({
            "atvr_pct": round(atvr_pct, 2),
            "frequency_of_trading_pct": round(frequency_of_trading_pct, 2),
            "eligible": eligible,
            "reason": "ok" if eligible else f"below threshold (need ATVR>={min_atvr}%, FoT>={min_fot}%)",
        })
        return result
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as e:
        logger.warning(f"calculate_atvr_and_fot: failed: {type(e).__name__}: {e}")
        result["reason"] = f"calc error: {e}"
        return result


def refresh_liquidity_data() -> bool:
    """
    Recompute ATVR/Frequency-of-Trading for every symbol in the current
    universe and write the results back into CUSTOM_UNIVERSE_FINAL.csv as
    new columns (turnover_liquid_ok, atvr_pct, frequency_of_trading_pct) —
    same convention as the other per-symbol eligibility flags in that file.

    Returns True only if at least one symbol was successfully scored this
    run (mirrors the Gap #12 pattern for sector/FII refresh — lets the
    scheduler detect a total failure, e.g. Dhan historical-data API down).
    """
    try:
        import pandas as pd
        from dhan_data import fetch_daily_data
    except ImportError as e:
        append_log(AUDIT_LOG_FILE, f"LIQUIDITY REFRESH: import failed: {e}")
        return False

    # Bootstrap rule: read the candidate CSV directly instead of calling
    # stock_selector.load_halal_universe().  The selector intentionally
    # returns an empty frame while the universe is paused/stale; using it
    # here created a circular deadlock where liquidity could never be
    # populated and therefore the pause could never become clearable.
    # This refresh only CALCULATES metrics. It does not authorize trading;
    # downstream eligibility and freshness gates remain fail-closed.
    try:
        df = pd.read_csv(CUSTOM_UNIVERSE_FILE, low_memory=False)
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"LIQUIDITY REFRESH: cannot read candidate universe: {e}")
        return False
    if df is None or df.empty:
        append_log(AUDIT_LOG_FILE, "LIQUIDITY REFRESH: candidate universe is empty, nothing to score")
        return False

    lookback_days = int(PARAMS.get("liquidity_lookback_trading_days", 63))
    scored = 0
    for idx, row in df.iterrows():
        symbol = row.get("symbol")
        market_cap = row.get("market_cap")
        if not symbol:
            continue
        try:
            candles = fetch_daily_data(symbol, days=int(lookback_days * float(PARAMS.get("liquidity_fetch_buffer_mult", 2.2))))  # buffer for weekends/holidays
            metrics = calculate_atvr_and_fot(candles, market_cap, lookback_days)
            df.at[idx, "turnover_liquid_ok"] = bool(metrics["eligible"])
            df.at[idx, "atvr_pct"] = metrics["atvr_pct"]
            df.at[idx, "frequency_of_trading_pct"] = metrics["frequency_of_trading_pct"]
            if metrics["eligible"]:
                scored += 1
        except (RuntimeError, ValueError, TypeError) as e:
            logger.warning(f"refresh_liquidity_data: {symbol} failed: {type(e).__name__}: {e}")
            df.at[idx, "turnover_liquid_ok"] = False  # fail closed for this row

    if scored == 0:
        append_log(AUDIT_LOG_FILE, "LIQUIDITY REFRESH: got ZERO eligible/scoreable symbols this run (Dhan historical-data outage?) — universe file NOT overwritten")
        return False

    try:
        import os
        tmp = CUSTOM_UNIVERSE_FILE + ".liquidity.tmp"
        df.to_csv(tmp, index=False)
        os.replace(tmp, CUSTOM_UNIVERSE_FILE)
    except OSError as e:
        append_log(AUDIT_LOG_FILE, f"LIQUIDITY REFRESH: failed to publish {CUSTOM_UNIVERSE_FILE}: {e}")
        return False

    state = load_json(LIQUIDITY_STATE_FILE, {})
    state["last_successful_update"] = now_ist().isoformat()
    state["symbols_scored"] = len(df)
    state["symbols_eligible"] = scored
    save_json(LIQUIDITY_STATE_FILE, state)
    append_log(AUDIT_LOG_FILE, f"LIQUIDITY REFRESH: {scored}/{len(df)} symbols pass the turnover-liquidity screen")
    return True


def is_liquidity_data_stale() -> bool:
    """
    Fail-Closed staleness check, same pattern as
    stock_selector.is_universe_data_stale() (Bug #9's fix) — any read/parse
    failure or unparseable timestamp is treated as stale, not "assume fine".
    A genuinely-missing state file (first run) is also treated as stale: the
    liquidity screen is mandatory when enabled, so "never verified" means
    BLOCK until the first successful refresh creates the state file.
    """
    if not PARAMS.get("enable_turnover_liquidity_filter", True):
        return False  # feature disabled entirely — staleness is moot

    try:
        from datetime import datetime
        state = load_json(LIQUIDITY_STATE_FILE, {})
        if not state:
            return True  # first deployment / missing state = never verified -> fail closed
        last_success = state.get("last_successful_update")
        if not last_success:
            return True  # state exists but no timestamp recorded — unknown age, fail closed
        last_dt = datetime.fromisoformat(last_success)
        now = now_ist().replace(tzinfo=None)
        delta_days = (now - last_dt.replace(tzinfo=None)).days
        stale_limit = int(PARAMS.get("liquidity_data_stale_days_limit", 45))
        return delta_days > stale_limit
    except (ValueError, TypeError, KeyError, OSError) as e:
        logger.error(f"is_liquidity_data_stale: parse failed: {type(e).__name__}: {e} — Fail-Closed (treating as stale)")
        return True
