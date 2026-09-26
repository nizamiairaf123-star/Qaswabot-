"""
risk_display.py — Phase-2 PATCH P3 (Feature B): Risk-First Display (ADD-ONLY).

SLOGANS (owner-designed — custom, koi external creator nahi; honestly marked):
  Slogan-1: "Kamai dekh ke nahi — JHELNE ki capacity dekh ke invest karo."
  Slogan-2: "Achhe result ke liye ₹X se start karo." (X = data-driven min capital)

METHOD ATTRIBUTIONS (user rule: har update ke aage method + creator):
  - Daily Loss Limit ₹     → repo ka EXISTING budget engine:
                             [Half-Kelly — J.L. Kelly, 1956 / Thorp; repo: capital_drawdown_manager]
  - Per-trade risk scaling → [Position sizing — Ralph Vince, "Portfolio Management
                             Formulas", 1992; Kelly Criterion — J.L. Kelly, 1956; E. Thorp]
  - Worst-day estimate     → MAX( backtest worst day , Monte Carlo 99% )
                             [Monte Carlo — Metropolis & Ulam, 1946]
  - Min capital (Slogan-2) → [Owner-designed hurdle: capital_drawdown_manager.
                             calculate_head_of_calculation_hurdles → min_viable_capital_stage_1]
  - Risk-first framing     → [Behavioral-finance practice: show loss capacity before
                             profit — custom application, inspired by loss-aversion
                             research (Kahneman & Tversky, 1979)]

IMPORTANT (ADD-ONLY guarantee):
  Yeh sirf DISPLAY layer hai. Existing risk calculations / order gates / limits
  KAHIN touch nahi hote. Har number graceful fallback ke saath — data na ho to
  honest "data pending" line, kabhi guess nahi.
"""

from __future__ import annotations

from config import PARAMS, BACKTEST_RESULTS_FILE
from utils import load_json

SLOGAN_1 = "Kamai dekh ke nahi — JHELNE ki capacity dekh ke invest karo."
SLOGAN_2_TMPL = "Achhe result ke liye kam se kam ₹{min_cap:,.0f} se start karo."

METHOD_LINE = (
    "Methods: Half-Kelly — J.L. Kelly, 1956 | Position sizing — R. Vince, 1992 / E. Thorp | "
    "Monte Carlo — Metropolis & Ulam, 1946 | Loss-aversion — Kahneman & Tversky, 1979 | "
    "Slogans & min-capital hurdle — owner-designed (custom)"
)


# ─────────────────────────────────────────
# COLLECTORS (best-effort; kuch bhi fail → None, kabhi crash nahi)
# ─────────────────────────────────────────

def collect_daily_loss_limit(capital: float) -> dict:
    """Daily loss limit ₹: existing dynamic budget engine → fallback config 2% flat."""
    try:
        from capital_drawdown_manager import calculate_daily_risk_budget
        from survival_manager import get_bot_health_pct
        budget = calculate_daily_risk_budget(capital, get_bot_health_pct())
        if not budget.get("error") and budget.get("max_daily_loss") is not None:
            return {"amount": float(budget["max_daily_loss"]),
                    "source": "dynamic budget (Half-Kelly — Kelly 1956, via capital_drawdown_manager)"}
    except Exception:
        pass
    flat_pct = float(PARAMS.get("daily_loss_limit_pct", 2.0))
    return {"amount": capital * flat_pct / 100.0,
            "source": f"fallback flat {flat_pct}% (config daily_loss_limit_pct)"}


def collect_min_capital(capital: float) -> dict:
    """Slogan-2 ka ₹X — owner-designed hurdle engine se (data-driven, static nahi)."""
    try:
        from capital_drawdown_manager import calculate_head_of_calculation_hurdles
        h = calculate_head_of_calculation_hurdles(capital)
        if not h.get("error"):
            return {"min_capital": float(h["min_viable_capital_stage_1"]),
                    "viable": bool(h.get("viable_at_stage_1")),
                    "source": "capital_drawdown_manager.calculate_head_of_calculation_hurdles (owner-designed)"}
    except Exception:
        pass
    return {"min_capital": None, "viable": None, "source": "unavailable"}


def collect_backtest_stats() -> dict:
    """Last /backtest se: worst single-day loss ₹, avg CAGR (projection ke liye),
    losing-trade return pool (Monte Carlo ke liye). File na ho → honest None."""
    try:
        data = load_json(BACKTEST_RESULTS_FILE, {})
    except Exception:
        data = {}
    stocks = (data or {}).get("stocks") or {}
    if not stocks:
        return {"worst_day_amt": None, "cagr_pct": None, "loss_returns_pct": [], "source": "no backtest yet"}
    worst = None
    cagrs, losses = [], []
    for r in stocks.values():
        if not isinstance(r, dict):
            continue
        msd = r.get("max_single_day_loss_amt")
        if isinstance(msd, (int, float)) and (worst is None or msd < worst):
            worst = float(msd)
        if isinstance(r.get("cagr_pct"), (int, float)):
            cagrs.append(float(r["cagr_pct"]))
        # per-trade returns pool: avg_loss × losing_trades (approx pool — trade-level
        # _net_returns_pct save nahi hoti; approximation honestly noted)
        nr = int(r.get("losing_trades", 0) or 0)
        al = r.get("avg_loss_pct")
        if nr > 0 and isinstance(al, (int, float)) and al < 0:
            losses.extend([float(al)] * min(nr, 25))  # cap per-stock to keep pool sane
    return {
        "worst_day_amt": worst,
        "cagr_pct": (sum(cagrs) / len(cagrs)) if cagrs else None,
        "loss_returns_pct": losses,
        "source": f"last backtest ({len(stocks)} stocks, {data.get('run_date', '?')[:10]})",
    }


def collect_worst_day(capital: float, open_slots: int = None) -> dict:
    """
    Conservative MAX(|backtest worst day|, |Monte Carlo 99%|).
    [Design doc open-item #3 resolution: conservative max, honestly labeled]
    slots default = max_slots (worst-case full deployment — display conservative raho).
    Position size = validator_reference_capital (backtest bhi isi scale pe hai).
    """
    bt = collect_backtest_stats()
    slots = int(open_slots if open_slots is not None else PARAMS.get("max_slots", 3))
    ref_cap = float(PARAMS.get("validator_reference_capital", capital))
    mc = {"pct99_loss_amt": None}
    if bt["loss_returns_pct"]:
        try:
            import monte_carlo
            mc = monte_carlo.estimate_max_day_loss(
                bt["loss_returns_pct"], position_size_amt=ref_cap, open_slots=slots)
        except Exception:
            mc = {"pct99_loss_amt": None}
    cands = []
    if bt["worst_day_amt"] is not None:
        cands.append(abs(bt["worst_day_amt"]))
    if mc.get("pct99_loss_amt") is not None:
        cands.append(abs(mc["pct99_loss_amt"]))
    return {
        "worst_day": (max(cands) if cands else None),
        "backtest_day": bt["worst_day_amt"],
        "mc_day": mc.get("pct99_loss_amt"),
        "mc": mc, "bt": bt, "slots": slots, "ref_cap": ref_cap,
    }


# ─────────────────────────────────────────
# FORMATTER (pure function — tests isi pe chalte hain)
# ─────────────────────────────────────────

def build_risk_first_block(capital: float, open_slots: int = None,
                           compact: bool = False) -> str:
    """
    Slogan-1 block — /simulate, /dashboard, /pnl, /report, /link-onboarding sab yahi call karte hain.
    Har value ke saath source honest hai; missing data = 'pending' line (guess kabhi nahi).
    """
    cap = max(float(capital or 0.0), 0.0)
    dll = collect_daily_loss_limit(cap)
    wd = collect_worst_day(cap, open_slots)
    mc2 = collect_min_capital(cap)

    profit_line = "🎯 PROFIT (projection): data pending — pehle /backtest chalao"
    if wd["bt"]["cagr_pct"] is not None and cap > 0:
        monthly = cap * (wd["bt"]["cagr_pct"] / 100.0) / 12.0
        profit_line = (f"🎯 PROFIT (projection): ≈ ₹{monthly:,.0f}/month "
                       f"(last backtest CAGR {wd['bt']['cagr_pct']:.1f}% se — projection hai, GUARANTEE nahi)")

    worst_line = "📉 WORST DAY: data pending — /backtest ke baad exact ₹ dikhega"
    nudge = ""
    if wd["worst_day"] is not None:
        worst_line = (f"📉 WORST DAY (ek din ka max nuksaan, 99% Monte Carlo + backtest): "
                      f"≈ ₹{wd['worst_day']:,.0f}")
        nudge = (f"   ❓ Kya aap ₹{wd['worst_day']:,.0f} ek din me jaate dekh SHAANT rah sakte ho? "
                 f"Nahi → capital kam karo. Yahi 'jhelne ki capacity' hai.")

    mincap_line = "💡 Min capital (Slogan-2): data pending"
    if mc2["min_capital"]:
        mincap_line = "💡 " + SLOGAN_2_TMPL.format(min_cap=mc2["min_capital"])
        if mc2["viable"] is False and cap > 0:
            mincap_line += "  ⚠️ (aapka capital iske neeche hai)"

    risk_pct = float(PARAMS.get("optimal_risk_per_trade_pct") or PARAMS.get("risk_per_trade_pct") or 0.5)
    lines = [
        "🧭 *Pehle JHELNE ki capacity — kamai baad me*",
        f"«{SLOGAN_1}»",
        "",
        profit_line,
        f"🛑 DAILY LOSS LIMIT: ₹{dll['amount']:,.0f}/day — iske baad bot aaj ke liye naye entries BAND ({dll['source']})",
        worst_line,
        nudge,
        "",
        mincap_line,
        f"ℹ️ Risk/trade = deployed × {risk_pct:.1f}% — deployed amount ke saath risk SCALE hota hai (fixed ₹ nahi)",
    ]
    if not compact:
        lines += ["", f"_{METHOD_LINE}_"]
    return "\n".join([l for l in lines if l is not None])


def build_onboarding_block() -> str:
    """/link ke waqt — capital abhi unknown, isliye compact capacity-first note."""
    return (
        "🧭 *Pehle JHELNE ki capacity — kamai baad me*\n"
        f"«{SLOGAN_1}»\n\n"
        "Link ke baad /dashboard pe dikhega: DAILY LOSS LIMIT ₹, WORST DAY ₹, "
        "aur data-driven minimum capital (Slogan-2). "
        "Capital aap decide karo — loss capacity dekh ke, profit dekh ke nahi.\n"
        f"_{METHOD_LINE}_"
    )
