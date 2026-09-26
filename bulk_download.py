"""
mtf/bulk_download.py — Warehouse ko Dhan se bharna (Phase-2 P1/P4, ADD-ONLY).

Modes:
  1) INITIAL bulk load  → eligible stocks × download-TFs, sy 2–5 hrs (rate-limit friendly)
       python3 -m mtf.bulk_download --initial
       python3 -m mtf.bulk_download --initial --symbols RELIANCE,TCS
  2) DAILY top-up       → sirf naye candles (~eligible×4 = ~580 calls, 2–3 min)
       python3 -m mtf.bulk_download --topup   (scheduler bhi yahi call karta hai)

[Custom engineering] — incremental top-up + dedupe (idempotent; dobara chalane
pe double data nahi). [Robert Pardo, 2008: data hygiene discipline]

SAFETY: Ye sirf data READ/save karta hai warehouse me — orders/trading engine se
iska koi lena dena nahi. Existing daily candle fetch ka behavior unchanged rehta hai
(trade_engine apni fresh Dhan call karta hi rahega — design: trade path untouched).
"""

from __future__ import annotations

import sys
import time

from config import MTF_DOWNLOAD_TFS, AUDIT_LOG_FILE
from utils import append_log
from mtf import warehouse
from mtf.timeframes import DHAN_INTERVAL_MAP

# Phase 4 spec-compliant timeframes (per QASWA v6.1 spec)
# Daily 1D: 5 years (1825 days), 15m: 90 days, 5m: 30 days, 60m: 90 days
SPEC_TIMEFRAMES_DAYS = {
    "1D": 1825,   # 5 years for long-term regime, 200 EMA, ATR Wilder
    "15m": 90,    # Rolling 60-90 trading days per spec
    "5m": 30,     # Rolling 30 trading days for precise entry/SL
    "60m": 90,    # 60m also 90 days (derived from 15m but keep same)
    "5": 30,      # Dhan interval mapping: 5 = 5m
    "15": 90,     # Dhan interval mapping: 15 = 15m
    "60": 90,
}

TOPUP_INTRADAY_DAYS = {"5": 7, "15": 10, "60": 15}   # top-up ke liye chhota window
INITIAL_INTRADAY_DAYS = 1825                          # ~5 saal target (probe se confirm) — legacy, use SPEC_TIMEFRAMES_DAYS now


def _log(msg: str):
    print(msg)
    try:
        append_log(f"{warehouse.MTF_WAREHOUSE_DIR}/warehouse_log.txt", msg)
    except Exception:
        pass


def _fetch(symbol: str, tf: str, days: int):
    """Dhan se TF data (download TFs only). Uses existing dhan_data (retry+rate-limit built-in)."""
    from dhan_data import fetch_intraday_data, fetch_daily_data
    if tf == "1D":
        return fetch_daily_data(symbol, days=days)
    interval = DHAN_INTERVAL_MAP.get(tf)
    if interval is None:
        raise ValueError(f"tf {tf} is not a direct-download TF")
    return fetch_intraday_data(symbol, interval=interval, days=days)


def _symbols(symbols=None, use_master: bool = False) -> list:
    if symbols:
        return [s.strip().upper() for s in symbols if s.strip()]
    if use_master:
        # Phase 4: Full 2160 MASTER list for complete coverage
        try:
            import pandas as pd
            from config import DATA_DIR
            import os
            master_path = os.path.join(DATA_DIR, "MASTER_STOCK_LIST_PERMANENT.csv")
            df = pd.read_csv(master_path)
            # Try different column names
            for col in ["symbol", "Symbol", "SYMBOL", "tradingsymbol"]:
                if col in df.columns:
                    return df[col].astype(str).str.upper().tolist()
            # Fallback to first column
            return df.iloc[:, 0].astype(str).str.upper().tolist()
        except Exception as e:
            print(f"MASTER list load failed: {e}, falling back to HALAL")
    from backtester import load_halal_symbols
    return load_halal_symbols()


def run_initial(symbols=None, intraday_days: int = None,
                daily_days: int = None, sleep_sec: float = 1.1,
                use_master: bool = False) -> dict:
    """Initial bulk load. HOLDOUT partition bhi yahin banti hai (20% aakhri).
    
    Phase 4: Supports MASTER 2160 list with spec-compliant timeframes:
      1D: 5 years (1825d), 15m: 90d, 5m: 30d per spec
    """
    stats = {"ok": 0, "fail": 0, "errors": []}
    syms = _symbols(symbols, use_master=use_master)

    # Use spec timeframes if not provided
    if daily_days is None:
        daily_days = SPEC_TIMEFRAMES_DAYS.get("1D", 1825)
    if intraday_days is None:
        # Will be per-TF from SPEC_TIMEFRAMES_DAYS
        pass

    _log(f"INITIAL DOWNLOAD START: {len(syms)} symbols × {MTF_DOWNLOAD_TFS} "
         f"(est. {len(syms)*len(MTF_DOWNLOAD_TFS)} calls, rate ~{sleep_sec}s/call, master={use_master})")
    for sym in syms:
        for tf in MTF_DOWNLOAD_TFS:
            try:
                # Per-TF days per spec
                if tf == "1D":
                    days = daily_days
                else:
                    # Map tf to days: 5m->30, 15m->90, 60m->90
                    days = SPEC_TIMEFRAMES_DAYS.get(tf, intraday_days or 90)
                    # Also check Dhan interval mapping
                    if tf in ["5m", "15m", "60m"]:
                        # Convert to Dhan interval key
                        interval_key = tf.replace("m", "")
                        days = SPEC_TIMEFRAMES_DAYS.get(interval_key, days)

                df = _fetch(sym, tf, days)
                if df is None or len(df) == 0:
                    raise ValueError("empty data")
                res = warehouse.materialize_train_holdout(sym, tf, df)
                _log(f"  OK {sym} {tf}: train={res['train']} holdout={res['holdout']} days={days}")
                stats["ok"] += 1
            except Exception as e:
                stats["fail"] += 1
                stats["errors"].append(f"{sym}:{tf} {type(e).__name__}: {e}")
                _log(f"  FAIL {sym} {tf}: {type(e).__name__}: {e}")
            time.sleep(sleep_sec)  # Dhan rate-limit respect (~1 req/sec)
    _log(f"INITIAL DOWNLOAD DONE: ok={stats['ok']} fail={stats['fail']}")
    return stats


def run_daily_topup(symbols=None, sleep_sec: float = 0.6) -> dict:
    """
    Roz market close ke baad: sirf naye candles append (idempotent dedupe).
    Warehouse NA ho (P1 initial abhi hua hi nahi) → skip silently (zero impact on bot).
    """
    if not warehouse._meta():
        _log("TOPUP SKIP: warehouse empty (initial download abhi nahi hua) — no-op")
        return {"skipped": True}
    stats = {"ok": 0, "fail": 0, "added_total": 0, "errors": []}
    syms = _symbols(symbols)
    _log(f"DAILY TOPUP START: {len(syms)} symbols × {MTF_DOWNLOAD_TFS}")
    for sym in syms:
        for tf in MTF_DOWNLOAD_TFS:
            try:
                days = 10 if tf == "1D" else TOPUP_INTRADAY_DAYS.get(DHAN_INTERVAL_MAP.get(tf, ""), 10)
                df = _fetch(sym, tf, days)
                if df is None or len(df) == 0:
                    raise ValueError("empty data")
                # train region top-up (holdout untouched — wo frozen hai conceptually;
                # quarterly full refresh me hi rebuild hoga)
                r = warehouse.top_up(sym, tf, df, holdout=False)
                stats["added_total"] += r["added"]
                stats["ok"] += 1
            except Exception as e:
                stats["fail"] += 1
                stats["errors"].append(f"{sym}:{tf} {type(e).__name__}: {e}")
            time.sleep(sleep_sec)
    _log(f"DAILY TOPUP DONE: ok={stats['ok']} fail={stats['fail']} added={stats['added_total']} rows")
    try:
        append_log(AUDIT_LOG_FILE, f"MTF WAREHOUSE TOPUP: ok={stats['ok']} fail={stats['fail']} added={stats['added_total']}")
    except Exception:
        pass
    return stats


def main():
    args = sys.argv[1:]
    syms = None
    use_master = "--master" in args
    if "--symbols" in args:
        i = args.index("--symbols")
        syms = args[i + 1].split(",")
    if "--initial" in args:
        run_initial(symbols=syms, use_master=use_master)
    elif "--topup" in args:
        run_daily_topup(symbols=syms)
    else:
        print("Usage: python3 -m mtf.bulk_download --initial [--symbols A,B] [--master] | --topup [--symbols A,B]")
        print("  --master: Use MASTER_STOCK_LIST_PERMANENT.csv (2160) for full coverage per Phase 4 spec")


if __name__ == "__main__":
    main()
