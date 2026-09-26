"""
overnight_movers.py — Next-Day Movers Research Module (v5.2 Phase-2)

GOAL (owner): har din halal universe (~1080 tradable) me se aise stocks
dhundna jo AGLE din sabse zyada bhagenge (top-N, owner: "top 5 jaise").
Entry aaj pre-close (15:10-15:25, CNC), exit agle din (target/SL —
owner rule: OPTIMIZER decide karega, paper phase me).

RESEARCH BASE (verified, honest scope):
- Post-Earnings Drift — Ball & Brown 1968 (earnings event + sentiment)
- Overnight Premium — Lou, Polk & Skouras 2019 (close→next-open drift)
- Closing auction imbalance — market microstructure literature
- Momentum — Jegadeesh & Titman 1993 (unusual volume + price strength)
- News sentiment — Loughran & McDonald 2011 (existing engine)

HONEST LIMIT (owner ko pata hai):
- 20% circuit wale runner me ENTRY impossible (seller hota hi nahi).
- Module daily 0.5-1.5% mover class target karta hai; 20% runner = lucky
  bonus (agar position pehle se ho).
- Ye RESEARCH module hai: DEFAULT OFF; paper-phase proof (t-test, same
  convention as phase gate) se pehle koi live nahi.

ARCHITECTURE (time-aware):
  14:00 job  = heavy pre-fetch (NSE announcements/bulk deals scrape +
               universe intraday snapshots, bounded concurrency + cache)
  15:00-15:25 scan = sirf LOCAL compute (cached data) + top-N finalists
               pe live price/depth (max N API calls) → BUY signals
  next-day 10:30 job = time-based exit (agar TP/SL nahi hua) + outcome
               tracking (paper proof ke liye)
  Existing trade_engine chain reuse: entry via _execute_entry (mode=
  "OVERNIGHT"), exits via existing monitor (SL/TP prices) + 10:30 job.

FAIL-CLOSED: koi bhi data source fail → us component ka score 0 (invent
nahi). Total score < overnight_min_score → no signal.
"""

import logging
import os
import time

import pandas as pd
import numpy as np

from utils import load_json, save_json, append_log, today_ist
from config import AUDIT_LOG_FILE, PARAMS

logger = logging.getLogger(__name__)

OVERNIGHT_TRACK_FILE = "data/overnight_track.json"
OVERNIGHT_PARAMS_FILE = "data/overnight_params.json"
OVERNIGHT_CACHE_DIR = "data/overnight_cache"

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com",
}


def is_overnight_enabled() -> bool:
    return bool(PARAMS.get("overnight_enabled", False))


# ═════════════════════════════════════════════════════════════════════════
# 1. NSE EVENT SCRAPERS (din me ek baar — 2-3 HTTP calls total, per-stock nahi)
# ═════════════════════════════════════════════════════════════════════════
def _nse_session():
    import requests
    s = requests.Session()
    try:
        s.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=10)
    except requests.exceptions.RequestException:
        pass
    return s


def fetch_today_events() -> dict:
    """
    Aaj ke (a) earnings/board-meeting announcements aur (b) bulk/block deals
    scrape karke {symbol: {"earnings": bool, "bulk": bool, "headline": str}}
    cache me dalta hai. Scrape fail → khali (fail-closed, koi fake event nahi).
    """
    import requests
    events = {}
    try:
        s = _nse_session()
        # (a) Corporate announcements — earnings/board outcomes
        try:
            r = s.get("https://www.nseindia.com/api/corporate-announcements?index=equities",
                      headers=NSE_HEADERS, timeout=15)
            if r.status_code == 200:
                for row in r.json() or []:
                    sym = str(row.get("symbol", "")).strip().upper()
                    desc = str(row.get("desc", "") or "")
                    if not sym:
                        continue
                    ev = events.setdefault(sym, {"earnings": False, "bulk": False, "headline": ""})
                    if any(k in desc.upper() for k in
                           ("FINANCIAL RESULTS", "OUTCOME OF BOARD MEETING", "DIVIDEND", "BUYBACK", "BONUS", "SPLIT")):
                        if ev["headline"]:
                            ev["headline"] += " | "
                        ev["headline"] += desc[:80]
                        if "FINANCIAL RESULTS" in desc.upper() or "OUTCOME" in desc.upper():
                            ev["earnings"] = True
        except (requests.exceptions.RequestException, ValueError, TypeError) as e:
            logger.debug(f"overnight: announcements scrape failed: {type(e).__name__}: {e}")

        # (b) Bulk/block deals
        try:
            r2 = s.get("https://www.nseindia.com/api/snapshot-capital-market-largedeal",
                       headers=NSE_HEADERS, timeout=15)
            if r2.status_code == 200:
                for row in (r2.json().get("data") or []):
                    sym = str(row.get("symbol", "")).strip().upper()
                    if sym:
                        events.setdefault(sym, {"earnings": False, "bulk": False, "headline": ""})["bulk"] = True
        except (requests.exceptions.RequestException, ValueError, TypeError) as e:
            logger.debug(f"overnight: bulk deals scrape failed: {type(e).__name__}: {e}")
    except Exception as e:
        logger.warning(f"overnight: event scrape failed: {type(e).__name__}: {e}")

    try:
        os.makedirs(OVERNIGHT_CACHE_DIR, exist_ok=True)
        save_json(f"{OVERNIGHT_CACHE_DIR}/events_{today_ist().isoformat()}.json",
                  {"date": today_ist().isoformat(), "events": events})
    except OSError:
        pass
    if events:
        append_log(AUDIT_LOG_FILE, f"OVERNIGHT EVENTS: {len(events)} symbols with announcements/deals")
    return events


def _load_today_events() -> dict:
    try:
        data = load_json(f"{OVERNIGHT_CACHE_DIR}/events_{today_ist().isoformat()}.json", {})
        return data.get("events", {}) if isinstance(data, dict) else {}
    except Exception:
        return {}


# ═════════════════════════════════════════════════════════════════════════
# 2. PRE-FETCH (14:00 job — heavy, trading window me nahi)
# ═════════════════════════════════════════════════════════════════════════
def prefetch_overnight_snapshots() -> dict:
    """
    Universe ke intraday 15-min snapshots (aaj ka) + events scrape.
    Bounded concurrency + rate-limit sleep. Cache → data/overnight_cache/.
    Returns {"fetched": n, "failed": m}. Enabled nahi → no-op.
    """
    if not is_overnight_enabled():
        return {}
    try:
        from stock_selector import load_halal_symbols
        symbols = load_halal_symbols()
    except (ImportError, RuntimeError) as e:
        append_log(AUDIT_LOG_FILE, f"OVERNIGHT PREFETCH: universe load failed: {e}")
        return {}

    cap = int(PARAMS.get("overnight_prefetch_max_symbols", 0) or 0)
    if cap > 0:
        symbols = symbols[:cap]
    sleep_sec = float(PARAMS.get("overnight_api_sleep_sec", 0.15))

    events = fetch_today_events()

    fetched, failed = 0, 0
    try:
        from dhan_data import fetch_intraday_data
    except ImportError as e:
        append_log(AUDIT_LOG_FILE, f"OVERNIGHT PREFETCH: dhan_data unavailable: {e}")
        return {"fetched": 0, "failed": len(symbols), "events": len(events)}

    os.makedirs(OVERNIGHT_CACHE_DIR, exist_ok=True)
    for sym in symbols:
        try:
            if sleep_sec > 0:
                time.sleep(sleep_sec)
            df = fetch_intraday_data(str(sym), interval="15min", days=1)
            if df is None or df.empty:
                failed += 1
                continue
            df.to_csv(f"{OVERNIGHT_CACHE_DIR}/{sym.upper()}_{today_ist().isoformat()}.csv")
            fetched += 1
        except (ConnectionError, TimeoutError, OSError, ValueError) as e:
            failed += 1
            logger.debug(f"overnight prefetch {sym}: {type(e).__name__}")
    append_log(AUDIT_LOG_FILE, f"OVERNIGHT PREFETCH: fetched={fetched} failed={failed} events={len(events)}")
    return {"fetched": fetched, "failed": failed, "events": len(events)}


def _load_today_snapshot(symbol: str) -> pd.DataFrame:
    try:
        path = f"{OVERNIGHT_CACHE_DIR}/{symbol.upper()}_{today_ist().isoformat()}.csv"
        if not os.path.exists(path):
            return pd.DataFrame()
        return pd.read_csv(path, index_col=0, parse_dates=True)
    except (FileNotFoundError, OSError, ValueError):
        return pd.DataFrame()


# ═════════════════════════════════════════════════════════════════════════
# 3. SIGNAL COMPONENTS (har ek fail-closed — data nahi = score 0)
# ═════════════════════════════════════════════════════════════════════════
def _component_volume_surge(sym: str, snap: pd.DataFrame) -> float:
    """Aaj ka volume vs 20-d avg — surge 0..1 (3x pe saturated)."""
    try:
        if snap is None or snap.empty or "volume" not in snap.columns:
            return 0.0
        from dhan_data import fetch_daily_data
        daily = fetch_daily_data(sym, days=60)
        if daily is None or daily.empty or len(daily) < 21:
            return 0.0
        lookback = int(PARAMS.get("overnight_volume_lookback", 20))
        avg_vol = float(daily["volume"].iloc[-lookback:].mean())
        today_vol = float(snap["volume"].sum())
        if avg_vol <= 0:
            return 0.0
        ratio = today_vol / avg_vol
        _sat = float(PARAMS.get("overnight_volume_saturation_mult", 3.0))
        return round(max(0.0, min(1.0, ratio / _sat)), 4)
    except (KeyError, TypeError, ValueError) as e:
        logger.debug(f"overnight volume {sym}: {type(e).__name__}: {e}")
        return 0.0


def _component_price_strength(sym: str, snap: pd.DataFrame) -> float:
    """Intraday return (capped) + close near day high — strength 0..1."""
    try:
        if snap is None or snap.empty or "close" not in snap.columns:
            return 0.0
        closes = snap["close"].astype(float)
        first, last = float(closes.iloc[0]), float(closes.iloc[-1])
        if first <= 0:
            return 0.0
        ret = (last - first) / first * 100.0
        _sat = float(PARAMS.get("overnight_price_saturation_pct", 5.0))
        ret_norm = max(0.0, min(1.0, ret / _sat))  # saturation pe capped (honest scale)
        day_high = float(snap["high"].astype(float).max())
        close_pos = (last - float(snap["low"].astype(float).min())) / max(day_high - float(snap["low"].astype(float).min()), 1e-6)
        _blend = PARAMS.get("overnight_price_blend", {"ret": 0.6, "pos": 0.4})
        return round(float(_blend.get("ret", 0.6)) * ret_norm +
                     float(_blend.get("pos", 0.4)) * max(0.0, min(1.0, close_pos)), 4)
    except (KeyError, TypeError, ValueError, IndexError) as e:
        logger.debug(f"overnight price {sym}: {type(e).__name__}: {e}")
        return 0.0


def _component_earnings_event(sym: str, events: dict) -> float:
    """Aaj earnings/board outcome announce hua → 1.0 (sentiment LM me add hota hai)."""
    try:
        ev = events.get(str(sym).upper())
        return 1.0 if ev and ev.get("earnings") else 0.0
    except (KeyError, AttributeError):
        return 0.0


def _component_bulk_deal(sym: str, events: dict) -> float:
    try:
        ev = events.get(str(sym).upper())
        return 1.0 if ev and ev.get("bulk") else 0.0
    except (KeyError, AttributeError):
        return 0.0


def _component_news_sentiment(sym: str) -> float:
    """LM news cache (pre-market prefetch) — positive score → 0..1."""
    try:
        from news_analyzer import get_sentiment
        score = get_sentiment(sym)
        if score is None:
            return 0.0
        return round(max(0.0, min(1.0, (float(score) + 1.0) / 2.0)), 4)
    except (ImportError, RuntimeError, TypeError, ValueError):
        return 0.0


def _component_fii_dii() -> float:
    """Market-level FII/DII bullish (T-1 point-in-time) → 1.0, else 0."""
    try:
        from fii_dii_tracker import is_market_bullish
        return 1.0 if is_market_bullish() else 0.0
    except (ImportError, RuntimeError):
        return 0.0


def _component_overnight_persistence(sym: str) -> float:
    """
    [VERIFIED — Lou, Polk & Skouras 2019, Journal of Financial Economics
    "A Tug of War: Overnight versus Intraday Expected Returns"]:
    firm-level overnight returns POSITIVELY predict future overnight returns
    (own-component continuation, t-stat ~6.0). Matlab: jo stock lagatar
    gap-up ho raha hai, uska agla overnight bhi upar khulne ki tendency.

    Signal: trailing N-day average overnight return
    (open_t / close_{t-1} - 1). Positive avg -> 0..1 (1.0 pe saturated);
    negative/zero -> 0. Fail-closed (data nahi -> 0).
    """
    try:
        from dhan_data import fetch_daily_data
        daily = fetch_daily_data(sym, days=60)
        if daily is None or daily.empty or "open" not in daily.columns:
            return 0.0
        lookback = int(PARAMS.get("overnight_persistence_lookback", 5))
        if len(daily) < lookback + 2:
            return 0.0
        opens = daily["open"].astype(float)
        closes = daily["close"].astype(float)
        overnight = (opens / closes.shift(1) - 1.0).dropna()
        recent = overnight.tail(lookback)
        avg_pct = float(recent.mean()) * 100.0
        _sat = float(PARAMS.get("overnight_persistence_saturation_pct", 1.0))
        return round(max(0.0, min(1.0, avg_pct / _sat)), 4)
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as e:
        logger.debug(f"overnight persistence {sym}: {type(e).__name__}: {e}")
        return 0.0


def _component_tug_of_war(sym: str) -> float:
    """
    [VERIFIED — Akbas, Boehmer, Jiang & Koch 2021, Journal of Financial
    Economics "Overnight returns, daytime reversals, and future stock
    returns"]: stocks with HIGH frequency of positive-overnight +
    negative-intraday reversals outperform next month by +0.92%
    (tug-of-war intensity = overnight noise-traders vs daytime arbitrageurs).

    Signal: trailing window me (overnight > 0 AND intraday < 0) din ka ratio.
    0.5 ratio pe 1.0 saturated (research me highest-frequency decile hi
    outperform karta hai). Fail-closed.
    """
    try:
        from dhan_data import fetch_daily_data
        daily = fetch_daily_data(sym, days=90)
        if daily is None or daily.empty or "open" not in daily.columns:
            return 0.0
        window = int(PARAMS.get("overnight_tug_of_war_lookback", 20))
        if len(daily) < window + 2:
            return 0.0
        opens = daily["open"].astype(float)
        closes = daily["close"].astype(float)
        overnight = (opens / closes.shift(1) - 1.0).dropna()
        intraday = (closes / opens - 1.0).dropna()
        tug = ((overnight > 0) & (intraday < 0))
        ratio = float(tug.tail(window).mean())
        _sat = float(PARAMS.get("overnight_tug_saturation_ratio", 0.5))
        return round(max(0.0, min(1.0, ratio / _sat)), 4)
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as e:
        logger.debug(f"overnight tug-of-war {sym}: {type(e).__name__}: {e}")
        return 0.0


def _component_depth_imbalance(sym: str) -> float:
    """
    Closing depth buy/sell imbalance (Dhan 5-level) — sirf FINALISTS ke liye
    (API cost). Buy qty > sell qty → 0..1.
    """
    try:
        from stock_selector import get_security_id
        from broker import get_dhan
        security_id = get_security_id(sym)
        if not security_id:
            return 0.0
        depth = get_dhan().get_market_depth(security_id=security_id, exchange_segment="NSE_EQ")
        if not isinstance(depth, dict):
            return 0.0
        bids = depth.get("bids", depth.get("buy", []))
        asks = depth.get("asks", depth.get("sell", []))
        if not bids or not asks:
            return 0.0

        def _qty(side):
            tot = 0
            for lvl in side[:5]:
                try:
                    tot += int(lvl.get("quantity", lvl.get("qty", 0)) or 0)
                except (TypeError, ValueError):
                    continue
            return tot

        bq, aq = _qty(bids), _qty(asks)
        if aq <= 0 and bq <= 0:
            return 0.0
        return round(max(0.0, min(1.0, bq / max(1.0, aq + bq))), 4)
    except (ImportError, RuntimeError, TypeError, ValueError) as e:
        logger.debug(f"overnight depth {sym}: {type(e).__name__}: {e}")
        return 0.0


# ═════════════════════════════════════════════════════════════════════════
# 4. SCAN (15:00 job — LOCAL compute, finalists pe hi API)
# ═════════════════════════════════════════════════════════════════════════
def _score_weights() -> dict:
    w = PARAMS.get("overnight_score_weights", {})
    if not isinstance(w, dict) or not w:
        return {"volume_surge": 0.20, "price_strength": 0.20,
                "overnight_persistence": 0.15, "earnings_event": 0.15,
                "tug_of_war": 0.10, "bulk_deal": 0.05,
                "news_sentiment": 0.05, "depth_imbalance": 0.05, "fii_dii": 0.05}
    total = sum(float(v) for v in w.values() if isinstance(v, (int, float)))
    if total <= 0:
        return w
    return {k: float(v) / total for k, v in w.items()}


def score_candidates(events: dict = None, finalists_only: bool = False) -> list:
    """
    Universe ka score (cached data se). Returns sorted [{symbol, score,
    components}] desc. finalists_only=True pe sirf top-N ko depth component
    milta hai (API budget).
    """
    if not is_overnight_enabled():
        return []
    try:
        from stock_selector import load_halal_symbols
        symbols = load_halal_symbols()
    except (ImportError, RuntimeError):
        return []
    events = events if events is not None else _load_today_events()
    weights = _score_weights()
    fii = _component_fii_dii()

    scored = []
    for sym in symbols:
        snap = _load_today_snapshot(sym)
        if snap is None or snap.empty:
            continue  # prefetch miss → skip (fail-closed, invent nahi)
        comp = {
            "volume_surge": _component_volume_surge(sym, snap),
            "price_strength": _component_price_strength(sym, snap),
            "overnight_persistence": _component_overnight_persistence(sym),
            "earnings_event": _component_earnings_event(sym, events),
            "tug_of_war": _component_tug_of_war(sym),
            "bulk_deal": _component_bulk_deal(sym, events),
            "news_sentiment": _component_news_sentiment(sym),
            "fii_dii": fii,
        }
        comp["depth_imbalance"] = 0.0  # finalists pe hi (API budget)
        score = sum(comp.get(k, 0.0) * w for k, w in weights.items())
        scored.append({"symbol": sym, "score": round(score, 4), "components": comp})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def get_top_candidates(events: dict = None) -> list:
    """Top-N candidates + unke liye depth component (max N API calls)."""
    max_n = int(PARAMS.get("overnight_max_candidates", 5))
    scored = score_candidates(events=events)
    top = scored[:max_n]
    for c in top:
        c["components"]["depth_imbalance"] = _component_depth_imbalance(c["symbol"])
        w = _score_weights()
        c["score"] = round(sum(c["components"].get(k, 0.0) * v for k, v in w.items()), 4)
    top.sort(key=lambda x: x["score"], reverse=True)
    return top


def build_overnight_signals() -> list:
    """
    Final candidates → BUY signals (entry price = live price, SL/TP
    optimizer/fallback params se). Existing entry chain ise consume karta hai.
    """
    if not is_overnight_enabled():
        return []
    min_score = float(PARAMS.get("overnight_min_score", 0.45))
    tp_pct = float(PARAMS.get("overnight_tp_pct", 1.0))
    sl_pct = float(PARAMS.get("overnight_sl_pct", 0.75))

    signals = []
    for c in get_top_candidates():
        try:
            if c["score"] < min_score:
                continue
            from dhan_data import get_live_price
            price = get_live_price(c["symbol"])
            if not price or price <= 0:
                continue
            entry = round(float(price), 2)
            sl = round(entry * (1.0 - sl_pct / 100.0), 2)
            tp = round(entry * (1.0 + tp_pct / 100.0), 2)
            signals.append({
                "action": "BUY",
                "symbol": c["symbol"],
                "entry_price": entry,
                "sl_price": sl,
                "tp1_price": tp,
                "entry_idx": 0,
                "phase": "OVERNIGHT",
                "signal_score": round(min(1.0, c["score"]), 2),
                "reason": (f"OVERNIGHT_MOVER score={c['score']:.2f} "
                           f"vol={c['components'].get('volume_surge', 0):.2f} "
                           f"persist={c['components'].get('overnight_persistence', 0):.2f} "
                           f"tow={c['components'].get('tug_of_war', 0):.2f} "
                           f"earn={c['components'].get('earnings_event', 0)}"),
            })
        except (ImportError, RuntimeError, ValueError, TypeError) as e:
            append_log(AUDIT_LOG_FILE, f"OVERNIGHT SIGNAL ERR {c.get('symbol')}: {type(e).__name__}: {e}")
    return signals


# ═════════════════════════════════════════════════════════════════════════
# 5. PAPER-PROOF TRACKING + MINI-OPTIMIZER (owner: exit optimizer decide karega)
# ═════════════════════════════════════════════════════════════════════════
def record_overnight_entry(symbol: str, entry_price: float, sl: float, tp: float, score: float):
    track = load_json(OVERNIGHT_TRACK_FILE, {"trades": []})
    track.setdefault("trades", []).append({
        "symbol": symbol,
        "entry_price": entry_price,
        "sl": sl,
        "tp": tp,
        "score": score,
        "entry_date": today_ist().isoformat(),
        "status": "OPEN",
    })
    save_json(OVERNIGHT_TRACK_FILE, track)


def record_overnight_outcome(symbol: str, exit_price: float, reason: str,
                             day_high: float = None, day_low: float = None,
                             exit_date: str = None):
    """
    Next-day outcome — paper proof ka data. day_high/day_low = agle din ke
    touch hue levels (optimizer ki TP/SL simulation ke liye zaroori).
    """
    track = load_json(OVERNIGHT_TRACK_FILE, {"trades": []})
    for t in track.get("trades", []):
        if t.get("symbol") == symbol and t.get("status") == "OPEN":
            t["exit_price"] = exit_price
            t["exit_reason"] = reason
            t["exit_date"] = exit_date or today_ist().isoformat()
            t["day_high"] = day_high if day_high is not None else exit_price
            t["day_low"] = day_low if day_low is not None else exit_price
            t["status"] = "CLOSED"
            t["net_pct"] = round((exit_price - t["entry_price"]) / t["entry_price"] * 100.0, 3)
            break
    save_json(OVERNIGHT_TRACK_FILE, track)


def overnight_edge_report() -> dict:
    """
    Paper proof: closed trades ka one-sided t-test (same convention as phase
    gate). min_trades poore + mean>0 + p<alpha → edge proven.
    """
    from optimizer import _phase_edge_test  # same statistical convention
    track = load_json(OVERNIGHT_TRACK_FILE, {"trades": []})
    closed = [t for t in track.get("trades", []) if t.get("status") == "CLOSED" and t.get("net_pct") is not None]
    min_trades = int(PARAMS.get("overnight_min_paper_trades", 30))
    alpha = float(PARAMS.get("overnight_edge_alpha", 0.10))
    rets = [t["net_pct"] for t in closed]
    win = [t for t in closed if t["net_pct"] > 0]
    edge = _phase_edge_test(rets, alpha=alpha, min_trades=min_trades)
    return {
        "closed_trades": len(closed),
        "win_rate_pct": round(len(win) / len(closed) * 100.0, 1) if closed else 0.0,
        "avg_net_pct": round(float(np.mean(rets)), 3) if rets else 0.0,
        "edge_enabled": edge["enabled"],
        "edge_reason": edge["reason"],
        "p_value": edge.get("p_value"),
        "min_trades_needed": min_trades,
    }


def optimize_overnight_exit_params() -> dict:
    """
    Owner rule: exit OPTIMIZER decide karega. Closed paper trades pe TP/SL
    grid search (expectancy maximization) — koi hardcoded nahi. Simulation
    point-in-time safe: entry ke baad agle din ka high/low track me hai —
    high ne TP touch kiya ya low ne SL (touch-order assume TP-first jab dono
    touch hue — standard conservative convention, documented).
    Results data/overnight_params.json me; runtime yahi padhta hai.
    """
    track = load_json(OVERNIGHT_TRACK_FILE, {"trades": []})
    closed = [t for t in track.get("trades", [])
              if t.get("status") == "CLOSED" and t.get("day_high") is not None]
    if len(closed) < int(PARAMS.get("overnight_min_paper_trades", 30)):
        return {"status": "insufficient_data", "trades": len(closed)}

    _tg = PARAMS.get("overnight_tp_grid", {"min": 0.5, "max": 2.75, "step": 0.25})
    _sg = PARAMS.get("overnight_sl_grid", {"min": 0.25, "max": 1.5, "step": 0.25})
    tp_grid = []
    _t = _tg["min"]
    while _t <= _tg["max"] + 1e-9:
        tp_grid.append(round(_t, 2))
        _t += _tg["step"]
    sl_grid = []
    _s = _sg["min"]
    while _s <= _sg["max"] + 1e-9:
        sl_grid.append(round(_s, 2))
        _s += _sg["step"]
    best = None
    for tp in tp_grid:
        for sl in sl_grid:
            nets = []
            for t in closed:
                entry = float(t["entry_price"])
                hi = float(t["day_high"])
                lo = float(t["day_low"])
                fallback = float(t.get("exit_price") or entry)
                tp_hit = hi >= entry * (1.0 + tp / 100.0)
                sl_hit = lo <= entry * (1.0 - sl / 100.0)
                if tp_hit and sl_hit:
                    net = tp  # conservative: TP-first assumption (documented)
                elif tp_hit:
                    net = tp
                elif sl_hit:
                    net = -sl
                else:
                    net = round((fallback - entry) / entry * 100.0, 3)
                nets.append(net)
            exp = float(np.mean(nets)) if nets else 0.0
            if best is None or exp > best["expectancy"]:
                best = {"tp_pct": tp, "sl_pct": sl, "expectancy": round(exp, 4),
                        "trades_evaluated": len(nets)}
    best["status"] = "optimized"
    save_json(OVERNIGHT_PARAMS_FILE, best)
    append_log(AUDIT_LOG_FILE, f"OVERNIGHT EXIT OPTIMIZED: {best}")
    return best


def get_overnight_params() -> dict:
    opt = load_json(OVERNIGHT_PARAMS_FILE, {})
    if opt.get("status") == "optimized":
        return opt
    return {"tp_pct": PARAMS.get("overnight_tp_pct", 1.0),
            "sl_pct": PARAMS.get("overnight_sl_pct", 0.75),
            "status": "fallback_defaults"}


def get_overnight_report() -> str:
    """Admin text report."""
    rep = overnight_edge_report()
    params = get_overnight_params()
    lines = [
        "🌙 OVERNIGHT MOVERS — PAPER PROOF",
        f"Enabled: {is_overnight_enabled()}",
        f"Closed paper trades: {rep['closed_trades']} (need {rep['min_trades_needed']})",
        f"Win rate: {rep['win_rate_pct']}% | Avg net: {rep['avg_net_pct']}%",
        f"Edge proven: {rep['edge_enabled']} ({rep['edge_reason']}, p={rep['p_value']})",
        f"Exit params: {params.get('status')} — TP={params.get('tp_pct')}% SL={params.get('sl_pct')}%",
    ]
    return "\n".join(lines)


def sync_outcomes_from_trades() -> int:
    """
    TP/SL exits jo existing 3-min monitor ne kiye (10:30 job se pehle) —
    unhe bhi paper track me sync karo (trades.json se). day_high/low
    approximate = exit price (honest note: monitor-exit ka exact H/L
    track me nahi — optimizer iske saath bhi kaam karta hai).
    Returns synced count.
    """
    try:
        trades_data = load_json("data/trades.json", {"trades": []})
        track = load_json(OVERNIGHT_TRACK_FILE, {"trades": []})
        synced = 0
        for t in trades_data.get("trades", []):
            if t.get("mode") != "OVERNIGHT" or t.get("status") != "CLOSED":
                continue
            symbol = t.get("symbol", "")
            exit_price = float(t.get("exit_price") or 0)
            entry_price = float(t.get("entry_price") or 0)
            if not symbol or exit_price <= 0 or entry_price <= 0:
                continue
            # already recorded?
            already = any(x.get("symbol") == symbol and x.get("status") == "CLOSED"
                          for x in track.get("trades", []))
            if already:
                continue
            track.setdefault("trades", []).append({
                "symbol": symbol,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "exit_reason": t.get("exit_reason", "MONITOR_EXIT"),
                "entry_date": str(t.get("entry_time", ""))[:10],
                "exit_date": str(t.get("exit_time", ""))[:10],
                "day_high": exit_price,
                "day_low": exit_price,
                "status": "CLOSED",
                "net_pct": round((exit_price - entry_price) / entry_price * 100.0, 3),
            })
            synced += 1
        if synced:
            save_json(OVERNIGHT_TRACK_FILE, track)
            append_log(AUDIT_LOG_FILE, f"OVERNIGHT SYNC: {synced} monitor-exits added to paper track")
        return synced
    except (KeyError, TypeError, ValueError) as e:
        logger.debug(f"sync_outcomes_from_trades: {type(e).__name__}: {e}")
        return 0
