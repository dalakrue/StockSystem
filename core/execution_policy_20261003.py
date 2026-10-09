"""Explicit candle ownership, conservative FX sessions and independent order state."""
from __future__ import annotations
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import numpy as np
import pandas as pd

VERSION = 'monthly-equation-240-execution-v1'

@dataclass(frozen=True)
class AuditPolicy:
    entry_timezone: str = 'UTC'
    check_hours: tuple = (6, 7, 10, 11, 12, 13)
    skip_entry_weekdays: tuple = (5, 6)
    max_new_symbols: int = 4
    display_slots: int = 4
    max_hold_hours: int = 48
    relaxation: float = 0.0
    spread_pips: float = 1.0
    slippage_pips: float = 0.0  # validated cost model: 1 pip spread, no slippage
    commission_pips: float = 0.0
    financing_pips_per_day: float = 0.0
    max_stop_pips: float = 103.0  # research budget, not an optimized recommendation
    max_stop_atr: float = 2.9
    min_tp_pips: float = 5.0
    max_tp_pips: float = 500.0
    min_net_reward_risk: float = 0.5
    max_spread_atr: float = 0.25
    max_spike_atr: float = 3.0
    max_gap_atr: float = 1.0
    min_samples: int = 40
    min_tp_probability_24h: float = 0.25
    min_ev_pips: float = 0.0
    min_ev_lower_bound: float = 0.0
    max_signal_age_minutes: int = 90
    flatten_before_closure: bool = True
    allow_rank_fill_orders: bool = False
    validation_manifest: str = ''

    def __post_init__(self):
        ZoneInfo(self.entry_timezone)
        if self.relaxation not in (0.0, 0.1, 0.2, 0.4):
            raise ValueError('Relaxation must be one of 0, .10, .20, .40; select in training only')
        if not 1 <= self.max_hold_hours <= 48 or not 0 <= self.max_new_symbols <= 4:
            raise ValueError('Authorized policy: hold <=48 elapsed hours and <=4 new symbols per check')
        if len(self.check_hours) != 6 or any(not 0 <= x <= 23 for x in self.check_hours):
            raise ValueError('Configure six distinct check hours')
        if len(set(self.check_hours)) != 6 or any(x not in range(7) for x in self.skip_entry_weekdays):
            raise ValueError('Invalid schedule')
        if min(self.spread_pips,self.slippage_pips,self.commission_pips,self.financing_pips_per_day) < 0:
            raise ValueError('Trading costs cannot be negative')
        if self.max_stop_pips <= 0 or self.max_stop_atr <= 0 or self.min_samples < 2:
            raise ValueError('Invalid stop budget/sample floor')

    @property
    def costs(self):
        return self.spread_pips+self.slippage_pips+self.commission_pips+self.financing_pips_per_day


def get_policy(overrides=None):
    raw = {}
    path = Path(__file__).resolve().parents[1] / 'config' / 'audited_execution.json'
    if path.exists():
        raw = json.loads(path.read_text())
    raw.update(overrides or {})
    accepted = {f.name for f in fields(AuditPolicy)}
    if set(raw)-accepted:
        raise ValueError('Unknown policy fields: '+', '.join(sorted(set(raw)-accepted)))
    return AuditPolicy(**raw)


def timeframe_delta(timeframe='H1'):
    t = str(timeframe).upper()
    if t.startswith('H'): return pd.Timedelta(hours=float(t[1:]))
    if t.startswith('M'): return pd.Timedelta(minutes=float(t[1:]))
    if t == 'D1': return pd.Timedelta(days=1)
    raise ValueError('Unknown candle interval: '+t)


def truthy(value):
    return value.astype(str).str.strip().str.lower().isin({'true','1','1.0','yes'})


def fx_session_open(times):
    """NY Sunday 17:00 to Friday 17:00 proxy, DST aware. Not broker verification."""
    s = pd.Series(pd.to_datetime(times, utc=True, format='mixed'))
    local = s.dt.tz_convert('America/New_York')
    day = local.dt.dayofweek
    minutes = local.dt.hour*60+local.dt.minute
    return s.notna() & ((day.between(0,3)) | ((day==4)&(minutes<1020)) | ((day==6)&(minutes>=1020)))


def quote_metadata(frame, timeframe='H1'):
    out = frame.copy()
    col = next((c for c in ('bar_open_time','open_time','Datetime','time','datetime') if c in out), None)
    times = pd.to_datetime(out[col], errors='coerce', utc=True, format='mixed') if col else pd.Series(pd.NaT,index=out.index,dtype='datetime64[ns, UTC]')
    close_times = times + timeframe_delta(timeframe)
    prices = pd.DataFrame({k:pd.to_numeric(out.get(k,pd.Series(np.nan,index=out.index)),errors='coerce') for k in ('open','high','low','close')})
    valid = np.isfinite(prices).all(axis=1) & prices.gt(0).all(axis=1)
    valid &= prices.high.ge(prices[['open','low','close']].max(axis=1)) & prices.low.le(prices[['open','high','close']].min(axis=1))
    duplicate = times.duplicated(keep=False) & times.notna()
    session = fx_session_open(times).set_axis(out.index)
    executable = valid & times.notna() & ~duplicate & session
    # Explicit false rows can never be upgraded by a calendar proxy.
    explicit = out.get('market_executable')
    if explicit is not None: executable &= truthy(explicit)
    verified = truthy(out.get('broker_quote_verified',pd.Series(False,index=out.index)))
    if 'broker_session_open' in out:
        executable &= truthy(out['broker_session_open'])
    quality = np.select([times.isna(),duplicate,~valid,~session,~executable,~verified],
        ['MISSING_TIMESTAMP','DUPLICATE_TIMESTAMP','INVALID_OHLC','BROKER_CLOSED_PROXY','EXPLICIT_NON_EXECUTABLE','UNVERIFIED_BROKER_QUOTES'], default='OK')
    availability = close_times
    for name in ('bar_close_time','signal_available_at'):
        if name in out:
            supplied = pd.to_datetime(out[name],errors='coerce',utc=True,format='mixed')
            availability = availability.where(supplied.notna() & availability.ge(supplied),supplied)
    return pd.DataFrame({'bar_open_time':times,'bar_close_time':close_times,'signal_available_at':availability,
        'market_executable':executable,'broker_quote_verified':verified,'data_quality_flag':quality,
        'quote_timezone':'UTC','timestamp_owner':'BAR_OPEN'},index=out.index)


def checks_between(start,end,policy=None):
    p = policy or get_policy()
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    lo = lo.tz_localize('UTC') if lo.tzinfo is None else lo.tz_convert('UTC')
    hi = hi.tz_localize('UTC') if hi.tzinfo is None else hi.tz_convert('UTC')
    dates = pd.date_range(lo.tz_convert(p.entry_timezone).normalize(),hi.tz_convert(p.entry_timezone).normalize(),freq='D')
    # Checks run at half past the hour; the replay fill is the next H1 open.
    return pd.DatetimeIndex(sorted(t.tz_convert('UTC') for d in dates for h in p.check_hours
        if d.dayofweek not in p.skip_entry_weekdays for t in [d+pd.Timedelta(hours=h,minutes=30)] if lo <= t.tz_convert('UTC') <= hi))


def latest_completed(frame,check_time,policy=None):
    p=policy or get_policy()
    ts=pd.Timestamp(check_time)
    ts=ts.tz_localize('UTC') if ts.tzinfo is None else ts.tz_convert('UTC')
    col='signal_available_at' if 'signal_available_at' in frame else 'bar_close_time'
    available=pd.to_datetime(frame[col],errors='coerce',utc=True,format='mixed')
    valid=frame.loc[available.le(ts)].copy()
    if valid.empty: return valid
    valid['_at']=available.loc[valid.index]
    valid=valid.sort_values(['_at','Symbol'],kind='mergesort').drop_duplicates('Symbol',keep='last')
    valid['signal_age_minutes']=(ts-valid['_at']).dt.total_seconds()/60
    valid.loc[valid.signal_age_minutes.gt(p.max_signal_age_minutes),'entry_eligible']=False
    if 'research_entry_eligible' in valid:
        valid.loc[valid.signal_age_minutes.gt(p.max_signal_age_minutes),'research_entry_eligible']=False
    return valid.drop(columns='_at')


def closure_deadline(entry_time,max_hold_hours=24):
    t=pd.Timestamp(entry_time).tz_convert('UTC')
    deadline=t+pd.Timedelta(hours=max_hold_hours)
    local=t.tz_convert('America/New_York')
    days=(4-local.dayofweek)%7
    friday=local.normalize()+pd.DateOffset(days=days)+pd.Timedelta(hours=17)
    if friday <= local: friday+=pd.DateOffset(days=7)
    closure=friday.tz_convert('UTC')
    return min(deadline,closure), closure <= deadline


def select_new_entries(candidates,held_symbols,*,policy=None,eligibility_column='entry_eligible'):
    """Rank TRIGGERED symbols by improved hour+symbol rank; walk the ranked
    list and admit up to max_new_symbols per check; never hold two positions
    in the same symbol."""
    from core.monthly_runtime import ENGINE_VERSION
    p=policy or get_policy()
    held={str(s).upper() for s in held_symbols}
    rank=candidates.copy()
    if 'Strategy Engine' not in rank or not rank['Strategy Engine'].eq(ENGINE_VERSION).all():
        return rank.iloc[:0],pd.DataFrame([{'reason':'STALE_STRATEGY_CACHE'}])
    hit=pd.to_numeric(rank.get('Strategy Hit Count',pd.Series(0,index=rank.index)),errors='coerce').eq(1)
    rank=rank.loc[hit].copy()
    if 'ranking_score' not in rank:rank['ranking_score']=0.
    if 'Equation ID' not in rank:rank['Equation ID']=''
    if 'Improved Rank' not in rank:
        from core.improved_strategy_config import rank_score as _rs
        _ck=rank.get('check_at')
        hrs=(pd.to_datetime(_ck,utc=True,errors='coerce').dt.hour.fillna(-1).astype(int)
             if _ck is not None else pd.Series(-1,index=rank.index))
        base=pd.to_numeric(rank.get('ranking_score',pd.Series(0,index=rank.index)),errors='coerce').fillna(0)
        rank['Improved Rank']=[_rs(s,int(h),r) for s,h,r in zip(rank['Symbol'].astype(str),hrs,base)]
    rank=rank.sort_values(['Improved Rank','Symbol','Equation ID'],ascending=[False,True,True],kind='mergesort').drop_duplicates('Symbol')
    selected=[];skipped=[]
    for position,(idx,row) in enumerate(rank.iterrows(),1):
        sym=str(row.Symbol).upper()
        reason=''
        if len(held)>=20:reason='MAX_20_HOLDINGS'
        elif sym in held:reason='ALREADY_HELD'
        elif not bool(row.get(eligibility_column,False)):reason='STRICT_VALID_NO' if eligibility_column=='entry_eligible' else 'NO_SIGNAL'
        elif len(selected)>=p.max_new_symbols:reason='MAX_NEW_ENTRIES_PER_CHECK'
        if reason:skipped.append(dict(Symbol=sym,candidate_rank=position,reason=reason))
        else:selected.append(idx)
    return rank.loc[selected],pd.DataFrame(skipped,columns=['Symbol','candidate_rank','reason'])

