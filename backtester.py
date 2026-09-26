"""
backtester.py — Backtest engine
Price-based DD (same formula as live), trading cost included
Mandatory before first trade
"""

import pandas as pd
import numpy as np
import json
from config import PARAMS, BACKTEST_RESULTS_FILE, CUSTOM_UNIVERSE_FILE, AUDIT_LOG_FILE
from utils import save_json, load_json, now_ist, append_log, safe_div
from strategy import get_active_strategy, calculate_price_dd_during_trade
from dhan_data import fetch_daily_data


# ─────────────────────────────────────────────
# DATA FETCHER
# ─────────────────────────────────────────────

def fetch_historical_data(symbol: str, period_days: int = 3650) -> pd.DataFrame:
    """
    Fetch OHLCV data from Dhan API.
    Replaces yfinance — no .NS suffix needed.
    """
    try:
        df = fetch_daily_data(symbol, days=period_days)
        if df.empty:
            append_log(AUDIT_LOG_FILE, f"BACKTEST DATA FETCH: Empty data for {symbol}")
            return pd.DataFrame()
        return df
    except (ConnectionError, TimeoutError, OSError, ValueError) as e:
        append_log(AUDIT_LOG_FILE, f"BACKTEST DATA FETCH ERROR: {symbol} {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# SINGLE STOCK BACKTEST
# ─────────────────────────────────────────────

def calculate_monte_carlo_dd_pct(net_returns_pct: list, capital: float,
                                  num_simulations: int = 1000,
                                  safety_percentile: float = 95.0,
                                  min_trades_required: int = 20) -> dict:
    """
    [VERIFIED QUANT METHOD] Monte Carlo bootstrap resampling of a strategy's
    actual historical trade returns, to estimate a statistically realistic
    worst-case drawdown -- NOT the single backtest's observed max drawdown.

    A single backtest only shows ONE possible ordering of trades. Multiple
    independent sources (AlgoTest, BuildAlpha, TradeZella Monte Carlo
    simulators, and the academic "Maximum Drawdown at Risk" methodology,
    ScienceDirect) confirm the single-run backtest max drawdown routinely
    understates true risk, because a different (equally likely) ordering
    of the same trades can produce a materially worse drawdown. The fix
    used industry-wide: randomly reshuffle the historical trade-return
    sequence thousands of times, compute the resulting drawdown for each
    shuffle, and use a conservative percentile (95th is standard) of that
    distribution as the real risk figure.

    Method:
    1. Take the strategy's actual historical net-return-% per trade.
    2. Randomly permute (reshuffle) this sequence `num_simulations` times.
    3. For each shuffle, compound through a simulated equity curve
       starting at `capital` and record that path's maximum drawdown %.
    4. Return the `safety_percentile`-th percentile of the resulting
       drawdown distribution (the value that is at least as bad as
       `safety_percentile`% of all simulated paths).

    Fails closed (Constitution Art. 2.4a -- no invented fallback number)
    if there are fewer than `min_trades_required` trades: too small a
    sample for a shuffled distribution to mean anything statistically.
    """
    if not net_returns_pct or len(net_returns_pct) < min_trades_required:
        return {
            "error": (
                f"Insufficient trade history for Monte Carlo simulation "
                f"({len(net_returns_pct) if net_returns_pct else 0} trades, "
                f"need >= {min_trades_required})"
            )
        }
    if capital is None or capital <= 0:
        return {"error": "Invalid capital for Monte Carlo simulation"}

    returns = np.array(net_returns_pct, dtype="float64") / 100.0
    rng = np.random.default_rng()
    max_drawdowns_pct = np.empty(num_simulations, dtype="float64")

    for i in range(num_simulations):
        shuffled = rng.permutation(returns)
        equity = float(capital) * np.cumprod(1.0 + shuffled)
        running_max = np.maximum.accumulate(equity)
        # Positive-magnitude drawdown (running_max - equity, not equity -
        # running_max) so percentile direction below is correct: a HIGHER
        # percentile means a WORSE (larger-magnitude) drawdown, matching
        # "95th percentile" meaning "worse than 95% of simulated paths."
        drawdown_series = (running_max - equity) / running_max * 100.0
        max_drawdowns_pct[i] = drawdown_series.max() if len(drawdown_series) > 0 else 0.0

    safe_dd_pct = float(np.percentile(max_drawdowns_pct, safety_percentile))
    median_dd_pct = float(np.percentile(max_drawdowns_pct, 50))
    worst_dd_pct = float(max_drawdowns_pct.max())

    return {
        "trades_used": len(net_returns_pct),
        "num_simulations": num_simulations,
        "safety_percentile": safety_percentile,
        "monte_carlo_dd_pct": round(abs(safe_dd_pct), 2),
        "monte_carlo_median_dd_pct": round(abs(median_dd_pct), 2),
        "monte_carlo_worst_dd_pct": round(abs(worst_dd_pct), 2),
    }


def backtest_single(symbol: str) -> dict:
    """
    Run backtest for one stock.
    Returns metrics including price_max_drawdown_pct (saved as DD reference).
    PILLAR 3: Includes Fundamental DNA alongside Technical triggers for audit attribution.
    """
    strategy = get_active_strategy()
    df = fetch_historical_data(symbol, period_days=3650)

    # PILLAR 3 CORRECTED: REAL DATA ONLY, PIT-SAFE, FAIL-CLOSED when mandatory
    # Same PIT logic as live: AS_OF(T) → latest eligible observation available at T
    # For trade date T: Only info publicly available on or before T may be used
    # Backtest and live must use same PIT logic
    _fund_dna = {}
    _fund_eval = {}
    _fund_alignment = {}
    as_of_date = None
    try:
        from fundamental_data import get_latest_fundamental_dna
        from fundamental_sync_engine import evaluate_fundamental_dna, enrich_with_fundamental_dna, _is_fundamental_mandatory
        
        # Use last bar date as as_of for PIT correctness — same as live trade_date
        try:
            if not df.empty:
                as_of_date = str(df.index[-1].date()) if hasattr(df.index[-1], 'date') else str(df.index[-1])[:10]
        except Exception:
            as_of_date = None
        
        is_mandatory = _is_fundamental_mandatory()
        
        # PIT retrieval: same logic as live — announcement_date <= as_of_date
        _fund_dna = get_latest_fundamental_dna(symbol, as_of=as_of_date, fail_closed_if_missing=is_mandatory)
        _fund_eval = evaluate_fundamental_dna(_fund_dna)
        
        # Build full alignment for traceability: raw Fundamental → Technical → final decision
        technical_context = {
            "technical_status": "STRONG" if results.get("trades_list") else "NEUTRAL",
            "technical_tools_used": ["SEQ", "EMA", "ATR", "RSI", "Volume"],
            "technical_alignment": "ALIGNED",
            "trades_count": len(results.get("trades_list", [])) if results else 0,
        }
        _fund_alignment = enrich_with_fundamental_dna(symbol, technical_context, as_of=as_of_date)
        
        # If fundamental mandatory and missing → mark backtest as INVALID/BLOCKED per spec
        # Never silently fall back to technical-only path
        if is_mandatory and not _fund_dna.get("available"):
            try:
                append_log(AUDIT_LOG_FILE, f"BACKTEST FUNDAMENTAL FAIL-CLOSED: {symbol} as_of={as_of_date} — no real fundamental data (mandatory) — marking as REJECT, not technical-only")
            except Exception:
                pass
        
    except Exception as e:
        _fund_dna = {"symbol": symbol, "available": False, "reason": f"backtest dna error: {e}", "fail_closed": True}
        _fund_eval = {"action": "REJECT", "final_alignment_decision": "REJECT", "fundamental_status": "BACKTEST_ERROR_FAIL_CLOSED", "reason": str(e), "rejection_reason": f"Backtest fundamental error (fail-closed): {e}", "fail_closed": True}
        _fund_alignment = {"final_alignment_decision": "REJECT", "rejection_reason": f"Error: {e}", "fail_closed": True}

    min_data_points = PARAMS.get("backtest_min_data_points", 100)
    if df.empty or len(df) < min_data_points:
        return {"symbol": symbol, "error": "Insufficient data", "valid": False}

    cost_pct = PARAMS["trading_cost_pct"] / 100
    # [VERIFIED QUANT METHOD] strategy.backtest_on_data now applies the same
    # point-in-time macro gate as live/optimizer: lagged FII/DII (T-1 for day T)
    # plus sector-primary / regime-fallback hierarchy.
    results = strategy.backtest_on_data(df, symbol)

    if not results or "trades_list" not in results:
        return {"symbol": symbol, "error": "Strategy returned no results", "valid": False}

    trades = results["trades_list"]
    if not trades:
        return {"symbol": symbol, "error": "No trades generated", "valid": False}

    # ── Price-based DD calculation (bar by bar) + equity ──
    worst_price_dd = 0.0
    equity = []
    # Owner engine: normalized capital from capital_drawdown_manager validator reference
    capital = float(PARAMS["validator_reference_capital"])  # Strict owner value — no fallback

    # ── PARITY WIRE (Section 12 workflow R1-R4, ADD-ONLY, fail-open) ──
    # Live ke jitne runtime filters historically reconstruct ho sakte hain,
    # utne parity_engine se apply karo: R1 PIT vol-mult, R2 stage-mult,
    # R3 Gate A/B, R4 survival circuit. Error → _parity_report None → exact
    # old behavior (else branch me PURANA code flow waise hi chalta hai).
    _parity_report = None
    _parity_error = None
    try:
        from per_stock_params import get_param as _gp
        from parity_engine import run_parity_equity
        _parity_report = run_parity_equity(
            trades, df, symbol,
            start_capital=float(PARAMS["validator_reference_capital"]),
            max_slots=int(PARAMS.get("max_slots", 8)),
            tp_return_pct=float(_gp(symbol, "tp1_pct", 3.0) or 3.0),
        )
    except Exception as _e:
        _parity_report = None
        _parity_error = f"{type(_e).__name__}: {_e}"
        # P1-001 [r38 verified fix]: a parity engine exception must not be a
        # silent fallback to old-style (pre-parity) numbers being reported
        # as if fully valid. Old-style stats below are still computed (kept
        # for inspection/debugging), but this result is marked invalid via
        # the existing "valid" gate — the same field optimizer.py,
        # deployment_manager.py, walk_forward_validator.py, strategy_validator.py,
        # portfolio_health.py and simulate_engine.py already filter on to
        # exclude unreliable backtests from selection/deployment.
        append_log(AUDIT_LOG_FILE,
                   f"PARITY VALIDATION BLOCKED {symbol}: {_parity_error} — "
                   f"result marked valid=False (no silent legacy fallback)")

    if _parity_report is not None:
        kept = _parity_report.get("kept_trades", trades)
        n_removed = len(trades) - len(kept)
        if n_removed > 0:
            append_log(AUDIT_LOG_FILE,
                       f"PARITY {symbol}: {n_removed}/{len(trades)} trades excluded "
                       f"(Gate A/B / circuit exit-only) — metrics on kept trades only")
        trades = kept  # downstream stats kept-trades pe — live kabhi rejected
                       # trades leta hi nahi, to parity ke liye ye sahi hai
        capital = _parity_report["final_capital"]
        equity = _parity_report["equity"]
        worst_price_dd = _parity_report["worst_price_dd"]
    else:
        # ── FALLBACK: exact old behaviour (unchanged code) ──
        for trade in trades:
            entry_idx = trade.get("entry_idx")
            exit_idx = trade.get("exit_idx")
            entry_price = trade.get("entry_price", 0)

            if entry_idx is None or exit_idx is None or entry_price <= 0:
                continue

            trade_bars = df.iloc[entry_idx:exit_idx + 1]
            price_dd = calculate_price_dd_during_trade(trade_bars, entry_price)
            worst_price_dd = min(worst_price_dd, price_dd)

            # Apply trading cost and verified position sizing multiplier (health + risk parity parity)
            gross_return = trade.get("return_pct", 0) / 100
            net_return = gross_return - cost_pct
            # [VERIFIED -- Constitution Art. 1.5/3.3 point-in-time correctness]
            # health_mult/regime_mult/sector_mult are LIVE, real-time signals
            # (current bot health, current market regime, current sector
            # strength) with no historical per-date archive existing for any
            # of the three (confirmed: sector_strength.py's refresh_sector_data()
            # overwrites SECTOR_DATA_FILE in place, no snapshot history kept;
            # portfolio_health/market_regime are likewise current-state-only).
            # Applying "today's" values to a historical trade from any other
            # date is not point-in-time correct and would make every trade in
            # a single backtest run share the same incidental multiplier
            # regardless of its real historical date. Since no verified
            # historical value exists for any of the three, the correct
            # fail-closed treatment is neutral (1.0) here -- a backtest must
            # measure the strategy's own raw historical performance, not
            # conflate it with today's unrelated live bot-health/regime/sector
            # state. Live trading (capital_manager.py's real-time sizing) is
            # unaffected -- there, "now" is the correct and only meaningful
            # reference point for these same three signals.
            health_mult, regime_mult, sector_mult = 1.0, 1.0, 1.0
            combined_mult = health_mult * regime_mult * sector_mult
            smax = max(1, int(PARAMS.get("max_slots", 8)))
            capital *= (1 + (net_return * combined_mult) / smax)  # [PHD-FIX F1] per-slot share: same as parity_engine
            equity.append(capital)

    # ── Portfolio DD from equity curve ──
    equity_series = pd.Series(equity)
    rolling_max = equity_series.cummax()
    portfolio_dd_series = (equity_series - rolling_max) / rolling_max * 100
    portfolio_max_dd = float(portfolio_dd_series.min()) if len(portfolio_dd_series) > 0 else 0.0

    total_trades = len([t for t in trades if t.get("return_pct") is not None])
    winning = len([t for t in trades if t.get("return_pct", 0) > 0])
    win_rate = (winning / total_trades * 100) if total_trades > 0 else 0

    # FIX02_EXTRA_STATS_START
    # TradingView-style extra stats: PF, RF, Sharpe, Sortino, idle days, max daily loss
    net_returns_pct = []
    daily_pnl_amt = {}
    durations = []
    idle_gaps = []
    prev_exit_idx = None
    last_exit_idx = None
    sim_cap = float(PARAMS["validator_reference_capital"])  # Strict owner value — no fallback

    for _t in sorted(trades, key=lambda x: int(x.get("entry_idx", 0) or 0)):
        try:
            _entry_idx = int(_t.get("entry_idx", 0))
            _exit_idx = int(_t.get("exit_idx", _entry_idx))
            _gross_pct = float(_t.get("return_pct", 0) or 0)

            if _t.get("net_return_pct") is not None:
                _net_pct = float(_t.get("net_return_pct") or 0)
            else:
                _net_pct = _gross_pct - PARAMS["trading_cost_pct"]

            net_returns_pct.append(_net_pct)
            durations.append(max(0, _exit_idx - _entry_idx))

            if prev_exit_idx is not None:
                idle_gaps.append(max(0, _entry_idx - prev_exit_idx - 1))
            prev_exit_idx = _exit_idx
            last_exit_idx = _exit_idx

            _pnl_amt = sim_cap * (_net_pct / 100.0)
            sim_cap += _pnl_amt

            try:
                _dt = df.index[_exit_idx]
                _dkey = _dt.date().isoformat() if hasattr(_dt, "date") else str(_dt)[:10]
            except (IndexError, TypeError, AttributeError):
                _dkey = "unknown"

            daily_pnl_amt[_dkey] = daily_pnl_amt.get(_dkey, 0.0) + _pnl_amt

        except (TypeError, ValueError, KeyError):
            continue

    wins_pct = [x for x in net_returns_pct if x > 0]
    losses_pct = [x for x in net_returns_pct if x <= 0]

    # [VERIFIED QUANT METHOD] Real Monte Carlo bootstrap drawdown -- see
    # calculate_monte_carlo_dd_pct() docstring for method and sources.
    mc_result = calculate_monte_carlo_dd_pct(
        net_returns_pct=net_returns_pct,
        capital=float(PARAMS["validator_reference_capital"]),
    )

    ref_cap = float(PARAMS["validator_reference_capital"])  # Strict owner value — no fallback
    # AI-DOS LOGIC-001 fix: guard against an owner misconfiguration of 0.
    total_return_pct = safe_div(capital - ref_cap, ref_cap, default=0.0) * 100
    avg_win_pct = float(np.mean(wins_pct)) if wins_pct else 0.0
    avg_loss_pct = float(np.mean(losses_pct)) if losses_pct else 0.0
    win_loss_ratio = abs(avg_win_pct / avg_loss_pct) if avg_loss_pct != 0 else 0.0

    gross_profit = float(sum(wins_pct))
    gross_loss = float(sum(losses_pct))
    profit_factor = gross_profit / abs(gross_loss) if gross_loss < 0 else 0.0

    recovery_factor = total_return_pct / abs(portfolio_max_dd) if portfolio_max_dd != 0 else 0.0

    returns_s = pd.Series(net_returns_pct, dtype="float64")
    if len(returns_s) > 1:
        sharpe = float(returns_s.mean() / (returns_s.std() + 1e-10))
        downside = returns_s[returns_s < 0]
        sortino = float(returns_s.mean() / (downside.std() + 1e-10)) if len(downside) > 1 else 0.0
    else:
        sharpe = 0.0
        sortino = 0.0

    max_consecutive_losses = 0
    _cur_losses = 0
    for _r in net_returns_pct:
        if _r <= 0:
            _cur_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, _cur_losses)
        else:
            _cur_losses = 0

    avg_duration_days = round(float(np.mean(durations)), 1) if durations else 0
    avg_idle_days = round(float(np.mean(idle_gaps)), 1) if idle_gaps else 0
    max_idle_days = int(max(idle_gaps)) if idle_gaps else 0
    current_idle_days = max(0, len(df) - last_exit_idx - 1) if last_exit_idx is not None else 0

    max_single_day_loss_amt = min([0.0] + list(daily_pnl_amt.values()))
    ref_cap = float(PARAMS["validator_reference_capital"])  # Strict owner value — no fallback
    max_single_day_loss_pct = max_single_day_loss_amt / ref_cap * 100
    portfolio_max_loss_amt = ref_cap * portfolio_max_dd / 100

    ref_cap = float(PARAMS["validator_reference_capital"])  # Strict owner value — no fallback
    try:
        _days = max(1, (df.index[-1].date() - df.index[0].date()).days)
        cagr_pct = ((capital / ref_cap) ** (365 / _days) - 1) * 100
    except (TypeError, ValueError, ZeroDivisionError, IndexError):
        cagr_pct = 0.0
    # FIX02_EXTRA_STATS_END

    metrics = {
        "symbol": symbol,
        # P1-001 [r38 verified fix]: invalid when the parity engine errored —
        # see PARITY VALIDATION BLOCKED audit entry above for the reason.
        "valid": _parity_error is None,
        "parity_error": _parity_error,
        "backtest_date": now_ist().isoformat(),
        "strategy_name": strategy.name,
        "strategy_version": strategy.version,
        # PARITY transparency (Section 12): kya apply hua, kitne trades exclude hue
        "parity_applied": _parity_report is not None,
        "parity_excluded_trades": (_parity_report or {}).get("n_rejected", 0),
        "parity_circuit_hit": (_parity_report or {}).get("circuit_hit", False),
        "parity_circuit_dd_pct": (_parity_report or {}).get("circuit_dd_pct"),
        "parity_stage_mult": (_parity_report or {}).get("stage_mult"),
        "total_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
        "winning_trades": winning,
        "losing_trades": total_trades - winning,
        "total_return_pct": round(total_return_pct, 2),
        "cagr_pct": round(cagr_pct, 2),
        "avg_win_pct": round(avg_win_pct, 2),
        "avg_loss_pct": round(avg_loss_pct, 2),
        "avg_win_amt": round(ref_cap * avg_win_pct / 100, 2),
        "avg_loss_amt": round(ref_cap * avg_loss_pct / 100, 2),
        "win_loss_ratio": round(win_loss_ratio, 2),
        "max_consecutive_losses": max_consecutive_losses,
        "profit_factor": round(profit_factor, 2),
        "price_max_drawdown_pct": round(worst_price_dd, 2),
        "portfolio_max_drawdown_pct": round(portfolio_max_dd, 2),
        "monte_carlo_dd_pct": mc_result.get("monte_carlo_dd_pct"),
        "monte_carlo_median_dd_pct": mc_result.get("monte_carlo_median_dd_pct"),
        "monte_carlo_worst_dd_pct": mc_result.get("monte_carlo_worst_dd_pct"),
        "monte_carlo_dd_error": mc_result.get("error"),
        "_net_returns_pct": net_returns_pct,
        "avg_return_pct": round(results.get("avg_return_pct", 0), 2),
        "recovery_factor": round(recovery_factor, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "max_single_day_loss_pct": round(max_single_day_loss_pct, 2),
        "max_single_day_loss_amt": round(max_single_day_loss_amt, 2),
        "portfolio_max_loss_amt": round(portfolio_max_loss_amt, 2),
        "avg_duration_days": avg_duration_days,
        "avg_idle_days": avg_idle_days,
        "max_idle_days": max_idle_days,
        "current_idle_days": current_idle_days,
        # PILLAR 3 CORRECTED: Full Fundamental+Technical alignment audit — REAL ONLY, PIT-SAFE
        "fundamental_dna": _fund_dna,
        "fundamental_evaluation": _fund_eval,
        "fundamental_alignment": _fund_alignment,
        "fundamental_sync_status": _fund_eval.get("action", "UNKNOWN") if isinstance(_fund_eval, dict) else "UNKNOWN",
        "fundamental_status": _fund_eval.get("fundamental_status", "UNKNOWN") if isinstance(_fund_eval, dict) else "UNKNOWN",
        "fundamental_score": _fund_eval.get("score", 0) if isinstance(_fund_eval, dict) else 0,
        "fundamental_features": _fund_alignment.get("fundamental_features", {}) if isinstance(_fund_alignment, dict) else {},
        "technical_status": _fund_alignment.get("technical_status", "UNKNOWN") if isinstance(_fund_alignment, dict) else "UNKNOWN",
        "technical_tools_used": _fund_alignment.get("technical_tools_used", []) if isinstance(_fund_alignment, dict) else [],
        "technical_alignment": _fund_alignment.get("technical_alignment", "UNKNOWN") if isinstance(_fund_alignment, dict) else "UNKNOWN",
        "final_alignment_decision": _fund_eval.get("final_alignment_decision", _fund_alignment.get("final_alignment_decision", "UNKNOWN")) if isinstance(_fund_eval, dict) else "UNKNOWN",
        "rejection_reason": _fund_eval.get("rejection_reason", _fund_eval.get("reason", "")) if isinstance(_fund_eval, dict) else "",
        "provenance_chain": _fund_dna.get("provenance_chain", {}) if isinstance(_fund_dna, dict) else {},
        "as_of": as_of_date,
        "is_mandatory": _fund_alignment.get("is_mandatory", True) if isinstance(_fund_alignment, dict) else True,
        "fail_closed": _fund_eval.get("fail_closed", False) if isinstance(_fund_eval, dict) else False,
    }

    # PILLAR 3 CORRECTED: Log full alignment with provenance
    try:
        append_log(AUDIT_LOG_FILE,
                   f"BACKTEST DONE: {symbol} trades={total_trades} win={win_rate:.1f}% "
                   f"price_dd={worst_price_dd:.2f}% portfolio_dd={portfolio_max_dd:.2f}% "
                   f"FundSync={_fund_eval.get('action','UNKNOWN')} Status={_fund_eval.get('fundamental_status','UNKNOWN')} "
                   f"FinalDecision={_fund_eval.get('final_alignment_decision','UNKNOWN')} Score={_fund_eval.get('score',0)} "
                   f"as_of={as_of_date} Mandatory={_fund_alignment.get('is_mandatory', True)} FailClosed={_fund_eval.get('fail_closed', False)} "
                   f"Provenance={_fund_dna.get('source','none')} ann={_fund_dna.get('announcement_date','none')} "
                   f"DNA={json.dumps({k: _fund_dna.get(k) for k in ('cfo','pat','debt_to_equity','promoter_pledging_pct','roce','piotroski_f_score') if k in _fund_dna}, default=str)}")
    except Exception:
        append_log(AUDIT_LOG_FILE,
                   f"BACKTEST DONE: {symbol} trades={total_trades} win={win_rate:.1f}% "
                   f"price_dd={worst_price_dd:.2f}% portfolio_dd={portfolio_max_dd:.2f}%")
    return metrics


# ─────────────────────────────────────────────
# FULL UNIVERSE BACKTEST
# ─────────────────────────────────────────────

def run_full_backtest(symbols: list = None) -> dict:
    """
    Backtest all halal universe stocks.
    Saves results to BACKTEST_RESULTS_FILE.
    """
    if symbols is None:
        symbols = load_halal_symbols()

    # [QUANT-001 FIX — honesty part] No historical eligibility archive ever
    # existed before universe_snapshot_manager.py started capturing one — so
    # every symbol below is filtered by TODAY's universe, applied uniformly
    # across the whole historical window. This does NOT retroactively fix
    # survivorship/look-ahead bias in past years (that data was never
    # captured, and fabricating it would violate the no-fabrication rule) —
    # it makes the limitation explicit in the report instead of silent.
    try:
        from universe_snapshot_manager import earliest_snapshot_date, list_snapshot_dates
        _pit_status = {
            "point_in_time_accurate": False,
            "reason": (
                "Universe eligibility below is today's snapshot applied across "
                "the ENTIRE backtest window (survivorship + look-ahead bias — "
                "not point-in-time correct for historical dates). No dated "
                "eligibility history existed before universe_snapshot_manager.py "
                "started capturing it (added as part of the QUANT-001 fix); "
                "retroactive correction of past years is not possible without "
                "data that was never recorded."
            ),
            "snapshot_capture_started": earliest_snapshot_date(),
            "snapshots_available": len(list_snapshot_dates()),
        }
    except Exception:
        _pit_status = {"point_in_time_accurate": False, "reason": "universe_snapshot_manager unavailable"}

    all_results = {}
    failed = []

    for symbol in symbols:
        result = backtest_single(symbol)
        if result.get("valid"):
            all_results[symbol] = result
        else:
            failed.append(symbol)

    # ── Portfolio-level DD from combined equity curve ──

    summary = _calculate_portfolio_summary(all_results, symbols)
    portfolio_dd = summary.get("portfolio_max_dd_pct", _calculate_portfolio_dd(all_results))

    # [VERIFIED QUANT METHOD] Portfolio-level Monte Carlo: pool every
    # stock's actual historical trade returns together (Monte Carlo
    # shuffles the combined set regardless of original per-stock
    # ordering, so pooling first is valid) and run the same verified
    # bootstrap method at portfolio scale.
    pooled_returns = []
    for r in all_results.values():
        pooled_returns.extend(r.get("_net_returns_pct") or [])
    portfolio_capital = float(PARAMS["validator_reference_capital"]) * max(1, len(all_results))
    portfolio_mc_result = calculate_monte_carlo_dd_pct(
        net_returns_pct=pooled_returns,
        capital=portfolio_capital,
    )

    for r in all_results.values():
        r.pop("_net_returns_pct", None)

    # [QUANT-002 FIX] portfolio_dd above is the average of ISOLATED per-stock
    # drawdowns — it never checks whether those trades' entries could have
    # actually co-existed under max_slots / max_stocks_per_sector /
    # correlation_threshold / reentry_cooldown_days. Run the concentration-
    # gated replay (portfolio_backtest_engine.py) as an ADDITIONAL field —
    # fail-open (never breaks the existing report) so a bug in the new engine
    # can't take down the whole backtest.
    concentration_gated = None
    try:
        from portfolio_backtest_engine import run_portfolio_backtest
        concentration_gated = run_portfolio_backtest(symbols)
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"QUANT-002 concentration-gated backtest failed: {e}")

    output = {
        "run_date": now_ist().isoformat(),
        "strategy_name": get_active_strategy().name,
        "strategy_version": get_active_strategy().version,
        "total_symbols": len(symbols),
        "successful": len(all_results),
        "failed": failed,
        "portfolio_max_dd_pct": portfolio_dd,
        "portfolio_max_dd_pct_concentration_gated": (
            concentration_gated.get("portfolio_max_dd_pct_concentration_gated")
            if concentration_gated else None
        ),
        "concentration_gated_detail": concentration_gated,
        "universe_point_in_time_status": _pit_status,
        "portfolio_monte_carlo_dd_pct": portfolio_mc_result.get("monte_carlo_dd_pct"),
        "portfolio_monte_carlo_median_dd_pct": portfolio_mc_result.get("monte_carlo_median_dd_pct"),
        "portfolio_monte_carlo_worst_dd_pct": portfolio_mc_result.get("monte_carlo_worst_dd_pct"),
        "portfolio_monte_carlo_dd_error": portfolio_mc_result.get("error"),
        "summary": summary,
        "stocks": all_results,
    }

    save_json(BACKTEST_RESULTS_FILE, output)
    append_log(AUDIT_LOG_FILE,
               f"FULL BACKTEST COMPLETE: {len(all_results)}/{len(symbols)} success "
               f"portfolio_dd={portfolio_dd:.2f}%")
    return output


def _calculate_portfolio_dd(all_results: dict) -> float:
    """Equal-weight portfolio DD from all stock equity curves."""
    # Simplified: average of all individual portfolio DDs
    dds = [r["portfolio_max_drawdown_pct"] for r in all_results.values() if r.get("valid")]
    if not dds:
        return 0.0
    return round(float(np.mean(dds)), 2)


def load_halal_symbols() -> list:
    """
    [AUDIT FIX — major backtest/live parity gap] Previously this just
    returned every symbol in the universe CSV, completely ignoring the
    per-row eligibility flags (core_business_halal, non_muslim_board,
    price>100, illiquid) that stock_selector._row_is_halal_eligible()
    enforces for LIVE trading. That meant backtest results could include
    haram stocks, Muslim-board stocks, sub-₹100 stocks, or illiquid stocks
    that would NEVER actually be traded live — backtest and live were
    silently running on two different universes.

    Now calls the exact same row-level eligibility function stock_selector
    uses live, so any future change to universe eligibility (including the
    turnover-liquidity screen added alongside this fix) automatically
    applies identically to both backtest and live — single source of truth,
    not two implementations that can drift apart.
    """
    try:
        from stock_selector import load_halal_universe, _row_is_halal_eligible
        df = load_halal_universe()
        if df is None or df.empty:
            return []
        eligible = df[df.apply(_row_is_halal_eligible, axis=1)]
        return eligible["symbol"].tolist()
    except (ImportError, RuntimeError, ValueError, KeyError) as e:
        append_log(AUDIT_LOG_FILE, f"load_halal_symbols: eligibility-filtered load failed ({type(e).__name__}: {e}), falling back to raw CSV read (may include ineligible symbols)")
        try:
            import pandas as pd
            from config import CUSTOM_UNIVERSE_FILE
            df = pd.read_csv(CUSTOM_UNIVERSE_FILE)
            return df["symbol"].tolist()
        except (FileNotFoundError, OSError, KeyError, ValueError):
            return []


# ─────────────────────────────────────────────
# BACKTEST STALENESS CHECK
# ─────────────────────────────────────────────

def check_backtest_staleness() -> dict:
    """
    Returns: {status: OK/WARN/BLOCK, days_old: int}
    WARN > 90 days, BLOCK > 180 days
    """
    data = load_json(BACKTEST_RESULTS_FILE, {})
    if not data or "run_date" not in data:
        return {"status": "BLOCK", "days_old": 999, "message": "No backtest found — run /backtest first"}

    from datetime import datetime
    run_date = datetime.fromisoformat(data["run_date"])
    days_old = (now_ist().replace(tzinfo=None) - run_date.replace(tzinfo=None)).days

    warn_days = PARAMS["backtest_warn_days"]
    block_days = PARAMS["backtest_block_days"]

    if days_old > block_days:
        return {"status": "BLOCK", "days_old": days_old,
                "message": f"⛔ Backtest {days_old} days old. New backtest REQUIRED."}
    elif days_old > warn_days:
        return {"status": "WARN", "days_old": days_old,
                "message": f"⚠️ Backtest {days_old} days old. Consider refreshing."}
    else:
        return {"status": "OK", "days_old": days_old, "message": "✅ Backtest fresh"}



# FIX02: Portfolio summary + admin message formatters
def _calculate_portfolio_summary(all_results: dict, symbols: list = None) -> dict:
    valid = [r for r in all_results.values() if r.get("valid")]
    if not valid:
        return {"total_trades": 0, "win_rate_pct": 0, "portfolio_max_dd_pct": 0}

    total_trades = sum(int(r.get("total_trades", 0)) for r in valid)
    wins = sum(int(r.get("winning_trades", 0)) for r in valid)
    losses = sum(int(r.get("losing_trades", 0)) for r in valid)
    win_rate = wins / total_trades * 100 if total_trades else 0

    profit_sum = sum(max(0, float(r.get("avg_win_pct", 0))) * int(r.get("winning_trades", 0)) for r in valid)
    loss_sum = sum(min(0, float(r.get("avg_loss_pct", 0))) * int(r.get("losing_trades", 0)) for r in valid)

    avg_win_pct = profit_sum / wins if wins else 0
    avg_loss_pct = loss_sum / losses if losses else 0
    profit_factor = profit_sum / abs(loss_sum) if loss_sum < 0 else (99.0 if profit_sum > 0 else 0)
    win_loss_ratio = abs(avg_win_pct / avg_loss_pct) if avg_loss_pct != 0 else 0

    total_return_pct = float(np.mean([float(r.get("total_return_pct", 0)) for r in valid]))
    cagr_pct = float(np.mean([float(r.get("cagr_pct", 0)) for r in valid]))
    portfolio_dd = float(np.mean([float(r.get("portfolio_max_drawdown_pct", 0)) for r in valid]))
    recovery_factor = total_return_pct / abs(portfolio_dd) if portfolio_dd != 0 else 0

    best = max(valid, key=lambda r: float(r.get("total_return_pct", 0)))
    worst = min(valid, key=lambda r: float(r.get("total_return_pct", 0)))

    return {
        "total_trades": total_trades,
        "winning_trades": wins,
        "losing_trades": losses,
        "win_rate_pct": round(win_rate, 2),
        "total_return_pct": round(total_return_pct, 2),
        "cagr_pct": round(cagr_pct, 2),
        "profit_factor": round(profit_factor, 2),
        "recovery_factor": round(recovery_factor, 2),
        "sharpe": round(float(np.mean([float(r.get("sharpe", 0)) for r in valid])), 2),
        "sortino": round(float(np.mean([float(r.get("sortino", 0)) for r in valid])), 2),
        "avg_win_pct": round(avg_win_pct, 2),
        "avg_loss_pct": round(avg_loss_pct, 2),
        "win_loss_ratio": round(win_loss_ratio, 2),
        "max_consecutive_losses": max(int(r.get("max_consecutive_losses", 0)) for r in valid),
        "avg_duration_days": round(float(np.mean([float(r.get("avg_duration_days", 0)) for r in valid])), 1),
        "avg_idle_days": round(float(np.mean([float(r.get("avg_idle_days", 0)) for r in valid])), 1),
        "max_idle_days": max(int(r.get("max_idle_days", 0)) for r in valid),
        "current_idle_days": max(int(r.get("current_idle_days", 0)) for r in valid),
        "portfolio_max_dd_pct": round(portfolio_dd, 2),
        "max_single_day_loss_pct": round(float(np.mean([float(r.get("max_single_day_loss_pct", 0)) for r in valid])), 2),
        "best_stock": best.get("symbol"),
        "best_stock_return_pct": best.get("total_return_pct"),
        "worst_stock": worst.get("symbol"),
        "worst_stock_return_pct": worst.get("total_return_pct"),
        "tested_symbols": len(symbols or []),
        "successful_symbols": len(valid),
    }


def _fmt_pct(value) -> str:
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        v = 0.0
    return f"{'+' if v >= 0 else ''}{v:.2f}%"


def _fmt_inr(value) -> str:
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        v = 0.0
    return f"{'-' if v < 0 else ''}Rs.{abs(v):,.0f}"


def format_single_backtest_message(result: dict) -> str:
    if not result or not result.get("valid"):
        return f"Backtest failed: {result.get('symbol', '')} - {result.get('error', 'Unknown error')}"

    return (
        f"BACKTEST RESULTS - {result['symbol']}\n"
        f"------------------------------\n"
        f"Return: {_fmt_pct(result.get('total_return_pct'))} | CAGR: {_fmt_pct(result.get('cagr_pct'))}\n"
        f"Max DD: {_fmt_pct(result.get('portfolio_max_drawdown_pct'))} | Sharpe: {result.get('sharpe', 0)} | Sortino: {result.get('sortino', 0)}\n"
        f"Profit Factor: {result.get('profit_factor', 0)} | RF: {result.get('recovery_factor', 0)}\n"
        f"------------------------------\n"
        f"Trades: {result.get('total_trades', 0)} | Win Rate: {result.get('win_rate_pct', 0)}%\n"
        f"Avg Win: {_fmt_pct(result.get('avg_win_pct'))} = {_fmt_inr(result.get('avg_win_amt'))}\n"
        f"Avg Loss: {_fmt_pct(result.get('avg_loss_pct'))} = {_fmt_inr(result.get('avg_loss_amt'))}\n"
        f"W/L Ratio: {result.get('win_loss_ratio', 0)} | Max Consec Loss: {result.get('max_consecutive_losses', 0)}\n"
        f"Idle Days: Avg {result.get('avg_idle_days', 0)} | Max {result.get('max_idle_days', 0)} | Current {result.get('current_idle_days', 0)}\n"
        f"------------------------------\n"
        f"Max Single Day Loss: {_fmt_pct(result.get('max_single_day_loss_pct'))} = {_fmt_inr(result.get('max_single_day_loss_amt'))}\n"
        f"Portfolio Max Loss: {_fmt_pct(result.get('portfolio_max_drawdown_pct'))} = {_fmt_inr(result.get('portfolio_max_loss_amt'))}\n"
        f"Backtest: {str(result.get('backtest_date', ''))[:16]} IST | Dhan data"
    )


def format_full_backtest_message(output: dict) -> str:
    s = output.get("summary", {}) if output else {}
    return (
        f"FULL BACKTEST COMPLETE\n"
        f"------------------------------\n"
        f"Return: {_fmt_pct(s.get('total_return_pct'))} | CAGR: {_fmt_pct(s.get('cagr_pct'))}\n"
        f"Portfolio DD: {_fmt_pct(s.get('portfolio_max_dd_pct'))} | Sharpe: {s.get('sharpe', 0)} | Sortino: {s.get('sortino', 0)}\n"
        f"Profit Factor: {s.get('profit_factor', 0)} | RF: {s.get('recovery_factor', 0)}\n"
        f"------------------------------\n"
        f"Trades: {s.get('total_trades', 0)} | Win Rate: {s.get('win_rate_pct', 0)}%\n"
        f"Avg Win: {_fmt_pct(s.get('avg_win_pct'))} | Avg Loss: {_fmt_pct(s.get('avg_loss_pct'))}\n"
        f"W/L Ratio: {s.get('win_loss_ratio', 0)} | Max Consec Loss: {s.get('max_consecutive_losses', 0)}\n"
        f"Idle Days: Avg {s.get('avg_idle_days', 0)} | Max {s.get('max_idle_days', 0)} | Current {s.get('current_idle_days', 0)}\n"
        f"------------------------------\n"
        f"Max Single Day Loss: {_fmt_pct(s.get('max_single_day_loss_pct'))}\n"
        f"Universe: {output.get('successful', 0)}/{output.get('total_symbols', 0)} tested | Failed: {len(output.get('failed', []))}\n"
        f"Best: {s.get('best_stock', 'N/A')} {_fmt_pct(s.get('best_stock_return_pct'))}\n"
        f"Worst: {s.get('worst_stock', 'N/A')} {_fmt_pct(s.get('worst_stock_return_pct'))}\n"
        f"Backtest: {str(output.get('run_date', ''))[:16]} IST | Dhan data"
    )
