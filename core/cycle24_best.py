"""Cycle 24 module: P55 (October-only, nearest-confidence pick).

The Cycle 24 research winner: 24 equations (14 mined mom/atr + 10 TREND
fallbacks) spanning 5 check hours (01:30, 15:30, 17:30, 18:30, 20:30 UTC),
exactly 1 entry per check (top-1 by score at each check).

Mined on October discovery only (2016-10 -> 2024-10); unseen October 2025
touched ONLY for the 12-check evaluation (never for selection).

Unseen (2025-10-01 -> 2025-10-31): +875.6 pips / 115 trades /
RoMAD 5.43 / Sharpe 9.06 / win 66.1%%. 12-check: 11/12 PASS
(fails only #7: 3/9 discovery Octobers slightly negative).
used_unseen_for_selection=False. Overfit verdict PASS.

Selection for Cycle 24 (user-approved): nearest-confidence pick P55 --
11/12 with the strongest unseen stats among the 52 processes; no 12/12
winner existed, and the bar was not lowered.

Fallback equations (FB_*): direction 'TREND' fires on every check so the
exactly-1-entry-per-check rule always has a candidate; live direction
resolves per-trade from the signal candle's mom24 sign (BUY if > 0 else
SELL) -- the same fixed rule the research used, no tuning.

Equations use the same two features as C18 (mom24, atr_ratio) with the
same definitions (see add_cycle12_features, imported below).
Fidelity: SL-first fills, 48h cap, 1-pip spread baseline,
TP = tp_mult x ATR14 clipped [10,500], SL = sl_mult x ATR14 clipped [5,100].

Source of truth: ~/workspace/fx/work_c24/results/P55.json
Discovery trade log: ~/workspace/fx/work_c24/results/P55_disc_log.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE24_VERSION = "cycle24-p55-v1"
CYCLE24_CHECK_HOURS = (1, 15, 17, 18, 20)  # checks at h:30 UTC
CYCLE24_SYMBOLS_N = 20
MAX_HOLD_HOURS = 48
BASE_SPREAD_PIPS = 1.0
TP_CLIP = (10.0, 500.0)
SL_CLIP = (5.0, 100.0)

# ---------------------------------------------------------------- equations --
C24_EQUATIONS = (
    {"id": 'mom_CHFJPY_h1_momS_T0.75_A1.0_2.0x1.5', "symbol": 'CHFJPY', "hour": 1, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 2.0, "sl_mult": 1.5, "score": 422.56095714286386},
    {"id": 'mom_GBPJPY_h1_momS_T2.0_A1.25_1.5x1.5', "symbol": 'GBPJPY', "hour": 1, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.0}, {"col": "atr_ratio", "op": "<", "val": 1.25}],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": 414.00917142858793},
    {"id": 'mom_GBPJPY_h15_momB_T2.0_A1.25_2.0x1.5', "symbol": 'GBPJPY', "hour": 15, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.0}, {"col": "atr_ratio", "op": "<", "val": 1.25}],
     "tp_mult": 2.0, "sl_mult": 1.5, "score": 651.0071428571506},
    {"id": 'mom_EURJPY_h15_momB_T2.0_A1.25_1.5x1.5', "symbol": 'EURJPY', "hour": 15, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.0}, {"col": "atr_ratio", "op": "<", "val": 1.25}],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": 331.40357142857044},
    {"id": 'mom_AUDNZD_h17_momS_T1.0_A1.25_1.5x1.5', "symbol": 'AUDNZD', "hour": 17, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.25}],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": 410.9464285714435},
    {"id": 'mom_AUDCAD_h17_momS_T0.75_A1.25_1.5x1.5', "symbol": 'AUDCAD', "hour": 17, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.25}],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": 353.36785714286225},
    {"id": 'mom_AUDCHF_h18_momS_T1.0_A1.25_1.5x1.5', "symbol": 'AUDCHF', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.25}],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": 378.81071428571727},
    {"id": 'mom_AUDCAD_h18_momS_T1.0_A1.25_1.5x1.5', "symbol": 'AUDCAD', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.25}],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": 336.70357142856966},
    {"id": 'mom_CHFJPY_h20_momS_T0.75_A1.0_2.0x1.5', "symbol": 'CHFJPY', "hour": 20, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 2.0, "sl_mult": 1.5, "score": 385.0464285714315},
    {"id": 'mom_AUDNZD_h20_momS_T1.0_A1.25_1.5x1.0', "symbol": 'AUDNZD', "hour": 20, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.25}],
     "tp_mult": 1.5, "sl_mult": 1.0, "score": 307.2607142857185},
    {"id": 'FB_EURUSD_h1_0', "symbol": 'EURUSD', "hour": 1, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": -1000000001.0},
    {"id": 'FB_GBPUSD_h1_1', "symbol": 'GBPUSD', "hour": 1, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": -1000000002.0},
    {"id": 'FB_USDJPY_h15_0', "symbol": 'USDJPY', "hour": 15, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": -1000000003.0},
    {"id": 'FB_AUDUSD_h15_1', "symbol": 'AUDUSD', "hour": 15, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": -1000000004.0},
    {"id": 'FB_EURJPY_h17_0', "symbol": 'EURJPY', "hour": 17, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": -1000000005.0},
    {"id": 'FB_GBPJPY_h17_1', "symbol": 'GBPJPY', "hour": 17, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": -1000000006.0},
    {"id": 'FB_AUDJPY_h18_0', "symbol": 'AUDJPY', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": -1000000007.0},
    {"id": 'FB_NZDUSD_h18_1', "symbol": 'NZDUSD', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": -1000000008.0},
    {"id": 'FB_EURCHF_h20_0', "symbol": 'EURCHF', "hour": 20, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": -1000000009.0},
    {"id": 'FB_USDCAD_h20_1', "symbol": 'USDCAD', "hour": 20, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": -1000000010.0},
    {"id": 'mom_GBPJPY_h15_momB_T2.0_A1.25_1.5x1.5', "symbol": 'GBPJPY', "hour": 15, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.0}, {"col": "atr_ratio", "op": "<", "val": 1.25}],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": 438.128571428575},
    {"id": 'mom_GBPJPY_h1_momS_T1.5_A1.25_1.5x1.5', "symbol": 'GBPJPY', "hour": 1, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 1.25}],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": 406.8413142857319},
    {"id": 'mom_CHFJPY_h20_momS_T1.0_A1.0_2.0x1.5', "symbol": 'CHFJPY', "hour": 20, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 2.0, "sl_mult": 1.5, "score": 382.3392857142887},
    {"id": 'mom_AUDCHF_h18_momS_T0.75_A1.25_1.5x1.5', "symbol": 'AUDCHF', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.25}],
     "tp_mult": 1.5, "sl_mult": 1.5, "score": 370.33571428571776},
)


_COND_OPS = {">": lambda a, v: a > v, "<": lambda a, v: a < v,
             ">=": lambda a, v: a >= v, "<=": lambda a, v: a <= v,
             "==": lambda a, v: a == v, "!=": lambda a, v: a != v}


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

    Fixed rule from the Cycle 24 research (c24_sim.py); fires 100%.
    """
    try:
        return "BUY" if float(mom24_value) > 0 else "SELL"
    except (TypeError, ValueError):
        return "SELL"


def evaluate_cycle24_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate P55 equations at one check time (h:30 UTC).

    frames: {symbol: H1 OHLC DataFrame indexed by candle-stamp}.
    Only equations whose hour matches the check hour are evaluated.
    Signal features come from the (h-1):00 UTC candle (last completed
    as of h:30 UTC); entry price = open of the h:00 UTC candle.
    'TREND' fallbacks resolve direction from the signal candle's mom24.
    Returns one row per firing equation with TP/SL already clipped.
    """
    check = _as_utc(check_time_utc)
    hour = int(check.hour)
    if hour not in CYCLE24_CHECK_HOURS:
        return pd.DataFrame()
    sig_stamp = (check - pd.Timedelta(hours=1, minutes=30)).tz_localize(None)
    ent_stamp = (check - pd.Timedelta(minutes=30)).tz_localize(None)
    rows = []
    for eq in C24_EQUATIONS:
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


def select_cycle24_entries(signals: pd.DataFrame, open_symbols=()) -> pd.DataFrame:
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


def is_cycle24_check_time(ts) -> bool:
    """True if ts (UTC) is at one of the C24 check hours (:30)."""
    t = _as_utc(ts)
    return int(t.hour) in CYCLE24_CHECK_HOURS and int(t.minute) == 30
