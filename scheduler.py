"""
scheduler.py — All automated jobs
FIX-35: Daily data backup 4:30 PM
FIX-45: Token escalation — 9:00 AM second alert, 9:10 AM pause
FIX-47: Heartbeat every 1 min during market hours
"""

import logging
import os
import sqlite3
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_MISSED
import pytz
from config import PARAMS, AUDIT_LOG_FILE
from utils import append_log, now_ist

# Job-function imports (AI-DOS ARCH-003 god-module remediation, 2026-09-17):
# job bodies now live in domain-specific modules; setup_scheduler() below is
# unchanged and still owns all cron-trigger registration in one place.
from scheduler_jobs_core import (
    _market_scan_job, _position_monitor_job, _external_healthcheck_job,
    _heartbeat_job, _health_check_job, _rapid_loss_pause_check_job,
)
from scheduler_jobs_daily_ops import (
    _morning_init_job, _morning_data_job, _token_second_alert_job,
    _token_escalation_job, _token_reminder_job, _daily_report_job,
    _entry_follow_eod_job, _job_eod_summary_and_backup, _subscription_expiry_job,
    _reconciliation_job, _backup_job, _stage_check_job,
)
from scheduler_jobs_market_data import (
    _market_data_refresh_job, _regime_premarket_job, _news_prefetch_job,
    _corporate_actions_job, _macro_refresh_job,
)
from scheduler_jobs_board_universe import (
    _load_custom_state, _save_custom_state, _sync_custom_universe_logic,
    _monthly_board_universe_update_job, _daily_board_retry_job,
    _monthly_market_metadata_refresh_job, _monthly_liquidity_refresh_job,
    _daily_liquidity_retry_job,
    _weekly_board_verification_job,
)
from scheduler_jobs_research import (
    _weekly_review_job, _auto_reoptimize_job, _overnight_prefetch_job,
    _overnight_scan_job, _overnight_exit_job, _mtf_warehouse_topup_job,
)

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

# [AUDIT F6 FIX, 2026-09-16] No job here set misfire_grace_time/max_instances
# explicitly, so every job silently used APScheduler's own tight built-in
# default (misfire_grace_time=1s) -- a transient event-loop stall (e.g. the
# F10/F12 freeze classes, now fixed, or any other brief hang) could make a
# scheduled run fire >1s late and get silently DROPPED as a "misfire" with
# no alert anywhere. Fixed via scheduler-wide job_defaults (single source of
# truth for all ~35 add_job() calls below, instead of editing each one):
# a much more forgiving grace window, explicit max_instances=1 (already the
# implicit default -- made explicit, no behavior change), and coalesce=True
# (if multiple runs were missed, catch up with one run, not a backlog burst).
scheduler = AsyncIOScheduler(
    timezone=IST,
    job_defaults={
        "misfire_grace_time": 120,
        "max_instances": 1,
        "coalesce": True,
    },
)


def _on_job_missed(event):
    """[AUDIT F6 FIX] Watchdog: a job STILL missed even past the new 120s
    grace window means something is genuinely wrong (a real stall, not a
    brief blip) -- alert loudly instead of the previous silent skip.
    logger.error() -> existing Telegram alert path (log_setup.py), which
    is itself now non-blocking per the F12 fix."""
    try:
        job_id = getattr(event, "job_id", "?")
        scheduled = getattr(event, "scheduled_run_time", "?")
        append_log(AUDIT_LOG_FILE, f"SCHEDULER JOB MISSED: id={job_id} scheduled_for={scheduled}")
        logger.error(f"SCHEDULER JOB MISSED: id={job_id} scheduled_for={scheduled} — job cycle silently skipped")
    except Exception as e:
        logger.warning(f"_on_job_missed: handler itself failed: {type(e).__name__}: {e}")


scheduler.add_listener(_on_job_missed, EVENT_JOB_MISSED)


def setup_scheduler():

    # ── Market Scan — configurable interval (default 5 min)
    market_scan_interval = PARAMS.get("market_scan_interval_min", 5)
    scheduler.add_job(
        _market_scan_job,
        CronTrigger(day_of_week="mon-fri",
                    hour="9,10,11,12,13,14,15", minute=f"*/{market_scan_interval}", timezone=IST),
        id="market_scan", name="Market Scan"
    )

    # ── Position Monitor — configurable interval (default 3 min)
    # SL protection is on broker (Dhan GTT orders), scheduler is for trail updates
    pos_monitor_interval = PARAMS.get("position_monitor_interval_min", 3)
    scheduler.add_job(
        _position_monitor_job,
        CronTrigger(day_of_week="mon-fri",
                    hour="9,10,11,12,13,14,15", minute=f"*/{pos_monitor_interval}", timezone=IST),
        id="position_monitor", name="Position Monitor"
    )

    # ── FIX-47: Heartbeat — every 1 min during market hours
    scheduler.add_job(
        _heartbeat_job,
        CronTrigger(day_of_week="mon-fri",
                    hour="9,10,11,12,13,14,15", minute="*/1", timezone=IST),
        id="heartbeat", name="Network Heartbeat"
    )

    # ── External dead-man ping (Healthchecks.io / UptimeRobot). Does NOT
    # replace _heartbeat_job (Dhan balance). Empty HEALTHCHECK_URL = skip.
    # 24/7 so overnight VPS death still alerts (market-hours-only would
    # false-alert the external monitor every night).
    try:
        hc_min = int(PARAMS.get("healthcheck_interval_min", 2) or 2)
    except (TypeError, ValueError):
        hc_min = 2
    hc_min = max(1, min(60, hc_min))
    scheduler.add_job(
        _external_healthcheck_job,
        CronTrigger(minute=f"*/{hc_min}", timezone=IST),
        id="external_healthcheck", name="External Healthcheck Ping"
    )

    # ── Morning Init — 9:10 AM Mon-Fri
    scheduler.add_job(
        _morning_init_job,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=10, timezone=IST),
        id="morning_init", name="Morning Init"
    )

    # ── Token Check — 8:30 AM daily
    scheduler.add_job(
        _morning_data_job,
        CronTrigger(hour=8, minute=30, timezone=IST),
        id="morning_data", name="Morning Data"
    )

    # ── FIX-45: Token second alert — 9:00 AM Mon-Fri
    scheduler.add_job(
        _token_second_alert_job,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=0, timezone=IST),
        id="token_second_alert", name="Token Second Alert"
    )

    # ── FIX-45: Token escalation — 9:10 AM Mon-Fri (market open)
    scheduler.add_job(
        _token_escalation_job,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=10, timezone=IST),
        id="token_escalation", name="Token Escalation"
    )

    # ── FIX-45: Token reminder every 15 min if invalid
    scheduler.add_job(
        _token_reminder_job,
        CronTrigger(day_of_week="mon-fri",
                    hour="9,10,11,12,13,14,15", minute="*/15", timezone=IST),
        id="token_reminder", name="Token Reminder"
    )

    # ── Daily Report — 3:35 PM Mon-Fri
    scheduler.add_job(
        _daily_report_job,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=35, timezone=IST),
        id="daily_report", name="Daily Report"
    )

    # ── GATE 13: EOD SQLite database backup — 3:35 PM Mon-Fri
    scheduler.add_job(
        _job_eod_summary_and_backup,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=35, timezone=IST),
        id="eod_summary_and_db_backup", name="EOD Database Backup"
    )

    # ── Entry Follow + Shadow EOD — 3:36 PM Mon-Fri (v5.9 owner D28)
    scheduler.add_job(
        _entry_follow_eod_job,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=36, timezone=IST),
        id="entry_follow_eod", name="Entry Follow EOD"
    )

    # ── Subscription Expiry — 8:00 AM daily
    scheduler.add_job(
        _subscription_expiry_job,
        CronTrigger(hour=8, minute=0, timezone=IST),
        id="sub_expiry", name="Subscription Expiry"
    )

    # ── Reconciliation — 3:40 PM Mon-Fri
    scheduler.add_job(
        _reconciliation_job,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=40, timezone=IST),
        id="reconciliation", name="Daily Reconciliation"
    )

    # ── FIX-35: Data Backup — 4:30 PM Mon-Fri + daily
    scheduler.add_job(
        _backup_job,
        CronTrigger(hour=16, minute=30, timezone=IST),
        id="backup", name="Data Backup"
    )

    # ── Economic Health Check — every 6 hours
    scheduler.add_job(
        _health_check_job,
        CronTrigger(hour="*/6", timezone=IST),
        id="health_check", name="Economic Health Check"
    )

    # ── Weekly Review — Saturday 10:00 AM
    scheduler.add_job(
        _weekly_review_job,
        CronTrigger(day_of_week="sat", hour=10, minute=0, timezone=IST),
        id="weekly_review", name="Weekly Review"
    )

    # ── v5.0: Auto Re-Optimize PROPOSAL (config-gated, default OFF) ──
    # Saturday 09:00 — sirf naya deployment PROPOSAL banata hai; approval
    # hamesha admin ke haath me rehta hai (/deployapprove).
    scheduler.add_job(
        _auto_reoptimize_job,
        CronTrigger(day_of_week="sat", hour=9, minute=0, timezone=IST),
        id="auto_reoptimize", name="Auto Re-Optimize Proposal (v5.0)"
    )

    # ── v5.7.2: India Macro Auto-Refresh (owner: EXTERNAL_FACT numbers
    # khud update hone chahiye — monthly, liquidity/board se pehle) ──
    scheduler.add_job(
        _macro_refresh_job,
        CronTrigger(day=1, hour=8, minute=0, timezone=IST),
        id="macro_refresh", name="India Macro Monthly Refresh (v5.7.2)"
    )

    # ── v5.2: OVERNIGHT MOVERS (research module — config-gated, default OFF) ──
    # 14:00 heavy pre-fetch | 15:00 local scan + entry | next-day 10:30 exit
    # enabled=False pe har job silent no-op (strategy system untouched).
    scheduler.add_job(
        _overnight_prefetch_job,
        CronTrigger(day_of_week="mon-fri", hour=14, minute=0, timezone=IST),
        id="overnight_prefetch", name="Overnight Pre-Fetch (v5.2)"
    )
    scheduler.add_job(
        _overnight_scan_job,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=0, timezone=IST),
        id="overnight_scan", name="Overnight Scan (v5.2)"
    )
    scheduler.add_job(
        _overnight_exit_job,
        CronTrigger(day_of_week="mon-fri", hour=10, minute=30, timezone=IST),
        id="overnight_exit", name="Overnight Next-Day Exit (v5.2)"
    )

    # ── Auto Stage Check — 4:00 PM Mon-Fri
    scheduler.add_job(
        _stage_check_job,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=0, timezone=IST),
        id="stage_check", name="Stage Check"
    )

    # ── Sector + FII/DII refresh — 9:05 AM Mon-Fri
    scheduler.add_job(
        _market_data_refresh_job,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=5, timezone=IST),
        id="market_data", name="Market Data Refresh"
    )

    # ── Regime pre-market refresh — 9:10 AM Mon-Fri ──
    # [TIME-AWARE] Heavy regime computation market open se PEHLE hoti hai;
    # scan me sirf cache read hota hai (trade-time cold refresh kabhi nahi).
    scheduler.add_job(
        _regime_premarket_job,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=10, timezone=IST),
        id="regime_premarket", name="Regime Pre-Market Refresh"
    )

    # ── News pre-fetch cache — 9:11 AM Mon-Fri ──
    # [TIME-AWARE] LM-lexicon news scores pre-market me pre-fetch hote hain;
    # trade-time par sirf cache read (network scrape trading window me nahi).
    scheduler.add_job(
        _news_prefetch_job,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=11, timezone=IST),
        id="news_prefetch", name="News Pre-Fetch Cache"
    )

    # ── FIX-05: Corporate Actions — 8:45 AM daily
    scheduler.add_job(
        _corporate_actions_job,
        CronTrigger(hour=8, minute=45, timezone=IST),
        id="corporate_actions", name="Corporate Actions"
    )

    # ── Rapid Loss Pause auto-expiry check — every 5 min during market hours
    # (previously nothing ever reverted RAPID_LOSS_PAUSE once the 3-SL
    # velocity brake was wired up -- see safety_manager.record_sl_hit())
    scheduler.add_job(
        _rapid_loss_pause_check_job,
        CronTrigger(day_of_week="mon-fri",
                    hour="9,10,11,12,13,14,15", minute="*/5", timezone=IST),
        id="rapid_loss_pause_check", name="Rapid Loss Pause Auto-Expiry"
    )

    # ── PHASE-2 PATCH P4.1 (ADD-ONLY): MTF warehouse daily top-up — Mon-Fri 15:45
    # [Method: incremental data top-up + dedupe — custom engineering;
    #  data hygiene discipline — Robert Pardo, 2008]
    # No-op jab tak warehouse empty ho (initial download na hui ho) → bot pe ZERO impact.
    scheduler.add_job(
        _mtf_warehouse_topup_job,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=45, timezone=IST),
        id="mtf_warehouse_topup", name="MTF Warehouse Daily Top-up"
    )

    # ── v3.2 Custom Board & Universe Monthly Auto-Update + Fail-Closed Retry Engine [DESIGN: AIRAF NIZAMI] ──
    # Runs 1st day every month at 08:30 AM IST per spec + daily retry at 08:30 if stale paused
    try:
        board_day = PARAMS.get("board_update_cron_day", 1)
        board_hour = PARAMS.get("board_update_cron_hour", 8)
        board_minute = PARAMS.get("board_update_cron_minute", 30)
    except Exception:
        board_day, board_hour, board_minute = 1, 8, 30

    scheduler.add_job(
        _monthly_board_universe_update_job,
        CronTrigger(day=board_day, hour=board_hour, minute=board_minute, timezone=IST),
        id="monthly_board_universe_update", name="Monthly Board & Universe Update (v3.2)"
    )

    # Daily retry at same time if BOARD_DATA_STALE_PAUSE active
    scheduler.add_job(
        _daily_board_retry_job,
        CronTrigger(hour=board_hour, minute=board_minute, timezone=IST),
        id="daily_board_retry", name="Daily Board Retry (Fail-Closed Recovery)"
    )

    # [AUDIT ADD] Monthly turnover-liquidity refresh (MSCI ATVR + Frequency
    # of Trading) — runs 30 min BEFORE the board/universe sync job, since
    # that sync job's eligibility filter (_row_is_halal_eligible) depends on
    # turnover_liquid_ok already being fresh — otherwise the sync's own
    # safety guard (see _sync_custom_universe_logic) will correctly refuse
    # to write, but running liquidity first avoids relying on that fallback
    # in the common case.
    scheduler.add_job(
        _monthly_market_metadata_refresh_job,
        CronTrigger(day=board_day, hour=board_hour, minute=(board_minute - 60) % 60, timezone=IST),
        id="monthly_market_metadata_refresh", name="Monthly Market Metadata Refresh"
    )
    scheduler.add_job(
        _monthly_liquidity_refresh_job,
        CronTrigger(day=board_day, hour=board_hour, minute=(board_minute - 30) % 60, timezone=IST),
        id="monthly_liquidity_refresh", name="Monthly Turnover-Liquidity Refresh (MSCI ATVR/FoT)"
    )
    scheduler.add_job(
        _daily_liquidity_retry_job,
        CronTrigger(hour=board_hour, minute=(board_minute - 30) % 60, timezone=IST),
        id="daily_liquidity_retry", name="Daily Liquidity Retry (Fail-Closed Recovery)"
    )

    # ── R39 CORRECTED: Weekly Board Verification — 09:00-15:30 operating window ──
    # Requirement: weekly verification 09:00–15:30, missing/stale/fetch/parse failure → BLOCK
    # Do not silently convert weekly verification into monthly-only refresh.
    try:
        weekly_enabled = PARAMS.get("board_weekly_verification_enabled", True)
        weekly_day = PARAMS.get("board_weekly_verification_day", "mon")
        weekly_hour = PARAMS.get("board_weekly_verification_hour", 9)
        weekly_minute = PARAMS.get("board_weekly_verification_minute", 30)
    except Exception:
        weekly_enabled = True
        weekly_day = "mon"
        weekly_hour = 9
        weekly_minute = 30

    if weekly_enabled:
        scheduler.add_job(
            _weekly_board_verification_job,
            CronTrigger(day_of_week=weekly_day, hour=weekly_hour, minute=weekly_minute, timezone=IST),
            id="weekly_board_verification", name="Weekly Board Verification (R39 09:00-15:30 Window)"
        )
        # Also add daily check during market hours if weekly verification is stale — ensures BLOCK within 24h
        scheduler.add_job(
            _weekly_board_verification_job,
            CronTrigger(day_of_week="mon-fri", hour="9,10,11,12,13,14,15", minute=30, timezone=IST),
            id="daily_board_staleness_check", name="Daily Board Staleness Check (Weekly Fail-Closed)"
        )

    scheduler.start()


# ─────────────────────────────────────────────
# JOB FUNCTIONS
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
# PHASE-2 PATCH P4.1 (ADD-ONLY) — MTF warehouse top-up job function
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
# v3.2 Custom Board & Universe Monthly Auto-Update & Fail-Closed Retry Engine [DESIGN: AIRAF NIZAMI]
# Implements: _monthly_board_universe_update_job() + daily retry + state file handling
# ─────────────────────────────────────────────


# ═════════════════════════════════════════════════════════════════════════
# v5.2 — OVERNIGHT MOVERS JOBS (research module; enabled=False → no-op)
# ═════════════════════════════════════════════════════════════════════════


