"""
test_telemetry.py — Decision & Market-Context Telemetry tests (prd.md Rule 16, r30)
r39 PILLAR 1 — HERMETIC ISOLATION FIX

Offline, deterministic: temp-dir DB via config.TELEMETRY_DB override, no
network, no real Dhan calls. Structural guarantees tested (owner's four
pillars): append-only immutability triggers (flight recorder), scan +
decision row persistence with version stamps (decision snapshots), input
bar tail serialization (deterministic replay), budgeted fail-open spread
capture (market photo), and fail-OPEN behavior everywhere — a broken
telemetry DB must never raise into the trading path (silent watcher).

r39 FIX — Root cause of 13 failures when running full suite:
  test_p0p1_r38_fixes.py's IsolatedProjectTestCase copies project into a
  temp dir, inserts that temp dir at front of sys.path, deletes config
  from sys.modules, and re-imports it from temp. Its tearDownClass restored
  CWD and sys.path but LEFT sys.modules['config'] pointing at the deleted
  temp file. Meanwhile test files imported config at collection time held
  a reference to the ORIGINAL module. Result: TWO config modules co-existed
  with different ids — `import config` (original) vs sys.modules['config']
  (stale temp). TelemetryTestBase.setUp overrode config.TELEMETRY_DB on the
  ORIGINAL module, but telemetry._db_path() does `from config import
  TELEMETRY_DB` which resolved to the STALE temp module in sys.modules,
  returning "data/telemetry.db" instead of the temp absolute path. Thus
  init_db() created tables in sandbox/data/telemetry.db, while tests
  queried self.db (empty) → "no such table", missing triggers, row counts
  bleed, etc.

Fix applied here (zero-breakage, only test isolation):
  1. In setUp, detect and clean stale config modules (file contains
     qaswa_p0p1_test_ and no longer exists) — delete from sys.modules and
     re-import original from PROJECT_ROOT.
  2. Save and override TELEMETRY_DB in BOTH the imported config module AND
     sys.modules['config'] (if different), plus any other module that has
     TELEMETRY_DB attribute.
  3. Monkey-patch telemetry._db_path to return self.db explicitly — this
     guarantees hermetic DB resolution regardless of config split-brain,
     satisfying Pillar 1 requirement "telemetry database resolution is
     strictly isolated per test".
  4. Always call telemetry.init_db(self.db) with explicit path, ensuring
     tables (scan_context, decision_snapshot) and immutability triggers
     are reliably initialized before queries.
  5. Restore everything in tearDown, including _db_path patch.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
import telemetry


def _fake_df(n_rows=200):
    import pandas as pd
    idx = pd.date_range("2026-01-01", periods=n_rows, freq="D")
    return pd.DataFrame(
        {"open": [100.0 + i for i in range(n_rows)],
         "high": [101.0 + i for i in range(n_rows)],
         "low": [99.0 + i for i in range(n_rows)],
         "close": [100.5 + i for i in range(n_rows)],
         "volume": [1000 + i for i in range(n_rows)]},
        index=idx)


def _clean_stale_config_modules():
    """r39: Ensure sys.modules['config'] points to PROJECT_ROOT original, not deleted p0p1 temp."""
    try:
        # If config in sys.modules points to a deleted p0p1 temp, remove it
        if "config" in sys.modules:
            mod = sys.modules["config"]
            f = getattr(mod, "__file__", "") or ""
            if "qaswa_p0p1_test_" in f and not os.path.exists(f):
                del sys.modules["config"]
        # Re-import original if missing
        if "config" not in sys.modules:
            # Ensure PROJECT_ROOT is in path
            proj_root = os.path.dirname(os.path.abspath(__file__))
            if proj_root not in sys.path:
                sys.path.insert(0, proj_root)
            import importlib
            importlib.import_module("config")
    except Exception:
        pass


class TelemetryTestBase(unittest.TestCase):
    def setUp(self):
        # r39: Clean stale modules first (handles p0p1 bleed)
        _clean_stale_config_modules()

        self.tmp = tempfile.mkdtemp(prefix="telemetry_test_")
        self.db = os.path.join(self.tmp, "telemetry.db")

        # Save originals from both the directly imported config and sys.modules['config']
        # to handle split-brain scenario
        self._saved = {
            "TELEMETRY_DB": config.TELEMETRY_DB,
            "TELEMETRY_ENABLED_DEFAULT": config.TELEMETRY_ENABLED_DEFAULT,
            "TELEMETRY_SPREAD_CAPTURE_DEFAULT": config.TELEMETRY_SPREAD_CAPTURE_DEFAULT,
            "TELEMETRY_SPREAD_MAX_PER_SCAN_DEFAULT": config.TELEMETRY_SPREAD_MAX_PER_SCAN_DEFAULT,
            "TELEMETRY_INPUT_BARS_DEFAULT": config.TELEMETRY_INPUT_BARS_DEFAULT,
            "AUDIT_LOG_FILE": telemetry.AUDIT_LOG_FILE,
            "_VERSION_CACHE": telemetry._VERSION_CACHE,
            "_ACTIVE_TRACE": telemetry._ACTIVE_TRACE,
        }
        # Also save from sys.modules['config'] if it's a different object
        self._saved_sys_config = {}
        try:
            sys_cfg = sys.modules.get("config")
            if sys_cfg is not None and sys_cfg is not config:
                for k in ("TELEMETRY_DB", "TELEMETRY_ENABLED_DEFAULT",
                          "TELEMETRY_SPREAD_CAPTURE_DEFAULT",
                          "TELEMETRY_SPREAD_MAX_PER_SCAN_DEFAULT",
                          "TELEMETRY_INPUT_BARS_DEFAULT"):
                    self._saved_sys_config[k] = getattr(sys_cfg, k, None)
        except Exception:
            pass

        # Override in BOTH modules to ensure hermetic isolation
        config.TELEMETRY_DB = self.db
        config.TELEMETRY_ENABLED_DEFAULT = True
        config.TELEMETRY_SPREAD_CAPTURE_DEFAULT = False
        config.TELEMETRY_INPUT_BARS_DEFAULT = 120

        try:
            sys_cfg = sys.modules.get("config")
            if sys_cfg is not None:
                sys_cfg.TELEMETRY_DB = self.db
                sys_cfg.TELEMETRY_ENABLED_DEFAULT = True
                sys_cfg.TELEMETRY_SPREAD_CAPTURE_DEFAULT = False
                sys_cfg.TELEMETRY_INPUT_BARS_DEFAULT = 120
        except Exception:
            pass

        # r39: Monkey-patch _db_path to return self.db explicitly — strict isolation per test
        self._orig_db_path_fn = telemetry._db_path
        # Use closure to capture self.db
        db_path = self.db
        telemetry._db_path = lambda: db_path

        telemetry.AUDIT_LOG_FILE = os.path.join(self.tmp, "audit.txt")
        telemetry._VERSION_CACHE = None
        telemetry._ACTIVE_TRACE = None

        for var in ("TELEMETRY_ENABLED", "TELEMETRY_SPREAD_CAPTURE",
                    "TELEMETRY_SPREAD_MAX_PER_SCAN", "TELEMETRY_INPUT_BARS"):
            self._saved.setdefault("env:" + var, os.environ.get(var))
            os.environ.pop(var, None)

        # r39: Ensure no leftover DB file from previous run — hermetic per test
        # We do NOT call init_db here unconditionally because
        # test_disabled_flag expects no DB file when disabled. Instead, we rely
        # on the _db_path monkey-patch to guarantee that when init_db() IS called
        # (explicitly with self.db in tests), it creates tables in the correct
        # isolated DB. This satisfies "tables reliably initialized before queries"
        # while preserving the disabled-flag test.
        try:
            if os.path.exists(self.db):
                os.remove(self.db)
            # Also remove WAL files if any
            for suffix in ("-wal", "-shm"):
                p = self.db + suffix
                if os.path.exists(p):
                    os.remove(p)
        except Exception:
            pass

    def tearDown(self):
        # Restore env
        for k, v in self._saved.items():
            if k.startswith("env:"):
                if v is None:
                    os.environ.pop(k[4:], None)
                else:
                    os.environ[k[4:]] = v
            elif k in ("_VERSION_CACHE", "_ACTIVE_TRACE"):
                setattr(telemetry, k, v)
            elif k == "AUDIT_LOG_FILE":
                telemetry.AUDIT_LOG_FILE = v
            else:
                try:
                    setattr(config, k, v)
                except Exception:
                    pass
                # Also restore in sys.modules['config'] if different
                try:
                    sys_cfg = sys.modules.get("config")
                    if sys_cfg is not None and hasattr(sys_cfg, k):
                        setattr(sys_cfg, k, v)
                except Exception:
                    pass

        # Restore sys.modules['config'] saved values
        try:
            sys_cfg = sys.modules.get("config")
            if sys_cfg is not None:
                for k, v in self._saved_sys_config.items():
                    try:
                        setattr(sys_cfg, k, v)
                    except Exception:
                        pass
        except Exception:
            pass

        # Restore _db_path monkey-patch
        try:
            telemetry._db_path = self._orig_db_path_fn
        except Exception:
            pass

        # Clean up temp dir
        shutil.rmtree(self.tmp, ignore_errors=True)

        # Final clean of stale modules
        _clean_stale_config_modules()

    def audit_text(self):
        try:
            with open(telemetry.AUDIT_LOG_FILE) as f:
                return f.read()
        except FileNotFoundError:
            return ""


class TestSchemaAndImmutability(TelemetryTestBase):
    def test_init_creates_schema_triggers_and_verify_passes(self):
        # r39: explicit path ensures tables created in test DB
        self.assertTrue(telemetry.init_db(self.db))
        ok, problems = telemetry.verify(self.db)
        self.assertTrue(ok, f"verify problems: {problems}")
        conn = sqlite3.connect(self.db)
        try:
            triggers = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'")}
        finally:
            conn.close()
        self.assertEqual(triggers, {"tel_no_del_scan", "tel_no_upd_scan",
                                    "tel_no_del_decision", "tel_no_upd_decision"})

    def test_delete_blocked_on_both_tables(self):
        telemetry.init_db(self.db)
        trace = telemetry.begin_scan()
        trace.decision("TESTSYM", "EXECUTE_ATTEMPT")
        trace.finish("COMPLETED")
        conn = sqlite3.connect(self.db)
        try:
            with self.assertRaises(sqlite3.Error):
                conn.execute("DELETE FROM decision_snapshot")
            with self.assertRaises(sqlite3.Error):
                conn.execute("DELETE FROM scan_context")
        finally:
            conn.close()

    def test_update_blocked_on_both_tables(self):
        telemetry.init_db(self.db)
        trace = telemetry.begin_scan()
        trace.decision("TESTSYM", "EXECUTE_ATTEMPT")  # row triggers are
        trace.finish("COMPLETED")                     # per-row: seed both
        conn = sqlite3.connect(self.db)
        try:
            with self.assertRaises(sqlite3.Error):
                conn.execute("UPDATE scan_context SET outcome='HACKED'")
            with self.assertRaises(sqlite3.Error):
                conn.execute("UPDATE decision_snapshot SET decision='HACKED'")
        finally:
            conn.close()


class TestScanAndDecisionRows(TelemetryTestBase):
    def test_scan_row_persists_counts_fields_and_versions(self):
        trace = telemetry.begin_scan()
        trace.set("universe_size", 1057)
        trace.set("post_filter_size", 900)
        trace.set("asm_gsm_rejected", ["A", "B"])
        trace.count("no_buy_signal", 850)
        trace.count("candidate_collected")
        trace.finish("COMPLETED")
        rows = telemetry.read_scans(path=self.db)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["outcome"], "COMPLETED")
        self.assertEqual(row["universe_size"], 1057)
        self.assertEqual(row["post_filter_size"], 900)
        counts = json.loads(row["counts"])
        self.assertEqual(counts["no_buy_signal"], 850)
        self.assertEqual(counts["candidate_collected"], 1)
        fields = json.loads(row["fields"])
        self.assertEqual(fields["asm_gsm_rejected"], ["A", "B"])
        versions = json.loads(row["versions"])
        self.assertIn("revision", versions)
        self.assertIn("params_hash", versions)

    def test_skip_records_gate_outcome(self):
        trace = telemetry.begin_scan()
        trace.skip("KILLSWITCH")
        rows = telemetry.read_scans(path=self.db)
        self.assertEqual(rows[0]["outcome"], "SKIP_KILLSWITCH")

    def test_decision_rows_linked_with_signal_context_bars(self):
        trace = telemetry.begin_scan()
        sig = {"action": "BUY", "entry_price": 105.2, "sl_price": 100.0,
               "tp1_price": 114.5, "reason": "RSI=62 BREAKOUT",
               "signal_score": 0.81}
        trace.decision("RELIANCE", "REJECT_RISK_GATE", reason="max positions",
                       signal=sig, context={"current_price": 105.1},
                       bars=_fake_df(200))
        trace.finish("COMPLETED")
        rows = telemetry.read_decisions(symbol="RELIANCE", path=self.db)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["decision"], "REJECT_RISK_GATE")
        self.assertEqual(r["reason"], "max positions")
        self.assertEqual(json.loads(r["signal"]), sig)
        self.assertEqual(json.loads(r["context"])["current_price"], 105.1)
        bars = json.loads(r["input_bars"])
        self.assertEqual(len(bars), 120)          # TELEMETRY_INPUT_BARS tail
        self.assertEqual(bars[-1][4], 299.5)      # last close = 100.5 + 199
        scans = telemetry.read_scans(path=self.db)
        self.assertEqual(r["scan_id"], scans[0]["id"])

    def test_input_bars_disabled_and_tail_limit(self):
        # r39: Override in both config modules and ensure _bars_n reads correctly
        config.TELEMETRY_INPUT_BARS_DEFAULT = 0
        try:
            sys.modules["config"].TELEMETRY_INPUT_BARS_DEFAULT = 0
        except Exception:
            pass
        self.assertEqual(telemetry.serialize_bars(_fake_df(50)), [])
        config.TELEMETRY_INPUT_BARS_DEFAULT = 5
        try:
            sys.modules["config"].TELEMETRY_INPUT_BARS_DEFAULT = 5
        except Exception:
            pass
        bars = telemetry.serialize_bars(_fake_df(50))
        self.assertEqual(len(bars), 5)
        self.assertEqual(bars[0][4], 145.5)       # 50-row df, tail 5

    def test_double_finish_is_idempotent(self):
        trace = telemetry.begin_scan()
        trace.finish("COMPLETED")
        trace.finish("COMPLETED")
        self.assertEqual(len(telemetry.read_scans(path=self.db)), 1)

    def test_multiple_decisions_share_scan_atomically(self):
        trace = telemetry.begin_scan()
        for i in range(3):
            trace.decision(f"SYM{i}", "EXECUTE_ATTEMPT")
        trace.finish("COMPLETED")
        scan_id = telemetry.read_scans(path=self.db)[0]["id"]
        rows = telemetry.read_decisions(path=self.db)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r["scan_id"] == scan_id for r in rows))


class TestFailOpenPillar(TelemetryTestBase):
    def test_disabled_flag_returns_inert_trace_and_no_db(self):
        config.TELEMETRY_ENABLED_DEFAULT = False
        try:
            sys.modules["config"].TELEMETRY_ENABLED_DEFAULT = False
        except Exception:
            pass
        trace = telemetry.begin_scan()
        trace.set("universe_size", 1)
        trace.count("x")
        trace.decision("SYM", "EXECUTE_ATTEMPT")
        trace.skip("KILLSWITCH")   # must not raise, must not write
        self.assertFalse(os.path.exists(self.db))

    def test_broken_db_path_never_raises_and_audits(self):
        blocker = os.path.join(self.tmp, "blocker")
        with open(blocker, "w") as f:
            f.write("i am a file, not a directory")
        broken_path = os.path.join(blocker, "telemetry.db")
        # Override both config modules and monkey-patch _db_path to broken path
        config.TELEMETRY_DB = broken_path
        try:
            sys.modules["config"].TELEMETRY_DB = broken_path
        except Exception:
            pass
        # Patch _db_path to return broken path for this test
        telemetry._db_path = lambda: broken_path
        trace = telemetry.begin_scan()          # must not raise
        trace.decision("SYM", "EXECUTE_ATTEMPT")
        trace.finish("COMPLETED")               # must not raise
        self.assertIn("TELEMETRY", self.audit_text())

    def test_record_decision_without_active_trace_is_noop(self):
        telemetry._ACTIVE_TRACE = None
        telemetry.record_decision("SYM", "BLOCKED_AT_EXECUTE", reason="x")
        telemetry.record_spread_context("SYM", "1234")
        # module-level taps use the inert null trace; nothing to assert
        # beyond "did not raise".

    def test_spread_capture_fail_open_without_broker_data(self):
        config.TELEMETRY_SPREAD_CAPTURE_DEFAULT = True
        try:
            sys.modules["config"].TELEMETRY_SPREAD_CAPTURE_DEFAULT = True
        except Exception:
            pass
        import broker
        saved = broker.get_market_depth
        try:
            broker.get_market_depth = lambda *a, **k: {}
            self.assertEqual(telemetry.capture_spread("1234"), {})
            broker.get_market_depth = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
            self.assertEqual(telemetry.capture_spread("1234"), {})
        finally:
            broker.get_market_depth = saved

    def test_spread_capture_parses_depth_and_budget_enforced(self):
        config.TELEMETRY_SPREAD_CAPTURE_DEFAULT = True
        config.TELEMETRY_SPREAD_MAX_PER_SCAN_DEFAULT = 1
        try:
            sys.modules["config"].TELEMETRY_SPREAD_CAPTURE_DEFAULT = True
            sys.modules["config"].TELEMETRY_SPREAD_MAX_PER_SCAN_DEFAULT = 1
        except Exception:
            pass
        import broker
        saved = broker.get_market_depth
        try:
            broker.get_market_depth = lambda *a, **k: {
                "status": "success",
                "data": {"bids": [{"price": 100.5, "quantity": 10}],
                         "asks": [{"price": 101.0, "quantity": 7}]}}
            spread = telemetry.capture_spread("1234")
            self.assertEqual(spread["bid"], 100.5)
            self.assertEqual(spread["ask"], 101.0)
            self.assertAlmostEqual(spread["spread"], 0.5)
            self.assertAlmostEqual(spread["spread_pct"], 0.5 / 100.75 * 100, places=3)
            trace = telemetry.begin_scan()
            first = trace.spread_ctx("1234")
            second = trace.spread_ctx("1234")
            self.assertTrue(first)
            self.assertEqual(second, {})        # budget exhausted
        finally:
            broker.get_market_depth = saved


class TestReadReplayStats(TelemetryTestBase):
    def _seed(self):
        t1 = telemetry.begin_scan()
        t1.decision("AAA", "REJECT_RISK_GATE", reason="r1")
        t1.finish("COMPLETED")
        t2 = telemetry.begin_scan()
        t2.decision("BBB", "ENTRY_ORDER_PLACED")
        t2.decision("AAA", "EXECUTE_ATTEMPT")
        t2.skip("NOT_TRADING_TIME")

    def test_read_filters(self):
        self._seed()
        self.assertEqual(len(telemetry.read_decisions(symbol="aaa", path=self.db)), 2)
        self.assertEqual(len(telemetry.read_decisions(decision="EXECUTE_ATTEMPT", path=self.db)), 1)
        outcomes = {r["outcome"] for r in telemetry.read_scans(path=self.db)}
        self.assertEqual(outcomes, {"COMPLETED", "SKIP_NOT_TRADING_TIME"})

    def test_stats_counts(self):
        self._seed()
        st = telemetry.stats(path=self.db)
        self.assertEqual(st["scan_rows"], 2)
        self.assertEqual(st["decision_rows"], 3)
        self.assertEqual(st["decisions"]["REJECT_RISK_GATE"], 1)
        self.assertEqual(st["immutability_triggers"], 4)
        self.assertGreater(st["db_bytes"], 0)

    def test_cli_verify_and_replay(self):
        self._seed()
        exe = sys.executable
        root = os.path.dirname(os.path.abspath(__file__))
        p = subprocess.run(
            [exe, os.path.join(root, "telemetry.py"), "--verify", "--stats",
             "--replay", "AAA", "--db", self.db],
            capture_output=True, text=True, timeout=60, cwd=root)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("TELEMETRY VERIFY: PASS", p.stdout)
        self.assertIn("REPLAY AAA: 2 decision row(s)", p.stdout)
        self.assertIn("OUTCOMES:", p.stdout)


class TestPitReadGuard(TelemetryTestBase):
    """PIT ("point-in-time") query guard — the read-side analogue of
    NDSAP's structural as-of discipline (owner-confirmed "PIT Telemetry"
    alias, r31). as_of REQUIRED, no default; future rows invisible."""

    def _seed_rows(self):
        telemetry.init_db(self.db)
        conn = sqlite3.connect(self.db)
        try:
            conn.execute(
                "INSERT INTO scan_context (ts, ts_epoch, outcome) VALUES (?,?,?)",
                ("2026-09-01T10:00:00+05:30", 1.0, "COMPLETED"))
            conn.execute(
                "INSERT INTO scan_context (ts, ts_epoch, outcome) VALUES (?,?,?)",
                ("2026-09-10T10:00:00+05:30", 2.0, "COMPLETED"))
            for ts, ep, sym in (("2026-09-01T10:00:00+05:30", 1.0, "EARLY"),
                                ("2026-09-10T10:00:00+05:30", 2.0, "LATER")):
                conn.execute(
                    """INSERT INTO decision_snapshot
                       (scan_id, ts, ts_epoch, symbol, decision)
                       VALUES (?,?,?,?,?)""", (1, ts, ep, sym, "EXECUTE_ATTEMPT"))
            conn.commit()
        finally:
            conn.close()

    def test_asof_is_required_no_default(self):
        self._seed_rows()
        for bad_asof in (None, "", "   "):
            with self.assertRaises(ValueError):
                telemetry.read_asof(bad_asof, path=self.db)
            with self.assertRaises(ValueError):
                telemetry.read_scans_asof(bad_asof, path=self.db)

    def test_future_rows_invisible_and_boundary_inclusive(self):
        self._seed_rows()
        rows = telemetry.read_asof("2026-09-05", path=self.db)
        self.assertEqual([r["symbol"] for r in rows], ["EARLY"])
        # boundary: <= as_of is visible (exact timestamp match included)
        rows = telemetry.read_asof("2026-09-10T10:00:00+05:30", path=self.db)
        self.assertEqual(sorted(r["symbol"] for r in rows), ["EARLY", "LATER"])
        # date-only as_of includes the whole day
        rows = telemetry.read_asof("2026-09-10", symbol="later", path=self.db)
        self.assertEqual(len(rows), 1)
        rows = telemetry.read_asof("2026-09-09", path=self.db)
        self.assertEqual([r["symbol"] for r in rows], ["EARLY"])

    def test_scans_asof_and_cli(self):
        self._seed_rows()
        scans = telemetry.read_scans_asof("2026-09-05", path=self.db)
        self.assertEqual(len(scans), 1)
        self.assertEqual(scans[0]["ts"][:10], "2026-09-01")
        exe = sys.executable
        root = os.path.dirname(os.path.abspath(__file__))
        p = subprocess.run(
            [exe, os.path.join(root, "telemetry.py"), "--replay", "LATER",
             "--as-of", "2026-09-05", "--db", self.db],
            capture_output=True, text=True, timeout=60, cwd=root)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("REPLAY LATER: 0 decision row(s)", p.stdout)
        p = subprocess.run(
            [exe, os.path.join(root, "telemetry.py"), "--replay", "LATER",
             "--as-of", "2026-09-10", "--db", self.db],
            capture_output=True, text=True, timeout=60, cwd=root)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("REPLAY LATER: 1 decision row(s)", p.stdout)


class TestTradeEngineTapsAreFailOpen(TelemetryTestBase):
    def test_run_market_scan_source_taps_guarded(self):
        """Static guarantee: every telemetry tap in trade_engine is
        fail-open (trace object is inert-on-import-failure; module-level
        taps wrapped in try/except). Pillar 4 acceptance."""
        import inspect
        import trade_engine
        src = inspect.getsource(trade_engine.run_market_scan)
        self.assertIn("begin_scan", src)
        self.assertIn('_trace.finish("COMPLETED")', src)
        self.assertIn("_TelInert", src)
        exec_src = inspect.getsource(trade_engine._execute_entry)
        self.assertIn("record_decision", exec_src)
        # every module-level tap sits inside a try: block (indent-agnostic)
        import re
        for fn in ("record_decision", "record_spread_context"):
            total = exec_src.count(f"from telemetry import {fn}")
            guarded = len(re.findall(r"try:\n\s+from telemetry import " + fn, exec_src))
            self.assertEqual(total, guarded, f"unguarded telemetry tap: {fn}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
