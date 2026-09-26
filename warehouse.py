"""
mtf/warehouse.py — Local candle warehouse (Parquet) for Phase-2 + Phase 5 Alternative Bars.

[Method: local data warehouse + incremental top-up — institutional quant practice;
         data hygiene discipline per Robert Pardo, 2008]
[Method: Final Untouched Holdout — institutional Model Risk Management practice]
[Method: Volume & Dollar Bars — Marcos Lopez de Prado, Advances in Financial ML Ch 2]

Layout (ADD-ONLY — data/ ke andar naya sub-dir, kuch overwrite nahi):
    data/mtf_warehouse/<SYMBOL>/<tf>.parquet          ← train+val region (time bars)
    data/mtf_warehouse/<SYMBOL>/holdout/<tf>.parquet  ← final 20% (untouched)
    data/mtf_warehouse/<SYMBOL>/<tf>_vol.parquet      ← volume bars (Phase 5)
    data/mtf_warehouse/<SYMBOL>/<tf>_dollar.parquet   ← dollar bars (Phase 5)
    data/mtf_warehouse/_meta.json                     ← per-symbol/TF last-candle info

Daily top-up = sirf naye candles append (dedupe by timestamp) → ~580 calls/2-3 min.

Phase 5: Volume & Dollar Bars — dynamic bar sampling based on volume/rupee turnover
         rather than fixed clock time. Normalizes volatility clusters, restores
         closer-to-Gaussian return distributions. Optional configurable mode
         alongside standard 5m/15m time bars.
"""

from __future__ import annotations

import os
import pandas as pd

from config import MTF_WAREHOUSE_DIR, MTF_HOLDOUT_FRACTION
from utils import load_json, save_json, append_log
from mtf.derive import normalize_ohlcv

AUDIT = f"{MTF_WAREHOUSE_DIR}/../audit_log.txt"  # data/audit_log.txt (existing convention)
_META_FILE = "_meta.json"


def _base_dir() -> str:
    os.makedirs(MTF_WAREHOUSE_DIR, exist_ok=True)
    return MTF_WAREHOUSE_DIR


def _path(symbol: str, tf: str, holdout: bool = False) -> str:
    sym = symbol.upper().replace("/", "_")
    if holdout:
        return os.path.join(_base_dir(), sym, "holdout", f"{tf}.parquet")
    return os.path.join(_base_dir(), sym, f"{tf}.parquet")


def _meta() -> dict:
    return load_json(os.path.join(_base_dir(), _META_FILE), {})


def _touch_meta(symbol: str, tf: str, df: pd.DataFrame, holdout: bool):
    m = _meta()
    key = f"{symbol.upper()}:{tf}{':holdout' if holdout else ''}"
    m[key] = {
        "rows": int(len(df)),
        "first": str(df.index.min()) if len(df) else None,
        "last": str(df.index.max()) if len(df) else None,
    }
    save_json(os.path.join(_base_dir(), _META_FILE), m)


def save_bars(symbol: str, tf: str, df: pd.DataFrame, holdout: bool = False) -> str:
    """Full overwrite save (initial bulk load ke liye). Top-up ke liye top_up() use karo."""
    d = normalize_ohlcv(df)
    p = _path(symbol, tf, holdout)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    d.to_parquet(p, engine="pyarrow", index=True)
    _touch_meta(symbol, tf, d, holdout)
    return p


def load_bars(symbol: str, tf: str, start=None, end=None, holdout: bool = False) -> pd.DataFrame:
    """Warehouse se candles. File na ho to EMPTY df (fail-soft; caller decide kare)."""
    p = _path(symbol, tf, holdout)
    if not os.path.exists(p):
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    d = pd.read_parquet(p, engine="pyarrow")
    d = normalize_ohlcv(d)
    if start is not None:
        d = d.loc[d.index >= pd.Timestamp(start)]
    if end is not None:
        d = d.loc[d.index <= pd.Timestamp(end)]
    return d


def top_up(symbol: str, tf: str, df_new: pd.DataFrame, holdout: bool = False) -> dict:
    """
    Incremental append + dedupe by timestamp (idempotent — dobara chalane pe double rows nahi).
    Returns {added, total}.
    """
    old = load_bars(symbol, tf, holdout=holdout)
    new = normalize_ohlcv(df_new)
    if new.empty:
        return {"added": 0, "total": len(old)}
    if old.empty:
        merged = new
    else:
        merged = pd.concat([old, new])
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
    added = int(len(merged) - len(old))
    p = _path(symbol, tf, holdout)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    merged.to_parquet(p, engine="pyarrow", index=True)
    _touch_meta(symbol, tf, merged, holdout)
    try:
        append_log(os.path.join(_base_dir(), "warehouse_log.txt"),
                   f"TOPUP {symbol} {tf}{' holdout' if holdout else ''}: +{added} rows (total {len(merged)})")
    except Exception:
        pass  # logging kabhi top-up ko fail nahi karegi
    return {"added": added, "total": len(merged)}


def split_train_holdout(df: pd.DataFrame, fraction: float = None):
    """
    Chronological split: pehle (1-fraction) = train/val, aakhri fraction = holdout.
    [PIT standard] shuffle NAHI — time order preserved, warna lookahead aa jata.
    """
    frac = MTF_HOLDOUT_FRACTION if fraction is None else float(fraction)
    d = normalize_ohlcv(df)
    n = len(d)
    cut = int(n * (1 - frac))
    return d.iloc[:cut].copy(), d.iloc[cut:].copy()


def materialize_train_holdout(symbol: str, tf: str, df: pd.DataFrame) -> dict:
    """Bulk df ko train+holdout files me likhta hai (initial load ke waqt)."""
    train, holdout = split_train_holdout(df)
    save_bars(symbol, tf, train, holdout=False)
    save_bars(symbol, tf, holdout, holdout=True)
    return {"train": len(train), "holdout": len(holdout)}


def last_timestamp(symbol: str, tf: str, holdout: bool = False):
    m = _meta().get(f"{symbol.upper()}:{tf}{':holdout' if holdout else ''}")
    return (m or {}).get("last")


def warehouse_status() -> dict:
    """Admin /mtfstatus ke liye: sab files ka rows/span summary."""
    return _meta()


# ─────────────────────────────────────────────
# Phase 5: Alternative Information Bars — Volume & Dollar Bars
# Lopez de Prado Ch 2: Sampling by volume/dollar normalizes volatility,
# restores Gaussian returns vs time bars which cluster volatility
# ─────────────────────────────────────────────

def create_volume_bars(df: pd.DataFrame, volume_threshold: float) -> pd.DataFrame:
    """
    Create volume bars: each bar accumulates fixed volume threshold.

    Args:
        df: OHLCV DataFrame with datetime index, columns open/high/low/close/volume
        volume_threshold: volume to accumulate per bar (e.g., avg daily volume / 10)

    Returns:
        DataFrame of volume bars with same OHLCV columns, index = last timestamp in bar

    Example:
        Time bars: 09:15-09:20 volume 10k, 09:20-09:25 volume 50k (news) → volatility cluster
        Volume bars: each bar 20k volume → news period creates 2-3 bars, normal period 1 bar
        → volatility normalized, returns more Gaussian
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = df.sort_index()
    if "volume" not in df.columns:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    bars = []
    cum_vol = 0.0
    bar_open = None
    bar_high = -float("inf")
    bar_low = float("inf")
    bar_start_idx = 0

    for i in range(len(df)):
        row = df.iloc[i]
        vol = float(row.get("volume", 0) or 0)
        if bar_open is None:
            bar_open = float(row.get("open", row.get("close", 0)))

        bar_high = max(bar_high, float(row.get("high", 0) or 0))
        bar_low = min(bar_low, float(row.get("low", 0) or 0))
        cum_vol += vol

        if cum_vol >= volume_threshold:
            # Close bar
            bar_close = float(row.get("close", 0))
            bar_timestamp = df.index[i]
            bars.append({
                "timestamp": bar_timestamp,
                "open": bar_open,
                "high": bar_high,
                "low": bar_low,
                "close": bar_close,
                "volume": cum_vol,
            })
            # Reset
            cum_vol = 0.0
            bar_open = None
            bar_high = -float("inf")
            bar_low = float("inf")
            bar_start_idx = i + 1

    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    vol_df = pd.DataFrame(bars)
    vol_df.set_index("timestamp", inplace=True)
    vol_df.index = pd.to_datetime(vol_df.index)
    return vol_df


def create_dollar_bars(df: pd.DataFrame, dollar_threshold: float) -> pd.DataFrame:
    """
    Create dollar bars: each bar accumulates fixed dollar/rupee turnover threshold.

    Dollar turnover = close * volume (rupee value traded)

    Args:
        df: OHLCV DataFrame
        dollar_threshold: rupee turnover per bar (e.g., avg daily turnover / 10)

    Returns:
        DataFrame of dollar bars

    Why better than time bars?
      - Time bars: volatile period (high volume + high price move) compresses info into few bars
      - Dollar bars: volatile period creates more bars (more information sampled)
      - Returns distribution closer to Gaussian, better for ML/statistics
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "dollar_volume"])

    df = df.sort_index()
    if "volume" not in df.columns or "close" not in df.columns:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "dollar_volume"])

    bars = []
    cum_dollar = 0.0
    cum_vol = 0.0
    bar_open = None
    bar_high = -float("inf")
    bar_low = float("inf")

    for i in range(len(df)):
        row = df.iloc[i]
        close = float(row.get("close", 0) or 0)
        vol = float(row.get("volume", 0) or 0)
        dollar_vol = close * vol

        if bar_open is None:
            bar_open = float(row.get("open", close))

        bar_high = max(bar_high, float(row.get("high", 0) or 0))
        bar_low = min(bar_low, float(row.get("low", 0) or 0))
        cum_dollar += dollar_vol
        cum_vol += vol

        if cum_dollar >= dollar_threshold:
            bar_close = close
            bar_timestamp = df.index[i]
            bars.append({
                "timestamp": bar_timestamp,
                "open": bar_open,
                "high": bar_high,
                "low": bar_low,
                "close": bar_close,
                "volume": cum_vol,
                "dollar_volume": cum_dollar,
            })
            cum_dollar = 0.0
            cum_vol = 0.0
            bar_open = None
            bar_high = -float("inf")
            bar_low = float("inf")

    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "dollar_volume"])

    dollar_df = pd.DataFrame(bars)
    dollar_df.set_index("timestamp", inplace=True)
    dollar_df.index = pd.to_datetime(dollar_df.index)
    return dollar_df


def estimate_volume_threshold(df: pd.DataFrame, daily_avg_bars: int = 10) -> float:
    """
    Estimate volume threshold to get ~daily_avg_bars volume bars per day.
    E.g., if avg daily volume is 1M, and we want 10 bars per day, threshold = 100k
    """
    if df is None or df.empty or "volume" not in df.columns:
        return 100000.0  # default

    try:
        # Group by date and sum volume
        df_copy = df.copy()
        df_copy["date"] = pd.to_datetime(df_copy.index).date
        daily_vol = df_copy.groupby("date")["volume"].sum()
        avg_daily_vol = float(daily_vol.mean())
        if avg_daily_vol <= 0:
            return 100000.0
        return avg_daily_vol / daily_avg_bars
    except Exception:
        return 100000.0


def estimate_dollar_threshold(df: pd.DataFrame, daily_avg_bars: int = 10) -> float:
    """
    Estimate dollar threshold to get ~daily_avg_bars dollar bars per day.
    Dollar = close * volume
    """
    if df is None or df.empty or "volume" not in df.columns or "close" not in df.columns:
        return 10000000.0  # 1 Cr default

    try:
        df_copy = df.copy()
        df_copy["dollar"] = df_copy["close"] * df_copy["volume"]
        df_copy["date"] = pd.to_datetime(df_copy.index).date
        daily_dollar = df_copy.groupby("date")["dollar"].sum()
        avg_daily_dollar = float(daily_dollar.mean())
        if avg_daily_dollar <= 0:
            return 10000000.0
        return avg_daily_dollar / daily_avg_bars
    except Exception:
        return 10000000.0


def convert_time_to_volume_bars(symbol: str, tf: str = "5m", daily_avg_bars: int = 10) -> dict:
    """
    Converts existing time bars in warehouse to volume bars.
    Saves to <symbol>/<tf>_vol.parquet

    Returns stats dict
    """
    try:
        df = load_bars(symbol, tf, holdout=False)
        if df.empty:
            return {"symbol": symbol, "tf": tf, "status": "no time bars", "volume_bars": 0}

        thresh = estimate_volume_threshold(df, daily_avg_bars=daily_avg_bars)
        vol_bars = create_volume_bars(df, volume_threshold=thresh)

        if vol_bars.empty:
            return {"symbol": symbol, "tf": tf, "status": "no volume bars generated", "volume_bars": 0, "threshold": thresh}

        # Save
        path = _path(symbol, f"{tf}_vol", holdout=False)
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        vol_bars.to_parquet(path, engine="pyarrow", index=True)

        return {
            "symbol": symbol,
            "tf": tf,
            "time_bars": len(df),
            "volume_bars": len(vol_bars),
            "threshold": thresh,
            "path": path,
            "status": "ok",
        }
    except Exception as e:
        return {"symbol": symbol, "tf": tf, "status": f"error: {type(e).__name__}: {e}", "volume_bars": 0}


def convert_time_to_dollar_bars(symbol: str, tf: str = "5m", daily_avg_bars: int = 10) -> dict:
    """
    Converts time bars to dollar bars.
    Saves to <symbol>/<tf>_dollar.parquet
    """
    try:
        df = load_bars(symbol, tf, holdout=False)
        if df.empty:
            return {"symbol": symbol, "tf": tf, "status": "no time bars", "dollar_bars": 0}

        thresh = estimate_dollar_threshold(df, daily_avg_bars=daily_avg_bars)
        dollar_bars = create_dollar_bars(df, dollar_threshold=thresh)

        if dollar_bars.empty:
            return {"symbol": symbol, "tf": tf, "status": "no dollar bars", "dollar_bars": 0, "threshold": thresh}

        path = _path(symbol, f"{tf}_dollar", holdout=False)
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        dollar_bars.to_parquet(path, engine="pyarrow", index=True)

        return {
            "symbol": symbol,
            "tf": tf,
            "time_bars": len(df),
            "dollar_bars": len(dollar_bars),
            "threshold": thresh,
            "path": path,
            "status": "ok",
        }
    except Exception as e:
        return {"symbol": symbol, "tf": tf, "status": f"error: {type(e).__name__}: {e}", "dollar_bars": 0}
