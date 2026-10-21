"""Cycle 64 (C64-09) -- May H1 system, PROMOTED BY USER OVERRIDE
2026-10-21 in the LCT-fix round (Cycle 64 verdict itself:
INCUMBENT_ALREADY_PASSES -- no challenger cleared every gate).

C32-20's 24 equations verbatim (15 mined mom24/atr_ratio legs +
9 TREND fallbacks) plus 6 fresh legs mined from indicator
families new to this program -- Awesome Oscillator, Chande
Momentum Oscillator, Alligator spread, Qstick and a
Yang-Zhang volatility-regime gate. The fresh legs carry scores
in the same 1000.x band as the mined legs, so they COMPETE for
the top-1 pick (157 of 603 discovery picks changed). Checks
10:00 / 16:00 / 18:00 UTC (17:00 / 23:00 / 01:00 MMT), exactly
1 entry/check, 48h cap, TP/SL = mult x ATR14 clipped to
[10, 500] / [5, 100] pips. TREND fallbacks follow mom24 sign.

Why it was promoted despite failing the unseen gates (leftover
48.3% vs C32-20's 64.7%, weak 1 vs 0): the Leftover Confidence
Test against C32-20 is the strongest of the whole round --
paired P 100.00%, 5th-percentile leftover 45.69% (MIDDLE and
STRICT pass) -- with discovery net@2.5 +3,814.8 vs +2,741.6 and
discovery leftover 63.93% vs 49.62% over 603 trades, 0/9 red
Mays. The user chose maximum discovery confidence over one
lucky unseen month. Unseen May 2025: net@2.5 +373.0 pips, win
90.91%, 3.00 entries/day, weak 1.

Feature formulas reproduce work_c64/scripts/c64_engine.py
add_features verbatim (CMO14 rolling sums; AO = SMA5-SMA34 of
the median price; Alligator SMMA = Wilder ewm alpha 1/n with
causal shifts 8/5/3; Qstick 8; Yang-Zhang 24-bar variance over
its trailing-480-bar median). Features are computed on the
signal candle (check - 1h30m).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE64_CHECK_HOURS = (10, 16, 18)
CYCLE64_EQUATIONS = (
{"id": 'mom_GBPJPY_h10_momB_T1.5_A0.9_0.75x5', "symbol": 'GBPJPY', "hour": 10, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -1.5},
     {"col": 'atr_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.3793892857143},
    {"id": 'mom_CHFJPY_h10_momS_T1.5_A0.9_0.5x8', "symbol": 'CHFJPY', "hour": 10, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.5},
     {"col": 'atr_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 971.6346928571429},
    {"id": 'mom_GBPUSD_h10_momS_T3.0_A1.0_1.0x8', "symbol": 'GBPUSD', "hour": 10, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 3.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 968.0472711981566},
    {"id": 'mom_EURAUD_h10_momB_T2.5_A1.0_0.5x5', "symbol": 'EURAUD', "hour": 10, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 967.9704283410139},
    {"id": 'mom_EURJPY_h10_momS_T3.0_A1.0_0.75x8', "symbol": 'EURJPY', "hour": 10, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 3.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 966.8900613095237},
    {"id": 'mom_EURNZD_h16_momS_T0.75_A1.0_1.0x2', "symbol": 'EURNZD', "hour": 16, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 2.0, "score": 1000.4631428571429},
    {"id": 'mom_NZDCAD_h16_momS_T0.75_A1.0_1.0x8', "symbol": 'NZDCAD', "hour": 16, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1000.38015},
    {"id": 'mom_AUDCHF_h16_momB_T1.0_A1.0_1.25x8', "symbol": 'AUDCHF', "hour": 16, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1000.2853571428572},
    {"id": 'mom_NZDUSD_h16_momB_T0.75_A1.0_1.0x8', "symbol": 'NZDUSD', "hour": 16, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1000.2677714285715},
    {"id": 'mom_AUDNZD_h16_momS_T0.75_A0.9_0.75x3', "symbol": 'AUDNZD', "hour": 16, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 0.75, "sl_mult": 3.0, "score": 1000.2169982142857},
    {"id": 'mom_GBPJPY_h18_momS_T1.0_A1.0_0.75x3', "symbol": 'GBPJPY', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 3.0, "score": 1000.4302160714286},
    {"id": 'mom_AUDCAD_h18_momB_T0.75_A1.0_0.5x8', "symbol": 'AUDCAD', "hour": 18, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.2611035714285},
    {"id": 'mom_AUDNZD_h18_momS_T0.75_A0.9_1.0x8', "symbol": 'AUDNZD', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1000.2405285714285},
    {"id": 'mom_NZDUSD_h18_momS_T2.0_A1.0_0.5x8', "symbol": 'NZDUSD', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.225},
    {"id": 'mom_NZDCAD_h18_momS_T0.75_A0.9_1.0x3', "symbol": 'NZDCAD', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 1.0, "sl_mult": 3.0, "score": 1000.2167285714286},
    {"id": 'FB_EURUSD_h10_0', "symbol": 'EURUSD', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000001.0},
    {"id": 'FB_GBPUSD_h10_1', "symbol": 'GBPUSD', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 8.0, "score": -1000000002.0},
    {"id": 'FB_USDJPY_h10_2', "symbol": 'USDJPY', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 8.0, "score": -1000000003.0},
    {"id": 'FB_AUDUSD_h16_0', "symbol": 'AUDUSD', "hour": 16, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 10.0, "score": -1000000004.0},
    {"id": 'FB_EURJPY_h16_1', "symbol": 'EURJPY', "hour": 16, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.2, "sl_mult": 8.0, "score": -1000000005.0},
    {"id": 'FB_GBPJPY_h16_2', "symbol": 'GBPJPY', "hour": 16, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.2, "sl_mult": 5.0, "score": -1000000006.0},
    {"id": 'FB_AUDJPY_h18_0', "symbol": 'AUDJPY', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000007.0},
    {"id": 'FB_NZDUSD_h18_1', "symbol": 'NZDUSD', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 10.0, "score": -1000000008.0},
    {"id": 'FB_EURCHF_h18_2', "symbol": 'EURCHF', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.2, "sl_mult": 5.0, "score": -1000000009.0},
    {"id": 'AO_ao_mom2_S_CHFJPY_h18_0.45x6.0_H48', "symbol": 'CHFJPY', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'ao_atr', "op": '<', "val": -0.1},
     {"col": 'ao_rise', "op": '<', "val": 0.0}],
     "tp_mult": 0.45, "sl_mult": 6.0, "score": 1000.4638878571428},
    {"id": 'CMO_cmo14_os40_B_AUDJPY_h16_0.9x7.0_H48', "symbol": 'AUDJPY', "hour": 16, "direction": 'BUY',
     "conditions": [{"col": 'cmo14', "op": '<', "val": -40}],
     "tp_mult": 0.9, "sl_mult": 7.0, "score": 1000.40521},
    {"id": 'ALG_alg_spr_S_AUDCAD_h18_0.6x6.0_H48', "symbol": 'AUDCAD', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'alg_spread', "op": '<', "val": -0.3},
     {"col": 'px_lips', "op": '<', "val": 0.0}],
     "tp_mult": 0.6, "sl_mult": 6.0, "score": 1000.4050414285714},
    {"id": 'CMO_cmo14_os40_S_EURAUD_h16_0.45x6.0_H48', "symbol": 'EURAUD', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": 'cmo14', "op": '>', "val": 40}],
     "tp_mult": 0.45, "sl_mult": 6.0, "score": 1000.2980778571429},
    {"id": 'QSTG_qst_zone_S_yzg_EURAUD_h10_0.75x5.0_H48', "symbol": 'EURAUD', "hour": 10, "direction": 'SELL',
     "conditions": [
     {"col": 'qstick', "op": '<', "val": -0.25},
     {"col": 'yz_ratio', "op": '>', "val": 0.65},
     {"col": 'yz_ratio', "op": '<', "val": 1.3}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.2945196428572},
    {"id": 'QST_qst_zone_B_CHFJPY_h16_0.6x6.0_H48', "symbol": 'CHFJPY', "hour": 16, "direction": 'BUY',
     "conditions": [{"col": 'qstick', "op": '>', "val": 0.25}],
     "tp_mult": 0.6, "sl_mult": 6.0, "score": 1000.2932128571429},
)


def _smma(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(alpha=1.0 / n, min_periods=n, adjust=False).mean()


def _symbol_feat(df: pd.DataFrame) -> pd.DataFrame:
    f = add_cycle12_features(df)
    op, cl, hi, lo = f['Open'], f['Close'], f['High'], f['Low']
    atr = f['atr14'].replace(0.0, np.nan)
    # CMO14: rolling sums of up/down close moves.
    d = cl.diff()
    su = d.clip(lower=0).rolling(14, min_periods=14).sum()
    sd = (-d.clip(upper=0)).rolling(14, min_periods=14).sum()
    f['cmo14'] = 100.0 * (su - sd) / (su + sd).replace(0.0, np.nan)
    # Awesome Oscillator on the median price.
    mp = (hi + lo) / 2.0
    ao = (mp.rolling(5, min_periods=5).mean()
          - mp.rolling(34, min_periods=34).mean())
    f['ao_atr'] = ao / atr
    f['ao_rise'] = (ao - ao.shift(2)) / atr
    # Alligator: SMMA lines with causal shifts.
    jaw = _smma(mp, 13).shift(8)
    lips = _smma(mp, 5).shift(3)
    f['alg_spread'] = (lips - jaw) / atr
    f['px_lips'] = (cl - lips) / atr
    # Qstick 8.
    f['qstick'] = (cl - op).rolling(8, min_periods=8).mean() / atr
    # Yang-Zhang volatility ratio (24-bar, trailing-480 median).
    oc = np.log(op / cl.shift(1))
    co = np.log(cl / op)
    u = np.log(hi / op)
    dn_ = np.log(lo / op)
    rs_bar = u * (u - co) + dn_ * (dn_ - co)
    n_yz = 24
    k_yz = 0.34 / (1.34 + (n_yz + 1) / (n_yz - 1))
    yz_var = (oc.rolling(n_yz, min_periods=n_yz).var()
              + k_yz * co.rolling(n_yz, min_periods=n_yz).var()
              + (1 - k_yz) * rs_bar.rolling(n_yz, min_periods=n_yz).mean())
    yz = np.sqrt(yz_var.clip(lower=0))
    f['yz_ratio'] = yz / yz.rolling(480, min_periods=120).median().replace(0.0, np.nan)
    return f


def _cond_ok(row: pd.Series, conditions) -> bool:
    for c in conditions:
        col, op, val = c['col'], c['op'], c['val']
        v = row.get(col, np.nan)
        if not np.isfinite(v):
            return False
        if op == '>' and not (v > val):
            return False
        if op == '<' and not (v < val):
            return False
        if op == '>=' and not (v >= val):
            return False
        if op == '<=' and not (v <= val):
            return False
    return True


def evaluate_cycle64_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """One row per firing Cycle 64 equation at `check_time_utc`."""
    check = pd.Timestamp(check_time_utc)
    if check.tzinfo is not None:
        check = check.tz_convert('UTC').tz_localize(None)
    if check.hour not in CYCLE64_CHECK_HOURS or check.minute != 30:
        return pd.DataFrame()
    sig_stamp = check - pd.Timedelta(hours=1, minutes=30)
    ent_stamp = check - pd.Timedelta(minutes=30)
    out = []
    for eq in CYCLE64_EQUATIONS:
        if eq['hour'] != check.hour:
            continue
        sym = eq['symbol']
        df = frames.get(sym)
        if df is None or not len(df):
            continue
        ff = df.copy()
        ff.index = pd.to_datetime(ff.index)
        if ff.index.tz is not None:
            ff.index = ff.index.tz_convert('UTC').tz_localize(None)
        if ent_stamp not in ff.index:
            continue
        pos = ff.index.get_indexer([sig_stamp])[0]
        if pos < 0:
            continue
        feat = _symbol_feat(ff.reset_index(drop=True))
        row = feat.iloc[pos]
        atr = float(row['atr14'])
        if not np.isfinite(atr) or atr <= 0:
            continue
        if not _cond_ok(row, eq['conditions']):
            continue
        direction = eq['direction']
        if direction == 'TREND':
            mom = float(row['mom24'])
            if not np.isfinite(mom):
                continue
            direction = 'BUY' if mom > 0 else 'SELL'
        pip = _pip_size(sym)
        atr_pips = atr / pip
        out.append({
            'check': check, 'symbol': sym, 'equation': eq['id'],
            'direction': direction, 'score': float(eq['score']),
            'atr_pips': atr_pips,
            'entry_px': float(ff.loc[ent_stamp, 'Open']),
            'tp_pips': float(np.clip(eq['tp_mult'] * atr_pips, 10.0, 500.0)),
            'sl_pips': float(np.clip(eq['sl_mult'] * atr_pips, 5.0, 100.0)),
            'signal_candle': sig_stamp, 'entry_candle': ent_stamp,
        })
    return pd.DataFrame(out)


def select_cycle64_entries(signals: pd.DataFrame,
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
    return pd.DataFrame(out).reset_index(drop=True) if out else signals.iloc[0:0]


def is_cycle64_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE64_CHECK_HOURS and t.minute == 30
