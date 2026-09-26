"""
fundamental_sync_engine.py — PILLAR 3: FUNDAMENTAL + TECHNICAL SYNC & TRADE SELECTION ENGINE (R39 CORRECTED)
============================================================================================================
CORRECTED per R39 audit requirements:

1. FUNDAMENTAL DATA MUST BE REAL — no synthetic in production path
2. PIT SAFETY — AS_OF(T) → latest eligible observation available at T
3. FUNDAMENTAL + TECHNICAL ALIGNMENT — genuine decision system, not two unrelated filters
4. MISSING/STALE → FAIL-CLOSED (NO TRADE) when mandatory
5. FUNDAMENTAL FEATURES — keep approved design, no blind addition
6. TECHNICAL/SEQ PARITY — same methodology backtest/live
7. SCORE ROBUSTNESS — not optimized for max profit, walk-forward validated
8. BACKTEST/LIVE PARITY — same PIT, same gates, same RR/exit
9. LIVE/PAPER PARITY — persist enough info to reconstruct
10. FAILURE SAFETY — critical failures → NO TRADE/HOLD/BLOCK

CORE FLOW:
Business Halal → Non-Muslim Board → Fundamental Quality → Technical/SEQ → Fundamental×Technical confirmation → Sector/Regime/FII-DII/OrderBook → Risk & liquidity → Entry → 1:1.8 RR → 1.8R lock → uncapped trailing

The Fundamental layer and Technical layer must work together as genuine decision system.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, List, Tuple

try:
    from config import DATA_DIR, PARAMS
except ImportError:
    DATA_DIR = "data"
    PARAMS = {}

try:
    from utils import append_log, now_ist, logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    def append_log(path, line):
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "a") as f:
                f.write(f"{line}\n")
        except Exception:
            pass
    def now_ist():
        return datetime.now()

try:
    from fundamental_data import get_latest_fundamental_dna, get_fundamental_asof, REAL_SOURCES
except ImportError:
    REAL_SOURCES = {"screener.in", "nse.in", "bse.in", "nse_archives"}
    def get_latest_fundamental_dna(symbol, as_of=None, fail_closed_if_missing=False):
        return {"symbol": symbol, "available": False, "reason": "fundamental_data module missing", "fail_closed": fail_closed_if_missing}
    def get_fundamental_asof(symbol, as_of, period=None):
        return []

AUDIT_LOG_FILE = os.path.join(DATA_DIR, "audit_log.txt")

def _get_threshold(key, default):
    try:
        return PARAMS.get(key, default)
    except Exception:
        return default

def _is_fundamental_mandatory() -> bool:
    """
    Determines if fundamental confirmation is mandatory.
    If mandatory: missing/stale/corrupt/invalid → NO TRADE (fail-closed)
    If not mandatory: missing → UNKNOWN (fail-open) — but must be explicit, documented
    
    Per spec: If Fundamental confirmation is mandatory for strategy, missing → NO TRADE
    """
    try:
        # Check config — enable_fundamental_filter is master switch
        # fundamental_filter_mandatory is explicit mandatory flag
        mandatory = PARAMS.get("fundamental_filter_mandatory", True)
        enabled = PARAMS.get("enable_fundamental_filter", True)
        # If filter is enabled and mandatory flag is True → mandatory
        # Default to True per R39 correction (fail-closed safe)
        if not enabled:
            return False
        return bool(mandatory)
    except Exception:
        # Fail-closed safe default: if we can't determine, assume mandatory (NO TRADE on missing)
        return True

WEAK_THRESHOLDS = {
    "max_debt_to_equity": _get_threshold("fund_weak_max_debt_to_equity", 1.0),
    "max_promoter_pledging_pct": _get_threshold("fund_weak_max_promoter_pledging_pct", 20.0),
    "min_interest_coverage": _get_threshold("fund_weak_min_interest_coverage", 1.5),
    "min_roce": _get_threshold("fund_weak_min_roce", 5.0),
    "max_piotroski_weak": _get_threshold("fund_weak_max_piotroski", 3),
    "min_roe": 8.0,
    "min_current_ratio": 1.2,
    "max_altman_distress": 1.8,
    "min_beneish_manipulation": -1.78,
    "min_revenue_growth": -10.0,
}

STRONG_THRESHOLDS = {
    "max_debt_to_equity": _get_threshold("fund_strong_max_debt_to_equity", 0.3),
    "max_promoter_pledging_pct": _get_threshold("fund_strong_max_promoter_pledging_pct", 5.0),
    "min_interest_coverage": _get_threshold("fund_strong_min_interest_coverage", 3.0),
    "min_roce": _get_threshold("fund_strong_min_roce", 15.0),
    "min_piotroski_strong": _get_threshold("fund_strong_min_piotroski", 7),
    "min_roe": 18.0,
    "min_current_ratio": 2.0,
    "min_altman_safe": 3.0,
    "min_revenue_growth": 15.0,
}

def evaluate_fundamental_dna(dna: Dict) -> Dict:
    """
    Evaluates fundamental DNA with explicit fail-closed for missing/invalid.
    
    For every trade decision must record:
    - fundamental_status
    - fundamental_score/features
    - technical_status (enriched later)
    - technical_tools_used (enriched later)
    - technical_alignment (enriched later)
    - final_alignment_decision
    - rejection_reason
    
    If fundamental confirmation is mandatory and DNA unavailable → REJECT (NO TRADE), not UNKNOWN/PASS
    """
    try:
        is_mandatory = _is_fundamental_mandatory()
        
        if not dna.get("available"):
            reason = dna.get("reason", "no fundamental data")
            # Check if this is a provenance violation or real missing data
            is_provenance_violation = "provenance violation" in reason.lower() or "synthetic" in reason.lower()
            
            if is_mandatory:
                # FAIL-CLOSED: missing/stale/corrupt/invalid → NO TRADE
                return {
                    "action": "REJECT",
                    "final_alignment_decision": "REJECT",
                    "fundamental_status": "MISSING_FAIL_CLOSED" if not is_provenance_violation else "PROVENANCE_VIOLATION_FAIL_CLOSED",
                    "reason": f"NO TRADE — missing required fundamental data (mandatory): {reason}",
                    "rejection_reason": f"Fundamental mandatory but unavailable: {reason}",
                    "weak_reasons": [],
                    "strong_reasons": [],
                    "score": -10,  # Strong negative to ensure rejection
                    "dna": dna,
                    "is_mandatory": True,
                    "fail_closed": True,
                    "provenance_chain": dna.get("provenance_chain", {}),
                }
            else:
                # Fail-open only if explicitly configured as non-mandatory — must be documented
                return {
                    "action": "UNKNOWN",
                    "final_alignment_decision": "UNKNOWN",
                    "fundamental_status": "MISSING_FAIL_OPEN" if not is_provenance_violation else "PROVENANCE_VIOLATION",
                    "reason": f"no fundamental data (non-mandatory, fail-open): {reason}",
                    "rejection_reason": f"Fundamental unavailable but non-mandatory: {reason}",
                    "weak_reasons": [],
                    "strong_reasons": [],
                    "score": 0,
                    "dna": dna,
                    "is_mandatory": False,
                    "fail_closed": False,
                }

        weak_reasons = list(dna.get("weak_reasons", []))
        strong_reasons = list(dna.get("strong_reasons", []))

        # Extract full category fields
        cfo = dna.get("cfo"); pat = dna.get("pat"); de = dna.get("debt_to_equity")
        pledge = dna.get("promoter_pledging_pct"); ic = dna.get("interest_coverage")
        roce = dna.get("roce"); roe = dna.get("roe"); f_score = dna.get("piotroski_f_score")
        curr = dna.get("current_ratio"); altman = dna.get("altman_z_score"); beneish = dna.get("beneish_m_score")
        rev_g = dna.get("revenue_growth"); npm = dna.get("net_profit_margin")
        debt_assets = dna.get("debt_to_assets"); promoter_hold = dna.get("promoter_holding_pct")
        pe = dna.get("pe_ratio"); free_cfo = dna.get("free_cash_flow")

        # 1. Cash Flow Quality
        if cfo is not None and pat is not None:
            try:
                if cfo < 0 and pat > 0:
                    if not any("CFO" in r for r in weak_reasons):
                        weak_reasons.append("negative CFO with positive PAT (manipulation/bull-trap risk)")
                if free_cfo is not None and free_cfo < 0 and pat > 0:
                    weak_reasons.append(f"negative Free Cash Flow {free_cfo:.1f} with positive PAT")
            except Exception:
                pass

        # 2. Leverage
        if de is not None:
            try:
                if de > WEAK_THRESHOLDS["max_debt_to_equity"]:
                    if not any("D/E" in r for r in weak_reasons):
                        weak_reasons.append(f"D/E {de:.2f} > {WEAK_THRESHOLDS['max_debt_to_equity']} (rising debt)")
            except Exception:
                pass
        if debt_assets is not None:
            try:
                if debt_assets > 0.6:
                    weak_reasons.append(f"high D/Assets {debt_assets:.2f} >0.6")
            except Exception:
                pass

        # 3. Governance
        if pledge is not None:
            try:
                if pledge > WEAK_THRESHOLDS["max_promoter_pledging_pct"]:
                    if not any("pledging" in r for r in weak_reasons):
                        weak_reasons.append(f"pledging {pledge:.1f}% > {WEAK_THRESHOLDS['max_promoter_pledging_pct']}%")
            except Exception:
                pass
        if promoter_hold is not None:
            try:
                if promoter_hold < 20:
                    weak_reasons.append(f"low promoter holding {promoter_hold:.1f}% <20% (governance risk)")
            except Exception:
                pass

        # 4. Profitability
        if ic is not None:
            try:
                if ic < WEAK_THRESHOLDS["min_interest_coverage"]:
                    if not any("interest coverage" in r for r in weak_reasons):
                        weak_reasons.append(f"IC {ic:.2f} < {WEAK_THRESHOLDS['min_interest_coverage']}")
            except Exception:
                pass
        if roce is not None and roe is not None:
            try:
                if roce < 5 and roe < 8:
                    if not any("ROCE" in r for r in weak_reasons):
                        weak_reasons.append(f"low ROCE {roce:.1f}% & ROE {roe:.1f}%")
            except Exception:
                pass
        if npm is not None:
            try:
                if npm < 2:
                    weak_reasons.append(f"low net margin {npm:.1f}% <2%")
            except Exception:
                pass

        # 5. Quality Scores
        if altman is not None:
            try:
                if altman < WEAK_THRESHOLDS["max_altman_distress"]:
                    weak_reasons.append(f"Altman Z {altman:.2f} <{WEAK_THRESHOLDS['max_altman_distress']} distress")
            except Exception:
                pass
        if beneish is not None:
            try:
                if beneish > WEAK_THRESHOLDS["min_beneish_manipulation"]:
                    weak_reasons.append(f"Beneish M {beneish:.2f} > {WEAK_THRESHOLDS['min_beneish_manipulation']} manipulation risk")
            except Exception:
                pass

        # 6. Liquidity
        if curr is not None:
            try:
                if curr < WEAK_THRESHOLDS["min_current_ratio"]:
                    if not any("current ratio" in r for r in weak_reasons):
                        weak_reasons.append(f"low current ratio {curr:.2f} <{WEAK_THRESHOLDS['min_current_ratio']}")
            except Exception:
                pass

        # 7. Growth
        if rev_g is not None:
            try:
                if rev_g < WEAK_THRESHOLDS["min_revenue_growth"]:
                    weak_reasons.append(f"negative revenue growth {rev_g:.1f}% <{WEAK_THRESHOLDS['min_revenue_growth']}%")
            except Exception:
                pass

        # Strong reasons additional
        if curr is not None and curr > STRONG_THRESHOLDS["min_current_ratio"]:
            if not any("current ratio" in r for r in strong_reasons):
                strong_reasons.append(f"strong current ratio {curr:.2f} >{STRONG_THRESHOLDS['min_current_ratio']}")
        if altman is not None and altman > STRONG_THRESHOLDS["min_altman_safe"]:
            if not any("Altman" in r for r in strong_reasons):
                strong_reasons.append(f"Altman Z {altman:.2f} >{STRONG_THRESHOLDS['min_altman_safe']} safe")
        if rev_g is not None and rev_g > STRONG_THRESHOLDS["min_revenue_growth"]:
            if not any("revenue growth" in r for r in strong_reasons):
                strong_reasons.append(f"high revenue growth {rev_g:.1f}% >{STRONG_THRESHOLDS['min_revenue_growth']}%")
        if pe is not None:
            try:
                if 10 <= pe <= 25:
                    strong_reasons.append(f"reasonable PE {pe:.1f} (10-25)")
            except Exception:
                pass

        score = len(strong_reasons) - len(weak_reasons)

        # Determine action with explicit final_alignment_decision
        if len(weak_reasons) >= 2:
            return {
                "action": "REJECT",
                "final_alignment_decision": "REJECT",
                "fundamental_status": "WEAK_REJECT",
                "reason": f"Weak fundamentals: {'; '.join(weak_reasons[:3])}",
                "rejection_reason": f"Weak fundamentals: {'; '.join(weak_reasons[:3])}",
                "weak_reasons": weak_reasons,
                "strong_reasons": strong_reasons,
                "score": score,
                "dna": dna,
                "is_mandatory": is_mandatory,
                "fail_closed": False,
                "provenance_chain": dna.get("provenance_chain", {}),
            }
        elif len(weak_reasons) == 1 and any(kw in weak_reasons[0].lower() for kw in ("negative cfo", "pledging", "manipulation", "beneish", "altman")):
            return {
                "action": "REJECT",
                "final_alignment_decision": "REJECT",
                "fundamental_status": "CRITICAL_WEAK_REJECT",
                "reason": f"Critical weak: {weak_reasons[0]}",
                "rejection_reason": f"Critical weak: {weak_reasons[0]}",
                "weak_reasons": weak_reasons,
                "strong_reasons": strong_reasons,
                "score": score,
                "dna": dna,
                "is_mandatory": is_mandatory,
                "fail_closed": False,
                "provenance_chain": dna.get("provenance_chain", {}),
            }
        elif dna.get("is_strong") or len(strong_reasons) >= 3:
            return {
                "action": "PRIORITIZE",
                "final_alignment_decision": "PRIORITIZE",
                "fundamental_status": "STRONG_PRIORITIZE",
                "reason": f"Strong fundamentals: {'; '.join(strong_reasons[:3])}",
                "rejection_reason": "",
                "weak_reasons": weak_reasons,
                "strong_reasons": strong_reasons,
                "score": score,
                "dna": dna,
                "is_mandatory": is_mandatory,
                "fail_closed": False,
                "provenance_chain": dna.get("provenance_chain", {}),
            }
        else:
            return {
                "action": "NEUTRAL",
                "final_alignment_decision": "NEUTRAL",
                "fundamental_status": "NEUTRAL",
                "reason": f"Neutral: {len(strong_reasons)} strong, {len(weak_reasons)} weak",
                "rejection_reason": "",
                "weak_reasons": weak_reasons,
                "strong_reasons": strong_reasons,
                "score": score,
                "dna": dna,
                "is_mandatory": is_mandatory,
                "fail_closed": False,
                "provenance_chain": dna.get("provenance_chain", {}),
            }
    except Exception as e:
        is_mandatory = _is_fundamental_mandatory()
        # On evaluation error, fail-closed if mandatory
        if is_mandatory:
            return {
                "action": "REJECT",
                "final_alignment_decision": "REJECT",
                "fundamental_status": "EVALUATION_ERROR_FAIL_CLOSED",
                "reason": f"evaluation error (fail-closed): {type(e).__name__}: {e}",
                "rejection_reason": f"Fundamental evaluation error (mandatory, fail-closed): {e}",
                "weak_reasons": [],
                "strong_reasons": [],
                "score": -10,
                "dna": dna,
                "is_mandatory": True,
                "fail_closed": True,
            }
        else:
            return {
                "action": "UNKNOWN",
                "final_alignment_decision": "UNKNOWN",
                "fundamental_status": "EVALUATION_ERROR",
                "reason": f"evaluation error: {type(e).__name__}: {e}",
                "rejection_reason": f"Evaluation error: {e}",
                "weak_reasons": [],
                "strong_reasons": [],
                "score": 0,
                "dna": dna,
                "is_mandatory": False,
                "fail_closed": False,
            }

def should_reject_due_to_weak_fundamentals(symbol: str, as_of=None) -> Tuple[bool, Dict]:
    """
    Checks if symbol should be rejected due to weak fundamentals.
    Uses PIT as_of for backtest/live parity.
    FAIL-CLOSED if mandatory and data missing.
    """
    try:
        is_mandatory = _is_fundamental_mandatory()
        dna = get_latest_fundamental_dna(symbol, as_of=as_of, fail_closed_if_missing=is_mandatory)
        eval_res = evaluate_fundamental_dna(dna)
        if eval_res["action"] == "REJECT":
            return True, eval_res
        return False, eval_res
    except Exception as e:
        is_mandatory = _is_fundamental_mandatory()
        if is_mandatory:
            # Fail-closed on error if mandatory
            return True, {
                "action": "REJECT",
                "final_alignment_decision": "REJECT",
                "fundamental_status": "CHECK_ERROR_FAIL_CLOSED",
                "reason": f"should_reject error (fail-closed): {e}",
                "rejection_reason": f"Fundamental check error (mandatory): {e}",
                "weak_reasons": [],
                "strong_reasons": [],
                "score": -10,
                "dna": {"symbol": symbol, "available": False, "fail_closed": True},
                "fail_closed": True,
            }
        else:
            return False, {
                "action": "UNKNOWN",
                "final_alignment_decision": "UNKNOWN",
                "fundamental_status": "CHECK_ERROR",
                "reason": f"should_reject error: {e}",
                "rejection_reason": f"Check error: {e}",
                "weak_reasons": [],
                "strong_reasons": [],
                "score": 0,
                "dna": {"symbol": symbol, "available": False},
                "fail_closed": False,
            }

def should_prioritize_due_to_strong_fundamentals(symbol: str, as_of=None) -> Tuple[bool, Dict]:
    try:
        dna = get_latest_fundamental_dna(symbol, as_of=as_of, fail_closed_if_missing=False)
        eval_res = evaluate_fundamental_dna(dna)
        if eval_res["action"] == "PRIORITIZE":
            return True, eval_res
        return False, eval_res
    except Exception as e:
        return False, {
            "action": "UNKNOWN",
            "final_alignment_decision": "UNKNOWN",
            "fundamental_status": "CHECK_ERROR",
            "reason": f"error: {e}",
            "rejection_reason": f"Check error: {e}",
            "weak_reasons": [],
            "strong_reasons": [],
            "score": 0,
            "dna": {},
            "fail_closed": False,
        }

def get_fundamental_priority_score(symbol: str, as_of=None) -> int:
    try:
        dna = get_latest_fundamental_dna(symbol, as_of=as_of, fail_closed_if_missing=False)
        eval_res = evaluate_fundamental_dna(dna)
        return int(eval_res.get("score", 0))
    except Exception:
        return -10 if _is_fundamental_mandatory() else 0

def enrich_with_fundamental_dna(symbol: str, technical_context: Dict, as_of=None) -> Dict:
    """
    Enriches technical context with fundamental DNA for genuine Fundamental+Technical alignment.
    
    Records:
    - fundamental_status
    - fundamental_score/features
    - technical_status
    - technical_tools_used
    - technical_alignment
    - final_alignment_decision
    - rejection_reason
    
    Candidate traceable from raw Fundamental data through Technical confirmation to final decision.
    """
    try:
        is_mandatory = _is_fundamental_mandatory()
        dna = get_latest_fundamental_dna(symbol, as_of=as_of, fail_closed_if_missing=is_mandatory)
        eval_res = evaluate_fundamental_dna(dna)
        
        # Extract technical info from context
        technical_status = technical_context.get("technical_status", technical_context.get("status", "UNKNOWN"))
        technical_tools_used = technical_context.get("technical_tools_used", technical_context.get("tools_used", []))
        technical_alignment = technical_context.get("technical_alignment", technical_context.get("alignment", "UNKNOWN"))
        
        # Determine final alignment decision — Fundamental × Technical confirmation
        final_decision = "UNKNOWN"
        rejection_reason = ""
        
        if eval_res["action"] == "REJECT":
            final_decision = "REJECT"
            rejection_reason = eval_res.get("rejection_reason", eval_res.get("reason", ""))
        elif eval_res["action"] == "PRIORITIZE" and technical_status in ("STRONG", "ALIGNED", "BULLISH", "BUY"):
            final_decision = "PRIORITIZE"
        elif eval_res["action"] == "NEUTRAL" and technical_status in ("STRONG", "ALIGNED"):
            final_decision = "NEUTRAL_TRADEABLE"
        elif not dna.get("available") and is_mandatory:
            final_decision = "REJECT"
            rejection_reason = f"Missing mandatory fundamental data: {dna.get('reason','')}"
        else:
            final_decision = eval_res.get("final_alignment_decision", "NEUTRAL")
            rejection_reason = eval_res.get("rejection_reason", "")
        
        return {
            "symbol": symbol,
            "technical": technical_context,
            "technical_status": technical_status,
            "technical_tools_used": technical_tools_used,
            "technical_alignment": technical_alignment,
            "fundamental_dna": dna,
            "fundamental_evaluation": eval_res,
            "fundamental_status": eval_res.get("fundamental_status", "UNKNOWN"),
            "fundamental_score": eval_res.get("score", 0),
            "fundamental_features": {
                "cfo": dna.get("cfo"),
                "pat": dna.get("pat"),
                "debt_to_equity": dna.get("debt_to_equity"),
                "promoter_pledging_pct": dna.get("promoter_pledging_pct"),
                "interest_coverage": dna.get("interest_coverage"),
                "roce": dna.get("roce"),
                "roe": dna.get("roe"),
                "piotroski_f_score": dna.get("piotroski_f_score"),
                "altman_z_score": dna.get("altman_z_score"),
                "beneish_m_score": dna.get("beneish_m_score"),
                "current_ratio": dna.get("current_ratio"),
                "revenue_growth": dna.get("revenue_growth"),
            },
            "sync_status": eval_res["action"],
            "final_alignment_decision": final_decision,
            "rejection_reason": rejection_reason,
            "is_mandatory": is_mandatory,
            "fail_closed": eval_res.get("fail_closed", False),
            "provenance_chain": dna.get("provenance_chain", {}),
            "timestamp": now_ist().isoformat(),
            "as_of": str(as_of) if as_of else None,
        }
    except Exception as e:
        is_mandatory = _is_fundamental_mandatory()
        return {
            "symbol": symbol,
            "technical": technical_context,
            "technical_status": "ERROR",
            "technical_tools_used": [],
            "technical_alignment": "ERROR",
            "fundamental_dna": {"available": False, "reason": str(e), "fail_closed": is_mandatory},
            "fundamental_evaluation": {"action": "REJECT" if is_mandatory else "UNKNOWN", "reason": str(e), "fail_closed": is_mandatory},
            "fundamental_status": "ENRICH_ERROR_FAIL_CLOSED" if is_mandatory else "ENRICH_ERROR",
            "fundamental_score": -10 if is_mandatory else 0,
            "fundamental_features": {},
            "sync_status": "REJECT" if is_mandatory else "UNKNOWN",
            "final_alignment_decision": "REJECT" if is_mandatory else "UNKNOWN",
            "rejection_reason": f"Enrich error (fail-closed={is_mandatory}): {e}",
            "is_mandatory": is_mandatory,
            "fail_closed": is_mandatory,
            "timestamp": now_ist().isoformat(),
            "as_of": str(as_of) if as_of else None,
        }

def filter_candidates_by_fundamentals(candidates: List[Dict], as_of=None) -> Tuple[List[Dict], List[Dict]]:
    """
    Filters candidates by fundamentals with PIT as_of.
    FAIL-CLOSED if mandatory: missing data → REJECT (NO TRADE)
    FAIL-OPEN only if explicitly non-mandatory (documented, audited).
    
    Backtest and live must use same logic.
    """
    accepted = []
    rejected = []
    is_mandatory = _is_fundamental_mandatory()
    
    for cand in candidates:
        try:
            sym = cand.get("symbol") or cand.get("SYMBOL") or ""
            if not sym:
                # No symbol → cannot check fundamentals → fail-closed if mandatory
                if is_mandatory:
                    cand["fundamental_dna"] = {"available": False, "reason": "no symbol provided", "fail_closed": True}
                    cand["fundamental_evaluation"] = {
                        "action": "REJECT",
                        "final_alignment_decision": "REJECT",
                        "fundamental_status": "NO_SYMBOL_FAIL_CLOSED",
                        "reason": "No symbol provided for fundamental check (mandatory)",
                        "rejection_reason": "No symbol — cannot verify fundamentals (mandatory)",
                        "fail_closed": True,
                    }
                    cand["fundamental_score"] = -10
                    cand["sync_status"] = "REJECT"
                    cand["final_alignment_decision"] = "REJECT"
                    cand["rejection_reason"] = "No symbol — fundamental check mandatory"
                    rejected.append(cand)
                else:
                    accepted.append(cand)
                continue
            
            should_reject, eval_res = should_reject_due_to_weak_fundamentals(sym, as_of=as_of)
            
            # Enrich candidate with full alignment info for traceability
            cand["fundamental_dna"] = eval_res.get("dna", {})
            cand["fundamental_evaluation"] = eval_res
            cand["fundamental_score"] = eval_res.get("score", 0)
            cand["fundamental_status"] = eval_res.get("fundamental_status", "UNKNOWN")
            cand["fundamental_features"] = eval_res.get("dna", {})
            cand["sync_status"] = eval_res.get("action", "UNKNOWN")
            cand["final_alignment_decision"] = eval_res.get("final_alignment_decision", "UNKNOWN")
            cand["rejection_reason"] = eval_res.get("rejection_reason", eval_res.get("reason", ""))
            cand["is_mandatory"] = is_mandatory
            cand["fail_closed"] = eval_res.get("fail_closed", False)
            cand["provenance_chain"] = eval_res.get("provenance_chain", eval_res.get("dna", {}).get("provenance_chain", {}))
            cand["as_of"] = str(as_of) if as_of else None
            
            if should_reject:
                rejected.append(cand)
                try:
                    append_log(AUDIT_LOG_FILE, f"FUNDAMENTAL REJECT: {sym} as_of={as_of} — {eval_res.get('reason')} | Score: {eval_res.get('score')} | Mandatory: {is_mandatory} | Fail-closed: {eval_res.get('fail_closed')}")
                except Exception:
                    pass
            else:
                accepted.append(cand)
        except Exception as e:
            # On filter error, fail-closed if mandatory
            try:
                append_log(AUDIT_LOG_FILE, f"FUNDAMENTAL FILTER ERROR: {cand.get('symbol')} as_of={as_of}: {e} — mandatory={is_mandatory} — {'REJECT (fail-closed)' if is_mandatory else 'ACCEPT (fail-open)'}")
            except Exception:
                pass
            
            if is_mandatory:
                cand["fundamental_dna"] = {"available": False, "reason": f"filter error: {e}", "fail_closed": True}
                cand["fundamental_evaluation"] = {
                    "action": "REJECT",
                    "final_alignment_decision": "REJECT",
                    "fundamental_status": "FILTER_ERROR_FAIL_CLOSED",
                    "reason": f"Filter error (fail-closed): {e}",
                    "rejection_reason": f"Fundamental filter error (mandatory): {e}",
                    "fail_closed": True,
                }
                cand["fundamental_score"] = -10
                cand["sync_status"] = "REJECT"
                cand["final_alignment_decision"] = "REJECT"
                cand["rejection_reason"] = f"Filter error (fail-closed): {e}"
                rejected.append(cand)
            else:
                accepted.append(cand)
    
    try:
        accepted.sort(key=lambda x: (x.get("fundamental_score", 0), x.get("signal_score", 0) or x.get("score", 0) or 0), reverse=True)
    except Exception:
        pass
    return accepted, rejected

def rank_by_fundamental_sync(candidates: List[Dict], as_of=None) -> List[Dict]:
    """
    Ranks by fundamental+technical sync with PIT as_of.
    Same logic backtest/live.
    """
    try:
        for cand in candidates:
            sym = cand.get("symbol", "")
            try:
                score = get_fundamental_priority_score(sym, as_of=as_of)
                cand["fundamental_score"] = score
                tech_score = cand.get("signal_score", 0) or cand.get("score", 0) or 0
                cand["combined_score"] = float(tech_score) + float(score) * 0.5
                cand["as_of"] = str(as_of) if as_of else cand.get("as_of")
            except Exception:
                cand["fundamental_score"] = -10 if _is_fundamental_mandatory() else 0
                cand["combined_score"] = cand.get("signal_score", 0) or 0
        candidates.sort(key=lambda x: x.get("combined_score", 0), reverse=True)
        return candidates
    except Exception:
        return candidates

LEARNING_DB = os.path.join(DATA_DIR, "fundamental_sync_learning.json")

def _load_learning_db() -> Dict:
    try:
        if os.path.exists(LEARNING_DB):
            with open(LEARNING_DB, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"patterns": [], "stats": {"total_trades": 0, "profit_sync": 0, "loss_weak": 0}}

def _save_learning_db(data: Dict):
    try:
        os.makedirs(os.path.dirname(LEARNING_DB) or ".", exist_ok=True)
        with open(LEARNING_DB, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def record_trade_outcome(symbol: str, technical_signal: Dict, fundamental_dna: Dict, pnl: float, as_of=None):
    """
    Records trade outcome for learning with full provenance.
    """
    try:
        db = _load_learning_db()
        eval_res = evaluate_fundamental_dna(fundamental_dna) if fundamental_dna.get("available") else {"action": "UNKNOWN", "final_alignment_decision": "UNKNOWN"}
        entry = {
            "symbol": symbol,
            "timestamp": now_ist().isoformat(),
            "as_of": str(as_of) if as_of else None,
            "technical": technical_signal,
            "technical_status": technical_signal.get("technical_status", technical_signal.get("status", "UNKNOWN")),
            "technical_tools_used": technical_signal.get("technical_tools_used", technical_signal.get("tools_used", [])),
            "fundamental_dna": fundamental_dna,
            "fundamental_status": eval_res.get("fundamental_status", "UNKNOWN"),
            "fundamental_score": eval_res.get("score", 0),
            "fundamental_features": {
                "cfo": fundamental_dna.get("cfo"),
                "pat": fundamental_dna.get("pat"),
                "debt_to_equity": fundamental_dna.get("debt_to_equity"),
                "promoter_pledging_pct": fundamental_dna.get("promoter_pledging_pct"),
                "roce": fundamental_dna.get("roce"),
                "piotroski_f_score": fundamental_dna.get("piotroski_f_score"),
            },
            "evaluation": eval_res,
            "final_alignment_decision": eval_res.get("final_alignment_decision", "UNKNOWN"),
            "pnl": pnl,
            "is_profit": pnl > 0,
            "sync_status": eval_res.get("action"),
            "provenance_chain": fundamental_dna.get("provenance_chain", {}),
        }
        db["patterns"].append(entry)
        if len(db["patterns"]) > 1000:
            db["patterns"] = db["patterns"][-1000:]
        db["stats"]["total_trades"] = db["stats"].get("total_trades", 0) + 1
        if pnl > 0 and eval_res.get("action") == "PRIORITIZE":
            db["stats"]["profit_sync"] = db["stats"].get("profit_sync", 0) + 1
        if pnl < 0 and eval_res.get("action") == "REJECT":
            db["stats"]["loss_weak"] = db["stats"].get("loss_weak", 0) + 1
        _save_learning_db(db)
        try:
            append_log(AUDIT_LOG_FILE, f"FUND SYNC LEARN: {symbol} as_of={as_of} PnL={pnl:.2f} Sync={eval_res.get('action')} FinalDecision={eval_res.get('final_alignment_decision')} FundScore={eval_res.get('score')} Tech={technical_signal.get('reason','')}")
        except Exception:
            pass
    except Exception as e:
        try:
            append_log(AUDIT_LOG_FILE, f"FUND SYNC LEARN ERROR: {symbol}: {e}")
        except Exception:
            pass

def get_learning_stats() -> Dict:
    try:
        db = _load_learning_db()
        stats = db.get("stats", {})
        patterns = db.get("patterns", [])
        profit_by_sync = {}
        for p in patterns:
            sync = p.get("sync_status", "UNKNOWN")
            if sync not in profit_by_sync:
                profit_by_sync[sync] = {"total": 0, "profit": 0, "loss": 0, "avg_pnl": 0, "pnl_sum": 0}
            profit_by_sync[sync]["total"] += 1
            profit_by_sync[sync]["pnl_sum"] += p.get("pnl", 0)
            if p.get("is_profit"):
                profit_by_sync[sync]["profit"] += 1
            else:
                profit_by_sync[sync]["loss"] += 1
        for sync in profit_by_sync:
            d = profit_by_sync[sync]
            d["win_rate"] = (d["profit"] / d["total"] * 100) if d["total"] else 0
            d["avg_pnl"] = (d["pnl_sum"] / d["total"]) if d["total"] else 0
        return {"stats": stats, "profit_by_sync": profit_by_sync, "total_patterns": len(patterns), "recent": patterns[-10:]}
    except Exception as e:
        return {"error": str(e)}

def _cli():
    import argparse
    parser = argparse.ArgumentParser(description="QASWA Fundamental+Technical Sync Engine (R39 CORRECTED — REAL ONLY, FAIL-CLOSED)")
    parser.add_argument("--symbol", help="Check symbol")
    parser.add_argument("--as-of", help="PIT as-of date YYYY-MM-DD (required for PIT safety)")
    parser.add_argument("--stats", action="store_true", help="Show learning stats")
    parser.add_argument("--test-filter", nargs="+", help="Test filter on symbols")
    parser.add_argument("--check-mandatory", action="store_true", help="Check if fundamental filter is mandatory (fail-closed)")
    args = parser.parse_args()
    
    if args.check_mandatory:
        print(f"Fundamental filter mandatory (fail-closed): {_is_fundamental_mandatory()}")
        print(f"Enabled: {PARAMS.get('enable_fundamental_filter', True)}")
        print(f"Mandatory flag: {PARAMS.get('fundamental_filter_mandatory', True)}")
    
    if args.symbol:
        if not args.as_of:
            print("WARNING: --as-of not provided — using current date for PIT safety (live mode)")
            try:
                from utils import now_ist
                as_of = now_ist().date().isoformat()
            except Exception:
                as_of = None
        else:
            as_of = args.as_of
        
        dna = get_latest_fundamental_dna(args.symbol, as_of=as_of, fail_closed_if_missing=_is_fundamental_mandatory())
        eval_res = evaluate_fundamental_dna(dna)
        print(json.dumps({"dna": dna, "evaluation": eval_res}, indent=2, ensure_ascii=False))
        reject, _ = should_reject_due_to_weak_fundamentals(args.symbol, as_of=as_of)
        print(f"Should REJECT: {reject} (mandatory={_is_fundamental_mandatory()})")
        prio, _ = should_prioritize_due_to_strong_fundamentals(args.symbol, as_of=as_of)
        print(f"Should PRIORITIZE: {prio}")
        print(f"Final alignment decision: {eval_res.get('final_alignment_decision')}")
        print(f"Fundamental status: {eval_res.get('fundamental_status')}")
    
    if args.test_filter:
        if not args.as_of:
            print("WARNING: --as-of not provided for filter test — using current date")
            try:
                from utils import now_ist
                as_of = now_ist().date().isoformat()
            except Exception:
                as_of = None
        else:
            as_of = args.as_of
        
        cands = [{"symbol": s, "reason": "technical breakout", "signal_score": 0.8, "technical_status": "STRONG", "technical_tools_used": ["RSI", "EMA"], "technical_alignment": "ALIGNED"} for s in args.test_filter]
        accepted, rejected = filter_candidates_by_fundamentals(cands, as_of=as_of)
        print(f"Accepted: {[c['symbol'] for c in accepted]}")
        print(f"Rejected: {[c['symbol'] for c in rejected]}")
        for c in rejected:
            print(f"  REJECT {c['symbol']}: {c.get('rejection_reason', c['fundamental_evaluation']['reason'])} | Final: {c.get('final_alignment_decision')}")
        for c in accepted:
            print(f"  ACCEPT {c['symbol']}: {c.get('final_alignment_decision')} | FundStatus: {c.get('fundamental_status')} | Score: {c.get('fundamental_score')}")
    
    if args.stats:
        print(json.dumps(get_learning_stats(), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    _cli()
