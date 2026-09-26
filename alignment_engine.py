"""Cross-environment strategy alignment monitor.

Goal: keep Backtest -> Paper -> Live behavior/results close without turning
alignment into a blanket AND gate. Compliance/safety gates remain mandatory;
this module measures model/execution drift and reports insufficient evidence
until enough observations exist.
"""
from __future__ import annotations
import math
from typing import Iterable
from utils import load_json, save_json, now_ist
from config import BACKTEST_RESULTS_FILE, TRADES_FILE, PARAMS

ALIGNMENT_FILE = "data/alignment_report.json"


def _f(v, default=None):
    try:
        x=float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _metrics_from_returns(returns: Iterable[float]) -> dict:
    vals=[_f(x) for x in returns]
    vals=[x for x in vals if x is not None]
    if not vals:
        return {"trades":0,"win_rate_pct":None,"profit_factor":None,"avg_return_pct":None}
    wins=[x for x in vals if x>0]
    losses=[x for x in vals if x<=0]
    gp=sum(wins); gl=abs(sum(losses))
    return {
        "trades":len(vals),
        "win_rate_pct":round(len(wins)/len(vals)*100,2),
        "profit_factor":round(gp/gl,2) if gl>0 else (99.0 if gp>0 else 0.0),
        "avg_return_pct":round(sum(vals)/len(vals),4),
    }


def _backtest_metrics():
    data=load_json(BACKTEST_RESULTS_FILE,{})
    summary=data.get("summary",{}) if isinstance(data,dict) else {}
    if summary:
        return {
            "trades":int(summary.get("total_trades",0) or 0),
            "win_rate_pct":_f(summary.get("win_rate_pct")),
            "profit_factor":_f(summary.get("profit_factor")),
            "avg_return_pct":_f(summary.get("avg_return_pct", summary.get("avg_return"))),
        }
    stocks=data.get("stocks",{}) if isinstance(data,dict) else {}
    vals=[]
    for r in stocks.values() if isinstance(stocks,dict) else []:
        if not isinstance(r,dict): continue
        for t in r.get("trades",[]) or []:
            if isinstance(t,dict): vals.append(t.get("net_return_pct",t.get("return_pct")))
    return _metrics_from_returns(vals)


def _runtime_metrics(environment: str):
    data=load_json(TRADES_FILE,{"trades":[]})
    trades=[]
    for t in data.get("trades",[]) if isinstance(data,dict) else []:
        if not isinstance(t,dict) or t.get("status")!="CLOSED": continue
        env=t.get("execution_environment")
        if env==environment:
            v=t.get("pnl_pct")
            if v is not None: trades.append(v)
    return _metrics_from_returns(trades)


def compare(reference: dict, observed: dict) -> dict:
    if not reference.get("trades") or not observed.get("trades"):
        return {"status":"INSUFFICIENT_DATA","sample_reference":reference.get("trades",0),"sample_observed":observed.get("trades",0)}
    wr_gap=abs(reference["win_rate_pct"]-observed["win_rate_pct"])
    pf_gap=None
    if reference.get("profit_factor") and observed.get("profit_factor") is not None:
        pf_gap=abs(reference["profit_factor"]-observed["profit_factor"])
    return {
        "status":"MEASURED",
        "sample_reference":reference["trades"],
        "sample_observed":observed["trades"],
        "win_rate_gap_pct_points":round(wr_gap,2),
        "profit_factor_gap":round(pf_gap,2) if pf_gap is not None else None,
        "avg_return_gap_pct":round(abs(reference.get("avg_return_pct",0)-observed.get("avg_return_pct",0)),4) if reference.get("avg_return_pct") is not None and observed.get("avg_return_pct") is not None else None,
        "wr_within_configured_gap":wr_gap <= float(PARAMS.get("max_wr_gap_vs_backtest",15)),
    }


def run_alignment_report() -> dict:
    bt=_backtest_metrics(); paper=_runtime_metrics("PAPER"); live=_runtime_metrics("LIVE")
    report={"generated_at":now_ist().isoformat(),"backtest":bt,"paper":paper,"live":live,
            "backtest_vs_paper":compare(bt,paper),"backtest_vs_live":compare(bt,live),
            "paper_vs_live":compare(paper,live),
            "policy":"Alignment is a robustness/monitoring objective, not a blanket hard AND gate. Safety/compliance gates remain mandatory."}
    save_json(ALIGNMENT_FILE,report)
    return report
