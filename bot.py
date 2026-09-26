"""
bot.py — Telegram bot main entry point
FIX-48: /exitonly command — EXIT_ONLY state
FIX-12: Unlink guard with force option
FIX-44: Dhan validation on link
"""

import asyncio
import logging
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, ContextTypes,
                           CallbackQueryHandler, MessageHandler)
from config import TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID, BOT_NAME, PARAMS
from utils import ensure_data_dir, install_redacting_log_formatter, install_redacting_excepthook, redact_secrets
from scheduler import setup_scheduler
from subscriber_manager import (register_subscriber, approve_subscriber,
                                  get_subscriber_status_text,
                                  get_all_subscribers, is_admin)
from log_setup import setup_advanced_logging
import database

# Command-handler imports (AI-DOS ARCH-003 god-module remediation, 2026-09-17):
# command bodies now live in domain-specific modules; main()/_main_guarded()
# below are unchanged and still own all CommandHandler registration in one place.
from bot_helpers import admin_only, check_command_access, _risk_first_block, _risk_first_onboarding
from bot_commands_account import (
    cmd_subscribe, cmd_link, cmd_linkdhan, cmd_unlink,
    callback_force_unlink, callback_risk_disclaimer, cmd_settoken,
    cmd_subscribers, cmd_broadcast, cmd_expiring,
)
from bot_commands_trading import (
    cmd_positions, cmd_pnl, cmd_result, cmd_report, cmd_zakat_calc,
    cmd_stocks, cmd_portfoliomap, cmd_portfoliohealth, cmd_capital,
    cmd_statement, cmd_slippage, cmd_pending, cmd_drawdown,
    cmd_dashboard, cmd_mtf_status,
)
from bot_commands_admin import (
    cmd_sebi, cmd_killswitch, cmd_exitonly, cmd_resume, cmd_bot_status,
    cmd_unblock, cmd_unblockall, cmd_approve, cmd_revoke, cmd_deploy_rollback,
    cmd_setsebi, cmd_board_refresh, cmd_board_review, cmd_corp_actions,
)
from bot_commands_research import (
    cmd_backtest, cmd_strategy_validator, cmd_sector_strength, cmd_fii_dii,
    cmd_excel_report, cmd_optimize, cmd_deploy_approve, cmd_deploy_reject,
    cmd_deployment_status, cmd_walkforward, cmd_per_stock_params, cmd_overnight,
)
from bot_livefeed import (
    cmd_paper, cmd_live, cmd_livefull, cmd_ruflo,
    _live_feed_instruments_from_watchlist, _start_live_feed_task,
    _live_feed_sync_job, _stop_live_feed, get_live_feed_status_text,
)

setup_advanced_logging()
logger = logging.getLogger(__name__)
database.init_db()


# ─────────────────────────────────────────────
# DECORATORS
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
# SUBSCRIBER COMMANDS
# ─────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    AI-DOS Phase A: Auto-Onboarding + Auto-trigger /help
    - Register new user with PAPER_TRIAL status
    - Grant immediate access to Paper Trading and Simulation
    - Auto-trigger /help to show guided menu
    """
    chat_id = update.effective_chat.id
    name = update.effective_chat.first_name or "User"
    register_subscriber(chat_id, name)
    
    from subscriber_manager import get_subscriber_status_text
    status_text = get_subscriber_status_text(chat_id)
    
    await update.message.reply_text(
        f"{BOT_NAME}\n\n"
        f"Assalamu Alaikum, {name}!\n\n"
        f"{status_text}\n\n"
        f"📖 Pehli baar? /guide — step-by-step user guide\n"
        f"Use /golive to upgrade to real trading."
    )
    
    # AI-DOS Phase A: Auto-trigger /help to show guided menu
    await cmd_help(update, context)


async def cmd_golive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    AI-DOS Phase B: Live Upgrade Intent & Compliance
    - Send risk disclaimer
    - Attach inline keyboard with Accept/Decline buttons
    """
    chat_id = update.effective_chat.id
    from subscriber_manager import get_subscriber, is_admin
    
    if is_admin(chat_id):
        await update.message.reply_text("Admin already has live access.")
        return
    
    sub = get_subscriber(chat_id)
    if not sub:
        await update.message.reply_text("Not registered. Use /start first.")
        return
    
    if sub.get("status") == "LIVE_ACTIVE":
        await update.message.reply_text("You already have live trading access.")
        return
    
    if sub.get("status") == "LIVE_PENDING_PAYMENT":
        await update.message.reply_text("Payment pending. Contact admin to complete.")
        return
    
    # Risk Disclaimer with Inline Keyboard
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ I Accept", callback_data="risk_accept")],
        [InlineKeyboardButton("❌ Decline", callback_data="risk_decline")]
    ])
    
    await update.message.reply_text(
        "⚠️ FINANCIAL RISK DISCLAIMER ⚠️\n\n"
        "By proceeding with Live Trading, you acknowledge and accept:\n\n"
        "1. You are 100% responsible for your own capital and trading decisions.\n"
        "2. This bot does NOT provide registered financial advice.\n"
        "3. Past performance does not guarantee future results.\n"
        "4. Trading involves substantial risk of loss.\n"
        "5. Developers hold ZERO LIABILITY for any losses incurred.\n"
        "6. You trade at your own risk and discretion.\n\n"
        "Do you accept these terms?",
        reply_markup=keyboard
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    AI-DOS Phase C: Dynamic Menu Construction + Phase E: Gatekeeping
    - Role-based menu (not hardcoded)
    - Short explanations per command
    """
    chat_id = update.effective_chat.id
    from subscriber_manager import get_user_role
    role = get_user_role(chat_id)
    
    # Dynamic menu based on role
    if role == "ADMIN":
        text = (
            "👑 ADMIN COMMANDS:\n\n"
            "📊 ANALYTICS & MONITORING:\n"
            "  /dashboard — Full analytics (P&L, win rate, health)\n"
            "  /portfoliohealth — Portfolio health score (0-100)\n"
            "  /portfoliomap — Stock modes (profit/loss/blocked)\n"
            "  /capital — Capital & slot status\n"
            "  /botstatus — Bot state (paper/live/killswitch)\n\n"
            "⚙️ STRATEGY MANAGEMENT:\n"
            "  /simulate AMT — Test strategy with amount (e.g., /simulate 100000)\n"
            "  /backtest — Run full backtest (10-15 min)\n"
            "  /backtest RELIANCE — Single stock backtest\n"
            "  /optimize — Run optimizer (2-3 hrs)\n"
            "  /deployapprove — Deploy optimized params\n"
            "  /deployreject — Reject deployment\n"
            "  /deployrollback — Rollback last deploy\n"
            "  /deploystatus — Check deployment status\n"
            "  /walkforward — Overfit check (WFV)\n"
            "  /strategyvalidator — Strategy health check\n"
            "  /boardrefresh — Refresh stock universe\n\n"
            "  /boardreview — [F16] Heuristic-only board classifications pending manual review\n\n"
            "👥 SUBSCRIBER MANAGEMENT:\n"
            "  /approve CHAT_ID — Approve subscriber (paper→live)\n"
            "  /revoke CHAT_ID — Revoke subscriber access\n"
            "  /statement CHAT_ID — View subscriber P&L\n"
            "  /pending — View pending subscribers\n"
            "  /expiring — View expiring subscriptions\n"
            "  /subscribers — List all subscribers\n"
            "  /broadcast MSG — Message all subscribers\n"
            "  /slippage — Trade-book slippage audit\n\n"
            "🛡️ RISK CONTROLS:\n"
            "  /killswitch — EMERGENCY STOP (all trading)\n"
            "  /exitonly — No new entries, monitor existing\n"
            "  /resume — Resume after stop\n"
            "  /unblock SYMBOL — Unblock a stock\n"
            "  /unblockall — Unblock all stocks\n\n"
            "🔄 MODE SWITCH:\n"
            "  /paper — Switch to PAPER mode (no real orders)\n"
            "  /live — Switch to LIVE staged (10% capital)\n"
            "  /livefull — Switch to LIVE full (100% capital)\n\n"
            "📋 REPORTS:\n"
            "  /excelreport — Download Excel report\n"
            "  /corpactions — Corporate actions check\n"
            "  /ruflo — RuFlo portfolio ranking\n"
            "  /sectorstrength — Sector analysis\n"
            "  /fiidii — FII/DII data\n"
            "  /overnight — Overnight movers report\n\n"
            "🔗 ACCOUNT:\n"
            "  /settoken CLIENT_ID TOKEN — Set Dhan token\n"
            "  /setsebi PCT — Set SEBI release %\n"
            "  /drawdown — Drawdown status\n"
        )
    
    elif role == "LIVE_ACTIVE":
        text = (
            "📊 YOUR COMMANDS:\n\n"
            "👤 MY PROFILE:\n"
            "  /mystatus — Check plan & health\n"
            "  /portfoliohealth — Portfolio health score\n"
            "  /positions — View open positions\n"
            "  /pnl — P&L summary\n"
            "  /report — Daily report\n"
            "  /dashboard — Full analytics\n\n"
            "🔗 DHAN ACCOUNT:\n"
            "  /link — Link Dhan account\n"
            "  /linkdhan CLIENT_ID TOKEN — Link with credentials\n"
            "  /unlink — Unlink Dhan account\n\n"
            "📋 REPORTS:\n"
            "  /zakat PORTFOLIO GOLD — Zakat calculator\n\n"
            "🚀 SUBSCRIPTION:\n"
            "  /subscribe — Pay & renew (28 days)\n"
            "  /guide — Step-by-step guide\n"
        )
    
    elif role == "PAPER_TRIAL":
        text = (
            "📝 PAPER TRADING MODE:\n\n"
            "👤 MY PROFILE:\n"
            "  /mystatus — Check plan & health\n\n"
            "🕹️ SIMULATION:\n"
            "  /simulate AMT — Test strategy (e.g., /simulate 100000)\n\n"
            "🚀 UPGRADE:\n"
            "  /golive — Upgrade to live trading\n"
            "  /subscribe — Pay & activate (28 days)\n\n"
            "📖 GUIDE:\n"
            "  /guide — Step-by-step guide\n"
        )
    
    elif role == "EXPIRED_EXIT_ONLY":
        text = (
            "❌ SUBSCRIPTION EXPIRED:\n\n"
            "👤 MY PROFILE:\n"
            "  /mystatus — Check status\n\n"
            "📊 MONITOR:\n"
            "  /positions — View exiting trades\n\n"
            "🚀 RENEW:\n"
            "  /golive — Renew subscription\n"
            "  /subscribe — Pay & renew (stacking)\n\n"
            "📖 GUIDE:\n"
            "  /guide — Guide + renewal steps\n"
        )
    
    else:  # NOT_REGISTERED or UNKNOWN
        text = (
            "❌ Not registered.\n\n"
            "Use /start to register and get 30-day free trial!"
        )
    
    await update.message.reply_text(text)


# ─────────────────────────────────────────────
# PHASE-2 PATCH P3 (ADD-ONLY): Risk-First display inject
# [Methods: Slogans — owner-designed (custom) | Half-Kelly — J.L. Kelly, 1956 |
#  Position sizing — Ralph Vince, 1992 / E. Thorp | Monte Carlo — Metropolis &
#  Ulam, 1946 | Loss-aversion — Kahneman & Tversky, 1979]
# SAFETY RULE: kuch bhi fail ho → "" return → original message EXACTLY waisa
# hi jaise pehle tha. Existing handlers ki behavior kabhi break nahi hogi.
# ─────────────────────────────────────────────


async def cmd_simulate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        capital = float(context.args[0].replace(",", ""))
        if capital <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /simulate 100000")
        return
    admin  = is_admin(update.effective_chat.id)
    from simulate_engine import run_simulation, format_simulation_message
    result = run_simulation(capital, is_admin=admin)
    # PHASE-2 PATCH P3 (ADD-ONLY): risk-first block append — fail → "" (message same as before)
    await update.message.reply_text(format_simulation_message(result, is_admin=admin) + _risk_first_block(capital))


async def cmd_mystatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        get_subscriber_status_text(update.effective_chat.id)
    )


async def cmd_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    v5.1 IN-BOT USER GUIDE — Telegram message hi (downloadable file nahi,
    owner safety policy). Status ke hisaab se role-aware guide.
    """
    from subscriber_manager import get_user_role, get_subscriber
    role = get_user_role(update.effective_chat.id)
    sub = get_subscriber(update.effective_chat.id) or {}
    status = sub.get("status", "PAPER_TRIAL")
    from guide_text import get_subscriber_guide
    guide = get_subscriber_guide(status if status in ("PAPER_TRIAL", "LIVE_ACTIVE", "EXPIRED_EXIT_ONLY") else "PAPER_TRIAL")
    from telegram.constants import ParseMode
    await update.message.reply_text(guide, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_admin_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    v5.1 IN-BOT ADMIN RUNBOOK — Telegram message hi (non-downloadable).
    Setup → strategy cycle → paper/live → subscribers → emergency → timeline.
    """
    from guide_text import get_admin_guide
    from telegram.constants import ParseMode
    await update.message.reply_text(get_admin_guide(), parse_mode=ParseMode.MARKDOWN)


# ─────────────────────────────────────────────
# ADMIN COMMANDS
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
# LIVE FEED (FIX-LIST 2026-09-04 items 1-3) — start / watchlist / stop
# ─────────────────────────────────────────────
_LIVE_FEED = None          # DhanLiveFeed instance (None when not started)
_LIVE_FEED_TASK = None     # asyncio.Task running feed.connect()
_LIVE_FEED_SYNC_JOB_ID = "live_feed_watchlist_sync"


def main():
    # 2026-09-20: install this FIRST, before anything else can log a line —
    # owner (non-technical) pastes journalctl/terminal output directly into
    # AI chats, so every logger.*/append_log() call across the whole process
    # must be secret-redacted from process start, not just this module's own.
    install_redacting_log_formatter()
    install_redacting_excepthook()  # uncaught crashes also redacted, not just logged errors
    ensure_data_dir()

    # v5.0 DOUBLE-RUN GUARD: doosra instance start ho → turant exit
    # (double trading ka sabse khatarnak ops bug block).
    from single_instance import acquire_instance_lock, release_instance_lock
    ok_lock, lock_reason = acquire_instance_lock()
    if not ok_lock:
        print(f"[FATAL] {lock_reason}")
        sys.exit(1)
    try:
        _main_guarded()
    finally:
        release_instance_lock()


def _main_guarded():
    # v5.0 CONFIG SANITY: galat config se bot silently galat na chale.
    from config import validate_config
    problems = validate_config()
    if problems:
        from utils import append_log
        from config import AUDIT_LOG_FILE
        for p in problems:
            append_log(AUDIT_LOG_FILE, f"CONFIG SANITY: {p}")
        print(f"[CONFIG SANITY] {len(problems)} problem(s) found — see audit log")

    # v5.7.2: India macro override apply (fresh ho to) — boot pe lagta hai
    try:
        from macro_refresh import apply_macro_override
        apply_macro_override()
    except Exception as e:
        print(redact_secrets(f"[MACRO] override apply skipped: {type(e).__name__}: {e}"))

    # v5.0 PAYMENT WEBHOOK (config-gated; bina env ke silent no-op)
    try:
        from payment import start_webhook_server
        start_webhook_server()
    except Exception as e:
        print(redact_secrets(f"[PAYMENT] webhook start skipped: {type(e).__name__}: {e}"))

    # Startup: timezone verify + recovery
    from utils import verify_timezone
    verify_timezone()

    from safety_manager import run_reconciliation
    run_reconciliation()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    async def startup_monitor(app):
        # ── (1) SCHEDULER — FIX-LIST 2026-09-04 item 6 ──────────────────────
        # AsyncIOScheduler.start() (APScheduler 3.11, pinned in
        # requirements-lock.txt) calls asyncio.get_running_loop() and raises
        # "RuntimeError: no running event loop" when invoked outside a loop.
        # The previous code called setup_scheduler() from _main_guarded()
        # BEFORE app.run_polling() — i.e. outside any loop — so on the VPS the
        # bot would have aborted at boot with the locked dependency versions.
        # post_init runs INSIDE python-telegram-bot's event loop, so the
        # scheduler binds to the same loop the handlers use. No fallback /
        # alternate timer: if the scheduler cannot start, boot must fail loud.
        setup_scheduler()
        logger.info("Scheduler started inside the bot event loop (post_init).")

        # ── (2) CRASH-WINDOW RECOVERY (unchanged) ───────────────────────────
        from startup_recovery import run_startup_recovery
        await run_startup_recovery()

        # ── (3) LIVE FEED — FIX-LIST 2026-09-04 item 2 ──────────────────────
        # Starts the Dhan WebSocket feed as a background task, subscribes the
        # current watchlist (open bot positions), and forwards every tick to
        # trade_engine.on_live_tick(). The 3-min monitor remains the safety
        # net; the feed only makes exits faster. Fail-open: if credentials
        # are missing or the SDK cannot connect, the bot still runs on the
        # scheduler path exactly as before (logged + admin-visible via
        # /botstatus). Real socket behaviour is an AFTER-VPS check
        # (scripts/live_feed_dry_run.py).
        try:
            _start_live_feed_task()
        except Exception as e:
            logger.warning(f"Live feed not started: {type(e).__name__}: {e}")

    async def shutdown_hook(app):
        try:
            _stop_live_feed()
        except Exception as e:
            logger.warning(f"Live feed stop failed: {type(e).__name__}: {e}")

    app.post_init = startup_monitor
    app.post_shutdown = shutdown_hook

    # Subscriber commands
    # [AUDIT ADD] Global error handler — previously any unhandled exception
    # inside a command handler was silently swallowed (python-telegram-bot
    # itself won't crash the bot process, but with no handler registered
    # here, neither the user NOR the admin ever found out a command failed
    # — same "logged to a file nobody watches live" pattern found elsewhere
    # in this audit, e.g. Gap #12). Now the user gets a plain-language
    # message and the admin gets an alert with the actual error, so a
    # failing command is never silently invisible.
    async def _global_error_handler(update, context):
        err = context.error
        logger.error(f"bot.py: Unhandled exception in a command handler: {type(err).__name__}: {err}", exc_info=err)
        try:
            if isinstance(update, Update) and update.effective_message:
                await update.effective_message.reply_text(
                    "⚠️ Something went wrong processing that command. The admin has been notified."
                )
        except Exception as e:
            logger.warning(f"_global_error_handler: could not reply to user: {type(e).__name__}: {e}")
        try:
            from signal_broadcaster import alert_admin
            chat_id = update.effective_chat.id if isinstance(update, Update) and update.effective_chat else "unknown"
            await alert_admin(f"⚠️ Bot command error (chat_id={chat_id}): {type(err).__name__}: {err}")
        except Exception as e:
            logger.warning(f"_global_error_handler: could not alert admin: {type(e).__name__}: {e}")

    app.add_error_handler(_global_error_handler)

    app.add_handler(CommandHandler("start",        cmd_start))
    app.add_handler(CommandHandler("golive",       cmd_golive))
    app.add_handler(CommandHandler("help",         cmd_help))
    app.add_handler(CommandHandler("simulate",     cmd_simulate))
    app.add_handler(CommandHandler("mystatus", cmd_mystatus))
    app.add_handler(CommandHandler("status", cmd_mystatus))
    app.add_handler(CommandHandler("guide", cmd_guide))
    app.add_handler(CommandHandler("adminguide", admin_only(cmd_admin_guide)))
    app.add_handler(CommandHandler("positions", admin_only(cmd_positions)))
    app.add_handler(CommandHandler("pnl", admin_only(cmd_pnl)))
    app.add_handler(CommandHandler("result", admin_only(cmd_result)))
    app.add_handler(CommandHandler("report", admin_only(cmd_report)))
    app.add_handler(CommandHandler("zakat",       cmd_zakat_calc))
    app.add_handler(CommandHandler("link",         cmd_link))
    app.add_handler(CommandHandler("linkdhan",     cmd_linkdhan))
    app.add_handler(CommandHandler("unlink",       cmd_unlink))
    app.add_handler(CommandHandler("stocks", admin_only(cmd_stocks)))

    # Admin commands
    app.add_handler(CommandHandler("settoken", admin_only(cmd_settoken)))
    app.add_handler(CommandHandler("backtest", admin_only(cmd_backtest)))
    app.add_handler(CommandHandler("optimize", admin_only(cmd_optimize)))
    app.add_handler(CommandHandler("deployapprove", admin_only(cmd_deploy_approve)))
    app.add_handler(CommandHandler("deployreject", admin_only(cmd_deploy_reject)))
    app.add_handler(CommandHandler("deployrollback", admin_only(cmd_deploy_rollback)))
    app.add_handler(CommandHandler("deploystatus", admin_only(cmd_deployment_status)))
    app.add_handler(CommandHandler("walkforward", admin_only(cmd_walkforward)))
    app.add_handler(CommandHandler("perstockparams", admin_only(cmd_per_stock_params)))
    app.add_handler(CommandHandler("portfoliomap", admin_only(cmd_portfoliomap)))
    app.add_handler(CommandHandler("portfoliohealth", admin_only(cmd_portfoliohealth)))
    app.add_handler(CommandHandler("capital", admin_only(cmd_capital)))
    app.add_handler(CommandHandler("sebi", admin_only(cmd_sebi)))
    app.add_handler(CommandHandler("killswitch", admin_only(cmd_killswitch)))
    app.add_handler(CommandHandler("exitonly", admin_only(cmd_exitonly)))
    app.add_handler(CommandHandler("resume", admin_only(cmd_resume)))
    app.add_handler(CommandHandler("botstatus", admin_only(cmd_bot_status)))
    app.add_handler(CommandHandler("unblock", admin_only(cmd_unblock)))
    app.add_handler(CommandHandler("unblockall", admin_only(cmd_unblockall)))
    app.add_handler(CommandHandler("approve", admin_only(cmd_approve)))
    app.add_handler(CommandHandler("revoke", admin_only(cmd_revoke)))
    app.add_handler(CommandHandler("pending", admin_only(cmd_pending)))
    app.add_handler(CommandHandler("expiring", admin_only(cmd_expiring)))
    app.add_handler(CommandHandler("subscribers", admin_only(cmd_subscribers)))
    app.add_handler(CommandHandler("broadcast", admin_only(cmd_broadcast)))
    # PHASE-2 PATCH P4.2 (ADD-ONLY): warehouse health command
    app.add_handler(CommandHandler("mtfstatus", admin_only(cmd_mtf_status)))
    app.add_handler(CommandHandler("setsebi", admin_only(cmd_setsebi)))
    app.add_handler(CommandHandler("drawdown", admin_only(cmd_drawdown)))
    app.add_handler(CommandHandler("dashboard", admin_only(cmd_dashboard)))
    app.add_handler(CommandHandler("strategyvalidator", admin_only(cmd_strategy_validator)))
    app.add_handler(CommandHandler("sectorstrength", admin_only(cmd_sector_strength)))
    app.add_handler(CommandHandler("fiidii", admin_only(cmd_fii_dii)))
    app.add_handler(CommandHandler("excelreport", admin_only(cmd_excel_report)))
    app.add_handler(CommandHandler("corpactions", admin_only(cmd_corp_actions)))

    app.add_handler(CommandHandler("ruflo", admin_only(cmd_ruflo)))
    app.add_handler(CommandHandler("paper", admin_only(cmd_paper)))
    app.add_handler(CommandHandler("live", admin_only(cmd_live)))
    app.add_handler(CommandHandler("livefull", admin_only(cmd_livefull)))
    app.add_handler(CommandHandler("boardrefresh", admin_only(cmd_board_refresh)))
    app.add_handler(CommandHandler("boardreview", admin_only(cmd_board_review)))
    app.add_handler(CommandHandler("statement", admin_only(cmd_statement)))
    app.add_handler(CommandHandler("slippage", admin_only(cmd_slippage)))
    app.add_handler(CommandHandler("overnight", admin_only(cmd_overnight)))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    # Callback handlers
    app.add_handler(CallbackQueryHandler(
        callback_force_unlink, pattern="^force_unlink_"
    ))
    app.add_handler(CallbackQueryHandler(
        callback_risk_disclaimer, pattern="^risk_"
    ))

    # Unknown command handler — prevent user confusion
    async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "❓ Unknown command.\n\n"
            "Use /help to see available commands."
        )
    
    app.add_handler(MessageHandler(None, unknown_command))

    # NOTE (FIX-LIST 2026-09-04 item 6): setup_scheduler() intentionally moved
    # into startup_monitor (post_init) above — it must run INSIDE the event loop.
    logger.info(f"{BOT_NAME} started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
