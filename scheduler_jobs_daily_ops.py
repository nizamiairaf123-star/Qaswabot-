"""Morning/token/EOD/reconciliation/backup daily-operations jobs (split out of scheduler.py, AI-DOS ARCH-003 god-module remediation, 2026-09-17)."""

from config import AUDIT_LOG_FILE
from utils import append_log, now_ist


async def _morning_init_job():
    from sebi_manager import release_due_funds
    from backtester import check_backtest_staleness
    from signal_broadcaster import alert_admin
    release_due_funds()
    staleness = check_backtest_staleness()
    if staleness["status"] != "OK":
        await alert_admin(f"Morning Alert\n{staleness['message']}")

    # v5.0 3-LAYER GTT (L3): kal ke miss/expired GTT ko pre-market me dobara
    # lagao — exit protection kabhi gap me na rahe.
    #
    # P1-002 [r38 verified fix]: this used to be fully fail-open — any
    # exception (or a per-symbol re-arm failure inside rearm_gtt_missing's
    # own result dict) was only logged, and unrelated positions could stay
    # unprotected with no admin visibility. Now: a hard failure to even
    # run the job, or any symbol that comes back not-OK from the re-arm
    # attempt, escalates via the existing RECONCILIATION_HOLD state (same
    # one P0-003 uses) — new entries + auto-exit blocked pending admin
    # review, admin alerted — instead of being silently swallowed. This
    # does NOT stop the rest of the daily-ops jobs.
    try:
        import asyncio
        def _rearm():
            from forever_order_manager import rearm_gtt_missing
            return rearm_gtt_missing()
        rearm_results = await asyncio.to_thread(_rearm)
        failed = {sym: res for sym, res in (rearm_results or {}).items() if res != "OK"}
        if failed:
            from bot_state_manager import activate_reconciliation_hold
            activate_reconciliation_hold(
                f"UNPROTECTED_POSITION: morning GTT re-arm failed for {failed} "
                f"— new entries and auto-exit blocked pending admin review"
            )
    except (ImportError, RuntimeError, AttributeError) as e:
        append_log(AUDIT_LOG_FILE, f"MORNING GTT RE-ARM FAILED: {type(e).__name__}: {e}")
        from bot_state_manager import activate_reconciliation_hold
        activate_reconciliation_hold(
            f"Morning GTT re-arm job itself failed: {type(e).__name__}: {e} — "
            f"open positions' protection status unknown, new entries and "
            f"auto-exit blocked pending admin review"
        )


async def _morning_data_job():
    """8:30 AM — Token check + Scrip master."""
    from broker import is_token_valid, check_token_expiry
    from signal_broadcaster import alert_admin
    from intraday_filter import download_scrip_master

    # Check token expiry status
    token_status = check_token_expiry()
    if not token_status["valid"]:
        await alert_admin(
            f"TOKEN EXPIRED\n"
            f"{token_status['message']}\n"
            f"Action: {token_status['action']}\n\n"
            f"Second alert at 9:00 AM if not resolved."
        )
    elif "expiring soon" in token_status["message"]:
        await alert_admin(
            f"⚠️ TOKEN EXPIRING SOON\n"
            f"{token_status['message']}\n"
            f"Action: {token_status['action']}"
        )

    success = download_scrip_master()
    if not success:
        await alert_admin(
            "SCRIP MASTER download failed! "
            "Intraday check may block all stocks."
        )


async def _token_second_alert_job():
    """FIX-45: 9:00 AM second alert if token still invalid."""
    from signal_broadcaster import alert_admin
    from bot_state_manager import get_state

    if get_state() == "TOKEN_INVALID_PAUSE":
        await alert_admin(
            "TOKEN STILL EXPIRED — 9:00 AM REMINDER\n\n"
            "Market opens in 15 minutes!\n"
            "Use: /settoken CLIENT_ID ACCESS_TOKEN\n\n"
            "Bot will pause at 9:10 AM if not resolved."
        )


async def _token_escalation_job():
    """FIX-45: 9:10 AM — market open, escalate to TOKEN_INVALID_PAUSE."""
    from broker import is_token_valid
    from bot_state_manager import activate_token_pause, get_state

    if not is_token_valid() and get_state() != "TOKEN_INVALID_PAUSE":
        activate_token_pause(
            "Token still invalid at market open (9:10 AM) — bot paused"
        )


async def _token_reminder_job():
    """FIX-45: Every 15 min reminder if token invalid."""
    from bot_state_manager import get_state
    from signal_broadcaster import alert_admin

    if get_state() == "TOKEN_INVALID_PAUSE":
        await alert_admin(
            "TOKEN INVALID — Bot paused\n"
            "Use: /settoken CLIENT_ID ACCESS_TOKEN"
        )


async def _daily_report_job():
    from trade_logger import get_daily_report
    from signal_broadcaster import broadcast_to_all, alert_admin
    await broadcast_to_all(get_daily_report())
    # FIX-LIST 2026-09-04 item 17: dynamic→static fallback visibility.
    # Admin-only line (subscribers don't need engine internals):
    # "Aaj X baar dynamic fallback hua" + top sites — so a silent
    # degradation (like the old regime NameError) is seen the SAME day.
    try:
        from fallback_monitor import get_daily_summary_line
        await alert_admin("📊 Fallback monitor — " + get_daily_summary_line())
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"FALLBACK MONITOR SUMMARY ERROR: {e}")


async def _entry_follow_eod_job():
    """v5.9 (owner D28): din ke end me (a) resting follow orders ka final
    tick — EOD pe exchange day-orders khud cancel karta hai, isliye records
    clean ho jate hain; (b) shadow log finalize → daily report +
    risk_units recommendation (approval sirf owner, auto-change nahi)."""
    import asyncio
    try:
        from entry_follow import tick_following_orders
        res = await asyncio.to_thread(tick_following_orders)
        append_log(AUDIT_LOG_FILE, f"ENTRY FOLLOW EOD TICK: {res}")
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"ENTRY FOLLOW EOD ERROR: {e}")
    try:
        from shadow_log import finalize_day
        await asyncio.to_thread(finalize_day)
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"SHADOW EOD ERROR: {e}")


async def _job_eod_summary_and_backup():
    """Create a transactionally consistent SQLite backup snapshot after EOD."""
    from database import DB_PATH
    from config import DATA_DIR

    backup_dir = os.path.join(DATA_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    if not os.path.isfile(DB_PATH):
        append_log(AUDIT_LOG_FILE, f"DB BACKUP WARNING: source database missing: {DB_PATH}")
        return

    timestamp = now_ist().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"trading_bot_{timestamp}.db.bak")

    try:
        with sqlite3.connect(DB_PATH, timeout=30) as src:
            with sqlite3.connect(backup_file, timeout=30) as dst:
                src.backup(dst)
                integrity = dst.execute("PRAGMA integrity_check").fetchone()
                if not integrity or integrity[0] != "ok":
                    raise RuntimeError(f"SQLite integrity_check failed: {integrity!r}")
        append_log(AUDIT_LOG_FILE, f"DB BACKUP COMPLETE: {backup_file}")
    except Exception as e:
        try:
            if os.path.exists(backup_file):
                os.remove(backup_file)
        except OSError:
            pass
        append_log(AUDIT_LOG_FILE, f"DB BACKUP ERROR: {type(e).__name__}: {e}")


async def _subscription_expiry_job():
    from subscriber_manager import auto_expire_subscriptions
    auto_expire_subscriptions()


async def _reconciliation_job():
    from trade_engine import run_reconciliation
    await run_reconciliation()


async def _backup_job():
    """FIX-35: Daily data backup — only JSON files, NOT scrip_master or backups folder."""
    import os, zipfile
    from utils import now_ist, append_log
    from config import AUDIT_LOG_FILE

    try:
        timestamp   = now_ist().strftime("%Y%m%d_%H%M")
        backup_dir  = "data/backups"
        os.makedirs(backup_dir, exist_ok=True)
        backup_file = f"{backup_dir}/backup_{timestamp}.zip"

        # Only backup important JSON files — NOT scrip_master, NOT backups folder itself
        important_files = [
            "data/subscribers.json",
            "data/trades.json",
            "data/portfolio_state.json",
            "data/stock_modes.json",
            "data/sebi_blocked.json",
            "data/per_stock_params.json",
            "data/optimizer_results.json",
            "data/optimizer_output.json",
            "data/backtest_results.json",
            "data/bot_state.json",
            "data/audit_log.txt",
        ]

        with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fpath in important_files:
                if os.path.exists(fpath):
                    zf.write(fpath)

        size_mb = os.path.getsize(backup_file) / 1024 / 1024
        append_log(AUDIT_LOG_FILE, f"BACKUP: Created {backup_file} ({size_mb:.1f}MB)")

        # Delete backups older than 7 days
        now_ts = now_ist().timestamp()
        for f in os.listdir(backup_dir):
            fpath = os.path.join(backup_dir, f)
            if os.path.isfile(fpath):
                age_days = (now_ts - os.path.getmtime(fpath)) / 86400
                if age_days > 7:
                    os.remove(fpath)
                    append_log(AUDIT_LOG_FILE, f"BACKUP: Deleted old {f}")
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"BACKUP ERROR: {e}")


async def _stage_check_job():
    from capital_manager import check_and_update_stage
    from subscriber_manager import get_all_subscribers
    check_and_update_stage("admin")
    for chat_id in get_all_subscribers():
        check_and_update_stage(str(chat_id))

