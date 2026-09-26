"""Position/PnL/portfolio/reporting Telegram command handlers (split out of bot.py, AI-DOS ARCH-003 god-module remediation, 2026-09-17)."""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from config import PARAMS
from bot_helpers import admin_only, _risk_first_block

logger = logging.getLogger(__name__)


async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # [F11 FIX] This used to show the admin's master positions to every
    # caller. A subscriber now sees their own copy-trade ledger rows
    # instead; admin behavior is unchanged.
    from subscriber_manager import is_admin
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        from broker import _load_copy_ledger, _find_open_copies_for
        rows = _find_open_copies_for(_load_copy_ledger(), chat_id)
        if not rows:
            await update.message.reply_text("No open positions.")
            return
        lines = ["Your Open Positions:", ""]
        for r in rows:
            sl = r.get("sl_price")
            lines.append(
                f"{r.get('symbol')}\n"
                f"  Qty: {r.get('qty')}\n"
                f"  Entry time: {r.get('entry_time', '?')}\n"
                f"  SL (as copied): {('Rs.' + format(sl, '.2f')) if sl else '?'}\n"
                f"  Protection order: {'OK' if r.get('protection_success') else 'CHECK — contact admin'}"
            )
        await update.message.reply_text("\n".join(lines))
        return

    from capital_manager import get_active_trades
    from forever_order_manager import get_sl
    trades = get_active_trades()
    if not trades:
        await update.message.reply_text("No open positions.")
        return
    lines = ["Open Positions:", ""]
    for sym, t in trades.items():
        sl = get_sl(sym)
        lines.append(
            f"{sym}\n"
            f"  Entry: Rs.{t['entry_price']:.2f} | Qty: {t['qty']}\n"
            f"  SL (strict, candle-low): Rs.{sl:.2f} | Selected-RR lock: Rs.{t['tp1_price']:.2f}\n"
            f"  Strategy: {t.get('strategy_name','?')} v{t.get('strategy_version','?')}"
        )
    await update.message.reply_text("\n".join(lines))


async def cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # [F11 FIX] Subscribers used to see the admin's master P&L. Route
    # them to their own copy-trade summary instead; admin unchanged.
    from subscriber_manager import is_admin
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        from trade_logger import get_subscriber_copy_summary
        # PHASE-2 PATCH P3 (ADD-ONLY): risk-first block append — fail → "" (message same as before)
        await update.message.reply_text(get_subscriber_copy_summary(chat_id) + _risk_first_block())
        return
    from trade_logger import get_pnl_summary
    await update.message.reply_text(get_pnl_summary() + _risk_first_block())


async def cmd_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user their P&L result."""
    # [F11 FIX] same admin/subscriber routing as cmd_pnl above.
    from subscriber_manager import is_admin
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        from trade_logger import get_subscriber_copy_summary
        await update.message.reply_text(get_subscriber_copy_summary(chat_id))
        return
    from trade_logger import get_pnl_summary
    await update.message.reply_text(get_pnl_summary())


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from trade_logger import get_daily_report
    # PHASE-2 PATCH P3 (ADD-ONLY): risk-first block append — fail → "" (message same as before)
    await update.message.reply_text(get_daily_report() + _risk_first_block())


async def cmd_zakat_calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        portfolio_val = float(context.args[0])
        gold_price    = float(context.args[1])
        from sharia_manager import calculate_zakat
        await update.message.reply_text(calculate_zakat(portfolio_val, gold_price))
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /zakat 500000 6000")


@admin_only
async def cmd_stocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from stock_selector import get_tradeable_universe
    symbols = get_tradeable_universe()
    if not symbols:
        await update.message.reply_text(
            "Run /backtest first to see tradeable stocks."
        )
        return
    await update.message.reply_text(
        f"Tradeable Universe ({len(symbols)} stocks):\n"
        + ", ".join(symbols[:50])
    )


@admin_only
async def cmd_portfoliomap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from portfolio_health import get_portfolio_map
    await update.message.reply_text(get_portfolio_map())


@admin_only
async def cmd_portfoliohealth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from portfolio_health import get_health_summary
    await update.message.reply_text(get_health_summary())


@admin_only
async def cmd_capital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from capital_manager import (get_deployable_balance, get_open_slot_count,
                                  get_current_stage)
    from broker import get_available_balance
    from config import PARAMS
    raw        = get_available_balance()
    deployable = get_deployable_balance()
    slots_used = get_open_slot_count()
    stage      = get_current_stage()
    await update.message.reply_text(
        f"Capital Status\n"
        f"Raw Balance: Rs.{raw:,.2f}\n"
        f"Deployable: Rs.{deployable:,.2f}\n"
        f"Stage: {stage} ({int(PARAMS.get('stage_pct',10)*100)}% of allocated)\n"
        f"Slots: {slots_used}/{PARAMS['max_slots']}"
    )


@admin_only
async def cmd_statement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """v5.0: subscriber P&L statement — VIEW-ONLY text (download available nahi, safety policy)."""
    try:
        chat_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /statement CHAT_ID")
        return
    from subscriber_manager import get_subscriber_statement
    await update.message.reply_text(get_subscriber_statement(chat_id))


@admin_only
async def cmd_slippage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """v5.0: trade-book slippage audit (actual fills vs expected)."""
    symbol = context.args[0].upper() if context.args else None
    from broker import fetch_trade_book_audit
    await update.message.reply_text(fetch_trade_book_audit(symbol=symbol))


@admin_only
async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: View pending users awaiting approval."""
    from subscriber_manager import get_pending_users
    pending = get_pending_users()
    if not pending:
        await update.message.reply_text("✅ No pending users.")
        return
    lines = [f"⏳ Pending Users ({len(pending)}):\n"]
    for user in pending:
        lines.append(f"🆔 {user['chat_id']} — {user['name']} (Joined: {user['joined'][:10]})")
    lines.append("\nUse /approve CHAT_ID to activate")
    await update.message.reply_text("\n".join(lines))


@admin_only
async def cmd_drawdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from stock_mode_manager import get_all_modes
    from utils import load_json
    from config import BACKTEST_RESULTS_FILE
    bt    = load_json(BACKTEST_RESULTS_FILE, {})
    modes = get_all_modes()
    lines = ["Drawdown Status:", ""]
    for symbol, state in list(modes.items())[:20]:
        mode  = state.get("mode", "PROFIT")
        bt_dd = bt.get("stocks", {}).get(symbol, {}).get(
            "price_max_drawdown_pct", "N/A"
        )
        lines.append(f"{symbol} [{mode}] BT_DD: {bt_dd}%")
    await update.message.reply_text("\n".join(lines))


@admin_only
async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from utils import load_json
    from config import TRADES_FILE, PARAMS
    from portfolio_health import calculate_health_score, get_portfolio_mode
    from capital_manager import get_deployable_balance, get_open_slot_count

    trades_data = load_json(TRADES_FILE, {"trades": []})
    closed      = [t for t in trades_data["trades"] if t["status"] == "CLOSED"]
    total       = len(closed)
    wins        = len([t for t in closed if (t.get("pnl") or 0) > 0])
    total_pnl   = sum(t.get("pnl", 0) for t in closed)
    win_rate    = wins / total * 100 if total > 0 else 0

    from bot_state_manager import get_state
    await update.message.reply_text(
        f"Dashboard\n\n"
        f"Bot State: {get_state()}\n"
        f"Health: {calculate_health_score()}/100 ({get_portfolio_mode()})\n"
        f"Total Trades: {total}\n"
        f"Win Rate: {win_rate:.1f}%\n"
        f"Total P&L: Rs.{total_pnl:,.2f}\n"
        f"Open Slots: {get_open_slot_count()}/{PARAMS['max_slots']}\n"
        f"Deployable: Rs.{get_deployable_balance():,.2f}"
        + _risk_first_block()   # PHASE-2 PATCH P3 (ADD-ONLY): fail → "" (message same as before)
    )


@admin_only
async def cmd_mtf_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """PHASE-2 PATCH P4.2 (ADD-ONLY): Warehouse health — rows/span per symbol:TF.
    Fail → honest error line (existing bot behavior unaffected)."""
    try:
        from mtf.warehouse import warehouse_status
        status = warehouse_status()
        if not status:
            await update.message.reply_text(
                "MTF Warehouse: EMPTY\n"
                "Initial download abhi nahi hui. VPS pe chalao:\n"
                "python3 -m mtf.probe_depth   (depth check)\n"
                "python3 -m mtf.bulk_download --initial   (bulk load, 2-5 hrs)")
            return
        lines = [f"MTF Warehouse ({len(status)} entries):"]
        for key in sorted(status):
            m = status[key]
            lines.append(f"  {key}: {m.get('rows', 0):,} rows | {str(m.get('first','?'))[:10]} → {str(m.get('last','?'))[:10]}")
        await update.message.reply_text("\n".join(lines[:40]))
    except Exception as e:
        logger.error(f"cmd_mtf_status: {type(e).__name__}: {e}", exc_info=True)
        await update.message.reply_text(f"MTF status error (display only, trading unaffected): {type(e).__name__}")

