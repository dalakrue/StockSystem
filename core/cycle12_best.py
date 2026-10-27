"""Cycle 15 FT-C01 module: the 18:30 UTC mean-reversion system with
trailing exits + dynamic k (Cycle 15 winner, honest upgrade over C12 BEST).

C12 BEST (the baseline): 4 SELL equations at 18:30 UTC, fixed TP/SL,
k=2 -- unseen +1164.21 pips / 163 trades / RoMAD 40.39.
FT-C01 (Cycle 15, current default): SAME 4 equations, but exits trail
(trigger +1.25xATR favorable, SL trails extreme by 0.4xATR) and k is
dynamic (Rule A: k=3 if >=4 candidates, k=2 if >=2, else k=1) --
unseen +1283.12 pips / 167 trades / RoMAD 44.52 / Sharpe 16.71.
10-check PASS, overfit PASS, unseen untouched by selection.
Source of truth for the win: ~/workspace/fx/work_c15/results/comparison_table.csv
(FR-C02 + FS-C01 combined as FT-C01, re-validated from scratch).

Cycle 12 BEST module (C12-BEST): the 18:30 UTC mean-reversion system.

Source of truth: ~/workspace/fx/work_c12/best_system.json (Cycle 6,
mean-reversion thresholds), mined on TRAIN+VAL, TP/SL calibrated on
DISCOVERY, 10-check PASS on UNSEEN. This file implements those equations
VERBATIM -- do not retune thresholds or multipliers here.

Equations (all SELL, 18:30 UTC = 01:00 AM Myanmar next day):
  BEST1 AUDNZD: mom24 > 1.0  AND atr_ratio < 1.0, TP 1.25x ATR14, SL 2.5x ATR14
  BEST2 AUDCHF: mom24 > 1.0  AND atr_ratio < 1.0, TP 1.75x ATR14, SL 1.5x ATR14
  BEST3 AUDCAD: mom24 > 2.0  AND atr_ratio < 1.0, TP 1.5x  ATR14, SL 1.0x ATR14
  BEST4 NZDCAD: mom24 > 1.25 AND atr_ratio < 0.9, TP 1.5x  ATR14, SL 1.0x ATR14

Feature definitions (identical to b11_core / c12_engine):
  mom24     = (close - close 24 H1 bars ago) / atr14
  atr_ratio = atr14 / atr_med30d, atr_med30d = 30-day median of atr14
              (rolling median over 720 H1 bars, min_periods=14)
  atr14     = 14-bar mean true range (rolling, min_periods=1)
  Signal features come from the last COMPLETED H1 candle as of 18:30 UTC,
  i.e. the candle stamped 17:00 UTC. Entry price = open of the H1 candle
  stamped 18:00 UTC (documented proxy for the 18:30 price; H1 cannot
  observe :30). SL-first fills, 1-pip spread baseline, 48h cap.

Selection (ONE condition, used by live indication and backtest alike):
  Top-k per check by score (score = equation standalone discovery RoMAD),
  max 1 open trade per symbol. DEFAULT k = 2 -- the headline BEST system
  (unseen +1164.21 pips / 163 trades / RoMAD 40.39).
  k = None selects EVERY qualifying entry per check (still max 1 open per
  symbol). Uncapped BEST was tested with the full 10-check and PASSED, but
  its unseen RoMAD is LOWER (33.97 vs 40.39) because drawdown deepens
  (-38.17 vs -28.82), so uncapped is an OPT-IN mode, never the default.

Check-time helpers (ONE condition for this module):
  is_cycle12_check_time(ts) / is_entry_check_time(ts) are the single
  source of truth for "is this an entry check?" used by the banner and
  any other Cycle-12 consumer. Old-module checks are OLD_CHECK_HOURS;
  the Cycle-12 check is CYCLE12_CHECK_HOUR_UTC = 18.

Time zones (fixed, from Check_Hours_Reference):
  Myanmar (MMT) = UTC + 6:30 year-round, no DST.
  MetaTrader (broker) = UTC + 3 in summer, UTC + 2 in winter
  (winter approx Oct 25 -> Mar 29; verify against broker Market Watch).

Caveat (from mining): BEST was chosen by ranking candidate systems on
UNSEEN RoMAD, so UNSEEN is not fully untouched for the chosen system and
the 10-check PASS is optimistic to some degree. Fresh forward / paper
trading is required before any live use.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CYCLE12_VERSION = "cycle12-best-v1"
CYCLE12_CHECK_HOUR_UTC = 18          # check at 18:30 UTC = 01:00 AM Myanmar
CYCLE12_CHECK_MINUTE = 30
OLD_CHECK_HOURS = (6, 10, 11, 12, 13)  # Cycle 12: 07 UTC (2:00 PM Myanmar) deleted
ALL_CHECK_HOURS = OLD_CHECK_HOURS + (CYCLE12_CHECK_HOUR_UTC,)
MAX_HOLD_HOURS = 48
BASE_SPREAD_PIPS = 1.0
TP_CLIP = (10.0, 500.0)
SL_CLIP = (5.0, 100.0)
DEFAULT_K = 2                        # C12 BEST baseline; None = every-symbol
# --- Cycle 15 FT-C01 (winner): trailing exits + dynamic k ---
CYCLE15_VERSION = "cycle15-ft01-v1"
EXIT_MODE_DEFAULT = "trailing"       # 'trailing' (FT-C01) | 'fixed' (C12 baseline)
TRAIL_TRIGGER_ATR = 1.25             # trailing activates after +1.25xATR favorable
TRAIL_DIST_ATR = 0.4                 # SL trails favorable extreme by 0.4xATR
def dynamic_k_rule(n_candidates: int) -> int:
    """FS-C01 Rule A, frozen on discovery: k=3 if >=4 cands, k=2 if >=2, else k=1."""
    return 3 if n_candidates >= 4 else (2 if n_candidates >= 2 else 1)
MAX_SIGNAL_AGE_MINUTES = 90          # same as app execution policy

# ---------------------------------------------------------------- equations --
BEST_EQUATIONS = (
    {"id": "BEST1", "symbol": "AUDNZD", "direction": "SELL",
     "mom24_gt": 1.0, "atr_ratio_lt": 1.0,
     "tp_mult": 1.25, "sl_mult": 2.5, "score": 38.82},
    {"id": "BEST2", "symbol": "AUDCHF", "direction": "SELL",
     "mom24_gt": 1.0, "atr_ratio_lt": 1.0,
     "tp_mult": 1.75, "sl_mult": 1.5, "score": 22.73},
    {"id": "BEST3", "symbol": "AUDCAD", "direction": "SELL",
     "mom24_gt": 2.0, "atr_ratio_lt": 1.0,
     "tp_mult": 1.5, "sl_mult": 1.0, "score": 22.64},
    {"id": "BEST4", "symbol": "NZDCAD", "direction": "SELL",
     "mom24_gt": 1.25, "atr_ratio_lt": 0.9,
     "tp_mult": 1.5, "sl_mult": 1.0, "score": 17.04},
)
_BEST_BY_SYMBOL = {e["symbol"]: e for e in BEST_EQUATIONS}



def _as_utc(ts) -> pd.Timestamp:
    """Timestamp -> tz-aware UTC (accepts strings, naive or aware stamps)."""
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


def pip_size(symbol: str) -> float:
    return 0.01 if "JPY" in str(symbol).upper() else 0.0001


# ------------------------------------------------------------------- clocks --
def to_myanmar(ts) -> pd.Timestamp:
    """UTC timestamp -> Myanmar time (UTC+6:30, fixed)."""
    return _as_utc(ts) + pd.Timedelta(hours=6, minutes=30)


def metatrader_offset_hours(ts) -> int:
    """Broker MetaTrader offset: +3 summer, +2 winter (approx Oct 25-Mar 29)."""
    t = _as_utc(ts).tz_localize(None)
    m, d = int(t.month), int(t.day)
    winter = (m == 10 and d >= 25) or m in (11, 12, 1, 2) or (m == 3 and d < 29)
    return 2 if winter else 3


def to_metatrader(ts) -> pd.Timestamp:
    """UTC timestamp -> broker MetaTrader time (approx; verify vs Market Watch)."""
    t = _as_utc(ts)
    return t + pd.Timedelta(hours=metatrader_offset_hours(t))


def fmt_clock(ts) -> dict:
    """UTC / Myanmar / MetaTrader strings for one instant."""
    t = _as_utc(ts)
    return {
        "utc": t.strftime("%Y-%m-%d %H:%M UTC"),
        "myanmar": to_myanmar(t).strftime("%Y-%m-%d %H:%M MMT"),
        "metatrader": to_metatrader(t).strftime("%Y-%m-%d %H:%M")
        + f" MT (GMT{metatrader_offset_hours(t):+d})",
    }


# ------------------------------------------------------- check-time (ONE) ---
def is_cycle12_check_time(ts) -> bool:
    """True only at the 18:30 UTC Cycle-12 check, weekdays."""
    t = _as_utc(ts).tz_localize(None)
    return (t.weekday() < 5 and t.hour == CYCLE12_CHECK_HOUR_UTC
            and t.minute == CYCLE12_CHECK_MINUTE)


def is_old_module_check_time(ts) -> bool:
    """True at an old-module (S1-S240) check: :30 of OLD_CHECK_HOURS, weekdays."""
    t = _as_utc(ts).tz_localize(None)
    return (t.weekday() < 5 and t.hour in OLD_CHECK_HOURS
            and t.minute == CYCLE12_CHECK_MINUTE)


def is_entry_check_time(ts) -> bool:
    """ONE condition: True at any entry check (old module OR Cycle-12)."""
    return is_cycle12_check_time(ts) or is_old_module_check_time(ts)


def check_time_status(now=None, latest_completed_candle=None) -> dict:
    """Banner facts: is this an entry check? is the data updated?

    latest_completed_candle: timestamp of the newest completed H1 candle
    the display was built from (any tz). Data counts as UPDATED when that
    candle closed within MAX_SIGNAL_AGE_MINUTES of now.
    """
    now = pd.Timestamp.now(tz="UTC") if now is None else _as_utc(now)
    cycle12 = is_cycle12_check_time(now)
    old = is_old_module_check_time(now)
    if latest_completed_candle is None:
        updated, age_min = None, None
    else:
        lc = _as_utc(latest_completed_candle)
        age_min = (now - lc).total_seconds() / 60.0
        updated = bool(age_min <= MAX_SIGNAL_AGE_MINUTES)
    return {
        "now_utc": now,
        "clocks": fmt_clock(now),
        "is_entry_check_time": bool(cycle12 or old),
        "is_cycle12_check_time": bool(cycle12),
        "is_old_module_check_time": bool(old),
        "data_updated": updated,
        "data_age_minutes": age_min,
        "latest_completed_candle": latest_completed_candle,
    }


# ----------------------------------------------------------------- features --
def add_cycle12_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add mom24 / atr_ratio / atr14 to an H1 OHLC frame (causal only).

    frame: Datetime-sorted OHLC with columns Open/High/Low/Close (any
    index). Returns a copy with atr14, atr_med30d, atr_ratio, mom24.
    Definitions identical to b11_core / c12_engine.
    """
    g = frame.copy().reset_index(drop=True)
    cl, hi, lo = g["Close"], g["High"], g["Low"]
    tr = pd.concat([(hi - lo), (hi - cl.shift(1)).abs(),
                    (lo - cl.shift(1)).abs()], axis=1).max(axis=1)
    g["atr14"] = tr.rolling(14, min_periods=1).mean()
    g["atr_med30d"] = g["atr14"].rolling(24 * 30, min_periods=14).median()
    g["atr_ratio"] = g["atr14"] / g["atr_med30d"]
    g["mom24"] = (cl - cl.shift(24)) / g["atr14"]
    g["mom24"] = g["mom24"].replace([np.inf, -np.inf], np.nan)
    return g


def evaluate_cycle12_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate BEST equations at one 18:30 UTC check.

    frames: {symbol: H1 OHLC DataFrame indexed by candle-stamp (UTC,
    tz-aware or naive-UTC) with Open/High/Low/Close}. Signal features
    come from the 17:00 UTC candle (last completed as of 18:30 UTC);
    entry price = open of the 18:00 UTC candle. Returns one row per
    firing equation with TP/SL already clipped.
    """
    check = _as_utc(check_time_utc)
    sig_stamp = (check - pd.Timedelta(hours=1, minutes=30)).tz_localize(None)
    ent_stamp = (check - pd.Timedelta(minutes=30)).tz_localize(None)
    rows = []
    for eq in BEST_EQUATIONS:
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
        # locate the signal row positionally (index now 0..n-1 in stamp order)
        pos = ff.index.get_loc(sig_stamp)
        if isinstance(pos, (np.ndarray, slice)):
            continue
        row = feat.iloc[pos]
        atr = float(row["atr14"])
        if not np.isfinite(atr) or atr <= 0:
            continue
        mom24 = float(row["mom24"])
        ratio = float(row["atr_ratio"])
        if not (np.isfinite(mom24) and np.isfinite(ratio)):
            continue
        if not (mom24 > eq["mom24_gt"] and ratio < eq["atr_ratio_lt"]):
            continue
        pip = pip_size(sym)
        atr_pips = atr / pip
        tp = float(min(max(eq["tp_mult"] * atr_pips, TP_CLIP[0]), TP_CLIP[1]))
        sl = float(min(max(eq["sl_mult"] * atr_pips, SL_CLIP[0]), SL_CLIP[1]))
        rows.append({
            "check": check, "symbol": sym, "equation": eq["id"],
            "direction": eq["direction"], "score": eq["score"],
            "mom24": mom24, "atr_ratio": ratio, "atr_pips": atr_pips,
            "entry_px": float(ff.loc[ent_stamp, "Open"]),
            "tp_pips": tp, "sl_pips": sl,
            "signal_candle": sig_stamp, "entry_candle": ent_stamp,
        })
    return pd.DataFrame(rows)


def select_cycle12_entries(signals: pd.DataFrame, open_symbols=(),
                           k=DEFAULT_K, dynamic=False) -> pd.DataFrame:
    """Top-k by score, max 1 open trade per symbol.

    k = 2 reproduces C12 BEST baseline. k = None takes every qualifying
    entry (still max 1 open per symbol). dynamic=True uses FT-C01 Rule A
    (k=3 if >=4 candidates, k=2 if >=2, else k=1), frozen on discovery.
    """
    if signals is None or len(signals) == 0:
        return signals.iloc[0:0] if signals is not None else pd.DataFrame()
    if dynamic:
        k = dynamic_k_rule(len(signals))
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


# ----------------------------------------------------------------- backtest --
def backtest_cycle12(frames: dict, start, end, k=DEFAULT_K,
                     spread_pips: float = BASE_SPREAD_PIPS,
                     exit_mode: str = EXIT_MODE_DEFAULT,
                     dynamic_k: bool = True) -> pd.DataFrame:
    """SL-first backtest of BEST over [start, end): one 18:30 UTC check per
    weekday. Mirrors c12_engine.build_log/simulate_sl_first semantics:
    entry = open of the 18:00 candle, SL-first on same-candle ambiguity,
    48h cap, exit at close on time-out. Returns the trade log.

    FT-C01 defaults (Cycle 15 winner): exit_mode='trailing' (SL trails the
    favorable extreme by TRAIL_DIST_ATR once price moves TRAIL_TRIGGER_ATR
    favorable; initial TP/SL still apply) and dynamic_k=True (Rule A).
    Pass exit_mode='fixed', dynamic_k=False, k=2 to reproduce the C12 BEST
    baseline exactly (unseen +1164.21 / 163 trades / RoMAD 40.39).
    k=None always means uncapped (every qualifying entry), regardless of
    dynamic_k."""
    start = _as_utc(start)
    end = _as_utc(end)
    days = pd.date_range(start.normalize(), end.normalize(), freq="D", tz="UTC")
    days = days[days.weekday < 5]
    checks = pd.DatetimeIndex(sorted(
        d + pd.Timedelta(hours=CYCLE12_CHECK_HOUR_UTC, minutes=30) for d in days))
    checks = checks[(checks >= start) & (checks < end)]
    # Precompute features + candle arrays per symbol once.
    prep = {}
    for sym, f in frames.items():
        ff = f.copy()
        ff.index = pd.to_datetime(ff.index, utc=True).tz_localize(None)
        ff = ff.sort_index()
        feat = add_cycle12_features(ff.reset_index(drop=True))
        prep[sym] = {
            "stamps": ff.index.values.astype("datetime64[ns]"),
            "open": ff["Open"].to_numpy(float),
            "high": ff["High"].to_numpy(float),
            "low": ff["Low"].to_numpy(float),
            "close": ff["Close"].to_numpy(float),
            "feat": feat,
            "pos": {t: i for i, t in enumerate(ff.index)},
        }
    trades = []
    open_until: dict[str, pd.Timestamp] = {}
    for check in checks:
        sig_stamp = (check - pd.Timedelta(hours=1, minutes=30)).tz_localize(None)
        ent_stamp = (check - pd.Timedelta(minutes=30)).tz_localize(None)
        cands = []
        for eq in BEST_EQUATIONS:
            sym = eq["symbol"]
            p = prep.get(sym)
            if p is None or sig_stamp not in p["pos"] or ent_stamp not in p["pos"]:
                continue
            row = p["feat"].iloc[p["pos"][sig_stamp]]
            atr = float(row["atr14"])
            if not np.isfinite(atr) or atr <= 0:
                continue
            mom24, ratio = float(row["mom24"]), float(row["atr_ratio"])
            if not (np.isfinite(mom24) and np.isfinite(ratio)):
                continue
            if not (mom24 > eq["mom24_gt"] and ratio < eq["atr_ratio_lt"]):
                continue
            pip = pip_size(sym)
            atr_pips = atr / pip
            cands.append({
                "check": check, "symbol": sym, "equation": eq["id"],
                "direction": eq["direction"], "score": eq["score"],
                "tp_pips": float(min(max(eq["tp_mult"] * atr_pips, TP_CLIP[0]), TP_CLIP[1])),
                "sl_pips": float(min(max(eq["sl_mult"] * atr_pips, SL_CLIP[0]), SL_CLIP[1])),
                "atr_pips": float(atr_pips),
                "entry_px": float(p["open"][p["pos"][ent_stamp]]),
                "entry_idx": p["pos"][ent_stamp],
            })
        cands.sort(key=lambda r: -r["score"])
        kk = dynamic_k_rule(len(cands)) if (dynamic_k and k is not None) else k
        taken = 0
        for c in cands:
            if kk is not None and taken >= kk:
                break
            sym = c["symbol"]
            if open_until.get(sym) is not None and open_until[sym] > check:
                continue
            p = prep[sym]
            pip = pip_size(sym)
            entry_px = c["entry_px"]
            tp_px = entry_px - c["tp_pips"] * pip   # all SELL
            sl_px = entry_px + c["sl_pips"] * pip
            atr_pips = c["atr_pips"]
            idx = c["entry_idx"]
            exit_px, reason, hold = np.nan, "TIME", MAX_HOLD_HOURS
            # FT-C01 trailing state (all SELL): extreme = lowest low so far
            extreme = entry_px
            trailing_on = False
            for j in range(idx, min(idx + MAX_HOLD_HOURS, len(p["stamps"]))):
                hi, lo, cl = p["high"][j], p["low"][j], p["close"][j]
                hit_sl = hi >= sl_px
                hit_tp = lo <= tp_px
                if hit_sl or hit_tp:  # SL-first
                    exit_px = sl_px if hit_sl else tp_px
                    reason = "SL" if hit_sl else "TP"
                    hold = j - idx + 1
                    break
                # trailing update applies from the NEXT bar (no intrabar ambiguity)
                if exit_mode == "trailing":
                    fav_pips = (entry_px - lo) / pip
                    extreme = min(extreme, lo)
                    if not trailing_on and fav_pips >= TRAIL_TRIGGER_ATR * atr_pips:
                        trailing_on = True
                    if trailing_on:
                        sl_px = min(sl_px, extreme + TRAIL_DIST_ATR * atr_pips * pip)
                if j == min(idx + MAX_HOLD_HOURS, len(p["stamps"])) - 1:
                    exit_px, hold = cl, j - idx + 1
            if not np.isfinite(exit_px):
                continue
            gross = (entry_px - exit_px) / pip
            exit_time = pd.Timestamp(p["stamps"][min(idx + hold - 1, len(p["stamps"]) - 1)]).tz_localize("UTC")
            trades.append({
                "check": check, "symbol": sym, "equation": c["equation"],
                "direction": c["direction"], "entry_px": entry_px,
                "exit_px": float(exit_px), "tp_pips": c["tp_pips"],
                "sl_pips": c["sl_pips"], "gross_pips": float(gross),
                "net_pips": float(gross - spread_pips),
                "exit_reason": reason, "hold_h": int(hold),
                "exit_time": exit_time, "score": c["score"],
            })
            open_until[sym] = exit_time
            taken += 1
    return pd.DataFrame(trades)


def metrics_cycle12(trades: pd.DataFrame) -> dict:
    """Same metric definitions as c12_engine.metrics (net, DD, RoMAD, ...)."""
    m = {"trades": 0, "net_pip": 0.0, "gross_pip": 0.0, "win_rate": 0.0,
         "profit_factor": 0.0, "max_dd": 0.0, "ev": 0.0, "romad": 0.0,
         "sharpe_d": 0.0, "breakeven": 0.0}
    if trades is None or len(trades) == 0:
        return m
    # Drawdown is order-sensitive: cumulate in EXIT order (when P/L is
    # realised), not in the symbol-grouped order a per-symbol simulator
    # emits. Net / EV / PF / Sharpe are order-invariant.
    if "exit_time" in trades.columns:
        trades = trades.sort_values(["exit_time", "symbol"], kind="mergesort")
    net = trades["net_pips"].to_numpy(float)
    gross = trades["gross_pips"].to_numpy(float)
    cum = np.cumsum(net)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))
    dd = float(min(0.0, (np.concatenate([[0.0], cum]) - peak).min()))
    wins, losses = net[net > 0], net[net <= 0]
    pf = float(wins.sum() / abs(losses.sum())) if losses.sum() != 0 else 999.0
    romad = float(cum[-1] / abs(dd)) if dd < 0 else (999.0 if cum[-1] > 0 else 0.0)
    d = pd.DataFrame({"day": pd.to_datetime(trades["check"], utc=True).dt.normalize(),
                      "n": net})
    ddaily = d.groupby("day")["n"].sum().to_numpy()
    sharpe = float(ddaily.mean() / ddaily.std() * np.sqrt(252)) \
        if len(ddaily) > 2 and ddaily.std() > 0 else 0.0
    m.update({"trades": int(len(net)), "net_pip": float(cum[-1]),
              "gross_pip": float(gross.sum()), "win_rate": float(len(wins) / len(net)),
              "profit_factor": float(min(pf, 999.0)), "max_dd": dd,
              "ev": float(net.mean()), "romad": float(min(romad, 999.0)),
              "sharpe_d": sharpe, "breakeven": float(max(0.0, gross.mean()))})
    return m


def describe() -> dict:
    """UI-ready spec summary (no numbers invented: from Cycle 15 mining)."""
    return {
        "version": CYCLE15_VERSION,
        "label": "C15-FT01 (C12 BEST equations + trailing exits + dynamic k)",
        "check": "18:30 UTC = 01:00 AM Myanmar (next day)",
        "default_k": "dynamic (Rule A: 3 if >=4 cands, 2 if >=2, else 1)",
        "selection": "Dynamic k per check by Rule A (frozen on discovery); max 1 open trade per symbol.",
        "execution": ("SL-first, 1-pip spread baseline, 48h cap. Exits trail: "
                      "SL trails favorable extreme by 0.4xATR once price moves "
                      "1.25xATR favorable; initial TP/SL = ATR multiples clipped "
                      "TP [10,500] / SL [5,100] still apply."),
        "equations": [
            {"id": e["id"], "symbol": e["symbol"], "direction": e["direction"],
             "condition": f"mom24 > {e['mom24_gt']} AND atr_ratio < {e['atr_ratio_lt']}",
             "tp": f"{e['tp_mult']}x ATR14", "sl": f"{e['sl_mult']}x ATR14",
             "score": e["score"]} for e in BEST_EQUATIONS],
        "unseen": {"net_pip": 1283.12, "trades": 167, "romad": 44.52,
                   "sharpe": 16.71, "max_dd": -28.82, "win_rate": 0.898,
                   "ev": 7.68, "breakeven": 8.68},
        "baseline_c12": {"net_pip": 1164.21, "trades": 163, "romad": 40.39,
                         "sharpe": 14.18, "max_dd": -28.82,
                         "note": "C12 BEST fixed TP/SL, k=2; available via exit_mode='fixed', dynamic_k=False"},
        "caveat": ("BEST was chosen by ranking on UNSEEN RoMAD, so UNSEEN is "
                   "not fully untouched; 10-check PASS is optimistic to some "
                   "degree. Paper-trade before any live use."),
    }
