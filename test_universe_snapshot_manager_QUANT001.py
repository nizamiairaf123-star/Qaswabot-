"""
Standalone functional test for universe_snapshot_manager.py (QUANT-001 fix,
forward-looking part). Synthetic data only, no network.
"""
# [AUDIT F7 FIX, 2026-09-16] This file deletes TEST_DIR at module level
# (below) and is meant to run standalone -- without a sandbox that
# targets the REAL data/universe_snapshots in the release tree, exactly
# the "test_portfolio_backtest_engine_QUANT002.py overwrote the real
# universe CSV" hazard already documented for this project's sibling
# file. `import conftest` activates the same temp-dir sandbox pytest
# already gets, before anything else in this file runs.
import conftest  # noqa: F401
import os
import sys
import shutil

sys.path.insert(0, os.path.dirname(__file__))

TEST_DIR = "data/universe_snapshots"
if os.path.isdir(TEST_DIR):
    shutil.rmtree(TEST_DIR)

import universe_snapshot_manager as usm

errors = []

# TEST 1: no snapshots yet -> everything returns empty/None honestly
if usm.list_snapshot_dates() != []:
    errors.append("FAIL: expected no snapshots before any save")
if usm.get_nearest_snapshot_asof("2026-01-01") is not None:
    errors.append("FAIL: expected None when no snapshot exists at/before date")
if usm.earliest_snapshot_date() is not None:
    errors.append("FAIL: expected None earliest date before any save")

# TEST 2: save a snapshot, verify round-trip
ok = usm.save_universe_snapshot(["AAA", "BBB", "CCC"], as_of_date="2026-06-01")
if not ok:
    errors.append("FAIL: save_universe_snapshot returned False")
if usm.list_snapshot_dates() != ["2026-06-01"]:
    errors.append(f"FAIL: expected ['2026-06-01'], got {usm.list_snapshot_dates()}")
if usm.earliest_snapshot_date() != "2026-06-01":
    errors.append("FAIL: earliest_snapshot_date mismatch")

got = usm.get_nearest_snapshot_asof("2026-06-01")
if sorted(got or []) != ["AAA", "BBB", "CCC"]:
    errors.append(f"FAIL: round-trip mismatch, got {got}")

# TEST 3: asof a date BEFORE the only snapshot -> honestly None (not silently
# substituting the only available snapshot, which would misrepresent an
# unknown historical period as known)
if usm.get_nearest_snapshot_asof("2025-01-01") is not None:
    errors.append("FAIL: expected None for a date before any snapshot exists")

# TEST 4: asof a date AFTER the snapshot -> returns nearest-prior snapshot
usm.save_universe_snapshot(["AAA", "DDD"], as_of_date="2026-07-01")
got2 = usm.get_nearest_snapshot_asof("2026-07-15")
if sorted(got2 or []) != ["AAA", "DDD"]:
    errors.append(f"FAIL: expected latest prior snapshot (2026-07-01), got {got2}")

got3 = usm.get_nearest_snapshot_asof("2026-06-15")
if sorted(got3 or []) != ["AAA", "BBB", "CCC"]:
    errors.append(f"FAIL: expected the 2026-06-01 snapshot for a date between "
                   f"the two saves, got {got3}")

print()
if errors:
    print("=== FAILURES ===")
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print("=== ALL UNIVERSE-SNAPSHOT TESTS PASSED ===")
