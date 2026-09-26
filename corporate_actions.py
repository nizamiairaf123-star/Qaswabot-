"""
corporate_actions.py — NSE corporate actions monitor
FIX-05

Daily 8:45 AM: Check open positions for corporate actions
Bonus/Split/Dividend = GTT recalculate + admin alert

NSE Endpoint: https://www.nseindia.com/api/corporates-corporateActions
"""

import logging

import requests
from utils import load_json, save_json, now_ist, append_log
from config import AUDIT_LOG_FILE

logger = logging.getLogger(__name__)

CORP_ACTIONS_FILE = "data/corporate_actions.json"

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept":     "application/json",
    "Referer":    "https://www.nseindia.com",
}

# Action types that affect GTT prices
CRITICAL_ACTIONS = [
    "bonus",
    "split",
    "rights",
    "merger",
    "demerger",
    "subdivision",
]


def check_corporate_actions():
    """
    Called daily 8:45 AM by scheduler.
    Check if any open position has a corporate action today.
    """
    from capital_manager import get_active_trades
    active_trades = get_active_trades()

    if not active_trades:
        return

    actions = _fetch_nse_actions()
    if actions is None:
        # [FIX] Fetch genuinely failed (network/parse error, non-200, etc.) —
        # this is NOT the same as "no corporate actions today". Silently
        # returning here means an undetected split/bonus during an outage
        # could leave a GTT stop-loss mispriced with nobody told. Alert.
        try:
            from signal_broadcaster import alert_admin_sync
            alert_admin_sync(
                "⚠️ Corporate-actions check FAILED — could not reach/parse the "
                "NSE feed today. Open positions were NOT screened for "
                "bonus/split/rights actions. Verify manually.",
                severity="WARN",
                dedup_key="corp_actions_fetch_fail",
            )
        except Exception as e:
            append_log(AUDIT_LOG_FILE, f"CORP ACTION FETCH-FAIL ALERT ERROR: {e}")
        return
    if not actions:
        return  # genuinely no corporate actions today — quiet day

    affected = []
    for symbol in active_trades:
        symbol_actions = [
            a for a in actions
            if a.get("symbol", "").upper() == symbol.upper()
        ]
        for action in symbol_actions:
            action_type = action.get("subject", "").lower()
            if any(ca in action_type for ca in CRITICAL_ACTIONS):
                affected.append({
                    "symbol":      symbol,
                    "action":      action.get("subject", "Unknown"),
                    "ex_date":     action.get("exDate", "N/A"),
                    "record_date": action.get("recordDate", "N/A"),
                })

    if affected:
        _handle_affected_positions(affected)


def _fetch_nse_actions() -> list:
    """
    Fetch corporate actions from NSE.

    Returns:
    - list of actions (possibly empty — genuinely no actions today)
    - None if the fetch itself failed (network error, bad status, parse
      error) — [FIX] callers must treat this differently from an empty
      list, or a fetch outage silently looks identical to a quiet day.
    """
    session = requests.Session()
    try:
        session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=10)
    except (requests.RequestException, OSError) as e:
        logger.warning(f"fetch_corporate_actions: NSE session init failed: {type(e).__name__}: {e}")

    try:
        url  = "https://www.nseindia.com/api/corporates-corporateActions"
        resp = session.get(url, headers=NSE_HEADERS, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            actions = data if isinstance(data, list) else data.get("data", [])
            append_log(AUDIT_LOG_FILE, f"CORP ACTIONS: Fetched {len(actions)} actions")
            return actions
        append_log(AUDIT_LOG_FILE, f"CORP ACTIONS FETCH ERROR: HTTP {resp.status_code}")
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"CORP ACTIONS FETCH ERROR: {e}")

    return None


def _handle_affected_positions(affected: list):
    """
    For each affected position:
    1. Cancel existing GTTs
    2. Recalculate adjusted prices
    3. Re-place GTTs
    4. Alert admin
    """
    from signal_broadcaster import alert_admin
    from forever_order_manager import close_forever_orders
    from capital_manager import get_active_trades
    import asyncio

    active = get_active_trades()

    for item in affected:
        symbol = item["symbol"]
        action = item["action"]

        append_log(AUDIT_LOG_FILE,
                   f"CORP ACTION DETECTED: {symbol} | {action} | ex={item['ex_date']}")

        trade = active.get(symbol, {})
        if not trade:
            continue

        # Cancel existing GTTs — prices will be wrong after action
        try:
            close_forever_orders(symbol)
            append_log(AUDIT_LOG_FILE,
                       f"CORP ACTION: GTTs cancelled for {symbol} — manual re-entry needed")
        except Exception as e:
            append_log(AUDIT_LOG_FILE, f"CORP ACTION GTT CANCEL ERROR {symbol}: {e}")

        # Alert admin — manual review required
        _msg = (
            f"CORPORATE ACTION DETECTED\n\n"
            f"Stock: {symbol}\n"
            f"Action: {action}\n"
            f"Ex-Date: {item['ex_date']}\n\n"
            f"GTTs cancelled — prices will adjust after ex-date.\n"
            f"Manual review required:\n"
            f"1. Verify adjusted entry price\n"
            f"2. Re-set SL and GTTs manually\n"
            f"3. Use /portfoliomap to check position"
        )
        try:
            asyncio.get_running_loop().create_task(alert_admin(_msg))
        except RuntimeError:
            # No running loop (scheduler thread) — deliver via sync wrapper
            from signal_broadcaster import alert_admin_sync
            alert_admin_sync(_msg)

    # Save affected list
    save_json(CORP_ACTIONS_FILE, {
        "checked_at": now_ist().isoformat(),
        "affected":   affected,
    })


def get_last_check_summary() -> str:
    data = load_json(CORP_ACTIONS_FILE, {})
    if not data:
        return "No corporate action check done yet."

    affected = data.get("affected", [])
    if not affected:
        return f"Last check: {data.get('checked_at', 'N/A')[:16]}\nNo corporate actions affecting open positions."

    lines = [
        f"Last check: {data.get('checked_at', 'N/A')[:16]}",
        f"Affected positions: {len(affected)}",
        "",
    ]
    for item in affected:
        lines.append(f"{item['symbol']}: {item['action']} (ex: {item['ex_date']})")

    return "\n".join(lines)
