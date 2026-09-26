"""
trade_logger.py — Trade logging, audit journal, reports
Every decision logged with REASON
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from utils import load_json, save_json, now_ist, today_ist, fmt_inr, fmt_pct
from config import TRADES_FILE, AUDIT_LOG_FILE
from datetime import date

logger = logging.getLogger(__name__)

# GATE 14: bounded audit-log handler. The existing QASWA audit-log path is
# preserved; trade_logger audit events are written through this rotating
# handler so the file cannot grow without bound from this module.
_AUDIT_ROTATING_LOGGER = logging.getLogger("QASWA_TRADE_AUDIT_ROTATING")
_AUDIT_ROTATING_LOGGER.setLevel(logging.INFO)
_AUDIT_ROTATING_LOGGER.propagate = False

def _configure_rotating_audit_logger():
    os.makedirs(os.path.dirname(AUDIT_LOG_FILE) or ".", exist_ok=True)
    expected = os.path.abspath(AUDIT_LOG_FILE)
    for handler in list(_AUDIT_ROTATING_LOGGER.handlers):
        if isinstance(handler, RotatingFileHandler) and os.path.abspath(handler.baseFilename) == expected:
            return
        _AUDIT_ROTATING_LOGGER.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    handler = RotatingFileHandler(
        AUDIT_LOG_FILE,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    _AUDIT_ROTATING_LOGGER.addHandler(handler)


def _append_rotating_audit_log(line: str):
    _configure_rotating_audit_logger()
    _AUDIT_ROTATING_LOGGER.info(f"{now_ist().isoformat()} | {line}")


_configure_rotating_audit_logger()


def _current_execution_environment() -> str:
    """Return PAPER/LIVE from the formal bot state; unknown is fail-loud.
    This is metadata only and never controls order execution.
    """
    try:
        from bot_state_manager import get_state
        state = get_state()
        if state == "PAPER":
            return "PAPER"
        if state in ("LIVE_STAGED", "LIVE_FULL"):
            return "LIVE"
    except Exception:
        pass
    return "UNKNOWN"


# ─────────────────────────────────────────────
# TRADE LOG
# ─────────────────────────────────────────────

def log_trade_entry(symbol: str, qty: int, entry_price: float,
                    sl_price: float, tp1_price: float, reason: str,
                    execution_environment: str = None):
    data = load_json(TRADES_FILE, {"trades": []})
    trade = {
        "id": _next_id(data),
        "symbol": symbol,
        "action": "BUY",
        "qty": qty,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp1_price": tp1_price,
        "entry_time": now_ist().isoformat(),
        "exit_price": None,
        "exit_time": None,
        "pnl": None,
        "pnl_pct": None,
        "exit_reason": None,
        "status": "OPEN",
        "reason": reason,
        "execution_environment": execution_environment or _current_execution_environment(),
    }
    data["trades"].append(trade)
    save_json(TRADES_FILE, data)
    _append_rotating_audit_log(f"BUY {symbol}: qty={qty} price={entry_price} SL={sl_price} | {reason}")


def log_trade_exit(symbol: str, exit_price: float, exit_reason: str):
    data = load_json(TRADES_FILE, {"trades": []})
    for trade in reversed(data["trades"]):
        if trade["symbol"] == symbol and trade["status"] == "OPEN":
            trade["exit_price"] = exit_price
            trade["exit_time"] = now_ist().isoformat()
            trade["exit_reason"] = exit_reason
            trade["status"] = "CLOSED"

            # P&L calculation (with trading cost)
            from config import PARAMS
            cost_pct = PARAMS["trading_cost_pct"] / 100
            gross_pnl = (exit_price - trade["entry_price"]) * trade["qty"]
            cost = trade["entry_price"] * trade["qty"] * cost_pct
            trade["pnl"] = round(gross_pnl - cost, 2)
            trade["pnl_pct"] = round(
                (exit_price - trade["entry_price"]) / trade["entry_price"] * 100 - (cost_pct * 100), 2
            )
            break

    save_json(TRADES_FILE, data)

    # Find the trade we just closed for logging
    closed = next((t for t in reversed(data["trades"])
                   if t["symbol"] == symbol and t["status"] == "CLOSED"), None)
    if closed:
        _append_rotating_audit_log(
            f"SELL {symbol}: price={exit_price} pnl={closed['pnl']} | {exit_reason}")

        # Record in safety manager
        from safety_manager import record_trade_pnl, record_sl_hit
        record_trade_pnl(closed["pnl"], symbol=symbol)   # symbol → per-stock WR threshold (decision #5)
        if "SL" in exit_reason.upper():
            record_sl_hit()

        # SEBI blocking
        from sebi_manager import block_funds_after_sell
        sell_value = exit_price * closed["qty"]
        block_funds_after_sell(symbol, sell_value)

        from sharia_manager import clear_haram_pending

        # FIX: clear_haram_pending() was only ever referenced from a test
        # file -- nothing in the production close path cleared the
        # haram-pending-exit flag once the position actually closed, so
        # data/haram_pending.json grew forever. Harmless for trading
        # decisions (a genuinely-haram symbol stays blocked anyway via the
        # halal-universe re-screen), but it's a data-hygiene leak worth
        # closing: clear the flag now that this position is confirmed shut.
        clear_haram_pending(symbol)

        # Workflow feedback loop
        try:
            from workflow_manager import record_performance_feedback
            record_performance_feedback(
                source="trade_logger.log_trade_exit",
                symbol=symbol,
                pnl=closed.get("pnl"),
                exit_reason=exit_reason,
            )
        except (ImportError, RuntimeError, ValueError, TypeError, KeyError) as e:
            logger.warning(f"log_trade_exit: Failed for {symbol}: {type(e).__name__}: {e}")


# ─────────────────────────────────────────────
# REPORTS
# ─────────────────────────────────────────────

def get_daily_report() -> str:
    data = load_json(TRADES_FILE, {"trades": []})
    today = today_ist().isoformat()
    today_trades = [
        t for t in data["trades"]
        if t.get("exit_time", "")[:10] == today and t["status"] == "CLOSED"
    ]

    if not today_trades:
        return "📊 *Daily Report*\nNo closed trades today."

    total_pnl = sum(t["pnl"] for t in today_trades if t["pnl"])
    wins = len([t for t in today_trades if (t["pnl"] or 0) > 0])
    total = len(today_trades)

    lines = [
        f"📊 *Daily Report — {today}*",
        f"Trades: {total} | Wins: {wins} | WR: {wins/total*100:.0f}%",
        f"Total P&L: {fmt_inr(total_pnl)}",
        "",
    ]
    for t in today_trades:
        emoji = "✅" if (t["pnl"] or 0) > 0 else "❌"
        lines.append(f"{emoji} {t['symbol']}: {fmt_inr(t['pnl'])} ({fmt_pct(t['pnl_pct'])})")

    return "\n".join(lines)


def get_pnl_summary(chat_id: int = None) -> str:
    """Master-account P&L summary. This reads TRADES_FILE, which only
    ever holds the admin's own master-account trades -- the chat_id
    parameter is accepted for backward compatibility but is NOT a
    per-subscriber filter (no subscriber's trades are ever stored here).
    [F11 FIX] Callers that need a subscriber's own outcome must use
    get_subscriber_copy_summary(chat_id) below instead -- bot.py's
    /pnl and /positions handlers now route subscribers there."""
    data = load_json(TRADES_FILE, {"trades": []})
    trades = [t for t in data["trades"] if t["status"] == "CLOSED"]

    if not trades:
        return "📈 No closed trades yet."

    total_pnl = sum(t["pnl"] for t in trades if t["pnl"])
    wins = len([t for t in trades if (t["pnl"] or 0) > 0])
    total = len(trades)

    return (
        f"📈 *P&L Summary*\n"
        f"Total Trades: {total}\n"
        f"Win Rate: {wins/total*100:.1f}%\n"
        f"Total P&L: {fmt_inr(total_pnl)}"
    )


def get_subscriber_copy_summary(chat_id: int) -> str:
    """[F11 FIX] A subscriber's own copy-trade outcome, from their own
    ledger rows in data/copy_trades.json -- NOT the admin's master
    TRADES_FILE. Note: the copy ledger records order IDs/status per
    subscriber fill, not fill price -- each subscriber's own entry/exit
    price can differ from the admin's (independent fills/slippage, per
    their own Dhan account), so an exact rupee P&L is not fabricated
    here; the subscriber is pointed to their own Dhan statement for
    that. This still fixes the core bug: a subscriber no longer sees
    the admin's numbers as if they were their own."""
    from broker import _load_copy_ledger

    ledger = _load_copy_ledger()
    rows = [r for r in ledger.get("copies", []) if r.get("chat_id") == chat_id]
    if not rows:
        return "📈 No copy-trades yet for your account."

    closed = [r for r in rows if r.get("status") == "CLOSED"]
    open_ = [r for r in rows if r.get("status") == "OPEN"]

    lines = [
        "📈 *Your Copy-Trade Summary*",
        f"Open positions: {len(open_)}",
        f"Closed positions: {len(closed)}",
    ]
    if closed:
        filled = len([r for r in closed if r.get("sell_status") in ("FILLED", "PARTIAL")])
        lines.append(f"Closed & filled: {filled}/{len(closed)}")
    lines.append(
        "\nExact ₹ P&L isn't shown here — your own fill price/slippage "
        "can differ from the admin's; check your Dhan account statement "
        "for your real numbers. Use /positions for your open symbols."
    )
    return "\n".join(lines)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def get_last_sl_hit_date(symbol: str):
    """Returns date of last SL hit for symbol, or None."""
    data = load_json(TRADES_FILE, {"trades": []})
    sl_trades = [
        t for t in data["trades"]
        if t["symbol"] == symbol
        and t["status"] == "CLOSED"
        and t.get("exit_reason", "").upper().find("SL") >= 0
    ]
    if not sl_trades:
        return None
    last = sl_trades[-1]
    exit_time = last.get("exit_time", "")
    if exit_time:
        return date.fromisoformat(exit_time[:10])
    return None


def _next_id(data: dict) -> int:
    trades = data.get("trades", [])
    if not trades:
        return 1
    return max(t.get("id", 0) for t in trades) + 1
