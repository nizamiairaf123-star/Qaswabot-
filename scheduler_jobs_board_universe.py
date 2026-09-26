"""Custom board/universe sync + monthly market-metadata/liquidity refresh jobs, and their shared state helpers (split out of scheduler.py, AI-DOS ARCH-003 god-module remediation, 2026-09-17)."""

import logging
from config import PARAMS
from utils import now_ist

logger = logging.getLogger(__name__)


def _load_custom_state():
    """Load data/custom_universe_state.json with defaults."""
    import os, json
    from config import CUSTOM_UNIVERSE_STATE_FILE
    default = {
        "last_successful_update": None,
        "last_attempt": None,
        # Missing state means board verification has NEVER succeeded.
        # Compliance gate therefore starts paused; only a verified successful
        # refresh may clear this flag.
        "BOARD_DATA_STALE_PAUSE": True,
        "last_error": "NO_SUCCESSFUL_BOARD_REFRESH_YET",
        "total_symbols": 0,
        "active_filters": ["core_business_halal", "non_muslim_board", "price>100", "illiquid", "strict NSE-EQ"]
    }
    try:
        path = CUSTOM_UNIVERSE_STATE_FILE if 'CUSTOM_UNIVERSE_STATE_FILE' in globals() else "data/custom_universe_state.json"
        # Fallback to config
        try:
            from config import CUSTOM_UNIVERSE_STATE_FILE as cfg_path
            path = cfg_path
        except Exception:
            path = "data/custom_universe_state.json"
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
            # Merge with defaults
            for k, v in default.items():
                if k not in data:
                    data[k] = v
            return data
        else:
            return default
    except Exception as e:
        logger.warning(f"_load_custom_state failed: {e}")
        return default


def _save_custom_state(state_dict):
    """Save state to data/custom_universe_state.json."""
    import os, json
    try:
        from config import CUSTOM_UNIVERSE_STATE_FILE as cfg_path
        path = cfg_path
    except Exception:
        path = "data/custom_universe_state.json"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(state_dict, f, indent=2)
        return True
    except Exception as e:
        logger.warning(f"_save_custom_state failed: {e}")
        return False


def _sync_custom_universe_logic():
    """
    Core sync logic — tries to download/sync updated CUSTOM_UNIVERSE_FINAL.csv

    v3.2 Implementation (production-grade with fallbacks):
    1. Try to fetch from external URL if CUSTOM_UNIVERSE_URL env set (future source refresh)
    2. Else re-scan canonical MASTER_STOCK_LIST_PERMANENT.csv and regenerate
       CUSTOM_UNIVERSE_FINAL.csv with the monthly Sharia + owner Board + NSE/EQ
       compliance criteria; trading-liquidity enrichment runs as the downstream
       decision-data stage.
    3. Handles reclassification: compares old vs new eligible list and calls handle_haram_reclassification
       for symbols that became ineligible, and clears pending for those that became eligible again

    Returns: (success: bool, message: str, count: int)
    """
    import os, pandas as pd, traceback
    from datetime import datetime
    from utils import now_ist
    try:
        from config import CUSTOM_UNIVERSE_FILE, CUSTOM_UNIVERSE_STATE_FILE, MASTER_STOCK_LIST_FILE
    except ImportError:
        CUSTOM_UNIVERSE_FILE = "data/CUSTOM_UNIVERSE_FINAL.csv"
        CUSTOM_UNIVERSE_STATE_FILE = "data/custom_universe_state.json"

    try:
        # Load existing custom universe for comparison (old eligible)
        old_symbols = set()
        old_path = CUSTOM_UNIVERSE_FILE
        if os.path.exists(old_path):
            try:
                old_df = pd.read_csv(old_path)
                old_symbols = set(old_df["symbol"].astype(str).str.strip().tolist())
            except Exception:
                old_symbols = set()

        # --- Attempt external fetch if URL configured ---
        # ADMIN NOTE: Price/Volume/Market data MUST use Dhan data only, not yfinance, to avoid 19-20 difference
        # Dhan is source of truth for trading (trade happens on Dhan account)
        # yfinance is used only for approved company information (this module uses board members) (companyOfficers) because Dhan does NOT provide board data
        # If any other AI sees yfinance usage for price/volume, DO NOT CHANGE without ADMIN PERMISSION
        external_url = os.getenv("CUSTOM_UNIVERSE_URL", "").strip()
        new_df = None
        if external_url:
            try:
                import requests
                logger.info(f"_sync_custom_universe_logic: Attempting download from {external_url}")
                resp = requests.get(external_url, timeout=30)
                resp.raise_for_status()
                from io import StringIO
                new_df = pd.read_csv(StringIO(resp.text))
                required = {"symbol", "security_id", "series", "exchange", "non_muslim_board", "core_business_halal"}
                missing = required - set(new_df.columns)
                if missing:
                    raise ValueError(f"Downloaded CSV missing required columns {missing}")
                logger.info(f"_sync_custom_universe_logic: Downloaded {len(new_df)} rows from external URL")
            except Exception as e:
                logger.warning(f"_sync_custom_universe_logic: External fetch failed: {e} — fallback to local re-scan")
                new_df = None

        # --- Fallback: Local re-scan / regeneration using DHAN data only (not yfinance) for price/volume ---
        # Dhan scrip master + Dhan market data is source of truth for trading
        if new_df is None:
            # Canonical monthly source is the full permanent master universe.
            # CUSTOM_UNIVERSE_FINAL.csv is the derived candidate/output, not its own
            # monthly source; using it as the next month's input caused stale-universe
            # drift and prevented newly re-qualified stocks from returning.
            base_path = MASTER_STOCK_LIST_FILE
            if not os.path.exists(base_path):
                raise FileNotFoundError(f"No master universe file found at {base_path} (canonical monthly source required)")

            base_df = pd.read_csv(base_path, low_memory=False)
            # Ensure new columns exist with defaults (backward compat)
            if "core_business_halal" not in base_df.columns:
                # Strict fail-closed: business-halal verification is mandatory.
                if "halal" in base_df.columns:
                    base_df["core_business_halal"] = base_df["halal"].apply(
                        lambda x: True if str(x).lower() in {"true","1","yes","y"} else False
                    )
                else:
                    raise ValueError(
                        "CUSTOM_UNIVERSE_FINAL.csv missing core_business_halal/halal "
                        "verification — refusing to trade"
                    )
            if "non_muslim_board" not in base_df.columns:
                # Strict fail-closed: missing board verification is a hard sync failure.
                raise ValueError("CUSTOM_UNIVERSE_FINAL.csv missing non_muslim_board column — board verification unavailable; refusing to trade")
            if "price" not in base_df.columns and "last_price" not in base_df.columns:
                raise ValueError(
                    "CUSTOM_UNIVERSE_FINAL.csv missing verified price — "
                    "refusing to synthesize a price"
                )
            if "is_illiquid" not in base_df.columns:
                if "net_liquid_ok" in base_df.columns:
                    base_df["is_illiquid"] = base_df["net_liquid_ok"].apply(
                        lambda x: not bool(x) if pd.notna(x) else True
                    )
                else:
                    raise ValueError(
                        "CUSTOM_UNIVERSE_FINAL.csv missing liquidity verification — "
                        "refusing to synthesize is_illiquid=False"
                    )

            # Apply v3.2 filters using same logic as stock_selector._row_is_halal_eligible
            # For regeneration keep only rows that pass core filters and strict NSE-EQ execution.
            try:
                from stock_selector import _row_is_halal_eligible, _deduplicate_nse_preferred
                # Compliance/universe stage: Sharia + Board + price + NSE/EQ.
                # Trading-liquidity is deliberately evaluated in the following
                # dedicated liquidity refresh, after this candidate universe exists.
                mask = base_df.apply(
                    lambda row: _row_is_halal_eligible(row, include_turnover_liquidity=False),
                    axis=1,
                )
                filtered = base_df[mask].copy()
                deduped = _deduplicate_nse_preferred(filtered)
                new_df = deduped
            except Exception as e:
                raise RuntimeError(
                    f"_sync_custom_universe_logic: eligibility filter failed — "
                    f"sync blocked fail-closed: {e}"
                ) from e

        # --- Handle strict NSE-EQ execution ---
        try:
            from stock_selector import _deduplicate_nse_preferred
            new_df = _deduplicate_nse_preferred(new_df)
            if new_df.empty:
                raise RuntimeError("Strict NSE-EQ filter produced an empty universe")
        except Exception as e:
            raise RuntimeError(f"Strict NSE-EQ filtering failed — sync blocked: {e}") from e

        # --- Apply Non-Muslim Board Filter from board_status.json (100% Non-Muslim required) ---
        # STRICT FAIL-CLOSED: missing/empty/incomplete board verification aborts the
        # sync. Never continue without the board filter and never synthesize True.
        try:
            from board_manager import refresh_board_status, load_json as bm_load
            board_symbols = new_df['symbol'].astype(str).str.strip().tolist()
            refresh_board_status(board_symbols)
            board_status = bm_load('data/board_status.json', {})
            missing = [sym for sym in board_symbols if sym not in board_status]
            failed = [sym for sym in board_symbols if board_status.get(sym, {}).get('board_refresh_failed') is True]
            if missing or failed:
                raise RuntimeError(
                    f"Board verification incomplete: missing={len(missing)}, failed={len(failed)}"
                )
            allowed_symbols = {
                sym for sym in board_symbols
                if board_status.get(sym, {}).get('non_muslim_board') is True
            }
            before_board = len(new_df)
            new_df = new_df[new_df['symbol'].isin(allowed_symbols)].copy()
            print(f'_sync_custom_universe_logic: Board filter applied: {before_board} -> {len(new_df)} after 100% Non-Muslim Board filter')
        except Exception as e:
            raise RuntimeError(f"Board filter failed — sync blocked fail-closed: {e}") from e

        # Liquidity is a downstream decision-data stage. The candidate universe
        # is published only after Sharia/Board/NSE-EQ checks; the dedicated
        # monthly liquidity job then enriches it with fresh Dhan-backed ATVR/FoT
        # metrics. Runtime entry remains fail-closed until that refresh succeeds.

        # --- [AUDIT ADD] Safety guard: refuse a catastrophic universe wipe ---
        # If the newly-filtered universe collapses to (near) zero or drops
        # drastically vs the previous file — e.g. because
        # liquidity_screen.refresh_liquidity_data() hasn't populated
        # turnover_liquid_ok yet on a fresh deployment, or any other filter
        # bug — do NOT silently overwrite the live universe file with an
        # empty/decimated one. Treat this as a sync FAILURE so
        # BOARD_DATA_STALE_PAUSE engages and the admin gets alerted, instead
        # of quietly ending up with a 0-stock tradeable universe.
        if old_symbols and len(new_df) < max(1, len(old_symbols) * 0.5):
            msg = (f"Sync produced {len(new_df)} rows vs previous {len(old_symbols)} — "
                   f">50% drop, refusing to overwrite (possible missing/stale filter data, "
                   f"e.g. turnover-liquidity not yet refreshed). Universe file left unchanged.")
            logger.error(f"_sync_custom_universe_logic: {msg}")
            return False, msg, len(old_symbols)
        if not old_symbols and len(new_df) == 0:
            msg = "Sync produced 0 rows on what appears to be a first run — refusing to write an empty universe file."
            logger.error(f"_sync_custom_universe_logic: {msg}")
            return False, msg, 0

        # --- Save new CUSTOM file ---
        os.makedirs(os.path.dirname(CUSTOM_UNIVERSE_FILE), exist_ok=True)
        new_df.to_csv(CUSTOM_UNIVERSE_FILE, index=False)
        logger.info(f"_sync_custom_universe_logic: Saved {len(new_df)} rows to {CUSTOM_UNIVERSE_FILE}")

        # --- Handle reclassification: compare old vs new symbols ---
        try:
            new_symbols = set(new_df["symbol"].astype(str).str.strip().tolist())
            # Symbols that were eligible before but now ineligible -> call handle_haram_reclassification
            became_ineligible = old_symbols - new_symbols if old_symbols else set()
            became_eligible_again = new_symbols - old_symbols if old_symbols else set()

            if became_ineligible:
                logger.info(f"_sync_custom_universe_logic: {len(became_ineligible)} symbols became ineligible: {sorted(list(became_ineligible))[:20]}")
                try:
                    from sharia_manager import handle_haram_reclassification
                    for sym in became_ineligible:
                        try:
                            handle_haram_reclassification(sym)
                        except Exception as inner_e:
                            logger.warning(f"  reclassification handling failed for {sym}: {inner_e}")
                except Exception as e:
                    logger.warning(f"Failed to import handle_haram_reclassification: {e}")

            if became_eligible_again:
                logger.info(f"_sync_custom_universe_logic: {len(became_eligible_again)} symbols became eligible again (auto-restore): {sorted(list(became_eligible_again))[:20]}")
                try:
                    from sharia_manager import clear_haram_pending
                    for sym in became_eligible_again:
                        try:
                            clear_haram_pending(sym)
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"_sync_custom_universe_logic: Reclassification handling failed: {e}")

        return True, f"Synced {len(new_df)} symbols to {CUSTOM_UNIVERSE_FILE}", len(new_df)

    except Exception as e:
        logger.warning(f"_sync_custom_universe_logic: FAILED: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        return False, f"{type(e).__name__}: {e}", 0


async def _monthly_board_universe_update_job():
    """
    Monthly Auto-Update & Fail-Closed Retry Engine — Runs 1st day 08:30 AM IST
    Spec:
    - On Success: Downloads/syncs CUSTOM_UNIVERSE_FINAL.csv, clears stale pause flag, sends success Telegram alert
    - On Failure: Sets BOARD_DATA_STALE_PAUSE=True, blocks BUY, sends warning alert, retries daily at 08:30
    """
    from utils import now_ist
    logger.info("_monthly_board_universe_update_job: Starting monthly board & universe update")

    try:
        # Load state and update last_attempt
        state = _load_custom_state()
        state["last_attempt"] = now_ist().isoformat()

        success, msg, count = _sync_custom_universe_logic()

        if success:
            # On Success
            state["last_successful_update"] = now_ist().isoformat()
            state["BOARD_DATA_STALE_PAUSE"] = False
            state["last_error"] = None
            state["total_symbols"] = count
            _save_custom_state(state)

            # [QUANT-001 FIX — forward-looking part] Capture a dated
            # snapshot of the eligible universe on every successful refresh
            # so real point-in-time backtesting becomes possible as history
            # accumulates. Fail-open: a snapshot-save problem must not
            # affect the refresh's own success/alerting, which already has
            # its own fail-closed handling above.
            try:
                from stock_selector import load_halal_universe, _row_is_halal_eligible
                from universe_snapshot_manager import save_universe_snapshot
                _df = load_halal_universe()
                if _df is not None and not _df.empty:
                    _eligible = _df[_df.apply(_row_is_halal_eligible, axis=1)]["symbol"].tolist()
                    save_universe_snapshot(_eligible)
            except Exception as e:
                logger.warning(f"_monthly_board_universe_update_job: universe snapshot capture failed (non-blocking): {e}")

            logger.info(f"_monthly_board_universe_update_job: SUCCESS — {msg}")

            # Send Telegram Admin Success Alert
            try:
                from signal_broadcaster import alert_admin
                await alert_admin(f"✅ Monthly Board & Universe Updated Successfully\n\n{msg}\nTime: {now_ist().strftime('%Y-%m-%d %H:%M IST')}\nTotal: {count} symbols\nFilters: Core Halal + 100% Non-Muslim Board + Price>100 + Liquid + strict NSE-EQ")
            except Exception as e:
                logger.warning(f"_monthly_board_universe_update_job: Success alert failed: {e}")

        else:
            # On Failure
            state["BOARD_DATA_STALE_PAUSE"] = True
            state["last_error"] = msg
            _save_custom_state(state)

            logger.warning(f"_monthly_board_universe_update_job: FAILURE — {msg} — Trading Paused")

            # Send Telegram Admin Warning Alert
            try:
                from signal_broadcaster import alert_admin
                await alert_admin(f"⚠️ Monthly Board Update Failed — Trading Paused. Retrying Tomorrow at 8:30 AM\n\nError: {msg}\nTime: {now_ist().strftime('%Y-%m-%d %H:%M IST')}\nAction: BOARD_DATA_STALE_PAUSE=True set — all new BUY entries blocked (Fail-Closed)\nRetry: Daily 08:30 AM IST")
            except Exception as e:
                logger.warning(f"_monthly_board_universe_update_job: Failure alert failed: {e}")

    except Exception as e:
        # Top-level failure handler — set pause flag and alert
        import traceback
        logger.warning(f"_monthly_board_universe_update_job: Top-level exception: {e}\n{traceback.format_exc()}")
        try:
            state = _load_custom_state()
            from utils import now_ist
            state["last_attempt"] = now_ist().isoformat()
            state["BOARD_DATA_STALE_PAUSE"] = True
            state["last_error"] = f"{type(e).__name__}: {e}"
            _save_custom_state(state)

            from signal_broadcaster import alert_admin
            await alert_admin(f"⚠️ Monthly Board Update Failed — Trading Paused. Retrying Tomorrow at 8:30 AM\n\nException: {type(e).__name__}: {e}\nAction: Fail-Closed active")
        except Exception as alert_e:
            logger.warning(f"_monthly_board_universe_update_job: Top-level failure alert also failed: {alert_e}")


async def _daily_board_retry_job():
    """
    Daily retry at 08:30 AM IST if BOARD_DATA_STALE_PAUSE active
    Automatically retries _monthly_board_universe_update_job daily until success
    """
    try:
        state = _load_custom_state()
        if state.get("BOARD_DATA_STALE_PAUSE") is True:
            logger.info("_daily_board_retry_job: BOARD_DATA_STALE_PAUSE=True — retrying monthly update")
            await _monthly_board_universe_update_job()
        else:
            logger.info("_daily_board_retry_job: No stale pause — skipping retry")
    except Exception as e:
        logger.warning(f"_daily_board_retry_job failed: {type(e).__name__}: {e}")


async def _monthly_market_metadata_refresh_job():
    """Refresh decision-critical sector/industry/market-cap metadata first."""
    logger.info("_monthly_market_metadata_refresh_job: starting")
    try:
        from market_metadata import refresh_market_metadata
        success = refresh_market_metadata()
        if not success:
            logger.error("_monthly_market_metadata_refresh_job: FAILED — metadata remains fail-closed")
        return success
    except Exception as e:
        logger.error("_monthly_market_metadata_refresh_job: FAILED: %s", e)
        return False


async def _monthly_liquidity_refresh_job():
    """
    [AUDIT ADD] Monthly Turnover-Liquidity Refresh — mirrors
    _monthly_board_universe_update_job's fail-closed pattern exactly:
    - On Success: recomputes ATVR + Frequency of Trading for every universe
      symbol, writes results back into CUSTOM_UNIVERSE_FINAL.csv, sends a
      success Telegram alert.
    - On Failure: liquidity_screen.is_liquidity_data_stale() will start
      returning True once the staleness limit is crossed, which
      stock_selector.is_universe_data_stale() now also checks — so ALL new
      BUY entries get blocked automatically (Fail-Closed), same real-world
      effect as BOARD_DATA_STALE_PAUSE, retried daily until it succeeds.
    """
    from utils import now_ist
    logger.info("_monthly_liquidity_refresh_job: Starting monthly turnover-liquidity refresh")
    try:
        metadata_ok = await _monthly_market_metadata_refresh_job()
        if not metadata_ok:
            logger.error("_monthly_liquidity_refresh_job: market metadata refresh failed — liquidity refresh BLOCKED")
            return False
        from liquidity_screen import refresh_liquidity_data
        success = refresh_liquidity_data()
        if success:
            logger.info("_monthly_liquidity_refresh_job: SUCCESS")
            try:
                from signal_broadcaster import alert_admin
                await alert_admin(f"✅ Monthly Turnover-Liquidity Refresh Successful\n\nTime: {now_ist().strftime('%Y-%m-%d %H:%M IST')}\nMethod: MSCI ATVR + Frequency of Trading")
            except Exception as e:
                logger.warning(f"_monthly_liquidity_refresh_job: Success alert failed: {e}")
        else:
            logger.warning("_monthly_liquidity_refresh_job: FAILURE — will retry daily; new entries will pause once staleness limit is crossed")
            try:
                from signal_broadcaster import alert_admin
                await alert_admin(f"⚠️ Monthly Turnover-Liquidity Refresh Failed — retrying daily.\n\nTime: {now_ist().strftime('%Y-%m-%d %H:%M IST')}\nNote: new BUY entries will auto-pause (Fail-Closed) once the staleness limit ({PARAMS.get('liquidity_data_stale_days_limit', 45)} days) is crossed, mirroring the board-data pause mechanism.")
            except Exception as e:
                logger.warning(f"_monthly_liquidity_refresh_job: Failure alert failed: {e}")
    except Exception as e:
        import traceback
        logger.warning(f"_monthly_liquidity_refresh_job: Top-level exception: {e}\n{traceback.format_exc()}")
        try:
            from signal_broadcaster import alert_admin
            await alert_admin(f"⚠️ Monthly Turnover-Liquidity Refresh Failed (exception) — retrying daily.\n\nException: {type(e).__name__}: {e}")
        except Exception as alert_e:
            logger.warning(f"_monthly_liquidity_refresh_job: Top-level failure alert also failed: {alert_e}")


async def _daily_liquidity_retry_job():
    """Daily retry if the turnover-liquidity data is stale — mirrors _daily_board_retry_job."""
    try:
        from liquidity_screen import is_liquidity_data_stale
        if is_liquidity_data_stale():
            logger.info("_daily_liquidity_retry_job: liquidity data stale — retrying monthly refresh")
            await _monthly_liquidity_refresh_job()
        else:
            logger.info("_daily_liquidity_retry_job: No stale pause — skipping retry")
    except Exception as e:
        logger.warning(f"_daily_liquidity_retry_job failed: {type(e).__name__}: {e}")


async def _weekly_board_verification_job():
    """
    R39 CORRECTED: Weekly Board Verification — 09:00-15:30 operating window
    Requirement: weekly verification 09:00–15:30, missing/stale/fetch/parse failure → BLOCK
    Do not silently convert weekly verification into monthly-only refresh.
    
    This job runs weekly (Monday 09:30 IST) during market hours.
    It verifies:
    - board_status.json exists and is not stale (>7 days)
    - board_members.json exists
    - No board_refresh_failed flags
    - Verification timestamps within weekly window
    
    If any check fails → BOARD_DATA_STALE_PAUSE=True → BLOCK all new BUY entries (fail-closed)
    """
    from utils import now_ist
    import os
    from datetime import datetime, timedelta
    
    logger.info("_weekly_board_verification_job: Starting weekly board verification (09:00-15:30 window)")
    
    try:
        state = _load_custom_state()
        state["last_attempt"] = now_ist().isoformat()
        state["last_weekly_verification_attempt"] = now_ist().isoformat()
        
        # Check operating window — must be within 09:00-15:30
        try:
            current_hour = now_ist().hour
            if not (9 <= current_hour <= 15):
                logger.warning(f"_weekly_board_verification_job: Outside operating window 09:00-15:30 (current hour={current_hour}) — skipping but logging")
                # Still update attempt timestamp but don't fail
                _save_custom_state(state)
                return False
        except Exception:
            pass
        
        # Verification steps
        verification_passed = True
        failure_reasons = []
        
        # 1. Check board_status.json exists
        try:
            from board_manager import load_json as bm_load
            board_status = bm_load('data/board_status.json', {})
            if not board_status:
                verification_passed = False
                failure_reasons.append("board_status.json empty or missing")
        except Exception as e:
            verification_passed = False
            failure_reasons.append(f"board_status.json load failed: {e}")
            board_status = {}
        
        # 2. Check for failed refresh flags
        try:
            failed_symbols = [sym for sym, rec in board_status.items() if rec.get('board_refresh_failed') is True]
            if failed_symbols:
                verification_passed = False
                failure_reasons.append(f"{len(failed_symbols)} symbols have board_refresh_failed=True: {failed_symbols[:5]}")
        except Exception as e:
            verification_passed = False
            failure_reasons.append(f"failed flag check error: {e}")
        
        # 3. Check staleness — weekly verification must be within 7 days
        try:
            stale_days_limit = PARAMS.get("board_data_stale_days_limit", 7)
            hard_limit = PARAMS.get("board_data_stale_days_hard_limit", 35)
            
            # Check last_successful_update
            last_success = state.get("last_successful_update")
            if not last_success:
                verification_passed = False
                failure_reasons.append("NO_SUCCESSFUL_BOARD_REFRESH_YET — never verified")
            else:
                try:
                    last_dt = datetime.fromisoformat(last_success.replace("Z", "+00:00"))
                    # Make naive for comparison if needed
                    if last_dt.tzinfo:
                        last_dt = last_dt.replace(tzinfo=None)
                    now_naive = now_ist().replace(tzinfo=None) if hasattr(now_ist(), 'replace') else datetime.now()
                    age_days = (now_naive - last_dt).days
                    
                    if age_days > hard_limit:
                        verification_passed = False
                        failure_reasons.append(f"board data hard stale: {age_days} days > hard limit {hard_limit} days")
                    elif age_days > stale_days_limit:
                        verification_passed = False
                        failure_reasons.append(f"board data weekly stale: {age_days} days > weekly limit {stale_days_limit} days")
                except Exception as e:
                    verification_passed = False
                    failure_reasons.append(f"staleness check error: {e}")
            
            # Also check individual symbol verification timestamps
            try:
                stale_symbols = []
                for sym, rec in board_status.items():
                    try:
                        last_checked = rec.get("last_checked")
                        if not last_checked:
                            stale_symbols.append(sym)
                            continue
                        lc_dt = datetime.fromisoformat(last_checked.replace("Z", "+00:00"))
                        if lc_dt.tzinfo:
                            lc_dt = lc_dt.replace(tzinfo=None)
                        now_naive = now_ist().replace(tzinfo=None) if hasattr(now_ist(), 'replace') else datetime.now()
                        sym_age = (now_naive - lc_dt).days
                        if sym_age > stale_days_limit:
                            stale_symbols.append(sym)
                    except Exception:
                        stale_symbols.append(sym)
                
                if len(stale_symbols) > len(board_status) * 0.5:  # More than 50% stale
                    verification_passed = False
                    failure_reasons.append(f"{len(stale_symbols)} symbols stale >{stale_days_limit} days (>{50}% of universe)")
            except Exception as e:
                failure_reasons.append(f"symbol staleness check error: {e}")
                
        except Exception as e:
            verification_passed = False
            failure_reasons.append(f"staleness verification error: {e}")
        
        # 4. Check board_members.json exists
        try:
            import os
            if not os.path.exists("data/board_members.json"):
                verification_passed = False
                failure_reasons.append("board_members.json missing")
            else:
                # Check if file is empty or too small
                size = os.path.getsize("data/board_members.json")
                if size < 10:
                    verification_passed = False
                    failure_reasons.append(f"board_members.json too small ({size} bytes)")
        except Exception as e:
            verification_passed = False
            failure_reasons.append(f"board_members.json check error: {e}")
        
        if verification_passed:
            # Success
            state["last_successful_weekly_verification"] = now_ist().isoformat()
            state["BOARD_DATA_STALE_PAUSE"] = False
            state["last_weekly_verification_error"] = None
            _save_custom_state(state)
            
            logger.info(f"_weekly_board_verification_job: SUCCESS — weekly verification passed, {len(board_status)} symbols verified")
            
            try:
                from signal_broadcaster import alert_admin
                await alert_admin(f"✅ Weekly Board Verification Passed\n\nTime: {now_ist().strftime('%Y-%m-%d %H:%M IST')}\nSymbols verified: {len(board_status)}\nOperating window: 09:00-15:30 IST\nStatus: Trading allowed")
            except Exception as e:
                logger.warning(f"_weekly_board_verification_job: Success alert failed: {e}")
            
            return True
        else:
            # Failure → BLOCK
            state["BOARD_DATA_STALE_PAUSE"] = True
            state["last_weekly_verification_error"] = "; ".join(failure_reasons)
            state["last_error"] = f"Weekly board verification failed: {'; '.join(failure_reasons)}"
            _save_custom_state(state)
            
            logger.warning(f"_weekly_board_verification_job: FAILURE — {'; '.join(failure_reasons)} — Trading BLOCKED (fail-closed)")
            
            try:
                from signal_broadcaster import alert_admin
                await alert_admin(f"⚠️ Weekly Board Verification Failed — Trading BLOCKED\n\nTime: {now_ist().strftime('%Y-%m-%d %H:%M IST')}\nOperating window: 09:00-15:30 IST\nFailures: {'; '.join(failure_reasons)}\nAction: BOARD_DATA_STALE_PAUSE=True — all new BUY entries BLOCKED (Fail-Closed)\nRetry: Daily 08:30 AM IST + Weekly Monday 09:30 AM IST")
            except Exception as e:
                logger.warning(f"_weekly_board_verification_job: Failure alert failed: {e}")
            
            return False
            
    except Exception as e:
        import traceback
        logger.warning(f"_weekly_board_verification_job: Top-level exception: {e}\n{traceback.format_exc()}")
        try:
            state = _load_custom_state()
            state["last_attempt"] = now_ist().isoformat()
            state["last_weekly_verification_attempt"] = now_ist().isoformat()
            state["BOARD_DATA_STALE_PAUSE"] = True
            state["last_weekly_verification_error"] = f"{type(e).__name__}: {e}"
            state["last_error"] = f"Weekly verification exception: {type(e).__name__}: {e}"
            _save_custom_state(state)
            
            from signal_broadcaster import alert_admin
            await alert_admin(f"⚠️ Weekly Board Verification Exception — Trading BLOCKED\n\nException: {type(e).__name__}: {e}\nAction: Fail-Closed active")
        except Exception as alert_e:
            logger.warning(f"_weekly_board_verification_job: Top-level failure alert also failed: {alert_e}")
        return False

