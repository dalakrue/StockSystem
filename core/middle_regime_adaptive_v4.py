"""Causal, completed-candle Middle Regime Adaptive Strategy Engine v4.

Probabilities are bounded directional model scores, NOT calibrated win probabilities.
No broker orders are placed here. All prices use the symbol's quote-price units.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import hashlib
import json
from pathlib import Path

VERSION = 'middle-regime-adaptive-v4-20260926'
FAMILIES = ('Trend continuation', 'Mean reversion', 'Volatility breakout',
            'Regime transition', 'Liquidity/session')
PROFILE_PATH = Path(__file__).resolve().parents[1] / 'data' / 'adaptive_v4_validated_profile.json'


def validated_profile():
    """An absent profile uses neutral weights; an unapproved profile fails closed."""
    if not PROFILE_PATH.exists():
        return {'id': 'BASELINE', 'weights': {}, 'effective_from': None}
    raw = PROFILE_PATH.read_bytes()
    profile = json.loads(raw)
    if profile.get('engine') != VERSION or profile.get('approved') is not True or not profile.get('effective_from'):
        raise ValueError('Unapproved or incompatible v4 family profile')
    effective = pd.Timestamp(profile['effective_from'])
    effective = effective.tz_localize('UTC') if effective.tzinfo is None else effective.tz_convert('UTC')
    return {'id': hashlib.sha256(raw).hexdigest()[:16],
            'weights': profile.get('family_weights', {}), 'effective_from': effective}


def current_profile_id():
    return validated_profile()['id']


def pip_size(symbol):
    symbol = str(symbol or '').upper().replace('/', '')
    return 0.01 if symbol.endswith('JPY') else 0.0001


def _series(value, index):
    if isinstance(value, str):
        return pd.Series(value, index=index)
    return pd.Series(value).reset_index(drop=True).reindex(index)


def _clip(s, low=0, high=1):
    return s.clip(lower=low, upper=high).fillna(0)


def build_adaptive_audit(source, higher_bias, middle_bias, symbol='UNKNOWN', timeframe='H1'):
    """Vectorized prefix-invariant decisions; input is chronological closed OHLC.

    Caller must remove still-forming candles. Missing or invalid timestamps fail
    the session gate instead of being silently treated as liquid hours.
    """
    df = source.copy().reset_index(drop=True)
    if df.empty or not {'open','high','low','close'}.issubset(df):
        return pd.DataFrame()
    n = len(df); ix = df.index
    def num(name): return pd.to_numeric(df[name], errors='coerce')
    o,h,l,c = (num(k) for k in ('open','high','low','close'))
    stamp = pd.to_datetime(df['open_time'] if 'open_time' in df else pd.Series(pd.NaT,index=ix),utc=True,errors='coerce')
    if str(timeframe).upper() not in ('H1','1H'):
        # Family decisions are H1-specific; no inferred hourly decisions on H4/D1.
        stamp = pd.Series(pd.NaT,index=ix,dtype='datetime64[ns, UTC]')
    hour = stamp.dt.hour
    pair=str(symbol or '').upper().replace('/','')
    # Asia and Pacific crosses have a different liquid window from Europe/US.
    session_hours=(0,16) if pair.startswith(('AUD','NZD')) else ((0,20) if pair.endswith('JPY') else (6,20))
    session = hour.between(*session_hours) & stamp.dt.dayofweek.lt(5)
    prev = c.shift(1)
    tr = pd.concat([(h-l).abs(),(h-prev).abs(),(l-prev).abs()],axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    atr_base = atr.shift(1).rolling(72,min_periods=24).median()
    ratio = (atr/atr_base.replace(0,np.nan)).replace([np.inf,-np.inf],np.nan)
    ema20 = c.ewm(span=20,adjust=False,min_periods=20).mean()
    ema50 = c.ewm(span=50,adjust=False,min_periods=50).mean()
    slope = (ema20-ema50)/atr.replace(0,np.nan)
    mom = (c-c.shift(4))/atr.replace(0,np.nan)
    prior_hi = h.shift(1).rolling(24,min_periods=20).max()
    prior_lo = l.shift(1).rolling(24,min_periods=20).min()
    width = (prior_hi-prior_lo)/atr.replace(0,np.nan)
    body = ((c-o)/(h-l).replace(0,np.nan)).clip(-1,1)
    hb = _series(higher_bias,ix).astype(str).str.upper()
    mb = _series(middle_bias,ix).astype(str).str.upper()
    hb_sign = hb.map({'BUY':1,'SELL':-1}).fillna(0)
    mb_sign = mb.map({'BUY':1,'SELL':-1}).fillna(0)
    activity=(pd.to_numeric(df['volume'],errors='coerce') if 'volume' in df else tr).clip(lower=0)
    # Each UTC hour is compared only with its own PRIOR observations.
    hour_baseline=activity.groupby(hour).transform(lambda x:x.shift(1).rolling(12,min_periods=4).median())
    liquid=activity.ge(.5*hour_baseline).where(hour_baseline.notna(),True)
    session=session & liquid.fillna(False)
    closed=stamp+pd.Timedelta(hours=1)<=pd.Timestamp.now(tz='UTC')
    valid = closed & o.notna() & h.notna() & l.notna() & c.notna() & (h>=pd.concat([o,c,l],axis=1).max(axis=1)) & (l<=pd.concat([o,c,h],axis=1).min(axis=1)) & atr.gt(0) & ratio.notna() & stamp.notna()
    # Thresholds adapt only to PRIOR symbol data. This is a volatility model,
    # never a tuning table selected from future outcomes.
    history = ratio.shift(1).rolling(240,min_periods=72)
    quiet_limit = history.quantile(.30).fillna(.82).clip(.65,1.0)
    expansion_limit = history.quantile(.75).fillna(1.18).clip(1.05,1.65)
    momentum_limit = (mom.abs().shift(1).rolling(240,min_periods=72).quantile(.50)
                      .fillna(.6).clip(.4,1.5))
    unstable = ratio.gt(expansion_limit*1.4) | (tr/atr).gt(2.5)
    transition = (np.sign(slope).ne(np.sign(slope.shift(3))) & slope.abs().gt(.12)) | (hb_sign.ne(mb_sign) & hb_sign.ne(0) & mb_sign.ne(0))
    regime = pd.Series(np.select([transition,unstable,ratio.lt(quiet_limit),slope.abs().ge(.45) & width.gt(2.5)],
                                  ['TRANSITION','HIGH_VOLATILITY','LOW_VOLATILITY','TREND'],default='RANGE'),index=ix)
    regime = regime.where(valid,'NO_DATA')
    direction = pd.Series('NONE',index=ix)
    family = pd.Series('NONE',index=ix)
    quality = pd.Series(0.,index=ix)
    buy = pd.Series(0.,index=ix); sell = pd.Series(0.,index=ix)
    tp = pd.Series(np.nan,index=ix); sl = tp.copy(); tp_price=tp.copy(); sl_price=tp.copy()
    rr = tp.copy(); reach = tp.copy(); sl_hit=tp.copy(); hold=tp.copy()
    tp_conf=tp.copy(); sl_conf=tp.copy(); reason=pd.Series('Insufficient completed OHLC',index=ix)
    pip = pip_size(symbol)
    profile = validated_profile()
    # Independent candidate families; select the strongest eligible family.
    # All directional features are expressed through sign for strict symmetry.
    for sign,label in ((1,'BUY'),(-1,'SELL')):
        bias = mb_sign*sign
        align = hb_sign*sign
        directional = (18*bias + 16*align + 13*_clip(sign*slope/1.6) +
                       12*_clip(sign*mom/2) + 9*_clip(sign*body) +
                       8*_clip((ratio-quiet_limit)/(expansion_limit-quiet_limit).clip(lower=.1)) +
                       8*_clip(sign*(c-ema50)/atr/2) + 8*session.astype(float) +
                       8*_clip((sign*(c-prev))/atr))
        directional = directional.clip(0,100).where(valid,0)
        if sign==1: buy=directional
        else: sell=directional
        dist = (prior_hi-c) if sign==1 else (c-prior_lo)
        available = dist/atr.replace(0,np.nan)
        pullback = (sign*(c-ema20)).between(-.65*atr,.7*atr) & (sign*(c-prev)>0)
        continuation = (sign*(c-ema20)).between(.7*atr,3*atr) & (sign*mom>momentum_limit) & (sign*body>.08)
        breakout = sign*(c-(prior_hi if sign==1 else prior_lo))>0
        reversal = (sign*body>.35) & (available.gt(1.0)) & (sign*(c-ema20)<-.25*atr)
        compression_break = ratio.shift(1).lt(quiet_limit.shift(1)) & breakout & ratio.gt(ratio.shift(1))
        flip = transition & (sign*slope>.12) & (sign*body>.35)
        liquid = session & (sign*body>.5) & (sign*mom>momentum_limit) & (ratio.between(quiet_limit,expansion_limit*1.2))
        candidates = [
            (regime.eq('TREND') & align.eq(1) & (pullback | continuation), 'Trend continuation',8),
            (regime.eq('RANGE') & reversal & (sign*mb_sign>=0), 'Mean reversion',9),
            (regime.eq('LOW_VOLATILITY') & compression_break & align.eq(1), 'Volatility breakout',10),
            (regime.eq('TRANSITION') & flip & align.eq(1), 'Regime transition',6),
            (regime.eq('HIGH_VOLATILITY') & liquid & align.eq(1), 'Liquidity/session',5),
        ]
        for trigger,name,bonus in candidates:
            # A family must have its own trigger; legacy votes never create one.
            active = stamp.gt(profile['effective_from']) if profile['effective_from'] is not None else pd.Series(False,index=ix)
            adjustment = float(profile['weights'].get(str(symbol).upper(), {}).get(name, 0))
            adjustment = max(-5., min(5., adjustment))
            proposed=(directional+bonus+active.astype(float)*adjustment).clip(0,100)
            eligible=trigger & valid & session & (hb_sign*sign>=0) & (directional>=57) & (proposed>quality)
            direction=direction.mask(eligible,label); family=family.mask(eligible,name)
            quality=quality.mask(eligible,proposed)
    advantage=(buy-sell).abs()
    chosen_sign=direction.map({'BUY':1,'SELL':-1}).fillna(0)
    same=chosen_sign*mb_sign>=0
    # The confidence is an uncalibrated quality score, not outcome likelihood.
    confidence=(quality*.7+advantage*.3).clip(0,100)
    swing_dist=pd.Series(np.where(chosen_sign.gt(0),prior_hi-c,c-prior_lo),index=ix)
    short_low=l.shift(1).rolling(6,min_periods=5).min()
    short_high=h.shift(1).rolling(6,min_periods=5).max()
    stop_structure=pd.Series(np.where(chosen_sign.gt(0),c-short_low,short_high-c),index=ix)
    extended=(family.eq('Trend continuation') | family.eq('Volatility breakout')) & swing_dist.le(.45*atr)
    swing_dist=swing_dist.where(~extended,2.2*atr)
    # Structural target caps near obstacles; structure invalidation and ATR protect the SL.
    # Lagged symbol behavior, volatility regime and structure set actual prices.
    typical_range=(tr.shift(1).rolling(240,min_periods=72).quantile(.8)/atr).clip(1.7,2.4).fillna(1.9)
    regime_scale=regime.map({'HIGH_VOLATILITY':.92,'LOW_VOLATILITY':1.05,'TRANSITION':.95}).fillna(1.)
    target_dist=pd.concat([typical_range*regime_scale*atr,(swing_dist-.12*atr).clip(lower=0)],axis=1).min(axis=1)
    noise_floor=tr.shift(1).rolling(72,min_periods=24).median().fillna(atr)
    stop_dist=pd.concat([1.15*atr,1.05*noise_floor,stop_structure+.12*atr],axis=1).max(axis=1)
    # Maximum risk rejects the setup, rather than placing an unsafe closer stop.
    max_risk=2.5*atr
    reward_risk=target_dist/stop_dist.replace(0,np.nan)
    p_tp=(confidence/100*.48 + _clip(reward_risk/3)*.3 + .08).clip(.05,.85)
    p_sl=1-p_tp
    acceptable=(direction.ne('NONE') & same & advantage.ge(12) & swing_dist.gt(1.35*atr)
                & stop_dist.le(max_risk) & reward_risk.ge(1.15)
                & (p_tp*reward_risk-p_sl).ge(.05) & session)
    reason=reason.mask(valid,'No family trigger or direction edge')
    reason=reason.mask(direction.ne('NONE') & ~acceptable,'Risk/structure/direction filter')
    reason=reason.mask(acceptable,'Accepted')
    direction=direction.where(acceptable,'NONE');family=family.where(acceptable,'NONE')
    tp=(target_dist/pip).round(1).where(acceptable)
    sl=(stop_dist/pip).round(1).where(acceptable)
    tp_price=(c+chosen_sign*target_dist).where(acceptable).round(5 if pip==.0001 else 3)
    sl_price=(c-chosen_sign*stop_dist).where(acceptable).round(5 if pip==.0001 else 3)
    rr=reward_risk.where(acceptable).round(2)
    reach=(p_tp*100).where(acceptable).round(1);sl_hit=(p_sl*100).where(acceptable).round(1)
    tp_conf=(confidence*.7+25).clip(0,100).where(acceptable).round(1)
    sl_conf=(confidence*.6+35).clip(0,100).where(acceptable).round(1)
    hold=(target_dist/atr.replace(0,np.nan)*6).clip(3,24).where(acceptable).round(1)
    decision=pd.Series(np.where(acceptable,direction+' '+family+' TP'+tp.astype(str)+' SL'+sl.astype(str),'None'),index=ix)
    return pd.DataFrame({'Market Regime':regime,'BUY Probability %':buy.round(1),'SELL Probability %':sell.round(1),
        'Confidence Score':confidence.round(1),'Strategy Family':family,'V4 Direction':direction,
        'Trade Quality Score':quality.where(acceptable,0).round(1),'Expected Reward Risk':rr,
        'Expected TP Reach %':reach,'Expected SL Hit %':sl_hit,'Suggested TP':tp,'Suggested SL':sl,
        'Suggested TP Price':tp_price,'Suggested SL Price':sl_price,'TP Confidence %':tp_conf,
        'SL Confidence %':sl_conf,'Expected Holding Hours':hold,'Expected TP Before SL %':reach,
        'Entry Session Valid':session.fillna(False),'Symbol ATR Threshold':expansion_limit.round(3),
        'Symbol Momentum Threshold':momentum_limit.round(3),'Adaptive Decision':decision,'Adaptive Reject Reason':reason,
        'Strategy Engine':VERSION,'Strategy Profile':profile['id']},index=ix)


def manage_trade(direction, entry, initial_stop, target, high, low, close, bars_held,
                 atr, bias='NEUTRAL', best_price=None, partial_done=False):
    """Protective stop evaluated first; caller supplies each *completed* bar.

    Conservative tie rule: when TP and SL are both inside a bar, SL wins.
    No old hourly cap applies to protective exits. Returns updated state.
    """
    sign={'BUY':1,'SELL':-1}.get(str(direction).upper())
    if sign is None: raise ValueError('direction must be BUY or SELL')
    if not (np.isfinite([entry,initial_stop,target,high,low,close,atr]).all() and atr>0):
        raise ValueError('finite prices and positive ATR required')
    extreme = high if sign==1 else low
    best = extreme if best_price is None else (max(best_price,extreme) if sign==1 else min(best_price,extreme))
    favorable=sign*(best-entry)
    stop=initial_stop
    hit_stop=low<=stop if sign==1 else high>=stop
    hit_target=high>=target if sign==1 else low<=target
    if hit_stop: exit_reason='PROTECTIVE_SL'; exit_price=stop
    elif hit_target: exit_reason='TP'; exit_price=target
    elif bias in ('BUY','SELL') and bias!=direction: exit_reason='BIAS_CHANGE';exit_price=close
    elif bars_held>=24 and sign*(close-entry)<.5*atr: exit_reason='TIME_DECAY';exit_price=close
    else: exit_reason=None;exit_price=None
    # A move earned within this bar only protects the NEXT bar.
    if exit_reason is None and favorable>=atr: stop=max(stop,entry+.05*atr) if sign==1 else min(stop,entry-.05*atr)
    if exit_reason is None and favorable>=1.5*atr: stop=max(stop,entry+.55*atr) if sign==1 else min(stop,entry-.55*atr)
    partial=bool(exit_reason is None and not partial_done and sign*(close-entry)>=1.5*atr)
    return {'stop':stop,'best_price':best,'exit_reason':exit_reason,'exit_price':exit_price,
            'partial_close_fraction':0.5 if partial else 0.,
            'partial_protection':favorable>=1.5*atr}
