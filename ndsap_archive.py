"""
ndsap_archive.py — NDSAP Part C: Live Data Accumulation Archive

[Method: NIZAMI Data Segregation & Accumulation Protocol (NDSAP) —
 AIRAF NIZAMI (owner-original method, no pre-existing external methodology
 claimed or invented). Registered 2026-09-08 as "Live Data Accumulation",
 refined 2026-09-13 — prd.md Rule 15, SYSTEM_BLUEPRINT.md §9,
 QASWA_AUDIT_QA_STATUS.md Q037. Owner implementation authorization for
 Part C: 2026-09-13. Part B remains REGISTERED-NOT-IMPLEMENTED (ToS
 pre-implementation blocker open) — its tap point exists here behind a
 provider allowlist that defaults to Dhan-only.]

Immutable, append-only, timestamped archive of every live data point QASWA
actually receives, in its OWN SQLite file (data/ndsap_archive.db) — separate
from key_value_store per Rule 15 (C) — written BEFORE any transformation,
via read-only taps at the ingestion points (dhan_data.py, broker.py,
market_metadata.py). Additive: never sits in or alters the trade-decision
path; every tap is fail-soft (archive failure is audit-logged, never raised
into a caller).

Each record carries the Rule 15 (C) fields (a)-(g):
  (a) raw_payload          exact provider payload, unmodified (canonical JSON)
  (b) arrival_ts/epoch     QASWA's own UTC arrival time (NOT the provider's)
  (c) event_ts             provider-claimed event timestamp, kept SEPARATE
                           (NULL when the provider claims none — never guessed)
  (d) symbol, exchange     (+ security_id when that is all the caller has)
  (e) provider, provider_api_version
  (f) seq                  monotonic sequence number (SQLite AUTOINCREMENT)
  (g) content_hash         SHA-256 of the canonical payload — tamper and
                           duplicate detection

Immutability is enforced STRUCTURALLY (SQLite triggers), not by convention:
DELETE is prohibited; UPDATE is only permitted for the documented retention
compaction (payload expiry: raw_payload→NULL + payload_state→
'expired_by_compaction', all identity fields untouched). Metadata rows and
content hashes are NEVER removed — the arrival/hash trail survives payload
expiry.

As-of guard (structural, query-layer): read_asof() REQUIRES an as_of
argument (no default) and only ever returns rows with arrival ≤ as_of.
A future backtest reading through this API cannot see data that had not
arrived at the simulated date. The archive does NOT retroactively create
history for any period before deployment — that gap remains a known,
disclosed limitation (prd.md Rule 15 C).

Retention/compaction policy: derived from the per-field volume/growth
estimate in NDSAP_RETENTION_ESTIMATE.md (a required Rule 15 deliverable),
not an arbitrary duration — bulk-refetch datasets (historical_daily,
intraday_minute) compact via compact_superseded(keep_last=N); incremental
datasets (ohlc_live, market_depth, market_metadata) are retained in full.
"""

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone

from config import (
    AUDIT_LOG_FILE,
    NDSAP_ARCHIVE_DB,
    NDSAP_ARCHIVE_ENABLED_DEFAULT,
    NDSAP_ARCHIVE_PROVIDERS_DEFAULT,
    NDSAP_COMPACT_KEEP_LAST_DEFAULT,
    PARAMS,
)
from utils import append_log

logger = logging.getLogger(__name__)

# Test hook: tests point this at a temp dir; production leaves it None.
DB_PATH_OVERRIDE = None

# Datasets whose payloads are bulk re-fetches of overlapping history —
# eligible for superseded-payload compaction (see module docstring).
BULK_DATASETS = ("historical_daily", "intraday_minute")


def _db_path() -> str:
    if DB_PATH_OVERRIDE:
        return os.path.join(DB_PATH_OVERRIDE, "ndsap_archive.db")
    return NDSAP_ARCHIVE_DB


def _utcnow():
    return datetime.now(timezone.utc)


def _to_epoch(value) -> float:
    """Normalize datetime / ISO string to a UTC epoch float.

    Naive datetimes are interpreted as UTC (archive timestamps are UTC by
    Rule 15 (C)(b)); 'Z' suffix accepted.
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    if isinstance(value, str):
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    raise TypeError(f"as_of must be datetime/ISO-string/epoch, got {type(value).__name__}")


def _canonical_json(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      default=str, ensure_ascii=False)


def _connect() -> sqlite3.Connection:
    path = _db_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_archive_db():
    """Idempotent schema creation — safe to call repeatedly."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS archive (
                seq                  INTEGER PRIMARY KEY AUTOINCREMENT,
                arrival_ts           TEXT    NOT NULL,
                arrival_epoch        REAL    NOT NULL,
                provider             TEXT    NOT NULL,
                provider_api_version TEXT,
                dataset              TEXT    NOT NULL,
                symbol               TEXT,
                exchange             TEXT,
                security_id          TEXT,
                event_ts             TEXT,
                raw_payload          TEXT,
                content_hash         TEXT    NOT NULL,
                payload_state        TEXT    NOT NULL DEFAULT 'full'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_archive_arrival "
                     "ON archive(arrival_epoch)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_archive_symbol_dataset "
                     "ON archive(symbol, dataset)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS compaction_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_ts          TEXT NOT NULL,
                datasets        TEXT NOT NULL,
                keep_last       INTEGER NOT NULL,
                records_expired INTEGER NOT NULL
            )
        """)
        # ── Structural immutability (Rule 15 C: "immutable, append-only") ──
        conn.execute("DROP TRIGGER IF EXISTS ndsap_no_delete")
        conn.execute("""
            CREATE TRIGGER ndsap_no_delete
            BEFORE DELETE ON archive
            BEGIN
                SELECT RAISE(ABORT,
                  'NDSAP: archive is append-only — DELETE prohibited (prd.md Rule 15 C)');
            END
        """)
        conn.execute("DROP TRIGGER IF EXISTS ndsap_immutable_except_compaction")
        conn.execute("""
            CREATE TRIGGER ndsap_immutable_except_compaction
            BEFORE UPDATE ON archive
            FOR EACH ROW
            WHEN NOT (
                     NEW.raw_payload IS NULL
                 AND NEW.payload_state = 'expired_by_compaction'
                 AND OLD.payload_state = 'full'
                 AND NEW.content_hash IS OLD.content_hash
                 AND NEW.arrival_ts IS OLD.arrival_ts
                 AND NEW.arrival_epoch = OLD.arrival_epoch
                 AND NEW.provider IS OLD.provider
                 AND NEW.dataset IS OLD.dataset
                 AND NEW.symbol IS OLD.symbol
                 AND NEW.exchange IS OLD.exchange
                 AND NEW.event_ts IS OLD.event_ts
            )
            BEGIN
                SELECT RAISE(ABORT,
                  'NDSAP: archive rows are immutable except documented payload-expiry compaction');
            END
        """)
        conn.commit()
        conn.execute("PRAGMA journal_mode=WAL")


def _enabled() -> bool:
    try:
        return bool(PARAMS.get("ndsap_archive_enabled",
                               NDSAP_ARCHIVE_ENABLED_DEFAULT))
    except (AttributeError, TypeError):
        return NDSAP_ARCHIVE_ENABLED_DEFAULT


def _providers_allowed() -> set:
    try:
        allowed = PARAMS.get("ndsap_archive_providers",
                             NDSAP_ARCHIVE_PROVIDERS_DEFAULT)
        return {str(p).lower() for p in allowed}
    except (AttributeError, TypeError):
        return {str(p).lower() for p in NDSAP_ARCHIVE_PROVIDERS_DEFAULT}


def _auto_api_version(provider: str) -> str:
    dist = {"dhan": "dhanhq", "yfinance": "yfinance"}.get(provider.lower())
    if dist:
        try:
            from importlib.metadata import version
            return f"{dist} {version(dist)}"
        except Exception:
            return f"{dist} (version unknown)"
    return "unknown"


def archive_record(payload, provider: str, dataset: str, symbol=None,
                   exchange=None, security_id=None, event_ts=None,
                   provider_api_version=None):
    """Append one received payload to the archive. Returns seq, or None.

    FAIL-SOFT BY DESIGN: this is an observation tap, never part of the
    trade-decision path — any problem (gate off, provider not allowed,
    unserializable payload, DB error) is audit-logged and returns None
    instead of raising into the caller.

    Provider gate: only providers in ndsap_archive_providers (default:
    ['dhan']) are archived. yfinance/NSE/Moneycontrol stay OFF until the
    Rule 15 ToS pre-implementation blocker is cleared by the owner.
    """
    try:
        if not _enabled():
            return None
        if str(provider).lower() not in _providers_allowed():
            return None  # gated off (ToS blocker) — silent by design, no data stored
        init_archive_db()
        canonical = _canonical_json(payload)
        content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        now = _utcnow()
        if isinstance(event_ts, datetime):
            event_ts = event_ts.isoformat()
        with _connect() as conn:
            cur = conn.execute(
                """INSERT INTO archive
                   (arrival_ts, arrival_epoch, provider, provider_api_version,
                    dataset, symbol, exchange, security_id, event_ts,
                    raw_payload, content_hash, payload_state)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?, 'full')""",
                (now.isoformat(), now.timestamp(), str(provider).lower(),
                 provider_api_version or _auto_api_version(provider),
                 dataset, symbol, exchange,
                 None if security_id is None else str(security_id),
                 event_ts, canonical, content_hash))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        try:
            append_log(AUDIT_LOG_FILE,
                       f"NDSAP ARCHIVE ERROR ({provider}/{dataset}"
                       f"{':' + str(symbol) if symbol else ''}): "
                       f"{type(e).__name__}: {e}")
        except Exception:
            logger.error("NDSAP archive failure could not be logged: %s", e)
        return None


def read_asof(as_of, symbol=None, dataset=None, provider=None,
              include_expired=False, limit=None):
    """The ONLY backtest-facing read API — structural as-of guard.

    as_of is REQUIRED (no default): a backtest cannot accidentally read
    'everything'. Only rows with arrival_epoch ≤ as_of are visible; rows
    that arrived after the simulated date do not exist for this query.
    Naive datetimes are interpreted as UTC. Returns list of dicts.
    """
    cutoff = _to_epoch(as_of)
    init_archive_db()
    sql = "SELECT * FROM archive WHERE arrival_epoch <= ?"
    args = [cutoff]
    if symbol is not None:
        sql += " AND symbol = ?"
        args.append(symbol)
    if dataset is not None:
        sql += " AND dataset = ?"
        args.append(dataset)
    if provider is not None:
        sql += " AND provider = ?"
        args.append(str(provider).lower())
    if not include_expired:
        sql += " AND payload_state = 'full'"
    sql += " ORDER BY arrival_epoch, seq"
    if limit is not None:
        sql += " LIMIT ?"
        args.append(int(limit))
    with _connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("raw_payload") is not None:
            try:
                d["payload"] = json.loads(d["raw_payload"])
            except (json.JSONDecodeError, TypeError):
                d["payload"] = None
        else:
            d["payload"] = None
        out.append(d)
    return out


def count_records() -> int:
    init_archive_db()
    with _connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM archive").fetchone()[0])


def latest_seq():
    init_archive_db()
    with _connect() as conn:
        row = conn.execute("SELECT MAX(seq) FROM archive").fetchone()
        return row[0]


def find_duplicates():
    """Groups of records sharing a content_hash (Rule 15 (C)(g) duplicate
    detection). Returns list of {content_hash, symbol, dataset, count, seqs}."""
    init_archive_db()
    with _connect() as conn:
        rows = conn.execute(
            """SELECT content_hash, symbol, dataset, COUNT(*) AS n,
                      GROUP_CONCAT(seq) AS seqs
               FROM archive GROUP BY content_hash, symbol, dataset
               HAVING n > 1 ORDER BY n DESC""").fetchall()
    return [{"content_hash": r["content_hash"], "symbol": r["symbol"],
             "dataset": r["dataset"], "count": r["n"],
             "seqs": [int(x) for x in str(r["seqs"]).split(",")]}
            for r in rows]


def verify_archive():
    """Tamper detection: recompute SHA-256 of every non-expired payload and
    compare against the stored content_hash. Also flags broken seq
    monotonicity. Returns {'checked': n, 'tampered': [...], 'ok': bool}."""
    init_archive_db()
    tampered = []
    checked = 0
    prev_seq = 0
    with _connect() as conn:
        rows = conn.execute(
            "SELECT seq, raw_payload, content_hash, payload_state "
            "FROM archive ORDER BY seq").fetchall()
    for r in rows:
        if r["seq"] <= prev_seq:
            tampered.append({"seq": r["seq"], "problem": "seq not monotonic"})
        prev_seq = r["seq"]
        if r["payload_state"] != "full":
            continue
        checked += 1
        actual = hashlib.sha256(
            (r["raw_payload"] or "").encode("utf-8")).hexdigest()
        if actual != r["content_hash"]:
            tampered.append({"seq": r["seq"], "problem": "hash mismatch"})
    return {"checked": checked, "tampered": tampered,
            "ok": len(tampered) == 0}


def compact_superseded(datasets=BULK_DATASETS, keep_last=None):
    """Retention policy implementation (Rule 15 retention requirement).

    For bulk-refetch datasets only: per (symbol, exchange, provider,
    dataset) group, keep the `keep_last` most recent FULL payloads and
    expire older ones (raw_payload → NULL, payload_state →
    'expired_by_compaction'). Identity fields, arrival timestamps, seq and
    content hashes are preserved forever — the trigger above rejects any
    other mutation. Every run is written to compaction_log and the audit
    log. NOT automatic: an explicit maintenance operation.
    """
    keep = int(keep_last if keep_last is not None
               else PARAMS.get("ndsap_compact_keep_last",
                               NDSAP_COMPACT_KEEP_LAST_DEFAULT))
    keep = max(1, keep)
    init_archive_db()
    expired_total = 0
    with _connect() as conn:
        groups = conn.execute(
            """SELECT DISTINCT symbol, exchange, provider, dataset
               FROM archive
               WHERE dataset IN ({}) AND payload_state = 'full'""".format(
                ",".join("?" * len(datasets))), tuple(datasets)).fetchall()
        for g in groups:
            rows = conn.execute(
                """SELECT seq FROM archive
                   WHERE symbol IS ? AND exchange IS ? AND provider IS ?
                     AND dataset = ? AND payload_state = 'full'
                   ORDER BY arrival_epoch DESC, seq DESC""",
                (g["symbol"], g["exchange"], g["provider"],
                 g["dataset"])).fetchall()
            victims = [r["seq"] for r in rows[keep:]]
            for seq in victims:
                conn.execute(
                    """UPDATE archive
                       SET raw_payload = NULL,
                           payload_state = 'expired_by_compaction'
                       WHERE seq = ?""", (seq,))
                expired_total += 1
        now = _utcnow()
        conn.execute(
            "INSERT INTO compaction_log (run_ts, datasets, keep_last, records_expired) "
            "VALUES (?,?,?,?)",
            (now.isoformat(), ",".join(datasets), keep, expired_total))
        conn.commit()
    append_log(AUDIT_LOG_FILE,
               f"NDSAP COMPACTION: datasets={','.join(datasets)} "
               f"keep_last={keep} payloads_expired={expired_total} "
               f"(metadata+hashes retained — append-only preserved)")
    return {"expired": expired_total, "keep_last": keep,
            "datasets": list(datasets)}


def archive_stats():
    """Per-dataset record/payload counts and on-disk size — for the
    retention review cycle (NDSAP_RETENTION_ESTIMATE.md)."""
    init_archive_db()
    with _connect() as conn:
        rows = conn.execute(
            """SELECT dataset, payload_state, COUNT(*) AS n,
                      COALESCE(SUM(LENGTH(raw_payload)), 0) AS bytes
               FROM archive GROUP BY dataset, payload_state
               ORDER BY dataset, payload_state""").fetchall()
    db_bytes = 0
    try:
        db_bytes = os.path.getsize(_db_path())
    except OSError:
        pass
    return {"by_dataset": [dict(r) for r in rows],
            "db_file_bytes": db_bytes}


if __name__ == "__main__":
    # Ops entry point — retention policy operations are EXPLICIT (never
    # automatic): python ndsap_archive.py --verify | --stats | --compact
    import argparse
    parser = argparse.ArgumentParser(
        description="NDSAP Part C archive maintenance (prd.md Rule 15)")
    parser.add_argument("--verify", action="store_true",
                        help="recompute payload hashes, report tamper")
    parser.add_argument("--stats", action="store_true",
                        help="per-dataset counts and disk usage")
    parser.add_argument("--compact", action="store_true",
                        help="expire superseded bulk-refetch payloads "
                             "(metadata+hashes retained)")
    parser.add_argument("--keep-last", type=int, default=None,
                        help="full payloads to keep per symbol/dataset "
                             "(default: config NDSAP_COMPACT_KEEP_LAST_DEFAULT)")
    args = parser.parse_args()

    if args.verify:
        print(json.dumps(verify_archive(), indent=2))
    if args.stats:
        print(json.dumps(archive_stats(), indent=2))
    if args.compact:
        print(json.dumps(compact_superseded(keep_last=args.keep_last), indent=2))
    if not (args.verify or args.stats or args.compact):
        parser.print_help()
