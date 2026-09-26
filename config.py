"""
config.py — Central configuration
All hardcoded values MINIMIZED — optimizable params loaded from optimizer output
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# CREDENTIALS (from .env)
# ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
DHAN_CLIENT_ID = os.getenv("DHAN_CLIENT_ID")
DHAN_ACCESS_TOKEN = os.getenv("DHAN_ACCESS_TOKEN")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")  # Fernet key for subscriber credentials
# External dead-man ping (Healthchecks.io / UptimeRobot). Empty = skip, never error.
HEALTHCHECK_URL = (os.getenv("HEALTHCHECK_URL") or "").strip()

# ─────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────
BOT_NAME = "Qaswa"
DATA_DIR = "data"
TOKEN_FILE = f"{DATA_DIR}/dhan_token.json"
SUBSCRIBERS_FILE = f"{DATA_DIR}/subscribers.json"
TRADES_FILE = f"{DATA_DIR}/trades.json"
STOCK_MODES_FILE = f"{DATA_DIR}/stock_modes.json"
PORTFOLIO_STATE_FILE = f"{DATA_DIR}/portfolio_state.json"
SEBI_BLOCKED_FILE = f"{DATA_DIR}/sebi_blocked.json"
AUDIT_LOG_FILE = f"{DATA_DIR}/audit_log.txt"
OPTIMIZER_OUTPUT_FILE = f"{DATA_DIR}/optimizer_output.json"
BACKTEST_RESULTS_FILE = f"{DATA_DIR}/backtest_results.json"
# Single tradable universe source (owner criteria: Core Business Halal +
# 100% Non-Muslim Board + Price>100 + Liquid, strict NSE-EQ execution).
# Runtime readers isi ko use karte hain — koi legacy fallback nahi.
CUSTOM_UNIVERSE_FILE = f"{DATA_DIR}/CUSTOM_UNIVERSE_FINAL.csv"
CUSTOM_UNIVERSE_STATE_FILE = f"{DATA_DIR}/custom_universe_state.json"
# Legacy alias for backward compat
CUSTOM_UNIVERSE_FINAL_CSV = CUSTOM_UNIVERSE_FILE
KILLSWITCH_FILE = f"{DATA_DIR}/killswitch.json"
SIGNAL_REGISTRY_FILE = f"{DATA_DIR}/signal_registry.json"

# ─────────────────────────────────────────────
# OPTIMIZABLE PARAMETERS
# These are defaults; owner-fixed policy values are reasserted after optimizer output is loaded.
# DO NOT hardcode strategy logic here
# ─────────────────────────────────────────────
OPTIMIZABLE_DEFAULTS = {
    # [ADMIN APPROVED] Standardized backtesting/simulation reference capital.
    # NOT a real user's capital and NOT used for real position sizing --
    # this is purely a fixed, arbitrary baseline so admin can compare
    # different stocks/strategies on equal footing during backtest/
    # optimization/deployment-approval (results are %-based, so the exact
    # number doesn't change correctness). Real trading always uses
    # get_deployable_balance() (actual broker balance); user-facing
    # simulation results always use the real amount the user specifies via
    # /simulate <amount> (see simulate_engine.run_simulation()'s capital
    # parameter). Value matches the pre-existing fallback convention
    # already used elsewhere (strategy_validator.py).
    "validator_reference_capital": 200000.0,

    # Risk per trade
    # [FAIL-CLOSED CONTRACT] sl_pct/tp1_pct are intentionally NOT here.
    # per_stock_params.get_param(symbol, "sl_pct"/"tp1_pct", None) must
    # return None for a never-optimized stock so trade_engine._execute_entry()
    # blocks it (fail-closed) instead of silently trading on a generic
    # default. Do not re-add these keys to PARAMS — that defeats the gate
    # system-wide even though callers pass default=None expecting it.
    "min_reward_risk": 1.8,         # [OWNER CONTRACT] Fixed exactly 1.8R lock. After lock, profit is uncapped via trailing
        "wick_multiplier": 1.5,        # SL hunt protection — wick/body ratio threshold (optimizer search 1.0-3.0)
    "candle_body_ratio": 1.5,     # Candle body size relative to ATR — optimized per stock
    "candle_wick_ratio": 1.5,     # Candle wick size relative to body — optimized per stock
    "candle_confirmation": 2,     # Number of candles for pattern confirmation
    "candle_volume_mult": 1.5,    # Volume requirement for candle patterns
    
    # RSI Divergence parameters
    "divergence_lookback": 10,    # Bars to look back for divergence
    "rsi_tolerance": 5.0,         # RSI difference tolerance for divergence
    
    # Volume Divergence parameters
    "volume_lookback": 10,        # Bars to look back for volume analysis
    "volume_threshold": 0.7,      # Volume decrease threshold
    
    # Candle-Volume parameters
    "candle_size_threshold": 0.5, # Candle size relative to ATR
    "volume_spike_threshold": 1.5, # Volume spike multiplier
    
    # MTF Composite parameters
    "mtf_min_score": 3,           # Minimum score for MTF composite signal — NO CAP, optimizer decides per stock per phase
    
    # Multiple Combo per Stock
    "max_combos_per_stock": None, # Deprecated compatibility field; no fixed TOP-N tool limit.
    "trail_multiplier": 1.5,        # ✅ OPTIMIZER-FALLBACK: ATR trail multiplier (search 1.0-3.0)
    "trail_activation_pct": 0.0,    # LEGACY COMPATIBILITY ONLY — ignored by canonical 1.8R exit engine
    "trail_gtt_update_min_pct": 0.1, # 🛠 ENGINEERING: trail itna upar bada tabhi GTT modify (broker-side follow)
    # ── v5.4 EXIT TOOLKIT (owner: lock/trail sirf EK tool hai; optimizer decide karega) ──
    "exit_mode": "hybrid",          # ✅ OPTIMIZER-FALLBACK: fixed_tp | trail | hybrid | ratchet — per-stock Categorical in search space
    "profit_lock_pct": 1.0,         # ✅ OPTIMIZER-FALLBACK: profit lock (hybrid/ratchet) — search 0.25-2.0
    "ratchet_step_pct": 1.5,        # ✅ OPTIMIZER-FALLBACK: ratchet step (progressive lock) — search 0.5-3.0

    # ── v5.7 HARDCODE MIGRATION (owner audit D1-D28) ──────────────────
    # India macro (EXTERNAL_FACT — MoSPI/RBI official; monthly review)
    "india_gdp_growth_pct": 6.8,
    "india_inflation_pct": 4.45,     # MoSPI July-2026 official CPI (owner ne 4.5 stale pakda)
    "india_risk_free_rate_pct": 7.0,
    "macro_warn_days": 90,
    # Hurdle formula coefficients (documented design)
    "hurdle_inflation_weight": 0.5,
    "macro_adj_inflation_slope": 0.02,
    "macro_adj_inflation_base": 4.0,
    # Minervini Trend Template canonical (Minervini 2013)
    "minervini_52w_low_mult": 1.30,
    "minervini_52w_high_mult": 0.75,
    # Min live WR formula guard band (owner)
    "min_wr_guard_low": 30.0,
    "min_wr_guard_high": 45.0,
    # Optimizer scoring policy (Decision 16 family — config-driven)
    "optimizer_score_penalties": {
        "small_trades_threshold": 20, "small_trades_factor": 0.45,
        "high_wr_threshold": 85.0, "high_wr_factor": 0.75,
        "high_dd_threshold": 20.0, "high_dd_factor": 0.6,
        "weak_factor": 0.2,
    },
    "optimizer_norm_baselines": {
        "pf": 3.0, "wr_center": 35.0, "ret": 60.0, "rf": 3.0,
        "sharpe": 2.5, "expectancy": 3.0,
        "dd_penalty_mult": 10.0, "quality_weight": 0.90, "expectancy_weight": 0.10,
    },
    "optimizer_adaptive_weight_base": {
        "pf_base": 0.24, "pf_vol_slope": 0.14, "wr_base": 0.18, "wr_vol_slope": 0.08,
        "ret_base": 0.22, "ret_liq_slope": 0.14, "rf_base": 0.16, "rf_trend_slope": 0.08,
        "dd_pen_base": 0.04, "dd_pen_vol_slope": 0.08, "dd_pen_liq_slope": 0.02,
    },
    # RuFlo ranking scale (owner design)
    "ruflo_score_weights": {"wfv": 25.0, "pf": 25.0, "wr": 20.0, "dd": 15.0, "stability": 15.0},
    "ruflo_multipliers": {"wfv_gap": 2.5, "pf": 12.5, "wr": 1.0, "dd": 1.5, "stability": 15.0},
    "ruflo_z_weights": {"wfv": 25.0, "pf": 25.0, "wr": 20.0, "dd": 15.0, "stability": 15.0},
    # Brokerage/statutory (EXTERNAL_FACT — SEBI/Dhan rate card, Oct-2024 update)
    "brokerage_rate_pct": 0.0,      # [PHD-FIX Section-10] Dhan delivery brokerage is ₹0 (verified, since 2021 launch) — this bot trades delivery/CNC only. 0.06% was Dhan's intraday rate, wrongly applied here.
    "brokerage_min_inr": 0.0,       # [PHD-FIX Section-10] Same correction — no ₹40 cap applies to delivery.
    "statutory_rate_pct": 0.25,
    # Confidence sizing multiplier (owner policy)
    "confidence_mult_base": 0.50,
    "confidence_mult_slope": 0.90,
    "confidence_mult_min": 0.50,
    "confidence_mult_max": 1.40,
    # Universe quality gates (owner policy)
    "universe_min_trades": 3,
    "universe_min_wr_opt": 25.0,
    "universe_min_wr_backtest": 30.0,
    # Tool micro-constants (OPTIMIZER search me — v5.7)
    "support_band_mult": 1.01,
    "vwap_rsi_max": 60.0,
    # Dempster-Shafer conflict threshold (Dempster 1967/Shafer 1976)
    "ds_conflict_threshold": 0.99,
    # Overnight normalizations (research-informed)
    "overnight_price_blend": {"ret": 0.6, "pos": 0.4},
    "overnight_price_saturation_pct": 5.0,
    "overnight_volume_saturation_mult": 3.0,
    "overnight_persistence_saturation_pct": 1.0,
    "overnight_tug_saturation_ratio": 0.5,
    "overnight_tp_grid": {"min": 0.5, "max": 2.75, "step": 0.25},
    "overnight_sl_grid": {"min": 0.25, "max": 1.5, "step": 0.25},
    # Simulation statistical constants (standard)
    "sim_worst_case_zscore": 1.28,
    "sim_recommended_buffer_mult": 1.5,
    "sim_mc_quantiles": {"worst": 0.05, "median": 0.5, "best": 0.95},
    # Validator penalties (owner policy)
    "validator_pf_penalty_mult": 60.0,
    "validator_pf_penalty_cap": 35.0,
    "validator_rf_penalty_mult": 20.0,
    "validator_rf_penalty_cap": 20.0,
    # Health benchmark weights (owner policy)
    "health_benchmark_wr_weight": 0.25,
    "health_benchmark_pf_weight": 0.35,
    "health_benchmark_return_weight": 0.25,
    "health_benchmark_rf_weight": 0.15,
    # Liquidity/Monte Carlo conventions
    "trading_days_per_year": 252,       # NSE convention
    "liquidity_fetch_buffer_mult": 2.2,
    "monte_carlo_n_sims": 10000,
    "monte_carlo_percentile": 5.0,
    # Stage ladder (owner) — DEPLOYMENT_STAGES single source
    "deployment_stage_pcts": [10.0, 25.0, 50.0, 100.0],

    # DD thresholds
    "dd_buffer_pct": 2.0,           # 🅾️ OWNER POLICY: DD + this % = soft block trigger
    "recovery_days_wait": 5,        # 🅾️ OWNER POLICY: days to wait before recovery entry
    "reentry_cooldown_days": 3,     # Days after SL hit before re-entry

    # Phase detection
    # [FAIL-CLOSED CONTRACT] phase_ema_fast/phase_ema_slow/phase_adx_threshold
    # intentionally NOT here — same reason as sl_pct/tp1_pct above. A stock
    # without optimizer-approved phase params must fail closed to SIDEWAYS
    # in strategy.detect_market_phase(), not silently use a generic TA
    # convention default (20/50/25). Do not re-add these keys.

    # ── PHASE-EDGE GATE ──────────────────────────────────────────────
    # Per-stock per-phase (UPTREND/SIDEWAYS/DOWNTREND) enable/disable.
    # Har phase ka decision optimizer ke statistical edge-test se aata hai
    # (data/per_stock_params.json → phase_allow_<phase>). Neeche wale values
    # RESEARCH PROTOCOL constants hain (standard statistical conventions —
    # Pardo 2008 walk-forward family), STRATEGY thresholds NAHI hain:
    "phase_edge_alpha": 0.10,            # ✅ VERIFIED CONVENTION: one-sided t-test significance (research standard; owner 0.05 kar sakta hai)
    "phase_edge_min_oos_trades": 3,      # ✅ VERIFIED CONVENTION: df >= 2 — t-statistic ki statistical necessity (strategy choice nahi)
    "phase_edge_train_fraction": 0.70,   # chronological IS/OOS split fraction (Pardo-style train/test convention)
    "phase_edge_fdr_alpha": 0.10,       # ✅ VERIFIED CONVENTION: Benjamini-Hochberg FDR level (multiple-testing correction — PHD-FIX F2)
    "phase_edge_use_fdr": True,          # 🅾️ OWNER POLICY: FDR correction ON (judge protection); False = purana per-test alpha
    "atr_fallback_pct": 2.0,             # 🛠 ENGINEERING: ATR unavailable ho to close ka % fallback (PHD-FIX F10)
    "phase_min_train_candles": 50,       # minimum in-sample phase candles for meaningful per-phase optimization
    "phase_tool_opt_n_calls": 15,        # per-tool Bayesian search budget (computational budget, not a strategy value)
    "optuna_n_jobs": 4,                  # 🛠 ENGINEERING: Optuna parallel trial workers (VPS pe 4; tests me 1 = deterministic)
    "phase_threshold_relief_cap": 0.15,  # max trend-strength relief on the dynamic ADX threshold (RegimeFolio-style calibration knob)

    # Connors RSI-2 pullback method (Connors & Alvarez 2009) — verified
    # long-only method for sideways/mild-downtrend phases. Ye values method
    # ke CANONICAL constants hain (research defaults); optimizer inhi ke
    # aas-paas per-stock tune karta hai:
    "connors_rsi2_oversold": 10.0,       # canonical Connors RSI(2) oversold line
    "connors_crash_sma_period": 200,     # canonical Connors crash-protection SMA

    # Support detection (tested: 50ema, 100ema, 200ema, sma, swing_low, vwap)
    "support_tool": "200ema",       # Optimizer picks best bounce rate

    # Portfolio health thresholds [🅾️ OWNER-DESIGNED composite — credit: AIRAF NIZAMI.
    # Concept (composite health score + traffic-light zones) = common monitoring practice
    # (Fed SR 11-7 2011 spirit); koi formal creator nahi. Exact values = policy; machine
    # calibrates within owner bands (approved 2026-07-30); current values = fallback defaults]
    "health_active_min": 70,        # [🅾️ OWNER BAND 65-80 — component-independent] Normal compounding zone
    "health_caution_min": 50,       # [🅾️ OWNER BAND 40-60] Soft sizing brake zone (0.5x multiplier)
    "health_warning_min": 30,       # [🅾️ OWNER BAND 20-35] Hard brake zone (Exit-Only recovery watch)

    # Capital deployment [VERIFIED QUANT METHOD: Modern Portfolio Theory Markowitz Diversification]
    "max_slots": 8,                 # [OVERRIDE 3, user-authorized pivot] band tightened to 5-10 (was 5-12) — equal-weight top 5-10 setups/day. Diversification principle still Markowitz 1952 / Evans & Archer 1968; exact band is owner value.
    "risk_pct_per_trade": 0.5,      # [VERIFIED QUANT METHOD] Canonical default (% of capital per trade derived via Half-Kelly)

    # Safety [VERIFIED QUANT METHOD: Dr. Van Tharp Velocity Circuit Breakers & Risk Budgeting]
    "daily_loss_limit_pct": 2.0,    # [ADMIN APPROVED] Constitution Art. 2.4a -- the SOLE fixed risk constant in the system. Day P&L limit used ONLY as the emergency fallback when capital_drawdown_manager.calculate_daily_risk_budget()'s verified Half-Kelly/health/regime budget is unavailable (is_daily_limit_hit() prefers the dynamic budget whenever it can compute one)
    "max_trades_per_day": 6,        # [VERIFIED CALCULATION CHAIN] Execution frequency cap derived from daily risk budget
    # Consecutive-loss cooldown [Method: day-trader "3 strikes" convention — industry
    # practice (no single formal creator; honestly marked). Purana "Van Tharp Velocity
    # Circuit Breaker" label ghalat tha — corrected v3.1.2+]
    "rapid_loss_pause_mode": "REST_OF_DAY",  # [OWNER DECISION 2026-07-29] 3 back-to-back losses → us din STOP, agle trading day 09:15 auto-resume. ("MINUTES" = legacy 30min-window/60min-pause behavior)
    "rapid_loss_count": 3,          # [OWNER APPROVED] back-to-back losses needed (jeet aayi → counter reset). [2026-07-30: ab ye FAIL-OPEN FALLBACK hai — verified WR available ho to machine khud threshold nikalta hai (runs_test_streak_p_cap_pct dekhiye)]
    "runs_test_streak_p_cap_pct": 5.0,  # [OWNER VALUE 2026-07-30 — decision #5, CORRECTED same day (owner 3 corrections)] 5%-crossing target: machine verified WR (WFV → optimizer → backtest chain) se EXACT crossing k* = ln(p_cap)/ln(1-WR) ka nearest-integer k derive karta hai (floor 2): WR40%→6, WR50%→4, WR55%→4, WR70%→2. NOTE: crossing ke sabse qareeb integer — P(k) kabhi-kabhi 5% se thoda upar bhi ho sakta hai ("hamesha neeche" nahi, "sabse qareeb" rule). [DESIGN: AIRAF NIZAMI — method: Geometric Run-Length Tail (1-WR)^k, geometric distribution; YE Wald-Wolfowitz runs test NAHI hai — purana naam ghalat tha, corrected. Independence assumption (iid trades) safety_manager docstring me explicitly documented]
    "rapid_loss_window_min": 30,    # MINUTES mode only (legacy)
    "rapid_loss_pause_min": 60,     # MINUTES mode only (legacy)

    # Correlation risk (cross-verified across multiple independent portfolio-
    # risk-management sources -- correlation is an inherently standardized,
    # bounded [-1,+1] statistic, so a fixed interpretation band is the
    # correct/verified approach here, unlike raw volatility which needs
    # per-stock rolling-percentile calibration, seq 11)
    # Survival circuit tiering (account-level risk-policy constants, not
    # per-stock -- calculate_survival_plan() operates on portfolio capital,
    # so these cannot be optimizer-tuned per-symbol like phase-detection
    # params, seq 11. Grounded in real-world risk-management convention
    # research rather than optimizer search, similar in nature to the 2%
    # daily-loss constant, Art. 2.4a.)
    "min_circuit_dd_pct": 3.0,       # [VERIFIED QUANT METHOD] Floor for the survival circuit when the economics-based recovery calculation is non-positive. "Static Drawdown Explained" (alphaexcapital.com) cites 3-7% as the commonly-used prop-trading drawdown-cap range for smaller/tighter accounts; 3.0% sits at that range's conservative/tightest end, appropriate as a floor (never go below the tightest commonly-used real-world cap).
    "survival_soft_mult": 0.50,      # [VERIFIED QUANT METHOD] Soft-warning tier as a fraction of the circuit level. Directly matches the explicit professional prop-trading convention (pickmytrade.trade, "Drawdown Limits in Prop Trading"): "Set Personal Loss Limits: Use half of the allowed daily drawdown as a self-imposed stop to avoid hitting hard limits."
    "survival_hard_mult": 0.75,      # [VERIFIED QUANT METHOD] Hard-brake tier as a fraction of the circuit level. Positioned as the mid-to-late stage of a 3-tier soft(50%)/hard(75%)/circuit(100%) escalation, consistent with the staged/tiered risk-response pattern found across multiple independent sources (bank soft/hard "amber/red" limit tiering, Federal Reserve working paper sra2401; prop-firm multi-stage warning-then-breach escalation, Finotive Funding; empirically-searched multi-tier drawdown thresholds, Talyxion arxiv 2511.13239).

    "correlation_threshold": 0.85,        # [VERIFIED QUANT METHOD] Stock-to-stock correlation "block as duplicate position" cutoff. Multiple independent sources (dqydj, prudentinvestors, guardfolio, thepredictiveinvestor, ryanoconnellfinance) converge on >0.7-0.8 = "high correlation/concentration risk, minimal diversification benefit"; 0.85 sits at the conservative/stricter end of that established range.
    "vix_correlation_threshold": 0.5,     # [VERIFIED QUANT METHOD] Same correlation-interpretation convention (0.5 = "moderate," the boundary where the same sources above start flagging reduced diversification benefit), applied conservatively here because equities normally show weak/negative VIX correlation -- even a moderate POSITIVE correlation (stock rises with fear) is an atypical, risk-flagging cross-asset signal.
    "usdinr_correlation_threshold": -0.4, # [VERIFIED QUANT METHOD] Same convention, conservative trigger: a moderate negative correlation with USDINR (stock falls as rupee weakens) is an atypical FX-sensitivity signal for a domestic equity, so the same "moderate" boundary is used as the flag point.

    # Spread check
    "max_spread_pct": 0.5,         # [VERIFIED QUANT METHOD] Institutional market microstructure execution standard

    # Position sizing
    "target_portfolio_vol": 20.0,   # [✅ CONCEPT VERIFIED: Risk Parity / Inverse-Vol — Qian 2005, Bridgewater 1996, Harvey et al. 2018 | 🅾️ VALUE owner band 10-20%, default 12 (approved 2026-07-30) — credit: AIRAF NIZAMI. NOTE: Bridgewater targets 10-12% (Pure Alpha II 18%), NOT 20; current 20 = legacy bootstrap value, machine selects within band]

    # ── MARKET REGIME CLASSIFICATION THRESHOLDS ──────────────────────
    # Config-driven (optimizer/admin tune kar sakte hain). Defaults =
    # FIX-04 ke verified values. Regime = Nifty HMM + 4 macro evidences —
    # regime ab: Nifty HMM (Hamilton 1989) + Nifty EMA structure + sector
    # + VIX + USDINR multi-factor fusion (Dempster-Shafer 1967/1976).
    "regime_ema_fast": 50,
    "regime_ema_slow": 200,
    "regime_ema200_rise_lookback": 5,       # bars back to check EMA200 rising
    "vix_high_level": 22.0,
    "vix_rise_20d_pct": 15.0,
    "vix_low_level": 15.0,
    "multi_factor_bull_threshold": 0.80,
    "multi_factor_bear_threshold": -0.80,
    "multi_factor_recovery_score": 0.20,
    "regime_weights": {
        "nifty": 0.45,
        "sector": 0.25,
        "vix": 0.15,
        "usdinr": 0.15,
    },
    # Dempster-Shafer evidence confidences (market regime fusion fallback)
    "ds_evidence_confidences": {
        "nifty": 0.6,
        "sector": 0.4,
        "vix": 0.3,
        "usdinr": 0.3,
    },

    # ── BEAR REGIME POLICY KNOBS (config-driven — koi hardcode nahi) ──
    # Bear regime me sector STRONG gate kitna strict ho (0.0 = koi extra
    # strictness nahi, optimizer ke sector_strength_threshold par hi chale):
    "sector_bear_regime_threshold_boost": 1.0,
    # Legacy downtrend engine me market-wide BEAR pe hard block
    # (False = per-stock phase gate hi decide karega):
    "downtrend_bear_regime_block": True,

    # ── NEWS SENTIMENT (Loughran-McDonald 2011 — verified method) ────
    "lm_wordlist_file": "data/lm_finance_wordlists.csv",
    "news_cache_ttl_min": 240,              # 🛠 ENGINEERING: cache validity = full trading day (240 min)
    "news_prefetch_max_symbols": 100,       # pre-market prefetch budget cap
    "news_negation_window": 3,              # LM negation convention (words after not/no/never)
    "news_max_headlines": 5,                # per symbol headlines analyzed

    # ── SCAN CONCURRENCY (time-aware fast path) ───────────────────────
    "scan_max_concurrent_fetches": 10,      # parallel Dhan candle fetches per scan cycle

    # ── SIZING-PARITY POLICY (v4.2 — backtest under live conditions) ──
    # Live ka deployable = stage × health × regime. Backtest parity me
    # health/regime live current-state hote hain isliye DEFAULT neutral
    # (1.0 = point-in-time correctness). Admin chahe to expected live
    # values set kar ke backtest ko live conditions ke under chala sakta
    # hai — koi hardcode nahi, defaults purana behavior hi rakhte hain.
    "parity_health_mult": 1.0,
    "parity_regime_mult": 1.0,

    # ── DATA / OPS ENGINEERING (v5.0) ───────────────────────────────
    "enable_daily_cache": True,        # 🛠 ENGINEERING: 1D candles local cache (optimizer 10x fast, Dhan API cost kam)
    "enable_auto_reoptimize": False,   # 🛠 ENGINEERING (owner opt-in): monthly auto re-optimize PROPOSAL — approval hamesha admin ke haath me
    "daily_cache_stale_days": 1,       # 🛠 ENGINEERING: cache valid for current trading day only
    "exit_verify_retry_sec": 5,        # 🛠 ENGINEERING: exit fill re-check wait (market order fill check)
    # [v5.8.2] Order-pending wait timing — config-driven (owner: "20 sec pending
    # wait hardcode kyun?"). ENGINEERING category: broker/exchange latency ka
    # infra decision — iska optimizer ke paas koi backtest data nahi hota
    # (backtest me fill instant assume), isliye OPTIMIZE galat hota (fake
    # precision). Owner band me tune kar sakte ho.
    "order_verify_wait_sec": 10,            # entry: pehla status check wait
    "order_verify_second_wait_sec": 10,     # entry: dusra wait (cancel se pehle) — 10+10 = 20 sec total
    "order_race_check_wait_sec": 2,         # cancel-fail race re-check (last-millisecond fill)
    "subscriber_order_verify_wait_sec": 10, # subscriber copy order fill verify wait
    "order_status_default_wait_sec": 30,    # broker verify function ka default (koi caller explicit nahi deta to)
    "fill_price_alert_threshold_pct": 1.0,  # entry re-anchor: signal vs real Dhan fill gap > ye % ho to admin alert

    # ── ENTRY FOLLOW + SHADOW LOG (v5.9 — owner D28, sirf execution rule) ──
    "entry_follow_enabled": True,               # 🅾️ OWNER POLICY (D28): pending order RESTING rahega — cancel nahi, broker CMP touch pe fill
    "entry_follow_risk_units": 1.0,             # 🅾️ OWNER POLICY (D28): point-of-no-return scale = entry−SL geometry (optimizer anchor); shadow data se refine (owner approval zaroori)
    "entry_follow_check_interval_min": 3,       # 🛠 ENGINEERING: follow tick cadence (position monitor cycle sync)
    "entry_follow_price_missing_ticks": 3,      # 🛠 ENGINEERING: lagataar ticks CMP missing → cancel (owner: bina price data trade nahi)
    "shadow_log_enabled": True,                 # 🅾️ OWNER POLICY (D28): observation-only research — sab BUY signals ka din-bhar path (koi order nahi)
    "shadow_log_max_path_points": 80,           # 🛠 ENGINEERING: per-symbol path points cap (~78 scans/day) — file size guard
    "shadow_log_min_samples": 30,               # ✅ VERIFIED CONVENTION: recommendation ke liye minimum samples (small-sample stats; overnight_min_paper_trades precedent)
    "shadow_log_min_return_pct": 60.0,          # 🅾️ OWNER POLICY: return-zone valid hone ka minimum return% (recommendation judge)

    # ── OVERNIGHT MOVERS MODULE (v5.2 Phase-2 research) ──────────────
    # Research base: Post-Earnings Drift (Ball & Brown 1968), Overnight
    # Premium (Lou/Polk/Skouras 2019), closing-auction imbalance
    # (microstructure), Momentum (Jegadeesh & Titman 1993).
    # DEFAULT OFF — paper-phase proof gate se pehle koi live nahi.
    "overnight_enabled": False,             # 🅾️ OWNER POLICY: master switch — paper edge proof ke baad hi True
    "overnight_max_candidates": 5,          # 🅾️ OWNER POLICY: din ke top-N candidates (owner: "top 5 jaise")
    "overnight_min_score": 0.45,            # 🅾️ OPTIMIZER-FALLBACK: candidate cutoff — mini-optimizer tune karta hai
    "overnight_tp_pct": 1.0,                # 🅾️ OPTIMIZER-FALLBACK: next-day target — mini-optimizer decide karta hai (paper phase)
    "overnight_sl_pct": 0.75,               # 🅾️ OPTIMIZER-FALLBACK: overnight tight SL — mini-optimizer decide karta hai
    "overnight_volume_lookback": 20,        # ✅ VERIFIED CONVENTION: volume surge baseline (20-d avg — standard)
    "overnight_score_weights": {            # ✅ VERIFIED CONVENTION: research-informed initial weights; mini-optimizer tune karta hai
        "volume_surge": 0.20,
        "price_strength": 0.20,
        "overnight_persistence": 0.15,
        "earnings_event": 0.15,
        "tug_of_war": 0.10,
        "bulk_deal": 0.05,
        "news_sentiment": 0.05,
        "depth_imbalance": 0.05,
        "fii_dii": 0.05,
    },
    "overnight_persistence_lookback": 5,    # ✅ VERIFIED CONVENTION: Lou/Polk/Skouras 2019 (JFE) — overnight-return persistence window
    "overnight_tug_of_war_lookback": 20,    # ✅ VERIFIED CONVENTION: Akbas et al. 2021 (JFE) — daily tug-of-war window (~1 month trading days)
    "overnight_prefetch_max_symbols": 0,    # 🛠 ENGINEERING: 0 = pura universe; >0 = cap (rate-limit budget)
    "overnight_api_sleep_sec": 0.15,        # 🛠 ENGINEERING: pre-fetch rate-limit respect (Dhan 1 req/sec convention)
    "overnight_min_paper_trades": 30,       # ✅ VERIFIED CONVENTION: paper proof ke liye minimum closed trades (small-sample stats convention)
    "overnight_edge_alpha": 0.10,           # ✅ VERIFIED CONVENTION: same one-sided t-test significance as phase gate

    # ── REGIME BEHAVIOR DEFAULTS ─────────────────────────────────────
    # FIX-05 regime size/slot policy — ab PARAMS-driven (optimizer/admin
    # override kar sakta hai). Defaults = purani hardcoded values, behavior
    # 100% same jab tak koi tune na kare. regime_manager.py inhe padhta hai:
    "regime_behavior_defaults": {
        "BULL": {
            "size_mult": 1.00,
            "max_slots_mult": 1.00,
            "min_slots": 1,
            "tp1_full_exit": False,
            "trail_tightness": "NORMAL",
            "description": "Bull mode — normal/aggressive compounding",
        },
        "SIDEWAYS": {
            "size_mult": 0.60,
            "max_slots_mult": 0.60,
            "min_slots": 1,
            "tp1_full_exit": False,
            "trail_tightness": "TIGHT",
            "description": "Sideways mode — selective, reduced capital",
        },
        "BEAR": {
            "size_mult": 0.25,
            "max_slots_mult": 0.40,
            "min_slots": 1,
            "tp1_full_exit": True,
            "trail_tightness": "VERY_TIGHT",
            "description": "Bear mode — survival, take profit faster",
        },
        "RECOVERY": {
            "size_mult": 0.40,
            "max_slots_mult": 0.50,
            "min_slots": 1,
            "tp1_full_exit": True,
            "trail_tightness": "TIGHT",
            "description": "Recovery mode — cautious re-entry",
        },
    },

    # WFV
    "wfv_min_candles": 200,        # [VERIFIED QUANT METHOD] Robert Pardo Rolling Out-of-Sample sample floor
    "walk_forward_max_gap": 10,     # [VERIFIED QUANT METHOD] Train-Test win rate gap > 10% indicates overfitting (supplementary diagnostic)
    "wfv_efficiency_threshold": 0.5, # [VERIFIED QUANT METHOD] Walk-Forward Efficiency (OOS return / IS return) primary pass bar -- cross-verified industry standard (Pardo; StratBase, Backtrex, TradeStation, Quanthop walk-forward guides all cite 0.5 as the minimum acceptance threshold, 0.7+ as strong, <0.3 as severe overfit)

    # SEBI T+1 settlement — UPDATED 2026-07-29 (v3.1.2):
    # Purana SEBI peak-margin rule (Dec 2020-2021): 80% same-day, 20% next day.
    # CURRENT rule (SEBI change effective 7 Oct 2024): 100% of delivery sell
    # credit same-day usable — Dhan official Risk Management Policy confirms:
    # "100% of the sell credit of delivery trades can be utilised ... same day"
    # (dhan.co/risk-management-policy). Note: mechanism below stays for future
    # rule changes; 100 → 0% blocked = extra idle capital khatam.
    "sebi_release_pct": 100,      # [OWNER APPROVED 2026-07-29 per Dhan/SEBI post-Oct-2024 rule]

    # Subscription & Onboarding [AI-DOS WORKFLOW + v5.0 expiry rule]
    "paper_trial_days": 30,        # Free trial period for paper trading
    "live_sub_days": 28,           # 🅾️ OWNER POLICY (v5.0): 28-din active cycle
    "grace_days": 2,               # 🅾️ OWNER POLICY (v5.0): expiry ke baad 2-din GRACE (entry band, exit chalu)
    "live_sub_fee_inr": 3000,      # Live subscription fee in INR
    "razorpay_amount_inr": 3105,   # 🅾️ OWNER POLICY (v5.0): payment-link amount — fee + gateway (~3.5%), fixed amount (partial payments OFF)
    "expiry_reminder_days": 2,     # 🅾️ OWNER POLICY (v5.0): T-2 renewal alert (Telegram + payment link)
    "gtt_layer2_offset_pct": 0.2,  # 🅾️ OWNER POLICY (v5.0): Layer-2 GTT trigger = fixed SL − 0.2% (sirf L1 fail/miss pe lagta hai; SL fix rahta hai)

    # Backtest staleness [✅ CONCEPT VERIFIED: ongoing model monitoring — Fed SR 11-7 (2011) MRM;
    # regime change — Hamilton 1989 | 🅾️ VALUES = policy (quarter/half-year review convention),
    # owner bands approved 2026-07-30 — credit: AIRAF NIZAMI]
    "backtest_warn_days": 90,       # [🅾️ OWNER BAND 60-120] Quarterly model re-validation threshold
    "backtest_block_days": 180,     # [🅾️ OWNER BAND 120-270] Semi-annual model expiry block threshold

    # Sector exposure diversification
    "max_stocks_per_sector": 2,     # [VERIFIED QUANT METHOD] Markowitz sector concentration cap

    # Strategy validator thresholds [VERIFIED QUANT METHOD: Model Risk Management Governance]
    "min_live_win_rate":                40,    # [✅ FORMULA-DERIVED (owner rule 2026-07-30): min_wr = 1/(1+effective R:R); 40 correct ONLY at R:R=1.5:1 — NOT a universal constant; auto-recalculates if R:R changes | guard band 30-45]
    "max_wr_gap_vs_backtest":           15,    # [✅ CONCEPT VERIFIED: overfit/drift detection — Bailey & López de Prado 2014 family | 🅾️ VALUE owner band 10-20, approved 2026-07-30]
    "min_profit_factor":                1.0,   # [✅ VERIFIED — STRUCTURAL] Economic breakeven (gross gains = gross losses); pure maths, LOCKED (owner confirmed) — no band
    "max_consecutive_losses_validator": 5,     # [✅ CONCEPT: binomial probability — Jacob Bernoulli 1713 (5 losses @50% WR = 3.1% chance) | 🅾️ VALUE owner band 3-7, default 5, approved 2026-07-30]
    "profit_degradation_alert_pct":     20.0,  # [🅾️ POLICY THRESHOLD — credit: AIRAF NIZAMI. Band 10-30; final value requires implementation validation + historical benchmark testing (2026-07-30 owner review)]
    "max_idle_trading_days":            10,    # [🅾️ OWNER POLICY band 5-15, approved 2026-07-30] Execution activity monitoring

    # Monte Carlo robustness
    "mc_robustness_min":                0.6,   # [✅ CONCEPT VERIFIED: Monte Carlo robustness — Boyle 1977, Efron 1979; PBO family — Bailey & López de Prado 2014 | 🅾️ VALUE owner band 0.5-0.8, approved 2026-07-30]
    "mc_deploy_max_dd_pct":             10.0,  # [🅾️ OWNER DECISION 2026-07-30: MC deploy-gate — worst-5% shuffled-path max-DD > 10% ⇒ BLOCK DEPLOYMENT (₹20,000 @ ₹2L ref capital); method: Monte Carlo bootstrap — Metropolis & Ulam 1946 / Boyle 1977 / Efron 1979]
    "candle_lookback":                  100,   # [VERIFIED QUANT METHOD] Statistical lookback depth
    "timeframe":                        "1D",  # [ADMIN APPROVED] Canonical Daily timeframe (Sharia CNC delivery standard)

    # Trading cost
    "trading_cost_pct": 0.30,       # [VERIFIED QUANT METHOD] Sourced directly from published SEBI/Dhan brokerage rate card

    # ── v3.2 Custom Sharia & Non-Muslim Board System [DESIGN: AIRAF NIZAMI] ──
    # Owner criteria: Core Business Halal (Sharia law) + 100% Non-Muslim
    # Board of Directors (nahi to trade BLOCK) + Price>100 + Liquid.
    # R39 CORRECTED: Weekly verification 09:00-15:30 operating window, missing/stale/fetch/parse failure → BLOCK
    # Do not silently convert weekly verification into monthly-only refresh.
    "board_update_cron_day": 1,                 # 1st day of month — monthly full sync (legacy, kept for full refresh)
    "board_update_cron_hour": 8,                # 08:30 AM IST — monthly
    "board_update_cron_minute": 30,
    "board_weekly_verification_enabled": True,  # 🅾️ OWNER POLICY: R39 CORRECTED — weekly verification mandatory
    "board_weekly_verification_day": "mon",     # 🅾️ OWNER POLICY: weekly verification day (mon = Monday)
    "board_weekly_verification_hour": 9,        # 🅾️ OWNER POLICY: weekly verification 09:00-15:30 window — 09:30 IST
    "board_weekly_verification_minute": 30,     # 🅾️ OWNER POLICY: 09:30 IST weekly verification
    "board_data_stale_days_limit": 7,           # 🅾️ OWNER POLICY: R39 CORRECTED — weekly verification, fail-closed if >7 days no successful verification (was 35)
    "board_data_stale_days_hard_limit": 35,     # 🅾️ OWNER POLICY: hard limit 35 days — absolute max even if weekly fails
    "require_non_muslim_board": True,           # 100% Non-Muslim Board Required
    "require_core_business_halal": True,        # Core business 100% halal (Riba/Alcohol/Gambling/Pork/Adult/Tobacco exclude)
    "min_price_threshold": 100.0,               # Price > ₹100 only — ill-penny filter
    "enable_illiquid_filter": True,             # Block illiquid stocks
    "full_nse_bse_universe": False,             # Legacy flag retained; execution universe is strict NSE-EQ
    "enable_board_filter": True,                # Enable non_muslim_board column check

    # [AUDIT ADD] Turnover-based liquidity screen — MSCI Global Investable
    # Market Indices Methodology's ATVR (Annualized Traded Value Ratio) +
    # Frequency of Trading, adapted for NSE. Goal: only trade stocks that
    # ALWAYS have active buyers/sellers present (turnover relative to the
    # company's own size), so exit is reliably easy — not just entry.
    # This is separate from illiquid_asset_pct (a Sharia balance-sheet
    # ratio) — this is real trading-volume liquidity.
    "enable_turnover_liquidity_filter": True,
    "liquidity_lookback_trading_days": 63,      # ~3 months, matches MSCI's 3-month ATVR/FoT window
    "min_atvr_pct": 15.0,                       # MSCI Emerging Markets minimum (owner band 10-25)
    "min_frequency_of_trading_pct": 80.0,       # MSCI minimum — % of days with at least one trade
    "asm_gsm_list_max_age_days": 7,             # [OWNER DECISION 2026-09-05] ASM/GSM pre-screen list max age — NSE surveillance circulars ~weekly; older list = unverifiable = fail-closed entry block
    "liquidity_data_stale_days_limit": 45,      # Fail-closed if refresh hasn't succeeded in this long
    "market_metadata_min_verified": 1,          # At least one verified row is required before publishing a refresh
    "market_metadata_request_pause_sec": 0.15,  # Rate-limit external metadata requests
    "market_metadata_stale_days_limit": 7,       # Decision-critical metadata freshness

    # ── FIX-LIST 2026-09-04 items 1-3: live WebSocket tick path (ENGINEERING) ──
    "live_tick_min_interval_sec": 1.0,          # per-symbol exit re-evaluation throttle on ticks (API/CPU guard)
    "live_tick_atr_refresh_sec": 180,           # ATR cache TTL for tick-path exits (= 3-min monitor cadence)
    "live_feed_sync_interval_sec": 60,          # watchlist ↔ open-position sync job cadence
    # ── External heartbeat + partial-fill remainder (ops, not strategy) ──
    "healthcheck_interval_min": 2,              # 🛠 ENGINEERING: dead-man HTTP GET cadence while process is alive
    "healthcheck_http_timeout_sec": 5,          # 🛠 ENGINEERING: ping fail-open timeout
    "partial_fill_remainder_timeout_sec": 600,  # 🛠 ENGINEERING: unfilled remainder cancel after 10 min

    # ── PILLAR 2 & 3: Fundamental Data & Sync Engine (r39 CORRECTED — REAL ONLY, PIT-SAFE, FAIL-CLOSED) ──
    # 10-20 years quarterly fundamentals (Screener.in / NSE Archives) — PIT format — REAL ONLY, NO SYNTHETIC IN PRODUCTION
    # Technical remains Dhan-only; fundamentals are REAL and gate trading via fail-closed when mandatory
    # Provenance: source → retrieval_ts → financial period → publication_timestamp → as-of visibility → transformation → final feature → decision
    "enable_fundamental_filter": True,          # 🅾️ OWNER POLICY: master switch for fundamental+technical sync
    "fundamental_filter_mandatory": True,       # 🅾️ OWNER POLICY: R39 CORRECTED — missing/stale/corrupt/invalid → NO TRADE (fail-closed), not PASS/NEUTRAL
    "fundamental_data_dir": "data/fundamentals", # 🛠 ENGINEERING: PIT JSON storage (REAL ONLY)
    "fundamentals_db": "data/fundamentals.db",   # 🛠 ENGINEERING: PIT SQLite (REAL ONLY, synthetic banned)
    "fundamentals_min_quarters": 40,            # ✅ VERIFIED CONVENTION: 10 years quarterly = 40, 20y = 80
    "fundamentals_max_quarters": 80,            # ✅ VERIFIED CONVENTION: 20 years max
    "fundamental_real_only": True,              # 🅾️ OWNER POLICY: R39 CORRECTED — synthetic banned from production, only real sources allowed
    "fundamental_pit_strict": True,             # 🅾️ OWNER POLICY: R39 CORRECTED — AS_OF(T) strict PIT, no future leakage
    # Weak thresholds — triggers REJECT (bull trap / gap-down risk) — validated walk-forward, not max profit optimized
    "fund_weak_max_debt_to_equity": 1.0,        # 🅾️ OWNER POLICY: D/E >1.0 = high leverage
    "fund_weak_max_promoter_pledging_pct": 20.0, # 🅾️ OWNER POLICY: pledging >20% = governance risk
    "fund_weak_min_interest_coverage": 1.5,     # ✅ VERIFIED CONVENTION: IC <1.5 = distress (Damodaran)
    "fund_weak_min_roce": 5.0,                  # ✅ VERIFIED CONVENTION: ROCE <5% = poor capital efficiency
    "fund_weak_max_piotroski": 3,               # ✅ VERIFIED CONVENTION: Piotroski <=3 = weak (Piotroski 2000)
    # Strong thresholds — triggers PRIORITIZE (high-probability) — walk-forward validated
    "fund_strong_max_debt_to_equity": 0.3,      # 🅾️ OWNER POLICY: D/E <0.3 = low debt
    "fund_strong_max_promoter_pledging_pct": 5.0, # 🅾️ OWNER POLICY: pledging <5% = clean governance
    "fund_strong_min_interest_coverage": 3.0,   # ✅ VERIFIED CONVENTION: IC >3 = safe (Damodaran)
    "fund_strong_min_roce": 15.0,               # ✅ VERIFIED CONVENTION: ROCE >15% = efficient
    "fund_strong_min_piotroski": 7,             # ✅ VERIFIED CONVENTION: Piotroski >=7 = strong
    "fund_cfo_pat_min_ratio": 0.8,              # ✅ VERIFIED CONVENTION: CFO >=80% PAT = healthy cash conversion
}

# ═════════════════════════════════════════════════════════════════════════
# NUMBER PROVENANCE REGISTRY (v4.3 — owner constitution, machine-enforced)
# -----------------------------------------------------------------------
# RULE: Har numeric/dict value jo OPTIMIZABLE_DEFAULTS me hai uska source
# yahan registered hona ZAROORI hai. Naya number bina entry ke aaya →
# test_sequence.py ka CONSTITUTION check FAIL → system me entry nahi.
#
# Valid sources (is ke bahar koi category allowed nahi):
#   OWNER_POLICY        = owner/admin ka fixed decision (price, goal,
#                         emergency cap, policy walls/bands)
#   OPTIMIZER_FALLBACK  = sirf default hai; optimizer per-stock override
#                         karta hai (PARAM_SPACE me search hota hai)
#   VERIFIED_CONVENTION = industry/research standard ya verified formula
#                         (Pardo, Connors, MSCI, SEBI-standard executions,
#                         statistical conventions) — optimize karna galat
#                         (overfitting), owner sirf tighten/loosen kar
#                         sakta hai
#   EXTERNAL_FACT       = duniya ka fact (regulator/broker/fiqh) — tune
#                         karna galat hoga
#   ENGINEERING         = infra/cache/compute/utility — strategy se alag,
#                         performance/ops ke liye
# ═════════════════════════════════════════════════════════════════════════
PARAM_SOURCES = {
    # ── Simulation/backtest engineering baseline (NOT real capital) ──
    "validator_reference_capital": {
        "source": "ENGINEERING",
        "detail": "backtest/simulation comparison baseline — real capital nahi (owner approved convention)",
    },

    # ── Entry/exit defaults ──
    # sl_pct/tp1_pct intentionally have NO entry here — they were removed
    # from OPTIMIZABLE_DEFAULTS/PARAMS to restore the fail-closed contract
    # (see config.py PARAMS comment). Do not re-add.
    "trail_multiplier":       {"source": "OPTIMIZER_FALLBACK", "detail": "optimizer PARAM_SPACE (ATR trail, backtest engine)"},
    "min_reward_risk":        {"source": "OWNER_POLICY", "detail": "Fixed exactly 1.8R lock; optimizer does not select RR; after lock, trailing handles uncapped profit"},
    "wick_multiplier":        {"source": "OPTIMIZER_FALLBACK", "detail": "SL hunt protection — wick/body ratio threshold, optimized per stock (search 1.0-3.0)"},
    "candle_body_ratio":      {"source": "OPTIMIZER_FALLBACK", "detail": "Candle body size relative to ATR — optimized per stock (search 0.5-3.0)"},
    "candle_wick_ratio":      {"source": "OPTIMIZER_FALLBACK", "detail": "Candle wick size relative to body — optimized per stock (search 0.5-3.0)"},
    "candle_confirmation":    {"source": "OPTIMIZER_FALLBACK", "detail": "Number of candles for pattern confirmation — optimized per stock (search 1-5)"},
    "candle_volume_mult":     {"source": "OPTIMIZER_FALLBACK", "detail": "Volume requirement for candle patterns — optimized per stock (search 1.0-3.0)"},
    
    # RSI Divergence parameters
    "divergence_lookback":    {"source": "OPTIMIZER_FALLBACK", "detail": "Bars to look back for RSI divergence — optimized per stock (search 5-30)"},
    "rsi_tolerance":          {"source": "OPTIMIZER_FALLBACK", "detail": "RSI difference tolerance for divergence — optimized per stock (search 1.0-10.0)"},
    
    # Volume Divergence parameters
    "volume_lookback":        {"source": "OPTIMIZER_FALLBACK", "detail": "Bars to look back for volume analysis — optimized per stock (search 5-30)"},
    "volume_threshold":       {"source": "OPTIMIZER_FALLBACK", "detail": "Volume decrease threshold — optimized per stock (search 0.5-0.9)"},
    
    # Candle-Volume parameters
    "candle_size_threshold":  {"source": "OPTIMIZER_FALLBACK", "detail": "Candle size relative to ATR — optimized per stock (search 0.3-1.0)"},
    "volume_spike_threshold": {"source": "OPTIMIZER_FALLBACK", "detail": "Volume spike multiplier — optimized per stock (search 1.0-3.0)"},
    
    # MTF Composite parameters
    "mtf_min_score":          {"source": "OPTIMIZER_FALLBACK", "detail": "Minimum score for MTF composite signal — NO CAP, optimizer decides per stock per phase (search 1-10)"},
    
    # Multiple Combo per Stock
    "max_combos_per_stock":   {"source": "COMPATIBILITY", "detail": "Deprecated; no fixed TOP-N tool limit. Optimizer may select any 1..11 tools per stock from the registered tool library."},
    "trail_activation_pct":   {"source": "ENGINEERING", "detail": "LEGACY compatibility field; ignored by canonical 1.8R lock-then-uncapped-trailing exit engine"},
    "trail_gtt_update_min_pct": {"source": "ENGINEERING",    "detail": "v5.3 GTT modify threshold — trail itna bada tabhi broker-side update (API cost control)"},
    "exit_mode":          {"source": "OPTIMIZER_FALLBACK", "detail": "v5.4 exit toolkit mode — fixed_tp|trail|hybrid|ratchet, optimizer per-stock decide karta hai (owner: lock/trail sirf ek tool)"},
    "profit_lock_pct":    {"source": "OPTIMIZER_FALLBACK", "detail": "v5.4 profit lock % (hybrid/ratchet) — profit reach hone ke baad loss me exit nahi (lalach-safe)"},
    "ratchet_step_pct":   {"source": "OPTIMIZER_FALLBACK", "detail": "v5.4 ratchet step — progressive profit locking, optimizer search 0.5-3.0"},
    "dd_buffer_pct":          {"source": "OWNER_POLICY",       "detail": "drawdown + buffer = soft-block trigger (owner decision)"},
    "recovery_days_wait":     {"source": "OWNER_POLICY",       "detail": "recovery-entry wait policy"},
    "reentry_cooldown_days":  {"source": "OPTIMIZER_FALLBACK", "detail": "optimizer PARAM_SPACE (1-7)"},

    # ── Phase detection (optimizer per-stock) ──
    # phase_ema_fast/phase_ema_slow/phase_adx_threshold intentionally have
    # NO entry here — same fail-closed-contract removal as sl_pct/tp1_pct
    # above. Do not re-add.

    # ── Phase-edge gate (statistical research conventions) ──
    "phase_edge_alpha":           {"source": "VERIFIED_CONVENTION", "detail": "one-sided t-test significance — research standard; owner tighten kar sakta hai (0.05)"},
    "phase_edge_min_oos_trades":  {"source": "VERIFIED_CONVENTION", "detail": "df >= 2 — t-statistic ki statistical necessity (strategy choice nahi)"},
    "phase_edge_train_fraction":  {"source": "VERIFIED_CONVENTION", "detail": "chronological IS/OOS split — Pardo-style train/test convention"},
    "phase_edge_fdr_alpha":      {"source": "VERIFIED_CONVENTION", "detail": "Benjamini-Hochberg 1995 FDR level — multiple-testing correction (7 tools × 3 phases = 21 tests/stock)"},
    "phase_edge_use_fdr":        {"source": "OWNER_POLICY",       "detail": "FDR correction toggle (default ON — judge protection)"},
    "atr_fallback_pct":          {"source": "ENGINEERING",        "detail": "ATR compute fail ho to close% fallback (0.02 → 2.0% config)"},
    "phase_min_train_candles":    {"source": "ENGINEERING",         "detail": "minimum in-sample phase sample for meaningful optimization"},
    "phase_tool_opt_n_calls":     {"source": "ENGINEERING",         "detail": "per-tool Bayesian compute budget (cost vs speed)"},
    "optuna_n_jobs":              {"source": "ENGINEERING",         "detail": "Optuna parallel trial workers — VPS 4; tests me 1 (determinism)"},
    "phase_threshold_relief_cap": {"source": "VERIFIED_CONVENTION", "detail": "trend-relief cap — RegimeFolio-style calibration knob"},

    # ── Connors RSI-2 (verified method ke canonical values) ──
    "connors_rsi2_oversold":   {"source": "VERIFIED_CONVENTION", "detail": "Connors & Alvarez 2009 canonical (<10); optimizer 5-15 range me per-stock tune karta hai"},
    "connors_crash_sma_period": {"source": "VERIFIED_CONVENTION", "detail": "Connors canonical crash-protection SMA(200); optimizer 150-250 range"},

    # ── Portfolio health bands (owner walls; machine andar calibrate karti hai) ──
    "health_active_min":   {"source": "OWNER_POLICY", "detail": "owner band 65-80 — machine live-cal karti hai"},
    "health_caution_min":  {"source": "OWNER_POLICY", "detail": "owner band 40-60 — machine live-cal karti hai"},
    "health_warning_min":  {"source": "OWNER_POLICY", "detail": "owner band 20-35 — machine live-cal karti hai"},

    # ── Capital deployment ──
    "max_slots":            {"source": "OWNER_POLICY",       "detail": "owner band 5-10 (Override-3); runtime candidate economics formula se (resolve_param)"},
    "risk_pct_per_trade":   {"source": "VERIFIED_CONVENTION", "detail": "Half-Kelly canonical default (Kelly 1956); daily budget dynamic"},
    "daily_loss_limit_pct": {"source": "OWNER_POLICY",       "detail": "ADMIN CONSTANT #3 — SOLE fixed risk cap; sirf emergency fallback (dynamic Half-Kelly budget pehle)"},

    # ── Safety / rapid-loss ──
    "max_trades_per_day":           {"source": "OWNER_POLICY", "detail": "execution frequency cap — daily risk budget se derived"},
    "rapid_loss_count":             {"source": "OWNER_POLICY", "detail": "fallback value; machine WR se k* = ln(p_cap)/ln(1-WR) derive karti hai"},
    "runs_test_streak_p_cap_pct":   {"source": "OWNER_POLICY", "detail": "5%-crossing target — owner value; k* formula derived (geometric tail)"},
    "rapid_loss_window_min":        {"source": "ENGINEERING",  "detail": "legacy MINUTES-mode window"},
    "rapid_loss_pause_min":         {"source": "ENGINEERING",  "detail": "legacy MINUTES-mode pause"},

    # ── Survival circuit (verified prop-trading conventions) ──
    "min_circuit_dd_pct":   {"source": "VERIFIED_CONVENTION", "detail": "prop 3-7% range ka conservative floor (Static Drawdown Explained)"},
    "survival_soft_mult":   {"source": "VERIFIED_CONVENTION", "detail": "prop convention: half of daily allowance as self-stop"},
    "survival_hard_mult":   {"source": "VERIFIED_CONVENTION", "detail": "tiered 50/75/100 escalation convention"},

    # ── Correlation bands (verified interpretation standards) ──
    "correlation_threshold":       {"source": "VERIFIED_CONVENTION", "detail": ">0.7-0.8 = high concentration (multi-source); 0.85 = conservative end"},
    "vix_correlation_threshold":   {"source": "VERIFIED_CONVENTION", "detail": "0.5 = moderate boundary, conservatively applied"},
    "usdinr_correlation_threshold": {"source": "VERIFIED_CONVENTION", "detail": "-0.4 moderate boundary — atypical FX sensitivity flag"},

    # ── Execution quality ──
    "max_spread_pct":        {"source": "VERIFIED_CONVENTION", "detail": "institutional microstructure execution standard"},
    "target_portfolio_vol":  {"source": "VERIFIED_CONVENTION", "detail": "Risk Parity/Inverse-Vol reference (Bridgewater 10-12%, PA II 18%); owner band 10-20"},

    # ── Market regime classification (FIX-04 verified values, config-driven) ──
    "regime_ema_fast":          {"source": "VERIFIED_CONVENTION", "detail": "standard EMA trend structure (50/200)"},
    "regime_ema_slow":          {"source": "VERIFIED_CONVENTION", "detail": "standard EMA trend structure (50/200)"},
    "regime_ema200_rise_lookback": {"source": "VERIFIED_CONVENTION", "detail": "EMA200 rising check — short lookback convention"},
    "vix_high_level":           {"source": "VERIFIED_CONVENTION", "detail": "FIX-04 verified VIX levels"},
    "vix_rise_20d_pct":         {"source": "VERIFIED_CONVENTION", "detail": "FIX-04 verified VIX levels"},
    "vix_low_level":            {"source": "VERIFIED_CONVENTION", "detail": "FIX-04 verified VIX levels"},
    "multi_factor_bull_threshold":  {"source": "VERIFIED_CONVENTION", "detail": "FIX-04 multi-factor thresholds (config-driven)"},
    "multi_factor_bear_threshold":  {"source": "VERIFIED_CONVENTION", "detail": "FIX-04 multi-factor thresholds (config-driven)"},
    "multi_factor_recovery_score":  {"source": "VERIFIED_CONVENTION", "detail": "FIX-04 multi-factor thresholds (config-driven)"},
    "regime_weights":           {"source": "VERIFIED_CONVENTION", "detail": "4-evidence fusion weights (rebalanced after breadth delete); normalized + owner-tunable"},
    "ds_evidence_confidences":  {"source": "VERIFIED_CONVENTION", "detail": "Dempster-Shafer source-confidences (Dempster 1967/Shafer 1976)"},
    "sector_bear_regime_threshold_boost": {"source": "OWNER_POLICY", "detail": "BEAR policy knob (v4.0 config-driven; 1.0 = purana behavior)"},

    # ── News (LM 2011 verified method) ──
    "news_cache_ttl_min":        {"source": "ENGINEERING",         "detail": "full trading-day cache validity (240 min = market window)"},
    "news_prefetch_max_symbols": {"source": "ENGINEERING",         "detail": "pre-market prefetch budget cap (rate-limit friendly)"},
    "news_negation_window":      {"source": "VERIFIED_CONVENTION", "detail": "LM negation convention — negation word ke baad 3 tokens flip"},
    "news_max_headlines":        {"source": "ENGINEERING",         "detail": "per-symbol headline analysis count"},

    # ── Scan / sizing parity ──
    "scan_max_concurrent_fetches": {"source": "ENGINEERING",         "detail": "parallel Dhan fetch bound (rate-limit vs cycle budget)"},
    "parity_health_mult":          {"source": "VERIFIED_CONVENTION", "detail": "PIT-neutrality default 1.0 (point-in-time correctness); admin expected-live set kar sakta hai"},
    "parity_regime_mult":          {"source": "VERIFIED_CONVENTION", "detail": "PIT-neutrality default 1.0; admin expected-live set kar sakta hai"},
    "regime_behavior_defaults":    {"source": "OWNER_POLICY",       "detail": "FIX-05 regime size/slot policy — config-driven (optimizer/admin tune kar sakte hain)"},

    # ── Walk-forward validation (Pardo) ──
    "wfv_min_candles":          {"source": "VERIFIED_CONVENTION", "detail": "Pardo out-of-sample sample floor"},
    "walk_forward_max_gap":     {"source": "VERIFIED_CONVENTION", "detail": "Pardo train-test WR gap diagnostic (>10% = overfit signal)"},
    "wfv_efficiency_threshold": {"source": "VERIFIED_CONVENTION", "detail": "WFE >= 0.5 — Pardo + TradeStation/StratBase/Quanthop consensus (owner 0.6 kar sakta hai)"},

    # ── SEBI / broker facts ──
    "sebi_release_pct":  {"source": "EXTERNAL_FACT", "detail": "SEBI Oct-2024 / Dhan risk policy: 100% delivery sell-credit same-day"},
    "trading_cost_pct":  {"source": "EXTERNAL_FACT", "detail": "published SEBI/Dhan brokerage rate card"},

    # ── Subscription business (owner prices) ──
    "paper_trial_days":    {"source": "OWNER_POLICY", "detail": "ADMIN price/policy #1 family — free paper trial"},
    "live_sub_days":       {"source": "OWNER_POLICY", "detail": "ADMIN policy (v5.0): 28-din active + 2-din GRACE (grace_days)"},
    "grace_days":          {"source": "OWNER_POLICY", "detail": "ADMIN policy (v5.0): GRACE window — entry band, exit chalu, daily renewal alert"},
    "live_sub_fee_inr":    {"source": "OWNER_POLICY", "detail": "ADMIN PRICE #1 — ₹3000 subscription fee"},
    "razorpay_amount_inr": {"source": "OWNER_POLICY", "detail": "ADMIN PRICE (v5.0): ₹3105 payment-link amount — fee + gateway ~3.5%, fixed (partial OFF)"},
    "expiry_reminder_days": {"source": "OWNER_POLICY", "detail": "ADMIN policy (v5.0): T-2 dual-channel renewal alert (Telegram + payment link)"},
    "gtt_layer2_offset_pct": {"source": "OWNER_POLICY", "detail": "v5.0 3-layer GTT: L2 trigger = fixed SL − 0.2% (sirf L1 fail/miss pe; SL fix, koi trailing nahi)"},

    # ── Model governance (SR 11-7 spirit) ──
    "backtest_warn_days":   {"source": "OWNER_POLICY", "detail": "owner band 60-120 — quarterly re-validation convention"},
    "backtest_block_days":  {"source": "OWNER_POLICY", "detail": "owner band 120-270 — semi-annual expiry"},
    "max_stocks_per_sector": {"source": "VERIFIED_CONVENTION", "detail": "Markowitz sector concentration cap"},
    "min_live_win_rate":     {"source": "VERIFIED_CONVENTION", "detail": "formula: min_wr = 1/(1+effective R:R) — R:R badle to khud recalculate"},
    "max_wr_gap_vs_backtest": {"source": "OWNER_POLICY", "detail": "owner band 10-20 — drift detection"},
    "min_profit_factor":      {"source": "VERIFIED_CONVENTION", "detail": "breakeven maths (gross gains = gross losses) — LOCKED pure maths"},
    "max_consecutive_losses_validator": {"source": "OWNER_POLICY", "detail": "owner band 3-7 (5@50% WR = 3.1% chance — Bernoulli 1713 anchor)"},
    "profit_degradation_alert_pct": {"source": "OWNER_POLICY", "detail": "policy threshold — implementation validation + benchmark testing chahiye"},
    "max_idle_trading_days": {"source": "OWNER_POLICY", "detail": "owner band 5-15 — execution activity monitoring"},
    "mc_robustness_min":     {"source": "OWNER_POLICY", "detail": "owner band 0.5-0.8 (Monte Carlo robustness — Boyle/Efron method)"},
    "mc_deploy_max_dd_pct":  {"source": "OWNER_POLICY", "detail": "owner decision: worst-5% MC path DD > 10% → deploy block"},
    "candle_lookback":       {"source": "VERIFIED_CONVENTION", "detail": "statistical lookback depth convention"},

    # ── Board/universe ops ──
    "board_update_cron_day":     {"source": "ENGINEERING", "detail": "monthly full sync job schedule (1st of month) — full board refresh"},
    "board_update_cron_hour":    {"source": "ENGINEERING", "detail": "monthly full sync job schedule (08:30 IST pre-market)"},
    "board_update_cron_minute":  {"source": "ENGINEERING", "detail": "monthly full sync job schedule (08:30 IST pre-market)"},
    "board_weekly_verification_enabled": {"source": "OWNER_POLICY", "detail": "R39 CORRECTED — weekly verification mandatory 09:00-15:30 window"},
    "board_weekly_verification_day": {"source": "OWNER_POLICY", "detail": "R39 CORRECTED — weekly verification day (mon = Monday) — weekly, not monthly-only"},
    "board_weekly_verification_hour": {"source": "OWNER_POLICY", "detail": "R39 CORRECTED — weekly verification hour 09:00-15:30 window — 09:30 IST"},
    "board_weekly_verification_minute": {"source": "OWNER_POLICY", "detail": "R39 CORRECTED — weekly verification minute 09:30 IST"},
    "board_data_stale_days_limit": {"source": "OWNER_POLICY", "detail": "R39 CORRECTED — weekly verification fail-closed if >7 days no successful verification (was 35) — missing/stale/fetch/parse failure → BLOCK"},
    "board_data_stale_days_hard_limit": {"source": "OWNER_POLICY", "detail": "R39 CORRECTED — hard limit 35 days absolute max even if weekly fails"},
    "min_price_threshold":       {"source": "OWNER_POLICY", "detail": "owner criteria: price > ₹100 only (ill-penny filter)"},

    # ── MSCI liquidity (verified methodology) ──
    "liquidity_lookback_trading_days": {"source": "VERIFIED_CONVENTION", "detail": "MSCI GIMI 3-month ATVR/FoT window"},
    "min_atvr_pct":                    {"source": "VERIFIED_CONVENTION", "detail": "MSCI Emerging Markets minimum (owner band 10-25)"},
    "min_frequency_of_trading_pct":    {"source": "VERIFIED_CONVENTION", "detail": "MSCI minimum — % of days with at least one trade"},
    "asm_gsm_list_max_age_days":       {"source": "OWNER_POLICY", "detail": "ASM/GSM pre-screen list freshness bound — NSE surveillance circulars ~weekly; 7 days = conservative (owner decision 2026-09-05)"},
    "liquidity_data_stale_days_limit": {"source": "OWNER_POLICY", "detail": "fail-closed liquidity staleness limit"},

    # ── Data / Ops engineering (v5.0) ──
        "market_metadata_min_verified":      {"source": "ENGINEERING", "detail": "minimum verified metadata count before commit"},
    "market_metadata_request_pause_sec": {"source": "ENGINEERING", "detail": "rate-limit external metadata requests"},
    "market_metadata_stale_days_limit":  {"source": "OWNER_POLICY", "detail": "fail-closed market metadata staleness limit"},

    "daily_cache_stale_days": {"source": "ENGINEERING", "detail": "1D cache valid sirf current trading day"},
    "exit_verify_retry_sec":  {"source": "ENGINEERING", "detail": "exit market-order fill re-check wait (seconds)"},
    "order_verify_wait_sec":             {"source": "ENGINEERING", "detail": "entry order pehla status check wait — broker latency infra, strategy value nahi"},
    "order_verify_second_wait_sec":      {"source": "ENGINEERING", "detail": "entry order dusra wait (cancel se pehle); 10+10=20s total pending window"},
    "order_race_check_wait_sec":         {"source": "ENGINEERING", "detail": "cancel-fail last-millisecond fill race re-check wait"},
    "subscriber_order_verify_wait_sec":  {"source": "ENGINEERING", "detail": "subscriber copy order fill verify wait (broker latency infra)"},
    "order_status_default_wait_sec":     {"source": "ENGINEERING", "detail": "broker verify_order_status default wait (caller explicit nahi deta to)"},
    "fill_price_alert_threshold_pct":    {"source": "ENGINEERING", "detail": "admin alert threshold for signal-vs-actual-fill price gap after entry re-anchor"},

    # ── Entry follow + shadow log (v5.9 — owner D28 execution-only) ──
    "entry_follow_enabled":             {"source": "OWNER_POLICY", "detail": "D28 2026-08-20: entry pending order RESTING rahega (cancel nahi) — broker CMP touch pe execute; sirf execution rule, strategy zero touch"},
    "entry_follow_risk_units":          {"source": "OWNER_POLICY", "detail": "D28: cancel level = risk_units × (entry−SL) optimizer geometry; shadow data se refine (approval sirf owner)"},
    "entry_follow_check_interval_min":  {"source": "ENGINEERING", "detail": "follow tick cadence (position monitor cycle sync)"},
    "entry_follow_price_missing_ticks": {"source": "ENGINEERING", "detail": "CMP missing ke lagataar ticks → cancel (owner rule: bina price data trade nahi)"},
    "shadow_log_enabled":               {"source": "OWNER_POLICY", "detail": "D28: signal shadow observation (koi order nahi) — pending-level accuracy data"},
    "shadow_log_max_path_points":       {"source": "ENGINEERING", "detail": "per-symbol path points cap (~78 scans/day) — file size guard"},
    "shadow_log_min_samples":           {"source": "VERIFIED_CONVENTION", "detail": "recommendation minimum samples (small-sample stats convention)"},
    "shadow_log_min_return_pct":        {"source": "OWNER_POLICY", "detail": "return-zone valid return% judge (recommendation band)"},

    # ── String/categorical policy defaults ──
    "support_tool":        {"source": "OPTIMIZER_FALLBACK", "detail": "support detection tool — optimizer Categorical (50ema/100ema/200ema/50sma/200sma/vwap/swing_low)"},
    "rapid_loss_pause_mode": {"source": "OWNER_POLICY",       "detail": "owner decision 2026-07-29: 3 back-to-back losses → us din STOP (REST_OF_DAY)"},
    "lm_wordlist_file":    {"source": "VERIFIED_CONVENTION", "detail": "Loughran-McDonald 2011 published word lists ka bundled path"},
    "timeframe":           {"source": "OWNER_POLICY",        "detail": "canonical 1D daily timeframe (Sharia CNC delivery standard)"},

    # ── Overnight Movers module (v5.2 Phase-2 research) ──
    "overnight_max_candidates":    {"source": "OWNER_POLICY",         "detail": "owner: top-5 next-day movers"},
    "overnight_min_score":         {"source": "OPTIMIZER_FALLBACK",   "detail": "mini-optimizer tune karta hai (paper phase)"},
    "overnight_tp_pct":            {"source": "OPTIMIZER_FALLBACK",   "detail": "owner: exit optimizer decide karega — default research range me"},
    "overnight_sl_pct":            {"source": "OPTIMIZER_FALLBACK",   "detail": "overnight tight SL default; optimizer decide karega"},
    "overnight_volume_lookback":   {"source": "VERIFIED_CONVENTION",  "detail": "volume surge baseline — 20-day average (standard)"},
    "overnight_score_weights":     {"source": "VERIFIED_CONVENTION",  "detail": "research-informed initial weights (PEAD/volume/momentum/overnight-persistence/tug-of-war family); optimizer tune karta hai"},
    "overnight_persistence_lookback": {"source": "VERIFIED_CONVENTION", "detail": "Lou/Polk/Skouras 2019 (JFE): firm-level overnight returns predict future overnight — 5-day window"},
    "overnight_tug_of_war_lookback":  {"source": "VERIFIED_CONVENTION", "detail": "Akbas et al. 2021 (JFE): positive-overnight + negative-intraday reversal frequency — 20-day window"},
    "overnight_prefetch_max_symbols": {"source": "ENGINEERING",       "detail": "0 = pura universe; rate-limit budget cap"},
    "overnight_api_sleep_sec":     {"source": "ENGINEERING",          "detail": "Dhan rate-limit respect (1 req/sec convention)"},
    "overnight_min_paper_trades":  {"source": "VERIFIED_CONVENTION",  "detail": "paper proof minimum closed trades (small-sample stats convention)"},
    "overnight_edge_alpha":        {"source": "VERIFIED_CONVENTION",  "detail": "same one-sided t-test significance as phase gate"},

    # ── v5.7 hardcode migration sources (owner audit D1-D28) ──
    "india_gdp_growth_pct":        {"source": "EXTERNAL_FACT", "detail": "MoSPI/RBI official GDP growth — monthly review"},
    "india_inflation_pct":         {"source": "EXTERNAL_FACT", "detail": "MoSPI CPI official (July-2026: 4.45) — owner ne stale 4.5 pakda; monthly update"},
    "india_risk_free_rate_pct":    {"source": "EXTERNAL_FACT", "detail": "RBI risk-free reference rate"},
    "macro_warn_days":             {"source": "ENGINEERING",   "detail": "macro staleness warning window"},
    "hurdle_inflation_weight":     {"source": "VERIFIED_CONVENTION", "detail": "hurdle formula coefficient (documented design)"},
    "macro_adj_inflation_slope":   {"source": "VERIFIED_CONVENTION", "detail": "macro risk adjustment slope (documented design)"},
    "macro_adj_inflation_base":    {"source": "VERIFIED_CONVENTION", "detail": "macro adjustment neutral inflation base"},
    "minervini_52w_low_mult":      {"source": "VERIFIED_CONVENTION", "detail": "Minervini Trend Template criterion 6: 1.30×52w-low (Minervini 2013)"},
    "minervini_52w_high_mult":     {"source": "VERIFIED_CONVENTION", "detail": "Minervini criterion 7: 0.75×52w-high (Minervini 2013)"},
    "min_wr_guard_low":            {"source": "OWNER_POLICY",       "detail": "min_live_win_rate formula guard band (owner)"},
    "min_wr_guard_high":           {"source": "OWNER_POLICY",       "detail": "min_live_win_rate formula guard band (owner)"},
    "optimizer_score_penalties":   {"source": "OWNER_POLICY",       "detail": "institutional score penalties (Decision 16 family) — config-driven"},
    "optimizer_norm_baselines":    {"source": "OWNER_POLICY",       "detail": "score normalization baselines — config-driven"},
    "optimizer_adaptive_weight_base": {"source": "VERIFIED_CONVENTION", "detail": "profile-driven adaptive weight formula coefficients (documented design)"},
    "ruflo_score_weights":         {"source": "OWNER_POLICY",       "detail": "RuFlo ranking scale (owner design) — config-driven"},
    "ruflo_multipliers":           {"source": "OWNER_POLICY",       "detail": "RuFlo component multipliers (owner design)"},
    "ruflo_z_weights":             {"source": "OWNER_POLICY",       "detail": "RuFlo z-score blend weights (owner design)"},
    "brokerage_rate_pct":          {"source": "EXTERNAL_FACT", "detail": "Dhan equity DELIVERY brokerage is ₹0 (verified against 8+ current published sources incl. Dhan's own pricing page; true continuously since Dhan's 2021 launch, not a recent change). 0.06% was Dhan's INTRADAY rate, wrongly applied here in the original build — corrected 2026-09-06 (Section-10 provenance fix)."},
    "brokerage_min_inr":           {"source": "EXTERNAL_FACT", "detail": "No ₹40 cap applies to delivery — see brokerage_rate_pct note. Corrected 2026-09-06 (Section-10 provenance fix)."},
    "statutory_rate_pct":          {"source": "EXTERNAL_FACT", "detail": "STT/statutory 0.25% delivery (SEBI rate card)"},
    "confidence_mult_base":        {"source": "OWNER_POLICY",       "detail": "confidence sizing multiplier base (owner policy)"},
    "confidence_mult_slope":       {"source": "OWNER_POLICY",       "detail": "confidence sizing multiplier slope"},
    "confidence_mult_min":         {"source": "OWNER_POLICY",       "detail": "confidence multiplier clamp min"},
    "confidence_mult_max":         {"source": "OWNER_POLICY",       "detail": "confidence multiplier clamp max"},
    "universe_min_trades":         {"source": "OWNER_POLICY",       "detail": "universe quality gate: minimum trades (owner)"},
    "universe_min_wr_opt":         {"source": "OWNER_POLICY",       "detail": "universe quality gate: min WR (optimization source)"},
    "universe_min_wr_backtest":    {"source": "OWNER_POLICY",       "detail": "universe quality gate: min WR (backtest source)"},
    "support_band_mult":           {"source": "OPTIMIZER_FALLBACK", "detail": "support_bounce near-support band (1.01) — optimizer search me (v5.7)"},
    "vwap_rsi_max":                {"source": "OPTIMIZER_FALLBACK", "detail": "vwap_bounce RSI ceiling (60) — optimizer search me (v5.7)"},
    "ds_conflict_threshold":       {"source": "VERIFIED_CONVENTION", "detail": "Dempster-Shafer conflict guard K<0.99 (Dempster 1967/Shafer 1976)"},
    "overnight_price_blend":       {"source": "VERIFIED_CONVENTION", "detail": "overnight price-strength blend (research-informed)"},
    "overnight_price_saturation_pct": {"source": "VERIFIED_CONVENTION", "detail": "price-strength saturation (+5%)"},
    "overnight_volume_saturation_mult": {"source": "VERIFIED_CONVENTION", "detail": "volume surge saturation (3×)"},
    "overnight_persistence_saturation_pct": {"source": "VERIFIED_CONVENTION", "detail": "persistence normalization (1%/avg gap)"},
    "overnight_tug_saturation_ratio": {"source": "VERIFIED_CONVENTION", "detail": "tug-of-war normalization (0.5 ratio)"},
    "overnight_tp_grid":          {"source": "OPTIMIZER_FALLBACK", "detail": "overnight exit optimizer TP grid bounds"},
    "overnight_sl_grid":          {"source": "OPTIMIZER_FALLBACK", "detail": "overnight exit optimizer SL grid bounds"},
    "sim_worst_case_zscore":       {"source": "VERIFIED_CONVENTION", "detail": "90th percentile z-score 1.28 (statistical standard)"},
    "sim_recommended_buffer_mult": {"source": "OWNER_POLICY",       "detail": "recommended capital buffer 1.5× breakeven"},
    "sim_mc_quantiles":            {"source": "VERIFIED_CONVENTION", "detail": "Monte Carlo percentile quantiles (5/50/95 standard)"},
    "validator_pf_penalty_mult":   {"source": "OWNER_POLICY",       "detail": "strategy validator PF penalty slope"},
    "validator_pf_penalty_cap":    {"source": "OWNER_POLICY",       "detail": "strategy validator PF penalty cap"},
    "validator_rf_penalty_mult":   {"source": "OWNER_POLICY",       "detail": "strategy validator RF penalty slope"},
    "validator_rf_penalty_cap":    {"source": "OWNER_POLICY",       "detail": "strategy validator RF penalty cap"},
    "health_benchmark_wr_weight":  {"source": "OWNER_POLICY",       "detail": "portfolio health composite weight (WR)"},
    "health_benchmark_pf_weight":  {"source": "OWNER_POLICY",       "detail": "portfolio health composite weight (PF)"},
    "health_benchmark_return_weight": {"source": "OWNER_POLICY",    "detail": "portfolio health composite weight (return)"},
    "health_benchmark_rf_weight":  {"source": "OWNER_POLICY",       "detail": "portfolio health composite weight (RF)"},
    "trading_days_per_year":       {"source": "EXTERNAL_FACT", "detail": "NSE trading-days convention (252)"},
    "liquidity_fetch_buffer_mult": {"source": "ENGINEERING",   "detail": "liquidity data fetch buffer (2.2× lookback)"},
    "monte_carlo_n_sims":          {"source": "VERIFIED_CONVENTION", "detail": "Monte Carlo simulation count (Boyle/Efron bootstrap standard)"},
    "monte_carlo_percentile":      {"source": "VERIFIED_CONVENTION", "detail": "Monte Carlo safety percentile (5th worst path)"},
    "deployment_stage_pcts":       {"source": "OWNER_POLICY",       "detail": "staged deployment ladder 10/25/50/100 (owner)"},
    "live_tick_min_interval_sec":  {"source": "ENGINEERING",   "detail": "live-tick exit re-evaluation throttle (1 s) — infra guard, not strategy"},
    "live_tick_atr_refresh_sec":   {"source": "ENGINEERING",   "detail": "tick-path ATR cache TTL = existing 3-min monitor cadence"},
    "live_feed_sync_interval_sec": {"source": "ENGINEERING",   "detail": "live-feed watchlist sync cadence (60 s)"},
    "healthcheck_interval_min":    {"source": "ENGINEERING",   "detail": "external dead-man ping cadence (2 min) — Healthchecks.io/UptimeRobot; empty URL = skip"},
    "healthcheck_http_timeout_sec": {"source": "ENGINEERING",  "detail": "external healthcheck HTTP timeout; fail-open (never crash scheduler)"},
    "partial_fill_remainder_timeout_sec": {"source": "ENGINEERING", "detail": "partial-fill: protect filled qty immediately; cancel unfilled remainder after 10 min"},

    # ── PILLAR 2 & 3: Fundamental Data & Sync (r39 CORRECTED — REAL ONLY, PIT-SAFE, FAIL-CLOSED) ──
    "enable_fundamental_filter": {"source": "OWNER_POLICY", "detail": "master switch for fundamental+technical sync (Pillar 3)"},
    "fundamental_filter_mandatory": {"source": "OWNER_POLICY", "detail": "R39 CORRECTED — missing/stale/corrupt/invalid → NO TRADE (fail-closed), not PASS/NEUTRAL"},
    "fundamental_real_only": {"source": "OWNER_POLICY", "detail": "R39 CORRECTED — synthetic banned from production, only real sources (screener.in, nse.in, bse.in)"},
    "fundamental_pit_strict": {"source": "OWNER_POLICY", "detail": "R39 CORRECTED — AS_OF(T) strict PIT, no future leakage, backtest/live parity"},
    "fundamental_data_dir": {"source": "ENGINEERING", "detail": "PIT JSON storage dir for fundamentals (REAL ONLY)"},
    "fundamentals_db": {"source": "ENGINEERING", "detail": "PIT SQLite for fundamentals (REAL ONLY)"},
    "fundamentals_min_quarters": {"source": "VERIFIED_CONVENTION", "detail": "10y quarterly = 40 quarters (PIT)"},
    "fundamentals_max_quarters": {"source": "VERIFIED_CONVENTION", "detail": "20y quarterly = 80 quarters (PIT)"},
    "fund_weak_max_debt_to_equity": {"source": "OWNER_POLICY", "detail": "weak D/E >1.0 high leverage (Loss Pattern) — walk-forward validated"},
    "fund_weak_max_promoter_pledging_pct": {"source": "OWNER_POLICY", "detail": "weak pledging >20% governance risk — walk-forward validated"},
    "fund_weak_min_interest_coverage": {"source": "VERIFIED_CONVENTION", "detail": "IC <1.5 distress (Damodaran) — walk-forward validated"},
    "fund_weak_min_roce": {"source": "VERIFIED_CONVENTION", "detail": "ROCE <5% poor efficiency — walk-forward validated"},
    "fund_weak_max_piotroski": {"source": "VERIFIED_CONVENTION", "detail": "Piotroski <=3 weak (Piotroski 2000) — walk-forward validated"},
    "fund_strong_max_debt_to_equity": {"source": "OWNER_POLICY", "detail": "strong D/E <0.3 low debt — walk-forward validated"},
    "fund_strong_max_promoter_pledging_pct": {"source": "OWNER_POLICY", "detail": "strong pledging <5% clean governance — walk-forward validated"},
    "fund_strong_min_interest_coverage": {"source": "VERIFIED_CONVENTION", "detail": "IC >3 safe — walk-forward validated"},
    "fund_strong_min_roce": {"source": "VERIFIED_CONVENTION", "detail": "ROCE >15% efficient — walk-forward validated"},
    "fund_strong_min_piotroski": {"source": "VERIFIED_CONVENTION", "detail": "Piotroski >=7 strong — walk-forward validated"},
    "fund_cfo_pat_min_ratio": {"source": "VERIFIED_CONVENTION", "detail": "CFO >=80% PAT healthy cash conversion — walk-forward validated"},
}

# ─────────────────────────────────────────────
# MARKET TIMINGS (IST)
# ─────────────────────────────────────────────
MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:30"
MARKET_TIMEZONE = "Asia/Kolkata"

# ─────────────────────────────────────────────
# ORDER SETTINGS
# ─────────────────────────────────────────────
ORDER_TYPE = "MKT"                  # legacy default (backward compat)
ENTRY_ORDER_TYPE = "LMT"            # 🅾️ OWNER POLICY: entry = LIMIT CNC at bot signal price (or better)
EXIT_ORDER_TYPE = "MKT"             # 🅾️ OWNER POLICY: exit = MARKET CNC (SL/TP hit pe; fill-verify)
ORDER_SEGMENT = "NSE_EQ"
ORDER_PRODUCT = "CNC"               # CNC swing only — NEVER MIS. No 15:20 square-off.
# Owner freeze 2026-09-04:
# - Long-only CNC delivery. Hold overnight until SL/TP (or trail) hits.
# - Dhan AMO does not support MARKET → broker.place_order hard-blocks
#   all real BUY/SELL when market is closed (09:15-15:30 IST only).
# - Overnight protection = GTT forever order (not AMO market).
# - is_intraday_allowed is NOT an MIS switch: it only excludes BE/T2T
#   where same-day CNC exit is impossible (SL/TP would be stuck).
PENDING_ORDER_TIMEOUT_SEC = 120     # 2 min timeout
CRASH_PENDING_ORDERS_FILE = f"{DATA_DIR}/crash_pending_orders.json"  # v5.0 crash-window safety
PARTIAL_REMAINDER_FILE = f"{DATA_DIR}/partial_fill_remainders.json"  # partial-fill remainder cancel
INSTANCE_LOCK_FILE = f"{DATA_DIR}/bot_instance.lock"                  # v5.0 double-run guard

# ─────────────────────────────────────────────
# PAPER TRADING MODE
# True = no real orders, everything simulated
# MUST stay True during testing
# Change to False ONLY when ready for live
# ─────────────────────────────────────────────
PAPER_MODE = True
IS_PAPER_MODE = PAPER_MODE

# ─────────────────────────────────────────────
# STAGED DEPLOYMENT
# ─────────────────────────────────────────────
CURRENT_STAGE = 1  # Admin changes this manually


def load_optimized_params() -> dict:
    """Load optimizer output — overrides defaults if file exists."""
    import json
    params = OPTIMIZABLE_DEFAULTS.copy()
    try:
        if os.path.exists(OPTIMIZER_OUTPUT_FILE):
            with open(OPTIMIZER_OUTPUT_FILE, "r") as f:
                optimized = json.load(f)
            params.update(optimized)
    except Exception as e:
        import sys
        # Lazy import: utils.py itself imports FROM config.py, so a
        # top-level import here would be circular.
        from utils import redact_secrets
        print(redact_secrets(f"[CONFIG WARNING] Failed to load {OPTIMIZER_OUTPUT_FILE}: {e}"), file=sys.stderr)
    # OWNER CONTRACT: optimizer output can never alter the exact 1.8R lock.
    params["min_reward_risk"] = 1.8
    return params


# Active params (used by all modules)
PARAMS = load_optimized_params()

# v5.7: single source — ladder PARAMS (deployment_stage_pcts) se banta hai
_stage_pcts = list(PARAMS.get("deployment_stage_pcts", [10.0, 25.0, 50.0, 100.0]))
while len(_stage_pcts) < 4:
    _stage_pcts.append(100.0)
DEPLOYMENT_STAGES = {
    1: _stage_pcts[0] / 100.0,   # Stage-1 %
    2: _stage_pcts[1] / 100.0,   # Stage-2 %
    3: _stage_pcts[2] / 100.0,   # Stage-3 %
    4: _stage_pcts[3] / 100.0,   # Stage-4 %
}


# FIX-04: Market regime detection — Nifty 50 via Dhan
NIFTY_SECURITY_ID = os.getenv("NIFTY_SECURITY_ID", "13")  # Verify from Dhan scrip master
NIFTY_EXCHANGE_SEGMENT = os.getenv("NIFTY_EXCHANGE_SEGMENT", "IDX_I")
NIFTY_INSTRUMENT_TYPE = os.getenv("NIFTY_INSTRUMENT_TYPE", "INDEX")
MARKET_REGIME_FILE = f"{DATA_DIR}/market_regime.json"

# BSE Stocks Enable Plan (FIX-10)
ENABLE_BSE_TRADING = False   # True only after NSE paper trade complete

# ═════════════════════════════════════════════════════════════════════════════
# PHASE-2 PATCH P1 — MULTI-TIMEFRAME CONFIG (ADD-ONLY BLOCK)
# [Method: Multiple Time Frame Analysis — Dr. Alexander Elder, 1986]
# [Method: Tournament selection via Walk-Forward — Robert Pardo, 2008]
# This block defines MTF data/analysis parameters. MTF warehouse jobs and the
# optimizer signal generator are independently invoked; there is no global
# ═════════════════════════════════════════════════════════════════════════════
# COMPLETE TF menu — koi TF drop nahi (user requirement)
MTF_TIMEFRAMES = ["5m", "15m", "30m", "60m", "2H", "1D"]

# Dhan se DIRECT download hone wale TFs (cost control: API rate limit 1 req/sec)
MTF_DOWNLOAD_TFS = ["5m", "15m", "60m", "1D"]

# DERIVED TFs — FREE (bandwidth/API bachta hai). 30m←15m, 2H←60m
# [Method: session-anchored resampling — custom engineering, NSE 09:15–15:30 IST]
MTF_DERIVED_TFS = {"30m": "15m", "2H": "60m"}

# Warehouse location (Parquet). holdout/ sub-dir = final untouched test data
# [Method: Final Untouched Holdout — institutional Model Risk Management practice]
MTF_WAREHOUSE_DIR = f"{DATA_DIR}/mtf_warehouse"
MTF_HOLDOUT_FRACTION = 0.20   # aakhri 20% data = holdout (kabhi optimize nahi hoga)
MTF_ANCHOR_TIME = "09:15"     # NSE session open (IST) — resample anchor


# ═════════════════════════════════════════════════════════════════════════
# CONFIG SANITY CHECK (v5.0 — startup pe chalta hai; silent misconfig block)
# ═════════════════════════════════════════════════════════════════════════
def validate_config() -> list:
    """
    Boot-time sanity: critical numeric/structural invariants check karta
    hai. Returns list of human-readable problems (khali list = sab OK).
    Kuch bhi block nahi karta — warnings log hote hain; bot fail-closed
    gates pe pehle se depend karta hai.
    """
    problems = []
    p = PARAMS or {}

    def _num(key, lo, hi):
        try:
            v = float(p.get(key))
            if not (lo <= v <= hi):
                problems.append(f"{key}={v} out of [{lo},{hi}]")
        except (TypeError, ValueError):
            problems.append(f"{key} missing/non-numeric")

    _num("daily_loss_limit_pct", 0.5, 5.0)
    _num("live_sub_days", 1, 90)
    _num("grace_days", 0, 7)
    _num("razorpay_amount_inr", 100, 100000)
    _num("gtt_layer2_offset_pct", 0.0, 2.0)
    _num("risk_pct_per_trade", 0.05, 5.0)
    _num("wfv_efficiency_threshold", 0.0, 1.0)
    _num("phase_edge_alpha", 0.01, 0.5)
    _num("max_slots", 1, 20)
    _num("trading_cost_pct", 0.0, 2.0)
    _num("min_price_threshold", 1, 100000)

    if int(p.get("grace_days", 0)) >= int(p.get("live_sub_days", 30)):
        problems.append("grace_days >= live_sub_days — expiry rule galat")
    if int(p.get("live_sub_days", 28)) + int(p.get("grace_days", 2)) <= 0:
        problems.append("live_sub_days + grace_days <= 0")
    return problems

# ═════════════════════════════════════════════════════════════════════════
# NDSAP (prd.md Rule 15, Part C) — LIVE DATA ACCUMULATION ARCHIVE
# (ADD-ONLY BLOCK, 2026-09-13)
# [Method: NIZAMI Data Segregation & Accumulation Protocol — AIRAF NIZAMI,
#  owner-original; registered 2026-09-08, refined 2026-09-13. Owner
#  implementation authorization (Part C): 2026-09-13. Part B remains
#  REGISTERED-NOT-IMPLEMENTED — ToS pre-implementation blocker open.]
# Archive lives in its OWN SQLite file — separate from key_value_store and
# trading_bot.db per Rule 15 (C). Retention/compaction policy is derived
# from NDSAP_RETENTION_ESTIMATE.md (Rule 15 required deliverable).
NDSAP_ARCHIVE_DB = f"{DATA_DIR}/ndsap_archive.db"
NDSAP_ARCHIVE_ENABLED_DEFAULT = True
# Provider allowlist: ONLY 'dhan' until the owner clears the Rule 15 ToS
# review for yfinance/NSE/Moneycontrol STORAGE/reuse — the market_metadata
# tap exists but stays a no-op for gated providers (structural, not
# conventional: gated payloads are never written at all).
NDSAP_ARCHIVE_PROVIDERS_DEFAULT = ["dhan"]
# Bulk-refetch datasets keep the N most recent full payloads per
# symbol/dataset; older payloads expire (metadata+hash retained forever).
NDSAP_COMPACT_KEEP_LAST_DEFAULT = 5

# ═════════════════════════════════════════════════════════════════════════
# TELEMETRY (prd.md Rule 16) — DECISION & MARKET-CONTEXT BLACK BOX
# (ADD-ONLY BLOCK, r30 / 2026-09-15)
# [Owner-conceived "flight data recorder" spec, 2026-09-15: Dhan price
#  deta hai; telemetry bot ke DECISIONS + market ka MAHAUL record karti
#  hai — bid/ask spread, SEBI ASM/GSM status, regime, sector ranks, aur
#  har trade ke take/reject WHY. SILENT WATCHER: passive observation,
#  order/SL path se hamesha bahar, fail-OPEN — telemetry ki koi bhi
#  failure trading ko zero impact karegi.]
# Archive lives in its OWN SQLite file — separate from trading_bot.db,
# key_value_store and ndsap_archive.db (same isolation discipline as
# Rule 15 (C)). Append-only (flight-recorder immutability: SQLite
# triggers block DELETE/UPDATE on both tables); no compaction, retain
# forever — sizing estimate in SYSTEM_BLUEPRINT.md §11 (<5 MB/day worst,
# typically <1 MB/day at 5-min scan cadence).
TELEMETRY_DB = f"{DATA_DIR}/telemetry.db"
TELEMETRY_ENABLED_DEFAULT = True
# Bid/ask spread capture = 1 extra market-depth API call per candidate/
# entry only (NEVER per-universe-symbol — Dhan rate-limit discipline).
# Hard budget per scan; raw depth payloads already PIT-archived by
# NDSAP (dataset=market_depth) — telemetry stores the derived spread.
TELEMETRY_SPREAD_CAPTURE_DEFAULT = True
TELEMETRY_SPREAD_MAX_PER_SCAN_DEFAULT = 10
# Deterministic-replay input snapshot: last N completed daily bars
# (OHLCV) fed to the strategy, stored with CANDIDATE/ENTRY decision
# rows so a future strategy version can be replayed against the exact
# recorded market conditions. 0 disables bar capture.
TELEMETRY_INPUT_BARS_DEFAULT = 120
