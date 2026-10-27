"""Cycle 65 module: C65-01 (June-only system, LCT-fix round).

30 equations spanning 3 check hours (01:30, 15:30, 18:30 UTC =
08:00, 22:00, 01:00 MMT), exactly 1 entry per check -- the incumbent
C42-18 system VERBATIM (15 mined mom/atr legs + 9 TREND fallbacks,
exits frozen) plus 6 fresh legs scored just below the mined legs so
they only preempt TREND fallbacks:
  * TRD_as1_EURCAD_h1_SELL / TRD_as1_EURNZD_h1_BUY -- Wilder Swing
    Index (ASI) smoothed-cross events (ev_asi_xdn / ev_asi_xup > 0.5);
  * REV_lr2_EURCAD_h15_SELL / REV_lr2_EURNZD_h18_SELL -- Laguerre RSI
    (gamma 0.8) in the upper zone (lrsi > 80);
  * TRD_as2_AUDCHF_h15_SELL / TRD_as2_EURJPY_h18_BUY -- normalised
    12-bar ASI momentum (asi_mom_n beyond -/+0.3).

C65-01 REPLACES C42-18 as June's system. The Cycle 65 verdict was
NO_IMPROVEMENT under the round's all-gates rule (it failed the unseen
leftover gate, 57.07% vs the incumbent's June-2025-lucky 82.67%, and
tied the weak gate 1 = 1); the user then promoted it by OVERRIDE on
2026-10-21 for its discovery record: it passes the LCT (Left95) at
the STRICT level against C42-18 (paired P 100.00%, 5th-percentile
41.83%; the incumbent fails even the middle level), discovery net
+3,163.8 vs +1,665.7, red discovery months 0 vs 1, checks 11/12,
sizing PASS, P(profit) 100%. Unseen June 2025 @2.5: net +346.3,
win 95.24%, leftover 57.07%, weak 1. Cycle 42 (C42-18) remains
selectable.

Exit caps (the research cap_h map): mined and fresh legs 48h;
TREND fallback legs 24h. TP/SL are per-equation ATR14 multiples,
clipped [10,500] / [5,100] pips.

Fresh feature definitions (verbatim from the Cycle 65 research,
work_c65/scripts/c65_engine.py add_features65; computed on the full
frame, all causal):
  lrsi      Laguerre RSI, gamma 0.8: L0..L3 are the Ehlers Laguerre
            filter stages of Close (zero-initialised recursions);
            CU/CD are the sums of the positive/negative parts of the
            stage diffs; lrsi = 100*CU/(CU+CD), 50 when CU+CD = 0.
  ASI       Wilder Swing Index SI (50 * ((C-Cp) + 0.5*(C-O) +
            0.25*(Cp-Op)) / R with the standard Wilder R rule),
            accumulated ASI = cumsum(SI); asi_s = EMA(span 10) of ASI;
            ev_asi_xup = 1 when ASI crosses above asi_s, ev_asi_xdn
            when it crosses below.
  asi_mom_n (ASI 12-bar change) / (12 * trailing-48-bar mean |SI|).

Fallback equations (FB_*): direction 'TREND' fires on every check so
the exactly-1-entry-per-check rule always has a candidate; live
direction resolves per-trade from the signal candle's mom24 sign
(BUY if > 0 else SELL) -- the same fixed rule the research used.

Source of truth: ~/workspace/fx/work_c65/results/C65-01.json
Discovery trade log: ~/workspace/fx/work_c65/results/logs/C65-01_disc_log.csv
Unseen trade log: ~/workspace/fx/work_c65/results/logs/C65-01_unseen_log.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE65_VERSION = "cycle65-c6501-v1"
CYCLE65_CHECK_HOURS = (1, 15, 18)  # checks at h:30 UTC
CYCLE65_SYMBOLS_N = 15
MAX_HOLD_HOURS = 48
BASE_SPREAD_PIPS = 1.0
TP_CLIP = (10.0, 500.0)
SL_CLIP = (5.0, 100.0)

# ---------------------------------------------------------------- equations --
C65_EQUATIONS = (
    {"id": 'mom_GBPUSD_h1_momS_T1.0_A1.0_1.25x8', "symbol": 'GBPUSD', "hour": 1, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1000.4964196428572, "cap_h": 48},
    {"id": 'mom_EURAUD_h1_momB_T1.5_A0.9_1.0x5', "symbol": 'EURAUD', "hour": 1, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -1.5},
     {"col": 'atr_ratio', "op": '<', "val": 0.9}],
     "tp_mult": 1.0, "sl_mult": 5.0, "score": 1000.4310571428572, "cap_h": 48},
    {"id": 'mom_USDCAD_h1_momB_T1.5_A1.0_1.25x5', "symbol": 'USDCAD', "hour": 1, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -1.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 1000.3812857142857, "cap_h": 48},
    {"id": 'mom_AUDCAD_h1_momS_T1.0_A1.0_1.25x8', "symbol": 'AUDCAD', "hour": 1, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 1000.3023035714285, "cap_h": 48},
    {"id": 'mom_EURCAD_h1_momB_T1.0_A1.0_0.75x3', "symbol": 'EURCAD', "hour": 1, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 3.0, "score": 1000.2830749999999, "cap_h": 48},
    {"id": 'mom_EURNZD_h15_momB_T0.75_A1.0_0.3x8', "symbol": 'EURNZD', "hour": 15, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 1000.2431485714285, "cap_h": 48},
    {"id": 'mom_EURCAD_h15_momB_T0.75_A1.0_0.5x8', "symbol": 'EURCAD', "hour": 15, "direction": 'BUY',
     "conditions": [
     {"col": 'mom24', "op": '<', "val": -0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 956.6437069875777, "cap_h": 48},
    {"id": 'mom_AUDCAD_h15_momS_T0.75_A1.0_1.25x5', "symbol": 'AUDCAD', "hour": 15, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 5.0, "score": 954.744525974026, "cap_h": 48},
    {"id": 'mom_AUDUSD_h15_momS_T0.75_A1.0_0.3x8', "symbol": 'AUDUSD', "hour": 15, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 954.7121545454546, "cap_h": 48},
    {"id": 'mom_AUDJPY_h15_momS_T2.0_A1.0_0.5x3', "symbol": 'AUDJPY', "hour": 15, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 2.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 3.0, "score": 920.154225, "cap_h": 48},
    {"id": 'mom_AUDNZD_h18_momS_T1.0_A1.0_1.0x5', "symbol": 'AUDNZD', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 5.0, "score": 1000.2648285714286, "cap_h": 48},
    {"id": 'mom_EURNZD_h18_momS_T0.75_A1.0_0.5x5', "symbol": 'EURNZD', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": 1000.2536821428571, "cap_h": 48},
    {"id": 'mom_AUDCHF_h18_momS_T1.0_A1.0_1.0x5', "symbol": 'AUDCHF', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.0},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 5.0, "score": 1000.23015, "cap_h": 48},
    {"id": 'mom_GBPJPY_h18_momS_T0.75_A1.0_0.3x5', "symbol": 'GBPJPY', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 0.75},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": 1000.1838814285715, "cap_h": 48},
    {"id": 'mom_NZDUSD_h18_momS_T1.5_A1.0_0.75x5', "symbol": 'NZDUSD', "hour": 18, "direction": 'SELL',
     "conditions": [
     {"col": 'mom24', "op": '>', "val": 1.5},
     {"col": 'atr_ratio', "op": '<', "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.1824803571428, "cap_h": 48},
    {"id": 'FB_GBPUSD_h1_1', "symbol": 'GBPUSD', "hour": 1, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000002.0, "cap_h": 24},
    {"id": 'FB_USDJPY_h1_2', "symbol": 'USDJPY', "hour": 1, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": -1000000003.0, "cap_h": 24},
    {"id": 'FB_AUDUSD_h15_0', "symbol": 'AUDUSD', "hour": 15, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000004.0, "cap_h": 24},
    {"id": 'FB_EURJPY_h15_1', "symbol": 'EURJPY', "hour": 15, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": -1000000005.0, "cap_h": 24},
    {"id": 'FB_GBPJPY_h15_2', "symbol": 'GBPJPY', "hour": 15, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 5.0, "score": -1000000006.0, "cap_h": 24},
    {"id": 'FB_AUDJPY_h18_0', "symbol": 'AUDJPY', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 10.0, "score": -1000000007.0, "cap_h": 24},
    {"id": 'FB_NZDUSD_h18_1', "symbol": 'NZDUSD', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 5.0, "score": -1000000008.0, "cap_h": 24},
    {"id": 'FB_EURCHF_h18_2', "symbol": 'EURCHF', "hour": 18, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000009.0, "cap_h": 24},
    {"id": 'FB_AUDUSD_h1_new', "symbol": 'AUDUSD', "hour": 1, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 8.0, "score": -1000000099.0, "cap_h": 24},
    {"id": 'TRD_as1_EURCAD_h1_SELL_0.3x8.0', "symbol": 'EURCAD', "hour": 1, "direction": 'SELL',
     "conditions": [{"col": 'ev_asi_xdn', "op": '>', "val": 0.5}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 919.154225, "cap_h": 48},
    {"id": 'TRD_as1_EURNZD_h1_BUY_0.3x8.0', "symbol": 'EURNZD', "hour": 1, "direction": 'BUY',
     "conditions": [{"col": 'ev_asi_xup', "op": '>', "val": 0.5}],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": 918.654225, "cap_h": 48},
    {"id": 'REV_lr2_EURCAD_h15_SELL_0.5x8.0', "symbol": 'EURCAD', "hour": 15, "direction": 'SELL',
     "conditions": [{"col": 'lrsi', "op": '>', "val": 80}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 918.154225, "cap_h": 48},
    {"id": 'TRD_as2_AUDCHF_h15_SELL_0.5x8.0', "symbol": 'AUDCHF', "hour": 15, "direction": 'SELL',
     "conditions": [{"col": 'asi_mom_n', "op": '<', "val": -0.3}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 917.654225, "cap_h": 48},
    {"id": 'REV_lr2_EURNZD_h18_SELL_0.5x8.0', "symbol": 'EURNZD', "hour": 18, "direction": 'SELL',
     "conditions": [{"col": 'lrsi', "op": '>', "val": 80}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 917.154225, "cap_h": 48},
    {"id": 'TRD_as2_EURJPY_h18_BUY_0.5x8.0', "symbol": 'EURJPY', "hour": 18, "direction": 'BUY',
     "conditions": [{"col": 'asi_mom_n', "op": '>', "val": 0.3}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 916.654225, "cap_h": 48},
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


def _symbol_feat(sym, ff):
    """Base cycle12 features + the Cycle 65 fresh columns (lrsi,
    asi_mom_n, ev_asi_xup, ev_asi_xdn) for a normalised frame
    (cached). Formulas verbatim from work_c65/scripts/c65_engine.py."""
    key = (sym, len(ff), ff.index[0], ff.index[-1])
    hit = _FEAT_CACHE.get(key)
    if hit is not None:
        return hit
    if len(_FEAT_CACHE) > 32:
        _FEAT_CACHE.clear()
    feat = add_cycle12_features(ff.reset_index(drop=True))
    feat.index = ff.index
    cl = ff["Close"].to_numpy(dtype=float)
    hi = ff["High"].to_numpy(dtype=float)
    lo = ff["Low"].to_numpy(dtype=float)
    op = ff["Open"].to_numpy(dtype=float)
    n = len(cl)
    # ---------------- Laguerre RSI (gamma 0.8) ----------------
    gam = 0.8
    L0 = np.zeros(n); L1 = np.zeros(n); L2 = np.zeros(n); L3 = np.zeros(n)
    for i in range(1, n):
        L0[i] = (1 - gam) * cl[i] + gam * L0[i - 1]
        L1[i] = -gam * L0[i] + L0[i - 1] + gam * L1[i - 1]
        L2[i] = -gam * L1[i] + L1[i - 1] + gam * L2[i - 1]
        L3[i] = -gam * L2[i] + L2[i - 1] + gam * L3[i - 1]
    d1 = L0 - L1; d2 = L1 - L2; d3 = L2 - L3
    cu = np.clip(d1, 0, None) + np.clip(d2, 0, None) + np.clip(d3, 0, None)
    cd = -np.clip(d1, None, 0) - np.clip(d2, None, 0) - np.clip(d3, None, 0)
    tot = cu + cd
    feat["lrsi"] = np.where(tot > 0, 100.0 * cu / np.where(tot > 0, tot, 1.0),
                            50.0)
    # ---------------- Wilder Swing Index -> ASI ----------------
    cp_ = np.roll(cl, 1); op_ = np.roll(op, 1)
    h_cp = np.abs(hi - cp_); l_cp = np.abs(lo - cp_)
    h_op = np.abs(hi - op_); h_l = hi - lo
    K = np.maximum(h_cp, l_cp)
    R = np.where(h_cp >= np.maximum(l_cp, h_l),
                 h_cp - 0.5 * np.abs(lo - op_) + 0.25 * np.abs(cp_ - op_),
                 np.where(l_cp >= h_l,
                          l_cp - 0.5 * h_op + 0.25 * np.abs(cp_ - op_),
                          h_l + 0.25 * np.abs(cp_ - op_)))
    si = 50.0 * ((cl - cp_) + 0.5 * (cl - op) + 0.25 * (cp_ - op_)) \
        / np.where(R > 0, R, np.nan)
    si[0] = 0.0
    asi = np.cumsum(np.nan_to_num(si))
    asi_s = pd.Series(asi).ewm(span=10, min_periods=10,
                               adjust=False).mean().to_numpy()
    asi_vel = asi - np.roll(asi, 12)
    asi_vel[:12] = 0.0
    si_scale = pd.Series(np.abs(si)).rolling(48, min_periods=12).mean().to_numpy()
    feat["asi_mom_n"] = asi_vel / np.where(si_scale > 0, 12.0 * si_scale,
                                           np.nan)
    amp = np.roll(asi, 1); asp = np.roll(asi_s, 1)
    ev_xup = ((asi > asi_s) & (amp <= asp)).astype(float)
    ev_xdn = ((asi < asi_s) & (amp >= asp)).astype(float)
    ev_xup[0] = 0.0; ev_xdn[0] = 0.0
    feat["ev_asi_xup"] = ev_xup
    feat["ev_asi_xdn"] = ev_xdn
    _FEAT_CACHE[key] = feat
    return feat


def evaluate_cycle65_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate C65-01 equations at one check time (h:30 UTC).

    frames: {symbol: H1 OHLC DataFrame indexed by candle-stamp}.
    Only equations whose hour matches the check hour are evaluated.
    Signal features come from the (h-1):00 UTC candle (last completed
    as of h:30 UTC); entry price = open of the h:00 UTC candle.
    TP/SL distances scale off ATR14, clipped to the standard
    [10,500] / [5,100] pip clips. 'TREND' fallbacks resolve
    direction from the signal candle's mom24. Each row carries the
    equation's research exit cap ('cap_h': 48h mined/fresh, 24h
    fallbacks).
    """
    check = _as_utc(check_time_utc)
    hour = int(check.hour)
    if hour not in CYCLE65_CHECK_HOURS:
        return pd.DataFrame()
    sig_stamp = (check - pd.Timedelta(hours=1, minutes=30)).tz_localize(None)
    ent_stamp = (check - pd.Timedelta(minutes=30)).tz_localize(None)
    frames_norm = {}
    for s, f in (frames or {}).items():
        if f is None or len(f) == 0:
            continue
        frames_norm[str(s).upper()] = _norm_frame(f)
    rows = []
    for eq in C65_EQUATIONS:
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
        rows.append({
            "check": check, "symbol": sym, "equation": eq["id"],
            "direction": direction, "score": eq["score"],
            "atr_pips": atr_pips, "cap_h": int(eq.get("cap_h", 48)),
            "entry_px": float(ff.loc[ent_stamp, "Open"]),
            "tp_pips": tp, "sl_pips": sl,
            "signal_candle": sig_stamp, "entry_candle": ent_stamp,
        })
    return pd.DataFrame(rows)


def select_cycle65_entries(signals: pd.DataFrame, open_symbols=()) -> pd.DataFrame:
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


def is_cycle65_check_time(ts) -> bool:
    """True if ts (UTC) is at one of the C65 check hours (:30)."""
    t = _as_utc(ts)
    return int(t.hour) in CYCLE65_CHECK_HOURS and int(t.minute) == 30
