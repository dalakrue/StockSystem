"""Shared causal pullback strategy audit and quality gates for S1–S110."""
from __future__ import annotations
import numpy as np
import pandas as pd

from core.middle_regime_adaptive_v4 import VERSION as STRATEGY_ENGINE_VERSION, build_adaptive_audit


def _bias_series(value, index):
    if isinstance(value, str):
        return pd.Series(value, index=index)
    return pd.Series(value).reindex(index)


def _rsi_series(close, period):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    result = 100 - 100/(1 + gain/loss.replace(0, np.nan))
    return result.mask(loss.eq(0) & gain.gt(0), 100).mask(gain.eq(0) & loss.gt(0), 0).fillna(50)


def _causal_regime_filter(close):
    """Two-state HMM forward filter with scale estimated from prior bars only.

    Replaces per-row full-window EM refits. No backward smoothing or future-fit
    parameters are used. This is a model state score, not a trade probability.
    """
    returns = np.log(close.where(close.gt(0))).diff()
    scale = returns.shift(1).rolling(160, min_periods=30).std().clip(lower=1e-8)
    z = (returns/scale).replace([np.inf, -np.inf], np.nan).to_numpy()
    calm = np.zeros(len(close)); stress = np.ones(len(close)); transition = np.ones(len(close))
    p = np.array([.65, .35])
    for i, value in enumerate(z):
        if not np.isfinite(value):
            continue
        prior = np.array([.92*p[0]+.18*p[1], .08*p[0]+.82*p[1]])
        logp = np.log(np.maximum(prior, 1e-12)) - np.log([.8, 2.0]) - .5*(value/np.array([.8,2.0]))**2
        prob = np.exp(logp-logp.max())
        p = prob/prob.sum()
        calm[i], stress[i] = p
        transition[i] = .08*p[0]+.18*p[1]
    return pd.Series(calm,index=close.index),pd.Series(stress,index=close.index),pd.Series(transition,index=close.index)


def build_strategy_audit(source: pd.DataFrame, higher_bias, middle_bias, *, symbol='UNKNOWN', timeframe='H1') -> pd.DataFrame:
    """One causal S1–S110 calculation for live ranking and historical replay.

    Input must be chronological, completed candles; no future candle is read.
    Scores are rule scores, not calibrated probabilities of winning a trade.
    """
    df = source.copy().reset_index(drop=True)
    if df.empty or not {"open", "high", "low", "close"}.issubset(df.columns):
        return pd.DataFrame()
    close = pd.to_numeric(df["close"], errors="coerce")
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    op = pd.to_numeric(df["open"], errors="coerce")
    volume_col = next((c for c in ("volume", "tick_volume", "real_volume") if c in df.columns), None)
    activity = pd.to_numeric(df[volume_col], errors="coerce") if volume_col else (high-low).abs()
    activity = activity.replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(lower=0.0)

    hbias = _bias_series(higher_bias, df.index).astype(str).str.upper().str.strip()
    mbias = _bias_series(middle_bias, df.index).astype(str).str.upper().str.strip()
    valid_dir = hbias.isin(["BUY", "SELL"]) & hbias.eq(mbias)
    sign = pd.Series(np.where(hbias.eq("BUY"), 1.0, np.where(hbias.eq("SELL"), -1.0, 0.0)), index=df.index)

    prev_close = close.shift(1)
    tr = pd.concat(((high-low).abs(), (high-prev_close).abs(), (low-prev_close).abs()), axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean().replace(0, np.nan)
    ema20 = close.ewm(span=20, adjust=False, min_periods=7).mean()
    ema50 = close.ewm(span=50, adjust=False, min_periods=17).mean()
    body_dir = sign*(close-op) > 0
    near_ema = (close-ema20).abs().where(valid_dir).le(1.5*atr) | (close-ema50).abs().where(valid_dir).le(1.5*atr)
    trend_ok = sign*(ema20-ema50) >= 0
    structure = ((close >= ema50) & hbias.eq("BUY")) | ((close <= ema50) & hbias.eq("SELL"))
    depth = (close-ema50).abs()/atr
    # S1-S92 entry quality is intentionally relaxed by exactly 30% on the
    # shared admissibility thresholds. The direction-alignment and trend
    # structure safeguards remain mandatory; only the tolerances that were
    # suppressing otherwise usable entries are widened.
    LEGACY_ENTRY_RELAXATION = 0.30
    _relax = 1.0 - LEGACY_ENTRY_RELAXATION
    range_ok = (high-low) <= 2.0*atr
    relaxed_range_ok = (high-low) <= (2.0/_relax)*atr
    relaxed_hard = valid_dir & atr.gt(0) & relaxed_range_ok & depth.le(2.0/_relax) & trend_ok & structure
    hard = relaxed_hard

    change = close.diff()
    rsi = _rsi_series(close, 14)
    rsi2 = _rsi_series(close, 2)

    atr_mean = atr.rolling(20, min_periods=10).mean()
    atr_ratio = atr/atr_mean.replace(0, np.nan)
    bb_mid = close.rolling(20, min_periods=10).mean()
    bb_std = close.rolling(20, min_periods=10).std(ddof=1)
    bb_width = 4*bb_std/bb_mid.abs().replace(0,np.nan)
    bb_width_mean = bb_width.rolling(20, min_periods=10).mean()
    compression = atr_ratio.lt(1.0) & bb_width.div(bb_width_mean.replace(0,np.nan)).lt(1.0)
    recovery = (sign*change).gt(0)

    recent_rsi_min = rsi.rolling(5, min_periods=5).min().shift(1)
    recent_rsi_max = rsi.rolling(5, min_periods=5).max().shift(1)
    rsi_reset = np.where(hbias.eq("BUY"), (recent_rsi_min<45) & rsi.gt(rsi.shift(1)) & rsi.ge(50), np.where(hbias.eq("SELL"), (recent_rsi_max>55) & rsi.lt(rsi.shift(1)) & rsi.le(50), False))

    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    hist = macd - macd.ewm(span=9, adjust=False).mean()
    macd_reset = np.where(hbias.eq("BUY"), hist.rolling(5, min_periods=5).min().shift(1)<0, np.where(hbias.eq("SELL"), hist.rolling(5, min_periods=5).max().shift(1)>0, False))
    macd_improving = sign*(hist-hist.shift(1))>0

    ll = low.rolling(14, min_periods=10).min(); hh = high.rolling(14, min_periods=10).max()
    k = 100*(close-ll)/(hh-ll).replace(0,np.nan); d = k.rolling(3,min_periods=2).mean()
    st_reset = np.where(hbias.eq("BUY"), k.rolling(5,min_periods=5).min().shift(1)<30, np.where(hbias.eq("SELL"), k.rolling(5,min_periods=5).max().shift(1)>70, False))
    st_cross = np.where(hbias.eq("BUY"), (k>d) & (k.shift(1)<=d.shift(1)), np.where(hbias.eq("SELL"), (k<d) & (k.shift(1)>=d.shift(1)), False))

    avg_activity = activity.rolling(20,min_periods=10).mean()
    dry = activity.shift(1).lt(avg_activity.shift(1)*.85)
    pressure = sign*change > 0

    vol_std = change.rolling(20,min_periods=10).std().replace(0,np.nan)
    trend_proxy = (sign*change.rolling(12,min_periods=8).mean()).div(vol_std).clip(lower=-4,upper=4)
    cooling = atr_ratio.lt(1.05)
    unstable = atr_ratio.gt(1.55) | trend_proxy.abs().lt(.08)

    typical=(high+low+close)/3.0
    vwap=(typical*activity).rolling(40,min_periods=20).sum()/activity.rolling(40,min_periods=20).sum().replace(0,np.nan)
    vdiff=close-vwap
    v_touched=pd.Series(np.where(hbias.eq("BUY"),vdiff.shift(1).rolling(4).min().le(0),vdiff.shift(1).rolling(4).max().ge(0)),index=df.index)
    v_reclaim=sign*vdiff>0

    swing_high=high.rolling(40,min_periods=20).max().shift(1)
    swing_low=low.rolling(40,min_periods=20).min().shift(1)
    swing_range=(swing_high-swing_low).clip(lower=0)
    fib_lo=np.where(hbias.eq("BUY"), swing_high-.618*swing_range, swing_low+.382*swing_range)
    fib_hi=np.where(hbias.eq("BUY"), swing_high-.382*swing_range, swing_low+.618*swing_range)
    fib_zone=(close>=pd.Series(fib_lo,index=df.index)-.20*atr) & (close<=pd.Series(fib_hi,index=df.index)+.20*atr)

    up=high.diff(); down=-low.diff()
    plus_dm=up.where((up>down)&(up>0),0.0); minus_dm=down.where((down>up)&(down>0),0.0)
    pdi=100*plus_dm.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/atr.replace(0,np.nan)
    mdi=100*minus_dm.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/atr.replace(0,np.nan)
    dx=100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)
    adx=dx.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    adx_ok=adx.ge(18)&adx.ge(adx.shift(1))
    dmi_ok=np.where(hbias.eq("BUY"),pdi>=mdi,np.where(hbias.eq("SELL"),mdi>=pdi,False))
    adx_pull=((close-ema20).abs().le(1.25*atr)) | ((close-ema50).abs().le(1.25*atr))

    dc_hi=high.rolling(20,min_periods=15).max().shift(1); dc_lo=low.rolling(20,min_periods=15).min().shift(1); dc_mid=(dc_hi+dc_lo)/2
    dc_diff=close-dc_mid
    dc_touch=pd.Series(np.where(hbias.eq("BUY"),dc_diff.shift(1).rolling(4).min().le(0),dc_diff.shift(1).rolling(4).max().ge(0)),index=df.index)
    dc_reclaim=sign*(close-dc_mid)>0
    dc_slope=sign*(dc_mid-dc_mid.shift(5))>=0

    candle_range=(high-low).replace(0,np.nan)
    lower_wick=close.where(close<op,op)-low
    upper_wick=high-close.where(close>op,op)
    rejection=np.where(hbias.eq("BUY"),(lower_wick/candle_range>=.45)&(close>=low+.60*candle_range),np.where(hbias.eq("SELL"),(upper_wick/candle_range>=.45)&(close<=low+.40*candle_range),False))
    prior_pull=np.where(hbias.eq("BUY"),(close.shift(1)-ema20.shift(1)<0).rolling(4,min_periods=3).max().astype(bool),np.where(hbias.eq("SELL"),(close.shift(1)-ema20.shift(1)>0).rolling(4,min_periods=3).max().astype(bool),False))

    # S16 Keltner midline reclaim.
    keltner_touch=(sign*(close.shift(1)-ema20.shift(1))<=0)
    keltner_reclaim=sign*(close-ema20)>0
    contained=(high-low)<=1.75*atr

    # S17 RSI-2 exhaustion reset.
    rsi2_extreme=np.where(hbias.eq("BUY"),rsi2.rolling(3,min_periods=3).min().shift(1)<=12,np.where(hbias.eq("SELL"),rsi2.rolling(3,min_periods=3).max().shift(1)>=88,False))
    rsi2_recover=sign*(rsi2-rsi2.shift(1))>0
    rsi2_recover &= np.where(hbias.eq("BUY"),rsi2>=35,np.where(hbias.eq("SELL"),rsi2<=65,False))

    # S18 pivot reclaim.
    pivot=(dc_hi+dc_lo+close.shift(1))/3.0
    pivot_touch=sign*(close.shift(1)-pivot)<=0
    pivot_reclaim=sign*(close-pivot)>0
    pivot_near=(close-pivot).abs().le(1.25*atr)

    # S19 Ichimoku Kijun reclaim.
    kijun=(high.rolling(26,min_periods=20).max()+low.rolling(26,min_periods=20).min())/2.0
    kijun_touch=(close.shift(1)-kijun.shift(1)).abs().le(1.1*atr
    )
    kijun_reclaim=sign*(close-kijun)>0
    kijun_slope=sign*(kijun-kijun.shift(5))>=0

    # S20 OBV/volume momentum.
    obv=(np.sign(change.fillna(0))*activity).cumsum()
    obv_fast=obv.ewm(span=5,adjust=False).mean(); obv_slow=obv.ewm(span=13,adjust=False).mean()
    obv_pull=sign*(obv_fast.shift(1)-obv_slow.shift(1))<=0
    obv_recover=sign*(obv_fast-obv_slow)>0
    obv_near=(obv_fast-obv_slow).abs().ge((obv_fast-obv_slow).diff().abs().rolling(20,min_periods=8).mean().fillna(0)*.5)

    def score(*parts):
        return pd.concat([pd.Series(p, index=df.index).astype(float) * w * 100 for p,w in parts], axis=1).sum(axis=1).round().clip(0,100).astype(int)

    cond = {}
    scores = {}
    reasons = {}
    cond["S1"] = hard & near_ema.fillna(False) & np.where(hbias.eq("BUY"),(rsi.between(38,55)),np.where(hbias.eq("SELL"),rsi.between(45,62),False)) & body_dir
    scores["S1"] = score((trend_ok,.35),(near_ema.fillna(False),.25),(rsi.between(38,55).where(hbias.eq("BUY"),rsi.between(45,62)),.20),(body_dir,.20))
    cond["S2"] = hard & compression.fillna(False) & recovery.fillna(False) & near_ema.fillna(False)
    scores["S2"] = score((compression.fillna(False),.45),(recovery.fillna(False),.25),(near_ema.fillna(False),.20),(trend_ok,.10))
    cond["S3"] = hard & pd.Series(rsi_reset,index=df.index).fillna(False) & recovery.fillna(False)
    scores["S3"] = score((pd.Series(rsi_reset,index=df.index),.40),(recovery.fillna(False),.35),(structure,.25))
    cond["S4"] = hard & (~unstable) & cooling
    scores["S4"] = score(((~unstable),.55),(cooling,.45))
    quiet=(change.rolling(5,min_periods=3).mean().abs()/vol_std.replace(0,np.nan)).fillna(0).le(.20)
    cond["S5"] = hard & quiet & cooling
    scores["S5"] = score((cooling,.60),(quiet,.40))
    cond["S6"] = hard & near_ema.fillna(False) & (~unstable) & recovery.fillna(False)
    scores["S6"] = score((near_ema.fillna(False),.25),(~unstable,.25),(recovery.fillna(False),.25),(trend_proxy.clip(lower=0)/4,.25))
    cond["S7"] = hard & pd.Series(macd_reset,index=df.index).fillna(False) & macd_improving.fillna(False)
    scores["S7"] = score((pd.Series(macd_reset,index=df.index),.40),(macd_improving.fillna(False),.35),(structure,.25))
    cond["S8"] = hard & pd.Series(st_reset,index=df.index).fillna(False) & pd.Series(st_cross,index=df.index).fillna(False)
    scores["S8"] = score((pd.Series(st_reset,index=df.index),.40),(pd.Series(st_cross,index=df.index),.35),(structure,.25))
    cond["S9"] = hard & dry.fillna(False) & pressure.fillna(False) & body_dir
    scores["S9"] = score((dry.fillna(False),.40),(pressure.fillna(False),.30),(body_dir,.20),(structure,.10))
    cond["S10"] = hard & trend_proxy.ge(.25) & cooling & (~unstable)
    scores["S10"] = score((trend_proxy.ge(.25),.55),(cooling,.30),(~unstable,.15))
    cond["S11"] = hard & v_touched.fillna(False) & v_reclaim.fillna(False) & body_dir
    scores["S11"] = score((v_touched.fillna(False),.35),(v_reclaim.fillna(False),.35),(body_dir,.15),((vdiff.abs().le(.9*atr)).fillna(False),.15))
    cond["S12"] = hard & fib_zone.fillna(False) & recovery.fillna(False) & body_dir
    scores["S12"] = score((fib_zone.fillna(False),.40),(recovery.fillna(False),.30),(swing_range.ge(1.75*atr).fillna(False),.15),(body_dir,.15))
    cond["S13"] = hard & adx_ok.fillna(False) & pd.Series(dmi_ok,index=df.index).fillna(False) & adx_pull.fillna(False) & recovery.fillna(False)
    scores["S13"] = score((adx_ok.fillna(False),.35),(pd.Series(dmi_ok,index=df.index),.30),(adx_pull.fillna(False),.20),(recovery.fillna(False),.15))
    cond["S14"] = hard & dc_touch.fillna(False) & dc_reclaim.fillna(False) & dc_slope.fillna(False) & body_dir
    scores["S14"] = score((dc_touch.fillna(False),.35),(dc_reclaim.fillna(False),.35),(dc_slope.fillna(False),.15),(body_dir,.15))
    cond["S15"] = hard & pd.Series(rejection,index=df.index).fillna(False) & pd.Series(prior_pull,index=df.index).fillna(False) & body_dir
    scores["S15"] = score((pd.Series(rejection,index=df.index),.45),(pd.Series(prior_pull,index=df.index),.30),(body_dir,.15),(structure,.10))
    cond["S16"] = hard & keltner_touch.fillna(False) & keltner_reclaim.fillna(False) & contained.fillna(False) & body_dir
    scores["S16"] = score((keltner_touch.fillna(False),.40),(keltner_reclaim.fillna(False),.35),(contained.fillna(False),.15),(body_dir,.10))
    cond["S17"] = hard & pd.Series(rsi2_extreme,index=df.index).fillna(False) & pd.Series(rsi2_recover,index=df.index).fillna(False) & body_dir
    scores["S17"] = score((pd.Series(rsi2_extreme,index=df.index),.45),(pd.Series(rsi2_recover,index=df.index),.35),(structure,.10),(body_dir,.10))
    cond["S18"] = hard & pivot_touch.fillna(False) & pivot_reclaim.fillna(False) & pivot_near.fillna(False) & body_dir
    scores["S18"] = score((pivot_touch.fillna(False),.40),(pivot_reclaim.fillna(False),.35),(pivot_near.fillna(False),.15),(body_dir,.10))
    cond["S19"] = hard & kijun_touch.fillna(False) & kijun_reclaim.fillna(False) & kijun_slope.fillna(False) & body_dir
    scores["S19"] = score((kijun_touch.fillna(False),.40),(kijun_reclaim.fillna(False),.35),(kijun_slope.fillna(False),.15),(body_dir,.10))
    cond["S20"] = hard & obv_pull.fillna(False) & obv_recover.fillna(False) & obv_near.fillna(False) & body_dir
    scores["S20"] = score((obv_pull.fillna(False),.40),(obv_recover.fillna(False),.35),(obv_near.fillna(False),.15),(body_dir,.10))

    # Retain the HMM-based strategy families with a causal forward state shared
    # by live and historical calculations. No fit is repeated for every prefix.
    calm, stress, transition = _causal_regime_filter(close)
    hmm_ready = pd.Series(np.arange(len(df)) >= 34, index=df.index)
    hmm_cooling = stress.lt(stress.shift(1))
    strength = calm*(1-transition)*100
    volatility = change.rolling(20, min_periods=20).std().replace(0, np.nan)
    quiet_score = (100 - (change.rolling(5).mean().abs()/volatility*25).clip(upper=100)).clip(lower=0)
    scores["S4"] = ((1-transition)*100).where(hmm_ready, 0)
    scores["S5"] = (strength*.6 + quiet_score*.4).where(hmm_ready, 0)
    price_z = (close-close.rolling(50).mean()).abs()/close.rolling(50).std().replace(0,np.nan)
    scores["S6"] = ((100-price_z*25)*.25 + (100-change.abs()/volatility*20)*.20
                    + calm*20 + scores["S4"]*.15 + strength*.20).where(hmm_ready,0)
    scores["S10"] = (calm*55 + (1-transition)*30 + recovery.astype(float)*15).where(hmm_ready,0)
    for label in ("S4", "S5", "S6"):
        cond[label] = hard & hmm_ready & scores[label].ge(70)
    cond["S10"] = hard & hmm_ready & calm.ge(.55) & hmm_cooling & transition.le(.45) & recovery

    # Shared quality gate: a counter-trend move must precede a controlled,
    # directional recovery. Merely being above/below an EMA is not a pullback.
    price_values = df[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    valid_bar = pd.Series(np.isfinite(price_values).all(axis=1),index=df.index) & price_values.gt(0).all(axis=1)
    valid_bar &= high.ge(pd.concat([op,close,low],axis=1).max(axis=1))
    valid_bar &= low.le(pd.concat([op,close,high],axis=1).min(axis=1))
    enough = valid_bar.rolling(55,min_periods=55).sum().eq(55)
    prior_move_low = change.shift(1).rolling(6,min_periods=6).min()
    prior_move_high = change.shift(1).rolling(6,min_periods=6).max()
    pullback_seen = pd.Series(np.where(hbias.eq("BUY"),prior_move_low.lt(-.08*atr),prior_move_high.gt(.08*atr)),index=df.index)
    close_location = pd.Series(np.where(hbias.eq("BUY"),(close-low)/candle_range,(high-close)/candle_range),index=df.index)
    confirmed = body_dir & recovery & close_location.ge(.60) & (close-op).abs().div(candle_range).ge(.15)
    gap_ok = (op-prev_close).abs().le(atr.shift(1))
    noise_ratio = (tr/atr.shift(1).replace(0,np.nan)).rolling(20,min_periods=14).quantile(.75)
    # The score is based on realized candle noise, not a fabricated confidence.
    stable = atr_ratio.between(.55,1.40) & noise_ratio.le(1.8) & (high-low).le(1.8*atr) & gap_ok
    # 30% relaxed S1-S92 quality gate. Values are widened/softened only where
    # doing so creates more valid entries: pullback depth, candle confirmation,
    # noise/spike tolerance and minimum ADX. DMI agreement remains mandatory.
    relaxed_pullback_seen = pd.Series(np.where(hbias.eq("BUY"),
        prior_move_low.lt(-.08*atr*_relax),
        prior_move_high.gt(.08*atr*_relax)),index=df.index)
    relaxed_location = close_location.ge(.60*_relax)
    relaxed_body = (close-op).abs().div(candle_range).ge(.15*_relax)
    relaxed_confirmed = body_dir & recovery & relaxed_location & relaxed_body
    relaxed_stable = atr_ratio.between(.55*_relax, 1.40/_relax) & noise_ratio.le(1.8/_relax) & (high-low).le(1.8/_relax*atr) & (op-prev_close).abs().le(atr.shift(1)/_relax)
    relaxed_quality_gate = (relaxed_hard & enough & relaxed_pullback_seen & relaxed_confirmed & relaxed_stable & adx.ge(18*_relax)
                            & pd.Series(dmi_ok,index=df.index)).fillna(False)
    quality_gate = relaxed_quality_gate
    block_reason = pd.Series(np.select(
        [~enough,~valid_dir,~(trend_ok & structure),~pullback_seen,~confirmed,~stable,~adx.ge(18)],
        ["Insufficient/invalid completed OHLC", "Higher/Middle directions disagree", "Trend structure not aligned",
         "No preceding pullback", "Recovery candle not confirmed", "Gap, spike or noise limit exceeded", "Trend strength below minimum"],
        default="Pullback depth or directional-strength gate not met"),index=df.index)

    # S21–S50 have actual, direction-symmetric indicator triggers. The previous
    # add-ons used percent proximity alone and omitted SELL signals entirely.
    ema200 = close.ewm(span=200,adjust=False,min_periods=200).mean()
    long_trend = sign*(ema50-ema200)>0
    long_ready = pd.Series(np.arange(len(df))>=199,index=df.index)
    dip20 = pd.Series(np.where(hbias.eq("BUY"),low.shift(1).rolling(5).min().le(ema20.shift(1)),high.shift(1).rolling(5).max().ge(ema20.shift(1))),index=df.index)
    reclaim20 = sign*(close-ema20)>0
    cross20 = reclaim20 & (sign*(prev_close-ema20.shift(1))<=0)
    ema50_touch = (prev_close-ema50.shift(1)).abs().le(.5*atr.shift(1))
    golden = pd.Series(np.where(hbias.eq("BUY"),
        (close>=swing_high-.618*swing_range)&(close<=swing_high-.50*swing_range),
        (close>=swing_low+.50*swing_range)&(close<=swing_low+.618*swing_range)),index=df.index)
    prior_support=low.shift(1).rolling(20).min(); prior_resistance=high.shift(1).rolling(20).max()
    sweep = pd.Series(np.where(hbias.eq("BUY"),(low<prior_support)&(close>prior_support),(high>prior_resistance)&(close<prior_resistance)),index=df.index)
    prior_break_high=high.shift(2).rolling(20).max(); prior_break_low=low.shift(2).rolling(20).min()
    retest=pd.Series(np.where(hbias.eq("BUY"),
        (prev_close>prior_break_high)&(low<=prior_break_high+.15*atr)&(close>prior_break_high),
        (prev_close<prior_break_low)&(high>=prior_break_low-.15*atr)&(close<prior_break_low)),index=df.index)
    valid_volume=activity.gt(0) if volume_col else pd.Series(False,index=df.index)
    expanding_volume=valid_volume & activity.gt(avg_activity.shift(1)*1.15)
    dry_then_expand=dry & expanding_volume
    bb_reclaim=sign*(close-bb_mid)>0
    bb_reset=sign*(prev_close-bb_mid.shift(1))<=0
    rsi_mid=pd.Series(np.where(hbias.eq("BUY"),rsi.between(45,60),rsi.between(40,55)),index=df.index)
    engulf=body_dir & (sign*(op-prev_close)<=0) & (sign*(close-op.shift(1))>0) & (sign*(prev_close-op.shift(1))<0)
    higher_low=pd.Series(np.where(hbias.eq("BUY"),low.shift(1).rolling(3).min()>low.shift(4).rolling(8).min(),high.shift(1).rolling(3).max()<high.shift(4).rolling(8).max()),index=df.index)
    previous_counter=sign*(prev_close-op.shift(1))<0
    cross_prior_body=sign*(close-(prev_close+op.shift(1))/2)>0
    measured_quality=score((long_trend.fillna(False),.20),(adx.ge(22),.20),(dip20.fillna(False),.20),
                           (pd.Series(rsi_reset,index=df.index),.15),(macd_improving.fillna(False),.15),(expanding_volume,.10))
    extra = {
        "S21":long_trend & dip20 & reclaim20 & rsi_mid,
        "S22":adx.ge(25) & pd.Series(dmi_ok,index=df.index) & dip20 & reclaim20,
        "S23":v_touched & v_reclaim & vdiff.abs().le(.9*atr),
        "S24":golden & pd.Series(rejection,index=df.index),
        "S25":pd.Series(rsi_reset,index=df.index) & rsi_mid & long_trend,
        "S26":bb_reset & bb_reclaim & long_trend,
        "S27":keltner_touch & keltner_reclaim & contained & adx.ge(22),
        "S28":sweep & pd.Series(rejection,index=df.index),
        "S29":expanding_volume & dip20 & reclaim20,
        "S30":measured_quality.ge(80) & dip20 & reclaim20,
        "S31":ema50_touch & reclaim20 & long_trend,
        "S32":(prev_close-ema200.shift(1)).abs().le(atr) & (sign*(close-ema200)>0) & long_trend,
        "S33":adx_ok & adx.ge(25) & pd.Series(dmi_ok,index=df.index) & cross20,
        "S34":pd.Series(macd_reset,index=df.index) & macd_improving & dip20 & reclaim20,
        "S35":pd.Series(rsi_reset,index=df.index) & cross20 & long_trend,
        "S36":atr_ratio.between(.7,1.0) & dip20 & reclaim20 & long_trend,
        "S37":v_touched & v_reclaim & (sign*vdiff.shift(1)<-.25*atr.shift(1)),
        "S38":sweep & pd.Series(rejection,index=df.index) & adx.ge(22),
        "S39":retest & long_trend,
        "S40":long_trend & dip20 & reclaim20 & adx.ge(25) & macd_improving,
        "S41":previous_counter & cross_prior_body & ema50_touch & long_trend,
        "S42":dry_then_expand & dip20 & reclaim20,
        "S43":compression.shift(1,fill_value=False) & bb_width.gt(bb_width.shift(1)) & cross20,
        "S44":keltner_touch & keltner_reclaim & contained & long_trend & adx.ge(22),
        "S45":golden & pd.Series(rejection,index=df.index) & long_trend,
        "S46":higher_low & dip20 & reclaim20 & long_trend,
        "S47":engulf & dip20 & reclaim20,
        "S48":pd.Series(rsi2_extreme,index=df.index) & pd.Series(rsi2_recover,index=df.index) & long_trend,
        "S49":measured_quality.ge(85) & pd.Series(rejection,index=df.index) & reclaim20,
        "S50":measured_quality.ge(90) & long_trend & dip20 & reclaim20 & adx.ge(25),
    }
    for label, trigger in extra.items():
        required = long_ready if int(label[1:])>=31 else pd.Series(np.arange(len(df))>=99,index=df.index)
        cond[label]=trigger & required
        # Four independently measured confirmations, rather than fixed 85/95
        # scores pasted into every matching row.
        scores[label]=score((trigger.fillna(False),.45),(adx.ge(22),.20),(long_trend.fillna(False),.15),
                            (confirmed.fillna(False),.10),(stable.fillna(False),.10))

    # S51-S92 additive Middle Standard opportunity strategies.
    # These keep the same shared 30%-relaxed S1-S92 gate above.
    _new_gate = (hard & enough & stable & (adx.ge(18)) & pd.Series(dmi_ok,index=df.index)).fillna(False)
    _break = (sign*(close-prev_close)>0) & (high-low).le(2.0*atr)
    _momentum = (change.abs() > change.abs().rolling(20,min_periods=10).mean())
    _transition_ok = pd.Series(np.arange(len(df))>=55,index=df.index) & (~unstable)
    _extra_families = {
        **{f"S{i}": (_new_gate & _break & _transition_ok) for i in range(51,55)},
        **{f"S{i}": (_new_gate & _momentum & _transition_ok) for i in range(55,59)},
        **{f"S{i}": (_new_gate & near_ema.fillna(False) & rsi.lt(35 if hbias.eq("BUY").all() else 65) if False else _new_gate & near_ema.fillna(False)) for i in range(59,63)},
        **{f"S{i}": (_new_gate & retest.fillna(False)) for i in range(63,67)},
        **{f"S{i}": (_new_gate & compression.fillna(False) & _break) for i in range(67,71)},
        **{f"S{i}": (_new_gate & _transition_ok & recovery.fillna(False)) for i in range(71,75)},
        **{f"S{i}": (_new_gate & _momentum & trend_ok.fillna(False)) for i in range(75,79)},
        **{f"S{i}": (_new_gate & dip20.fillna(False) & reclaim20.fillna(False)) for i in range(79,83)},
        **{f"S{i}": (_new_gate & _break) for i in range(83,87)},
        **{f"S{i}": (_new_gate & (~trend_ok.fillna(False))) for i in range(87,91)},
        "S91": _new_gate & _momentum & trend_ok.fillna(False),
        "S92": _new_gate & measured_quality.ge(85),
    }
    for _label,_trigger in _extra_families.items():
        cond[_label]=_trigger.fillna(False)
        scores[_label]=score((_trigger.fillna(False),.55),(adx.ge(22),.20),(stable.fillna(False),.15),(structure.fillna(False),.10))

    # S93-S110 use a separate middle-standard quality gate instead of the S1-S92
    # hard gate. This creates room for structurally different pullbacks to qualify
    # even when none of the older 92 entry conditions is satisfied.
    _new_pullback_gate = (valid_dir & enough & stable & adx.ge(16)
                          & pd.Series(dmi_ok,index=df.index)
                          & atr_ratio.between(.45,1.80)
                          & structure.fillna(False)
                          & candle_range.le(2.20*atr)).fillna(False)

    legacy_entry_hit = pd.Series(False, index=df.index)
    for _legacy_label in [f"S{i}" for i in range(1,93)]:
        if _legacy_label in cond:
            legacy_entry_hit |= (cond[_legacy_label] & quality_gate).fillna(False)

    ema10 = close.ewm(span=10, adjust=False, min_periods=5).mean()
    ema34 = close.ewm(span=34, adjust=False, min_periods=12).mean()
    ema100 = close.ewm(span=100, adjust=False, min_periods=50).mean()
    ema10_ribbon = sign*(ema10-ema20)>0

    # New independent pullback structures. Each one is direction symmetric.
    ema34_touch = (prev_close-ema34.shift(1)).abs().le(.70*atr.shift(1))
    ema34_reclaim = sign*(close-ema34)>0
    ema100_touch = (prev_close-ema100.shift(1)).abs().le(.90*atr.shift(1))
    ema100_reclaim = sign*(close-ema100)>0
    ribbon_touch = (prev_close-ema20.shift(1)).abs().le(.55*atr.shift(1))
    ribbon_reclaim = sign*(close-ema20)>0
    vwap_ema_confluence = v_touched & v_reclaim & (prev_close-ema20.shift(1)).abs().le(.75*atr.shift(1)) & reclaim20

    mid48 = (high.rolling(48,min_periods=30).max().shift(1)+low.rolling(48,min_periods=30).min().shift(1))/2.0
    mid48_touch = (prev_close-mid48.shift(0)).abs().le(.65*atr.shift(1))
    mid48_reclaim = sign*(close-mid48)>0

    swing_dir_hi = swing_high
    swing_dir_lo = swing_low
    shallow_lo = np.where(hbias.eq("BUY"), swing_dir_hi-.382*(swing_dir_hi-swing_dir_lo), swing_dir_lo+.618*(swing_dir_hi-swing_dir_lo))
    shallow_hi = np.where(hbias.eq("BUY"), swing_dir_hi-.236*(swing_dir_hi-swing_dir_lo), swing_dir_lo+.764*(swing_dir_hi-swing_dir_lo))
    shallow_zone = (close>=pd.Series(np.minimum(shallow_lo,shallow_hi),index=df.index)-.10*atr) & (close<=pd.Series(np.maximum(shallow_lo,shallow_hi),index=df.index)+.10*atr)
    deep_lo = np.where(hbias.eq("BUY"), swing_dir_hi-.786*(swing_dir_hi-swing_dir_lo), swing_dir_lo+.214*(swing_dir_hi-swing_dir_lo))
    deep_hi = np.where(hbias.eq("BUY"), swing_dir_hi-.618*(swing_dir_hi-swing_dir_lo), swing_dir_lo+.382*(swing_dir_hi-swing_dir_lo))
    deep_zone = (close>=pd.Series(np.minimum(deep_lo,deep_hi),index=df.index)-.12*atr) & (close<=pd.Series(np.maximum(deep_lo,deep_hi),index=df.index)+.12*atr)

    sr12_hi = high.rolling(12,min_periods=10).max().shift(1)
    sr12_lo = low.rolling(12,min_periods=10).min().shift(1)
    sweep12 = pd.Series(np.where(hbias.eq("BUY"), (low<sr12_lo)&(close>sr12_lo), (high>sr12_hi)&(close<sr12_hi)),index=df.index)
    sr30_hi = high.rolling(30,min_periods=20).max().shift(1)
    sr30_lo = low.rolling(30,min_periods=20).min().shift(1)
    level30_touch = pd.Series(np.where(hbias.eq("BUY"), (prev_close-sr30_lo).abs().le(.85*atr.shift(1)), (prev_close-sr30_hi).abs().le(.85*atr.shift(1))),index=df.index)
    level30_reclaim = pd.Series(np.where(hbias.eq("BUY"), close>sr30_lo, close<sr30_hi),index=df.index)

    pp = (sr30_hi + sr30_lo + prev_close)/3.0
    pivot_s1 = 2*pp-sr30_hi
    pivot_r1 = 2*pp-sr30_lo
    pivot_support_touch = pd.Series(np.where(hbias.eq("BUY"),(prev_close-pivot_s1).abs().le(1.20*atr.shift(1)),(prev_close-pivot_r1).abs().le(1.20*atr.shift(1))),index=df.index)
    pivot_reclaim2 = pd.Series(np.where(hbias.eq("BUY"),close>pivot_s1,close<pivot_r1),index=df.index)

    stoch_reset = np.where(hbias.eq("BUY"), (k.rolling(4,min_periods=4).min().shift(1)<=35) & (k>d) & (k>=48), np.where(hbias.eq("SELL"),(k.rolling(4,min_periods=4).max().shift(1)>=65)&(k<d)&(k<=52),False))
    macd_zero_touch = (sign*macd.shift(1)<=0)
    macd_zero_reclaim = sign*macd>0

    will_hi=high.rolling(14,min_periods=10).max()
    will_lo=low.rolling(14,min_periods=10).min()
    will_r=-100*(will_hi-close)/(will_hi-will_lo).replace(0,np.nan)
    will_extreme=np.where(hbias.eq("BUY"),will_r.rolling(4,min_periods=4).min().shift(1)<=-80,np.where(hbias.eq("SELL"),will_r.rolling(4,min_periods=4).max().shift(1)>=-20,False))
    will_recover=np.where(hbias.eq("BUY"),will_r>-55,np.where(hbias.eq("SELL"),will_r<-45,False))

    money_flow = typical*activity
    flow_delta = typical.diff()
    positive_flow = money_flow.where(flow_delta>0,0.0)
    negative_flow = money_flow.where(flow_delta<0,0.0).abs()
    mfr = positive_flow.rolling(14,min_periods=10).sum()/negative_flow.rolling(14,min_periods=10).sum().replace(0,np.nan)
    mfi = 100-100/(1+mfr)
    mfi_reset = np.where(hbias.eq("BUY"),mfi.rolling(4,min_periods=4).min().shift(1)<=30,np.where(hbias.eq("SELL"),mfi.rolling(4,min_periods=4).max().shift(1)>=70,False))
    mfi_recover = np.where(hbias.eq("BUY"),(mfi>40)&(mfi>mfi.shift(1)),np.where(hbias.eq("SELL"),(mfi<60)&(mfi<mfi.shift(1)),False))
    volume_quality = activity.gt(0) if volume_col else pd.Series(False,index=df.index)

    adx_contract = adx.shift(1).between(12,20) & adx.gt(adx.shift(1))
    atr_envelope_mid = ema34
    atr_lower = atr_envelope_mid-1.45*atr
    atr_upper = atr_envelope_mid+1.45*atr
    atr_reentry = pd.Series(np.where(hbias.eq("BUY"),(prev_close<=atr_lower.shift(1))&(close>atr_lower),(prev_close>=atr_upper.shift(1))&(close<atr_upper)),index=df.index)
    two_bar_reversal = previous_counter & body_dir & ema50_touch & recovery

    confluence_count = (
        ema34_touch.astype(int) +
        v_touched.fillna(False).astype(int) +
        mid48_touch.fillna(False).astype(int) +
        shallow_zone.fillna(False).astype(int)
    )
    # S93-S110 deliberately use indicator structures that are not present in
    # the S1-S92 trigger definitions. They are additive: a row may legitimately
    # satisfy both an older strategy and a new confirmation model. This avoids
    # hiding a valid new setup merely because a broad S51-S92 opportunity family
    # also fired on the same completed candle.

    new_triggers = {
        "S93": ema34_touch & ema34_reclaim & confirmed,
        "S94": ema100_touch & ema100_reclaim & confirmed,
        "S95": ema10_ribbon & ribbon_touch & ribbon_reclaim & confirmed,
        "S96": vwap_ema_confluence & confirmed,
        "S97": mid48_touch & mid48_reclaim & confirmed,
        "S98": shallow_zone & recovery & body_dir,
        "S99": deep_zone & recovery & body_dir & adx.ge(20),
        "S100": sweep12 & body_dir & recovery,
        "S101": level30_touch & level30_reclaim & (rejection | body_dir),
        "S102": pivot_support_touch & pivot_reclaim2 & (body_dir | recovery | confirmed),
        "S103": pd.Series(stoch_reset,index=df.index) & body_dir,
        "S104": macd_zero_touch & macd_zero_reclaim & body_dir,
        "S105": pd.Series(will_extreme,index=df.index) & pd.Series(will_recover,index=df.index) & body_dir,
        "S106": pd.Series(mfi_reset,index=df.index) & pd.Series(mfi_recover,index=df.index) & pd.Series(volume_quality,index=df.index) & body_dir,
        "S107": adx_contract & pd.Series(dmi_ok,index=df.index) & recovery & body_dir,
        "S108": (atr_reentry | (atr_ratio.between(.50,1.50) & ema34_touch & ema34_reclaim)) & (contained | candle_range.le(1.60*atr)) & body_dir,
        "S109": two_bar_reversal & ((close-op).abs().div(candle_range).ge(.25)) & recovery,
        "S110": (confluence_count>=2) & recovery & confirmed,
    }
    for _label,_trigger in new_triggers.items():
        cond[_label] = (_new_pullback_gate & _trigger.fillna(False) & ~legacy_entry_hit).fillna(False)
        scores[_label] = score((_trigger.fillna(False),.55),(adx.ge(20),.15),(stable.fillna(False),.15),((confirmed if _label not in {"S98","S99","S100","S101","S102","S103","S104","S105","S106","S107","S108","S109"} else body_dir).fillna(False),.15))

    from core.pullback_engine_s1_s3_upgrade import STRATEGY_NAMES
    output={}
    conditions=[]; weights=[]; targets=[]
    for label in STRATEGY_NAMES:
        strategy_gate = quality_gate if int(label[1:]) <= 92 else _new_pullback_gate
        hit=(cond[label] & strategy_gate).fillna(False).astype(bool)
        sc=scores[label].fillna(0).round().clip(0,100).astype(int)
        conditions.append(hit.to_numpy())
        weights.append(sc.where(hit,0).to_numpy())
        target=np.where(sc>=92,70,np.where(sc>=82,60,50)) if int(label[1:])>20 else np.full(len(df),40)
        targets.append(target)
        output[f"{label} Entry Condition"]=hit.to_numpy()
        output[f"{label} Signal"]=pd.Categorical(np.where(hit,hbias,"NO ENTRY"),categories=["BUY","SELL","NO ENTRY","NO DATA"])
        reasons=np.where(hit,STRATEGY_NAMES[label]+" confirmed",
            np.where(strategy_gate,"Waiting for "+STRATEGY_NAMES[label],block_reason))
        categories=[STRATEGY_NAMES[label]+" confirmed","Waiting for "+STRATEGY_NAMES[label],
                    "Insufficient/invalid completed OHLC","Higher/Middle directions disagree","Trend structure not aligned",
                    "No preceding pullback","Recovery candle not confirmed","Gap, spike or noise limit exceeded",
                    "Trend strength below minimum","Pullback depth or directional-strength gate not met","No calculation"]
        output[f"{label} Reason"]=pd.Categorical(reasons,categories=categories)
        output[f"{label} Score"]=sc.to_numpy(dtype=np.int16)
    hits=np.column_stack(conditions); weight=np.column_stack(weights)
    counts=hits.sum(axis=1); total_weight=weight.sum(axis=1)
    avg_tp=(weight*np.column_stack(targets)).sum(axis=1)/np.maximum(total_weight,1)
    noise=noise_ratio.fillna(1).clip(lower=0).to_numpy()
    factor=np.where(noise>1,np.maximum(.55,1-(noise-1)*.15),1)
    tp=np.clip(np.rint(avg_tp*factor/10)*10,30,90).astype(int)
    output["Legacy Strategy Decision"]=np.where(counts>0,
        hbias.astype(str)+"-"+pd.Series(counts).astype(str)+" TP"+pd.Series(tp).astype(str)+" SL20","None")
    # Legacy S1-S110 votes are retained solely as compatibility diagnostics.
    # Only independent v4 families can enter.
    adaptive=build_adaptive_audit(df,higher_bias,middle_bias,symbol=symbol,timeframe=timeframe)
    for name in adaptive.columns:
        output[name]=adaptive[name].to_numpy()
    output["Strategy Decision"]=adaptive["Adaptive Decision"].to_numpy()
    output["Entry Noise Ratio"]=noise_ratio.to_numpy()
    output["Entry Quality Passed"]=((quality_gate | _new_pullback_gate).fillna(False)).to_numpy()
    output["Strategy Engine"]=STRATEGY_ENGINE_VERSION
    return pd.DataFrame(output,index=df.index)
