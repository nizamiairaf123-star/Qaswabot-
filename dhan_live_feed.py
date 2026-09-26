"""
dhan_live_feed.py — Dhan WebSocket live market feed (real implementation).

AUDIT NOTE (important — read before trusting this in live trading):
This replaces the previous version, which was placeholder/boilerplate only
(logged a message and slept forever — never actually connected to anything).
This version uses the REAL dhanhq.MarketFeed API, confirmed against the
official DhanHQ-py documentation (github.com/dhan-oss/DhanHQ-py) as of this
writing. HOWEVER: it has NOT been tested against a real, live Dhan
connection — this sandbox has no network access and no real Dhan
credentials. A known real-world stability issue with this exact API exists
(DhanHQ-py GitHub issue #102, "no close frame received or sent") — the
reconnect-on-any-exception loop below is this module's mitigation for that,
but it has not been exercised against a real disconnect.

WIRING (FIX-LIST 2026-09-04 items 1-3): bot.py starts this feed after the
Telegram application is initialised (post_init), subscribes the watchlist of
OPEN bot positions, and forwards every normalised tick to
trade_engine.on_live_tick(), which runs the SAME exit_engine math as the
3-minute monitor and places the exit order through the same _execute_exit()
path (fill-verify, GTT cancel, subscriber copy). The 3-minute scheduler
monitor stays as the safety net; the feed only makes exits faster.

scripts/live_feed_dry_run.py remains the safe AFTER-VPS check: run it during
market hours against your real Dhan account and confirm ticks + reconnects
before trusting the live path. This sandbox cannot exercise a real socket.

SAFETY: this module is READ-ONLY market data. It cannot place, modify, or
cancel any order — no such capability exists in this file.
"""
import asyncio
import logging
import threading
import time
from typing import Callable, Awaitable, Union

from config import TOKEN_FILE, DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN
from database import db_load

logger = logging.getLogger(__name__)

RECONNECT_BASE_DELAY_SEC = 1
RECONNECT_MAX_DELAY_SEC = 30
RECONNECT_JITTER_SEC = 1  # Random jitter to avoid thundering herd
HEARTBEAT_TIMEOUT_SEC = 15  # No ticks for 15s = stale connection


class DhanLiveFeed:
    """
    Thin, defensive wrapper around dhanhq.MarketFeed.

    dhanhq's MarketFeed.run_forever() is a BLOCKING call (per official docs'
    own sample usage: `while True: data.run_forever(); response = data.get_data()`),
    so it's run in a background thread here and bridged back into this
    process's asyncio event loop via callbacks, rather than blocking the
    Telegram bot / scheduler.
    """

    def __init__(self, client_id: str = None, access_token: str = None):
        self.client_id = client_id
        self.access_token = access_token
        self._feed = None  # the real dhanhq.MarketFeed instance, created on connect()
        self.callbacks: list[Callable[[dict], Union[None, Awaitable[None]]]] = []
        self._stop_requested = False
        self._loop = None
        self.subscribed_tokens = set()  # Auto-resubscription buffer
        self._last_tick_time = 0  # Heartbeat watchdog
        self._pending_subscribe = []      # subscribe requests queued before the socket is up
        self._lock = threading.Lock()     # guards _pending_subscribe / subscribed_tokens
        self._thread_alive = False        # True while _run_blocking is running
        self.stats = {"ticks": 0, "reconnects": 0, "last_error": None}
        self._load_tokens()

    def _load_tokens(self):
        if not self.client_id or not self.access_token:
            # Prefer explicit config/env first (admin's own account), then
            # the stored token record as a fallback -- matches how the rest
            # of the codebase (broker.py) resolves credentials.
            self.client_id = self.client_id or DHAN_CLIENT_ID
            self.access_token = self.access_token or DHAN_ACCESS_TOKEN
            if not self.client_id or not self.access_token:
                token_data = db_load(TOKEN_FILE.split("/")[-1], {})
                self.client_id = self.client_id or token_data.get("client_id")
                self.access_token = self.access_token or token_data.get("access_token")

    def add_callback(self, callback: Callable[[dict], Union[None, Awaitable[None]]]):
        """Register a function (sync or async) to receive each tick dict."""
        self.callbacks.append(callback)

    @staticmethod
    def parse_tick(raw) -> dict:
        """Normalise a dhanhq MarketFeed packet into a plain dict.

        The SDK already decodes the binary frame (process_ticker/process_quote/
        process_full) but returns LTP/open/high/low/close as *strings* and
        security_id as int. Consumers (trade_engine.on_live_tick) need
        numeric fields keyed consistently regardless of packet type. Returns
        {} for non-price packets (prev-close, OI, status, disconnection) so
        callers can `if not tick: return`.
        """
        if not isinstance(raw, dict):
            return {}
        ptype = str(raw.get("type", ""))
        if ptype not in ("Ticker Data", "Quote Data", "Full Data"):
            return {}
        try:
            ltp = float(raw.get("LTP") or 0.0)
        except (TypeError, ValueError):
            return {}
        if ltp <= 0:
            return {}

        def _f(key):
            try:
                v = raw.get(key)
                return float(v) if v not in (None, "") else None
            except (TypeError, ValueError):
                return None

        return {
            "type": ptype,
            "security_id": str(raw.get("security_id", "")).strip(),
            "exchange_segment": raw.get("exchange_segment"),
            "ltp": ltp,
            "ltt": raw.get("LTT"),
            "open": _f("open"),
            "high": _f("high"),
            "low": _f("low"),
            "close": _f("close"),
            "volume": raw.get("volume"),
            "raw": raw,
        }

    def _dispatch(self, tick: dict):
        """Fan a received tick out to every registered callback. A callback
        raising an exception must never kill the feed loop or silently
        stop other callbacks from receiving the tick -- each is isolated."""
        for cb in list(self.callbacks):
            try:
                result = cb(tick)
                if asyncio.iscoroutine(result) and self._loop is not None:
                    asyncio.run_coroutine_threadsafe(result, self._loop)
            except Exception as e:
                logger.error(f"DhanLiveFeed: callback {getattr(cb, '__name__', cb)} raised: {type(e).__name__}: {e}")

    def _run_blocking(self, instruments: list, version: str = "v2"):
        """Runs in a background thread. Blocking by design (dhanhq's own API)."""
        import random
        from dhanhq import DhanContext, MarketFeed

        delay = RECONNECT_BASE_DELAY_SEC
        attempt = 0
        self._thread_alive = True
        while not self._stop_requested:
            try:
                dhan_context = DhanContext(self.client_id, self.access_token)
                # Re-create the SDK object every attempt: it binds its own
                # asyncio loop and websocket; reuse after a failure is unsafe.
                # Union of the initial list + everything subscribed since, so a
                # reconnect restores the full watchlist in one handshake.
                with self._lock:
                    full_list = list({*instruments, *self.subscribed_tokens})
                self._feed = MarketFeed(dhan_context, full_list, version)
                logger.info(f"DhanLiveFeed: connecting (attempt {attempt + 1}), {len(full_list)} instruments")

                self._last_tick_time = time.monotonic()
                self._feed.run_forever()          # opens socket + subscribes `instruments`
                delay = RECONNECT_BASE_DELAY_SEC  # reset backoff after a clean connect
                if attempt > 0:
                    self.stats["reconnects"] += 1
                attempt += 1

                # Auto-resubscribe on reconnect + drain anything queued while
                # the socket was down. Done AFTER run_forever() because the
                # SDK only sends subscription packets on an OPEN socket.
                self._flush_subscriptions()

                while not self._stop_requested:
                    raw = self._feed.get_data()
                    if raw:
                        self._last_tick_time = time.monotonic()
                        tick = self.parse_tick(raw)
                        if tick:
                            self.stats["ticks"] += 1
                            self._dispatch(tick)
                        elif isinstance(raw, dict) and raw.get("type") == "Disconnection":
                            raise ConnectionError(f"server disconnection packet: {raw}")
                    self._flush_subscriptions()

                    # Heartbeat watchdog: check for stale feed
                    if self._is_market_open():
                        elapsed = time.monotonic() - self._last_tick_time
                        if elapsed > HEARTBEAT_TIMEOUT_SEC:
                            logger.warning(f"DhanLiveFeed: no ticks for {elapsed:.0f}s -- triggering reconnect")
                            break  # Break inner loop to reconnect

            except Exception as e:
                if self._stop_requested:
                    break
                # Exponential backoff with jitter
                jitter = random.uniform(0, RECONNECT_JITTER_SEC)
                sleep_time = delay + jitter
                self.stats["last_error"] = f"{type(e).__name__}: {e}"
                logger.error(
                    f"DhanLiveFeed: connection error ({type(e).__name__}: {e}) -- "
                    f"reconnecting in {sleep_time:.1f}s"
                )
                time.sleep(sleep_time)
                delay = min(delay * 2, RECONNECT_MAX_DELAY_SEC)
            finally:
                # Never leave a half-open socket behind between attempts.
                try:
                    if self._feed is not None:
                        self._feed.close_connection()
                except Exception:
                    pass
        self._thread_alive = False
        logger.info("DhanLiveFeed: feed thread stopped")

    def _flush_subscriptions(self):
        """Send queued subscribe requests on the feed's own thread.

        dhanhq.MarketFeed owns a private asyncio loop; calling
        subscribe_symbols() from another thread (the Telegram/scheduler loop)
        is not thread-safe. So subscribe_tick() only queues, and the feed
        thread flushes here between get_data() calls.
        """
        with self._lock:
            pending, self._pending_subscribe = self._pending_subscribe, []
        if not pending or self._feed is None:
            return
        try:
            self._feed.subscribe_symbols(pending)
            logger.info(f"DhanLiveFeed: subscribed {len(pending)} instrument(s); total tracked={len(self.subscribed_tokens)}")
        except Exception as e:
            # put them back so the next flush / reconnect retries
            with self._lock:
                self._pending_subscribe = pending + self._pending_subscribe
            logger.warning(f"DhanLiveFeed: subscribe failed ({type(e).__name__}: {e}) -- will retry")
    
    def _is_market_open(self) -> bool:
        """Check if NSE market is currently open (09:15 - 15:30 IST)."""
        from datetime import datetime
        import pytz
        try:
            ist = pytz.timezone("Asia/Kolkata")
            now = datetime.now(ist)
            if now.weekday() >= 5:  # Saturday/Sunday
                return False
            market_open = now.replace(hour=9, minute=15, second=0)
            market_close = now.replace(hour=15, minute=30, second=0)
            return market_open <= now <= market_close
        except Exception:
            return False

    async def connect(self, instruments: list, version: str = "v2"):
        """
        instruments: list of (exchange_segment, security_id, subscription_type)
        tuples, e.g. [(MarketFeed.NSE, "1333", MarketFeed.Ticker)].
        Must be built by the caller (this module doesn't decide which
        symbols to watch -- that stays the trading system's decision).
        """
        if not self.client_id or not self.access_token:
            logger.error("DhanLiveFeed: cannot connect, missing Dhan credentials.")
            return
        self._loop = asyncio.get_running_loop()
        self._stop_requested = False
        await asyncio.to_thread(self._run_blocking, instruments, version)

    def subscribe_tick(self, exchange_segment, security_id, subscription_type=None) -> bool:
        """Thread-safe subscribe. Safe to call from any thread and BEFORE
        connect(): the request is queued and flushed by the feed thread once
        the socket is open (and re-sent automatically after every reconnect).
        Returns True if newly queued, False if already tracked."""
        from dhanhq import MarketFeed
        stype = subscription_type or MarketFeed.Ticker
        token_key = (exchange_segment, str(security_id), stype)
        with self._lock:
            if token_key in self.subscribed_tokens:
                return False
            self.subscribed_tokens.add(token_key)  # Track for auto-resubscription
            self._pending_subscribe.append(token_key)
        return True

    def unsubscribe_tick(self, exchange_segment, security_id, subscription_type=None) -> None:
        """Forget an instrument so it is NOT re-subscribed after a reconnect.
        (Live unsubscribe on the open socket is intentionally not attempted
        from a foreign thread; the SDK drops it on the next reconnect.)"""
        from dhanhq import MarketFeed
        stype = subscription_type or MarketFeed.Ticker
        token_key = (exchange_segment, str(security_id), stype)
        with self._lock:
            self.subscribed_tokens.discard(token_key)
            self._pending_subscribe = [t for t in self._pending_subscribe if t != token_key]

    def is_running(self) -> bool:
        return bool(self._thread_alive and not self._stop_requested)

    def stop(self):
        self._stop_requested = True
        if self._feed is not None:
            try:
                self._feed.close_connection()
            except Exception as e:
                logger.warning(f"DhanLiveFeed: error while closing connection: {e}")


async def start_live_feed(instruments: list, on_tick: Callable = None):
    """Convenience entrypoint. `on_tick` is an optional single callback for
    simple use; for multiple consumers, create a DhanLiveFeed and call
    add_callback() as many times as needed instead."""
    feed = DhanLiveFeed()
    if on_tick:
        feed.add_callback(on_tick)
    await feed.connect(instruments)


if __name__ == "__main__":
    # Not runnable standalone without real instruments/credentials --
    # see scripts/live_feed_dry_run.py for a safe way to exercise this.
    logging.basicConfig(level=logging.INFO)
    print("Use scripts/live_feed_dry_run.py to test this against a real Dhan account.")
