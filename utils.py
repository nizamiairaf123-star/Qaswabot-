"""
utils.py — Common utilities: time, formatting, persistence, validation
FIX-08: Timezone lock on startup
FIX-14: NSE Holiday list
FIX-47: Network partition handler
"""

import json
import logging
import os
import pytz
import re
from datetime import datetime, date
from config import MARKET_TIMEZONE, DATA_DIR, AUDIT_LOG_FILE

logger = logging.getLogger(__name__)

IST = pytz.timezone(MARKET_TIMEZONE)

# ─────────────────────────────────────────────
# FIX-14: NSE Holiday List 2025-2026
# ─────────────────────────────────────────────

NSE_HOLIDAYS = {
    # 2025
    "2025-01-26",  # Republic Day
    "2025-02-19",  # Chhatrapati Shivaji Maharaj Jayanti
    "2025-03-14",  # Holi
    "2025-04-14",  # Dr. Ambedkar Jayanti
    "2025-04-18",  # Good Friday
    "2025-05-01",  # Maharashtra Day
    "2025-08-15",  # Independence Day
    "2025-08-27",  # Ganesh Chaturthi
    "2025-10-02",  # Gandhi Jayanti
    "2025-10-24",  # Dussehra
    "2025-11-05",  # Diwali Laxmi Puja
    "2025-11-14",  # Diwali Balipratipada
    "2025-11-26",  # Gurunanak Jayanti
    "2025-12-25",  # Christmas
    # 2026
    "2026-01-26",  # Republic Day
    "2026-03-03",  # Holi
    "2026-03-20",  # Gudi Padwa
    "2026-04-03",  # Good Friday
    "2026-04-14",  # Dr. Ambedkar Jayanti
    "2026-05-01",  # Maharashtra Day
    "2026-08-15",  # Independence Day
    "2026-10-02",  # Gandhi Jayanti
    "2026-11-11",  # Diwali
    "2026-12-25",  # Christmas
}

# Years this static list actually covers — used below to fail LOUD
# (Telegram alert) instead of silently treating a new year's holidays
# as trading days once this list runs out. No live NSE calendar fetch
# is used: NSE's own endpoints are known to block datacenter IPs (see
# asm_gsm_screen.py) — refresh this set by hand each Nov/Dec.
_NSE_HOLIDAY_COVERAGE_YEARS = {int(d[:4]) for d in NSE_HOLIDAYS}

# Special/non-standard session timings — e.g. Diwali Muhurat trading,
# or any date NSE announces a different open/close than 09:15-15:30.
# Maintain alongside NSE_HOLIDAYS. Format: "YYYY-MM-DD": ("HH:MM", "HH:MM")
NSE_SPECIAL_SESSIONS = {
    # "2026-11-08": ("18:15", "19:15"),  # example: Diwali Muhurat trading
}

_last_holiday_coverage_warning_date = None


def _warn_if_holiday_list_stale():
    """Fire at most one ERROR log (-> Telegram alert) per day once the
    static NSE_HOLIDAYS/NSE_SPECIAL_SESSIONS lists no longer cover the
    current year, so this degrades loudly instead of silently."""
    global _last_holiday_coverage_warning_date
    today = today_ist()
    if today.year not in _NSE_HOLIDAY_COVERAGE_YEARS and _last_holiday_coverage_warning_date != today:
        _last_holiday_coverage_warning_date = today
        logger.error(
            f"NSE_HOLIDAYS/NSE_SPECIAL_SESSIONS in utils.py do not cover "
            f"{today.year} - this year's holidays will NOT be detected "
            f"(treated as normal trading days). Refresh both lists with "
            f"{today.year}'s official NSE calendar before relying on them."
        )


# ─────────────────────────────────────────────
# FIX-08: Timezone Verification
# ─────────────────────────────────────────────

def verify_timezone():
    """
    FIX-08: Verify system timezone is IST.
    Bot should not start if timezone is wrong.
    """
    import subprocess
    try:
        result = subprocess.run(
            ["timedatectl", "show", "--property=Timezone", "--value"],
            capture_output=True, text=True, timeout=5
        )
        tz = result.stdout.strip()
        if tz not in ("Asia/Kolkata", "IST"):
            raise SystemError(
                f"TIMEZONE ERROR: System timezone is '{tz}'. "
                f"Set IST before running: timedatectl set-timezone Asia/Kolkata"
            )
    except FileNotFoundError as e:
        # Production safety: an unavailable timezone verification command is
        # not evidence that the clock is correct.  Fail closed instead of
        # silently starting with an unknown timezone.
        raise SystemError(
            "TIMEZONE VERIFICATION UNAVAILABLE: timedatectl is required for "
            "production startup; refusing to continue with unknown timezone"
        ) from e


# ─────────────────────────────────────────────
# TIME UTILITIES
# ─────────────────────────────────────────────

def now_ist() -> datetime:
    return datetime.now(IST)


def today_ist() -> date:
    return now_ist().date()


def is_market_open() -> bool:
    """
    FIX-14: Check market hours + NSE holidays + any special-session
    override (e.g. Muhurat trading). Called before every scheduled job.
    """
    n = now_ist()
    _warn_if_holiday_list_stale()

    # Weekend check
    if n.weekday() >= 5:
        return False

    today_str = today_ist().isoformat()

    # NSE Holiday check
    if today_str in NSE_HOLIDAYS:
        return False

    special = NSE_SPECIAL_SESSIONS.get(today_str)
    if special:
        open_h, open_m = (int(x) for x in special[0].split(":"))
        close_h, close_m = (int(x) for x in special[1].split(":"))
    else:
        open_h, open_m = 9, 15
        close_h, close_m = 15, 30

    market_open  = n.replace(hour=open_h,  minute=open_m,  second=0, microsecond=0)
    market_close = n.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
    return market_open <= n <= market_close


def is_trading_day() -> bool:
    """Check if today is a trading day (not weekend, not holiday).

    [AUDIT note, 2026-09-17] Unused dead code — no caller anywhere in the
    codebase (is_market_open() is the function actually used everywhere
    for this check). The holiday-list logic here is correct (see F13 fix
    history), but it currently has zero real effect since nothing calls
    it. Kept for potential future use; not wired into any live path.
    """
    n = now_ist()
    _warn_if_holiday_list_stale()
    if n.weekday() >= 5:
        return False
    if today_ist().isoformat() in NSE_HOLIDAYS:
        return False
    return True


def minutes_since(dt: datetime) -> float:
    return (now_ist() - dt).total_seconds() / 60


# ─────────────────────────────────────────────
# FILE PERSISTENCE (crash-safe JSON)
# ─────────────────────────────────────────────

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


from database import db_save, db_load

def load_json(filepath: str, default=None):
    """Load JSON safely. Migrated to SQLite key-value store."""
    key = os.path.basename(filepath)
    # Check if legacy file exists and migrate it
    if os.path.exists(filepath) and not filepath.endswith(".migrated"):
        try:
            with open(filepath, "r") as f:
                content = f.read().strip()
                if content:
                    f.seek(0)
                    legacy_data = json.load(f)
                    saved_ok = db_save(key, legacy_data)
                    if saved_ok:
                        os.rename(filepath, filepath + ".migrated")
                        logging.info(f"Migrated {filepath} to SQLite.")
                    else:
                        logging.error(
                            f"Migration: db_save failed for {filepath} -- "
                            f"keeping legacy file in place (not renamed) so it "
                            f"can be retried, instead of losing the only copy of this data."
                        )
                    return legacy_data
        except (json.JSONDecodeError, IOError) as e:
            logging.warning(f"Migration: Failed to load {filepath}: {e}")
            
    return db_load(key, default)

def save_json(filepath: str, data):
    """Save JSON atomically. Migrated to SQLite key-value store."""
    key = os.path.basename(filepath)
    db_save(key, data)


def append_log(filepath: str, line: str):
    ensure_data_dir()
    with open(filepath, "a") as f:
        f.write(f"{now_ist().isoformat()} | {redact_secrets(line)}\n")


# ─────────────────────────────────────────────
# FORMATTING
# ─────────────────────────────────────────────

def fmt_inr(amount: float) -> str:
    return f"Rs.{amount:,.2f}"


def fmt_pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def fmt_datetime(dt: datetime) -> str:
    return dt.strftime("%d-%b-%Y %H:%M IST")


# ─────────────────────────────────────────────
# SAFE-DIV (AI-DOS LOGIC-001 remediation, 2026-09-17)
# Single-sourced zero-check for every division site flagged by the
# static-analysis pass, instead of a bespoke guard per call-site.
# ─────────────────────────────────────────────

def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Division that returns `default` instead of raising ZeroDivisionError
    when denominator is 0, None, or NaN. Never silently changes a genuine
    non-zero-division result."""
    try:
        if denominator in (0, 0.0, None):
            return default
        result = numerator / denominator
        if result != result:  # NaN check without importing math
            return default
        return result
    except (TypeError, ZeroDivisionError):
        return default


# ─────────────────────────────────────────────
# SECRET REDACTION (2026-09-20, owner request: non-technical owner pastes
# terminal/journalctl output directly into AI chats — this is a defensive
# safety-net so a credential/IP can never appear in anything this bot
# prints or logs, even from a future/unforeseen error-message leak, not
# just the known .env variable names.)
# ─────────────────────────────────────────────

_REDACT_PATTERNS = [
    # Telegram bot token: "<8-10 digits>:<35 char secret>"
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"), "[REDACTED_TELEGRAM_TOKEN]"),
    # Generic "Bearer <token>" auth headers (Dhan/Razorpay/webhook calls)
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-_.]{15,}"), "Bearer [REDACTED_TOKEN]"),
    # JWT-shaped tokens (three base64url segments separated by dots) — Dhan
    # access tokens are JWTs
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "[REDACTED_JWT]"),
    # Any identifier ending in KEY/TOKEN/SECRET/PASSWORD, where the suffix
    # is either the whole word or immediately preceded by an underscore
    # (SNAKE_CASE prefix segments only, e.g. TELEGRAM_BOT_TOKEN,
    # DHAN_ACCESS_TOKEN, RAZORPAY_KEY_SECRET, or the bare word token=/key=)
    # — followed by =/: and a value. `(?:[A-Za-z0-9]+_)*` requires each
    # prefix segment to end in a literal underscore, so an ordinary word
    # that merely ends in those letters (monkey, turkey, hockey) can never
    # match — there's no underscore for the prefix-group to consume.
    (re.compile(r"(?i)\b((?:[A-Za-z0-9]+_)*(?:KEY|TOKEN|SECRET|PASSWORD))\b\s*[=:]\s*\S+"),
     r"\1=[REDACTED]"),
    # Fernet-style 44-char base64 key ending in '='
    (re.compile(r"\b[A-Za-z0-9_-]{43}=\b"), "[REDACTED_KEY]"),
    # IPv4 addresses
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED_IP]"),
]


def redact_secrets(text: str) -> str:
    """Mask credential-shaped and IP-shaped substrings in `text` before it
    is logged or printed. Defensive/best-effort — matches known secret
    SHAPES (token formats, KEY=value patterns, IPv4), not a specific
    allowlist of this project's own env vars, so it also catches leaks
    this project didn't anticipate. Never raises — a redaction failure
    must never crash the caller; on any internal error, returns the
    original text unmodified rather than silently dropping the log line."""
    try:
        out = str(text)
        for pattern, replacement in _REDACT_PATTERNS:
            out = pattern.sub(replacement, out)
        return out
    except Exception:
        return text


class RedactingFormatter(logging.Formatter):
    """Drop-in replacement for logging.Formatter that redacts secrets from
    the final formatted line (message + any %-args + exception text) before
    it reaches a handler (console/journalctl/file)."""

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return redact_secrets(formatted)


def install_redacting_log_formatter(fmt: str = "%(asctime)s %(levelname)s %(name)s: %(message)s"):
    """Call once at process startup (bot.py's main(), and any standalone
    entry point) so every logger.info/warning/error/exception call across
    the whole app is redacted before it reaches stderr/journalctl — not
    just the ones this project's own code writes via append_log()."""
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter(fmt))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


def install_redacting_excepthook():
    """Call once at process startup, alongside install_redacting_log_formatter().
    An UNCAUGHT exception (one no try/except anywhere catches) is printed by
    Python's own default crash handler directly to stderr — this completely
    bypasses both append_log() and the logging.Formatter above, since it
    never goes through the `logging` module at all. This installs a
    replacement sys.excepthook that redacts the formatted traceback text
    before printing it, so even a crash's error message (which could
    embed a URL/token from an underlying library's exception string)
    can't leak a secret to journalctl."""
    import sys
    import traceback

    def _redacting_excepthook(exc_type, exc_value, exc_tb):
        formatted = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        sys.stderr.write(redact_secrets(formatted))

    sys.excepthook = _redacting_excepthook


# ─────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────

def is_valid_token(token_data: dict) -> bool:
    return bool(token_data.get("access_token") and token_data.get("client_id"))


def is_positive_number(value) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


# ─────────────────────────────────────────────
# KILLSWITCH
# ─────────────────────────────────────────────

def is_killswitch_active() -> bool:
    from config import KILLSWITCH_FILE
    from database import is_db_failure_recent
    data = load_json(KILLSWITCH_FILE, {"active": False})
    # [PHD-FIX Section-47] A genuine DB read failure right at this call would
    # otherwise silently resolve to {"active": False} — the exact opposite
    # of what an emergency stop must do. If db_load just recorded a failure
    # (vs. this key genuinely never having been set), fail CLOSED: treat the
    # killswitch as ACTIVE so trading halts rather than silently continuing
    # through an unreadable emergency-stop state.
    if is_db_failure_recent(within_seconds=30):
        logger.error("is_killswitch_active: DB read just failed — failing CLOSED (treating killswitch as ACTIVE)")
        return True
    return data.get("active", False)


def set_killswitch(state: bool):
    from config import KILLSWITCH_FILE
    save_json(KILLSWITCH_FILE, {
        "active":  state,
        "updated": now_ist().isoformat()
    })


# ─────────────────────────────────────────────
# TRADING DAY COUNTER
# ─────────────────────────────────────────────

def trading_days_between(start: date, end: date) -> int:
    """Count trading days (Mon-Fri, excluding holidays) between dates."""
    from datetime import timedelta
    count   = 0
    current = start
    while current < end:
        if current.weekday() < 5 and current.isoformat() not in NSE_HOLIDAYS:
            count += 1
        current += timedelta(days=1)
    return count


# ─────────────────────────────────────────────
# FIX-47: Network Partition Handler
# ─────────────────────────────────────────────

NETWORK_STATE_FILE = "data/network_state.json"


def record_heartbeat_success():
    save_json(NETWORK_STATE_FILE, {
        "last_success": now_ist().isoformat(),
        "partition_detected": False,
    })


def record_heartbeat_failure():
    data = load_json(NETWORK_STATE_FILE, {"last_success": None, "partition_detected": False})
    if data.get("last_success"):
        from datetime import datetime
        last = datetime.fromisoformat(data["last_success"])
        gap  = (now_ist().replace(tzinfo=None) - last.replace(tzinfo=None)).total_seconds()
        if gap > 120:  # 2 min continuous failure
            if not data.get("partition_detected"):
                data["partition_detected"] = True
                data["partition_start"]    = now_ist().isoformat()
                save_json(NETWORK_STATE_FILE, data)
                append_log(AUDIT_LOG_FILE, "NETWORK_PARTITION_DETECTED")
                # Set reconciliation flag
                save_json("data/needs_reconciliation.json", {
                    "flag":     True,
                    "detected": now_ist().isoformat()
                })


def is_network_partition() -> bool:
    data = load_json(NETWORK_STATE_FILE, {"partition_detected": False})
    return data.get("partition_detected", False)


def clear_network_partition():
    data = load_json(NETWORK_STATE_FILE, {})
    data["partition_detected"] = False
    data["cleared_at"]         = now_ist().isoformat()
    save_json(NETWORK_STATE_FILE, data)
    # Clear reconciliation flag
    save_json("data/needs_reconciliation.json", {"flag": False})
    append_log(AUDIT_LOG_FILE, "NETWORK_PARTITION: Cleared — reconciliation will run")


def calculate_dhan_friction(trade_value: float, is_intraday: bool = True) -> float:
    """
    Dhan Exact Real-World Brokerage + Statutory Taxes Calculator

    `trade_value` = ONE LEG value (qty * price for a single buy or sell —
    matches the call site: trade_val = qty * entry_price). Every line below
    must use this same convention consistently.

    [AUDIT FIX 2026-08-31] Found 2 real, currently-LIVE cost-underestimation
    bugs (STT delivery was missing the buy-side leg entirely; stamp duty was
    incorrectly halved) plus 1 latent bug in the currently-unused intraday
    branch (STT was also incorrectly halved). All stemmed from inconsistent
    treatment of what `trade_value` represents across lines — brokerage
    already used the correct one-leg convention, the other three didn't.
    STT rates verified against current published rates (delivery: 0.1% on
    BOTH buy and sell sides; intraday: 0.025% sell-side only) — confirmed
    via multiple independent sources, unchanged as of Budget 2026.
    """
    if trade_value <= 0:
        return 0.0

    # 1. Dhan Brokerage:
    #    [PHD-FIX Section-10 provenance] Delivery brokerage is ₹0 — verified
    #    against 8+ current published sources (incl. Dhan's own pricing
    #    page), true continuously since Dhan's 2021 launch, not a recent
    #    change. The ₹20-or-0.03%-per-side (max ₹40) rate below is Dhan's
    #    INTRADAY rate and was previously being applied to delivery trades
    #    too — this bot trades delivery/CNC only (is_intraday=False at its
    #    one real call site), so that was a genuine EXTERNAL_FACT error,
    #    not a legitimate simplification.
    brokerage = 0.0 if not is_intraday else min(40.0, trade_value * 0.0006)

    # 2. STT (Securities Transaction Tax):
    #    Delivery: 0.1% on BOTH buy and sell sides (0.2% round-trip total)
    #    Intraday: 0.025% on sell side ONLY (trade_value already = one leg,
    #    no halving needed)
    stt = (trade_value * 0.00025) if is_intraday else (trade_value * 0.001 * 2)

    # 3. NSE Exchange Turnover Charges: 0.00345%
    turnover_charge = trade_value * 0.0000345

    # 4. GST: 18% on (Brokerage + Exchange Charges)
    gst = (brokerage + turnover_charge) * 0.18

    # 5. Stamp Duty: 0.003% on Buy side only (trade_value already = one leg)
    stamp_duty = trade_value * 0.00003

    total_friction = brokerage + stt + turnover_charge + gst + stamp_duty
    return total_friction
