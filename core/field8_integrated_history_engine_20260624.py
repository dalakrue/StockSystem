"""Leakage-resistant Field 8 builder using only saved origin-time evidence."""
from __future__ import annotations
import math, json
from typing import Any, Mapping, MutableMapping
import numpy as np
import pandas as pd
from core.field8_integrated_history_contract_20260624 import CALCULATION_VERSION, Field8Bundle, TABLE_COLUMNS
from core.field8_probabilistic_scores_20260624 import crps, interval_score, brier_score, log_score
from core.field8_alpha_beta_delta_engine_20260624 import alpha_metrics, RecursiveBeta, classify_state, change_point_evidence, filardo_transition
from core.field8_dynamic_model_averaging_20260624 import DMAState
from core.shadow_multi_horizon_20260624 import HORIZONS, independent_expert_forecasts, dma_weights, reconcile, adaptive_interval, bocpd_proxy, three_standard_regime
_TIME_ALIASES=("broker_candle_time","Broker Time","Time","time","Datetime","DateTime","Timestamp","event_time_utc")

def _num(v,default=np.nan):
    try:
        x=float(v); return x if math.isfinite(x) else default
    except Exception:return default

def _first(m:Mapping[str,Any],*names,default=None):
    norm={''.join(ch for ch in str(k).lower() if ch.isalnum()):v for k,v in m.items()}
    for n in names:
        k=''.join(ch for ch in str(n).lower() if ch.isalnum())
        if k in norm and norm[k] not in (None,''):return norm[k]
    return default

def _source_frame(state:MutableMapping[str,Any])->pd.DataFrame:
    frames=[]
    for key in ("full_metric_history_df_20260618","canonical_priority_table_20260617","lunch_quick_decision_merged_table_20260617","home_reversal_25d_scan"):
        v=state.get(key)
        if isinstance(v,pd.DataFrame) and not v.empty:frames.append(v.copy(deep=False))
    return max(frames,key=len) if frames else pd.DataFrame()

def _time_column(df):return next((c for c in _TIME_ALIASES if c in df.columns),None)

def _origin_interval(raw,h):
    l=_num(_first(raw,f'origin_lower_h{h}',f'lower_interval_h{h}',f'lower_h{h}'))
    u=_num(_first(raw,f'origin_upper_h{h}',f'upper_interval_h{h}',f'upper_h{h}'))
    a=_num(_first(raw,f'origin_interval_alpha_h{h}',f'interval_alpha_h{h}'),.1)
    if pd.isna(l) or pd.isna(u):
        l=_num(_first(raw,'lower_interval','lower_band'));u=_num(_first(raw,'upper_interval','upper_band'))
    return l,u,a

def _session(ts):
    h=int(ts.hour)
    return 'ASIAN' if h<7 else 'LONDON' if h<12 else 'LONDON_NEW_YORK_OVERLAP' if h<16 else 'NEW_YORK' if h<21 else 'OTHER'

def build_bundle(snapshot,state:MutableMapping[str,Any],*,days:int=25)->Field8Bundle:
    run_id=str(snapshot.run_id);generation_id=str(snapshot.generation_id or run_id);snapshot_hash=str(snapshot.source_snapshot_hash or f'SOURCE_HASH_UNAVAILABLE:{run_id}')
    cutoff=pd.Timestamp(snapshot.broker_candle_time);cutoff=cutoff.tz_localize('UTC') if cutoff.tzinfo is None else cutoff.tz_convert('UTC')
    frame=_source_frame(state);tc=_time_column(frame)
    if frame.empty or tc is None:return Field8Bundle(run_id,generation_id,snapshot_hash,'EURUSD','H1',[])
    work=frame.copy(deep=False);work['_t']=pd.to_datetime(work[tc],errors='coerce',utc=True)
    work=work.loc[work['_t'].notna() & (work['_t']<cutoff.floor('h')) & (work['_t']>=cutoff.floor('h')-pd.Timedelta(days=days))].sort_values('_t').drop_duplicates('_t',keep='last')
    preds=dict(snapshot.predictions);metrics=dict(snapshot.metrics);rows=[];alpha_history={h:[] for h in HORIZONS};beta=RecursiveBeta();dma=DMAState();coverage={h:[] for h in HORIZONS};loss_history=[]
    close_col=next((c for c in ('Close','close','origin_price','current_price') if c in work.columns),None)
    close_values=pd.to_numeric(work[close_col],errors='coerce').to_numpy() if close_col else np.array([])
    residual_history={h:[] for h in HORIZONS}
    for row_index,(_,series) in enumerate(work.iterrows()):
        raw=series.to_dict();t=pd.Timestamp(raw['_t']);origin=_num(_first(raw,'Close','origin_price','current_price'),_num(snapshot.current_price))
        ph={h:_num(_first(raw,f'predicted_price_h{h}',f'predicted_{h}h'),_num(_first(preds,f'h{h}',f'predicted_price_h{h}'))) for h in HORIZONS}
        expert_maps={}; base_points={}
        history_close=close_values[:row_index+1] if len(close_values) else np.array([origin])
        for h in HORIZONS:
            expert_maps[h]=independent_expert_forecasts(history_close,h)
            if pd.isna(ph[h]) and expert_maps[h]:
                weights=dma_weights(); ph[h]=sum(weights.get(k,0.0)*v for k,v in expert_maps[h].items())
            if pd.notna(ph[h]): base_points[h]=ph[h]
        if len(base_points)>=2:
            reconciled,pre_coherence,post_coherence=reconcile(base_points,origin)
            ph.update(reconciled)
        else: pre_coherence=post_coherence=np.nan
        actual={h:_num(_first(raw,f'actual_price_h{h}',f'actual_h{h}')) for h in HORIZONS}
        matured={h:pd.notna(actual[h]) and t+pd.Timedelta(hours=h)<=cutoff for h in HORIZONS}
        required=[h for h in HORIZONS if pd.notna(ph[h])]
        maturity='FULLY_SETTLED' if required and all(matured[h] for h in required) else 'PARTIALLY_SETTLED' if any(matured.values()) else 'PENDING'
        intervals={h:_origin_interval(raw,h) for h in HORIZONS}
        for h in HORIZONS:
            if (pd.isna(intervals[h][0]) or pd.isna(intervals[h][1])) and pd.notna(ph[h]):
                l,u,q,method=adaptive_interval(ph[h],residual_history[h],h)
                intervals[h]=(l,u,.1)
        scores={};dirs={};covered={}
        for h in HORIZONS:
            if matured[h] and pd.notna(origin) and pd.notna(ph[h]):
                err=(ph[h]-actual[h])/.0001;dirs[h]=float(np.sign(ph[h]-origin)==np.sign(actual[h]-origin));l,u,a=intervals[h]
                covered[h]=float(l<=actual[h]<=u) if pd.notna(l) and pd.notna(u) else np.nan
                if pd.notna(covered[h]):coverage[h].append(covered[h])
                scale=_num(_first(raw,f'forecast_std_h{h}',f'origin_forecast_scale_h{h}'))
                samples=_first(raw,f'predictive_samples_h{h}');qs=_first(raw,f'predictive_quantiles_h{h}');ql=_first(raw,f'quantile_levels_h{h}')
                c,method=crps(actual[h],ph[h],scale,samples,qs,ql)
                scores[h]={'err':err,'mae':abs(err),'crps':c,'crps_method':method,'interval_score':interval_score(actual[h],l,u,a)/.0001 if pd.notna(l) and pd.notna(u) else np.nan}
            else:scores[h]={'err':np.nan,'mae':np.nan,'crps':np.nan,'crps_method':'UNAVAILABLE','interval_score':np.nan};dirs[h]=np.nan;covered[h]=np.nan
        benchmark={h:_num(_first(raw,f'benchmark_price_h{h}',f'random_walk_price_h{h}'),origin) for h in HORIZONS}
        scale1=_num(_first(raw,'origin_forecast_scale_h1','forecast_std_h1'),abs(intervals[1][1]-intervals[1][0])/.0001/3.29 if pd.notna(intervals[1][0]) and pd.notna(intervals[1][1]) else 1.0)
        abd=alpha_metrics(origin,ph[1],benchmark[1],scale1,alpha_history[1]);
        if math.isfinite(abd['alpha']):alpha_history[1].append(abd['alpha'])
        factors={'volatility':_num(_first(raw,'volatility_factor','atr_normalized')),'regime':_num(_first(raw,'regime_probability'),_num(snapshot.regime_reliability)/100),'usd_factor':_num(_first(raw,'usd_factor')),'session':{'ASIAN':-1,'LONDON':.5,'LONDON_NEW_YORK_OVERLAP':1,'NEW_YORK':.5,'OTHER':0}[_session(t)],'liquidity':_num(_first(raw,'liquidity_factor','spread_factor')),'interval_width':abs(intervals[1][1]-intervals[1][0])/.0001 if pd.notna(intervals[1][0]) and pd.notna(intervals[1][1]) else np.nan}
        realized=10000*math.log(actual[1]/origin) if matured[1] and origin>0 and actual[1]>0 else np.nan;beta_out=beta.update(factors,realized,matured[1])
        if matured[1] and pd.notna(scores[1]['mae']):loss_history.append(scores[1]['mae'])
        cp=change_point_evidence(loss_history)
        abd_state=classify_state(abd['alpha_z'],abd['delta_alpha'],abd['delta_acceleration'],beta_out['beta_instability'],cp['change_point_probability'])
        duration=filardo_transition(_num(_first(raw,'regime_age'),_num(snapshot.regime_age)),abd['alpha_z'],abd['delta_alpha'],abd['delta_acceleration'],beta_out['beta_instability'],factors['volatility'],_session(t),factors['interval_width'],cp['change_point_probability'])
        candidates=_first(raw,'candidate_losses',default={});candidate_losses=candidates if isinstance(candidates,Mapping) else {}
        dma_out=dma.update(candidate_losses,any(matured.values()))
        model_weights=dma_out.get('weights',{});dyn_status=dma_out['initialization_status'];dyn_weight=max(model_weights.values()) if len(model_weights)>=2 else np.nan
        rel=_num(_first(raw,'production_reliability','Reliability'),_num(snapshot.reliability));regime_rel=_num(_first(raw,'regime_reliability'),_num(snapshot.regime_reliability));valid_dirs=[v for v in dirs.values() if pd.notna(v)];path_acc=float(np.mean(valid_dirs)*100) if valid_dirs else np.nan
        rolling_cov=float(np.mean(coverage[1][-50:])) if coverage[1] else np.nan;debt=max(0,.9-rolling_cov)*100 if pd.notna(rolling_cov) else np.nan
        legacy=np.nan if pd.isna(path_acc) else float(np.clip(.2*rel+.4*path_acc+.3*regime_rel+10,0,100));research=np.nan if pd.isna(legacy) else float(np.clip(legacy*(1-min(beta_out['beta_uncertainty']/20,.5))*(1-min(cp['change_point_probability'],.5))*(1-min((debt if pd.notna(debt) else 0)/100,.5)),0,100))
        decision=str(_first(raw,'production_decision','Decision',default=snapshot.decision)).upper();path_dir='WAIT' if pd.isna(ph[1]) else 'BUY' if ph[1]>origin else 'SELL' if ph[1]<origin else 'WAIT';regime=str(_first(raw,'regime','Current Regime',default=snapshot.regime));regime_dir='BUY' if 'BULL' in regime.upper() else 'SELL' if 'BEAR' in regime.upper() else 'WAIT'
        f12=decision==path_dir;f23=path_dir==regime_dir;allagree=f12 and f23;evidence='VALID' if any(matured.values()) else 'PENDING';reasons=[]
        if maturity!='FULLY_SETTLED':reasons.append('OUTCOME_NOT_FULLY_MATURED')
        if dyn_status!='VALID_DYNAMIC_WEIGHTS':reasons.append(dyn_status)
        if duration.get('duration_model_status')!='VALID_SHADOW':reasons.append('DURATION_INSUFFICIENT')
        regime_shadow=three_standard_regime(history_close,{'change_probability':cp['change_point_probability']})
        for horizon in HORIZONS:
            if pd.isna(ph[horizon]):
                continue
            horizon_maturity='FULLY_SETTLED' if matured[horizon] else 'PENDING'
            row={c:np.nan for c in TABLE_COLUMNS}
            row.update({'broker_candle_time':t.isoformat(),'forecast_origin_time':t.isoformat(),'target_time':(t+pd.Timedelta(hours=horizon)).isoformat(),'forecast_horizon':horizon,'model_id':'SHADOW_DMA_RECONCILED','formula_version':'SHADOW_ONLY_PROTECTED_UNCHANGED','run_id':run_id,'generation_id':generation_id,'snapshot_hash':snapshot_hash,'source_snapshot_hash':snapshot_hash,'symbol':'EURUSD','timeframe':'H1','maturity_status':horizon_maturity,'identity_status':'MATCHED','production_decision':decision,'less_risky_decision':str(_first(raw,'less_risky_decision','Less Risky Decision',default=snapshot.less_risky_decision)).upper(),'production_reliability':rel,'data_quality_score':_num(_first(raw,'data_quality_score','Data Quality'),_num(_first(metrics,'data_quality_score'))),'origin_price':origin,'regime':regime,'regime_reliability':regime_rel,'path_reliability':path_acc,'dynamic_model_weight':dyn_weight,'dynamic_model_status':dyn_status,'model_weights':json.dumps(dma_weights(),sort_keys=True),'weight_entropy':dma_out.get('weight_entropy'),'effective_model_count':dma_out.get('effective_model_count'),'dominant_model':dma_out.get('dominant_model'),'model_confidence_set_status':'INSUFFICIENT_EVIDENCE','validation_status':'VALID_MATURED' if matured[horizon] else 'PENDING','alpha_h':abd['alpha'],'alpha_z_h':abd['alpha_z'],'alpha_decay_h':abd['alpha_decay'],'delta_alpha_h':abd['delta_alpha'],'delta_acceleration_h':abd['delta_acceleration'],'alpha_beta_delta_state':abd_state,'rolling_coverage':float(np.mean(coverage[horizon][-50:])) if coverage[horizon] else np.nan,'conformal_coverage_debt':max(0,.9-float(np.mean(coverage[horizon][-50:])))*100 if coverage[horizon] else np.nan,'calibration_sample_count':len(coverage[horizon]),'legacy_integrated_trust_score':legacy,'research_integrated_trust_score':research,'integrated_trust_score':legacy,'evidence_status':'VALID' if matured[horizon] else 'PENDING','shadow_recommendation':'CONFIRM' if allagree and pd.notna(research) and research>=60 else 'DOWNGRADE_TO_WAIT' if matured[horizon] else 'INSUFFICIENT_DATA','field1_field2_agreement':f12,'field2_field3_agreement':f23,'all_fields_agreement':allagree,'structural_break_state':cp['change_state'],'reason_codes':'|'.join(reasons) if reasons else 'NONE','calculation_version':CALCULATION_VERSION})
            for h in HORIZONS:
                row[f'predicted_price_h{h}']=ph[h];row[f'actual_price_h{h}']=actual[h];row[f'error_pips_h{h}']=scores[h]['err'];row[f'direction_correct_h{h}']=dirs[h];row[f'origin_lower_h{h}']=intervals[h][0];row[f'origin_upper_h{h}']=intervals[h][1];row[f'origin_interval_alpha_h{h}']=intervals[h][2]
            l,u,a=intervals[horizon]
            row.update({'base_forecast':base_points.get(horizon,np.nan),'reconciled_forecast':ph[horizon],'pre_reconciliation_coherence_error':pre_coherence,'post_reconciliation_coherence_error':post_coherence,'horizon_disagreement':float(np.std(list(ph.values()))) if len(ph)>1 else 0.0,'combined_regime_probability':max(regime_shadow.get('combined_probabilities',{}).values()) if regime_shadow.get('combined_probabilities') else np.nan,'combined_transition_risk':regime_shadow.get('combined_transition_risk',np.nan),'three_standard_agreement':regime_shadow.get('three_standard_agreement',False),'lower_interval':l,'upper_interval':u,'interval_width':(u-l)/.0001 if pd.notna(l) and pd.notna(u) else np.nan,'interval_covered':covered[horizon],'interval_score':scores[horizon]['interval_score'],'mae':scores[horizon]['mae'],'crps':scores[horizon]['crps'],'crps_method':scores[horizon]['crps_method'],'change_point_probability':cp['change_point_probability'],'run_length_posterior_mean':cp['run_length_posterior_mean'],'run_length_posterior_mode':cp['run_length_posterior_mode'],'run_length_entropy':cp['run_length_entropy'],'change_state':cp['change_state']})
            row.update(beta_out);row.update(duration);row['transition_probability']=duration.get('transition_probability_h1',np.nan)
            rows.append(row)
            if matured[horizon] and pd.notna(ph[horizon]) and pd.notna(actual[horizon]): residual_history[horizon].append(actual[horizon]-ph[horizon])
    # One immutable origin record contains all independent horizon values.  The
    # calculation above temporarily creates horizon views so horizon-local
    # scores can be computed without leakage; publication collapses those
    # views back to the canonical one-row-per-origin contract.
    collapsed=[]
    by_origin={}
    for item in rows:
        by_origin.setdefault(item['broker_candle_time'], []).append(item)
    for _, group in by_origin.items():
        group=sorted(group, key=lambda x:int(x.get('forecast_horizon') or 99))
        base=dict(group[0])
        status_by_h={int(x.get('forecast_horizon')):x.get('maturity_status','PENDING') for x in group}
        required=[h for h in HORIZONS if pd.notna(base.get(f'predicted_price_h{h}'))]
        settled=[status_by_h.get(h)=='FULLY_SETTLED' for h in required]
        base['maturity_status']='FULLY_SETTLED' if settled and all(settled) else 'PARTIALLY_SETTLED' if any(settled) else 'PENDING'
        for h in HORIZONS:
            base[f'maturity_status_h{h}']=status_by_h.get(h,'PENDING') if h in required else 'NOT_REQUIRED'
        base['forecast_horizon']=0
        base['target_time']=max((x['target_time'] for x in group), default=base['forecast_origin_time'])
        base['validation_status']='VALID_MATURED' if base['maturity_status']=='FULLY_SETTLED' else base['maturity_status']
        base['evidence_status']='VALID' if base['maturity_status']!='PENDING' else 'PENDING'
        collapsed.append(base)
    collapsed.sort(key=lambda r:r['broker_candle_time'],reverse=True)
    bundle=Field8Bundle(run_id,generation_id,snapshot_hash,'EURUSD','H1',collapsed);bundle.validate_identity();return bundle
