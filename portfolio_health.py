"""
portfolio_health.py — Robust relative portfolio health + smooth capital multiplier

Health 100% means:
    Strategy is performing near expected robust benchmark.
It does NOT mean 100% win rate.

Capital multiplier:
    health_score / 100 with 10% floor.
Emergency brakes/circuit breaker can still override separately.
"""

from utils import load_json, append_log, logger
from config import PARAMS, AUDIT_LOG_FILE, BACKTEST_RESULTS_FILE, TRADES_FILE
from stock_mode_manager import get_all_modes


MIN_HEALTH_CAPITAL_FLOOR = float(PARAMS.get("min_health_capital_floor", 0.10))


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _component_score(actual: float, expected: float, higher_is_better: bool = True) -> float:
    """
    Relative score.
    Example: expected WR 55%, actual WR 55% => 100 health component.
    """
    actual = _safe_float(actual)
    expected = _safe_float(expected)

    if expected <= 0:
        return 100.0

    if higher_is_better:
        return max(0.0, min(100.0, actual / expected * 100.0))

    # For DD/idle: lower is better. actual <= expected => 100
    if actual <= expected:
        return 100.0

    if actual == 0: return 0.0
    return max(0.0, min(100.0, expected / actual * 100.0))


def _get_backtest_summary() -> dict:
    bt = load_json(BACKTEST_RESULTS_FILE, {})
    summary = bt.get("summary", {})
    if isinstance(summary, dict) and summary:
        return summary

    # Fallback: aggregate stocks if summary missing
    stocks = [s for s in bt.get("stocks", {}).values() if s.get("valid")]
    if not stocks:
        return {}

    total_trades = sum(int(s.get("total_trades", 0)) for s in stocks)
    wins = sum(int(s.get("winning_trades", 0)) for s in stocks)
    return {
        "win_rate_pct": round(wins / total_trades * 100, 2) if total_trades else 0,
        "profit_factor": sum(_safe_float(s.get("profit_factor")) for s in stocks) / len(stocks),
        "portfolio_max_dd_pct": sum(abs(_safe_float(s.get("portfolio_max_drawdown_pct"))) for s in stocks) / len(stocks),
        "max_idle_days": max(int(s.get("max_idle_days", 0) or 0) for s in stocks),
    }


def _get_live_recent_metrics() -> dict:
    """
    Live/recent trades from trade logger.
    If not enough live data, return {} and health uses backtest/mode fallback.
    """
    data = load_json(TRADES_FILE, {"trades": []})
    trades = [t for t in data.get("trades", []) if t.get("status") == "CLOSED"]

    n = int(PARAMS.get("health_recent_trades", 20))
    recent = trades[-n:]

    if len(recent) < int(PARAMS.get("health_min_live_trades", 5)):
        return {}

    total = len(recent)
    wins = [t for t in recent if _safe_float(t.get("pnl", 0)) > 0]
    losses = [t for t in recent if _safe_float(t.get("pnl", 0)) <= 0]

    gross_profit = sum(_safe_float(t.get("pnl", 0)) for t in wins)
    gross_loss = sum(_safe_float(t.get("pnl", 0)) for t in losses)

    pf = gross_profit / abs(gross_loss) if gross_loss < 0 else 0.0

    return {
        "win_rate_pct": len(wins) / total * 100 if total else 0,
        "profit_factor": pf,
        "recent_trades": total,
    }


def _stock_mode_health_score() -> float:
    """
    Existing stock mode based health. Acts as fallback/penalty.
    """
    modes = get_all_modes()
    if not modes:
        return 100.0

    total = len(modes)
    score = 0.0

    for state in modes.values():
        mode = state.get("mode", "PROFIT")
        if mode == "PROFIT":
            score += float(PARAMS.get("health_mode_profit", 100))
        elif mode == "RECOVERY":
            score += float(PARAMS.get("health_mode_recovery", 60))
        elif mode == "SOFT_BLOCKED":
            score += float(PARAMS.get("health_mode_soft_blocked", 40))
        elif mode == "HARD_BLOCKED":
            score += float(PARAMS.get("health_mode_hard_blocked", 0))
        else:
            score += float(PARAMS.get("health_mode_default", 70))

    return round(score / total, 2)


def _execution_monitoring_score() -> float:
    """Decision 20 — execution monitoring input for bot health."""
    try:
        from bot_state_manager import get_state
        state = get_state()
    except (ImportError, RuntimeError, AttributeError):
        state = "PAPER"

    state_score_map = {
        "PAPER": float(PARAMS.get("health_state_paper", 95.0)),
        "LIVE_STAGED": float(PARAMS.get("health_state_live_staged", 100.0)),
        "LIVE_FULL": float(PARAMS.get("health_state_live_full", 100.0)),
        "EXIT_ONLY": float(PARAMS.get("health_state_exit_only", 55.0)),
        "TOKEN_INVALID_PAUSE": float(PARAMS.get("health_state_token_pause", 20.0)),
        "RAPID_LOSS_PAUSE": float(PARAMS.get("health_state_rapid_loss", 35.0)),
        "RECONCILIATION_HOLD": float(PARAMS.get("health_state_recon", 10.0)),
        "KILLSWITCH_STOP": float(PARAMS.get("health_state_killswitch", 0.0)),
        "COLD_START": float(PARAMS.get("health_state_cold_start", 40.0)),
    }
    state_score = state_score_map.get(state, float(PARAMS.get("health_state_default", 60.0)))

    workflow_score = float(PARAMS.get("health_workflow_base", 100.0))
    try:
        from workflow_manager import get_workflow_status_text
        wf_text = get_workflow_status_text()
        if "deployment_approval: PENDING" in wf_text:
            workflow_score = float(PARAMS.get("health_workflow_deployment_pending", 70.0))
        if "simulation: PENDING" in wf_text and state in ("LIVE_STAGED", "LIVE_FULL", "PAPER"):
            workflow_score = min(workflow_score, float(PARAMS.get("health_workflow_simulation_pending", 60.0)))
    except (ImportError, RuntimeError, AttributeError):
        workflow_score = float(PARAMS.get("health_workflow_default", 80.0))

    state_weight = float(PARAMS.get("health_execution_state_weight", 0.7))
    workflow_weight = float(PARAMS.get("health_execution_workflow_weight", 0.3))
    return round((state_score * state_weight) + (workflow_score * workflow_weight), 2)



def calculate_ulcer_index(returns_pct: list) -> float:
    """
    [VERIFIED QUANT METHOD] Ulcer Index — Peter G. Martin, 1987
    ("The Investors Guide to Fidelity Funds").
    Drawdown-pain measure: depth AUR duration dono count hote hain
    (max-DD sirf worst point dekhata hai; UI poori pain history ka RMS hai).
        UI = sqrt( mean( dd_i^2 ) ),  dd_i = (equity_i - peak_i)/peak_i * 100
    Input: periodic net returns (%). Fail → None (caller fallback).
    """
    try:
        import math
        if not returns_pct:
            return None
        equity, peak = 1.0, 1.0
        dds = []
        for r in returns_pct:
            equity *= (1 + float(r) / 100.0)
            peak = max(peak, equity)
            dds.append((equity - peak) / peak * 100.0)
        if not dds:
            return None
        return round(math.sqrt(sum(d * d for d in dds) / len(dds)), 2)
    except Exception as e:
        logger.warning(f"calculate_ulcer_index failed: {e}")
        return None


def _ulcer_pain_score() -> float:
    """
    Ulcer Index ko 0-100 health component me map karta hai.
    UI measured = ✅ verified (Martin 1987); display mapping 100 - min(100, UI*scale)
    = documented display normalization ONLY (risk threshold nahi; owner
    PARAMS.health_ulcer_scale se change kar sakta hai, default 8.0).
    Data missing → None (caller purana binary path use kare — fail-open).
    """
    try:
        from config import BACKTEST_RESULTS_FILE
        from utils import load_json
        data = load_json(BACKTEST_RESULTS_FILE, {}) or {}
        nets = []
        for stock in (data.get("stocks", {}) or {}).values():
            for tr in (stock.get("trades_list") or []):
                try:
                    nets.append(float(tr.get("net_return_pct", tr.get("return_pct", 0)) or 0))
                except (TypeError, ValueError):
                    continue
        ui = calculate_ulcer_index(nets)
        if ui is None:
            return None
        scale = float(PARAMS.get("health_ulcer_scale", 8.0))
        return round(max(0.0, 100.0 - min(100.0, ui * scale)), 2)
    except Exception as e:
        logger.warning(f"_ulcer_pain_score failed: {e}")
        return None


def _benchmark_quality_score(bt: dict) -> float:
    """
    Benchmark quality cap.
    If latest backtest/strategy itself is weak, health cannot be 100
    just because live data is not available.

    Example:
    WR 20%, PF 0.44, negative return => health capped low.
    """
    expected_wr = _safe_float(bt.get("win_rate_pct"), 0)
    expected_pf = _safe_float(bt.get("profit_factor"), 0)
    expected_return = _safe_float(bt.get("total_return_pct"), 0)
    expected_rf = _safe_float(bt.get("recovery_factor"), 0)

    try:
        from economics_brain import min_win_rate_floor
        min_wr = _safe_float(min_win_rate_floor(), 45)
    except Exception:
        min_wr = _safe_float(PARAMS.get("min_live_win_rate", 45), 45)
    min_pf = _safe_float(PARAMS.get("min_profit_factor", 1.0), 1.0)
    min_rf = _safe_float(PARAMS.get("min_recovery_factor", 1.0), 1.0)

    wr_score = _component_score(expected_wr, min_wr, higher_is_better=True)
    pf_score = _component_score(expected_pf, min_pf, higher_is_better=True)

    # [Method upgrade 2026-07-30] return component: binary (0/100) → Ulcer Index
    # pain score (Martin 1987) — verified method. Sign gate waisa hi: non-positive
    # return = 0. UI data nahi → exact purana binary (fail-open).
    if expected_return <= 0:
        return_score = 0.0
    else:
        ulcer_score = _ulcer_pain_score()
        return_score = ulcer_score if ulcer_score is not None else 100.0

    if expected_rf > 0:
        rf_score = _component_score(expected_rf, min_rf, higher_is_better=True)
    else:
        rf_score = 0.0

    wr_w = float(PARAMS.get("health_benchmark_wr_weight", 0.25))
    pf_w = float(PARAMS.get("health_benchmark_pf_weight", 0.35))
    ret_w = float(PARAMS.get("health_benchmark_return_weight", 0.25))
    rf_w = float(PARAMS.get("health_benchmark_rf_weight", 0.15))
    quality = (
        wr_score * wr_w +
        pf_score * pf_w +
        return_score * ret_w +
        rf_score * rf_w
    )

    return round(max(0.0, min(100.0, quality)), 2)


def calculate_health_score() -> float:
    """Decision 20 — runtime bot health score.

    Blends benchmark quality, live performance analytics, drawdown/recovery posture,
    stock-mode state and execution monitoring with continuous sample-aware weights.
    """
    bt = _get_backtest_summary()
    live = _get_live_recent_metrics()
    mode_score = _stock_mode_health_score()
    execution_score = _execution_monitoring_score()

    if not bt:
        mode_w = float(PARAMS.get("health_fallback_mode_weight", 0.6))
        exec_w = float(PARAMS.get("health_fallback_execution_weight", 0.4))
        return round((mode_score * mode_w) + (execution_score * exec_w), 2)

    expected_wr = _safe_float(bt.get("win_rate_pct"), PARAMS.get("min_live_win_rate", 45))
    expected_pf = max(_safe_float(bt.get("profit_factor"), 1.2), 0.1)
    expected_rf = max(_safe_float(bt.get("recovery_factor"), 1.0), 0.1)

    if live:
        actual_wr = _safe_float(live.get("win_rate_pct"), expected_wr)
        actual_pf = _safe_float(live.get("profit_factor"), expected_pf)
    else:
        actual_wr = expected_wr
        actual_pf = expected_pf

    wr_score = _component_score(actual_wr, expected_wr, higher_is_better=True)
    pf_score = _component_score(actual_pf, expected_pf, higher_is_better=True)
    benchmark_quality = _benchmark_quality_score(bt)
    rf_score = _component_score(_safe_float(bt.get("recovery_factor"), expected_rf), expected_rf, higher_is_better=True)

    live_sample_ratio = 0.0
    if live:
        target = max(1, int(PARAMS.get("health_recent_trades", 20)))
        live_sample_ratio = min(1.0, float(live.get("recent_trades", 0)) / float(target))

    wr_perf_w = float(PARAMS.get("health_wr_perf_weight", 0.45))
    pf_perf_w = float(PARAMS.get("health_pf_perf_weight", 0.55))
    performance_score = (wr_score * wr_perf_w) + (pf_score * pf_perf_w)

    perf_base = float(PARAMS.get("health_perf_base_weight", 0.20))
    perf_live = float(PARAMS.get("health_perf_live_ratio", 0.30))
    bench_base = float(PARAMS.get("health_bench_base_weight", 0.35))
    bench_live = float(PARAMS.get("health_bench_live_ratio", 0.15))
    rec_base = float(PARAMS.get("health_rec_base_weight", 0.15))
    rec_live = float(PARAMS.get("health_rec_live_ratio", 0.05))
    mode_w = float(PARAMS.get("health_mode_weight", 0.15))
    exec_min = float(PARAMS.get("health_exec_min_weight", 0.10))

    performance_weight = perf_base + (perf_live * live_sample_ratio)
    benchmark_weight = bench_base - (bench_live * live_sample_ratio)
    recovery_weight = rec_base + (rec_live * (1.0 - live_sample_ratio))
    mode_weight = mode_w
    execution_weight = max(exec_min, 1.0 - (performance_weight + benchmark_weight + recovery_weight + mode_weight))

    # Normalize weights to sum to 1.0
    weight_sum = performance_weight + benchmark_weight + recovery_weight + mode_weight + execution_weight
    if weight_sum > 0:
        performance_weight /= weight_sum
        benchmark_weight /= weight_sum
        recovery_weight /= weight_sum
        mode_weight /= weight_sum
        execution_weight /= weight_sum

    health = (
        performance_score * performance_weight +
        benchmark_quality * benchmark_weight +
        rf_score * recovery_weight +
        mode_score * mode_weight +
        execution_score * execution_weight
    )

    health_floor = float(PARAMS.get("health_benchmark_quality_floor", 25.0))
    health = min(health, max(benchmark_quality, health_floor))
    health = max(0.0, min(100.0, health))
    return round(health, 2)


def get_portfolio_mode() -> str:
    score = calculate_health_score()

    active_min = PARAMS.get("health_active_min", 70)
    caution_min = PARAMS.get("health_caution_min", 50)
    warning_min = PARAMS.get("health_warning_min", 30)

    if score >= active_min:
        return "ACTIVE"
    if score >= caution_min:
        return "CAUTION"
    if score >= warning_min:
        return "WARNING"

    _trigger_strategy_failed()
    return "FAILED"


def get_health_multiplier() -> float:
    """
    Smooth multiplier:
        Health 100 => 1.00x
        Health 70  => 0.70x
        Health 40  => 0.40x
        Floor      => 0.10x

    Emergency brakes/circuit can override this elsewhere.
    """
    score = calculate_health_score()
    return round(max(score / 100.0, MIN_HEALTH_CAPITAL_FLOOR), 2)


def _trigger_strategy_failed():
    # Do not auto-kill instantly here; FIX-03 circuit manager handles emergency.
    # Log and alert only. Business pause should be controlled, not accidental shutdown.
    append_log(AUDIT_LOG_FILE, "STRATEGY FAILED HEALTH: score below threshold")

    msg = (
        "STRATEGY HEALTH FAILED\n"
        "Portfolio health below threshold.\n"
        "Review /portfoliohealth and consider /optimize."
    )

    try:
        from signal_broadcaster import alert_admin
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(alert_admin(msg))
        except RuntimeError:
            # No running event loop (sync/scheduler context) — deliver via the
            # author's own sync wrapper instead of silently dropping the alert.
            from signal_broadcaster import alert_admin_sync
            alert_admin_sync(msg)

    except (ImportError, RuntimeError) as e:
        logger.warning(f"_trigger_strategy_failed: Failed to alert admin: {type(e).__name__}: {e}")


def get_portfolio_map() -> str:
    modes = get_all_modes()
    score = calculate_health_score()
    port_mode = get_portfolio_mode()

    if not modes:
        return "No stock mode data yet. Health based on backtest/live benchmark."

    emoji_map = {
        "PROFIT": "G",
        "SOFT_BLOCKED": "Y",
        "RECOVERY": "B",
        "HARD_BLOCKED": "R",
    }

    lines = [
        "Portfolio Map",
        f"Health: {score}/100 | Mode: {port_mode}",
        f"Active stocks tracked: {len(modes)}",
        "",
        f"{'Symbol':<14} {'Mode':<14} {'Mauka'}",
        "-" * 35,
    ]

    for symbol, state in sorted(modes.items()):
        mode = state.get("mode", "PROFIT")
        label = emoji_map.get(mode, "?")
        mauka = "Used" if state.get("mauka_used") else "Avail"
        lines.append(f"{symbol:<14} {mode:<14} {mauka}")

    return "\n".join(lines)


def get_health_summary() -> str:
    modes = get_all_modes()
    score = calculate_health_score()
    mode = get_portfolio_mode()
    multiplier = get_health_multiplier()
    bt = _get_backtest_summary()
    live = _get_live_recent_metrics()

    counts = {"PROFIT": 0, "SOFT_BLOCKED": 0, "RECOVERY": 0, "HARD_BLOCKED": 0}
    for state in modes.values():
        m = state.get("mode", "PROFIT")
        counts[m] = counts.get(m, 0) + 1

    return (
        f"Portfolio Health\n"
        f"Score: {score}/100 | Mode: {mode}\n"
        f"Capital Multiplier: {multiplier}x\n"
        f"Note: 100 health = strategy matching expected benchmark, not 100% win rate.\n\n"
        f"Benchmark WR: {bt.get('win_rate_pct', 'N/A')}% | PF: {bt.get('profit_factor', 'N/A')}\n"
        f"Benchmark Quality Cap: {_benchmark_quality_score(bt) if bt else 'N/A'}/100\n"
        f"Live Recent WR: {live.get('win_rate_pct', 'No live sample')} | PF: {live.get('profit_factor', 'No live sample')}\n\n"
        f"Stocks tracked: {len(modes)}\n"
        f"Profit: {counts['PROFIT']}\n"
        f"Soft Blocked: {counts['SOFT_BLOCKED']}\n"
        f"Recovery: {counts['RECOVERY']}\n"
        f"Hard Blocked: {counts['HARD_BLOCKED']}"
    )
