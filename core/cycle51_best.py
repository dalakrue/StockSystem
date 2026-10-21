"""Cycle 51 module: C51-20 (November-only system, improvement round 2).

28 equations (16 freshly mined mom/atr + 12 incumbent TREND fallbacks)
spanning 3 check hours (10:30, 11:30, 18:30 UTC = 17:00, 18:00, 01:00
MMT), exactly 1 entry per check, plus the book900 joint rule H023 as
a rerank overlay on top.

C51-20 REPLACES C26-33 as November's system. It won Improvement
Program 2 (Cycles 49-55, user order 2026-10-21): 20 end-to-end
processes built from the "H1 OHLC Monthly Currency Research Book"
(900 ranked combinations), every process judged end-to-end at the
2.5-pip primary cost with Priority-1-only promotion (entries/day >= 2,
win > 90%, leftover strictly better) plus a strict weak-rating drop.
Cycle 26 (C26-33) remains selectable.

Design: a fresh week-smooth momentum re-mine at the 2.5-pip cost
(December C48-style selection: standalone net@2.5 > 0, win@2.5 >= 0.85,
n >= 20, November red weeks <= 3; score = 1000*win25 + net25
- 60*red_weeks; top 6 mined per hour, at most 2 per symbol per hour),
assembled incumbent-style, with the incumbent's 12 TREND fallback
equations verbatim (tp 0.5x / sl 5.0x).

At 2.5-pip cost (vs C26-33): weak ratings (star1+star2) 4 (vs 11),
unseen net +356.6 pips (vs +134.5) / win 96.67% (vs 91.67%) /
leftover 73.2% (vs 25.6%) / entries/day 3.0 / checks 10/12 /
best N 90 (peak margin 47.4%, max DD 19.5%, sizing PASS) /
P(profit) 96.9% / discovery net +1091.1, win 89.57%.

THE H023 RERANK OVERLAY (the second layer)
H023 = catalyst H02 (matured historical leftover) x gate C03.
At each check, candidates whose screen passes are considered first
(incumbent score order inside each group; the pool is never deleted):
  * Historical leftover: from a reference ledger of virtual trades
    for the same pair and direction, entered every 48 clock hours
    from 2015-01-01 00:00 UTC at the first available H1 open, exited
    with TP 0.60 x entry Wilder ATR14 / SL 6.00 x ATR / 48h cap,
    SL-first, at 2.5-pip cost. At a signal, only trades closed by the
    signal close are used; entries within the preceding 3 years
    (1096 days); matched on ATR-percentile bin [0,33)/[33,67)/[67,100]
    (percentile = rank of the entry ATR within the prior 480 Wilder
    ATR values) and target-to-cost bin [0,4)/[4,8)/[8,inf) (target =
    candidate TP in pips / 2.5). If the same-pair sample has < 80
    trades, all pairs are pooled (same direction and bins,
    ATR-normalised outcomes). At most the 360 most recent.
    HistLeftover = mean(net) / mean(positive net); pass requires
    HistN >= 80 and HistLeftover >= 0.45.
  * Gate C03: H4 EMA20 slope over the last 3 completed H4 blocks,
    divided by H4 ATR14 (Wilder), in the candidate direction,
    >= -0.15.
The overlay's measured contribution: 16 boosted fills on discovery
(-18.8 pips incremental) and 6 on unseen (+45.5 pips).
The ledger is rebuilt from whatever history the supplied frames
carry; with short live frames the screen finds too few records and
no candidate is boosted (incumbent score order).

Fallback equations (FB_*): direction 'TREND' fires on every check so
the exactly-1-entry-per-check rule always has a candidate; live
direction resolves per-trade from the signal candle's mom24 sign
(BUY if > 0 else SELL) -- the same fixed rule the research used.

Source of truth: ~/workspace/fx/work_c51/results/WINNER.json
Full spec: ~/workspace/fx/work_c51/results/winner_spec.json
Discovery trade log: ~/workspace/fx/work_c51/results/winner_disc_log.csv
Unseen trade log: ~/workspace/fx/work_c51/results/winner_unseen_log.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE51_VERSION = "cycle51-c5120-v1"
CYCLE51_CHECK_HOURS = (10, 11, 18)  # checks at h:30 UTC
CYCLE51_SYMBOLS_N = 20
MAX_HOLD_HOURS = 48
BASE_SPREAD_PIPS = 1.0
TP_CLIP = (10.0, 500.0)
SL_CLIP = (5.0, 100.0)

# ---------------------------------------------------------------- equations --
C51_EQUATIONS = (
    {"id": 'F51_AUDCAD_h11_0', "symbol": 'AUDCAD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 5.0, "score": 1468.7857142857183},
    {"id": 'F51_AUDCAD_h11_1', "symbol": 'AUDCAD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1468.7857142857183},
    {"id": 'F51_AUDUSD_h11_2', "symbol": 'AUDUSD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1403.5499999999995},
    {"id": 'F51_EURNZD_h10_3', "symbol": 'EURNZD', "hour": 10, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.0, "sl_mult": 5.0, "score": 1397.2785714285733},
    {"id": 'F51_EURNZD_h10_4', "symbol": 'EURNZD', "hour": 10, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1397.2785714285733},
    {"id": 'F51_AUDUSD_h11_5', "symbol": 'AUDUSD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1362.1857142857157},
    {"id": 'F51_NZDCAD_h11_6', "symbol": 'NZDCAD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 1322.883928571429},
    {"id": 'F51_NZDCAD_h11_7', "symbol": 'NZDCAD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1322.883928571429},
    {"id": 'F51_EURAUD_h18_8', "symbol": 'EURAUD', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1264.3250000000028},
    {"id": 'F51_EURAUD_h18_9', "symbol": 'EURAUD', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1264.3250000000028},
    {"id": 'F51_GBPJPY_h10_10', "symbol": 'GBPJPY', "hour": 10, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1262.0249999999967},
    {"id": 'F51_GBPJPY_h10_11', "symbol": 'GBPJPY', "hour": 10, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1262.0249999999967},
    {"id": 'F51_CHFJPY_h18_12', "symbol": 'CHFJPY', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1239.9404556650127},
    {"id": 'F51_CHFJPY_h18_13', "symbol": 'CHFJPY', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1239.9404556650127},
    {"id": 'F51_AUDJPY_h18_14', "symbol": 'AUDJPY', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1215.1089285714206},
    {"id": 'F51_AUDJPY_h18_15', "symbol": 'AUDJPY', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1215.1089285714206},
    {"id": 'FB_EURUSD_h10_0', "symbol": 'EURUSD', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000001.0},
    {"id": 'FB_GBPUSD_h10_1', "symbol": 'GBPUSD', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000002.0},
    {"id": 'FB_USDJPY_h10_2', "symbol": 'USDJPY', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000003.0},
    {"id": 'FB_AUDUSD_h10_3', "symbol": 'AUDUSD', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000004.0},
    {"id": 'FB_EURJPY_h11_0', "symbol": 'EURJPY', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000005.0},
    {"id": 'FB_GBPJPY_h11_1', "symbol": 'GBPJPY', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000006.0},
    {"id": 'FB_AUDJPY_h11_2', "symbol": 'AUDJPY', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000007.0},
    {"id": 'FB_NZDUSD_h11_3', "symbol": 'NZDUSD', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000008.0},
    {"id": 'FB_EURCHF_h18_0', "symbol": 'EURCHF', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000009.0},
    {"id": 'FB_USDCAD_h18_1', "symbol": 'USDCAD', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000010.0},
    {"id": 'FB_CHFJPY_h18_2', "symbol": 'CHFJPY', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000011.0},
    {"id": 'FB_EURAUD_h18_3', "symbol": 'EURAUD', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000012.0},)

_COND_OPS = {">": lambda a, v: a > v, "<": lambda a, v: a < v,
             ">=": lambda a, v: a >= v, "<=": lambda a, v: a <= v}

_SYMBOLS = ("AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "AUDUSD", "CHFJPY",
            "EURAUD", "EURCAD", "EURCHF", "EURGBP", "EURJPY", "EURNZD",
            "EURUSD", "GBPJPY", "GBPUSD", "NZDCAD", "NZDUSD", "USDCAD",
            "USDCHF", "USDJPY")
_D3Y = np.timedelta64(1096, "D")

_FEAT_CACHE = {}
_LEDGER_CACHE = {}


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


def _trend_direction(mom24_value) -> str:
    """Fallback direction rule: BUY if signal-candle mom24 > 0 else SELL."""
    try:
        return "BUY" if float(mom24_value) > 0 else "SELL"
    except (TypeError, ValueError):
        return "SELL"


def _norm_frame(f):
    ff = f.copy()
    ff.index = pd.to_datetime(ff.index, utc=True).tz_localize(None)
    return ff.sort_index()


# ------------------------------------------------------------ Wilder ATR --
def _true_range(ff):
    h, l, c = ff["High"], ff["Low"], ff["Close"]
    pc = c.shift(1)
    return pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()],
                     axis=1).max(axis=1)


def _wilder_atr(ff, n=14):
    """Book ATR14: Wilder smoothing (ewm alpha=1/n, adjust=False)."""
    tr = _true_range(ff)
    return tr.ewm(alpha=1.0 / n, min_periods=n, adjust=False).mean()


def _pct_rank_prior_at(x, pos, w=480):
    """100*(#{prior w < x[pos]} + 0.5*#{prior w == x[pos]})/w over the
    window x[pos-w:pos] (current excluded). NaN if pos < w or any NaN
    in the window or the current value (research definition)."""
    if pos < w:
        return np.nan
    cur = x[pos]
    if not np.isfinite(cur):
        return np.nan
    win = x[pos - w:pos]
    if not np.isfinite(win).all():
        return np.nan
    return 100.0 * (float((win < cur).sum())
                    + 0.5 * float((win == cur).sum())) / w


def _pct_rank_prior(x, w=480, chunk=1500):
    """Vectorised _pct_rank_prior_at over a whole series (the research
    c51_common.rolling_pct_rank_prior implementation)."""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    out = np.full(n, np.nan)
    if n <= w:
        return out
    from numpy.lib.stride_tricks import sliding_window_view
    win = sliding_window_view(x, w + 1)  # rows: i-w .. i
    for s in range(0, len(win), chunk):
        blk = win[s:s + chunk]
        prior, cur = blk[:, :-1], blk[:, -1:]
        valid = ~np.isnan(prior).any(axis=1) & ~np.isnan(cur[:, 0])
        lt = (prior < cur).sum(axis=1)
        eq = (prior == cur).sum(axis=1)
        vals = 100.0 * (lt + 0.5 * eq) / w
        idx = np.arange(s, s + len(blk)) + w
        out[idx[valid]] = vals[valid]
    return out


def _h4_slope3(ff):
    """H4 EMA20 slope (bookfeat definition): completed H4 blocks
    (resample 4h, origin start-of-day), EMA20 ewm(span=20) of block
    closes, Wilder ATR14 of block true ranges, slope = (EMA - EMA 3
    blocks earlier) / ATR4; each H1 bar takes the last block whose
    END is <= the bar's close time."""
    gg = ff.sort_index()
    h4 = pd.DataFrame({
        "Open": gg["Open"].resample("4h", origin="start_day").first(),
        "High": gg["High"].resample("4h", origin="start_day").max(),
        "Low": gg["Low"].resample("4h", origin="start_day").min(),
        "Close": gg["Close"].resample("4h", origin="start_day").last(),
    }).dropna()
    if len(h4) == 0:
        return pd.Series(np.nan, index=gg.index)
    e20 = h4["Close"].ewm(span=20, min_periods=20, adjust=False).mean()
    tr4 = pd.concat([(h4["High"] - h4["Low"]),
                     (h4["High"] - h4["Close"].shift(1)).abs(),
                     (h4["Low"] - h4["Close"].shift(1)).abs()],
                    axis=1).max(axis=1)
    atr4 = tr4.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean()
    slope = (e20 - e20.shift(3)) / atr4
    slope_by_end = pd.Series(slope.to_numpy(),
                             index=h4.index + pd.Timedelta(hours=4))
    close_times = (gg.index + pd.Timedelta(hours=1)).to_numpy()
    posn = slope_by_end.index.get_indexer(close_times, method="ffill")
    vals = np.where(posn >= 0,
                    slope_by_end.to_numpy()[np.maximum(posn, 0)], np.nan)
    return pd.Series(vals, index=gg.index)


def _symbol_feat(sym, ff):
    """(engine features, Wilder ATR, atrpct480, h4slope3) for one
    normalised frame (cached)."""
    key = (sym, len(ff), ff.index[0], ff.index[-1])
    hit = _FEAT_CACHE.get(key)
    if hit is None:
        if len(_FEAT_CACHE) > 32:
            _FEAT_CACHE.clear()
        feat = add_cycle12_features(ff.reset_index(drop=True))
        feat.index = ff.index
        watr = _wilder_atr(ff).to_numpy(dtype=float)
        hit = (feat, watr, _pct_rank_prior(watr), _h4_slope3(ff))
        _FEAT_CACHE[key] = hit
    return hit


# ------------------------------------------------------------- H023 ledger --
def _sim_gross(o, h, l, c, entry_pos, sgn, tp_pips, sl_pips, pip,
               max_hold=MAX_HOLD_HOURS):
    """SL-first fixed-exit sim (research sim_x1 semantics, no cost,
    no TP/SL clipping inside the ledger). Returns (gross, exit_pos)."""
    entry_pos = np.asarray(entry_pos, dtype=np.int64)
    n = len(entry_pos)
    if n == 0:
        return np.array([]), np.array([], dtype=np.int64)
    N = len(o)
    epx = o[entry_pos].astype(float)
    tp_px = epx + sgn * np.asarray(tp_pips, dtype=float) * pip
    sl_px = epx - sgn * np.asarray(sl_pips, dtype=float) * pip
    H = int(max_hold)
    idx = np.minimum(entry_pos[:, None] + np.arange(H), N - 1)
    wh, wl, wc = h[idx], l[idx], c[idx]
    if sgn > 0:
        sl_hit = wl <= sl_px[:, None]
        tp_hit = wh >= tp_px[:, None]
    else:
        sl_hit = wh >= sl_px[:, None]
        tp_hit = wl <= tp_px[:, None]
    has_sl = sl_hit.any(axis=1)
    has_tp = tp_hit.any(axis=1)
    fsl = np.where(has_sl, sl_hit.argmax(axis=1), H + 1)
    ftp = np.where(has_tp, tp_hit.argmax(axis=1), H + 1)
    use_sl = has_sl & (fsl <= ftp)
    use_tp = has_tp & ~use_sl
    exit_px = np.where(use_sl, sl_px, np.where(use_tp, tp_px, wc[:, -1]))
    hold = np.where(use_sl, fsl + 1, np.where(use_tp, ftp + 1, H)).astype(np.int64)
    exit_pos = np.minimum(entry_pos + hold - 1, N - 1)
    gross = sgn * (exit_px - epx) / pip
    return gross, exit_pos


def _build_ledger(frames_norm):
    """General X1 ledger (faithful port of c51_ledger.build_general,
    0.60 TP variant): one virtual entry every 48 clock hours from
    2015-01-01 00:00 UTC at the first available H1 open, entry Wilder
    ATR taken from the preceding bar, TP 0.60 x ATR / SL 6.00 x ATR
    (unclipped), 48h cap, SL-first, outcomes net of 2.5 pips.
    Rows are sorted by entry time like the research GeneralLedger."""
    rows = []
    anchor = pd.Timestamp("2015-01-01 00:00")
    end = pd.Timestamp("2025-12-01 00:00")
    grid = pd.date_range(anchor, end, freq="48h").to_numpy()
    for s in _SYMBOLS:
        ff = frames_norm.get(s)
        if ff is None or len(ff) == 0:
            continue
        _, watr, atrpct, _ = _symbol_feat(s, ff)
        dt = ff.index.to_numpy()
        o = ff["Open"].to_numpy(dtype=float)
        h = ff["High"].to_numpy(dtype=float)
        l = ff["Low"].to_numpy(dtype=float)
        c = ff["Close"].to_numpy(dtype=float)
        pip = _pip_size(s)
        pos = np.searchsorted(dt, grid)
        pos = pos[(pos >= 1) & (pos < len(dt) - 1)]
        if len(pos) == 0:
            continue
        atr_e = watr[pos - 1]
        ok = np.isfinite(atr_e) & (atr_e > 0)
        pos, atr_e = pos[ok], atr_e[ok]
        if len(pos) == 0:
            continue
        sl_pips = 6.0 * atr_e / pip
        tp_pips = 0.60 * atr_e / pip
        for sgn in (1, -1):
            gross, exit_pos = _sim_gross(o, h, l, c, pos, sgn,
                                         tp_pips, sl_pips, pip)
            net = gross - 2.5
            rows.append(pd.DataFrame({
                "symbol": s, "dir": sgn,
                "entry_time": dt[pos], "exit_time": dt[exit_pos],
                "net_atr": net * pip / atr_e,
                "atrpct": atrpct[pos - 1],
                "tcost": (0.60 * atr_e / pip) / 2.5,
            }))
    if not rows:
        return {"by_pair": {}, "by_dir": {}}
    led = pd.concat(rows, ignore_index=True).sort_values("entry_time")
    by_pair, by_dir = {}, {}
    for (s, d), sub in led.groupby(["symbol", "dir"]):
        by_pair[(s, int(d))] = {c: sub[c].to_numpy()
                                for c in ("entry_time", "exit_time",
                                          "net_atr", "atrpct", "tcost")}
    for d, sub in led.groupby("dir"):
        by_dir[int(d)] = {c: sub[c].to_numpy()
                          for c in ("entry_time", "exit_time",
                                    "net_atr", "atrpct", "tcost")}
    return {"by_pair": by_pair, "by_dir": by_dir}


def _ledger_for(frames_norm):
    key = tuple((s, len(frames_norm[s]), frames_norm[s].index[-1])
                for s in _SYMBOLS if s in frames_norm)
    hit = _LEDGER_CACHE.get(key)
    if hit is None:
        hit = _build_ledger(frames_norm)
        _LEDGER_CACHE.clear()
        _LEDGER_CACHE[key] = hit
    return hit


def _bin(v, edges):
    if v is None or not np.isfinite(v):
        return -1
    for i, e in enumerate(edges):
        if v < e:
            return i
    return len(edges)


def _h023_hist_pass(led, sym, d, tc, atrpct, tcost):
    """H02 matured-leftover screen: matched sample -> HistN >= 80 and
    HistLeftover = mean(net_atr) / mean(positive net_atr) >= 0.45."""
    ab, tb = _bin(atrpct, (33.0, 67.0)), _bin(tcost, (4.0, 8.0))
    if ab < 0 or tb < 0:
        return False

    def mask(a):
        return ((a["exit_time"] <= tc)
                & (a["entry_time"] >= tc - _D3Y)
                & (np.digitize(a["atrpct"], (33.0, 67.0)) == ab)
                & (np.digitize(a["tcost"], (4.0, 8.0)) == tb))

    a = led["by_pair"].get((sym, d))
    idx = None
    if a is not None:
        m = mask(a)
        if m.sum() >= 80:
            idx = np.where(m)[0][-360:]
            src = a
    if idx is None:
        a = led["by_dir"].get(d)
        if a is None:
            return False
        idx = np.where(mask(a))[0][-360:]
        src = a
    if len(idx) < 80:
        return False
    net = src["net_atr"][idx]
    pos = net[net > 0]
    if len(pos) == 0:
        return False
    return float(net.mean() / pos.mean()) >= 0.45


# ------------------------------------------------------------- evaluation --
def evaluate_cycle51_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate C51-20 at one check time (h:30 UTC).

    Candidate generation as in the incumbent family (28 equations,
    signal candle (h-1):00, entry = open of the h:00 candle, TP/SL
    clipped), plus the H023 rerank flag in column 'rerank_pass':
    True when the matured historical-leftover screen passes for the
    candidate's pair+direction AND gate C03 passes (directional H4
    EMA20 slope >= -0.15). select_* considers passing candidates
    first (incumbent score order inside each group); the pool is
    never deleted.
    """
    check = _as_utc(check_time_utc)
    hour = int(check.hour)
    if hour not in CYCLE51_CHECK_HOURS:
        return pd.DataFrame()
    sig_stamp = (check - pd.Timedelta(hours=1, minutes=30)).tz_localize(None)
    ent_stamp = (check - pd.Timedelta(minutes=30)).tz_localize(None)
    frames_norm = {}
    for s, f in (frames or {}).items():
        if f is None or len(f) == 0:
            continue
        frames_norm[str(s).upper()] = _norm_frame(f)
    rows = []
    pending = []
    for eq in C51_EQUATIONS:
        if eq["hour"] != hour:
            continue
        sym = eq["symbol"]
        ff = frames_norm.get(sym)
        if ff is None:
            continue
        if sig_stamp not in ff.index or ent_stamp not in ff.index:
            continue
        feat, watr, atrpct, h4s = _symbol_feat(sym, ff)
        pos = ff.index.get_loc(sig_stamp)
        if isinstance(pos, (np.ndarray, slice)):
            continue
        row = feat.iloc[pos]
        if not all(_cond_ok(row, c) for c in eq["conditions"]):
            continue
        atr = float(row["atr14"])
        if not np.isfinite(atr) or atr <= 0:
            continue
        direction = eq["direction"]
        if direction == "TREND":
            direction = _trend_direction(row.get("mom24"))
        pip = _pip_size(sym)
        atr_pips = atr / pip
        tp = float(min(max(eq["tp_mult"] * atr_pips, TP_CLIP[0]), TP_CLIP[1]))
        sl = float(min(max(eq["sl_mult"] * atr_pips, SL_CLIP[0]), SL_CLIP[1]))
        out = {
            "check": check, "symbol": sym, "equation": eq["id"],
            "direction": direction, "score": eq["score"],
            "atr_pips": atr_pips,
            "entry_px": float(ff.loc[ent_stamp, "Open"]),
            "tp_pips": tp, "sl_pips": sl,
            "signal_candle": sig_stamp, "entry_candle": ent_stamp,
            "rerank_pass": False,
        }
        rows.append(out)
        pending.append((out, sym, direction, pos, atrpct, h4s, tp))
    if pending:
        led = _ledger_for(frames_norm)
        tc = (sig_stamp + pd.Timedelta(hours=1)).to_datetime64()
        for out, sym, direction, pos, atrpct, h4s, tp in pending:
            d = 1 if direction == "BUY" else -1
            h4d = d * float(h4s.iloc[pos])
            if not (h4d >= -0.15):
                continue
            out["rerank_pass"] = bool(_h023_hist_pass(
                led, sym, d, tc, float(atrpct[pos]), tp / 2.5))
    return pd.DataFrame(rows)


def select_cycle51_entries(signals: pd.DataFrame, open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: H023-passing candidates first, then
    incumbent score order (stable sort), max 1 open trade per symbol.
    Ties in (tier, score) break by equation id, as in the research
    walk (order key: tier, -score, eq_id)."""
    if signals is None or len(signals) == 0:
        return signals.iloc[0:0] if signals is not None else pd.DataFrame()
    held = {str(s).upper() for s in (open_symbols or ())}
    df = signals.copy()
    if "rerank_pass" not in df.columns:
        df["rerank_pass"] = False
    df = df.assign(_tier=(~df["rerank_pass"].astype(bool)).astype(int),
                   _neg=-df["score"].astype(float))
    df = df.sort_values(["_tier", "_neg", "equation"], kind="mergesort")
    out = []
    for _, row in df.iterrows():
        if len(out) >= 1:
            break
        if str(row["symbol"]).upper() in held:
            continue
        out.append(row.drop(labels=["_tier", "_neg"]))
        held.add(str(row["symbol"]).upper())
    return pd.DataFrame(out)


def is_cycle51_check_time(ts) -> bool:
    """True if ts (UTC) is at one of the C51 check hours (:30)."""
    t = _as_utc(ts)
    return int(t.hour) in CYCLE51_CHECK_HOURS and int(t.minute) == 30
