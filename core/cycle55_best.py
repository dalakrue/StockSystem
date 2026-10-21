"""Cycle 55 module: C55-15 (August-only system, Improvement Program 2).

24 equations (all book-900 List D relative-value legs over the widened
all-symbol pool: D020 median-peer spread, D035 breakout + cross-pair
confirmation, and the G-series currency-strength / breadth variants),
spanning 3 check hours (06:30, 16:30, 17:30 UTC = 13:00, 23:00, 00:00
MMT), up to 2 entries per check (top-2 by score, max 1 open trade per
symbol). No TREND fallbacks. Uniform exits tp05 = TP 0.5xATR /
SL 5.0xATR (the C44 family's 0.75xATR take-profit was the one design
change vs the failed C55-04 sibling).

C55-15 REPLACES C44-15 as August's system, by the user's explicit
override decision 2026-10-21. In Improvement Program 2 (Cycle 55,
August frequency repair, 20 end-to-end processes judged at the
2.5-pip primary cost) it passed 3 of the 4 August-special gates --
win 95.00% > 90%, leftover 68.7% > 40%, weak 0 <= 2 -- and missed
only the frequency gate: 40 unseen trades = 1.90 entries/day vs the
required 42 trades / 2.0 per day; the user waived that single gate
(as for C44-15 itself in Program 1). The deciding test the user
ordered first -- the LCT "Left95" leftover-confidence test at the
MIDDLE level, computed 2026-10-21 -- it passes at BOTH levels:
paired P 98.83% (bar 80%) and 5th-percentile discovery leftover
86.78% (bar 20%; strict bar 40%), discovery leftover 95.03% vs
C44-15's 48.84% on 471 discovery trades, all 9 August blocks green.
Cycle 44 (C44-15) and Cycle 35 (C35-31) remain selectable.

At 2.5-pip cost (vs C44-15): weak ratings (star1+star2) 0 (vs 2),
unseen net +227.3 pips on 40 trades, win 95.00%, leftover 68.7%,
checks 10/12, discovery net +3,988.5, best N 103 (peak margin 47.8%,
max DD 0.4%, sizing PASS), P(profit) 100.0%, entries/day 1.90.

Exits: tp 0.5xATR / sl 5.0xATR on every equation, TP/SL clipped
[10,500]/[5,100] pips, 48h cap, SL-first fills (research conventions).

PANEL REPAIR (load-bearing): the Cycle 44 research panel builds the
canonical USD log series as the constant 0, so its rolling-120 return
SD is 0 and the strength precision weight B = 1/(sd120*sqrt(n)) is
+inf for USD, which poisoned Bsum/ABsum for every currency --
cs_spr*/cs_acc3 came out +-inf/NaN and the C55 trigger legs could
never fire on the original panel. The repaired panel (Cycle 55
research, work_c55/scripts/c44_panel.py) zero-weights the non-finite
entries -- the numeraire contributes no precision weight -- restoring
the intended leave-one-out z-strength. This module implements the
REPAIRED panel for the strength-derived columns (cs_spr6, cs_spr24,
cs_acc3). Features that do not use strength (medpeer12_spread,
xconf_b/xconf_s, brd12_b/brd12_q) are mathematically unchanged by
the repair, and core/cycle44_best.py keeps the ORIGINAL panel:
C44-15 uses no strength features and its published numbers were
produced on the original panel, so it must (and does) still
reproduce exactly -- re-verified bit-exact at this integration.

Features (definitions copied from the Cycle 55 research engine,
work_c55/scripts/c44_engine.py + c44_panel.py + c55_augment.py;
all causal):
  atr14            rolling-14 mean of true range
  ema20_d          (close - EMA20) / atr14
  ema20_slope6     (EMA20 - EMA20 6 bars ago) / atr14
  ret6_atr         (close - close 6 bars ago) / atr14
  brk8 / brk8_dn   (close - prior-8-bar high) / atr14 and mirror
  brk12_dn         (prior-12-bar low - close) / atr14
  brkc24 / brkc24_dn  close vs prior-24-bar CLOSING high/low, / atr14
  cs_spr6          base-minus-quote currency strength spread at
                   horizon 6 (repaired leave-one-out z-strength:
                   mean signed peer log return, precision-weighted
                   by each peer's preceding 120-bar return SD)
  cs_spr24         same at horizon 24
  cs_acc3          cs_spr24 - cs_spr24 3 bars ago (acceleration)
  brd12_b / brd12_q  breadth at horizon 12: fraction of peers whose
                   12-bar canonical return is below the base's /
                   quote's own
  brd_diff12       brd12_b - brd12_q
  medpeer12_spread pair's base-vs-quote median-peer 12h log-return
                   spread, divided by the pair's own rolling-480 SD
                   of 12h log returns
  xconf_b/xconf_s  cross-pair confirmation counts (D035): 6h pair
                   returns signed across all 20 pairs, counted per
                   currency via base/quote incidence; xconf_b =
                   min(base-appreciation count, quote-depreciation
                   count), xconf_s the mirror.
The panel features need all 20 symbols' frames; if any symbol frame
is missing, the panel features are NaN and no equation fires (a data
problem, not a signal -- same philosophy as the other cycles).

Source of truth: ~/workspace/fx/work_c55/results/C55-15.json
Discovery trade log: ~/workspace/fx/work_c55/results/C55-15_disc_log.csv
Unseen trade log: ~/workspace/fx/work_c55/results/C55-15_unseen_log.csv
LCT record: ~/workspace/fx/work_imp3/lct_c55-15.md
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import pip_size as _pip_size

CYCLE55_VERSION = "cycle55-c5515-v1"
CYCLE55_CHECK_HOURS = (6, 16, 17)  # checks at h:30 UTC
CYCLE55_SYMBOLS_N = 20
MAX_HOLD_HOURS = 48
BASE_SPREAD_PIPS = 1.0
TP_CLIP = (10.0, 500.0)
SL_CLIP = (5.0, 100.0)
MAX_ENTRIES_PER_CHECK = 2

_SYMBOLS = ("AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "AUDUSD", "CHFJPY",
            "EURAUD", "EURCAD", "EURCHF", "EURGBP", "EURJPY", "EURNZD",
            "EURUSD", "GBPJPY", "GBPUSD", "NZDCAD", "NZDUSD", "USDCAD",
            "USDCHF", "USDJPY")
_CCYS = ("EUR", "USD", "JPY", "GBP", "CHF", "CAD", "AUD", "NZD")

# ---------------------------------------------------------------- equations --
C55_EQUATIONS = (
    {"id": 'D_GBPJPY_h6_G003x_0.5x5.0', "symbol": 'GBPJPY', "hour": 6, "direction": 'SELL',
     "conditions": [{"col": "cs_spr6", "op": "<", "val": -0.75}, {"col": "ret6_atr", "op": "<", "val": 0.25}, {"col": "ema20_d", "op": "<", "val": 0.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.2911214285714},
    {"id": 'D_EURNZD_h6_D020p150_0.5x5.0', "symbol": 'EURNZD', "hour": 6, "direction": 'BUY',
     "conditions": [{"col": "medpeer12_spread", "op": ">", "val": 1.5}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.2093357142858},
    {"id": 'D_EURUSD_h6_D035b8x2_0.5x5.0', "symbol": 'EURUSD', "hour": 6, "direction": 'SELL',
     "conditions": [{"col": "brk8_dn", "op": ">", "val": 0.0}, {"col": "xconf_s", "op": ">=", "val": 2.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.1575},
    {"id": 'D_GBPUSD_h6_D020w75_0.5x5.0', "symbol": 'GBPUSD', "hour": 6, "direction": 'BUY',
     "conditions": [{"col": "medpeer12_spread", "op": ">", "val": 0.75}, {"col": "ema20_d", "op": ">", "val": 0.0}, {"col": "ema20_slope6", "op": ">", "val": 0.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.1441428571428},
    {"id": 'D_USDCAD_h6_D035b8x2_0.5x5.0', "symbol": 'USDCAD', "hour": 6, "direction": 'BUY',
     "conditions": [{"col": "brk8", "op": ">", "val": 0.0}, {"col": "xconf_b", "op": ">=", "val": 2.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.12},
    {"id": 'D_EURCAD_h6_D020s100_0.5x5.0', "symbol": 'EURCAD', "hour": 6, "direction": 'BUY',
     "conditions": [{"col": "medpeer12_spread", "op": ">", "val": 1.0}, {"col": "ema20_d", "op": ">", "val": 0.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.1152857142857},
    {"id": 'D_EURJPY_h6_G003x_0.5x5.0', "symbol": 'EURJPY', "hour": 6, "direction": 'SELL',
     "conditions": [{"col": "cs_spr6", "op": "<", "val": -0.75}, {"col": "ret6_atr", "op": "<", "val": 0.25}, {"col": "ema20_d", "op": "<", "val": 0.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 967.9525926267281},
    {"id": 'D_EURAUD_h6_G031x_0.5x5.0', "symbol": 'EURAUD', "hour": 6, "direction": 'SELL',
     "conditions": [{"col": "xconf_s", "op": ">=", "val": 5.0}, {"col": "ret6_atr", "op": "<", "val": 0.25}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 967.8912569124424},
    {"id": 'D_EURAUD_h16_G023x_0.5x5.0', "symbol": 'EURAUD', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": "brd12_q", "op": ">", "val": 0.6}, {"col": "brd12_b", "op": "<", "val": 0.4}, {"col": "cs_acc3", "op": "<", "val": 0.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.4278535714286},
    {"id": 'D_EURNZD_h16_D035cx3_0.5x5.0', "symbol": 'EURNZD', "hour": 16, "direction": 'BUY',
     "conditions": [{"col": "brkc24", "op": ">", "val": 0.0}, {"col": "xconf_b", "op": ">=", "val": 3.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.2299285714286},
    {"id": 'D_AUDCAD_h16_G011x_0.5x5.0', "symbol": 'AUDCAD', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": "cs_acc3", "op": "<", "val": -0.5}, {"col": "brd_diff12", "op": "<", "val": -0.2}, {"col": "ema20_d", "op": "<", "val": 0.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.2025},
    {"id": 'D_EURJPY_h16_D035b8x2_0.5x5.0', "symbol": 'EURJPY', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": "brk8_dn", "op": ">", "val": 0.0}, {"col": "xconf_s", "op": ">=", "val": 2.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.1945392857143},
    {"id": 'D_CHFJPY_h16_D035b8x2_0.5x5.0', "symbol": 'CHFJPY', "hour": 16, "direction": 'BUY',
     "conditions": [{"col": "brk8", "op": ">", "val": 0.0}, {"col": "xconf_b", "op": ">=", "val": 2.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.1523571428571},
    {"id": 'D_USDCAD_h16_D035b8x2_0.5x5.0', "symbol": 'USDCAD', "hour": 16, "direction": 'BUY',
     "conditions": [{"col": "brk8", "op": ">", "val": 0.0}, {"col": "xconf_b", "op": ">=", "val": 2.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.1392321428572},
    {"id": 'D_AUDNZD_h16_D035cx3_0.5x5.0', "symbol": 'AUDNZD', "hour": 16, "direction": 'BUY',
     "conditions": [{"col": "brkc24", "op": ">", "val": 0.0}, {"col": "xconf_b", "op": ">=", "val": 3.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.1182964285714},
    {"id": 'D_EURUSD_h16_D035b8x3_0.5x5.0', "symbol": 'EURUSD', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": "brk8_dn", "op": ">", "val": 0.0}, {"col": "xconf_s", "op": ">=", "val": 3.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.1170321428572},
    {"id": 'D_GBPUSD_h17_D020s100_0.5x5.0', "symbol": 'GBPUSD', "hour": 17, "direction": 'SELL',
     "conditions": [{"col": "medpeer12_spread", "op": "<", "val": -1.0}, {"col": "ema20_d", "op": "<", "val": 0.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.4595642857142},
    {"id": 'D_NZDCAD_h17_G023x_0.5x5.0', "symbol": 'NZDCAD', "hour": 17, "direction": 'SELL',
     "conditions": [{"col": "brd12_q", "op": ">", "val": 0.6}, {"col": "brd12_b", "op": "<", "val": 0.4}, {"col": "cs_acc3", "op": "<", "val": 0.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.215825},
    {"id": 'D_AUDNZD_h17_G003x_0.5x5.0', "symbol": 'AUDNZD', "hour": 17, "direction": 'SELL',
     "conditions": [{"col": "cs_spr6", "op": "<", "val": -0.75}, {"col": "ret6_atr", "op": "<", "val": 0.25}, {"col": "ema20_d", "op": "<", "val": 0.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.1725},
    {"id": 'D_EURUSD_h17_G011x_0.5x5.0', "symbol": 'EURUSD', "hour": 17, "direction": 'SELL',
     "conditions": [{"col": "cs_acc3", "op": "<", "val": -0.5}, {"col": "brd_diff12", "op": "<", "val": -0.2}, {"col": "ema20_d", "op": "<", "val": 0.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.16245},
    {"id": 'D_USDCAD_h17_G011x_0.5x5.0', "symbol": 'USDCAD', "hour": 17, "direction": 'BUY',
     "conditions": [{"col": "cs_acc3", "op": ">", "val": 0.5}, {"col": "brd_diff12", "op": ">", "val": 0.2}, {"col": "ema20_d", "op": ">", "val": 0.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.1574892857143},
    {"id": 'D_AUDCAD_h17_G011x_0.5x5.0', "symbol": 'AUDCAD', "hour": 17, "direction": 'BUY',
     "conditions": [{"col": "cs_acc3", "op": ">", "val": 0.5}, {"col": "brd_diff12", "op": ">", "val": 0.2}, {"col": "ema20_d", "op": ">", "val": 0.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.15},
    {"id": 'D_NZDUSD_h17_D035cx3_0.5x5.0', "symbol": 'NZDUSD', "hour": 17, "direction": 'SELL',
     "conditions": [{"col": "brkc24_dn", "op": ">", "val": 0.0}, {"col": "xconf_s", "op": ">=", "val": 3.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.1440607142857},
    {"id": 'D_AUDUSD_h17_D035b12x2_0.5x5.0', "symbol": 'AUDUSD', "hour": 17, "direction": 'SELL',
     "conditions": [{"col": "brk12_dn", "op": ">", "val": 0.0}, {"col": "xconf_s", "op": ">=", "val": 2.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.1358821428571},
)

_COND_OPS = {">": lambda a, v: a > v, "<": lambda a, v: a < v,
             ">=": lambda a, v: a >= v, "<=": lambda a, v: a <= v}


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


def _pair_idx(sym):
    return _CCYS.index(sym[:3]), _CCYS.index(sym[3:])


def _symbol_features(ff):
    """Base + extended features for one symbol frame (c44_engine
    add_features / add_features_ext logic, restricted to the columns
    C55-15 conditions on, plus atr14)."""
    g = ff.sort_index()
    cl, hi, lo = g["Close"], g["High"], g["Low"]
    tr = pd.concat([(hi - lo), (hi - cl.shift(1)).abs(),
                    (lo - cl.shift(1)).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14, min_periods=1).mean()
    atr = atr14.replace(0.0, np.nan)
    e20 = cl.ewm(span=20, min_periods=20, adjust=False).mean()
    feat = pd.DataFrame(index=g.index)
    feat["atr14"] = atr14
    feat["ema20_d"] = (cl - e20) / atr
    feat["ema20_slope6"] = (e20 - e20.shift(6)) / atr
    feat["ret6_atr"] = (cl - cl.shift(6)) / atr
    for n_ in (8, 12):
        hi_n = hi.shift(1).rolling(n_, min_periods=n_).max()
        lo_n = lo.shift(1).rolling(n_, min_periods=n_).min()
        if n_ == 8:
            feat["brk8"] = (cl - hi_n) / atr
            feat["brk8_dn"] = (lo_n - cl) / atr
        else:
            feat["brk12_dn"] = (lo_n - cl) / atr
    chi24 = cl.shift(1).rolling(24, min_periods=24).max()
    clo24 = cl.shift(1).rolling(24, min_periods=24).min()
    feat["brkc24"] = (cl - chi24) / atr
    feat["brkc24_dn"] = (clo24 - cl) / atr
    return feat


def _panel_features(frames_norm):
    """Cross-pair (H+X) panel features per symbol (REPAIRED c44_panel
    logic from Cycle 55 research, restricted to the columns C55-15
    conditions on: cs_spr6, cs_spr24, cs_acc3, brd12_b, brd12_q,
    brd_diff12, medpeer12_spread, xconf_b, xconf_s).

    frames_norm: {symbol: OHLC DataFrame with naive-UTC DatetimeIndex}.
    Returns {symbol: DataFrame on the panel (union) index} or {} if any
    of the 20 symbol frames is missing.
    """
    if any(frames_norm.get(s) is None or len(frames_norm[s]) == 0
           for s in _SYMBOLS):
        return {}
    closes = {s: frames_norm[s]["Close"] for s in _SYMBOLS}
    panel = pd.DataFrame(closes).sort_index()
    panel = panel.ffill(limit=2)
    PL = np.log(panel)
    S = pd.DataFrame(index=panel.index)
    S["EUR"] = PL["EURUSD"]
    S["GBP"] = PL["GBPUSD"]
    S["AUD"] = PL["AUDUSD"]
    S["NZD"] = PL["NZDUSD"]
    S["JPY"] = -PL["USDJPY"]
    S["CHF"] = -PL["USDCHF"]
    S["CAD"] = -PL["USDCAD"]
    S["USD"] = 0.0
    S = S[list(_CCYS)]
    lr1 = S.diff()
    sd120 = lr1.rolling(120, min_periods=60).std()
    strength = {}
    breadth = {}
    for n in (6, 12, 24):
        dn = S - S.shift(n)
        A = dn.to_numpy()
        B = (1.0 / (sd120 * np.sqrt(n))).to_numpy()
        # CYCLE 55 PANEL REPAIR: the canonical USD series is constant 0
        # by construction, so sd120[USD] = 0 and B[USD] = inf, which
        # poisoned Bsum/ABsum for every currency (strengths came out
        # +-inf/NaN). Zero-weighting the non-finite entries (the
        # numeraire contributes no precision weight) restores the
        # intended leave-one-out z-strength for all 8 currencies.
        B = np.where(np.isfinite(B), B, 0.0)
        Bsum = np.nansum(B, axis=1)
        ABsum = np.nansum(A * B, axis=1)
        # strength_c = (1/7)[A_c*(Bsum - B_c) - (ABsum - A_c*B_c)]
        st = (A * (Bsum[:, None] - B) - (ABsum[:, None] - A * B)) / 7.0
        strength[n] = pd.DataFrame(st, index=S.index, columns=list(_CCYS))
        if n == 12:
            # breadth: fraction of peers p with dn_c > dn_p
            gt = (A[:, :, None] > A[:, None, :])
            gt[:, range(8), range(8)] = False
            breadth[12] = pd.DataFrame(gt.mean(axis=2), index=S.index,
                                       columns=list(_CCYS))
    # median peer return 12 (raw log-return units, canonical series)
    d12 = (S - S.shift(12)).to_numpy()
    diffs = d12[:, :, None] - d12[:, None, :]
    diffs[:, range(8), range(8)] = np.nan
    med_peer12 = pd.DataFrame(np.nanmedian(diffs, axis=2),
                              index=S.index, columns=list(_CCYS))
    # cross-pair confirmation counts (D035), 6-bar pair returns
    d6p = (PL - PL.shift(6)).to_numpy()
    pos = (d6p > 0).astype(float)
    neg = (d6p < 0).astype(float)
    base_inc = np.zeros((8, 20))
    quote_inc = np.zeros((8, 20))
    for j, s in enumerate(_SYMBOLS):
        b, q = _pair_idx(s)
        base_inc[b, j] = 1.0
        quote_inc[q, j] = 1.0
    mpb = pos @ base_inc.T
    mnb = neg @ base_inc.T
    mpq = pos @ quote_inc.T
    mnq = neg @ quote_inc.T
    out = {}
    for s in _SYMBOLS:
        b, q = _pair_idx(s)
        B, Q = _CCYS[b], _CCYS[q]
        f = pd.DataFrame(index=panel.index)
        f["cs_spr6"] = strength[6][B] - strength[6][Q]
        f["cs_spr24"] = strength[24][B] - strength[24][Q]
        f["cs_acc3"] = f["cs_spr24"] - f["cs_spr24"].shift(3)
        f["brd12_b"] = breadth[12][B]
        f["brd12_q"] = breadth[12][Q]
        f["brd_diff12"] = f["brd12_b"] - f["brd12_q"]
        raw_med = med_peer12[B] - med_peer12[Q]
        denom = (PL[s] - PL[s].shift(12)).rolling(480, min_periods=120).std()
        f["medpeer12_spread"] = raw_med / denom.replace(0.0, np.nan)
        cnt_b_app = mpb[:, b] + mnq[:, b]
        cnt_q_dep = mnb[:, q] + mpq[:, q]
        cnt_b_dep = mnb[:, b] + mpq[:, b]
        cnt_q_app = mpb[:, q] + mnq[:, q]
        f["xconf_b"] = np.minimum(cnt_b_app, cnt_q_dep)
        f["xconf_s"] = np.minimum(cnt_b_dep, cnt_q_app)
        out[s] = f
    return out


def evaluate_cycle55_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate C55-15 equations at one check time (h:30 UTC).

    frames: {symbol: H1 OHLC DataFrame indexed by candle-stamp} -- all
    20 symbols are used (the List D panel features are cross-pair).
    Only equations whose hour matches the check hour are evaluated.
    Signal features come from the (h-1):00 UTC candle (last completed
    as of h:30 UTC); entry price = open of the h:00 UTC candle.
    Returns one row per firing equation with TP/SL already clipped.
    """
    check = _as_utc(check_time_utc)
    hour = int(check.hour)
    if hour not in CYCLE55_CHECK_HOURS:
        return pd.DataFrame()
    sig_stamp = (check - pd.Timedelta(hours=1, minutes=30)).tz_localize(None)
    ent_stamp = (check - pd.Timedelta(minutes=30)).tz_localize(None)
    frames_norm = {}
    for s, f in (frames or {}).items():
        if f is None or len(f) == 0:
            continue
        ff = f.copy()
        ff.index = pd.to_datetime(ff.index, utc=True).tz_localize(None)
        frames_norm[str(s).upper()] = ff.sort_index()
    panel = _panel_features(frames_norm)
    if not panel:
        return pd.DataFrame()
    rows = []
    feat_cache = {}
    for eq in C55_EQUATIONS:
        if eq["hour"] != hour:
            continue
        sym = eq["symbol"]
        ff = frames_norm.get(sym)
        if ff is None:
            continue
        if sig_stamp not in ff.index or ent_stamp not in ff.index:
            continue
        if sym not in feat_cache:
            feat = _symbol_features(ff)
            pf = panel[sym].reindex(feat.index)
            for col in pf.columns:
                feat[col] = pf[col]
            feat_cache[sym] = feat
        feat = feat_cache[sym]
        pos = ff.index.get_loc(sig_stamp)
        if isinstance(pos, (np.ndarray, slice)):
            continue
        row = feat.iloc[pos]
        if not all(_cond_ok(row, c) for c in eq["conditions"]):
            continue
        atr = float(row["atr14"])
        if not np.isfinite(atr) or atr <= 0:
            continue
        pip = _pip_size(sym)
        atr_pips = atr / pip
        tp = float(min(max(eq["tp_mult"] * atr_pips, TP_CLIP[0]), TP_CLIP[1]))
        sl = float(min(max(eq["sl_mult"] * atr_pips, SL_CLIP[0]), SL_CLIP[1]))
        rows.append({
            "check": check, "symbol": sym, "equation": eq["id"],
            "direction": eq["direction"], "score": eq["score"],
            "atr_pips": atr_pips,
            "entry_px": float(ff.loc[ent_stamp, "Open"]),
            "tp_pips": tp, "sl_pips": sl,
            "signal_candle": sig_stamp, "entry_candle": ent_stamp,
        })
    return pd.DataFrame(rows)


def select_cycle55_entries(signals: pd.DataFrame, open_symbols=()) -> pd.DataFrame:
    """Up to 2 entries per check (the researched C55-15 assembly):
    top-2 by score, max 1 open trade per symbol. Stable sort
    reproduces the research assembly order on ties."""
    if signals is None or len(signals) == 0:
        return signals.iloc[0:0] if signals is not None else pd.DataFrame()
    held = {str(s).upper() for s in (open_symbols or ())}
    out = []
    for _, row in signals.sort_values("score", ascending=False, kind="mergesort").iterrows():
        if len(out) >= MAX_ENTRIES_PER_CHECK:
            break
        if str(row["symbol"]).upper() in held:
            continue
        out.append(row)
        held.add(str(row["symbol"]).upper())
    return pd.DataFrame(out)


def is_cycle55_check_time(ts) -> bool:
    """True if ts (UTC) is at one of the C55 check hours (:30)."""
    t = _as_utc(ts)
    return int(t.hour) in CYCLE55_CHECK_HOURS and int(t.minute) == 30
