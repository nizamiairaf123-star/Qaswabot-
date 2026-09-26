"""
scripts/live_feed_dry_run.py — SAFE, READ-ONLY test for the real Dhan live feed.

Run this against your REAL Dhan account, during real market hours, BEFORE
trusting dhan_live_feed.py for anything trading-related.

What it does: connects, subscribes to a couple of well-known liquid symbols
(RELIANCE, TCS), and prints every tick it receives with a timestamp. Nothing
else. It does NOT touch trade_engine.py, does NOT place orders, does NOT
write to any state file used by the live bot.

What to watch for:
  1. Does it actually print ticks at all, and do the prices look sane
     (compare against your broker app)?
  2. Leave it running for a while, ideally through a natural network hiccup
     or by briefly disabling your network -- does it print a "reconnecting"
     log line and then resume printing ticks afterward, or does it go
     silent forever? (This is the exact failure mode flagged in DhanHQ-py
     GitHub issue #102 -- confirm this mitigation actually works for you.)
  3. Run it for at least one full session before concluding it's reliable.

Usage:
    cd trading-bot && python3 -m scripts.live_feed_dry_run
"""
import asyncio
import logging
from utils import now_ist, install_redacting_log_formatter, install_redacting_excepthook

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def main():
    install_redacting_log_formatter()  # 2026-09-20: owner pastes this script's terminal output into AI chats
    install_redacting_excepthook()
    from dhan_live_feed import DhanLiveFeed
    from dhanhq import MarketFeed
    from stock_selector import get_security_id

    # Two well-known, liquid symbols -- easy to sanity-check against any
    # broker app or Google Finance while this runs.
    test_symbols = ["RELIANCE", "TCS"]
    instruments = []
    for sym in test_symbols:
        sec_id = get_security_id(sym)
        if sec_id:
            instruments.append((MarketFeed.NSE, sec_id, MarketFeed.Ticker))
        else:
            print(f"WARNING: could not resolve security_id for {sym}, skipping it.")

    if not instruments:
        print("No instruments resolved -- check stock_selector.get_security_id() and your halal universe CSV.")
        return

    tick_count = 0

    def on_tick(tick: dict):
        nonlocal tick_count
        tick_count += 1
        print(f"[{now_ist().isoformat(timespec='seconds')}] tick #{tick_count}: {tick}")

    feed = DhanLiveFeed()
    feed.add_callback(on_tick)
    print(f"Connecting with {len(instruments)} instrument(s): {test_symbols}")
    print("Watching for ticks... (Ctrl+C to stop)")
    print("Try disconnecting your network briefly at some point to test reconnection.\n")
    await feed.connect(instruments)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
