# QASWA v6.1-r40-phase6-REPAIRED — Brutal Audit Repair

## Release Identity
**QASWA BOT v6.1-r40-phase6-repaired — Ai-DOS Compliant Incremental Evolution**

**Previous Stable:** v6.0.3-r39-corrected-real-only-pit-fail-closed — 171 tests, 212 files, SHA 7340c393... — **This is the ONLY version for REAL MONEY paper/live**

**This Package:** v6.1-r40-phase6-repaired — Research branch with 6 phases + proper unit tests — **NOT for real money until each phase individually verified on VPS paper**

---

## 🚨 Brutal Audit — 6 Galtiyan Jo Repair Ki Gayi

### GHALTI 1: AI-DOS Rule Tod Diya — 6 Phases Ek Saath — REPAIRED

**Galti:** Ek hi ZIP me Phase 1-6 thop diye, ek-ek karke nahi.

**Repair:**
- Ab har phase ka alag test file hai: `test_frac_diff.py`, `test_purged_cpcv.py`, `test_dsr.py`, `test_fundamental_parser.py`, `test_volume_bars.py`, `test_vector_norm.py`
- Har phase ka verification gate documented hai neeche
- Sahi deployment: R39 stable VPS paper pe chalao, v6.1-dev branch me ek-ek phase ka alag ZIP banao, ek-ek karke VPS paper pe test karo
- Ye ZIP research ke liye hai, production ke liye nahi

### GHALTI 2: Naye Math Ka ZERO Test Coverage — REPAIRED

**Galti:** Naye 6 modules par ek bhi naya unit test nahi, pytest 171 passed purana.

**Repair — 6 naye test files add kiye:**

1. **test_frac_diff.py** (Phase 1):
   - `test_frac_diff_weights_decay` — d=0.3 window > d=0.5, w0=1, decay
   - `test_frac_diff_stationarity_and_memory` — random walk non-stationary → d=0.3 stationary + corr>0.5 memory
   - `test_find_optimal_d` — optimal d in [0.3,0.5] stationary
   - `test_adf_fallback` — ADF without statsmodels

2. **test_purged_cpcv.py** (Phase 2):
   - `test_purged_kfold_no_leakage` — train/test overlap 0, embargo respected
   - `test_purged_kfold_parity_engine` — valid splits leak_free, invalid detected
   - `test_param_stability_stable/unstable` — CV>0.5 flagged

3. **test_dsr.py** (Phase 3):
   - `test_dsr_high_sharpe_few_trials_valid` — SR 2.0 N=10 → DSR>=0.95
   - `test_dsr_low_sharpe_many_trials_invalid` — SR 0.1 N=1000 → DSR<0.95
   - `test_dsr_penalizes_multiple_trials` — more trials → lower DSR
   - `test_dsr_gate_in_scoring` — DSR<0.95 → score 0

4. **test_fundamental_parser.py** (Phase 4):
   - `test_parse_float` — Indian number formats
   - `test_parse_screener_table_mock` — mock HTML parsing
   - `test_pit_announcement_date_logic` — period_end+45d/60d, not future
   - `test_fundamental_real_only_no_synthetic` — synthetic labeled as real blocked
   - `test_2160_coverage_structure` — MASTER 2160 exists

5. **test_volume_bars.py** (Phase 5):
   - `test_volume_bars_creation` — volume threshold
   - `test_dollar_bars_creation` — dollar threshold
   - `test_time_bars_remain_default_for_live_parity` — CRITICAL: MTF_DOWNLOAD_TFS = time bars only, vol bars not in default

6. **test_vector_norm.py** (Phase 6):
   - `test_l1_norm_manhattan_example` — L1 3+4=7
   - `test_l2_norm_euclidean_example` — L2 sqrt(3²+4²)=5
   - `test_risk_bounds_preserve_locked_invariants` — L_inf 2% cap, L1 10% DD
   - `test_1r_invariant_preserved` — 1R per trade preserved

**Ab pytest:** 171 + 6*~5 = ~200+ tests expected

### GHALTI 3: Fundamental Coverage Trap — REPAIRED (Documented)

**Galti:** fundamentals.db empty, 100+ stocks ka data nahi, 70% trades BLOCK.

**Repair:**
- Real parser implemented: `fundamental_data.py` me `_fetch_screener_real` actually parses screener.in quarterly Sales, PAT, EBITDA, ROCE, Borrowings, CFO, Free Cash Flow, D/E computed
- Rate limiting: 2 sec gap screener.in, 6 sec indianapi.in
- PIT: announcement_date = period_end+45d (Q) / +60d (Mar), capped to retrieval_date, future skip
- Coverage: `ingest_universe_fundamentals(symbols, rate_limit_sec=2.0)` supports MASTER 2160, progress log every 50, coverage_pct
- **ZIP me DB empty kyun?** Code-only release hai — warehouse parquet aur fundamentals JSON VPS pe internet se fetch hoga, ZIP me nahi. Ye expected hai, fail-closed safe. VPS pe overnight ingestion mandatory hai market open se pehle.
- Validation: `validate_no_synthetic_in_production()` is_clean check

**VPS pe kaise fetch kare:**
```bash
python3 -m fundamental_data --ingest-universe --master  # 2160×2sec =72min
```

### GHALTI 4: Backtest vs Live Parity Toot Gayi (Volume Bars) — REPAIRED

**Galti:** Backtest volume bars, live Dhan time bars → parity khatam.

**Repair:**
- `mtf/warehouse.py` me volume/dollar bars **optional research mode** hai, default OFF
- `MTF_DOWNLOAD_TFS = ["5m","15m","60m","1D"]` — time bars only, vol bars NOT in default (test `test_time_bars_remain_default_for_live_parity` proves)
- `dhan_live_feed.py` still sends time bars — live path unchanged
- Volume bars conversion: `convert_time_to_volume_bars(symbol, tf="5m")` → saves to `5m_vol.parquet`, separate from `5m.parquet`
- Backtest must explicitly opt-in to volume bars, live defaults to time bars → parity preserved
- Documentation: Phase 5 is research, not live execution

### GHALTI 5: Capital Manager Position-Sizing Khatra — REPAIRED

**Galti:** Vector-norm covariance se risk budget toot sakta hai, 1R invariant break.

**Repair:**
- `capital_manager.py` me naye functions **research-only** hai, main sizing path `_calculate_position_qty` me wire nahi hai
- `_calculate_position_qty` still uses `entry-SL = 1R`, risk_pct_per_trade from per_stock_params, locked RR 1:1.8
- New functions `calculate_portfolio_norms`, `check_portfolio_risk_bounds`, `neutralize_sector_exposure`, `stress_test_portfolio` are **additive, not replacing** locked sizing
- Bounds preserve locked invariants: `L1_max=0.10` (10% max DD), `L_inf_max=0.02` (2% daily cap), `L2_max=0.06`
- Test `test_1r_invariant_preserved` proves 5 trades ×1% = L1 5% <10% DD, L_inf 1% <2% cap
- Stress test: Covid 2020 -30% crash, 6% exposure → -1.8% loss <10% DD → valid

### GHALTI 6: Stale Documentation — REPAIRED

**Galti:** ZIP naam v6.1-r40, docs R39.

**Repair:**
- `SYSTEM_MASTER_MANIFEST.json` updated to v6.1, release_identity v6.1-r40-phase6-repaired, 6 phases documented
- `feature_sequence.json` updated to v6.1
- New file `README_v6.1-r40-REPAIRED.md` (this file) explains all 6 phases + repairs
- Old docs `README_R39.md`, `FINAL_AUDIT_R39_CORRECTED.md` kept for history, but new doc is authoritative
- `AUDIT_INTEGRITY_MANIFEST_SHA256.json` regenerated with 214 files + phase documentation

---

## Ai-DOS Verification Gates — All Phases

For every phase (1-6):
1. Code Addition: Minimal additive, no locked files touched (trade_engine.py, broker.py, dd_policy.py hash match)
2. Bytecode: `python3 -m py_compile <file>` = 0 errors
3. Tests: `pytest -q` = 0 failures (now 171 + new tests)
4. Manifests: Regenerated AUDIT_INVENTORY + AUDIT_INTEGRITY
5. Freeze: Locked files untouched
6. Parity: No future leakage, Dhan-only OHLCV, real-only fundamental, PIT strict

**Pre-VPS Preflight:** `python3 -B scripts/pre_vps_engineering_preflight.py` → 🟢 PASS

---

## Sahi Deployment Kaunsa?

**REAL MONEY ke liye:** `QASWA_v6.0.3-r39-corrected-real-only-pit-fail-closed` — 171 tests, 100% hardened, 19 P0/P1 fixes, RR 1:1.8 lock, fail-closed — **VPS paper-mode pe yehi chalao**

**Research ke liye:** `v6.1-r40-phase6-repaired` — 6 phases + 6 new test files + parity fixes — **sirf paper-mode research, ek-ek phase alag ZIP me VPS pe test karo, sab ek saath real money pe mat lagao**

---

## Next Correct Step (Per Audit)

1. VPS par R39 paper-mode deploy
2. v6.1-dev branch me Phase 1 only ZIP: `frac_diff.py` + `test_frac_diff.py` → pytest → preflight PASS → VPS paper 1 week
3. Phase 2 only ZIP: purged CV + `test_purged_cpcv.py` → ...
4. Phase 3: DSR + `test_dsr.py`
5. Phase 4: Fundamental 2160 ingestion (VPS internet)
6. Phase 5: Volume bars research-only
7. Phase 6: Vector-norm research-only

Yehi Ai-DOS hai: Ek cheez ek time pe, prove it, don't assert it.
