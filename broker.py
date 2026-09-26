"""
broker.py — Dhan API wrapper
FIX-01: Token expiry wrapper — TOKEN_INVALID_PAUSE state
FIX-10: Minimum qty check
FIX-40: Order rejection handling with categorization
FIX-47: Heartbeat for network partition detection
[AUDIT FIX 2026-08-31] FIX-52: dhanhq SDK has no confirmed default
timeout (its internals aren't available to inspect here) — a network
stall on a blocking SDK call could hang a thread-pool worker
indefinitely instead of failing fast like the rest of this codebase
does. call_dhan_with_timeout() below enforces a hard deadline on any
blocking Dhan call regardless of the SDK's own behavior. Applied to
the two highest-value call sites this pass: live order placement
(place_order) and boot-time holdings verification (startup_recovery.py
via get_holdings) — other call sites can be wrapped the same way later.
"""

import logging
import time
import asyncio
import concurrent.futures
from config import (TOKEN_FILE, PARAMS, ORDER_SEGMENT, ORDER_PRODUCT,
                    ORDER_TYPE, ENTRY_ORDER_TYPE, AUDIT_LOG_FILE)
from utils import load_json, save_json, now_ist, append_log

logger = logging.getLogger(__name__)

def _create_dhan_client(*args, **kwargs):
    from dhan_client import create_dhan_client
    return create_dhan_client(*args, **kwargs)


_dhan_instance = None
_DHAN_CALL_TIMEOUT_SECONDS = 15
_dhan_call_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="dhan_call"
)


def call_dhan_with_timeout(fn, *args, timeout: float = _DHAN_CALL_TIMEOUT_SECONDS, **kwargs):
    """
    Run a blocking Dhan SDK call with a hard timeout, regardless of
    whatever (unconfirmed) timeout the SDK uses internally. Raises
    concurrent.futures.TimeoutError if the call doesn't return in time
    — callers should treat that the same as any other RETRYABLE network
    error (it already matches the "timeout"/"network" keywords in
    RETRYABLE_ERRORS below).
    """
    future = _dhan_call_executor.submit(fn, *args, **kwargs)
    return future.result(timeout=timeout)

COPY_LEDGER_FILE = "data/copy_trades.json"

# ─────────────────────────────────────────────
# FIX-40: Rejection code categories
# ─────────────────────────────────────────────

RETRYABLE_ERRORS = [
    "timeout", "network", "server error", "temporarily",
    "try again", "overloaded", "rate limit",
]

PERMANENT_ERRORS = [
    "price band", "circuit", "invalid quantity", "insufficient",
    "account blocked", "not authorized", "invalid symbol",
    "trading suspended", "delisted",
]

MARKET_CLOSED_ERRORS = [
    "market closed", "outside trading hours", "pre-open", "post-closing", "after market hours"
]


def _categorize_rejection(reason: str) -> str:
    reason_lower = reason.lower()
    if any(e in reason_lower for e in MARKET_CLOSED_ERRORS):
        return "MARKET_CLOSED"
    if any(e in reason_lower for e in RETRYABLE_ERRORS):
        return "RETRYABLE"
    if any(e in reason_lower for e in PERMANENT_ERRORS):
        return "PERMANENT"
    return "UNKNOWN"


# ─────────────────────────────────────────────
# TOKEN MANAGEMENT
# ─────────────────────────────────────────────

def get_dhan():
    """Lazy singleton — FIX-01: raises clear error if token missing."""
    global _dhan_instance
    token_data = load_json(TOKEN_FILE)
    if not token_data:
        # FIX-01: Activate TOKEN_INVALID_PAUSE state
        try:
            from bot_state_manager import activate_token_pause
            activate_token_pause("Token file missing")
        except (ImportError, RuntimeError, AttributeError) as e:
            logger.warning(f"get_dhan: Failed to activate token pause: {type(e).__name__}: {e}")
        raise ValueError("Dhan token not found. Admin must /settoken first.")
    from crypto_utils import decrypt
    access_token = token_data.get("access_token") or decrypt(token_data.get("access_token_enc", ""))
    _dhan_instance = _create_dhan_client(token_data["client_id"], access_token)
    return _dhan_instance


def update_token(client_id: str, access_token: str):
    """Save Dhan token with encryption (Industry Standard)."""
    from crypto_utils import encrypt
    save_json(TOKEN_FILE, {
        "client_id": client_id,
        "access_token_enc": encrypt(access_token),  # Encrypted
        "updated_at": now_ist().isoformat()
    })
    global _dhan_instance
    _dhan_instance = None
    # Resume from token pause
    try:
        from bot_state_manager import get_state, resume_from_pause
        if get_state() == "TOKEN_INVALID_PAUSE":
            resume_from_pause()
    except (ImportError, RuntimeError, AttributeError) as e:
        logger.warning(f"update_token: Failed to resume from pause: {type(e).__name__}: {e}")


def check_admin_token() -> bool:
    """Lightweight check: is a Dhan token configured at all (no live API call).

    Used by admin commands (/backtest, /optimize) that need a token to exist
    before running, without incurring an API round-trip on every invocation.
    """
    token_data = load_json(TOKEN_FILE)
    return bool(token_data)


def is_token_valid() -> bool:
    try:
        dhan   = get_dhan()
        result = dhan.get_fund_limits()
        if result is not None:
            from utils import record_heartbeat_success
            record_heartbeat_success()
            return True
        return False
    except Exception as e:
        from utils import record_heartbeat_failure
        record_heartbeat_failure()
        # FIX-01: Token invalid → pause state
        if "token" in str(e).lower() or "unauthorized" in str(e).lower():
            try:
                from bot_state_manager import activate_token_pause
                activate_token_pause(str(e))
            except (ImportError, RuntimeError, AttributeError) as pause_err:
                logger.warning(f"is_token_valid: Failed to activate token pause: {type(pause_err).__name__}: {pause_err}")
        return False


def check_token_expiry() -> dict:
    """
    Check token expiry status and return details.
    Returns: {valid: bool, message: str, action: str}
    """
    token_data = load_json(TOKEN_FILE)
    if not token_data:
        return {
            "valid": False,
            "message": "No token found",
            "action": "Use /settoken CLIENT_ID ACCESS_TOKEN"
        }
    
    updated_at = token_data.get("updated_at")
    if updated_at:
        from datetime import datetime
        try:
            token_time = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
            now = now_ist().replace(tzinfo=None)
            hours_old = (now - token_time.replace(tzinfo=None)).total_seconds() / 3600
            
            if hours_old > 24:
                return {
                    "valid": False,
                    "message": f"Token is {hours_old:.0f} hours old (expired)",
                    "action": "Use /settoken CLIENT_ID ACCESS_TOKEN"
                }
            elif hours_old > 20:
                return {
                    "valid": True,
                    "message": f"Token is {hours_old:.0f} hours old (expiring soon)",
                    "action": "Consider refreshing token"
                }
            else:
                return {
                    "valid": True,
                    "message": f"Token is {hours_old:.0f} hours old (valid)",
                    "action": "No action needed"
                }
        except Exception:
            pass
    
    return {
        "valid": is_token_valid(),
        "message": "Token status unknown",
        "action": "Use /settoken to refresh"
    }


def validate_and_standby() -> dict:
    """
    Startup token validation with standby mode.
    Returns: {state: str, message: str, valid: bool}
    """
    from dhan_client import validate_token_health
    from bot_state_manager import set_state, get_state
    
    is_valid, message, data = validate_token_health()
    
    if is_valid:
        # Token valid — check if we were in standby
        if get_state() == "STANDBY_TOKEN_REQUIRED":
            from bot_state_manager import resume_from_pause
            resume_from_pause()
        return {"state": "READY", "message": message, "valid": True}
    else:
        # Token invalid — enter standby
        try:
            set_state("STANDBY_TOKEN_REQUIRED", message)
        except Exception:
            pass
        
        logger.warning(f"[DHAN TOKEN EXPIRED] {message}")
        return {"state": "STANDBY_TOKEN_REQUIRED", "message": message, "valid": False}


def reload_token() -> dict:
    """
    Reload token from .env and re-validate.
    Used when admin updates token without restarting bot.
    Returns: {success: bool, message: str}
    """
    global _dhan_instance
    
    try:
        # Clear cached instance
        _dhan_instance = None
        
        # Re-validate
        result = validate_and_standby()
        
        if result["valid"]:
            return {"success": True, "message": f"Token reloaded: {result['message']}"}
        else:
            return {"success": False, "message": f"Token still invalid: {result['message']}"}
    except Exception as e:
        return {"success": False, "message": f"Reload failed: {e}"}


# ─────────────────────────────────────────────
# FUND LIMITS
# ─────────────────────────────────────────────

def get_available_balance() -> float:
    try:
        dhan   = get_dhan()
        result = dhan.get_fund_limits()
        return float(result.get("availabelBalance", 0))
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"BROKER ERROR get_balance: {e}")
        return 0.0


def get_available_balance_or_none():
    """
    AUDIT FIX (fail-open family): same fetch as get_available_balance(), but
    signals a failed fetch explicitly as None instead of masking it as 0.0.
    0.0 is a legitimate real balance and must stay distinguishable from
    "could not verify balance" for any safety-critical caller (daily loss
    limit, heartbeat/network-partition detection) that needs to fail CLOSED
    on a fetch failure rather than silently treating it as a safe value.
    get_available_balance() itself is left unchanged for its other callers.
    """
    try:
        dhan   = get_dhan()
        result = dhan.get_fund_limits()
        return float(result.get("availabelBalance", 0))
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"BROKER ERROR get_balance (safe-variant, signaling failure): {e}")
        return None


# ─────────────────────────────────────────────
# ORDER PLACEMENT
# FIX-10: Minimum qty check
# FIX-40: Rejection categorization
# ─────────────────────────────────────────────

def _live_order_session_gate(symbol: str, qty: int, order_type: str,
                             transaction_type: str) -> dict:
    """
    Owner freeze (CNC swing, not MIS):
    - Product type MUST be CNC (delivery). MIS/intraday product never allowed.
    - Dhan AMO does not support MARKET. Buy + exit only 09:15-15:30 IST.
    Overnight SL protection = GTT forever order (separate path), not AMO.
    Returns {} if allowed, otherwise a failed place_order payload.
    """
    product = str(ORDER_PRODUCT or "").strip().upper()
    if product != "CNC":
        append_log(AUDIT_LOG_FILE,
                   f"ORDER BLOCKED NOT_CNC: {transaction_type} {symbol} qty={qty} "
                   f"product={ORDER_PRODUCT} — swing bot CNC-only (no MIS)")
        return {
            "success": False,
            "order_id": None,
            "message": f"Only CNC product allowed (got {ORDER_PRODUCT}). No MIS.",
            "rejection_type": "PERMANENT",
            "skip_reason": "NOT_CNC",
        }

    from utils import is_market_open
    if not is_market_open():
        otype = order_type or ORDER_TYPE
        append_log(AUDIT_LOG_FILE,
                   f"ORDER BLOCKED MARKET_CLOSED: {transaction_type} {symbol} "
                   f"qty={qty} type={otype} — Dhan AMO market nahi; "
                   f"CNC buy/exit sirf 09:15-15:30 IST")
        return {
            "success": False,
            "order_id": None,
            "message": ("Market closed — Dhan AMO does not support market orders; "
                        "CNC buy/exit only 09:15-15:30 IST"),
            "rejection_type": "MARKET_CLOSED",
            "skip_reason": "MARKET_CLOSED",
        }
    return {}


def place_order(security_id: str, symbol: str, qty: int,
                order_type: str = None, price: float = 0,
                transaction_type: str = "BUY") -> dict:
    """
    Place CNC order on Dhan.
    Returns: {success, order_id, status, message}

    Owner: LIMIT CNC entry at bot price; MARKET CNC exit; long-only.
    Real orders are refused when the market is closed (Dhan AMO ≠ MARKET).
    """
    # PAPER MODE — simulate order
    from bot_state_manager import is_real_orders
    if not is_real_orders():
        fake_id = f"PAPER-{symbol}-{transaction_type}-{qty}"
        append_log(AUDIT_LOG_FILE,
                   f"[PAPER] ORDER: {transaction_type} {symbol} qty={qty} fake_id={fake_id}")
        return {"success": True, "order_id": fake_id, "raw": {"paper": True}}

    blocked = _live_order_session_gate(symbol, qty, order_type, transaction_type)
    if blocked:
        return blocked

    # FIX-10: Minimum qty check
    if qty < 1:
        append_log(AUDIT_LOG_FILE,
                   f"ORDER SKIP: {symbol} qty={qty} < 1 — insufficient capital")
        return {
            "success": False,
            "order_id": None,
            "message": f"Capital insufficient for {symbol}. Qty < 1.",
            "skip_reason": "MIN_QTY"
        }

    try:
        dhan  = get_dhan()
        otype = order_type or ORDER_TYPE
        result = call_dhan_with_timeout(
            dhan.place_order,
            security_id=security_id,
            exchange_segment=ORDER_SEGMENT,
            transaction_type=transaction_type,
            quantity=qty,
            order_type=otype,
            product_type=ORDER_PRODUCT,
            price=price if otype == "LMT" else 0,
        )
        order_id = result.get("orderId") or result.get("order_id")

        # P0-001 [r38 verified fix]: broker ack without a valid order_id is
        # NOT a confirmed success — treat it as UNKNOWN so the caller's
        # existing reconciliation/safety path is used instead of assuming
        # the order was placed. Do not retry here (would risk a duplicate
        # order); reconciliation is the existing safe recovery mechanism.
        if not order_id or not str(order_id).strip():
            append_log(AUDIT_LOG_FILE,
                       f"ORDER ACK MISSING ID: {transaction_type} {symbol} qty={qty} "
                       f"raw={result} — treating as UNKNOWN, not a confirmed success")
            return {
                "success":  False,
                "order_id": None,
                "status":   "UNKNOWN",
                "message":  "Broker accepted the call but returned no valid order_id — "
                            "order status UNKNOWN, verify manually before retrying",
                "raw":      result,
            }

        append_log(AUDIT_LOG_FILE,
                   f"ORDER PLACED: {transaction_type} {symbol} qty={qty} order_id={order_id}")
        return {"success": True, "order_id": order_id, "raw": result}

    except concurrent.futures.TimeoutError:
        append_log(AUDIT_LOG_FILE,
                   f"ORDER TIMEOUT: {transaction_type} {symbol} qty={qty} — Dhan API did not respond within {_DHAN_CALL_TIMEOUT_SECONDS}s")
        return {
            "success": False,
            "order_id": None,
            "message": f"Dhan API timeout after {_DHAN_CALL_TIMEOUT_SECONDS}s — order status UNKNOWN, verify manually before retrying",
            "skip_reason": "TIMEOUT",
        }

    except Exception as e:
        error_msg = str(e)
        # FIX-40: Categorize rejection
        category = _categorize_rejection(error_msg)
        append_log(AUDIT_LOG_FILE,
                   f"ORDER FAILED [{category}]: {transaction_type} {symbol} "
                   f"qty={qty} error={error_msg}")
        return {
            "success":        False,
            "order_id":       None,
            "message":        error_msg,
            "rejection_type": category,
        }


def verify_order_status(order_id: str, wait_sec: int = None) -> tuple:
    """
    Wait then check order status.
    Paper mode = always FILLED.

    Returns (status: str, avg_fill_price: float|None). avg_fill_price comes
    from Dhan's averageTradedPrice field so callers can re-anchor entry/SL/TP
    to the real fill instead of the pre-computed signal price. None means no
    fill price was reported (e.g. not yet filled, or field missing) — callers
    must fall back to the signal price and log loudly, never silently.

    [FIX] PART_TRADED contains the substring TRADED, so the PART/PARTIAL
    check must run BEFORE the TRADED/FILLED check, or a partial fill gets
    silently misclassified as a complete fill.
    """
    if str(order_id).startswith("PAPER-"):
        return "FILLED", None

    # [v5.8.2] default config-driven (order_status_default_wait_sec) — hardcode
    # nahi; callers explicit wait dete hain to wahi respect hota hai.
    if wait_sec is None:
        wait_sec = int(PARAMS.get("order_status_default_wait_sec", 30))
    time.sleep(wait_sec)
    try:
        dhan   = get_dhan()
        result = dhan.get_order_by_id(order_id)
        status = result.get("orderStatus", "UNKNOWN").upper()
        avg_fill_price = result.get("averageTradedPrice")
        try:
            avg_fill_price = float(avg_fill_price) if avg_fill_price not in (None, "", 0) else None
        except (TypeError, ValueError):
            avg_fill_price = None

        if "PART" in status:
            return "PARTIAL", avg_fill_price
        elif "TRADED" in status or "FILLED" in status:
            return "FILLED", avg_fill_price
        elif "REJECT" in status or "CANCEL" in status:
            return "REJECTED", avg_fill_price
        else:
            return "PENDING", avg_fill_price
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"ORDER VERIFY ERROR order_id={order_id}: {e}")
        return "UNKNOWN", None


def get_order_fill_snapshot(order_id: str) -> dict:
    """Qty-aware fill snapshot. Does NOT sleep. Does NOT change
    verify_order_status's 2-tuple (status, avg_fill_price).

    Returns {status, filled_qty, remaining_qty, avg_fill_price, raw}.
    Paper orders: FILLED with filled_qty=None (not a partial).
    Fail-closed: unknown/error → filled_qty=0 so callers do not adopt ghosts.
    """
    empty = {
        "status": "UNKNOWN",
        "filled_qty": 0,
        "remaining_qty": 0,
        "avg_fill_price": None,
        "raw": None,
    }
    if str(order_id).startswith("PAPER-"):
        return {
            "status": "FILLED",
            "filled_qty": None,
            "remaining_qty": 0,
            "avg_fill_price": None,
            "raw": {"paper": True},
        }
    try:
        dhan = get_dhan()
        result = dhan.get_order_by_id(order_id) or {}
        status_raw = str(result.get("orderStatus", "UNKNOWN")).upper()

        def _int_field(*keys):
            for k in keys:
                v = result.get(k)
                if v in (None, "", "None"):
                    continue
                try:
                    n = int(float(v))
                except (TypeError, ValueError):
                    continue
                if n > 0:
                    return n
            return 0

        filled = _int_field("filledQty", "filled_qty", "tradedQty")
        remaining = _int_field("remainingQuantity", "remaining_qty", "unfilledQty")
        ordered = _int_field("quantity", "qty", "orderQty")
        if remaining <= 0 and ordered > 0 and filled > 0 and filled < ordered:
            remaining = ordered - filled
        avg = result.get("averageTradedPrice")
        try:
            avg = float(avg) if avg not in (None, "", 0, "0") else None
        except (TypeError, ValueError):
            avg = None

        if "PART" in status_raw:
            st = "PARTIAL"
        elif "TRADED" in status_raw or "FILLED" in status_raw:
            st = "FILLED"
        elif "REJECT" in status_raw:
            st = "REJECTED"
        elif "CANCEL" in status_raw:
            st = "CANCELLED"
        elif status_raw and status_raw != "UNKNOWN":
            st = "PENDING"
        else:
            st = "UNKNOWN"
        return {
            "status": st,
            "filled_qty": filled,
            "remaining_qty": remaining,
            "avg_fill_price": avg,
            "raw": result,
        }
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"ORDER FILL SNAPSHOT ERROR order_id={order_id}: {e}")
        empty["error"] = str(e)
        return empty


def cancel_order(order_id: str) -> bool:
    if str(order_id).startswith("PAPER-"):
        return True
    try:
        dhan = get_dhan()
        dhan.cancel_order(order_id)
        append_log(AUDIT_LOG_FILE, f"ORDER CANCELLED: order_id={order_id}")
        return True
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"ORDER CANCEL ERROR order_id={order_id}: {e}")
        return False


# ─────────────────────────────────────────────
# FOREVER ORDERS (GTT)
# ─────────────────────────────────────────────

def place_forever_order(security_id: str, symbol: str, qty: int,
                        trigger_price: float, order_label: str = "") -> dict:
    """Place GTT/Forever order."""
    from bot_state_manager import is_real_orders
    if not is_real_orders():
        fake_id = f"PAPER-GTT-{symbol}-{order_label}"
        return {"success": True, "forever_id": fake_id}

    try:
        dhan   = get_dhan()
        result = dhan.place_forever_order(
            security_id=security_id,
            exchange_segment=ORDER_SEGMENT,
            transaction_type="SELL",
            product_type=ORDER_PRODUCT,
            quantity=qty,
            price=0,
            order_type="MKT",
            trigger_price=trigger_price,
        )
        forever_id = result.get("foreverOrderId") or result.get("id")

        # P0-002 [r38 verified fix]: a GTT ack without a valid forever_id
        # must NOT be reported as a successful protective order — the
        # position would silently be left unprotected. Report failure so
        # the caller's existing UNPROTECTED_POSITION / safety path runs.
        if not forever_id or not str(forever_id).strip():
            append_log(AUDIT_LOG_FILE,
                       f"FOREVER ORDER ACK MISSING ID: {symbol} [{order_label}] "
                       f"trigger={trigger_price} raw={result} — NOT reporting as protected")
            return {
                "success":    False,
                "forever_id": None,
                "message":    "Broker accepted the GTT call but returned no valid "
                              "forever_order_id — position must be treated as unprotected",
                "raw":        result,
            }

        append_log(AUDIT_LOG_FILE,
                   f"FOREVER ORDER SET: {symbol} [{order_label}] "
                   f"trigger={trigger_price} id={forever_id}")
        return {"success": True, "forever_id": forever_id, "raw": result}
    except Exception as e:
        append_log(AUDIT_LOG_FILE,
                   f"FOREVER ORDER FAILED: {symbol} [{order_label}] error={e}")
        return {"success": False, "forever_id": None, "message": str(e)}


def modify_forever_order(forever_id: str, symbol: str,
                         new_trigger_price: float, order_label: str = "") -> bool:
    if str(forever_id).startswith("PAPER-"):
        return True
    try:
        dhan = get_dhan()
        dhan.modify_forever_order(
            forever_order_id=forever_id,
            trigger_price=new_trigger_price,
        )
        append_log(AUDIT_LOG_FILE,
                   f"FOREVER MODIFIED: {symbol} [{order_label}] "
                   f"new_trigger={new_trigger_price} id={forever_id}")
        return True
    except Exception as e:
        append_log(AUDIT_LOG_FILE,
                   f"FOREVER MODIFY ERROR: {symbol} id={forever_id} error={e}")
        return False


def cancel_forever_order(forever_id: str, symbol: str) -> bool:
    if str(forever_id).startswith("PAPER-"):
        return True
    try:
        dhan = get_dhan()
        dhan.cancel_forever_order(forever_id)
        append_log(AUDIT_LOG_FILE, f"FOREVER CANCELLED: {symbol} id={forever_id}")
        return True
    except Exception as e:
        append_log(AUDIT_LOG_FILE,
                   f"FOREVER CANCEL ERROR: {symbol} id={forever_id} error={e}")
        return False


# ─────────────────────────────────────────────
# MARKET DEPTH (5-level bid/ask)
# Dhan API: get_market_depth
# ─────────────────────────────────────────────

def get_market_depth(security_id: str, exchange_segment: str = "NSE_EQ") -> dict:
    """Get 5-level bid/ask market depth from Dhan."""
    try:
        dhan = get_dhan()
        result = dhan.get_market_depth(
            security_id=security_id,
            exchange_segment=exchange_segment,
        )
        # NDSAP Part C tap (prd.md Rule 15) — raw depth payload, pre-transformation.
        if result:
            from ndsap_archive import archive_record
            archive_record(result, provider="dhan", dataset="market_depth",
                           security_id=security_id, exchange=exchange_segment)
        return result or {}
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"MARKET DEPTH ERROR {security_id}: {e}")
        return {}


def get_quote_data(security_id: str, exchange_segment: str = "NSE_EQ") -> dict:
    """Get full quote (OHLC + depth + OI + volume) from Dhan."""
    try:
        dhan = get_dhan()
        result = dhan.ohlc_data(
            securities={exchange_segment: [int(security_id)]}
        )
        # NDSAP Part C tap (prd.md Rule 15) — raw payload, pre-transformation.
        if result:
            from ndsap_archive import archive_record
            archive_record(result, provider="dhan", dataset="ohlc_live",
                           security_id=security_id, exchange=exchange_segment)
        return result or {}
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"QUOTE DATA ERROR {security_id}: {e}")
        return {}


# ─────────────────────────────────────────────
# POSITIONS & HOLDINGS
# ─────────────────────────────────────────────

def get_positions() -> list:
    """Returns Dhan positions. Raises on API failure -- callers MUST treat
    a failed fetch as 'cannot verify', never silently as 'confirmed zero
    positions' (a broker API error and a genuinely empty account produce
    an identical empty list if swallowed here)."""
    return get_dhan().get_positions() or []


def get_holdings() -> list:
    """Returns Dhan holdings. Raises on API failure (including a Dhan-call
    timeout, per call_dhan_with_timeout) -- callers MUST treat a failed
    fetch as 'cannot verify', never silently as 'confirmed zero
    holdings' (a broker API error and a genuinely empty account produce
    an identical empty list if swallowed here). This was previously a
    fail-open pattern: reconciliation and crash-recovery callers treated
    an empty list from a failed API call the same as "you truly have zero
    positions" -- which could silently wipe tracked live positions."""
    return call_dhan_with_timeout(get_dhan().get_holdings) or []


# ─────────────────────────────────────────────
# COPY TRADING — Async
# ─────────────────────────────────────────────

def _load_copy_ledger() -> dict:
    return load_json(COPY_LEDGER_FILE, {"copies": []})


def _save_copy_ledger(data: dict):
    save_json(COPY_LEDGER_FILE, data)


def _find_open_copy(data: dict, chat_id: int, symbol: str) -> dict:
    for row in data.get("copies", []):
        if row.get("chat_id") == chat_id and row.get("symbol") == symbol and row.get("status") == "OPEN":
            return row
    return None


def _find_open_copies_for(data: dict, chat_id: int) -> list:
    """v5.0: subscriber ke saare OPEN bot-copied positions."""
    return [row for row in data.get("copies", [])
            if row.get("chat_id") == chat_id and row.get("status") == "OPEN"]


def _upsert_copy_entry(entry: dict):
    data = _load_copy_ledger()
    rows = data.setdefault("copies", [])
    for idx, row in enumerate(rows):
        if row.get("copy_id") == entry.get("copy_id"):
            rows[idx] = entry
            _save_copy_ledger(data)
            return
    rows.append(entry)
    _save_copy_ledger(data)


def _verify_subscriber_order_status(sub_dhan, order_id: str, wait_sec: int = None) -> str:
    """Verify subscriber order status using the same status taxonomy as admin orders."""
    if not order_id:
        return "UNKNOWN"
    try:
        wait = int(wait_sec if wait_sec is not None else PARAMS.get("subscriber_order_verify_wait_sec", PARAMS.get("order_verify_wait_sec", 10)))
        if wait > 0:
            time.sleep(wait)
        result = sub_dhan.get_order_by_id(order_id)
        status = str(result.get("orderStatus", "UNKNOWN")).upper()
        # [FIX] PART_TRADED contains the substring TRADED — check PART/PARTIAL
        # first or a partial fill gets silently misclassified as FILLED.
        if "PART" in status:
            return "PARTIAL"
        if "TRADED" in status or "FILLED" in status:
            return "FILLED"
        if "REJECT" in status:
            return "REJECTED"
        if "CANCEL" in status:
            return "CANCELLED"
        return "PENDING" if status and status != "UNKNOWN" else "UNKNOWN"
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"SUB ORDER VERIFY ERROR order_id={order_id}: {e}")
        return "UNKNOWN"


async def place_order_for_subscriber(sub: dict, security_id: str,
                                      symbol: str, qty: int,
                                      transaction_type: str = "BUY") -> dict:
    """Place and verify an order using subscriber's own Dhan credentials."""
    try:
        if qty < 1:
            return {"success": False, "sub_id": sub.get("chat_id"), "error": "qty < 1", "status": "REJECTED"}

        from config import EXIT_ORDER_TYPE
        otype = ENTRY_ORDER_TYPE if transaction_type == "BUY" else EXIT_ORDER_TYPE
        blocked = _live_order_session_gate(symbol, qty, otype, transaction_type)
        if blocked:
            return {
                "success": False,
                "sub_id": sub.get("chat_id"),
                "error": blocked.get("message"),
                "status": blocked.get("rejection_type", "MARKET_CLOSED"),
            }

        from crypto_utils import decrypt
        client_id    = sub["dhan_client_id"]
        access_token = decrypt(sub["dhan_access_token_enc"])
        sub_dhan     = _create_dhan_client(client_id, access_token)

        loop   = asyncio.get_event_loop()
        # otype already set above: ENTRY_ORDER_TYPE (LMT) BUY / EXIT_ORDER_TYPE (MKT) SELL
        result = await loop.run_in_executor(None, lambda: sub_dhan.place_order(
            security_id=security_id,
            exchange_segment=ORDER_SEGMENT,
            transaction_type=transaction_type,
            quantity=qty,
            order_type=otype,
            product_type=ORDER_PRODUCT,
            price=0,
        ))
        order_id = result.get("orderId") or result.get("order_id")
        status = await loop.run_in_executor(None, lambda: _verify_subscriber_order_status(sub_dhan, order_id))
        if status not in ("FILLED", "PARTIAL"):
            return {"success": False, "sub_id": sub["chat_id"], "order_id": order_id, "status": status, "result": result}
        return {"success": True, "sub_id": sub["chat_id"], "order_id": order_id, "status": status, "result": result}
    except Exception as e:
        return {"success": False, "sub_id": sub.get("chat_id"), "error": str(e), "status": "ERROR"}


async def place_forever_order_for_subscriber(sub: dict, security_id: str,
                                             symbol: str, qty: int,
                                             trigger_price: float,
                                             order_label: str = "COPY_SL") -> dict:
    """Place subscriber protective SELL forever order after a copied BUY."""
    try:
        if qty < 1 or trigger_price <= 0:
            return {"success": False, "sub_id": sub.get("chat_id"), "message": "invalid qty/trigger"}
        from crypto_utils import decrypt
        client_id    = sub["dhan_client_id"]
        access_token = decrypt(sub["dhan_access_token_enc"])
        sub_dhan     = _create_dhan_client(client_id, access_token)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: sub_dhan.place_forever_order(
            security_id=security_id,
            exchange_segment=ORDER_SEGMENT,
            transaction_type="SELL",
            product_type=ORDER_PRODUCT,
            quantity=qty,
            price=0,
            order_type="MKT",
            trigger_price=trigger_price,
        ))
        forever_id = result.get("foreverOrderId") or result.get("id")
        # P0-002b [r39 verified fix — found by LOGIC-007/CWE-252 general
        # rule, not the original manual pass]: same unvalidated-ID gap as
        # the admin place_forever_order() above, but here for subscriber
        # (copy-trade) accounts — a subscriber's protective SL could be
        # reported as installed with no valid forever_order_id.
        if not forever_id or not str(forever_id).strip():
            append_log(AUDIT_LOG_FILE,
                       f"SUB FOREVER ORDER ACK MISSING ID: sub={sub.get('chat_id')} "
                       f"raw={result} — NOT reporting as protected")
            return {"success": False, "sub_id": sub.get("chat_id"),
                    "forever_id": None,
                    "message": "Broker accepted the GTT call but returned no valid "
                               "forever_order_id — subscriber position must be "
                               "treated as unprotected",
                    "raw": result}
        return {"success": True, "sub_id": sub["chat_id"], "forever_id": forever_id, "raw": result}
    except Exception as e:
        return {"success": False, "sub_id": sub.get("chat_id"), "message": str(e)}


def _subscriber_status_allows(sub: dict, transaction_type: str) -> bool:
    # v5.0 owner exit rule: entry sirf LIVE_ACTIVE; exit un sab states me jinke
    # paas bot-dili OPEN copies ho sakti hain (expired/grace/revoked = exit
    # KABHI band nahi, sirf ledger wali positions).
    status = sub.get("status")
    if transaction_type == "BUY":
        return status == "LIVE_ACTIVE"
    if transaction_type == "SELL":
        return status in ("LIVE_ACTIVE", "EXPIRED_EXIT_ONLY", "GRACE", "REVOKED")
    return False


def _get_subscriber_holding_qty(sub: dict, symbol: str) -> int:
    """Fallback SELL qty from subscriber Dhan holdings if ledger is unavailable."""
    try:
        from crypto_utils import decrypt
        client_id = sub["dhan_client_id"]
        access_token = decrypt(sub["dhan_access_token_enc"])
        sub_dhan = _create_dhan_client(client_id, access_token)
        holdings = sub_dhan.get_holdings() or []
        for h in holdings:
            if h.get("tradingSymbol") == symbol:
                return max(0, int(float(h.get("totalQty", 0))))
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"SUB HOLDING QTY ERROR {sub.get('chat_id')} {symbol}: {e}")
    return 0


async def _notify_copy_skip(chat_id: int, message: str):
    try:
        from signal_broadcaster import notify_subscriber
        await notify_subscriber(chat_id, message)
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"COPY NOTIFY ERROR {chat_id}: {e}")


async def copy_trade_all_subscribers(subscribers: list, security_id: str,
                                      symbol: str,
                                      transaction_type: str = "BUY",
                                      admin_trade: dict = None):
    """Replicate admin orders to eligible subscribers with ledger + protection."""
    try:
        from bot_state_manager import is_real_orders
        if not is_real_orders():
            append_log(AUDIT_LOG_FILE, f"COPY SKIPPED: admin not in real-order mode for {transaction_type} {symbol}")
            return []
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"COPY REAL-ORDER CHECK FAILED: {e}")
        return []

    admin_trade = admin_trade or {}
    transaction_type = transaction_type.upper()
    ledger = _load_copy_ledger()
    tasks = []
    task_meta = []
    
    # [FIX-03] Limit concurrent API calls to prevent Dhan 429 rate limit blocks
    sem = asyncio.Semaphore(5)

    for sub in subscribers:
        chat_id = sub.get("chat_id")
        if not sub.get("dhan_linked") or not _subscriber_status_allows(sub, transaction_type):
            continue

        if transaction_type == "BUY":
            if _find_open_copy(ledger, chat_id, symbol):
                append_log(AUDIT_LOG_FILE, f"COPY BUY SKIPPED DUPLICATE: {chat_id} {symbol}")
                continue
            try:
                from capital_manager import calculate_qty_for_subscriber
                qty = await calculate_qty_for_subscriber(sub, security_id, symbol)
                if qty < 1:
                    await _notify_copy_skip(chat_id, f"Trade skipped for {symbol} — insufficient capital for minimum qty.")
                    continue
            except (ImportError, RuntimeError, ValueError, TypeError) as e:
                logger.warning(f"copy_trade_all_subscribers: Qty calc failed for {chat_id}: {type(e).__name__}: {e}")
                continue
        elif transaction_type == "SELL":
            open_copy = _find_open_copy(ledger, chat_id, symbol)
            qty = int(open_copy.get("qty", 0) or 0) if open_copy else 0
            # v5.0 owner rule: SIRF bot-dili (ledger) positions exit hoti hain —
            # subscriber ki MANUAL holdings hamari zimmedari NAHI. Holdings
            # fallback (pehle wala _get_subscriber_holding_qty path) hata diya.
            if qty < 1:
                append_log(AUDIT_LOG_FILE, f"COPY SELL SKIPPED: no bot-copied qty for {chat_id} {symbol} (manual positions excluded per owner rule)")
                continue
        else:
            continue

        # Stagger subscriber orders by 0.3s and run with semaphore concurrency cap of 5
        delay_idx = len(tasks)
        
        async def place_with_guard(s_user, s_id, sym, q, tx_t, d_idx):
            if d_idx > 0:
                await asyncio.sleep(d_idx * 0.3)
            async with sem:
                return await place_order_for_subscriber(s_user, s_id, sym, q, tx_t)

        tasks.append(place_with_guard(sub, security_id, symbol, qty, transaction_type, delay_idx))
        task_meta.append({"sub": sub, "qty": qty})

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for meta, result in zip(task_meta, results):
        sub = meta["sub"]
        chat_id = sub.get("chat_id")
        qty = meta["qty"]
        if isinstance(result, Exception):
            append_log(AUDIT_LOG_FILE, f"COPY {transaction_type} ERROR {chat_id} {symbol}: {result}")
            continue

        if transaction_type == "BUY":
            if not result.get("success"):
                append_log(AUDIT_LOG_FILE, f"COPY BUY FAILED {chat_id} {symbol}: {result}")
                continue
            copy_id = f"{symbol}:{chat_id}:{admin_trade.get('entry_time', now_ist().isoformat())}"
            entry = {
                "copy_id": copy_id,
                "chat_id": chat_id,
                "symbol": symbol,
                "security_id": security_id,
                "qty": qty,
                "status": "OPEN",
                "buy_order_id": result.get("order_id"),
                "buy_status": result.get("status"),
                "entry_time": now_ist().isoformat(),
                "admin_entry_time": admin_trade.get("entry_time"),
                "sl_price": admin_trade.get("sl_price"),
            }
            protection = await place_forever_order_for_subscriber(
                sub, security_id, symbol, qty, float(admin_trade.get("sl_price") or 0), "COPY_SL"
            )
            entry["protection_success"] = bool(protection.get("success"))
            entry["protection_order_id"] = protection.get("forever_id")
            if not protection.get("success"):
                append_log(AUDIT_LOG_FILE, f"COPY PROTECTION FAILED {chat_id} {symbol}: {protection}")
                await _notify_copy_skip(chat_id, f"Protective order failed for copied {symbol}. Contact admin / check Dhan.")
            _upsert_copy_entry(entry)
            append_log(AUDIT_LOG_FILE, f"COPY BUY RECORDED {chat_id} {symbol} qty={qty} status={result.get('status')}")

        elif transaction_type == "SELL":
            open_copy = _find_open_copy(_load_copy_ledger(), chat_id, symbol)
            if result.get("success") and open_copy:
                open_copy["status"] = "CLOSED"
                open_copy["sell_order_id"] = result.get("order_id")
                open_copy["sell_status"] = result.get("status")
                open_copy["exit_time"] = now_ist().isoformat()
                _upsert_copy_entry(open_copy)
                # v5.0 FULL-CLOSE: non-live subscriber ka aakhri bot-position
                # close hua → plan poora band (na entry, na exit). Ek hi baar.
                try:
                    from subscriber_manager import get_subscriber
                    _sub = get_subscriber(chat_id)
                    if _sub and _sub.get("status") not in ("LIVE_ACTIVE", "PAPER_TRIAL"):
                        remaining = _find_open_copies_for(_load_copy_ledger(), chat_id)
                        if not remaining:
                            from subscriber_manager import _notify
                            _notify(chat_id,
                                "✅ Plan Fully Closed\n\n"
                                "All bot-opened positions are now closed.\n\n"
                                "Subscription state: no new entries, no further exits.\n"
                                "Renew your plan to resume copy trading.")
                            append_log(AUDIT_LOG_FILE, f"PLAN FULLY CLOSED: {chat_id}")
                except (ImportError, RuntimeError, ValueError, TypeError) as e:
                    logger.warning(f"copy_trade_all_subscribers: full-close notify failed {chat_id}: {type(e).__name__}: {e}")
            append_log(AUDIT_LOG_FILE, f"COPY SELL {('OK' if result.get('success') else 'FAILED')} {chat_id} {symbol} qty={qty} status={result.get('status')}")

    return results


# ═════════════════════════════════════════════════════════════════════════
# v5.0 — TRADE-BOOK SLIPPAGE AUDIT (Tier 1: performance truth)
# ═════════════════════════════════════════════════════════════════════════
def fetch_trade_book_audit(symbol: str = None, max_days: int = 30) -> str:
    """
    Dhan trade book se ASLI fill prices nikalo aur compare karo:
    - market SELL ka slippage vs monitor-kiya exit price
    - order place → fill ka status chain
    Network-dependent — VPS pe chalta hai; sandbox me graceful skip.
    Returns readable audit text (admin /slippage).
    """
    try:
        from config import PARAMS
        dhan = get_dhan()
        result = dhan.get_trade_book()
        if not result:
            return "Slippage audit: trade book empty/unavailable."
        data = result if isinstance(result, list) else result.get("data", [])
        if not data:
            return "Slippage audit: trade book empty."
        from datetime import datetime, timedelta
        cutoff = now_ist().replace(tzinfo=None) - timedelta(days=int(max_days))
        lines = ["📐 SLIPPAGE AUDIT (trade book, actual fills)", ""]
        n = 0
        for t in data:
            try:
                ts = str(t.get("tradeTime") or t.get("exchangeTradeTime") or "")
                if ts:
                    try:
                        tdt = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                    except (ValueError, TypeError):
                        tdt = now_ist().replace(tzinfo=None)
                    if tdt < cutoff:
                        continue
                if symbol and str(t.get("tradingSymbol") or t.get("securityId")) != symbol:
                    continue
                sym = t.get("tradingSymbol", "?")
                tx = t.get("transactionType", "?")
                qty = t.get("filledQty", t.get("tradedQty", "?"))
                price = t.get("tradePrice", t.get("price", "?"))
                lines.append(f"{ts[:19]} {tx} {sym} qty={qty} fill={price}")
                n += 1
                if n >= 25:
                    break
            except (TypeError, ValueError):
                continue
        lines.append("")
        lines.append(f"Records shown: {n}")
        lines.append("Compare fill price vs bot-monitor price — gap = real slippage "
                     "(backtest cost_pct ka reality check).")
        return "\n".join(lines)
    except Exception as e:
        return f"Slippage audit unavailable: {type(e).__name__}: {e}"
