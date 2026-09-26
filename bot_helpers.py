"""Shared decorator + small display helpers used across bot.py and the
bot_commands_*.py / bot_livefeed.py command modules (split out of bot.py,
AI-DOS ARCH-003 god-module remediation, 2026-09-17). Deliberately dependency-
free w.r.t. bot.py itself, so bot.py and every command module can import
from here without a circular import.

check_command_access() is currently unreferenced anywhere in the codebase
(pre-existing dead code, carried over as-is — not introduced by this split;
flagged separately by AI-DOS as a dead-code finding, not fixed here).
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from subscriber_manager import is_admin

logger = logging.getLogger(__name__)


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_chat.id):
            await update.message.reply_text("Admin only.")
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


def check_command_access(chat_id: int, command: str) -> bool:
    """
    AI-DOS Phase E: Execution Gatekeeping
    - Check if user has access to command
    - Returns True if allowed, False if denied
    """
    from subscriber_manager import get_user_role
    role = get_user_role(chat_id)
    
    # Admin has access to everything
    if role == "ADMIN":
        return True
    
    # Universal commands (all roles)
    universal_cmds = {"/start", "/help", "/mystatus", "/status", "/golive"}
    if command in universal_cmds:
        return True
    
    # LIVE_ACTIVE commands
    live_cmds = {
        "/simulate", "/result", "/positions", "/pnl", "/report",
        "/dashboard", "/link", "/unlink", "/portfoliohealth",
        "/zakat"
    }
    if role == "LIVE_ACTIVE" and command in live_cmds:
        return True
    
    # PAPER_TRIAL commands
    paper_cmds = {"/simulate"}
    if role == "PAPER_TRIAL" and command in paper_cmds:
        return True
    
    # EXPIRED_EXIT_ONLY commands
    expired_cmds = {"/positions"}
    if role == "EXPIRED_EXIT_ONLY" and command in expired_cmds:
        return True
    
    return False


def _risk_first_block(capital: float = None) -> str:
    try:
        if capital is None:
            try:
                from capital_manager import get_deployable_balance
                capital = float(get_deployable_balance())
            except Exception:
                capital = 0.0
        if not capital or capital <= 0:
            return ""
        from risk_display import build_risk_first_block
        return "\n\n" + build_risk_first_block(capital)
    except Exception as e:
        logger.warning(f"_risk_first_block skipped (display only): {type(e).__name__}: {e}")
        return ""


def _risk_first_onboarding() -> str:
    try:
        from risk_display import build_onboarding_block
        return "\n\n" + build_onboarding_block()
    except Exception as e:
        logger.warning(f"_risk_first_onboarding skipped (display only): {type(e).__name__}: {e}")
        return ""

