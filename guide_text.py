"""
guide_text.py — In-Bot Guides (v5.1)

Owner rule: guides sirf bot ke ANDAR Telegram messages me milti hain —
koi downloadable file nahi (safety purpose). Subscriber ko /guide,
admin ko /adminguide. Dono role-aware hain.
"""

from config import PARAMS


def get_subscriber_guide(status: str) -> str:
    """Subscriber ka step-by-step guide (status ke hisaab se)."""

    intro = (
        "📖 *QASWA BOT — USER GUIDE*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Ye bot *long-only (CNC delivery)* halal trading karta hai — "
        "no intraday leverage, no F&O, no interest.\n\n"
        "Isme *Sharia-core-halal* stocks + *100% non-Muslim board* + "
        "price>100 + liquid — sirf whi trade hote hain.\n\n"
    )

    how = (
        "🔄 *KAISE KAAM KARTA HAI*\n"
        "1. Bot optimize → backtest → validate karta hai\n"
        "2. Paper trading me prove karta hai\n"
        "3. Live trades admin ke Dhan account pe hote hain\n"
        "4. Subscribers ko SAME trades copy hoti hain\n\n"
        "🛡️ *RISK RULES (hamesha)*\n"
        "- SL = entry candle ka low (fixed, broker-side GTT)\n"
        "- TP = 1:1.8 RR lock, uske baad uncapped trailing\n"
        "- Daily loss limit + killswitch + 3-layer exit protection\n"
        "- Bot ki DILI positions ka exit bot KAREGA — expiry ke baad bhi\n"
        "- ⚠️ Aapki MANUAL positions hamari zimmedari NAHI\n\n"
    )

    steps = {
        "PAPER_TRIAL": (
            "🎁 *ABHI — PAPER TRIAL*\n"
            "1. /simulate 100000 — strategy ka projection dekho\n"
            "   (win rate, monthly profit, risk, subscription viability)\n"
            "2. Result se satisfied ho to aage badho\n"
            "3. /golive — risk disclaimer accept karo\n"
            "4. /subscribe — ₹{amount} pay karo (UPI/card, fixed amount)\n"
            "5. /linkdhan CLIENT_ID TOKEN — Dhan link karo\n"
            "6. Admin approve karega → LIVE_ACTIVE (expiry date milegi)\n\n"
        ).format(amount=int(PARAMS.get("razorpay_amount_inr", 3105))),
        "LIVE_ACTIVE": (
            "✅ *AAP LIVE ACTIVE HO*\n"
            "- Naye trades ki copies aapke Dhan me automatic lagengi\n"
            "- Har entry/exit pe Telegram message milega\n"
            "- /mystatus — plan + expiry\n"
            "- /positions — open positions\n"
            "- Expiry se 2 din pehle renewal reminder milega\n"
            "- /subscribe se kabhi bhi renew — *stacking*: purane expiry ke "
            "baad se hi counting (din waste nahi)\n\n"
        ),
        "EXPIRED_EXIT_ONLY": (
            "🔴 *PLAN EXPIRE HO CHUKA HAI*\n"
            "- Naye trades band hain\n"
            "- Bot ki DILI open positions ka exit bot karega\n"
            "- Sab close hone pe *Plan Fully Closed* message milega\n"
            "- /subscribe se renew karo → turant wapas active\n\n"
        ),
    }

    footer = (
        "📋 *USEFUL COMMANDS*\n"
        "/mystatus — status | /simulate AMT — projection\n"
        "/positions — open | /pnl — profit/loss\n"
        "/link — Dhan link | /unlink — unlink\n"
        "/help — pura menu | /guide — ye guide\n\n"
        "⚠️ *DISCLAIMER*\n"
        "Trading me risk hai. Past performance guarantee nahi. "
        "Bot advisory nahi deta — decision aapka.\n"
    )

    status_key = status if status in steps else "PAPER_TRIAL"
    return intro + how + steps[status_key] + footer


def get_admin_guide() -> str:
    """Admin ka complete runbook — bot ke andar hi (non-downloadable)."""

    return (
        "👑 *QASWA BOT — ADMIN RUNBOOK*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔧 *PEHLI BAAR SETUP*\n"
        "1. /settoken CLIENT_ID ACCESS_TOKEN — Dhan token\n"
        "2. /boardrefresh — board+universe sync (fail → pause + retry)\n"
        "3. /corpactions — corporate actions check\n\n"

        "⚙️ *STRATEGY CYCLE (har update pe isi order me)*\n"
        "1. /optimize — per-stock params + phase-edge proof\n"
        "   (market hours me blocked; /optimize --force bypass)\n"
        "2. /backtest — parity chain (live-identical)\n"
        "3. /walkforward — overfit check (WFE >= 0.5)\n"
        "4. /ruflo — ranking\n"
        "5. /simulate AMT — *RESULT REVIEW* (ye dekh ke decide karo)\n"
        "6. /deployapprove — sirf result se satisfied ho ke\n"
        "   (galat lage to: /deployreject ya /deployrollback)\n\n"

        "📊 *PAPER → LIVE*\n"
        "1. Paper trading 2-4 hafte — /result, /report, /botstatus dekho\n"
        "2. /capital — deployable capital (stage x health x regime)\n"
        "3. Stage auto-advance hota hai (win-rate pe) — 16:00 job\n"
        "4. Live: staged 10% → 25% → 50% → 100%\n\n"

        "👥 *SUBSCRIBER MANAGEMENT*\n"
        "/pending — upgrade requests | /approve CHAT_ID — activate\n"
        "/revoke CHAT_ID — access band | /statement CHAT_ID — view-only\n"
        "/subscribers | /expiring | /broadcast\n"
        "Payment: RAZORPAY_KEY_ID/SECRET/WEBHOOK_SECRET env me daalne ke\n"
        "baad /subscribe automatic ho jata hai (₹3105 fixed, stacking).\n\n"

        "🛡️ *EMERGENCY (revert end-to-end)*\n"
        "/killswitch — SAB band (revert: /resume)\n"
        "/exitonly — sirf entries band (revert: /resume)\n"
        "/unblock SYMBOL | /unblockall — blocked stocks\n"
        "/deployrollback — last deploy revert\n"
        "/setsebi P — SEBI release % fix\n"
        "/slippage — asli fills ka audit\n\n"

        "⏰ *DAILY TIMELINE*\n"
        "08:00 liquidity | 08:30 token+scrip | 09:05 sector+FII\n"
        "09:10 regime | 09:11 news prefetch | 09:15-15:30 scans (5-min)\n"
        "15:35 report | 15:40 reconciliation | 16:00 stage | 16:30 backup\n\n"

        "📖 *NEW AI/DEVELOPER*\n"
        "feature_sequence.json = canonical pipeline (Stage 0-11) —\n"
        "pehle wahi padho. test_sequence.py = top-to-bottom auto-test.\n"
    )
