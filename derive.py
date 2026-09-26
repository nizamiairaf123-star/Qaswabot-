"""
mtf/derive.py — Derived timeframes (30m, 2H) from downloaded candles.

[Method: session-anchored resampling — custom engineering, NSE session 09:15–15:30 IST]
Kyun anchored? Standard pandas resample midnight se bucket banata hai → market candles
bigad jaate hain (09:15 open ke bajaye 09:00/09:30 buckets). Hum 09:15 IST se bucket
start karte hain — yahi trading desks ka standard tareeqa hai.

GUARANTEE: sirf naye functions; pandas ke default ko touch nahi karta.
"""

from datetime import time as dtime
import pandas as pd

from config import MTF_ANCHOR_TIME

SESSION_END = dtime(15, 30)          # NSE close
DERIVE_WINDOWS = {"30m": 30, "2H": 120, "15m": 15, "60m": 60}  # target_tf → minutes

REQUIRED_COLS = ["open", "high", "low", "close", "volume"]


def _anchor_today() -> dtime:
    hh, mm = str(MTF_ANCHOR_TIME).split(":")[:2]
    return dtime(int(hh), int(mm))


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """
    TS index + lowercase OHLCV columns me laata hai (Dhan daily/intraday dono shapes se).
    Existing dhan_data._standardize already ye karta hai; yeh defensive copy hai.
    """
    out = df.copy()
    out.columns = [str(c).lower() for c in out.columns]
    if "timestamp" in out.columns:
        out["timestamp"] = pd.to_datetime(out["timestamp"])
        out = out.set_index("timestamp")
    out.index = pd.to_datetime(out.index)
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_convert("Asia/Kolkata").tz_localize(None)
    missing = [c for c in REQUIRED_COLS if c not in out.columns]
    if missing:
        raise ValueError(f"normalize_ohlcv: missing columns {missing}")
    return out.sort_index()


def resample_anchored(df: pd.DataFrame, window_minutes: int) -> pd.DataFrame:
    """
    Intraday candles ko 09:15 IST se anchored bade TF me aggregate karta hai.
    open=first, high=max, low=min, close=last, volume=sum (OHLCV canonical rules).
    Sirf session (09:15–15:30) ke andar ke candles use hote hain; session ke bahar ka
    data (agar ho) exclude hota hai — Sharia CNC bot ke liye session hi relevant hai.
    """
    if df.empty:
        return df.copy()
    d = normalize_ohlcv(df)
    a = _anchor_today()
    start = dtime(a.hour, a.minute)

    t = d.index
    in_session = (t.time >= start) & (t.time <= SESSION_END)
    d = d.loc[in_session]
    if d.empty:
        return d

    anchor = d.index.normalize() + pd.Timedelta(hours=a.hour, minutes=a.minute)
    minutes_since = (d.index - anchor).total_seconds() // 60
    bucket = (minutes_since // window_minutes).astype(int)
    d = d.assign(_date=d.index.date, _bucket=bucket)

    agg = d.groupby(["_date", "_bucket"]).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum"),
    )
    idx = [pd.Timestamp(dt) + pd.Timedelta(hours=a.hour, minutes=a.minute + int(b) * window_minutes)
           for dt, b in agg.index]
    agg.index = pd.DatetimeIndex(idx, name="timestamp")
    return agg.sort_index()


def derive_tf(df: pd.DataFrame, target_tf: str) -> pd.DataFrame:
    """
    Generic entry: kisi bhi chhote TF ke candles se target TF derive karo.
    Dhan chunk-boundary quirks ke baad bhi OHLCV consistent rehta hai (aggregation se).
    """
    if target_tf not in DERIVE_WINDOWS:
        raise ValueError(f"derive_tf: unsupported target_tf={target_tf!r} (allowed: {list(DERIVE_WINDOWS)})")
    return resample_anchored(df, DERIVE_WINDOWS[target_tf])
