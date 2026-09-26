"""
report_generator.py — Excel + Summary report generator
Admin: full Excel with trades, monthly P&L, drawdown
Subscriber: Telegram text summary only
"""

import logging
import os
import pandas as pd
from datetime import datetime
from utils import load_json, now_ist

logger = logging.getLogger(__name__)
from config import TRADES_FILE


# ─────────────────────────────────────────────
# EXCEL REPORT — Admin only
# ─────────────────────────────────────────────

def generate_admin_excel_report() -> str:
    """
    Generate full Excel report for admin.
    Returns: filepath of generated Excel file
    """
    trades_data = load_json(TRADES_FILE, {"trades": []})
    closed_trades = [t for t in trades_data["trades"] if t["status"] == "CLOSED"]

    if not closed_trades:
        return None

    # ── Sheet 1: All Trades ──
    trades_df = pd.DataFrame(closed_trades)
    trades_df = trades_df[[
        "id", "symbol", "entry_price", "exit_price", "qty",
        "pnl", "pnl_pct", "entry_time", "exit_time",
        "exit_reason", "reason"
    ]].copy()
    trades_df.columns = [
        "ID", "Symbol", "Entry Price", "Exit Price", "Qty",
        "P&L (₹)", "P&L %", "Entry Time", "Exit Time",
        "Exit Reason", "Entry Reason"
    ]

    # ── Sheet 2: Monthly P&L ──
    monthly_df = _calculate_monthly_pnl(closed_trades)

    # ── Sheet 3: Weekly P&L ──
    weekly_df = _calculate_weekly_pnl(closed_trades)

    # ── Sheet 4: Summary Metrics ──
    summary_df = _calculate_summary_metrics(closed_trades)

    # ── Sheet 5: Per Stock Performance ──
    stock_df = _calculate_per_stock_performance(closed_trades)

    # ── Generate Excel ──
    os.makedirs("data/reports", exist_ok=True)
    filename = f"data/reports/halal_algo_report_{now_ist().strftime('%Y%m%d_%H%M')}.xlsx"

    with pd.ExcelWriter(filename, engine="xlsxwriter") as writer:
        workbook = writer.book

        # Formats
        header_fmt = workbook.add_format({
            "bold": True, "bg_color": "#1a472a", "font_color": "white",
            "border": 1, "align": "center"
        })
        green_fmt = workbook.add_format({"font_color": "#1a472a", "bold": True})
        red_fmt = workbook.add_format({"font_color": "#8b0000", "bold": True})
        currency_fmt = workbook.add_format({"num_format": "₹#,##0.00"})
        pct_fmt = workbook.add_format({"num_format": "0.00%"})

        # Sheet 1: Trades
        trades_df.to_excel(writer, sheet_name="All Trades", index=False)
        ws = writer.sheets["All Trades"]
        ws.set_column("A:A", 5)
        ws.set_column("B:B", 12)
        ws.set_column("C:F", 12)
        ws.set_column("G:G", 8)
        ws.set_column("H:I", 20)
        ws.set_column("J:K", 20)

        # Sheet 2: Monthly P&L
        monthly_df.to_excel(writer, sheet_name="Monthly P&L", index=False)
        ws2 = writer.sheets["Monthly P&L"]
        ws2.set_column("A:A", 12)
        ws2.set_column("B:F", 15)

        # Sheet 3: Weekly P&L
        weekly_df.to_excel(writer, sheet_name="Weekly P&L", index=False)

        # Sheet 4: Summary
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        ws4 = writer.sheets["Summary"]
        ws4.set_column("A:B", 30)

        # Sheet 5: Per Stock
        stock_df.to_excel(writer, sheet_name="Per Stock", index=False)
        ws5 = writer.sheets["Per Stock"]
        ws5.set_column("A:A", 15)
        ws5.set_column("B:G", 15)

        # Equity curve chart
        _add_equity_chart(writer, workbook, monthly_df)

    return filename


def _calculate_monthly_pnl(trades: list) -> pd.DataFrame:
    rows = []
    by_month = {}

    for t in trades:
        exit_time = t.get("exit_time", "")
        if not exit_time:
            continue
        month = exit_time[:7]  # YYYY-MM
        if month not in by_month:
            by_month[month] = []
        by_month[month].append(t)

    for month, month_trades in sorted(by_month.items()):
        total_pnl = sum(t.get("pnl", 0) for t in month_trades)
        wins = len([t for t in month_trades if (t.get("pnl") or 0) > 0])
        total = len(month_trades)
        rows.append({
            "Month": month,
            "Total Trades": total,
            "Wins": wins,
            "Losses": total - wins,
            "Win Rate %": round(wins / total * 100, 1) if total > 0 else 0,
            "Total P&L (₹)": round(total_pnl, 2),
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Month", "Total Trades", "Wins", "Losses", "Win Rate %", "Total P&L (₹)"]
    )


def _calculate_weekly_pnl(trades: list) -> pd.DataFrame:
    rows = []
    by_week = {}

    for t in trades:
        exit_time = t.get("exit_time", "")
        if not exit_time:
            continue
        try:
            dt = datetime.fromisoformat(exit_time)
            week = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
        except (ValueError, TypeError, AttributeError):
            continue
        if week not in by_week:
            by_week[week] = []
        by_week[week].append(t)

    for week, week_trades in sorted(by_week.items()):
        total_pnl = sum(t.get("pnl", 0) for t in week_trades)
        wins = len([t for t in week_trades if (t.get("pnl") or 0) > 0])
        total = len(week_trades)
        rows.append({
            "Week": week,
            "Total Trades": total,
            "Wins": wins,
            "Losses": total - wins,
            "Win Rate %": round(wins / total * 100, 1) if total > 0 else 0,
            "Total P&L (₹)": round(total_pnl, 2),
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Week", "Total Trades", "Wins", "Losses", "Win Rate %", "Total P&L (₹)"]
    )


def _calculate_summary_metrics(trades: list) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()

    total_pnl = sum(t.get("pnl", 0) for t in trades)
    wins = [t for t in trades if (t.get("pnl") or 0) > 0]
    losses = [t for t in trades if (t.get("pnl") or 0) <= 0]
    total = len(trades)

    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0

    metrics = [
        ("Total Closed Trades", total),
        ("Total Wins", len(wins)),
        ("Total Losses", len(losses)),
        ("Win Rate %", f"{len(wins)/total*100:.1f}%" if total > 0 else "0%"),
        ("Total P&L (₹)", f"₹{total_pnl:,.2f}"),
        ("Avg Win (₹)", f"₹{avg_win:,.2f}"),
        ("Avg Loss (₹)", f"₹{avg_loss:,.2f}"),
        ("Profit Factor", f"{profit_factor:.2f}"),
        ("Report Generated", now_ist().strftime("%d-%b-%Y %H:%M IST")),
    ]

    return pd.DataFrame(metrics, columns=["Metric", "Value"])


def _calculate_per_stock_performance(trades: list) -> pd.DataFrame:
    by_stock = {}
    for t in trades:
        sym = t.get("symbol", "UNKNOWN")
        if sym not in by_stock:
            by_stock[sym] = []
        by_stock[sym].append(t)

    rows = []
    for sym, stock_trades in sorted(by_stock.items()):
        total_pnl = sum(t.get("pnl", 0) for t in stock_trades)
        wins = len([t for t in stock_trades if (t.get("pnl") or 0) > 0])
        total = len(stock_trades)
        rows.append({
            "Symbol": sym,
            "Trades": total,
            "Wins": wins,
            "Win Rate %": round(wins / total * 100, 1) if total > 0 else 0,
            "Total P&L (₹)": round(total_pnl, 2),
            "Avg P&L (₹)": round(total_pnl / total, 2) if total > 0 else 0,
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Symbol", "Trades", "Wins", "Win Rate %", "Total P&L (₹)", "Avg P&L (₹)"]
    )


def _add_equity_chart(writer, workbook, monthly_df: pd.DataFrame):
    """Add equity curve chart to Monthly P&L sheet."""
    if monthly_df.empty:
        return
    try:
        ws = writer.sheets["Monthly P&L"]
        chart = workbook.add_chart({"type": "line"})
        rows = len(monthly_df) + 1
        chart.add_series({
            "name": "Monthly P&L",
            "categories": ["Monthly P&L", 1, 0, rows, 0],
            "values": ["Monthly P&L", 1, 5, rows, 5],
            "line": {"color": "#1a472a", "width": 2},
        })
        chart.set_title({"name": "Monthly P&L Chart"})
        chart.set_x_axis({"name": "Month"})
        chart.set_y_axis({"name": "P&L (₹)"})
        chart.set_style(10)
        ws.insert_chart("H2", chart, {"x_scale": 1.5, "y_scale": 1.2})
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"_add_pnl_chart: Chart creation failed: {type(e).__name__}: {e}")


# ─────────────────────────────────────────────
# TELEGRAM TEXT REPORT — Subscriber
# ─────────────────────────────────────────────

def get_subscriber_report(chat_id: int) -> str:
    """
    Text-based P&L summary for subscriber in Telegram.
    No stock names shown.
    """
    trades_data = load_json(TRADES_FILE, {"trades": []})
    closed = [t for t in trades_data["trades"] if t["status"] == "CLOSED"]

    if not closed:
        return "📭 No closed trades yet."

    total_pnl = sum(t.get("pnl", 0) for t in closed)
    wins = len([t for t in closed if (t.get("pnl") or 0) > 0])
    total = len(closed)

    # This month
    this_month = now_ist().strftime("%Y-%m")
    month_trades = [t for t in closed if (t.get("exit_time") or "")[:7] == this_month]
    month_pnl = sum(t.get("pnl", 0) for t in month_trades)

    return (
        f"📊 *Strategy Performance Report*\n\n"
        f"━━━ Overall ━━━\n"
        f"Total Trades: `{total}`\n"
        f"Win Rate: `{wins/total*100:.1f}%`\n"
        f"Total P&L: `₹{total_pnl:,.2f}`\n\n"
        f"━━━ This Month ━━━\n"
        f"Trades: `{len(month_trades)}`\n"
        f"P&L: `₹{month_pnl:,.2f}`\n\n"
        f"_For detailed report, contact admin._"
    )
