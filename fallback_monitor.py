"""
fallback_monitor.py — DYNAMIC→STATIC FALLBACK VISIBILITY (FIX-LIST 2026-09-04 item 17)

Owner requirement (non-technical, verbatim intent):
    "Jab bhi dynamic calculation fail hoke static default pe jaye, error log
     ho aur counter badhe. Daily summary me dikhe: 'Aaj X baar dynamic
     fallback hua.' Isse future me silent failure turant pata chalega."

Why this exists: the r4 audit found TWO real bugs that were invisible for
months precisely because a `try: dynamic() except: return static` pattern
swallowed them (regime_manager DEFAULT_BEHAVIOR NameError → always SIDEWAYS;
economics_brain missing PARAMS import → max_slots always static). Each site
still "worked", so nothing alerted anyone.

What this module does (and does NOT do):
  * record_fallback(site, error, static_value) — ONE call placed inside each
    decision-critical `except` branch. It appends a line to the audit log,
    logs at WARNING, and increments today's counter (persisted per day).
  * get_daily_summary_line() — "Aaj X baar dynamic fallback hua (sites: ...)"
    for the 15:35 daily report and /botstatus.
  * It NEVER changes the fallback value or control flow. Behaviour of every
    wired site is byte-for-byte what it was; only visibility is added.
  * Persistence goes through utils.save_json/load_json (SQLite KV store) so
    it follows the same DATA_DIR sandboxing as everything else in tests.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

FALLBACK_STATE_FILE = "data/fallback_counter.json"
_LOCK = threading.Lock()


def _today() -> str:
    try:
        from utils import today_ist
        return str(today_ist())
    except Exception:  # pragma: no cover — utils always available in package
        import datetime
        return datetime.date.today().isoformat()


def _load() -> dict:
    from utils import load_json
    data = load_json(FALLBACK_STATE_FILE, {}) or {}
    if data.get("date") != _today():
        data = {"date": _today(), "total": 0, "sites": {}, "last": None}
    data.setdefault("total", 0)
    data.setdefault("sites", {})
    return data


def _save(data: dict) -> None:
    from utils import save_json
    save_json(FALLBACK_STATE_FILE, data)


def record_fallback(site: str, error: Optional[BaseException | str], static_value=None,
                    detail: str = "") -> None:
    """Call from an `except` branch where a dynamic calculation was replaced
    by a static/default value. Never raises."""
    try:
        err_txt = (f"{type(error).__name__}: {error}" if isinstance(error, BaseException)
                   else str(error or ""))
        with _LOCK:
            data = _load()
            data["total"] = int(data.get("total", 0)) + 1
            data["sites"][site] = int(data["sites"].get(site, 0)) + 1
            data["last"] = {"site": site, "error": err_txt[:300],
                            "static_value": repr(static_value)[:80], "detail": detail[:200]}
            _save(data)
            total = data["total"]
        msg = (f"DYNAMIC FALLBACK #{total} today | site={site} | static_value={static_value!r} | "
               f"{err_txt}" + (f" | {detail}" if detail else ""))
        logger.warning(msg)
        try:
            from utils import append_log
            from config import AUDIT_LOG_FILE
            append_log(AUDIT_LOG_FILE, msg)
        except Exception:
            pass
    except Exception as e:  # visibility must never break the caller
        logger.error(f"fallback_monitor.record_fallback failed: {type(e).__name__}: {e}")


def get_today_counts() -> dict:
    try:
        with _LOCK:
            return _load()
    except Exception:
        return {"date": _today(), "total": 0, "sites": {}, "last": None}


def get_daily_summary_line() -> str:
    """Plain-language line for the daily report / /botstatus."""
    d = get_today_counts()
    total = int(d.get("total", 0))
    if total == 0:
        return "Aaj 0 baar dynamic fallback hua ✅ (sab dynamic calculations chale)"
    sites = d.get("sites", {})
    top = ", ".join(f"{k}×{v}" for k, v in sorted(sites.items(), key=lambda kv: -kv[1])[:6])
    last = d.get("last") or {}
    return (f"⚠️ Aaj {total} baar dynamic fallback hua (static default use hua) — sites: {top}"
            + (f" | last: {last.get('site')} → {last.get('error')}" if last else ""))


def reset_today() -> None:
    """Admin/test helper — clears today's counter."""
    with _LOCK:
        _save({"date": _today(), "total": 0, "sites": {}, "last": None})
