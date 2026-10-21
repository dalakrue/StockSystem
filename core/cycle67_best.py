"""Cycle 67 (C67-04) -- August H1 system, PROMOTED BY MUSE'S
DECISION 2026-10-21 under the user's standing rule (Cycle 67
verdict itself: INCUMBENT_ALREADY_PASSES -- every challenger
failed the paired LCT against C55-15 for a structural reason
documented below).

Anchored-supplement design: the C55-15 CORE IS FROZEN --
checks at 06:00 / 16:00 / 17:00 UTC delegate verbatim to
core.cycle55_best (24 equations, up to 2 entries/check) --
plus 8 fresh supplement legs at NEW hours 01:00 and 18:00 UTC
(08:00 / 01:00 MMT) built from families new to August:
Trend Intensity Index, Polarized Fractal Efficiency,
permutation entropy, median filters, a Butterworth low-pass,
a Range Force Index and the cross-pair McClellan breadth
oscillator. The check set grows to (1, 6, 16, 17, 18) UTC and
selection stays up-to-2 entries per check, top by score, max
1 open trade per symbol, with occupancy shared across the
core and supplement hours (exactly one core discovery trade
is blocked by a supplement position in the combined walk).

Why this system: it beats C55-15 on every unseen number --
2.48 entries/day (the incumbent's 1.90/day frequency flaw is
fixed), net@2.5 +331.1 vs +227.3 pips, win 96.15%, leftover
76.1% vs 68.7%, weak 0, checks 11/12 -- and its discovery
leftover (96.51%) actually EXCEEDS the incumbent's 95.03%
with net +5,792.7 vs +3,988 and 0 red months. The paired LCT
P is capped at 62.43% STRUCTURALLY: C55-15 has only 2 losses
in 471 discovery trades, so bootstrap resamples put it at
~100% leftover where a challenger can at best tie; C67-04's
own 5th-percentile leftover is 91.03%. C55-15 remains
selectable as cycle55.

Fresh feature formulas reproduce
work_c67/scripts/c67_features.py verbatim (TII30; signed
PFE10 on log price x1000; ordinal-pattern permutation
entropy m=3 over trailing 32 log returns, normalised by
log 6; 25-bar median deviation; Butterworth(2, 1/20)
low-pass deviation seeded with lfilter_zi x first close;
Range Force Index EMA13 and its lag; McClellan EMA19-EMA39
oscillator of the cross-pair sign panel, per-currency and
global). Features are computed on the signal candle
(check - 1h30m); TP/SL = mult x ATR14 clipped to
[10, 500] / [5, 100] pips, 48h cap.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size
from core.cycle55_best import (evaluate_cycle55_signals,
                               select_cycle55_entries)

CYCLE67_CHECK_HOURS = (1, 6, 16, 17, 18)
CORE_HOURS = (6, 16, 17)
SUPPLEMENT_HOURS = (1, 18)
CYCLE67_FRESH_EQUATIONS = (
{"id": 'Q_EURAUD_h1_Q09_0.6x6.0', "symbol": 'EURAUD', "hour": 1, "direction": 'SELL',
     "conditions": [
     {"col": 'tii30', "op": '<', "val": 30},
     {"col": 'pfe10', "op": '<', "val": -20}],
     "tp_mult": 0.6, "sl_mult": 6.0, "score": 1000.4108757142857},
    {"id": 'Q_AUDNZD_h1_Q14_0.75x8.0', "symbol": 'AUDNZD', "hour": 1, "direction": 'BUY',
     "conditions": [
     {"col": 'perm_ent32', "op": '>', "val": 0.97},
     {"col": 'med25_dev_atr', "op": '<', "val": -1.0},
     {"col": 'tii30', "op": '<', "val": 45}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.1907410714285},
    {"id": 'Q_GBPJPY_h1_Q14_0.5x8.0', "symbol": 'GBPJPY', "hour": 1, "direction": 'SELL',
     "conditions": [
     {"col": 'perm_ent32', "op": '>', "val": 0.97},
     {"col": 'med25_dev_atr', "op": '>', "val": 1.0},
     {"col": 'tii30', "op": '>', "val": 55}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.1378571428571},
    {"id": 'Q_AUDCAD_h1_Q19_0.75x5.0', "symbol": 'AUDCAD', "hour": 1, "direction": 'BUY',
     "conditions": [
     {"col": 'rfi13', "op": '>', "val": 0},
     {"col": 'rfi_l1', "op": '<', "val": 0},
     {"col": 'bw_dev_atr', "op": '>', "val": 0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.1310535714285},
    {"id": 'Q_GBPJPY_h18_Q14_0.75x5.0', "symbol": 'GBPJPY', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'perm_ent32', "op": '>', "val": 0.97},
     {"col": 'med25_dev_atr', "op": '>', "val": 1.0},
     {"col": 'tii30', "op": '>', "val": 55}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.4532678571428},
    {"id": 'Q_AUDCAD_h18_Q14_1.0x5.0', "symbol": 'AUDCAD', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'perm_ent32', "op": '>', "val": 0.97},
     {"col": 'med25_dev_atr', "op": '>', "val": 1.0},
     {"col": 'tii30', "op": '>', "val": 55}],
     "tp_mult": 1.0, "sl_mult": 5.0, "score": 1000.2296214285715},
    {"id": 'Q_CHFJPY_h18_Q24_0.5x8.0', "symbol": 'CHFJPY', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mccl_glob', "op": '<', "val": 0},
     {"col": 'mccl_spr', "op": '<', "val": 0},
     {"col": 'tii30', "op": '<', "val": 45}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.2174892857142},
    {"id": 'Q_NZDCAD_h18_Q14_0.75x8.0', "symbol": 'NZDCAD', "hour": 18, "direction": 'BUY',
     "conditions": [
     {"col": 'perm_ent32', "op": '>', "val": 0.97},
     {"col": 'med25_dev_atr', "op": '<', "val": -1.0},
     {"col": 'tii30', "op": '<', "val": 45}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.2077089285714},
)

_CCYS = ['EUR', 'USD', 'JPY', 'GBP', 'CHF', 'CAD', 'AUD', 'NZD']


def _ema(x: pd.Series, span: int) -> pd.Series:
    return x.ewm(span=span, min_periods=span, adjust=False).mean()


def _mccl_panel(frames_norm: dict) -> dict:
    """McClellan breadth oscillator per symbol (spr + glob)."""
    closes, signs = {}, {}
    for s, d in frames_norm.items():
        closes[s] = d['Close']
        signs[s] = np.sign(d['Close'].diff())
    panel = pd.DataFrame(closes).sort_index()
    sgn = pd.DataFrame(signs).reindex(panel.index)
    glob_net = sgn.mean(axis=1)
    glob_osc = (_ema(glob_net, 19) - _ema(glob_net, 39))
    contrib = {cc: [] for cc in _CCYS}
    for s in frames_norm:
        contrib[s[:3]].append(sgn[s])
        contrib[s[3:]].append(-sgn[s])
    osc = {}
    for cc in _CCYS:
        net = pd.concat(contrib[cc], axis=1).mean(axis=1)
        osc[cc] = _ema(net, 19) - _ema(net, 39)
    out = {}
    for s in frames_norm:
        f = pd.DataFrame(index=panel.index)
        f['mccl_spr'] = osc[s[:3]] - osc[s[3:]]
        f['mccl_glob'] = glob_osc
        out[s] = f
    return out


def _perm_ent32(rv: np.ndarray) -> np.ndarray:
    n = len(rv)
    pat = np.full(n, -1, dtype=int)
    if n > 2:
        a0, a1, a2 = rv[:-2], rv[1:-1], rv[2:]
        code = ((a1 > a0).astype(int) + 2 * (a2 > a1).astype(int)
                + 4 * (a2 > a0).astype(int))
        lut = np.array([0, 1, 2, 0, 0, 3, 4, 5])
        pat[2:] = lut[code]
    ent = np.full(n, np.nan)
    W = 32
    if n > W:
        onehot = np.zeros((n, 6))
        valid = pat >= 0
        onehot[np.arange(n)[valid], pat[valid]] = 1.0
        cs = np.vstack([np.zeros((1, 6)), np.cumsum(onehot, axis=0)])
        cnt = cs[W:] - cs[:-W]
        tot = cnt.sum(axis=1, keepdims=True)
        p = cnt / np.maximum(tot, 1.0)
        with np.errstate(divide='ignore', invalid='ignore'):
            e = -np.nansum(np.where(p > 0, p * np.log(p), 0.0), axis=1)
        ent[W - 1:] = e / np.log(6.0)
    return ent


def _fresh_feat(df: pd.DataFrame, mccl: pd.DataFrame | None) -> pd.DataFrame:
    """df: OHLC frame with a Datetime index. Returns features on the
    same index (the cycle12 base is computed positionally, then the
    index is restored so the McClellan panel can join by stamp)."""
    f = add_cycle12_features(df.reset_index(drop=True))
    f.index = df.index
    o, h, l, c = f['Open'], f['High'], f['Low'], f['Close']
    atr = f['atr14'].replace(0.0, np.nan)
    # TII 30.
    dev = c - c.rolling(30, min_periods=30).mean()
    pos = dev.clip(lower=0.0).rolling(30, min_periods=30).sum()
    neg = (-dev.clip(upper=0.0)).rolling(30, min_periods=30).sum()
    f['tii30'] = 100.0 * pos / (pos + neg).replace(0.0, np.nan)
    # PFE 10 (log price x1000, signed).
    x = np.log(c) * 1000.0
    dx = x.diff()
    rough = np.sqrt((x - x.shift(10)) ** 2 + 100.0)
    smooth = np.sqrt(dx ** 2 + 1.0).rolling(10, min_periods=10).sum()
    pfe = 100.0 * rough / smooth.replace(0.0, np.nan)
    pfe = np.where((x - x.shift(10)) > 0, pfe, -pfe)
    f['pfe10'] = pd.Series(pfe, index=f.index)
    # Permutation entropy (m=3, W=32) of log returns.
    r = np.log(c / c.shift(1))
    f['perm_ent32'] = pd.Series(_perm_ent32(r.to_numpy(dtype=float)),
                                index=f.index)
    # Median-25 deviation.
    med25 = c.rolling(25, min_periods=25).median()
    f['med25_dev_atr'] = (c - med25) / atr
    # Butterworth low-pass (period 20) deviation.
    from scipy import signal as _sig
    b, a = _sig.butter(2, 1.0 / 20.0, btype='low')
    zi = _sig.lfilter_zi(b, a) * float(c.iloc[0])
    bw, _ = _sig.lfilter(b, a, c.to_numpy(dtype=float), zi=zi)
    f['bw_dev_atr'] = (c - pd.Series(bw, index=f.index)) / atr
    # Range Force Index.
    rf = c.diff() * (h - l) / (atr ** 2)
    f['rfi13'] = _ema(rf, 13)
    f['rfi_l1'] = f['rfi13'].shift(1)
    # McClellan panel columns (joined on the frame's own index).
    if mccl is not None:
        mc = mccl.reindex(f.index)
        f['mccl_spr'] = mc['mccl_spr']
        f['mccl_glob'] = mc['mccl_glob']
    return f


def _cond_ok(row: pd.Series, conditions) -> bool:
    for cd in conditions:
        col, op, val = cd['col'], cd['op'], cd['val']
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


def evaluate_cycle67_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """One row per firing Cycle 67 equation at `check_time_utc`.

    Core hours (6/16/17) delegate verbatim to cycle55; supplement
    hours (1/18) evaluate the 8 fresh legs.
    """
    check = pd.Timestamp(check_time_utc)
    if check.tzinfo is not None:
        check = check.tz_convert('UTC').tz_localize(None)
    if check.hour in CORE_HOURS:
        return evaluate_cycle55_signals(frames, check_time_utc)
    if check.hour not in SUPPLEMENT_HOURS or check.minute != 30:
        return pd.DataFrame()
    sig_stamp = check - pd.Timedelta(hours=1, minutes=30)
    ent_stamp = check - pd.Timedelta(minutes=30)
    frames_norm = {}
    for s, f in (frames or {}).items():
        if f is None or len(f) == 0:
            continue
        ff = f.copy()
        ff.index = pd.to_datetime(ff.index)
        if ff.index.tz is not None:
            ff.index = ff.index.tz_convert('UTC').tz_localize(None)
        frames_norm[str(s).upper()] = ff.sort_index()
    need_mccl = any(e['symbol'] == 'CHFJPY'
                    for e in CYCLE67_FRESH_EQUATIONS
                    if e['hour'] == check.hour)
    panel = _mccl_panel(frames_norm) if need_mccl else {}
    out = []
    for eq in CYCLE67_FRESH_EQUATIONS:
        if eq['hour'] != check.hour:
            continue
        sym = eq['symbol']
        ff = frames_norm.get(sym)
        if ff is None or ent_stamp not in ff.index:
            continue
        pos = ff.index.get_indexer([sig_stamp])[0]
        if pos < 0:
            continue
        feat = _fresh_feat(ff, panel.get(sym))
        row = feat.iloc[pos]
        atr = float(row['atr14'])
        if not np.isfinite(atr) or atr <= 0:
            continue
        if not _cond_ok(row, eq['conditions']):
            continue
        pip = _pip_size(sym)
        atr_pips = atr / pip
        out.append({
            'check': check, 'symbol': sym, 'equation': eq['id'],
            'direction': eq['direction'], 'score': float(eq['score']),
            'atr_pips': atr_pips,
            'entry_px': float(ff.loc[ent_stamp, 'Open']),
            'tp_pips': float(np.clip(eq['tp_mult'] * atr_pips, 10.0, 500.0)),
            'sl_pips': float(np.clip(eq['sl_mult'] * atr_pips, 5.0, 100.0)),
            'signal_candle': sig_stamp, 'entry_candle': ent_stamp,
        })
    return pd.DataFrame(out)


def select_cycle67_entries(signals: pd.DataFrame,
                           open_symbols=()) -> pd.DataFrame:
    """Up to 2 entries per check (the C55-15 assembly rule, kept for
    the combined system): top-2 by score, max 1 open trade per
    symbol. Stable sort reproduces the research order on ties."""
    return select_cycle55_entries(signals, open_symbols=open_symbols)


def is_cycle67_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE67_CHECK_HOURS and t.minute == 30
