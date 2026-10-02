from __future__ import annotations
import json, sqlite3
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping
MIGRATION=Path(__file__).resolve().parents[1]/'migrations'/'20260624_advanced_causal_forecast.sql'

def ensure_schema(conn:sqlite3.Connection)->None:
    conn.executescript(MIGRATION.read_text(encoding='utf-8'))

def save(conn:sqlite3.Connection,p:Mapping[str,Any])->dict[str,Any]:
    ensure_schema(conn);rid=str(p.get('run_id') or '');t=str(p.get('origin_candle_time') or '');version=str(p.get('schema_version') or 'advanced-causal')
    for hs,h in (p.get('horizons') or {}).items():
        hi=int(hs);oi=h.get('origin_interval') or {};qs=h.get('quantiles') or {};scores=h.get('scores') or {}
        conn.execute('INSERT OR IGNORE INTO forecast_origin_distributions(run_id,origin_candle_time,horizon,model_version,lower,upper,target_alpha,interval_method,interval_width,quantiles_json,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(rid,t,hi,version,oi.get('lower'),oi.get('upper'),oi.get('target_alpha'),oi.get('method'),oi.get('width'),json.dumps(qs,sort_keys=True),json.dumps(h,sort_keys=True,default=str)))
        for q,v in qs.items():conn.execute('INSERT OR IGNORE INTO quantile_forecasts(run_id,origin_candle_time,horizon,quantile,value,model_version) VALUES(?,?,?,?,?,?)',(rid,t,hi,float(q),float(v),version))
        for model,w in (h.get('weights') or {}).items():
            for q in qs:conn.execute('INSERT OR IGNORE INTO model_origin_weights(run_id,origin_candle_time,horizon,quantile,model_name,weight) VALUES(?,?,?,?,?,?)',(rid,t,hi,float(q),model,float(w)))
        conn.execute('INSERT OR REPLACE INTO probabilistic_scores(run_id,origin_candle_time,horizon,model_version,crps,crps_method,mae,rmse,direction_brier,interval_score,coverage,sharpness,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(rid,t,hi,version,scores.get('crps'),scores.get('crps_method'),scores.get('mae'),scores.get('rmse'),scores.get('direction_brier'),scores.get('interval_score'),scores.get('empirical_coverage'),scores.get('sharpness'),json.dumps(scores,sort_keys=True,default=str)))
        conn.execute('INSERT OR REPLACE INTO conformal_calibration_state(run_id,horizon,origin_candle_time,method,target_alpha,rolling_coverage,coverage_debt,payload_json) VALUES(?,?,?,?,?,?,?,?)',(rid,hi,t,oi.get('method',''),oi.get('target_alpha'),scores.get('empirical_coverage'),h.get('coverage_debt'),json.dumps(oi,sort_keys=True,default=str)))
    for scale,v in ((p.get('regime') or {}).get('scales') or {}).items():
        for regime in ('bull','bear','high_volatility','low_volatility'):
            if v.get(regime) is not None:conn.execute('INSERT OR REPLACE INTO regime_probabilities(run_id,origin_candle_time,scale,regime,probability,model_version,payload_json) VALUES(?,?,?,?,?,?,?)',(rid,t,scale,regime,v.get(regime),version,json.dumps(v,sort_keys=True,default=str)))
    duration=p.get('duration') or {};regime=(p.get('regime') or {}).get('major_regime','UNKNOWN')
    conn.execute('INSERT OR REPLACE INTO regime_durations(run_id,origin_candle_time,regime,age,expected_total,expected_remaining,payload_json) VALUES(?,?,?,?,?,?,?)',(rid,t,regime,duration.get('current_regime_age'),duration.get('expected_total_duration'),duration.get('expected_remaining_duration'),json.dumps(duration,sort_keys=True,default=str)))
    drift=p.get('drift') or {};event_hash=sha256(f"{rid}|{t}|{drift.get('state')}".encode()).hexdigest()
    conn.execute('INSERT OR REPLACE INTO drift_events(event_hash,run_id,origin_candle_time,state,payload_json) VALUES(?,?,?,?,?)',(event_hash,rid,t,drift.get('state','INSUFFICIENT_HISTORY'),json.dumps(drift,sort_keys=True,default=str)))
    meta=p.get('meta_label') or {};conn.execute('INSERT OR REPLACE INTO meta_label_outcomes(run_id,origin_candle_time,primary_side,meta_label,actionability_probability,payload_json) VALUES(?,?,?,?,?,?)',(rid,t,meta.get('primary_side','WAIT'),meta.get('label','insufficient matured evidence'),meta.get('actionability_probability'),json.dumps(meta,sort_keys=True,default=str)))
    conn.execute('INSERT OR REPLACE INTO confidence_set_results(run_id,origin_candle_time,horizon,metric,regime,session,volatility_bucket,payload_json) VALUES(?,?,?,?,?,?,?,?)',(rid,t,0,'MULTI_METRIC',regime,'ALL','ALL',json.dumps(p.get('model_confidence_set') or {},sort_keys=True,default=str)))
    gate=p.get('promotion_gate') or {};conn.execute('INSERT OR REPLACE INTO promotion_gate_results(run_id,origin_candle_time,eligible,payload_json) VALUES(?,?,?,?)',(rid,t,int(bool(gate.get('eligible'))),json.dumps(gate,sort_keys=True,default=str)))
    rt=p.get('runtime') or {};conn.execute('INSERT OR REPLACE INTO runtime_metrics(run_id,origin_candle_time,module,wall_seconds,peak_memory_bytes,payload_json) VALUES(?,?,?,?,?,?)',(rid,t,'advanced_causal_forecast',rt.get('wall_seconds'),rt.get('peak_traced_memory_bytes'),json.dumps(rt,sort_keys=True,default=str)))
    conn.commit();return {'ok':True,'run_id':rid,'origin_candle_time':t}
__all__=['ensure_schema','save']
