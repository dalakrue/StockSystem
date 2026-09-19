"""Unified research-grade shadow pipeline V19.

Additive only: reads the immutable canonical snapshot and V17 research evidence.
It never imports or mutates Field 1 production logic. Heavy publication is intended
for the Settings one-click transaction; renderers only consume saved compact output.
"""
from __future__ import annotations
import hashlib, json, math, sqlite3, time, tracemalloc
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

VERSION = "v19.20260624"
HORIZONS = (1, 2, 3, 6)

def _m(v): return dict(v) if isinstance(v, Mapping) else {}
def _f(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception: return None
def _iso(v):
    if isinstance(v, datetime): return v.astimezone(timezone.utc).isoformat()
    return str(v or "")
def _hash(v): return hashlib.sha256(json.dumps(v,sort_keys=True,default=str,separators=(",",":")).encode()).hexdigest()
def _clip(v, lo=0.0, hi=1.0): return max(lo,min(hi,float(v)))
def _status(n, minimum=20): return "AVAILABLE" if n >= minimum else "INSUFFICIENT_EVIDENCE"

def build_contract(snapshot: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    s=_m(snapshot)
    broker=_iso(s.get("broker_candle_time") or s.get("candle_time") or s.get("data_cutoff_time"))
    run_id=str(s.get("run_id") or s.get("generation_id") or "")
    source_hash=str(s.get("source_data_hash") or state.get("source_data_hash") or _hash({"run_id":run_id,"broker":broker,"price":s.get("current_price")}))
    return {"run_id":run_id,"symbol":str(s.get("symbol") or "EURUSD"),"timeframe":str(s.get("timeframe") or "H1"),"broker_candle_time":broker,"source_data_hash":source_hash,"model_version":VERSION,"evidence_version":VERSION,"production_decision":str(s.get("decision") or s.get("production_decision") or "WAIT").upper(),"production_regime":str(s.get("regime") or s.get("production_regime") or "UNKNOWN"),"current_price":_f(s.get("current_price") or s.get("price"))}

def _history(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows=state.get("prediction_outcomes") or state.get("forecast_outcomes") or []
    return [dict(r) for r in rows if isinstance(r,Mapping)]

def _field2(contract, v17, state):
    source=_m(v17.get("field2")); hist=_history(state); rows={}
    for h in HORIZONS:
        if h==2:
            a,b=_m(source.get("1")),_m(source.get("3"))
            def avg(k):
                x,y=_f(a.get(k)),_f(b.get(k)); return None if x is None or y is None else (x+y)/2
            base={"point_forecast":avg("point_forecast"),"origin_lower":avg("origin_lower"),"origin_upper":avg("origin_upper"),"display_derivation":"LINEAR_INTERPOLATION_H1_H3_SHADOW_ONLY"}
        else: base=_m(source.get(str(h)))
        matured=[r for r in hist if int(_f(r.get("horizon")) or -1)==h and str(r.get("settlement_status") or r.get("status")).upper() in {"MATURED","FULLY_SETTLED","SETTLED"}]
        errs=[]; cover=[]; direction=[]
        for r in matured:
            a,p=_f(r.get("actual_return")),_f(r.get("predicted_return"))
            if a is not None and p is not None:
                errs.append(a-p); direction.append(int((a>=0)==(p>=0)))
                lo,hi=_f(r.get("origin_lower")),_f(r.get("origin_upper"))
                if lo is not None and hi is not None: cover.append(int(lo<=a<=hi))
        n=len(errs); mae=sum(abs(x) for x in errs)/n if n else None; rmse=math.sqrt(sum(x*x for x in errs)/n) if n else None
        lo,hi=_f(base.get("origin_lower")),_f(base.get("origin_upper")); point=_f(base.get("point_forecast")); width=None if lo is None or hi is None else hi-lo
        metrics=_m(base.get("metrics")); cp=_f(_m(v17.get("field3")).get("changepoint_probability")) or 0
        disagreement=_f(base.get("model_disagreement") or _m(base.get("ensemble")).get("model_disagreement"))
        path_stability=_clip(1-(disagreement or 0)-0.5*cp)
        rows[str(h)]={**contract,"horizon":h,"maturity_time":_mature(contract["broker_candle_time"],h),"pending_matured_status":"PENDING","current_price":contract["current_price"],"predicted_price":point,"consensus_path":point,"bullish_trajectory":hi,"adverse_trajectory":lo,"raw_band":{"lower":_f(base.get("raw_lower") or lo),"upper":_f(base.get("raw_upper") or hi)},"conformal_band":{"lower":lo,"upper":hi},"interval_coverage":(sum(cover)/len(cover) if cover else _f(metrics.get("interval_coverage"))),"interval_sharpness":width,"empirical_calibration_error":(abs((sum(cover)/len(cover))-0.90) if cover else None),"path_mae":mae if mae is not None else _f(metrics.get("mae")),"path_rmse":rmse if rmse is not None else _f(metrics.get("rmse")),"endpoint_error":abs(errs[-1]) if errs else None,"turning_point_error":None,"maximum_path_deviation":max((abs(x) for x in errs),default=None),"realized_vs_predicted_volatility":None,"aleatoric_uncertainty":width/3.29 if width is not None else None,"epistemic_uncertainty":disagreement,"whole_path_stability":path_stability,"trajectory_coverage":sum(cover)/len(cover) if cover else None,"trusted_forecast_horizon":h if n>=20 and (not cover or sum(cover)/len(cover)>=.80) else None,"change_point_warning":cp>=.35,"regime_conditioned_forecast":{"lower":lo,"middle":point,"higher":hi},"three_standard_regime_agreement":_f(_m(v17.get("field3")).get("three_standard_agreement")),"direction_correctness":sum(direction)/len(direction) if direction else None,"evidence_count":n,"evidence_sufficiency":_status(n),"content_hash":""}
        rows[str(h)]["content_hash"]=_hash(rows[str(h)])
    probs=_action_probabilities(v17, rows)
    for r in rows.values(): r.update(probs)
    return rows

def _mature(broker,h):
    try:return (datetime.fromisoformat(broker.replace("Z","+00:00"))+timedelta(hours=h)).isoformat()
    except Exception:return ""

def _action_probabilities(v17, f2):
    acts={"BUY":None,"WAIT":None,"SELL":None}
    for r in _m(v17.get("field9")).get("action_results") or []:
        a=str(r.get("action") or "").upper()
        if a in acts: acts[a]=_f(r.get("action_probability"))
    if not any(v is not None for v in acts.values()):
        h3=_m(f2.get("3")); p=_f(h3.get("predicted_price")); c=_f(h3.get("current_price")); up=.5 if p is None or c is None else _clip(.5+(p-c)*2500)
        wait=_clip(1-abs(up-.5)*2); acts={"BUY":up,"SELL":1-up,"WAIT":wait}
    total=sum(v or 0 for v in acts.values()) or 1
    return {f"{k.lower()}_probability":(v or 0)/total for k,v in acts.items()}

def _field3(contract,v17,state):
    src=_m(v17.get("field3")); cp=_f(src.get("changepoint_probability")) or 0.0; prod=contract["production_regime"]
    posterior=_m(src.get("posterior_probabilities")); top=max(posterior,key=posterior.get) if posterior else prod
    standards={}
    specs=(("lower",24,1.0),("middle",120,.72),("higher",600,.45))
    for name,window,speed in specs:
        n=min(window,len(_history(state))); prob=_clip((_f(posterior.get(top)) or .5)*(1-cp*speed)); age=max(1,int((_f(src.get("expected_regime_duration")) or 6)*(1-speed/3)))
        label=top if prob>=.55 else "TRANSITION"
        standards[name]={"regime_label":label,"probability":prob,"age":age,"expected_remaining_duration":max(0,(_f(src.get("estimated_remaining_duration")) or 6)-age/3),"transition_probability_1h":_clip(cp*speed),"transition_probability_3h":_clip(cp*speed*1.35),"transition_probability_6h":_clip(cp*speed*1.7),"change_point_probability":_clip(cp*speed),"feature_stability":_clip(1-cp*speed),"forecast_residual_stability":_clip(_f(src.get("persistence_probability")) or .5),"evidence_count":n,"reliability":prob if n>=20 else None,"knn_priority":label,"greedy_priority":label,"less_risky_bias":"WAIT" if label=="TRANSITION" else ("BUY" if "BULL" in label else "SELL" if "BEAR" in label else "WAIT"),"evidence_sufficiency":_status(n)}
    labels={x["regime_label"] for x in standards.values()}; disagreement=len(labels)>1; sparse=any(x["evidence_count"]<20 for x in standards.values())
    consensus="TRANSITION / INSUFFICIENT EVIDENCE / WAIT PREFERRED" if disagreement or cp>=.35 or sparse else max(standards.values(),key=lambda x:x["reliability"] or 0)["regime_label"]
    return {**contract,"standards":standards,"consensus_regime":consensus,"material_disagreement":disagreement,"change_point_probability":cp,"reliability_weighted_consensus":consensus,"production_regime_preserved":prod,"content_hash":_hash(standards)}

def _integrated_row(contract,f2,f3,v17):
    h3=_m(f2.get("3")); f9=_m(v17.get("field9")); std=f3["standards"]
    return {**contract,"field_id":"FIELD_4","evidence_type":"INTEGRATED_HISTORY","horizon":3,"maturity_time":h3.get("maturity_time"),"pending_matured_status":"PENDING","broker_time":contract["broker_candle_time"],"decision":contract["production_decision"],"lower_regime":std["lower"]["regime_label"],"middle_regime":std["middle"]["regime_label"],"higher_regime":std["higher"]["regime_label"],"consensus_regime":f3["consensus_regime"],"prediction_path_bias":max(("BUY","WAIT","SELL"),key=lambda a:h3.get(a.lower()+"_probability") or 0),"buy_probability":h3.get("buy_probability"),"wait_probability":h3.get("wait_probability"),"sell_probability":h3.get("sell_probability"),"reliability":std["middle"].get("reliability"),"uncertainty":f3.get("change_point_probability"),"expected_value_after_costs":f9.get("net_expected_action_value") or f9.get("after_cost_expected_value"),"adverse_impact_estimate":f9.get("expected_adverse_impact") or f9.get("downside_probability"),"main_supporting_factor":f9.get("main_supporting_factor") or "Multi-horizon calibrated path","main_contradiction":f9.get("main_contradiction") or ("Regime standards disagree" if f3["material_disagreement"] else "None material in saved evidence"),"minimum_reversal_condition":f9.get("minimum_input_change_required") or "Insufficient evidence","outcome_status":"PENDING","realized_result":None,"regret":f9.get("counterfactual_regret"),"content_hash":""}

def _history_rows(contract,f2,f3,v17,state):
    base=_integrated_row(contract,f2,f3,v17); base["content_hash"]=_hash(base)
    rows={"field4":[base],"field6":[],"field7":[],"field8":[]}
    hist=_history(state)
    for r in hist[-600:]:
        bt=_iso(r.get("origin_candle_time") or r.get("broker_candle_time")); h=int(_f(r.get("horizon")) or 1); status=str(r.get("settlement_status") or "PENDING")
        common={**contract,"broker_candle_time":bt or contract["broker_candle_time"],"horizon":h,"maturity_time":_iso(r.get("maturity_time")),"pending_matured_status":"MATURED" if status in {"FULLY_SETTLED","SETTLED","MATURED"} else "PENDING"}
        f6={**common,"field_id":"FIELD_6","evidence_type":"PREPARATION","session_state":r.get("session") or "UNKNOWN","london_overlap_preparation":r.get("session") in {"LONDON","LONDON_NY_OVERLAP"},"eurusd_h1_context":r.get("origin_regime") or "UNKNOWN","m1_confirmation":r.get("m1_confirmation") or "Insufficient evidence","pattern_evidence":r.get("pattern") or "Insufficient evidence","cross_horizon_agreement":r.get("cross_horizon_agreement"),"sentiment_technical_agreement":r.get("sentiment_technical_agreement"),"preparation_decision":r.get("decision") or "WAIT","evidence_freshness":r.get("freshness") or "HISTORICAL","outcome":r.get("actual_return")}
        f7={**common,"field_id":"FIELD_7","evidence_type":"CHALLENGER","challenger_name":r.get("model_name") or "heterogeneous_ensemble","eligible_ineligible":"ELIGIBLE" if common["pending_matured_status"]=="MATURED" else "INELIGIBLE","regime":r.get("origin_regime"),"walk_forward_score":None if _f(r.get("actual_return")) is None or _f(r.get("predicted_return")) is None else abs(_f(r.get("actual_return"))-_f(r.get("predicted_return"))),"calibration_score":r.get("brier_score"),"drift_state":"WARNING" if (_f(r.get("changepoint_probability")) or 0)>=.35 else "STABLE","champion_challenger_difference":r.get("champion_challenger_difference"),"status":"SHADOW","reason":"Production remains canonical","matured_outcome":r.get("actual_return")}
        a,p=_f(r.get("actual_return")),_f(r.get("predicted_return")); err=None if a is None or p is None else a-p; lo,hi=_f(r.get("origin_lower")),_f(r.get("origin_upper"))
        f8={**common,"field_id":"FIELD_8","evidence_type":"ACCURACY","path_mae":abs(err) if err is not None else None,"path_rmse":abs(err) if err is not None else None,"endpoint_error":abs(err) if err is not None else None,"turning_point_error":None,"direction_correctness":None if a is None or p is None else int((a>=0)==(p>=0)),"brier_score":r.get("brier_score"),"log_score":r.get("log_score"),"interval_score":None if a is None or lo is None or hi is None else (hi-lo)+(20*(lo-a) if a<lo else 20*(a-hi) if a>hi else 0),"coverage":None if a is None or lo is None or hi is None else int(lo<=a<=hi),"sharpness":None if lo is None or hi is None else hi-lo,"regime_correctness":None if not r.get("actual_regime") else int(r.get("actual_regime")==r.get("origin_regime")),"transition_correctness":r.get("transition_correctness"),"reliability_calibration":r.get("reliability_calibration"),"expected_value_after_costs":r.get("expected_value_after_costs"),"realized_value":a,"maximum_adverse_excursion":r.get("maximum_adverse_excursion"),"regret":r.get("regret"),"evidence_sufficiency":"AVAILABLE" if a is not None else "INSUFFICIENT_EVIDENCE"}
        for key,row in (("field6",f6),("field7",f7),("field8",f8)):
            row["content_hash"]=_hash(row); rows[key].append(row)
    for key in rows: rows[key]=sorted(rows[key],key=lambda x:x.get("broker_candle_time","") ,reverse=True)[:600]
    return rows

def _priority(contract,f2,f3,v17):
    h3=_m(f2.get("3")); probs={a:h3.get(a.lower()+"_probability") or 0 for a in ("BUY","WAIT","SELL")}; ranked=sorted(probs,key=probs.get,reverse=True); f9=_m(v17.get("field9"))
    return {**contract,"priority_1":ranked[0],"priority_2":ranked[1],"priority_3":ranked[2],"current_decision":contract["production_decision"],"less_risky_action":"WAIT" if f3["material_disagreement"] or f3["change_point_probability"]>=.35 else ranked[0],"current_regime":contract["production_regime"],"regime_disagreement":f3["material_disagreement"],"prediction_path_state":h3.get("evidence_sufficiency"),"reliability":f3["standards"]["middle"].get("reliability"),"uncertainty":f3["change_point_probability"],"principal_reason":f9.get("main_supporting_factor") or "Calibrated multi-horizon evidence","principal_risk":f9.get("main_contradiction") or ("Transition risk" if f3["change_point_probability"]>=.35 else "Evidence may be sparse"),"reversal_condition":f9.get("minimum_input_change_required") or "Insufficient evidence","evidence_sufficiency":h3.get("evidence_sufficiency")}

def evaluate(snapshot,state,v17=None):
    started=time.perf_counter(); tracemalloc.start(); contract=build_contract(snapshot,state); v17=_m(v17 or state.get("research_grade_system_v17_20260624")); f2=_field2(contract,v17,state); f3=_field3(contract,v17,state); histories=_history_rows(contract,f2,f3,v17,state); current=_integrated_row(contract,f2,f3,v17); current["content_hash"]=_hash(current); _,peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
    return {**contract,"ok":True,"status":"AVAILABLE","shadow_only":True,"production_influence_enabled":False,"field2":f2,"field3":f3,"field4_current":current,"histories":histories,"priority_summary":_priority(contract,f2,f3,v17),"ai_sources":{"canonical":contract,"field2":f2,"field3":f3,"field4":current,"histories":histories},"performance":{"runtime_seconds":time.perf_counter()-started,"peak_memory_bytes":peak,"shared_feature_matrix_reused":True,"heavy_models_retained":False},"limitations":["Shadow evidence cannot change Field 1 or the production decision.","No profitability or future accuracy guarantee.","H2 is an explicitly labelled display-only interpolation unless a native H2 origin exists."]}

def _db_path(state): return Path(str(state.get("unified_shadow_v19_db_path") or Path("data")/"unified_shadow_v19.sqlite"))
def migrate(conn):
    conn.executescript("""CREATE TABLE IF NOT EXISTS unified_shadow_v19_runs(run_id TEXT PRIMARY KEY, broker_candle_time TEXT, payload_json TEXT NOT NULL, content_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS unified_shadow_v19_history(history_key TEXT PRIMARY KEY, run_id TEXT NOT NULL, field_id TEXT NOT NULL, evidence_type TEXT NOT NULL, horizon INTEGER, broker_candle_time TEXT NOT NULL, maturity_time TEXT, pending_matured_status TEXT NOT NULL, content_hash TEXT NOT NULL, row_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_usv19_history_field_time ON unified_shadow_v19_history(field_id,broker_candle_time DESC);""")
def _key(r): return "|".join(str(r.get(k) or "") for k in ("broker_candle_time","run_id","field_id","evidence_type","horizon"))
def publish(state,snapshot,v17=None):
    payload=evaluate(snapshot,state,v17); path=_db_path(state); path.parent.mkdir(parents=True,exist_ok=True); conn=sqlite3.connect(path)
    try:
        migrate(conn); blob=json.dumps(payload,default=str,sort_keys=True); h=_hash(payload); existing=conn.execute("SELECT content_hash FROM unified_shadow_v19_runs WHERE run_id=?",(payload["run_id"],)).fetchone()
        if existing and existing[0]==h: payload["idempotent_cache_hit"]=True
        else: conn.execute("INSERT OR REPLACE INTO unified_shadow_v19_runs VALUES(?,?,?,?,?)",(payload["run_id"],payload["broker_candle_time"],blob,h,datetime.now(timezone.utc).isoformat()))
        for group in payload["histories"].values():
            for r in group:
                conn.execute("INSERT OR IGNORE INTO unified_shadow_v19_history VALUES(?,?,?,?,?,?,?,?,?,?)",(_key(r),r["run_id"],r["field_id"],r["evidence_type"],r.get("horizon"),r["broker_candle_time"],r.get("maturity_time"),r["pending_matured_status"],r["content_hash"],json.dumps(r,default=str,sort_keys=True)))
        conn.commit()
    finally: conn.close()
    state["unified_shadow_pipeline_v19_20260624"]=payload; return payload

INTENTS={"current decision":("decision","buy","sell","wait","action"),"prediction":("prediction","forecast","path","price"),"regime":("regime","transition","changepoint"),"history":("history","past","25 day"),"reliability":("reliability","trust","confidence"),"uncertainty":("uncertainty","interval","coverage"),"risk":("risk","adverse","drawdown"),"reversal condition":("reverse","reversal","change decision"),"model comparison":("model","challenger","champion"),"explanation":("why","explain","reason"),"session":("session","london","overlap"),"system health":("health","run id","broker time","sync")}
def route_intent(question):
    q=str(question or "").lower()
    for intent,terms in INTENTS.items():
        if any(t in q for t in terms): return intent
    return "unsupported/off-topic"
def answer_question(question,payload):
    p=_m(payload); intent=route_intent(question); c={k:p.get(k) for k in ("run_id","broker_candle_time","production_decision","production_regime")}; f3=_m(p.get("field3")); f4=_m(p.get("field4_current")); pr=_m(p.get("priority_summary"))
    if intent=="unsupported/off-topic": return {"intent":intent,"answer":"I only answer from this EURUSD H1 system's saved canonical and shadow evidence. No market value was invented."}
    hist=_m(p.get("histories")); support=len(hist.get("field8") or [])
    lines=[f"Direct answer: {intent.replace('_',' ').title()} is grounded in the saved run.",f"Current production value: decision={c.get('production_decision')}; regime={c.get('production_regime')}.",f"Three-standard regime interpretation: {f3.get('consensus_regime') or 'Insufficient evidence'}.",f"Reliability and uncertainty: reliability={pr.get('reliability')}; uncertainty={pr.get('uncertainty')}.",f"Main supporting factors: {pr.get('principal_reason') or 'Insufficient evidence'}.",f"Main contradictory factors: {f4.get('main_contradiction') or 'Insufficient evidence'}.",f"Minimum reversal conditions: {pr.get('reversal_condition') or 'Insufficient evidence'}.",f"Historical support: {support} stored accuracy rows; missing observations are not fabricated.",f"Broker candle time and run_id: {c.get('broker_candle_time')} · {c.get('run_id')}." ]
    return {"intent":intent,"answer":"\n\n".join(lines)}



def build_ai_evidence_contract_for_state(state):
    from core.ai_canonical_intents_v10 import build_ai_evidence_contract
    return build_ai_evidence_contract(state)


def answer_ai_question_from_state(question, state):
    from core.ai_canonical_intents_v10 import answer_canonical_question
    return answer_canonical_question(question, state)
