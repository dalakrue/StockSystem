import pandas as pd
FILTER_COLUMNS={'horizon':'forecast_horizon','maturity':'maturity_status','regime':'regime','alpha_beta_delta_state':'alpha_beta_delta_state','evidence_status':'evidence_status','structural_break_state':'structural_break_state','validation_status':'validation_status'}
def prepare_table(df,query='',filters=None):
    if not isinstance(df,pd.DataFrame):return pd.DataFrame()
    out=df.copy(deep=False)
    if query:out=out.loc[out.astype(str).apply(lambda c:c.str.contains(query,case=False,na=False)).any(axis=1)]
    for key,value in (filters or {}).items():
        col=FILTER_COLUMNS.get(key,key)
        if value not in (None,'','ALL') and col in out.columns:out=out.loc[out[col].astype(str)==str(value)]
    return out
