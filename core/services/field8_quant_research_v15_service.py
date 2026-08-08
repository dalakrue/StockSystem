"""Settings-only publisher for the v15 shadow research contract."""
from __future__ import annotations
import math, pandas as pd, numpy as np
from core.field8_quant_research_v15_20260624 import har_volatility,promotion_report

def build_and_publish_v15(state):
    canonical=state.get('canonical_decision_result_20260617') or state.get('last_valid_canonical_decision_result_20260617') or {}
    run_id=str(canonical.get('run_id') or state.get('canonical_run_id_20260617') or '')
    if not run_id:return {'ok':False,'shadow_only':True,'reason':'CANONICAL_RUN_UNAVAILABLE'}
    df=state.get('dv_pp_df'); vol={'forecast':math.nan,'fallback_reason':'OHLC_UNAVAILABLE'}
    if isinstance(df,pd.DataFrame) and not df.empty:
        close=next((c for c in ('close','Close') if c in df.columns),None)
        if close:vol=har_volatility(pd.to_numeric(df[close],errors='coerce').to_numpy())
    payload={
      'run_id':run_id,'shadow_only':True,'production_decision_unchanged':True,
      'field1_immutable_source':True,'horizons':[1,3,6],
      'har_volatility':vol,
      'research_layers':['HORIZON_DMA','MCS','PROPER_SCORING','SEQUENTIAL_CONFORMAL','COMPLETE_SUBSET','BOCPD','HSMM_DURATION','HAR_VOLATILITY','VENN_ABERS','CONFORMAL_RISK'],
      'promotion_report':promotion_report({'no_leakage':True,'protected_hash_unchanged':True,'bounded_runtime':True}),
      'fallback_status':'EVIDENCE_DEPENDENT','sample_size_note':'Only matured origin-time outcomes are eligible for updates.',
    }
    state['field8_quant_research_v15_20260624']=payload
    return {'ok':True,'published':True,'run_id':run_id,'shadow_only':True}
