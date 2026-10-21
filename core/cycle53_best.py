"""Cycle 53 module: C53-07 (March-only system, improvement round 2).

24 equations (15 mined mom/atr + 9 TREND fallbacks) spanning 3 check
hours (11:30, 16:30, 17:30 UTC = 18:00, 23:00, 00:00 MMT), exactly 1
entry per check -- the incumbent C30-31 system VERBATIM, plus ONE
added selection layer: the book900 joint rule G013 used as a per-check
reranker (book experiment mode "R").

C53-07 REPLACES C30-31 as March's system. It won Improvement
Program 2 (Cycles 49-55, user order 2026-10-21): 20 end-to-end
processes built from the "H1 OHLC Monthly Currency Research Book"
(900 ranked combinations), every process judged end-to-end at the
2.5-pip primary cost with Priority-1-only promotion (entries/day >= 2,
win > 90%, leftover strictly better) plus a strict weak-rating drop.
Cycle 30 (C30-31) remains selectable.

At 2.5-pip cost (vs C30-31): weak ratings (star1+star2) 2 (vs 9),
unseen net +225.0 pips (vs +140.8) / win 92.06% (vs 90.48%) /
leftover 47.2% (vs 29.6%) / entries/day 3.0 / checks 10/12 /
best N 102 (peak margin 48.0%, max DD 19.6%, sizing PASS) /
P(profit) 98.6%. Discovery net +1,408.2 (incumbent +1,773.4) but
healthy: 8 of 9 March blocks green. G013 fired on 217 of ~2,500
candidate points and changed 138 picks across 2016-2025.

THE G013 RERANK LAYER (the only change vs C30-31)
G013 = catalyst G02 (PeerStrengthAcceleration) x gate C03 (H4 trend
readiness), March menu rank 29. At each check, candidates that pass
G013 are looked at first (incumbent score order inside each group);
everyone else keeps the usual score order. No candidate is added or
removed; no exit changes.
  * G02: for every pair, z12 = log(C/C[-12]) / (population SD of the
    480 preceding hourly log returns * sqrt(12)) on the signal
    candle. A currency's score = mean of oriented z12 over all pairs
    containing it (+z if the currency is the pair base, -z if quote),
    EXCLUDING the candidate pair itself; at least 3 valid incident
    pairs required per currency. For a candidate buying currency B
    and selling currency S: Strength = score(B) - score(S);
    StrengthAccel(3) = Strength[t] - Strength[t-3]; Breadth(K) =
    fraction of K's oriented incident z12 values > 0 (same
    exclusion). PASS requires StrengthAccel(3) > 0.50 AND
    Breadth(B) - Breadth(S) > 0.20.
  * C03: PASS requires direction * H4EMA20Slope(3) >= -0.15, where
    H4EMA20Slope(3) = (EMA20 - EMA20 3 blocks earlier) / Wilder
    ATR14, built only from completed UTC 4h blocks (EMA20 seeded by
    the mean of the first 20 H4 closes, alpha 2/21; Wilder ATR14
    seeded by the mean of the first 14 H4 true ranges).
The panel is rebuilt from whatever history the supplied frames
carry; with short live frames the z-scores are undefined and no
candidate is boosted (incumbent score order).

Fallback equations (FB_*): direction 'TREND' fires on every check so
the exactly-1-entry-per-check rule always has a candidate; live
direction resolves per-trade from the signal candle's mom24 sign
(BUY if > 0 else SELL) -- the same fixed rule the research used.

Source of truth: ~/workspace/fx/work_c53/results/WINNER.json
Full spec: ~/workspace/fx/work_c53/results/WINNER_SPEC.json
Discovery trade log: ~/workspace/fx/work_c53/results/WINNER_disc_log.csv
Unseen trade log: ~/workspace/fx/work_c53/results/WINNER_unseen_log.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE53_VERSION = "cycle53-c5307-v1"
CYCLE53_CHECK_HOURS = (11, 16, 17)  # checks at h:30 UTC
CYCLE53_SYMBOLS_N = 20
MAX_HOLD_HOURS = 48
BASE_SPREAD_PIPS = 1.0
TP_CLIP = (10.0, 500.0)
SL_CLIP = (5.0, 100.0)

# ---------------------------------------------------------------- equations --
C53_EQUATIONS = (
    {"id": 'mom_NZDCAD_h11_momB_T2.0_A0.9_1.0x8', "symbol": 'NZDCAD', "hour": 11, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.0}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 970.9303924369748},
    {"id": 'mom_USDCHF_h11_momB_T2.5_A0.9_1.25x8', "symbol": 'USDCHF', "hour": 11, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.5}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 913.2169889751552},
    {"id": 'mom_EURUSD_h11_momB_T2.0_A0.9_0.75x8', "symbol": 'EURUSD', "hour": 11, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.0}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 911.8895987394958},
    {"id": 'mom_AUDNZD_h11_momS_T0.75_A1.0_0.75x8', "symbol": 'AUDNZD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 909.2657126623376},
    {"id": 'mom_USDCAD_h11_momB_T0.75_A0.9_0.5x8', "symbol": 'USDCAD', "hour": 11, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 906.2684392857142},
    {"id": 'mom_AUDNZD_h16_momS_T0.75_A1.0_0.5x8', "symbol": 'AUDNZD', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.3960285714285},
    {"id": 'mom_NZDCAD_h16_momS_T1.0_A1.0_0.5x5', "symbol": 'NZDCAD', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 965.7091199507389},
    {"id": 'mom_USDCAD_h16_momS_T1.0_A1.0_0.75x8', "symbol": 'USDCAD', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 958.5618494047619},
    {"id": 'mom_NZDUSD_h16_momS_T2.5_A1.0_0.75x3', "symbol": 'NZDUSD', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 3.0, "score": 904.8740690476191},
    {"id": 'mom_EURGBP_h16_momB_T0.75_A1.0_1.25x5', "symbol": 'EURGBP', "hour": 16, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 900.1055785714286},
    {"id": 'mom_NZDCAD_h17_momS_T0.75_A1.0_0.75x8', "symbol": 'NZDCAD', "hour": 17, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 965.7696985221675},
    {"id": 'mom_AUDNZD_h17_momS_T0.75_A0.9_1.25x5', "symbol": 'AUDNZD', "hour": 17, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 960.22975},
    {"id": 'mom_NZDUSD_h17_momB_T1.5_A1.0_1.25x8', "symbol": 'NZDUSD', "hour": 17, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 909.3016465909091},
    {"id": 'mom_USDCAD_h17_momB_T1.5_A1.0_0.5x3', "symbol": 'USDCAD', "hour": 17, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 3.0, "score": 900.0832964285714},
    {"id": 'mom_USDCHF_h17_momS_T1.0_A1.0_0.75x8', "symbol": 'USDCHF', "hour": 17, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
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
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000009.0},)

_COND_OPS = {">": lambda a, v: a > v, "<": lambda a, v: a < v,
             ">=": lambda a, v: a >= v, "<=": lambda a, v: a <= v}

_SYMBOLS = ("AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "AUDUSD", "CHFJPY",
            "EURAUD", "EURCAD", "EURCHF", "EURGBP", "EURJPY", "EURNZD",
            "EURUSD", "GBPJPY", "GBPUSD", "NZDCAD", "NZDUSD", "USDCAD",
            "USDCHF", "USDJPY")
_CURRENCIES = ("EUR", "USD", "JPY", "GBP", "CHF", "CAD", "AUD", "NZD")
_SYM_IDX = {s: i for i, s in enumerate(_SYMBOLS)}
_INCIDENT = {}
for _s in _SYMBOLS:
    for _pos, _c in enumerate((_s[:3], _s[3:])):
        _INCIDENT.setdefault(_c, []).append(
            (_SYM_IDX[_s], 1.0 if _pos == 0 else -1.0))

_FEAT_CACHE = {}
_PANEL_CACHE = {}


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


# ------------------------------------------------------------- H4 slope --
def _wilder_atr_arr(tr, n=14):
    """Wilder ATR: seed = mean of first n TR at index n-1, then
    ATR = (13*prior + TR)/14 (book definition, research port)."""
    out = np.full(len(tr), np.nan)
    if len(tr) < n:
        return out
    out[n - 1] = np.nanmean(tr[:n])
    for i in range(n, len(tr)):
        out[i] = (13.0 * out[i - 1] + tr[i]) / 14.0
    return out


def _ema_seeded_arr(x, span=20):
    """EMA seeded by the first-`span` mean, alpha = 2/(span+1)."""
    out = np.full(len(x), np.nan)
    if len(x) < span:
        return out
    a = 2.0 / (span + 1.0)
    out[span - 1] = np.nanmean(x[:span])
    for i in range(span, len(x)):
        out[i] = out[i - 1] + a * (x[i] - out[i - 1])
    return out


def _h4_slope3(ff):
    """H4EMA20Slope(3) per H1 bar (c53_features definition): UTC 4h
    blocks (floor), block Wilder ATR14 + seeded EMA20 of block closes,
    slope = (EMA - EMA 3 blocks earlier) / block ATR; each bar takes
    the last block whose end is <= the bar's close time."""
    idx = ff.index
    H = ff["High"].to_numpy(dtype=float)
    L = ff["Low"].to_numpy(dtype=float)
    C = ff["Close"].to_numpy(dtype=float)
    tmp = pd.DataFrame({"H": H, "L": L, "C": C}, index=idx)
    blk = tmp.groupby(tmp.index.floor("4h")).agg(
        H=("H", "max"), L=("L", "min"), C=("C", "last"))
    bh, bl, bc = (blk["H"].to_numpy(), blk["L"].to_numpy(),
                  blk["C"].to_numpy())
    bcp = np.concatenate([[np.nan], bc[:-1]])
    btr = np.maximum(bh - bl, np.maximum(np.abs(bh - bcp),
                                         np.abs(bl - bcp)))
    if len(btr):
        btr[0] = bh[0] - bl[0]
    batr = _wilder_atr_arr(btr)
    bema = _ema_seeded_arr(bc, 20)
    bslope = (bema - pd.Series(bema).shift(3).to_numpy()) \
        / np.where(batr == 0, np.nan, batr)
    blk_end = (blk.index + pd.Timedelta(hours=4)).to_numpy()
    bar_close = (idx + pd.Timedelta(hours=1)).to_numpy()
    pos = np.searchsorted(blk_end, bar_close, side="right") - 1
    out = np.where(pos >= 0, bslope[np.maximum(pos, 0)], np.nan)
    return pd.Series(out, index=idx)


def _symbol_feat(sym, ff):
    """(engine features, h4slope3) for one normalised frame (cached)."""
    key = (sym, len(ff), ff.index[0], ff.index[-1])
    hit = _FEAT_CACHE.get(key)
    if hit is None:
        if len(_FEAT_CACHE) > 32:
            _FEAT_CACHE.clear()
        feat = add_cycle12_features(ff.reset_index(drop=True))
        feat.index = ff.index
        hit = (feat, _h4_slope3(ff))
        _FEAT_CACHE[key] = hit
    return hit


# ------------------------------------------------------------- z12 panel --
def _panel_for(frames_norm):
    """z12 matrix (float32, research dtype) on the union timestamp
    index of all supplied frames + position lookup (cached)."""
    key = tuple((s, len(frames_norm[s]), frames_norm[s].index[-1])
                for s in _SYMBOLS if s in frames_norm)
    hit = _PANEL_CACHE.get(key)
    if hit is not None:
        return hit
    idx = None
    for s in _SYMBOLS:
        f = frames_norm.get(s)
        if f is None or len(f) == 0:
            continue
        idx = f.index if idx is None else idx.union(f.index)
    if idx is None:
        hit = (None, {}, None)
        _PANEL_CACHE.clear()
        _PANEL_CACHE[key] = hit
        return hit
    idx = idx.sort_values()
    T = len(idx)
    Z = np.full((len(_SYMBOLS), T), np.nan, dtype=np.float32)
    for j, s in enumerate(_SYMBOLS):
        f = frames_norm.get(s)
        if f is None or len(f) == 0:
            continue
        c = f["Close"]
        lr = np.log(c / c.shift(1))
        sd480 = lr.rolling(480, min_periods=480).std(ddof=0)
        z = np.log(c / c.shift(12)) / (sd480 * np.sqrt(12.0))
        Z[j] = z.reindex(idx).to_numpy(dtype=np.float32)
    hit = (idx, {t: i for i, t in enumerate(idx)}, Z)
    _PANEL_CACHE.clear()
    _PANEL_CACHE[key] = hit
    return hit


def _peer_means(Z, j, ppos):
    """Currency mean oriented z12 at panel position ppos, candidate
    pair j excluded; None if any currency has < 3 valid pairs."""
    row = Z[:, ppos]
    means = {}
    for curr, lst in _INCIDENT.items():
        vals = [sgn * row[pj] for (pj, sgn) in lst
                if pj != j and np.isfinite(row[pj])]
        if len(vals) < 3:
            return None
        means[curr] = float(np.mean(vals))
    return means


def _g013_pass(Z, pos_map, sym, direction, sig_stamp):
    """G02 catalyst: StrengthAccel(3) > 0.50 AND BreadthDiff > 0.20."""
    ppos = pos_map.get(sig_stamp, -1)
    if ppos < 3:
        return False
    j = _SYM_IDX[sym]
    B, Q = sym[:3], sym[3:]
    bought, sold = (B, Q) if direction == "BUY" else (Q, B)
    row = Z[:, ppos]

    def cstats(curr):
        vals = []
        for (pj, sgn) in _INCIDENT[curr]:
            if pj == j:
                continue
            v = sgn * row[pj]
            if np.isfinite(v):
                vals.append(v)
        return vals

    vb, vs = cstats(bought), cstats(sold)
    if len(vb) < 3 or len(vs) < 3:
        return False
    strength = float(np.mean(vb)) - float(np.mean(vs))
    breadth_diff = (float(np.mean([1.0 if v > 0 else 0.0 for v in vb]))
                    - float(np.mean([1.0 if v > 0 else 0.0 for v in vs])))
    prev = _peer_means(Z, j, ppos - 3)
    if prev is None:
        return False
    strength_accel = strength - (prev[bought] - prev[sold])
    return bool(strength_accel > 0.50 and breadth_diff > 0.20)


# ------------------------------------------------------------- evaluation --
def evaluate_cycle53_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate C53-07 at one check time (h:30 UTC).

    Candidate generation identical to C30-31 (24 equations, signal
    candle (h-1):00, entry = open of the h:00 candle, TP/SL clipped),
    plus the G013 rerank flag in column 'rerank_pass': True when the
    G02 peer-strength-acceleration catalyst passes for the candidate
    AND gate C03 passes (directional H4 EMA20 slope >= -0.15).
    select_* considers passing candidates first (incumbent score
    order inside each group); the pool is never deleted.
    """
    check = _as_utc(check_time_utc)
    hour = int(check.hour)
    if hour not in CYCLE53_CHECK_HOURS:
        return pd.DataFrame()
    sig_stamp = (check - pd.Timedelta(hours=1, minutes=30)).tz_localize(None)
    ent_stamp = (check - pd.Timedelta(minutes=30)).tz_localize(None)
    frames_norm = {}
    for s, f in (frames or {}).items():
        if f is None or len(f) == 0:
            continue
        frames_norm[str(s).upper()] = _norm_frame(f)
    _, pos_map, Z = _panel_for(frames_norm)
    rows = []
    for eq in C53_EQUATIONS:
        if eq["hour"] != hour:
            continue
        sym = eq["symbol"]
        ff = frames_norm.get(sym)
        if ff is None:
            continue
        if sig_stamp not in ff.index or ent_stamp not in ff.index:
            continue
        feat, h4s = _symbol_feat(sym, ff)
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
        d = 1 if direction == "BUY" else -1
        rpass = False
        if Z is not None and d * float(h4s.iloc[pos]) >= -0.15:
            rpass = _g013_pass(Z, pos_map, sym, direction, sig_stamp)
        rows.append({
            "check": check, "symbol": sym, "equation": eq["id"],
            "direction": direction, "score": eq["score"],
            "atr_pips": atr_pips,
            "entry_px": float(ff.loc[ent_stamp, "Open"]),
            "tp_pips": tp, "sl_pips": sl,
            "signal_candle": sig_stamp, "entry_candle": ent_stamp,
            "rerank_pass": bool(rpass),
        })
    return pd.DataFrame(rows)


def select_cycle53_entries(signals: pd.DataFrame, open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: G013-passing candidates first, then
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


def is_cycle53_check_time(ts) -> bool:
    """True if ts (UTC) is at one of the C53 check hours (:30)."""
    t = _as_utc(ts)
    return int(t.hour) in CYCLE53_CHECK_HOURS and int(t.minute) == 30
