"""
sharia_manager.py — Zakat + Mid-Trade Reclassification Policy (v3.2 Custom)
[Method: Custom Core Business Halal (100%) + Non-Muslim Board 100% — DESIGN: AIRAF NIZAMI]
[Standard: Zakat 2.5% on zakatable wealth above Nisab 87.48g — classical fiqh]

FIX-15 (Updated v3.2): Mid-Trade Reclassification Policy — no panic exit, natural TP1/SL exit
- Running Trades: DO NOT TOUCH, let exit naturally via TP1/SL
- Post-Exit: Block NEW BUY entries (haram_pending)
- Future Re-Match: If monthly update confirms eligible again, restore automatically

No purification / financial-ratio screening mechanism — eligibility is strictly Core
Business Halal + 100% Non-Muslim Board (owner's stated custom scope). Zakat is a
separate, unrelated 2.5%-above-Nisab calculator retained below.
"""

import logging
from utils import load_json, save_json

logger = logging.getLogger(__name__)

NISAB_GOLD_GRAMS = 87.48  # Hanafi Nisab


# ─────────────────────────────────────────────
# v3.2 MID-TRADE RECLASSIFICATION POLICY [DESIGN: AIRAF NIZAMI]
# ─────────────────────────────────────────────

def handle_haram_reclassification(symbol: str):
    """
    v3.2 Mid-Trade Reclassification Policy — [DESIGN: AIRAF NIZAMI]

    When a stock gets reclassified (fails core_business_halal OR non_muslim_board)
    during monthly_board_universe_update_job:

    - Running Trades: DO NOT TOUCH the running trade (no panic exit, no forced close).
      Let it exit naturally via TP1 or SL targets (3-layer GTT).
    - Post-Exit: After the trade closes (handled by trade_engine calling clear_haram_pending
      on exit? Actually we mark pending now, and clear_haram_pending is called after exit
      to keep blocked state until re-validation). Mark in ineligible/blocked category
      so NEW BUY entries are blocked post-exit.
    - Future Criteria Re-Match: If future monthly update confirms stock meets criteria again,
      automatically restore it to Halal universe for fresh buys (by removing from haram_pending
      and ensuring CUSTOM_UNIVERSE_FINAL.csv includes it again).

    This function is called during monthly universe update when a previously eligible
    symbol is now ineligible.

    Policy (Sharia-compliant):
    - Forced instant exit NOT required — avoids unnecessary loss
    - No NEW entries allowed immediately (via _mark_haram_pending_exit)
    - Existing position exits naturally via TP1/SL (broker GTT)
    - Admin + subscriber alerted
    """
    from capital_manager import get_active_trades
    from signal_broadcaster import alert_admin, broadcast_to_all
    import asyncio

    try:
        active = get_active_trades()
    except Exception as e:
        logger.warning(f"handle_haram_reclassification: get_active_trades failed for {symbol}: {e} — proceeding to block new entries anyway")
        active = []

    # Always block new entries immediately (core of policy)
    _mark_haram_pending_exit(symbol)

    if symbol not in active:
        # No open position — just block new entries, no alert needed for running trade
        logger.info(f"handle_haram_reclassification: {symbol} reclassified, no open position — new BUY blocked")
        return

    # Open position exists — DO NOT panic exit, let it exit naturally
    _admin_msg = (
        f"HARAM/BOARD RECLASSIFICATION (v3.2)\n\n"
        f"Stock: {symbol}\n"
        f"Status: Open position exists\n\n"
        f"Policy Action (Mid-Trade Reclassification):\n"
        f"- Running trade: DO NOT TOUCH — will exit naturally via TP1/SL (GTT)\n"
        f"- New BUY entries: BLOCKED post-exit (ineligible category)\n"
        f"- Forced exit: NOT triggered (avoids unnecessary loss)\n"
        f"- Future: If monthly update re-confirms eligible (core halal + 100% non-Muslim board + price>100 + liquid), "
        f"will be auto-restored to Halal universe\n\n"
        f"Criteria: Core Business 100% Halal + 100% Non-Muslim Board + Price>100 + Liquid + strict NSE-EQ\n"
        f"[DESIGN: AIRAF NIZAMI]"
    )
    _broadcast_msg = (
        f"Stock Update (v3.2)\n\n"
        f"A stock has been reclassified during monthly board update.\n"
        f"Existing position will exit naturally via TP1/SL.\n"
        f"No new entries will be taken until re-validated.\n"
    )
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(alert_admin(_admin_msg))
        loop.create_task(broadcast_to_all(_broadcast_msg))
    except RuntimeError:
        # No running loop (sync/scheduler context) — deliver via sync wrappers
        try:
            from signal_broadcaster import alert_admin_sync, broadcast_to_all_sync
            alert_admin_sync(_admin_msg)
            broadcast_to_all_sync(_broadcast_msg)
        except Exception as sync_e:
            logger.warning(f"handle_haram_reclassification: failed to send alerts for {symbol}: {sync_e}")


def _mark_haram_pending_exit(symbol: str):
    """Mark stock as haram/board-ineligible — no new entries (retained per spec)."""
    data = load_json("data/haram_pending.json", {"symbols": []})
    if symbol not in data["symbols"]:
        data["symbols"].append(symbol)
        logger.info(f"_mark_haram_pending_exit: Marked {symbol} as pending blocked (new BUY blocked post-exit)")
    save_json("data/haram_pending.json", data)


def is_haram_pending_exit(symbol: str) -> bool:
    """Check if symbol is pending exit due to haram/board reclassification (retained per spec)."""
    data = load_json("data/haram_pending.json", {"symbols": []})
    return symbol in data["symbols"]


def clear_haram_pending(symbol: str):
    """
    Called after position exits — clear haram pending flag?
    v3.2 Update: Per Mid-Trade Policy, post-exit we KEEP blocked until future re-validation.
    However this function is retained per spec and can be used when monthly update
    re-confirms eligibility (future criteria re-match → restore).
    For now, it removes from pending list when called (e.g., after natural exit + re-validation).
    """
    data = load_json("data/haram_pending.json", {"symbols": []})
    if symbol in data["symbols"]:
        data["symbols"].remove(symbol)
        logger.info(f"clear_haram_pending: Cleared {symbol} from pending — eligible for re-validation in next monthly update")
    save_json("data/haram_pending.json", data)


# ─────────────────────────────────────────────
# ZAKAT — Retained universal 2.5% calculator above Nisab
# ─────────────────────────────────────────────

def calculate_zakat(portfolio_value: float,
                     gold_price_per_gram: float) -> str:
    """
    Zakat Calculator — Retained as universal 2.5% calculator on Zakatable wealth above Nisab (87.48g Gold)
    Per spec v3.2: Retain as universal calculator
    """
    nisab_value = NISAB_GOLD_GRAMS * gold_price_per_gram

    if portfolio_value < nisab_value:
        return (
            f"Zakat Calculator (v3.2 Universal)\n"
            f"Portfolio (incl. open positions): Rs.{portfolio_value:,.2f}\n"
            f"Nisab ({NISAB_GOLD_GRAMS}g gold): Rs.{nisab_value:,.2f}\n\n"
            f"Below Nisab — Zakat not obligatory.\n\n"
            f"Active Universe: 100% Core Business Halal + 100% Non-Muslim Board\n"
            f"Note: Calculate on your Islamic lunar year anniversary."
        )
    else:
        zakat = portfolio_value * 0.025
        return (
            f"Zakat Calculator (v3.2 Universal)\n"
            f"Portfolio (incl. open positions): Rs.{portfolio_value:,.2f}\n"
            f"Nisab ({NISAB_GOLD_GRAMS}g gold): Rs.{nisab_value:,.2f}\n\n"
            f"Above Nisab — Zakat due!\n"
            f"Zakat (2.5%): Rs.{zakat:,.2f}\n\n"
            f"Active Universe: 100% Core Business Halal + 100% Non-Muslim Board\n"
            f"Note: Calculate on your Islamic lunar year anniversary.\n"
            f"Consult your scholar for exact calculation."
        )


def save_zakat_date(chat_id: int, lunar_date: str):
    """Store subscriber's zakat anniversary date."""
    data = load_json("data/zakat_dates.json", {})
    data[str(chat_id)] = lunar_date
    save_json("data/zakat_dates.json", data)


def get_zakat_date(chat_id: int) -> str:
    data = load_json("data/zakat_dates.json", {})
    return data.get(str(chat_id), "Not set")


