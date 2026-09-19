from __future__ import annotations
import hashlib, json, math, time, tracemalloc
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping
from core.quant_research_v14_contract_20260623 import base, METHODS

def _d(x):
    if is_dataclass(x): return asdict(x)
    if isinstance(x, Mapping): return dict(x)
    return {k:getattr(x,k) for k in dir(x) if not k.startswith('_') and isinstance(getattr(x,k,None),(str,int,float,bool,list,dict,type(None)))}
def _series(settled,key): return [r.get(key) for r in settled if isinstance(r,Mapping) and r.get(key) is not None]
def evaluate_v14(snapshot, settled, state=None):
    from core.quant_research_v14_student_t import evaluate as student
    from core.quant_research_v14_mixture_experts import evaluate as moe
    from core.quant_research_v14_venn_abers import evaluate as va
    from core.quant_research_v14_caviar import evaluate as caviar
    from core.quant_research_v14_conformal_risk import evaluate as conformal
    from core.quant_research_v14_wasserstein import evaluate as wass
    from core.quant_research_v14_copula import evaluate as copula
    from core.quant_research_v14_knockoffs import evaluate as knock
    from core.quant_research_v14_scoring import evaluate as scoring
    from core.quant_research_v14_causal_news import evaluate as news
    started=time.perf_counter(); tracemalloc.start(); state=state or {}; s=_d(snapshot); rows=[r for r in settled if isinstance(r,Mapping)][-2000:]
    identity={k:s.get(k) for k in ('run_id','generation_id','calculation_id','symbol','timeframe','snapshot_hash','broker_candle_time')}
    rets=_series(rows,'return') or _series(rows,'actual_return') or _series(rows,'pnl_return')
    probs=_series(rows,'probability') or _series(rows,'confidence')
    labels=_series(rows,'label') or _series(rows,'direction_correct')
    if probs and max(probs)>1: probs=[p/100 for p in probs]
    experts={k:v for k,v in {'production':s.get('confidence'),'trend':s.get('trend_score'),'regime':s.get('regime_reliability'),'priority':s.get('priority_score')}.items() if isinstance(v,(int,float))}
    scenarios=[{'return':r.get('return',r.get('actual_return',0)) or 0,'cost':r.get('transaction_cost',0) or 0} for r in rows]
    features={k:_series(rows,k) for k in ('confidence','atr','volatility','spread','regime_age','data_quality') if _series(rows,k)}
    events=state.get('nlp_news_history_25d') or state.get('news_events') or []
    calls={
      'student_t_state':lambda:student(rets),'mixture_of_experts':lambda:moe(experts,rows),'venn_abers_calibration':lambda:va(probs,labels),
      'caviar_tail_risk':lambda:caviar(rets),'conformal_risk_control':lambda:conformal([0 if bool(x) else 1 for x in labels]),
      'wasserstein_robust_decision':lambda:wass(scenarios),'asymmetric_copula':lambda:copula(rets[:-1],rets[1:]),
      'knockoff_selection':lambda:knock(features,labels),'proper_scoring':lambda:scoring(probs,labels),'causal_news_impact':lambda:news(events,rets)}
    out=base(identity); perf={}
    for name,fn in calls.items():
      t=time.perf_counter()
      try: out[name]=fn()
      except Exception as e: out[name]={'status':'FAILED_SAFELY','available':False,'error':f'{type(e).__name__}: {e}','shadow_only':True,'production_influence_enabled':False}
      perf[name]={'wall_time_seconds':round(time.perf_counter()-t,6),'row_count':len(rows),'serialized_bytes':len(json.dumps(out[name],default=str))}
    current,peak=tracemalloc.get_traced_memory(); tracemalloc.stop(); available=sum(bool((out.get(m) or {}).get('available')) for m in METHODS)
    out['readiness']={'available_methods':available,'total_methods':10,'matured_outcome_count':len(rows),'oos_score_improvement':(out['proper_scoring'].get('status') if isinstance(out['proper_scoring'],dict) else 'INSUFFICIENT_DATA'),'calibration_status':(out['venn_abers_calibration'].get('status') if isinstance(out['venn_abers_calibration'],dict) else 'INSUFFICIENT_DATA'),'production_changed':'NO','promotion_ready':False}
    out['limitations']=['Shadow-only evidence','No automatic promotion','Missing samples return INSUFFICIENT_DATA','Causal news defaults to ASSOCIATIONAL_ONLY without valid controls']
    out['performance']={'methods':perf,'total_wall_time_seconds':round(time.perf_counter()-started,6),'peak_memory_bytes_approx':peak,'serialized_result_size':len(json.dumps(out,default=str))}
    out['snapshot_hash']=hashlib.sha256(json.dumps(out,default=str,sort_keys=True).encode()).hexdigest()
    return out
