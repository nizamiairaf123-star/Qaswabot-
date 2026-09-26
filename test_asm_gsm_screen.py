"""
test_asm_gsm_screen.py — ASM/GSM pre-screen (OWNER DECISION 2026-09-05)

Executable evidence for the pre-trade surveillance gate:
  * fail-closed: missing / malformed / stale list → entries blocked
  * fresh list + listed symbol → blocked with stage reason
  * fresh list + clean symbol → allowed
  * NSE CSV/API parsers + manual refresh path
Sandbox: conftest.py temp data/ copy me chalta hai (production data untouched).
"""
# [AUDIT F7 FIX, 2026-09-16] Explicit import guarantees the sandbox is
# active even if this file is ever run standalone (python3 test_X.py),
# not just under pytest.
import conftest  # noqa: F401
import json
import sys
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asm_gsm_screen
from asm_gsm_screen import (
    is_asm_gsm_data_stale, is_symbol_blocked, check_entry,
    parse_nse_csv, parse_nse_api_json, refresh_asm_gsm_list,
)

LIST_PATH = Path("data") / "asm_gsm_list.json"


def _write_list(symbols=None, as_of=None, source="test"):
    payload = {
        "as_of": str(as_of if as_of is not None else asm_gsm_screen._today()),
        "source": source,
        "symbols": symbols if symbols is not None else {"ABANS": "ASM_L1", "XYZ-CHEM": "GSM_STAGE_0"},
    }
    LIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIST_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class TestFailClosed(unittest.TestCase):
    def setUp(self):
        if LIST_PATH.exists():
            LIST_PATH.unlink()

    def test_missing_list_blocks_entries(self):
        self.assertTrue(is_asm_gsm_data_stale())
        blocked, reason = check_entry("RELIANCE")
        self.assertTrue(blocked)
        self.assertIn("ASM/GSM DATA STALE PAUSE", reason)

    def test_malformed_list_blocks_entries(self):
        LIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        LIST_PATH.write_text("{not-json", encoding="utf-8")
        self.assertTrue(is_asm_gsm_data_stale())
        self.assertTrue(check_entry("RELIANCE")[0])

    def test_stale_age_blocks_entries(self):
        _write_list(as_of=asm_gsm_screen._today() - timedelta(days=int(
            __import__("config").PARAMS.get("asm_gsm_list_max_age_days", 7)) + 1))
        self.assertTrue(is_asm_gsm_data_stale())
        blocked, reason = check_entry("TCS")
        self.assertTrue(blocked)
        self.assertIn("ASM/GSM DATA STALE PAUSE", reason)

    def test_check_error_fails_closed(self):
        orig = asm_gsm_screen._load_list
        asm_gsm_screen._load_list = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            self.assertTrue(check_entry("TCS")[0])
        finally:
            asm_gsm_screen._load_list = orig


class TestGating(unittest.TestCase):
    def setUp(self):
        _write_list()

    def test_asm_gsm_symbol_is_not_automatically_rejected(self):
        blocked, reason = is_symbol_blocked("ABANS")
        self.assertFalse(blocked)
        self.assertIn("SURVEILLANCE FLAG", reason)
        blocked, reason = check_entry("abans")  # case-insensitive
        self.assertFalse(blocked)
        self.assertIn("SURVEILLANCE FLAG", reason)

    def test_explicit_suspended_status_is_blocked(self):
        _write_list()
        data = json.loads(LIST_PATH.read_text(encoding="utf-8"))
        data["symbols"]["BLOCKME"] = "SUSPENDED"
        LIST_PATH.write_text(json.dumps(data), encoding="utf-8")
        blocked, reason = check_entry("BLOCKME")
        self.assertTrue(blocked)
        self.assertIn("HARD STATUS BLOCKED", reason)

    def test_clean_symbol_allowed(self):
        blocked, reason = check_entry("CLEANCO")
        self.assertFalse(blocked)
        self.assertEqual(reason, "")

    def test_fresh_list_not_stale(self):
        self.assertFalse(is_asm_gsm_data_stale())


class TestParsersAndRefresh(unittest.TestCase):
    SAMPLE_CSV = (
        "SYMBOL,SERIES,DATE,ASM/GSM STAGE\n"
        "ABANS,EW,22-Jul-2026,ASM Long Term Stage 1\n"
        'VODAFONE IDEA,EQ,22-Jul-2026,"GSM Stage 0"\n'
    )

    SAMPLE_API_JSON = json.dumps({"data": [
        {"symbol": "ABANS", "smType": "ASM", "stage": "Long Term Stage 1"},
        {"symbol": "SUVEN", "smType": "GSM", "stage": "Stage 0"},
    ]})

    def test_csv_parser_variants(self):
        out = parse_nse_csv(self.SAMPLE_CSV)
        self.assertEqual(out["ABANS"], "ASM LONG TERM STAGE 1")
        self.assertIn("VODAFONE IDEA", out)

    def test_api_json_parser(self):
        out = parse_nse_api_json(self.SAMPLE_API_JSON)
        self.assertEqual(len(out), 2)
        self.assertIn("ASM", out["ABANS"])

    def test_manual_csv_refresh_commits_fresh_list(self):
        if LIST_PATH.exists():
            LIST_PATH.unlink()
        self.assertTrue(is_asm_gsm_data_stale())
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "asm.csv"
            csv_path.write_text(self.SAMPLE_CSV, encoding="utf-8")
            n = refresh_asm_gsm_list(manual_csv=str(csv_path))
        self.assertGreaterEqual(n, 2)
        self.assertFalse(is_asm_gsm_data_stale())          # fresh now
        self.assertFalse(check_entry("ABANS")[0])            # ASM/GSM is informational, not an automatic rejection
        self.assertFalse(check_entry("CLEANCO")[0])         # clean symbol

    def test_network_refresh_failure_is_fail_closed(self):
        if LIST_PATH.exists():
            LIST_PATH.unlink()
        orig_get = asm_gsm_screen._http_get
        asm_gsm_screen._http_get = lambda url, timeout=20: (_ for _ in ()).throw(RuntimeError("blocked"))
        try:
            with self.assertRaises(RuntimeError):
                refresh_asm_gsm_list()
            self.assertTrue(is_asm_gsm_data_stale())  # list stale hi rehti hai — fabricated data nahi
        finally:
            asm_gsm_screen._http_get = orig_get


if __name__ == "__main__":
    unittest.main()
