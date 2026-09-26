"""
test_ndsap_archive.py — NDSAP Part C archive tests (prd.md Rule 15)

Offline, deterministic: temp-dir DB via DB_PATH_OVERRIDE, no network,
no real Dhan/yfinance calls. Structural guarantees tested:
immutability triggers, as-of query guard, provider gate, fail-soft tap,
compaction policy, tamper detection, and one integration test that the
dhan_data.fetch_daily_data tap archives the RAW payload pre-transformation.
"""

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
import ndsap_archive


class NdsapTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ndsap_test_")
        ndsap_archive.DB_PATH_OVERRIDE = self.tmp
        self._saved_params = {
            k: config.PARAMS.get(k) for k in
            ("ndsap_archive_enabled", "ndsap_archive_providers",
             "ndsap_compact_keep_last")
        }
        self._audit = os.path.join(self.tmp, "audit.txt")
        self._saved_audit = ndsap_archive.AUDIT_LOG_FILE
        ndsap_archive.AUDIT_LOG_FILE = self._audit

    def tearDown(self):
        ndsap_archive.DB_PATH_OVERRIDE = None
        ndsap_archive.AUDIT_LOG_FILE = self._saved_audit
        for k, v in self._saved_params.items():
            if v is None:
                config.PARAMS.pop(k, None)
            else:
                config.PARAMS[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def audit_text(self):
        try:
            with open(self._audit) as f:
                return f.read()
        except FileNotFoundError:
            return ""


class TestArchiveCore(NdsapTestBase):
    def test_append_seq_monotonic_and_rule15_fields(self):
        payload = {"status": "success", "data": [{"open": 1.0, "close": 2.0}]}
        s1 = ndsap_archive.archive_record(
            payload, provider="dhan", dataset="historical_daily",
            symbol="RELIANCE", exchange="NSE_EQ", security_id="1337",
            event_ts="2026-09-12T15:30:00+05:30")
        s2 = ndsap_archive.archive_record(
            payload, provider="dhan", dataset="historical_daily",
            symbol="RELIANCE", exchange="NSE_EQ")
        self.assertIsNotNone(s1)
        self.assertIsNotNone(s2)
        self.assertGreater(s2, s1)  # (f) monotonic sequence
        self.assertEqual(ndsap_archive.latest_seq(), s2)
        self.assertEqual(ndsap_archive.count_records(), 2)

        rows = ndsap_archive.read_asof(datetime.now(timezone.utc) + timedelta(minutes=1))
        self.assertEqual(len(rows), 2)
        r = rows[0]
        # Rule 15 (C) fields (a)-(g):
        self.assertEqual(r["payload"], payload)                  # (a) unmodified
        self.assertIn("+00:00", r["arrival_ts"])                 # (b) UTC arrival
        self.assertEqual(r["event_ts"], "2026-09-12T15:30:00+05:30")  # (c) separate
        self.assertEqual(r["symbol"], "RELIANCE")                # (d)
        self.assertEqual(r["exchange"], "NSE_EQ")
        self.assertEqual(r["security_id"], "1337")
        self.assertEqual(r["provider"], "dhan")                  # (e)
        self.assertTrue(r["provider_api_version"].startswith("dhanhq"))
        self.assertEqual(r["seq"], s1)                           # (f)
        self.assertEqual(len(r["content_hash"]), 64)             # (g)
        self.assertIsNone(rows[1]["event_ts"])  # never guessed when absent

    def test_content_hash_and_duplicate_detection(self):
        p = {"a": 1, "b": [1, 2, 3]}
        ndsap_archive.archive_record(p, provider="dhan", dataset="ohlc_live", symbol="X")
        ndsap_archive.archive_record(p, provider="dhan", dataset="ohlc_live", symbol="X")
        ndsap_archive.archive_record({"a": 2}, provider="dhan", dataset="ohlc_live", symbol="X")
        dups = ndsap_archive.find_duplicates()
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0]["count"], 2)
        rep = ndsap_archive.verify_archive()
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["checked"], 3)

    def test_asof_guard_structural(self):
        ndsap_archive.archive_record({"v": 1}, provider="dhan",
                                     dataset="ohlc_live", symbol="X")
        now = datetime.now(timezone.utc)
        # future cutoff sees it; past cutoff does not
        self.assertEqual(len(ndsap_archive.read_asof(now + timedelta(hours=1))), 1)
        self.assertEqual(len(ndsap_archive.read_asof(now - timedelta(hours=1))), 0)
        # as_of is REQUIRED — no default (structural, not convention)
        with self.assertRaises(TypeError):
            ndsap_archive.read_asof()
        # ISO-string and naive-datetime (UTC) forms accepted
        self.assertEqual(len(ndsap_archive.read_asof(
            (now + timedelta(hours=1)).isoformat())), 1)
        naive_utc_plus_1h = datetime.utcnow() + timedelta(hours=1)
        self.assertEqual(len(ndsap_archive.read_asof(naive_utc_plus_1h)), 1)

    def test_delete_prohibited_by_trigger(self):
        ndsap_archive.archive_record({"v": 1}, provider="dhan",
                                     dataset="ohlc_live", symbol="X")
        with self.assertRaises(sqlite3.IntegrityError):
            with ndsap_archive._connect() as conn:
                conn.execute("DELETE FROM archive WHERE seq = 1")

    def test_update_prohibited_except_compaction(self):
        ndsap_archive.archive_record({"v": 1}, provider="dhan",
                                     dataset="ohlc_live", symbol="X")
        with self.assertRaises(sqlite3.IntegrityError):
            with ndsap_archive._connect() as conn:
                conn.execute("UPDATE archive SET content_hash = 'deadbeef' WHERE seq = 1")
        with self.assertRaises(sqlite3.IntegrityError):
            with ndsap_archive._connect() as conn:
                conn.execute("UPDATE archive SET raw_payload = '{\"v\": 999}' WHERE seq = 1")
        with self.assertRaises(sqlite3.IntegrityError):
            with ndsap_archive._connect() as conn:
                conn.execute("UPDATE archive SET arrival_epoch = arrival_epoch - 99999 WHERE seq = 1")

    def test_verify_detects_tamper(self):
        ndsap_archive.archive_record({"v": 1}, provider="dhan",
                                     dataset="ohlc_live", symbol="X")
        self.assertTrue(ndsap_archive.verify_archive()["ok"])
        # Simulate an attacker/corruption BELOW the API: drop triggers, tamper.
        with ndsap_archive._connect() as conn:
            conn.execute("DROP TRIGGER ndsap_immutable_except_compaction")
            conn.execute("UPDATE archive SET raw_payload = '{\"v\": 666}' WHERE seq = 1")
        rep = ndsap_archive.verify_archive()
        self.assertFalse(rep["ok"])
        self.assertEqual(rep["tampered"][0]["problem"], "hash mismatch")


class TestCompaction(NdsapTestBase):
    def test_compact_superseded_keeps_latest_metadata_forever(self):
        for i in range(3):
            ndsap_archive.archive_record(
                {"candles": i}, provider="dhan", dataset="historical_daily",
                symbol="TATASTEEL", exchange="NSE_EQ")
        res = ndsap_archive.compact_superseded(keep_last=1)
        self.assertEqual(res["expired"], 2)

        now = datetime.now(timezone.utc) + timedelta(minutes=1)
        full = ndsap_archive.read_asof(now, symbol="TATASTEEL")
        self.assertEqual(len(full), 1)
        self.assertEqual(full[0]["payload"], {"candles": 2})  # latest kept

        allrows = ndsap_archive.read_asof(now, symbol="TATASTEEL",
                                          include_expired=True)
        self.assertEqual(len(allrows), 3)  # metadata rows never removed
        expired = [r for r in allrows if r["payload_state"] == "expired_by_compaction"]
        self.assertEqual(len(expired), 2)
        for r in expired:
            self.assertIsNone(r["payload"])
            self.assertEqual(len(r["content_hash"]), 64)  # hash trail intact
        self.assertIn("NDSAP COMPACTION", self.audit_text())
        with ndsap_archive._connect() as conn:
            n = conn.execute("SELECT COUNT(*) FROM compaction_log").fetchone()[0]
        self.assertEqual(n, 1)

    def test_incremental_datasets_not_compacted(self):
        for i in range(3):
            ndsap_archive.archive_record({"p": i}, provider="dhan",
                                         dataset="ohlc_live", symbol="X")
        res = ndsap_archive.compact_superseded(keep_last=1)
        self.assertEqual(res["expired"], 0)
        self.assertEqual(ndsap_archive.count_records(), 3)


class TestGates(NdsapTestBase):
    def test_provider_gate_yfinance_off_by_default(self):
        seq = ndsap_archive.archive_record(
            {"sector": "Energy"}, provider="yfinance",
            dataset="market_metadata", symbol="ONGC")
        self.assertIsNone(seq)
        self.assertEqual(ndsap_archive.count_records(), 0)

    def test_provider_gate_opens_when_owner_enables(self):
        config.PARAMS["ndsap_archive_providers"] = ["dhan", "yfinance"]
        seq = ndsap_archive.archive_record(
            {"sector": "Energy"}, provider="yfinance",
            dataset="market_metadata", symbol="ONGC")
        self.assertIsNotNone(seq)
        self.assertEqual(ndsap_archive.count_records(), 1)

    def test_disabled_flag(self):
        config.PARAMS["ndsap_archive_enabled"] = False
        seq = ndsap_archive.archive_record({"v": 1}, provider="dhan",
                                           dataset="ohlc_live", symbol="X")
        self.assertIsNone(seq)
        self.assertEqual(ndsap_archive.count_records(), 0)

    def test_fail_soft_on_unserializable_payload(self):
        cyc = {}
        cyc["self"] = cyc  # circular → serializer failure
        seq = ndsap_archive.archive_record(cyc, provider="dhan",
                                           dataset="ohlc_live", symbol="X")
        self.assertIsNone(seq)  # never raises into the caller
        self.assertIn("NDSAP ARCHIVE ERROR", self.audit_text())


class TestDhanDataTapIntegration(NdsapTestBase):
    """The dhan_data.fetch_daily_data tap must archive the RAW provider
    payload BEFORE _standardize transforms it (Rule 15 C)."""

    def test_fetch_daily_data_archives_raw_payload(self):
        import dhan_data

        raw = {"status": "success", "data": [
            {"open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0,
             "volume": 1000, "timestamp": 1757500000},
            {"open": 104.0, "high": 106.0, "low": 103.0, "close": 105.5,
             "volume": 1200, "timestamp": 1757586400},
        ]}

        saved = {
            "get_security_id": dhan_data.get_security_id,
            "_get_dhan": dhan_data._get_dhan,
            "_call_with_retry": dhan_data._call_with_retry,
            "audit": dhan_data.AUDIT_LOG_FILE,
            "cache_param": config.PARAMS.get("enable_daily_cache"),
        }
        dhan_data.get_security_id = lambda s: "1337"
        import types
        dummy_dhan = types.SimpleNamespace(
            historical_daily_data=lambda **kw: None,
            intraday_minute_data=lambda **kw: None)
        dhan_data._get_dhan = lambda: dummy_dhan
        dhan_data._call_with_retry = lambda api_func, **kw: dict(raw)
        dhan_data.AUDIT_LOG_FILE = self._audit
        config.PARAMS["enable_daily_cache"] = False
        try:
            df = dhan_data.fetch_daily_data("TESTSYM")
            self.assertEqual(len(df), 2)  # transformed result still correct
        finally:
            dhan_data.get_security_id = saved["get_security_id"]
            dhan_data._get_dhan = saved["_get_dhan"]
            dhan_data._call_with_retry = saved["_call_with_retry"]
            dhan_data.AUDIT_LOG_FILE = saved["audit"]
            if saved["cache_param"] is None:
                config.PARAMS.pop("enable_daily_cache", None)
            else:
                config.PARAMS["enable_daily_cache"] = saved["cache_param"]

        rows = ndsap_archive.read_asof(
            datetime.now(timezone.utc) + timedelta(minutes=1),
            dataset="historical_daily")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["provider"], "dhan")
        self.assertEqual(r["symbol"], "TESTSYM")
        self.assertEqual(r["security_id"], "1337")
        # (a) EXACT raw payload — pre-transformation (still has 'timestamp'
        # column and dict shape, unlike the standardized DataFrame)
        self.assertEqual(r["payload"], raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
