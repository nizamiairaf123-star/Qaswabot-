"""
parity_engine.py — Runtime parity helpers (Section 12 workflow, Step 3/4).

OWNER-DESIGNED wiring — credit: AIRAF NIZAMI (Design Doc Section 11 R1-R4 gaps,
approved 2026-07-30). Reuses verified building blocks with their own creators:
Risk Parity (Edward Qian 2005 / Bridgewater 1996), Survival circuit
(A. D. Roy Safety-First 1952 family).

GOAL: Backtest/Simulation ko live ke jitne criteria use karwane jitne historically
reconstruct ho sakte hain — WITHOUT look-ahead bias:
  R1 Volatility multiplier  → trade ke din tak ka past window se (PIT-safe)
  R2 Stage deployment %     → same DEPLOYMENT_STAGES multiplier as live
  R3 Gate A/B (fee hurdle)  → SAME capital_manager.is_trade_economically_viable
  R4 Survival circuit       → SAME survival_manager.calculate_survival_plan

CONSCIOUSLY NOT YAHAN (Section 11 verified reasons): current bot health, current
regime, current sector (aaj-ka state; history me =1.0 hi sahi), order-book depth
(historical source nahi — market-data limitation, defect nahi).

FAIL-OPEN DESIGN: kisi bhi helper me error → neutral old behavior (mult 1.0,
no rejection, no circuit). Kuch bhi tootta nahi — worst case = exact old result.
"""

import math
import logging

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252  # NSE convention


# ───────────────────────────── R1: Volatility multiplier (PIT) ─────────────────────────────
def pit_vol_multiplier(df, entry_idx: int, symbol: str = None) -> float:
    """
    Same formula as live capital_manager.get_volatility_multiplier():
    multiplier = target_portfolio_vol / stock_vol, clamped
    [min_volatility_multiplier, max_volatility_multiplier] (defaults 0.3-1.5).

    Difference (parity, PIT-safe): stock_vol yahan LIVE Dhan fetch se nahi,
    historical data ke TRAILING window se aata hai — strictly bars <= entry_idx.
    Future candles compute me shamil NAHI (no look-ahead).
    Fail → 1.0 (neutral = old backtest behavior).
    """
    try:
        from config import PARAMS
        entry_idx = int(entry_idx)
        if entry_idx < 1 or df is None or len(df) < 2:
            return 1.0
        window = int(PARAMS.get("vol_lookback", 20))
        start = max(1, entry_idx - window)
        closes = df["close"].iloc[start:entry_idx + 1]
        if len(closes) < 10:
            return 1.0
        rets = closes.pct_change().dropna()
        if len(rets) < 5:
            return 1.0
        vol = float(rets.std()) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0
        if not math.isfinite(vol) or vol <= 0:
            return 1.0
        target = float(PARAMS.get("target_portfolio_vol", 20.0))
        lo = float(PARAMS.get("min_volatility_multiplier", 0.3))
        hi = float(PARAMS.get("max_volatility_multiplier", 1.5))
        raw = target / vol if vol > 0 else 1.0
        return max(lo, min(hi, round(raw, 2)))
    except Exception as e:
        logger.warning(f"[PARITY] pit_vol_multiplier failed: {e} → 1.0")
        return 1.0


# ───────────────────────────── R2: Stage deployment % ─────────────────────────────
def stage_multiplier() -> float:
    """Same DEPLOYMENT_STAGES[CURRENT_STAGE] as live capital_manager. Fail → 1.0."""
    try:
        from config import DEPLOYMENT_STAGES, CURRENT_STAGE
        return float(DEPLOYMENT_STAGES.get(CURRENT_STAGE, 0.10))
    except Exception as e:
        logger.warning(f"[PARITY] stage_multiplier failed: {e} → 1.0")
        return 1.0


# ───────────────────────────── R3: Gate A/B (same live function) ─────────────────────────────
def gate_ab_allows(symbol: str, qty: int, entry_price: float, expected_tp_return_pct: float) -> bool:
    """
    SAME live gate — delegates to capital_manager.is_trade_economically_viable
    (single source of truth; no duplicate economics).
    Fail-closed: helper unavailable/error → REJECT. Backtest parity must not
    silently bypass the same economics gate used by the live path.
    """
    try:
        from capital_manager import is_trade_economically_viable
        return bool(is_trade_economically_viable(
            symbol, int(qty), float(entry_price),
            expected_tp_return_pct=float(expected_tp_return_pct)))
    except Exception as e:
        logger.error(f"[PARITY] gate_ab_allows failed for {symbol}: {e} → rejected (fail-closed)")
        return False


# ───────────────────────────── R4: Survival circuit (same live plan) ─────────────────────────────
def circuit_dd_pct(capital: float, expected_monthly_return_pct: float = 1.0,
                   monte_carlo_dd_pct: float = None):
    """
    SAME live survival plan — survival_manager.calculate_survival_plan
    (capital + expected monthly profit + survival benchmark based circuit).
    bot_health/regime deliberately None/1.0 (current-state signals — Section 11).
    Returns final_circuit_pct or None (None = no circuit → old behavior).
    """
    try:
        from survival_manager import calculate_survival_plan
        plan = calculate_survival_plan(
            capital=float(capital),
            expected_monthly_return_pct=float(expected_monthly_return_pct or 1.0),
            monte_carlo_safe_dd_pct=monte_carlo_dd_pct,
        )
        if isinstance(plan, dict) and not plan.get("error"):
            return float(plan.get("final_circuit_pct")) if plan.get("final_circuit_pct") is not None else None
        return None
    except Exception as e:
        logger.warning(f"[PARITY] circuit_dd_pct failed: {e} → None")
        return None


# ───────────────────────────── Parity equity pass (single choke point) ─────────────────────────────
def run_parity_equity(trades: list, df, symbol: str, start_capital: float,
                      max_slots: int = 8, tp_return_pct: float = 3.0) -> dict:
    """
    One sequential pass over trades applying R1+R2+R3+R4:

      For each trade (entry_idx asc):
        R4: peak-DD >= circuit → EXIT-ONLY → is trade ke baad ke trades exclude
        R3: qty = per-slot capital / entry_price; Gate A/B reject → exclude
        R1+R2: combined = stage_mult × pit_vol_mult
        capital *= (1 + net_pct/100 × combined / smax)  # per-slot share

    Excluded trades metrics se nikal jaate hain (live bhi unhe leta hi nahi) —
    isliye kept/rejected dono return hote hain, stats kept pe honi chahiye.

    Circuit level: survival plan from start capital + expected monthly return
    estimate (live bhi latest expectation se compute karta hai — same info class;
    documented approximation, fabrication nahi). Helper fail → circuit None
    (old behavior). MC DD (same-run) ko caller baad me de sakta hai — yahan
    None hi use hota hai (conservative: sirf owner caps/economics).
    """
    from config import PARAMS
    from strategy import calculate_price_dd_during_trade

    stage_mult = stage_multiplier()
    smax = max(1, int(PARAMS.get("max_slots", max_slots) or max_slots))

    # Expected monthly return estimate (same info class as live's "latest expectation")
    try:
        nets = [float(t.get("net_return_pct", t.get("return_pct", 0) - PARAMS["trading_cost_pct"]) or 0) for t in trades]
        avg_net = sum(nets) / len(nets) if nets else 0.0
        span_days = max(1, (df.index[-1] - df.index[0]).days) if hasattr(df.index[-1], 'date') else 365
        tpm = max(1.0, len(trades) / max(1.0, span_days / 30.44))
        est_monthly = max(0.0, avg_net * tpm)
    except Exception:
        est_monthly = 1.0
    cct = circuit_dd_pct(start_capital, expected_monthly_return_pct=est_monthly)

    capital = float(start_capital)
    peak = capital
    equity = []
    kept, rejected = [], []
    worst_dd = 0.0
    circuit_hit = False

    for t in sorted(trades, key=lambda x: int(x.get("entry_idx", 0) or 0)):
        entry_idx = t.get("entry_idx")
        exit_idx = t.get("exit_idx")
        entry_price = float(t.get("entry_price", 0) or 0)
        if entry_idx is None or exit_idx is None or entry_price <= 0:
            continue

        # R4: circuit (EXIT-ONLY) — live me circuit ke baad naye trades band
        if cct is not None and peak > 0 and (peak - capital) / peak * 100.0 >= cct:
            circuit_hit = True
            rejected.append({**t, "parity_excluded": "CIRCUIT_EXIT_ONLY"})
            continue

        net_pct = t.get("net_return_pct")
        net_pct = float(net_pct) if net_pct is not None else float(t.get("return_pct", 0) or 0) - float(PARAMS["trading_cost_pct"])
        # [v4.2 SIZING-PARITY] Live ka deployable = stage × health × regime.
        # Backtest parity me stage (deterministic) + vol (PIT-safe) pehle se
        # hain; health/regime LIVE current-state hote hain isliye default
        # neutral (1.0) = point-in-time correctness. Admin chahe to
        # `parity_health_mult` / `parity_regime_mult` (config-driven policy)
        # set kar ke backtest ko expected live conditions ke under chala
        # sakta hai — koi hardcode nahi, defaults behavior change nahi karte.
        parity_health = float(PARAMS.get("parity_health_mult", 1.0) or 1.0)
        parity_regime = float(PARAMS.get("parity_regime_mult", 1.0) or 1.0)
        combined = stage_mult * pit_vol_multiplier(df, int(entry_idx), symbol) * parity_health * parity_regime

        # R3: Gate A/B — per-slot capital se qty, same live check
        per_slot = (capital * combined) / smax
        qty = int(per_slot / entry_price) if entry_price > 0 else 0
        if qty <= 0 or not gate_ab_allows(symbol, qty, entry_price, tp_return_pct):
            rejected.append({**t, "parity_excluded": "GATE_AB"})
            continue

        try:
            trade_bars = df.iloc[int(entry_idx):int(exit_idx) + 1]
            worst_dd = min(worst_dd, calculate_price_dd_during_trade(trade_bars, entry_price))
        except Exception:
            pass

        capital *= (1 + (net_pct / 100.0) * combined / smax)  # [PHD-FIX F1] per-slot share: qty = deployable/smax, isliye portfolio P&L = net% × combined/smax
        peak = max(peak, capital)
        equity.append(capital)
        kept.append(t)

    return {
        "kept_trades": kept,
        "rejected_trades": rejected,
        "final_capital": capital,
        "equity": equity,
        "worst_price_dd": worst_dd,
        "circuit_dd_pct": cct,
        "circuit_hit": circuit_hit,
        "stage_mult": stage_mult,
        "n_rejected": len(rejected),
    }
