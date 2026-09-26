"""
signal_broadcaster.py — Telegram message sending
Admin alerts + subscriber notifications
"""

import logging
try:
    from telegram import Bot
    from telegram.constants import ParseMode
    HAS_TELEGRAM = True
except ImportError:
    Bot = None
    ParseMode = None
    HAS_TELEGRAM = False
from config import TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID
from utils import load_json
from config import SUBSCRIBERS_FILE

logger = logging.getLogger(__name__)


_bot = None


def get_bot() -> Bot:
    global _bot
    if not HAS_TELEGRAM:
        raise RuntimeError("python-telegram-bot is unavailable")
    if _bot is None:
        _bot = Bot(token=TELEGRAM_BOT_TOKEN)
    return _bot


# v5.0 ALERT TAXONOMY: severity + dedup (alert fatigue block — important
# alert miss nahi hona chahiye). CRITICAL = hamesha bhejta hai; INFO/WARN
# same dedup_key pe din me ek baar.
ALERT_SEVERITIES = ("INFO", "WARN", "CRITICAL")
_ALERT_DEDUP_FILE = "data/alert_dedup.json"


def _should_send_alert(severity: str, dedup_key: str) -> bool:
    if severity == "CRITICAL" or not dedup_key:
        return True
    from utils import load_json, save_json, today_ist
    data = load_json(_ALERT_DEDUP_FILE, {"days": {}})
    day = today_ist().isoformat()
    sent = data.setdefault("days", {}).get(day, [])
    if dedup_key in sent:
        return False
    sent.append(dedup_key)
    data["days"] = {k: v for k, v in data["days"].items() if k >= day}  # sirf aaj retain
    save_json(_ALERT_DEDUP_FILE, data)
    return True


async def alert_admin(message: str, severity: str = "INFO", dedup_key: str = None):
    """Send message to admin (v5.0: severity + daily dedup)."""
    if severity not in ALERT_SEVERITIES:
        severity = "INFO"
    if not _should_send_alert(severity, dedup_key):
        return
    prefix = {"CRITICAL": "🚨 CRITICAL\n", "WARN": "⚠️ WARNING\n"}.get(severity, "")
    try:
        await get_bot().send_message(
            chat_id=ADMIN_CHAT_ID,
            text=prefix + message,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        from utils import append_log
        from config import AUDIT_LOG_FILE
        append_log(AUDIT_LOG_FILE, f"ALERT ADMIN FAILED: {e}")


async def notify_subscriber(chat_id: int, message: str):
    """Send message to one subscriber."""
    try:
        await get_bot().send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN
        )
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"send_message: Failed to send to {chat_id}: {type(e).__name__}: {e}")


async def broadcast_to_all(message: str, active_only: bool = True):
    """
    Send message to all (active) subscribers.
    Used for trade signals, reports.
    """
    subs = load_json(SUBSCRIBERS_FILE, {"subscribers": {}})
    for chat_id_str, sub in subs.get("subscribers", {}).items():
        if active_only and sub.get("status") != "LIVE_ACTIVE":
            continue
        await notify_subscriber(int(chat_id_str), message)


async def broadcast_trade_signal(symbol: str, action: str, entry_price: float,
                                  sl_price: float, tp1_price: float, reason: str):
    """Signal-only subscribers get this (no Dhan linked)."""
    emoji = "🟢" if action == "BUY" else "🔴"
    msg = (
        f"{emoji} *{action} Signal — {symbol}*\n"
        f"Entry: ₹{entry_price:.2f}\n"
        f"SL: ₹{sl_price:.2f}\n"
        f"TP1: ₹{tp1_price:.2f}\n"
        f"Reason: _{reason}_"
    )
    await broadcast_to_all(msg)


async def broadcast_exit(symbol: str, exit_price: float,
                          pnl: float, exit_reason: str):
    emoji = "✅" if pnl >= 0 else "❌"
    from utils import fmt_inr
    msg = (
        f"{emoji} *EXIT — {symbol}*\n"
        f"Price: ₹{exit_price:.2f}\n"
        f"P&L: {fmt_inr(pnl)}\n"
        f"Reason: _{exit_reason}_"
    )
    await broadcast_to_all(msg)


def alert_admin_sync(message: str, severity: str = "INFO", dedup_key: str = None):
    """Non-blocking sync wrapper — spawns a background thread with httpx to prevent blocking."""
    import threading
    if severity not in ALERT_SEVERITIES:
        severity = "INFO"
    if not _should_send_alert(severity, dedup_key):
        return
    prefix = {"CRITICAL": "🚨 CRITICAL\n", "WARN": "⚠️ WARNING\n"}.get(severity, "")
    message = prefix + message
    # Resolve the audit path at call time.  This is critical for test sandboxes:
    # the background thread may outlive pytest's temporary cwd and otherwise
    # write to the release tree after pytest_sessionfinish restores cwd.
    import os
    from config import AUDIT_LOG_FILE
    _audit_log_path = os.path.abspath(AUDIT_LOG_FILE)
    def _send():
        try:
            from config import TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID
            import httpx
            with httpx.Client(timeout=30.0) as client:
                # P1-004 [r38 verified fix]: httpx does not raise on a
                # non-2xx response by itself — an unchecked .post() call
                # here previously treated a 401/403/429/5xx Telegram
                # rejection as a silent success. raise_for_status() makes
                # any non-2xx response fall into the existing except
                # branch below (local audit-log record), same as a
                # network exception already does.
                resp = client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": ADMIN_CHAT_ID, "text": message}
                )
                resp.raise_for_status()
        except Exception as e:
            try:
                from utils import append_log
                append_log(_audit_log_path, f"ALERT_SYNC BG FAILED: {e}")
            except Exception as log_e:
                # Notification failure must never create an unhandled background
                # exception or affect trading safety.
                logger.warning("ALERT_SYNC logging failed: %s", log_e)

    threading.Thread(target=_send, daemon=True).start()


def notify_subscriber_sync(chat_id: int, message: str):
    """Non-blocking sync wrapper for one subscriber — mirrors alert_admin_sync.
    Spawns a background thread with httpx so scheduler-thread callers (no running
    event loop) can still deliver the notification instead of dropping it."""
    import threading
    import os
    from config import AUDIT_LOG_FILE
    _audit_log_path = os.path.abspath(AUDIT_LOG_FILE)
    def _send():
        try:
            from config import TELEGRAM_BOT_TOKEN
            import httpx
            with httpx.Client(timeout=30.0) as client:
                client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": message}
                )
        except Exception as e:
            try:
                from utils import append_log
                append_log(_audit_log_path, f"NOTIFY_SYNC BG FAILED: {e}")
            except Exception as log_e:
                logger.warning("NOTIFY_SYNC logging failed: %s", log_e)

    threading.Thread(target=_send, daemon=True).start()


def broadcast_to_all_sync(message: str, active_only: bool = True):
    """Sync mirror of broadcast_to_all — sends via notify_subscriber_sync so
    callers without a running event loop still reach every eligible subscriber."""
    subs = load_json(SUBSCRIBERS_FILE, {"subscribers": {}})
    for chat_id_str, sub in subs.get("subscribers", {}).items():
        if active_only and sub.get("status") != "LIVE_ACTIVE":
            continue
        notify_subscriber_sync(int(chat_id_str), message)
