"""Cycle 18 winner module: C18-A3 (quota-rebuild, mean-reversion).

The Cycle 18 constrained champion: 26 equations spanning 4 check hours
(10:30, 11:30, 13:30, 18:30 UTC) and all 20 symbols, both directions.
Mined on discovery only (train/val screen, discovery TP/SL calibration);
unseen touched ONLY for the 10-check evaluation (never for selection).

Unseen (2025-10-05 -> 2026-10-05): +2,198.8 pips / 601 trades /
RoMAD 5.71 / Sharpe 4.61 / DD -385.3 / EV +3.66 / win 68.6%%.
10-check PASS (10/10), overfit PASS, used_unseen_for_selection=False.
Unseen net at 3-pip costs: +996.8. Bootstrap P(net>0) = 100%%.

Selection rule for Cycle 18 (user-override): best RoMAD among processes
satisfying ALL FOUR hard requirements (>=4 check hours, 20 symbols,
10-check PASS, overfit PASS). The unconstrained optimum FT-C01
(core/cycle12_best.py) is KEPT as a selectable baseline mode and is
NOT deleted; see core/signal_mode.py for the router.

Source of truth: ~/workspace/fx/work_c18/results/comparison_table.csv
Trade logs: ~/workspace/fx/work_c18/families/famA/out/C18-A3_*_log.csv

Equations use the same two features as FT-C01 (mom24, atr_ratio) with
the same definitions (see add_cycle12_features, imported below).
Fidelity: SL-first fills, 48h cap, 1-pip spread baseline,
TP = tp_mult x ATR14 clipped [10,500], SL = sl_mult x ATR14 clipped [5,100].
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE18_VERSION = "cycle18-a3-v1"
CYCLE18_CHECK_HOURS = (10, 11, 13, 18)  # checks at h:30 UTC
CYCLE18_SYMBOLS_N = 20
MAX_HOLD_HOURS = 48
BASE_SPREAD_PIPS = 1.0
TP_CLIP = (10.0, 500.0)
SL_CLIP = (5.0, 100.0)
DEFAULT_K = 2  # top-2 per check by score, max 1 open trade per symbol

# ---------------------------------------------------------------- equations --
C18_EQUATIONS = (
    {"id": "A_AUDNZD_h18_SELL", "symbol": "AUDNZD", "hour": 18, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 2.5, "score": 41.0243},
    {"id": "A_AUDCHF_h18_SELL", "symbol": "AUDCHF", "hour": 18, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.75, "sl_mult": 1.5, "score": 25.3083},
    {"id": "A_AUDCAD_h18_SELL", "symbol": "AUDCAD", "hour": 18, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.5, "sl_mult": 1.0, "score": 22.6368},
    {"id": "A_NZDCAD_h18_SELL", "symbol": "NZDCAD", "hour": 18, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.5, "sl_mult": 2.0, "score": 21.4881},
    {"id": "A_EURGBP_h18_SELL", "symbol": "EURGBP", "hour": 18, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 0.75, "score": 11.5984},
    {"id": "A_USDCHF_h18_SELL", "symbol": "USDCHF", "hour": 18, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.75, "sl_mult": 2.5, "score": 9.8456},
    {"id": "A_EURAUD_h18_SELL", "symbol": "EURAUD", "hour": 18, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 0.75, "score": 9.8325},
    {"id": "A_AUDJPY_h18_SELL", "symbol": "AUDJPY", "hour": 18, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 2.5, "score": 9.5005},
    {"id": "A_EURCAD_h18_BUY", "symbol": "EURCAD", "hour": 18, "direction": "BUY",
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 2.0, "sl_mult": 2.5, "score": 7.5751},
    {"id": "A_GBPUSD_h18_BUY", "symbol": "GBPUSD", "hour": 18, "direction": "BUY",
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 2.0, "sl_mult": 0.5, "score": 5.6895},
    {"id": "A_EURNZD_h18_SELL", "symbol": "EURNZD", "hour": 18, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 2.0}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.0, "sl_mult": 2.5, "score": 5.1470},
    {"id": "A_NZDUSD_h18_SELL", "symbol": "NZDUSD", "hour": 18, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 2.0, "sl_mult": 2.5, "score": 5.0988},
    {"id": "A_EURUSD_h18_BUY", "symbol": "EURUSD", "hour": 18, "direction": "BUY",
     "conditions": [{"col": "mom24", "op": "<", "val": -1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 1.5, "score": 3.5356},
    {"id": "A_GBPJPY_h18_SELL", "symbol": "GBPJPY", "hour": 18, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 2.0, "sl_mult": 2.0, "score": 3.3310},
    {"id": "A_USDCAD_h18_SELL", "symbol": "USDCAD", "hour": 18, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 1.0, "score": 2.8749},
    {"id": "A_AUDCAD_h11_SELL", "symbol": "AUDCAD", "hour": 11, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 2.0, "sl_mult": 2.5, "score": 12.4879},
    {"id": "A_NZDCAD_h11_SELL", "symbol": "NZDCAD", "hour": 11, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 2.0, "sl_mult": 2.5, "score": 8.3617},
    {"id": "A_EURNZD_h13_BUY", "symbol": "EURNZD", "hour": 13, "direction": "BUY",
     "conditions": [{"col": "mom24", "op": "<", "val": -2.0}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.0, "sl_mult": 1.5, "score": 9.7887},
    {"id": "A_EURNZD_h13_SELL", "symbol": "EURNZD", "hour": 13, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 2.0}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.5, "sl_mult": 2.5, "score": 8.6617},
    {"id": "A_EURJPY_h13_BUY", "symbol": "EURJPY", "hour": 13, "direction": "BUY",
     "conditions": [{"col": "mom24", "op": "<", "val": -1.5}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 2.0, "sl_mult": 1.5, "score": 5.3297},
    {"id": "A_AUDUSD_h13_BUY", "symbol": "AUDUSD", "hour": 13, "direction": "BUY",
     "conditions": [{"col": "mom24", "op": "<", "val": -2.0}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.75, "sl_mult": 1.5, "score": 4.3710},
    {"id": "A_CHFJPY_h13_SELL", "symbol": "CHFJPY", "hour": 13, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 2.0, "sl_mult": 2.5, "score": 3.5922},
    {"id": "A_USDJPY_h13_BUY", "symbol": "USDJPY", "hour": 13, "direction": "BUY",
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 2.0, "sl_mult": 2.5, "score": 2.7330},
    {"id": "A_NZDCAD_h10_SELL", "symbol": "NZDCAD", "hour": 10, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 2.0, "sl_mult": 2.0, "score": 12.7918},
    {"id": "A_CHFJPY_h10_SELL", "symbol": "CHFJPY", "hour": 10, "direction": "SELL",
     "conditions": [{"col": "mom24", "op": ">", "val": 1.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 2.5, "score": 5.6132},
    {"id": "A_EURCHF_h10_BUY", "symbol": "EURCHF", "hour": 10, "direction": "BUY",
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 1.5, "score": 3.7632},
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


def evaluate_cycle18_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate C18-A3 equations at one check time (h:30 UTC).

    frames: {symbol: H1 OHLC DataFrame indexed by candle-stamp}.
    Only equations whose hour matches the check hour are evaluated.
    Signal features come from the (h-1):00 UTC candle (last completed
    as of h:30 UTC); entry price = open of the h:00 UTC candle.
    Returns one row per firing equation with TP/SL already clipped.
    """
    check = _as_utc(check_time_utc)
    hour = int(check.hour)
    if hour not in CYCLE18_CHECK_HOURS:
        return pd.DataFrame()
    sig_stamp = (check - pd.Timedelta(hours=1, minutes=30)).tz_localize(None)
    ent_stamp = (check - pd.Timedelta(minutes=30)).tz_localize(None)
    rows = []
    for eq in C18_EQUATIONS:
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


def select_cycle18_entries(signals: pd.DataFrame, open_symbols=(),
                           k=DEFAULT_K) -> pd.DataFrame:
    """Top-k by score at this check, max 1 open trade per symbol.
    k=2 reproduces the researched C18-A3 system (unseen RoMAD 5.71)."""
    if signals is None or len(signals) == 0:
        return signals.iloc[0:0] if signals is not None else pd.DataFrame()
    held = {str(s).upper() for s in (open_symbols or ())}
    out = []
    for _, row in signals.sort_values("score", ascending=False).iterrows():
        if k is not None and len(out) >= k:
            break
        if str(row["symbol"]).upper() in held:
            continue
        out.append(row)
        held.add(str(row["symbol"]).upper())
    return pd.DataFrame(out)


def is_cycle18_check_time(ts) -> bool:
    """True if ts (UTC) is at one of the C18 check hours (:30)."""
    t = _as_utc(ts)
    return int(t.hour) in CYCLE18_CHECK_HOURS and int(t.minute) == 30

