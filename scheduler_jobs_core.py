"""Market-scan, position-monitor, heartbeat and health-check jobs (split out of scheduler.py, AI-DOS ARCH-003 god-module remediation, 2026-09-17)."""

import logging
from config import PARAMS

logger = logging.getLogger(__name__)


async def _market_scan_job():
    from trade_engine import run_market_scan
    await run_market_scan()


async def _position_monitor_job():
    from trade_engine import monitor_positions
    await monitor_positions()


async def _external_healthcheck_job():
    """Dead-man HTTP GET to HEALTHCHECK_URL. Empty = skip, never error.
    Fail-open: ping failure only logs; does not crash the scheduler."""
    try:
        from config import HEALTHCHECK_URL
        url = (HEALTHCHECK_URL or "").strip()
        if not url:
            return
        timeout = float(PARAMS.get("healthcheck_http_timeout_sec", 5) or 5)
        import urllib.request
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(64)
    except Exception as e:
        logger.warning(f"_external_healthcheck_job: ping failed: {type(e).__name__}: {e}")


async def _heartbeat_job():
    """FIX-47: Network partition detection via API ping."""
    try:
        # AUDIT FIX (Bug #2, fail-open): get_available_balance() used to mask
        # a genuine API failure as 0.0, and 0.0 >= 0 was recorded as a
        # SUCCESSFUL heartbeat -- meaning network-partition detection could
        # never trigger on a real outage. get_available_balance_or_none()
        # signals a fetch failure explicitly as None.
        from broker import get_available_balance_or_none
        from utils import record_heartbeat_success, record_heartbeat_failure
        balance = get_available_balance_or_none()
        if balance is None:
            record_heartbeat_failure()
        else:
            record_heartbeat_success()
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"_heartbeat_job: Balance check failed: {type(e).__name__}: {e}")
        from utils import record_heartbeat_failure
        record_heartbeat_failure()


async def _health_check_job():
    from safety_manager import check_economic_health
    check_economic_health()


async def _rapid_loss_pause_check_job():
    try:
        from bot_state_manager import check_and_clear_rapid_loss_pause
        check_and_clear_rapid_loss_pause()
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"_rapid_loss_pause_check_job: {type(e).__name__}: {e}")

