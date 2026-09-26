"""Account/linking/subscription Telegram command handlers (split out of bot.py, AI-DOS ARCH-003 god-module remediation, 2026-09-17)."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import PARAMS
from bot_helpers import admin_only, _risk_first_onboarding

logger = logging.getLogger(__name__)


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    v5.0 AUTO-PAYMENT: fixed ₹3105 payment link (UPI + cards, amount locked).
    Payment success → bot khud plan activate karega (expiry date ke saath msg).
    Payment configured nahi → admin se contact karne ko bolega (fallback).
    """
    chat_id = update.effective_chat.id
    from config import PARAMS
    from payment import create_payment_link, is_payment_configured
    if not is_payment_configured():
        await update.message.reply_text(
            "💳 Payment system abhi activate nahi hai.\n"
            "Renewal/upgrade ke liye admin se contact karo."
        )
        return
    link = create_payment_link(chat_id)
    if not link:
        await update.message.reply_text(
            "⚠️ Payment link bana nahi — thodi der baad try karo ya admin se contact karo."
        )
        return
    amount = int(PARAMS.get("razorpay_amount_inr", 3105))
    url = link.get("short_url") or link.get("long_url")
    await update.message.reply_text(
        f"💳 Pay ₹{amount} to activate your live subscription (28 days).\n\n"
        f"{url}\n\n"
        "✅ Payment ke turant baad plan auto-activate ho jayega "
        "(expiry date ke saath confirmation milega).\n"
        "♻️ Jaldi renew karne par counting purane expiry ke baad se start hogi — koi din waste nahi."
    )


async def cmd_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "To link your Dhan account:\n"
        "/linkdhan CLIENT_ID ACCESS_TOKEN\n\n"
        "Your credentials will be validated and encrypted."
        + _risk_first_onboarding()  # PHASE-2 PATCH P3 (ADD-ONLY): fail → "" (message same as before)
    )


async def cmd_linkdhan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """FIX-44/F013: Validate, encrypt, link, and always clean credential message."""
    credentials_supplied = False
    try:
        client_id    = context.args[0]
        access_token = context.args[1]
        credentials_supplied = True
    except IndexError:
        await update.message.reply_text("Usage: /linkdhan CLIENT_ID TOKEN")
        return

    try:
        await update.message.reply_text("Validating Dhan credentials...")
        from subscriber_manager import link_dhan
        result = link_dhan(update.effective_chat.id, client_id, access_token)
        await update.message.reply_text(result["message"])
    except Exception as e:
        logger.error(f"cmd_linkdhan: Unexpected error for chat_id={update.effective_chat.id}: {type(e).__name__}: {e}", exc_info=True)
        await update.message.reply_text("Dhan linking failed safely. No credentials were saved. Contact admin if this repeats.")
    finally:
        if credentials_supplied:
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"cmd_linkdhan: Could not delete message for chat_id={update.effective_chat.id}: {type(e).__name__}: {e}")


async def cmd_unlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """F014: Normal unlink with fail-closed subscriber-position safety checks."""
    try:
        from subscriber_manager import unlink_dhan
        result = unlink_dhan(update.effective_chat.id)
    except Exception as e:
        logger.error(f"cmd_unlink: Unexpected error for chat_id={update.effective_chat.id}: {type(e).__name__}: {e}", exc_info=True)
        await update.message.reply_text("Unlink failed safely. No credentials were changed. Contact admin if this repeats.")
        return

    if not result.get("success") and result.get("has_positions"):
        # F015 force unlink is intentionally not changed here; this only offers
        # the existing callback for users who knowingly choose manual position
        # management.
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "Force Unlink (positions stay in Dhan)",
                callback_data=f"force_unlink_{update.effective_chat.id}"
            )
        ]])
        await update.message.reply_text(result["message"], reply_markup=keyboard)
    else:
        await update.message.reply_text(result.get("message", "Unlink request completed."))


async def callback_force_unlink(update: Update,
                                 context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    chat_id = int(query.data.split("_")[-1])
    if query.from_user.id != chat_id:
        await query.answer("Not authorized.")
        return
    from subscriber_manager import force_unlink_dhan
    force_unlink_dhan(chat_id)
    await query.edit_message_text(
        "Force unlinked.\n"
        "Your open positions remain in Dhan — manage them manually."
    )


async def callback_risk_disclaimer(update: Update,
                                    context: ContextTypes.DEFAULT_TYPE):
    """
    AI-DOS Phase C: Disclaimer Callback Handling
    - risk_decline: Cancel upgrade
    - risk_accept: Update status to LIVE_PENDING_PAYMENT, alert admin
    """
    query = update.callback_query
    await query.answer()
    
    chat_id = query.from_user.id
    from subscriber_manager import get_subscriber, is_admin
    
    if is_admin(chat_id):
        await query.edit_message_text("Admin already has live access.")
        return
    
    if query.data == "risk_decline":
        await query.edit_message_text(
            "❌ Upgrade cancelled.\n\n"
            "You may continue using Paper Trading.\n"
            "Use /golive anytime to upgrade."
        )
        return
    
    if query.data == "risk_accept":
        from subscriber_manager import request_live_upgrade
        result = request_live_upgrade(chat_id)

        from config import PARAMS
        live_sub_fee = PARAMS.get("live_sub_fee_inr", 3000)
        
        await query.edit_message_text(
            f"✅ Risk Disclaimer Accepted!\n\n"
            f"{result['message']}\n\n"
            f"Payment Instructions:\n"
            f"• Amount: Rs.{live_sub_fee:,.0f}\n"
            f"• Contact admin to complete payment\n"
            f"• After payment, use /status to verify activation"
        )
        
        # Alert admin
        from signal_broadcaster import alert_admin
        await alert_admin(
            f"Live Upgrade Request\n\n"
            f"Chat ID: {chat_id}\n"
            f"User: {query.from_user.first_name or 'Unknown'}\n"
            f"Accepted risk disclaimer\n\n"
            f"Use /approve {chat_id} to approve payment."
        )


@admin_only
async def cmd_settoken(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Update Dhan token with validation (Industry Standard)."""
    try:
        client_id = context.args[0]
        access_token = context.args[1]
    except IndexError:
        await update.message.reply_text("Usage: /settoken CLIENT_ID TOKEN")
        return

    # Validate token format
    if not client_id or not access_token or len(client_id) < 5 or len(access_token) < 10:
        await update.message.reply_text("❌ Invalid token format. Please check CLIENT_ID and ACCESS_TOKEN.")
        return

    # Validate token with Dhan API before saving
    await update.message.reply_text("🔄 Validating token with Dhan API...")
    
    from broker import update_token, is_token_valid
    
    # Save token (encrypted)
    update_token(client_id, access_token)
    
    # Verify token works
    if is_token_valid():
        await update.message.reply_text(
            "✅ Token updated and verified successfully!\n"
            "📊 Bot can now access Dhan API."
        )
    else:
        await update.message.reply_text(
            "⚠️ Token saved but validation failed.\n"
            "Please check your Dhan credentials."
        )
    
    # Delete message for security
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"cmd_settoken: Could not delete message: {type(e).__name__}: {e}")


@admin_only
async def cmd_subscribers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subs = get_all_subscribers()
    if not subs:
        await update.message.reply_text("No subscribers yet.")
        return
    lines = [f"Subscribers ({len(subs)}):"]
    for sub in subs.values():
        status = sub.get("status", "UNKNOWN")
        linked = "Linked" if sub.get("dhan_linked") else "Not linked"
        lines.append(f"{sub['chat_id']} — {sub['name']} [{status}] {linked}")
    await update.message.reply_text("\n".join(lines))


@admin_only
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /broadcast Your message")
        return
    msg = " ".join(context.args)
    from signal_broadcaster import broadcast_to_all
    await broadcast_to_all(f"Broadcast:\n{msg}")
    await update.message.reply_text("Broadcast sent.")


@admin_only
async def cmd_expiring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: View users with expiring subscriptions."""
    from subscriber_manager import get_expiring_users
    # [FIX] get_expiring_users() takes zero args — it reads the threshold
    # internally from PARAMS["expiry_reminder_days"] (config-driven, not a
    # per-call override). Passing days=3 raised TypeError every time.
    expiring = get_expiring_users()
    if not expiring:
        await update.message.reply_text("✅ No expiring subscriptions.")
        return
    lines = [f"⚠️ Expiring Soon ({len(expiring)}):\n"]
    for user in expiring:
        lines.append(f"🆔 {user['chat_id']} — {user['name']} ({user['days_remaining']} days left)")
    await update.message.reply_text("\n".join(lines))

