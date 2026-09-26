"""
Standalone functional test for portfolio_backtest_engine.py (QUANT-002 fix).
Synthetic, deterministic data only — no live Dhan API, no network. Verifies
each of the 4 concentration gates actually blocks trades that the OLD
isolated per-stock backtest would have silently let co-exist.
"""
# [AUDIT F7 FIX, 2026-09-16] This is the exact file previously documented
# as overwriting the real data/CUSTOM_UNIVERSE_FINAL.csv via its own test
# fixture when run standalone (no conftest.py sandbox reaches a plain
# `python3 test_portfolio_backtest_engine_QUANT002.py` run). Activating
# the sandbox here closes that recurring hazard at the source instead of
# relying on catching + restoring it during packaging every time.
import conftest  # noqa: F401
import os
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

import config
_ORIGINAL_PARAMS = {k: config.PARAMS.get(k) for k in (
    "max_stocks_per_sector", "correlation_threshold", "reentry_cooldown_days",
    "max_slots", "validator_reference_capital", "trading_cost_pct"
)}
config.PARAMS["max_stocks_per_sector"] = 2
config.PARAMS["correlation_threshold"] = 0.85
config.PARAMS["reentry_cooldown_days"] = 3
config.PARAMS["max_slots"] = 8
config.PARAMS["validator_reference_capital"] = 100000.0
config.PARAMS["trading_cost_pct"] = 0.1

import portfolio_backtest_engine as pbe

# This test supplies sector maps directly to _replay_candidates and therefore
# must never overwrite the shipped production universe CSV.

dates = pd.date_range("2023-01-01", periods=300, freq="B")


def make_df(seed, base=100.0):
    rng = np.random.RandomState(seed)
    rets = rng.normal(0.0005, 0.01, len(dates))
    closes = base * (1 + rets).cumprod()
    return pd.DataFrame({"close": closes}, index=dates)


errors = []

entry, exit_ = dates[60], dates[120]

# ── TEST 1: correlation gate, isolated — AAA & BBB identical series,
# different sectors so the sector-cap gate can't interfere with this check ──
df_aaa = make_df(1)
df_bbb = df_aaa.copy()          # identical -> corr = 1.0
df_by_symbol_corr = {"AAA": df_aaa, "BBB": df_bbb}
sector_map_corr = {"AAA": "TECH", "BBB": "PHARMA"}
candidates_corr = [
    {"symbol": s, "entry_date": entry, "exit_date": exit_, "net_return_pct": 2.0}
    for s in ["AAA", "BBB"]
]
r0 = pbe._replay_candidates(candidates_corr, df_by_symbol_corr, sector_map_corr)
print("TEST 1 RESULT (correlation, isolated):", r0)
if r0["blocked_breakdown"]["correlation"] < 1:
    errors.append("FAIL (correlation gate): identical AAA/BBB series did not block")
if r0["kept_trades"] != 1:
    errors.append(f"FAIL (correlation gate): expected 1 kept trade, got {r0['kept_trades']}")

# ── TEST 2: sector-cap gate, isolated — 3 MUTUALLY UNCORRELATED TECH
# stocks, cap=2 -> the 3rd must block on sector, not correlation ──
df_p = make_df(101)
df_q = make_df(202)
df_r = make_df(303)
df_by_symbol_sec = {"P": df_p, "Q": df_q, "R": df_r}
sector_map_sec = {"P": "TECH", "Q": "TECH", "R": "TECH"}
candidates_sec = [
    {"symbol": s, "entry_date": entry, "exit_date": exit_, "net_return_pct": 2.0}
    for s in ["P", "Q", "R"]
]
r1 = pbe._replay_candidates(candidates_sec, df_by_symbol_sec, sector_map_sec)
print("TEST 2 RESULT (sector cap, isolated):", r1)
if r1["blocked_breakdown"]["sector_cap"] < 1:
    errors.append("FAIL (sector cap gate): 3rd TECH stock did not block (cap=2)")
if r1["kept_trades"] != 2:
    errors.append(f"FAIL (sector cap gate): expected 2 kept trades, got {r1['kept_trades']}")
if r1["blocked_breakdown"]["correlation"] != 0:
    errors.append("FAIL: sector-cap test unexpectedly triggered correlation block "
                   "(test stocks not independent enough — check make_df seeds)")
if r1["kept_trades"] + r1["blocked_trades"] != r1["total_candidate_trades"]:
    errors.append("FAIL (accounting): kept + blocked != total candidates")

# NOTE: _get_max_slots() now genuinely calls the (just-fixed) dynamic
# economics_brain path, so it no longer simply echoes PARAMS["max_slots"].
# That path is verified separately below (TEST 4b); here we pin the slot
# cap directly so this test isolates ONLY the gate-blocking logic.
_real_get_max_slots = pbe._get_max_slots
pbe._get_max_slots = lambda capital: 2

df_e = make_df(10)
df_f = make_df(11)
df_g = make_df(12)
df_by_symbol2 = {"E": df_e, "F": df_f, "G": df_g}
sector_map2 = {"E": "S1", "F": "S2", "G": "S3"}
config.PARAMS["max_stocks_per_sector"] = 10
candidates_2 = [
    {"symbol": s, "entry_date": entry, "exit_date": exit_, "net_return_pct": 1.0}
    for s in ["E", "F", "G"]
]
r2 = pbe._replay_candidates(candidates_2, df_by_symbol2, sector_map2)
print("TEST 4 RESULT (max_slots, pinned cap=2):", r2)
if r2["blocked_breakdown"]["max_slots"] < 1:
    errors.append("FAIL (max_slots gate): 3rd concurrent stock did not block (cap=2)")
pbe._get_max_slots = _real_get_max_slots
config.PARAMS["max_stocks_per_sector"] = 2

# ── TEST 4b: dynamic economics-based max_slots path actually executes
# (this is the economics_brain.py PARAMS-import bug fix, confirmed live) ──
try:
    slots = pbe._get_max_slots(100000.0)
    print(f"TEST 4b RESULT (dynamic max_slots path): {slots} (no NameError)")
    if not isinstance(slots, int) or slots <= 0:
        errors.append(f"FAIL (dynamic max_slots): expected positive int, got {slots!r}")
except NameError as e:
    errors.append(f"FAIL (dynamic max_slots): NameError still present: {e}")

df_h = make_df(20)
df_by_symbol3 = {"H": df_h}
sector_map3 = {"H": "S9"}
loss_exit = dates[65]
reentry = dates[66]
candidates_3 = [
    {"symbol": "H", "entry_date": dates[60], "exit_date": loss_exit, "net_return_pct": -3.0},
    {"symbol": "H", "entry_date": reentry, "exit_date": dates[90], "net_return_pct": 1.5},
]
r3 = pbe._replay_candidates(candidates_3, df_by_symbol3, sector_map3)
print("TEST 5 RESULT (cooldown):", r3)
if r3["blocked_breakdown"]["cooldown"] < 1:
    errors.append("FAIL (cooldown gate): re-entry 1 day after a losing exit did not block")
if r3["kept_trades"] != 1:
    errors.append(f"FAIL (cooldown gate): expected 1 kept trade, got {r3['kept_trades']}")

reentry_ok = dates[70]
candidates_4 = [
    {"symbol": "H", "entry_date": dates[60], "exit_date": loss_exit, "net_return_pct": -3.0},
    {"symbol": "H", "entry_date": reentry_ok, "exit_date": dates[90], "net_return_pct": 1.5},
]
r4 = pbe._replay_candidates(candidates_4, df_by_symbol3, sector_map3)
print("TEST 6 RESULT (cooldown expired -> allowed):", r4)
if r4["kept_trades"] != 2:
    errors.append(f"FAIL: re-entry after cooldown window should be ALLOWED, got {r4['kept_trades']}")

# Restore every config mutation before module import completes so this
# standalone script cannot pollute unrelated pytest modules during collection.
for _k, _v in _ORIGINAL_PARAMS.items():
    if _v is None:
        config.PARAMS.pop(_k, None)
    else:
        config.PARAMS[_k] = _v

print()
if errors:
    print("=== FAILURES ===")
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print("=== ALL 6 GATE ASSERTIONS PASSED ===")
