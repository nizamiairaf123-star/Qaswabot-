"""
subscriber_manager.py — AI-DOS Workflow Implementation
Industry Method: Freemium Tiered Onboarding & Term Stacking (Rollover)

States (v5.0):
- PAPER_TRIAL: Free paper trading (default on /start)
- LIVE_PENDING_PAYMENT: User requested live upgrade, awaiting payment
- LIVE_ACTIVE: Live trading active (28-din cycle)
- GRACE: expiry ke baad grace window — entry band, exit chalu, daily reminder
- EXPIRED_EXIT_ONLY: Subscription expired, no new trades; sirf bot-dili
  positions ka exit (ledger-only) — sab close hone pe full stop
- REVOKED: admin ne access revoke kiya — entry band, bot-dili exits chalu
"""

from utils import load_json, save_json, now_ist, today_ist
from config import SUBSCRIBERS_FILE, PARAMS
from datetime import date, timedelta
from broker import _create_dhan_client


def _load() -> dict:
    return load_json(SUBSCRIBERS_FILE, {"subscribers": {}})


def _save(data: dict):
    save_json(SUBSCRIBERS_FILE, data)


# ============================================================
# Phase A: Auto-Onboarding (Trigger: /start)
# ============================================================

def register_subscriber(chat_id: int, name: str):
    """
    Phase A: Auto-Onboarding
    - Register new user
    - Set status to PAPER_TRIAL
    - Calculate trial_expiry = current_date + paper_trial_days
    """
    data = _load()
    chat_id_str = str(chat_id)
    if chat_id_str not in data["subscribers"]:
        paper_trial_days = PARAMS.get("paper_trial_days", 30)
        data["subscribers"][chat_id_str] = {
            "chat_id":              chat_id,
            "name":                 name,
            "status":               "PAPER_TRIAL",
            "joined":               today_ist().isoformat(),
            "trial_expiry":         (today_ist() + timedelta(days=paper_trial_days)).isoformat(),
            "live_expiry":          None,
            "dhan_linked":          False,
            "dhan_client_id":       None,
            "dhan_access_token_enc":None,
        }
        _save(data)


# ============================================================
# Phase B: Live Upgrade Request (Trigger: /golive)
# ============================================================

def request_live_upgrade(chat_id: int) -> dict:
    """
    Phase B: Live Upgrade Request
    - Change status to LIVE_PENDING_PAYMENT
    - Return payment instructions
    """
    data = _load()
    chat_id_str = str(chat_id)
    if chat_id_str not in data["subscribers"]:
        return {"success": False, "message": "Not registered. Use /start first."}
    
    sub = data["subscribers"][chat_id_str]
    if sub["status"] not in ("PAPER_TRIAL", "EXPIRED_EXIT_ONLY"):
        return {"success": False, "message": f"Cannot upgrade from status: {sub['status']}"}
    
    sub["status"] = "LIVE_PENDING_PAYMENT"
    _save(data)
    
    live_sub_fee = PARAMS.get("live_sub_fee_inr", 3000)
    return {
        "success": True,
        "message": (
            f"Live Trading Upgrade Request\n\n"
            f"Fee: Rs.{live_sub_fee:,.0f}\n"
            f"Duration: {PARAMS.get('live_sub_days', 30)} days\n\n"
            f"Contact admin to complete payment.\n"
            f"Use /status to check your status."
        )
    }


# ============================================================
# Phase C: Payment Approval & Rollover (Trigger: /approve <chat_id>)
# ============================================================

def approve_subscriber(chat_id: int) -> dict:
    """
    Phase C: Payment Approval & Term Stacking (Rollover)
    - Admin only
    - Execute Term Stacking:
      - If LIVE_ACTIVE AND live_expiry in future: new_expiry = current_expiry + live_sub_days
      - Otherwise: new_expiry = current_date + live_sub_days
    - Update status to LIVE_ACTIVE
    """
    data = _load()
    chat_id_str = str(chat_id)
    if chat_id_str not in data["subscribers"]:
        return {"success": False, "message": "Subscriber not found."}
    
    sub = data["subscribers"][chat_id_str]
    live_sub_days = PARAMS.get("live_sub_days", 30)
    now = today_ist()
    
    # Term Stacking (Rollover) Logic
    if sub["status"] == "LIVE_ACTIVE" and sub.get("live_expiry"):
        try:
            current_expiry = date.fromisoformat(sub["live_expiry"])
            if current_expiry > now:
                # Rollover: extend from current expiry
                new_expiry = current_expiry + timedelta(days=live_sub_days)
            else:
                # Expired, start fresh
                new_expiry = now + timedelta(days=live_sub_days)
        except ValueError:
            new_expiry = now + timedelta(days=live_sub_days)
    else:
        # New upgrade or from PAPER_TRIAL/EXPIRED_EXIT_ONLY
        new_expiry = now + timedelta(days=live_sub_days)
    
    sub["status"] = "LIVE_ACTIVE"
    sub["live_expiry"] = new_expiry.isoformat()
    _save(data)
    
    return {
        "success": True,
        "message": (
            f"Approved: {chat_id}\n"
            f"Status: LIVE_ACTIVE\n"
            f"Expiry: {new_expiry.isoformat()}"
        )
    }


# ============================================================
# Phase D: Graceful Expiry & Exit-Only State (Daily Job)
# ============================================================

def _notify(chat_id: int, msg: str):
    """Sync/async-safe subscriber notification (scheduler thread + asyncio dono)."""
    try:
        from signal_broadcaster import notify_subscriber, notify_subscriber_sync
        import asyncio
        try:
            asyncio.get_running_loop().create_task(notify_subscriber(chat_id, msg))
        except RuntimeError:
            notify_subscriber_sync(chat_id, msg)
    except (ImportError, RuntimeError) as e:
        import logging
        logging.warning(f"_notify failed for {chat_id}: {e}")


def _renewal_link_or_none(chat_id: int):
    """Payment link banao (agar payment configured ho) — renewal message me chipkane ke liye."""
    try:
        from payment import create_payment_link
        link = create_payment_link(chat_id)
        return link.get("short_url") or link.get("long_url") if link else None
    except Exception:
        return None


def auto_expire_subscriptions():
    """
    Phase D: Daily Expiry Check (v5.0 — 28-din active + 2-din GRACE)

    - T-2: renewal reminder (Telegram) + payment link (agar configured)
    - Expiry se pehle payment → term-stacking (approve_subscriber): counting
      purane expiry ke BAAD se — koi din waste nahi.
    - Expiry ke baad GRACE (grace_days): entry band, exit chalu, daily reminder
    - GRACE khatam → EXPIRED_EXIT_ONLY: na entry, sirf bot-dili positions ka exit
      (ledger-only), sab close hone pe full stop.
    """
    data = _load()
    today = today_ist()
    reminder_days = PARAMS.get("expiry_reminder_days", 2)
    grace_days = PARAMS.get("grace_days", 2)

    for chat_id_str, sub in data["subscribers"].items():
        status = sub.get("status")
        if status not in ("LIVE_ACTIVE", "GRACE"):
            continue

        live_expiry = sub.get("live_expiry")
        if not live_expiry:
            continue

        try:
            expiry_date = date.fromisoformat(live_expiry)
        except ValueError as e:
            import logging
            logging.error(f"auto_expire_subscriptions: corrupt live_expiry='{live_expiry}' for chat_id={chat_id_str} — forcing EXPIRED_EXIT_ONLY (fail-closed)")
            sub["status"] = "EXPIRED_EXIT_ONLY"
            try:
                from signal_broadcaster import alert_admin_sync
                alert_admin_sync(f"⚠️ Subscriber chat_id={chat_id_str} corrupt live_expiry ('{live_expiry}') — auto-expired (fail-closed). Review manually.")
            except Exception as alert_e:
                logging.warning(f"auto_expire_subscriptions: admin alert failed: {alert_e}")
            continue

        days_remaining = (expiry_date - today).days
        chat_id = int(chat_id_str)

        if status == "LIVE_ACTIVE":
            if 0 < days_remaining <= reminder_days:
                # T-2 dual-channel renewal alert
                link = _renewal_link_or_none(chat_id)
                msg = (
                    "⏳ Subscription Expiring Soon\n\n"
                    f"Your subscription expires in {days_remaining} day(s) ({live_expiry}).\n\n"
                    "After expiry:\n"
                    "- No new copy trades\n"
                    "- Your open positions will be exited by the bot\n\n"
                    "Renew to continue without any gap:"
                )
                if link:
                    msg += f"\n\n💳 Pay ₹{int(PARAMS.get('razorpay_amount_inr', 3105))} and renew:\n{link}"
                else:
                    msg += "\n\nContact admin to renew."
                _notify(chat_id, msg)
            elif days_remaining <= 0:
                overdue = -days_remaining
                if overdue < grace_days:
                    sub["status"] = "GRACE"
                    link = _renewal_link_or_none(chat_id)
                    msg = (
                        "🟡 GRACE PERIOD\n\n"
                        f"Your subscription expired on {live_expiry}.\n"
                        f"Grace ends in {grace_days - overdue} day(s).\n\n"
                        "During grace:\n"
                        "- No new copy trades\n"
                        "- Open positions will still be exited by the bot\n\n"
                        "Renew now — your plan will continue from the expiry date (no days lost):"
                    )
                    if link:
                        msg += f"\n\n💳 {link}"
                    _notify(chat_id, msg)
                else:
                    sub["status"] = "EXPIRED_EXIT_ONLY"
                    _notify(chat_id,
                        "🔴 Subscription Expired\n\n"
                        f"Your subscription expired on {live_expiry}.\n\n"
                        "Now:\n"
                        "- No new copy trades\n"
                        "- Only the positions opened through the bot will be exited\n"
                        "- After all bot positions close, the plan is fully closed\n\n"
                        "Renew to resume copy trading.")
        elif status == "GRACE":
            overdue = -days_remaining
            if overdue < grace_days:
                link = _renewal_link_or_none(chat_id)
                msg = (
                    "🟡 GRACE — Renewal Reminder\n\n"
                    f"Grace ends in {grace_days - overdue} day(s).\n"
                    "No new copy trades during grace.\n\nRenew now:"
                )
                if link:
                    msg += f"\n\n💳 {link}"
                _notify(chat_id, msg)
            else:
                sub["status"] = "EXPIRED_EXIT_ONLY"
                _notify(chat_id,
                    "🔴 Subscription Expired\n\n"
                    f"Grace period over ({live_expiry}).\n"
                    "Only bot-opened positions will be exited.\n"
                    "After that, the plan is fully closed.\n\n"
                    "Renew to resume copy trading.")

    _save(data)


# ═════════════════════════════════════════════════════════════════════════
# v5.0 — REVOKE / STATEMENT / DIVERGENCE / APPROVAL VALIDATION
# ═════════════════════════════════════════════════════════════════════════
def revoke_subscriber(chat_id: int, reason: str = "") -> dict:
    """
    Admin revoke (command lifecycle — approve ka revert).
    REVOKED = no new entries (BUY copy band); bot-opened positions ki SELL
    copy chalti rahegi (owner exit rule); sab close hone pe full stop.
    """
    data = _load()
    key = str(chat_id)
    if key not in data["subscribers"]:
        return {"success": False, "message": "Subscriber not found."}
    sub = data["subscribers"][key]
    sub["status"] = "REVOKED"
    sub["revoked_at"] = now_ist().isoformat()
    sub["revoke_reason"] = reason or "Admin revoke"
    _save(data)
    _notify(chat_id,
        "🚫 Access Revoked\n\n"
        "Your live subscription access has been revoked by the admin.\n\n"
        "- No new copy trades\n"
        "- Positions opened through the bot will still be exited\n"
        "Contact the admin for details.")
    return {"success": True, "message": f"chat_id={chat_id} revoked."}


def can_approve(chat_id: int) -> tuple:
    """
    Command-lifecycle validation (v5.0): /approve se pehle —
    (a) subscriber exist, (b) payment requested (LIVE_PENDING_PAYMENT),
    (c) Dhan linked. Pay/verify ho chuka ho to allow.
    """
    sub = get_subscriber(chat_id)
    if not sub:
        return False, "Subscriber not found."
    if not sub.get("dhan_linked"):
        return False, "Subscriber ne Dhan link nahi kiya — pehle /linkdhan."
    if sub.get("status") == "LIVE_ACTIVE":
        return True, "Already active (term-stacking approve allowed)."
    if sub.get("status") != "LIVE_PENDING_PAYMENT":
        return False, f"Status '{sub.get('status')}' — pehle /golive se upgrade request aani chahiye."
    return True, "OK"


def get_subscriber_statement(chat_id: int) -> str:
    """
    v5.0 — VIEW-ONLY monthly P&L statement (Telegram text; DOWNLOAD NAHI —
    owner rule: safety purpose, koi file export nahi).
    """
    sub = get_subscriber(chat_id)
    if not sub:
        return "Subscriber not found."
    try:
        from broker import _load_copy_ledger
        ledger = _load_copy_ledger()
        mine = [e for e in ledger.get("copies", []) if str(e.get("chat_id")) == str(chat_id)]
        if not mine:
            return "No copy-trade records yet."
        closed = [e for e in mine if e.get("status") == "CLOSED"]
        open_c = [e for e in mine if e.get("status") == "OPEN"]
        lines = [f"📊 STATEMENT — chat_id {chat_id}", f"Status: {sub.get('status')}",
                 f"Bot-copied positions: {len(mine)} (open: {len(open_c)}, closed: {len(closed)})", ""]
        for e in mine[-30:]:
            sym = e.get("symbol", "?")
            in_t = str(e.get("entry_time", ""))[:10]
            out_t = str(e.get("exit_time", ""))[:10] or "—"
            lines.append(f"{sym}: qty={e.get('qty', '?')} in={in_t} out={out_t} [{e.get('status', '?')}]")
        lines.append("")
        lines.append("(View-only statement — download available nahi, owner safety policy)")
        return "\n".join(lines)
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        return f"Statement unavailable: {type(e).__name__}: {e}"


def get_copy_divergence_report() -> str:
    """
    v5.0 — subscriber-vs-admin copy divergence (business quality proof).
    Admin ka avg net return% vs subscribers ka avg copy return% (ledger se).
    """
    try:
        from broker import _load_copy_ledger
        ledger = _load_copy_ledger()
        entries = ledger.get("copies", [])
        if not entries:
            return "Divergence: no copy records yet."
        subs = {}
        for e in entries:
            cid = str(e.get("chat_id"))
            rec = subs.setdefault(cid, {"open": 0, "closed": 0, "buy_ok": 0, "buy_fail": 0})
            if e.get("status") == "OPEN":
                rec["open"] += 1
            else:
                rec["closed"] += 1
            if str(e.get("buy_status", "")).upper() in ("FILLED", "TRADED", "EXECUTED", ""):
                rec["buy_ok"] += 1
            else:
                rec["buy_fail"] += 1
        lines = ["📉 Copy Divergence (admin vs subscribers)", ""]
        for cid, rec in subs.items():
            lines.append(f"chat_id {cid}: closed={rec['closed']} open={rec['open']} "
                         f"buys_ok={rec['buy_ok']}/{rec['buy_ok'] + rec['buy_fail']}")
        lines.append("")
        lines.append("(Admin reference: /pnl. Gap chhota = copy execution clean. "
                     "Statement me P&L nahi kyunki ledger sirf order-status track karta hai — honest scope.)")
        return "\n".join(lines)
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        return f"Divergence unavailable: {type(e).__name__}: {e}"


# ============================================================
# Phase E: Execution Engine Gatekeeping (Security)
# ============================================================

def can_trade(chat_id: int) -> tuple:
    """
    Phase E: Gatekeeping
    - BUY/Entry: Only if LIVE_ACTIVE
    - SELL/SL/TP: LIVE_ACTIVE or EXPIRED_EXIT_ONLY (to close existing positions)
    """
    sub = get_subscriber(chat_id)
    if not sub:
        return False, "Not registered"
    
    status = sub.get("status", "UNKNOWN")
    
    if status == "LIVE_ACTIVE":
        return True, "OK"
    elif status == "EXPIRED_EXIT_ONLY":
        return True, "EXIT_ONLY"  # Can only exit, not enter
    else:
        return False, f"Trading not allowed (status: {status})"


def can_enter_trade(chat_id: int) -> tuple:
    """Only LIVE_ACTIVE can enter new trades."""
    sub = get_subscriber(chat_id)
    if not sub:
        return False, "Not registered"
    
    if sub.get("status") == "LIVE_ACTIVE":
        return True, "OK"
    return False, f"New trades not allowed (status: {sub.get('status')})"


def can_exit_trade(chat_id: int) -> tuple:
    """LIVE_ACTIVE or EXPIRED_EXIT_ONLY can exit trades."""
    sub = get_subscriber(chat_id)
    if not sub:
        return False, "Not registered"
    
    if sub.get("status") in ("LIVE_ACTIVE", "EXPIRED_EXIT_ONLY"):
        return True, "OK"
    return False, f"Exit not allowed (status: {sub.get('status')})"


# ============================================================
# Helper Functions
# ============================================================

def get_subscriber(chat_id: int) -> dict:
    data = _load()
    return data["subscribers"].get(str(chat_id), {})


def get_all_subscribers() -> dict:
    return _load().get("subscribers", {})


def get_active_subscribers() -> list:
    """Get subscribers with LIVE_ACTIVE status."""
    return [s for s in get_all_subscribers().values()
            if s.get("status") == "LIVE_ACTIVE"]


def get_pending_users() -> list:
    """Get users with PAPER_TRIAL or LIVE_PENDING_PAYMENT status."""
    data = _load()
    pending = []
    for chat_id_str, sub in data["subscribers"].items():
        if sub.get("status") in ("PAPER_TRIAL", "LIVE_PENDING_PAYMENT"):
            pending.append({
                "chat_id": sub["chat_id"],
                "name": sub.get("name", "Unknown"),
                "status": sub.get("status"),
                "joined": sub.get("joined", "N/A"),
            })
    return pending


def get_expiring_users() -> list:
    """Get users whose subscription is expiring soon (within reminder_days)."""
    data = _load()
    today = today_ist()
    reminder_days = PARAMS.get("expiry_reminder_days", 3)
    expiring = []
    
    for chat_id_str, sub in data["subscribers"].items():
        if sub.get("status") != "LIVE_ACTIVE":
            continue
        live_expiry = sub.get("live_expiry")
        if live_expiry:
            try:
                expiry_date = date.fromisoformat(live_expiry)
                remaining = (expiry_date - today).days
                if 0 < remaining <= reminder_days:
                    expiring.append({
                        "chat_id": sub["chat_id"],
                        "name": sub.get("name", "Unknown"),
                        "expiry": live_expiry,
                        "days_remaining": remaining,
                    })
            except ValueError:
                pass
    return expiring


def link_dhan(chat_id: int, client_id: str, access_token: str) -> dict:
    """Fail-closed Dhan account linking transaction.

    F013 invariant: credentials are saved only after token format, Dhan API
    validation, and encryption all succeed. Linking a Dhan account does not by
    itself activate copy trading; runtime copy eligibility still requires
    LIVE_ACTIVE + dhan_linked.
    """
    from utils import is_valid_token

    client_id = str(client_id or "").strip()
    access_token = str(access_token or "").strip()
    if not is_valid_token({"client_id": client_id, "access_token": access_token}):
        return {"success": False, "message": "Invalid token format."}

    data = _load()
    chat_id_str = str(chat_id)
    if chat_id_str not in data.get("subscribers", {}):
        return {"success": False, "message": "Not registered. Use /start first."}

    # Validate Dhan credentials before encryption/save. Any provider/client
    # exception fails closed and leaves existing subscriber data unchanged.
    try:
        test_dhan = _create_dhan_client(client_id, access_token)
        result = test_dhan.get_fund_limits()
        if not isinstance(result, dict) or result is None:
            return {"success": False, "message": "Invalid credentials or account inactive."}
    except Exception as e:
        return {"success": False, "message": f"Invalid credentials or account inactive. Error: {e}"}

    # Validate encryption readiness before modifying persistent data.
    try:
        from crypto_utils import encrypt
        encrypted_token = encrypt(access_token)
    except Exception as e:
        return {"success": False, "message": f"Credential encryption failed. Contact admin. Error: {e}"}

    updated = dict(data)
    updated.setdefault("subscribers", {})
    sub = dict(updated["subscribers"][chat_id_str])
    sub["dhan_linked"] = True
    sub["dhan_client_id"] = client_id
    sub["dhan_access_token_enc"] = encrypted_token
    sub["linked_at"] = now_ist().isoformat()
    updated["subscribers"][chat_id_str] = sub

    try:
        _save(updated)
    except Exception as e:
        return {"success": False, "message": f"Could not save linked account. No credentials were updated. Error: {e}"}

    status = sub.get("status", "UNKNOWN")
    if status == "LIVE_ACTIVE":
        suffix = "Copy trading is active for new trades."
    else:
        suffix = "Copy trading will activate only when your subscription status is LIVE_ACTIVE."
    return {
        "success": True,
        "message": f"Dhan account linked and validated successfully. {suffix}"
    }


def _has_open_copy_positions(chat_id: int) -> tuple:
    """Check F079 copy-trade ledger for this subscriber's open copied positions."""
    try:
        from broker import COPY_LEDGER_FILE
        ledger = load_json(COPY_LEDGER_FILE, {"copies": []})
        open_rows = [
            row for row in ledger.get("copies", [])
            if row.get("chat_id") == chat_id and row.get("status") == "OPEN"
        ]
        return bool(open_rows), open_rows
    except Exception as e:
        return None, f"copy ledger check failed: {e}"


def _subscriber_dhan_exposure(sub: dict) -> tuple:
    """Return (ok, exposure_list_or_error) for subscriber's own Dhan account."""
    if not sub.get("dhan_linked"):
        return True, []
    client_id = sub.get("dhan_client_id")
    token_enc = sub.get("dhan_access_token_enc")
    if not client_id or not token_enc:
        return False, "linked account credentials missing"

    try:
        from crypto_utils import decrypt
        access_token = decrypt(token_enc)
        dhan = _create_dhan_client(client_id, access_token)

        exposures = []
        try:
            holdings = dhan.get_holdings() or []
            for h in holdings:
                qty = float(h.get("totalQty", h.get("qty", 0)) or 0)
                if qty > 0:
                    exposures.append({
                        "type": "holding",
                        "symbol": h.get("tradingSymbol", h.get("symbol", "UNKNOWN")),
                        "qty": qty,
                    })
        except Exception as e:
            return False, f"Dhan holdings check failed: {e}"

        try:
            positions = dhan.get_positions() or []
            for pos in positions:
                qty = float(pos.get("netQty", pos.get("quantity", pos.get("qty", 0))) or 0)
                if qty != 0:
                    exposures.append({
                        "type": "position",
                        "symbol": pos.get("tradingSymbol", pos.get("symbol", "UNKNOWN")),
                        "qty": qty,
                    })
        except Exception as e:
            return False, f"Dhan positions check failed: {e}"

        return True, exposures
    except Exception as e:
        return False, f"subscriber Dhan validation failed: {e}"


def unlink_dhan(chat_id: int) -> dict:
    """F014: fail-closed normal unlink using subscriber's own runtime state."""
    data = _load()
    chat_id_str = str(chat_id)
    if chat_id_str not in data.get("subscribers", {}):
        return {"success": False, "has_positions": False, "message": "Subscriber not found."}

    sub = data["subscribers"][chat_id_str]
    if not sub.get("dhan_linked"):
        return {"success": True, "has_positions": False, "message": "Dhan account is already unlinked."}

    has_copy, copy_detail = _has_open_copy_positions(chat_id)
    if has_copy is None:
        return {
            "success": False,
            "has_positions": False,
            "check_failed": True,
            "message": f"Cannot unlink safely — {copy_detail}. Try again later or contact admin."
        }
    if has_copy:
        return {
            "success": False,
            "has_positions": True,
            "message": (
                f"Cannot unlink — {len(copy_detail)} copied open position(s) exist.\n\n"
                f"Wait for copied trades to close before unlinking.\n\n"
                f"Force unlink is a separate admin-risk action and should be used only if you will manage positions manually."
            )
        }

    dhan_ok, exposure = _subscriber_dhan_exposure(sub)
    if not dhan_ok:
        return {
            "success": False,
            "has_positions": False,
            "check_failed": True,
            "message": f"Cannot unlink safely — {exposure}. No credentials were changed."
        }
    if exposure:
        preview = ", ".join([f"{x['symbol']}:{x['qty']}" for x in exposure[:5]])
        return {
            "success": False,
            "has_positions": True,
            "message": (
                f"Cannot unlink — open Dhan holdings/positions detected ({preview}).\n\n"
                f"Close positions before unlinking, or manage force unlink separately."
            )
        }

    updated = dict(data)
    updated.setdefault("subscribers", {})
    updated_sub = dict(updated["subscribers"][chat_id_str])
    updated_sub["dhan_linked"] = False
    updated_sub["dhan_client_id"] = None
    updated_sub["dhan_access_token_enc"] = None
    updated_sub["unlinked_at"] = now_ist().isoformat()
    updated["subscribers"][chat_id_str] = updated_sub

    try:
        _save(updated)
    except Exception as e:
        return {
            "success": False,
            "has_positions": False,
            "check_failed": True,
            "message": f"Could not save unlink state. No credentials were changed. Error: {e}"
        }

    return {"success": True, "has_positions": False, "message": "Dhan account unlinked safely."}


def force_unlink_dhan(chat_id: int) -> bool:
    """FIX-12: Force unlink even with open positions."""
    data = _load()
    chat_id_str = str(chat_id)
    if chat_id_str in data["subscribers"]:
        data["subscribers"][chat_id_str]["dhan_linked"] = False
        data["subscribers"][chat_id_str]["dhan_client_id"] = None
        data["subscribers"][chat_id_str]["dhan_access_token_enc"] = None
        _save(data)
        return True
    return False


def is_admin(chat_id: int) -> bool:
    from config import ADMIN_CHAT_ID
    return chat_id == ADMIN_CHAT_ID


def get_user_role(chat_id: int) -> str:
    """
    AI-DOS Phase B: Role Verification
    Returns one of: ADMIN, LIVE_ACTIVE, PAPER_TRIAL, EXPIRED_EXIT_ONLY
    """
    if is_admin(chat_id):
        return "ADMIN"
    
    sub = get_subscriber(chat_id)
    if not sub:
        return "NOT_REGISTERED"
    
    status = sub.get("status", "UNKNOWN")
    
    if status == "LIVE_ACTIVE":
        return "LIVE_ACTIVE"
    elif status == "PAPER_TRIAL":
        return "PAPER_TRIAL"
    elif status in ("EXPIRED_EXIT_ONLY", "GRACE", "REVOKED"):
        return "EXPIRED_EXIT_ONLY"
    else:
        return "UNKNOWN"


def get_subscriber_status_text(chat_id: int) -> str:
    """Get user-friendly subscription status text."""
    sub = get_subscriber(chat_id)
    if not sub:
        return "Not registered. Use /start"
    
    status = sub.get("status", "UNKNOWN")
    linked = "✅ Linked" if sub.get("dhan_linked") else "❌ Not linked"
    joined = sub.get("joined", "N/A")[:10]
    
    msg = (
        f"📊 Your Status\n"
        f"Status: {status}\n"
        f"📅 Joined: {joined}\n"
        f"🔗 Dhan: {linked}\n"
    )
    
    # Trial info
    if status == "PAPER_TRIAL" and sub.get("trial_expiry"):
        try:
            trial_date = date.fromisoformat(sub["trial_expiry"])
            days_left = (trial_date - today_ist()).days
            msg += f"🎁 Trial: {max(0, days_left)} days remaining\n"
        except ValueError:
            pass
    
    live_expired_display_warning = False

    # Live subscription info (display-only; F061 owns lifecycle mutation)
    if sub.get("live_expiry"):
        try:
            live_date = date.fromisoformat(sub["live_expiry"])
            days_left = (live_date - today_ist()).days
            if days_left > 0:
                msg += f"📆 Subscription: {days_left} days remaining\n"
            elif status == "LIVE_ACTIVE":
                live_expired_display_warning = True
                msg += "⚠️ Subscription has passed expiry. Final status will update after the expiry workflow.\n"
        except ValueError:
            if status == "LIVE_ACTIVE":
                msg += "⚠️ Subscription expiry date unavailable. Contact admin.\n"
    
    msg += "\n"
    
    # Status-specific messages
    if status == "PAPER_TRIAL":
        msg += (
            "📝 Paper Trading Mode\n"
            "Use /simulate to test strategy.\n"
            "Use /golive to upgrade to real trading."
        )
    elif status == "LIVE_PENDING_PAYMENT":
        msg += "⏳ Payment pending. Contact admin to complete."
    elif status == "LIVE_ACTIVE" and live_expired_display_warning:
        msg += (
            "LIVE_ACTIVE subscription expiry has passed.\n"
            "No lifecycle state was changed by this status view.\n"
            "Expiry processing is handled by the scheduled expiry workflow."
        )
    elif status == "LIVE_ACTIVE" and sub.get("dhan_linked"):
        msg += (
            "✅ Copy Trading Active\n"
            "You will receive copies of NEW trades only.\n"
            "Existing admin positions are not copied."
        )
    elif status == "LIVE_ACTIVE" and not sub.get("dhan_linked"):
        msg += "⚠️ Link your Dhan account to start copy trading.\nUse /link for instructions."
    elif status == "EXPIRED_EXIT_ONLY":
        msg += (
            "❌ Subscription Expired\n"
            "No new trades.\n"
            "Existing trades managed to closure.\n"
            "Contact admin to renew."
        )
    else:
        msg += "⚠️ Status unrecognized. Contact admin for assistance."
    
    return msg
