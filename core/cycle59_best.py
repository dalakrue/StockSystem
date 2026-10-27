"""Cycle 59 module: C59-18 (September-only system, follow-up round).

24 equations spanning 3 check hours (01:30, 10:30, 11:30 UTC =
07:30, 16:30, 17:30 MMT), exactly 1 entry per check -- the incumbent
C36-40 system VERBATIM (15 mined mom/atr legs + 9 TREND fallbacks,
exits frozen), plus ONE added selection layer: an Alligator-ordering
rerank overlay.

C59-18 REPLACES C36-40 as September's system. It won the follow-up
round (Cycle 59, 20 end-to-end processes, fresh mining only, judged
at the 2.5-pip primary cost with the round's relaxed win gate >= 80%
plus leftover improvement): weak ratings 1 (vs 8), unseen net@2.5
+278.1 (vs +100.2), win 93.94%, leftover 56.0% (vs 20.2%), checks
11/12, discovery net@2.5 +1,981.1, sizing PASS (best N 101),
P(profit) 100%. The overlay changed 79 discovery picks and 11 unseen
picks. LCT (Left95) at the middle level FAILS (paired P 41.85%,
5th-percentile 22.78%) but is report-only under the user's rule --
the unseen leftover improvement is +35.8 pts, not a close call.
Cycle 36 (C36-40) remains selectable.

THE ALLIGATOR RERANK OVERLAY (the only change vs C36-40)
At each check, a candidate whose Alligator ordering agrees with its
trade direction gets +400 added to its score before the top-1 pick:
  alg_order (signal bar): median price MP = (High+Low)/2;
  jaw = SMMA(MP,13) shifted 8 bars, teeth = SMMA(MP,8) shifted 5
  bars, lips = SMMA(MP,5) shifted 3 bars (SMMA = Wilder smoothing,
  alpha = 1/n, ewm adjust=False; the value at bar t is the SMMA from
  bars up to t-shift, so everything is causal);
  alg_order = +1 if lips > teeth > jaw, -1 if lips < teeth < jaw,
  else 0.
Agreement: BUY candidate with alg_order = +1, or SELL candidate with
alg_order = -1. For TREND fallback legs the candidate direction is
the resolved direction (BUY if the signal bar's mom24 > 0 else
SELL), exactly the incumbent fallback rule. The candidate pool,
exits, occupancy and 1-entry-per-check are otherwise identical to
C36-40; ties keep the incumbent order.

Fallback equations (FB_*): direction 'TREND' fires on every check so
the exactly-1-entry-per-check rule always has a candidate; live
direction resolves per-trade from the signal candle's mom24 sign
(BUY if > 0 else SELL) -- the same fixed rule the research used.

Source of truth: ~/workspace/fx/work_c59/results/WINNER.json
Full spec: ~/workspace/fx/work_c59/results/WINNER_SPEC.json
Discovery trade log: ~/workspace/fx/work_c59/results/WINNER_disc_log.csv
Unseen trade log: ~/workspace/fx/work_c59/results/WINNER_unseen_log.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE59_VERSION = "cycle59-c5918-v1"
CYCLE59_CHECK_HOURS = (1, 10, 11)  # checks at h:30 UTC
CYCLE59_SYMBOLS_N = 15
MAX_HOLD_HOURS = 48
BASE_SPREAD_PIPS = 1.0
TP_CLIP = (10.0, 500.0)
SL_CLIP = (5.0, 100.0)
RERANK_BONUS = 400.0

# ---------------------------------------------------------------- equations --
C59_EQUATIONS = (
    {"id": 'mom_AUDNZD_h1_momB_T0.75_A1.0_1.0x8', "symbol": 'AUDNZD', "hour": 1, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 976.5705976190476},
    {"id": 'mom_EURUSD_h1_momS_T0.75_A1.0_0.75x5', "symbol": 'EURUSD', "hour": 1, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 943.0208214285715},
    {"id": 'mom_EURNZD_h1_momS_T0.75_A1.0_0.5x5', "symbol": 'EURNZD', "hour": 1, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 919.0060974903475},
    {"id": 'mom_USDJPY_h1_momS_T1.0_A1.0_0.5x5', "symbol": 'USDJPY', "hour": 1, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 916.9162416666666},
    {"id": 'mom_USDCHF_h1_momS_T0.75_A1.0_1.0x8', "symbol": 'USDCHF', "hour": 1, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 900.1920642857143},
    {"id": 'mom_GBPJPY_h10_momS_T1.5_A1.0_0.5x8', "symbol": 'GBPJPY', "hour": 10, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.349075},
    {"id": 'mom_NZDCAD_h10_momS_T0.75_A0.9_1.0x8', "symbol": 'NZDCAD', "hour": 10, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 970.8924352941177},
    {"id": 'mom_USDCHF_h10_momB_T0.75_A1.0_1.0x8', "symbol": 'USDCHF', "hour": 10, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 967.0983880952381},
    {"id": 'mom_GBPUSD_h10_momS_T0.75_A1.0_0.75x8', "symbol": 'GBPUSD', "hour": 10, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 964.0082761363636},
    {"id": 'mom_EURNZD_h10_momS_T0.75_A1.0_0.5x3', "symbol": 'EURNZD', "hour": 10, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 3.0, "score": 951.4719836236933},
    {"id": 'mom_GBPUSD_h11_momS_T2.0_A1.0_0.75x8', "symbol": 'GBPUSD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.3498339285715},
    {"id": 'mom_USDCHF_h11_momB_T0.75_A0.9_1.25x8', "symbol": 'USDCHF', "hour": 11, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 977.1244181893687},
    {"id": 'mom_EURAUD_h11_momS_T0.75_A1.0_0.3x5', "symbol": 'EURAUD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 975.8687560975609},
    {"id": 'mom_AUDCAD_h11_momB_T1.5_A1.0_1.0x8', "symbol": 'AUDCAD', "hour": 11, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 971.6845214285714},
    {"id": 'mom_NZDCAD_h11_momS_T0.75_A0.9_1.0x8', "symbol": 'NZDCAD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 970.8844781512605},
    {"id": 'FB_EURUSD_h1_0', "symbol": 'EURUSD', "hour": 1, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 10.0, "score": -1000000001.0},
    {"id": 'FB_GBPUSD_h1_1', "symbol": 'GBPUSD', "hour": 1, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 8.0, "score": -1000000002.0},
    {"id": 'FB_USDJPY_h1_2', "symbol": 'USDJPY', "hour": 1, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": -1000000003.0},
    {"id": 'FB_AUDUSD_h10_0', "symbol": 'AUDUSD', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 10.0, "score": -1000000004.0},
    {"id": 'FB_EURJPY_h10_1', "symbol": 'EURJPY', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000005.0},
    {"id": 'FB_GBPJPY_h10_2', "symbol": 'GBPJPY', "hour": 10, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": -1000000006.0},
    {"id": 'FB_AUDJPY_h11_0', "symbol": 'AUDJPY', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 8.0, "score": -1000000007.0},
    {"id": 'FB_NZDUSD_h11_1', "symbol": 'NZDUSD', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000008.0},
    {"id": 'FB_EURCHF_h11_2', "symbol": 'EURCHF', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 10.0, "score": -1000000009.0},
)

_COND_OPS = {">": lambda a, v: a > v, "<": lambda a, v: a < v,
             ">=": lambda a, v: a >= v, "<=": lambda a, v: a <= v}

_FEAT_CACHE = {}


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


def _smma(x, n):
    """Wilder-style SMMA (alpha = 1/n), as in the Cycle 59 research."""
    return x.ewm(alpha=1.0 / n, min_periods=n, adjust=False).mean()


def _symbol_feat(sym, ff):
    """Base cycle12 features + alg_order (Alligator ordering state)
    for a normalised frame (cached)."""
    key = (sym, len(ff), ff.index[0], ff.index[-1])
    hit = _FEAT_CACHE.get(key)
    if hit is not None:
        return hit
    if len(_FEAT_CACHE) > 32:
        _FEAT_CACHE.clear()
    feat = add_cycle12_features(ff.reset_index(drop=True))
    feat.index = ff.index
    mp = (ff["High"] + ff["Low"]) / 2.0
    jaw = _smma(mp, 13).shift(8)
    teeth = _smma(mp, 8).shift(5)
    lips = _smma(mp, 5).shift(3)
    feat["alg_order"] = np.where((lips > teeth) & (teeth > jaw), 1.0,
                                 np.where((lips < teeth) & (teeth < jaw),
                                          -1.0, 0.0))
    _FEAT_CACHE[key] = feat
    return feat


def evaluate_cycle59_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate C59-18 at one check time (h:30 UTC).

    Same candidate generation as C36-40 (24 equations, signal candle
    (h-1):00, entry = open of the h:00 candle, TP/SL clipped), plus
    the Alligator rerank columns: 'alg_order' (the signal bar's
    ordering state) and 'eff_score' = score + 400 when the ordering
    agrees with the candidate's (resolved) direction. select_* then
    picks by eff_score (incumbent order on ties); the pool is never
    deleted. 'score' stays the incumbent equation score.
    """
    check = _as_utc(check_time_utc)
    hour = int(check.hour)
    if hour not in CYCLE59_CHECK_HOURS:
        return pd.DataFrame()
    sig_stamp = (check - pd.Timedelta(hours=1, minutes=30)).tz_localize(None)
    ent_stamp = (check - pd.Timedelta(minutes=30)).tz_localize(None)
    frames_norm = {}
    for s, f in (frames or {}).items():
        if f is None or len(f) == 0:
            continue
        frames_norm[str(s).upper()] = _norm_frame(f)
    rows = []
    for eq in C59_EQUATIONS:
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
        try:
            alg = float(row["alg_order"])
        except (TypeError, ValueError):
            alg = 0.0
        if not np.isfinite(alg):
            alg = 0.0
        agree = ((direction == "BUY" and alg == 1.0)
                 or (direction == "SELL" and alg == -1.0))
        rows.append({
            "check": check, "symbol": sym, "equation": eq["id"],
            "direction": direction, "score": eq["score"],
            "eff_score": eq["score"] + (RERANK_BONUS if agree else 0.0),
            "alg_order": alg,
            "atr_pips": atr_pips,
            "entry_px": float(ff.loc[ent_stamp, "Open"]),
            "tp_pips": tp, "sl_pips": sl,
            "signal_candle": sig_stamp, "entry_candle": ent_stamp,
        })
    return pd.DataFrame(rows)


def select_cycle59_entries(signals: pd.DataFrame, open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: top-1 by effective score (incumbent
    score + the +400 Alligator-agreement bonus), max 1 open trade per
    symbol. Stable sort keeps the incumbent order on ties."""
    if signals is None or len(signals) == 0:
        return signals.iloc[0:0] if signals is not None else pd.DataFrame()
    held = {str(s).upper() for s in (open_symbols or ())}
    df = signals.copy()
    if "eff_score" not in df.columns:
        df["eff_score"] = df["score"]
    out = []
    for _, row in df.sort_values("eff_score", ascending=False, kind="mergesort").iterrows():
        if len(out) >= 1:
            break
        if str(row["symbol"]).upper() in held:
            continue
        out.append(row)
        held.add(str(row["symbol"]).upper())
    return pd.DataFrame(out)


def is_cycle59_check_time(ts) -> bool:
    """True if ts (UTC) is at one of the C59 check hours (:30)."""
    t = _as_utc(ts)
    return int(t.hour) in CYCLE59_CHECK_HOURS and int(t.minute) == 30
