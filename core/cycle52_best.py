"""Cycle 52 module: C52-04 (January-only system, improvement round 2).

24 equations (15 mined mom/atr + 9 TREND fallbacks) spanning 3 check
hours (11:30, 13:30, 17:30 UTC = 18:00, 20:00, 00:00 MMT), exactly 1
entry per check -- the incumbent C28-30 system VERBATIM, plus ONE
added selection layer: the book900 joint rule H012 used as a per-check
reranker (book experiment mode "R").

C52-04 REPLACES C28-30 as January's system. It won Improvement
Program 2 (Cycles 49-55, user order 2026-10-21): 20 end-to-end
processes built from the "H1 OHLC Monthly Currency Research Book"
(900 ranked combinations), every process judged end-to-end at the
2.5-pip primary cost with Priority-1-only promotion (entries/day >= 2,
win > 90%, leftover strictly better) plus a strict weak-rating drop.
Cycle 28 (C28-30) remains selectable.

At 2.5-pip cost (vs C28-30): weak ratings (star1+star2) 5 (vs 11),
unseen net +321.6 pips (vs +201.4) / win 93.94% (vs 90.91%) /
leftover 61.5% (vs 36.5%) / entries/day 2.87 / checks 9/12 /
discovery net +278.9 (incumbent +663.0; 3 of 9 January blocks red,
same count as the incumbent).

THE H012 RERANK LAYER (the only change vs C28-30)
At each check, before the top-1 pick, every candidate is tested
against rule H012 = catalyst H02 (Wilson95) x gate C02:
  * H02: simulate X1 virtual trades (TP 0.60 x ATR14 / SL 6.00 x
    ATR14 / 48h cap, SL-first, 2.5-pip cost) for the candidate's
    pair+direction on a fixed grid (one virtual entry every 48 clock
    hours from 2015-01-01 00:00 UTC). For a candidate whose signal
    candle is t, take ledger trades of the same pair+direction that
    closed by t's close, entered within the preceding 3 years, and
    match the candidate's ATR-percentile bin ([0,33)/[33,67)/[67,100]
    of the pair's own ledger ATRs in the preceding 3 years) and
    target-to-cost bin ([0,4)/[4,8)/[8,inf), target = the candidate's
    own tp_pips / 2.5), keeping at most the 360 most recent. If fewer
    than 80 same-pair records match, pool all pairs in the same
    direction (ATR-normalised outcomes, same bins). H02 passes iff
    matched N >= 80 AND the Wilson lower bound (z = 1.96) of the
    matched win rate >= 0.85.
  * C02: the candidate symbol's ATR percentile over the preceding
    480 ATR values (excluding the current) must lie in [15, 85].
Candidates that pass H012 are considered first; within each group
(pass / no-pass) the incumbent score order decides. The pool is never
deleted -- a check with no passing candidate trades exactly as the
incumbent. Occupancy and top-1 rules are unchanged.
ATR everywhere is the engine ATR14 (rolling mean of true range),
including inside the ledger and the percentile bins (a deliberate,
documented simplification of the book's Wilder ATR, so the layer is
consistent with the incumbent's own exits/features). All ledger
quantities are causal. The ledger is rebuilt from whatever history
the supplied frames carry; with short live frames the screen simply
finds too few records and no candidate is boosted (incumbent order).

Fallback equations (FB_*): direction 'TREND' fires on every check so
the exactly-1-entry-per-check rule always has a candidate; live
direction resolves per-trade from the signal candle's mom24 sign
(BUY if > 0 else SELL) -- the same fixed rule the research used.

Source of truth: ~/workspace/fx/work_c52/results/WINNER.json
Full spec: ~/workspace/fx/work_c52/results/WINNER_SPEC.md
Discovery trade log: ~/workspace/fx/work_c52/results/WINNER_disc_log.csv
Unseen trade log: ~/workspace/fx/work_c52/results/WINNER_unseen_log.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE52_VERSION = "cycle52-c5204-v1"
CYCLE52_CHECK_HOURS = (11, 13, 17)  # checks at h:30 UTC
CYCLE52_SYMBOLS_N = 10
MAX_HOLD_HOURS = 48
BASE_SPREAD_PIPS = 1.0
TP_CLIP = (10.0, 500.0)
SL_CLIP = (5.0, 100.0)

# ---------------------------------------------------------------- equations --
C52_EQUATIONS = (
    {"id": 'mom_USDCAD_h11_momS_T2.5_A1.0_1.25x8', "symbol": 'USDCAD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 971.8205553571429},
    {"id": 'mom_EURGBP_h11_momS_T1.5_A1.0_1.25x8', "symbol": 'EURGBP', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 970.8838388655463},
    {"id": 'mom_AUDUSD_h11_momS_T0.75_A0.9_1.25x5', "symbol": 'AUDUSD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 956.7476409161492},
    {"id": 'mom_GBPUSD_h11_momB_T2.0_A1.0_0.5x8', "symbol": 'GBPUSD', "hour": 11, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 944.5815373015873},
    {"id": 'mom_AUDNZD_h11_momS_T0.75_A1.0_1.0x8', "symbol": 'AUDNZD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 914.475957142857},
    {"id": 'mom_AUDNZD_h13_momS_T0.75_A1.0_1.0x5', "symbol": 'AUDNZD', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 5.0, "score": 967.9883426267281},
    {"id": 'mom_AUDUSD_h13_momS_T0.75_A1.0_0.75x8', "symbol": 'AUDUSD', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 967.9528176267281},
    {"id": 'mom_USDCAD_h13_momS_T2.5_A1.0_0.75x8', "symbol": 'USDCAD', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 966.8598488095238},
    {"id": 'mom_EURUSD_h13_momB_T1.0_A1.0_1.0x8', "symbol": 'EURUSD', "hour": 13, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -1.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 961.3261422969189},
    {"id": 'mom_EURGBP_h13_momS_T2.5_A1.0_1.25x8', "symbol": 'EURGBP', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 954.7206634740261},
    {"id": 'mom_AUDNZD_h17_momS_T1.0_A1.0_0.75x5', "symbol": 'AUDNZD', "hour": 17, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.2548767857143},
    {"id": 'mom_USDJPY_h17_momB_T0.75_A1.0_0.75x8', "symbol": 'USDJPY', "hour": 17, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 950.1085375},
    {"id": 'mom_NZDCAD_h17_momS_T0.75_A1.0_0.3x5', "symbol": 'NZDCAD', "hour": 17, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
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
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.2548767857143},
    {"id": 'mom_AUDNZD_h17_momS_T1.0_A1.0_0.3x5', "symbol": 'AUDNZD', "hour": 17, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 1000.252},)

_COND_OPS = {">": lambda a, v: a > v, "<": lambda a, v: a < v,
             ">=": lambda a, v: a >= v, "<=": lambda a, v: a <= v}

_SYMBOLS = ("AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "AUDUSD", "CHFJPY",
            "EURAUD", "EURCAD", "EURCHF", "EURGBP", "EURJPY", "EURNZD",
            "EURUSD", "GBPJPY", "GBPUSD", "NZDCAD", "NZDUSD", "USDCAD",
            "USDCHF", "USDJPY")
_YEAR_NS = 365.25 * 24 * 3600 * 1e9
_LEDGER_ANCHOR_NS = int(pd.Timestamp("2015-01-01 00:00").value)
_LEDGER_STEP_NS = 48 * 3600 * 1_000_000_000

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


def _symbol_feat(sym, ff):
    """add_cycle12_features output for a normalised frame (cached)."""
    key = (sym, len(ff), ff.index[0], ff.index[-1])
    hit = _FEAT_CACHE.get(key)
    if hit is None:
        if len(_FEAT_CACHE) > 32:
            _FEAT_CACHE.clear()
        hit = add_cycle12_features(ff.reset_index(drop=True))
        hit.index = ff.index
        _FEAT_CACHE[key] = hit
    return hit


def _atrpct480_at(feat, pos):
    """ATR percentile (C02): rank of atr14[pos] among the 480 preceding
    atr14 values (current excluded), 100*(#less + 0.5*#equal)/480.
    NaN when fewer than 480 preceding values (research definition)."""
    if pos < 480:
        return np.nan
    av = feat["atr14"].to_numpy(dtype=float)
    cur = av[pos]
    if not np.isfinite(cur):
        return np.nan
    w = av[pos - 480:pos]
    return 100.0 * (float((w < cur).sum()) + 0.5 * float((w == cur).sum())) / 480.0


# ------------------------------------------------------------- H012 ledger --
def _sim_gross(o, h, l, c, entry_pos, direction, tp_pips, sl_pips, pip,
               max_hold=MAX_HOLD_HOURS):
    """Fixed-exit SL-first simulation (research c52_sim semantics).
    Returns (gross_pips, exit_pos) arrays; cost NOT deducted here."""
    entry_pos = np.asarray(entry_pos, dtype=np.int64)
    n = len(entry_pos)
    if n == 0:
        return np.array([]), np.array([], dtype=np.int64)
    N = len(o)
    epx = o[entry_pos].astype(float)
    tp_pips = np.asarray(tp_pips, dtype=float)
    sl_pips = np.asarray(sl_pips, dtype=float)
    buy = (direction == "BUY")
    sgn = 1.0 if buy else -1.0
    tp_px = epx + sgn * tp_pips * pip
    sl_px = epx - sgn * sl_pips * pip
    H = int(max_hold)
    idx = np.minimum(entry_pos[:, None] + np.arange(H), N - 1)
    wh, wl, wc = h[idx], l[idx], c[idx]
    if buy:
        sl_hit = wl <= sl_px[:, None]
        tp_hit = wh >= tp_px[:, None]
    else:
        sl_hit = wh >= sl_px[:, None]
        tp_hit = wl <= tp_px[:, None]
    has_sl = sl_hit.any(axis=1)
    has_tp = tp_hit.any(axis=1)
    fsl = sl_hit.argmax(axis=1)
    ftp = tp_hit.argmax(axis=1)
    use_sl = has_sl & (~has_tp | (fsl <= ftp))   # SL-first on ties
    use_tp = has_tp & ~use_sl
    exit_px = np.where(use_sl, sl_px, np.where(use_tp, tp_px, wc[:, -1]))
    hold = np.where(use_sl, fsl + 1, np.where(use_tp, ftp + 1, H)).astype(np.int64)
    exit_pos = np.minimum(entry_pos + hold - 1, N - 1)
    gross = sgn * (exit_px - epx) / pip
    return gross, exit_pos


def _atr_bins(entry_ns, entry_atr, window_years=3.0):
    """Causal ATR-percentile bin of each ledger entry vs the pair's own
    entries in the preceding window (strictly before, entry-anchored)."""
    bins = np.zeros(len(entry_ns), dtype=int)
    for i in range(len(entry_ns)):
        lo = np.searchsorted(entry_ns, entry_ns[i] - window_years * _YEAR_NS)
        if i - lo < 1:
            bins[i] = 1
            continue
        w = entry_atr[lo:i]
        pct = 100.0 * ((w < entry_atr[i]).sum()
                       + 0.5 * (w == entry_atr[i]).sum()) / len(w)
        bins[i] = 0 if pct < 33 else (1 if pct < 67 else 2)
    return bins


def _build_ledger(frames_norm):
    """X1 virtual-trade ledger (H012), faithful port of the Cycle 52
    research builder (c52_book.build_ledger, '60' variant + bins):
    one entry every 48 clock hours from 2015-01-01 00:00 UTC per pair,
    TP 0.60 x entry ATR14 / SL 6.00 x ATR14 / 48h, SL-first, outcomes
    recorded net of the 2.5-pip cost in ATR units. Records are sorted
    by exit time, exactly as in the research."""
    led = {}
    for s in _SYMBOLS:
        ff = frames_norm.get(s)
        if ff is None or len(ff) == 0:
            continue
        feat = _symbol_feat(s, ff)
        times = ff.index
        tns = times.to_numpy().astype("datetime64[ns]").astype(np.int64)
        atr = feat["atr14"].to_numpy(dtype=float)
        o = ff["Open"].to_numpy(dtype=float)
        h = ff["High"].to_numpy(dtype=float)
        l = ff["Low"].to_numpy(dtype=float)
        c = ff["Close"].to_numpy(dtype=float)
        pip = _pip_size(s)
        grid_mask = ((tns - _LEDGER_ANCHOR_NS) % _LEDGER_STEP_NS) == 0
        epos = np.where(grid_mask & np.isfinite(atr))[0]
        epos = epos[epos + 48 < len(ff)]
        if len(epos) == 0:
            continue
        entry_ns = tns[epos]
        entry_atr = atr[epos]
        abin = _atr_bins(entry_ns, entry_atr)
        tp = np.clip(0.60 * entry_atr / pip, *TP_CLIP)
        sl = np.clip(6.0 * entry_atr / pip, *SL_CLIP)
        tc_bin = np.where(tp / 2.5 < 4, 0, np.where(tp / 2.5 < 8, 1, 2))
        for dname in ("BUY", "SELL"):
            gross, exit_pos = _sim_gross(o, h, l, c, epos, dname, tp, sl, pip)
            net = gross - 2.5
            rec = {"entry_ns": entry_ns, "entry_atr": entry_atr,
                   "atr_bin": abin, "tc_bin": tc_bin,
                   "exit_ns": tns[exit_pos] + int(3600e9),
                   "net_atr": net * pip / entry_atr}
            order = np.argsort(rec["exit_ns"])
            for k in list(rec.keys()):
                rec[k] = rec[k][order]
            led[(s, dname)] = rec
    for dname in ("BUY", "SELL"):
        parts = [led[(s, dname)] for s in _SYMBOLS if (s, dname) in led]
        if not parts:
            continue
        pool = {}
        for k in parts[0].keys():
            pool[k] = np.concatenate([p[k] for p in parts])
        order = np.argsort(pool["exit_ns"])
        for k in list(pool.keys()):
            pool[k] = pool[k][order]
        led[("POOL", dname)] = pool
    return led


def _ledger_for(frames_norm):
    key = tuple((s, len(frames_norm[s]), frames_norm[s].index[-1])
                for s in _SYMBOLS if s in frames_norm)
    hit = _LEDGER_CACHE.get(key)
    if hit is None:
        hit = _build_ledger(frames_norm)
        _LEDGER_CACHE.clear()
        _LEDGER_CACHE[key] = hit
    return hit


def _cand_atr_bin(led_pair, t_ns, atr_now):
    e = led_pair
    lo = np.searchsorted(e["entry_ns"], t_ns - 3 * _YEAR_NS)
    hi = np.searchsorted(e["entry_ns"], t_ns)
    if hi - lo < 1:
        return None
    w = e["entry_atr"][lo:hi]
    pct = 100.0 * ((w < atr_now).sum() + 0.5 * (w == atr_now).sum()) / len(w)
    return 0 if pct < 33 else (1 if pct < 67 else 2)


def _wilson_lb(nets):
    """Wilson lower bound (z=1.96) of the win rate of net outcomes."""
    n = len(nets)
    if n == 0:
        return 0.0
    ph = float((nets > 0).mean())
    z = 1.96
    return float((ph + z * z / (2 * n)
                  - z * np.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)))
                 / (1 + z * z / n))


def _h012_pass(led, sym, direction, t_ns, atr_now, tp_pips):
    """H02 (Wilson95) catalyst of H012 against the X1 ledger."""
    pair = led.get((sym, direction))
    if pair is None:
        return False
    abin = _cand_atr_bin(pair, t_ns, atr_now)
    if abin is None:
        return False
    tcbin = 0 if tp_pips / 2.5 < 4 else (1 if tp_pips / 2.5 < 8 else 2)
    t_close = t_ns + int(3600e9)

    def matched(src):
        m = ((src["exit_ns"] <= t_close)
             & (src["entry_ns"] >= t_ns - 3.0 * _YEAR_NS)
             & (src["atr_bin"] == abin) & (src["tc_bin"] == tcbin))
        idx = np.where(m)[0]
        if len(idx) > 360:
            idx = idx[-360:]
        return idx

    idx = matched(pair)
    src = pair
    if len(idx) < 80:
        pool = led.get(("POOL", direction))
        if pool is not None:
            idxp = matched(pool)
            if len(idxp) > len(idx):
                src, idx = pool, idxp
    if len(idx) < 80:
        return False
    return _wilson_lb(src["net_atr"][idx]) >= 0.85


# ------------------------------------------------------------- evaluation --
def evaluate_cycle52_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate C52-04 at one check time (h:30 UTC).

    Same candidate generation as C28-30 (24 equations, signal candle
    (h-1):00, entry = open of the h:00 candle, TP/SL clipped), plus the
    H012 rerank flag in column 'rerank_pass': True when gate C02 passes
    (signal ATR percentile in [15, 85]) AND the H02 Wilson95 ledger
    screen passes for the candidate's pair+direction. select_* then
    considers passing candidates first (incumbent score order inside
    each group); the pool is never deleted.
    """
    check = _as_utc(check_time_utc)
    hour = int(check.hour)
    if hour not in CYCLE52_CHECK_HOURS:
        return pd.DataFrame()
    sig_stamp = (check - pd.Timedelta(hours=1, minutes=30)).tz_localize(None)
    ent_stamp = (check - pd.Timedelta(minutes=30)).tz_localize(None)
    frames_norm = {}
    for s, f in (frames or {}).items():
        if f is None or len(f) == 0:
            continue
        frames_norm[str(s).upper()] = _norm_frame(f)
    rows = []
    pending = []   # (row, sym, direction, sig_pos, feat)
    for eq in C52_EQUATIONS:
        if eq["hour"] != hour:
            continue
        sym = eq["symbol"]
        ff = frames_norm.get(sym)
        if ff is None:
            continue
        if sig_stamp not in ff.index or ent_stamp not in ff.index:
            continue
        feat = _symbol_feat(sym, ff)
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
        pending.append((out, sym, direction, pos, feat, atr, tp))
    if pending:
        led = _ledger_for(frames_norm)
        t_ns = int(sig_stamp.value)
        for out, sym, direction, pos, feat, atr, tp in pending:
            pct = _atrpct480_at(feat, pos)
            if not (15.0 <= pct <= 85.0):
                continue
            out["rerank_pass"] = bool(
                _h012_pass(led, sym, direction, t_ns, atr, tp))
    return pd.DataFrame(rows)


def select_cycle52_entries(signals: pd.DataFrame, open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: H012-passing candidates first, then
    incumbent score order (stable sort), max 1 open trade per symbol."""
    if signals is None or len(signals) == 0:
        return signals.iloc[0:0] if signals is not None else pd.DataFrame()
    held = {str(s).upper() for s in (open_symbols or ())}
    df = signals.copy()
    if "rerank_pass" not in df.columns:
        df["rerank_pass"] = False
    df = df.assign(_tier=(~df["rerank_pass"].astype(bool)).astype(int))
    df = df.sort_values(["_tier", "score"], ascending=[True, False],
                        kind="mergesort")
    out = []
    for _, row in df.iterrows():
        if len(out) >= 1:
            break
        if str(row["symbol"]).upper() in held:
            continue
        out.append(row.drop(labels=["_tier"]))
        held.add(str(row["symbol"]).upper())
    return pd.DataFrame(out)


def is_cycle52_check_time(ts) -> bool:
    """True if ts (UTC) is at one of the C52 check hours (:30)."""
    t = _as_utc(ts)
    return int(t.hour) in CYCLE52_CHECK_HOURS and int(t.minute) == 30
