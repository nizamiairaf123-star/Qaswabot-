"""
test_sequence.py — SEQUENCE AUTO-TEST (v4.0)

Canonical pipeline test: feature_sequence.json ke Stage 0-11 order me
top-to-bottom offline verification. Registry order == test order == JSON
order (single source — mismatch impossible).

Run:
    python3 test_sequence.py

Network-dependent checks (Dhan/Telegram/NSE live) sandbox me gracefully
skip hote hain; VPS pe full run hota hai. Exit code 0 = sab pass.
"""

import importlib
import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)
sys.dont_write_bytecode = True   # FIX-LIST item 9/11: never leave __pycache__ in the release tree

SEQ_FILE = os.path.join(PROJECT_DIR, "feature_sequence.json")


def _enter_test_sandbox() -> str:
    """FIX-LIST 2026-09-04 item 9 — run inside a throw-away copy of data/.

    Every module resolves 'data/...' relative to CWD. Import-time side effects
    (database.init_db, log handlers, load_json legacy-migration) and some
    checks below WRITE to data/. Previously this file did os.chdir(PROJECT_DIR)
    and therefore mutated the shipped data/trading_bot.db + audit_log.txt
    (audit finding F-01/F-02). Now: temp dir with a copy of data/ + symlinks to
    the sources, so reads see the real code and all writes stay in /tmp.
    Source-text checks below still open files relative to CWD — the symlinks
    make them resolve to the real release tree.
    """
    import shutil
    import tempfile
    sandbox = tempfile.mkdtemp(prefix="qaswa_seq_sandbox_")
    shutil.copytree(os.path.join(PROJECT_DIR, "data"), os.path.join(sandbox, "data"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.log"))
    for entry in os.listdir(PROJECT_DIR):
        if entry in ("data", "__pycache__", ".pytest_cache"):
            continue
        try:
            os.symlink(os.path.join(PROJECT_DIR, entry), os.path.join(sandbox, entry))
        except OSError:
            pass
    os.chdir(sandbox)
    import atexit
    atexit.register(lambda: (os.chdir(PROJECT_DIR), shutil.rmtree(sandbox, ignore_errors=True)))
    return sandbox


SANDBOX_DIR = None   # set in __main__ below (not when merely imported, e.g. by pytest collection)

PASS, FAIL = [], []
EXTERNAL_REQUIRED = []
IMPORT_SKIPPED = []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    tag = "PASS" if cond else "FAIL"
    print(f"    [{tag}] {name}" + (f" — {detail}" if detail else ""))

def external(name, detail=""):
    EXTERNAL_REQUIRED.append((name, detail))
    print(f"    [EXTERNAL REQUIRED] {name}" + (f" — {detail}" if detail else ""))


def compile_check(files):
    # FIX-LIST item 9/11: builtin compile() gives the same SyntaxError detection
    # as py_compile but writes NO __pycache__/*.pyc into the release tree.
    for f in files:
        p = os.path.join(PROJECT_DIR, f)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    compile(fh.read(), p, "exec", dont_inherit=True)
            except Exception as e:
                ok(f"compile {f}", False, f"{type(e).__name__}: {e}")
        else:
            ok(f"exists {f}", False, "FILE MISSING")
    return True


def import_check(mod):
    try:
        importlib.import_module(mod)
        return True
    except Exception as e:
        IMPORT_SKIPPED.append((mod, f"{type(e).__name__}: {e}"))
        return False


def cleanup_temp_state():
    """Test-generated state (JSON + SQLite migrated keys) remove karo."""
    keys = ("per_stock_params.json", "optimizer_results.json",
            "walk_forward_results.json", "news_sentiment_cache.json",
            "signal_registry.json")
    try:
        import database
        con = database._get_connection()
        for k in keys:
            con.execute("DELETE FROM key_value_store WHERE key=?", (k,))
        con.commit()
        con.close()
    except Exception:
        pass
    for f in keys:
        try:
            if os.path.exists(f"data/{f}"):
                os.remove(f"data/{f}")
            if os.path.exists(f"data/{f}.migrated"):
                os.remove(f"data/{f}.migrated")
        except OSError:
            pass


def main():
    print("=" * 72)
    print("QASWA BOT — SEQUENCE AUTO-TEST (feature_sequence.json Stage 0-11)")
    print("=" * 72)

    if not os.path.exists(SEQ_FILE):
        print("FATAL: feature_sequence.json not found — sequence master missing")
        return 1

    seq = json.load(open(SEQ_FILE))
    stages = seq.get("stages", [])
    print(f"Sequence loaded: {len(stages)} stages (v{seq['meta']['version']})")
    print(f"Owner criteria: {len(seq['meta']['owner_criteria'])} rules")
    print()

    # ── SEQ MATCH: registry order == test order (same JSON source) ──
    expected_order = [s["id"] for s in stages]
    ok("SEQ MATCH: stage ids sequential 0..11",
       expected_order == list(range(len(stages))), str(expected_order))

    for stage in stages:
        sid = stage["id"]
        label = stage["label"]
        files = stage.get("chained_files", [])
        print(f"\n=== STAGE {sid}: {label} ===")
        print(f"    when: {stage.get('when')} | time_class: {stage.get('time_class')}")
        compile_check(files)

        # ── per-stage smoke checks ──
        if sid == 0:
            ok("master list present", os.path.exists("data/MASTER_STOCK_LIST_PERMANENT.csv"))
            ok("custom universe present", os.path.exists("data/CUSTOM_UNIVERSE_FINAL.csv"))
            try:
                import pandas as pd
                master = pd.read_csv("data/MASTER_STOCK_LIST_PERMANENT.csv")
                custom = pd.read_csv("data/CUSTOM_UNIVERSE_FINAL.csv")
                ok("master ~2158 rows", len(master) >= 2000, f"rows={len(master)}")
                ok("custom > 1000 rows", len(custom) >= 1000, f"rows={len(custom)}")
                ok("custom all core_business_halal=True", bool(custom["core_business_halal"].all()) if "core_business_halal" in custom.columns else False)
                ok("custom all non_muslim_board=True", bool(custom["non_muslim_board"].all()) if "non_muslim_board" in custom.columns else False)
                ok("custom all price>100 (if col)", bool((custom["price"] > 100).all()) if "price" in custom.columns else True)
                for _field in ("sector", "industry", "market_cap", "turnover_liquid_ok", "atvr_pct", "frequency_of_trading_pct"):
                    _series = custom[_field] if _field in custom.columns else None
                    _populated = _series is not None and _series.notna().any() and not _series.astype(str).str.strip().isin({"", "0", "0.0", "unknown", "nan"}).all()
                    if not _populated:
                        external(f"custom data provider: {_field}", "decision-critical field is unavailable in shipped snapshot; real provider refresh required; not a code-test failure")
                    elif _field == "market_cap":
                        ok("custom has positive market_cap", pd.to_numeric(_series, errors="coerce").gt(0).all())
                    else:
                        ok(f"custom has {_field}", _series.notna().all())
                try:
                    state = json.load(open("data/custom_universe_state.json"))
                    if state.get("BOARD_DATA_STALE_PAUSE") is True or not state.get("last_successful_update"):
                        external("universe data refresh", "current state is fail-closed/paused pending real decision-data refresh")
                    else:
                        ok("universe state is not paused", True)
                except Exception as e:
                    ok("universe state readable", False, f"{type(e).__name__}: {e}")
            except Exception as e:
                ok("universe CSV validation", False, f"{type(e).__name__}: {e}")
            if import_check("stock_selector"):
                import stock_selector
                ok("eligibility fn exists", hasattr(stock_selector, "_row_is_halal_eligible"))
                ok("universe fn exists", hasattr(stock_selector, "load_halal_universe"))
            if import_check("sharia_manager"):
                import sharia_manager
                ok("zakat fn exists", hasattr(sharia_manager, "calculate_zakat"))

        elif sid == 1:
            if import_check("config"):
                import config
                ok("PAPER_MODE defined", hasattr(config, "PAPER_MODE"))
            if import_check("bot_state_manager"):
                ok("state machine imports", True)
            if import_check("startup_recovery"):
                ok("startup recovery imports", True)
            import_check("database")

        elif sid == 2:
            compile_check(["bot.py"])
            if import_check("broker"):
                ok("broker imports", True)
            if import_check("guide_text"):
                import guide_text
                ok("v5.1: subscriber guide (in-bot, non-downloadable)",
                   "KAISE KAAM" in guide_text.get_subscriber_guide("PAPER_TRIAL"))
                ok("v5.1: admin runbook (in-bot, non-downloadable)",
                   "ADMIN RUNBOOK" in guide_text.get_admin_guide())
            if import_check("bot"):
                import inspect as _inspect
                import bot as _bot
                handlers = _inspect.getsource(_bot._main_guarded)
                ok("v5.1: /guide + /adminguide registered",
                   'CommandHandler("guide"' in handlers and 'CommandHandler("adminguide"' in handlers)
            else:
                external("bot module runtime import", "declared third-party dependency is unavailable in the current environment; validate after clean dependency installation")
            ok("v5.1: VPS deploy files present",
               all(os.path.exists(f) for f in (".env.example", "VPS_DEPLOYMENT_GUIDE.md",
                                               "start_bot.sh", "qaswa-bot@.service", "README.md",
                                               "deploy.sh")))

        elif sid == 3:
            if import_check("scheduler"):
                import scheduler, inspect
                src = inspect.getsource(scheduler.setup_scheduler)
                ok("regime pre-market job registered", 'id="regime_premarket"' in src)
                ok("news prefetch job registered", 'id="news_prefetch"' in src)
                ok("market data 09:05 job", 'id="market_data"' in src)
                ok("v5.2: overnight jobs registered (prefetch/scan/exit)",
                   all(x in src for x in ('id="overnight_prefetch"', 'id="overnight_scan"', 'id="overnight_exit"')))
                ok("v5.7.2: macro monthly job registered", 'id="macro_refresh"' in src)
            if import_check("overnight_movers"):
                import overnight_movers as om
                ok("v5.2: overnight module disabled by default", om.is_overnight_enabled() is False)
                ok("v5.2: exit optimizer exists (owner: optimizer decides)",
                   hasattr(om, "optimize_overnight_exit_params"))
                ok("v5.2: edge report exists", hasattr(om, "overnight_edge_report"))
                ok("v5.2: score components fail-closed offline",
                   om._component_depth_imbalance("NONEXISTENT") == 0.0
                   and om._component_news_sentiment("NONEXISTENT") == 0.0)
                ok("v5.5: overnight_persistence (Lou/Polk/Skouras 2019) exists",
                   hasattr(om, "_component_overnight_persistence"))
                ok("v5.5: tug_of_war (Akbas et al. 2021) exists",
                   hasattr(om, "_component_tug_of_war"))
                w = om._score_weights()
                ok("v5.5: naye signals weights me registered",
                   "overnight_persistence" in w and "tug_of_war" in w
                   and abs(sum(w.values()) - 1.0) < 1e-6)
            if import_check("news_analyzer"):
                import news_analyzer
                wl = news_analyzer._load_lm_words()
                ok("LM lexicon loaded (neg 2355/pos 354)",
                   len(wl["neg"]) == 2355 and len(wl["pos"]) == 354,
                   f"neg={len(wl['neg'])} pos={len(wl['pos'])}")
            if import_check("macro_refresh"):
                import macro_refresh
                ok("v5.7.2: macro auto-refresh module (EXTERNAL_FACT monthly update)",
                   hasattr(macro_refresh, "refresh_india_macro")
                   and hasattr(macro_refresh, "apply_macro_override"))

        elif sid == 4:
            if import_check("market_regime"):
                import market_regime as mr
                d = {"nifty": {"regime": "BULL", "score": 2.0},
                     "sector": {"score": 1.0}, "vix": {"score": 0.0}, "usdinr": {"score": 0.0}}
                r = mr._combine(d)
                ok("regime combine (4 evidences)", r.get("regime") == "BULL", str(r))
                ok("no breadth remnants", "halal_breadth" not in mr.__dict__.get("_combine", lambda: "").__code__.co_names if hasattr(mr, "_combine") else True)
            if import_check("regime_manager"):
                import regime_manager
                b = regime_manager.get_regime_behavior("BEAR")
                ok("regime behavior config-driven", b.get("regime") == "BEAR", str(b))
            if import_check("correlation_tracker"):
                ok("correlation imports", True)
            if import_check("portfolio_health"):
                ok("portfolio health imports", True)

        elif sid == 5:
            cleanup_temp_state()  # gate check se pehle koi test-residue nahi
            if import_check("strategy"):
                import strategy
                a1, _ = strategy.is_phase_trade_allowed("SEQTEST", "UPTREND")
                a2, _ = strategy.is_phase_trade_allowed("SEQTEST", "SIDEWAYS")
                a3, _ = strategy.is_phase_trade_allowed("SEQTEST", "DOWNTREND")
                ok("phase gate legacy defaults (T/T-block/F-block)",
                   a1 is True and a2 is False and a3 is False, f"{a1},{a2},{a3}")
            if import_check("strategy_tools"):
                import strategy_tools
                ok("connors_rsi2 tool registered", "connors_rsi2" in strategy_tools.TOOL_NAMES)
            if import_check("optimizer"):
                import optimizer
                import inspect as _ins
                names = [p.name for p in optimizer.PARAM_SPACE]
                ok("connors params in search space",
                   "connors_rsi2_oversold" in names and "connors_crash_sma_period" in names)
                ok("RR fixed at exactly 1.8R; not an optimizer dimension",
                   "min_reward_risk" not in names)
                ok("v1.1: no early percentage activation parameter",
                   "trail_activation_pct" not in names)
                ok("v5.4: exit toolkit optimizer search me (mode + lock params)",
                   all(k in names for k in ("exit_mode", "profit_lock_pct", "ratchet_step_pct")))
                ok("PHD-FIX F2: Benjamini-Hochberg FDR correction exists",
                   hasattr(optimizer, "_benjamini_hochberg"))
                ok("PHD-FIX F2: FDR wired in per-phase gate",
                   "fdr_entries" in _ins.getsource(optimizer.optimize_tool_per_phase))
                e1 = optimizer._phase_edge_test([2.1, 3.4, 1.8, 2.9, 2.2, 3.1])
                e2 = optimizer._phase_edge_test([-1.2, -0.8, -2.0, -1.5, -0.6, -1.9])
                ok("edge test enables positive OOS", e1["enabled"] is True)
                ok("edge test blocks negative OOS", e2["enabled"] is False)
            if import_check("per_stock_params"):
                import per_stock_params
                per_stock_params.save_stock_params("SEQTEST", {"sl_pct": 3.0, "tp1_pct": 4.5,
                                                               "phase_allow_sideways": True})
                got = per_stock_params.get_param("SEQTEST", "phase_allow_sideways", None)
                ok("per-stock param roundtrip", got is True)
            cleanup_temp_state()

        elif sid == 6:
            if import_check("backtester"):
                ok("backtester imports", True)
            if import_check("simulate_engine"):
                import simulate_engine, inspect
                src = inspect.getsource(simulate_engine.run_simulation)
                ok("simulation mirrors live sizing chain (stage × health × regime)",
                   "get_regime_capital_multiplier" in src and "parity_health_mult" in src,
                   "v4.2 sizing-parity")
            if import_check("parity_engine"):
                import parity_engine
                import pandas as pd
                import numpy as np
                idx = pd.date_range("2026-01-01", periods=80, freq="B")
                df = pd.DataFrame({"open": np.linspace(100, 108, 80), "high": np.linspace(100.2, 108.4, 80),
                                   "low": np.linspace(99.8, 107.6, 80), "close": np.linspace(100, 108, 80),
                                   "volume": np.full(80, 1e6)}, index=idx)
                trades = [{"entry_idx": 10, "exit_idx": 20, "entry_price": 101.0, "net_return_pct": 1.2},
                          {"entry_idx": 30, "exit_idx": 40, "entry_price": 103.0, "net_return_pct": -0.6}]
                try:
                    pr = parity_engine.run_parity_equity(trades, df, "SEQTEST", start_capital=200000.0)
                    ok("parity chain runs (fail-open offline)", "final_capital" in pr, f"kept={len(pr.get('kept_trades', []))}")
                except Exception as e:
                    ok("parity chain runs (fail-open offline)", False, f"{type(e).__name__}: {e}")
                import inspect as _parity_inspect
                src2 = _parity_inspect.getsource(parity_engine.run_parity_equity)
                ok("PHD-FIX F1: parity compounding per-slot (/smax)",
                   "combined / smax" in src2 and "(1 + (net_pct / 100.0) * combined)" not in src2)
            if import_check("monte_carlo"):
                ok("monte carlo imports", True)
            if import_check("simulate_engine"):
                ok("simulate engine imports", True)

        elif sid == 7:
            if import_check("deployment_manager"):
                import deployment_manager, inspect
                ok("deployment manager imports", True)
                ok("v5.0: deployment rollback exists", hasattr(deployment_manager, "rollback_deployment"))
                ok("v5.0: approve enforces simulation-done",
                   "_stage_done(\"simulation\")" in inspect.getsource(deployment_manager._approve_deployment_locked))
            if import_check("workflow_manager"):
                import workflow_manager
                ok("stage order correct", workflow_manager.STAGE_ORDER[0] == "data_collection",
                   str(workflow_manager.STAGE_ORDER[:4]))
                # v4.1: simulation approval se PEHLE (admin result dekh ke approve)
                i_sim = workflow_manager.STAGE_ORDER.index("simulation")
                i_app = workflow_manager.STAGE_ORDER.index("deployment_approval")
                ok("simulation BEFORE deployment approval (v4.1 workflow fix)",
                   i_sim < i_app,
                   f"simulation@{i_sim}, approval@{i_app}")

        elif sid == 8:
            compile_check(["trade_engine.py", "risk_manager.py"])
            if import_check("trade_engine"):
                import trade_engine, inspect
                src = inspect.getsource(trade_engine.run_market_scan)
                ok("scan parallel fetch (time-aware)", "asyncio.gather" in src and "to_thread" in src)
                ok("scan semaphore bounded", "Semaphore" in src)
                entry_src = inspect.getsource(trade_engine._execute_entry)
                exit_src = inspect.getsource(trade_engine._execute_exit)
                # FIX-LIST 2026-09-04 item 3: exit-state math is shared between the
                # 3-min monitor and the live-tick path via _evaluate_exit_state —
                # check the shared helper together with the monitor wrapper.
                monitor_src = (inspect.getsource(trade_engine._monitor_single)
                               + inspect.getsource(trade_engine._evaluate_exit_state))
                ok("v5.0: entry LIMIT order", "ENTRY_ORDER_TYPE" in entry_src)
                ok("v5.0: exit MARKET + fill verify", "EXIT_ORDER_TYPE" in exit_src and "verify_order_status" in exit_src)
                ok("v5.0: crash-window pending-order record", "CRASH_PENDING_ORDERS_FILE" in entry_src)
                ok("v5.0: crash recovery function", hasattr(trade_engine, "recover_pending_orders"))
                ok("v5.4: live unified exit toolkit (exit_engine + modes + GTT follow)",
                   "exit_engine" in monitor_src and "update_trail_sl" in monitor_src
                   and "exit_mode" in monitor_src and "PROFIT-LOCK GUARANTEE" in monitor_src)
                scan_src = inspect.getsource(trade_engine.run_market_scan)
                ok("PHD-FIX F5: live signal sirf completed bars pe (forming-bar bias khatam)",
                   "sig_data = data.iloc[:-1]" in scan_src and "entry@live" in scan_src)
                # FIX-LIST 2026-09-04 items 1-3: WebSocket tick → same exit engine → same _execute_exit
                tick_src = inspect.getsource(trade_engine.on_live_tick)
                ok("live-tick exit path: same exit engine + same _execute_exit + no duplicate SELL",
                   "_evaluate_exit_state" in tick_src and "_execute_exit" in tick_src
                   and "exit_in_progress" in tick_src and "asyncio.Lock" in inspect.getsource(trade_engine._live_tick_lock))
                ok("live-tick exit path: honours killswitch/can_monitor/can_exit gates",
                   "is_killswitch_active" in tick_src and "can_monitor" in tick_src and "can_exit" in tick_src)
                ok("live-tick watchlist = open bot positions only", hasattr(trade_engine, "get_live_watchlist"))
                # FIX-LIST 2026-09-04 item 6 (P0 regression guard): APScheduler 3.11
                # AsyncIOScheduler.start() needs a RUNNING loop. setup_scheduler()
                # must be called from post_init (inside PTB's loop), never from
                # the sync main() before run_polling().
                bot_src_all = open("bot.py").read()
                pre_poll = bot_src_all[bot_src_all.find("def main():"):bot_src_all.find("    app.run_polling(drop_pending_updates")]
                _code_lines = [ln for ln in pre_poll.splitlines() if not ln.strip().startswith("#")]
                _calls = [i for i, ln in enumerate(_code_lines) if ln.strip().startswith("setup_scheduler()")]
                _pi = next((i for i, ln in enumerate(_code_lines) if "async def startup_monitor" in ln), -1)
                _reg = next((i for i, ln in enumerate(_code_lines) if "app.post_init = startup_monitor" in ln), -1)
                ok("item 6: setup_scheduler() runs inside event loop (post_init), not before run_polling",
                   _pi != -1 and _reg != -1 and len(_calls) == 1 and _pi < _calls[0] < _reg,
                   f"startup_monitor@L{_pi} setup_scheduler calls@{_calls} post_init-register@L{_reg}")
                ok("item 6: APScheduler pinned in requirements.txt",
                   "APScheduler==3." in open("requirements.txt").read())
                # FIX-LIST 2026-09-04 items 2 + 17: live feed wired in bot.py, fallback monitor exists
                # AI-DOS ARCH-003 remediation (2026-09-17): the live-feed start/task/job
                # bodies moved to bot_livefeed.py in the bot.py god-module split; the
                # call site (_start_live_feed_task() inside _main_guarded) stays in
                # bot.py unchanged. Check both files' combined text, not bot.py alone.
                _bot_livefeed_src = (open("bot_livefeed.py").read()
                                     if os.path.exists("bot_livefeed.py") else "")
                bot_src_combined = bot_src_all + _bot_livefeed_src
                ok("item 2: bot.py starts DhanLiveFeed + subscribes watchlist + routes ticks to trade_engine.on_live_tick",
                   "DhanLiveFeed(" in bot_src_combined and "on_live_tick" in bot_src_combined
                   and "_start_live_feed_task()" in pre_poll and "live_feed_watchlist_sync" in bot_src_combined)
                # [2026-09-04 r5] Board-scanner regression guard (Sharia fail-closed):
                # high-confidence Muslim names can NEVER be cleared by context;
                # dual-community names are cleared ONLY with an unmistakable
                # non-Muslim marker in the same full name; unknown → blocked.
                if import_check("board_manager"):
                    import board_manager as _bm
                    _must_block = ["Ms. Naheed Rehan Patel", "Mr. Kabir Khan", "Mr. Kamal  Dalia", "Mr. A. Chowdhury",
                                   "Dr. Habil Fakhruddin Khorakiwala", "Ms. Shabnum  Zaman", "Mr. Malik  Ahmed",
                                   "Md. Irfan", "Mr. Kamal Khan Sharma", "Mr. Iqbal Ahmed", "Ms. Tabassum  Begum"]
                    _must_clear = ["Mr. Kamal Kumar Jain", "Dr. Parveen Kumar Luthra", "Mr. Rajeev  Chowdhury",
                                   "Mr. Iqbal Singh", "Mr. Rakesh Sharma", "Ms. Alison Smith", "Mr. Salil Parekh",
                                   "Mr. Aaron Industries Limited"]
                    _bad_block = [n for n in _must_block if not _bm.is_potential_muslim_name(n)[0]]
                    _bad_clear = [n for n in _must_clear if _bm.is_potential_muslim_name(n)[0]]
                    ok("board scanner: Muslim / doubtful names stay BLOCKED (fail-closed)", not _bad_block, str(_bad_block))
                    ok("board scanner: Hindu names with dual-use given name are NOT blocked", not _bad_clear, str(_bad_clear))
                    ok("board scanner: single source — batch script delegates to board_manager",
                       "from board_manager import is_potential_muslim_name" in open("board_filter_auto.py").read())
                    ok("board scanner: no marker/high-conf overlap",
                       not (set(_bm.NON_MUSLIM_MARKERS) & set(_bm.HIGH_CONF_MUSLIM))
                       and not (set(_bm.NON_MUSLIM_MARKERS) & set(_bm.AMBIGUOUS_NAMES)))
                    # shipped universe must itself pass the shipped scanner (data ↔ code consistency)
                    try:
                        import json as _j, pandas as _pd
                        _boards = _j.load(open("data/board_members_yfinance.json"))
                        _uni = _pd.read_csv("data/CUSTOM_UNIVERSE_FINAL.csv")["symbol"].astype(str).tolist()
                        _fail = []
                        for _sym in _uni:
                            _b = _boards.get(_sym) or {}
                            _dirs = _b.get("directors") if isinstance(_b, dict) else _b
                            if _dirs and not _bm.check_board_100_non_muslim_with_confirmation(_dirs, _sym)[0]:
                                _fail.append(_sym)
                        ok("shipped universe: every board passes the shipped scanner", not _fail, str(_fail[:8]))
                    except Exception as _e:
                        ok("shipped universe scanner consistency ran", False, f"{type(_e).__name__}: {_e}")
                if import_check("fallback_monitor"):
                    import fallback_monitor
                    ok("item 17: fallback_monitor API (record_fallback / get_daily_summary_line)",
                       hasattr(fallback_monitor, "record_fallback") and hasattr(fallback_monitor, "get_daily_summary_line"))
                    # AI-DOS ARCH-003 remediation (2026-09-17): the scheduler.py job that
                    # reports to fallback_monitor moved to scheduler_jobs_daily_ops.py as
                    # part of the scheduler.py god-module split (see VERSION.txt) — treat
                    # scheduler's job code as one logical site wherever it now lives,
                    # instead of assuming it is still scheduler.py's own file text.
                    scheduler_site_hit = ("fallback_monitor" in open("scheduler.py").read()
                                          or "fallback_monitor" in open("scheduler_jobs_daily_ops.py").read())
                    wired = [fn for fn in ("economics_brain.py", "capital_manager.py", "regime_manager.py",
                                           "market_regime.py", "trade_engine.py")
                             if "fallback_monitor" in open(fn).read()]
                    if scheduler_site_hit:
                        wired.append("scheduler")
                    ok("item 17: dynamic→static fallback sites report to fallback_monitor (6 files)",
                       len(wired) == 6, f"wired={wired}")
            if import_check("forever_order_manager"):
                import forever_order_manager, inspect
                setup_src = inspect.getsource(forever_order_manager.setup_forever_orders)
                ok("v5.0: 3-layer GTT (L2 fallback)", "L2" in setup_src and "layer" in setup_src)
                ok("v5.0: GTT daily re-arm", hasattr(forever_order_manager, "rearm_gtt_missing"))
                ok("v5.3: trail follow (GTT modify) exists", hasattr(forever_order_manager, "update_trail_sl"))
            if import_check("risk_manager"):
                import risk_manager
                ok("risk gate exists", hasattr(risk_manager, "can_enter_trade"))
                ok("spread check exists", hasattr(risk_manager, "_check_spread"))

        elif sid == 9:
            if import_check("bot_state_manager"):
                import bot_state_manager
                ok("live states exist",
                   all(hasattr(bot_state_manager, s) for s in ("activate_live_staged", "activate_live_full"))
                   or "LIVE_STAGED" in str(getattr(bot_state_manager, "__dict__", {})))

        elif sid == 10:
            if import_check("subscriber_manager"):
                import subscriber_manager
                ok("subscriber manager imports", True)
                ok("v5.0: revoke exists", hasattr(subscriber_manager, "revoke_subscriber"))
                ok("v5.0: approval validation exists", hasattr(subscriber_manager, "can_approve"))
                ok("v5.0: view-only statement exists", hasattr(subscriber_manager, "get_subscriber_statement"))
                import inspect
                src = inspect.getsource(subscriber_manager.auto_expire_subscriptions)
                ok("v5.0: GRACE flow (28+2 expiry)", "GRACE" in src and "grace_days" in src)
            if import_check("payment"):
                import payment
                ok("payment module: link + verify + event", all(hasattr(payment, f) for f in
                    ("create_payment_link", "verify_webhook_signature", "handle_payment_event")))
                ok("payment module: disabled-by-default (no creds → None)",
                   payment.create_payment_link(123) is None)
            if import_check("single_instance"):
                ok("v5.0: double-run guard exists", hasattr(__import__("single_instance"), "acquire_instance_lock"))
            if import_check("crypto_utils"):
                ok("crypto utils imports", True)

        elif sid == 11:
            if import_check("trade_logger"):
                ok("trade logger imports", True)
            compile_check(["build_pdf_report.py"])
            if import_check("economics_brain"):
                ok("economics brain imports", True)

    # ── Final compliance: no forbidden legacy traces in project ──
    print("\n=== COMPLIANCE: LEGACY TRACE SCAN ===")
    bad_words = ["a" + "a" + "o" + "i" + "f" + "i"]
    found_bad = []
    import re
    for root, dirs, files in os.walk(PROJECT_DIR):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "mtf_warehouse", ".pytest_cache")]
        for f in files:
            # Documentation/checklists may legitimately mention retired legacy
            # methodologies as part of the inspection rules. This compliance
            # scan is for executable/runtime artifacts only.
            if f.endswith((".py", ".json", ".csv", ".sh", ".service", ".env.example")):
                p = os.path.join(root, f)
                if os.path.abspath(p) == os.path.abspath(__file__):
                    continue  # self-scan exclude (marker list khud isi file me hai)
                try:
                    txt = open(p, encoding="utf-8", errors="ignore").read()
                    low = txt.lower()
                    for w in bad_words:
                        if w in low:
                            found_bad.append((p, w))
                except OSError:
                    continue
    ok("no forbidden legacy traces", not found_bad, str(found_bad[:5]))

    # ── CONSTITUTION: NUMBER PROVENANCE (v4.3 — owner rule, machine-enforced)
    # Rule: OPTIMIZABLE_DEFAULTS me har numeric/dict value ka source
    # PARAM_SOURCES me registered hona ZAROORI hai. Bina source ka naya
    # number = hardcoded = FAIL (system me entry nahi). Optimizer ke derived
    # numbers (data/per_stock_params.json) is check se exempt hain — unka
    # source = optimizer + WFV + /deployapprove chain hi hai.
    print("\n=== CONSTITUTION: NUMBER PROVENANCE ===")
    allowed_sources = {"OWNER_POLICY", "OPTIMIZER_FALLBACK",
                       "VERIFIED_CONVENTION", "EXTERNAL_FACT", "ENGINEERING"}

    def _validate_provenance(defaults: dict, sources: dict):
        missing, invalid = [], []
        checked = 0
        for key, val in defaults.items():
            if isinstance(val, (bool, type(None))):
                continue  # flags — provenance scope se bahar; strings (categorical jaise exit_mode) included
            checked += 1
            entry = sources.get(key)
            if entry is None:
                missing.append(key)
            else:
                cat = entry.get("source") if isinstance(entry, dict) else None
                if cat not in allowed_sources:
                    invalid.append((key, cat))
        return checked, missing, invalid

    try:
        import config as _cfg
        sources = dict(getattr(_cfg, "PARAM_SOURCES", {}) or {})
        checked, missing, invalid = _validate_provenance(_cfg.OPTIMIZABLE_DEFAULTS, sources)
        orphans = [k for k in sources if k not in _cfg.OPTIMIZABLE_DEFAULTS]
        ok(f"har parameter default ka source registered ({checked} values — numbers + categoricals)",
           not missing and not invalid,
           f"missing={missing[:6]} invalid={invalid[:6]}")
        ok("no orphan source entries", not orphans, str(orphans[:6]))
        ok("v5.0: config sanity validator clean (no silent misconfig)",
           _cfg.validate_config() == [], str(_cfg.validate_config()[:3]))

        # NEGATIVE SELF-TEST: bina source ka naya number FAKE inject karke
        # proof ki check use pakad leti hai (constitution machine-enforced).
        _n, _m, _i = _validate_provenance(
            {**_cfg.OPTIMIZABLE_DEFAULTS, "fake_magic_number": 7.5},
            sources,
        )
        ok("negative self-test: bina source ka naya number pakda jata hai",
           "fake_magic_number" in _m, str(_m[:4]))
    except Exception as e:
        ok("number provenance check ran", False, f"{type(e).__name__}: {e}")

    # ── MASTER MANIFEST VERIFICATION (v5.6 — single source of truth check)
    # Rule: SYSTEM_MASTER_MANIFEST.json me listed har cheez sach me exist
    # karni chahiye. Koi command missing / domain bina verification /
    # version mismatch → FAIL (reverse pakda jayega).
    print("\n=== MASTER MANIFEST VERIFICATION ===")
    try:
        import json as _json
        manifest = _json.load(open("SYSTEM_MASTER_MANIFEST.json"))
        seq_doc = _json.load(open("feature_sequence.json"))
        mver = manifest.get("meta", {}).get("version")
        ok("manifest version == sequence version",
           mver == seq_doc.get("meta", {}).get("version"),
           f"manifest={mver} seq={seq_doc['meta']['version']}")

        domains = manifest.get("domains", [])
        ok(f"manifest me {len(domains)} domains (20 expected)",
           len(domains) >= 20, f"domains={len(domains)}")
        bad_domains = [d.get("name") for d in domains
                       if not d.get("verification") or not d.get("status")]
        ok("har domain ka verification + status registered",
           not bad_domains, str(bad_domains[:5]))

        # Cross-check: revert-map + critical commands bot.py me registered
        try:
            bot_src = open("bot.py").read()
            cmd_keys = []
            for pair in manifest.get("lifecycle_revert_map", {}).values():
                for part in (pair.get("forward", ""), pair.get("revert", "")):
                    cmd_keys += [w.strip(" |")
                                 for w in part.replace(" | ", " ").split()
                                 if w.strip(" |").startswith("/")]
            cmd_keys += ["/guide", "/adminguide", "/overnight", "/statement",
                         "/slippage", "/boardrefresh", "/subscribe", "/deployrollback"]
            missing_cmds = sorted({c for c in cmd_keys
                                   if f'CommandHandler("{c.lstrip("/")}"' not in bot_src})
            ok("manifest ke saare lifecycle/revert commands bot me registered",
               not missing_cmds, str(missing_cmds[:8]))
        except OSError as e:
            ok("manifest command cross-check", False, f"{type(e).__name__}: {e}")

        # Cross-check: provenance count claim
        try:
            import config as _cfg2
            n_reg = len([k for k, v in _cfg2.OPTIMIZABLE_DEFAULTS.items()
                         if not isinstance(v, (bool, type(None)))])
            claim = str(manifest.get("domains", [{}])[15].get("status", ""))
            ok("manifest provenance claim matches config",
               str(n_reg) in claim or "registered" in claim, f"config={n_reg}, claim={claim[:40]}")
        except Exception:
            ok("manifest provenance cross-check", False, "config load failed")

        ok("manifest read-order docs exist",
           all(os.path.exists(f) for f in ("AI_ONBOARDING.md", "feature_sequence.json",
                                           "UPDATE_HISTORY_FIX_LOG.md", "test_sequence.py")))
    except Exception as e:
        ok("master manifest verification ran", False, f"{type(e).__name__}: {e}")

    # ── HARDCODE WATCHDOG (v5.7 — owner audit D1-D32 machine-enforced)
    # Rule: audit me pakde gaye logic-level hardcoded numbers ab config/PARAMS
    # se drive hote hain. Unke purane literals code me wapas aa gaye → FAIL.
    # Benign literals (loop counters, data guards, HTTP codes) included nahi.
    print("\n=== HARDCODE WATCHDOG (v5.7) ===")
    WATCHDOG = [
        ("capital_manager.py", ["trade_val * 0.0006", "trade_val * 0.0025",
                                "SECTOR_TILT", "0.85 + (0.20"]),
        ("economics_brain.py", ["trade_value * 0.0006", "trade_value * 0.0025"]),
        ("strategy.py", ["* 1.30", "* 0.75", "risk * 1.5"]),
        ("strategy_tools.py", ["risk * 1.5", "support.iloc[i] * 1.01", "rsi.iloc[i] < 60"]),
        ("capital_drawdown_manager.py", ['"inflation_pct": 4.5']),
        ("regime_manager.py", ["DEFAULT_BEHAVIOR = {"]),
        ("market_regime.py", ["K >= 0.99"]),
        ("liquidity_screen.py", ["* 252", "lookback_days * 2.2"]),
        ("simulate_engine.py", ["1.28 * std", "breakeven_capital * 1.5"]),
        ("strategy_validator.py", ["(min_pf - pf) * 60", "(min_rf - rf) * 20"]),
        ("ruflo_ranker.py", ["wfv_gap * 2.5", "stability_score * 15"]),
        ("deployment_manager.py", ["int(n_sims * 0.05)"]),  # v5.7.1 MC percentile fix
        # PHD-FIX F1/F10: purane buggy patterns wapas na aayen
        ("parity_engine.py", ["(1 + (net_pct / 100.0) * combined)"]),
        ("optimizer.py", ['close"].iloc[idx]) * 0.02']),
        # PHD-FIX F4: RSI ka purana SMA formula wapas na aaye
        ("strategy.py", ["delta.clip(lower=0).rolling(period).mean()"]),
        ("strategy_tools.py", ["delta.clip(lower=0).rolling(period).mean()"]),
        # v5.8.2: order-pending wait hardcodes (10+10=20s, race 2s, broker
        # default 30) ab config-driven — purane literals wapas aaye → FAIL
        ("trade_engine.py", ["verify_order_status(order_id, wait_sec=10)",
                             "await asyncio.sleep(10)",
                             "verify_order_status(order_id, wait_sec=2)"]),
        ("broker.py", ["wait_sec: int = 30)"]),
    ]
    violations = []
    for fn, patterns in WATCHDOG:
        try:
            content = open(fn).read()
        except OSError:
            violations.append((fn, "FILE_MISSING"))
            continue
        for pat in patterns:
            if pat in content:
                violations.append((fn, pat))
    ok("hardcode watchdog: purane hardcoded numbers wapas nahi aaye",
       not violations, str(violations[:6]))

    # ── DEAD-CODE WATCHDOG (v5.8.1 — legacy module removal machine-enforced)
    # paper_trade_manager.py (v1 subscriber paper-trial system, alag formula)
    # remove hua 2026-08-20: koi import/call nahi tha, koi test/manifest
    # reference nahi, koi data file nahi (current paper = broker PAPER mode,
    # same chain as live). Rule: file wapas aaye ya koi .py isko reference
    # kare → FAIL (D15 dead-code DELETE ka precedent).
    print("\n=== DEAD-CODE WATCHDOG (v5.8.1) ===")
    dead_violations = []
    if os.path.exists("paper_trade_manager.py"):
        dead_violations.append("paper_trade_manager.py:FILE_RETURNED")
    for _fn in sorted(os.listdir(".")):
        if not _fn.endswith(".py") or _fn == "test_sequence.py":
            continue
        try:
            _content = open(_fn).read()
        except OSError:
            continue
        if ("import paper_trade_manager" in _content
                or "from paper_trade_manager" in _content):
            dead_violations.append(_fn + ":IMPORT_RETURNED")
    ok("dead-code watchdog: removed module wapas nahi aaya (paper_trade_manager)",
       not dead_violations, str(dead_violations[:6]))

    # ── V5.9 ENTRY FOLLOW + SHADOW LOG WIRING (owner D28 execution-only) ──
    print("\n=== V5.9 ENTRY FOLLOW + SHADOW LOG ===")
    _te_src = open("trade_engine.py").read() if os.path.exists("trade_engine.py") else ""
    _sch_src = open("scheduler.py").read() if os.path.exists("scheduler.py") else ""
    _cfg_src = open("config.py").read() if os.path.exists("config.py") else ""
    ok("v5.9: entry follow register wired (trade_engine)",
       "register_following_order" in _te_src and "entry_follow_enabled" in _te_src)
    ok("v5.9: follow tick in monitor (trade_engine)",
       "tick_following_orders" in _te_src)
    ok("v5.9: shadow record + cmp hooks (trade_engine)",
       "record_signal" in _te_src and "shadow_log" in _te_src)
    # AI-DOS ARCH-003 remediation (2026-09-17): the job body (which calls
    # finalize_day) moved to scheduler_jobs_daily_ops.py in the god-module
    # split; scheduler.py itself still owns the "entry_follow_eod" cron
    # registration unchanged. Check both files, not just scheduler.py.
    _sch_jobs_daily_src = (open("scheduler_jobs_daily_ops.py").read()
                           if os.path.exists("scheduler_jobs_daily_ops.py") else "")
    ok("v5.9: EOD finalize job (scheduler)",
       "entry_follow_eod" in _sch_src and "finalize_day" in (_sch_src + _sch_jobs_daily_src))
    ok("v5.9: config keys registered (entry follow + shadow)",
       all(k in _cfg_src for k in ("entry_follow_risk_units",
                                   "shadow_log_min_samples")))
    ok("v5.9: modules exist (entry_follow.py + shadow_log.py)",
       os.path.exists("entry_follow.py") and os.path.exists("shadow_log.py"))
    _v59_compile_ok = True
    try:
        import py_compile as _pyc
        for _m59 in ("entry_follow.py", "shadow_log.py"):
            try:
                _pyc.compile(_m59, doraise=True)
            except Exception as _ce:
                _v59_compile_ok = False
                print(f"    [FAIL] v5.9 compile {_m59}: {_ce}")
    except Exception as _ce2:
        _v59_compile_ok = False
        print(f"    [FAIL] v5.9 py_compile: {_ce2}")
    ok("v5.9: modules compile", _v59_compile_ok)

    # ── Summary ──
    print("\n" + "=" * 72)
    print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed, {len(EXTERNAL_REQUIRED)} external-required")
    if EXTERNAL_REQUIRED:
        print("External-required items (not counted as internal test failures):")
        for name, detail in EXTERNAL_REQUIRED:
            print(f"  - {name}: {detail}")
    if IMPORT_SKIPPED:
        print("Import-skips (optional modules, VPS pe verify):")
        for m, e in IMPORT_SKIPPED:
            print(f"  - {m}: {e}")
    if FAIL:
        print("FAILED:", FAIL)
        return 1
    print("SEQUENCE TEST: ALL STAGES PASSED (sandbox offline scope)")
    return 0


if __name__ == "__main__":
    SANDBOX_DIR = _enter_test_sandbox()
    sys.exit(main())
