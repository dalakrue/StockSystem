"""Cycle 63 (C63-04) -- April H1 system, PROMOTED CLEANLY
2026-10-21 in the LCT-fix round (all Priority-1 gates + LCT).

C57-16's 36 equations verbatim (C28/C29-era incumbent legs +
Schaff TC / Camarilla-DeMarker / Heikin-Ashi / kurtosis fresh
legs from Cycle 57) plus 6 fresh ZigZag swing-structure legs:
swing-reversion BUYs stretched below confirmed structure
(zz_dlo < 0.35 with zz_dhi < -1.2) and an Ehlers+ZigZag combo
SELL. The fresh legs compete on score (weak@2.5 fell 4 -> 0).
Checks 16:00 / 17:00 / 18:00 UTC (23:00 / 00:00 / 01:00 MMT),
exactly 1 entry/check, 48h cap, TP/SL = mult x ATR14 clipped
to [10, 500] / [5, 100] pips. TREND fallbacks follow mom24.

Promotion record: weak 4 -> 0, unseen net@2.5 +571.3 pips, win
90.91%, leftover 40.1% -> 53.7%, checks 11/12, sizing PASS;
LCT vs C57-16 PASS at middle AND strict (paired P 100.0%,
5th-percentile 58.2%); discovery net +4,166.5, leftover 74.21%,
0/9 red Aprils. One watch item: the USDCAD reversion leg was
-53.5 on 6 unseen trades.

Base features reuse core.cycle57_best._symbol_feat verbatim;
the ZigZag confirmed-pivot distances (2-bar pivots from a
centred 5-bar window, confirmed 2 bars later, forward-filled)
and the Ehlers Super Smoother (period 10) distance reproduce
work_c63/scripts/c63_prep.py fresh_features verbatim. Features
are computed on the signal candle (check - 1h30m). Sibling
variants share conditions and scores (different exits);
equation order is preserved and selection is a stable sort,
exactly as mined.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import pip_size as _pip_size
from core.cycle57_best import (_FEAT_CACHE as _C57_CACHE,  # noqa: F401
                               _cond_ok, _norm_frame, _symbol_feat as _c57_feat,
                               _trend_direction)

TP_CLIP = (10.0, 500.0)
SL_CLIP = (5.0, 100.0)
CYCLE63_CHECK_HOURS = (16, 17, 18)
CYCLE63_EQUATIONS = (
{"id": 'mom_NZDCAD_h16_momB_T2.5_A1.0_1.25x8', "symbol": 'NZDCAD', "hour": 16, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1000.3399285714286},
    {"id": 'mom_EURNZD_h16_momS_T2.5_A1.0_0.5x5', "symbol": 'EURNZD', "hour": 16, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.2771714285714},
    {"id": 'mom_USDCHF_h16_momB_T0.75_A1.0_1.25x5', "symbol": 'USDCHF', "hour": 16, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 961.8244883241758},
    {"id": 'mom_USDCAD_h16_momS_T1.0_A1.0_0.5x8', "symbol": 'USDCAD', "hour": 16, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 961.7629472527473},
    {"id": 'mom_EURAUD_h16_momS_T1.5_A1.0_0.3x3', "symbol": 'EURAUD', "hour": 16, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 3.0, "score": 961.7210072527472},
    {"id": 'mom_EURNZD_h17_momB_T1.0_A1.0_0.75x5', "symbol": 'EURNZD', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.6852928571428},
    {"id": 'mom_NZDCAD_h17_momS_T1.5_A1.0_1.0x5', "symbol": 'NZDCAD', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 5.0, "score": 1000.31805},
    {"id": 'mom_EURUSD_h17_momB_T0.75_A1.0_0.75x8', "symbol": 'EURUSD', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.2678964285715},
    {"id": 'mom_USDCHF_h17_momS_T0.75_A1.0_0.75x2', "symbol": 'USDCHF', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 2.0, "score": 956.736196273292},
    {"id": 'mom_EURAUD_h17_momB_T2.5_A1.0_0.3x8', "symbol": 'EURAUD', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 954.6578338311689},
    {"id": 'mom_NZDCAD_h18_momS_T0.75_A1.0_0.5x8', "symbol": 'NZDCAD', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.3314357142857},
    {"id": 'mom_EURUSD_h18_momB_T1.0_A1.0_0.75x8', "symbol": 'EURUSD', "hour": 18, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.2346196428572},
    {"id": 'mom_AUDCAD_h18_momS_T0.75_A0.9_0.5x8', "symbol": 'AUDCAD', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.1982071428571},
    {"id": 'mom_EURAUD_h18_momB_T0.75_A1.0_0.3x5', "symbol": 'EURAUD', "hour": 18, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 974.6506665018314},
    {"id": 'mom_EURNZD_h18_momS_T2.0_A1.0_0.3x5', "symbol": 'EURNZD', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
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
    {"id": 'STC_stc_zone2_EURJPY_h18_BUY_0.75x5.0', "symbol": 'EURJPY', "hour": 18, "direction": 'BUY',
     "conditions": [
     {"col": 'stc', "op": '>', "val": 60.0},
     {"col": 'stc_slope3', "op": '>', "val": 2.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.5151660714286},
    {"id": 'STC_stc_zone2_EURJPY_h18_BUY_0.75x8.0', "symbol": 'EURJPY', "hour": 18, "direction": 'BUY',
     "conditions": [
     {"col": 'stc', "op": '>', "val": 60.0},
     {"col": 'stc_slope3', "op": '>', "val": 2.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.5151660714286},
    {"id": 'COMBO_cam_dm_EURJPY_h18_BUY_0.4x6.5', "symbol": 'EURJPY', "hour": 18, "direction": 'BUY',
     "conditions": [
     {"col": 'cam_s3d', "op": '<', "val": 0.0},
     {"col": 'dem', "op": '<', "val": 0.38}],
     "tp_mult": 0.4, "sl_mult": 6.5, "score": 1000.4212885714286},
    {"id": 'STC_stc_zone2_EURJPY_h18_BUY_0.6x10.0', "symbol": 'EURJPY', "hour": 18, "direction": 'BUY',
     "conditions": [
     {"col": 'stc', "op": '>', "val": 60.0},
     {"col": 'stc_slope3', "op": '>', "val": 2.0}],
     "tp_mult": 0.6, "sl_mult": 10.0, "score": 1000.4043214285714},
    {"id": 'COMBO_cam_dm_EURJPY_h18_BUY_0.3x5.0', "symbol": 'EURJPY', "hour": 18, "direction": 'BUY',
     "conditions": [
     {"col": 'cam_s3d', "op": '<', "val": 0.0},
     {"col": 'dem', "op": '<', "val": 0.38}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 1000.3720378571428},
    {"id": 'COMBO_cam_dm_EURJPY_h18_BUY_0.3x8.0', "symbol": 'EURJPY', "hour": 18, "direction": 'BUY',
     "conditions": [
     {"col": 'cam_s3d', "op": '<', "val": 0.0},
     {"col": 'dem', "op": '<', "val": 0.38}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1000.3720378571428},
    {"id": 'STC_stc_zone2_EURJPY_h18_BUY_0.5x8.0', "symbol": 'EURJPY', "hour": 18, "direction": 'BUY',
     "conditions": [
     {"col": 'stc', "op": '>', "val": 60.0},
     {"col": 'stc_slope3', "op": '>', "val": 2.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.3404785714285},
    {"id": 'STC_stc_zone2_EURJPY_h18_BUY_0.5x5.0', "symbol": 'EURJPY', "hour": 18, "direction": 'BUY',
     "conditions": [
     {"col": 'stc', "op": '>', "val": 60.0},
     {"col": 'stc_slope3', "op": '>', "val": 2.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.3404785714285},
    {"id": 'COMBO_ha_volhot_AUDJPY_h18_SELL_0.6x10.0', "symbol": 'AUDJPY', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'ha_body', "op": '<', "val": -0.1},
     {"col": 'rs_ratio', "op": '>', "val": 1.1}],
     "tp_mult": 0.6, "sl_mult": 10.0, "score": 1000.3116285714285},
    {"id": 'COMBO_ha_volcalm_EURAUD_h16_BUY_0.3x8.0', "symbol": 'EURAUD', "hour": 16, "direction": 'BUY',
     "conditions": [
     {"col": 'ha_body', "op": '>', "val": 0.1},
     {"col": 'yz_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1000.3002914285714},
    {"id": 'COMBO_ha_volcalm_EURAUD_h16_BUY_0.3x5.0', "symbol": 'EURAUD', "hour": 16, "direction": 'BUY',
     "conditions": [
     {"col": 'ha_body', "op": '>', "val": 0.1},
     {"col": 'yz_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 1000.3002914285714},
    {"id": 'COMBO_stc_kurt_EURCAD_h17_BUY_0.3x5.0', "symbol": 'EURCAD', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'stc', "op": '>', "val": 75.0},
     {"col": 'kurt72', "op": '<', "val": 2.0}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 1000.2958007142856},
    {"id": 'ZZ_zz_rev_GBPJPY_h16_BUY_0.4x6.5', "symbol": 'GBPJPY', "hour": 16, "direction": 'BUY',
     "conditions": [
     {"col": 'zz_dlo', "op": '<', "val": 0.35},
     {"col": 'zz_dhi', "op": '<', "val": -1.2}],
     "tp_mult": 0.4, "sl_mult": 6.5, "score": 1000.4505285714285},
    {"id": 'ZZ_zz_rev_USDCAD_h17_BUY_0.5x5.0', "symbol": 'USDCAD', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'zz_dlo', "op": '<', "val": 0.35},
     {"col": 'zz_dhi', "op": '<', "val": -1.2}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.4306785714285},
    {"id": 'ZZ_zz_rev_USDCAD_h17_BUY_0.5x8.0', "symbol": 'USDCAD', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'zz_dlo', "op": '<', "val": 0.35},
     {"col": 'zz_dhi', "op": '<', "val": -1.2}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.4306785714285},
    {"id": 'XCOMBO_ehl_zz_EURNZD_h17_SELL_0.75x5.0', "symbol": 'EURNZD', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'ss_dist', "op": '<', "val": -0.35},
     {"col": 'zz_dlo', "op": '>', "val": 0.4}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.4180035714286},
    {"id": 'XCOMBO_ehl_zz_EURNZD_h17_SELL_0.75x8.0', "symbol": 'EURNZD', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'ss_dist', "op": '<', "val": -0.35},
     {"col": 'zz_dlo', "op": '>', "val": 0.4}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.4180035714286},
    {"id": 'ZZ_zz_rev_USDCAD_h17_BUY_0.4x6.5', "symbol": 'USDCAD', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'zz_dlo', "op": '<', "val": 0.35},
     {"col": 'zz_dhi', "op": '<', "val": -1.2}],
     "tp_mult": 0.4, "sl_mult": 6.5, "score": 1000.3914171428571},
)

_FEAT63_CACHE = {}


def _super_smoother(v: np.ndarray, period: int) -> np.ndarray:
    """Ehlers 2-pole Super Smoother (causal, NaN-aware seeding)."""
    a = np.exp(-1.414 * np.pi / period)
    b = 2.0 * a * np.cos(1.414 * np.pi / period)
    c2, c3 = b, -a * a
    c1 = 1.0 - c2 - c3
    out = np.full(len(v), np.nan)
    f1 = f2 = np.nan
    for t in range(len(v)):
        x = v[t]
        if not np.isfinite(x):
            out[t] = f1 if np.isfinite(f1) else np.nan
            continue
        if not np.isfinite(f1):
            f = x
        elif not np.isfinite(f2):
            f = c1 * x + c2 * f1
            f = f / (c1 + c2) if (c1 + c2) != 0 else x
        else:
            f = c1 * x + c2 * f1 + c3 * f2
        out[t] = f
        f2, f1 = f1, f
    return out


def _symbol_feat63(sym: str, ff: pd.DataFrame) -> pd.DataFrame:
    """Cycle 57 features + Cycle 63 fresh columns (ss_dist,
    zz_dhi, zz_dlo) for a normalised frame (cached)."""
    key = (sym, len(ff), ff.index[0], ff.index[-1])
    hit = _FEAT63_CACHE.get(key)
    if hit is not None:
        return hit
    if len(_FEAT63_CACHE) > 32:
        _FEAT63_CACHE.clear()
    feat = _c57_feat(sym, ff).copy()
    H, L, C = ff['High'], ff['Low'], ff['Close']
    atrs = feat['atr14'].replace(0.0, np.nan)
    ss = pd.Series(_super_smoother(C.to_numpy(dtype=float), 10),
                   index=ff.index)
    feat['ss_dist'] = (C - ss) / atrs
    Hv, Lv = H.to_numpy(dtype=float), L.to_numpy(dtype=float)
    hmax = H.rolling(5, center=True).max().to_numpy()
    lmin = L.rolling(5, center=True).min().to_numpy()
    ph = np.where(Hv == hmax, Hv, np.nan)
    pl = np.where(Lv == lmin, Lv, np.nan)
    conf_h = pd.Series(ph, index=ff.index).shift(2).ffill()
    conf_l = pd.Series(pl, index=ff.index).shift(2).ffill()
    feat['zz_dhi'] = (C - conf_h) / atrs
    feat['zz_dlo'] = (C - conf_l) / atrs
    _FEAT63_CACHE[key] = feat
    return feat


def evaluate_cycle63_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """One row per firing Cycle 63 equation at `check_time_utc`."""
    check = pd.Timestamp(check_time_utc)
    if check.tzinfo is not None:
        check = check.tz_convert('UTC')
    hour = int(check.hour)
    if hour not in CYCLE63_CHECK_HOURS or int(check.minute) != 30:
        return pd.DataFrame()
    sig_stamp = (check - pd.Timedelta(hours=1, minutes=30)).tz_localize(None)
    ent_stamp = (check - pd.Timedelta(minutes=30)).tz_localize(None)
    frames_norm = {}
    for s, f in (frames or {}).items():
        if f is None or len(f) == 0:
            continue
        frames_norm[str(s).upper()] = _norm_frame(f)
    rows = []
    for eq in CYCLE63_EQUATIONS:
        if eq['hour'] != hour:
            continue
        sym = eq['symbol']
        ff = frames_norm.get(sym)
        if ff is None:
            continue
        if sig_stamp not in ff.index or ent_stamp not in ff.index:
            continue
        feat = _symbol_feat63(sym, ff)
        pos = ff.index.get_loc(sig_stamp)
        if isinstance(pos, (np.ndarray, slice)):
            continue
        row = feat.iloc[pos]
        if not all(_cond_ok(row, c) for c in eq['conditions']):
            continue
        atr = float(row['atr14'])
        if not np.isfinite(atr) or atr <= 0:
            continue
        direction = eq['direction']
        if direction == 'TREND':
            direction = _trend_direction(row.get('mom24'))
        pip = _pip_size(sym)
        atr_pips = atr / pip
        tp = float(min(max(eq['tp_mult'] * atr_pips, TP_CLIP[0]), TP_CLIP[1]))
        sl = float(min(max(eq['sl_mult'] * atr_pips, SL_CLIP[0]), SL_CLIP[1]))
        rows.append({
            'check': check.tz_localize(None) if check.tzinfo else check,
            'symbol': sym, 'equation': eq['id'],
            'direction': direction, 'score': eq['score'],
            'atr_pips': atr_pips,
            'entry_px': float(ff.loc[ent_stamp, 'Open']),
            'tp_pips': tp, 'sl_pips': sl,
            'signal_candle': sig_stamp, 'entry_candle': ent_stamp,
        })
    return pd.DataFrame(rows)


def select_cycle63_entries(signals: pd.DataFrame,
                           open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: top-1 by score (stable mergesort),
    skipping symbols with an open position."""
    if signals is None or len(signals) == 0:
        return signals.iloc[0:0] if signals is not None else pd.DataFrame()
    held = {str(s).upper() for s in (open_symbols or ())}
    out = []
    for _, row in signals.sort_values('score', ascending=False,
                                      kind='mergesort').iterrows():
        if len(out) >= 1:
            break
        if str(row['symbol']).upper() in held:
            continue
        out.append(row)
        held.add(str(row['symbol']).upper())
    return pd.DataFrame(out)


def is_cycle63_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    if t.tzinfo is not None:
        t = t.tz_convert('UTC')
    return int(t.hour) in CYCLE63_CHECK_HOURS and int(t.minute) == 30
