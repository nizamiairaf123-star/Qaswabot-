"""
shadow_log.py — Signal Shadow Log (v5.9 research, observation-only)

Owner decision (GOAL_DISCUSSION D28): pending-order ka "point of no return"
level (entry_follow_risk_units) real data se refine hoga. Paper phase ke
pending orders kam hote hain (~30-50 / 4 hafte) — data kaafi nahi hota.
Isliye SAB BUY signals ka din-bhar ka price path record hota hai (koi order
nahi, koi risk nahi, koi capital block nahi):

  har scan (5 min) → jo bhi BUY signal banta hai uski entry/SL/TP note
  har scan        → us symbol ka CMP path update (fetched close reuse)
  EOD (15:36 job) → har signal ki kahani: max gap (risk-units me),
                     wapas aayi ya nahi (would-fill), fill hota to TP ya SL
                     (path-based hypothetical — clearly labeled approximation)
  report          → bucket stats: "X risk-units gap pe wapas aane ka
                     chance Y%" → risk_units RECOMMENDATION
                     (APPROVAL sirf owner — auto-change kabhi nahi)

Method: empirical forward observation (observation only, model nahi).
Approximation documented: CMP = scan data ka last close (5-min resolution),
path-based TP/SL outcome = hypothetical (asli order nahi tha).
"""

from __future__ import annotations

from config import DATA_DIR, PARAMS, AUDIT_LOG_FILE
from utils import load_json, save_json, now_ist, append_log

SHADOW_DAY_FILE = f"{DATA_DIR}/shadow_log_day.json"
SHADOW_REPORT_FILE = f"{DATA_DIR}/shadow_log_report.json"


def _day_key() -> str:
    return now_ist().strftime("%Y-%m-%d")


def _enabled() -> bool:
    try:
        return bool(int(PARAMS.get("shadow_log_enabled", 1)))
    except Exception:
        return True


def record_signal(symbol, entry_price, sl_price, tp1_price):
    """Din ka PEHLA BUY signal per symbol (level anchor). Baad ke signals
    same day ignore — sample cleanliness (ek symbol ek din = ek record)."""
    if not _enabled():
        return
    try:
        entry = float(entry_price)
        sl = float(sl_price)
        tp = float(tp1_price)
    except (TypeError, ValueError):
        return
    if entry <= 0 or sl <= 0 or entry <= sl:
        return
    day = _day_key()
    data = load_json(SHADOW_DAY_FILE, {"day": day, "signals": {}})
    if data.get("day") != day:
        data = {"day": day, "signals": {}}
    sigs = data.setdefault("signals", {})
    if str(symbol) in sigs:
        return
    sigs[str(symbol)] = {
        "entry": round(entry, 2),
        "sl": round(sl, 2),
        "tp": round(tp, 2),
        "first_ts": now_ist().isoformat(),
        "path": [],
        "touched_entry": False,
        "max_gap_units": None,
    }
    save_json(SHADOW_DAY_FILE, data)


def update_cmp(symbol, price):
    """Scan hook — signal ke path me CMP point add (5-min resolution)."""
    if not _enabled():
        return
    try:
        px = float(price)
    except (TypeError, ValueError):
        return
    day = _day_key()
    data = load_json(SHADOW_DAY_FILE, {"day": day, "signals": {}})
    if data.get("day") != day:
        return
    sig = data.get("signals", {}).get(str(symbol))
    if not sig:
        return
    path = sig["path"]
    if path and abs(path[-1]["px"] - px) < 1e-9:
        return  # same-scan duplicate
    path.append({"ts": now_ist().isoformat(), "px": round(px, 2)})
    try:
        max_points = int(PARAMS.get("shadow_log_max_path_points", 80))
    except Exception:
        max_points = 80
    if len(path) > max_points:
        sig["path"] = path[-max_points:]
    save_json(SHADOW_DAY_FILE, data)


def _bucket(units: float) -> str:
    for limit in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
        if units < limit:
            return f"<{limit}"
    return ">=2.0"


def recommend_risk_units(buckets: dict) -> dict:
    """Data-based recommendation (owner approval zaroori — auto-change nahi).
    Rule: sabse bada gap-bucket jisme wapas aane ka chance abhi bhi
    shadow_log_min_return_pct se zyada hai = safe hold-zone."""
    try:
        min_samples = int(PARAMS.get("shadow_log_min_samples", 30))
        min_ret = float(PARAMS.get("shadow_log_min_return_pct", 60.0))
    except Exception:
        min_samples, min_ret = 30, 60.0
    out = {"risk_units": None, "reason": "insufficient data"}
    total = sum(b.get("n", 0) for b in buckets.values())
    if total < min_samples:
        out["reason"] = f"insufficient samples ({total} < {min_samples})"
        return out
    order = ["<0.25", "<0.5", "<0.75", "<1.0", "<1.25", "<1.5", "<2.0", ">=2.0"]
    current = None
    for b in order:
        bd = buckets.get(b, {})
        n = bd.get("n", 0)
        if n == 0:
            continue
        if bd.get("return_pct", 0.0) >= min_ret:
            try:
                current = float(b.replace("<", "").replace(">=", ""))
            except ValueError:
                current = 2.0
        else:
            break
    out["risk_units"] = current
    out["reason"] = f"buckets: {buckets} (min return {min_ret}%)"
    return out


def finalize_day() -> dict:
    """EOD (15:36 job): har signal ki kahani compute + report append +
    agle din ke liye day-file clear. Observation-only — koi order touch
    nahi hota."""
    day = _day_key()
    data = load_json(SHADOW_DAY_FILE, {"day": day, "signals": {}})
    if data.get("day") != day:
        return {"finalized": 0}
    report = load_json(SHADOW_REPORT_FILE, {"days": [], "buckets": {}})
    rows = []
    for symbol, sig in data.get("signals", {}).items():
        try:
            entry = float(sig["entry"])
            sl = float(sig["sl"])
            tp = float(sig["tp"])
        except (KeyError, TypeError, ValueError):
            continue
        risk = entry - sl
        if risk <= 0:
            continue
        path = sig.get("path", [])
        px_list = [float(p["px"]) for p in path]
        max_px = max(px_list) if px_list else entry
        min_px = min(px_list) if px_list else entry
        max_gap_units = round((max_px - entry) / risk, 3)
        touched = bool(min_px <= entry)
        # would-fill → path-based hypothetical outcome (approximation:
        # first-touch ke BAAD ke path me TP/SL extremes; asli order nahi tha)
        outcome = None
        if touched:
            first_touch_idx = next(
                (i for i, p in enumerate(path) if float(p["px"]) <= entry), 0)
            after = [float(p["px"]) for p in path[first_touch_idx:]]
            hit_tp = any(p >= tp for p in after)
            hit_sl = any(p <= sl for p in after)
            outcome = "TP" if hit_tp else ("SL" if hit_sl else "OPEN")
        rows.append({
            "day": day,
            "symbol": symbol,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "max_gap_units": max_gap_units,
            "touched_entry": touched,
            "would_fill": touched,
            "outcome_if_filled": outcome,
            "path_points": len(path),
        })
    buckets = {}
    for r in rows:
        b = _bucket(float(r["max_gap_units"]))
        bd = buckets.setdefault(b, {"n": 0, "returned": 0, "tp_hit": 0, "sl_hit": 0})
        bd["n"] += 1
        if r["touched_entry"]:
            bd["returned"] += 1
        if r["outcome_if_filled"] == "TP":
            bd["tp_hit"] += 1
        if r["outcome_if_filled"] == "SL":
            bd["sl_hit"] += 1
    for b, bd in buckets.items():
        bd["return_pct"] = round(100.0 * bd["returned"] / bd["n"], 1) if bd["n"] else 0.0
    report.setdefault("days", []).append({"day": day, "signals": len(rows), "summary": rows})
    report["buckets"] = buckets
    try:
        max_days = 60
        report["days"] = report["days"][-max_days:]
    except Exception:
        pass
    save_json(SHADOW_REPORT_FILE, report)
    # agle din ke liye clean
    save_json(SHADOW_DAY_FILE, {"day": day, "signals": {}})
    rec = recommend_risk_units(buckets)
    append_log(AUDIT_LOG_FILE,
               f"SHADOW REPORT {day}: {len(rows)} signals tracked | "
               f"buckets={buckets} | recommendation={rec}")
    return {"finalized": len(rows), "buckets": buckets, "recommendation": rec}
