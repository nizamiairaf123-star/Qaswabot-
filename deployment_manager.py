"""
deployment_manager.py — Semi-auto strategy deployment
Optimizer results → Walk-forward check → Admin alert → Approve/Reject → Deploy
"""

import logging
from utils import load_json, save_json, now_ist, append_log
from config import AUDIT_LOG_FILE, BACKTEST_RESULTS_FILE

logger = logging.getLogger(__name__)

DEPLOYMENT_STATE_FILE = "data/deployment_state.json"
PENDING_DEPLOYMENT_FILE = "data/pending_deployment.json"
DEPLOYMENT_LOCK_FILE = "data/deployment_lock.json"


def _pid_is_alive(pid: int) -> bool:
    """Return True if pid appears alive on this host."""
    if not pid or pid <= 0:
        return False
    try:
        import os
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _acquire_deployment_lock() -> tuple:
    """Acquire an exclusive deployment lock.

    Prevents two deployment approvals from committing simultaneously. If a
    prior process crashed and left a dead-PID lock, rollback any interrupted
    transaction before taking the lock.
    """
    import json
    import os

    os.makedirs("data", exist_ok=True)
    lock_payload = {
        "pid": os.getpid(),
        "acquired_at": now_ist().isoformat(),
        "purpose": "deployment_approval",
    }
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(DEPLOYMENT_LOCK_FILE, flags)
        with os.fdopen(fd, "w") as f:
            json.dump(lock_payload, f, indent=2)
        return True, "OK"
    except FileExistsError:
        lock = load_json(DEPLOYMENT_LOCK_FILE, {})
        pid = int(lock.get("pid", 0) or 0)
        if _pid_is_alive(pid):
            return False, "Deployment already in progress. Try again after current deployment completes."

        # Dead lock from crashed process: rollback interrupted transaction and
        # remove the stale lock, then acquire once.
        _recover_incomplete_deployment()
        try:
            os.remove(DEPLOYMENT_LOCK_FILE)
        except FileNotFoundError:
            pass
        fd = os.open(DEPLOYMENT_LOCK_FILE, flags)
        with os.fdopen(fd, "w") as f:
            json.dump(lock_payload, f, indent=2)
        return True, "OK"


def _release_deployment_lock():
    import os
    try:
        os.remove(DEPLOYMENT_LOCK_FILE)
    except FileNotFoundError:
        pass


# ─────────────────────────────────────────────
# DEPLOYMENT FLOW
# ─────────────────────────────────────────────

async def propose_deployment(new_params: dict, wfv_results: dict,
                              optimization_metrics: dict):
    """
    Called by optimizer after optimization + walk-forward.
    Saves proposal and alerts admin for approval.
    """
    # Check walk-forward validity
    valid_count   = sum(1 for r in wfv_results.values() if r.get("valid"))
    total_count   = len(wfv_results)
    validity_pct  = round(valid_count / max(total_count, 1) * 100, 1)

    # Save pending deployment
    proposal = {
        "proposed_at":         now_ist().isoformat(),
        "status":              "PENDING",
        "new_params":          new_params,
        "wfv_results_summary": {
            "valid":        valid_count,
            "total":        total_count,
            "validity_pct": validity_pct,
        },
        "wfv_results":         wfv_results,
        "optimization_metrics": optimization_metrics,
        "approved_by":          None,
        "approved_at":          None,
    }
    save_json(PENDING_DEPLOYMENT_FILE, proposal)

    # Alert admin
    from signal_broadcaster import alert_admin_sync
    alert_admin_sync(
        f"NEW STRATEGY OPTIMIZATION READY\n\n"
        f"Walk-Forward: {valid_count}/{total_count} stocks valid ({validity_pct}%)\n"
        f"Avg Win Rate: {optimization_metrics.get('avg_win_rate', 'N/A')}%\n"
        f"Avg Return/Trade: {optimization_metrics.get('avg_return', 'N/A')}%\n\n"
        f"Use /deployapprove to deploy\n"
        f"Use /deployreject to reject\n\n"
        f"Check /walkforward for details."
    )
    append_log(AUDIT_LOG_FILE,
               f"DEPLOYMENT PROPOSED: wfv={validity_pct}% valid")


def _deployment_target_files() -> list:
    from per_stock_params import PER_STOCK_PARAMS_FILE
    from config import OPTIMIZER_OUTPUT_FILE
    from workflow_manager import WORKFLOW_STATE_FILE
    return [
        PER_STOCK_PARAMS_FILE,
        OPTIMIZER_OUTPUT_FILE,
        BACKTEST_RESULTS_FILE,
        PENDING_DEPLOYMENT_FILE,
        "data/deployment_history.json",
        WORKFLOW_STATE_FILE,
    ]


def _recover_incomplete_deployment():
    """Rollback any prior interrupted deployment transaction before proceeding."""
    tx_file = "data/deployment_transaction.json"
    tx = load_json(tx_file, {})
    if not tx or tx.get("status") != "COMMITTING":
        return
    try:
        for filepath, backup in tx.get("backups", {}).items():
            if backup.get("existed"):
                save_json(filepath, backup.get("data", {}))
            else:
                import os
                try:
                    os.remove(filepath)
                except FileNotFoundError:
                    pass
        append_log(AUDIT_LOG_FILE, f"DEPLOYMENT TRANSACTION ROLLED BACK: {tx.get('tx_id')}")
    finally:
        import os
        try:
            os.remove(tx_file)
        except FileNotFoundError:
            pass


def _snapshot_targets(target_files: list) -> dict:
    import os
    backups = {}
    for filepath in target_files:
        backups[filepath] = {
            "existed": os.path.exists(filepath),
            "data": load_json(filepath, {}) if os.path.exists(filepath) else {},
        }
    return backups


def _rollback_deployment(backups: dict, tx_file: str):
    import os
    for filepath, backup in backups.items():
        if backup.get("existed"):
            save_json(filepath, backup.get("data", {}))
        else:
            try:
                os.remove(filepath)
            except FileNotFoundError:
                pass
    try:
        os.remove(tx_file)
    except FileNotFoundError:
        pass


def _build_candidate_benchmark(approved_per_stock: dict, blocked_symbols: list, approved_at: str) -> dict:
    optimizer = load_json("data/optimizer_results.json", {})
    opt_results = optimizer.get("results", {}) if isinstance(optimizer, dict) else {}
    missing = sorted([sym for sym in approved_per_stock if sym not in opt_results])
    if missing:
        raise ValueError(f"optimizer results missing for approved symbols: {', '.join(missing[:10])}")

    stocks = {}
    for sym in sorted(approved_per_stock.keys()):
        r = opt_results.get(sym, {})
        if not isinstance(r, dict) or not r:
            raise ValueError(f"optimizer result incomplete for {sym}")

        trades = r.get("trades_list") or r.get("trades") or []
        net = []
        for tr in trades:
            try:
                net.append(float(tr.get("net_return_pct", tr.get("return_pct", 0)) or 0))
            except (TypeError, ValueError):
                continue

        total_trades = int(r.get("total_trades", len(net)) or 0)
        if total_trades <= 0:
            raise ValueError(f"optimizer result has no trades for {sym}")
        wr = float(r.get("win_rate_pct", 0) or 0)
        wins = len([x for x in net if x > 0]) if net else int(round(total_trades * wr / 100))
        losses = max(0, total_trades - wins)

        avg_win = None
        avg_loss = None
        win_vals = [x for x in net if x > 0]
        loss_vals = [x for x in net if x <= 0]
        if r.get("avg_win_return") is not None:
            avg_win = round(float(r.get("avg_win_return") or 0), 2)
        elif win_vals:
            avg_win = round(sum(win_vals) / len(win_vals), 2)
        if r.get("avg_loss_return") is not None:
            avg_loss = round(float(r.get("avg_loss_return") or 0), 2)
        elif loss_vals:
            avg_loss = round(sum(loss_vals) / len(loss_vals), 2)

        max_consec_losses = 0
        if net:
            current_streak = 0
            for x in net:
                if x <= 0:
                    current_streak += 1
                    max_consec_losses = max(max_consec_losses, current_streak)
                else:
                    current_streak = 0

        portfolio_dd = r.get("portfolio_max_drawdown_pct", r.get("portfolio_max_dd_pct", 0))
        stocks[sym] = {
            "symbol": sym,
            "valid": True,
            "source": "optimization_walkforward",
            "backtest_date": approved_at,
            "strategy_name": "HalalMultiPhase",
            "strategy_version": "1.0",
            "total_trades": total_trades,
            "win_rate_pct": round(wr, 2),
            "winning_trades": wins,
            "losing_trades": losses,
            "total_return_pct": round(float(r.get("total_return_pct", 0) or 0), 2),
            "cagr_pct": round(float(r.get("cagr_pct", r.get("total_return_pct", 0)) or 0), 2),
            "avg_win_pct": avg_win,
            "avg_loss_pct": avg_loss,
            "profit_factor": round(float(r.get("profit_factor", 0) or 0), 2),
            "price_max_drawdown_pct": round(float(r.get("price_max_drawdown_pct", 0) or 0), 2),
            "portfolio_max_drawdown_pct": round(float(portfolio_dd or 0), 2),
            "avg_return_pct": round(float(r.get("avg_return_pct", 0) or 0), 2),
            "recovery_factor": round(float(r.get("recovery_factor", 0) or 0), 2),
            "sharpe": round(float(r.get("sharpe", 0) or 0), 2),
            "sortino": round(float(r.get("sortino", 0) or 0), 2),
            "max_consecutive_losses": max_consec_losses,
            "max_idle_days": None,
            "max_single_day_loss_pct": None,
            "trades_list": trades,
        }

    valid = list(stocks.values())
    if not valid:
        raise ValueError("candidate benchmark has no valid stocks")

    total_trades = sum(int(x.get("total_trades", 0)) for x in valid)
    wins = sum(int(x.get("winning_trades", 0)) for x in valid)
    losses = sum(int(x.get("losing_trades", 0)) for x in valid)
    total_return = sum(float(x.get("total_return_pct", 0)) for x in valid) / len(valid)
    cagr = sum(float(x.get("cagr_pct", 0)) for x in valid) / len(valid)
    dd = sum(float(x.get("portfolio_max_drawdown_pct", 0)) for x in valid) / len(valid)
    pf = sum(float(x.get("profit_factor", 0)) for x in valid) / len(valid)
    rf = sum(float(x.get("recovery_factor", 0)) for x in valid) / len(valid)
    sharpe = sum(float(x.get("sharpe", 0)) for x in valid) / len(valid)
    sortino_vals = [float(x.get("sortino", 0)) for x in valid if x.get("sortino") is not None]
    avg_sortino = round(sum(sortino_vals) / len(sortino_vals), 2) if sortino_vals else 0
    avg_ret = sum(float(x.get("avg_return_pct", 0)) for x in valid) / len(valid)
    win_pct_vals = [float(x.get("avg_win_pct")) for x in valid if x.get("avg_win_pct") is not None]
    loss_pct_vals = [float(x.get("avg_loss_pct")) for x in valid if x.get("avg_loss_pct") is not None]
    max_consec_all = [int(x.get("max_consecutive_losses", 0)) for x in valid]

    summary = {
        "total_trades": total_trades,
        "winning_trades": wins,
        "losing_trades": losses,
        "win_rate_pct": round(wins / total_trades * 100, 2) if total_trades else 0,
        "total_return_pct": round(total_return, 2),
        "cagr_pct": round(cagr, 2),
        "profit_factor": round(pf, 2),
        "recovery_factor": round(rf, 2),
        "sharpe": round(sharpe, 2),
        "sortino": avg_sortino,
        "avg_win_pct": round(sum(win_pct_vals) / len(win_pct_vals), 2) if win_pct_vals else None,
        "avg_loss_pct": round(sum(loss_pct_vals) / len(loss_pct_vals), 2) if loss_pct_vals else None,
        "max_consecutive_losses": max(max_consec_all) if max_consec_all else 0,
        "max_idle_days": None,
        "portfolio_max_dd_pct": round(dd, 2),
        "max_single_day_loss_pct": None,
        "tested_symbols": len(approved_per_stock),
        "successful_symbols": len(valid),
        "avg_return_pct": round(avg_ret, 2),
        "source": "optimization_walkforward",
    }

    return {
        "run_date": approved_at,
        "source": "optimization_walkforward",
        "analysis_window_days": 7300,
        "strategy_name": "HalalMultiPhase",
        "strategy_version": "1.0",
        "total_symbols": len(approved_per_stock),
        "successful": len(stocks),
        "failed": blocked_symbols,
        "active_symbols": sorted(stocks.keys()),
        "blocked_symbols": blocked_symbols,
        "portfolio_max_dd_pct": summary.get("portfolio_max_dd_pct", 0),
        "summary": summary,
        "stocks": stocks,
    }


def _mc_gate_core(returns_pct, capital, fee, tpm, dd_cap, rob_min, n_sims=1000):
    """MC gate math (shared by per-stock & portfolio). Seed=42 → auditable.
    Method: Monte Carlo bootstrap — Metropolis & Ulam 1946; Boyle 1977; Efron 1979."""
    import random
    try:
        from config import PARAMS
    except ImportError:
        PARAMS = {}
    rets = [r / 100.0 for r in returns_pct]
    path_fee = float(fee) * (len(returns_pct) / max(1.0, float(tpm)))
    rng = random.Random(42)
    dds, viable = [], 0
    for _ in range(int(n_sims)):
        path = rets[:]
        rng.shuffle(path)
        equity, peak, max_dd = capital, capital, 0.0
        for r in path:
            equity *= (1 + r)
            peak = max(peak, equity)
            dd = (equity - peak) / peak * 100.0
            if dd < max_dd:
                max_dd = dd
        if equity - capital - path_fee > 0:
            viable += 1
        dds.append(max_dd)
    robustness = viable / n_sims
    dds.sort()  # worst-5% = DD-distribution ka worst tail (same multiset ke shuffles ka final equity identical hota hai — DD percentile hi sahi selector hai)
    # v5.7: percentile ab config-driven (monte_carlo_percentile — VERIFIED
    # statistical convention; 5.0 default = VaR-95 family). Judge parameter,
    # optimization se nahi aata.
    _mc_pct = float(PARAMS.get("monte_carlo_percentile", 5.0))
    worst_5_dd = dds[min(len(dds) - 1, max(0, int(n_sims * _mc_pct / 100.0)))]
    if abs(worst_5_dd) > dd_cap:
        return {"ok": False, "dd": worst_5_dd, "robustness": robustness,
                "reason": f"worst-case path drawdown {abs(worst_5_dd):.1f}% > {dd_cap}% owner cap"}
    if robustness < rob_min:
        return {"ok": False, "dd": worst_5_dd, "robustness": robustness,
                "reason": f"economic-viability probability {robustness:.2f} < {rob_min} (net-of-fee profitable paths @ ₹{capital:,.0f})"}
    return {"ok": True, "dd": worst_5_dd, "robustness": robustness, "reason": "pass"}


def _econ_dd_cap_pct(gross_annual_pct, capital: float, fee_annual: float = None):
    """
    [DESIGN: AIRAF NIZAMI — owner idea 2026-07-30: "calmar + economics se cap
     aana chahiye; 10% kisi ke liye zyada, kisi ke liye kam sahi nahi."]
    Ye EXACT formula kisi ka published verified method NAHI hai — humara design
    hai (credit: AIRAF NIZAMI). Frames borrowed from verified sources:
      frame:  Calmar ratio = return/DD — Terry Young, 1991 (concept only)
      frame:  breakeven ≥1.0 structural — owner PF≥1.0 LOCKED precedent
    Per-stock DD cap = min( NET annual return after fee drag, 10% owner ceiling ).
      net = gross_CAGR% − fee_drag%   (fee_drag = annual fee / REAL capital)
    calmar ≥ 1.0 breakeven structural — worst DD jo 1 saal ki net kamai se zyada
    ho = year-one me recover nahi hoga, economics kharab (SAME structural idea
    as owner-LOCKED min_profit_factor ≥ 1.0). Method: Calmar — Terry Young 1991;
    breakeven-hurdle structural = owner constitution precedent.
    Koi naya constant NAHI: fee config se, capital REAL, gross WFV-verified
    benchmark se. Data missing → None (caller flat ceiling fallback, fail-open).
    """
    try:
        if fee_annual is None:
            from config import PARAMS as _P
            fee_annual = float(_P.get("monthly_subscription_fee", 3000.0)) * 12.0
        gross = float(gross_annual_pct)
        capital = float(capital)
        if capital <= 0:
            return None
        net = gross - (fee_annual / capital) * 100.0
        from config import PARAMS as _P2
        ceiling = float(_P2.get("mc_deploy_max_dd_pct", 10.0))
        return round(min(max(net, 0.0), ceiling), 2)
    except Exception as e:
        logger.warning(f"_econ_dd_cap_pct failed: {e}")
        return None


def _validate_monte_carlo_gate(candidate: dict, capital: float = None) -> tuple:
    """
    MONTE CARLO DEPLOY GATE v2 (owner orders 2026-07-30 — Section 12A.3 + 12A.4):
      1. Economics INVESTOR KE ACTUAL capital pe (owner: "har investor ka amount
         alag" + "real bal pata hona he chahiye") → capital None/invalid = BLOCK.
      2. DD + viability PER-STOCK aur PORTFOLIO dono level pe (owner: "dd
         portfolio and individual stock k lye").
      Flow: per-stock gate → failers DEMOTE (deploy list se out) → survivors ka
      pooled portfolio gate → dono pass = deploy allowed. Sab stocks fail = BLOCK.

    Rules (owner): worst-dd > mc_deploy_max_dd_pct(10%) ⇒ fail; robustness
    (economic-viability probability: net profit after fee+₹3,000/month
    subscription) < mc_robustness_min(0.6) ⇒ fail. FAIL-CLOSED (Art. 2.4a).
    Returns (ok, reason, info) — info = {per_stock, demoted, portfolio}.
    """
    try:
        from config import PARAMS, AUDIT_LOG_FILE
        from utils import append_log

        if capital is None:
            return False, ("MC gate: real balance unknown — owner rule 2026-07-30 "
                           "('real bal pata hona he chahiye') ⇒ fail-closed"), {"demoted": []}
        capital = float(capital)
        if not capital > 0:
            return False, f"MC gate: invalid real balance ₹{capital} — fail-closed", {"demoted": []}

        stocks = (candidate or {}).get("stocks", {}) or {}
        if not stocks:
            return False, "MC gate: candidate me koi stock nahi — fail-closed", {"demoted": []}

        try:
            from capital_drawdown_manager import get_verified_financial_economics
            econ = get_verified_financial_economics()
            fee = float(econ.get("subscription_fee", PARAMS.get("monthly_subscription_fee", 3000.0)))
            tpm = float(econ.get("expected_trades_per_month", PARAMS.get("default_trades_per_month", 15.0)))
        except Exception:
            fee = float(PARAMS.get("monthly_subscription_fee", 3000.0))
            tpm = float(PARAMS.get("default_trades_per_month", 15.0))
        dd_cap = float(PARAMS.get("mc_deploy_max_dd_pct", 10.0))
        rob_min = float(PARAMS.get("mc_robustness_min", 0.6))

        def _rets(stock):
            out = []
            for tr in (stock.get("trades_list") or []):
                try:
                    out.append(float(tr.get("net_return_pct", tr.get("return_pct", 0)) or 0))
                except (TypeError, ValueError):
                    continue
            return out

        # STEP 1: per-stock gates (owner: individual stock level DD + viability)
        # [Upgrade 2026-07-30] DD cap per-stock = ECONOMICS-DERIVED (net annual
        # return after fee @ REAL capital, Calmar-1 structural) — flat 10% sirf
        # ceiling + data-missing fallback. Owner: "10% sab pe ek jaisa galat hai."
        per_stock, survivors, demoted = {}, {}, []
        for sym, stock in stocks.items():
            rs = _rets(stock)
            if len(rs) < 10:
                per_stock[sym] = {"ok": False, "reason": f"insufficient trades ({len(rs)} < 10) — fail-closed"}
                demoted.append(sym)
                continue
            econ_cap = _econ_dd_cap_pct(stock.get("cagr_pct", stock.get("total_return_pct")),
                                        capital, fee_annual=fee * 12.0)
            stock_dd_cap = econ_cap if econ_cap is not None else dd_cap
            if econ_cap is not None and econ_cap <= 0.0:
                per_stock[sym] = {"ok": False, "dd_cap": stock_dd_cap,
                                  "reason": f"no net economic room: gross {stock.get('cagr_pct', stock.get('total_return_pct'))}% - fee drag ≈ 0 net @ ₹{capital:,.0f}"}
                demoted.append(sym)
                continue
            res = _mc_gate_core(rs, capital, fee, tpm, stock_dd_cap, rob_min)
            res["dd_cap"] = stock_dd_cap
            per_stock[sym] = res
            if res["ok"]:
                survivors[sym] = rs
            else:
                demoted.append(sym)

        if not survivors:
            detail = "; ".join(f"{k}: {v['reason']}" for k, v in list(per_stock.items())[:3])
            append_log(AUDIT_LOG_FILE,
                f"MC GATE BLOCK: all {len(stocks)} symbols failed MC verification @ ₹{capital:,.0f} ({detail})")
            return False, f"MC verification failed: all symbols rejected ({detail})",                    {"per_stock": per_stock, "demoted": demoted}

        # STEP 2: pooled portfolio gate — SIRF survivors pe (demoted pool se bahar)
        # [Upgrade 2026-07-30] pool cap bhi economics-derived: survivors ke gross
        # ka mean − fee drag (Calmar-1), flat 10% sirf ceiling/fallback.
        pooled = [r for rs in survivors.values() for r in rs]
        surv_gross = [float(stocks[sym].get("cagr_pct", stocks[sym].get("total_return_pct", 0)) or 0)
                      for sym in survivors]
        if surv_gross and any(g > 0 for g in surv_gross):
            pool_econ_cap = _econ_dd_cap_pct(sum(surv_gross) / len(surv_gross), capital,
                                             fee_annual=fee * 12.0)
        else:
            pool_econ_cap = None
        pool_dd_cap = pool_econ_cap if pool_econ_cap is not None else dd_cap
        pool_res = _mc_gate_core(pooled, capital, fee, tpm, pool_dd_cap, rob_min)
        pool_res["dd_cap"] = pool_dd_cap
        if not pool_res["ok"]:
            append_log(AUDIT_LOG_FILE,
                f"MC GATE BLOCK (portfolio) @ ₹{capital:,.0f}: {pool_res['reason']}")
            return False, f"MC verification failed (portfolio level): {pool_res['reason']}",                    {"per_stock": per_stock, "demoted": demoted, "portfolio": pool_res}

        if demoted:
            append_log(AUDIT_LOG_FILE,
                f"MC DEMOTION: {demoted} removed from deployment | survivors={sorted(survivors.keys())}")
        append_log(AUDIT_LOG_FILE,
            f"MC GATE PASS @ ₹{capital:,.0f}: portfolioDD={pool_res['dd']:.2f}% (cap {dd_cap}%) | "
            f"robustness={pool_res['robustness']:.2f} (min {rob_min}) | "
            f"stocks={len(survivors)}/{len(stocks)} | demoted={demoted}")
        return True, (f"MC gate pass @ ₹{capital:,.0f}: portfolioDD={pool_res['dd']:.1f}%, "
                      f"robustness={pool_res['robustness']:.2f}"
                      + (f" | demoted={demoted}" if demoted else "")),                {"per_stock": per_stock, "demoted": demoted, "portfolio": pool_res}

    except Exception as e:
        try:
            from config import AUDIT_LOG_FILE
            from utils import append_log
            append_log(AUDIT_LOG_FILE, f"MC GATE BLOCK: gate error (fail-closed): {type(e).__name__}: {e}")
        except Exception:
            pass
        return False, f"MC verification unavailable (fail-closed): {type(e).__name__}: {e}", {"demoted": []}


def _validate_candidate_benchmark(candidate: dict) -> tuple:
    try:
        from strategy_validator import _benchmark_quality
        from config import PARAMS
        summary = dict(candidate.get("summary", {}))
        summary["source"] = candidate.get("source", "optimization_walkforward")
        bq_score, issues = _benchmark_quality(summary)

        # [DESIGN upgrade 2026-07-30 — AIRAF NIZAMI: "Economic calculation kya kehta hai"]
        # BQ score = ECONOMIC-VIABILITY PROBABILITY (custom penalty-list hatao):
        #   score = 100 × P(net profit after broker+tax+₹3,000 subscription > 0)
        # Score-as-economics DESIGN humara hai (credit: AIRAF NIZAMI);
        # calculation engine = MC bootstrap — Boyle 1977 (verified);
        # economics frame: expected utility — von Neumann-Morgenstern 1944.
        # SAME _mc_gate_core engine as MC gate (single economics brain).
        # Hard-rule issues (min-WR formula / PF>=1.0 breakeven) UNCHANGED — wo
        # verified gates hain. Trades ya real balance missing → old deduction
        # score (fail-open, Art. 2.4a — guess nahi).
        try:
            trades = []
            for stock in (candidate.get("stocks", {}) or {}).values():
                for tr in (stock.get("trades_list") or []):
                    try:
                        trades.append(float(tr.get("net_return_pct", tr.get("return_pct", 0)) or 0))
                    except (TypeError, ValueError):
                        continue
            if len(trades) >= 10:
                from capital_manager import get_stage_readiness_decision
                cap = float(get_stage_readiness_decision().get("capital") or 0)
                if cap > 0:
                    try:
                        from capital_drawdown_manager import get_verified_financial_economics
                        econ = get_verified_financial_economics()
                        fee = float(econ.get("subscription_fee", PARAMS.get("monthly_subscription_fee", 3000.0)))
                        tpm = float(econ.get("expected_trades_per_month", PARAMS.get("default_trades_per_month", 15.0)))
                    except Exception:
                        fee = float(PARAMS.get("monthly_subscription_fee", 3000.0))
                        tpm = float(PARAMS.get("default_trades_per_month", 15.0))
                    core = _mc_gate_core(trades, cap, fee, tpm,
                                         float(PARAMS.get("mc_deploy_max_dd_pct", 10.0)),
                                         0.0)  # rob_min=0 → sirf robustness measure, no block
                    bq_score = round(core["robustness"] * 100.0, 2)
                    append_log(AUDIT_LOG_FILE,
                        f"BQ ECON SCORE: viability-prob {core['robustness']:.2f} ×100 = {bq_score} "
                        f"@ ₹{cap:,.0f} real capital ({len(trades)} trades; vNM-1944 economics)")
        except Exception as _e:
            logger.warning(f"BQ econ score failed, deduction score kept: {_e}")
        thresholds = PARAMS.get("strategy_validation_thresholds", {"red_bq_score": 50})
        if issues or bq_score < float(thresholds.get("red_bq_score", 50)):
            return False, f"candidate strategy validation failed: bq={bq_score} issues={' | '.join(issues)}"
        return True, "OK"
    except Exception as e:
        return False, f"candidate strategy validation error: {e}"


def _commit_deployment_transaction(proposal: dict, approved_per_stock: dict,
                                   global_params: dict, candidate_benchmark: dict,
                                   admin_chat_id: int, approved_at: str,
                                   fail_after_step: int = None):
    """Commit deployment after validation, rolling back on any commit exception."""
    tx_file = "data/deployment_transaction.json"
    target_files = _deployment_target_files()
    backups = _snapshot_targets(target_files)
    tx_id = f"deploy-{approved_at}"
    save_json(tx_file, {
        "status": "COMMITTING",
        "tx_id": tx_id,
        "started_at": approved_at,
        "backups": backups,
    })

    step = 0
    old_param_values = {}
    try:
        def mark_step():
            nonlocal step
            step += 1
            if fail_after_step is not None and step >= fail_after_step:
                raise RuntimeError(f"simulated deployment commit failure after step {step}")

        from per_stock_params import PER_STOCK_PARAMS_FILE
        from config import OPTIMIZER_OUTPUT_FILE, PARAMS

        per_stock_existing = load_json(PER_STOCK_PARAMS_FILE, {})
        for symbol, params in approved_per_stock.items():
            stored = dict(params)
            stored["updated_at"] = approved_at
            per_stock_existing[symbol] = stored
        save_json(PER_STOCK_PARAMS_FILE, per_stock_existing)
        mark_step()

        optimizer_existing = load_json(OPTIMIZER_OUTPUT_FILE, {})
        optimizer_existing.update(global_params)
        save_json(OPTIMIZER_OUTPUT_FILE, optimizer_existing)
        mark_step()

        save_json(BACKTEST_RESULTS_FILE, candidate_benchmark)
        mark_step()

        proposal["status"] = "APPROVED"
        proposal["approved_by"] = admin_chat_id
        proposal["approved_at"] = approved_at
        proposal["deployed_symbols"] = sorted(approved_per_stock.keys())
        proposal["blocked_symbols"] = candidate_benchmark.get("blocked_symbols", [])
        save_json(PENDING_DEPLOYMENT_FILE, proposal)
        mark_step()

        history_file = "data/deployment_history.json"
        history = load_json(history_file, {"deployments": []})
        history.setdefault("deployments", []).append(proposal)
        save_json(history_file, history)
        mark_step()

        from workflow_manager import record_deployment_approved
        record_deployment_approved(
            admin_chat_id=admin_chat_id,
            deployed_symbols=len(approved_per_stock),
            blocked_symbols=len(candidate_benchmark.get("blocked_symbols", [])),
            source="deployment_manager.approve_deployment",
        )
        mark_step()

        for k, v in global_params.items():
            old_param_values[k] = PARAMS.get(k)
            PARAMS[k] = v

        import os
        os.remove(tx_file)
    except Exception:
        _rollback_deployment(backups, tx_file)
        if old_param_values:
            from config import PARAMS
            for k, v in old_param_values.items():
                if v is None:
                    PARAMS.pop(k, None)
                else:
                    PARAMS[k] = v
        raise


async def approve_deployment(admin_chat_id: int):
    """Admin approves deployment using prepare -> validate -> commit.

    No live deployment state is modified until all proposal, WFV, optimizer,
    benchmark, stage-readiness, economics, and candidate strategy validations
    pass. Commit is transaction-backed and rolls back on commit exceptions.
    Concurrent approvals are blocked by an exclusive deployment lock.
    """
    lock_ok, lock_reason = _acquire_deployment_lock()
    if not lock_ok:
        append_log(AUDIT_LOG_FILE, f"DEPLOY BLOCKED: {lock_reason}")
        return lock_reason

    try:
        return await _approve_deployment_locked(admin_chat_id)
    finally:
        _release_deployment_lock()


async def _approve_deployment_locked(admin_chat_id: int):
    """Approval implementation that runs only while deployment lock is held."""

    proposal = load_json(PENDING_DEPLOYMENT_FILE, {})
    if not proposal or proposal.get("status") != "PENDING":
        return "No pending deployment."

    # v5.0 COMMAND LIFECYCLE: /deployapprove sirf tab jab admin ne /simulate
    # se result dekh liya ho (v4.1 workflow order — pehle simulation, phir
    # satisfied ho kar approval; bina result ke approve = galat decision risk).
    try:
        from workflow_manager import _stage_done
        if not _stage_done("simulation"):
            return ("Deployment blocked: pehle /simulate se result review karo "
                    "(v4.1 rule — approval sirf simulation result se satisfied hone ke baad).")
    except (ImportError, RuntimeError) as e:
        append_log(AUDIT_LOG_FILE, f"DEPLOY BLOCKED: simulation-stage check failed: {e} — fail-closed")
        return f"Deployment blocked: simulation review state unavailable ({e})."

    new_params = proposal.get("new_params", {})
    if not new_params:
        return "No params in proposal."

    per_stock = new_params.get("per_stock", {})
    if not isinstance(per_stock, dict) or not per_stock:
        return "Deployment blocked: no per-stock params in proposal."

    # F089: Missing WFV mapping fails closed. Never deploy all proposed symbols
    # as a legacy fallback.
    wfv_results = proposal.get("wfv_results")
    if not isinstance(wfv_results, dict) or not wfv_results:
        append_log(AUDIT_LOG_FILE, "DEPLOY BLOCKED: WFV map missing")
        return "Deployment blocked: walk-forward validation map missing. Run /optimize again."

    valid_symbols = {sym for sym, r in wfv_results.items() if isinstance(r, dict) and r.get("valid")}
    approved_per_stock = {sym: params for sym, params in per_stock.items() if sym in valid_symbols}
    blocked_symbols = sorted([sym for sym in per_stock.keys() if sym not in valid_symbols])

    if not approved_per_stock:
        append_log(AUDIT_LOG_FILE, "DEPLOY BLOCKED: no walk-forward-valid stocks")
        return "Deployment blocked: no walk-forward-valid stocks found. Run /optimize again."

    try:
        from capital_manager import get_stage_readiness_decision
        stage_ready = get_stage_readiness_decision()
        if not stage_ready.get("allow", False):
            return f"Deployment blocked: {stage_ready.get('reason')}"
    except Exception as e:
        return f"Deployment blocked: capital/stage readiness unavailable ({e})."

    opt_avg_return = float(proposal.get("optimization_metrics", {}).get("avg_return", 0) or 0)
    if opt_avg_return <= 0:
        return "Deployment blocked: optimization average return is not economically positive."

    approved_at = now_ist().isoformat()
    try:
        candidate_benchmark = _build_candidate_benchmark(approved_per_stock, blocked_symbols, approved_at)
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"DEPLOY BLOCKED: candidate benchmark build failed: {e}")
        return f"Deployment blocked: candidate benchmark unavailable ({e})."

    candidate_ok, candidate_reason = _validate_candidate_benchmark(candidate_benchmark)
    if not candidate_ok:
        append_log(AUDIT_LOG_FILE, f"DEPLOY BLOCKED: {candidate_reason}")
        return f"Deployment blocked by strategy approval: {candidate_reason}"

    # ── Monte Carlo deploy gate v2 (owner orders 2026-07-30 — Section 12A.3/12A.4) ──
    # Capital = investor ka REAL balance (stage readiness se — owner rule:
    # 'real bal pata hona he chahiye'). None/invalid ⇒ gate fail-closed BLOCK.
    mc_capital = None
    try:
        _sr = stage_ready if isinstance(stage_ready, dict) else {}
        mc_capital = float(_sr.get("capital") or 0) or None
    except Exception:
        mc_capital = None
    mc_ok, mc_reason, mc_info = _validate_monte_carlo_gate(candidate_benchmark, capital=mc_capital)
    if not mc_ok:
        append_log(AUDIT_LOG_FILE, f"DEPLOY BLOCKED: {mc_reason}")
        return f"Deployment blocked by Monte Carlo gate: {mc_reason}"

    # Per-stock MC failers → demote (deploy list se out); phir survivors pe
    # candidate rebuild + re-validate (owner: "jo stock fail ho use nikalo").
    mc_demoted = list(mc_info.get("demoted") or [])
    if mc_demoted:
        append_log(AUDIT_LOG_FILE, f"MC DEMOTION: removing {mc_demoted} from approved set")
        approved_per_stock = {k: v for k, v in approved_per_stock.items() if k not in mc_demoted}
        candidate_benchmark = _build_candidate_benchmark(approved_per_stock, blocked_symbols, approved_at)
        candidate_ok, candidate_reason = _validate_candidate_benchmark(candidate_benchmark)
        if not candidate_ok:
            append_log(AUDIT_LOG_FILE, f"DEPLOY BLOCKED post-MC-demotion: {candidate_reason}")
            return f"Deployment blocked by strategy approval: {candidate_reason}"
        proposal["mc_demoted_symbols"] = mc_demoted

    try:
        from ruflo_ranker import check_portfolio_diversity
        div_stat = check_portfolio_diversity(list(approved_per_stock.keys()))
        append_log(AUDIT_LOG_FILE, f"RUFLO DIVERSITY CHECK: {div_stat}")
    except (ImportError, RuntimeError, ValueError) as e:
        logger.warning(f"approve_deployment: Diversity check failed: {type(e).__name__}: {e}")

    global_params = new_params.get("global", {}) or {}

    # v5.0 ROLLBACK SUPPORT: commit se pehle purani files ka snapshot stash
    # karo — /deployrollback isi se wapas layega.
    prev_snapshot = {}
    for path in _deployment_target_files():
        prev_snapshot[path] = load_json(path, None)
    proposal["prev_files"] = prev_snapshot

    try:
        _commit_deployment_transaction(
            proposal=proposal,
            approved_per_stock=approved_per_stock,
            global_params=global_params,
            candidate_benchmark=candidate_benchmark,
            admin_chat_id=admin_chat_id,
            approved_at=approved_at,
        )
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"DEPLOY COMMIT FAILED AND ROLLED BACK: {e}")
        return f"Deployment failed during commit and was rolled back: {e}"

    append_log(AUDIT_LOG_FILE, f"DEPLOYMENT APPROVED by admin {admin_chat_id}; active={len(approved_per_stock)} blocked={len(blocked_symbols)}")

    from signal_broadcaster import alert_admin_sync
    alert_admin_sync(
        "Strategy DEPLOYED\n\n"
        "New optimized parameters are now active.\n"
        f"Active stocks: {len(approved_per_stock)} | Blocked: {len(blocked_symbols)}\n"
        f"Approved at: {now_ist().strftime('%d-%b-%Y %H:%M')}\n\n"
        "Monitor with /strategyvalidator\n"
        "Source: Optimization + Walk-Forward + RuFlo"
    )
    return "Deployed successfully."


async def reject_deployment(admin_chat_id: int, reason: str = ""):
    """Admin rejects — keep current params."""
    proposal = load_json(PENDING_DEPLOYMENT_FILE, {})
    if not proposal or proposal.get("status") != "PENDING":
        return "No pending deployment."

    proposal["status"]      = "REJECTED"
    proposal["approved_by"] = admin_chat_id
    proposal["approved_at"] = now_ist().isoformat()
    proposal["reject_reason"] = reason
    save_json(PENDING_DEPLOYMENT_FILE, proposal)

    append_log(AUDIT_LOG_FILE,
               f"DEPLOYMENT REJECTED by admin {admin_chat_id} reason={reason}")

    from signal_broadcaster import alert_admin_sync
    alert_admin_sync(f"Deployment REJECTED.\nCurrent params unchanged.")
    return "Rejected. Current params unchanged."


def get_pending_proposal() -> dict:
    return load_json(PENDING_DEPLOYMENT_FILE, {})


def _save_deployment_history(proposal: dict):
    """Keep history of all deployments."""
    history_file = "data/deployment_history.json"
    history = load_json(history_file, {"deployments": []})
    history["deployments"].append(proposal)
    save_json(history_file, history)


def get_deployment_status() -> str:
    """Admin: current deployment status."""
    proposal = load_json(PENDING_DEPLOYMENT_FILE, {})
    history  = load_json("data/deployment_history.json", {"deployments": []})

    lines = [f"Deployment Manager\n"]

    if proposal and proposal.get("status") == "PENDING":
        wfv = proposal.get("wfv_results_summary", {})
        lines.append(
            f"PENDING APPROVAL\n"
            f"Proposed: {proposal.get('proposed_at', 'N/A')[:16]}\n"
            f"Walk-Forward: {wfv.get('valid')}/{wfv.get('total')} valid\n\n"
            f"/deployapprove to deploy\n"
            f"/deployreject to reject"
        )
    else:
        lines.append("No pending deployment.")

    total_deployments = len(history.get("deployments", []))
    lines.append(f"\nTotal deployments: {total_deployments}")

    try:
        from workflow_manager import get_workflow_status_text
        lines.append("\n" + get_workflow_status_text())
    except (ImportError, RuntimeError) as e:
        logger.warning(f"get_deployment_status: Workflow status failed: {type(e).__name__}: {e}")

    return "\n".join(lines)


def propose_deployment_sync(new_params: dict, wfv_results: dict, optimization_metrics: dict):
    """Sync wrapper for propose_deployment — safe to call from background thread."""
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(propose_deployment(new_params, wfv_results, optimization_metrics))
        loop.close()
    except Exception as e:
        from utils import append_log
        from config import AUDIT_LOG_FILE
        append_log(AUDIT_LOG_FILE, f"PROPOSE_SYNC ERROR: {e}")


# ═════════════════════════════════════════════════════════════════════════
# v5.0 — DEPLOYMENT ROLLBACK (command lifecycle revert: /deployrollback)
# ═════════════════════════════════════════════════════════════════════════
def rollback_deployment() -> str:
    """
    Latest APPROVED deployment ko revert karo: approve ke waqt stash kiye
    hue purane files restore hote hain. Workflow stages simulation se reset
    hote hain (dobara /simulate → /deployapprove zaroori). Purana proposal
    status ROLLED_BACK mark hota hai (history me rahta hai — audit).
    """
    history = load_json("data/deployment_history.json", {"deployments": []})
    deps = [d for d in history.get("deployments", [])
            if isinstance(d, dict) and d.get("status") == "APPROVED" and isinstance(d.get("prev_files"), dict)]
    if not deps:
        return "Rollback not possible: no approved deployment with a restore snapshot."

    latest = deps[-1]
    prev_files = latest.get("prev_files", {})
    restored, removed = [], []
    try:
        for path, value in prev_files.items():
            if value is None:
                try:
                    import os
                    if os.path.exists(path):
                        os.remove(path)
                        removed.append(path)
                except OSError as e:
                    append_log(AUDIT_LOG_FILE, f"ROLLBACK REMOVE FAILED {path}: {e}")
            else:
                save_json(path, value)
                restored.append(path)
    except Exception as e:
        append_log(AUDIT_LOG_FILE, f"ROLLBACK RESTORE FAILED: {e}")
        return f"Rollback FAILED: {type(e).__name__}: {e}"

    latest["status"] = "ROLLED_BACK"
    latest["rolled_back_at"] = now_ist().isoformat()
    save_json("data/deployment_history.json", history)
    save_json(PENDING_DEPLOYMENT_FILE, {
        "status": "ROLLED_BACK",
        "rolled_back_at": now_ist().isoformat(),
        "rolled_back_from": latest.get("approved_at"),
    })
    try:
        from workflow_manager import _reset_from, _load_state, _save_state
        state = _load_state()
        _reset_from(state, "simulation")
        _save_state(state)
        append_log(AUDIT_LOG_FILE, "WORKFLOW ROLLED BACK: simulation → approval → paper stages reset")
    except (ImportError, RuntimeError) as e:
        append_log(AUDIT_LOG_FILE, f"ROLLBACK: workflow reset failed: {e}")

    append_log(AUDIT_LOG_FILE,
               f"DEPLOYMENT ROLLED BACK: restored={len(restored)} removed={len(removed)} at {now_ist().isoformat()}")
    return ("✅ Deployment rolled back.\n\n"
            f"Restored files: {len(restored)}\n"
            f"Removed files: {len(removed)}\n\n"
            "Workflow reset: dobara /simulate → review → /deployapprove zaroori.")
