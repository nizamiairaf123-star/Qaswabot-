"""
trade_engine.py — BRAIN of the bot
FIX-11: Reconciliation action matrix (3 cases)
FIX-17: Duplicate signal handler
FIX-27: TP1 detection every 3 min + breakeven gap documented
"""

import logging
import asyncio
from utils import append_log, now_ist, safe_div
from config import AUDIT_LOG_FILE, PARAMS, SIGNAL_REGISTRY_FILE

logger = logging.getLogger(__name__)
from strategy import get_active_strategy, detect_market_phase
from risk_manager import can_enter_trade
from capital_manager import (calculate_qty_enhanced, register_trade, release_trade,
                              get_active_trades, has_free_slot, update_trade,
                              get_stage_multiplier, get_health_capital_multiplier,
                              get_regime_capital_multiplier)
from broker import (place_order, verify_order_status, cancel_order,
                    copy_trade_all_subscribers, get_order_fill_snapshot)
from forever_order_manager import (setup_forever_orders, close_forever_orders,
                                    get_sl)
from trade_logger import log_trade_entry, log_trade_exit
from signal_broadcaster import broadcast_trade_signal, broadcast_exit, alert_admin
from stock_selector import get_tradeable_universe, get_security_id
from stock_mode_manager import (update_watermark, check_and_apply_soft_block,
                                 try_recovery_entry, recovery_sl_hit,
                                 recovery_success, check_soft_to_profit,
                                 get_mode)
from intraday_filter import is_good_time_to_trade
from per_stock_params import get_param
from bot_state_manager import (can_enter, can_monitor, can_exit, can_place_gtt,
                                get_state, activate_reconciliation_hold)
import pandas as pd

# [FIX-04] Persistence for Trade Deduplication helpers
def _load_processed_signals() -> dict:
    from utils import load_json
    return load_json(SIGNAL_REGISTRY_FILE, {})

def _save_processed_signals(data: dict):
    from utils import save_json
    save_json(SIGNAL_REGISTRY_FILE, data)


# ─────────────────────────────────────────────
# PARTIAL-FILL PROTECTION
# Adopt filled qty immediately (SL + fixed 1.8R lock / GTT). Unfilled
# remainder times out then cancel_order. Do NOT send q_filled>=1 PARTIAL
# into entry_follow HOLD. verify_order_status stays a 2-tuple.
# ─────────────────────────────────────────────

def _load_partial_remainders() -> dict:
    from utils import load_json
    from config import PARTIAL_REMAINDER_FILE
    return load_json(PARTIAL_REMAINDER_FILE, {"orders": []})


def _save_partial_remainders(data: dict):
    from utils import save_json
    from config import PARTIAL_REMAINDER_FILE
    save_json(PARTIAL_REMAINDER_FILE, data)


def _register_partial_remainder(order_id, symbol, requested_qty, filled_qty,
                                security_id, entry_price, sl_price, tp1_price):
    remaining = int(requested_qty) - int(filled_qty)
    if remaining < 1:
        return
    timeout = int(PARAMS.get("partial_fill_remainder_timeout_sec", 600) or 600)
    rec = {
        "order_id": str(order_id),
        "symbol": symbol,
        "requested_qty": int(requested_qty),
        "filled_qty": int(filled_qty),
        "security_id": security_id,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp1_price": tp1_price,
        "deadline_ts": now_ist().timestamp() + timeout,
        "registered_at": now_ist().isoformat(),
        "status": "OPEN",
    }
    data = _load_partial_remainders()
    data["orders"] = [o for o in data.get("orders", [])
                      if str(o.get("order_id")) != str(order_id)]
    data.setdefault("orders", []).append(rec)
    _save_partial_remainders(data)
    append_log(AUDIT_LOG_FILE,
               f"PARTIAL REMAINDER ARMED: {symbol} order={order_id} "
               f"filled={filled_qty} remaining={remaining} timeout={timeout}s")


def _adopt_extra_partial_qty(symbol: str, extra: int, rec: dict):
    """Remainder filled more shares before timeout — adopt so recon Case 2
    does not see ghost Dhan qty. Re-arm GTT for the new total."""
    if extra < 1:
        return
    active = get_active_trades()
    if symbol not in active:
        append_log(AUDIT_LOG_FILE,
                   f"PARTIAL EXTRA UNTRACKED: {symbol} extra={extra} — "
                   f"no local position (recon Case 2 if still open)")
        return
    trade = active[symbol]
    new_qty = int(trade.get("qty") or 0) + extra
    update_trade(symbol, {"qty": new_qty})
    append_log(AUDIT_LOG_FILE,
               f"PARTIAL EXTRA ADOPTED: {symbol} +{extra} → qty={new_qty}")
    if can_place_gtt():
        try:
            close_forever_orders(symbol)
            sec_id = rec.get("security_id") or trade.get("security_id")
            if sec_id:
                setup_forever_orders(
                    symbol, sec_id, new_qty,
                    float(trade.get("entry_price") or rec.get("entry_price") or 0),
                    float(trade.get("sl_price") or rec.get("sl_price") or 0),
                )
        except Exception as e:
            append_log(AUDIT_LOG_FILE,
                       f"PARTIAL EXTRA GTT REARM FAILED {symbol}: {e}")


def expire_partial_remainders() -> dict:
    """Cancel unfilled remainder after timeout; adopt extra fills before then."""
    results = {}
    try:
        data = _load_partial_remainders()
        orders = list(data.get("orders", []))
        if not orders:
            return results
        now_ts = now_ist().timestamp()
        changed = False
        for rec in orders:
            if rec.get("status") != "OPEN":
                continue
            oid = str(rec.get("order_id") or "")
            symbol = rec.get("symbol", "")
            snap = get_order_fill_snapshot(oid)
            qf = int(snap.get("filled_qty") or 0)
            st = snap.get("status") or "UNKNOWN"
            extra = qf - int(rec.get("filled_qty") or 0)
            if extra > 0:
                _adopt_extra_partial_qty(symbol, extra, rec)
                rec["filled_qty"] = qf
                changed = True
            requested = int(rec.get("requested_qty") or 0)
            if st in ("FILLED", "TRADED", "EXECUTED") or (requested > 0 and qf >= requested):
                rec["status"] = "FULLY_FILLED"
                results[oid] = "FULLY_FILLED"
                changed = True
                continue
            if st in ("CANCELLED", "REJECTED"):
                rec["status"] = st
                results[oid] = st
                changed = True
                continue
            if now_ts >= float(rec.get("deadline_ts") or 0):
                ok = cancel_order(oid)
                rec["status"] = "REMAINDER_CANCELLED" if ok else "CANCEL_FAILED"
                rec["cancelled_at"] = now_ist().isoformat()
                results[oid] = rec["status"]
                changed = True
                append_log(AUDIT_LOG_FILE,
                           f"PARTIAL REMAINDER CANCEL: {symbol} order={oid} ok={ok}")
                if not ok:
                    try:
                        from signal_broadcaster import alert_admin_sync
                        alert_admin_sync(
                            f"⚠️ PARTIAL remainder cancel FAILED: {symbol} "
                            f"order {oid} — check Dhan (unfilled qty may still be live)."
                        )
                    except Exception as e:
                        append_log(AUDIT_LOG_FILE,
                                   f"PARTIAL REMAINDER ALERT FAILED {symbol}: {e}")
        if changed:
            open_recs = [o for o in orders if o.get("status") == "OPEN"]
            closed = [o for o in orders if o.get("status") != "OPEN"][-20:]
            _save_partial_remainders({"orders": open_recs + closed})
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"PARTIAL REMAINDER EXPIRE ERROR: {type(e).__name__}: {e}")
    return results


def _try_adopt_partial_fill(order_id, requested_qty, fill_price,
                            symbol, security_id, entry_price, sl_price, tp1_price):
    """If broker reports q_filled>=1, return (True, qty, fill_price) and arm
    remainder timeout. Else (False, requested_qty, fill_price)."""
    snap = get_order_fill_snapshot(order_id)
    qf = snap.get("filled_qty")
    try:
        qf = int(qf or 0)
    except (TypeError, ValueError):
        qf = 0
    avg = snap.get("avg_fill_price") or fill_price
    if qf < 1:
        return False, requested_qty, fill_price
    remaining = int(snap.get("remaining_qty") or 0)
    if remaining < 1 and qf < int(requested_qty):
        remaining = int(requested_qty) - qf
    _register_partial_remainder(order_id, symbol, requested_qty, qf,
                                security_id, entry_price, sl_price, tp1_price)
    append_log(AUDIT_LOG_FILE,
               f"PARTIAL ADOPT: {symbol} order={order_id} q_filled={qf} "
               f"of {requested_qty} remaining={remaining}")
    return True, qf, avg


# ─────────────────────────────────────────────
# MARKET SCAN
# ─────────────────────────────────────────────

async def run_market_scan():
    from utils import is_killswitch_active

    # [r30 TELEMETRY — prd.md Rule 16 Black Box] Silent watcher: fail-open
    # in-memory trace of this scan (gates, counts, decisions, market photo).
    # Telemetry kabhi scan block nahi karta — begin_scan never raises, and
    # the fallback object below is fully inert if even the import fails.
    try:
        from telemetry import begin_scan as _tel_begin
        _trace = _tel_begin()
    except Exception:
        class _TelInert:
            def __getattr__(self, _n):
                return lambda *a, **k: None
        _trace = _TelInert()

    if is_killswitch_active():
        _trace.skip("KILLSWITCH")
        return

    # [AUDIT FIX 2026-08-31] FIX-53: FIX-47's heartbeat mechanism
    # (scheduler.py) correctly DETECTED network partitions and set
    # data/needs_reconciliation.json, but nothing ever READ that
    # detection to actually block new entries -- the circuit breaker
    # logged "NETWORK_PARTITION_DETECTED" and then took no protective
    # action. Wiring it in here, at the same early-gate point as the
    # killswitch check. This only blocks NEW entries -- existing
    # position monitoring/exits are untouched (same pattern as
    # EXPIRED_EXIT_ONLY elsewhere: entry band closes, exit stays open).
    # Self-clears automatically the next successful heartbeat
    # (record_heartbeat_success() resets partition_detected=False).
    from utils import is_network_partition
    if is_network_partition():
        append_log(AUDIT_LOG_FILE, "SCAN BLOCKED: network partition active — new entries paused until heartbeat recovers")
        _trace.skip("NETWORK_PARTITION")
        return

    # [PHD-FIX Section-47 DB-failure -> SAFE STOP] Same gate point as the
    # killswitch/network-partition checks above. A DB read/write failure
    # anywhere (killswitch state, active-trades, SEBI-blocked list,
    # crash-pending orders, etc. all persist through the same DB layer)
    # otherwise resolves silently to each caller's own default rather than
    # halting. This blocks only NEW entries, exactly like the two checks
    # above — existing position monitoring/exits are untouched. Self-clears
    # on the next successful DB read/write (database.py's _clear_db_failure).
    from database import is_db_failure_recent
    if is_db_failure_recent():
        append_log(AUDIT_LOG_FILE, "SCAN BLOCKED: recent DB read/write failure detected — new entries paused (Fail-Closed) until DB recovers")
        _trace.skip("DB_FAILURE")
        return

    # FIX-06: Check bot state
    if not can_enter():
        _trace.skip("BOT_STATE")
        return

    try:
        from workflow_manager import can_execute_trade_cycle, record_paper_trading_started, record_live_trading_started
        state = get_state()
        real_orders_mode = state in ("LIVE_STAGED", "LIVE_FULL")
        wf_ok, wf_reason = can_execute_trade_cycle(real_orders=real_orders_mode)
        if not wf_ok:
            append_log(AUDIT_LOG_FILE, f"SCAN BLOCKED: workflow gate | state={state} | {wf_reason}")
            _trace.skip("WORKFLOW", wf_reason)
            return
        if real_orders_mode:
            record_live_trading_started(state=state, source="trade_engine.run_market_scan")
        else:
            record_paper_trading_started(state=state, source="trade_engine.run_market_scan")
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"WORKFLOW GATE ERROR: {e}")
        _trace.skip("WORKFLOW_ERROR", str(e))
        return

    time_ok, _ = is_good_time_to_trade()
    if not time_ok:
        _trace.skip("NOT_TRADING_TIME")
        return

    try:
        from strategy_validator import is_strategy_valid
        if not is_strategy_valid():
            append_log(AUDIT_LOG_FILE, "SCAN BLOCKED: Strategy validator INVALID")
            _trace.skip("STRATEGY_INVALID")
            return
    except (ImportError, RuntimeError) as e:
        logger.warning(f"_run_market_scan: Strategy validator check failed: {type(e).__name__}: {e}")

    symbols  = get_tradeable_universe()
    _trace.set("universe_size", len(symbols))

    # [Rule 14 / QASWA Remix — SEQ audit-observability, added r15] Read-only,
    # non-blocking per-scan trace: confirms (does not decide/enforce — that's
    # already done by get_tradeable_universe() -> load_halal_symbols(), which
    # structurally cannot return a non-eligible symbol) how many symbols are
    # entering SEQ-stage processing this scan and that they are pre-verified
    # Business-Halal + Non-Muslim-Board eligible. No scoring, no new decision
    # logic, no RR/exit/risk change — same class as the existing boot-time
    # seq_alignment_registry.py trace, just per-scan instead of per-boot.
    try:
        append_log(AUDIT_LOG_FILE, f"SEQ_STAGE_ENTRY: {len(symbols)} symbols entering SEQ stage; all pre-verified Halal + Non-Muslim Board eligible")
    except Exception as e:
        logger.warning(f"_run_market_scan: SEQ_STAGE_ENTRY trace failed (non-blocking): {type(e).__name__}: {e}")

    # [SURVEILLANCE/STATUS PRE-FILTER — OWNER DECISION 2026-09-05] Hard-rejected stocks scan se
    # PEHLE hat jate hain — blocked stock ka candle-fetch/signal-compute hi nahi
    # hota (timepass band). List stale/missing → poora entry scan fail-closed
    # skip (master gate bhi sab block karta hai; exit path alag hai, untouched).
    try:
        from asm_gsm_screen import is_asm_gsm_data_stale, is_symbol_blocked, notify_stale_once
        if is_asm_gsm_data_stale():
            notify_stale_once()
            append_log(AUDIT_LOG_FILE, "SCAN SKIP: ASM/GSM list stale/missing — new entries fail-closed (refresh: python3 scripts/refresh_decision_data.py)")
            _trace.skip("ASM_GSM_STALE")
            return
        _kept, _rejected = [], []
        for _s in symbols:
            (_rejected if is_symbol_blocked(_s)[0] else _kept).append(_s)
        if _rejected:
            append_log(AUDIT_LOG_FILE, f"STATUS PRE-FILTER: hard-rejected stocks scan se hata diye: {', '.join(_rejected[:10])}{' ...' if len(_rejected) > 10 else ''}")
        symbols = _kept
        _trace.set("post_filter_size", len(symbols))
        if _rejected:
            _trace.set("asm_gsm_rejected", list(_rejected))
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"STATUS PRE-FILTER ERROR: {e} — scan skip (Fail-Closed)")
        _trace.skip("PREFILTER_ERROR", str(e))
        return

    strategy = get_active_strategy()
    _trace.set("strategy", getattr(strategy, "name", "") or "")

    # [OVERRIDE 3 — user-authorized architectural pivot] Two-phase scan:
    # collect every symbol's candidate signal WITHOUT executing, rank by
    # (sector strength score, signal score) descending, then execute in
    # that priority order until the day's slot budget (5-10, see
    # capital_manager._calculate_position_qty) is full. Previously this
    # loop executed each symbol's signal immediately in whatever order
    # get_tradeable_universe() happened to return them — meaning a
    # mediocre setup scanned early could take a slot a stronger setup
    # (scanned later in the same 5-min cycle) would have deserved more.
    #
    # [TIME-AWARE] Phase 0: candle fetch + signal compute PARALLEL
    # (asyncio.to_thread + semaphore) — poora universe ek saath, sequential
    # network loop nahi. Trading window ke andar cold network work sirf
    # isi bounded concurrency se hota hai.
    max_concurrent = int(PARAMS.get("scan_max_concurrent_fetches", 10))
    sem = asyncio.Semaphore(max_concurrent)

    def _compute(symbol):
        """Thread-pool compute (network-bound, no side effects):
        candles fetch + signal generation.
        [PHD-FIX F5] Signal evaluation sirf COMPLETED bars pe (forming
        candle drop) — live/backtest divergence (forming-bar false signals)
        khatam. Entry phir bhi live price pe hota hai (neeche)."""
        try:
            data = _fetch_candles(symbol)
            if data is None or data.empty:
                return None
            sig_data = data.iloc[:-1] if len(data) >= 2 else data
            signals = strategy.generate_signals(sig_data, symbol)
            return (data, signals)
        except Exception as e:
            append_log(AUDIT_LOG_FILE, f"SCAN FETCH ERROR {symbol}: {e}")
            return None

    async def _compute_async(symbol):
        async with sem:
            return await asyncio.to_thread(_compute, symbol)

    computed = {}
    results = await asyncio.gather(
        *[asyncio.create_task(_compute_async(s)) for s in symbols],
        return_exceptions=True,
    )
    for symbol, res in zip(symbols, results):
        if isinstance(res, Exception):
            append_log(AUDIT_LOG_FILE, f"SCAN FETCH ERROR {symbol}: {res}")
            _trace.count("fetch_error")
            continue
        if res is not None:
            computed[symbol] = res
        else:
            _trace.count("fetch_fail")

    # Phase 1: sequential state checks in ORIGINAL symbol order (watermark,
    # stock modes, recovery entries, dedup, risk gate, news) — order
    # preserving, sirf fast local checks.
    candidates = []
    for symbol in symbols:
        try:
            if symbol not in computed:
                continue
            data, signals = computed[symbol]

            current_price = float(data["close"].iloc[-1])
            update_watermark(symbol, current_price)
            check_soft_to_profit(symbol, current_price)
            # [v5.9] CMP hooks — entry-follow + shadow research (no extra API
            # call; scan ka fetched close reuse). Fail-open: ye support path
            # hai, scan kabhi block nahi hota.
            try:
                from entry_follow import update_cmp as _follow_cmp
                _follow_cmp(symbol, current_price)
                from shadow_log import update_cmp as _shadow_cmp
                _shadow_cmp(symbol, current_price)
            except Exception as e:
                logger.debug(f"v5.9 cmp hook failed {symbol}: {type(e).__name__}: {e}")

            if get_mode(symbol) != "PROFIT":
                _trace.count("mode_skip")
                if get_mode(symbol) == "SOFT_BLOCKED":
                    # [FIX] Recovery ("mauka") entries previously bypassed
                    # can_enter_trade() entirely and called try_recovery_entry()
                    # unguarded — meaning a killswitch, an active capital-
                    # survival circuit, or a FAILED/WARNING portfolio-health
                    # mode would NOT stop a recovery entry from firing. Reuse
                    # the same 3 core safety gates the normal entry path uses
                    # (risk_manager.can_enter_trade) as a minimal guard here —
                    # fail-closed (block) if any check itself errors.
                    try:
                        from utils import is_killswitch_active
                        if is_killswitch_active():
                            continue
                        from risk_override_manager import check_capital_survival_override
                        survival_ok, _survival_reason = check_capital_survival_override(apply_state=True)
                        if not survival_ok:
                            continue
                        from portfolio_health import get_portfolio_mode
                        if get_portfolio_mode() in ("WARNING", "FAILED"):
                            continue
                    except Exception as e:
                        append_log(AUDIT_LOG_FILE, f"RECOVERY ENTRY GUARD ERROR {symbol}: {e} (Fail-Closed — recovery entry skipped)")
                        continue
                    _trace.count("recovery_attempt")
                    if try_recovery_entry(symbol, current_price):
                        # Recovery entries bypass ranking — handled immediately,
                        # same as before, since they're a distinct risk category.
                        _trace.decision(symbol, "RECOVERY_ENTRY_OK",
                                        context={"price": current_price})
                        await _execute_recovery_entry(symbol, current_price, data)
                    else:
                        _trace.decision(symbol, "RECOVERY_ENTRY_DECLINED",
                                        context={"price": current_price})
                continue

            buy_signals = [s for s in signals if s["action"] == "BUY"]
            if not buy_signals:
                _trace.count("no_buy_signal")
                continue

            candle_key = f"{symbol}_{data.index[-1]}"
            processed = _load_processed_signals()
            if candle_key in processed:
                append_log(AUDIT_LOG_FILE, f"DUPLICATE SIGNAL IGNORED: {symbol} same candle")
                _trace.count("dup_skip")
                continue

            signal = buy_signals[0]
            # [PHD-FIX F5] Signal completed bar pe bana hai — entry ab LIVE
            # price pe re-anchor karo (SL signal-bar low hi rehta hai; TP =
            # entry + (entry-SL) × 1.8R — parity D7 rule intact).
            try:
                _sl = float(signal.get("sl_price") or 0)
                _rr = 1.8
                if _sl > 0 and current_price > _sl:
                    signal = dict(signal)
                    signal["entry_price"] = round(current_price, 2)
                    signal["tp1_price"] = round(current_price + (current_price - _sl) * _rr, 2)
                    signal["reason"] = (signal.get("reason", "") + " [entry@live]").strip()
            except (TypeError, ValueError, KeyError) as e:
                logger.debug(f"live re-anchor failed {symbol}: {type(e).__name__}: {e}")
            # [v5.9] Shadow research record — har BUY signal (chahe entry ho
            # ya na ho — slot/risk blocks se independent) ka level anchor +
            # din-bhar path track hota hai. Koi order nahi, koi risk nahi —
            # sirf observation data (risk_units refinement ke liye).
            try:
                from shadow_log import record_signal
                record_signal(symbol, float(signal.get("entry_price") or 0),
                              float(signal.get("sl_price") or 0),
                              float(signal.get("tp1_price") or 0))
            except Exception as e:
                logger.debug(f"shadow record failed {symbol}: {type(e).__name__}: {e}")
            # [F10 FIX] can_enter_trade() -> correlation_tracker synchronously
            # hits Dhan for every active symbol on the event loop; to_thread
            # it so a hung call here can't freeze scanning/monitoring/ticks.
            allowed, reason = await asyncio.to_thread(can_enter_trade, symbol, current_price)
            if not allowed:
                append_log(AUDIT_LOG_FILE, f"BLOCKED {symbol}: {reason}")
                _trace.count("risk_reject")
                _trace.decision(symbol, "REJECT_RISK_GATE", reason=reason,
                                signal=signal,
                                context={"current_price": current_price},
                                bars=data.iloc[:-1])
                continue

            try:
                from news_analyzer import is_sentiment_ok
                if not is_sentiment_ok(symbol):
                    _trace.count("news_reject")
                    _trace.decision(symbol, "REJECT_NEWS",
                                    reason="news sentiment not ok",
                                    signal=signal,
                                    context={"current_price": current_price},
                                    bars=data.iloc[:-1])
                    continue
            except Exception as e:
                append_log(AUDIT_LOG_FILE, f"NEWS CHECK ERROR ({symbol}): {e} — continuing (supplementary)")

            candidates.append({"symbol": symbol, "signal": signal, "data": data})
            _trace.count("candidate_collected")
        except Exception as e:
            append_log(AUDIT_LOG_FILE, f"SCAN ERROR {symbol}: {e}")
            _trace.count("phase1_error")

    def _priority_key(c):
        # v5.7 (owner D7): RR pehle priority — comparative behtar R:R wale
        # stock ko pehle slot (rr fixed 1.8R se).
        try:
            from sector_strength import get_sector_runtime_signal
            sector_score = float(get_sector_runtime_signal(c["symbol"]).get("strength_score", 0.0) or 0.0)
        except (ImportError, RuntimeError, ValueError, TypeError):
            sector_score = 0.0
        signal_score = float(c["signal"].get("signal_score", 0.5) or 0.5)
        # RR is fixed at 1.8R; do not rank candidates by an optimizer RR dimension.
        return (sector_score, signal_score)

    # ─────────────────────────────────────────────
    # PILLAR 3: Fundamental + Technical Sync — Profit Pattern Execution (r39 CORRECTED)
    # REAL DATA ONLY, PIT-SAFE, FAIL-CLOSED when mandatory
    # Business Halal → Non-Muslim Board → Fundamental Quality → Technical/SEQ → Fundamental×Technical confirmation
    # ─────────────────────────────────────────────
    try:
        from fundamental_sync_engine import filter_candidates_by_fundamentals, rank_by_fundamental_sync
        # PIT: trade date T = today for live scan — only info available on or before T
        try:
            trade_date = now_ist().date().isoformat()
        except Exception:
            trade_date = None
        
        # First, filter out weak fundamentals (bull traps / gap-down risk) — PIT as_of=trade_date
        accepted, rejected = filter_candidates_by_fundamentals(candidates, as_of=trade_date)
        if rejected:
            try:
                append_log(AUDIT_LOG_FILE,
                           f"FUNDAMENTAL FILTER (Pillar 3 CORRECTED REAL ONLY PIT as_of={trade_date}): Rejected {len(rejected)} weak/missing setups: "
                           f"{', '.join([r['symbol'] for r in rejected[:10]])}")
                for rej in rejected:
                    _trace.decision(rej["symbol"], "REJECT_FUNDAMENTAL_WEAK",
                                    reason=str(rej.get("rejection_reason") or rej.get("fundamental_evaluation", {}).get("reason", "")),
                                    signal=rej.get("signal", {}),
                                    context={
                                        "trade_date": trade_date,
                                        "as_of": rej.get("as_of") or trade_date,
                                        "fundamental_dna": rej.get("fundamental_dna", {}),
                                        "fundamental_evaluation": rej.get("fundamental_evaluation", {}),
                                        "fundamental_status": rej.get("fundamental_status", "UNKNOWN"),
                                        "fundamental_score": rej.get("fundamental_score", 0),
                                        "fundamental_features": rej.get("fundamental_features", rej.get("fundamental_dna", {})),
                                        "technical_status": rej.get("technical_status", rej.get("signal", {}).get("reason", "UNKNOWN")),
                                        "technical_tools_used": rej.get("technical_tools_used", []),
                                        "technical_alignment": rej.get("technical_alignment", "UNKNOWN"),
                                        "final_alignment_decision": rej.get("final_alignment_decision", "REJECT"),
                                        "rejection_reason": rej.get("rejection_reason", ""),
                                        "provenance_chain": rej.get("provenance_chain", {}),
                                        "is_mandatory": rej.get("is_mandatory", True),
                                        "fail_closed": rej.get("fail_closed", False),
                                        "sync_status": "REJECT",
                                    },
                                    bars=rej.get("data").iloc[:-1] if rej.get("data") is not None and hasattr(rej.get("data"), 'iloc') else None)
                    _trace.count("fundamental_reject")
            except Exception:
                pass
        candidates = accepted
        # Then rank by fundamental+technical sync (strong first) — PIT as_of=trade_date
        candidates = rank_by_fundamental_sync(candidates, as_of=trade_date)
    except Exception as e:
        try:
            # On filter error, check if mandatory — if mandatory, fail-closed (BLOCK), else fail-open
            from fundamental_sync_engine import _is_fundamental_mandatory
            is_mand = _is_fundamental_mandatory()
            if is_mand:
                append_log(AUDIT_LOG_FILE, f"FUNDAMENTAL SYNC FILTER ERROR (FAIL-CLOSED mandatory): {type(e).__name__}: {e} — NO TRADE for safety")
                # Fail-closed: clear candidates to block trades
                candidates = []
            else:
                append_log(AUDIT_LOG_FILE, f"FUNDAMENTAL SYNC FILTER ERROR (fail-open non-mandatory): {type(e).__name__}: {e}")
        except Exception:
            try:
                append_log(AUDIT_LOG_FILE, f"FUNDAMENTAL SYNC FILTER ERROR (fail-closed safe): {type(e).__name__}: {e}")
                candidates = []
            except Exception:
                pass

    candidates.sort(key=_priority_key, reverse=True)

    # [r30 TELEMETRY] Ranked-candidate photo: rank + both scores, exactly
    # as the slot budget will consume them (replay pillar — "kaunsa stock
    # kis rank pe tha aur kyun").
    try:
        _trace.set("candidates_ranked", [
            {"rank": i + 1, "symbol": c["symbol"],
             "sector_score": k[0], "signal_score": k[1]}
            for i, (c, k) in enumerate(
                (c, _priority_key(c)) for c in candidates)])
    except Exception:
        pass

    for candidate in candidates:
        try:
            if not has_free_slot():
                append_log(AUDIT_LOG_FILE, f"SCAN: slot budget full — remaining candidates skipped this cycle ({len(candidates) - candidates.index(candidate)} left)")
                for _left in candidates[candidates.index(candidate):]:
                    _trace.decision(_left["symbol"], "SKIP_SLOT_FULL",
                                    reason="slot budget full")
                break
            _trace.decision(candidate["symbol"], "EXECUTE_ATTEMPT")
            await _execute_candidate(candidate)
        except Exception as e:
            append_log(AUDIT_LOG_FILE, f"SCAN EXECUTE ERROR {candidate.get('symbol')}: {e}")
            _trace.count("execute_error")

    # [r30 TELEMETRY] Scan complete — market photo + counts + decision rows
    # ek hi atomic transaction me telemetry.db me likhe jate hain (fail-open).
    _trace.finish("COMPLETED")


async def _execute_candidate(candidate: dict):
    """[OVERRIDE 3] Phase 2 of the scan: actually enter a ranked candidate.
    Re-checks can_enter_trade() as a final defense-in-depth (time has
    passed since collection — another candidate earlier in this same
    ranked batch may have consumed the last slot, or conditions may have
    changed) before committing capital."""
    symbol = candidate["symbol"]
    current_price = float(candidate["data"]["close"].iloc[-1])
    # [F10 FIX] same to_thread wrap as the Phase-1 check above.
    allowed, reason = await asyncio.to_thread(can_enter_trade, symbol, current_price)
    if not allowed:
        append_log(AUDIT_LOG_FILE, f"BLOCKED AT EXECUTE {symbol}: {reason}")
        try:
            from telemetry import record_decision as _tel_dec
            _tel_dec(symbol, "BLOCKED_AT_EXECUTE", reason=reason,
                     context={"current_price": current_price})
        except Exception:
            pass
        return
    await _execute_entry(symbol, candidate["signal"], candidate["data"])


# ─────────────────────────────────────────────
# ENTRY EXECUTION
# ─────────────────────────────────────────────

async def _execute_entry(symbol: str, signal: dict, data: pd.DataFrame,
                          mode: str = "NORMAL"):
    entry_price = signal["entry_price"]
    sl_price    = signal["sl_price"]
    tp1_price   = signal["tp1_price"]
    reason      = signal.get("reason", "Strategy signal")

    security_id = get_security_id(symbol)
    if not security_id:
        try:
            from telemetry import record_decision as _tel_dec
            _tel_dec(symbol, "ENTRY_SKIP_NO_SECURITY_ID")
        except Exception:
            pass
        return

    # ─────────────────────────────────────────────
    # PILLAR 3: Fundamental + Technical Sync — Loss Pattern Detection (r39 CORRECTED)
    # REAL DATA ONLY, PIT-SAFE, FAIL-CLOSED when mandatory
    # Business Halal → Board → Fundamental Quality → Technical/SEQ → Fundamental×Technical confirmation
    # For trade date T: Only info publicly available on or before T may be used
    # Missing/stale/corrupt/invalid → NO TRADE when mandatory (not PASS/NEUTRAL)
    # ─────────────────────────────────────────────
    _fund_dna = {}
    _fund_eval = {}
    _fund_alignment = {}
    try:
        from fundamental_sync_engine import should_reject_due_to_weak_fundamentals, should_prioritize_due_to_strong_fundamentals, enrich_with_fundamental_dna, _is_fundamental_mandatory
        from fundamental_data import get_latest_fundamental_dna
        
        # PIT: trade date T = today (live) — only data available on or before T
        try:
            trade_date = now_ist().date().isoformat()
        except Exception:
            trade_date = None
        
        is_mandatory = _is_fundamental_mandatory()
        
        # Get DNA with PIT as_of=trade_date and fail-closed if mandatory
        _fund_dna = get_latest_fundamental_dna(symbol, as_of=trade_date, fail_closed_if_missing=is_mandatory)
        reject_weak, eval_res = should_reject_due_to_weak_fundamentals(symbol, as_of=trade_date)
        _fund_eval = eval_res
        
        # Build full alignment info for traceability: raw Fundamental → Technical → final decision
        technical_context = {
            "technical_status": "STRONG" if signal.get("signal_score", 0) > 0.5 else "NEUTRAL",
            "technical_tools_used": signal.get("tools_used", signal.get("technical_tools", ["SEQ", "EMA", "ATR"])),
            "technical_alignment": signal.get("alignment", "ALIGNED"),
            "reason": reason,
            "entry_price": entry_price,
            "sl_price": sl_price,
            "signal_score": signal.get("signal_score", 0),
        }
        _fund_alignment = enrich_with_fundamental_dna(symbol, technical_context, as_of=trade_date)
        
        if reject_weak:
            append_log(AUDIT_LOG_FILE,
                       f"FUNDAMENTAL REJECT (Pillar 3 CORRECTED REAL ONLY PIT as_of={trade_date}): {symbol} — {eval_res.get('reason')} | "
                       f"Technical: {reason} | Score: {eval_res.get('score')} | Status: {eval_res.get('fundamental_status')} | "
                       f"FinalDecision: {eval_res.get('final_alignment_decision')} | Mandatory: {is_mandatory} | Fail-closed: {eval_res.get('fail_closed')}")
            try:
                from telemetry import record_decision as _tel_dec
                _tel_dec(symbol, "REJECT_FUNDAMENTAL_WEAK",
                         reason=str(eval_res.get('rejection_reason') or eval_res.get('reason','')),
                         signal=signal,
                         context={
                             "trade_date": trade_date,
                             "as_of": trade_date,
                             "current_price": float(data["close"].iloc[-1]) if hasattr(data, 'iloc') else entry_price,
                             "fundamental_dna": _fund_dna,
                             "fundamental_evaluation": eval_res,
                             "fundamental_status": eval_res.get("fundamental_status", "UNKNOWN"),
                             "fundamental_score": eval_res.get("score", 0),
                             "fundamental_features": eval_res.get("dna", {}),
                             "technical_status": technical_context["technical_status"],
                             "technical_tools_used": technical_context["technical_tools_used"],
                             "technical_alignment": technical_context["technical_alignment"],
                             "final_alignment_decision": eval_res.get("final_alignment_decision", "REJECT"),
                             "rejection_reason": eval_res.get("rejection_reason", eval_res.get("reason", "")),
                             "provenance_chain": eval_res.get("provenance_chain", {}),
                             "is_mandatory": is_mandatory,
                             "fail_closed": eval_res.get("fail_closed", False),
                             "sync_status": "REJECT",
                             "technical_reason": reason,
                         },
                         bars=data.iloc[:-1] if hasattr(data, 'iloc') else None)
            except Exception:
                pass
            return
        # Profit Pattern — prioritize strong fundamentals (log only, ranking handled in scan)
        try:
            prio, prio_eval = should_prioritize_due_to_strong_fundamentals(symbol, as_of=trade_date)
            if prio:
                append_log(AUDIT_LOG_FILE,
                           f"FUNDAMENTAL PRIORITIZE (Pillar 3 CORRECTED REAL ONLY PIT as_of={trade_date}): {symbol} — {prio_eval.get('reason')} | Score: {prio_eval.get('score')} | FinalDecision: {prio_eval.get('final_alignment_decision')}")
        except Exception:
            pass
    except Exception as e:
        # On check error, fail-closed if mandatory, else fail-open
        try:
            from fundamental_sync_engine import _is_fundamental_mandatory
            is_mand = _is_fundamental_mandatory()
            if is_mand:
                append_log(AUDIT_LOG_FILE, f"FUNDAMENTAL CHECK ERROR (FAIL-CLOSED mandatory): {symbol}: {type(e).__name__}: {e} — NO TRADE for safety")
                try:
                    from telemetry import record_decision as _tel_dec
                    _tel_dec(symbol, "REJECT_FUNDAMENTAL_ERROR_FAIL_CLOSED",
                             reason=f"Fundamental check error (mandatory, fail-closed): {e}",
                             signal=signal,
                             context={
                                 "trade_date": trade_date if 'trade_date' in locals() else None,
                                 "fundamental_dna": _fund_dna if '_fund_dna' in locals() else {},
                                 "fundamental_status": "CHECK_ERROR_FAIL_CLOSED",
                                 "final_alignment_decision": "REJECT",
                                 "rejection_reason": f"Fundamental check error (mandatory): {e}",
                                 "fail_closed": True,
                                 "is_mandatory": True,
                             },
                             bars=data.iloc[:-1] if hasattr(data, 'iloc') else None)
                except Exception:
                    pass
                return
            else:
                append_log(AUDIT_LOG_FILE, f"FUNDAMENTAL CHECK ERROR (fail-open non-mandatory): {symbol}: {type(e).__name__}: {e}")
        except Exception:
            try:
                append_log(AUDIT_LOG_FILE, f"FUNDAMENTAL CHECK ERROR (FAIL-CLOSED safe): {symbol}: {type(e).__name__}: {e} — NO TRADE")
            except Exception:
                pass
            return
        _fund_dna = {"symbol": symbol, "available": False, "reason": f"check error: {e}", "fail_closed": False}
        _fund_eval = {"action": "UNKNOWN", "reason": str(e), "fail_closed": False}

    from per_stock_params import get_param
    sl_pct_val  = get_param(symbol, "sl_pct", None)
    tp1_pct_val = get_param(symbol, "tp1_pct", None)
    if sl_pct_val is None or tp1_pct_val is None:
        append_log(AUDIT_LOG_FILE, f"SKIP {symbol}: Optimized sl_pct or tp1_pct missing (Fail-Closed)")
        try:
            from telemetry import record_decision as _tel_dec
            _tel_dec(symbol, "ENTRY_SKIP_PARAMS_MISSING",
                     reason="optimized sl_pct/tp1_pct missing (fail-closed)")
        except Exception:
            pass
        return

    try:
        from capital_manager import get_low_balance_decision
        low_balance = get_low_balance_decision(
            symbol,
            entry_price,
            sl_price,
            signal_score=signal.get("signal_score", signal.get("sig_score", 1.0)),
            phase=signal.get("phase", ""),
        )
        if not low_balance.get("allow", False):
            append_log(AUDIT_LOG_FILE, f"SKIP {symbol}: {low_balance.get('reason')}")
            try:
                from telemetry import record_decision as _tel_dec
                _tel_dec(symbol, "ENTRY_SKIP_LOW_BALANCE",
                         reason=str(low_balance.get("reason", "")))
            except Exception:
                pass
            return
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"LOW BALANCE ENGINE ERROR ({symbol}): {e}")
        try:
            from telemetry import record_decision as _tel_dec
            _tel_dec(symbol, "ENTRY_SKIP_LOW_BALANCE_ERROR", reason=str(e))
        except Exception:
            pass
        return

    qty = calculate_qty_enhanced(
        symbol,
        entry_price,
        sl_price,
        signal_score=signal.get("signal_score", signal.get("sig_score", 1.0)),
        phase=signal.get("phase", ""),
    )
    if qty < 1:
        append_log(AUDIT_LOG_FILE, f"SKIP {symbol}: qty={qty} < 1")
        try:
            from telemetry import record_decision as _tel_dec
            _tel_dec(symbol, "ENTRY_SKIP_QTY_ZERO", reason=f"qty={qty} < 1")
        except Exception:
            pass
        return

    from config import ENTRY_ORDER_TYPE, CRASH_PENDING_ORDERS_FILE
    from utils import load_json as _lj, save_json as _sj

    # v5.0 owner rule: entry = LIMIT at signal price (existing verify flow
    # handles pending/cancel/race), exit = MARKET.
    # [r30 TELEMETRY — pillar 1] Bid/ask spread photo at the entry moment
    # (ONE budgeted depth call; raw payload already PIT-archived by NDSAP).
    _tel_spread = {}
    try:
        from telemetry import record_spread_context as _tel_spread_ctx
        _tel_spread = _tel_spread_ctx(symbol, security_id) or {}
    except Exception:
        pass

    result = place_order(security_id, symbol, qty, transaction_type="BUY",
                         order_type=ENTRY_ORDER_TYPE, price=entry_price)

    # [r30 TELEMETRY — pillar 2] Entry decision snapshot: order placed ya
    # reject — WHY + signal + live-price context + replay bars, fail-open.
    # PILLAR 3: Audit Attribution — explicitly record Fundamental DNA alongside Technical triggers
    try:
        from telemetry import record_decision as _tel_dec
        _ctx = {"order_id": result.get("order_id"), "qty": qty,
                "entry_price": entry_price, "sl_price": sl_price,
                "tp1_price": tp1_price,
                "order_type": ENTRY_ORDER_TYPE,
                "rejection_type": result.get("rejection_type"),
                "mode": mode, "spread": _tel_spread,
                "fundamental_dna": _fund_dna if '_fund_dna' in locals() else {},
                "fundamental_evaluation": _fund_eval if '_fund_eval' in locals() else {},
                "sync_status": _fund_eval.get("action") if '_fund_eval' in locals() and isinstance(_fund_eval, dict) else "UNKNOWN"}
        _tel_dec(symbol,
                 "ENTRY_ORDER_PLACED" if result.get("success") else "ENTRY_ORDER_REJECTED",
                 reason=str(result.get("message", "") or ""),
                 signal=signal,
                 context=_ctx,
                 bars=data.iloc[:-1])
    except Exception:
        pass

    # v5.0 CRASH-WINDOW SAFETY: order broker pe gaya, lekin bot yahin crash
    # ho jaye (state save se pehle) to position anath na rahe — turant
    # pending-order record likho; startup recovery isko adopt/clean karega.
    if result["success"] and result.get("order_id"):
        try:
            pending = _lj(CRASH_PENDING_ORDERS_FILE, {"orders": []})
            pending.setdefault("orders", []).append({
                "order_id": str(result["order_id"]),
                "symbol": symbol,
                "qty": qty,
                "entry_price": entry_price,
                "sl_price": sl_price,
                "tp1_price": tp1_price,
                "ts": now_ist().isoformat(),
            })
            _sj(CRASH_PENDING_ORDERS_FILE, pending)
        except Exception as e:
            logger.warning(f"enter_position: crash-pending record failed: {type(e).__name__}: {e}")
    if not result["success"]:
        # FIX-40: Handle rejection type
        rej_type = result.get("rejection_type", "UNKNOWN")
        if rej_type == "PERMANENT":
            await alert_admin(
                f"Order PERMANENTLY REJECTED: {symbol}\n"
                f"Reason: {result.get('message')}\n"
                f"No retry — manual check needed."
            )
        else:
            await alert_admin(
                f"Order FAILED: {symbol}\n{result.get('message')}"
            )
        return

    order_id = result["order_id"]
    requested_qty = qty
    status, fill_price = verify_order_status(order_id, wait_sec=int(PARAMS.get("order_verify_wait_sec", 10)))

    try:
        from telemetry import record_decision as _tel_dec
        _tel_dec(symbol, "ENTRY_VERIFY", reason=str(status),
                 context={"order_id": order_id, "status": status,
                          "fill_price": fill_price})
    except Exception:
        pass

    if status in ("REJECTED", "CANCELLED"):
        await alert_admin(f"Order {status}: {symbol} — Trade Cancelled")
        return
    if status == "PARTIAL":
        adopted, qty, fill_price = _try_adopt_partial_fill(
            order_id, requested_qty, fill_price, symbol, security_id,
            entry_price, sl_price, tp1_price)
        if adopted:
            status = "FILLED"
            await alert_admin(
                f"PARTIAL FILL ADOPTED: {symbol} qty={qty}/{requested_qty} "
                f"— SL/GTT armed on filled qty; remainder cancel after "
                f"{int(PARAMS.get('partial_fill_remainder_timeout_sec', 600))}s")
    if status != "FILLED":  # PENDING or unknown — dusra wait
        await asyncio.sleep(int(PARAMS.get("order_verify_second_wait_sec", 10)))
        status, fill_price = verify_order_status(order_id, wait_sec=0)
        if status == "PARTIAL":
            adopted, qty, fill_price = _try_adopt_partial_fill(
                order_id, requested_qty, fill_price, symbol, security_id,
                entry_price, sl_price, tp1_price)
            if adopted:
                status = "FILLED"
                await alert_admin(
                    f"PARTIAL FILL ADOPTED: {symbol} qty={qty}/{requested_qty} "
                    f"— SL/GTT armed on filled qty; remainder cancel after "
                    f"{int(PARAMS.get('partial_fill_remainder_timeout_sec', 600))}s")

    # [v5.9 ENTRY FOLLOW — owner D28] Ab bhi PENDING? Order RESTING mode me
    # chala jata hai (cancel NAHI). Entry LMT order exchange pe resting rehta
    # hai — jab CMP level pe aayegi, BROKER khud fill karega (bot ki latency
    # ka koi role nahi; lightning-speed moves covered). Har tick me
    # (entry_follow.tick_following_orders — monitor/scan cycle + EOD):
    #   FILLED → ADOPT (position register + GTT SL/TP arm)
    #   gap > risk_units × (entry−SL) → CANCEL (point-of-no-return; capital free)
    #   warna → RESTING continue (EOD exchange khud cancel karta hai)
    # Sirf execution rule — strategy/RR/optimizer ZERO touch.
    if status != "FILLED":
        if int(PARAMS.get("entry_follow_enabled", 1)):
            try:
                from entry_follow import register_following_order
                register_following_order(order_id=order_id, symbol=symbol,
                                         qty=qty, entry_price=entry_price,
                                         sl_price=sl_price, tp1_price=tp1_price,
                                         security_id=security_id)
                try:
                    from telemetry import record_decision as _tel_dec
                    _tel_dec(symbol, "ENTRY_RESTING_FOLLOW",
                             context={"order_id": order_id})
                except Exception:
                    pass
                await alert_admin(
                    f"Order RESTING: {symbol} — pending order follow mode me "
                    f"hai (cancel nahi hoga). Price entry level pe aate hi "
                    f"broker fill karega → SL/TP GTT turant arm.")
            except Exception as e:
                append_log(AUDIT_LOG_FILE,
                           f"ENTRY FOLLOW REGISTER ERROR {symbol}: {e} — "
                           f"fallback safety cancel")
                cancel_order(order_id)
                await alert_admin(
                    f"Order Safety Net: {symbol} follow-register fail hua — "
                    f"order cancel ({type(e).__name__}). Check karo.")
            return  # position abhi open NAHI — follow tick ADOPT karega
        # follow DISABLED → purana safety cancel (fail-closed)
        cancel_ok = cancel_order(order_id)
        if not cancel_ok:
            # [FIX-05] Check if order was actually filled at the last millisecond
            status_check, _race_fill_price = verify_order_status(order_id, wait_sec=int(PARAMS.get("order_race_check_wait_sec", 2)))
            if status_check == "FILLED":
                append_log(AUDIT_LOG_FILE, f"RACE CONDITION GATED: {symbol} filled at last millisecond before cancel. Syncing state.")
            else:
                await alert_admin(f"Order Safety Net: {symbol} cancel failed and order status is {status_check}. Check Dhan manually!")
                return
        else:
            # v5.0: cancel success = no position — crash-pending record clear
            try:
                pending = _lj(CRASH_PENDING_ORDERS_FILE, {"orders": []})
                pending["orders"] = [o for o in pending.get("orders", []) if str(o.get("order_id")) != str(order_id)]
                _sj(CRASH_PENDING_ORDERS_FILE, pending)
            except Exception as e:
                logger.warning(f"enter_position: crash-pending cancel cleanup failed: {type(e).__name__}: {e}")
            await alert_admin(f"Order Safety Net: {symbol} order unconfirmed/pending — Cancelled for safety")
        try:
            from telemetry import record_decision as _tel_dec
            _tel_dec(symbol, "ENTRY_SAFETY_CANCEL",
                     context={"order_id": order_id, "last_status": status})
        except Exception:
            pass
        return

    # [FIX — fill-price re-anchor] entry_price/sl_price/tp1_price above are the
    # pre-computed SIGNAL price (timeframe="1D" daily close), not the real
    # broker fill. MKT-style LIMIT-at-signal-price entries can fill at a
    # different price on gap days. Re-anchor to Dhan's real average fill price
    # here, preserving the original risk/reward distance (shift SL and TP1 by
    # the same signal-vs-fill gap rather than recomputing from scratch). Never
    # silent: falls back to the signal price with a loud audit-log line if
    # Dhan reports no fill price, and alerts admin if the gap is large.
    if fill_price and fill_price > 0:
        fill_gap_pct = abs(fill_price - entry_price) / entry_price * 100.0 if entry_price else 0.0
        shift = fill_price - entry_price
        sl_price = sl_price + shift
        tp1_price = tp1_price + shift
        if fill_gap_pct > float(PARAMS.get("fill_price_alert_threshold_pct", 1.0)):
            await alert_admin(
                f"⚠️ FILL PRICE GAP: {symbol} signal={entry_price} actual_fill={fill_price} "
                f"({fill_gap_pct:.2f}%) — SL/TP re-anchored to real fill."
            )
        append_log(AUDIT_LOG_FILE,
                   f"ENTRY RE-ANCHOR: {symbol} signal_price={entry_price} -> "
                   f"fill_price={fill_price} (gap={fill_gap_pct:.2f}%)")
        entry_price = fill_price
    else:
        append_log(AUDIT_LOG_FILE,
                   f"ENTRY RE-ANCHOR SKIPPED: {symbol} no fill price reported by broker — "
                   f"using signal price {entry_price} (Fail-loud, not silent)")

    # Params snapshot at entry
    strategy   = get_active_strategy()

    # [v4.2 SIZING-PARITY] Paper aur live SAME sizing chain use karte hain
    # (calculate_qty_enhanced → get_deployable_balance = stage × health ×
    # regime). Har trade me applied multipliers ka snapshot rakha jata hai —
    # isse paper log prove karta hai ki sizing live jaisi thi, aur backtest
    # se comparison ke liye real scale record hota hai. Fail-open: 1.0.
    sizing_scale = {}
    try:
        sizing_scale["stage_mult"] = float(get_stage_multiplier() or 1.0)
        sizing_scale["health_mult"] = float(get_health_capital_multiplier() or 1.0)
        sizing_scale["regime_mult"] = float(get_regime_capital_multiplier() or 1.0)
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"enter_position: sizing scale snapshot failed: {type(e).__name__}: {e} — recording 1.0")
        from fallback_monitor import record_fallback   # FIX-LIST item 17 (visibility only)
        record_fallback("trade_engine._execute_entry.sizing_scale", e, 1.0, symbol)

    trade_data = {
        "security_id":      security_id,
        "qty":              qty,
        "entry_price":      entry_price,
        "sl_price":         sl_price,
        "tp1_price":        tp1_price,
        "entry_time":       now_ist().isoformat(),
        "mode":             mode,
        "phase":            signal.get("phase") or detect_market_phase(data, symbol),
        "signal_score":     float(signal.get("signal_score", signal.get("sig_score", 1.0)) or 1.0),
        "tp1_hit":          False,
        "sl_pct":           sl_pct_val,
        "tp1_pct":          tp1_pct_val,
        "trail_multiplier": get_param(symbol, "trail_multiplier",
                                      PARAMS.get("trail_multiplier", 1.5)),
        "sizing_scale":     sizing_scale,
        "strategy_name":    strategy.name,
        "strategy_version": strategy.version,
    }

    register_trade(symbol, trade_data)
    # v5.0: entry fill confirm ho gaya + registered — crash-pending record clear
    try:
        pending = _lj(CRASH_PENDING_ORDERS_FILE, {"orders": []})
        oid = str(result.get("order_id") or "")
        before = len(pending.get("orders", []))
        pending["orders"] = [o for o in pending.get("orders", []) if str(o.get("order_id")) != oid]
        if len(pending.get("orders", [])) != before:
            _sj(CRASH_PENDING_ORDERS_FILE, pending)
    except Exception as e:
        logger.warning(f"enter_position: crash-pending cleanup failed: {type(e).__name__}: {e}")
    # [FIX-04] Persist signal deduplication candle key immediately after successful entry registration
    try:
        candle_key = f"{symbol}_{data.index[-1]}"
        processed = _load_processed_signals()
        processed[candle_key] = now_ist().isoformat()
        if len(processed) > 200:
            oldest = list(processed.keys())[0]
            del processed[oldest]
        _save_processed_signals(processed)
    except Exception as d_err:
        logger.warning(f"Failed to persist signal deduplication: {d_err}")

    try:
        from safety_manager import record_risk_used
        from capital_manager import get_deployable_balance
        # AUDIT FIX (Bug #7, units mismatch): use the true capital-weighted
        # risk % for THIS trade (risk amount / deployable capital), not the
        # raw per-stock sl_pct (a price-movement %, unrelated to portfolio
        # capital) -- see get_verified_risk_context()/calculate_qty_enhanced()
        # which used this same capital-relative risk % to size qty in the
        # first place.
        deployable_now = get_deployable_balance()
        if deployable_now and deployable_now > 0:
            risk_amount = qty * abs(entry_price - sl_price)
            true_risk_pct = (risk_amount / deployable_now) * 100.0
        else:
            true_risk_pct = float(trade_data["sl_pct"])  # fallback, fails toward stopping too early not too late
        record_risk_used(true_risk_pct)
    except (ImportError, RuntimeError, ValueError, TypeError, KeyError) as e:
        logger.warning(f"enter_position: Record risk used failed: {type(e).__name__}: {e}")

    # FIX-06: Only place GTT if state allows
    gtt_confirmed = True
    if can_place_gtt():
        gtt_result = setup_forever_orders(symbol, security_id, qty,
                             entry_price, sl_price)
        if not gtt_result.get("success"):
            gtt_confirmed = False
            logger.warning(f"enter_position: {symbol} entered with incomplete GTT protection")

    # P0-003 [r38 verified fix]: a filled position with no confirmed
    # protective GTT must not flow through normal continuation as if it
    # were fully protected. We still record the fill locally (the
    # position is real at the broker and must stay visible/trackable —
    # dropping it would hide risk, not reduce it), but we do NOT
    # broadcast/copy-trade an unprotected position into subscriber
    # accounts, and we reuse the existing RECONCILIATION_HOLD safety
    # state — same state startup_recovery.py already uses for this kind
    # of mismatch: blocks new_entries AND auto-exit (admin review
    # required before any action), still allows monitoring, and sends
    # the existing admin alert — instead of silently continuing as normal.
    log_trade_entry(symbol, qty, entry_price, sl_price, tp1_price, reason)

    if gtt_confirmed:
        await broadcast_trade_signal(symbol, "BUY", entry_price,
                                      sl_price, tp1_price, reason)

        subs = _get_active_linked_subscribers("BUY")
        if subs:
            await copy_trade_all_subscribers(subs, security_id, symbol, "BUY", admin_trade=trade_data)
    else:
        activate_reconciliation_hold(
            f"UNPROTECTED_POSITION: {symbol} qty={qty} filled at {entry_price} "
            f"with no confirmed protective GTT — new entries and auto-exit "
            f"blocked pending admin review (position still monitored)"
        )

    append_log(AUDIT_LOG_FILE,
               f"ENTRY: {symbol} qty={qty} price={entry_price} "
               f"strategy={strategy.name} | {reason}")


async def _execute_recovery_entry(symbol: str, current_price: float,
                                   data: pd.DataFrame):
    strategy    = get_active_strategy()
    signals     = strategy.generate_signals(data, symbol)
    buy_signals = [s for s in signals if s["action"] == "BUY"]
    if not buy_signals:
        return
    signal           = buy_signals[0]
    signal["reason"] = f"RECOVERY: {signal.get('reason', 'support bounce')}"
    await _execute_entry(symbol, signal, data, mode="RECOVERY")


# ─────────────────────────────────────────────
# POSITION MONITOR
# FIX-27: TP1 detection every 3 min (scheduler controlled)
# Known limitation: 3 min gap between checks — documented
# ─────────────────────────────────────────────

async def monitor_positions():
    from utils import is_killswitch_active

    if is_killswitch_active():
        return

    if not can_monitor():
        return

    # Partial-fill remainder: adopt extra fills; timeout → cancel unfilled.
    try:
        expire_partial_remainders()
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"PARTIAL REMAINDER TICK ERROR: {e}")

    # [v5.9] Entry-follow tick — resting pending orders ka status + CMP check
    # (fail-open: tick error se monitor rukta nahi, next cycle retry).
    try:
        from entry_follow import tick_following_orders
        res = await asyncio.to_thread(tick_following_orders)
        for _oid, _act in (res or {}).items():
            if _act.startswith(("ADOPTED", "CANCELLED", "CLEANED")):
                await alert_admin(f"Entry Follow: {_oid} → {_act}")
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"ENTRY FOLLOW TICK ERROR: {e}")

    active = get_active_trades()
    for symbol, trade in active.items():
        try:
            await _monitor_single(symbol, trade)
        except Exception as e:
            append_log(AUDIT_LOG_FILE, f"MONITOR ERROR {symbol}: {e}")


async def _monitor_single(symbol: str, trade: dict):
    # [F10 FIX] Synchronous Dhan candle fetch was called directly on the
    # asyncio event loop — a single hung network call here freezes the
    # entire bot (scan, other monitors, heartbeat, Telegram, live-tick
    # exits). Run it in a worker thread instead, same pattern already
    # used for the Phase-0 scan fetch above.
    data = await asyncio.to_thread(_fetch_candles, symbol, bars=50)
    if data is None or data.empty:
        return

    current_price = float(data["close"].iloc[-1])
    entry_price   = trade["entry_price"]
    # v5.3: tp1_price ab sirf metadata hai (display/log) — exits trailing-driven
    mode          = trade.get("mode", "NORMAL")

    update_watermark(symbol, current_price)

    # v5.0 EXIT-IN-PROGRESS: pehle wala SELL order abhi pending hai — naya
    # SELL mat bhejo (double-sell risk); usi order ka status verify karo.
    pending_order_id = trade.get("exit_in_progress")
    if pending_order_id:
        status, _fp = verify_order_status(pending_order_id, wait_sec=0)
        if status == "FILLED":
            trade.pop("exit_in_progress", None)
            await _finalize_exit(symbol, trade, current_price,
                                 trade.get("exit_reason_pending", "Exit (pending order filled)"), mode)
        elif status in ("REJECTED", "CANCELLED"):
            trade.pop("exit_in_progress", None)
            trade.pop("exit_reason_pending", None)
            append_log(AUDIT_LOG_FILE,
                       f"EXIT RETRY: {symbol} pending order {pending_order_id} {status} — GTT intact, fresh SELL next check")
        return

    # v5.4 UNIFIED EXIT TOOLKIT (owner rule: lock/trail sirf EK tool; optimizer
    # decide karega) — backtest == live ek hi engine (exit_engine):
    #   fixed_tp: TP pe exit | trail: ATR trail + breakeven | hybrid: TP lock +
    #   trail | ratchet: progressive profit lock + trail
    # PROFIT-LOCK GUARANTEE: profit reach hua to exit us lock ke neeche nahi
    # (lalach-safe). Floor SL (candle-low) kabhi nahi ghat-ta. GTT follow.
    # FIX-LIST 2026-09-04 item 3: the state math lives in ONE shared helper
    # (_evaluate_exit_state) used by BOTH this 3-min monitor and the
    # WebSocket tick path (on_live_tick) — so the two can never drift apart.
    atr_period = int(get_param(symbol, "atr_period", 14) or 14)
    atr_v = _calculate_atr(data, atr_period)
    exit_now, reason = _evaluate_exit_state(symbol, trade, current_price, atr_v)

    if exit_now:
        if not can_exit():
            append_log(AUDIT_LOG_FILE,
                       f"EXIT BLOCKED by state: {symbol} — {reason} hit but exit not allowed")
            return
        await _execute_exit(symbol, trade, current_price, reason, mode)
        return


# ─────────────────────────────────────────────
# LIVE TICK EXIT PATH (FIX-LIST 2026-09-04 item 3)
# ─────────────────────────────────────────────
# The 3-minute scheduler monitor (_monitor_single) stays exactly as it is —
# it is the safety net and the parity reference. The WebSocket feed only
# makes exits FASTER: every tick for an OPEN bot position is run through the
# SAME exit_engine math with the SAME persisted state, and if the engine says
# exit, the SAME _execute_exit() path is used (MARKET order, fill verify,
# GTT cancel, subscriber SELL copy). No second exit implementation exists.
#
# Safety properties:
#   * per-symbol asyncio.Lock → a burst of ticks can never place two SELLs;
#   * ticks are throttled to at most one evaluation per
#     PARAMS["live_tick_min_interval_sec"] per symbol (ATR still comes from
#     candles — fetched at most once per PARAMS["live_tick_atr_refresh_sec"]);
#   * every gate the monitor honours (killswitch, can_monitor, can_exit,
#     exit_in_progress guard) is honoured here too;
#   * any exception is logged and swallowed — a bad tick must never kill the
#     feed thread or the Telegram loop; the 3-min monitor still runs.

_LIVE_TICK_LOCKS: dict = {}
_LIVE_TICK_LAST_EVAL: dict = {}
_LIVE_TICK_ATR_CACHE: dict = {}   # symbol -> (monotonic_ts, atr_value)
_LIVE_TICK_STATS: dict = {"ticks": 0, "evaluated": 0, "exits": 0, "skipped_no_position": 0}


def _live_tick_lock(symbol: str) -> asyncio.Lock:
    lock = _LIVE_TICK_LOCKS.get(symbol)
    if lock is None:
        lock = asyncio.Lock()
        _LIVE_TICK_LOCKS[symbol] = lock
    return lock


def _symbol_for_security_id(security_id: str, active: dict) -> str:
    sid = str(security_id or "").strip()
    if not sid:
        return ""
    for sym, trade in active.items():
        if str(trade.get("security_id", "")).strip() == sid:
            return sym
    return ""


def get_live_watchlist() -> list:
    """(exchange_segment_code, security_id) for every OPEN bot position —
    what bot.py subscribes on the WebSocket. Only bot-held positions are
    watched (owner rule 9: sirf bot-dili positions exit hoti hain)."""
    out = []
    try:
        for _sym, trade in get_active_trades().items():
            sid = str(trade.get("security_id", "")).strip()
            if sid and sid.lower() not in ("none", "nan"):
                out.append(sid)
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"LIVE WATCHLIST ERROR: {e}")
    return out


def _cached_atr(symbol: str, period: int) -> float:
    """ATR from candles, refreshed at most every live_tick_atr_refresh_sec.
    Returns 0.0 when unavailable — exit_engine then behaves like fixed floor
    (trail cannot move) which is the conservative direction."""
    import time as _time
    ttl = float(PARAMS.get("live_tick_atr_refresh_sec", 180) or 180)
    now = _time.monotonic()
    ts, val = _LIVE_TICK_ATR_CACHE.get(symbol, (0.0, None))
    if val is not None and (now - ts) < ttl:
        return val
    try:
        data = _fetch_candles(symbol, bars=50)
        atr_v = _calculate_atr(data, period) if data is not None and not data.empty else 0.0
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"LIVE TICK ATR ERROR {symbol}: {e}")
        atr_v = val if val is not None else 0.0
    _LIVE_TICK_ATR_CACHE[symbol] = (now, float(atr_v or 0.0))
    return float(atr_v or 0.0)


async def on_live_tick(tick: dict):
    """Entry point for dhan_live_feed → called on the bot's event loop.

    tick = {"security_id": "1333", "ltp": 2871.5, ...} (see
    DhanLiveFeed.parse_tick). Anything that is not an open bot position is
    ignored cheaply (no I/O)."""
    import time as _time
    from utils import is_killswitch_active

    try:
        _LIVE_TICK_STATS["ticks"] += 1
        ltp = float(tick.get("ltp") or 0.0)
        if ltp <= 0:
            return
        active = get_active_trades()
        symbol = _symbol_for_security_id(tick.get("security_id"), active)
        if not symbol:
            _LIVE_TICK_STATS["skipped_no_position"] += 1
            return
        if is_killswitch_active() or not can_monitor():
            return
        # Dhan AMO has no MARKET support — live-tick MARKET exit only in session.
        # Overnight SL remains on broker GTT; monitor retries from 09:15.
        from utils import is_market_open
        if not is_market_open():
            return

        min_gap = float(PARAMS.get("live_tick_min_interval_sec", 1.0) or 1.0)
        now = _time.monotonic()
        if now - _LIVE_TICK_LAST_EVAL.get(symbol, 0.0) < min_gap:
            return

        lock = _live_tick_lock(symbol)
        if lock.locked():
            return  # an evaluation/exit for this symbol is already in flight
        async with lock:
            _LIVE_TICK_LAST_EVAL[symbol] = now
            # Re-read: the position may have been closed while we waited.
            trade = get_active_trades().get(symbol)
            if not trade:
                return
            if trade.get("exit_in_progress"):
                return  # monitor cycle follows that order — never a 2nd SELL
            _LIVE_TICK_STATS["evaluated"] += 1
            update_watermark(symbol, ltp)
            atr_period = int(get_param(symbol, "atr_period", 14) or 14)
            # [F10 FIX, same class] _cached_atr() only hits the network on a
            # TTL miss, but that miss is still a synchronous Dhan call sitting
            # directly on this exact live-tick loop -- to_thread it too.
            atr_v = await asyncio.to_thread(_cached_atr, symbol, atr_period)
            exit_now, reason = _evaluate_exit_state(symbol, trade, ltp, atr_v)
            if not exit_now:
                return
            if not can_exit():
                append_log(AUDIT_LOG_FILE,
                           f"LIVE TICK EXIT BLOCKED by state: {symbol} — {reason}")
                return
            _LIVE_TICK_STATS["exits"] += 1
            append_log(AUDIT_LOG_FILE, f"LIVE TICK EXIT TRIGGER: {symbol} ltp={ltp} {reason}")
            await _execute_exit(symbol, trade, ltp, reason + " [live-tick]",
                                trade.get("mode", "NORMAL"))
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"LIVE TICK ERROR {tick.get('security_id')}: {type(e).__name__}: {e}")


def _evaluate_exit_state(symbol: str, trade: dict, current_price: float, atr_v: float):
    """The exit_engine block shared by _monitor_single and on_live_tick:
    rebuild persisted state → step → persist floor/flags → GTT follow.
    Returns (exit_now: bool, reason: str). Pure state math + persistence;
    order placement is the caller's job."""
    from exit_engine import init_state, step as exit_step
    entry_price = trade["entry_price"]
    floor_sl = trade["sl_price"]
    st = init_state({
        "exit_mode": get_param(symbol, "exit_mode", PARAMS.get("exit_mode", "hybrid")),
        "min_reward_risk": PARAMS.get("min_reward_risk", 1.8),
        "trail_multiplier": float(trade.get("trail_multiplier",
                                            PARAMS.get("trail_multiplier", 1.5)) or 1.5),
        "profit_lock_pct": get_param(symbol, "profit_lock_pct",
                                     PARAMS.get("profit_lock_pct", 1.0)),
        "ratchet_step_pct": get_param(symbol, "ratchet_step_pct",
                                      PARAMS.get("ratchet_step_pct", 1.5)),
    }, entry_price, floor_sl)
    st["activated"] = bool(trade.get("trail_activated", False))
    st["tp_hit"] = bool(trade.get("tp_hit", False))
    st["floor"] = max(float(trade.get("trail_sl", floor_sl) or floor_sl), floor_sl)
    st["next_ratchet"] = float(trade.get("next_ratchet", st["next_ratchet"]) or st["next_ratchet"])

    old_floor = st["floor"]
    exit_now = exit_step(st, current_price, current_price, current_price, atr_v)

    if st["floor"] > old_floor:
        try:
            from forever_order_manager import update_trail_sl
            update_trail_sl(symbol, st["floor"])
        except (ImportError, RuntimeError, ValueError) as e:
            logger.warning(f"trail follow failed for {symbol}: {type(e).__name__}: {e}")
    update_trade(symbol, {"trail_activated": st["activated"], "tp_hit": st["tp_hit"],
                          "next_ratchet": st["next_ratchet"],
                          "trail_sl": round(st["floor"], 2)})
    trade["trail_activated"] = st["activated"]
    trade["trail_sl"] = round(st["floor"], 2)

    if not exit_now:
        return False, ""
    tags = {"fixed_tp": "TP hit (exit_mode=fixed_tp)",
            "trail": "Trail hit (ATR trail)",
            "hybrid": "Exit (hybrid: TP lock + trail)",
            "ratchet": "Exit (ratchet: profit locked + trail)"}
    reason = tags.get(st["mode"], f"Exit (exit_mode={st['mode']})")
    if st["floor"] > entry_price:
        # AI-DOS LOGIC-001 fix: live-path guard — a corrupted 0 entry_price
        # must not crash exit-reason formatting.
        reason += f" — profit locked at {round((safe_div(st['floor'], entry_price, default=1.0) - 1.0) * 100.0, 2)}%"
    return True, reason


# ─────────────────────────────────────────────
# EXIT EXECUTION (v5.0 — MARKET order + fill verify)
# ─────────────────────────────────────────────

async def _execute_exit(symbol: str, trade: dict, exit_price: float,
                         exit_reason: str, mode: str = "NORMAL"):
    """
    v5.0 owner rule: exit = MARKET order, lekin place hone ke BAAD fill
    verify zaroori (market order bhi India me reject ho sakta hai — lower
    circuit/RMS/T2T). Fill confirm hone se pehle: GTT cancel NAHI, position
    release NAHI, subscriber copy NAHI — warna "nikal gaye soch ke andar"
    wala dangerous case banta hai (SL bhi cancel ho jata).
    """
    from config import EXIT_ORDER_TYPE
    security_id = trade.get("security_id")
    qty         = trade.get("qty", 0)

    result = place_order(security_id, symbol, qty,
                         transaction_type="SELL", order_type=EXIT_ORDER_TYPE)

    if not result["success"]:
        # REJECTED at placement — GTT intact, position intact; retry next
        # monitor cycle (bounded), loud alert once.
        rej_type = result.get("rejection_type", "UNKNOWN")
        if rej_type in ("PERMANENT", "MARKET_CLOSED") or "market" in result.get("message", "").lower():
            append_log(AUDIT_LOG_FILE,
                       f"EXIT REJECTED (market closed?): {symbol} — GTT active, reconciliation will sync")
            await alert_admin(
                f"EXIT ORDER REJECTED: {symbol}\n"
                f"Reason: {result.get('message', 'Unknown')}\n\n"
                f"Action: position NOT closed locally, GTT orders still active at broker.\n"
                f"Bot will retry next monitor cycle / reconciliation will sync.")
        else:
            append_log(AUDIT_LOG_FILE, f"EXIT PLACE FAILED: {symbol} {result.get('message')} — retry next cycle")
            await alert_admin(f"EXIT ORDER FAILED: {symbol}\n{result.get('message')}\nBot will retry.")
        return

    order_id = result["order_id"]
    if str(order_id).startswith("PAPER-"):
        # Paper mode — fill simulate hota hai; directly finalize.
        await _finalize_exit(symbol, trade, exit_price, exit_reason, mode)
        return

    # ── FILL VERIFY (market order) ──
    status, _fp = verify_order_status(order_id, wait_sec=0)
    if status not in ("FILLED", "TRADED", "EXECUTED"):
        retry_sec = int(PARAMS.get("exit_verify_retry_sec", 5))
        await asyncio.sleep(retry_sec)
        status, _fp = verify_order_status(order_id, wait_sec=0)

    if status in ("FILLED", "TRADED", "EXECUTED"):
        await _finalize_exit(symbol, trade, exit_price, exit_reason, mode)
    elif status in ("REJECTED", "CANCELLED"):
        # GTT intact, position intact — fresh retry next cycle.
        append_log(AUDIT_LOG_FILE,
                   f"EXIT FILL REJECTED: {symbol} order={order_id} status={status} — GTT intact, retry next cycle")
        await alert_admin(
            f"⚠️ EXIT {status}: {symbol} order {order_id}\n"
            f"Position abhi bhi open hai; GTT SL intact (protection active).\n"
            f"Bot agle monitor cycle me retry karega.")
    else:
        # PENDING — in-progress guard; monitor usi order ko follow karega.
        trade["exit_in_progress"] = order_id
        trade["exit_reason_pending"] = exit_reason
        append_log(AUDIT_LOG_FILE,
                   f"EXIT PENDING: {symbol} order={order_id} status={status} — following same order (no duplicate SELL)")


async def _finalize_exit(symbol: str, trade: dict, exit_price: float,
                         exit_reason: str, mode: str = "NORMAL"):
    """v5.0: fill confirm hone ke BAAD hi — GTT cancel, release, broadcast, copy."""
    security_id = trade.get("security_id")
    qty         = trade.get("qty", 0)

    try:
        close_forever_orders(symbol)
    except Exception as e:
        append_log(AUDIT_LOG_FILE,
                   f"FOREVER CANCEL ERROR on exit {symbol}: {e}")
        await alert_admin(
            f"Forever order cancel failed for {symbol}. Check Dhan manually!"
        )

    log_trade_exit(symbol, exit_price, exit_reason)
    release_trade(symbol)

    if mode == "RECOVERY":
        if "SL" in exit_reason.upper():
            recovery_sl_hit(symbol)
        else:
            recovery_success(symbol)
    elif "SL" in exit_reason.upper():
        check_and_apply_soft_block(symbol, exit_price)

    pnl = (exit_price - trade["entry_price"]) * qty
    await broadcast_exit(symbol, exit_price, pnl, exit_reason)

    # v5.0: subscriber SELL copy sirf admin exit FILL hone ke baad (yahan)
    subs = _get_active_linked_subscribers("SELL")
    if subs:
        await copy_trade_all_subscribers(subs, security_id, symbol, "SELL", admin_trade=trade)

    append_log(AUDIT_LOG_FILE,
               f"EXIT: {symbol} price={exit_price} "
               f"reason={exit_reason} pnl={pnl:.2f}")


# ─────────────────────────────────────────────
# FIX-11: RECONCILIATION ACTION MATRIX
# 3:40 PM daily — 3 cases, explicit handling
# ─────────────────────────────────────────────

async def run_reconciliation():
    """
    FIX-11: Reconciliation Action Matrix:

    Case 1: Bot open + Dhan closed
            → Update local state, log anomaly
            → DO NOT alert subscriber (silent clean)

    Case 2: Bot closed + Dhan open
            → Emergency admin alert
            → Bot does NOTHING — manual review only
            → Activate RECONCILIATION_HOLD

    Case 3: Qty mismatch
            → Admin alert
            → DO NOT auto-correct
            → Activate RECONCILIATION_HOLD
    """
    try:
        from broker import get_holdings
        from capital_manager import get_active_trades, release_trade

        # FIX: a failed holdings fetch must NOT be treated the same as
        # "Dhan confirmed zero open positions" -- previously get_holdings()
        # swallowed API errors into an empty list, which Case 1 below would
        # then silently interpret as "every bot-tracked position was closed
        # by Dhan" and wipe them all out with no admin alert (Case 1 is
        # explicitly designed to be silent). Verify the fetch succeeded
        # before doing any comparison.
        try:
            holdings = get_holdings()
        except Exception as e:
            append_log(AUDIT_LOG_FILE, f"RECONCILIATION: could not verify Dhan holdings -- {type(e).__name__}: {e}")
            from bot_state_manager import activate_reconciliation_hold
            activate_reconciliation_hold(
                f"Reconciliation: could not verify Dhan holdings ({type(e).__name__}: {e}) -- manual check required"
            )
            await alert_admin(
                "⚠️ RECONCILIATION: Could not fetch Dhan holdings "
                f"({type(e).__name__}: {e}).\n\n"
                "Bot placed in RECONCILIATION_HOLD as a precaution -- "
                "NOT treated as 'zero positions'. Please check Dhan manually "
                "and /resume when verified."
            )
            return

        dhan_open    = {h["tradingSymbol"]: h for h in holdings
                        if float(h.get("totalQty", 0)) > 0}
        bot_open     = get_active_trades()

        mismatches  = []
        anomalies   = []
        ghost_pos   = []

        # Case 1: Bot open + Dhan closed
        for symbol in list(bot_open.keys()):
            if symbol not in dhan_open:
                anomalies.append(symbol)
                append_log(AUDIT_LOG_FILE,
                           f"RECONCILIATION Case1: {symbol} bot=open dhan=closed")
                # FIX: real fill price is unknown, but recording 0.0 here
                # previously caused a fake ~-100% P&L (gross_pnl = (0 -
                # entry_price) * qty) to be logged, corrupting day_pnl,
                # drawdown, and win-rate stats used by the live safety
                # system. Approximate with the position's strict SL price
                # (candle-low at entry — the most likely trigger for an
                # unattended exit now that there's no trailing SL),
                # falling back to entry price (0% impact) if no SL state
                # exists -- still approximate, which is why this remains a
                # logged, reviewable anomaly.
                approx_exit_price = bot_open[symbol].get("entry_price", 0.0)
                try:
                    from forever_order_manager import get_sl
                    sl_price = float(get_sl(symbol) or 0)
                    if sl_price > 0:
                        approx_exit_price = sl_price
                except (TypeError, ValueError, ImportError) as e:
                    logger.warning(f"reconcile_positions: SL lookup failed for {symbol}: {type(e).__name__}: {e}")
                log_trade_exit(symbol, approx_exit_price,
                               "Reconciliation: Dhan closed, bot updated "
                               "-- exit price APPROXIMATED, verify against Dhan trade book")
                release_trade(symbol)
                try:
                    close_forever_orders(symbol)
                except (ImportError, RuntimeError, ValueError) as e:
                    logger.warning(f"reconcile_positions: Close forever orders failed for {symbol}: {type(e).__name__}: {e}")

        # Case 2: Dhan open + Bot closed
        for symbol in dhan_open:
            if symbol not in bot_open:
                ghost_pos.append(symbol)
                append_log(AUDIT_LOG_FILE,
                           f"RECONCILIATION Case2: {symbol} dhan=open bot=closed — MANUAL REVIEW")

        # Case 3: Qty mismatch
        for symbol, trade in bot_open.items():
            if symbol in dhan_open:
                dhan_qty = int(dhan_open[symbol].get("totalQty", 0))
                bot_qty  = trade.get("qty", 0)
                if dhan_qty != bot_qty:
                    mismatches.append(
                        f"{symbol}: Bot={bot_qty} Dhan={dhan_qty}"
                    )
                    append_log(AUDIT_LOG_FILE,
                               f"RECONCILIATION Case3 QTY MISMATCH: {symbol}")

        # Alerts
        if anomalies:
            append_log(AUDIT_LOG_FILE,
                       f"RECONCILIATION: {len(anomalies)} positions cleaned")

        if ghost_pos:
            await alert_admin(
                f"RECONCILIATION ALERT — Case 2\n\n"
                f"Dhan has open positions not in bot:\n"
                + "\n".join(ghost_pos) +
                f"\n\nBot doing NOTHING — manual review required.\n"
                f"Bot in RECONCILIATION_HOLD."
            )
            from bot_state_manager import activate_reconciliation_hold
            activate_reconciliation_hold()

        if mismatches:
            await alert_admin(
                f"RECONCILIATION ALERT — Qty Mismatch\n\n"
                + "\n".join(mismatches) +
                f"\n\nDO NOT auto-correct.\n"
                f"Manual review required.\n"
                f"Bot in RECONCILIATION_HOLD."
            )
            from bot_state_manager import activate_reconciliation_hold
            activate_reconciliation_hold()

        if not ghost_pos and not mismatches:
            append_log(AUDIT_LOG_FILE, "RECONCILIATION: All positions match")

    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"RECONCILIATION ERROR: {e}")


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _fetch_candles(symbol: str, bars: int = None) -> pd.DataFrame:
    try:
        from per_stock_params import get_param
        tf = get_param(symbol, "timeframe", PARAMS.get("timeframe", None))
        if not tf:
            append_log(AUDIT_LOG_FILE, f"SKIP {symbol}: Timeframe parameter missing (Fail-Closed)")
            return None
        bars = bars or PARAMS.get("candle_lookback", 100)
        from dhan_data import fetch_data
        df = fetch_data(symbol, tf, bars)
        if df is None or df.empty:
            return None
        return df.tail(bars)
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"FETCH CANDLES ERROR ({symbol}): {e}")
        return None


def _calculate_atr(data: pd.DataFrame, period: int = 14) -> float:
    try:
        # [PHD-FIX F4 completion] Wilder smoothing (alpha=1/period) — matches
        # strategy.calc_atr()/strategy_tools.calc_atr() (backtest side) so
        # live and backtest ATR stay in parity, and matches this codebase's
        # own declared standard (same alpha calc_rsi/calculate_adx already use).
        tr = pd.concat([
            data["high"] - data["low"],
            (data["high"] - data["close"].shift()).abs(),
            (data["low"]  - data["close"].shift()).abs()
        ], axis=1).max(axis=1)
        return float(tr.ewm(alpha=1.0 / period, adjust=False).mean().iloc[-1])
    except (TypeError, ValueError, IndexError, AttributeError, ZeroDivisionError) as e:
        # AI-DOS LOGIC-001 fix: ZeroDivisionError (period=0 caller bug) was not
        # previously caught here — added to the existing fail-soft contract.
        logger.warning(f"calculate_atr: ATR calculation failed: {type(e).__name__}: {e}")
        return 0.0


def _get_active_linked_subscribers(transaction_type: str = "BUY") -> list:
    from config import SUBSCRIBERS_FILE
    from utils import load_json
    subs = load_json(SUBSCRIBERS_FILE, {"subscribers": {}})
    tx = transaction_type.upper()
    allowed = {"LIVE_ACTIVE"} if tx == "BUY" else {"LIVE_ACTIVE", "EXPIRED_EXIT_ONLY"}
    return [
        s for s in subs.get("subscribers", {}).values()
        if s.get("status") in allowed and s.get("dhan_linked")
    ]


# ═════════════════════════════════════════════════════════════════════════
# v5.0 — CRASH-WINDOW RECOVERY (Tier 1)
# ═════════════════════════════════════════════════════════════════════════
def recover_pending_orders() -> dict:
    """
    Boot pe chalta hai (startup_recovery): jo orders crash se pehle broker
    pe place ho gaye the unka status verify karo:
    - FILLED + bot ne track nahi kiya → position ADOPT (register + GTT re-arm)
    - REJECTED/CANCELLED → record clean (kuch nahi karna)
    Returns {order_id: action}.
    """
    from utils import load_json as _lj, save_json as _sj
    from config import CRASH_PENDING_ORDERS_FILE
    results = {}
    try:
        pending = _lj(CRASH_PENDING_ORDERS_FILE, {"orders": []})
        orders = list(pending.get("orders", []))
        if not orders:
            return results
        append_log(AUDIT_LOG_FILE, f"CRASH RECOVERY: {len(orders)} pending order(s) found at boot")
        for rec in orders:
            oid = str(rec.get("order_id") or "")
            symbol = rec.get("symbol", "")
            try:
                status, _fp = verify_order_status(oid, wait_sec=0)
            except Exception as e:
                status = "UNKNOWN"
                append_log(AUDIT_LOG_FILE, f"CRASH RECOVERY: verify failed {oid} {symbol}: {e}")
            if status in ("FILLED", "TRADED", "EXECUTED"):
                from capital_manager import get_active_trades
                if symbol not in get_active_trades():
                    trade_data = {
                        "security_id": rec.get("security_id") or "",
                        "qty": int(rec.get("qty") or 0),
                        "entry_price": float(rec.get("entry_price") or 0),
                        "sl_price": float(rec.get("sl_price") or 0),
                        "tp1_price": float(rec.get("tp1_price") or 0),
                        "entry_time": rec.get("ts", now_ist().isoformat()),
                        "mode": "NORMAL",
                        "phase": "CRASH_ADOPT",
                        "signal_score": 1.0,
                        "tp1_hit": False,
                        "strategy_name": "crash_adopt",
                        "strategy_version": "v5.0",
                    }
                    if trade_data["qty"] > 0 and trade_data["entry_price"] > 0:
                        register_trade(symbol, trade_data)
                        append_log(AUDIT_LOG_FILE,
                                   f"CRASH ADOPT: {symbol} order={oid} FILLED but untracked — position adopted (SL {trade_data['sl_price']})")
                        try:
                            from forever_order_manager import setup_forever_orders
                            sec_id = rec.get("security_id") or get_security_id(symbol)
                            if sec_id:
                                setup_forever_orders(symbol, sec_id, trade_data["qty"],
                                                     trade_data["entry_price"], trade_data["sl_price"])
                        except Exception as e:
                            append_log(AUDIT_LOG_FILE, f"CRASH ADOPT GTT failed {symbol}: {e}")
                        results[oid] = "ADOPTED"
                else:
                    results[oid] = "ALREADY_TRACKED"
            elif status in ("REJECTED", "CANCELLED"):
                results[oid] = f"CLEANED({status})"
            else:
                results[oid] = f"LEFT({status})"
        remaining = [o for o in orders if results.get(str(o.get("order_id")), "").startswith("LEFT")]
        _sj(CRASH_PENDING_ORDERS_FILE, {"orders": remaining})
        append_log(AUDIT_LOG_FILE, f"CRASH RECOVERY DONE: {results}")
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"CRASH RECOVERY ERROR: {type(e).__name__}: {e}")
    return results
