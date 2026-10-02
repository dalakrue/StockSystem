"""Research-grade SHADOW governance utilities.

Pure, bounded and causal helpers. They never alter canonical Field 1 values or the
production BUY/SELL/WAIT decision. All timestamps must be supplied by the saved
canonical snapshot or forecast-origin records.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import erf, exp, log, pi, sqrt
from typing import Any, Iterable, Mapping, Sequence
import numpy as np

VERSION = "shadow-intelligence-governance-20260624-v1"
HORIZONS = (1, 3, 6)
STATES = ("STABLE", "WATCH", "DRIFTED", "INSUFFICIENT_EVIDENCE")
MODEL_STATUSES = ("SUPERIOR", "NOT_SIGNIFICANT", "INFERIOR", "INSUFFICIENT_SAMPLE", "DRIFT_BLOCKED", "COVERAGE_FAILED", "OVERFIT_RISK")


def _finite(values: Iterable[Any]) -> np.ndarray:
    x = np.asarray(list(values), dtype=float)
    return x[np.isfinite(x)]


def gaussian_crps(observation: float, mean: float, std: float) -> float:
    """Analytical Gaussian CRPS (Gneiting & Raftery)."""
    s = max(float(std), 1e-12); z = (float(observation) - float(mean)) / s
    phi = exp(-0.5 * z * z) / sqrt(2.0 * pi)
    Phi = 0.5 * (1.0 + erf(z / sqrt(2.0)))
    return float(s * (z * (2.0 * Phi - 1.0) + 2.0 * phi - 1.0 / sqrt(pi)))


def sample_crps(observation: float, samples: Sequence[float]) -> float:
    x = _finite(samples)
    if x.size == 0: return float("nan")
    return float(np.mean(np.abs(x - observation)) - 0.5 * np.mean(np.abs(x[:, None] - x[None, :])))


def quantile_crps(observation: float, quantiles: Sequence[float], levels: Sequence[float]) -> float:
    q, p = _finite(quantiles), _finite(levels)
    n = min(q.size, p.size)
    if n == 0: return float("nan")
    q, p = q[:n], p[:n]; order = np.argsort(p); q, p = q[order], p[order]
    loss = (float(observation) - q) * (p - (float(observation) < q).astype(float))
    return float(2.0 * np.trapezoid(loss, p)) if n > 1 else float(2.0 * loss[0])


def settlement_state(actuals: Mapping[str, Any]) -> str:
    matured = [actuals.get(f"actual_h{h}") is not None for h in HORIZONS]
    if all(matured): return "FULLY_SETTLED"
    if any(matured): return "PARTIALLY_SETTLED"
    return "UNSETTLED"


def settle_origin(origin: Mapping[str, Any], actual_by_horizon: Mapping[int, Mapping[str, Any]], *, asof: Any) -> dict[str, Any]:
    """Settle horizons independently and reject actuals whose availability exceeds as-of."""
    asof_s = str(asof); out: dict[str, Any] = {}
    for h in HORIZONS:
        row = actual_by_horizon.get(h) or {}
        available = str(row.get("available_time") or "")
        valid = bool(available and available <= asof_s and row.get("actual") is not None)
        out[f"actual_h{h}"] = float(row["actual"]) if valid else None
        out[f"h{h}_status"] = "SETTLED" if valid else "PENDING"
    out["settlement_status"] = settlement_state(out)
    out["forecast_origin"] = origin.get("forecast_origin") or origin.get("origin_time")
    out["asof"] = asof_s
    return out


def conformal_interval(lower: float, upper: float, prior_scores: Sequence[float], alpha: float = 0.1) -> dict[str, Any]:
    scores = _finite(prior_scores); alpha = min(max(float(alpha), 1e-6), 0.999)
    if scores.size < 8:
        return {"lower": float(lower), "upper": float(upper), "adjustment": 0.0, "sample_count": int(scores.size), "fallback_reason": "INSUFFICIENT_LOCAL_OR_GLOBAL_MATURED_RESIDUALS"}
    rank = int(np.ceil((scores.size + 1) * (1.0 - alpha))) - 1
    adj = float(np.sort(scores)[min(max(rank, 0), scores.size - 1)])
    return {"lower": float(lower) - adj, "upper": float(upper) + adj, "adjustment": adj, "sample_count": int(scores.size), "fallback_reason": None}


def transition_evidence(labels: Sequence[str], current: str) -> dict[str, Any]:
    labs = [str(x) for x in labels if x is not None]
    states = sorted(set(labs) | {str(current)})
    if len(labs) < 10:
        return {"status": "INSUFFICIENT_EVIDENCE", "state_mapping": {s:i for i,s in enumerate(states)}, "probabilities": {str(h): {} for h in HORIZONS}}
    idx = {s:i for i,s in enumerate(states)}; counts = np.ones((len(states), len(states)))
    for a,b in zip(labs[:-1], labs[1:]): counts[idx[a], idx[b]] += 1
    P = counts / counts.sum(axis=1, keepdims=True); c = idx[str(current)]
    probs = {}
    for h in HORIZONS:
        Ph = np.linalg.matrix_power(P, h); row = Ph[c]
        probs[str(h)] = {s: float(row[idx[s]]) for s in states}
    persist = float(P[c,c]); entropy = float(-np.sum(P[c] * np.log(np.clip(P[c],1e-12,1))))
    return {"status":"AVAILABLE", "state_mapping":idx, "one_step_matrix":P.tolist(), "probabilities":probs,
            "probability_persist_1h":persist, "probability_reversal_1h":1.0-persist,
            "expected_duration": float(1.0/max(1.0-persist,1e-9)), "regime_entropy":entropy,
            "deterministic_ordering":"LEXICOGRAPHIC_CANONICAL_LABEL_ORDER"}


def drift_state(reference: Sequence[float], recent: Sequence[float], *, min_n: int = 20) -> dict[str, Any]:
    a,b = _finite(reference), _finite(recent)
    if min(a.size,b.size) < min_n: return {"state":"INSUFFICIENT_EVIDENCE", "score":None, "reference_n":int(a.size), "recent_n":int(b.size)}
    scale = max(float(np.std(a, ddof=1)), 1e-9)
    mean_shift = abs(float(np.mean(b)-np.mean(a)))/scale
    var_ratio = max(float(np.std(b,ddof=1))/scale, scale/max(float(np.std(b,ddof=1)),1e-9))
    score = mean_shift + max(0.0, log(max(var_ratio,1.0)))
    state = "DRIFTED" if score >= 1.5 else "WATCH" if score >= 0.75 else "STABLE"
    return {"state":state,"score":float(score),"mean_shift_z":mean_shift,"variance_ratio":var_ratio,"reference_n":int(a.size),"recent_n":int(b.size)}


def counterfactual_regret(decision: str, price_change_pips: float, cost_pips: float) -> dict[str, Any]:
    d = str(decision or "WAIT").upper(); move=float(price_change_pips); cost=max(float(cost_pips),0.0)
    values={"BUY":move-cost,"SELL":-move-cost,"WAIT":0.0}; best=max(values,key=values.get)
    chosen=values.get(d,0.0)
    return {"production_action":d,"production_action_realised_value":float(chosen),"counterfactual_values":values,
            "best_counterfactual_action":best,"best_counterfactual_value":float(values[best]),
            "regret":float(values[best]-chosen),"transaction_cost_pips":cost}


def diebold_mariano(loss_a: Sequence[float], loss_b: Sequence[float], *, horizon: int = 1) -> dict[str, Any]:
    a,b=_finite(loss_a),_finite(loss_b); n=min(a.size,b.size)
    if n < 30: return {"status":"INSUFFICIENT_SAMPLE","sample_count":int(n),"statistic":None}
    d=a[:n]-b[:n]; lag=max(0,int(horizon)-1); gamma=float(np.var(d,ddof=1))
    for k in range(1,min(lag,n-2)+1): gamma += 2.0*(1.0-k/(lag+1))*float(np.cov(d[k:],d[:-k],ddof=1)[0,1])
    se=sqrt(max(gamma/n,1e-18)); stat=float(np.mean(d)/se)
    p=float(2.0*(1.0-0.5*(1.0+erf(abs(stat)/sqrt(2.0)))))
    status="SUPERIOR" if stat>1.96 else "INFERIOR" if stat<-1.96 else "NOT_SIGNIFICANT"
    return {"status":status,"sample_count":int(n),"statistic":stat,"p_value":p,"hac_lag":lag,"positive_means_b_lower_loss":True}


def pbo_proxy(block_losses: Sequence[Sequence[float]]) -> dict[str, Any]:
    x=np.asarray(block_losses,dtype=float)
    if x.ndim!=2 or min(x.shape)<4: return {"status":"INSUFFICIENT_SAMPLE","probability_overfit":None}
    winners=[]
    for hold in range(x.shape[1]):
        train=np.delete(x,hold,axis=1).mean(axis=1); winner=int(np.argmin(train)); ranks=np.argsort(np.argsort(x[:,hold]))
        winners.append(float(ranks[winner]/max(x.shape[0]-1,1)))
    pbo=float(np.mean(np.asarray(winners)>.5))
    return {"status":"OVERFIT_RISK" if pbo>.5 else "ACCEPTABLE","probability_overfit":pbo,"blocks":int(x.shape[1]),"configurations":int(x.shape[0])}


def linear_attribution(features: Mapping[str,float], coefficients: Mapping[str,float], intercept: float=0.0) -> dict[str,Any]:
    contrib={k:float(features.get(k,0.0))*float(v) for k,v in coefficients.items()}; total=float(intercept+sum(contrib.values()))
    ranked=sorted(contrib.items(),key=lambda kv:abs(kv[1]),reverse=True)
    return {"baseline_output":float(intercept),"model_output":total,"contributions":contrib,
            "top_positive":[{"feature":k,"value":v} for k,v in ranked if v>0][:5],
            "top_negative":[{"feature":k,"value":v} for k,v in ranked if v<0][:5],
            "reconciliation_error":float(total-intercept-sum(contrib.values())),
            "limitations":"Predictive additive attribution; not a causal explanation."}


def promotion_status(*, dm_status:str, coverage:float|None, target_coverage:float, drift:str, pbo_status:str, sample_count:int, net_after_cost:float|None, stable_blocks:bool) -> str:
    if sample_count < 30: return "INSUFFICIENT_SAMPLE"
    if drift == "DRIFTED": return "DRIFT_BLOCKED"
    if coverage is None or coverage < target_coverage-0.05: return "COVERAGE_FAILED"
    if pbo_status == "OVERFIT_RISK" or not stable_blocks: return "OVERFIT_RISK"
    if dm_status == "INFERIOR": return "INFERIOR"
    if dm_status == "SUPERIOR" and net_after_cost is not None and net_after_cost > 0: return "SUPERIOR"
    return "NOT_SIGNIFICANT"

__all__=["VERSION","HORIZONS","STATES","MODEL_STATUSES","gaussian_crps","sample_crps","quantile_crps","settlement_state","settle_origin","conformal_interval","transition_evidence","drift_state","counterfactual_regret","diebold_mariano","pbo_proxy","linear_attribution","promotion_status"]

def build_governance_summary(snapshot: Mapping[str,Any], research_payload: Mapping[str,Any]) -> dict[str,Any]:
    """Compact saved sidecar for Lunch; performs no training and changes no decision."""
    run_id=str(snapshot.get("run_id") or research_payload.get("run_id") or "")
    decision=str(snapshot.get("decision") or snapshot.get("production_decision") or "WAIT")
    broker=str(snapshot.get("broker_candle_time") or snapshot.get("broker_candle_timestamp") or research_payload.get("origin_candle_time") or "")
    promotion=(research_payload.get("promotion_eligibility") or {}).get("models") or []
    statuses=[str(x.get("status") or "") for x in promotion if isinstance(x,Mapping)]
    validation="SUPERIOR" if "SUPERIOR" in statuses else "NOT_SIGNIFICANT" if promotion else "INSUFFICIENT_SAMPLE"
    return {"run_id":run_id,"model_version":VERSION,"broker_candle_timestamp":broker,
            "production_decision":decision,"production_decision_unchanged":True,"shadow_only":True,
            "drift_state":"INSUFFICIENT_EVIDENCE","validation_status":validation,"pbo_status":"INSUFFICIENT_SAMPLE",
            "source_snapshot_hash":research_payload.get("snapshot_hash"),
            "limitations":["Promotion remains disabled until leakage-safe matured out-of-sample evidence passes every gate."]}

__all__.append("build_governance_summary")
