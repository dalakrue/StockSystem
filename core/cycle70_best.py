"""Cycle 70 (C70-07) -- November H1 system, PROMOTED BY USER OVERRIDE
2026-10-21 in the LCT-fix round (Cycle 70 verdict itself:
NO_IMPROVEMENT on the unseen Priority-1 gates).

A genuinely fresh assembly (NOT incumbent + legs): 24 per-symbol
equations mined end-to-end from four indicator families that had
never been used in this program -- Ehlers Cyber Cycle / Bandpass
(CYB/BP), True Strength Index (TSI), Random Walk Index (RWI) --
scored by RoMAD with "wideB" exits, plus 9 TREND fallbacks.
Checks 09:00 / 13:00 / 15:00 UTC (16:00 / 20:00 / 22:00 MMT),
exactly 1 entry/check, top-1 across symbols by score, 48h cap,
TP/SL = mult x ATR14 clipped to [10, 500] / [5, 100] pips.
Direction for TREND fallbacks follows mom24 sign (BUY if > 0).

Why it was promoted despite failing the unseen leftover gate: its
DISCOVERY record is the strongest in the round -- net@2.5 +5,580.8
pips over 585 trades, 0/9 red year-blocks, discovery leftover
55.74% -- and it passed the Leftover Confidence Test against
C51-20 at BOTH levels (paired P 99.33%, 5th-percentile 42.22%).
Unseen November 2025: net@2.5 +268.2 pips, win 85.00%, 3.00
entries/day, leftover 31.49%, weak 4 (tied C51-20's 4).

Ehlers recursion (Cyber Cycle alpha 0.07; Bandpass period 20,
bandwidth 0.3), TSI double-smoothed momentum (25/13, signal 7)
and RWI (14-bar, ATR-normalised) reproduce
work_c70/scripts/c70_engine.py add_features verbatim. Features
are computed on the signal candle (check - 1h30m).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE70_CHECK_HOURS = (9, 13, 15)
CYCLE70_EQUATIONS = (
{"id": 'RWI_rwi_trd_B_USDCHF_h9_1.5x7.0_H48', "symbol": 'USDCHF', "hour": 9, "direction": 'BUY',
     "conditions": [
     {"col": 'rwi_diff', "op": '>', "val": 0.4},
     {"col": 'rwi_max', "op": '>', "val": 1.0}],
     "tp_mult": 1.5, "sl_mult": 7.0, "score": 944.6121751534008},
    {"id": 'BP_bp_pos_S_AUDCAD_h9_1.1x6.0_H48', "symbol": 'AUDCAD', "hour": 9, "direction": 'SELL',
     "conditions": [{"col": 'bp_atr', "op": '<', "val": -0.15}],
     "tp_mult": 1.1, "sl_mult": 6.0, "score": 629.2149607074462},
    {"id": 'CYB_cyb_x_B_EURAUD_h9_1.5x7.0_H48', "symbol": 'EURAUD', "hour": 9, "direction": 'BUY',
     "conditions": [{"col": 'cyber_x', "op": '>', "val": 0.5}],
     "tp_mult": 1.5, "sl_mult": 7.0, "score": 540.6867931968637},
    {"id": 'RWI_rwi_trd_B_AUDUSD_h9_2.0x8.0_H48', "symbol": 'AUDUSD', "hour": 9, "direction": 'BUY',
     "conditions": [
     {"col": 'rwi_diff', "op": '>', "val": 0.4},
     {"col": 'rwi_max', "op": '>', "val": 1.0}],
     "tp_mult": 2.0, "sl_mult": 8.0, "score": 453.82169926829346},
    {"id": 'CYB_cyb_x_S_EURNZD_h9_1.5x7.0_H48', "symbol": 'EURNZD', "hour": 9, "direction": 'SELL',
     "conditions": [{"col": 'cyber_x', "op": '<', "val": -0.5}],
     "tp_mult": 1.5, "sl_mult": 7.0, "score": 409.02487224994235},
    {"id": 'CYB_cyb_x_B_GBPUSD_h13_2.0x8.0_H48', "symbol": 'GBPUSD', "hour": 13, "direction": 'BUY',
     "conditions": [{"col": 'cyber_x', "op": '>', "val": 0.5}],
     "tp_mult": 2.0, "sl_mult": 8.0, "score": 781.1196862020851},
    {"id": 'BP_bp_pos_S_AUDCHF_h13_2.0x8.0_H48', "symbol": 'AUDCHF', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": 'bp_atr', "op": '<', "val": -0.15}],
     "tp_mult": 2.0, "sl_mult": 8.0, "score": 770.8965462824918},
    {"id": 'CYB_cyb_x_S_USDCHF_h13_2.0x8.0_H48', "symbol": 'USDCHF', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": 'cyber_x', "op": '<', "val": -0.5}],
     "tp_mult": 2.0, "sl_mult": 8.0, "score": 598.1818139820724},
    {"id": 'RWI_rwi_str_S_EURNZD_h13_1.5x7.0_H48', "symbol": 'EURNZD', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": 'rwi_diff', "op": '<', "val": -0.8}],
     "tp_mult": 1.5, "sl_mult": 7.0, "score": 479.06819900977837},
    {"id": 'CYB_cyb_x_S_EURAUD_h13_1.5x7.0_H48', "symbol": 'EURAUD', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": 'cyber_x', "op": '<', "val": -0.5}],
     "tp_mult": 1.5, "sl_mult": 7.0, "score": 435.80997071654394},
    {"id": 'TSI_tsi_zone_S_AUDCAD_h15_1.1x6.0_H48', "symbol": 'AUDCAD', "hour": 15, "direction": 'SELL',
     "conditions": [
     {"col": 'tsi', "op": '<', "val": -5.0},
     {"col": 'tsi_diff', "op": '<', "val": 0.0}],
     "tp_mult": 1.1, "sl_mult": 6.0, "score": 796.622286193513},
    {"id": 'CYB_cyb_pos_S_EURNZD_h15_1.1x6.0_H48', "symbol": 'EURNZD', "hour": 15, "direction": 'SELL',
     "conditions": [{"col": 'cyber_atr', "op": '<', "val": -0.1}],
     "tp_mult": 1.1, "sl_mult": 6.0, "score": 646.0680781236132},
    {"id": 'CYB_cyb_x_S_AUDUSD_h15_1.5x7.0_H48', "symbol": 'AUDUSD', "hour": 15, "direction": 'SELL',
     "conditions": [{"col": 'cyber_x', "op": '<', "val": -0.5}],
     "tp_mult": 1.5, "sl_mult": 7.0, "score": 574.646986384907},
    {"id": 'CYB_cyb_x_S_AUDNZD_h15_1.1x6.0_H48', "symbol": 'AUDNZD', "hour": 15, "direction": 'SELL',
     "conditions": [{"col": 'cyber_x', "op": '<', "val": -0.5}],
     "tp_mult": 1.1, "sl_mult": 6.0, "score": 536.5936040573517},
    {"id": 'RWI_rwi_str_S_USDCHF_h15_1.5x7.0_H48', "symbol": 'USDCHF', "hour": 15, "direction": 'SELL',
     "conditions": [{"col": 'rwi_diff', "op": '<', "val": -0.8}],
     "tp_mult": 1.5, "sl_mult": 7.0, "score": 511.7081602181903},
    {"id": 'FB_EURUSD_h9_0', "symbol": 'EURUSD', "hour": 9, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.6, "sl_mult": 8.0, "score": -1000000001.0},
    {"id": 'FB_GBPUSD_h9_1', "symbol": 'GBPUSD', "hour": 9, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.45, "sl_mult": 7.0, "score": -1000000002.0},
    {"id": 'FB_USDJPY_h9_2', "symbol": 'USDJPY', "hour": 9, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.45, "sl_mult": 8.0, "score": -1000000003.0},
    {"id": 'FB_AUDUSD_h13_0', "symbol": 'AUDUSD', "hour": 13, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.6, "sl_mult": 7.0, "score": -1000000004.0},
    {"id": 'FB_EURJPY_h13_1', "symbol": 'EURJPY', "hour": 13, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 7.0, "score": -1000000005.0},
    {"id": 'FB_GBPJPY_h13_2', "symbol": 'GBPJPY', "hour": 13, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000006.0},
    {"id": 'FB_AUDJPY_h15_0', "symbol": 'AUDJPY', "hour": 15, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 6.0, "score": -1000000007.0},
    {"id": 'FB_NZDUSD_h15_1', "symbol": 'NZDUSD', "hour": 15, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.6, "sl_mult": 8.0, "score": -1000000008.0},
    {"id": 'FB_EURCHF_h15_2', "symbol": 'EURCHF', "hour": 15, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.6, "sl_mult": 8.0, "score": -1000000009.0},
)


def _ehlers_filters(cl: np.ndarray):
    """Cyber Cycle (alpha=0.07) and Bandpass (P=20, BW=0.3)."""
    x = np.asarray(cl, dtype=float)
    n = len(x)
    sm = np.full(n, np.nan)
    xs = np.convolve(np.nan_to_num(x), [1, 2, 2, 1], mode='full')[:n] / 6.0
    sm[3:] = xs[3:]
    a = 0.07
    cyc = np.zeros(n)
    bp = np.zeros(n)
    beta = np.cos(2.0 * np.pi / 20.0)
    gamma = 1.0 / np.cos(2.0 * np.pi * 0.3 / 20.0)
    abp = gamma - np.sqrt(max(gamma * gamma - 1.0, 0.0))
    s = np.nan_to_num(sm)
    for i in range(2, n):
        cyc[i] = ((1 - 0.5 * a) ** 2 * (s[i] - 2 * s[i - 1] + s[i - 2])
                  + 2 * (1 - a) * cyc[i - 1] - (1 - a) ** 2 * cyc[i - 2])
        bp[i] = (0.5 * (1 - abp) * (x[i] - x[i - 2])
                 + beta * (1 + abp) * bp[i - 1] - abp * bp[i - 2])
    return cyc, bp


def _symbol_feat(df: pd.DataFrame) -> pd.DataFrame:
    f = add_cycle12_features(df)
    cl = f['Close']
    atr = f['atr14'].replace(0.0, np.nan)
    cyc, bp = _ehlers_filters(cl.to_numpy(dtype=float))
    f['cyber_atr'] = pd.Series(cyc, index=f.index) / atr
    f['cyber_x'] = np.where(
        (np.roll(cyc, 1) <= np.roll(cyc, 2)) & (cyc > np.roll(cyc, 1)), 1.0,
        np.where((np.roll(cyc, 1) >= np.roll(cyc, 2))
                 & (cyc < np.roll(cyc, 1)), -1.0, 0.0))
    f['cyber_x'] = f['cyber_x'].copy()
    f.iloc[:3, f.columns.get_loc('cyber_x')] = 0.0
    f['bp_atr'] = pd.Series(bp, index=f.index) / atr
    # TSI: double-smoothed momentum (25/13), signal EMA 7.
    mom = cl.diff()
    num = (mom.ewm(span=25, min_periods=25, adjust=False).mean()
           .ewm(span=13, min_periods=13, adjust=False).mean())
    den = (mom.abs().ewm(span=25, min_periods=25, adjust=False).mean()
           .ewm(span=13, min_periods=13, adjust=False).mean())
    tsi = 100.0 * num / den.replace(0.0, np.nan)
    tsig = tsi.ewm(span=7, min_periods=7, adjust=False).mean()
    f['tsi'] = tsi
    f['tsi_diff'] = tsi - tsig
    # Random Walk Index (14).
    sq = np.sqrt(14.0)
    f['rwi_hi'] = (f['High'] - f['Low'].shift(14)) / (atr * sq)
    f['rwi_lo'] = (f['High'].shift(14) - f['Low']) / (atr * sq)
    f['rwi_diff'] = f['rwi_hi'] - f['rwi_lo']
    f['rwi_max'] = np.maximum(f['rwi_hi'], f['rwi_lo'])
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


def evaluate_cycle70_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """One row per firing Cycle 70 equation at `check_time_utc`."""
    check = pd.Timestamp(check_time_utc)
    if check.tzinfo is not None:
        check = check.tz_convert('UTC').tz_localize(None)
    if check.hour not in CYCLE70_CHECK_HOURS or check.minute != 30:
        return pd.DataFrame()
    sig_stamp = check - pd.Timedelta(hours=1, minutes=30)
    ent_stamp = check - pd.Timedelta(minutes=30)
    out = []
    for eq in CYCLE70_EQUATIONS:
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


def select_cycle70_entries(signals: pd.DataFrame,
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


def is_cycle70_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE70_CHECK_HOURS and t.minute == 30
