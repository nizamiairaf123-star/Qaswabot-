"""
sebi_manager.py — Sell-proceeds fund blocking (rule-change ready)
Current rule (SEBI change effective 7 Oct 2024; Dhan Risk Management Policy):
100% of delivery sell credit usable same day → default block = 0.
Mechanism intact: agar rule wapas badle to sebi_release_pct (config) set karke
80/20 ya koi bhi split wapas enable ho jayega.
"""

from utils import load_json, save_json, today_ist
from config import SEBI_BLOCKED_FILE, PARAMS, AUDIT_LOG_FILE
from utils import append_log


def block_funds_after_sell(symbol: str, sell_value: float):
    """
    After selling, block T+1 portion.
    sebi_release_pct% available same day, rest next trading day.
    v3.1.2: default 100% (SEBI Oct-2024 change; Dhan policy confirms 100%
    same-day usable) → blocked=0 → no-op. Mechanism future rule-changes ke
    liye intact hai.
    """
    release_pct = PARAMS["sebi_release_pct"] / 100
    blocked_pct = 1 - release_pct
    blocked_amount = sell_value * blocked_pct

    if blocked_amount <= 0.0:
        # 100% same-day usable (current Dhan/SEBI rule) — kuch block nahi
        append_log(AUDIT_LOG_FILE,
                   f"SEBI NO-BLOCK: {symbol} sell={sell_value:.2f} — 100% same-day usable (post-Oct-2024 rule)")
        return

    data = load_json(SEBI_BLOCKED_FILE, {"blocked": []})
    data["blocked"].append({
        "symbol": symbol,
        "amount": blocked_amount,
        "sell_date": today_ist().isoformat(),
        "release_date": _next_trading_day(today_ist()).isoformat()
    })
    save_json(SEBI_BLOCKED_FILE, data)
    append_log(AUDIT_LOG_FILE,
               f"SEBI BLOCKED: {symbol} amount={blocked_amount:.2f} release={_next_trading_day(today_ist())}")


def release_due_funds():
    """
    Called every morning — release funds whose release_date has passed.
    """
    from datetime import date
    today = today_ist()
    data = load_json(SEBI_BLOCKED_FILE, {"blocked": []})
    before = len(data["blocked"])
    data["blocked"] = [
        item for item in data["blocked"]
        if date.fromisoformat(item["release_date"]) > today
    ]
    released = before - len(data["blocked"])
    save_json(SEBI_BLOCKED_FILE, data)
    if released > 0:
        append_log(AUDIT_LOG_FILE, f"SEBI RELEASED: {released} entries released today")


def get_blocked_summary() -> str:
    data = load_json(SEBI_BLOCKED_FILE, {"blocked": []})
    if not data["blocked"]:
        return "✅ No SEBI blocked funds."
    lines = ["📋 *SEBI Blocked Funds:*"]
    total = 0
    for item in data["blocked"]:
        lines.append(f"• {item['symbol']}: ₹{item['amount']:.2f} (releases {item['release_date']})")
        total += item["amount"]
    lines.append(f"\n*Total Blocked:* ₹{total:.2f}")
    return "\n".join(lines)


def _next_trading_day(from_date) -> object:
    from datetime import timedelta
    from utils import NSE_HOLIDAYS
    d = from_date + timedelta(days=1)
    while d.weekday() >= 5 or d.isoformat() in NSE_HOLIDAYS:  # Skip weekends and holidays
        d += timedelta(days=1)
    return d
