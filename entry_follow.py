"""
entry_follow.py — Entry Order FOLLOW Mode (v5.9)

Owner rule 2026-08-20 (GOAL_DISCUSSION D28):
  "Order broker pe pending/resting rahega — cancel nahi. Jab CMP level pe
   aaye to broker khud execute kare (lightning-speed moves me bot ki
   wait/latency ka koi role na ho). Backtest/optimizer ke levels (entry-SL
   geometry) hi point-of-no-return ka scale hain — price utna upar bhaag
   jaye to order CANCEL (wapas aana unlikely; capital free → dusra stock).
   Ye SIRF order-pending ka execution rule hai — strategy/RR/optimizer
   ZERO touch. Time ke saath shadow data se level accuracy improve hoti hai.
   Jo stock ka price data nahi hai usme trade nahi."

Flow:
  entry LMT place → initial waits (trade_engine) → phir bhi PENDING
    → register_following_order() [order exchange pe RESTING continue]
  Har tick (position monitor 3-min / scan cycle, + EOD job):
    1. Order status check (broker) — FILLED → ADOPT (position register +
       GTT SL/TP arm — crash-adopt jaisa hi pattern)
    2. CMP gap check — risk_units × (entry − SL) se zyada upar → CANCEL
    3. warna → HOLD (resting continue; EOD pe exchange day-order khud
       cancel karta hai — agle din ka record clean ho jata hai)

Safety:
  - CMP missing → hold (retry); lagataar entry_follow_price_missing_ticks
    ticks missing → cancel (owner: bina price data trade nahi)
  - Adopt double-guard: symbol already tracked → skip (no double register)
  - Crash-recovery (CRASH_PENDING_ORDERS_FILE) ke saath overlap-safe:
    dono taraf se cleanup hota hai, adopt guard dono jagah hai
  - Sab fail-open: tick error → next cycle retry, order resting rehta hai

Method refs: LIMIT resting order = standard exchange mechanics (NSE day
order); cancel-if-ran = owner-decision scale (optimizer geometry),
refinement = empirical forward observation (shadow_log) — model nahi.
"""

from __future__ import annotations

from config import DATA_DIR, PARAMS, AUDIT_LOG_FILE
from utils import load_json, save_json, now_ist, append_log

ENTRY_FOLLOW_STATE_FILE = f"{DATA_DIR}/entry_follow_state.json"

# In-memory CMP cache — scan loop (har 5 min, pura universe) update karta
# hai, koi extra API call nahi. Restart pe khali → agle scan me refill;
# missing = gap check SKIP (hold), kabhi blind cancel nahi.
_cmp_cache: dict = {}


def _load() -> dict:
    return load_json(ENTRY_FOLLOW_STATE_FILE, {"orders": []})


def _save(state: dict):
    save_json(ENTRY_FOLLOW_STATE_FILE, state)


def register_following_order(order_id, symbol, qty, entry_price,
                             sl_price, tp1_price, security_id=None):
    """Entry order RESTING mode me register (initial waits ke baad PENDING).
    Crash-pending record already bana hota hai (trade_engine) — ye alag
    follow-state hai; dono terminal action pe clean hote hain."""
    state = _load()
    orders = [o for o in state.get("orders", [])
              if str(o.get("order_id")) != str(order_id)]
    orders.append({
        "order_id": str(order_id),
        "symbol": str(symbol),
        "qty": int(qty or 0),
        "entry_price": float(entry_price or 0),
        "sl_price": float(sl_price or 0),
        "tp1_price": float(tp1_price or 0),
        "security_id": security_id or "",
        "ts": now_ist().isoformat(),
        "date": now_ist().strftime("%Y-%m-%d"),
        "missing_price_ticks": 0,
    })
    _save({"orders": orders})
    append_log(AUDIT_LOG_FILE,
               f"ENTRY FOLLOW REGISTER: {symbol} order={order_id} RESTING "
               f"(entry {entry_price}, SL {sl_price}) — cancel nahi hoga, "
               f"har tick decide karega (fill → adopt, bhaag gaya → cancel)")


def update_cmp(symbol: str, price: float):
    """Scan loop hook — har cycle fresh CMP (fetched close reuse)."""
    try:
        _cmp_cache[str(symbol)] = float(price)
    except (TypeError, ValueError):
        pass


def _remove(state: dict, order_id: str):
    state["orders"] = [o for o in state.get("orders", [])
                       if str(o.get("order_id")) != str(order_id)]
    _save(state)


def _clean_crash_pending(order_id: str):
    """Follow order terminal ho gaya → crash-pending record bhi clean."""
    try:
        from config import CRASH_PENDING_ORDERS_FILE
        p = load_json(CRASH_PENDING_ORDERS_FILE, {"orders": []})
        p["orders"] = [o for o in p.get("orders", [])
                       if str(o.get("order_id")) != str(order_id)]
        save_json(CRASH_PENDING_ORDERS_FILE, p)
    except Exception as e:
        append_log(AUDIT_LOG_FILE,
                   f"ENTRY FOLLOW crash-pending cleanup error: {e}")


def _adopt(rec: dict) -> str:
    """FILLED order → position ADOPT + GTT SL/TP arm (crash-adopt pattern,
    trade_engine.recover_pending_orders jaisa hi — same info class)."""
    from capital_manager import get_active_trades, register_trade
    from forever_order_manager import setup_forever_orders
    from stock_selector import get_security_id
    from strategy import get_active_strategy

    symbol = str(rec.get("symbol") or "")
    if symbol in get_active_trades():
        return "ALREADY_TRACKED"
    qty = int(rec.get("qty") or 0)
    entry_price = float(rec.get("entry_price") or 0)
    sl_price = float(rec.get("sl_price") or 0)
    tp1_price = float(rec.get("tp1_price") or 0)
    if qty <= 0 or entry_price <= 0:
        return "BAD_RECORD"
    try:
        strategy = get_active_strategy()
        sname = getattr(strategy, "name", "follow_adopt")
        sver = getattr(strategy, "version", "v5.9")
    except Exception:
        sname, sver = "follow_adopt", "v5.9"
    trade_data = {
        "security_id": rec.get("security_id") or "",
        "qty": qty,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp1_price": tp1_price,
        "entry_time": rec.get("ts", now_ist().isoformat()),
        "mode": "NORMAL",
        "phase": "FOLLOW_ADOPT",
        "signal_score": 1.0,
        "tp1_hit": False,
        "strategy_name": sname,
        "strategy_version": sver,
    }
    register_trade(symbol, trade_data)
    sec_id = rec.get("security_id") or get_security_id(symbol)
    if sec_id:
        try:
            setup_forever_orders(symbol, sec_id, qty, entry_price, sl_price)
        except Exception as e:
            append_log(AUDIT_LOG_FILE,
                       f"ENTRY FOLLOW ADOPT GTT FAILED {symbol}: {e} — "
                       f"position tracked hai, GTT retry zaroori")
    else:
        append_log(AUDIT_LOG_FILE,
                   f"ENTRY FOLLOW ADOPT NO SECURITY_ID {symbol} — position "
                   f"tracked, GTT arm Nahi ho paya (manual check zaroori)")
    append_log(AUDIT_LOG_FILE,
               f"ENTRY FOLLOW ADOPT: {symbol} order={rec.get('order_id')} "
               f"FILLED (resting se) — position registered + SL GTT armed")
    return "ADOPTED"


def tick_following_orders() -> dict:
    """Har monitor/scan cycle: status + CMP check. Idempotent, fail-open.
    Returns {order_id: action} (caller alert bhej sakta hai)."""
    from broker import verify_order_status, cancel_order

    results = {}
    state = _load()
    today = now_ist().strftime("%Y-%m-%d")
    orders = [o for o in state.get("orders", []) if o.get("date") == today]
    if not orders:
        return results
    risk_units = float(PARAMS.get("entry_follow_risk_units", 1.0))
    max_missing = int(PARAMS.get("entry_follow_price_missing_ticks", 3))
    for rec in orders:
        oid = str(rec.get("order_id"))
        symbol = str(rec.get("symbol"))
        try:
            status, _fp = verify_order_status(oid, wait_sec=0)
        except Exception as e:
            append_log(AUDIT_LOG_FILE,
                       f"ENTRY FOLLOW STATUS ERROR {symbol} {oid}: {e}")
            continue  # next cycle retry — order resting hi hai
        if status in ("FILLED", "TRADED", "EXECUTED"):
            act = _adopt(rec)
            results[oid] = f"ADOPTED({act})"
            _remove(state, oid)
            _clean_crash_pending(oid)
            continue
        if status in ("REJECTED", "CANCELLED"):
            results[oid] = f"CLEANED({status})"
            _remove(state, oid)
            _clean_crash_pending(oid)
            append_log(AUDIT_LOG_FILE,
                       f"ENTRY FOLLOW CLEAN: {symbol} order={oid} {status}")
            continue
        if status == "PARTIAL":
            # CNC delivery LMT partial fill rare hai — qty mismatch se adopt
            # galat hoga. Alert + hold (order baaki qty pe working rehta hai).
            append_log(AUDIT_LOG_FILE,
                       f"ENTRY FOLLOW PARTIAL: {symbol} order={oid} — manual "
                       f"check zaroori (partial fill)")
            results[oid] = "HOLD(PARTIAL)"
            continue
        # PENDING → CMP gap check
        cmp = _cmp_cache.get(symbol)
        if cmp is None:
            rec["missing_price_ticks"] = int(rec.get("missing_price_ticks", 0)) + 1
            _save(state)  # counter persist — continue se pehle zaroori
            if rec["missing_price_ticks"] >= max_missing:
                try:
                    cancel_order(oid)
                except Exception as e:
                    append_log(AUDIT_LOG_FILE,
                               f"ENTRY FOLLOW CANCEL ERROR {symbol}: {e}")
                results[oid] = "CANCELLED(NO_PRICE)"
                _remove(state, oid)
                _clean_crash_pending(oid)
                append_log(AUDIT_LOG_FILE,
                           f"ENTRY FOLLOW CANCEL: {symbol} price data "
                           f"{max_missing} ticks se missing — order cancel "
                           f"(owner rule: bina data trade nahi)")
            else:
                results[oid] = "HOLD(no_price)"
            continue
        rec["missing_price_ticks"] = 0
        entry = float(rec.get("entry_price") or 0)
        sl = float(rec.get("sl_price") or 0)
        if entry > 0 and sl > 0 and entry > sl:
            gap_units = (cmp - entry) / (entry - sl)
            if gap_units > risk_units:
                # point-of-no-return paar — cancel (capital free)
                try:
                    cancel_ok = cancel_order(oid)
                except Exception:
                    cancel_ok = False
                if not cancel_ok:
                    # last-millisecond fill race check (FIX-05 pattern)
                    try:
                        status_check, _race_fp = verify_order_status(
                            oid,
                            wait_sec=int(PARAMS.get("order_race_check_wait_sec", 2)))
                    except Exception:
                        status_check = "UNKNOWN"
                    if status_check in ("FILLED", "TRADED", "EXECUTED"):
                        act = _adopt(rec)
                        results[oid] = f"ADOPTED_RACE({act})"
                        _remove(state, oid)
                        _clean_crash_pending(oid)
                        continue
                results[oid] = "CANCELLED(RAN_AWAY)"
                _remove(state, oid)
                _clean_crash_pending(oid)
                append_log(AUDIT_LOG_FILE,
                           f"ENTRY FOLLOW CANCEL: {symbol} CMP {cmp} entry se "
                           f"{gap_units:.2f}x risk-units upar (> {risk_units}) "
                           f"— point-of-no-return, capital free")
                continue
        results[oid] = "HOLD"
    _save(state)
    return results
