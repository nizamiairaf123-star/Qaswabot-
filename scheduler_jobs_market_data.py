"""Sector/FII-DII/regime/news/corporate-actions/macro data-refresh jobs (split out of scheduler.py, AI-DOS ARCH-003 god-module remediation, 2026-09-17)."""

import logging
from config import AUDIT_LOG_FILE
from utils import append_log, now_ist

logger = logging.getLogger(__name__)


async def _market_data_refresh_job():
    """
    [AUDIT FIX Gap #12]: previously a failure here (e.g. NSE blocking the
    scraper — a real, common risk) only produced a logger.warning line in a
    local log file, with no admin alert and no persistent tracking of how
    long the data had been stale. Unlike the board subsystem's
    BOARD_DATA_STALE_PAUSE (monthly retry + admin alert), sector/FII data
    could silently go stale for weeks unnoticed. Now tracks consecutive
    failures + staleness in data/market_data_health.json and alerts the
    admin on failure or once data is stale beyond a threshold.
    """
    from utils import now_ist, load_json, save_json
    from datetime import datetime
    HEALTH_FILE = "data/market_data_health.json"
    STALE_ALERT_DAYS = 2  # this job runs daily; 2 missed days is worth a human looking

    health = load_json(HEALTH_FILE, {})

    async def _handle(name: str, ok: bool):
        key_fail = f"{name}_consecutive_failures"
        key_success = f"{name}_last_success"
        if ok:
            if health.get(key_fail, 0) > 0:
                try:
                    from signal_broadcaster import alert_admin
                    await alert_admin(f"✅ {name.upper()} data refresh recovered after {health.get(key_fail)} failed attempt(s).")
                except (ImportError, RuntimeError) as e:
                    logger.warning(f"_market_data_refresh_job: recovery alert failed for {name}: {e}")
            health[key_fail] = 0
            health[key_success] = now_ist().isoformat()
            return

        health[key_fail] = health.get(key_fail, 0) + 1
        stale_days = None
        last_success = health.get(key_success)
        if last_success:
            try:
                last_dt = datetime.fromisoformat(last_success)
                stale_days = (now_ist().replace(tzinfo=last_dt.tzinfo) - last_dt).days
            except (ValueError, TypeError):
                stale_days = None
        should_alert = (health[key_fail] == 1) or (stale_days is not None and stale_days >= STALE_ALERT_DAYS) or (stale_days is None and health[key_fail] >= STALE_ALERT_DAYS)
        if should_alert:
            try:
                from signal_broadcaster import alert_admin
                await alert_admin(
                    f"⚠️ {name.upper()} data refresh failed (consecutive failures: {health[key_fail]}"
                    f"{f', stale for {stale_days} days' if stale_days is not None else ''}).\n"
                    f"This is NOT a hard trading pause, but signals derived from this data "
                    f"(sector-strength / FII-DII gates) may now be running on outdated information. "
                    f"Please check the NSE scraper / network on the VPS."
                )
            except (ImportError, RuntimeError) as e:
                logger.warning(f"_market_data_refresh_job: failure alert failed for {name}: {e}")

    try:
        from sector_strength import refresh_sector_data
        ok = refresh_sector_data()
    except (ImportError, RuntimeError, ValueError, OSError) as e:
        logger.warning(f"_market_data_refresh_job: Sector refresh failed: {type(e).__name__}: {e}")
        ok = False
    await _handle("sector", ok)

    try:
        from fii_dii_tracker import refresh_fii_dii_data
        ok = refresh_fii_dii_data()
    except (ImportError, RuntimeError, ValueError, OSError) as e:
        logger.warning(f"_market_data_refresh_job: FII/DII refresh failed: {type(e).__name__}: {e}")
        ok = False
    await _handle("fii", ok)

    save_json(HEALTH_FILE, health)


async def _regime_premarket_job():
    """09:10 AM — market regime open se pehle refresh (cache warm karo).
    Trading window ke andar cold-refresh kabhi nahi hoga — scan me sirf
    cached regime read hota hai."""
    import asyncio
    from utils import append_log
    from config import AUDIT_LOG_FILE

    def _run():
        from market_regime import refresh_market_regime
        out = refresh_market_regime(force_refresh=True)
        append_log(AUDIT_LOG_FILE,
                   f"REGIME PREMARKET: {out.get('regime')} method={out.get('method', 'multi-factor')}")

    try:
        await asyncio.to_thread(_run)
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"REGIME PREMARKET ERROR: {e}")


async def _news_prefetch_job():
    """09:11 AM — deployable universe ke news headlines pre-fetch + LM score
    cache (Loughran-McDonald 2011). Trade-time par sirf cache read hota hai."""
    import asyncio
    from utils import append_log
    from config import AUDIT_LOG_FILE

    def _run():
        from news_analyzer import prefetch_news_cache
        prefetch_news_cache()

    try:
        await asyncio.to_thread(_run)
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"NEWS PREFETCH ERROR: {e}")


async def _corporate_actions_job():
    """FIX-05: Daily corporate actions check."""
    try:
        from corporate_actions import check_corporate_actions
        check_corporate_actions()
    except Exception as e:
        from utils import append_log
        from config import AUDIT_LOG_FILE
        append_log(AUDIT_LOG_FILE, f"CORPORATE ACTIONS JOB ERROR: {e}")


async def _macro_refresh_job():
    """Monthly 1st 08:00 — India macro (CPI/GDP/RF) auto-refresh (v5.7.2).
    Fail-open: source fail → purani values intact + admin alert."""
    try:
        import asyncio
        from macro_refresh import refresh_india_macro
        await asyncio.to_thread(refresh_india_macro)
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"MACRO REFRESH JOB ERROR: {type(e).__name__}: {e}")

