"""Weekly-review/auto-reoptimize/overnight-movers/MTF-warehouse research jobs (split out of scheduler.py, AI-DOS ARCH-003 god-module remediation, 2026-09-17)."""

import logging
from config import PARAMS, AUDIT_LOG_FILE
from utils import append_log

logger = logging.getLogger(__name__)


async def _weekly_review_job():
    from signal_broadcaster import alert_admin
    from backtester import check_backtest_staleness
    staleness = check_backtest_staleness()
    await alert_admin(
        f"Weekly Review\n{staleness['message']}\n\n"
        f"Use /backtest to refresh.\n"
        f"Use /strategyvalidator to check performance."
    )


async def _auto_reoptimize_job():
    """v5.0 Tier 3: model taza rakhne ke liye weekly optimize — PROPOSAL only."""
    try:
        if not bool(PARAMS.get("enable_auto_reoptimize", False)):
            return
        append_log(AUDIT_LOG_FILE, "AUTO REOPTIMIZE: start (proposal only — approval admin ke haath)")
        import asyncio

        def _run():
            from optimizer import optimize_full_universe
            optimize_full_universe()

        await asyncio.to_thread(_run)
        append_log(AUDIT_LOG_FILE, "AUTO REOPTIMIZE: complete — proposal ready (/deploystatus)")
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"AUTO REOPTIMIZE ERROR: {type(e).__name__}: {e}")


async def _overnight_prefetch_job():
    """14:00 — heavy pre-fetch (events scrape + intraday snapshots)."""
    try:
        from overnight_movers import is_overnight_enabled, prefetch_overnight_snapshots
        if not is_overnight_enabled():
            return
        import asyncio
        await asyncio.to_thread(prefetch_overnight_snapshots)
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"OVERNIGHT PREFETCH JOB ERROR: {type(e).__name__}: {e}")


async def _overnight_scan_job():
    """
    15:00 — LOCAL scan (cached data) + top-N candidates ki entry existing
    trade_engine chain se (mode=OVERNIGHT). Paper/live dono isi path pe —
    paper mode me orders simulate hote hain (existing PAPER check).
    """
    try:
        from overnight_movers import is_overnight_enabled, build_overnight_signals, record_overnight_entry
        if not is_overnight_enabled():
            return
        import asyncio
        signals = await asyncio.to_thread(build_overnight_signals)
        if not signals:
            append_log(AUDIT_LOG_FILE, "OVERNIGHT SCAN: no candidates above threshold")
            return
        from trade_engine import _execute_entry, _fetch_candles
        for sig in signals:
            try:
                symbol = sig["symbol"]
                data = _fetch_candles(symbol)
                if data is None or data.empty:
                    continue
                await _execute_entry(symbol, sig, data, mode="OVERNIGHT")
                record_overnight_entry(symbol, sig["entry_price"], sig["sl_price"],
                                       sig["tp1_price"], sig.get("signal_score", 0.5))
            except Exception as e:
                append_log(AUDIT_LOG_FILE, f"OVERNIGHT ENTRY ERROR {sig.get('symbol')}: {type(e).__name__}: {e}")
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"OVERNIGHT SCAN JOB ERROR: {type(e).__name__}: {e}")


async def _overnight_exit_job():
    """
    Next-day 10:30 — overnight positions jo TP/SL pe exit nahi hue unka
    time-based exit + paper-proof outcome record (day high/low ke saath,
    optimizer ke liye). Existing exit chain reuse (fill-verify ke saath).
    """
    try:
        from overnight_movers import is_overnight_enabled, record_overnight_outcome
        if not is_overnight_enabled():
            return
        from capital_manager import get_active_trades
        from trade_engine import _execute_exit, _fetch_candles
        from dhan_data import get_live_price
        from overnight_movers import sync_outcomes_from_trades
        sync_outcomes_from_trades()  # monitor ke TP/SL exits bhi paper track me
        for symbol, trade in list(get_active_trades().items()):
            try:
                if trade.get("mode") != "OVERNIGHT":
                    continue
                data = _fetch_candles(symbol, bars=50)
                if data is None or data.empty:
                    continue
                price = float(data["close"].iloc[-1])
                day_high = float(data["high"].max())
                day_low = float(data["low"].min())
                await _execute_exit(symbol, trade, price, "OVERNIGHT time exit (10:30)", mode="OVERNIGHT")
                record_overnight_outcome(symbol, price, "TIME_EXIT_1030",
                                         day_high=day_high, day_low=day_low)
            except Exception as e:
                append_log(AUDIT_LOG_FILE, f"OVERNIGHT EXIT ERROR {symbol}: {type(e).__name__}: {e}")
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"OVERNIGHT EXIT JOB ERROR: {type(e).__name__}: {e}")


def _mtf_warehouse_topup_job():
    """Daily 15:45 Mon-Fri: naye candles warehouse me append (idempotent).
    Sync job — author pattern (apscheduler sync job thread me chalti hai).
    Kuch bhi fail ho → sirf log, bot ka koi aur job affect NAHI hota."""
    try:
        from mtf.bulk_download import run_daily_topup
        run_daily_topup()
    except Exception as e:
        logger.warning(f"_mtf_warehouse_topup_job skipped: {type(e).__name__}: {e}")

