"""Cycle 56 module: C56-15 (February-only system, follow-up round).

22 equations (13 incumbent mined mom/atr legs + 2 fresh legs + 7 TREND
fallbacks) spanning 3 check hours (11:30, 13:30, 16:30 UTC = 17:30,
19:30, 22:30 MMT), exactly 1 entry per check (top-1 by score).

C56-15 REPLACES C29-31 as February's system. It won the follow-up
round (Cycle 56, 20 end-to-end processes, fresh mining only, judged
at the 2.5-pip primary cost with the round's relaxed win gate >= 80%
plus leftover improvement): weak ratings 7 (vs 11), unseen net@2.5
+124.8 (vs -26.7), win 86.44%, leftover 21.6% (vs -5.7%), checks
10/12, discovery net +2,321.1 (9/9 February blocks positive), sizing
PASS (best N 104), P(profit) 100%. Its LCT (Left95) at the MIDDLE
level PASSES (paired P 96.47%, 5th-percentile 24.13%; report-only --
the unseen leftover improvement of +27.3 pts is not a close call).
Cycle 29 (C29-31) remains selectable.

Design (HYBRID surgery of the incumbent): the incumbent's 15 mined
legs minus its 2 USDCHF legs, plus the incumbent's TREND fallbacks
minus the CHF slots (EURCHF h13 and USDCHF h16 fallbacks removed),
plus 2 fresh legs:
  * f56_kst_rev_EURJPY_h11_SELL -- KST-reversion: fires when the
    normalised Know Sure Thing oscillator (kst_n) at the signal
    candle exceeds 1.2. Exits scale off ATR14 like the incumbent.
  * f56_cmo_trd_GBPJPY_h13_BUY -- Chande Momentum trend: fires when
    CMO14 > 30 and still rising over 3 bars (cmo14_d3 > 0). Its
    TP/SL distances scale off the Rogers-Satchell volatility in
    price units (rs_vol_px) instead of ATR14 -- the ONLY leg with a
    non-ATR14 exit scale (vol_col in the research spec).

Fresh feature definitions (verbatim from the Cycle 56 research,
work_c56/scripts/c56_feats.py; all causal):
  kst_n     ROCn = 100*(Close/Close[-n] - 1);
            KST = SMA10(ROC10) + 2*SMA10(ROC15) + 3*SMA10(ROC20)
                  + 4*SMA15(ROC30); kst_n = KST / trailing-480-bar
            mean of |KST| (min 120 bars).
  cmo14     over the last 14 close diffs: 100*(sum up - sum down) /
            (sum up + sum down); cmo14_d3 = cmo14 - cmo14 3 bars ago.
  rs_vol_px per bar v = ln(H/O)*ln(H/C) + ln(L/O)*ln(L/C);
            rs_vol = sqrt(20-bar mean of v); rs_vol_px = rs_vol*Close.

Fallback equations (FB_*): direction 'TREND' fires on every check so
the exactly-1-entry-per-check rule always has a candidate; live
direction resolves per-trade from the signal candle's mom24 sign
(BUY if > 0 else SELL) -- the same fixed rule the research used.

Source of truth: ~/workspace/fx/work_c56/results/WINNER.json
Full spec: ~/workspace/fx/work_c56/results/WINNER_SPEC.json
Discovery trade log: ~/workspace/fx/work_c56/results/WINNER_disc_log.csv
Unseen trade log: ~/workspace/fx/work_c56/results/WINNER_unseen_log.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle12_best import add_cycle12_features, pip_size as _pip_size

CYCLE56_VERSION = "cycle56-c5615-v1"
CYCLE56_CHECK_HOURS = (11, 13, 16)  # checks at h:30 UTC
CYCLE56_SYMBOLS_N = 10
MAX_HOLD_HOURS = 48
BASE_SPREAD_PIPS = 1.0
TP_CLIP = (10.0, 500.0)
SL_CLIP = (5.0, 100.0)

# ---------------------------------------------------------------- equations --
# "vol_col": volatility column the TP/SL distances scale off. All legs
# use atr14 except f56_cmo_trd_GBPJPY_h13_BUY (rs_vol_px).
C56_EQUATIONS = (
    {"id": 'mom_GBPUSD_h11_momS_T0.75_A0.9_0.75x8', "symbol": 'GBPUSD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 983.298883189655, "vol_col": "atr14"},
    {"id": 'mom_NZDCAD_h11_momB_T2.0_A0.9_0.75x8', "symbol": 'NZDCAD', "hour": 11, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.0}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 954.7054795454546, "vol_col": "atr14"},
    {"id": 'mom_AUDNZD_h11_momS_T2.0_A1.0_1.25x8', "symbol": 'AUDNZD', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 950.2179125, "vol_col": "atr14"},
    {"id": 'mom_USDCAD_h11_momB_T2.0_A1.0_1.0x8', "symbol": 'USDCAD', "hour": 11, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.0}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 944.8548444444444, "vol_col": "atr14"},
    {"id": 'mom_NZDCAD_h13_momB_T2.5_A0.9_0.75x5', "symbol": 'NZDCAD', "hour": 13, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.5}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.18665, "vol_col": "atr14"},
    {"id": 'mom_USDCAD_h13_momB_T2.5_A1.0_1.25x8', "symbol": 'USDCAD', "hour": 13, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -2.5}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 1.25, "sl_mult": 8.0, "score": 976.1924650261324, "vol_col": "atr14"},
    {"id": 'mom_GBPUSD_h13_momS_T1.0_A0.9_1.0x8', "symbol": 'GBPUSD', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 1.0}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 972.6338722222222, "vol_col": "atr14"},
    {"id": 'mom_NZDUSD_h13_momS_T0.75_A1.0_0.75x8', "symbol": 'NZDUSD', "hour": 13, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 956.8170855590063, "vol_col": "atr14"},
    {"id": 'mom_AUDCHF_h16_momB_T0.75_A0.9_0.75x5', "symbol": 'AUDCHF', "hour": 16, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 1000.2607357142857, "vol_col": "atr14"},
    {"id": 'mom_USDCAD_h16_momS_T0.75_A1.0_0.5x8', "symbol": 'USDCAD', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": 1000.2561107142857, "vol_col": "atr14"},
    {"id": 'mom_NZDCAD_h16_momB_T0.75_A0.9_0.75x8', "symbol": 'NZDCAD', "hour": 16, "direction": 'BUY',
     "conditions": [{"col": "mom24", "op": "<", "val": -0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 966.870338095238, "vol_col": "atr14"},
    {"id": 'mom_NZDUSD_h16_momS_T0.75_A0.9_0.75x8', "symbol": 'NZDUSD', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 0.9}],
     "tp_mult": 0.75, "sl_mult": 8.0, "score": 950.1407125, "vol_col": "atr14"},
    {"id": 'mom_GBPUSD_h16_momS_T0.75_A1.0_0.75x5', "symbol": 'GBPUSD', "hour": 16, "direction": 'SELL',
     "conditions": [{"col": "mom24", "op": ">", "val": 0.75}, {"col": "atr_ratio", "op": "<", "val": 1.0}],
     "tp_mult": 0.75, "sl_mult": 5.0, "score": 920.1384178571428, "vol_col": "atr14"},
    {"id": 'f56_kst_rev_EURJPY_h11_SELL', "symbol": 'EURJPY', "hour": 11, "direction": 'SELL',
     "conditions": [{"col": "kst_n", "op": ">", "val": 1.2}],
     "tp_mult": 1.0, "sl_mult": 8.0, "score": 1093.0446428571433, "vol_col": "atr14"},
    {"id": 'f56_cmo_trd_GBPJPY_h13_BUY', "symbol": 'GBPJPY', "hour": 13, "direction": 'BUY',
     "conditions": [{"col": "cmo14", "op": ">", "val": 30}, {"col": "cmo14_d3", "op": ">", "val": 0}],
     "tp_mult": 1.5, "sl_mult": 8.0, "score": 1100.0, "vol_col": "rs_vol_px"},
    {"id": 'FB_EURUSD_h11_0', "symbol": 'EURUSD', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 10.0, "score": -1000000001.0, "vol_col": "atr14"},
    {"id": 'FB_GBPUSD_h11_1', "symbol": 'GBPUSD', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 10.0, "score": -1000000002.0, "vol_col": "atr14"},
    {"id": 'FB_NZDUSD_h11_2', "symbol": 'NZDUSD', "hour": 11, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000003.0, "vol_col": "atr14"},
    {"id": 'FB_USDCAD_h13_1', "symbol": 'USDCAD', "hour": 13, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 8.0, "score": -1000000005.0, "vol_col": "atr14"},
    {"id": 'FB_EURGBP_h13_2', "symbol": 'EURGBP', "hour": 13, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.5, "sl_mult": 8.0, "score": -1000000006.0, "vol_col": "atr14"},
    {"id": 'FB_EURUSD_h16_1', "symbol": 'EURUSD', "hour": 16, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.4, "sl_mult": 10.0, "score": -1000000008.0, "vol_col": "atr14"},
    {"id": 'FB_GBPUSD_h16_2', "symbol": 'GBPUSD', "hour": 16, "direction": 'TREND',
     "conditions": [],
     "tp_mult": 0.3, "sl_mult": 8.0, "score": -1000000009.0, "vol_col": "atr14"},
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
    """Base cycle12 features + the Cycle 56 fresh columns (kst_n,
    cmo14, cmo14_d3, rs_vol_px) for a normalised frame (cached)."""
    key = (sym, len(ff), ff.index[0], ff.index[-1])
    hit = _FEAT_CACHE.get(key)
    if hit is not None:
        return hit
    if len(_FEAT_CACHE) > 32:
        _FEAT_CACHE.clear()
    feat = add_cycle12_features(ff.reset_index(drop=True))
    feat.index = ff.index
    O, H, L, C = ff["Open"], ff["High"], ff["Low"], ff["Close"]
    # --- KST (Know Sure Thing), normalised ---
    def _roc(x, n):
        return (x / x.shift(n) - 1.0) * 100.0
    kst = (_roc(C, 10).rolling(10).mean() + 2 * _roc(C, 15).rolling(10).mean()
           + 3 * _roc(C, 20).rolling(10).mean()
           + 4 * _roc(C, 30).rolling(15).mean())
    scale = kst.abs().rolling(480, min_periods=120).mean().replace(0.0, np.nan)
    feat["kst_n"] = kst / scale
    # --- Chande Momentum Oscillator 14 ---
    d = C.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    su = up.rolling(14).sum()
    sd = dn.rolling(14).sum()
    feat["cmo14"] = 100.0 * (su - sd) / (su + sd).replace(0.0, np.nan)
    feat["cmo14_d3"] = feat["cmo14"] - feat["cmo14"].shift(3)
    # --- Rogers-Satchell volatility in price units ---
    lo_, lh, ll_, lc = np.log(O), np.log(H), np.log(L), np.log(C)
    rs_bar = (lh - lo_) * (lh - lc) + (ll_ - lo_) * (ll_ - lc)
    rs_vol = np.sqrt(rs_bar.rolling(20, min_periods=20).mean().clip(lower=0))
    feat["rs_vol_px"] = rs_vol * C
    _FEAT_CACHE[key] = feat
    return feat


def evaluate_cycle56_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate C56-15 equations at one check time (h:30 UTC).

    frames: {symbol: H1 OHLC DataFrame indexed by candle-stamp}.
    Only equations whose hour matches the check hour are evaluated.
    Signal features come from the (h-1):00 UTC candle (last completed
    as of h:30 UTC); entry price = open of the h:00 UTC candle.
    TP/SL distances scale off each equation's vol_col (atr14 for all
    legs except the CMO leg, which uses rs_vol_px), clipped to the
    standard [10,500] / [5,100] pip clips. 'TREND' fallbacks resolve
    direction from the signal candle's mom24.
    Returns one row per firing equation with TP/SL already clipped.
    """
    check = _as_utc(check_time_utc)
    hour = int(check.hour)
    if hour not in CYCLE56_CHECK_HOURS:
        return pd.DataFrame()
    sig_stamp = (check - pd.Timedelta(hours=1, minutes=30)).tz_localize(None)
    ent_stamp = (check - pd.Timedelta(minutes=30)).tz_localize(None)
    frames_norm = {}
    for s, f in (frames or {}).items():
        if f is None or len(f) == 0:
            continue
        frames_norm[str(s).upper()] = _norm_frame(f)
    rows = []
    for eq in C56_EQUATIONS:
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
        vol = float(row[eq["vol_col"]])
        if not np.isfinite(vol) or vol <= 0:
            continue
        direction = eq["direction"]
        if direction == "TREND":
            direction = _trend_direction(row.get("mom24"))
        pip = _pip_size(sym)
        vol_pips = vol / pip
        tp = float(min(max(eq["tp_mult"] * vol_pips, TP_CLIP[0]), TP_CLIP[1]))
        sl = float(min(max(eq["sl_mult"] * vol_pips, SL_CLIP[0]), SL_CLIP[1]))
        rows.append({
            "check": check, "symbol": sym, "equation": eq["id"],
            "direction": direction, "score": eq["score"],
            "atr_pips": atr / pip, "vol_pips": vol_pips,
            "entry_px": float(ff.loc[ent_stamp, "Open"]),
            "tp_pips": tp, "sl_pips": sl,
            "signal_candle": sig_stamp, "entry_candle": ent_stamp,
        })
    return pd.DataFrame(rows)


def select_cycle56_entries(signals: pd.DataFrame, open_symbols=()) -> pd.DataFrame:
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


def is_cycle56_check_time(ts) -> bool:
    """True if ts (UTC) is at one of the C56 check hours (:30)."""
    t = _as_utc(ts)
    return int(t.hour) in CYCLE56_CHECK_HOURS and int(t.minute) == 30
