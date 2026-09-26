"""
fii_dii_tracker.py — FII/DII data tracker

[VERIFIED QUANT METHOD] Point-in-time correctness / no-look-ahead bias:
FII/DII cash data is published AFTER market close. Therefore any trade decision
for trading day T may only use the last published institutional flow record
available BEFORE T (normally T-1 trading day). Backtest, optimizer, paper, and
live all use the same rule.
"""

import logging
import re
from datetime import date, datetime

import requests

from utils import load_json, save_json, now_ist, append_log
from config import AUDIT_LOG_FILE, PARAMS

logger = logging.getLogger(__name__)

FII_DII_FILE = "data/fii_dii.json"
FII_DII_HISTORY_FILE = "data/fii_dii_history.json"

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com",
}


def _safe_float(value) -> float:
    try:
        text = str(value).replace(",", "").replace("₹", "").strip()
        return float(text) if text else 0.0
    except (TypeError, ValueError):
        return 0.0


def _parse_trade_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime().date()
        except (TypeError, ValueError, AttributeError) as e:
            logger.debug(f"_parse_trade_date: to_pydatetime failed: {type(e).__name__}: {e}")
    if hasattr(value, "date") and not isinstance(value, str):
        try:
            return value.date()
        except (TypeError, ValueError, AttributeError) as e:
            logger.debug(f"_parse_trade_date: date() failed: {type(e).__name__}: {e}")

    text = str(value).strip()
    for fmt in ("%d-%b-%Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _format_trade_date(trade_date: date) -> str:
    return trade_date.strftime("%d-%b-%Y")


def _sentiment_from_fii_net(fii_net: float) -> str:
    """Classify FII/DII net flow into sentiment (optimizer-tunable threshold)."""
    threshold = PARAMS.get("fii_sentiment_threshold", 500)
    if fii_net > threshold:
        return "BULLISH"
    if fii_net < -threshold:
        return "BEARISH"
    return "NEUTRAL"


def _normalize_row(row: dict):
    if not isinstance(row, dict):
        return None

    trade_date = _parse_trade_date(row.get("date"))
    if trade_date is None:
        return None

    fii_buy = _safe_float(row.get("fii_buy", row.get("buyValue", 0)))
    fii_sell = _safe_float(row.get("fii_sell", row.get("sellValue", 0)))
    fii_net = _safe_float(row.get("fii_net", fii_buy - fii_sell))
    dii_buy = _safe_float(row.get("dii_buy", 0))
    dii_sell = _safe_float(row.get("dii_sell", 0))
    dii_net = _safe_float(row.get("dii_net", dii_buy - dii_sell))
    total_net = _safe_float(row.get("total_net", fii_net + dii_net))
    fii_sentiment = row.get("fii_sentiment") or _sentiment_from_fii_net(fii_net)

    return {
        "date": _format_trade_date(trade_date),
        "fii_buy": round(fii_buy, 2),
        "fii_sell": round(fii_sell, 2),
        "fii_net": round(fii_net, 2),
        "dii_buy": round(dii_buy, 2),
        "dii_sell": round(dii_sell, 2),
        "dii_net": round(dii_net, 2),
        "total_net": round(total_net, 2),
        "fii_sentiment": fii_sentiment,
        "updated_at": row.get("updated_at") or now_ist().isoformat(),
    }


def _load_history() -> list:
    history = load_json(FII_DII_HISTORY_FILE, [])
    normalized = []
    for row in history if isinstance(history, list) else []:
        fixed = _normalize_row(row)
        if fixed:
            normalized.append(fixed)

    latest = _normalize_row(load_json(FII_DII_FILE, {}))
    if latest and latest["date"] not in {r["date"] for r in normalized}:
        normalized.append(latest)

    normalized.sort(key=lambda r: _parse_trade_date(r["date"]) or date.min)
    return normalized


def _save_history(history: list):
    unique = {}
    for row in history:
        fixed = _normalize_row(row)
        if fixed:
            unique[fixed["date"]] = fixed
    ordered = sorted(unique.values(), key=lambda r: _parse_trade_date(r["date"]) or date.min)
    save_json(FII_DII_HISTORY_FILE, ordered)


def _upsert_history_row(row: dict):
    history = _load_history()
    fixed = _normalize_row(row)
    if not fixed:
        return
    by_date = {r["date"]: r for r in history}
    by_date[fixed["date"]] = fixed
    _save_history(list(by_date.values()))


def _bootstrap_recent_history_from_groww(max_rows: int = 10):
    """
    Bootstrap a few recent daily rows from a public SSR page so the paper/optimizer
    stack gets a real point-in-time history immediately instead of waiting days.
    """
    try:
        html = requests.get(
            "https://groww.in/fii-dii-data",
            headers={"User-Agent": NSE_HEADERS["User-Agent"]},
            timeout=12,
        ).text
        if not html:
            return

        pattern = re.compile(
            r">(\d{2}\s+[A-Za-z]{3}\s+\d{4})</td>"
            r".*?>([+\-]?[\d,]+(?:\.\d+)?)</td>"
            r".*?>([+\-]?[\d,]+(?:\.\d+)?)</td>"
            r".*?>([+\-]?[\d,]+(?:\.\d+)?)</td>"
            r".*?>([+\-]?[\d,]+(?:\.\d+)?)</td>"
            r".*?>([+\-]?[\d,]+(?:\.\d+)?)</td>"
            r".*?>([+\-]?[\d,]+(?:\.\d+)?)</td>",
            re.S,
        )

        rows = []
        for match in pattern.finditer(html):
            trade_date = _parse_trade_date(match.group(1))
            if trade_date is None:
                continue
            row = {
                "date": _format_trade_date(trade_date),
                "fii_buy": _safe_float(match.group(2)),
                "fii_sell": _safe_float(match.group(3)),
                "fii_net": _safe_float(match.group(4)),
                "dii_buy": _safe_float(match.group(5)),
                "dii_sell": _safe_float(match.group(6)),
                "dii_net": _safe_float(match.group(7)),
                "total_net": _safe_float(match.group(4)) + _safe_float(match.group(7)),
                "fii_sentiment": _sentiment_from_fii_net(_safe_float(match.group(4))),
                "updated_at": now_ist().isoformat(),
            }
            rows.append(row)
            if len(rows) >= max_rows:
                break

        if rows:
            history = _load_history()
            history.extend(rows)
            _save_history(history)
            append_log(AUDIT_LOG_FILE, f"FII/DII HISTORY BOOTSTRAP: loaded {len(rows)} recent rows from public source")
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"FII/DII HISTORY BOOTSTRAP SKIPPED: {e}")


def refresh_fii_dii_data() -> bool:
    """
    Fetch latest combined NSE FII/DII cash data.
    Called daily 9:05 AM by scheduler.

    [AUDIT FIX Gap #12]: previously returned nothing on any path — a scraper
    block or bad payload from NSE just logged to a file nobody watches live,
    with no way for the caller to know refresh had failed. Now returns
    True/False so the scheduler can alert the admin on failure.
    """
    session = requests.Session()
    try:
        session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=10)
    except (requests.RequestException, OSError) as e:
        logger.warning(f"refresh_fii_dii_data: NSE session init failed: {type(e).__name__}: {e}")

    try:
        url = "https://www.nseindia.com/api/fiidiiTradeReact"
        resp = session.get(url, headers=NSE_HEADERS, timeout=10)
        if resp.status_code != 200:
            append_log(AUDIT_LOG_FILE, f"FII/DII FETCH ERROR: status={resp.status_code}")
            return False

        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            append_log(AUDIT_LOG_FILE, "FII/DII FETCH ERROR: empty/unexpected payload")
            return False

        trade_date = None
        fii_buy = fii_sell = fii_net = 0.0
        dii_buy = dii_sell = dii_net = 0.0

        for row in rows:
            category = str(row.get("category", "")).upper()
            trade_date = trade_date or row.get("date")
            if "FII" in category or "FPI" in category:
                fii_buy = _safe_float(row.get("buyValue", 0))
                fii_sell = _safe_float(row.get("sellValue", 0))
                fii_net = _safe_float(row.get("netValue", fii_buy - fii_sell))
            elif "DII" in category:
                dii_buy = _safe_float(row.get("buyValue", 0))
                dii_sell = _safe_float(row.get("sellValue", 0))
                dii_net = _safe_float(row.get("netValue", dii_buy - dii_sell))

        if not trade_date:
            trade_date = now_ist().strftime("%d-%b-%Y")

        result = _normalize_row({
            "date": trade_date,
            "fii_buy": fii_buy,
            "fii_sell": fii_sell,
            "fii_net": fii_net,
            "dii_buy": dii_buy,
            "dii_sell": dii_sell,
            "dii_net": dii_net,
            "total_net": fii_net + dii_net,
            "fii_sentiment": _sentiment_from_fii_net(fii_net),
            "updated_at": now_ist().isoformat(),
        })

        if not result:
            append_log(AUDIT_LOG_FILE, "FII/DII FETCH ERROR: could not normalize latest row")
            return False

        save_json(FII_DII_FILE, result)
        _upsert_history_row(result)

        history = _load_history()
        if len(history) < 5:
            _bootstrap_recent_history_from_groww(max_rows=10)

        append_log(
            AUDIT_LOG_FILE,
            f"FII/DII: date={result['date']} FII net={result['fii_net']} Cr | "
            f"DII net={result['dii_net']} Cr | Sentiment={result['fii_sentiment']}"
        )
        return True

    except (requests.RequestException, ValueError, TypeError, OSError) as e:
        append_log(AUDIT_LOG_FILE, f"FII/DII ERROR: {e}")
        return False


def get_point_in_time_record(as_of_date=None, publication_lag_trading_days: int = 1) -> dict:
    """
    [VERIFIED QUANT METHOD] Returns the latest published row available BEFORE
    the given trade date. For live/paper trading on day T, this naturally means
    the T-1 published record because FII/DII prints after close.
    """
    lag = max(0, int(publication_lag_trading_days or 0))
    trade_date = _parse_trade_date(as_of_date) or now_ist().date()

    history = _load_history()
    if not history:
        return {}

    dated_rows = []
    for row in history:
        row_date = _parse_trade_date(row.get("date"))
        if row_date is not None:
            dated_rows.append((row_date, row))
    dated_rows.sort(key=lambda x: x[0])

    if lag <= 0:
        eligible = [row for d, row in dated_rows if d <= trade_date]
    else:
        eligible = [row for d, row in dated_rows if d < trade_date]

    if len(eligible) < max(1, lag if lag > 0 else 1):
        return {}

    return eligible[-(lag if lag > 0 else 1)] if lag > 0 else eligible[-1]


def get_fii_sentiment(as_of_date=None, publication_lag_trading_days: int = 1) -> str:
    """Returns: BULLISH / NEUTRAL / BEARISH using point-in-time lagged data."""
    data = get_point_in_time_record(as_of_date=as_of_date, publication_lag_trading_days=publication_lag_trading_days)
    if not data:
        return "NEUTRAL"
    return data.get("fii_sentiment", "NEUTRAL")


def is_market_bullish(as_of_date=None, publication_lag_trading_days: int = 1) -> bool:
    """True if lagged point-in-time FII record is bullish."""
    return get_fii_sentiment(as_of_date=as_of_date, publication_lag_trading_days=publication_lag_trading_days) == "BULLISH"


def is_market_bearish(as_of_date=None, publication_lag_trading_days: int = 1) -> bool:
    """True if lagged point-in-time FII record is bearish."""
    return get_fii_sentiment(as_of_date=as_of_date, publication_lag_trading_days=publication_lag_trading_days) == "BEARISH"


def get_fii_dii_report() -> str:
    """Admin: latest FII/DII report + history coverage."""
    latest = _normalize_row(load_json(FII_DII_FILE, {}))
    if not latest:
        return "No FII/DII data. Refreshes at 9:05 AM on trading days."

    history = _load_history()
    history_start = history[0]["date"] if history else latest["date"]
    history_end = history[-1]["date"] if history else latest["date"]

    return (
        f"FII/DII Data\n"
        f"Latest Published Date: {latest.get('date', 'N/A')}\n"
        f"History Coverage: {history_start} -> {history_end} ({len(history)} rows)\n"
        f"Trading Rule: live/paper/backtest use last published row only (T-1 for day T)\n\n"
        f"FII\n"
        f"Buy:  Rs.{latest.get('fii_buy', 0):,.2f} Cr\n"
        f"Sell: Rs.{latest.get('fii_sell', 0):,.2f} Cr\n"
        f"Net:  Rs.{latest.get('fii_net', 0):,.2f} Cr\n\n"
        f"DII\n"
        f"Buy:  Rs.{latest.get('dii_buy', 0):,.2f} Cr\n"
        f"Sell: Rs.{latest.get('dii_sell', 0):,.2f} Cr\n"
        f"Net:  Rs.{latest.get('dii_net', 0):,.2f} Cr\n\n"
        f"Total Net: Rs.{latest.get('total_net', 0):,.2f} Cr\n"
        f"FII Sentiment: {latest.get('fii_sentiment', 'NEUTRAL')}"
    )
