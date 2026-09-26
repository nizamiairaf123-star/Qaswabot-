"""Kill-switch/risk-control/board/subscriber-admin Telegram command handlers (split out of bot.py, AI-DOS ARCH-003 god-module remediation, 2026-09-17)."""

import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from config import PARAMS
from bot_helpers import admin_only
from bot_livefeed import get_live_feed_status_text


@admin_only
async def cmd_sebi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from sebi_manager import get_blocked_summary
    await update.message.reply_text(get_blocked_summary())


@admin_only
async def cmd_killswitch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from utils import set_killswitch
    from bot_state_manager import activate_killswitch
    set_killswitch(True)
    activate_killswitch()
    await update.message.reply_text("KILLSWITCH ACTIVATED — All trading stopped.")


@admin_only
async def cmd_exitonly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """FIX-48: EXIT_ONLY mode — no new entries, existing positions monitored."""
    from bot_state_manager import activate_exit_only
    activate_exit_only("Admin /exitonly command")
    await update.message.reply_text(
        "EXIT ONLY MODE\n\n"
        "No new entries will be taken.\n"
        "Existing positions monitored normally.\n"
        "Positions will exit when trail SL hits.\n\n"
        "Use /resume to return to normal."
    )


@admin_only
async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from utils import set_killswitch
    from bot_state_manager import resume_from_pause
    set_killswitch(False)
    resume_from_pause()
    await update.message.reply_text("Trading RESUMED.")


@admin_only
async def cmd_bot_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from bot_state_manager import get_status_text
    # FIX-LIST 2026-09-04 item 2/17: live-feed health + today's dynamic-fallback
    # counter are surfaced here so a silent degradation is visible on demand.
    extra = []
    try:
        extra.append(get_live_feed_status_text())
    except Exception as e:
        extra.append(f"Live feed: status unavailable ({type(e).__name__})")
    try:
        from fallback_monitor import get_daily_summary_line
        extra.append(get_daily_summary_line())
    except Exception as e:
        extra.append(f"Fallback monitor: unavailable ({type(e).__name__})")
    await update.message.reply_text(get_status_text() + "\n\n" + "\n".join(extra))


@admin_only
async def cmd_unblock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        symbol = context.args[0].upper()
        from stock_mode_manager import admin_unblock
        admin_unblock(symbol)
        await update.message.reply_text(
            f"{symbol} unblocked. Ensure new backtest done."
        )
    except IndexError:
        await update.message.reply_text("Usage: /unblock SYMBOL")


@admin_only
async def cmd_unblockall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from stock_mode_manager import get_all_modes, admin_unblock
    modes = get_all_modes()
    for symbol in modes:
        admin_unblock(symbol)
    await update.message.reply_text(f"{len(modes)} stocks unblocked.")


@admin_only
async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    AI-DOS Phase C: Payment Approval & Term Stacking (Rollover)
    v5.0 COMMAND LIFECYCLE: approve se pehle validation (payment requested +
    Dhan linked) + subscriber ko expiry DATE ke saath confirmation.
    """
    try:
        chat_id = int(context.args[0])
        from subscriber_manager import approve_subscriber, can_approve, get_subscriber
        ok, reason = can_approve(chat_id)
        if not ok:
            await update.message.reply_text(f"❌ Approve blocked: {reason}")
            return
        result = approve_subscriber(chat_id)
        if result["success"]:
            sub = get_subscriber(chat_id) or {}
            expiry = sub.get("live_expiry", "?")
            await update.message.reply_text(result["message"])
            from signal_broadcaster import notify_subscriber
            await notify_subscriber(
                chat_id,
                "🎉 Live Trading ACTIVATED!\n"
                "JazakAllah Khair!\n\n"
                f"✅ Your plan is activated till {expiry}\n"
                "📊 You will receive copies of NEW trades\n\n"
                "Use /help to see commands."
            )
        else:
            await update.message.reply_text(f"❌ {result['message']}")
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /approve CHAT_ID")


@admin_only
async def cmd_revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """v5.0: approve ka revert — subscriber access revoke (entry band, exits chalu)."""
    try:
        chat_id = int(context.args[0])
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""
        from subscriber_manager import revoke_subscriber
        result = revoke_subscriber(chat_id, reason)
        await update.message.reply_text(result["message"])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /revoke CHAT_ID [reason]")


@admin_only
async def cmd_deploy_rollback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """v5.0: deployment ka revert — last approved params wapas, workflow reset."""
    from deployment_manager import rollback_deployment
    await update.message.reply_text(rollback_deployment())


@admin_only
async def cmd_setsebi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        pct = float(context.args[0])
        if not (0 < pct <= 100):
            raise ValueError
        from config import PARAMS
        PARAMS["sebi_release_pct"] = pct
        from utils import load_json, save_json
        from config import OPTIMIZER_OUTPUT_FILE
        data = load_json(OPTIMIZER_OUTPUT_FILE, {})
        data["sebi_release_pct"] = pct
        save_json(OPTIMIZER_OUTPUT_FILE, data)
        await update.message.reply_text(f"SEBI release set to {pct}%")
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /setsebi 80")


@admin_only
async def cmd_board_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """v5.0: Stage 0 manual trigger — monthly board/universe sync abhi chalao."""
    import asyncio
    from scheduler import _monthly_board_universe_update_job
    asyncio.create_task(_monthly_board_universe_update_job())
    await update.message.reply_text(
        "🔄 Board & Universe refresh started.\n"
        "Complete hone pe result yahan ayega (success/fail-closed pause alert).")


@admin_only
async def cmd_board_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """[AUDIT F16 FIX] Surface heuristic-only board classifications for manual
    review. Does not change any accept/reject decision — informational only."""
    from board_manager import get_boards_needing_manual_review
    items = get_boards_needing_manual_review()
    if not items:
        await update.message.reply_text("No heuristic-only board classifications pending review.")
        return
    allowed = [i for i in items if i["reason"] == "heuristic_allowed"]
    excluded = [i for i in items if i["reason"] == "heuristic_excluded_ambiguous"]
    lines = ["🔍 *Board Classifications Needing Manual Review*", ""]
    if allowed:
        lines.append(f"⚠️ Heuristic-ALLOWED (no keyword hit — double-check these, false-negative risk):")
        for i in allowed[:30]:
            lines.append(f"  {i['symbol']} (checked {i.get('last_checked','?')})")
        if len(allowed) > 30:
            lines.append(f"  ...and {len(allowed) - 30} more")
        lines.append("")
    if excluded:
        lines.append("🚫 Heuristic-EXCLUDED (ambiguous name, unconfirmed — correctly blocked today):")
        for i in excluded[:30]:
            lines.append(f"  {i['symbol']}: {', '.join(i.get('ambiguous_names', []))}")
        if len(excluded) > 30:
            lines.append(f"  ...and {len(excluded) - 30} more")
    await update.message.reply_text("\n".join(lines))


@admin_only
async def cmd_corp_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from corporate_actions import get_last_check_summary
    await update.message.reply_text(get_last_check_summary())

