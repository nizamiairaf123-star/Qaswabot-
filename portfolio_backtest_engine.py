"""
portfolio_backtest_engine.py — QUANT-002 fix.

PROBLEM (confirmed by grep — zero matches for `can_enter_trade` in
backtester.py / parity_engine.py / strategy.py): every stock is backtested
in isolation. `portfolio_max_dd_pct` is just the average of independent
per-stock drawdowns — it proves nothing about what would happen if several
of those trades' real-world entries had actually competed for the SAME
capital slots, sector cap, correlation limit and re-entry cooldown that
risk_manager.can_enter_trade() enforces live. A backtest that never applies
those four checks cannot claim to represent real concurrent-portfolio risk.

FIX: reuse strategy.backtest_on_data() UNCHANGED for per-symbol signal
generation (zero risk to core strategy math), then merge every symbol's
candidate trades chronologically and replay them through ONE shared
simulated portfolio, applying the SAME formulas the live gates use for the
four checks that are genuinely point-in-time reconstructable from data this
codebase actually has:

  - max_slots           — same dynamic economics-based cap as
                           capital_manager.has_free_slot() (falls back to
                           static PARAMS["max_slots"] identically)
  - max_stocks_per_sector — same formula as risk_manager.check_sector_exposure()
  - correlation_threshold — same 90-day/>=20-overlap-days rule as
                           correlation_tracker.is_correlated_with_active(),
                           but using each symbol's own historical price data
                           strictly UP TO the candidate trade's entry date
                           (no look-ahead) instead of a live API fetch
  - reentry_cooldown_days — same trading_days_between() formula as
                           risk_manager.check_reentry_cooldown(); "SL hit" is
                           approximated as any exit with net_return_pct < 0,
                           because strategy.backtest_on_data()'s trades_list
                           has no explicit exit-reason field to distinguish a
                           real SL exit from a timeout/other loss exit — this
                           is a documented approximation, not fabricated data

Deliberately OUT OF SCOPE (same reasoning as parity_engine.py's own R1-R4
docstring: these read LIVE-only state with no historical per-date archive
anywhere in this codebase, so applying "today's" value to a historical
trade would not be point-in-time correct — not a fix that was skipped, a
fix that cannot honestly be built from data that doesn't exist):
killswitch, board-data-stale pause, capital-survival override, stage
readiness, backtest-staleness self-check, daily loss limit, max trades/day,
daily risk budget, bid-ask spread check, portfolio-health mode, stock
mode/DD soft-block, intraday-band check, sector-strength STRONG filter,
VIX/USDINR cross-asset correlation.
"""

import logging
import pandas as pd

from config import PARAMS, AUDIT_LOG_FILE
from utils import append_log, trading_days_between
from strategy import get_active_strategy
from backtester import fetch_historical_data, load_halal_symbols

logger = logging.getLogger(__name__)

_UNIVERSE_CSV = "data/CUSTOM_UNIVERSE_FINAL.csv"


def _load_sector_map() -> dict:
    try:
        df = pd.read_csv(_UNIVERSE_CSV)
        return dict(zip(df["symbol"], df["sector"]))
    except Exception as e:
        logger.warning(f"[PORTFOLIO-BT] sector map load failed: {e}")
        return {}


def _get_max_slots(capital: float) -> int:
    """Mirrors capital_manager.has_free_slot(): try the dynamic
    economics-based candidate first, fall back to static PARAMS on any
    failure — identical fallback behavior to the live function."""
    try:
        from economics_brain import get_recommended_max_slots
        slots = get_recommended_max_slots(capital)
        if slots and slots > 0:
            return int(slots)
    except Exception as e:
        logger.warning(f"[PORTFOLIO-BT] dynamic max_slots failed: {e} — using static PARAMS")
    return int(PARAMS.get("max_slots", 8))


def _trailing_returns_asof(df: pd.DataFrame, asof_date, window: int = 90) -> pd.Series:
    """Returns series using only bars with date <= asof_date (no look-ahead)."""
    try:
        sub = df[df.index <= asof_date].tail(window + 1)
        if len(sub) < 2:
            return pd.Series(dtype="float64")
        return sub["close"].pct_change().dropna()
    except Exception:
        return pd.Series(dtype="float64")


def _is_correlated_asof(symbol, entry_date, df_by_symbol, active_symbols, threshold):
    """Same pairwise logic as correlation_tracker.is_correlated_with_active():
    fail-closed (block) if the NEW symbol has no usable trailing data;
    fail-open per-pair (skip that comparison, don't block) if a given active
    symbol has <20 overlapping observations — exactly matching the live
    function's own stance in both cases."""
    df_new = df_by_symbol.get(symbol)
    if df_new is None or df_new.empty:
        return True, "no price data for correlation check (fail-closed)"
    sym_returns = _trailing_returns_asof(df_new, entry_date)
    if sym_returns.empty:
        return True, "insufficient trailing data for correlation check (fail-closed)"

    for active_sym in active_symbols:
        df_active = df_by_symbol.get(active_sym)
        if df_active is None or df_active.empty:
            continue
        active_returns = _trailing_returns_asof(df_active, entry_date)
        if active_returns.empty:
            continue
        combined = pd.concat([sym_returns, active_returns], axis=1, join="inner").dropna()
        if len(combined) < 20:
            continue
        corr = combined.iloc[:, 0].corr(combined.iloc[:, 1])
        if corr is not None and corr >= threshold:
            return True, f"correlated with {active_sym} (corr={corr:.2f})"
    return False, ""


def run_portfolio_backtest(symbols: list = None) -> dict:
    """
    Runs the concentration-gated multi-symbol backtest described above.
    Returns a dict with `portfolio_max_dd_pct_concentration_gated` plus
    diagnostic breakdown of what got blocked and why.
    """
    if symbols is None:
        symbols = load_halal_symbols()

    candidate_trades, df_by_symbol = _generate_candidates(symbols)
    sector_map = _load_sector_map()
    return _replay_candidates(candidate_trades, df_by_symbol, sector_map)


def _generate_candidates(symbols: list):
    """Runs strategy.backtest_on_data() per symbol (UNCHANGED signal logic)
    and returns (candidate_trades, df_by_symbol). Split out from
    run_portfolio_backtest() so the replay/gating logic below can be
    unit-tested directly against hand-built candidate lists."""
    strategy = get_active_strategy()
    min_pts = PARAMS.get("backtest_min_data_points", 100)

    df_by_symbol = {}
    candidate_trades = []

    for symbol in symbols:
        try:
            df = fetch_historical_data(symbol, period_days=3650)
        except Exception as e:
            append_log(AUDIT_LOG_FILE, f"PORTFOLIO-BT: {symbol} data fetch failed: {e}")
            continue
        if df.empty or len(df) < min_pts:
            continue
        df_by_symbol[symbol] = df
        try:
            results = strategy.backtest_on_data(df, symbol)
        except Exception as e:
            append_log(AUDIT_LOG_FILE, f"PORTFOLIO-BT: {symbol} signal-gen failed: {e}")
            continue
        trades = (results or {}).get("trades_list") or []
        for t in trades:
            try:
                entry_idx = int(t["entry_idx"])
                exit_idx = int(t["exit_idx"])
                entry_date = df.index[entry_idx]
                exit_date = df.index[exit_idx]
                net_pct = t.get("net_return_pct")
                if net_pct is None:
                    net_pct = t.get("return_pct", 0) - PARAMS["trading_cost_pct"]
                candidate_trades.append({
                    "symbol": symbol,
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "net_return_pct": float(net_pct),
                })
            except (KeyError, ValueError, TypeError, IndexError):
                continue

    return candidate_trades, df_by_symbol


def _replay_candidates(candidate_trades: list, df_by_symbol: dict, sector_map: dict) -> dict:
    candidate_trades = sorted(candidate_trades, key=lambda t: t["entry_date"])

    threshold = float(PARAMS.get("correlation_threshold", 0.85))
    max_sector = int(PARAMS.get("max_stocks_per_sector", 2))
    cooldown_days = int(PARAMS.get("reentry_cooldown_days", 3))
    capital = float(PARAMS["validator_reference_capital"])

    active = {}          # symbol -> exit_date (open positions)
    last_loss_exit = {}  # symbol -> exit_date of most recent losing exit (SL proxy)
    kept_trades = []
    equity = []
    blocked = {"max_slots": 0, "sector_cap": 0, "correlation": 0, "cooldown": 0}

    for t in candidate_trades:
        entry_date, exit_date, symbol = t["entry_date"], t["exit_date"], t["symbol"]

        for s in [s for s, xd in active.items() if xd < entry_date]:
            del active[s]

        max_slots = _get_max_slots(capital)
        if len(active) >= max_slots:
            blocked["max_slots"] += 1
            continue

        sector = sector_map.get(symbol)
        sector_valid = sector is not None and str(sector).strip() not in ("", "0", "nan", "None")
        if not sector_valid:
            # Same fail-closed stance as live check_sector_exposure() when
            # sector data is missing/invalid for the symbol.
            blocked["sector_cap"] += 1
            continue
        sector_count = sum(
            1 for s in active
            if str(sector_map.get(s, "")).strip() == str(sector).strip()
        )
        if sector_count >= max_sector:
            blocked["sector_cap"] += 1
            continue

        if active:
            corr_blocked, _ = _is_correlated_asof(
                symbol, entry_date, df_by_symbol, list(active.keys()), threshold
            )
            if corr_blocked:
                blocked["correlation"] += 1
                continue

        last_loss = last_loss_exit.get(symbol)
        if last_loss is not None:
            days_since = trading_days_between(last_loss.date(), entry_date.date())
            if days_since < cooldown_days:
                blocked["cooldown"] += 1
                continue

        active[symbol] = exit_date
        smax = max(1, max_slots)
        capital *= (1 + (t["net_return_pct"] / 100.0) / smax)
        equity.append(capital)
        kept_trades.append(t)
        if t["net_return_pct"] < 0:
            last_loss_exit[symbol] = exit_date

    if equity:
        equity_series = pd.Series(equity)
        rolling_max = equity_series.cummax()
        dd_series = (equity_series - rolling_max) / rolling_max * 100
        portfolio_max_dd_concentration_gated = float(dd_series.min())
    else:
        portfolio_max_dd_concentration_gated = 0.0

    total_candidates = len(candidate_trades)
    total_kept = len(kept_trades)

    result = {
        "portfolio_max_dd_pct_concentration_gated": round(portfolio_max_dd_concentration_gated, 2),
        "final_capital_concentration_gated": round(capital, 2),
        "total_candidate_trades": total_candidates,
        "kept_trades": total_kept,
        "blocked_trades": total_candidates - total_kept,
        "blocked_breakdown": blocked,
        "gates_applied": [
            "max_slots(dynamic-economics-based, same as capital_manager.has_free_slot)",
            "max_stocks_per_sector(same as risk_manager.check_sector_exposure)",
            "correlation_threshold(PIT-safe, same as correlation_tracker.is_correlated_with_active)",
            "reentry_cooldown_days(same formula, SL-hit approximated as any losing exit)",
        ],
        "gates_not_applied_reason": (
            "killswitch/board-stale-pause/capital-survival-override/stage-readiness/"
            "backtest-staleness/daily-loss-limit/max-trades-per-day/daily-risk-budget/"
            "spread-check/portfolio-health-mode/stock-mode-DD-softblock/intraday-band/"
            "sector-strength-STRONG-filter/VIX-USDINR-correlation — all read live-only "
            "state with no historical per-date archive in this codebase (same reasoning "
            "as parity_engine.py's own R1-R4 docstring)"
        ),
    }

    append_log(
        AUDIT_LOG_FILE,
        f"PORTFOLIO-BT CONCENTRATION-GATED: candidates={total_candidates} "
        f"kept={total_kept} blocked={total_candidates - total_kept} "
        f"({blocked}) dd={portfolio_max_dd_concentration_gated:.2f}%"
    )
    return result
