"""Backtest/optimizer/validator/deployment-approval Telegram command handlers (split out of bot.py, AI-DOS ARCH-003 god-module remediation, 2026-09-17)."""

import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from config import TELEGRAM_BOT_TOKEN
from bot_helpers import admin_only

logger = logging.getLogger(__name__)


@admin_only
async def cmd_backtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Run backtest. Requires Dhan token."""
    from broker import check_admin_token
    if not check_admin_token():
        await update.message.reply_text(
            "⚠️ Dhan token not set!\n\n"
            "Use /settoken CLIENT_ID ACCESS_TOKEN first."
        )
        return
    try:
        # Admin only via CommandHandler admin_only wrapper.
        # /backtest          = full universe backtest
        # /backtest RELIANCE = single stock detailed backtest
        if context.args:
            symbol = context.args[0].upper().strip()
            await update.message.reply_text(f"Running backtest for {symbol}...")
            from backtester import backtest_single, format_single_backtest_message
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: backtest_single(symbol)
            )
            await update.message.reply_text(format_single_backtest_message(result))
        else:
            await update.message.reply_text("Running full universe backtest... (10-15 min)")
            from backtester import run_full_backtest, format_full_backtest_message
            result = await asyncio.get_event_loop().run_in_executor(
                None, run_full_backtest
            )
            await update.message.reply_text(format_full_backtest_message(result))

    except (ValueError, RuntimeError, ImportError) as e:
        logger.error(f"cmd_backtest: {type(e).__name__}: {e}", exc_info=True)
        await update.message.reply_text(f"Backtest failed: {e}")


@admin_only
async def cmd_strategy_validator(update: Update,
                                  context: ContextTypes.DEFAULT_TYPE):
    try:
        from strategy_validator import get_validation_report
        await update.message.reply_text(get_validation_report())
    except (ImportError, RuntimeError, ValueError) as e:
        logger.error(f"cmd_strategy_validator: {type(e).__name__}: {e}", exc_info=True)
        await update.message.reply_text(f"Strategy validator error: {e}")


@admin_only
async def cmd_sector_strength(update: Update,
                               context: ContextTypes.DEFAULT_TYPE):
    try:
        from sector_strength import get_sector_report
        await update.message.reply_text(get_sector_report())
    except (ImportError, RuntimeError, ValueError) as e:
        logger.error(f"cmd_sector_strength: {type(e).__name__}: {e}", exc_info=True)
        await update.message.reply_text(f"Sector strength error: {e}")


@admin_only
async def cmd_fii_dii(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        from fii_dii_tracker import get_fii_dii_report
        await update.message.reply_text(get_fii_dii_report())
    except (ImportError, RuntimeError, ValueError) as e:
        logger.error(f"cmd_fii_dii: {type(e).__name__}: {e}", exc_info=True)
        await update.message.reply_text(f"FII/DII error: {e}")


@admin_only
async def cmd_excel_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        from report_generator import generate_admin_excel_report
        filepath = generate_admin_excel_report()
        if filepath:
            with open(filepath, "rb") as doc:
                await update.message.reply_document(document=doc)
        else:
            await update.message.reply_text("No closed trades yet.")
    except (ImportError, RuntimeError, OSError, ValueError) as e:
        logger.error(f"cmd_excel_report: {type(e).__name__}: {e}", exc_info=True)
        await update.message.reply_text(f"Report error: {e}")


@admin_only
async def cmd_optimize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from broker import check_admin_token
    if not check_admin_token():
        await update.message.reply_text(
            "⚠️ Dhan token not set!\n\n"
            "Use /settoken CLIENT_ID ACCESS_TOKEN first."
        )
        return
    # v5.0 TIME-AWARE GUARD: heavy optimize market-hours me scan ko slow karega
    # (trade miss risk). Force karne ke liye: /optimize --force
    from utils import is_market_open
    if is_market_open() and "--force" not in context.args:
        await update.message.reply_text(
            "⚠️ Market hours me /optimize se scan slow ho sakta hai (trade miss risk).\n\n"
            "Market close ke baad (15:30) ya weekend pe chalao.\n"
            "Agar abhi hi karna hai: /optimize --force"
        )
        return
    chat_id = update.effective_chat.id
    n_stocks = None
    if context.args:
        try:
            n_stocks = int(context.args[0])
        except (ValueError, TypeError) as e:
            logger.warning(f"cmd_optimize: Invalid n_stocks arg '{context.args[0]}': {e}")
            n_stocks = None
    if not n_stocks:
        try:
            from stock_selector import get_tradeable_universe
            universe_size = len(get_tradeable_universe())
            universe_desc = f"all {universe_size}" if universe_size else "all tradeable"
        except (ImportError, RuntimeError):
            universe_desc = "all tradeable"
    else:
        universe_desc = str(n_stocks)
    msg_start = f"⚙️ Optimization started for {universe_desc} stocks.\n2-3 ghante lagenge.\nApp band kar sakte ho — complete hone pe message aayega."
    await update.message.reply_text(msg_start)
    import threading
    import traceback
    def run_optimize():
        try:
            from optimizer import optimize_full_universe
            from stock_selector import load_halal_symbols
            from config import AUDIT_LOG_FILE as _ALF
            from utils import append_log as _alog

            symbols = load_halal_symbols()
            if not symbols:
                msg = "❌ Optimization failed: No halal symbols found. Check data/CUSTOM_UNIVERSE_FINAL.csv"
                _send_telegram(chat_id, msg)
                return

            if n_stocks:
                symbols = symbols[:n_stocks]

            _alog(_ALF, f"OPTIMIZE THREAD: Starting for {len(symbols)} stocks")
            result = optimize_full_universe(symbols)
            _alog(_ALF, f"OPTIMIZE THREAD: Completed successfully")

            optimized = result.get('optimized', 0)
            total = result.get('total', 0)
            deployable = result.get('deployable', 0)
            overfit = result.get('overfit', 0)
            avg_wr = "N/A"
            avg_ret = "N/A"
            opt_metrics = result.get('optimization_metrics', {})
            if opt_metrics:
                avg_wr = opt_metrics.get('avg_win_rate', 'N/A')
                avg_ret = opt_metrics.get('avg_return', 'N/A')

            msg = (
                f"✅ Optimization Complete!\n\n"
                f"Optimized: {optimized}/{total}\n"
                f"Deployable (WFV valid): {deployable}\n"
                f"Overfit (blocked): {overfit}\n"
                f"Avg Win Rate: {avg_wr}%\n"
                f"Avg Return/Trade: {avg_ret}%\n\n"
                f"Use /deployapprove to deploy\n"
                f"Use /walkforward for details\n"
                f"Use /ruflo for portfolio ranking"
            )
        except Exception as e:
            tb = traceback.format_exc()
            try:
                from config import AUDIT_LOG_FILE as _ALF2
                from utils import append_log as _alog2
                _alog2(_ALF2, f"OPTIMIZE THREAD ERROR: {e}\n{tb[:500]}")
            except (ImportError, OSError) as log_err:
                logger.error(f"Failed to write audit log: {log_err}")
            msg = f"❌ Optimizer error: {e}\n\nCheck audit log for details."
        _send_telegram(chat_id, msg)

    def _send_telegram(chat_id, msg):
        """Robust notification — tries multiple ways to reach admin."""
        token = None
        # Try 1: Config token
        try:
            from config import TELEGRAM_BOT_TOKEN
            token = TELEGRAM_BOT_TOKEN
        except (ImportError, AttributeError) as e:
            logger.warning(f"_send_telegram: Config token unavailable: {e}")
        # Try 2: tokens.json
        if not token:
            try:
                import os
                from utils import load_json
                project_dir = os.path.dirname(os.path.abspath(__file__))
                t = load_json(os.path.join(project_dir, "tokens.json"), {})
                token = t.get("access_token") or t.get("bot_token")
            except (OSError, ValueError) as e:
                logger.warning(f"_send_telegram: tokens.json unavailable: {e}")
        if token:
            try:
                import httpx
                resp = httpx.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": msg},
                    timeout=30.0
                )
                if resp.status_code == 200:
                    return
            except (httpx.HTTPError, OSError) as e:
                logger.warning(f"_send_telegram: Telegram API call failed: {e}")
        # Try 3: Write to audit log as fallback
        try:
            from config import AUDIT_LOG_FILE
            from utils import append_log
            append_log(AUDIT_LOG_FILE, f"OPTIMIZE NOTIFY (telegram failed): {msg[:200]}")
        except (ImportError, OSError) as e:
            logger.error(f"_send_telegram: Audit log fallback failed: {e}")

    t = threading.Thread(target=run_optimize, daemon=False)
    t.start()


@admin_only
async def cmd_deploy_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from deployment_manager import approve_deployment
    result = await approve_deployment(update.effective_chat.id)
    await update.message.reply_text(result)


@admin_only
async def cmd_deploy_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = " ".join(context.args) if context.args else ""
    from deployment_manager import reject_deployment
    result = await reject_deployment(update.effective_chat.id, reason)
    await update.message.reply_text(result)


@admin_only
async def cmd_deployment_status(update: Update,
                                 context: ContextTypes.DEFAULT_TYPE):
    from deployment_manager import get_deployment_status
    await update.message.reply_text(get_deployment_status())


@admin_only
async def cmd_walkforward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from walk_forward_validator import get_wfv_summary
    await update.message.reply_text(get_wfv_summary())


@admin_only
async def cmd_per_stock_params(update: Update,
                                context: ContextTypes.DEFAULT_TYPE):
    from per_stock_params import get_params_summary
    await update.message.reply_text(get_params_summary())


@admin_only
async def cmd_overnight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    v5.2 OVERNIGHT MOVERS — paper-proof status. Args:
      /overnight             → report (edge proof + exit params)
      /overnight optimize    → exit params ka grid-optimize (paper data se)
    """
    from overnight_movers import get_overnight_report, optimize_overnight_exit_params
    if context.args and context.args[0].lower() == "optimize":
        res = optimize_overnight_exit_params()
        await update.message.reply_text(
            "🌙 OVERNIGHT EXIT OPTIMIZATION\n\n" + str(res) +
            "\n\n(Owner rule: exit optimizer decide karta hai — 30+ closed paper trades ke baad.)")
        return
    await update.message.reply_text(get_overnight_report())

