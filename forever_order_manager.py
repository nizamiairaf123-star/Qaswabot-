"""
forever_order_manager.py — Strict, single-layer exit management.

[OVERRIDE 1 — user-authorized architectural pivot] Previously this was a
3-layer system (in-memory trailing SL + a broker-side "trail SL" GTT order
that moved up with price + a broker-side "hard SL" GTT order that never
moved). Per the pivot: SL is now STRICTLY the low of the entry candle,
fixed for the life of the trade — there is no trailing-stop concept at all
anymore. This file now manages exactly ONE broker-side GTT stop-loss order
per position, placed once at entry and never modified.

The retry-once + loud-admin-alert-on-failure safety pattern from the old
3-layer system is kept (it protects against a silently-unprotected
position regardless of whether there's 1 or 2 orders).
"""

from broker import place_forever_order, cancel_forever_order, modify_forever_order
from utils import load_json, save_json, append_log
from config import AUDIT_LOG_FILE

FOREVER_STATE_FILE = "data/forever_orders.json"


def _load() -> dict:
    return load_json(FOREVER_STATE_FILE, {})


def _save(data: dict):
    save_json(FOREVER_STATE_FILE, data)


# ─────────────────────────────────────────────
# SETUP — Called at trade entry
# ─────────────────────────────────────────────

def setup_forever_orders(symbol: str, security_id: str, qty: int,
                          entry_price: float, sl_price: float) -> dict:
    """
    v5.0 — 3-LAYER EXIT PROTECTION (owner rule: SL FIXED, koi trailing nahi)

    L1: Broker GTT at strict candle-low SL (primary; bot down ho to bhi active).
    L2: Agar L1 REJECT ho jaye → fallback GTT SL − gtt_layer2_offset_pct%
        (fixed bhi; sirf tab lagta hai jab L1 nahi laga).
    L3: Bot ka 3-min hard-SL monitor + daily re-arm job + reconciliation +
        loud admin alert (hamesha active).

    Retries + loud admin alert on failure — position kabhi silently
    unprotected nahi rehti (crash/VPS-down par bhi L1/L2 broker pe hai).
    """
    from config import PARAMS
    offset_pct = float(PARAMS.get("gtt_layer2_offset_pct", 0.2) or 0.0)

    def _place_with_retry(trigger_price, label):
        result = place_forever_order(security_id=security_id, symbol=symbol,
                                      qty=qty, trigger_price=trigger_price,
                                      order_label=label)
        if not result.get("success"):
            append_log(AUDIT_LOG_FILE,
                       f"FOREVER ORDER FAILED (retry 1): {symbol} [{label}] {result.get('message')}")
            result = place_forever_order(security_id=security_id, symbol=symbol,
                                          qty=qty, trigger_price=trigger_price,
                                          order_label=label)
        return result

    # L1 — strict SL
    sl_result = _place_with_retry(sl_price, "STRICT_SL")
    sl_ok = bool(sl_result.get("success")) and sl_result.get("forever_id")
    layer = 1

    # L2 — fallback (sirf jab L1 fail)
    if not sl_ok:
        l2_price = round(sl_price * (1.0 - offset_pct / 100.0), 2)
        append_log(AUDIT_LOG_FILE,
                   f"FOREVER L1 FAILED → L2 fallback: {symbol} trigger={l2_price} (SL−{offset_pct}%)")
        sl_result = _place_with_retry(l2_price, "STRICT_SL_L2")
        sl_ok = bool(sl_result.get("success")) and sl_result.get("forever_id")
        layer = 2

    data = _load()
    data[symbol] = {
        "security_id": security_id,
        "qty": qty,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "sl_forever_id": sl_result.get("forever_id"),
        "sl_failed": not sl_ok,
        "layer": layer,
    }
    _save(data)

    if sl_ok:
        append_log(AUDIT_LOG_FILE, f"STRICT SL SET: {symbol} layer={layer} (candle-low SL, non-flexible)")
        return {"success": True, "layer": layer}

    append_log(AUDIT_LOG_FILE,
               f"FOREVER ORDER SETUP FAILED: {symbol} -- position has NO broker-side protection (L3 monitor-only)")
    try:
        import asyncio
        from signal_broadcaster import alert_admin
        msg = (
            f"🚨 URGENT: {symbol} entry has NO broker-side GTT stop-loss protection (L1+L2 dono fail).\n\n"
            f"Only the bot's in-memory monitoring is protecting this position. "
            f"If the bot restarts or loses connectivity, this position is unprotected.\n\n"
            f"Check Dhan manually and consider placing the SL order manually "
            f"(at {sl_price}) or exiting the position."
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(alert_admin(msg))
        except RuntimeError:
            from signal_broadcaster import alert_admin_sync
            alert_admin_sync(msg)
    except (ImportError, RuntimeError) as e:
        append_log(AUDIT_LOG_FILE, f"FOREVER ORDER ALERT FAILED: {symbol} {type(e).__name__}: {e}")

    return {"success": False}


# ─────────────────────────────────────────────
# CLOSE — Called when position exits
# ─────────────────────────────────────────────

def close_forever_orders(symbol: str):
    """
    Position closed → cancel the SL order. Called after confirmed exit
    (bot-triggered TP1 hit, or broker-triggered SL hit).

    Retries once, loud admin alert if still failing, and keeps the local
    record (flagged as pending-cancel) instead of deleting it, so a later
    reconcile pass or the admin can still find and clean up an orphaned
    live order on the real Dhan account.
    """
    data = _load()
    state = data.get(symbol)
    if not state:
        return

    sl_id = state.get("sl_forever_id")

    def _cancel_with_retry(forever_id, label):
        if not forever_id:
            return True  # nothing to cancel
        ok = cancel_forever_order(forever_id, symbol)
        if not ok:
            append_log(AUDIT_LOG_FILE,
                       f"FOREVER CANCEL FAILED (retry 1): {symbol} [{label}] id={forever_id}")
            ok = cancel_forever_order(forever_id, symbol)
        return ok

    sl_ok = _cancel_with_retry(sl_id, "STRICT_SL")

    if sl_ok:
        data.pop(symbol, None)
        _save(data)
        append_log(AUDIT_LOG_FILE, f"FOREVER ORDER CLOSED: {symbol}")
        return

    state["pending_cancel_failed"] = True
    data[symbol] = state
    _save(data)
    append_log(AUDIT_LOG_FILE,
               f"FOREVER ORDER CLOSE INCOMPLETE: {symbol} -- SL order may still be LIVE on the real Dhan account")
    try:
        import asyncio
        from signal_broadcaster import alert_admin
        msg = (
            f"🚨 URGENT: {symbol} exit could NOT cancel the broker-side SL order.\n\n"
            f"This stop-loss order may still be LIVE on the real Dhan account even "
            f"though the bot considers this position closed.\n\n"
            f"Check Dhan manually and cancel the order if still present."
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(alert_admin(msg))
        except RuntimeError:
            from signal_broadcaster import alert_admin_sync
            alert_admin_sync(msg)
    except (ImportError, RuntimeError) as e:
        append_log(AUDIT_LOG_FILE, f"FOREVER ORDER CLOSE ALERT FAILED: {symbol} {type(e).__name__}: {e}")


# ─────────────────────────────────────────────
# STATUS
# ─────────────────────────────────────────────

def get_forever_state(symbol: str) -> dict:
    return _load().get(symbol, {})


def get_sl(symbol: str) -> float:
    """Strict SL price for this position (candle-low, fixed — never trails)."""
    return get_forever_state(symbol).get("sl_price", 0)


# ═════════════════════════════════════════════════════════════════════════
# v5.0 — L3: DAILY RE-ARM (missing/expired GTT dobara lagta hai)
# ═════════════════════════════════════════════════════════════════════════
def rearm_gtt_missing() -> dict:
    """
    Daily job (pre-market): jinke paas GTT nahi hai (sl_failed ya id missing,
    ya kal ka GTT expire ho gaya) unke liye dobara placement attempt.
    Fixed SL hi rehta hai — koi trailing nahi. Returns {symbol: result}.
    """
    from config import PARAMS
    results = {}
    data = _load()
    for symbol, state in list(data.items()):
        try:
            sl_id = state.get("sl_forever_id")
            needs_rearm = bool(state.get("sl_failed")) or not sl_id
            if not needs_rearm:
                continue
            sl_price = float(state.get("sl_price") or 0)
            qty = int(state.get("qty") or 0)
            security_id = state.get("security_id")
            if sl_price <= 0 or qty <= 0 or not security_id:
                continue
            offset_pct = float(PARAMS.get("gtt_layer2_offset_pct", 0.2) or 0.0)
            result = place_forever_order(security_id=security_id, symbol=symbol,
                                         qty=qty, trigger_price=sl_price,
                                         order_label="STRICT_SL_REARM")
            if not result.get("success"):
                l2_price = round(sl_price * (1.0 - offset_pct / 100.0), 2)
                result = place_forever_order(security_id=security_id, symbol=symbol,
                                             qty=qty, trigger_price=l2_price,
                                             order_label="STRICT_SL_L2_REARM")
            state["sl_forever_id"] = result.get("forever_id")
            state["sl_failed"] = not (result.get("success") and result.get("forever_id"))
            results[symbol] = "OK" if not state["sl_failed"] else "FAILED"
            append_log(AUDIT_LOG_FILE, f"GTT RE-ARM {symbol}: {results[symbol]}")
        except Exception as e:
            results[symbol] = f"ERROR {type(e).__name__}"
    _save(data)
    if results:
        append_log(AUDIT_LOG_FILE, f"GTT RE-ARM SUMMARY: {results}")
    return results


# ═════════════════════════════════════════════════════════════════════════
# v5.3 — TRAIL FOLLOW (robust trailing: GTT broker-side bhi trail ke saath)
# ═════════════════════════════════════════════════════════════════════════
def update_trail_sl(symbol: str, new_sl: float) -> dict:
    """
    Trail upar gaya → broker-side GTT trigger bhi upar karo (VPS crash ho
    to bhi protection trail ke saath rahe). Floor SL (entry candle-low)
    KABHI nahi ghat-ta — new_sl hamesha >= previous. Modify fail → loud
    alert (purana GTT bhi protection hai — sirf trail lock miss hoga).
    """
    from config import PARAMS
    data = _load()
    state = data.get(symbol)
    if not state:
        return {"success": False, "reason": "no_state"}

    cur = float(state.get("trail_sl") or state.get("sl_price") or 0)
    new_sl = float(new_sl)
    if new_sl <= cur:
        return {"success": True, "reason": "no_change"}
    # GTT modify sirf meaningful move pe (API cost control) — trail_gtt_update_min_pct
    min_pct = float(PARAMS.get("trail_gtt_update_min_pct", 0.1))
    if cur > 0 and (new_sl - cur) / cur * 100.0 < min_pct:
        return {"success": True, "reason": "below_update_threshold"}

    sl_id = state.get("sl_forever_id")
    if not sl_id:
        return {"success": False, "reason": "no_gtt_id"}

    ok = modify_forever_order(str(sl_id), symbol, round(new_sl, 2), "TRAIL_FOLLOW")
    if ok:
        state["trail_sl"] = round(new_sl, 2)
        state["sl_price"] = float(state.get("sl_price") or state.get("trail_sl"))  # floor preserved
        data[symbol] = state
        _save(data)
        append_log(AUDIT_LOG_FILE, f"TRAIL FOLLOW: {symbol} GTT trigger -> {round(new_sl, 2)} (floor intact)")
        return {"success": True, "reason": "modified"}
    else:
        state["trail_modify_failed"] = True
        data[symbol] = state
        _save(data)
        append_log(AUDIT_LOG_FILE, f"TRAIL FOLLOW FAILED: {symbol} -> {new_sl} (old GTT still active)")
        try:
            from signal_broadcaster import alert_admin_sync
            alert_admin_sync(f"⚠️ Trail follow failed for {symbol} — broker GTT purani trigger pe hai (protection active, sirf trail lock miss).")
        except (ImportError, RuntimeError) as e:
            append_log(AUDIT_LOG_FILE, f"TRAIL FOLLOW ALERT FAILED: {e}")
        return {"success": False, "reason": "modify_failed"}
