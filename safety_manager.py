"""
safety_manager.py — Daily limits, rapid loss detection, reconciliation
"""

import logging
import math
from utils import load_json, save_json, now_ist, today_ist, append_log
from config import PARAMS, AUDIT_LOG_FILE

logger = logging.getLogger(__name__)

SAFETY_FILE = "data/safety_state.json"


def _load() -> dict:
    return load_json(SAFETY_FILE, {
        "date": None,
        "trades_today": 0,
        "day_pnl": 0.0,
        "daily_risk_used_pct": 0.0,  # Cumulative daily risk budget
        "sl_hits": [],       # List of timestamps
        "pause_until": None,
    })


def _save(data: dict):
    save_json(SAFETY_FILE, data)


def _reset_if_new_day(data: dict) -> dict:
    today = today_ist().isoformat()
    if data.get("date") != today:
        data["date"] = today
        data["trades_today"] = 0
        data["day_pnl"] = 0.0
        data["daily_risk_used_pct"] = 0.0
        data["sl_hits"] = []
        data["pause_until"] = None
        data["sl_streak"] = 0   # PHASE: consecutive-loss counter (owner rule)
    return data


# ─────────────────────────────────────────────
# CONSECUTIVE-LOSS STREAK THRESHOLD — dynamic (OWNER DECISION #5, 2026-07-30;
# CORRECTED version — owner 3 corrections, 2026-07-30)
# ─────────────────────────────────────────────

def geometric_runlength_streak_threshold(win_rate: float, p_cap: float = None) -> int:
    """Exact crossing-point se threshold: k = max(2, round(ln(p_cap) / ln(1-WR))).

    [DESIGN: AIRAF NIZAMI.
    Method: GEOMETRIC RUN-LENGTH TAIL — P(run of k losses) = (1-WR)^k,
    geometric distribution (standard probability theory).
    YAHI SAHI NAAM HAI. Pehle "Wald-Wolfowitz Runs Test (1940)" tag lagaya
    gaya tha — wo GHALAT tha (Wald-Wolfowitz ek non-parametric RANDOMNESS
    test hai; hum yahan randomness test nahi, run-length tail probability
    use karte hain). Owner correction (b), 2026-07-30 — name fixed.

    FORMULA (owner correction (a), 2026-07-30 — "exact crossing-point use
    karo, n=4 na ki 5"): exact (real-valued) crossing k* wo point hai jahan
    (1-WR)^k* = p_cap theek hota hai:  k* = ln(p_cap) / ln(1-WR).
    Streaks poore numbers me hoti hain, isliye k = k* ka NEAREST integer
    (round half up), floor 2. Example: WR 50% → k* = ln(0.05)/ln(0.5) = 4.32
    → k = 4 (purana one-sided strict rule 5 deta tha).
    Trade-off (honest note): crossing ke sabse qareeb integer lene se P(k)
    kabhi-kabhi p_cap se THODA upar bhi ho sakta hai (WR50%: 6.25%) —
    ye "hamesha 5% se neeche" nahi, "5% line ke sabse qareeb" rule hai.
    Worked values (p_cap=5%): WR 40% → k=6 (k*=5.86), WR 50% → k=4 (4.32),
    WR 55% → k=4 (3.75), WR 70% → k=2 (2.49).

    INDEPENDENCE ASSUMPTION (owner correction (c), 2026-07-30 — explicitly):
    (1-WR)^k tail tabhi valid hai jab trades INDEPENDENT hon (iid Bernoulli) —
    yaani ek trade ka result agle trade ke outcome probability ko change na
    kare. Real markets me losses cluster ho sakti hain (regime shifts, gap
    risk), to ye ek APPROXIMATION hai — exact guarantee nahi. Isi liye:
    (i) WR input khud WFV out-of-sample verified chain se aata hai,
    (ii) koi bhi data suspect ho to EXACT purana fixed-3 rule (fail-open),
    (iii) daily loss limit alag se backstop bana rehta hai.

    Owner values: p_cap = 5% (PARAMS runs_test_streak_p_cap_pct),
    k minimum 2 (ek akeli loss par kabhi stop nahi). Pure math — no I/O,
    directly testable.]
    """
    if p_cap is None:
        p_cap = PARAMS.get("runs_test_streak_p_cap_pct", 5.0) / 100.0
    p_cap = float(p_cap)
    wr = float(win_rate)
    if not math.isfinite(p_cap) or not math.isfinite(wr):
        raise ValueError(f"non-finite input (wr={win_rate}, p_cap={p_cap})")  # caller fail-open karega
    p_cap = min(max(p_cap, 0.001), 0.5)   # sanity guard — cap hi cap rehne do
    wr = min(max(wr, 0.05), 0.95)         # sanity guard — ghalat WR data par bhi safe
    crossing = math.log(p_cap) / math.log(1.0 - wr)   # exact real-valued crossing k*
    return max(2, int(math.floor(crossing + 0.5)))    # nearest integer, floor 2


def _get_streak_win_rate(symbol: str = None):
    """Verified WR chain — SAME verified-data sources as capital_drawdown_manager:
    1) per-symbol WFV out-of-sample test_wr  (best — Walk-Forward OOS)
    2) per-symbol optimizer win_rate_pct
    3) portfolio backtest summary win_rate_pct
    Returns (win_rate 0..1 or None, source_str). Koi assumption nahi — sirf
    bot ke apne verified files. Missing data → None (caller fail-open karega)."""
    try:
        if symbol:
            wfv = load_json("data/walk_forward_results.json", {})
            s_wfv = wfv.get(symbol) if isinstance(wfv, dict) else None
            if isinstance(s_wfv, dict) and s_wfv.get("test_wr"):
                return float(s_wfv["test_wr"]) / 100.0, "wfv_oos"
            opt = load_json("data/optimizer_results.json", {})
            s_opt = opt.get("results", {}).get(symbol) if isinstance(opt, dict) else None
            if isinstance(s_opt, dict) and s_opt.get("win_rate_pct"):
                return float(s_opt["win_rate_pct"]) / 100.0, "optimizer"
        bt = load_json("data/backtest_results.json", {})
        summary = bt.get("summary", {}) if isinstance(bt, dict) else {}
        if summary.get("win_rate_pct"):
            return float(summary["win_rate_pct"]) / 100.0, "backtest"
    except (TypeError, ValueError, KeyError) as e:
        logger.debug(f"_get_streak_win_rate: data parse failed: {type(e).__name__}: {e}")
    return None, None


def _dynamic_streak_threshold(symbol: str = None):
    """Machine-derived streak threshold (owner decision #5, 2026-07-30).
    FAIL-OPEN STRICT: koi bhi error ya verified WR missing → EXACT old behavior
    = PARAMS['rapid_loss_count'] (fixed 3). Returns (threshold:int, basis:str)."""
    fallback = int(PARAMS.get("rapid_loss_count", 3))
    try:
        wr, src = _get_streak_win_rate(symbol)
        if wr is None:
            return fallback, f"no verified WR → fixed {fallback}"
        k = geometric_runlength_streak_threshold(wr)
        return k, f"{src} WR={wr*100:.1f}% → crossing≈5% → k={k}"
    except (TypeError, ValueError, KeyError, ArithmeticError) as e:
        logger.warning(f"_dynamic_streak_threshold failed: {type(e).__name__}: {e} → fixed {fallback}")
        return fallback, f"fail-open → fixed {fallback}"


# ─────────────────────────────────────────────
# DAILY LOSS LIMIT
# ─────────────────────────────────────────────

def is_daily_limit_hit() -> bool:
    data = _reset_if_new_day(_load())
    # AUDIT FIX (Bug #1, fail-open): a failed balance fetch used to be
    # indistinguishable from a genuine ₹0 balance, and both returned False
    # ("limit not hit") -- allowing new trades exactly when the daily-loss
    # check could not actually be verified. get_available_balance_or_none()
    # signals a fetch failure explicitly as None; fail CLOSED on it (treat
    # as limit hit) instead of silently permitting entries.
    from broker import get_available_balance_or_none
    balance = get_available_balance_or_none()
    if balance is None:
        logger.warning("is_daily_limit_hit: balance fetch failed -- failing closed (limit treated as hit)")
        return True
    if balance <= 0:
        return False

    try:
        from capital_drawdown_manager import calculate_daily_risk_budget
        from survival_manager import get_bot_health_pct
        budget = calculate_daily_risk_budget(balance, get_bot_health_pct())
        if not budget.get("error") and "max_daily_loss" in budget:
            max_daily_loss = float(budget["max_daily_loss"])
            return float(data["day_pnl"]) <= -max_daily_loss
    except (ImportError, RuntimeError, ValueError, TypeError, KeyError) as e:
        logger.warning(f"is_daily_limit_hit: Risk budget check failed: {type(e).__name__}: {e}")

    pnl_pct = data["day_pnl"] / balance * 100
    return pnl_pct <= -PARAMS["daily_loss_limit_pct"]


def record_trade_pnl(pnl_amount: float, symbol: str = None):
    data = _reset_if_new_day(_load())
    data["day_pnl"] += pnl_amount
    data["trades_today"] += 1
    _save(data)

    # ── Consecutive-loss DAY STOP [OWNER RULE 2026-07-29; UPGRADE #5 2026-07-30] ──
    # BACK-TO-BACK losses (beech me jeet → reset) → us din STOP;
    # agle trading day 09:15 auto-resume (scheduler check job).
    # Threshold ab machine-derived hai (Geometric Run-Length Tail,
    # _dynamic_streak_threshold): har stock ka verified WR → exact 5%-crossing
    # ka nearest-integer k. Verified WR nahi mila /
    # koi error → EXACT old fixed rule (PARAMS rapid_loss_count = 3) — fail-open.
    # [DESIGN: AIRAF NIZAMI — method: Geometric Run-Length Tail, geometric
    #  distribution (standard probability theory); independence assumption
    #  docstring me explicitly documented]
    if PARAMS.get("rapid_loss_pause_mode", "REST_OF_DAY") == "REST_OF_DAY":
        data = _load()
        if pnl_amount > 0:
            data["sl_streak"] = 0
        else:
            data["sl_streak"] = int(data.get("sl_streak", 0)) + 1
            count_needed, thr_basis = _dynamic_streak_threshold(symbol)
            if data["sl_streak"] >= count_needed and not data.get("pause_until"):
                pause_until = _next_trading_open_iso()
                data["pause_until"] = pause_until
                append_log(AUDIT_LOG_FILE,
                           f"CONSECUTIVE LOSS DAY-STOP: {data['sl_streak']} back-to-back losses "
                           f"(threshold={count_needed} | {thr_basis}) "
                           f"-- no new entries for the day, auto-resume {pause_until}")
                _save(data)
                from bot_state_manager import activate_rapid_loss_pause
                activate_rapid_loss_pause(f"{data['sl_streak']} consecutive losses — stopped for the day")
                return
        _save(data)

    if is_daily_limit_hit():
        append_log(AUDIT_LOG_FILE,
                   f"DAILY LIMIT HIT: day_pnl={data['day_pnl']:.2f} — trading stopped for today")


def _next_trading_open_iso() -> str:
    """Agle trading day 09:15 IST (weekend/NSE holidays skip) — auto-resume point."""
    from datetime import datetime, time as dtime, timedelta
    from utils import NSE_HOLIDAYS
    d = today_ist() + timedelta(days=1)
    while d.weekday() >= 5 or d.isoformat() in NSE_HOLIDAYS:
        d += timedelta(days=1)
    return datetime.combine(d, dtime(9, 15)).isoformat()


# ─────────────────────────────────────────────
# MAX TRADES PER DAY
# ─────────────────────────────────────────────

def is_max_trades_hit() -> bool:
    data = _reset_if_new_day(_load())
    return data["trades_today"] >= PARAMS["max_trades_per_day"]


# ─────────────────────────────────────────────
# TRADING PAUSE
# ─────────────────────────────────────────────

def is_trading_paused() -> bool:
    """Check if trading is currently paused via data['pause_until'].

    Restored as a real, callable function (previously this code had no
    'def' line and was silently unreachable dead code appended to
    is_max_trades_hit(), after its return statement). record_sl_hit()
    below is the setter that populates 'pause_until'.
    """
    data = _reset_if_new_day(_load())
    pause_until = data.get("pause_until")
    if not pause_until:
        return False
    from datetime import datetime
    return now_ist() < datetime.fromisoformat(pause_until).replace(tzinfo=now_ist().tzinfo)


def get_pause_until():
    """Raw pause_until value (ISO string or None). Used by the
    scheduler's auto-expiry job to know when to revert RAPID_LOSS_PAUSE."""
    data = _reset_if_new_day(_load())
    return data.get("pause_until")


def record_sl_hit():
    """FIX: wires up the rapid-loss brake (MINUTES mode, legacy).

    Call this whenever a trade closes via stop-loss. If rapid_loss_count SL
    hits occur within rapid_loss_window_min minutes, activates
    RAPID_LOSS_PAUSE for rapid_loss_pause_min minutes.

    OWNER RULE (2026-07-29): default mode REST_OF_DAY — streak record_trade_pnl
    me handle hota hai (3 back-to-back losses → din band). Isliye ye window-
    based version sirf rapid_loss_pause_mode == "MINUTES" pe chalti hai,
    warna no-op (double-pause rokne ke liye).
    """
    if PARAMS.get("rapid_loss_pause_mode", "REST_OF_DAY") != "MINUTES":
        return
    from datetime import datetime, timedelta
    data = _reset_if_new_day(_load())
    now = now_ist()
    hits = data.get("sl_hits", [])
    hits.append(now.isoformat())

    window_min = PARAMS.get("rapid_loss_window_min", 30)
    cutoff = now - timedelta(minutes=window_min)
    recent = [t for t in hits if datetime.fromisoformat(t) >= cutoff]
    data["sl_hits"] = recent

    count_needed = PARAMS.get("rapid_loss_count", 3)
    if len(recent) >= count_needed:
        pause_min = PARAMS.get("rapid_loss_pause_min", 60)
        pause_until = (now + timedelta(minutes=pause_min)).isoformat()
        data["pause_until"] = pause_until
        _save(data)
        append_log(AUDIT_LOG_FILE,
                   f"RAPID LOSS PAUSE: {len(recent)} SL hits in {window_min}min "
                   f"-- new entries paused until {pause_until}")
        from bot_state_manager import activate_rapid_loss_pause
        activate_rapid_loss_pause()
    else:
        _save(data)


# ─────────────────────────────────────────────
# DAILY RECONCILIATION
# ─────────────────────────────────────────────

def run_reconciliation():
    """
    Startup/manual reconciliation entry point.

    Delegates to trade_engine.run_reconciliation() -- the single owner
    engine for reconciliation logic (FIX-11 Reconciliation Action Matrix:
    Case 1/2/3 handling, state mutation via release_trade()/
    log_trade_exit()/close_forever_orders(), RECONCILIATION_HOLD
    activation) -- instead of duplicating a simpler, weaker check here.
    Constitution Art. 2.1/2.2: one decision, one owner engine.

    trade_engine.run_reconciliation() is async; this function is called
    synchronously from bot.py's main() at raw startup, before any event
    loop is running, so it safely creates and runs one here. If ever
    called from within an already-running loop instead, schedules as a
    task rather than nesting asyncio.run().
    """
    import asyncio
    from trade_engine import run_reconciliation as _owner_run_reconciliation
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_owner_run_reconciliation())
    except RuntimeError:
        # No running event loop (the expected case: called synchronously
        # right after restart, before the bot's async loop is up).
        try:
            asyncio.run(_owner_run_reconciliation())
        except Exception as e:
            append_log(AUDIT_LOG_FILE, f"RECONCILIATION ERROR: {e}")

# ─────────────────────────────────────────────
# ECONOMIC HEALTH MONITORING
# ─────────────────────────────────────────────

def check_economic_health():
    """
    Alert admin if:
    - No trade in 72 hours
    - Error count > 10/hour (from audit log)
    - Low deployable capital under owner low-balance logic
    """
    try:
        from signal_broadcaster import alert_admin
        from broker import get_available_balance
        from capital_manager import get_stage_readiness_decision
        import asyncio

        balance = get_available_balance()
        stage_ready = get_stage_readiness_decision(capital=float(balance or 0))
        if not stage_ready.get("allow", True):
            _msg = f"⚠️ Low balance / stage readiness: {stage_ready.get('reason')} | Balance ₹{balance:.2f}"
            try:
                asyncio.get_running_loop().create_task(alert_admin(_msg))
            except RuntimeError:
                # No running loop (scheduler thread) — deliver via sync wrapper
                from signal_broadcaster import alert_admin_sync
                alert_admin_sync(_msg)

        # Check last trade time
        data = load_json("data/trades.json", {"trades": []})
        trades = data.get("trades", [])
        if trades:
            from datetime import datetime
            last_trade = datetime.fromisoformat(trades[-1]["timestamp"])
            hours_since = (now_ist().replace(tzinfo=None) - last_trade.replace(tzinfo=None)).total_seconds() / 3600
            if hours_since > 72:
                _msg = f"⚠️ No trade in {hours_since:.0f} hours"
                try:
                    asyncio.get_running_loop().create_task(alert_admin(_msg))
                except RuntimeError:
                    # No running loop (scheduler thread) — deliver via sync wrapper
                    from signal_broadcaster import alert_admin_sync
                    alert_admin_sync(_msg)
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"HEALTH CHECK ERROR: {e}")


# ─────────────────────────────────────────────
# DAILY RISK BUDGET
# Source: Professional risk management (Van Tharp)
# Verified: Track cumulative risk allocated per day
# ─────────────────────────────────────────────

def get_daily_risk_used() -> float:
    """Get total risk % used today."""
    data = _reset_if_new_day(_load())
    return data.get("daily_risk_used_pct", 0.0)


def record_risk_used(risk_pct: float):
    """Record risk allocated to a trade. Called when trade enters."""
    data = _reset_if_new_day(_load())
    data["daily_risk_used_pct"] = data.get("daily_risk_used_pct", 0.0) + risk_pct
    _save(data)

    try:
        from broker import get_available_balance
        from capital_drawdown_manager import calculate_daily_risk_budget
        from capital_manager import get_health_capital_multiplier
        budget_ctx = calculate_daily_risk_budget(float(get_available_balance() or 0), get_health_capital_multiplier() * 100.0)
        budget = float(budget_ctx.get("adjusted_risk_pct", 1.5) or 1.5)
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"is_daily_risk_budget_exceeded: Risk budget calc failed: {type(e).__name__}: {e}")
        budget = PARAMS.get("daily_risk_budget_pct", 1.5)
    if data["daily_risk_used_pct"] >= budget:
        append_log(AUDIT_LOG_FILE,
                   f"DAILY RISK BUDGET USED: {data['daily_risk_used_pct']:.2f}% of {budget}%")


def is_daily_risk_budget_hit() -> bool:
    """Check if daily risk budget is exhausted."""
    data = _reset_if_new_day(_load())
    try:
        from broker import get_available_balance
        from capital_drawdown_manager import calculate_daily_risk_budget
        from capital_manager import get_health_capital_multiplier
        budget_ctx = calculate_daily_risk_budget(float(get_available_balance() or 0), get_health_capital_multiplier() * 100.0)
        budget = float(budget_ctx.get("adjusted_risk_pct", 1.5) or 1.5)
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"is_daily_risk_used_exceeded: Risk budget calc failed: {type(e).__name__}: {e}")
        budget = PARAMS.get("daily_risk_budget_pct", 1.5)
    return data.get("daily_risk_used_pct", 0.0) >= budget
