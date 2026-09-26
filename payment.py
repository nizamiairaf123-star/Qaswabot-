"""
payment.py — Auto-Payment Integration (v5.0, Razorpay Payment Links)

OWNER DECISIONS (v5.0):
- Amount FIXED ₹3105 (fee + gateway ~3.5%) — payment link me locked,
  partial payments OFF → subscriber kam-zyada amount nahi kar sakta.
- Methods: UPI + cards dono.
- Auto-renewal NAHI — manual renewal; T-2 pe Telegram alert + payment link
  (Razorpay apni link delivery bhi karta hai — dono channels chalte hain).
- Term-stacking: jaldi payment → counting purane expiry ke BAAD se
  (subscriber_manager.approve_subscriber ka rollover logic hi use hota hai).
- Duplicate-payment guard: har payment id ek hi baar count.

DISABLED-BY-DEFAULT: RAZORPAY_KEY_ID/SECRET env set nahi hone tak link
creation None return karta hai — /subscribe bolega "contact admin".
Webhook server sirf RAZORPAY_WEBHOOK_PORT env set hone pe chalta hai.

Security: webhook signature HMAC-SHA256 (X-Razorpay-Signature) verify hota
hai; verify fail = event reject (fake-payment block).
"""

import hashlib
import hmac
import json
import logging
import os
import threading

import requests

from utils import append_log, load_json, save_json, now_ist
from config import AUDIT_LOG_FILE, PARAMS

logger = logging.getLogger(__name__)

PAYMENT_LINKS_FILE = "data/payment_links.json"

RAZORPAY_API = "https://api.razorpay.com/v1"


def _creds() -> tuple:
    return (os.getenv("RAZORPAY_KEY_ID", ""), os.getenv("RAZORPAY_KEY_SECRET", ""))


def is_payment_configured() -> bool:
    kid, ksec = _creds()
    return bool(kid and ksec)


def _amount_paise() -> int:
    return int(float(PARAMS.get("razorpay_amount_inr", 3105)) * 100)


def create_payment_link(chat_id: int, description: str = "Qaswa Live Subscription (28 days)") -> dict:
    """
    Fixed-amount payment link (notes me chat_id — webhook isi se subscriber
    pehchanta hai). Not configured → None (caller "contact admin" dikhaye).
    """
    if not is_payment_configured():
        return None
    kid, ksec = _creds()
    try:
        payload = {
            "amount": _amount_paise(),
            "currency": "INR",
            "accept_partial": False,                 # fixed amount — kam-zyada nahi
            "description": description,
            "notes": {"chat_id": str(chat_id)},
            "expire_by": 0,                          # no expiry on link
        }
        resp = requests.post(
            f"{RAZORPAY_API}/payment_links",
            json=payload,
            auth=(kid, ksec),
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            append_log(AUDIT_LOG_FILE, f"PAYMENT LINK FAILED: {resp.status_code} {resp.text[:200]}")
            return None
        data = resp.json()
        links = load_json(PAYMENT_LINKS_FILE, {"links": {}})
        links.setdefault("links", {})[data.get("id")] = {
            "link_id": data.get("id"),
            "chat_id": chat_id,
            "amount": _amount_paise(),
            "status": data.get("status"),
            "short_url": data.get("short_url"),
            "long_url": data.get("long_url"),
            "created_at": now_ist().isoformat(),
        }
        save_json(PAYMENT_LINKS_FILE, links)
        append_log(AUDIT_LOG_FILE, f"PAYMENT LINK CREATED: chat_id={chat_id} link={data.get('id')}")
        return {"link_id": data.get("id"),
                "short_url": data.get("short_url"),
                "long_url": data.get("long_url")}
    except requests.exceptions.RequestException as e:
        append_log(AUDIT_LOG_FILE, f"PAYMENT LINK ERROR: {type(e).__name__}: {e}")
        return None
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"PAYMENT LINK ERROR: {type(e).__name__}: {e}")
        return None


def verify_webhook_signature(body: bytes, signature: str, secret: str = None) -> bool:
    """Razorpay X-Razorpay-Signature = HMAC-SHA256(body, webhook_secret)."""
    secret = secret or os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _activate_subscriber(chat_id: int, payment_id: str) -> str:
    """
    Payment success → plan activate (term-stacking ke saath — purane expiry
    ke baad se counting). Duplicate guard: same payment_id ek baar.
    """
    from subscriber_manager import approve_subscriber, get_subscriber, _notify
    sub = get_subscriber(chat_id)
    if not sub:
        return f"PAYMENT IGNORED: subscriber {chat_id} not found"
    if sub.get("last_payment_id") == payment_id:
        return f"PAYMENT DUPLICATE SKIPPED: {payment_id} (chat_id {chat_id})"
    result = approve_subscriber(chat_id)  # rollover/stacking already handles counting
    if not result.get("success"):
        append_log(AUDIT_LOG_FILE, f"PAYMENT ACTIVATION FAILED {chat_id}: {result.get('message')}")
        return f"ACTIVATION FAILED: {result.get('message')}"
    # duplicate guard record
    from subscriber_manager import _load, _save
    data = _load()
    if str(chat_id) in data["subscribers"]:
        data["subscribers"][str(chat_id)]["last_payment_id"] = payment_id
        _save(data)
    expiry = get_subscriber(chat_id).get("live_expiry", "?")
    _notify(chat_id,
        f"✅ Payment received — ₹{int(PARAMS.get('razorpay_amount_inr', 3105))}\n\n"
        f"Your plan is activated till {expiry}.\n"
        f"(Jaldi renew karne par counting purane expiry ke baad se start hoti hai — koi din waste nahi.)")
    append_log(AUDIT_LOG_FILE, f"PAYMENT ACTIVATED: chat_id={chat_id} payment={payment_id} expiry={expiry}")
    return f"ACTIVATED: chat_id={chat_id} till {expiry}"


def handle_payment_event(event: dict) -> str:
    """
    Webhook event → activate. Expected Razorpay shapes:
      {"event": "payment_link.paid", "payload": {"payment_link": {"entity": {...}}}}
      ya {"event": "payment.captured", "payload": {"payment": {"entity": {"notes": {...}}}}}
    Refund/dispute → status untouched (admin ko alert log).
    """
    try:
        ev = str(event.get("event") or "")
        if ev in ("payment_link.paid", "payment.captured"):
            payload = event.get("payload", {})
            for key in ("payment_link", "payment"):
                ent = (payload.get(key) or {}).get("entity", {}) if isinstance(payload, dict) else {}
                if not isinstance(ent, dict):
                    continue
                notes = ent.get("notes", {}) or {}
                chat_id = notes.get("chat_id")
                if not chat_id:
                    continue
                payment_id = str(ent.get("payment_id") or ent.get("id") or ev)
                return _activate_subscriber(int(chat_id), payment_id)
            return "EVENT IGNORED: no chat_id in notes"
        if "refund" in ev or "dispute" in ev:
            append_log(AUDIT_LOG_FILE, f"PAYMENT REFUND/DISPUTE EVENT: {ev} — manual review")
            return "REFUND_EVENT_LOGGED"
        return f"EVENT IGNORED: {ev}"
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"PAYMENT EVENT ERROR: {type(e).__name__}: {e}")
        return f"EVENT ERROR: {e}"


# ── Lightweight webhook server (config-gated) ──
def start_webhook_server(port: int = None) -> bool:
    """
    Threaded HTTPS-ke-piche HTTP server: POST /razorpay/webhook pe signature
    verify + handle. RAZORPAY_WEBHOOK_PORT env set ho tabhi start hota hai.
    Returns True agar server start hua.
    """
    try:
        port = int(port or os.getenv("RAZORPAY_WEBHOOK_PORT", ""))
        if not port or not is_payment_configured():
            return False
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length)
                    sig = self.headers.get("X-Razorpay-Signature", "")
                    if self.path.rstrip("/") != "/razorpay/webhook":
                        self.send_response(404); self.end_headers(); return
                    if not verify_webhook_signature(body, sig):
                        append_log(AUDIT_LOG_FILE, "PAYMENT WEBHOOK: signature verify FAILED — event rejected")
                        self.send_response(401); self.end_headers(); return
                    event = json.loads(body.decode("utf-8", "ignore") or "{}")
                    result = handle_payment_event(event)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(result.encode())
                except Exception as e:
                    logger.warning(f"PAYMENT WEBHOOK HANDLER ERROR: {type(e).__name__}: {e}")
                    try:
                        self.send_response(500); self.end_headers()
                    except OSError:
                        pass

            def log_message(self, *args):
                pass  # silence default stderr logging

        server = HTTPServer(("0.0.0.0", port), Handler)
        t = threading.Thread(target=server.serve_forever, daemon=True, name="razorpay-webhook")
        t.start()
        append_log(AUDIT_LOG_FILE, f"PAYMENT WEBHOOK SERVER STARTED: port={port}")
        return True
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"PAYMENT WEBHOOK START FAILED: {type(e).__name__}: {e}")
        return False
