"""Cycle 69 (C69-07) -- October H1 system, PROMOTED BY MUSE'S
DECISION 2026-10-21 under the user's standing rule (promote the
best system meeting the middle-enough-confidence standard;
Cycle 69 verdict itself: NO_IMPROVEMENT on the formal gates).

R4A01's 24 equations verbatim (Cycle 24: 15 mined mom24 legs +
9 TREND fallbacks) plus 9 fresh "tail-penalised" legs from
families new to this program -- Laguerre RSI + Zero-Lag EMA
combos, WaveTrend zones, Stochastic RSI crosses and a Rainbow
ribbon calm-trend leg. Fresh scores sit in the same 1000.x band,
so the legs compete for the top-1 pick (131 of 594 discovery
picks changed; 101 fresh discovery trades). Checks 15:00 /
17:00 / 18:00 UTC (21:30 / 23:30 / 00:30 MMT), exactly 1
entry/check, 48h cap, TP/SL = mult x ATR14 clipped to
[10, 500] / [5, 100] pips. TREND fallbacks follow mom24 sign.

Why this system: it beats R4A01 on EVERY unseen measure --
net@2.5 +305.3 vs +223.0 pips, win 92.75%, leftover 47.7% vs
42.8%, weak 3 vs 8, checks 10/12, sizing PASS -- and on
discovery net +1,658.4 vs +792.5 with 1/9 red Octobers vs 4/9.
Paired LCT P = 100.00%, but its own 5th-percentile leftover is
8.90% (< the 20% middle bar), so the formal LCT-middle gate
failed; the round's only full-LCT passer (C69-10) lost money
unseen (-47.6), which is a standing red line. NOTE: this module
is the APP default for October only -- the live signal crons
keep running R4A01 unchanged.

Feature formulas reproduce work_c69/scripts/c69_prep.py
fresh_features verbatim (Laguerre RSI gamma 0.8 recursion;
ZLEMA 24 with lag 11; WaveTrend ESA10/DEMA10/EMA21; Stochastic
RSI on Wilder RSI14 with SMA3/SMA3; Rainbow = SMAs 5..30 step
5). Features are computed on the signal candle (check - 1h30m).
Several fresh legs share identical conditions AND scores with
different exits (tail-penalised variants); equation order is
preserved and selection is a stable sort, exactly as mined.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE69_CHECK_HOURS = (15, 17, 18)
CYCLE69_EQUATIONS = (
{"id": 'mom_EURUSD_h15_momS_T0.75_A1.0_0.3x8', "symbol": 'EURUSD', "hour": 15, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1000.189},
    {"id": 'mom_EURGBP_h15_momB_T0.75_A1.0_0.3x8', "symbol": 'EURGBP', "hour": 15, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1000.171},
    {"id": 'mom_CHFJPY_h15_momS_T2.5_A1.0_0.3x8', "symbol": 'CHFJPY', "hour": 15, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1000.1709999999999},
    {"id": 'mom_EURJPY_h15_momS_T0.75_A0.9_0.3x5', "symbol": 'EURJPY', "hour": 15, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 1000.153},
    {"id": 'mom_USDJPY_h17_momB_T0.75_A1.0_0.3x10', "symbol": 'USDJPY', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 10.0, "score": 1000.1709999999999},
    {"id": 'mom_EURNZD_h17_momS_T2.5_A1.0_0.3x8', "symbol": 'EURNZD', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1000.135},
    {"id": 'mom_GBPJPY_h17_momS_T0.75_A1.0_0.3x3', "symbol": 'GBPJPY', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 3.0, "score": 952.495088095238},
    {"id": 'mom_AUDJPY_h17_momS_T3.0_A1.0_0.3x8', "symbol": 'AUDJPY', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 3.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 941.2876705882352},
    {"id": 'mom_USDJPY_h18_momS_T2.5_A1.0_0.3x3', "symbol": 'USDJPY', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 3.0, "score": 1000.216},
    {"id": 'mom_GBPJPY_h18_momS_T0.75_A1.0_0.3x8', "symbol": 'GBPJPY', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1000.20554},
    {"id": 'mom_EURCHF_h18_momS_T0.75_A1.0_0.3x5', "symbol": 'EURCHF', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 1000.18},
    {"id": 'mom_EURCAD_h18_momB_T0.75_A1.0_0.3x8', "symbol": 'EURCAD', "hour": 18, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1000.153},
    {"id": 'FB_EURUSD_h15_0', "symbol": 'EURUSD', "hour": 15, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 3.0, "score": -1000000001.0},
    {"id": 'FB_GBPUSD_h15_1', "symbol": 'GBPUSD', "hour": 15, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 3.0, "score": -1000000002.0},
    {"id": 'FB_USDJPY_h17_0', "symbol": 'USDJPY', "hour": 17, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 3.0, "score": -1000000003.0},
    {"id": 'FB_AUDUSD_h17_1', "symbol": 'AUDUSD', "hour": 17, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 3.0, "score": -1000000004.0},
    {"id": 'FB_EURJPY_h18_0', "symbol": 'EURJPY', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 3.0, "score": -1000000005.0},
    {"id": 'FB_GBPJPY_h18_1', "symbol": 'GBPJPY', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 3.0, "score": -1000000006.0},
    {"id": 'mom_USDJPY_h18_momS_T2.5_A1.0_0.3x5', "symbol": 'USDJPY', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 1000.216},
    {"id": 'mom_USDJPY_h18_momS_T2.5_A1.0_0.3x8', "symbol": 'USDJPY', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1000.216},
    {"id": 'mom_USDJPY_h18_momS_T2.5_A1.0_0.3x10', "symbol": 'USDJPY', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 10.0, "score": 1000.216},
    {"id": 'mom_GBPJPY_h18_momS_T0.75_A1.0_0.3x3', "symbol": 'GBPJPY', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 3.0, "score": 1000.20554},
    {"id": 'mom_GBPJPY_h18_momS_T0.75_A1.0_0.3x5', "symbol": 'GBPJPY', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 1000.20554},
    {"id": 'mom_GBPJPY_h18_momS_T0.75_A1.0_0.3x10', "symbol": 'GBPJPY', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 10.0, "score": 1000.20554},
    {"id": 'RBW_rbw_calm_CHFJPY_h18_SELL_0.75x8.0', "symbol": 'CHFJPY', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'rbw_d', "op": '<', "val": -0.3},
     {"col": 'rbw_sp', "op": '<', "val": 1.2}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.5154910714285},
    {"id": 'COMBO_lag_zle_EURJPY_h17_BUY_0.5x8.0', "symbol": 'EURJPY', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'lag_rsi', "op": '>', "val": 0.5},
     {"col": 'zle_d', "op": '>', "val": 0.2}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.5082392857142},
    {"id": 'WT_wt_zone_EURJPY_h17_BUY_0.5x8.0', "symbol": 'EURJPY', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'wt_1', "op": '>', "val": 30.0},
     {"col": 'wt_s2', "op": '>', "val": 0.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.4674285714285},
    {"id": 'COMBO_lag_zle_EURJPY_h17_BUY_0.3x8.0', "symbol": 'EURJPY', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'lag_rsi', "op": '>', "val": 0.5},
     {"col": 'zle_d', "op": '>', "val": 0.2}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1000.4011278571428},
    {"id": 'COMBO_lag_zle_EURJPY_h17_BUY_0.3x10.0', "symbol": 'EURJPY', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'lag_rsi', "op": '>', "val": 0.5},
     {"col": 'zle_d', "op": '>', "val": 0.2}],
     "tp_mult": 0.3, "sl_mult": 10.0, "score": 1000.4011278571428},
    {"id": 'WT_wt_zone_EURJPY_h17_BUY_0.3x8.0', "symbol": 'EURJPY', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'wt_1', "op": '>', "val": 30.0},
     {"col": 'wt_s2', "op": '>', "val": 0.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1000.3711278571428},
    {"id": 'WT_wt_zone_EURJPY_h17_BUY_0.3x10.0', "symbol": 'EURJPY', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'wt_1', "op": '>', "val": 30.0},
     {"col": 'wt_s2', "op": '>', "val": 0.0}],
     "tp_mult": 0.3, "sl_mult": 10.0, "score": 1000.3711278571428},
    {"id": 'SRS_srs_x_EURJPY_h17_BUY_1.0x8.0', "symbol": 'EURJPY', "hour": 17, "direction": 'BUY',
     "conditions": [{"col": 'srs_xup', "op": '>', "val": 0.5}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1000.3603142857143},
    {"id": 'RBW_rbw_calm_CHFJPY_h18_SELL_0.5x5.0', "symbol": 'CHFJPY', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'rbw_d', "op": '<', "val": -0.3},
     {"col": 'rbw_sp', "op": '<', "val": 1.2}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.3601321428571},
)


def _ema_s(x: pd.Series, span: int) -> pd.Series:
    return x.ewm(span=span, min_periods=span, adjust=False).mean()


def _laguerre_rsi(C: np.ndarray, gamma: float) -> np.ndarray:
    n = len(C)
    L0 = L1 = L2 = L3 = 0.0
    out = np.full(n, np.nan)
    g = gamma
    for t in range(n):
        p = C[t]
        if not np.isfinite(p):
            continue
        if t == 0:
            L0 = L1 = L2 = L3 = p
        nL0 = (1 - g) * p + g * L0
        nL1 = -g * nL0 + L0 + g * L1
        nL2 = -g * nL1 + L1 + g * L2
        nL3 = -g * nL2 + L2 + g * L3
        L0, L1, L2, L3 = nL0, nL1, nL2, nL3
        cu = cd = 0.0
        for a, b in ((L0, L1), (L1, L2), (L2, L3)):
            if a > b:
                cu += a - b
            else:
                cd += b - a
        out[t] = cu / (cu + cd) if (cu + cd) > 0 else 0.5
    return out


def _symbol_feat(df: pd.DataFrame) -> pd.DataFrame:
    f = add_cycle12_features(df)
    O, H, L, C = f['Open'], f['High'], f['Low'], f['Close']
    atrs = f['atr14'].replace(0.0, np.nan)
    Cv = C.to_numpy(dtype=float)
    # Laguerre RSI (gamma 0.8).
    f['lag_rsi'] = pd.Series(_laguerre_rsi(Cv, 0.8), index=f.index)
    # Zero-Lag EMA 24 (lag 11).
    lag = (24 - 1) // 2
    z24 = _ema_s(2.0 * C - C.shift(lag), 24)
    f['zle_d'] = (C - z24) / atrs
    # Stochastic RSI (Wilder RSI14, stoch 14, SMA3 / SMA3).
    delta = C.diff()
    ag = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14,
                                 adjust=False).mean()
    al = (-delta.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14,
                                    adjust=False).mean()
    rsi = 100.0 - 100.0 / (1.0 + ag / al.replace(0.0, np.nan))
    lo = rsi.rolling(14, min_periods=14).min()
    hi = rsi.rolling(14, min_periods=14).max()
    raw = (rsi - lo) / (hi - lo).replace(0.0, np.nan) * 100.0
    k = raw.rolling(3, min_periods=3).mean()
    dd = k.rolling(3, min_periods=3).mean()
    f['srs_xup'] = ((k > dd) & (k.shift(1) <= dd.shift(1))).astype(float)
    # WaveTrend.
    tp = (H + L + C) / 3.0
    esa = _ema_s(tp, 10)
    dev = _ema_s((tp - esa).abs(), 10)
    ci = (tp - esa) / (0.015 * dev).replace(0.0, np.nan)
    wt1 = _ema_s(ci, 21)
    f['wt_1'] = wt1
    f['wt_s2'] = wt1 - wt1.shift(2)
    # Rainbow ribbon (SMAs 5,10,...,30).
    smas = [C.rolling(n, min_periods=n).mean() for n in (5, 10, 15, 20, 25, 30)]
    mid = sum(smas) / 6.0
    spread = (pd.concat(smas, axis=1).max(axis=1)
              - pd.concat(smas, axis=1).min(axis=1))
    f['rbw_d'] = (C - mid) / atrs
    f['rbw_sp'] = spread / atrs
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


def evaluate_cycle69_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """One row per firing Cycle 69 equation at `check_time_utc`."""
    check = pd.Timestamp(check_time_utc)
    if check.tzinfo is not None:
        check = check.tz_convert('UTC').tz_localize(None)
    if check.hour not in CYCLE69_CHECK_HOURS or check.minute != 30:
        return pd.DataFrame()
    sig_stamp = check - pd.Timedelta(hours=1, minutes=30)
    ent_stamp = check - pd.Timedelta(minutes=30)
    out = []
    for eq in CYCLE69_EQUATIONS:
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


def select_cycle69_entries(signals: pd.DataFrame,
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


def is_cycle69_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE69_CHECK_HOURS and t.minute == 30
