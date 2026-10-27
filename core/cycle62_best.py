"""Cycle 62 (C62-10) -- March H1 system, PROMOTED CLEANLY
2026-10-21 in the LCT-fix round (all Priority-1 gates + LCT).

C30-31's 24 equations walked PLAIN -- the Cycle 53 G013
rerank overlay is NOT part of this system -- plus 5 fresh legs
chosen by a maximin-year greedy search: return-skew (skew96),
Laguerre RSI (gamma 0.3) + Mass Index combos, a kurtosis-48
regime leg and an Elder Bear Power leg. The fresh legs carry
plain mining scores (203-649), below the mined legs' 1000.x
band, so they fire where the mined legs are silent but still
beat the TREND fallbacks. Checks 11:00 / 16:00 / 17:00 UTC
(18:00 / 23:00 / 00:00 MMT), exactly 1 entry/check, 48h cap,
TP/SL = mult x ATR14 clipped to [10, 500] / [5, 100] pips.
TREND fallbacks follow mom24 sign. (The research logs for
this cycle are stored at the 1.0-pip cost basis.)

Promotion record: LCT MIDDLE PASS vs C53-07 (paired P
96.74%, 5th-percentile 34.59%), discovery leftover 49.82%
(beats both ancestors: C30-31's 35.62% and C53-07's 28.64%),
0/9 red Marches, unseen net@2.5 +277.3 pips, leftover 52.21%,
weak 2 -> 0, checks 11/12, sizing PASS.

Feature formulas reproduce work_c62/scripts/c62_features.py
verbatim (Elder Bear Power vs EMA13; Mass Index = 25-bar sum
of the EMA9/EMA9-of-EMA9 true-range ratio, delta over 3 bars;
Laguerre RSI gamma 0.3; rolling skew-96 / excess kurtosis-48
of 1h log returns). Features are computed on the signal
candle (check - 1h30m).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE62_CHECK_HOURS = (11, 16, 17)
CYCLE62_EQUATIONS = (
{"id": 'mom_NZDCAD_h11_momB_T2.0_A0.9_1.0x8', "symbol": 'NZDCAD', "hour": 11, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -2.0},
     {"col": 'atr_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 970.9303924369748},
    {"id": 'mom_USDCHF_h11_momB_T2.5_A0.9_1.25x8', "symbol": 'USDCHF', "hour": 11, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -2.5},
     {"col": 'atr_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 913.2169889751552},
    {"id": 'mom_EURUSD_h11_momB_T2.0_A0.9_0.75x8', "symbol": 'EURUSD', "hour": 11, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -2.0},
     {"col": 'atr_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 911.8895987394958},
    {"id": 'mom_AUDNZD_h11_momS_T0.75_A1.0_0.75x8', "symbol": 'AUDNZD', "hour": 11, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 909.2657126623376},
    {"id": 'mom_USDCAD_h11_momB_T0.75_A0.9_0.5x8', "symbol": 'USDCAD', "hour": 11, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 906.2684392857142},
    {"id": 'mom_AUDNZD_h16_momS_T0.75_A1.0_0.5x8', "symbol": 'AUDNZD', "hour": 16, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.3960285714285},
    {"id": 'mom_NZDCAD_h16_momS_T1.0_A1.0_0.5x5', "symbol": 'NZDCAD', "hour": 16, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 965.7091199507389},
    {"id": 'mom_USDCAD_h16_momS_T1.0_A1.0_0.75x8', "symbol": 'USDCAD', "hour": 16, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 958.5618494047619},
    {"id": 'mom_NZDUSD_h16_momS_T2.5_A1.0_0.75x3', "symbol": 'NZDUSD', "hour": 16, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 3.0, "score": 904.8740690476191},
    {"id": 'mom_EURGBP_h16_momB_T0.75_A1.0_1.25x5', "symbol": 'EURGBP', "hour": 16, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 900.1055785714286},
    {"id": 'mom_NZDCAD_h17_momS_T0.75_A1.0_0.75x8', "symbol": 'NZDCAD', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 965.7696985221675},
    {"id": 'mom_AUDNZD_h17_momS_T0.75_A0.9_1.25x5', "symbol": 'AUDNZD', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 960.22975},
    {"id": 'mom_NZDUSD_h17_momB_T1.5_A1.0_1.25x8', "symbol": 'NZDUSD', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -1.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 909.3016465909091},
    {"id": 'mom_USDCAD_h17_momB_T1.5_A1.0_0.5x3', "symbol": 'USDCAD', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -1.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 3.0, "score": 900.0832964285714},
    {"id": 'mom_USDCHF_h17_momS_T1.0_A1.0_0.75x8', "symbol": 'USDCHF', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 857.2243839285713},
    {"id": 'FB_EURUSD_h11_0', "symbol": 'EURUSD', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000001.0},
    {"id": 'FB_GBPUSD_h11_1', "symbol": 'GBPUSD', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000002.0},
    {"id": 'FB_NZDUSD_h11_2', "symbol": 'NZDUSD', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 10.0, "score": -1000000003.0},
    {"id": 'FB_EURCHF_h16_0', "symbol": 'EURCHF', "hour": 16, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000004.0},
    {"id": 'FB_USDCAD_h16_1', "symbol": 'USDCAD', "hour": 16, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000005.0},
    {"id": 'FB_EURGBP_h16_2', "symbol": 'EURGBP', "hour": 16, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000006.0},
    {"id": 'FB_USDCHF_h17_0', "symbol": 'USDCHF', "hour": 17, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000007.0},
    {"id": 'FB_EURUSD_h17_1', "symbol": 'EURUSD', "hour": 17, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 5.0, "score": -1000000008.0},
    {"id": 'FB_GBPUSD_h17_2', "symbol": 'GBPUSD', "hour": 17, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000009.0},
    {"id": 'c62_CHFJPY_h11_S_100', "symbol": 'CHFJPY', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": 'kurt48', "op": '>', "val": 6.0}],
     "tp_mult": 0.75, "sl_mult": 3.0, "score": 234.78749999999735},
    {"id": 'c62_EURCHF_h11_S_308', "symbol": 'EURCHF', "hour": 11, "direction": 'SELL',
     "conditions": [
     {"col": 'bearp', "op": '<', "val": -1.0},
     {"col": 'mom24', "op": '>', "val": 0.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 203.86607142856704},
    {"id": 'c62_EURGBP_h16_S_251', "symbol": 'EURGBP', "hour": 16, "direction": 'SELL',
     "conditions": [
     {"col": 'lrsi_g3', "op": '>', "val": 0.9},
     {"col": 'mass_d3', "op": '>', "val": 0.15}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 310.87142857142896},
    {"id": 'c62_EURNZD_h16_B_233', "symbol": 'EURNZD', "hour": 16, "direction": 'BUY',
     "conditions": [{"col": 'skew96', "op": '<', "val": -0.4}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 648.9892857142833},
    {"id": 'c62_CHFJPY_h11_S_095', "symbol": 'CHFJPY', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": 'kurt48', "op": '<', "val": 0.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 208.39464285714342},
)


def _laguerre_rsi(close: np.ndarray, gamma: float) -> np.ndarray:
    n = len(close)
    out = np.full(n, np.nan)
    l0 = l1 = l2 = l3 = np.nan
    p0 = p1 = p2 = p3 = 0.0
    started = False
    for i in range(n):
        c = close[i]
        if not np.isfinite(c):
            continue
        if not started:
            l0 = l1 = l2 = l3 = c
            p0 = p1 = p2 = p3 = c
            started = True
        else:
            p0, p1, p2, p3 = l0, l1, l2, l3
            l0 = (1.0 - gamma) * c + gamma * p0
            l1 = -gamma * l0 + p0 + gamma * p1
            l2 = -gamma * l1 + p1 + gamma * p2
            l3 = -gamma * l2 + p2 + gamma * p3
        cu = max(l0 - l1, 0.0) + max(l1 - l2, 0.0) + max(l2 - l3, 0.0)
        cd = max(l1 - l0, 0.0) + max(l2 - l1, 0.0) + max(l3 - l2, 0.0)
        out[i] = cu / (cu + cd) if (cu + cd) > 0 else 0.5
    return out


def _symbol_feat(df: pd.DataFrame) -> pd.DataFrame:
    f = add_cycle12_features(df)
    O, H, L, C = f['Open'], f['High'], f['Low'], f['Close']
    atrs = f['atr14'].replace(0.0, np.nan)
    # Elder Bear Power (EMA13).
    ema13 = C.ewm(span=13, adjust=False, min_periods=13).mean()
    f['bearp'] = (L - ema13) / atrs
    # Mass Index delta-3.
    Cv = C.to_numpy(dtype=float)
    Hv = H.to_numpy(dtype=float)
    Lv = L.to_numpy(dtype=float)
    Cp = np.concatenate([[np.nan], Cv[:-1]])
    tr = np.maximum(Hv - Lv, np.maximum(np.abs(Hv - Cp), np.abs(Lv - Cp)))
    tr[0] = Hv[0] - Lv[0]
    trs = pd.Series(tr, index=f.index)
    e1 = trs.ewm(span=9, adjust=False, min_periods=9).mean()
    e2 = e1.ewm(span=9, adjust=False, min_periods=9).mean()
    ratio = e1 / e2.replace(0.0, np.nan)
    mass25 = ratio.rolling(25, min_periods=25).sum()
    f['mass_d3'] = mass25 - mass25.shift(3)
    # Laguerre RSI gamma 0.3.
    f['lrsi_g3'] = pd.Series(_laguerre_rsi(Cv, 0.3), index=f.index)
    # Rolling return moments.
    lr = np.log(C / C.shift(1))
    f['kurt48'] = lr.rolling(48, min_periods=48).kurt()
    f['skew96'] = lr.rolling(96, min_periods=96).skew()
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


def evaluate_cycle62_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """One row per firing Cycle 62 equation at `check_time_utc`."""
    check = pd.Timestamp(check_time_utc)
    if check.tzinfo is not None:
        check = check.tz_convert('UTC').tz_localize(None)
    if check.hour not in CYCLE62_CHECK_HOURS or check.minute != 30:
        return pd.DataFrame()
    sig_stamp = check - pd.Timedelta(hours=1, minutes=30)
    ent_stamp = check - pd.Timedelta(minutes=30)
    out = []
    for eq in CYCLE62_EQUATIONS:
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


def select_cycle62_entries(signals: pd.DataFrame,
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


def is_cycle62_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE62_CHECK_HOURS and t.minute == 30
