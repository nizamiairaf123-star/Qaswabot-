"""
startup_recovery.py — Cold start + crash recovery handler
FIX-04 + FIX-49

Cold start: no state file → initialize safely
Crash recovery: state file exists → verify vs Dhan holdings
SLA: 60 seconds max recovery time
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)
from utils import load_json, save_json, append_log
from config import AUDIT_LOG_FILE, PORTFOLIO_STATE_FILE
from bot_state_manager import (set_state, activate_reconciliation_hold)

RECOVERY_SLA_SECONDS = 60


async def recover_state_on_boot() -> bool:
    """
    Check if Dhan API has open positions at boot.
    If open positions exist, transition state machine to EXIT_ONLY/RECONCILIATION_HOLD.
    Otherwise treat as fresh start.
    """
    from signal_broadcaster import alert_admin
    try:
        from broker import get_holdings
        holdings = get_holdings()
        open_positions = [h for h in holdings if float(h.get("totalQty", 0)) > 0]
        if open_positions:
            append_log(AUDIT_LOG_FILE, f"RECOVER_STATE: Found {len(open_positions)} open positions on Dhan API at boot")
            # P1-003 [r38 verified fix]: a successful holdings check on THIS
            # boot must not automatically de-escalate a RECONCILIATION_HOLD
            # left over from a PREVIOUS boot's failure — that would be
            # "resume normal trading merely because the process restarted"
            # (this boot succeeding doesn't mean the admin ever reviewed
            # whatever caused the earlier hold). Only /resume (an explicit
            # admin action, existing resume_from_pause()) may clear it.
            from bot_state_manager import get_state as _get_state
            if _get_state() == "RECONCILIATION_HOLD":
                append_log(AUDIT_LOG_FILE,
                           "RECOVER_STATE: RECONCILIATION_HOLD already active from a prior "
                           "boot — staying on hold, NOT auto-transitioning to EXIT_ONLY")
                await alert_admin(
                    f"Startup Recovery: Found {len(open_positions)} open positions on Dhan API, "
                    f"but bot remains in RECONCILIATION_HOLD from a prior failure. "
                    f"Manual /resume required before trading resumes."
                )
            else:
                set_state("EXIT_ONLY", f"Boot recovery: {len(open_positions)} live positions found")
                await alert_admin(f"Startup Recovery: Found {len(open_positions)} open positions on Dhan API. State set to EXIT_ONLY.")
            return True
        else:
            append_log(AUDIT_LOG_FILE, "RECOVER_STATE: No open positions on Dhan API — clean start")
            return False
    except Exception as e:
        # FIX: get_holdings() failing (API/auth/network error) is NOT the
        # same thing as "verified zero holdings" -- previously both paths
        # returned False here, so a failed API call at boot looked
        # identical to a genuinely clean start and the bot would proceed
        # as if positions were confirmed empty. Fail closed instead: alert
        # admin explicitly and hold, don't assume clean.
        append_log(AUDIT_LOG_FILE, f"RECOVER_STATE ERROR: could not verify Dhan holdings at boot -- {type(e).__name__}: {e}")
        from bot_state_manager import activate_reconciliation_hold
        activate_reconciliation_hold(f"Startup: could not verify Dhan holdings ({type(e).__name__}: {e}) -- manual check required before trading resumes")
        await alert_admin(
            "⚠️ STARTUP RECOVERY: Could not verify Dhan holdings at boot "
            f"({type(e).__name__}: {e}).\n\n"
            "Bot placed in RECONCILIATION_HOLD as a precaution -- this is NOT "
            "confirmed as a clean start. Please check Dhan holdings manually "
            "and /resume when verified."
        )
        return False


async def run_startup_recovery():
    """
    Main entry point — called at bot start.
    Returns: True if recovery successful, False if needs admin attention.
    """
    start_time = time.time()
    append_log(AUDIT_LOG_FILE, "STARTUP RECOVERY: Starting...")

    # SEQ registry boot-trace (Rule 14 / QASWA Remix) — additive, observational
    # only; never blocks startup even if this import/call itself fails.
    try:
        from seq_alignment_registry import log_seq_boot_trace
        log_seq_boot_trace(append_log_fn=append_log, audit_log_file=AUDIT_LOG_FILE)
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"STARTUP: SEQ registry boot-trace skipped: {type(e).__name__}: {e}")

    from signal_broadcaster import alert_admin

    # ── Step 0: Token Health Check ──
    try:
        from broker import validate_and_standby
        token_result = validate_and_standby()
        if not token_result["valid"]:
            await alert_admin(
                f"⚠️ [DHAN TOKEN EXPIRED]\n"
                f"{token_result['message']}\n\n"
                f"Bot is in Standby Mode waiting for valid token.\n"
                f"Use /settoken CLIENT_ID ACCESS_TOKEN to update."
            )
            append_log(AUDIT_LOG_FILE, f"STARTUP: Token invalid — {token_result['message']}")
            # Continue with recovery even if token invalid
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"STARTUP: Token check skipped: {e}")

    recovered_ok = await recover_state_on_boot()
    if not recovered_ok:
        append_log(AUDIT_LOG_FILE, "STARTUP RECOVERY WARNING: recover_state_on_boot() did not complete successfully -- check logs for RECOVER_STATE ERROR")

    # Check if state file exists
    state_data = load_json(PORTFOLIO_STATE_FILE, None)

    if state_data is None:
        # Cold start
        await _handle_cold_start()
    else:
        # Crash recovery
        await _handle_crash_recovery(state_data)

    # v5.0 CRASH-WINDOW SAFETY (Tier 1): broker pe place hue orders jo crash ki
    # wajah se track nahi hue — status verify karke adopt/clean karo.
    try:
        from trade_engine import recover_pending_orders
        await asyncio.to_thread(recover_pending_orders)
    except (ImportError, RuntimeError, AttributeError) as e:
        append_log(AUDIT_LOG_FILE, f"STARTUP RECOVERY: crash-pending recovery skipped: {type(e).__name__}: {e}")

    elapsed = round(time.time() - start_time, 1)
    append_log(AUDIT_LOG_FILE, f"STARTUP RECOVERY: Complete in {elapsed}s")

    # SLA check — FIX-49
    if elapsed > RECOVERY_SLA_SECONDS:
        await alert_admin(
            f"Bot slow recovery — {elapsed}s (SLA: {RECOVERY_SLA_SECONDS}s)\n"
            f"Check manually. Market hours may have been missed."
        )

    return True


async def _handle_cold_start():
    """
    No state file = first boot ever.
    Initialize everything safely.
    FIX-04: high_watermark = entry_price, DD = 0
    """
    from signal_broadcaster import alert_admin

    append_log(AUDIT_LOG_FILE, "COLD_START: No state file found — first boot")

    # Initialize empty state
    save_json(PORTFOLIO_STATE_FILE, {"active_trades": {}})

    # Set cold start state
    set_state("COLD_START", "No state file — first boot")

    await alert_admin(
        "COLD START DETECTED\n\n"
        "No previous state found.\n"
        "Bot initialized fresh.\n\n"
        "If this is unexpected (VPS crash), "
        "check Dhan holdings manually before resuming."
    )

    # Transition to PAPER by default
    from config import IS_PAPER_MODE
    if IS_PAPER_MODE:
        set_state("PAPER", "Cold start → Paper mode (default)")
    else:
        set_state("LIVE_STAGED", "Cold start → Live staged")

    append_log(AUDIT_LOG_FILE, "COLD_START: Complete")


async def _handle_crash_recovery(state_data: dict):
    """
    State file exists — verify vs Dhan actual holdings.
    FIX-04: Reconcile, alert on mismatch.
    """
    from signal_broadcaster import alert_admin

    active_trades = state_data.get("active_trades", {})
    append_log(AUDIT_LOG_FILE,
               f"CRASH RECOVERY: {len(active_trades)} open positions in state")

    if not active_trades:
        append_log(AUDIT_LOG_FILE, "CRASH RECOVERY: No open positions — clean start")
        return

    # Fetch Dhan holdings
    try:
        from broker import get_holdings
        holdings     = get_holdings()
        dhan_symbols = {h["tradingSymbol"]: h for h in holdings}
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"CRASH RECOVERY: Cannot fetch holdings — {e}")
        await alert_admin(
            f"Startup recovery failed — cannot fetch Dhan holdings\n"
            f"Error: {e}\n\n"
            f"Bot in RECONCILIATION_HOLD. Manual check required."
        )
        activate_reconciliation_hold()
        return

    mismatches  = []
    broker_exits= []

    for symbol, trade in list(active_trades.items()):
        if symbol not in dhan_symbols:
            # Broker exited during downtime (GTT triggered)
            broker_exits.append(symbol)
            append_log(AUDIT_LOG_FILE,
                       f"CRASH RECOVERY: {symbol} — broker exited during downtime")

            # Clean local state
            from capital_manager import release_trade
            from forever_order_manager import close_forever_orders, get_sl
            from trade_logger import log_trade_exit

            try:
                close_forever_orders(symbol)
            except (ImportError, RuntimeError, ValueError) as e:
                logger.warning(f"run_startup_recovery: Close forever orders failed for {symbol}: {type(e).__name__}: {e}")

            # FIX: the real fill price is unknown (broker exited during bot
            # downtime), but recording 0.0 here previously caused
            # trade_logger.log_trade_exit() to compute a fake ~-100% P&L
            # (gross_pnl = (0 - entry_price) * qty), corrupting day_pnl,
            # drawdown, and win-rate stats used by the live safety system.
            # Use the position's strict SL price (candle-low at entry, the
            # most likely trigger for an unattended exit) as the closest
            # available approximation, falling back to entry price (neutral,
            # 0% impact) if no SL state exists. This is still an
            # approximation -- the admin alert below explicitly calls out
            # manual verification against Dhan's actual trade book.
            approx_exit_price = trade.get("entry_price", 0.0)
            try:
                sl_price = float(get_sl(symbol) or 0)
                if sl_price > 0:
                    approx_exit_price = sl_price
            except (TypeError, ValueError) as e:
                logger.warning(f"run_startup_recovery: SL lookup failed for {symbol}: {type(e).__name__}: {e}")

            release_trade(symbol)
            log_trade_exit(symbol, approx_exit_price,
                           "Position exited by broker during bot downtime (GTT triggered) "
                           "-- exit price APPROXIMATED from last known trail/entry price, "
                           "verify against Dhan trade book")

        else:
            # Position still open — check qty
            dhan_qty = dhan_symbols[symbol].get("totalQty", 0)
            bot_qty  = trade.get("qty", 0)

            # FIX-04: Reset watermark data from trade
            # high_watermark = entry_price (conservative reset)
            from stock_mode_manager import update_watermark
            entry_price = trade.get("entry_price", 0)
            if entry_price > 0:
                update_watermark(symbol, entry_price)
                append_log(AUDIT_LOG_FILE,
                           f"CRASH RECOVERY: {symbol} watermark reset to entry={entry_price}")

            if dhan_qty != bot_qty:
                mismatches.append(
                    f"{symbol}: Bot={bot_qty}, Dhan={dhan_qty}"
                )

    # Alert summary
    if broker_exits:
        await alert_admin(
            f"Startup Recovery\n\n"
            f"Broker exited {len(broker_exits)} positions during downtime:\n"
            + "\n".join(broker_exits) +
            f"\n\nLocal state cleaned. Check Dhan for exact exit prices."
        )

    if mismatches:
        # FIX-11: DO NOT auto-correct qty mismatch
        await alert_admin(
            f"QTY MISMATCH DETECTED\n\n"
            + "\n".join(mismatches) +
            f"\n\nBot in RECONCILIATION_HOLD.\n"
            f"DO NOT auto-correct — manual review required.\n"
            f"Use /resume after verifying."
        )
        activate_reconciliation_hold()
        return

    # All good — resume monitoring
    from trade_engine import monitor_positions
    await monitor_positions()
    append_log(AUDIT_LOG_FILE, "CRASH RECOVERY: All positions verified — monitoring resumed")
