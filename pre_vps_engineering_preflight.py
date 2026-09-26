#!/usr/bin/env python3
"""Deterministic PRE-VPS engineering/package gate.

This gate intentionally does NOT require real VPS, broker, or external market-data
execution. Those are AFTER-VPS checks. It verifies that the shipped engineering
artifact contains the required controls, declarations, fail-closed boundaries,
local evidence, and provenance needed to move to that environment.
"""
from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import os
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REQUIRED = [
    "prd.md", "SYSTEM_BLUEPRINT.md", "SYSTEM_MASTER_MANIFEST.json", "feature_sequence.json",
    "AI_ONBOARDING.md", "FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md",
    "MASTER_AUDIT_EXECUTION_AND_SCORECARD.md",
    "docs/MASTER_ZERO_OMISSION_ZIP_INSPECTION_CONSTITUTION_55_SECTIONS.md",
    "docs/PRE_VPS_VERIFICATION_GATE_v1.0.md", "docs/PRE_VPS_GATE_PROFILE_v1.0.md",
    "docs/AI_INSPECTION_TRIGGER_AND_RESULT_CONTRACT_v1.0.md",
    "requirements.txt", "requirements-lock.txt", "deploy.sh", "start_bot.sh", "qaswa-bot@.service",
    "scripts/release_preflight.py", "scripts/refresh_decision_data.py", "test_sequence.py",
]

PASS = []
FAIL = []
DEFERRED = []

def ok(name, detail=""):
    PASS.append((name, detail))

def bad(name, detail):
    FAIL.append((name, detail))

def defer(name, detail):
    DEFERRED.append((name, detail))

# 1) Required artifacts
for rel in REQUIRED:
    if (ROOT / rel).is_file(): ok("required artifact", rel)
    else: bad("required artifact", f"missing: {rel}")

# 2) Python syntax for every source file
py_files = [p for p in ROOT.rglob("*.py") if "__pycache__" not in p.parts and ".pytest_cache" not in p.parts]
for p in py_files:
    try:
        ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
    except Exception as e:
        bad("python syntax", f"{p.relative_to(ROOT)}: {type(e).__name__}: {e}")
if not any(n == "python syntax" for n, _ in FAIL): ok("python syntax", f"{len(py_files)}/{len(py_files)} parsed")

# 3) JSON parse
json_files = [p for p in ROOT.rglob("*.json") if "__pycache__" not in p.parts]
for p in json_files:
    try: json.loads(p.read_text(encoding="utf-8"))
    except Exception as e: bad("json parse", f"{p.relative_to(ROOT)}: {type(e).__name__}: {e}")
if not any(n == "json parse" for n, _ in FAIL): ok("json parse", f"{len(json_files)}/{len(json_files)} parsed")

# Capture release-tree hygiene BEFORE test execution; tests may create pycache/pytest-cache.
initial_generated = []
for _p in ROOT.rglob("*"):
    if _p.is_file() and ("__pycache__" in _p.parts or _p.suffix == ".pyc" or ".pytest_cache" in _p.parts):
        initial_generated.append(str(_p.relative_to(ROOT)))

# Verify artifact SHA-256 manifest BEFORE tests can mutate runtime-state/log files.
def verify_sha_manifest():
    manifest_path = ROOT / "AUDIT_INTEGRITY_MANIFEST_SHA256.json"
    if not manifest_path.is_file():
        bad("SHA-256 provenance", "AUDIT_INTEGRITY_MANIFEST_SHA256.json missing")
        return
    m = json.loads(manifest_path.read_text())
    listed = {x["path"]: x for x in m.get("files", [])}
    actual = []
    mismatches = []
    for _p in sorted(ROOT.rglob("*")):
        if not _p.is_file(): continue
        rel = _p.relative_to(ROOT).as_posix()
        if "__pycache__/" in rel or rel.startswith(".pytest_cache/") or rel in {manifest_path.name, "AUDIT_INVENTORY_SHA256.json"}: continue
        actual.append(rel)
        if rel not in listed:
            mismatches.append(f"unlisted:{rel}")
        elif hashlib.sha256(_p.read_bytes()).hexdigest() != listed[rel]["sha256"]:
            mismatches.append(f"hash:{rel}")
    for rel in listed:
        if rel not in actual:
            mismatches.append(f"missing:{rel}")
    if mismatches:
        bad("SHA-256 provenance", "; ".join(mismatches[:20]))
    else:
        ok("SHA-256 provenance", f"{len(actual)} shipped artifacts match manifest")

verify_sha_manifest()

# [r31 STRUCTURAL GUARD] Second inventory manifest staleness check.
# Root cause of the r30 audit finding: AUDIT_INVENTORY_SHA256.json is a
# separate shipped integrity manifest ({path,size,sha256} entries) that
# the SHA-provenance check above deliberately skips (self-referential
# pair) and no test covered — r30 regenerated the primary manifest + CSV
# but left this one stale (12 mismatched hashes, 2 missing entries).
# Now every release gate re-verifies it against the tree: same scope
# (all shipped files except the two self-referential audit manifests).
def verify_inventory_manifest():
    inv_path = ROOT / "AUDIT_INVENTORY_SHA256.json"
    if not inv_path.is_file():
        bad("inventory manifest", "AUDIT_INVENTORY_SHA256.json missing")
        return
    entries = json.loads(inv_path.read_text())
    listed = {x["path"]: x for x in entries}
    actual, mismatches = [], []
    for _p in sorted(ROOT.rglob("*")):
        if not _p.is_file(): continue
        rel = _p.relative_to(ROOT).as_posix()
        if ("__pycache__/" in rel or rel.startswith(".pytest_cache/")
                or rel in {"AUDIT_INTEGRITY_MANIFEST_SHA256.json",
                           "AUDIT_INVENTORY_SHA256.json"}): continue
        actual.append(rel)
        if rel not in listed:
            mismatches.append(f"unlisted:{rel}")
        else:
            data = _p.read_bytes()
            if hashlib.sha256(data).hexdigest() != listed[rel]["sha256"]:
                mismatches.append(f"hash:{rel}")
            elif listed[rel].get("size") != len(data):
                mismatches.append(f"size:{rel}")
    for rel in listed:
        if rel not in actual:
            mismatches.append(f"missing:{rel}")
    if mismatches:
        bad("inventory manifest", "; ".join(mismatches[:20]))
    else:
        ok("inventory manifest", f"{len(actual)}/{len(actual)} entries exact (second inventory in sync)")

verify_inventory_manifest()

# 4) Local executable evidence
for cmd, label in [
    # FIX-LIST item 9/11: -B + PYTHONDONTWRITEBYTECODE so the gate itself never
    # leaves __pycache__ in the release tree; the suites run in temp sandboxes.
    ([sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider"], "pytest"),
    ([sys.executable, "-B", "test_sequence.py"], "test_sequence"),
]:
    r = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    if r.returncode == 0:
        ok(label, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "exit 0")
    else:
        bad(label, f"exit {r.returncode}\n{r.stdout[-3000:]}")

# 5) Data boundary: missing real provider data is allowed only if fail-closed + explicit external contract exists
provider = json.loads((ROOT / "data/decision_data_provider.json").read_text())
state = json.loads((ROOT / "data/custom_universe_state.json").read_text())
required_fields = provider.get("required_fields", [])
missing_fields = []
import csv
with (ROOT / "data/CUSTOM_UNIVERSE_FINAL.csv").open(newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
for field in required_fields:
    if any((r.get(field) or "").strip() == "" for r in rows): missing_fields.append(field)
if missing_fields:
    if state.get("BOARD_DATA_STALE_PAUSE") is True and provider.get("provider") is None:
        ok("external data boundary", f"deferred fields fail closed: {', '.join(missing_fields)}")
        defer("real decision-data refresh", "sector/industry/market_cap/turnover_liquid_ok/atvr_pct/frequency_of_trading_pct require real provider after VPS")
    else:
        bad("external data boundary", "decision-critical fields missing without an explicit fail-closed pause/provider boundary")
else:
    ok("external data boundary", "decision-critical fields are populated")

# 6) Dependency reproducibility: lock exists and deploy.sh actually prefers it
req_text = (ROOT / "requirements.txt").read_text()
lock_text = (ROOT / "requirements-lock.txt").read_text()
deploy_text = (ROOT / "deploy.sh").read_text()
if lock_text.strip() and "requirements-lock.txt" in deploy_text and 'pip install -r "$INSTALL_REQUIREMENTS"' in deploy_text:
    ok("dependency reproducibility", "requirements-lock.txt exists and deploy.sh uses it when present")
else:
    bad("dependency reproducibility", "lock exists but deploy path does not deterministically consume it")

# 7) Dead MTF global must not remain
config_text = (ROOT / "config.py").read_text()
if "MTF_ENABLED" not in config_text:
    ok("MTF dead-config removal", "unused global flag absent from config.py")
else:
    bad("MTF dead-config removal", "unused MTF_ENABLED global remains")

# 8) No generated artifacts in release tree
if initial_generated:
    bad("package hygiene", f"generated artifacts present before gate run: {len(initial_generated)}")
else:
    ok("package hygiene", "no pycache/pyc/pytest-cache artifacts at gate start")

# 9) Trigger contract + gate phrases
onboard=(ROOT/"AI_ONBOARDING.md").read_text()
profile=(ROOT/"docs/PRE_VPS_GATE_PROFILE_v1.0.md").read_text()
for phrase, source in [("Inspection karo ZIP ka.", onboard), ("Criterion → Implementation → Integration/Wiring → Invocation/Reachability → Actual Effect → Enforcement → Failure/Bypass Analysis → Evidence", onboard)]:
    if phrase in source: ok("AI inspection contract", phrase)
    else: bad("AI inspection contract", f"missing exact phrase: {phrase}")
if "AFTER-VPS EXTERNAL EVIDENCE" in profile and "PRE-VPS ENGINEERING EVIDENCE" in profile:
    ok("phase boundary contract", "PRE-VPS and AFTER-VPS evidence explicitly separated")
else: bad("phase boundary contract", "phase boundary missing")

# 10) Artifact SHA-256 manifest was verified before test execution above.

# Report
print("="*78)
print("QASWA PRE-VPS ENGINEERING PREFLIGHT")
print("="*78)
print(f"PASS: {len(PASS)} | FAIL: {len(FAIL)} | EXTERNAL/DEFERRED: {len(DEFERRED)}")
for n,d in PASS: print(f"[PASS] {n}: {d}")
for n,d in DEFERRED: print(f"[EXTERNAL/DEFERRED] {n}: {d}")
for n,d in FAIL: print(f"[FAIL] {n}: {d}")
print("="*78)
if FAIL:
    print("🔴 PRE-VPS: FAIL — FIX REQUIRED — VPS DEPLOYMENT MAT KARO")
    sys.exit(2)
print("🟢 PRE-VPS: PASS — ZIP VERIFIED — NEXT STEP: VPS")
print("AFTER-VPS external verification remains mandatory where listed above.")
