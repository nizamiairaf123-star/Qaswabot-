"""
stock_selector.py — Tradeable halal universe gatekeeper (v3.2 Custom)
F074: Single validated halal eligibility source + v3.2 Custom Core Business Halal + Non-Muslim Board Filter + Fail-Closed

Changes in v3.2 [DESIGN: AIRAF NIZAMI]:
- Owner criteria: Core Business 100% Halal (Sharia law) + 100% Non-Muslim Board
- Strict NSE cash-equity universe only; BSE-only stocks are rejected
- Filters: core_business_halal, non_muslim_board, price > 100, illiquid block
- Fail-Closed: is_universe_data_stale() reads data/custom_universe_state.json
- Monthly auto-update compatible with CUSTOM_UNIVERSE_FINAL.csv

Preserves: Half-Kelly, risk gates, GTT controls, existing function signatures
"""

import os
import json
import pandas as pd
from datetime import datetime
from utils import load_json, logger, now_ist

try:
    from config import (
        CUSTOM_UNIVERSE_FILE,
        CUSTOM_UNIVERSE_STATE_FILE,
        BACKTEST_RESULTS_FILE,
        ENABLE_BSE_TRADING,
        ORDER_SEGMENT,
        PARAMS,
    )
except ImportError:
    # Fallback for testing without full config
    CUSTOM_UNIVERSE_FILE = "data/CUSTOM_UNIVERSE_FINAL.csv"
    CUSTOM_UNIVERSE_STATE_FILE = "data/custom_universe_state.json"
    BACKTEST_RESULTS_FILE = "data/backtest_results.json"
    ENABLE_BSE_TRADING = False
    ORDER_SEGMENT = "NSE_EQ"
    PARAMS = {}

SELECTED_STOCKS_FILE = "data/selected_stocks.json"

# v3.2 Required columns — includes new filters
REQUIRED_HALAL_COLUMNS = {"symbol", "halal", "security_id", "series", "exchange"}
REQUIRED_CUSTOM_COLUMNS = {"symbol", "security_id", "series", "exchange", "non_muslim_board", "core_business_halal"}

# Backward compat set for old CSV
LEGACY_REQUIRED = {"symbol", "halal", "security_id", "series", "exchange"}


def _runtime_exchange() -> str:
    """Derive the runtime exchange from configured broker order segment."""
    segment = str(ORDER_SEGMENT or "")
    if "_" in segment:
        return segment.split("_", 1)[0].upper()
    return segment.upper()


def _runtime_series() -> str:
    """Derive the runtime equity series from configured broker order segment."""
    segment = str(ORDER_SEGMENT or "")
    if "_" in segment:
        return segment.rsplit("_", 1)[-1].upper()
    return ""


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y", "t"}


def is_universe_data_stale() -> bool:
    """
    v3.2 Fail-Closed check: Reads data/custom_universe_state.json
    Returns True if BOARD_DATA_STALE_PAUSE == True or data is stale beyond limit.

    If the state file is genuinely missing (first run, nothing to be stale yet),
    returns False. Any other failure (unreadable file, corrupt JSON, unparseable
    timestamp, or any unexpected error) returns True (stale/paused) — this is a
    compliance gate (board data), so "don't know" must mean "don't trade", not
    "assume it's fine". [AUDIT FIX #9: previous version fail-opened here.]
    """
    state_path = CUSTOM_UNIVERSE_STATE_FILE if 'CUSTOM_UNIVERSE_STATE_FILE' in globals() else "data/custom_universe_state.json"
    if not os.path.exists(state_path):
        # Compliance data has never been successfully verified.  Unknown
        # freshness is unsafe, so first deployment is blocked until the
        # first successful board/universe refresh creates the state file.
        logger.warning(f"is_universe_data_stale: state file missing at {state_path} — Fail-Closed")
        return True
    try:
        with open(state_path, 'r') as f:
            data = json.load(f)

        # 1. Direct pause flag — fail closed immediately
        if data.get("BOARD_DATA_STALE_PAUSE") is True:
            logger.warning(f"is_universe_data_stale: BOARD_DATA_STALE_PAUSE=True in {state_path} — Fail-Closed active")
            return True

        # 2. Check staleness by days since last successful update
        stale_limit = 35
        try:
            stale_limit = int(PARAMS.get("board_data_stale_days_limit", 35)) if PARAMS else 35
        except Exception:
            stale_limit = 35

        last_success = data.get("last_successful_update")
        if last_success:
            try:
                # Parse ISO format: 2026-08-01T08:30:00 or 2026-08-01
                if isinstance(last_success, str):
                    # Handle both date-only and datetime
                    if "T" in last_success:
                        last_dt = datetime.fromisoformat(last_success.replace("Z", ""))
                    else:
                        last_dt = datetime.fromisoformat(last_success)
                    # Make timezone aware as IST if naive
                    if last_dt.tzinfo is None:
                        # Assume IST but compare with UTC now -> use days diff
                        pass
                    now = now_ist().replace(tzinfo=None)
                    delta = now - last_dt.replace(tzinfo=None) if last_dt.tzinfo else now - last_dt
                    if delta.days > stale_limit:
                        logger.warning(f"is_universe_data_stale: Last update {last_success} is {delta.days} days ago > {stale_limit} limit — Fail-Closed")
                        return True
            except Exception as e:
                # Could not parse the timestamp at all -> we genuinely don't know
                # how old the board data is. Fail-closed: treat as stale.
                logger.error(f"is_universe_data_stale: Failed to parse last_successful_update '{last_success}': {e} — Fail-Closed (treating as stale)")
                return True
        else:
            # No last_successful_update recorded at all -> unknown age -> fail-closed
            logger.error("is_universe_data_stale: no last_successful_update in state file — Fail-Closed (treating as stale)")
            return True

        # [AUDIT ADD] Also fail-closed if the turnover-liquidity data has
        # gone stale — same reasoning as the board check above: this is now
        # a genuine entry-eligibility criterion (_is_turnover_liquid), so
        # "don't know if it's still accurate" must pause new trades, not
        # silently keep trading on outdated liquidity classifications.
        try:
            from liquidity_screen import is_liquidity_data_stale
            if is_liquidity_data_stale():
                logger.warning("is_universe_data_stale: turnover-liquidity data is stale — Fail-Closed active")
                return True
        except (ImportError, RuntimeError) as e:
            # Consistent with this function's own fail-closed philosophy:
            # if we can't even determine liquidity staleness, don't assume
            # it's fine — treat as stale/paused.
            logger.error(f"is_universe_data_stale: could not check liquidity staleness: {type(e).__name__}: {e} — Fail-Closed (treating as stale)")
            return True

        return False
    except Exception as e:
        logger.error(f"is_universe_data_stale: Failed to read/parse {state_path}: {type(e).__name__}: {e} — Fail-Closed (treating as stale)")
        return True


def _is_price_valid(row) -> bool:
    """Fail-closed price gate: require a verified price and enforce min-price threshold."""

    try:
        min_price = 100.0
        try:
            min_price = float(PARAMS.get("min_price_threshold", 100.0)) if PARAMS else 100.0
        except Exception:
            min_price = 100.0

        # Try multiple possible price column names
        price = None
        for col in ["last_price", "price", "ltp", "close", "Close", "current_price"]:
            if col in row and pd.notna(row.get(col)):
                try:
                    price = float(row.get(col))
                    break
                except (ValueError, TypeError):
                    continue

        if price is None:
            logger.warning("Price verification unavailable for %s — blocking (fail-closed)",
                           row.get("symbol", "<unknown>") if hasattr(row, "get") else "<unknown>")
            return False

        return price > min_price
    except Exception as e:
        logger.error("Price validation failed — blocking (fail-closed): %s", e)
        return False


def _is_turnover_liquid(row) -> bool:
    """
    [AUDIT ADD] Trading-volume liquidity check (MSCI ATVR + Frequency of
    Trading, see liquidity_screen.py) — distinct from _is_liquid() above,
    which is the Sharia balance-sheet illiquid-assets ratio, a completely
    different concept. This answers "does this stock always have an active
    buyer/seller, sized relative to its own market cap" — user's stated
    concern was entering a stock easily but finding no buyer at exit.

    Fails closed on missing data (same convention as the board/Sharia
    columns) — a symbol that has never been scored by
    liquidity_screen.refresh_liquidity_data() is NOT assumed liquid.
    This means `refresh_liquidity_data()` must run at least once before
    any symbol can pass — same bootstrap requirement as running
    board_filter_auto.py once before first live use (see blueprint setup).
    """
    try:
        if PARAMS and not PARAMS.get("enable_turnover_liquidity_filter", True):
            return True  # feature disabled entirely
        if "turnover_liquid_ok" in row and pd.notna(row.get("turnover_liquid_ok")):
            return _as_bool(row.get("turnover_liquid_ok")) is True
        # Column missing/NaN -> never scored -> fail closed
        return False
    except Exception as e:
        logger.warning(f"_is_turnover_liquid: check failed: {type(e).__name__}: {e} — blocking")
        return False


def _is_liquid(row) -> bool:
    """Check illiquid filter. Returns True if liquid (tradeable), False if illiquid (block)."""
    try:
        # If enable_illiquid_filter is disabled in config, allow all
        if PARAMS and not PARAMS.get("enable_illiquid_filter", True):
            return True

        # Direct boolean flags
        for col in ["is_illiquid", "illiquid"]:
            if col in row and pd.notna(row.get(col)):
                # If is_illiquid == True → NOT liquid → block
                if _as_bool(row.get(col)) is True:
                    return False

        # Inverted flag: net_liquid_ok == False → illiquid
        if "net_liquid_ok" in row and pd.notna(row.get("net_liquid_ok")):
            if _as_bool(row.get("net_liquid_ok")) is False:
                return False

        # illiquid_asset_pct high? Old logic had threshold but we keep simple:
        # If illiquid_asset_pct column exists and > 90% and net_liquid_ok False => handled above
        # New system: if is_illiquid flag True, block; else allow for now.
        # Future: volume based check can be added here via Dhan avg volume.

        return True
    except Exception as e:
        logger.warning(f"_is_liquid: check failed: {type(e).__name__}: {e} — blocking")
        return False


def _deduplicate_nse_preferred(df: pd.DataFrame) -> pd.DataFrame:
    """
    Strict NSE-EQ execution universe.
    If symbol exists in multiple source rows, keep the NSE row only.
    BSE-only rows are rejected from the execution universe.
    """
    if df.empty:
        return df

    try:
        # Normalize symbol for grouping
        df["_norm_symbol"] = df["symbol"].astype(str).str.strip().str.upper()
        df["_exchange_norm"] = df["exchange"].astype(str).str.strip().str.upper()

        # Strict NSE-only: discard all non-NSE rows before deduplication.
        nse_df = df[df["_exchange_norm"] == "NSE"].copy()
        if nse_df.empty:
            return nse_df.drop(columns=["_norm_symbol", "_exchange_norm", "_pref"], errors="ignore")

        # Prefer one NSE row per symbol.
        nse_df["_pref"] = 0
        df_sorted = nse_df.sort_values(["_norm_symbol", "exchange"])
        deduped = df_sorted.drop_duplicates(subset=["_norm_symbol"], keep="first")

        # Clean temp columns
        deduped = deduped.drop(columns=["_norm_symbol", "_exchange_norm", "_pref"], errors="ignore")
        # Also drop from original df if present (cleanup)
        df.drop(columns=["_norm_symbol", "_exchange_norm", "_pref"], errors="ignore", inplace=True)

        logger.info(f"_deduplicate_nse_preferred: {len(df)} → {len(deduped)} after NSE-preferred dedup")
        return deduped
    except Exception as e:
        logger.warning(f"_deduplicate_nse_preferred failed: {e} — returning original df")
        # Cleanup temp columns on failure
        for col in ["_norm_symbol", "_exchange_norm", "_pref"]:
            if col in df.columns:
                try:
                    df.drop(columns=[col], inplace=True)
                except Exception:
                    pass
        return df


def load_halal_universe() -> pd.DataFrame:
    """
    Load and schema-validate the single tradable universe CSV; fail closed
    on error. v3.2: sirf CUSTOM_UNIVERSE_FILE — koi legacy fallback nahi.
    """
    # Fail-closed if stale pause active
    if is_universe_data_stale():
        logger.warning("load_halal_universe: BOARD_DATA_STALE_PAUSE active — returning empty universe (Fail-Closed)")
        return pd.DataFrame()

    custom_path = CUSTOM_UNIVERSE_FILE if 'CUSTOM_UNIVERSE_FILE' in globals() else "data/CUSTOM_UNIVERSE_FINAL.csv"

    def _try_load(path, required_set, file_label):
        try:
            if not os.path.exists(path):
                logger.info(f"load_halal_universe: {file_label} not found at {path}")
                return None
            df = pd.read_csv(path)
            if df.empty:
                logger.warning(f"load_halal_universe: {file_label} at {path} is empty")
                return pd.DataFrame()
            missing = required_set - set(df.columns)
            if missing:
                logger.warning(f"load_halal_universe: CUSTOM missing required {sorted(missing)} in {path}")
                return None
            return df
        except (FileNotFoundError, OSError, ValueError, pd.errors.EmptyDataError) as e:
            logger.warning(f"load_halal_universe: Failed to load {file_label} {path}: {type(e).__name__}: {e}")
            return None
        except Exception as e:
            logger.warning(f"load_halal_universe: Unexpected error loading {file_label} {path}: {type(e).__name__}: {e}")
            return None

    df = _try_load(custom_path, REQUIRED_CUSTOM_COLUMNS, "CUSTOM")
    if df is not None and not df.empty:
        logger.info(f"load_halal_universe: Loaded CUSTOM universe from {custom_path} with {len(df)} rows (Core Halal + 100% Non-Muslim Board)")
        return df

    # Single source — missing file = fail closed, no fallback
    logger.warning(f"load_halal_universe: CUSTOM universe not found at {custom_path} — returning empty (Fail-Closed)")
    return pd.DataFrame()


def _row_is_halal_eligible(row, include_turnover_liquidity: bool = True) -> bool:
    """
    Central v3.2 eligibility validator for one universe row.
    Implements:
    - Core Business Halal 100% (Sharia law — owner criteria)
    - Non-Muslim Board 100% (owner criteria — nahi to block)
    - Price > 100
    - Turnover-liquidity block (MSCI ATVR + Frequency of Trading — trading-
      volume liquidity, execution concern, not a Sharia criterion)
    - NSE-preferred handled at dataframe level, not row level
    - Haram pending exit
    - Security ID, symbol presence
    - Exchange/Series matching runtime (with full universe override)
    """
    symbol = str(row.get("symbol", "")).strip()
    security_id = str(row.get("security_id", "")).strip()
    exchange = str(row.get("exchange", "")).strip().upper()
    series = str(row.get("series", "")).strip().upper()

    if not symbol or not security_id or security_id.lower() in {"nan", "none"}:
        return False

    # --- v3.2 Custom Filters ---

    # 1. Core Business Halal (100% required)
    # Try core_business_halal column first, fallback to halal column for legacy
    try:
        require_core = True
        if PARAMS:
            require_core = PARAMS.get("require_core_business_halal", True)
        if require_core:
            if "core_business_halal" in row and pd.notna(row.get("core_business_halal")):
                if not _as_bool(row.get("core_business_halal")):
                    return False
            elif "halal" in row and pd.notna(row.get("halal")):
                # Backward compat fallback
                if not _as_bool(row.get("halal")):
                    return False
            else:
                # No halal info at all -> fail closed (block)
                return False
    except Exception:
        # On error, fail closed for safety? But to avoid blocking all on bad row, we check halal fallback
        try:
            if "halal" in row and not _as_bool(row.get("halal")):
                return False
        except Exception:
            return False

    # 2. Non-Muslim Board (100% required)
    try:
        require_board = True
        if PARAMS:
            require_board = PARAMS.get("require_non_muslim_board", True)
        if require_board and PARAMS.get("enable_board_filter", True):
            if "non_muslim_board" in row and pd.notna(row.get("non_muslim_board")):
                if not _as_bool(row.get("non_muslim_board")):
                    return False
            else:
                # If column missing in CUSTOM file, fail closed — do not allow
                # But for LEGACY file we injected True above, so this only triggers for malformed CUSTOM
                # Check if this is CUSTOM file context by presence of other new columns
                if "core_business_halal" in row and "non_muslim_board" not in row:
                    # CUSTOM file malformed — missing board column => fail closed for this row
                    logger.warning(f"_row_is_halal_eligible: Row for {symbol} missing non_muslim_board in CUSTOM file — blocking")
                    return False
                # For legacy injected case, we already have True, so pass
    except Exception as e:
        logger.warning(f"_row_is_halal_eligible: board check failed for {symbol}: {e} — blocking")
        return False

    # 3. Price > 100
    if not _is_price_valid(row):
        return False

    # 4. [Owner scope decision] Balance-sheet ratio checks are NOT part of
    # this bot's Sharia criteria. The two religious criteria enforced here:
    # (a) core business activity halal — no alcohol/gambling/pork/adult/
    # conventional-interest-banking (`core_business_halal` flag), and
    # (b) 100% Non-Muslim board of directors (owner's requirement).
    # `_is_liquid()` is left defined (unused) in case a future decision
    # re-enables it. Zakat (sharia_manager.py) is a separate, unrelated
    # calculator and has no eligibility-gate role.

    # 4b. Turnover-liquidity check (MSCI ATVR + Frequency of Trading) — a
    # trading-execution concern, NOT a Sharia criterion, kept as-is.
    if include_turnover_liquidity and not _is_turnover_liquid(row):
        return False

    # 5. Haram pending exit (mid-trade reclassification policy)
    try:
        from sharia_manager import is_haram_pending_exit
        if is_haram_pending_exit(symbol):
            return False
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"_row_is_halal_eligible: haram-pending check failed for {symbol}: {type(e).__name__}: {e}")
        return False

    # 6. Exchange / Series check — with full universe override
    runtime_exchange = _runtime_exchange()
    runtime_series = _runtime_series()

    try:
        # Final execution universe is strictly NSE EQ. BSE-only symbols are
        # not eligible, regardless of ENABLE_BSE_TRADING or legacy flags.
        # This is the mandated cash-equity execution boundary.
        if exchange != "NSE":
            return False
        required_series = runtime_series or "EQ"
        if series != required_series:
            return False
    except Exception:
        # On error in exchange logic, fail closed
        return False

    return True


def _eligible_halal_universe() -> pd.DataFrame:
    """Return only rows that pass the centralized halal eligibility validator (v3.2)."""
    # Fail-closed if stale
    if is_universe_data_stale():
        logger.warning("_eligible_halal_universe: Stale pause active — returning empty")
        return pd.DataFrame()

    df = load_halal_universe()
    if df.empty:
        return pd.DataFrame()

    # Apply row-level filters
    try:
        mask = df.apply(_row_is_halal_eligible, axis=1)
        filtered = df[mask].copy()
    except Exception as e:
        logger.warning(f"_eligible_halal_universe: Filter apply failed: {e} — returning empty")
        return pd.DataFrame()

    # Apply strict NSE-only deduplication.
    try:
        deduped = _deduplicate_nse_preferred(filtered)
        return deduped
    except Exception as e:
        logger.warning(f"_eligible_halal_universe: Dedup failed: {e}")
        return filtered


def is_in_halal_universe(symbol: str) -> bool:
    """Return True only if symbol is currently halal-eligible for runtime (v3.2 with stale check)."""
    if not symbol:
        return False

    # Fail-closed stale check — block all
    if is_universe_data_stale():
        return False

    df = _eligible_halal_universe()
    if df.empty:
        return False
    return str(symbol).strip() in set(df["symbol"].astype(str).str.strip())


def load_halal_symbols() -> list:
    """Get all currently eligible halal symbols (v3.2)."""
    if is_universe_data_stale():
        return []
    df = _eligible_halal_universe()
    if df.empty:
        return []
    return df["symbol"].astype(str).str.strip().tolist()


def get_security_id(symbol: str) -> str:
    """Get Dhan security ID only for currently halal-eligible symbols (v3.2)."""
    if not symbol:
        return None
    if is_universe_data_stale():
        return None
    symbol = str(symbol).strip()
    df = _eligible_halal_universe()
    if df.empty:
        return None
    row = df[df["symbol"].astype(str).str.strip() == symbol]
    if row.empty:
        return None
    security_id = str(row["security_id"].values[0]).strip()
    if not security_id or security_id.lower() in {"nan", "none"}:
        return None
    return security_id


def get_tradeable_universe() -> list:
    """
    Return the COMPLETE currently eligible NSE-EQ universe for signal scanning.

    Architecture: universe eligibility and strategy-quality deployment are two
    separate gates. This function must not preselect stocks using historical
    backtest results; otherwise the bot is not actually scanning the full
    eligible NSE universe. Per-stock strategy/deployment validity is enforced
    immediately before order entry by the risk/deployment gate.
    """
    if is_universe_data_stale():
        logger.warning("get_tradeable_universe: Stale pause active — returning empty (Fail-Closed)")
        return []
    return load_halal_symbols()


def is_deployed_strategy_valid(symbol: str) -> bool:
    """Return True only when a symbol has a valid deployed/backtest strategy."""
    symbol = str(symbol or "").strip()
    if not symbol or is_universe_data_stale():
        return False
    backtest = load_json(BACKTEST_RESULTS_FILE, {})
    stocks = backtest.get("stocks", {})
    result = stocks.get(symbol)
    if not isinstance(result, dict) or not result.get("valid"):
        return False
    min_trades = int(PARAMS.get("universe_min_trades", 3))
    if result.get("total_trades", 0) < min_trades:
        return False
    source = backtest.get("source", "backtest")
    if source == "optimization_walkforward":
        return float(result.get("win_rate_pct", 0)) >= float(PARAMS.get("universe_min_wr_opt", 25.0))
    return float(result.get("win_rate_pct", 0)) >= float(PARAMS.get("universe_min_wr_backtest", 30.0))


def get_deployed_symbols() -> list:
    """Get symbols that were deployed (active_symbols from deployment)."""
    backtest = load_json(BACKTEST_RESULTS_FILE, {})
    return backtest.get("active_symbols", [])


def get_blocked_symbols() -> list:
    """Get symbols that were blocked during deployment."""
    backtest = load_json(BACKTEST_RESULTS_FILE, {})
    return backtest.get("blocked_symbols", [])
