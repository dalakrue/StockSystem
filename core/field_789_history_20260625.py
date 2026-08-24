"""Read-only 25-day decision evidence adapters for Lunch Fields 7, 8 and 9."""
from __future__ import annotations
from typing import Any, Mapping
import pandas as pd


def _frames(state: Mapping[str, Any]):
    keys=(
        'home_reversal_25d_scan','prediction_history_df','prediction_vs_actual_history_df',
        'dv_pp_bt_hist','canonical_priority_table_20260617','regime_history_df',
        'full_metric_history_df','lunch_metric_history_df',
    )
    for key in keys:
        value=state.get(key)
        if isinstance(value,pd.DataFrame) and not value.empty:
            yield key,value


def _canonical_meta(state: Mapping[str, Any]) -> tuple[str,str]:
    for key in ('canonical_decision_result_20260617','last_valid_canonical_decision_result_20260617','adx_shared_calc_result_20260615'):
        value=state.get(key)
        if isinstance(value, Mapping) and value:
            return str(value.get('run_id') or value.get('canonical_calculation_id') or '-'), str(value.get('latest_completed_candle_time') or value.get('broker_candle_time') or '-')
    return '-','-'


def _time_col(df: pd.DataFrame):
    return next((c for c in df.columns if str(c).lower().replace('_',' ') in {'time','timestamp','date','broker time','event time utc','forecast origin time','created at','datetime'}),None)


def build_field_history(state: Mapping[str, Any], field: int, limit: int=600)->pd.DataFrame:
    chosen=None; source=''
    for key,frame in _frames(state):
        if chosen is None or len(frame)>len(chosen): chosen,source=frame,key
    if chosen is None:return pd.DataFrame()
    df=chosen.copy(deep=False)
    tcol=_time_col(df)
    if tcol:
        ts=pd.to_datetime(df[tcol],errors='coerce',utc=True)
        if ts.notna().any():
            df=df.loc[ts>=ts.max()-pd.Timedelta(days=25)].copy()
            df=df.assign(**{tcol:ts.loc[df.index]}).sort_values(tcol, ascending=False)
    wanted={
      7:[('Broker Time',('broker time','time','timestamp','event time utc','forecast origin time')),('Decision',('decision','direction')),('Data Quality',('quality','data quality')),('Drift Status',('drift',)),('Reliability',('reliability',)),('Error',('error',)),('Regime',('regime',)),('Evidence Source',('source',))],
      8:[('Broker Time',('broker time','time','timestamp','forecast origin time')),('Decision',('decision',)),('Prediction Accuracy',('accuracy',)),('Coverage',('coverage',)),('Combined Score',('score',)),('Priority',('priority',)),('Model',('model',)),('Agreement',('agreement',)),('Reliability',('reliability',)),('Regime',('regime',))],
      9:[('Broker Time',('broker time','time','timestamp','forecast origin time')),('Decision',('decision',)),('Expected Value',('expected','value')),('Regret',('regret',)),('Risk',('risk',)),('Stability',('stability',)),('Contribution',('contribution',)),('Reversal',('reversal',)),('Regime',('regime',))],
    }[field]
    out=pd.DataFrame()
    for label,tokens in wanted:
        col=next((c for c in df.columns if any(tok in str(c).lower() for tok in tokens)), None)
        if col is not None:
            out[label]=df[col]
    if out.empty:
        cols=list(df.columns[:12])
        out=df.loc[:, cols].copy()
    run_id, broker_time = _canonical_meta(state)
    out.insert(0,'Run ID',run_id)
    out.insert(1,'Latest Broker Candle',broker_time)
    out.insert(2,'Field',field)
    out.insert(3,'Source Table',source)
    return out.head(limit).reset_index(drop=True)
