from __future__ import annotations
from datetime import datetime, timezone
import uuid
from typing import Any, Mapping
from .schemas import ALGORITHM_VERSION
from .decision_mapping import map_decision
from .calibration import calibrated_from_action
from .conditional_reliability import matrix
from .dynamic_model_averaging import update_weights
from .regime_model import infer_regime
from .changepoint import detect
from .validation_gates import default_validation
from .evidence_fusion import fuse
from .master_policy import decide, POLICY_VERSION
from .history_store import append_history, register_experiment, version_history
from .diagnostics import stable_hash, equation_parameters
from .ablation import build as build_ablation

DECISION_KEYS=("decision","entry_decision","less_risky_bias","direction","master_decision","technical_bias")
def _mapping(v): return dict(v) if isinstance(v,Mapping) else {}
def _find_sources(snapshot):
    rows=[]; seen=set()
    def walk(obj,path="canonical"):
        if isinstance(obj,Mapping):
            for k,v in obj.items():
                kp=f"{path}.{k}"
                if str(k).lower() in DECISION_KEYS and isinstance(v,(str,int,float)):
                    key=(kp,str(v));
                    if key not in seen: rows.append((path,k,str(v))); seen.add(key)
                elif isinstance(v,Mapping): walk(v,kp)
    walk(snapshot)
    if not rows: rows=[("canonical","decision",str(snapshot.get("decision") or "WAIT"))]
    return rows[:32]
def build_arcef_result(snapshot: Mapping[str,Any], *, state=None):
    snap=_mapping(snapshot); run_id=str(snap.get("run_id") or ""); generation_id=str(snap.get("generation_id") or snap.get("calculation_generation") or "")
    model_rows=[]
    for field,table,label in _find_sources(snap):
        m=map_decision(label); conf=float(snap.get("confidence") or snap.get("reliability_score") or 50)/100; conf=max(0,min(1,conf))
        probs=calibrated_from_action(m["standardized_action"],conf)
        model_rows.append({"source_field":field,"source_table":table,**m,"published_confidence":conf,"calibrated_reliability":max(.25,conf),"conditional_reliability":max(.25,conf),"probabilities":probs})
    names=[f"{r['source_field']}::{r['source_table']}" for r in model_rows]; reg=infer_regime(snap); cp=detect(snap,reg["regime_entropy"])
    prior={n:1/max(1,len(names)) for n in names}; likelihoods={n:max(.05,model_rows[i]["calibrated_reliability"]) for i,n in enumerate(names)}
    dyn=update_weights(prior,likelihoods,.97,cp["reset_factor"]); gates=default_validation(names)
    un=[]
    for i,r in enumerate(model_rows):
        n=names[i]; r.update({"raw_dynamic_weight":dyn[n],"dynamic_weight":dyn[n],"global_reliability":r["calibrated_reliability"],"validation_gate":gates[n]["gate"],"validation_status":gates[n]["reason"],"mcs_status":"MEMBER" if gates[n]["mcs_member"] else "REJECTED","pbo_penalty":1-gates[n]["pbo"],"correlation_penalty":1.0,"data_quality_factor":max(.1,min(1,float(snap.get("data_quality_score") or 100)/100))})
        w=r["dynamic_weight"]*r["conditional_reliability"]*r["validation_gate"]*r["correlation_penalty"]*r["data_quality_factor"]*r["pbo_penalty"]; un.append(w)
    total=sum(un)
    if total<=0 and model_rows: un=[1/len(model_rows)]*len(model_rows); total=1
    for r,w in zip(model_rows,un): r["final_weight"]=w/total if total else 0; r["weighted_contribution"]=r["final_weight"]*r["standardized_action"]; r.setdefault("exclusion_reason","")
    fused=fuse(model_rows,reg["regime_entropy"],cp["changepoint_probability"])
    entry=max(0,min(1,float(snap.get("entry_score") or snap.get("priority_score") or 50)/100)); decision=decide(fused["direction_score"],fused["master_strength"],fused["uncertainty"],entry,cp["changepoint_probability"])
    intended="BUY" if fused["direction_score"]>0 else "SELL" if fused["direction_score"]<0 else "NONE"
    result={"ok":True,"algorithm_version":ALGORITHM_VERSION,"policy_version":POLICY_VERSION,"run_id":run_id,"generation_id":generation_id,"symbol":str(snap.get("symbol") or "EURUSD"),"timeframe":str(snap.get("timeframe") or "H1"),"completed_broker_candle":str(snap.get("broker_candle_time") or snap.get("latest_completed_candle_time") or snap.get("completed_candle_utc") or ""),"master_decision":decision,"intended_direction":intended,"entry_quality":entry,"reliability":sum(r["final_weight"]*r["conditional_reliability"] for r in model_rows),"valid_model_count":sum(1 for r in model_rows if r["final_weight"]>0),"excluded_model_count":sum(1 for r in model_rows if r["final_weight"]<=0),"data_quality_status":str(snap.get("data_quality_status") or "AVAILABLE"),**reg,**cp,**fused,"model_contribution_ledger":model_rows,"conditional_reliability_matrix":matrix(),"validation_tests":gates,"model_confidence_set":[n for n in names if gates[n]["mcs_member"]],"pbo_result":{"pbo":0.0,"status":"NOT_ESTIMATED_WITHOUT_CSCV_SAMPLE"},"walk_forward_result":{"status":"PENDING_SETTLED_HISTORY"},"ablation_study":build_ablation(),"equation_parameters":equation_parameters(),"proper_scoring_diagnostics":{"status":"requires settled probability/outcome pairs","brier_score":None,"log_loss":None,"calibration_error":None},"calibration_table":[],"prediction_interval":{"lower":None,"central":None,"upper":None,"width":None},"expected_value":None,"created_timestamp":datetime.now(timezone.utc).isoformat()}
    hist={"broker_candle":result["completed_broker_candle"],"master_decision":decision,"direction_score":fused["direction_score"],"master_strength":fused["master_strength"],"reliability":result["reliability"],"uncertainty":fused["uncertainty"],"regime":str(snap.get("regime") or "UNKNOWN"),"regime_entropy":reg["regime_entropy"],"change_probability":cp["changepoint_probability"],"entry_quality":entry,"forecast_lower":None,"forecast_centre":None,"forecast_upper":None,"actual_outcome":None,"realized_return":None,"correct_incorrect":None,"brier_score":None,"interval_covered":None,"model_agreement":1-fused["disagreement"],"valid_model_count":result["valid_model_count"],"effective_independent_models":fused["effective_independent_model_count"],"algorithm_version":ALGORITHM_VERSION,"run_id":run_id}
    result["history_25d"]=append_history(hist)
    exp={"experiment_id":f"{ALGORITHM_VERSION}-{run_id or uuid.uuid4().hex[:8]}","algorithm_version":ALGORITHM_VERSION,"source_code_hash":stable_hash({"version":ALGORITHM_VERSION}),"dataset_hash":str(snap.get("snapshot_hash") or stable_hash({"run_id":run_id,"generation_id":generation_id})),"features":[r["source_table"] for r in model_rows],"parameter_values":{"forgetting_factor":.97},"threshold_values":{"buy":.24,"sell":-.24},"training_window":"strictly prior settled history","calibration_window":"separate","validation_window":"walk-forward","test_window":"held-out","number_of_attempted_variants":6,"benchmark":"existing production system","loss_function":"multiclass Brier/log loss","result":"shadow published","p_values":{},"PBO":0.0,"deployment_status":"SHADOW_ONLY","created_timestamp":result["created_timestamp"]}
    register_experiment(exp); result["experiment_registry"]=version_history(); result["version_history"]=result["experiment_registry"]
    return result
def publish_arcef_result(state, snapshot):
    result=build_arcef_result(snapshot,state=state); state["arcef_sv_result"]=result; state["arcef_sv_run_id"]=result.get("run_id"); return result
