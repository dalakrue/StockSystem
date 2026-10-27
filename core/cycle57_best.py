"""Cycle 57 module: C57-16 (April-only system, follow-up round).

36 equations (the incumbent C31-29's 24 equations VERBATIM -- 15 mined
mom/atr legs + 9 TREND fallbacks -- plus 12 fresh-mined competitor
legs) spanning 3 check hours (16:30, 17:30, 18:30 UTC = 22:30, 23:30,
00:30 MMT), exactly 1 entry per check (top-1 by score across the
whole pool). The fresh legs carry win-scores on the incumbent scale,
so a fresh leg takes a check only when it outscores the incumbent leg
that would otherwise fire; otherwise the incumbent system trades
exactly as before.

C57-16 REPLACES C31-29 as April's system. It won the follow-up round
(Cycle 57, 20 end-to-end processes, fresh mining only, judged at the
2.5-pip primary cost with the round's relaxed win gate >= 80% plus
leftover improvement): weak ratings 4 (vs 6), unseen net@2.5 +372.3
(vs +325.9), win 90.91%, leftover 40.1% (vs 37.1%), checks 10/12,
discovery net@2.5 +3,312.7 (vs incumbent +1,940.6; 0/9 red months;
discovery leftover 60.8% vs 37.3%), sizing PASS (best N 108; the
incumbent failed sizing), P(profit) 99.9%. The unseen leftover
improvement (+3.0 pts) was a close call, so the LCT (Left95) was
required: it PASSES at the middle level (paired P 100.0%,
5th-percentile 32.2%). Cycle 31 (C31-29) remains selectable.

The 12 fresh legs are exit-profile variants of 5 fresh signals:
  * STC zone momentum, EURJPY h18 BUY (5 variants): stc > 60 and
    stc_slope3 > 2.
  * Camarilla S3 reclaim + DeMarker, EURJPY h18 BUY (3 variants):
    cam_s3d < 0 and dem < 0.38.
  * Heikin-Ashi downtrend body in a hot Rogers-Satchell vol regime,
    AUDJPY h18 SELL: ha_body < -0.1 and rs_ratio > 1.1.
  * Heikin-Ashi uptrend body in a calm Yang-Zhang vol regime,
    EURAUD h16 BUY (2 variants): ha_body > 0.1 and yz_ratio < 0.9.
  * Schaff zone + calm return distribution, EURCAD h17 BUY:
    stc > 75 and kurt72 < 2.
Fresh legs fired 145 discovery trades and 15 unseen trades (+137.4).

Fresh feature definitions (verbatim from the Cycle 57 research,
work_c57/scripts/c57_prep.py fresh_features; all causal; atr14 is the
incumbent scale unit and sizes every exit):
  stc       Schaff Trend Cycle: macd = EMA(23) - EMA(50) of close;
            d1 = EMA3(stochastic10(macd)); stc = EMA3(stochastic10(d1)).
            stc_slope3 = stc - stc 3 bars ago.
  cam_s3d   prior completed UTC day's Camarilla S3 = prior day close
            - (prior day high - prior day low) * 1.1 / 4;
            cam_s3d = (close - S3) / atr14.
  dem       DeMarker(14): SMA14(max(high - prev high, 0)) divided by
            that plus SMA14(max(prev low - low, 0)).
  ha_body   Heikin-Ashi body in ATR units: HA close = (O+H+L+C)/4;
            HA open recursive (seeded (open+close)/2 of the first
            bar); ha_body = (HA close - HA open) / atr14.
  rs_ratio  Rogers-Satchell vol regime: per-bar RS variance
            ln(H/O)*ln(H/C) + ln(L/O)*ln(L/C) clipped at 0;
            rs24 = sqrt(24-bar mean); rs_ratio = rs24 / 720-bar
            median of rs24 (min 240 bars).
  yz_ratio  Yang-Zhang vol regime (n=24, k = 0.34/(1.34 + 25/23)):
            yz24 = sqrt(var24(ln(open/prev close)) + k*var24(ln(close/
            open)) + (1-k)*mean24(RS variance)); yz_ratio = yz24 /
            720-bar median of yz24 (min 240 bars).
  kurt72    excess kurtosis of the last 72 one-bar log returns
            (pandas rolling kurt, Fisher).

Fallback equations (FB_*): direction 'TREND' fires on every check so
the exactly-1-entry-per-check rule always has a candidate; live
direction resolves per-trade from the signal candle's mom24 sign
(BUY if > 0 else SELL) -- the same fixed rule the research used.

Source of truth: ~/workspace/fx/work_c57/results/WINNER.json
Full spec: ~/workspace/fx/work_c57/results/WINNER_SPEC.json
Discovery trade log: ~/workspace/fx/work_c57/results/WINNER_disc_log.csv
Unseen trade log: ~/workspace/fx/work_c57/results/WINNER_unseen_log.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE57_VERSION = "cycle57-c5716-v1"
CYCLE57_CHECK_HOURS = (16, 17, 18)  # checks at h:30 UTC
CYCLE57_SYMBOLS_N = 10
MAX_HOLD_HOURS = 48
BASE_SPREAD_PIPS = 1.0
TP_CLIP = (10.0, 500.0)
SL_CLIP = (5.0, 100.0)

# ---------------------------------------------------------------- equations --
# Order is the research assembly order (incumbent 24 verbatim, then the
# 12 fresh legs in their ranked order); the stable top-1 sort makes
# this order the tie-break, exactly as in the research walk.
C57_EQUATIONS = (
    {"id": 'mom_NZDCAD_h16_momB_T2.5_A1.0_1.25x8', "symbol": 'NZDCAD', "hour": 16, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1000.3399285714286},
    {"id": 'mom_EURNZD_h16_momS_T2.5_A1.0_0.5x5', "symbol": 'EURNZD', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.2771714285714},
    {"id": 'mom_USDCHF_h16_momB_T0.75_A1.0_1.25x5', "symbol": 'USDCHF', "hour": 16, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 961.8244883241758},
    {"id": 'mom_USDCAD_h16_momS_T1.0_A1.0_0.5x8', "symbol": 'USDCAD', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 961.7629472527473},
    {"id": 'mom_EURAUD_h16_momS_T1.5_A1.0_0.3x3', "symbol": 'EURAUD', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 3.0, "score": 961.7210072527472},
    {"id": 'mom_EURNZD_h17_momB_T1.0_A1.0_0.75x5', "symbol": 'EURNZD', "hour": 17, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -1.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.6852928571428},
    {"id": 'mom_NZDCAD_h17_momS_T1.5_A1.0_1.0x5', "symbol": 'NZDCAD', "hour": 17, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 5.0, "score": 1000.31805},
    {"id": 'mom_EURUSD_h17_momB_T0.75_A1.0_0.75x8', "symbol": 'EURUSD', "hour": 17, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.2678964285715},
    {"id": 'mom_USDCHF_h17_momS_T0.75_A1.0_0.75x2', "symbol": 'USDCHF', "hour": 17, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 2.0, "score": 956.736196273292},
    {"id": 'mom_EURAUD_h17_momB_T2.5_A1.0_0.3x8', "symbol": 'EURAUD', "hour": 17, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 954.6578338311689},
    {"id": 'mom_NZDCAD_h18_momS_T0.75_A1.0_0.5x8', "symbol": 'NZDCAD', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.3314357142857},
    {"id": 'mom_EURUSD_h18_momB_T1.0_A1.0_0.75x8', "symbol": 'EURUSD', "hour": 18, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -1.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.2346196428572},
    {"id": 'mom_AUDCAD_h18_momS_T0.75_A0.9_0.5x8', "symbol": 'AUDCAD', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.1982071428571},
    {"id": 'mom_EURAUD_h18_momB_T0.75_A1.0_0.3x5', "symbol": 'EURAUD', "hour": 18, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 974.6506665018314},
    {"id": 'mom_EURNZD_h18_momS_T2.0_A1.0_0.3x5', "symbol": 'EURNZD', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 969.8995075541126},
    {"id": 'FB_EURUSD_h16_0', "symbol": 'EURUSD', "hour": 16, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000001.0},
    {"id": 'FB_GBPUSD_h16_1', "symbol": 'GBPUSD', "hour": 16, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000002.0},
    {"id": 'FB_AUDUSD_h16_2', "symbol": 'AUDUSD', "hour": 16, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 8.0, "score": -1000000003.0},
    {"id": 'FB_NZDUSD_h17_0', "symbol": 'NZDUSD', "hour": 17, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000004.0},
    {"id": 'FB_EURCHF_h17_1', "symbol": 'EURCHF', "hour": 17, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000005.0},
    {"id": 'FB_USDCAD_h17_2', "symbol": 'USDCAD', "hour": 17, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 8.0, "score": -1000000006.0},
    {"id": 'FB_EURAUD_h18_0', "symbol": 'EURAUD', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000007.0},
    {"id": 'FB_EURGBP_h18_1', "symbol": 'EURGBP', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 5.0, "score": -1000000008.0},
    {"id": 'FB_USDCHF_h18_2', "symbol": 'USDCHF', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000009.0},
    # ---- 12 fresh competitor legs (Cycle 57) ----
    {"id": 'STC_stc_zone2_EURJPY_h18_BUY_0.75x5.0', "symbol": 'EURJPY', "hour": 18, "direction": 'BUY',
     "conditions": [{"col": "stc", "op": ">", "val": 60.0}, {"col": "stc_slope3", "op": ">", "val": 2.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.5151660714286},
    {"id": 'STC_stc_zone2_EURJPY_h18_BUY_0.75x8.0', "symbol": 'EURJPY', "hour": 18, "direction": 'BUY',
     "conditions": [{"col": "stc", "op": ">", "val": 60.0}, {"col": "stc_slope3", "op": ">", "val": 2.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.5151660714286},
    {"id": 'COMBO_cam_dm_EURJPY_h18_BUY_0.4x6.5', "symbol": 'EURJPY', "hour": 18, "direction": 'BUY',
     "conditions": [{"col": "cam_s3d", "op": "<", "val": 0.0}, {"col": "dem", "op": "<", "val": 0.38}],
     "tp_mult": 0.4, "sl_mult": 6.5, "score": 1000.4212885714286},
    {"id": 'STC_stc_zone2_EURJPY_h18_BUY_0.6x10.0', "symbol": 'EURJPY', "hour": 18, "direction": 'BUY',
     "conditions": [{"col": "stc", "op": ">", "val": 60.0}, {"col": "stc_slope3", "op": ">", "val": 2.0}],
     "tp_mult": 0.6, "sl_mult": 10.0, "score": 1000.4043214285714},
    {"id": 'COMBO_cam_dm_EURJPY_h18_BUY_0.3x5.0', "symbol": 'EURJPY', "hour": 18, "direction": 'BUY',
     "conditions": [{"col": "cam_s3d", "op": "<", "val": 0.0}, {"col": "dem", "op": "<", "val": 0.38}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 1000.3720378571428},
    {"id": 'COMBO_cam_dm_EURJPY_h18_BUY_0.3x8.0', "symbol": 'EURJPY', "hour": 18, "direction": 'BUY',
     "conditions": [{"col": "cam_s3d", "op": "<", "val": 0.0}, {"col": "dem", "op": "<", "val": 0.38}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1000.3720378571428},
    {"id": 'STC_stc_zone2_EURJPY_h18_BUY_0.5x8.0', "symbol": 'EURJPY', "hour": 18, "direction": 'BUY',
     "conditions": [{"col": "stc", "op": ">", "val": 60.0}, {"col": "stc_slope3", "op": ">", "val": 2.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.3404785714285},
    {"id": 'STC_stc_zone2_EURJPY_h18_BUY_0.5x5.0', "symbol": 'EURJPY', "hour": 18, "direction": 'BUY',
     "conditions": [{"col": "stc", "op": ">", "val": 60.0}, {"col": "stc_slope3", "op": ">", "val": 2.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.3404785714285},
    {"id": 'COMBO_ha_volhot_AUDJPY_h18_SELL_0.6x10.0', "symbol": 'AUDJPY', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "ha_body", "op": "<", "val": -0.1}, {"col": "rs_ratio", "op": ">", "val": 1.1}],
     "tp_mult": 0.6, "sl_mult": 10.0, "score": 1000.3116285714285},
    {"id": 'COMBO_ha_volcalm_EURAUD_h16_BUY_0.3x8.0', "symbol": 'EURAUD', "hour": 16, "direction": 'BUY',
     "conditions": [{"col": "ha_body", "op": ">", "val": 0.1}, {"col": "yz_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1000.3002914285714},
    {"id": 'COMBO_ha_volcalm_EURAUD_h16_BUY_0.3x5.0', "symbol": 'EURAUD', "hour": 16, "direction": 'BUY',
     "conditions": [{"col": "ha_body", "op": ">", "val": 0.1}, {"col": "yz_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 1000.3002914285714},
    {"id": 'COMBO_stc_kurt_EURCAD_h17_BUY_0.3x5.0', "symbol": 'EURCAD', "hour": 17, "direction": 'BUY',
     "conditions": [{"col": "stc", "op": ">", "val": 75.0}, {"col": "kurt72", "op": "<", "val": 2.0}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 1000.2958007142856},
)

_COND_OPS = {">": lambda a, v: a > v, "<": lambda a, v: a < v,
             ">=": lambda a, v: a >= v, "<=": lambda a, v: a <= v}

_FEAT_CACHE = {}


def _as_utc(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


def _cond_ok(row, cond) -> bool:
    """Single condition on a feature row; NaN -> False."""
    v = row.get(cond["col"])
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return False
    if not np.isfinite(fv):
        return False
    return bool(_COND_OPS[cond["op"]](fv, cond["val"]))


def _trend_direction(mom24_value) -> str:
    """Fallback direction rule: BUY if signal-candle mom24 > 0 else SELL."""
    try:
        return "BUY" if float(mom24_value) > 0 else "SELL"
    except (TypeError, ValueError):
        return "SELL"


def _norm_frame(f):
    ff = f.copy()
    ff.index = pd.to_datetime(ff.index, utc=True).tz_localize(None)
    return ff.sort_index()


def _ema(x, span, minp=None):
    return x.ewm(span=span, min_periods=minp or span, adjust=False).mean()


def _stoch(v, n):
    lo = v.rolling(n, min_periods=n).min()
    hi = v.rolling(n, min_periods=n).max()
    return (v - lo) / (hi - lo).replace(0.0, np.nan) * 100.0


def _symbol_feat(sym, ff):
    """Base cycle12 features + the Cycle 57 fresh columns (stc,
    stc_slope3, cam_s3d, dem, ha_body, rs_ratio, yz_ratio, kurt72)
    for a normalised frame (cached). Verbatim ports of the research
    fresh_features (work_c57/scripts/c57_prep.py)."""
    key = (sym, len(ff), ff.index[0], ff.index[-1])
    hit = _FEAT_CACHE.get(key)
    if hit is not None:
        return hit
    if len(_FEAT_CACHE) > 32:
        _FEAT_CACHE.clear()
    feat = add_cycle12_features(ff.reset_index(drop=True))
    feat.index = ff.index
    O, H, L, C = ff["Open"], ff["High"], ff["Low"], ff["Close"]
    atrs = feat["atr14"].replace(0.0, np.nan)
    # --- Heikin-Ashi body (ATR units) ---
    hac = (O + H + L + C) / 4.0
    hao = np.empty(len(ff))
    hac_v = hac.to_numpy()
    hao[0] = (float(O.iloc[0]) + float(C.iloc[0])) / 2.0
    for t in range(1, len(ff)):
        hao[t] = 0.5 * (hao[t - 1] + hac_v[t - 1])
    feat["ha_body"] = (hac - pd.Series(hao, index=ff.index)) / atrs
    # --- Schaff Trend Cycle ---
    macd = _ema(C, 23) - _ema(C, 50)
    d1 = _ema(_stoch(macd, 10), 3, minp=3)
    stc = _ema(_stoch(d1, 10), 3, minp=3)
    feat["stc"] = stc
    feat["stc_slope3"] = stc - stc.shift(3)
    # --- Camarilla S3 distance (prior completed UTC day) ---
    dates = ff.index.normalize()
    day = pd.DataFrame({'d': dates, 'h': H.to_numpy(), 'l': L.to_numpy(),
                        'c': C.to_numpy()}).groupby('d').agg(
        dh=('h', 'max'), dl=('l', 'min'), dc=('c', 'last'))
    rng = day['dh'] - day['dl']
    day['S3'] = day['dc'] - rng * 1.1 / 4.0
    prior_s3 = day['S3'].shift(1)
    feat["cam_s3d"] = (C - dates.map(prior_s3)) / atrs
    # --- DeMarker 14 ---
    demax = (H - H.shift(1)).clip(lower=0.0)
    demin = (L.shift(1) - L).clip(lower=0.0)
    m1 = demax.rolling(14, min_periods=14).mean()
    m2 = demin.rolling(14, min_periods=14).mean()
    feat["dem"] = m1 / (m1 + m2).replace(0.0, np.nan)
    # --- Rogers-Satchell / Yang-Zhang vol ratios ---
    with np.errstate(divide='ignore', invalid='ignore'):
        a = np.log(H / O)
        b = np.log(H / C)
        c_ = np.log(L / O)
        d_ = np.log(L / C)
        o_ = np.log(O / C.shift(1))
        cc = np.log(C / O)
    rs_var = (a * b + c_ * d_).clip(lower=0.0)
    rs24 = np.sqrt(rs_var.rolling(24, min_periods=24).mean())
    n_yz = 24
    k_yz = 0.34 / (1.34 + (n_yz + 1.0) / (n_yz - 1.0))
    yz_var = (o_.rolling(n_yz, min_periods=n_yz).var()
              + k_yz * cc.rolling(n_yz, min_periods=n_yz).var()
              + (1.0 - k_yz) * rs_var.rolling(n_yz, min_periods=n_yz).mean())
    yz24 = np.sqrt(yz_var.clip(lower=0.0))
    feat["rs_ratio"] = rs24 / rs24.rolling(720, min_periods=240).median()
    feat["yz_ratio"] = yz24 / yz24.rolling(720, min_periods=240).median()
    # --- return-distribution kurtosis ---
    lr = np.log(C / C.shift(1))
    feat["kurt72"] = lr.rolling(72, min_periods=72).kurt()
    _FEAT_CACHE[key] = feat
    return feat


def evaluate_cycle57_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate C57-16 equations at one check time (h:30 UTC).

    frames: {symbol: H1 OHLC DataFrame indexed by candle-stamp}.
    Only equations whose hour matches the check hour are evaluated.
    Signal features come from the (h-1):00 UTC candle (last completed
    as of h:30 UTC); entry price = open of the h:00 UTC candle.
    TP/SL scale off ATR14 for every leg (standard clips). 'TREND'
    fallbacks resolve direction from the signal candle's mom24.
    Returns one row per firing equation with TP/SL already clipped.
    """
    check = _as_utc(check_time_utc)
    hour = int(check.hour)
    if hour not in CYCLE57_CHECK_HOURS:
        return pd.DataFrame()
    sig_stamp = (check - pd.Timedelta(hours=1, minutes=30)).tz_localize(None)
    ent_stamp = (check - pd.Timedelta(minutes=30)).tz_localize(None)
    frames_norm = {}
    for s, f in (frames or {}).items():
        if f is None or len(f) == 0:
            continue
        frames_norm[str(s).upper()] = _norm_frame(f)
    rows = []
    for eq in C57_EQUATIONS:
        if eq["hour"] != hour:
            continue
        sym = eq["symbol"]
        ff = frames_norm.get(sym)
        if ff is None:
            continue
        if sig_stamp not in ff.index or ent_stamp not in ff.index:
            continue
        feat = _symbol_feat(sym, ff)
        pos = ff.index.get_loc(sig_stamp)
        if isinstance(pos, (np.ndarray, slice)):
            continue
        row = feat.iloc[pos]
        if not all(_cond_ok(row, c) for c in eq["conditions"]):
            continue
        atr = float(row["atr14"])
        if not np.isfinite(atr) or atr <= 0:
            continue
        direction = eq["direction"]
        if direction == "TREND":
            direction = _trend_direction(row.get("mom24"))
        pip = _pip_size(sym)
        atr_pips = atr / pip
        tp = float(min(max(eq["tp_mult"] * atr_pips, TP_CLIP[0]), TP_CLIP[1]))
        sl = float(min(max(eq["sl_mult"] * atr_pips, SL_CLIP[0]), SL_CLIP[1]))
        rows.append({
            "check": check, "symbol": sym, "equation": eq["id"],
            "direction": direction, "score": eq["score"],
            "atr_pips": atr_pips,
            "entry_px": float(ff.loc[ent_stamp, "Open"]),
            "tp_pips": tp, "sl_pips": sl,
            "signal_candle": sig_stamp, "entry_candle": ent_stamp,
        })
    return pd.DataFrame(rows)


def select_cycle57_entries(signals: pd.DataFrame, open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: top-1 by score across the whole
    36-equation pool, max 1 open trade per symbol. Stable sort
    reproduces the research assembly order on ties."""
    if signals is None or len(signals) == 0:
        return signals.iloc[0:0] if signals is not None else pd.DataFrame()
    held = {str(s).upper() for s in (open_symbols or ())}
    out = []
    for _, row in signals.sort_values("score", ascending=False, kind="mergesort").iterrows():
        if len(out) >= 1:
            break
        if str(row["symbol"]).upper() in held:
            continue
        out.append(row)
        held.add(str(row["symbol"]).upper())
    return pd.DataFrame(out)


def is_cycle57_check_time(ts) -> bool:
    """True if ts (UTC) is at one of the C57 check hours (:30)."""
    t = _as_utc(ts)
    return int(t.hour) in CYCLE57_CHECK_HOURS and int(t.minute) == 30
