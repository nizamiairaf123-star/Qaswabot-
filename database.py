import sqlite3
import json
import logging
from config import DATA_DIR
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(DATA_DIR, "trading_bot.db")
# [PHD-FIX Section-47 DB-failure] Out-of-band marker file (deliberately NOT
# stored via db_save/db_load — if the DB itself is what's failing, recording
# the failure THROUGH the DB would silently swallow it, same bug again).
_DB_FAILURE_MARKER = os.path.join(DATA_DIR, "db_failure_state.txt")

def _record_db_failure(context: str):
    """Best-effort plain-file marker so callers (e.g. the entry gate) can
    detect 'the DB just failed' without depending on the DB itself."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(_DB_FAILURE_MARKER, "w") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} | {context}\n")
    except Exception:
        pass  # best-effort only — never let the failure-recorder itself raise

def _clear_db_failure():
    try:
        if os.path.exists(_DB_FAILURE_MARKER):
            os.remove(_DB_FAILURE_MARKER)
    except Exception:
        pass

def is_db_failure_recent(within_seconds: int = 300) -> bool:
    """[PHD-FIX Section-47] True if a DB read/write failed within the last
    `within_seconds`. Mirrors the existing is_network_partition() pattern —
    a plain out-of-band flag the entry gate checks before scanning, so a DB
    failure produces SAFE STOP (new entries blocked) instead of every
    individual caller silently trusting its own default on failure."""
    try:
        if not os.path.exists(_DB_FAILURE_MARKER):
            return False
        with open(_DB_FAILURE_MARKER) as f:
            line = f.read().strip()
        ts_str = line.split(" | ")[0]
        ts = datetime.fromisoformat(ts_str)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age <= within_seconds
    except Exception:
        # Can't parse the marker itself -> treat as failure still active
        # (fail-closed), don't silently say "no failure".
        return True

def _get_connection():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            # Simple Key-Value store to replace JSON files easily
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS key_value_store (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            ''')
            conn.commit()
            logger.info("SQLite database initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")


# AUDIT FIX: previously this only ran when bot.py explicitly called it at
# startup -- any other entry point (a test, a standalone script, a future
# admin CLI tool) that imported database.py without also importing bot.py
# would hit "no such table: key_value_store" on first use. init_db() is
# idempotent (CREATE TABLE IF NOT EXISTS), so it's safe to run here,
# unconditionally, once per process, the moment this module is imported.
init_db()

def db_save(key: str, data: dict) -> bool:
    """Saves a dictionary as a JSON string under the given key.
    Returns True on success, False on failure -- AUDIT FIX: callers (notably
    the legacy-JSON migration in utils.py) need to know if the save actually
    happened before treating the old data as safely persisted."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            json_str = json.dumps(data)
            cursor.execute('''
                INSERT INTO key_value_store (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
            ''', (key, json_str))
            conn.commit()
        _clear_db_failure()
        return True
    except Exception as e:
        logger.error(f"Failed to save {key} to db: {e}")
        _record_db_failure(f"db_save failed for key={key}: {e}")
        return False

def db_load(key: str, default=None):
    """Loads a JSON string for the given key and returns a dictionary."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM key_value_store WHERE key = ?', (key,))
            row = cursor.fetchone()
            _clear_db_failure()
            if row:
                return json.loads(row['value'])
            return default if default is not None else {}
    except Exception as e:
        # [PHD-FIX Section-47] Still fail-open on the RETURN VALUE here
        # (changing every one of ~40 load_json() callers' return contract
        # would be a much larger, riskier change than this specific defect
        # requires) — but now ALSO records the failure out-of-band so the
        # entry gate (trade_engine.run_market_scan, same place that already
        # checks the killswitch and network-partition flags) can detect it
        # and produce the frozen-criteria-required SAFE STOP for new entries,
        # instead of every caller silently trusting a possibly-wrong default.
        logger.error(f"DB_LOAD_FAILURE (recording out-of-band, returning default to this caller) for key={key}: {e}")
        _record_db_failure(f"db_load failed for key={key}: {e}")
        return default if default is not None else {}
