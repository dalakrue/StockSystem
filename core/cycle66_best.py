"""Cycle 66 (C66-08) -- July H1 system, PROMOTED CLEANLY
2026-10-21 in the LCT-fix round (all Priority-1 gates + LCT).

C34-17's 24 equations with ONE structural change plus 3 fresh
legs. The change: every TREND fallback now carries a Guppy
ribbon gate (gup_spread < 0 -- the fallback fires only when
the Guppy short/long EMA ribbon is in its downtrend
configuration). Research found the ungated fallback block was
-555.3 pips on discovery standalone (+159.9 with the ribbon
down vs -715.3 with it up), so the gate removes the toxic
half. The 3 fresh legs are all EURNZD h17: two Stochastic-RSI
overbought-reversion SELLs and one ZigZag breakout BUY,
scored in a 1600.x band so they take priority when they fire.
Checks 15:00 / 17:00 / 18:00 UTC (21:30 / 23:30 / 00:30 MMT),
exactly 1 entry/check, 48h cap, TP/SL = mult x ATR14 clipped
to [10, 500] / [5, 100] pips. TREND fallbacks follow mom24.

Promotion record: LCT MIDDLE PASS vs C34-17 (paired P 100%,
5th-percentile 39.96% -- strict missed by 0.04), discovery
leftover 31.27% -> 61.14%, discovery net +3,621.6, 0/9 red
Julys, unseen net@2.5 +477.7, leftover 61.2%, weak 4 -> 1,
sizing FAIL -> PASS.

Feature formulas reproduce work_c66/scripts/c66_prep.py
fresh_features verbatim: Guppy spread = (mean EMA 3/5/8/10/
12/15 - mean EMA 30/35/40/45/50/60) / ATR; Stochastic RSI =
14-bar stochastic of Wilder RSI14 (its slope is k - k.shift(2));
ZigZag confirmed swings use the causal 1.0xATR retracement
state machine, and zz_dhi = (last confirmed swing high -
Close) / ATR -- NOTE this sign convention is the opposite of
cycle63's zz_dhi. Features are computed on the signal candle
(check - 1h30m).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE66_CHECK_HOURS = (15, 17, 18)
CYCLE66_EQUATIONS = (
{"id": 'mom_AUDJPY_h15_momB_T0.75_A1.0_0.75x8', "symbol": 'AUDJPY', "hour": 15, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.2282839285714},
    {"id": 'mom_EURCAD_h15_momB_T0.75_A1.0_0.75x5', "symbol": 'EURCAD', "hour": 15, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 969.0159053571429},
    {"id": 'mom_AUDNZD_h15_momB_T0.75_A1.0_1.25x8', "symbol": 'AUDNZD', "hour": 15, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 964.5710035714286},
    {"id": 'mom_USDCAD_h15_momB_T1.5_A1.0_1.25x8', "symbol": 'USDCAD', "hour": 15, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -1.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 960.2759196428572},
    {"id": 'mom_EURAUD_h15_momS_T0.75_A1.0_1.0x2', "symbol": 'EURAUD', "hour": 15, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 2.0, "score": 958.730561904762},
    {"id": 'mom_CHFJPY_h17_momS_T0.75_A1.0_0.75x5', "symbol": 'CHFJPY', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.3781553571429},
    {"id": 'mom_AUDJPY_h17_momB_T0.75_A1.0_1.25x8', "symbol": 'AUDJPY', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1000.3319375},
    {"id": 'mom_AUDNZD_h17_momB_T0.75_A0.9_1.0x8', "symbol": 'AUDNZD', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1000.2557785714286},
    {"id": 'mom_EURAUD_h17_momB_T1.0_A1.0_0.5x8', "symbol": 'EURAUD', "hour": 17, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.2192},
    {"id": 'mom_USDJPY_h17_momS_T0.75_A1.0_1.25x5', "symbol": 'USDJPY', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 969.1712589285714},
    {"id": 'mom_EURAUD_h18_momS_T1.0_A1.0_0.75x5', "symbol": 'EURAUD', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.3750732142857},
    {"id": 'mom_AUDJPY_h18_momB_T0.75_A1.0_1.25x8', "symbol": 'AUDJPY', "hour": 18, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1000.3624821428572},
    {"id": 'mom_CHFJPY_h18_momS_T0.75_A1.0_0.75x8', "symbol": 'CHFJPY', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.3395553571429},
    {"id": 'mom_AUDNZD_h18_momS_T1.5_A1.0_0.75x3', "symbol": 'AUDNZD', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 3.0, "score": 1000.2915571428571},
    {"id": 'mom_EURNZD_h18_momB_T0.75_A1.0_0.3x8', "symbol": 'EURNZD', "hour": 18, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1000.2429999999999},
    {"id": 'FB_EURUSD_h15_0_G', "symbol": 'EURUSD', "hour": 15, "direction": 'TREND',
     "conditions": [{"col": 'gup_spread', "op": '<', "val": 0.0}],
     "tp_mult": 0.4, "sl_mult": 8.0, "score": -1000000001.0},
    {"id": 'FB_GBPUSD_h15_1_G', "symbol": 'GBPUSD', "hour": 15, "direction": 'TREND',
     "conditions": [{"col": 'gup_spread', "op": '<', "val": 0.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000002.0},
    {"id": 'FB_USDJPY_h15_2_G', "symbol": 'USDJPY', "hour": 15, "direction": 'TREND',
     "conditions": [{"col": 'gup_spread', "op": '<', "val": 0.0}],
     "tp_mult": 0.3, "sl_mult": 10.0, "score": -1000000003.0},
    {"id": 'FB_AUDUSD_h17_0_G', "symbol": 'AUDUSD', "hour": 17, "direction": 'TREND',
     "conditions": [{"col": 'gup_spread', "op": '<', "val": 0.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000004.0},
    {"id": 'FB_EURJPY_h17_1_G', "symbol": 'EURJPY', "hour": 17, "direction": 'TREND',
     "conditions": [{"col": 'gup_spread', "op": '<', "val": 0.0}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": -1000000005.0},
    {"id": 'FB_GBPJPY_h17_2_G', "symbol": 'GBPJPY', "hour": 17, "direction": 'TREND',
     "conditions": [{"col": 'gup_spread', "op": '<', "val": 0.0}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": -1000000006.0},
    {"id": 'FB_AUDJPY_h18_0_G', "symbol": 'AUDJPY', "hour": 18, "direction": 'TREND',
     "conditions": [{"col": 'gup_spread', "op": '<', "val": 0.0}],
     "tp_mult": 0.5, "sl_mult": 10.0, "score": -1000000007.0},
    {"id": 'FB_NZDUSD_h18_1_G', "symbol": 'NZDUSD', "hour": 18, "direction": 'TREND',
     "conditions": [{"col": 'gup_spread', "op": '<', "val": 0.0}],
     "tp_mult": 0.5, "sl_mult": 10.0, "score": -1000000008.0},
    {"id": 'FB_EURCHF_h18_2_G', "symbol": 'EURCHF', "hour": 18, "direction": 'TREND',
     "conditions": [{"col": 'gup_spread', "op": '<', "val": 0.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000009.0},
    {"id": 'SRSI_srsi_osr_EURNZD_h17_SELL_1.25x8.0', "symbol": 'EURNZD', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'srsi_k', "op": '>', "val": 70.0},
     {"col": 'srsi_slope', "op": '<', "val": 0.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1600.7997410714286},
    {"id": 'ZZ_zz_brk_EURNZD_h17_BUY_1.25x8.0', "symbol": 'EURNZD', "hour": 17, "direction": 'BUY',
     "conditions": [{"col": 'zz_dhi', "op": '<', "val": 0.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1600.6954910714285},
    {"id": 'SRSI_srsi_osr_EURNZD_h17_SELL_1.0x8.0', "symbol": 'EURNZD', "hour": 17, "direction": 'SELL',
     "conditions": [
     {"col": 'srsi_k', "op": '>', "val": 70.0},
     {"col": 'srsi_slope', "op": '<', "val": 0.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1600.6267928571428},
)


def _ema(x: pd.Series, span: int) -> pd.Series:
    return x.ewm(span=span, min_periods=span, adjust=False).mean()


def _zigzag_dhi(H: pd.Series, L: pd.Series, C: pd.Series,
                atr: pd.Series, k: float = 1.0) -> pd.Series:
    """Causal confirmed swings (1.0xATR retracement); returns
    d_hi = (last confirmed swing high - Close) / ATR."""
    h = H.to_numpy(dtype=float)
    l = L.to_numpy(dtype=float)
    c = C.to_numpy(dtype=float)
    a = atr.to_numpy(dtype=float)
    n = len(c)
    dhi = np.full(n, np.nan)
    dirn = 0
    hi_ext = h[0]
    hi_i = 0
    lo_ext = l[0]
    lo_i = 0
    last_hi = np.nan
    last_lo = np.nan
    for t in range(n):
        thr = k * a[t] if np.isfinite(a[t]) and a[t] > 0 else np.inf
        if dirn <= 0:
            if l[t] < lo_ext:
                lo_ext = l[t]
                lo_i = t
        if dirn >= 0:
            if h[t] > hi_ext:
                hi_ext = h[t]
                hi_i = t
        if dirn == 0:
            conf_hi = hi_ext - l[t] >= thr and t > hi_i
            conf_lo = h[t] - lo_ext >= thr and t > lo_i
            if conf_hi and (not conf_lo or hi_i <= lo_i):
                last_hi = hi_ext
                dirn = -1
                lo_ext = l[t]
                lo_i = t
            elif conf_lo:
                last_lo = lo_ext
                dirn = 1
                hi_ext = h[t]
                hi_i = t
        elif dirn == -1:
            if h[t] - lo_ext >= thr and t > lo_i:
                last_lo = lo_ext
                dirn = 1
                hi_ext = h[t]
                hi_i = t
        else:
            if hi_ext - l[t] >= thr and t > hi_i:
                last_hi = hi_ext
                dirn = -1
                lo_ext = l[t]
                lo_i = t
        if np.isfinite(last_hi) and np.isfinite(last_lo) \
                and np.isfinite(a[t]) and a[t] > 0:
            dhi[t] = (last_hi - c[t]) / a[t]
    return pd.Series(dhi, index=C.index)


def _symbol_feat(df: pd.DataFrame) -> pd.DataFrame:
    f = add_cycle12_features(df)
    C = f['Close']
    atrs = f['atr14'].replace(0.0, np.nan)
    # Guppy ribbon spread.
    es = [_ema(C, n) for n in (3, 5, 8, 10, 12, 15)]
    el = [_ema(C, n) for n in (30, 35, 40, 45, 50, 60)]
    short_m = sum(es) / len(es)
    long_m = sum(el) / len(el)
    f['gup_spread'] = (short_m - long_m) / atrs
    # Stochastic RSI on Wilder RSI14.
    delta = C.diff()
    ag = delta.clip(lower=0.0).ewm(alpha=1.0 / 14, min_periods=14,
                                   adjust=False).mean()
    al = (-delta.clip(upper=0.0)).ewm(alpha=1.0 / 14, min_periods=14,
                                      adjust=False).mean()
    rsi = 100.0 - 100.0 / (1.0 + ag / al.replace(0.0, np.nan))
    lo = rsi.rolling(14, min_periods=14).min()
    hi = rsi.rolling(14, min_periods=14).max()
    k = (rsi - lo) / (hi - lo).replace(0.0, np.nan) * 100.0
    f['srsi_k'] = k
    f['srsi_slope'] = k - k.shift(2)
    # ZigZag confirmed-swing distance (cycle66 convention).
    f['zz_dhi'] = _zigzag_dhi(f['High'], f['Low'], C, f['atr14'])
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


def evaluate_cycle66_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """One row per firing Cycle 66 equation at `check_time_utc`."""
    check = pd.Timestamp(check_time_utc)
    if check.tzinfo is not None:
        check = check.tz_convert('UTC').tz_localize(None)
    if check.hour not in CYCLE66_CHECK_HOURS or check.minute != 30:
        return pd.DataFrame()
    sig_stamp = check - pd.Timedelta(hours=1, minutes=30)
    ent_stamp = check - pd.Timedelta(minutes=30)
    out = []
    for eq in CYCLE66_EQUATIONS:
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


def select_cycle66_entries(signals: pd.DataFrame,
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


def is_cycle66_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE66_CHECK_HOURS and t.minute == 30
