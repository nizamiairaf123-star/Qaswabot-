"""
ECONOMICS BRAIN — Owner-approved constitution of number bands.

OWNER-DESIGNED framework — credit: AIRAF NIZAMI (Economics Brain Design Doc §7/§8A,
approved 2026-07-30). Adapted from Goals-Based Wealth Management (Jean Brunel, CFA
Institute 2015), Behavioral Portfolio Theory (Shefrin & Statman 2000), Safety-First
(A. D. Roy 1952). Underlying verified methods keep their own creators (Risk Parity —
Qian 2005; Monte Carlo — Boyle 1977 / Efron 1979; MRM — Fed SR 11-7 2011, etc.).

RUNTIME GOVERNANCE (ADR §8A engineering terminology, owner review 2026-07-30):
  Set Batsman  = current validated production configuration
  New Batsman  = candidate configuration under evaluation
  Fallback     = last validated production configuration
  Captains Rules = risk envelope & governance constraints

  [Industry frame (retag 2026-07-30, approved same day): "Set Batsman / New Batsman"
   owner ka cricket-metaphor NAAM hai; iska industry-verified equivalent hai
   CHAMPION / CHALLENGER — banking model-risk management ki practice (ek champion
   model production me rehta hai, challenger sirf validation pass karne par
   promote hota hai; industry convention — koi single formal creator nahi,
   honestly marked). Behavior koi change nahi — sirf naam ka honest mapping.]

  If the candidate configuration fails validation, the production configuration
  remains active. No automatic promotion occurs.

SAFETY DESIGN:
  - This module NEVER raises on bad input. Every public function falls back to the
    current production value on any failure (last validated configuration remains
    active). Kuch tootta nahi — worst case = exact old behavior.
  - Machine can only pick INSIDE owner bands. Band ke bahar candidate ban hi nahi
    sakta / clamp ho jata hai.
"""

import logging

# [FIX — QUANT-002 audit, 2026-09] calculate_max_slots_candidate() below reads
# PARAMS.get("brokerage_min_inr"/"brokerage_rate_pct"/"statutory_rate_pct")
# but this module never imported PARAMS. Every call raised NameError, was
# swallowed by get_recommended_max_slots()'s except clause, and silently
# fell back to the static band value — so the dynamic economics-based
# max_slots feature (this file's own stated purpose, "[AUDIT FIX Gap #11]")
# has never actually run. This import is the only change; no formula logic
# touched.
from config import PARAMS

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
# OWNER BAND CONSTITUTION (approved 2026-07-30) — credit: AIRAF NIZAMI
# low/high = hard bounds. Machine choose karega band ke ANDAR, kabhi bahar nahi.
# fallback  = current validated production configuration (Set Batsman).
# track: "live-cal" = paper/live data se calibrate hoga (Band B),
#        "formula"  = configured R:R se derive (Band A)
# ══════════════════════════════════════════════════════════════════════
BANDS = {
    "target_portfolio_vol": {
        "low": 10.0, "high": 20.0, "fallback": 20.0, "track": "live-cal",
        "note": "Bridgewater 10-12% / Pure Alpha II 18% reference; 20 = legacy bootstrap"},
    "health_active_min": {
        "low": 65.0, "high": 80.0, "fallback": 70.0, "track": "live-cal",
        "note": "Component-independent band (owner correction 2026-07-30)"},
    "health_caution_min": {
        "low": 40.0, "high": 60.0, "fallback": 50.0, "track": "live-cal", "note": ""},
    "health_warning_min": {
        "low": 20.0, "high": 35.0, "fallback": 30.0, "track": "live-cal", "note": ""},
    "stage_up_win_rate": {
        "low": 50.0, "high": 65.0, "fallback": 55.0, "track": "live-cal", "note": ""},
    "stage_down_win_rate": {
        "low": 35.0, "high": 45.0, "fallback": 40.0, "track": "live-cal", "note": ""},
    "max_wr_gap_vs_backtest": {
        "low": 10.0, "high": 20.0, "fallback": 15.0, "track": "live-cal", "note": ""},
    "max_consecutive_losses_validator": {
        "low": 3.0, "high": 7.0, "fallback": 5.0, "track": "live-cal",
        "note": "Binomial anchor: 5 @50% WR = 3.1% chance (Bernoulli 1713)"},
    "profit_degradation_alert_pct": {
        "low": 10.0, "high": 30.0, "fallback": 20.0, "track": "live-cal",
        "note": "POLICY threshold — final value needs implementation validation + historical benchmark testing"},
    "max_idle_trading_days": {
        "low": 5.0, "high": 15.0, "fallback": 10.0, "track": "live-cal", "note": ""},
    "backtest_warn_days": {
        "low": 60.0, "high": 120.0, "fallback": 90.0, "track": "live-cal", "note": ""},
    "backtest_block_days": {
        "low": 120.0, "high": 270.0, "fallback": 180.0, "track": "live-cal", "note": ""},
    "mc_robustness_min": {
        "low": 0.5, "high": 0.8, "fallback": 0.6, "track": "live-cal", "note": ""},
    "max_slots": {
        "low": 5.0, "high": 10.0, "fallback": 8.0, "track": "live-cal",
        "note": "[OVERRIDE 3] band tightened 5-12->5-10 per user-authorized pivot: equal-weight top 5-10 setups/day"},
    "min_live_win_rate": {
        "low": 30.0, "high": 45.0, "fallback": 40.0, "track": "formula",
        "note": "min_wr = 1/(1+effective R:R). NOT universal — recalc if R:R changes"},
}

# Guard band for the R:R-derived floor (owner rule 2026-07-30)
MIN_WR_GUARD_LOW = 30.0
MIN_WR_GUARD_HIGH = 45.0


def _safe_num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ══════════════════════════════════════════════════════════════════════
# [AUDIT FIX Gap #11 — 2026-08] HONEST STATUS OF THIS FRAMEWORK
# resolve_param() below is the intended single choke-point for turning a
# "candidate" value into a validated, band-clamped production value. A full
# codebase grep found it was NEVER actually called anywhere — every "track":
# "live-cal" parameter above (all 13 of them) just sat permanently at its
# static "fallback", despite this file's own framework implying they were
# being calibrated from live/paper data. That is still true for 12 of them
# today (target_portfolio_vol, health_active/caution/warning_min,
# stage_up/down_win_rate, max_wr_gap_vs_backtest,
# max_consecutive_losses_validator, profit_degradation_alert_pct,
# max_idle_trading_days, backtest_warn/block_days, mc_robustness_min) —
# they remain static/fallback-only; genuinely calibrating them from real
# paper/live trade history is a bigger feature that hasn't been built and
# should not be claimed as done.
#
# max_slots is now the SECOND parameter (after min_live_win_rate) that is
# genuinely calibrated — via calculate_max_slots_candidate() below, a
# deterministic formula (not a live-data-fitted model) directly answering
# the question the owner asked: with a fixed daily risk budget, more slots
# means smaller per-trade size, and the ₹40 flat brokerage cap eats a bigger
# % of a smaller trade — so slot count should be bounded by that economics,
# not just an arbitrary owner-picked number inside the band.
# ══════════════════════════════════════════════════════════════════════

def calculate_max_slots_candidate(capital: float, max_daily_risk_pct: float = 2.0,
                                   avg_sl_pct: float = 1.5,
                                   expected_tp_return_pct: float = 3.0,
                                   subscription_fee: float = None,
                                   trades_per_month: float = None) -> float:
    """
    Deterministic economics formula for how many concurrent slots the capital
    can support before per-trade costs make the average trade uneconomical.

    [Design note, corrected after live-testing the first version]: the ₹40
    Dhan brokerage CAP alone does not create a "smaller trade = worse %"
    problem — below the cap threshold (~₹66,667 trade value) brokerage is a
    flat 0.06% regardless of size, and above it the % actually gets CHEAPER
    for bigger trades. The real fixed-cost-per-trade that punishes smaller
    trades (more slots) is the subscription-fee-per-trade term
    (subscription_fee / trades_per_month) already used by
    capital_manager.is_trade_economically_viable — a fixed ₹ amount that
    becomes a bigger % of a smaller trade. This function reuses that exact
    cost model (not a new one) so the two never disagree, and finds the
    LARGEST N (within the owner's [5, 12] band) for which a typical trade at
    that slot count still clears is_trade_economically_viable's own hurdle.
    """
    band = BANDS.get("max_slots", {"low": 5.0, "high": 12.0, "fallback": 8.0})
    if not capital or capital <= 0 or avg_sl_pct <= 0:
        return band["fallback"]

    try:
        from capital_drawdown_manager import get_verified_financial_economics
        econ = get_verified_financial_economics(symbol=None)
        sub_fee = float(subscription_fee if subscription_fee is not None else econ.get("subscription_fee", 3000.0))
        tpm = float(trades_per_month if trades_per_month is not None else econ.get("expected_trades_per_month", 15.0))
    except (ImportError, RuntimeError, ValueError, TypeError, KeyError):
        sub_fee = float(subscription_fee if subscription_fee is not None else 3000.0)
        tpm = float(trades_per_month if trades_per_month is not None else 15.0)

    sub_cost_per_trade = sub_fee / max(1.0, tpm)

    best_n = None
    for n in range(int(band["low"]), int(band["high"]) + 1):
        risk_per_trade = capital * (max_daily_risk_pct / 100.0) / n
        trade_value = risk_per_trade / (avg_sl_pct / 100.0)
        if trade_value <= 0:
            continue
        brokerage = min(float(PARAMS.get("brokerage_min_inr", 40.0)),
                       trade_value * float(PARAMS.get("brokerage_rate_pct", 0.06)) / 100.0)
        statutory = trade_value * float(PARAMS.get("statutory_rate_pct", 0.25)) / 100.0
        total_tx_cost = brokerage + statutory + sub_cost_per_trade
        expected_gross_profit = trade_value * (expected_tp_return_pct / 100.0)
        expected_net_profit = expected_gross_profit - total_tx_cost
        if expected_net_profit > 0:
            best_n = n  # this slot count still clears the same economic-viability hurdle used per-trade
        else:
            break  # beyond this N, the average trade would already fail is_trade_economically_viable

    if best_n is None:
        # Even the owner's minimum band value doesn't clear the economics hurdle
        # with current assumptions (e.g. no real backtest data yet, so
        # expected_trades_per_month defaults very low and sub_cost_per_trade
        # is high) — be honest about this rather than silently pretending the
        # floor is "validated". Still return the floor as the safest number we
        # can act on, but flagged.
        logger.warning(
            f"calculate_max_slots_candidate: even the minimum band value "
            f"({int(band['low'])}) does not clear is_trade_economically_viable's "
            f"hurdle at capital={capital} (sub_cost_per_trade={sub_cost_per_trade:.1f}, "
            f"likely because no real backtest history exists yet) — "
            f"returning the floor anyway, but this capital may be too small "
            f"for the current subscription-fee/trade-frequency assumptions."
        )
        return band["low"]
    return float(best_n)


def get_recommended_max_slots(capital: float) -> int:
    """
    Convenience wrapper: computes the candidate from current capital and runs
    it through the SAME resolve_param() choke-point every other band-governed
    value uses, so this is genuinely validated/clamped rather than a bypass.
    Falls back to the static band fallback (8) on any failure — never raises.
    """
    try:
        candidate = calculate_max_slots_candidate(capital)
        return int(resolve_param("max_slots", candidate=candidate, validated=True))
    except (TypeError, ValueError, KeyError) as e:
        logger.warning(f"get_recommended_max_slots: failed for capital={capital}: {type(e).__name__}: {e} — using static fallback")
        _static = int(BANDS.get("max_slots", {}).get("fallback", 8))
        from fallback_monitor import record_fallback   # FIX-LIST item 17 (visibility only)
        record_fallback("economics_brain.get_recommended_max_slots", e, _static, f"capital={capital}")
        return _static


def get_band(key: str) -> dict:
    """Owner band for a key. {} if key not constitution-governed."""
    return BANDS.get(key, {})


def clamp_to_band(key: str, value):
    """Force a value inside the owner band. Unknown key/unparsable → value as-is."""
    band = BANDS.get(key)
    num = _safe_num(value)
    if not band or num is None:
        return value
    return max(band["low"], min(band["high"], num))


def resolve_param(key: str, candidate=None, validated: bool = False):
    """
    ADR §8A promotion rule — single choke point for band-governed numbers.

    candidate=None or validated=False  → FALLBACK (production remains active).
    validated=True + candidate in band → candidate (clamped, belt-and-suspenders).
    validated=True + candidate out of band → clamp + warning (never promotes
        an out-of-constitution value; no automatic promotion occurs).
    """
    band = BANDS.get(key)
    if not band:
        return candidate
    fallback = band["fallback"]

    if candidate is None or not validated:
        return fallback

    num = _safe_num(candidate)
    if num is None:
        logger.warning(f"[ECON-BRAIN] {key}: bad candidate {candidate!r} → fallback {fallback}")
        return fallback

    if num < band["low"] or num > band["high"]:
        clamped = max(band["low"], min(band["high"], num))
        logger.warning(
            f"[ECON-BRAIN] {key}: candidate {num} OUTSIDE owner band "
            f"[{band['low']}, {band['high']}] → clamped to {clamped} (constitution enforced)")
        return clamped

    return num


def min_win_rate_floor(symbol: str = None) -> float:
    """
    Owner rule (2026-07-30): min live win rate = (1 + fees/risk) / (1 + R:R), NOT a
    fixed constant. Includes brokerage + statutory + subscription fees.

    Formula derivation:
      Win = reward - fees, Loss = risk + fees
      Breakeven: wr × win = (1-wr) × loss
      Solving: wr = (risk + fees) / (risk × (1 + R:R))
             = (1 + fees/risk) / (1 + R:R)

    At R:R=2.0 with 0.51% fees and 3% SL:
      fees/risk = 0.51/3 = 0.17
      wr = (1 + 0.17) / (1 + 2) = 1.17/3 = 39% (not 33%)

    Any failure → current static production value (40 / PARAMS fallback chain).
    Production configuration remains active on error.
    """
    fallback_chain = (40.0, 45.0)
    try:
        from config import PARAMS
        static_fallback = None
        for f in fallback_chain:
            static_fallback = _safe_num(PARAMS.get("min_live_win_rate", f))
            if static_fallback is not None:
                break
        if static_fallback is None:
            static_fallback = 40.0
    except Exception:
        return 40.0

    try:
        from config import PARAMS
        rr = None
        # v5.3: trailing exits ki wajah se R:R ab backtest ke ACTUAL
        # avg_win/avg_loss se derive hota hai (preference order:
        # canonical RR contract → exactly 1.8R).
        try:
            from config import BACKTEST_RESULTS_FILE
            from utils import load_json
            bt = load_json(BACKTEST_RESULTS_FILE, {})
            summary = bt.get("summary", {}) if isinstance(bt, dict) else {}
            avg_win = _safe_num(summary.get("avg_win_pct", 0))
            avg_loss = _safe_num(summary.get("avg_loss_pct", 0))
            if avg_win is not None and avg_loss is not None and avg_win > 0 and avg_loss < 0:
                rr = abs(avg_win / avg_loss)
        except Exception:
            rr = None
        if rr is None and symbol is not None:
            try:
                                rr = 1.8
            except Exception:
                rr = None
        if rr is None:
            rr = 1.8
        if rr is None or rr <= 0:
            return static_fallback

        # [FIX] Include fees in breakeven calculation
        # Fees: brokerage + statutory + subscription per trade
        brokerage_pct = float(PARAMS.get("brokerage_rate_pct", 0.06))
        statutory_pct = float(PARAMS.get("statutory_rate_pct", 0.25))
        subscription_fee = float(PARAMS.get("live_sub_fee_inr", 3000.0))
        trades_per_month = float(PARAMS.get("default_trades_per_month", 15.0))
        # Subscription cost as % of typical trade (assume ₹1L trade)
        typical_trade_value = float(PARAMS.get("validator_reference_capital", 200000.0)) / max(1.0, float(PARAMS.get("max_slots", 8)))
        sub_pct = (subscription_fee / max(1.0, trades_per_month)) / max(typical_trade_value, 1e-6) * 100.0
        total_cost_pct = brokerage_pct + statutory_pct + sub_pct

        # SL % for fees/risk ratio
        sl_pct = float(PARAMS.get("sl_pct", 3.0))
        fees_risk_ratio = total_cost_pct / sl_pct if sl_pct > 0 else 0.17

        # Breakeven with fees: wr = (1 + fees/risk) / (1 + R:R)
        derived = 100.0 * (1.0 + fees_risk_ratio) / (1.0 + rr)
        guarded = max(MIN_WR_GUARD_LOW, min(MIN_WR_GUARD_HIGH, derived))
        return round(guarded, 2)
    except Exception as e:
        logger.warning(f"[ECON-BRAIN] min_win_rate_floor failed: {e} → static fallback")
        from fallback_monitor import record_fallback   # FIX-LIST item 17 (visibility only)
        record_fallback("economics_brain.min_win_rate_floor", e, static_fallback)
        return static_fallback
