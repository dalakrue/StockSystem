"""Cycle 44 module: C44-15 (August-only system, improvement round).

9 equations (all book List D relative-value: D020 median-peer spread
and D035 breakout + cross-pair confirmation), USD majors only
(AUDUSD, EURUSD, GBPUSD, USDCAD, USDJPY), spanning 3 check hours
(01:30, 13:30, 16:30 UTC = 08:00, 20:00, 23:00 MMT), up to 2 entries
per check (top-2 by score, max 1 open trade per symbol). No TREND
fallbacks: the system trades only when its rare List D signals fire.

C44-15 REPLACES C35-31 as August's system, by the user's explicit
override decision 2026-10-21. In the Cycles 37-48 improvement program
(20 end-to-end processes per month, judged at the 2.5-pip primary
cost) it scored weak 2 vs the incumbent's 8 with win 100% and
leftover 100%, but it trades only 0.62 entries/day, failing the
program's >=2 entries/day frequency gate; the user waived that single
gate and ordered the promotion. Cycle 35 (C35-31) remains selectable.

At 2.5-pip cost (vs C35-31): weak ratings (star1+star2) 2 (vs 8),
unseen net +155.0 pips on 13 trades, win 100%, leftover 100%,
checks 9/12, discovery net +1058.2, best N 62 (peak margin 48.2%,
max DD 23.5%, sizing PASS), P(profit) 98.2%, entries/day 0.62.

Exits: tp 0.75xATR / sl 5.0xATR on every equation, TP/SL clipped
[10,500]/[5,100] pips, 48h cap, SL-first fills (research conventions).

Features (definitions copied from the Cycle 44 research engine,
work_c44/scripts/c44_engine.py + c44_panel.py; all causal):
  atr14            rolling-14 mean of true range
  ema20_d          (close - EMA20) / atr14
  ema20_slope6     (EMA20 - EMA20 6 bars ago) / atr14
  brk24            (close - prior-24-bar high) / atr14
  brk24_dn         (prior-24-bar low - close) / atr14
  medpeer12_spread pair's base-vs-quote median-peer 12h log-return
                   spread (canonical G8 USD-value series), divided by
                   the pair's own rolling-480 SD of 12h log returns
  xconf_b/xconf_s  cross-pair confirmation counts (D035): 6h pair
                   returns signed across all 20 pairs, counted per
                   currency via base/quote incidence; xconf_b =
                   min(base-appreciation count, quote-depreciation
                   count), xconf_s the mirror.
The panel features need all 20 symbols' frames; if any symbol frame
is missing, the panel features are NaN and no equation fires (a data
problem, not a signal -- same philosophy as the other cycles).

Source of truth: ~/workspace/fx/work_c44/results/C44-15.json
Discovery trade log: ~/workspace/fx/work_c44/results/C44-15_disc_log.csv
Unseen trade log: ~/workspace/fx/work_c44/results/C44-15_unseen_log.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import pip_size as _pip_size

CYCLE44_VERSION = "cycle44-c4415-v1"
CYCLE44_CHECK_HOURS = (1, 13, 16)  # checks at h:30 UTC
CYCLE44_SYMBOLS_N = 5
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
C44_EQUATIONS = (

    {"id": 'D_USDCAD_h1_D020_0.75x5.0', "symbol": 'USDCAD', "hour": 1, "direction": 'SELL',
     "conditions": [{"col": "medpeer12_spread", "op": "<", "val": -1.5}, {"col": "ema20_d", "op": "<", "val": 0.0}, {"col": "ema20_slope6", "op": "<", "val": 0.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 956.668096273292},
    {"id": 'D_EURUSD_h1_D020_0.75x5.0', "symbol": 'EURUSD', "hour": 1, "direction": 'SELL',
     "conditions": [{"col": "medpeer12_spread", "op": "<", "val": -1.5}, {"col": "ema20_d", "op": "<", "val": 0.0}, {"col": "ema20_slope6", "op": "<", "val": 0.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 916.7207934523809},
    {"id": 'D_AUDUSD_h1_D035_0.75x5.0', "symbol": 'AUDUSD', "hour": 1, "direction": 'SELL',
     "conditions": [{"col": "brk24_dn", "op": ">", "val": 0.0}, {"col": "xconf_s", "op": ">=", "val": 4.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 866.6731505952382},
    {"id": 'D_USDCAD_h13_D020_0.75x5.0', "symbol": 'USDCAD', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": "medpeer12_spread", "op": "<", "val": -1.5}, {"col": "ema20_d", "op": "<", "val": 0.0}, {"col": "ema20_slope6", "op": "<", "val": 0.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.1505982142858},
    {"id": 'D_USDJPY_h13_D035_0.75x5.0', "symbol": 'USDJPY', "hour": 13, "direction": 'BUY',
     "conditions": [{"col": "brk24", "op": ">", "val": 0.0}, {"col": "xconf_b", "op": ">=", "val": 4.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 941.3000795168067},
    {"id": 'D_GBPUSD_h13_D020_0.75x5.0', "symbol": 'GBPUSD', "hour": 13, "direction": 'BUY',
     "conditions": [{"col": "medpeer12_spread", "op": ">", "val": 1.5}, {"col": "ema20_d", "op": ">", "val": 0.0}, {"col": "ema20_slope6", "op": ">", "val": 0.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 875.0584321428571},
    {"id": 'D_GBPUSD_h16_D020_0.75x5.0', "symbol": 'GBPUSD', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": "medpeer12_spread", "op": "<", "val": -1.5}, {"col": "ema20_d", "op": "<", "val": 0.0}, {"col": "ema20_slope6", "op": "<", "val": 0.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 928.9022839285714},
    {"id": 'D_USDCAD_h16_D020_0.75x5.0', "symbol": 'USDCAD', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": "medpeer12_spread", "op": "<", "val": -1.5}, {"col": "ema20_d", "op": "<", "val": 0.0}, {"col": "ema20_slope6", "op": "<", "val": 0.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 923.2429284340659},
    {"id": 'D_USDJPY_h16_D020_0.75x5.0', "symbol": 'USDJPY', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": "medpeer12_spread", "op": "<", "val": -1.5}, {"col": "ema20_d", "op": "<", "val": 0.0}, {"col": "ema20_slope6", "op": "<", "val": 0.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 869.6221459627329},
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
    """Base + extended features for one symbol frame (c44_engine logic,
    restricted to the columns C44-15 conditions on, plus atr14)."""
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
    hi24 = hi.shift(1).rolling(24, min_periods=24).max()
    lo24 = lo.shift(1).rolling(24, min_periods=24).min()
    feat["brk24"] = (cl - hi24) / atr
    feat["brk24_dn"] = (lo24 - cl) / atr
    return feat


def _panel_features(frames_norm):
    """Cross-pair (H+X) panel features per symbol (c44_panel logic,
    restricted to medpeer12_spread / xconf_b / xconf_s).

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


def evaluate_cycle44_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate C44-15 equations at one check time (h:30 UTC).

    frames: {symbol: H1 OHLC DataFrame indexed by candle-stamp} -- all
    20 symbols are used (the List D panel features are cross-pair).
    Only equations whose hour matches the check hour are evaluated.
    Signal features come from the (h-1):00 UTC candle (last completed
    as of h:30 UTC); entry price = open of the h:00 UTC candle.
    Returns one row per firing equation with TP/SL already clipped.
    """
    check = _as_utc(check_time_utc)
    hour = int(check.hour)
    if hour not in CYCLE44_CHECK_HOURS:
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
    for eq in C44_EQUATIONS:
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


def select_cycle44_entries(signals: pd.DataFrame, open_symbols=()) -> pd.DataFrame:
    """Up to 2 entries per check (the researched C44-15 assembly):
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


def is_cycle44_check_time(ts) -> bool:
    """True if ts (UTC) is at one of the C44 check hours (:30)."""
    t = _as_utc(ts)
    return int(t.hour) in CYCLE44_CHECK_HOURS and int(t.minute) == 30
