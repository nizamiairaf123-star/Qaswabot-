"""
intraday_filter.py — Same-day CNC EXIT possibility check + market-hours filter

YE MIS / INTRADAY PRODUCT NAHI HAI.
Bot CNC swing hai (delivery, overnight hold). Order product hamesha CNC.

Is filter ka SIRF itna kaam hai:
- Jis stock me ENTRY allowed ho lekin SAME-DAY EXIT banned ho (BE / T2T /
  trade-to-trade), usme ENTRY HI MAT LO.
- Kyunki SL/TP hit hua to exit nahi milega — position stuck.

Dhan scrip master:
- EQ  = same-day CNC sell possible → allow
- BE / T2T / other series = same-day exit not possible → block

CSV downloaded daily at 8:30 AM by scheduler.
"""

import logging

import os
import pandas as pd

logger = logging.getLogger(__name__)
from utils import is_market_open, append_log
from config import AUDIT_LOG_FILE

SCRIP_MASTER_FILE = "data/scrip_master.csv"
SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

# In-memory cache to avoid re-reading CSV every call
_scrip_cache = None


# ─────────────────────────────────────────────
# CSV DOWNLOAD
# ─────────────────────────────────────────────

def download_scrip_master():
    """Download Dhan scrip master CSV. Called daily at 8:30 AM."""
    global _scrip_cache
    try:
        import requests
        from config import DATA_DIR
        os.makedirs(DATA_DIR, exist_ok=True)
        r = requests.get(SCRIP_MASTER_URL, timeout=30)
        r.raise_for_status()
        with open(SCRIP_MASTER_FILE, "wb") as f:
            f.write(r.content)
        _scrip_cache = None  # Reset cache after fresh download
        append_log(AUDIT_LOG_FILE, "SCRIP MASTER: Downloaded successfully")
        return True
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"SCRIP MASTER DOWNLOAD ERROR: {e}")
        return False


def _load_scrip_master() -> pd.DataFrame:
    """Load scrip master CSV into memory (cached)."""
    global _scrip_cache
    if _scrip_cache is not None:
        return _scrip_cache
    try:
        if not os.path.exists(SCRIP_MASTER_FILE):
            append_log(AUDIT_LOG_FILE, "SCRIP MASTER: File not found — downloading now")
            download_scrip_master()
        _scrip_cache = pd.read_csv(SCRIP_MASTER_FILE, low_memory=False)
        return _scrip_cache
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"SCRIP MASTER LOAD ERROR: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# INTRADAY CHECK
# ─────────────────────────────────────────────

def is_intraday_allowed(security_id: str, symbol: str) -> bool:
    """
    Same-day CNC EXIT possible? (name historical — this is NOT an MIS switch)

    Logic:
    - EQ series  = same-day CNC sell possible → allow entry
    - BE / T2T   = trade-to-trade → block (SL/TP hit pe exit nahi milega)

    Product type CNC hi rahega. Filter sirf un stocks ko hataata hai
    jahan entry allowed + exit banned ho.
    """
    try:
        df = _load_scrip_master()
        if df.empty:
            append_log(AUDIT_LOG_FILE, f"SCRIP MASTER empty — blocking {symbol} safe side")
            return False

        # Match by security_id (SEM_SMST_SECURITY_ID column)
        row = df[df["SEM_SMST_SECURITY_ID"].astype(str) == str(security_id)]

        if row.empty:
            append_log(AUDIT_LOG_FILE, f"SCRIP MASTER: {symbol} not found — blocking safe side")
            return False

        series = str(row["SEM_SERIES"].values[0]).strip().upper()

        if series == "EQ":
            return True
        else:
            append_log(AUDIT_LOG_FILE,
                       f"EXIT-BANNED BLOCK: {symbol} series={series} — "
                       f"same-day CNC exit not possible, skip (SL/TP stuck ho jaayega)")
            return False

    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"INTRADAY CHECK ERROR {symbol}: {e} — blocking safe side")
        return False


# ─────────────────────────────────────────────
# TIME CHECK
# ─────────────────────────────────────────────

def is_good_time_to_trade() -> tuple:
    """
    Returns (allowed: bool, reason: str)
    Only check: market must be open (9:15 - 15:30)
    No time-based restrictions — optimization will decide
    if any time slot is bad based on real trade data.
    """
    if not is_market_open():
        return False, "Market closed"

    return True, "Market open"


# ─────────────────────────────────────────────
# ANALYTICS — Best trading time slot
# ─────────────────────────────────────────────

def get_best_trading_time_slot() -> str:
    """Returns best historical 5-min slot based on P&L data."""
    from utils import load_json
    from config import TRADES_FILE
    from datetime import datetime

    data = load_json(TRADES_FILE, {"trades": []})
    trades = [t for t in data["trades"] if t["status"] == "CLOSED" and t.get("pnl")]

    if not trades:
        return "Not enough data"

    slot_stats = {}
    for trade in trades:
        entry_time = trade.get("entry_time", "")
        if not entry_time:
            continue
        try:
            dt = datetime.fromisoformat(entry_time)
            slot_min = (dt.minute // 5) * 5
            slot_key = f"{dt.hour:02d}:{slot_min:02d}"
            if slot_key not in slot_stats:
                slot_stats[slot_key] = {"pnl": 0, "count": 0}
            slot_stats[slot_key]["pnl"] += trade["pnl"]
            slot_stats[slot_key]["count"] += 1
        except (TypeError, ValueError, KeyError) as e:
            logger.debug(f"_slot_analysis: Trade stats failed: {type(e).__name__}: {e}")
            continue

    if not slot_stats:
        return "Not enough data"

    best = max(slot_stats.items(), key=lambda x: x[1]["pnl"])
    return f"{best[0]} (P&L: Rs{best[1]['pnl']:.0f}, trades: {best[1]['count']})"
