"""
sector_strength.py — NSE sector indices strength analysis
Free NSE API se sector data fetch karo
Strong sector = zyada trade, Weak sector = skip
"""

import logging
import requests
from utils import load_json, save_json, now_ist, append_log
from config import AUDIT_LOG_FILE, PARAMS

logger = logging.getLogger(__name__)

SECTOR_DATA_FILE = "data/sector_strength.json"

# NSE sector indices
SECTOR_INDICES = {
    "IT":          "NIFTY IT",
    "Pharma":      "NIFTY PHARMA",
    "Bank":        "NIFTY BANK",
    "Auto":        "NIFTY AUTO",
    "FMCG":        "NIFTY FMCG",
    "Metal":       "NIFTY METAL",
    "Energy":      "NIFTY ENERGY",
    "Realty":      "NIFTY REALTY",
    "Infra":       "NIFTY INFRA",
    "Media":       "NIFTY MEDIA",
    "Healthcare":  "NIFTY HEALTHCARE INDEX",
    "Consumer":    "NIFTY INDIA CONSUMPTION",
}

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com",
}


def refresh_sector_data() -> bool:
    """
    Fetch sector indices data from NSE.
    Called daily 9:05 AM by scheduler.

    [AUDIT FIX Gap #12]: previously returned nothing — if NSE blocked every
    request (a real, common risk for scrapers), sector_data stayed empty,
    nothing was saved, and NOTHING raised or logged at a visible level; the
    scheduler job had no way to know the refresh had completely failed. Now
    returns True only if at least one sector was actually fetched this run,
    so the caller can alert the admin on a total failure.
    """
    session = requests.Session()
    try:
        # Init session with NSE homepage
        session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=10)
    except (requests.RequestException, OSError) as e:
        logger.warning(f"refresh_sector_data: NSE session init failed: {type(e).__name__}: {e}")

    sector_data = {}
    for sector, index_name in SECTOR_INDICES.items():
        try:
            url = f"https://www.nseindia.com/api/equity-stockIndices?index={index_name.replace(' ', '%20')}"
            resp = session.get(url, headers=NSE_HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            advance = data.get("advance", {})
            decline = data.get("decline", {})
            metadata = data.get("metadata", {})

            change_pct = float(metadata.get("percentChange", 0))
            advances   = int(advance.get("advances", 0))
            declines   = int(decline.get("declines", 0))

            # Strength score: change % + advance/decline ratio
            # Weights configurable via PARAMS (optimizer-tunable)
            weights = PARAMS.get("sector_strength_weights", {"change_pct": 0.6, "adv_dec": 0.4})
            adv_dec_ratio = advances / max(declines, 1)
            strength_score = round(change_pct * weights["change_pct"] + (adv_dec_ratio - 1) * weights["adv_dec"], 2)

            sector_data[sector] = {
                "index": index_name,
                "change_pct": change_pct,
                "advances": advances,
                "declines": declines,
                "adv_dec_ratio": round(adv_dec_ratio, 2),
                "strength_score": strength_score,
                "status": _get_status(strength_score),
            }
        except (requests.RequestException, ValueError, TypeError, KeyError) as e:
            append_log(AUDIT_LOG_FILE, f"SECTOR FETCH ERROR {sector}: {e}")
            continue

    if sector_data:
        _append_sector_snapshot(sector_data)  # J&T 1993 history (ADD-ONLY)
        # [Method upgrade 2026-07-30] RS momentum blend (Jegadeesh & Titman 1993):
        # history ready → strength = old_score + momentum_point (documented add);
        # history nahi → exact purana score (fail-open).
        try:
            mom = sector_momentum_points()
            if mom:
                for sec, v in sector_data.items():
                    if isinstance(v, dict) and "strength_score" in v:
                        v["momentum_point"] = mom.get(sec, 0.0)
                        v["strength_score"] = round(v["strength_score"] + v["momentum_point"], 2)
                        v["status"] = _get_status(v["strength_score"])
        except Exception as _e:
            logger.warning(f"sector momentum blend failed (old score kept): {_e}")
        sector_data["updated_at"] = now_ist().isoformat()
        save_json(SECTOR_DATA_FILE, sector_data)
        append_log(AUDIT_LOG_FILE, f"SECTOR DATA: Updated {len(sector_data)-1} sectors")
        return True

    append_log(AUDIT_LOG_FILE, "SECTOR DATA: refresh_sector_data got ZERO sectors this run (NSE blocked/unreachable?) — existing data unchanged, may be going stale")
    return False


SECTOR_HISTORY_FILE = "data/sector_history.json"


def _append_sector_snapshot(sector_data: dict):
    """J&T 1993 momentum ke liye daily change% archive (ADD-ONLY accumulation).
    Window din-ba-din badhti hai (bootstrap path documented — snap ke din se start)."""
    try:
        hist = load_json(SECTOR_HISTORY_FILE, {"days": []})
        days = hist.get("days", [])
        snap = {"date": now_ist().date().isoformat(),
                "sectors": {k: float(v.get("change_pct", 0)) for k, v in sector_data.items()
                            if isinstance(v, dict) and "change_pct" in v}}
        if not days or days[-1].get("date") != snap["date"]:
            days.append(snap)
        else:
            days[-1] = snap
        hist["days"] = days[-130:]  # ~6 months cap (J&T formation 3-12M tak badhegi)
        save_json(SECTOR_HISTORY_FILE, hist)
    except Exception as e:
        logger.warning(f"_append_sector_snapshot failed: {e}")


def sector_momentum_points(min_days: int = 6) -> dict:
    """
    [VERIFIED METHOD — ADAPTED, not exact] Jegadeesh & Titman 1993 ne 3-12
    MAHINE ki formation window use ki thi; yahan archive ke available DIN (6+)
    ka window hai = method ka adapted short-window roop, exact J&T nahi.
    Cross-sectional relative-strength principle verified (J&T 1993);
    skip-last-1 convention bhi wahi family. Window chhota = honest scope note. Score = sector ka return − universe median,
    ±1 scale (display normalization; gate thresholds owner-side same).
    Data < min_days → {} (fail-open: caller purana score use kare).
    """
    try:
        import statistics
        days = (load_json(SECTOR_HISTORY_FILE, {"days": []}) or {}).get("days", [])
        if len(days) < min_days:
            return {}
        window = days[:-1] if len(days) > 1 else days  # J&T skip last-1
        sectors = {s for d in window for s in (d.get("sectors") or {})}
        rets = {}
        for sec in sectors:
            r = 1.0
            n = 0
            for d in window:
                cp = (d.get("sectors") or {}).get(sec)
                if cp is None:
                    continue
                r *= (1 + float(cp) / 100.0)
                n += 1
            if n >= max(3, len(window) - 2):
                rets[sec] = (r - 1) * 100.0
        if len(rets) < 3:
            return {}
        med = statistics.median(rets.values())
        return {sec: round((ret - med) / 2.0, 2) for sec, ret in rets.items()}  # ±~1 display scale
    except Exception as e:
        logger.warning(f"sector_momentum_points failed: {e}")
        return {}


def _get_status(score: float) -> str:
    """Classify sector strength (optimizer-tunable thresholds)."""
    thresholds = PARAMS.get("sector_status_thresholds", {"strong": 1.0, "neutral": 0.0})
    if score >= thresholds["strong"]:
        return "STRONG"
    elif score >= thresholds["neutral"]:
        return "NEUTRAL"
    else:
        return "WEAK"


def is_sector_strong(sector: str) -> bool:
    """Check if a sector is strong enough to trade."""
    data = load_json(SECTOR_DATA_FILE, {})
    sector_info = data.get(sector, {})
    status = sector_info.get("status", "NEUTRAL")
    # STRONG or NEUTRAL = allow, WEAK = skip
    return status != "WEAK"


def get_stock_sector(symbol: str) -> str:
    """Get sector for a symbol from halal universe CSV."""
    try:
        import pandas as pd
        from config import CUSTOM_UNIVERSE_FILE
        df = pd.read_csv(CUSTOM_UNIVERSE_FILE)
        row = df[df["symbol"] == symbol]
        if not row.empty:
            return row["sector"].values[0]
    except (FileNotFoundError, OSError, KeyError, ValueError) as e:
        logger.warning(f"get_stock_sector: Failed for {symbol}: {type(e).__name__}: {e}")
    return "Unknown"


def get_sector_runtime_signal(symbol: str) -> dict:
    """
    Decision 11 owner engine for dynamic sector thresholding.

    [AUDIT FIX — user-confirmed design change, long-only bot]: sector strength is
    now a HARD entry filter — only a sector genuinely classified STRONG passes;
    NEUTRAL and WEAK are both blocked for new entries (previously NEUTRAL always
    passed here, and only WEAK reduced size elsewhere). Rationale researched from
    sector-rotation literature (Jegadeesh & Titman 1993 relative strength,
    O'Neil/Faber rotation): long-only strategies should fully avoid non-outperforming
    sectors for new longs, not merely downsize into them — there's no verified edge
    in going long specifically because a sector is weak (that's a separate,
    untested contrarian/mean-reversion strategy, not part of this bot's design).

    This is now the SINGLE source of truth for "is this stock's sector tradeable" —
    it requires BOTH (a) the dynamic, regime/correlation-adjusted score>=threshold
    check below, AND (b) the underlying raw 3-way classification from
    data/sector_strength.json being exactly "STRONG" (not "NEUTRAL"). Every other
    caller (strategy.py's macro-context filter, risk_manager's entry gate,
    capital_manager's sizing) must go through this function so they can never
    disagree with each other again.
    """
    try:
        from per_stock_params import get_param
        sector = get_stock_sector(symbol)
        data = load_json(SECTOR_DATA_FILE, {})
        info = data.get(sector, {}) if isinstance(data, dict) else {}
        score = float(info.get("strength_score", 0.0) or 0.0)
        raw_status = info.get("status", "WEAK")  # STRONG / NEUTRAL / WEAK, from _get_status()
        base_threshold = float(get_param(symbol, "sector_strength_threshold", 0.5) or 0.5)
        threshold = base_threshold
        try:
            from market_regime import get_market_regime_details
            regime = str(get_market_regime_details().get("final_regime", get_market_regime_details().get("regime", "SIDEWAYS")))
        except (ImportError, RuntimeError, ValueError) as e:
            logger.debug(f"get_sector_runtime_signal: Regime fetch failed: {type(e).__name__}: {e}")
            regime = "SIDEWAYS"
        if regime == "BEAR":
            # [CONFIG-DRIVEN] Bear regime strictness ab PARAMS se aati hai
            # (koi hardcode nahi): sector_bear_regime_threshold_boost=1.0 →
            # purana behavior; 0.0 → koi extra strictness nahi, per-stock
            # optimized threshold hi use hota hai.
            threshold = max(threshold, float(PARAMS.get("sector_bear_regime_threshold_boost", 1.0)))
        elif regime == "BULL":
            threshold = max(threshold, 0.0)
        try:
            from correlation_tracker import is_correlated_with_active
            if is_correlated_with_active(symbol):
                threshold = max(threshold, 1.0)
        except (ImportError, RuntimeError) as e:
            logger.debug(f"get_sector_runtime_signal: Correlation check failed: {type(e).__name__}: {e}")
        score_ok = score >= threshold
        allow = score_ok and (raw_status == "STRONG")
        return {
            "sector": sector,
            "strength_score": round(score, 2),
            "threshold": round(threshold, 2),
            "raw_status": raw_status,
            "allow": allow,
            "status": "STRONG" if allow else ("NEUTRAL" if raw_status == "NEUTRAL" else "WEAK"),
        }
    except (ImportError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(f"get_sector_runtime_signal: Failed for {symbol}: {type(e).__name__}: {e}")
        return {"sector": "Unknown", "strength_score": 0.0, "threshold": 0.5, "raw_status": "WEAK", "allow": False, "status": "WEAK"}


def is_stock_sector_strong(symbol: str) -> bool:
    """Check if the sector of a given stock is strong."""
    return bool(get_sector_runtime_signal(symbol).get("allow"))


def get_sector_report_old() -> str:
    """Admin: sector strength report."""
    data = load_json(SECTOR_DATA_FILE, {})
    if not data or "updated_at" not in data:
        return "No sector data. Refreshes at 9:05 AM on trading days."

    lines = [
        f"Sector Strength Report",
        f"Updated: {data.get('updated_at', 'N/A')[:16]}",
        "",
        f"{'Sector':<14} {'Status':<10} {'Change%':<10} {'A/D'}",
        "-" * 45,
    ]

    for sector, info in sorted(data.items()):
        if sector == "updated_at":
            continue
        status = info.get("status", "?")
        change = info.get("change_pct", 0)
        adr    = info.get("adv_dec_ratio", 0)
        lines.append(f"{sector:<14} {status:<10} {change:>+.2f}%     {adr:.1f}")

    return "\n".join(lines)


def get_strong_sectors() -> list:
    """Return list of strong sectors."""
    data = load_json(SECTOR_DATA_FILE, {})
    return [
        sector for sector, info in data.items()
        if sector != "updated_at" and info.get("status") == "STRONG"
    ]


def get_weak_sectors() -> list:
    """Return list of weak sectors."""
    data = load_json(SECTOR_DATA_FILE, {})
    return [
        sector for sector, info in data.items()
        if sector != "updated_at" and info.get("status") == "WEAK"
    ]



# ─────────────────────────────────────────────
# FIX-04 HYBRID MARKET REGIME WRAPPERS
# Keep backward compatibility: other modules can import from sector_strength.
# ─────────────────────────────────────────────

def get_market_regime(force_refresh: bool = False) -> str:
    from market_regime import get_market_regime as _get_market_regime
    return _get_market_regime(force_refresh=force_refresh)


def get_market_regime_details(force_refresh: bool = False) -> dict:
    from market_regime import get_market_regime_details as _get_market_regime_details
    return _get_market_regime_details(force_refresh=force_refresh)


def get_market_regime_report(force_refresh: bool = False) -> str:
    from market_regime import get_market_regime_report as _get_market_regime_report
    return _get_market_regime_report(force_refresh=force_refresh)

# FIX-04: Combined admin report = Hybrid Market Regime + Sector Strength
def get_sector_report() -> str:
    try:
        from market_regime import get_market_regime_report
        regime = get_market_regime_report(force_refresh=False)
    except (ImportError, RuntimeError, ValueError) as e:
        regime = f"Market Regime unavailable: {e}"

    try:
        sector = get_sector_report_old()
    except (RuntimeError, ValueError, OSError) as e:
        sector = f"Sector Strength unavailable: {e}"

    return (
        "HYBRID MARKET REGIME\n"
        "====================\n"
        f"{regime}\n\n"
        "SECTOR STRENGTH\n"
        "===============\n"
        f"{sector}"
    )
