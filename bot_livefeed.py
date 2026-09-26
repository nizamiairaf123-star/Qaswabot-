"""Paper/live-mode Telegram commands + the Dhan WebSocket live-feed background task (split out of bot.py, AI-DOS ARCH-003 god-module remediation, 2026-09-17). get_live_feed_status_text is imported by bot_commands_admin.py's cmd_bot_status."""

import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from config import PARAMS
from bot_helpers import admin_only

logger = logging.getLogger(__name__)


@admin_only
async def cmd_paper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to paper mode — no real orders."""
    from bot_state_manager import activate_paper
    activate_paper()
    await update.message.reply_text(
        "📝 PAPER MODE ACTIVATED\n\n"
        "No real orders will be placed.\n"
        "All trades simulated.\n\n"
        "Use /live to switch to live trading."
    )


@admin_only
async def cmd_live(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to live staged mode — real orders with staged capital."""
    from bot_state_manager import activate_live_staged
    activate_live_staged()
    from capital_manager import get_current_stage
    stage = get_current_stage()
    await update.message.reply_text(
        "🔴 LIVE STAGED MODE ACTIVATED\n\n"
        f"Stage: {stage} (10% capital)\n"
        "Real orders will be placed.\n"
        "Subscribers will receive copy trades.\n\n"
        "Use /paper to switch back to paper mode.\n"
        "Use /livefull for full capital deployment."
    )


@admin_only
async def cmd_livefull(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to live full mode — real orders with full capital."""
    from bot_state_manager import activate_live_full
    result = activate_live_full()
    if result.get("success"):
        await update.message.reply_text(
            "🔴 LIVE FULL MODE ACTIVATED\n\n"
            "Full capital deployment.\n"
            "Real orders will be placed.\n"
            "Subscribers will receive copy trades.\n\n"
            "Use /paper to switch back to paper mode."
        )
    else:
        await update.message.reply_text(
            f"❌ Cannot activate live full mode:\n{result.get('reason', 'Unknown error')}"
        )


@admin_only
async def cmd_ruflo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """RuFlo portfolio ranking."""
    try:
        from ruflo_ranker import get_ruflo_summary
        await update.message.reply_text(get_ruflo_summary())
    except (ImportError, RuntimeError, ValueError) as e:
        logger.error(f"cmd_ruflo: {type(e).__name__}: {e}", exc_info=True)
        await update.message.reply_text(f"RuFlo error: {e}")


def _live_feed_instruments_from_watchlist() -> list:
    """Open bot positions → [(MarketFeed.NSE, security_id, MarketFeed.Ticker)]."""
    from dhanhq import MarketFeed
    from trade_engine import get_live_watchlist
    return [(MarketFeed.NSE, str(sid), MarketFeed.Ticker) for sid in get_live_watchlist()]


def _start_live_feed_task() -> None:
    """Create the feed, register trade_engine.on_live_tick, start it as a
    background task on the running loop, and register a lightweight
    scheduler job that keeps the subscription list in sync with open
    positions (new entry → subscribe; exit → forget for next reconnect)."""
    global _LIVE_FEED, _LIVE_FEED_TASK
    from dhan_live_feed import DhanLiveFeed
    from trade_engine import on_live_tick

    feed = DhanLiveFeed()
    if not feed.client_id or not feed.access_token:
        logger.warning("Live feed: Dhan credentials missing — running on 3-min monitor only. Use /settoken, then /restart or wait for the sync job.")
        _LIVE_FEED = feed          # keep the object so the sync job can start it later
        _LIVE_FEED_TASK = None
    else:
        feed.add_callback(on_live_tick)
        instruments = _live_feed_instruments_from_watchlist()
        _LIVE_FEED = feed
        _LIVE_FEED_TASK = asyncio.get_running_loop().create_task(feed.connect(instruments))
        logger.info(f"Live feed started with {len(instruments)} instrument(s) → trade_engine.on_live_tick")

    # keep watchlist in sync (also (re)starts the feed once a token arrives)
    try:
        from scheduler import scheduler as _sched
        if _sched.get_job(_LIVE_FEED_SYNC_JOB_ID) is None:
            _sched.add_job(_live_feed_sync_job, "interval",
                           seconds=int(PARAMS.get("live_feed_sync_interval_sec", 60) or 60),
                           id=_LIVE_FEED_SYNC_JOB_ID, name="Live Feed Watchlist Sync")
    except Exception as e:
        logger.warning(f"Live feed sync job not registered: {type(e).__name__}: {e}")


async def _live_feed_sync_job() -> None:
    """Every N seconds: subscribe security_ids of newly opened positions and
    forget closed ones; if the feed never started (no token at boot) and a
    token is now available, start it."""
    global _LIVE_FEED, _LIVE_FEED_TASK
    try:
        from dhanhq import MarketFeed
        from trade_engine import get_live_watchlist, on_live_tick
        feed = _LIVE_FEED
        if feed is None:
            return
        if _LIVE_FEED_TASK is None or _LIVE_FEED_TASK.done():
            feed._load_tokens()
            if not feed.client_id or not feed.access_token:
                return
            if not feed.callbacks:
                feed.add_callback(on_live_tick)
            feed._stop_requested = False
            _LIVE_FEED_TASK = asyncio.get_running_loop().create_task(
                feed.connect(_live_feed_instruments_from_watchlist()))
            logger.info("Live feed (re)started by watchlist sync job")
            return
        wanted = {str(s) for s in get_live_watchlist()}
        have = {sid for (_ex, sid, _t) in feed.subscribed_tokens}
        for sid in wanted - have:
            feed.subscribe_tick(MarketFeed.NSE, sid, MarketFeed.Ticker)
        for sid in have - wanted:
            feed.unsubscribe_tick(MarketFeed.NSE, sid, MarketFeed.Ticker)
    except Exception as e:
        logger.warning(f"Live feed sync job error: {type(e).__name__}: {e}")


def _stop_live_feed() -> None:
    global _LIVE_FEED_TASK
    if _LIVE_FEED is not None:
        _LIVE_FEED.stop()
    if _LIVE_FEED_TASK is not None:
        _LIVE_FEED_TASK.cancel()
        _LIVE_FEED_TASK = None


def get_live_feed_status_text() -> str:
    """One-line status for /botstatus."""
    feed = _LIVE_FEED
    if feed is None:
        return "Live feed: not started"
    if not feed.is_running():
        return f"Live feed: STOPPED (last_error={feed.stats.get('last_error')})"
    return (f"Live feed: RUNNING | subscribed={len(feed.subscribed_tokens)} | "
            f"ticks={feed.stats.get('ticks')} | reconnects={feed.stats.get('reconnects')}")

