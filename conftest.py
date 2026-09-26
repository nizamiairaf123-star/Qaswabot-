"""
conftest.py — TEST SANDBOX (FIX-LIST 2026-09-04 item 9) + HERMETIC ISOLATION FIX r39

Problem this solves (found in the independent ZIP audit, finding F-01/F-02):
the test-suite writes through utils.save_json → SQLite (data/trading_bot.db),
utils.append_log → data/audit_log.txt and a few CSV writers. Every module
resolves its paths RELATIVE to the current working directory ("data/...",
config.DATA_DIR = "data"). Running pytest inside the release tree therefore
polluted the SHIPPED database with fake subscribers / trades / approval
flags — which then got zipped and sent to the VPS.

How the sandbox works (no production module is modified):
  1. pytest loads this file BEFORE collecting any test module.
  2. We create a fresh temp dir, copy the pristine `data/` folder into it,
     and chdir there. Because every path in the project is relative, the
     whole suite now reads/writes ONLY the temp copy.
  3. The project root stays on sys.path so `import bot` etc. still work.
  4. On session end we chdir back and delete the temp dir.

r39 PILLAR 1 — HERMETIC ISOLATION FIX:
  * test_p0p1_r38_fixes.py uses its own IsolatedProjectTestCase that copies
    the whole project into a temp dir, inserts that temp dir at front of
    sys.path, and deletes config/broker/etc from sys.modules to force
    re-import from the temp copy. Its tearDownClass previously restored
    CWD and sys.path but LEFT the temp modules in sys.modules, leaving
    sys.modules['config'] pointing at a deleted file. Subsequent tests
    (e.g. test_telemetry) that imported config at collection time held a
    reference to the ORIGINAL module, while telemetry._db_path() did
    `from config import TELEMETRY_DB` which resolved to the STALE temp
    module in sys.modules — split-brain, causing DB path mismatch,
    missing tables, and state bleed.

  * This conftest now provides:
    - _clean_stale_modules(): removes any module whose __file__ no longer
      exists or lives inside a qaswa_p0p1_test_ temp dir that was deleted.
    - Function-scoped autouse fixture _hermetic_isolation that runs before
      and after EACH test, ensuring sys.modules['config'] always points to
      the PROJECT_ROOT original, and clearing telemetry globals.
    - Session fixture still ensures sandbox is active.

Consequences:
  * `pytest` may be run from the release tree at any time and the tree
    stays byte-identical (verified by the SHA-256 manifest check in
    scripts/pre_vps_engineering_preflight.py, which runs pytest and then
    re-hashes).
  * Tests that build absolute paths from __file__ (test_sequence.py, which
    is NOT a pytest module) are unaffected — test_sequence is read-only
    except for py_compile, and is run with `python -B`.
  * Bytecode caches are also disabled (sys.dont_write_bytecode) so pytest's
    assertion-rewrite step does not leave __pycache__ inside the release tree.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

import pytest

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# No .pyc files anywhere while testing (pytest's assertion rewriter honours this;
# the env var makes child processes — e.g. the unittest subprocess in
# test_full_pipeline — behave the same). Run pytest as `python3 -B -m pytest`
# so even conftest.py itself is not cached before this line executes.
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

# Make sure imports resolve to the project root even after we chdir away.
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _make_sandbox() -> str:
    sandbox = tempfile.mkdtemp(prefix="qaswa_test_sandbox_")
    src_data = os.path.join(PROJECT_ROOT, "data")
    dst_data = os.path.join(sandbox, "data")
    if os.path.isdir(src_data):
        shutil.copytree(
            src_data, dst_data,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.log"),
        )
    else:
        os.makedirs(dst_data, exist_ok=True)
    # Root-level files some tests read relative to CWD (never written by tests).
    for name in ("feature_sequence.json", "SYSTEM_MASTER_MANIFEST.json",
                 "requirements.txt", "requirements-lock.txt", "deploy.sh"):
        p = os.path.join(PROJECT_ROOT, name)
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(sandbox, name))
    # Source files are read by a few policy tests via Path("*.py") — expose
    # them read-only via symlinks so the tests see the real code, while all
    # WRITES (which only ever target data/) land in the sandbox copy.
    for entry in os.listdir(PROJECT_ROOT):
        if entry in ("data", "__pycache__", ".pytest_cache"):
            continue
        target = os.path.join(sandbox, entry)
        if os.path.exists(target):
            continue
        try:
            os.symlink(os.path.join(PROJECT_ROOT, entry), target)
        except OSError:
            pass
    return sandbox


_SANDBOX = _make_sandbox()
_ORIG_CWD = os.getcwd()
os.chdir(_SANDBOX)

# test_sequence.py is a stand-alone runner (python test_sequence.py), not a
# pytest module — do not import it during collection.
collect_ignore = ["test_sequence.py"]


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """Keep pytest cache outside the release tree."""
    config.option.cache_dir = os.path.join(_SANDBOX, ".pytest_cache")


def _remove_own_bytecode() -> None:
    """pytest's assertion-rewriter caches conftest.py itself BEFORE the
    dont_write_bytecode line above runs (only when invoked without -B).
    Remove exactly that artefact so the release tree stays byte-identical."""
    cache_dir = os.path.join(PROJECT_ROOT, "__pycache__")
    if not os.path.isdir(cache_dir):
        return
    for name in os.listdir(cache_dir):
        if name.startswith("conftest.") and name.endswith(".pyc"):
            try:
                os.remove(os.path.join(cache_dir, name))
            except OSError:
                pass
    try:
        if not os.listdir(cache_dir):
            os.rmdir(cache_dir)
    except OSError:
        pass


def pytest_sessionfinish(session, exitstatus):
    """Return to the release tree, remove the sandbox and our own .pyc."""
    _cleanup()


_cleanup_done = False


def _cleanup():
    """[AUDIT F7 FIX, 2026-09-16] Idempotent so it's safe to call from both
    pytest_sessionfinish (pytest runs) and the atexit hook below (standalone
    `python3 test_X.py` runs, which never trigger pytest hooks at all)."""
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True
    try:
        os.chdir(_ORIG_CWD)
    finally:
        shutil.rmtree(_SANDBOX, ignore_errors=True)
        _remove_own_bytecode()


import atexit  # noqa: E402  (placed here: only needed for the standalone-run path)
atexit.register(_cleanup)


# ─────────────────────────────────────────────
# r39 PILLAR 1 — HERMETIC CLEANUP
# ─────────────────────────────────────────────

_P0P1_MODULES = (
    "broker", "trade_engine", "backtester",
    "scheduler_jobs_daily_ops", "signal_broadcaster",
    "startup_recovery", "bot_state_manager", "config",
    "utils", "forever_order_manager", "database",
)

def _is_stale_module(mod) -> bool:
    """True if module's __file__ points to a deleted temp dir or p0p1 temp."""
    try:
        f = getattr(mod, "__file__", None)
        if not f:
            return False
        # If file no longer exists, it's stale (p0p1 temp deleted)
        if not os.path.exists(f):
            # Only consider it stale if it looks like a p0p1 temp or sandbox
            # to avoid deleting stdlib modules that legitimately have no file.
            if "qaswa_p0p1_test_" in f or "qaswa_test_sandbox_" in f:
                return True
            # Also if it's inside a temp dir that doesn't exist anymore
            # we treat it as stale for our known project modules
            if f.startswith(tempfile.gettempdir()) and not os.path.exists(f):
                return True
        # If file path contains qaswa_p0p1_test_ but still exists (test running),
        # it's NOT stale during that test, but should be cleaned after.
        return False
    except Exception:
        return False

def _clean_stale_modules():
    """Remove any project modules whose file points to a deleted p0p1 temp dir.
    Also ensures sys.modules['config'] points to PROJECT_ROOT original if stale."""
    # First, remove any module that is stale
    to_delete = []
    for name, mod in list(sys.modules.items()):
        if name in _P0P1_MODULES or name.startswith("config") or name.startswith("telemetry"):
            if _is_stale_module(mod):
                to_delete.append(name)
            # Also if module's file is inside a qaswa_p0p1_test_ dir that no longer exists
            try:
                f = getattr(mod, "__file__", "") or ""
                if "qaswa_p0p1_test_" in f and not os.path.exists(f):
                    to_delete.append(name)
            except Exception:
                pass
    for name in set(to_delete):
        try:
            del sys.modules[name]
        except KeyError:
            pass

    # Ensure config is loaded from PROJECT_ROOT original if it was deleted
    if "config" not in sys.modules:
        # Force re-import from PROJECT_ROOT
        if PROJECT_ROOT not in sys.path:
            sys.path.insert(0, PROJECT_ROOT)
        try:
            import importlib
            importlib.import_module("config")
        except Exception:
            pass
    else:
        # If config in sys.modules points to a deleted file, delete it and re-import
        try:
            cfg = sys.modules["config"]
            f = getattr(cfg, "__file__", "") or ""
            if "qaswa_p0p1_test_" in f and not os.path.exists(f):
                del sys.modules["config"]
                import importlib
                importlib.import_module("config")
        except Exception:
            pass

    # Also clean telemetry globals that could bleed across tests
    try:
        import telemetry
        # Reset active trace and version cache to avoid cross-test bleed
        telemetry._ACTIVE_TRACE = None
        # Do NOT clear _VERSION_CACHE aggressively here — it is cached per process
        # but TelemetryTestBase handles it. We just ensure no active trace.
    except Exception:
        pass


@pytest.fixture(scope="session", autouse=True)
def _qaswa_test_sandbox():
    """Session-wide marker fixture: everything runs inside the temp sandbox."""
    assert os.getcwd() == _SANDBOX, "test sandbox not active"
    yield _SANDBOX


@pytest.fixture(autouse=True)
def _hermetic_isolation():
    """Function-scoped hermetic isolation — runs before and after EACH test.

    Guarantees:
    - Any stale p0p1 temp modules are purged before test starts.
    - After test, stale modules are purged again so next test gets clean slate.
    - Telemetry globals (_ACTIVE_TRACE) are cleared.
    - Config's TELEMETRY_DB is NOT forced here (telemetry tests override it),
      but we ensure config module itself is the PROJECT_ROOT original, not a
      deleted temp copy, so overrides work.
    """
    _clean_stale_modules()
    yield
    _clean_stale_modules()
    # Extra safety: clear telemetry active trace after each test
    try:
        import telemetry
        telemetry._ACTIVE_TRACE = None
    except Exception:
        pass
