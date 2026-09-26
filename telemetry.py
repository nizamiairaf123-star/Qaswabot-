"""
telemetry.py — [r30] DECISION & MARKET-CONTEXT TELEMETRY ("BLACK BOX")
=======================================================================
Owner-conceived flight-data-recorder spec (2026-09-15), registered as
prd.md Rule 16 (new Rule 16 — unrelated to the old Rule 16 deleted at
r26; number deliberately reused per governance note). Owner's words:
"Dhan gives price; telemetry records decisions + market mahoul."

FOUR PILLARS (owner spec):
  1. MARKET PHOTO the broker doesn't give — per scan: bid/ask spread
     (candidates/entries only), sector ranks, regime (trend-vs-chop),
     SEBI ASM/GSM blocked list, gate outcomes, universe size.
  2. DECISION SNAPSHOTS — why the bot took OR rejected every trade it
     considered: risk-gate blocks, news rejects, duplicate-candle skips,
     slot-full skips, blocked-at-execute, order rejections, fills.
  3. DETERMINISTIC REPLAY — each candidate/entry row carries the last N
     completed daily bars actually fed to the strategy (input_bars) plus
     signal JSON, params hash and revision stamp: 6 months later a new
     strategy version can be replayed against the exact recorded market
     conditions — zero guessing.
  4. SILENT WATCHER — passive only. Telemetry NEVER sits in the order or
     SL path and NEVER blocks a scan: every public function is fail-open
     (any telemetry failure = one audit-log line, zero trading impact).

BOUNDARY (documented, deliberate): no per-symbol-per-scan rows for the
full universe (~1000 symbols x 84 scans/day would be ~88k rows/day and
Dhan rate limits forbid per-symbol depth calls). The silent majority is
captured as scan-level counts in scan_context.counts; per-symbol rows
exist only for symbols that REACHED a decision point. Spread capture is
gated + budgeted (entries/candidates only). Exit/follow-event telemetry
is a documented future scope, not r30.

Storage: own SQLite file (config.TELEMETRY_DB, default
data/telemetry.db) — separate from trading_bot.db / key_value_store /
ndsap_archive.db. Append-only via SQLite triggers (DELETE and UPDATE
are blocked on both tables — flight-recorder immutability). No
compaction; retain forever (sizing: SYSTEM_BLUEPRINT.md §11).

PIT ("point-in-time") QUERY GUARD — the owner-side audit used the name
"PIT Telemetry" for this capability (owner-confirmed alias, r31): the
replay read path mirrors NDSAP's structural as-of discipline —
`read_asof(as_of, ...)` / `read_scans_asof(as_of, ...)` REQUIRE an
explicit as_of (no default): a replay analysis can only ever see rows
recorded at or before the simulated point in time, so backtesting a new
strategy against the black box cannot accidentally peek at future
decisions (lookahead-bias block, structural not conventional). The
fail-open pillar applies to RECORDING (trading path); the read-side PIT
guard deliberately RAISES on a missing as_of — it is analysis tooling,
never a trading-path call.

CLI:
  python3 telemetry.py --verify           # schema + triggers + counts
  python3 telemetry.py --stats            # outcomes, decisions, size
  python3 telemetry.py --replay SYMBOL [--date YYYY-MM-DD] [--as-of TS]
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime

AUDIT_LOG_FILE = "logs/audit_trail.log"

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scan_context (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ts               TEXT    NOT NULL,
    ts_epoch         REAL    NOT NULL,
    outcome          TEXT    NOT NULL,
    detail           TEXT    DEFAULT '',
    duration_ms      INTEGER DEFAULT 0,
    universe_size    INTEGER DEFAULT 0,
    post_filter_size INTEGER DEFAULT 0,
    counts           TEXT    DEFAULT '{}',
    fields           TEXT    DEFAULT '{}',
    regime           TEXT    DEFAULT '{}',
    sectors          TEXT    DEFAULT '{}',
    versions         TEXT    DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS decision_snapshot (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id    INTEGER NOT NULL,
    ts         TEXT    NOT NULL,
    ts_epoch   REAL    NOT NULL,
    symbol     TEXT    NOT NULL,
    decision   TEXT    NOT NULL,
    reason     TEXT    DEFAULT '',
    signal     TEXT    DEFAULT '{}',
    context    TEXT    DEFAULT '{}',
    input_bars TEXT    DEFAULT '[]',
    versions   TEXT    DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_decision_symbol_ts ON decision_snapshot(symbol, ts_epoch);
CREATE INDEX IF NOT EXISTS idx_decision_scan      ON decision_snapshot(scan_id);
CREATE INDEX IF NOT EXISTS idx_scan_ts            ON scan_context(ts_epoch);
"""

# Flight-recorder immutability: both tables are append-only. There is no
# compaction story for telemetry (unlike NDSAP bulk-refetch datasets) —
# rows are small and retained forever; if the owner ever wants pruning
# that is a NEW governance decision, not a silent feature.
_TRIGGERS = [
    ("tel_no_del_scan",
     "CREATE TRIGGER IF NOT EXISTS tel_no_del_scan BEFORE DELETE ON scan_context "
     "BEGIN SELECT RAISE(ABORT, 'scan_context is append-only (Rule 16 flight recorder)'); END"),
    ("tel_no_upd_scan",
     "CREATE TRIGGER IF NOT EXISTS tel_no_upd_scan BEFORE UPDATE ON scan_context "
     "BEGIN SELECT RAISE(ABORT, 'scan_context is append-only (Rule 16 flight recorder)'); END"),
    ("tel_no_del_decision",
     "CREATE TRIGGER IF NOT EXISTS tel_no_del_decision BEFORE DELETE ON decision_snapshot "
     "BEGIN SELECT RAISE(ABORT, 'decision_snapshot is append-only (Rule 16 flight recorder)'); END"),
    ("tel_no_upd_decision",
     "CREATE TRIGGER IF NOT EXISTS tel_no_upd_decision BEFORE UPDATE ON decision_snapshot "
     "BEGIN SELECT RAISE(ABORT, 'decision_snapshot is append-only (Rule 16 flight recorder)'); END"),
]


# ─────────────────────────────────────────────
# FAIL-OPEN PLUMBING (pillar 4)
# ─────────────────────────────────────────────

def _audit(line: str) -> None:
    try:
        from utils import append_log
        append_log(AUDIT_LOG_FILE, line)
    except Exception:
        pass


def _enabled() -> bool:
    try:
        from config import TELEMETRY_ENABLED_DEFAULT
        raw = os.getenv("TELEMETRY_ENABLED")
        if raw is not None:
            return raw.strip().lower() in ("1", "true", "yes", "on")
        return bool(TELEMETRY_ENABLED_DEFAULT)
    except Exception:
        return False


def _db_path() -> str:
    try:
        from config import TELEMETRY_DB
        return TELEMETRY_DB
    except Exception:
        return os.path.join("data", "telemetry.db")


def _spread_enabled() -> bool:
    try:
        from config import TELEMETRY_SPREAD_CAPTURE_DEFAULT
        raw = os.getenv("TELEMETRY_SPREAD_CAPTURE")
        if raw is not None:
            return raw.strip().lower() in ("1", "true", "yes", "on")
        return bool(TELEMETRY_SPREAD_CAPTURE_DEFAULT)
    except Exception:
        return False


def _spread_budget() -> int:
    try:
        from config import TELEMETRY_SPREAD_MAX_PER_SCAN_DEFAULT
        return int(os.getenv("TELEMETRY_SPREAD_MAX_PER_SCAN",
                             TELEMETRY_SPREAD_MAX_PER_SCAN_DEFAULT))
    except Exception:
        return 0


def _bars_n() -> int:
    try:
        from config import TELEMETRY_INPUT_BARS_DEFAULT
        return int(os.getenv("TELEMETRY_INPUT_BARS", TELEMETRY_INPUT_BARS_DEFAULT))
    except Exception:
        return 0


def _now():
    try:
        from utils import now_ist
        return now_ist()
    except Exception:
        return datetime.now()


def _connect(path: str | None = None) -> sqlite3.Connection:
    p = path or _db_path()
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    conn = sqlite3.connect(p, timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
    except Exception:
        pass
    return conn


def init_db(path: str | None = None) -> bool:
    """Idempotent schema + append-only trigger creation. Fail-open."""
    try:
        conn = _connect(path)
        try:
            conn.executescript(_SCHEMA)
            for _name, ddl in _TRIGGERS:
                conn.execute(ddl)
            conn.execute(
                "INSERT OR REPLACE INTO telemetry_meta(key, value) VALUES(?, ?)",
                ("schema_version", str(SCHEMA_VERSION)))
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as e:
        _audit(f"TELEMETRY INIT ERROR (fail-open, trading unaffected): {type(e).__name__}: {e}")
        return False


# ─────────────────────────────────────────────
# VERSION STAMPS (deterministic replay pillar)
# ─────────────────────────────────────────────

_VERSION_CACHE: dict | None = None


def version_stamp(strategy_name: str | None = None) -> dict:
    """{revision, params_hash, strategy} — cached per process."""
    global _VERSION_CACHE
    try:
        if _VERSION_CACHE is None:
            import hashlib
            rev = "unknown"
            try:
                with open("VERSION.txt", "r", encoding="utf-8") as f:
                    head = f.readline()
                import re
                m = re.search(r"r(\d+)", head)
                if m:
                    rev = f"r{m.group(1)}"
            except Exception:
                pass
            phash = ""
            try:
                from config import PARAMS
                phash = hashlib.sha256(
                    json.dumps(PARAMS, sort_keys=True, default=str).encode("utf-8")
                ).hexdigest()[:16]
            except Exception:
                pass
            _VERSION_CACHE = {"revision": rev, "params_hash": phash}
        stamp = dict(_VERSION_CACHE)
        if strategy_name:
            stamp["strategy"] = str(strategy_name)
        return stamp
    except Exception:
        return {"revision": "unknown", "params_hash": ""}


def serialize_bars(df, n: int | None = None) -> list:
    """Tail of the completed-bar OHLCV frame actually fed to the strategy.
    Compact rows: [ts, open, high, low, close, volume]. Fail-open -> []."""
    try:
        if df is None:
            return []
        n = _bars_n() if n is None else int(n)
        if n <= 0 or len(df) == 0:
            return []
        tail = df.tail(n)
        out = []
        for ts, row in tail.iterrows():
            def _f(col):
                try:
                    v = row[col]
                    return float(v) if v == v else None  # NaN check
                except Exception:
                    return None
            out.append([str(ts), _f("open"), _f("high"), _f("low"),
                        _f("close"), _f("volume")])
        return out
    except Exception:
        return []


def capture_spread(security_id, exchange_segment: str = "NSE_EQ") -> dict:
    """Best bid/ask + spread from ONE market-depth call. Never raises.
    Raw payload is already PIT-archived by NDSAP (dataset=market_depth);
    this stores the derived numbers only. Budget enforced by ScanTrace."""
    try:
        if not _spread_enabled() or not security_id:
            return {}
        from broker import get_market_depth
        res = get_market_depth(str(security_id), exchange_segment) or {}
        data = res.get("data") if isinstance(res, dict) else None
        if not isinstance(data, dict):
            data = res if isinstance(res, dict) else {}
        bids = data.get("bids") or []
        asks = data.get("asks") or []
        bid = float(bids[0]["price"]) if bids and bids[0].get("price") else None
        ask = float(asks[0]["price"]) if asks and asks[0].get("price") else None
        if bid is None and ask is None:
            return {}
        out = {"bid": bid, "ask": ask, "captured_at": _now().isoformat()}
        if bid is not None and ask is not None:
            out["spread"] = round(ask - bid, 4)
            mid = (ask + bid) / 2.0
            if mid > 0:
                out["spread_pct"] = round((ask - bid) / mid * 100.0, 4)
        return out
    except Exception:
        return {}


# ─────────────────────────────────────────────
# SCAN TRACE (one per run_market_scan call)
# ─────────────────────────────────────────────

class _NullTrace:
    """Inert stand-in when telemetry is disabled or broken."""
    def __getattr__(self, _name):
        def _noop(*_a, **_k):
            return None
        return _noop


_NULL_TRACE = _NullTrace()
_ACTIVE_TRACE = None


class ScanTrace:
    """In-memory collector for ONE scan. Decision rows are buffered and
    written atomically with the scan_context row at finish()/skip() —
    no mid-scan DB load, one transaction per scan."""

    def __init__(self):
        self.t0 = time.monotonic()
        self.counts: dict[str, int] = {}
        self.fields: dict = {}
        self.decisions: list[dict] = []
        self.spread_left = _spread_budget() if _spread_enabled() else 0
        self.finished = False

    # -- collection API (all fail-open) -------------------------------
    def count(self, key: str, n: int = 1) -> None:
        try:
            self.counts[key] = self.counts.get(key, 0) + int(n)
        except Exception:
            pass

    def set(self, key: str, value) -> None:
        try:
            self.fields[key] = value
        except Exception:
            pass

    def decision(self, symbol: str, decision: str, reason: str = "",
                 signal: dict | None = None, context: dict | None = None,
                 bars=None) -> None:
        try:
            self.decisions.append({
                "symbol": str(symbol),
                "decision": str(decision),
                "reason": str(reason or ""),
                "signal": signal if isinstance(signal, dict) else {},
                "context": context if isinstance(context, dict) else {},
                "input_bars": serialize_bars(bars) if bars is not None else [],
            })
        except Exception:
            pass

    def spread_ctx(self, security_id, exchange_segment: str = "NSE_EQ") -> dict:
        """Budgeted spread capture for candidates/entries only."""
        try:
            if self.spread_left <= 0:
                return {}
            self.spread_left -= 1
            return capture_spread(security_id, exchange_segment)
        except Exception:
            return {}

    def skip(self, gate: str, detail: str = "") -> None:
        self._finish(f"SKIP_{gate}", detail)

    def finish(self, outcome: str = "COMPLETED", detail: str = "") -> None:
        self._finish(outcome, detail)

    # -- persistence ---------------------------------------------------
    def _market_context(self) -> tuple[dict, dict]:
        regime, sectors = {}, {}
        try:
            from market_regime import get_market_regime_details
            regime = get_market_regime_details(force_refresh=False) or {}
        except Exception:
            pass
        try:
            from sector_strength import SECTOR_DATA_FILE
            if os.path.exists(SECTOR_DATA_FILE):
                with open(SECTOR_DATA_FILE, "r", encoding="utf-8") as f:
                    sectors = json.load(f) or {}
        except Exception:
            pass
        return regime, sectors

    def _finish(self, outcome: str, detail: str = "") -> None:
        global _ACTIVE_TRACE
        if self.finished:
            return
        self.finished = True
        if _ACTIVE_TRACE is self:
            _ACTIVE_TRACE = None
        if not _enabled():
            return
        try:
            regime, sectors = self._market_context()
            versions = version_stamp(self.fields.get("strategy"))
            now = _now()
            conn = _connect()
            try:
                cur = conn.execute(
                    """INSERT INTO scan_context
                       (ts, ts_epoch, outcome, detail, duration_ms,
                        universe_size, post_filter_size,
                        counts, fields, regime, sectors, versions)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (now.isoformat(), time.time(), str(outcome), str(detail or ""),
                     int((time.monotonic() - self.t0) * 1000),
                     int(self.fields.get("universe_size", 0) or 0),
                     int(self.fields.get("post_filter_size", 0) or 0),
                     json.dumps(self.counts, default=str),
                     json.dumps(self.fields, default=str),
                     json.dumps(regime, default=str)[:65536],
                     json.dumps(sectors, default=str)[:65536],
                     json.dumps(versions, default=str)))
                scan_id = cur.lastrowid
                ts_iso, ts_ep = now.isoformat(), time.time()
                conn.executemany(
                    """INSERT INTO decision_snapshot
                       (scan_id, ts, ts_epoch, symbol, decision, reason,
                        signal, context, input_bars, versions)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    [(scan_id, ts_iso, ts_ep, d["symbol"], d["decision"],
                      d["reason"], json.dumps(d["signal"], default=str),
                      json.dumps(d["context"], default=str),
                      json.dumps(d["input_bars"], default=str),
                      json.dumps(versions, default=str))
                     for d in self.decisions])
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            _audit(f"TELEMETRY WRITE ERROR (fail-open, trading unaffected): "
                   f"{type(e).__name__}: {e}")


def begin_scan() -> ScanTrace:
    """Start a scan trace. NEVER raises; returns an inert trace when
    telemetry is disabled or initialization fails."""
    global _ACTIVE_TRACE
    try:
        if not _enabled():
            return _NULL_TRACE
        init_db()
        trace = ScanTrace()
        _ACTIVE_TRACE = trace
        return trace
    except Exception as e:
        _audit(f"TELEMETRY BEGIN ERROR (fail-open): {type(e).__name__}: {e}")
        return _NULL_TRACE


def current_trace():
    return _ACTIVE_TRACE if _ACTIVE_TRACE is not None else _NULL_TRACE


def record_decision(symbol: str, decision: str, reason: str = "",
                    signal: dict | None = None, context: dict | None = None,
                    bars=None) -> None:
    """Module-level tap for helpers outside run_market_scan
    (_execute_candidate / _execute_entry). No-op without an active trace."""
    try:
        if not _enabled():
            return
        current_trace().decision(symbol, decision, reason=reason,
                                 signal=signal, context=context, bars=bars)
    except Exception:
        pass


def record_spread_context(symbol: str, security_id,
                          exchange_segment: str = "NSE_EQ") -> dict:
    """Budgeted spread capture for code outside the trace object."""
    try:
        if not _enabled():
            return {}
        return current_trace().spread_ctx(security_id, exchange_segment)
    except Exception:
        return {}


# ─────────────────────────────────────────────
# READ / REPLAY / STATS
# ─────────────────────────────────────────────

def read_scans(since: str | None = None, until: str | None = None,
               limit: int = 100, path: str | None = None) -> list[dict]:
    try:
        conn = _connect(path)
        try:
            q = "SELECT * FROM scan_context"
            args: list = []
            conds = []
            if since:
                conds.append("ts >= ?"); args.append(since)
            if until:
                conds.append("ts <= ?"); args.append(until)
            if conds:
                q += " WHERE " + " AND ".join(conds)
            q += " ORDER BY id DESC LIMIT ?"
            args.append(int(limit))
            return [dict(r) for r in conn.execute(q, args).fetchall()]
        finally:
            conn.close()
    except Exception:
        return []


def read_decisions(symbol: str | None = None, decision: str | None = None,
                   since: str | None = None, until: str | None = None,
                   limit: int = 500, path: str | None = None) -> list[dict]:
    try:
        conn = _connect(path)
        try:
            q = "SELECT * FROM decision_snapshot"
            args: list = []
            conds = []
            if symbol:
                conds.append("symbol = ?"); args.append(symbol.upper())
            if decision:
                conds.append("decision = ?"); args.append(decision)
            if since:
                conds.append("ts >= ?"); args.append(since)
            if until:
                conds.append("ts <= ?"); args.append(until)
            if conds:
                q += " WHERE " + " AND ".join(conds)
            q += " ORDER BY id DESC LIMIT ?"
            args.append(int(limit))
            return [dict(r) for r in conn.execute(q, args).fetchall()]
        finally:
            conn.close()
    except Exception:
        return []


def _asof_normalize(as_of) -> str:
    """Normalize an as_of value for lexicographic ISO comparison.
    Date-only ('YYYY-MM-DD') includes the whole day (IST local stamps)."""
    if as_of is None:
        raise ValueError("as_of is required (PIT guard — no default)")
    s = str(as_of).strip()
    if not s:
        raise ValueError("as_of is required (PIT guard — no default)")
    if len(s) == 10:  # date-only → end of that day
        s = s + "T23:59:59.999999"
    return s


def read_asof(as_of, symbol: str | None = None, decision: str | None = None,
              limit: int = 500, path: str | None = None) -> list[dict]:
    """PIT decision read: ONLY rows recorded at or before `as_of`.
    as_of is REQUIRED (positional, no default) — structural lookahead-bias
    guard, same discipline as ndsap_archive.read_asof. Raises ValueError
    on missing as_of (analysis-side strictness; recording stays fail-open)."""
    cutoff = _asof_normalize(as_of)  # raises before any DB touch if missing
    try:
        conn = _connect(path)
        try:
            q = "SELECT * FROM decision_snapshot WHERE ts <= ?"
            args: list = [cutoff]
            if symbol:
                q += " AND symbol = ?"; args.append(symbol.upper())
            if decision:
                q += " AND decision = ?"; args.append(decision)
            q += " ORDER BY id DESC LIMIT ?"
            args.append(int(limit))
            return [dict(r) for r in conn.execute(q, args).fetchall()]
        finally:
            conn.close()
    except ValueError:
        raise
    except Exception:
        return []


def read_scans_asof(as_of, limit: int = 100, path: str | None = None) -> list[dict]:
    """PIT scan-context read: ONLY scans recorded at or before `as_of`.
    as_of REQUIRED — same structural guard as read_asof."""
    cutoff = _asof_normalize(as_of)
    try:
        conn = _connect(path)
        try:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM scan_context WHERE ts <= ? ORDER BY id DESC LIMIT ?",
                (cutoff, int(limit))).fetchall()]
        finally:
            conn.close()
    except ValueError:
        raise
    except Exception:
        return []


def stats(path: str | None = None) -> dict:
    try:
        p = path or _db_path()
        out: dict = {"db_path": p, "db_exists": os.path.exists(p)}
        if not out["db_exists"]:
            return out
        out["db_bytes"] = os.path.getsize(p)
        conn = _connect(p)
        try:
            out["scan_rows"] = conn.execute(
                "SELECT COUNT(*) FROM scan_context").fetchone()[0]
            out["decision_rows"] = conn.execute(
                "SELECT COUNT(*) FROM decision_snapshot").fetchone()[0]
            out["outcomes"] = {r[0]: r[1] for r in conn.execute(
                "SELECT outcome, COUNT(*) FROM scan_context GROUP BY outcome")}
            out["decisions"] = {r[0]: r[1] for r in conn.execute(
                "SELECT decision, COUNT(*) FROM decision_snapshot GROUP BY decision")}
            first = conn.execute(
                "SELECT MIN(ts), MAX(ts) FROM scan_context").fetchone()
            out["first_scan_ts"], out["last_scan_ts"] = first[0], first[1]
            trg = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
                "AND name LIKE 'tel_no_%'").fetchone()[0]
            out["immutability_triggers"] = trg
        finally:
            conn.close()
        return out
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def verify(path: str | None = None) -> tuple[bool, list[str]]:
    problems: list[str] = []
    try:
        p = path or _db_path()
        if not os.path.exists(p):
            problems.append(f"telemetry db missing: {p}")
            return False, problems
        conn = _connect(p)
        try:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            for t in ("scan_context", "decision_snapshot", "telemetry_meta"):
                if t not in tables:
                    problems.append(f"missing table: {t}")
            trg = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'")}
            for name, _ddl in _TRIGGERS:
                if name not in trg:
                    problems.append(f"missing immutability trigger: {name}")
            sv = conn.execute(
                "SELECT value FROM telemetry_meta WHERE key='schema_version'"
            ).fetchone()
            if not sv or sv[0] != str(SCHEMA_VERSION):
                problems.append(f"schema_version mismatch: {sv[0] if sv else None}")
        finally:
            conn.close()
    except Exception as e:
        problems.append(f"verify error: {type(e).__name__}: {e}")
    return (not problems), problems


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def _cli() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="QASWA telemetry black box (Rule 16) — verify/stats/replay")
    parser.add_argument("--verify", action="store_true",
                        help="schema + immutability triggers + row counts")
    parser.add_argument("--stats", action="store_true",
                        help="outcome/decision counts + db size")
    parser.add_argument("--replay", metavar="SYMBOL", default=None,
                        help="dump every decision row for a symbol")
    parser.add_argument("--date", metavar="YYYY-MM-DD", default=None,
                        help="restrict --replay to one trading day (IST)")
    parser.add_argument("--as-of", metavar="TS", default=None, dest="as_of",
                        help="PIT guard: only rows recorded at or before TS")
    parser.add_argument("--db", metavar="PATH", default=None,
                        help="telemetry db path (default: config.TELEMETRY_DB)")
    args = parser.parse_args()

    if args.verify or not (args.stats or args.replay):
        ok, problems = verify(args.db)
        st = stats(args.db)
        print(f"TELEMETRY VERIFY: {'PASS' if ok else 'FAIL'}")
        for k in ("db_path", "db_bytes", "scan_rows", "decision_rows",
                  "immutability_triggers", "first_scan_ts", "last_scan_ts"):
            if k in st:
                print(f"  {k}: {st[k]}")
        for p in problems:
            print(f"  PROBLEM: {p}")
        if not ok:
            return 1

    if args.stats:
        st = stats(args.db)
        print("\nOUTCOMES:")
        for k, v in sorted(st.get("outcomes", {}).items(),
                           key=lambda kv: -kv[1]):
            print(f"  {k}: {v}")
        print("DECISIONS:")
        for k, v in sorted(st.get("decisions", {}).items(),
                           key=lambda kv: -kv[1]):
            print(f"  {k}: {v}")

    if args.replay:
        since = until = None
        if args.date:
            since, until = f"{args.date}T00:00:00", f"{args.date}T23:59:59"
        if args.as_of:
            rows = read_asof(args.as_of, symbol=args.replay, limit=1000,
                             path=args.db)
            scans = {s["id"]: s for s in read_scans_asof(args.as_of, limit=5000,
                                                        path=args.db)}
        else:
            rows = read_decisions(symbol=args.replay, since=since, until=until,
                                  limit=1000, path=args.db)
            scans = {s["id"]: s for s in read_scans(limit=5000, path=args.db)}
        print(f"\nREPLAY {args.replay.upper()}: {len(rows)} decision row(s)")
        for r in reversed(rows):
            sc = scans.get(r["scan_id"], {})
            print(f"\n  [{r['ts']}] {r['decision']}  (scan #{r['scan_id']} "
                  f"outcome={sc.get('outcome', '?')})")
            if r["reason"]:
                print(f"    reason: {r['reason']}")
            for key in ("signal", "context"):
                try:
                    payload = json.loads(r[key] or "{}")
                except Exception:
                    payload = {}
                if payload:
                    print(f"    {key}: {json.dumps(payload, ensure_ascii=False)}")
            try:
                bars = json.loads(r["input_bars"] or "[]")
            except Exception:
                bars = []
            if bars:
                print(f"    input_bars: {len(bars)} bars "
                      f"({bars[0][0]} .. {bars[-1][0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
