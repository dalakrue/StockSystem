"""Cycle 35 module: C35-31 (August-only research winner).

24 equations (15 mined mom/atr + 9 TREND fallbacks) spanning 3 check
hours (1/15/18 UTC = 07:30/21:30/00:30 MMT), exactly 1
entry per check (top-1 by score at each check). Each equation is
symbol-specific with its own entry condition and its own TP/SL.

Mined on August discovery only; unseen August 2025
touched ONLY for the 12-check evaluation (never for selection).

Unseen: 63 trades / +304.6 pips / RoMAD 4.58 /
win 88.89% / max DD -66.5 / 3-pip +178.6 /
bootstrap P(net>0) 99.2%. 12-check: 10/12 PASS -- failed: 7_each_disc_aug_gt0, 8_no_red_weeks.
used_unseen_for_selection=False.

Fallback equations (FB_*): direction 'TREND' fires on every check so the
exactly-1-entry-per-check rule always has a candidate; live direction
resolves per-trade from the signal candle's mom24 sign (BUY if > 0 else
SELL) -- the same fixed rule the research used, no further tuning.

Every mined equation conditions on August price momentum (mom24) and
volatility (atr_ratio), same definitions as C12/C24/C26/C27/C28.

Source of truth: ~/workspace/fx/work_c35/results/WINNER.json
Discovery trade log: ~/workspace/fx/work_c35/results/C35-31_disc_log.csv
Unseen trade log: ~/workspace/fx/work_c35/results/C35-31_unseen_log.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE35_VERSION = "cycle35-c3531-v1"
CYCLE35_CHECK_HOURS = (1, 15, 18)  # checks at h:30 UTC
CYCLE35_SYMBOLS_N = 10
MAX_HOLD_HOURS = 48
BASE_SPREAD_PIPS = 1.0
TP_CLIP = (10.0, 500.0)
SL_CLIP = (5.0, 100.0)

# ---------------------------------------------------------------- equations --
C35_EQUATIONS = (
    {"id": 'mom_GBPUSD_h1_momB_T3.0_A1.0_1.0x8', "symbol": 'GBPUSD', "hour": 1, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -3.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1000.2925214285714},
    {"id": 'mom_AUDNZD_h1_momB_T1.5_A1.0_0.75x8', "symbol": 'AUDNZD', "hour": 1, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 969.0007053571428},
    {"id": 'mom_AUDCHF_h1_momS_T3.0_A1.0_1.0x3', "symbol": 'AUDCHF', "hour": 1, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 3.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 3.0, "score": 950.1559857142857},
    {"id": 'mom_NZDCAD_h1_momS_T2.0_A1.0_1.0x8', "symbol": 'NZDCAD', "hour": 1, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 920.1400642857143},
    {"id": 'mom_EURUSD_h1_momS_T2.0_A1.0_1.25x8', "symbol": 'EURUSD', "hour": 1, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 904.8285476190476},
    {"id": 'mom_GBPUSD_h15_momB_T0.75_A1.0_1.25x8', "symbol": 'GBPUSD', "hour": 15, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1000.4680089285714},
    {"id": 'mom_USDCAD_h15_momB_T1.5_A1.0_0.75x8', "symbol": 'USDCAD', "hour": 15, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 1000.3434607142857},
    {"id": 'mom_NZDCAD_h15_momB_T0.75_A1.0_0.75x8', "symbol": 'NZDCAD', "hour": 15, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 971.7145},
    {"id": 'mom_AUDNZD_h15_momB_T0.75_A1.0_0.75x8', "symbol": 'AUDNZD', "hour": 15, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 889.0353853174602},
    {"id": 'mom_AUDCHF_h15_momS_T1.0_A1.0_1.25x5', "symbol": 'AUDCHF', "hour": 15, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 866.7230470238096},
    {"id": 'mom_NZDCAD_h18_momB_T0.75_A1.0_0.75x5', "symbol": 'NZDCAD', "hour": 18, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 969.9192411255411},
    {"id": 'mom_AUDNZD_h18_momB_T2.0_A1.0_1.25x8', "symbol": 'AUDNZD', "hour": 18, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 916.8156845238095},
    {"id": 'mom_NZDUSD_h18_momS_T1.0_A1.0_0.75x5', "symbol": 'NZDUSD', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 913.1509371894409},
    {"id": 'mom_AUDCHF_h18_momS_T0.75_A0.9_1.0x5', "symbol": 'AUDCHF', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.0, "sl_mult": 5.0, "score": 904.8191190476191},
    {"id": 'FB_EURUSD_h1_0', "symbol": 'EURUSD', "hour": 1, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000001.0},
    {"id": 'FB_GBPUSD_h1_1', "symbol": 'GBPUSD', "hour": 1, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 10.0, "score": -1000000002.0},
    {"id": 'FB_NZDUSD_h1_2', "symbol": 'NZDUSD', "hour": 1, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000003.0},
    {"id": 'FB_EURCHF_h15_0', "symbol": 'EURCHF', "hour": 15, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000004.0},
    {"id": 'FB_USDCAD_h15_1', "symbol": 'USDCAD', "hour": 15, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000005.0},
    {"id": 'FB_EURGBP_h15_2', "symbol": 'EURGBP', "hour": 15, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 10.0, "score": -1000000006.0},
    {"id": 'FB_USDCHF_h18_0', "symbol": 'USDCHF', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 8.0, "score": -1000000007.0},
    {"id": 'FB_EURUSD_h18_1', "symbol": 'EURUSD', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000008.0},
    {"id": 'FB_GBPUSD_h18_2', "symbol": 'GBPUSD', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 8.0, "score": -1000000009.0},
    {"id": 'mom_GBPUSD_h15_momB_T0.75_A1.0_1.25x5', "symbol": 'GBPUSD', "hour": 15, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 1000.4680089285714},
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


def _trend_direction(mom24_value) -> str:
    """Fallback direction rule: BUY if signal-candle mom24 > 0 else SELL.

    Fixed rule from the Cycle 35 research (c35_sim.py); fires 100%.
    """
    try:
        return "BUY" if float(mom24_value) > 0 else "SELL"
    except (TypeError, ValueError):
        return "SELL"


def evaluate_cycle35_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate CC35-31 equations at one check time (h:30 UTC).

    frames: {symbol: H1 OHLC DataFrame indexed by candle-stamp}.
    Only equations whose hour matches the check hour are evaluated.
    Signal features come from the (h-1):00 UTC candle (last completed
    as of h:30 UTC); entry price = open of the h:00 UTC candle.
    'TREND' fallbacks resolve direction from the signal candle's mom24.
    Returns one row per firing equation with TP/SL already clipped.
    """
    check = _as_utc(check_time_utc)
    hour = int(check.hour)
    if hour not in CYCLE35_CHECK_HOURS:
        return pd.DataFrame()
    sig_stamp = (check - pd.Timedelta(hours=1, minutes=30)).tz_localize(None)
    ent_stamp = (check - pd.Timedelta(minutes=30)).tz_localize(None)
    rows = []
    for eq in C35_EQUATIONS:
        if eq["hour"] != hour:
            continue
        sym = eq["symbol"]
        f = frames.get(sym)
        if f is None or len(f) == 0:
            continue
        ff = f.copy()
        ff.index = pd.to_datetime(ff.index, utc=True).tz_localize(None)
        ff = ff.sort_index()
        if sig_stamp not in ff.index or ent_stamp not in ff.index:
            continue
        feat = add_cycle12_features(ff.reset_index(drop=True))
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
        rows.append({
            "check": check, "symbol": sym, "equation": eq["id"],
            "direction": direction, "score": eq["score"],
            "atr_pips": atr_pips,
            "entry_px": float(ff.loc[ent_stamp, "Open"]),
            "tp_pips": tp, "sl_pips": sl,
            "signal_candle": sig_stamp, "entry_candle": ent_stamp,
        })
    return pd.DataFrame(rows)


def select_cycle35_entries(signals: pd.DataFrame, open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: top-1 by score, max 1 open trade per
    symbol. Stable sort reproduces the research assembly order on ties."""
    if signals is None or len(signals) == 0:
        return signals.iloc[0:0] if signals is not None else pd.DataFrame()
    held = {str(s).upper() for s in (open_symbols or ())}
    out = []
    for _, row in signals.sort_values("score", ascending=False, kind="mergesort").iterrows():
        if len(out) >= 1:
            break
        if str(row["symbol"]).upper() in held:
            continue
        out.append(row)
        held.add(str(row["symbol"]).upper())
    return pd.DataFrame(out)


def is_cycle35_check_time(ts) -> bool:
    """True if ts (UTC) is at one of the C35 check hours (:30)."""
    t = _as_utc(ts)
    return int(t.hour) in CYCLE35_CHECK_HOURS and int(t.minute) == 30
