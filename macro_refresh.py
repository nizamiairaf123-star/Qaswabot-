"""
macro_refresh.py — India Macro Auto-Refresh (v5.7.2)

Owner rule: EXTERNAL_FACT numbers (inflation etc.) jab real world me badle
to bot khud update kare — monthly, bina manual kaam ke.

SOURCE: MACRO_SOURCE_URL (env) — koi bhi reliable JSON endpoint jo ye
format de (MoSPI/RBI release se bana hua, owner ka hosted JSON ya Google
Sheet API — documented contract):

    {
      "cpi_inflation_pct": 4.45,
      "gdp_growth_pct": 6.8,
      "risk_free_rate_pct": 7.0,
      "as_of": "2026-07"
    }

FAIL-OPEN DESIGN (baaki external data jaisa): fetch/parse fail → purani
values BILKUL waisi rahengi + admin alert (stale track). Koi invent nahi.

Staleness: data/macro_override.json me saved_at hota hai; age > macro_warn_days
→ alert + "manual update" flag (silent stale kabhi nahi).
"""

import logging
import os

import requests

from utils import load_json, save_json, append_log, now_ist
from config import AUDIT_LOG_FILE, PARAMS

logger = logging.getLogger(__name__)

MACRO_OVERRIDE_FILE = "data/macro_override.json"
SOURCE_URL = os.getenv("MACRO_SOURCE_URL", "").strip()


def _fetch_macro_data() -> dict:
    """Source URL se JSON fetch karo. Fail → {} (purani values intact)."""
    if not SOURCE_URL:
        return {}
    try:
        r = requests.get(SOURCE_URL, timeout=15)
        if r.status_code != 200:
            append_log(AUDIT_LOG_FILE, f"MACRO REFRESH: source HTTP {r.status_code}")
            return {}
        data = r.json()
        if not isinstance(data, dict):
            return {}
        return data
    except requests.exceptions.RequestException as e:
        append_log(AUDIT_LOG_FILE, f"MACRO REFRESH: fetch failed {type(e).__name__}: {e}")
        return {}
    except ValueError as e:
        append_log(AUDIT_LOG_FILE, f"MACRO REFRESH: bad JSON {e}")
        return {}


def refresh_india_macro() -> dict:
    """
    Monthly job: source se fresh values lao; valid → override file save +
    config PARAMS update (runtime). Invalid/absent → purana hi rehta hai
    (fail-open) + alert. Returns status dict.
    """
    data = _fetch_macro_data()
    result = {"updated": False, "reason": "no_source"}
    if not data:
        append_log(AUDIT_LOG_FILE, "MACRO REFRESH: no data (source not set/failed) — existing values intact")
        return result

    new = {}
    try:
        cpi = float(data.get("cpi_inflation_pct"))
        gdp = float(data.get("gdp_growth_pct"))
        rf = float(data.get("risk_free_rate_pct"))
        if not (0 < cpi < 30) or not (-10 < gdp < 30) or not (0 < rf < 20):
            raise ValueError("out-of-sane-range")
        new = {
            "india_inflation_pct": cpi,
            "india_gdp_growth_pct": gdp,
            "india_risk_free_rate_pct": rf,
            "as_of": str(data.get("as_of", now_ist().date().isoformat())[:7]),
            "saved_at": now_ist().isoformat(),
        }
    except (TypeError, ValueError) as e:
        append_log(AUDIT_LOG_FILE, f"MACRO REFRESH: invalid values {e} — ignored")
        return {"updated": False, "reason": "invalid_values"}

    save_json(MACRO_OVERRIDE_FILE, new)
    # runtime update (config PARAMS — bina restart ke)
    try:
        PARAMS["india_inflation_pct"] = cpi
        PARAMS["india_gdp_growth_pct"] = gdp
        PARAMS["india_risk_free_rate_pct"] = rf
    except Exception:
        pass  # PARAMS dict mutable — agle load pe file se aayega

    append_log(AUDIT_LOG_FILE,
               f"MACRO REFRESH UPDATED: CPI={cpi}% GDP={gdp}% RF={rf}% as_of={new['as_of']}")
    try:
        from signal_broadcaster import alert_admin_sync
        alert_admin_sync(
            f"🇮🇳 Macro auto-updated (monthly)\n"
            f"CPI Inflation: {cpi}%\nGDP Growth: {gdp}%\nRisk-Free: {rf}%\nAs-of: {new['as_of']}",
            severity="INFO", dedup_key="macro_monthly")
    except (ImportError, RuntimeError) as e:
        append_log(AUDIT_LOG_FILE, f"MACRO REFRESH: admin alert failed {e}")
    return {"updated": True, "values": new}


def apply_macro_override():
    """
    Boot pe chalta hai: fresh override file ho to config PARAMS me apply
    karo (restart ke baad bhi naye values rehte hain).
    """
    ov = load_json(MACRO_OVERRIDE_FILE, {})
    if not isinstance(ov, dict) or not ov.get("saved_at"):
        return
    try:
        from datetime import datetime
        age_days = (now_ist().replace(tzinfo=None)
                    - datetime.fromisoformat(ov["saved_at"]).replace(tzinfo=None)).days
        if age_days > int(PARAMS.get("macro_warn_days", 90)):
            append_log(AUDIT_LOG_FILE,
                       f"MACRO STALE: override {age_days} din purana — manual update zaroori (warn_days={PARAMS.get('macro_warn_days', 90)})")
            try:
                from signal_broadcaster import alert_admin_sync
                alert_admin_sync(
                    f"⚠️ India macro data {age_days} din purana hai — MACRO_SOURCE_URL check karo ya manually update karo.",
                    severity="WARN", dedup_key="macro_stale")
            except (ImportError, RuntimeError):
                pass
            return  # stale → apply NAHI (fail-open: defaults se purani value hi hai)
        for key in ("india_inflation_pct", "india_gdp_growth_pct", "india_risk_free_rate_pct"):
            if key in ov:
                try:
                    PARAMS[key] = float(ov[key])
                except (TypeError, ValueError):
                    continue
        append_log(AUDIT_LOG_FILE, f"MACRO OVERRIDE APPLIED: as_of={ov.get('as_of')}")
    except (ValueError, TypeError) as e:
        append_log(AUDIT_LOG_FILE, f"MACRO OVERRIDE parse failed: {e}")
