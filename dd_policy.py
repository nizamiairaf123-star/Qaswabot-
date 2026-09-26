"""
dd_policy.py — PHASE-3 PATCH (ADD-ONLY): machine-proposed DD constants
              within OWNER HARD CAPS.

User directive: "constants bhi machine decide kare, LAKIN industry-based
verified method hona chahiye" — yahan har value named-method se aati hai,
aur owner policy caps ke bahar kabhi nahi ja sakti (fail-safe structure).
Data insufficient → return None → caller EXISTING constants use karta hai
(exact old behavior fallback — kuch break nahi hota).

METHOD ATTRIBUTIONS (user rule: har update ke aage method + creator):
  - Tier multipliers (soft/hard)  → Quantile mapping of own loss distribution
                                    [Value-at-Risk framework — JP Morgan RiskMetrics, 1994]
  - DD buffer                     → Estimation error of backtest DD
                                    [Bootstrap resampling — Bradley Efron, 1979]
  - Recovery days (re-entry wait) → Measured median recovery-days from the
                                    stock's OWN price history [custom/owner-designed
                                    measurement on standard High-Watermark DD metric;
                                    watermark concept = fund/CTA industry standard]
  - Hard caps themselves          → OWNER POLICY (constitution) — machine propose,
                                    caps validate. [Prop-firm convention already cited
                                    in config.py:103 — alphaexcapital 3-7% range]
  - Hard-floor design principle   → Hard-coded automated stops that nothing
                                    can override: SEC Rule 15c3-5 "Market Access Rule"
                                    (Nov 2010); Knight Capital enforcement (2013);
                                    MiFID II Article 17 (kill-switch requirement)
  - Re-entry confirmation window  → Multi-day confirmation before re-entry:
                                    Follow-Through Day — William J. O'Neil
                                    ("How to Make Money in Stocks", 1988; 4–7 din window)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ── OWNER HARD CAPS (policy — machine inke BAHAR propose nahi kar sakta) ──
TIER_SOFT_RANGE = (0.40, 0.60)   # "half of limit" prop convention window (pickmytrade cited in config:104)
TIER_HARD_RANGE = (0.70, 0.90)   # tiered escalation convention (Fed sra2401 cited in config:105)
BUFFER_PCT_FLOOR = 2.0           # existing 2% = floor (kabhi isse kam nahi)
BUFFER_PCT_CAP = 5.0
RECOVERY_DAYS_FLOOR = 5          # existing 5 = floor
RECOVERY_DAYS_CAP = 20
MIN_OBS = 60                     # is se kam data → propose NAHI (fallback)


# ── data helper (warehouse first, phir Dhan; dono fail → None) ──
def _daily_closes(symbol: str, days: int = 1825) -> pd.Series:
    try:
        from mtf import warehouse
        df = warehouse.load_bars(symbol, "1D")
        if not df.empty:
            return df["close"]
    except Exception:
        pass
    try:
        from dhan_data import fetch_daily_data
        df = fetch_daily_data(symbol, days=days)
        if df is not None and len(df):
            return df["close"]
    except Exception:
        pass
    return pd.Series(dtype=float)


def _daily_losses(symbol: str) -> np.ndarray:
    """Negative daily close-to-close returns (positive magnitudes %)."""
    c = _daily_closes(symbol)
    if len(c) < MIN_OBS:
        return np.array([])
    r = c.pct_change().dropna() * 100.0
    losses = (-r[r < 0]).values
    return losses if len(losses) >= MIN_OBS // 2 else np.array([])


# ── 1) Tier multipliers [VaR quantile mapping — JP Morgan RiskMetrics, 1994] ──
def _pooled_daily_losses(max_symbols: int = 40) -> np.ndarray:
    """Portfolio-level: universe ke symbols ke bad-day losses pool (warehouse se)."""
    try:
        from mtf import warehouse
        meta = warehouse.warehouse_status()
        syms = sorted({k.split(":")[0] for k in meta if k.endswith(":1D")})
        pool = []
        for s in syms[:max_symbols]:
            pool.extend(_daily_losses(s).tolist())
        return np.array(pool)
    except Exception:
        return np.array([])


def suggested_tier_multipliers(symbol: str = None):
    """
    Bad-day loss distribution se tier RATIOS (symbol diya to us stock ka,
    warna PORTFOLIO pooled universe):
      soft-ratio = P75(loss)/P99(loss), hard-ratio = P90(loss)/P99(loss)
    (99th percentile = 'circuit' bad day; uske andar soft/hard zone map)
    Ratios owner windows me clip. Data na ho → None (fallback old 0.50/0.75).
    """
    losses = _daily_losses(symbol) if symbol else _pooled_daily_losses()
    if len(losses) == 0:
        return None
    p75, p90, p99 = np.percentile(losses, [75, 90, 99])
    if p99 <= 0:
        return None
    soft = float(np.clip(p75 / p99, *TIER_SOFT_RANGE))
    hard = float(np.clip(p90 / p99, *TIER_HARD_RANGE))
    return {"soft_mult": round(soft, 3), "hard_mult": round(hard, 3),
            "method": "VaR quantile mapping — JP Morgan RiskMetrics, 1994",
            "obs": int(len(losses))}


# ── 2) DD buffer [Bootstrap estimation error — Bradley Efron, 1979] ──
def suggested_buffer_pct(symbol: str, n_boot: int = 1000, seed: int = 7):
    """
    Backtest-DW ke aas-paas uncertainty = bootstrap resampled daily returns se:
      buffer = 95th pct of |boot_max_dd − observed_max_dd| (estimation error)
    Floor/cap policy se. Data na ho → None (fallback old 2%).
    """
    c = _daily_closes(symbol)
    if len(c) < MIN_OBS:
        return None
    r = c.pct_change().dropna().values
    if len(r) < MIN_OBS:
        return None

    def max_dd(x):
        eq = np.cumprod(1 + x)
        peak = np.maximum.accumulate(eq)
        return float(((eq - peak) / peak).min())

    obs_dd = max_dd(r)
    rng = np.random.default_rng(seed)
    errs = []
    for _ in range(n_boot):
        sample = rng.choice(r, size=len(r), replace=True)
        errs.append(abs(max_dd(sample) - obs_dd))
    buf = float(np.percentile(errs, 95) * 100.0)
    buf = float(np.clip(buf, BUFFER_PCT_FLOOR, BUFFER_PCT_CAP))
    return {"buffer_pct": round(buf, 2),
            "method": "Bootstrap DD estimation-error — B. Efron, 1979",
            "obs_dd_pct": round(abs(obs_dd) * 100, 2)}


# ── 3) Recovery days [custom measurement on standard watermark metric] ──
def suggested_recovery_days(symbol: str, dd_threshold_pct: float = None):
    """
    Stock ke apne HISTORY me: price (wm − dd%) ke neeche gira → kitne din me
    us level ko reclaim kiya? Median of those recovery-durations.
    Floor/cap policy se. Data na ho → None (fallback old 5).
    Watermark DD = industry-standard metric (fund/CTA standard, no single creator);
    measurement rule = custom/owner-designed (honestly marked).
    """
    c = _daily_closes(symbol)
    if len(c) < MIN_OBS:
        return None
    if dd_threshold_pct is None:
        # us stock ka apna backtest DD (existing source, author convention)
        try:
            from stock_mode_manager import _get_backtest_dd
            bd = _get_backtest_dd(symbol)
            dd_threshold_pct = abs(bd) if bd is not None else None
        except Exception:
            dd_threshold_pct = None
    if not dd_threshold_pct or dd_threshold_pct <= 0:
        return None

    closes = c.values
    wm = closes[0]
    recoveries, in_dip, dip_start = [], False, 0
    level = None
    for i, p in enumerate(closes[1:], 1):
        if p > wm:
            wm = p
            if in_dip and level is not None and p >= level:
                recoveries.append(i - dip_start)
                in_dip = False
            continue
        level = wm * (1 - dd_threshold_pct / 100.0)
        if not in_dip and p < level:
            in_dip, dip_start = True, i
        elif in_dip and p >= level:
            recoveries.append(i - dip_start)
            in_dip = False
    if not recoveries:
        return None
    days = float(np.median(recoveries))
    days = float(np.clip(days, RECOVERY_DAYS_FLOOR, RECOVERY_DAYS_CAP))
    return {"recovery_days": int(days),
            "method": "median historical recovery-days (custom measurement; "
                      "watermark metric = fund/CTA industry standard)",
            "events": int(len(recoveries))}
