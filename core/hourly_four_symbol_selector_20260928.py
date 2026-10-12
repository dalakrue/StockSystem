"""Monthly equation opportunity ranking; holdings admission is a separate step."""
import numpy as np
import pandas as pd
from core.monthly_runtime import ENGINE_VERSION
from core.execution_policy_20261003 import get_policy, select_new_entries
SELECTOR_VERSION=ENGINE_VERSION
SELECTOR_MAX_SYMBOLS=4
MAX_HOLD_HOURS=24
ENTRY_FILTER_RELAXATION=0.0
ENTRY_FILTER_MULTIPLIER=1.0
LOW_FREQUENCY_COVERAGE_SYMBOLS=frozenset()


def price_string(value,symbol='',reference_price=None):
    try:return f'{float(value):.5f}' if np.isfinite(float(value)) else '—'
    except (ValueError,TypeError):return '—'


def add_dynamic_24h_targets(df,bias=None,*,timeframe='H1',symbol=None,**kwargs):
    # Legacy enrichment cannot recalculate or overwrite frozen monthly targets.
    from core.monthly_runtime import build_history
    return df.copy() if 'Equation ID' in df else build_history(df,symbol=symbol if isinstance(symbol,str) else None,timeframe=timeframe)


def middle_bias_exit_decision(position_side,current_middle_bias,*,position_age_hours=None,hold_hours=24):
    if position_age_hours is not None and float(position_age_hours)>=hold_hours:
        return dict(action='EXIT',reason='ELAPSED HOLD CAP',exit_method='TIME_EXIT',max_hold_hours=hold_hours)
    if (position_side,current_middle_bias) in (('BUY','SELL'),('SELL','BUY')):
        return dict(action='EXIT',reason='OPPOSITE COMPLETED RESEARCH BIAS',exit_method='MIDDLE_BIAS_EXIT',max_hold_hours=hold_hours)
    return dict(action='HOLD',reason='No opposite completed bias',exit_method='FROZEN_EQUATION',max_hold_hours=hold_hours)


def attach_hourly_four_selection(frame,*,timestamp_columns=('check_at','Datetime'),max_symbols=4,coverage_state=None,copy=True):
    from core.strategy_audit_20260924 import recompute_family_evidence
    out=recompute_family_evidence(frame.loc[:,~frame.columns.duplicated()].copy()).reset_index(drop=True)
    if out.empty:return out
    out['Hourly 4 Entry']=False # means top-four OPPORTUNITY, never an order
    out['Hourly Selection Rank']=pd.Series(pd.NA,index=out.index,dtype='Int64')
    out['Hourly Selected Count']=0
    out['Hourly Entry Origin']='NONE'
    out['Hourly Selection Score']=out.get('ranking_score',0)
    col=next((x for x in timestamp_columns if x in out),None)
    out['_check']=pd.to_datetime(out[col],utc=True,errors='coerce') if col else pd.NaT
    if 'Equation ID' not in out:out['Equation ID']=''
    if 'ranking_score' not in out:out['ranking_score']=0.
    if 'Improved Rank' not in out:
        # Improved strategy config: hour+symbol rank replaces Best Strategy Score sort.
        from core.improved_strategy_config import rank_score as _rank_score
        _hrs=out['_check'].dt.hour.fillna(-1).astype(int)
        out['Improved Rank']=[_rank_score(s,int(h),r) for s,h,r in zip(out['Symbol'],_hrs,out['ranking_score'])]
    ranked=out.loc[out['Strategy Hit Count'].eq(1)].sort_values(['_check','Improved Rank','Symbol','Equation ID'],ascending=[True,False,True,True],kind='mergesort')
    selected=ranked.groupby('_check',sort=False).head(min(4,max_symbols))
    for _,g in selected.groupby('_check',sort=False):
        out.loc[g.index,'Hourly 4 Entry']=True
        out.loc[g.index,'Hourly Selection Rank']=np.arange(1,len(g)+1)
        out.loc[g.index,'Hourly Selected Count']=len(g)
        out.loc[g.index,'Hourly Entry Origin']='MONTHLY_EQUATION'
    # Preserve raw equation decision text, even for opportunities below rank four.
    return out.drop(columns='_check').sort_values([col or 'Symbol','Hourly Selection Rank','Symbol'],na_position='last',kind='mergesort').reset_index(drop=True)


def select_portfolio_entries(candidates,held_symbols,*,policy=None,eligibility_column='entry_eligible'):
    return select_new_entries(candidates,held_symbols,policy=policy,eligibility_column=eligibility_column)
