"""Cycle 60 (C60-03) -- January H1 system, PROMOTED BY MUSE'S
DECISION 2026-10-21 under the user's standing rule (Cycle 60
verdict itself: NO_IMPROVEMENT on the formal gates).

The 24 incumbent equations (C28-30's mined legs + TREND
fallbacks, carried through C52-04's WINNER.json verbatim)
walked PLAIN by score -- note the Cycle 52 H012 rerank layer
is NOT part of this system; the Cycle 60 harness assembled it
without the rerank -- plus 8 fresh "compete" legs: GMMA
squeeze, TSF trend and Tillson T3 legs, every fresh leg scored
at a flat 1095.0 so it competes just above the incumbent mined
band (sibling exit variants share the score; equation order
decides, exactly as mined). Checks 11:00 / 13:00 / 17:00 UTC
(18:00 / 20:00 / 00:00 MMT), exactly 1 entry/check, 48h cap,
TP/SL = mult x ATR14 clipped to [10, 500] / [5, 100] pips.
TREND fallbacks follow mom24 sign.

Why this system: it passes every standard gate -- unseen
net@2.5 +335.4 pips, leftover 62.3%, weak 5 -> 1, checks
11/12, sizing PASS, discovery healthy with 0 red Januaries --
and its paired LCT P is 98.15%; only its own 5th-percentile
leftover (12.81%) misses the 20% middle bar. The round's three
full-LCT passers all failed the unseen month, which is a
standing red line, so C60-03 is the best admissible system.

Feature formulas reproduce work_c60/scripts/c60_prep.py and
c60_prep2.py verbatim (GMMA short/long EMA groups and short-
group width; 14-bar OLS Time Series Forecast oscillator;
Tillson T3 with a = 0.7, n = 5). Features are computed on the
signal candle (check - 1h30m).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE60_CHECK_HOURS = (11, 13, 17)
CYCLE60_EQUATIONS = (
{"id": 'mom_USDCAD_h11_momS_T2.5_A1.0_1.25x8', "symbol": 'USDCAD', "hour": 11, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 971.8205553571429},
    {"id": 'mom_EURGBP_h11_momS_T1.5_A1.0_1.25x8', "symbol": 'EURGBP', "hour": 11, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 970.8838388655463},
    {"id": 'mom_AUDUSD_h11_momS_T0.75_A0.9_1.25x5', "symbol": 'AUDUSD', "hour": 11, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 956.7476409161492},
    {"id": 'mom_GBPUSD_h11_momB_T2.0_A1.0_0.5x8', "symbol": 'GBPUSD', "hour": 11, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -2.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 944.5815373015873},
    {"id": 'mom_AUDNZD_h11_momS_T0.75_A1.0_1.0x8', "symbol": 'AUDNZD', "hour": 11, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 914.475957142857},
    {"id": 'mom_AUDNZD_h13_momS_T0.75_A1.0_1.0x5', "symbol": 'AUDNZD', "hour": 13, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 5.0, "score": 967.9883426267281},
    {"id": 'mom_AUDUSD_h13_momS_T0.75_A1.0_0.75x8', "symbol": 'AUDUSD', "hour": 13, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 967.9528176267281},
    {"id": 'mom_USDCAD_h13_momS_T2.5_A1.0_0.75x8', "symbol": 'USDCAD', "hour": 13, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 966.8598488095238},
    {"id": 'mom_EURUSD_h13_momB_T1.0_A1.0_1.0x8', "symbol": 'EURUSD', "hour": 13, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 961.3261422969189},
    {"id": 'mom_EURGBP_h13_momS_T2.5_A1.0_1.25x8', "symbol": 'EURGBP', "hour": 13, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 954.7206634740261},
    {"id": 'mom_AUDNZD_h17_momS_T1.0_A1.0_0.75x5', "symbol": 'AUDNZD', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.2548767857143},
    {"id": 'mom_USDJPY_h17_momB_T0.75_A1.0_0.75x8', "symbol": 'USDJPY', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 950.1085375},
    {"id": 'mom_NZDCAD_h17_momS_T0.75_A1.0_0.3x5', "symbol": 'NZDCAD', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 888.9328531746031},
    {"id": 'FB_EURUSD_h11_0', "symbol": 'EURUSD', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 8.0, "score": -1000000001.0},
    {"id": 'FB_GBPUSD_h11_1', "symbol": 'GBPUSD', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 10.0, "score": -1000000002.0},
    {"id": 'FB_USDJPY_h11_2', "symbol": 'USDJPY', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 8.0, "score": -1000000003.0},
    {"id": 'FB_AUDUSD_h13_0', "symbol": 'AUDUSD', "hour": 13, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 10.0, "score": -1000000004.0},
    {"id": 'FB_NZDUSD_h13_1', "symbol": 'NZDUSD', "hour": 13, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000005.0},
    {"id": 'FB_USDCAD_h13_2', "symbol": 'USDCAD', "hour": 13, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 10.0, "score": -1000000006.0},
    {"id": 'FB_EURGBP_h17_0', "symbol": 'EURGBP', "hour": 17, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000007.0},
    {"id": 'FB_USDCHF_h17_1', "symbol": 'USDCHF', "hour": 17, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 10.0, "score": -1000000008.0},
    {"id": 'FB_EURUSD_h17_2', "symbol": 'EURUSD', "hour": 17, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 10.0, "score": -1000000009.0},
    {"id": 'mom_AUDNZD_h17_momS_T1.0_A1.0_0.75x8', "symbol": 'AUDNZD', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.2548767857143},
    {"id": 'mom_AUDNZD_h17_momS_T1.0_A1.0_0.3x5', "symbol": 'AUDNZD', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 1000.252},
    {"id": 'GMMA_gmma_sqz_GBPJPY_h17_BUY_0.3x5.0', "symbol": 'GBPJPY', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'gmma_width', "op": '<', "val": 0.35},
     {"col": 'gmma_diff', "op": '>', "val": 0.1}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 1095.0},
    {"id": 'GMMA_gmma_sqz_GBPJPY_h17_BUY_0.3x8.0', "symbol": 'GBPJPY', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'gmma_width', "op": '<', "val": 0.35},
     {"col": 'gmma_diff', "op": '>', "val": 0.1}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1095.0},
    {"id": 'TSF_tsf_tr_USDCAD_h17_BUY_0.3x5.0', "symbol": 'USDCAD', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'tsf', "op": '>', "val": 0.05},
     {"col": 'tsf_slope', "op": '>', "val": 0.0}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 1095.0},
    {"id": 'TSF_tsf_tr_USDCAD_h17_BUY_0.3x8.0', "symbol": 'USDCAD', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'tsf', "op": '>', "val": 0.05},
     {"col": 'tsf_slope', "op": '>', "val": 0.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1095.0},
    {"id": 'T3_t3_tr2_AUDJPY_h13_SELL_0.3x5.0', "symbol": 'AUDJPY', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": 't3_dist', "op": '<', "val": -0.8}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 1095.0},
    {"id": 'T3_t3_tr2_AUDJPY_h13_SELL_0.3x8.0', "symbol": 'AUDJPY', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": 't3_dist', "op": '<', "val": -0.8}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1095.0},
    {"id": 'T3_t3_tr2_AUDJPY_h13_SELL_0.5x5.0', "symbol": 'AUDJPY', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": 't3_dist', "op": '<', "val": -0.8}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1095.0},
    {"id": 'T3_t3_tr2_AUDJPY_h13_SELL_1.0x8.0', "symbol": 'AUDJPY', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": 't3_dist', "op": '<', "val": -0.8}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1095.0},
)


def _ema(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(span=n, min_periods=n, adjust=False).mean()


def _symbol_feat(df: pd.DataFrame) -> pd.DataFrame:
    f = add_cycle12_features(df)
    C = f['Close']
    atrs = f['atr14'].replace(0.0, np.nan)
    # GMMA groups.
    shorts = [_ema(C, n) for n in (3, 5, 8, 10, 12, 15)]
    longs = [_ema(C, n) for n in (30, 35, 40, 45, 50, 60)]
    ms = sum(shorts) / len(shorts)
    ml = sum(longs) / len(longs)
    f['gmma_diff'] = (ms - ml) / atrs
    f['gmma_width'] = (pd.concat(shorts, axis=1).max(axis=1)
                       - pd.concat(shorts, axis=1).min(axis=1)) / atrs
    # TSF oscillator (14-bar OLS, 1-step forecast).
    w = 14
    Sx = w * (w - 1) / 2.0
    Sxx = w * (w - 1) * (2 * w - 1) / 6.0
    idx = pd.Series(np.arange(len(f), dtype=float), index=f.index)
    Sy = C.rolling(w).sum()
    Sty = (C * idx).rolling(w).sum()
    start = idx - (w - 1)
    Sxy = Sty - start * Sy
    slope = (w * Sxy - Sx * Sy) / (w * Sxx - Sx * Sx)
    intercept = (Sy - slope * Sx) / w - slope * start
    forecast = intercept + slope * (idx + 1.0)
    f['tsf'] = (forecast - C) / atrs
    f['tsf_slope'] = slope / atrs
    # Tillson T3 (a = 0.7, n = 5).
    a = 0.7
    e1 = _ema(C, 5)
    e2 = _ema(e1, 5)
    e3 = _ema(e2, 5)
    e4 = _ema(e3, 5)
    e5 = _ema(e4, 5)
    e6 = _ema(e5, 5)
    t3 = (-(a ** 3) * e6 + (3 * a ** 2 + 3 * a ** 3) * e5
          + (-6 * a ** 2 - 3 * a - 3 * a ** 3) * e4
          + (1 + 3 * a + a ** 3 + 3 * a ** 2) * e3)
    f['t3_dist'] = (C - t3) / atrs
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


def evaluate_cycle60_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """One row per firing Cycle 60 equation at `check_time_utc`."""
    check = pd.Timestamp(check_time_utc)
    if check.tzinfo is not None:
        check = check.tz_convert('UTC').tz_localize(None)
    if check.hour not in CYCLE60_CHECK_HOURS or check.minute != 30:
        return pd.DataFrame()
    sig_stamp = check - pd.Timedelta(hours=1, minutes=30)
    ent_stamp = check - pd.Timedelta(minutes=30)
    out = []
    for eq in CYCLE60_EQUATIONS:
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


def select_cycle60_entries(signals: pd.DataFrame,
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


def is_cycle60_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE60_CHECK_HOURS and t.minute == 30
