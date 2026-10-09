"""Compatibility entry point; all old strategy formulas are replaced."""
import json
import re
import numpy as np
import pandas as pd
from core.monthly_strategy_columns import STRATEGY_COLUMNS
from core.monthly_runtime import ENGINE_VERSION as STRATEGY_ENGINE_VERSION, build_history
ENTRY_FILTER_RELAXATION=0.0
ENTRY_FILTER_MULTIPLIER=1.0
STRATEGY_ALIASES={}
DISABLED_STRATEGY_IDS=frozenset()
VOLUME_REQUIRED_IDS=frozenset()


def strategy_enabled(label,removed=()):
    return label in STRATEGY_COLUMNS and label not in set(removed)


def build_strategy_audit(source,higher_bias=None,middle_bias=None,timeframe='H1',*,backtest_fast=False,removed_strategy_ids=(),relaxation=None,policy=None):
    if source.empty:return pd.DataFrame()
    if relaxation not in (None,0,0.0):raise ValueError('Frozen equations cannot be relaxed or optimized')
    result=build_history(source,timeframe=timeframe,audit=not backtest_fast)
    if removed_strategy_ids: result.loc[:,[c for c in removed_strategy_ids if c in STRATEGY_COLUMNS]]=0
    result=recompute_family_evidence(result)
    # Return audit columns only to legacy callers that concatenate candle/regime data.
    keep=[c for c in result if c not in source or c in STRATEGY_COLUMNS]
    return result[keep].reset_index(drop=True)


def recompute_family_evidence(frame):
    out=frame.copy()
    if 'Strategy Engine' not in out or not out['Strategy Engine'].eq(STRATEGY_ENGINE_VERSION).all():
        # Never reinterpret numeric IDs from the old engine under the new mapping.
        out=out.drop(columns=[c for c in out if re.fullmatch(r'S\d+(?: .*|)',str(c))])
        out=pd.concat([out,pd.DataFrame(np.zeros((len(out),240),np.int8),index=out.index,columns=STRATEGY_COLUMNS)],axis=1)
        out['Strategy Decision']='None'
        out['entry_eligible']=False
        out['research_entry_eligible']=False
        out['Direction']='WAIT'
        for c in ('TP Price','SL Price','Suggested TP','Suggested SL','Suggested TP Price','Suggested SL Price','tp_price','sl_price'):
            if c in out:out[c]=np.nan
    missing=[c for c in STRATEGY_COLUMNS if c not in out]
    if missing: out=pd.concat([out,pd.DataFrame(np.zeros((len(out),len(missing)),np.int8),index=out.index,columns=missing)],axis=1)
    a=out[STRATEGY_COLUMNS].fillna(0).to_numpy(dtype=float)
    if not np.isin(a,[-1,0,1]).all() or (np.count_nonzero(a,axis=1)>1).any(): raise ValueError('Monthly columns must contain ±1/0 with at most one signal per row')
    counts=np.count_nonzero(a,axis=1).astype(np.int8)
    ids=[[STRATEGY_COLUMNS[int(i)]] if n else [] for i,n in zip(np.abs(a).argmax(axis=1),counts)] if len(out) else []
    out['active_strategy_ids']=[json.dumps(x,separators=(',',':')) for x in ids]
    out['active_strategy_family_ids']=out.active_strategy_ids
    out['unique_family_count']=counts
    out['Strategy Hit Count']=counts
    out['Best Strategy']=[x[0] if x else 'NONE' for x in ids]
    out['Best Strategy Score']=pd.to_numeric(out.get('ranking_score',pd.Series(0,index=out.index)),errors='coerce').fillna(0).where(counts!=0,0)
    return out
