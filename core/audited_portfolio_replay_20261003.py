"""Legacy backtest API delegates to frozen monthly execution only."""
from core.monthly_backtest import replay_portfolio as _replay,metrics
from core.monthly_runtime import raw_frame
SCENARIOS=('Frozen monthly equations',)


def normalize_quotes(frame):
    from core.execution_policy_20261003 import quote_metadata
    f=raw_frame(frame)
    return f.assign(open_time=f.Datetime,open=f.Open,high=f.High,low=f.Low,close=f.Close)


def replay_portfolio(signals,raw_quotes,*,scenario='Frozen monthly equations',tp_pips=None,sl_pips=None,policy=None,entry_start=None,entry_end=None,ambiguity='SL_FIRST',research=True,removed_symbols=()):
    # Old scenario/TP/SL overrides cannot mutate the frozen equations.
    raw=raw_frame(raw_quotes)
    if removed_symbols:raw=raw.loc[~raw.Symbol.isin(removed_symbols)]
    result=_replay(raw,entry_start=entry_start,entry_end=entry_end,strict_only=not research)
    result['skips']=result['checks']
    result['hourly_equity']=__import__('pandas').DataFrame()
    return result
