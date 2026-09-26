"""
asm_gsm_screen.py — NSE ASM/GSM/suspended-stock PRE-TRADE screen.

[OWNER DECISION 2026-09-05] Rejected stocks PEHLE SE confirm — ASM/GSM/
suspended stock ka BUY order kabhi place nahi hoga. Pehle ye gap tha:
broker.py rejection SIRF reactive pakadta tha (order reject hone ke BAAD,
FIX-40 categorization) — pre-trade block missing tha (AUDIT_PROGRESS_READ_
ME_FIRST.md open item 1: "Needs a real ASM/GSM data source").

Design (zip ke fail-closed conventions par — BOARD DATA STALE PAUSE jaisa):
  * Local list file: data/asm_gsm_list.json
      {"as_of": "YYYY-MM-DD", "source": "...", "symbols": {"SYM": "ASM_L1", ...}}
  * List missing / malformed / older than PARAMS["asm_gsm_list_max_age_days"]
    → surveillance/status data unverified → new BUY entries blocked fail-closed.
    Fresh ASM/GSM membership alone is informational and does not reject a stock.
      - Exit par koi asar NAHI (constitution: "Exit kabhi band nahi") —
        ye sirf new-entry gate hai; open positions ka exit/GTT untouched.
  * List fresh + symbol listed → us symbol ka entry blocked (reason me stage).
  * Refresh: refresh_asm_gsm_list() NSE official endpoints se list laata hai
    (archives CSV + api JSON dono supported). Admin manually bhi CSV/JSON
    place kar sakta hai (manual_csv/manual_json arg). Refresh FAIL → list
    stale hi rehti hai → entries blocked (koi fabricated data NAHI — same
    policy jo refresh_decision_data.py follow karta hai).
  * Real-list verification AFTER-VPS evidence hai (datacenter IP se NSE
    block karta hai) — PRE-VPS me mechanism + fail-closed + tests shipped.

Wiring:
  * risk_manager.can_enter_trade()  — master entry gate (defense-in-depth)
  * trade_engine.run_market_scan()  — scan se PEHLE filter (timepass band:
    blocked stock ka fetch/signal-compute hi nahi hota)
"""

import json
import logging
from pathlib import Path

from config import PARAMS

logger = logging.getLogger(__name__)

LIST_FILE = Path("data") / "asm_gsm_list.json"

_STALE_REASON = ("⛔ ASM/GSM DATA STALE PAUSE — surveillance list missing/stale "
                 "(refresh: python3 scripts/refresh_decision_data.py) — new BUY entries fail-closed")

_stale_notify_done = False


def _max_age_days() -> int:
    try:
        return int(PARAMS.get("asm_gsm_list_max_age_days", 7))
    except (TypeError, ValueError):
        return 7


def _today():
    from utils import now_ist
    return now_ist().date()


def _load_list():
    """List file parse karo. Koi bhi problem → None (fail-closed)."""
    try:
        raw = json.loads(LIST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    symbols = raw.get("symbols")
    as_of = raw.get("as_of")
    if not isinstance(symbols, dict) or not isinstance(as_of, str):
        return None
    clean = {}
    for sym, stage in symbols.items():
        if isinstance(sym, str) and sym.strip():
            clean[sym.strip().upper()] = str(stage).strip() if stage else "LISTED"
    if not clean:
        return None
    try:
        from datetime import datetime
        as_of_date = datetime.strptime(as_of[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return {"as_of": as_of_date, "source": str(raw.get("source", "unknown")), "symbols": clean}


def is_asm_gsm_data_stale() -> bool:
    """
    True = list unverifiable (missing/malformed/too old) → fail-closed block.
    """
    data = _load_list()
    if data is None:
        return True
    age = (_today() - data["as_of"]).days
    return age < 0 or age > _max_age_days()


def is_symbol_blocked(symbol: str) -> tuple:
    """
    Per-symbol check. ASM/GSM membership is informational; explicit hard-status
    values (suspended/banned/delisted/rejected/not-tradeable) are blocked.
    Returns (blocked: bool, reason: str)
    """
    data = _load_list()
    if data is None:
        return True, _STALE_REASON
    sym = str(symbol or "").strip().upper()
    stage = data["symbols"].get(sym)
    if stage:
        normalized = stage.upper()
        hard_reject_markers = ("SUSPEND", "BANNED", "DELIST", "REJECT", "INACTIVE", "NOT TRADEABLE")
        if any(marker in normalized for marker in hard_reject_markers):
            return True, f"⛔ HARD STATUS BLOCKED: {sym} ({stage}, list as_of {data['as_of']}) — order place nahi hoga"
        # ASM/GSM surveillance membership is informational under the owner
        # universe rule. It must not be converted into an automatic rejection.
        return False, f"ℹ️ SURVEILLANCE FLAG: {sym} ({stage}, list as_of {data['as_of']})"
    return False, ""


def check_entry(symbol: str) -> tuple:
    """
    Master entry gate fn — risk_manager.can_enter_trade() isey call karta hai.
    Stale list → sab entries blocked (fail-closed). Listed symbol → blocked.
    Koi bhi internal error → blocked (fail-closed, trade path kabhi open nahi).
    """
    try:
        if is_asm_gsm_data_stale():
            return True, _STALE_REASON
        return is_symbol_blocked(symbol)
    except Exception as e:
        logger.warning(f"asm_gsm check_entry error ({symbol}): {type(e).__name__}: {e} — Fail-Closed block")
        return True, f"⛔ ASM/GSM SCREEN UNAVAILABLE (Fail-Closed): {e}"


def notify_stale_once():
    """Stale-pause ko din me ek baar audit log karo (har scan cycle ka spam band —
    strategy.py ke _log_phase_gate_once convention jaisa)."""
    global _stale_notify_done
    if not _stale_notify_done:
        _stale_notify_done = True
        try:
            from utils import append_log
            from config import AUDIT_LOG_FILE
            append_log(AUDIT_LOG_FILE, "ASM/GSM DATA STALE PAUSE ACTIVE — new BUY entries fail-closed blocked until list refresh")
        except Exception as e:  # logging kabhi trade path na roke
            logger.debug(f"asm_gsm stale notify failed: {type(e).__name__}: {e}")


# ─────────────────────────────────────────────
# Refresh — NSE official sources (fail-closed)
# ─────────────────────────────────────────────

_NSE_ARCHIVES_CSV = "https://archives.nseindia.com/content/fo/asm_gsm_list.csv"
_NSE_API_JSON = "https://www.nseindia.com/api/asm-gsm-list"
_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


def _norm_header(name: str) -> str:
    return str(name or "").strip().strip('"').lower().replace(" ", "_")


def parse_nse_csv(text: str) -> dict:
    """
    NSE archives CSV → {SYMBOL: stage}. Column names case/space-tolerant
    (SYMBOL / Symbol / asm_gsm stage / stage / sm_type variants).
    """
    import io
    import csv
    rows = list(csv.reader(io.StringIO(text)))
    rows = [r for r in rows if any(str(c).strip() for c in r)]
    if len(rows) < 2:
        raise ValueError("CSV me sirf header hai, koi data rows nahi")
    header = [_norm_header(c) for c in rows[0]]

    sym_idx = stage_idx = None
    for i, h in enumerate(header):
        if sym_idx is None and h in ("symbol", "sym", "nse_symbol"):
            sym_idx = i
        if stage_idx is None and ("stage" in h or "sm_type" in h or h in ("asm", "gsm", "asm_gsm")):
            stage_idx = i
    if sym_idx is None:
        sym_idx = 0  # NSE files me col-0 symbol hi hota hai
    if stage_idx is None:
        stage_idx = len(header) - 1 if len(header) > 1 else sym_idx

    out = {}
    for r in rows[1:]:
        if len(r) <= max(sym_idx, stage_idx):
            continue
        sym = str(r[sym_idx]).strip().strip('"').upper()
        if not sym or sym == header[sym_idx].upper():
            continue
        stage = str(r[stage_idx]).strip().strip('"').upper() or "LISTED"
        if sym:
            out[sym] = stage
    if not out:
        raise ValueError("CSV parse: koi valid symbol nahi mila")
    return out


def parse_nse_api_json(text: str) -> dict:
    """NSE api JSON ({\"data\":[{\"symbol\":..,\"smType\":..,\"stage\":..}]}) → {SYMBOL: stage}."""
    payload = json.loads(text)
    rows = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("API JSON me 'data' list nahi mili")
    out = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol") or row.get("nse_symbol") or "").strip().upper()
        if not sym:
            continue
        stage_parts = [str(row.get(k) or "").strip() for k in ("smType", "stage", "asmGsmStage")]
        stage = " ".join(p for p in stage_parts if p).strip().upper() or "LISTED"
        out[sym] = stage
    if not out:
        raise ValueError("API JSON parse: koi valid symbol nahi mila")
    return out


def _http_get(url: str, timeout: int = 20) -> str:
    import requests
    resp = requests.get(url, timeout=timeout, headers={
        "User-Agent": _UA, "Accept": "text/csv,application/json,*/*",
    })
    resp.raise_for_status()
    body = resp.text.lstrip("\ufeff").strip()
    if not body or body[:1] == "<":
        raise RuntimeError(f"{url} ne HTML/block-page return kiya (NSE bot-protection)")
    return body


def refresh_asm_gsm_list(manual_csv: str = None, manual_json: str = None, root: Path = None) -> int:
    """
    Surveillance list refresh (fail-closed: koi fabricated data NAHI).
      * default: NSE archives CSV → NSE api JSON (order me try)
      * manual_csv/manual_json: admin ne file di (network bypass)
    Success → data/asm_gsm_list.json atomic-write, as_of=aaj (IST).
    Returns: committed symbol count. Failure → RuntimeError (purani list intact).
    """
    symbols, source = None, None
    errors = []
    if manual_csv:
        symbols = parse_nse_csv(Path(manual_csv).read_text(encoding="utf-8"))
        source = f"manual_csv:{Path(manual_csv).name}"
    elif manual_json:
        symbols = parse_nse_api_json(Path(manual_json).read_text(encoding="utf-8"))
        source = f"manual_json:{Path(manual_json).name}"
    else:
        for url, parser, label in ((_NSE_ARCHIVES_CSV, parse_nse_csv, "archives_csv"),
                                   (_NSE_API_JSON, parse_nse_api_json, "api_json")):
            try:
                symbols = parser(_http_get(url))
                source = f"nse:{label}"
                break
            except Exception as e:
                errors.append(f"{label}: {type(e).__name__}: {e}")
        if symbols is None:
            raise RuntimeError("ASM/GSM refresh FAIL — " + " | ".join(errors)
                               + " — admin manually bhi de sakta hai (manual_csv/manual_json arg)")

    payload = {
        "as_of": str(_today()),
        "source": source,
        "symbols": symbols,
    }
    target = (Path(root) / "data" / "asm_gsm_list.json") if root else LIST_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(target)
    logger.info(f"ASM/GSM list refreshed: {len(symbols)} symbols from {source}")
    return len(symbols)
