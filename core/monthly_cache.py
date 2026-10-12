"""Invalidate obsolete strategy projections while retaining raw candle stores."""
import re
import pandas as pd
from core.monthly_runtime import ENGINE_VERSION


def invalidate_strategy_state(state):
    if state.get('monthly_cache_engine')==ENGINE_VERSION:return
    for key in list(state):
        value=state[key]
        if key=='field3_live_audit_cache_20260924' or 'middle_history_backfill_signature' in key:
            state.pop(key,None);continue
        if isinstance(value,pd.DataFrame) and any(re.fullmatch(r'S\d+(?: .*|)',str(c)) for c in value):
            if 'Strategy Engine' not in value or not value['Strategy Engine'].eq(ENGINE_VERSION).all():
                out=value.drop(columns=[c for c in value if re.fullmatch(r'S\d+(?: .*|)',str(c))],errors='ignore').copy()
                for c in ('Strategy Decision','Best Strategy','entry_side'):out[c]='None'
                for c in ('Strategy Hit Count','unique_family_count'):out[c]=0
                for c in ('entry_eligible','research_entry_eligible','Hourly 4 Entry'):out[c]=False
                out['Direction']='WAIT'
                for c in ('TP Price','SL Price','Suggested TP','Suggested SL','Suggested TP Price','Suggested SL Price','tp_price','sl_price'):
                    if c in out:out[c]=float('nan')
                out['Strategy Engine']='STALE; REBUILD MONTHLY EQUATIONS'
                state[key]=out
    state['monthly_cache_engine']=ENGINE_VERSION
