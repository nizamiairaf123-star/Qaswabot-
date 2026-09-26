"""
universe_snapshot_manager.py — QUANT-001 fix (forward-looking part).

PROBLEM: backtester.load_halal_symbols() (and stock_selector.load_halal_universe())
only ever read TODAY's single CUSTOM_UNIVERSE_FINAL.csv. A backtest over the last
10 years therefore tests every symbol currently eligible across ALL of those 10
years (look-ahead bias — a stock that only became eligible last month gets tested
as if it were always tradeable) and never tests a symbol that was eligible in the
past but has since dropped out (survivorship bias).

HONEST LIMIT (checked directly — no historical eligibility archive exists
anywhere in this codebase: no dated snapshot files, no history table in
custom_universe_state.json, nothing in the DB). This means TRUE retroactive
point-in-time correction of PAST backtest years is not possible without
fabricating data that was never captured — doing so would violate the
no-fabrication rule. What IS honestly fixable:

  1. Start capturing a dated snapshot of the eligible universe every time it's
     refreshed (this module), so from today forward, real point-in-time
     backtesting becomes possible as history accumulates.
  2. Stop letting the backtest report imply full historical accuracy it
     doesn't have — surface the limitation explicitly in the backtest output
     (wired in backtester.py) instead of the current silent no-op with no
     mention.

Snapshots are stored as one CSV per successful universe refresh at
data/universe_snapshots/universe_<YYYY-MM-DD>.csv (symbol column only —
the full CUSTOM_UNIVERSE_FINAL.csv already has today's row detail; a
snapshot only needs to record WHICH symbols were eligible on that date).
"""

import os
import logging
import pandas as pd

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = "data/universe_snapshots"


def save_universe_snapshot(eligible_symbols: list, as_of_date=None) -> bool:
    """
    Call this on every SUCCESSFUL universe refresh (wired into
    scheduler._monthly_board_universe_update_job's success branch).
    Writes data/universe_snapshots/universe_<date>.csv. Never raises —
    a snapshot-save failure must not block the universe refresh itself
    (fail-open by design for this specific side-channel, since the
    refresh's own success/failure has its own separate fail-closed
    handling in scheduler.py).
    """
    try:
        from utils import now_ist
        default_date = now_ist().date()
    except Exception:
        import datetime
        default_date = datetime.date.today()

    if as_of_date is None:
        date_str = default_date.isoformat()
    elif isinstance(as_of_date, str):
        date_str = as_of_date
    else:
        date_str = as_of_date.isoformat()

    try:
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        path = os.path.join(SNAPSHOT_DIR, f"universe_{date_str}.csv")
        pd.DataFrame({"symbol": list(eligible_symbols)}).to_csv(path, index=False)
        logger.info(f"[UNIVERSE-SNAPSHOT] saved {len(eligible_symbols)} symbols -> {path}")
        return True
    except Exception as e:
        logger.warning(f"[UNIVERSE-SNAPSHOT] save failed for {date_str}: {e}")
        return False


def list_snapshot_dates() -> list:
    """Sorted list of ISO date strings for which a snapshot exists."""
    try:
        if not os.path.isdir(SNAPSHOT_DIR):
            return []
        dates = []
        for fname in os.listdir(SNAPSHOT_DIR):
            if fname.startswith("universe_") and fname.endswith(".csv"):
                dates.append(fname[len("universe_"):-len(".csv")])
        return sorted(dates)
    except Exception as e:
        logger.warning(f"[UNIVERSE-SNAPSHOT] list failed: {e}")
        return []


def get_nearest_snapshot_asof(date_str: str):
    """
    Returns the symbol list from the LATEST snapshot dated <= date_str, or
    None if no snapshot exists at or before that date (i.e. that historical
    period predates when snapshotting started — genuinely unknown, not a
    bug, and callers must treat None as "point-in-time data unavailable",
    never silently substitute today's universe for it).
    """
    dates = [d for d in list_snapshot_dates() if d <= date_str]
    if not dates:
        return None
    latest = dates[-1]
    try:
        df = pd.read_csv(os.path.join(SNAPSHOT_DIR, f"universe_{latest}.csv"))
        return df["symbol"].tolist()
    except Exception as e:
        logger.warning(f"[UNIVERSE-SNAPSHOT] read failed for {latest}: {e}")
        return None


def earliest_snapshot_date():
    """First date we actually have real point-in-time universe data for.
    None if snapshotting hasn't captured anything yet."""
    dates = list_snapshot_dates()
    return dates[0] if dates else None
