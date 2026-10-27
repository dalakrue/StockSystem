"""Cycle 274 (C274) -- December SECOND-BEST system: the BRIEF18
Block A A1 confirmation stack at depth 10 over the standing
December system C94-23 (core.cycle94_best, UNCHANGED and still
the December default).

INTEGRATED 2026-10-25 under the user's explicit waiver order
("I can ignore chain and DSR test, continue"): this candidate
passed every other term of the standing middle battery (audit
judging, corrected LCT-middle P 100.00% / q05 100.00%, EC22
15 vs control 14, priorities 14/16, red lines) and was blocked
ONLY by the chain floor and (for the round) the compounding
terms the user waived. It is NOT an old-policy validation. The
incumbent C94-23 remains the December default everywhere; this
module is an additional selectable system only.

DEFINITION (BRIEF18 December, C265-C274; engine:
fx/work_m15mine/b18_dec, stacks_a1.json depth 10 = condition
indices [96, 1, 3, 7, 13, 18, 31, 56, 15, 25] of
step2_trackA_lib.all_conditions(), thresholds = the FIT-frame
th_fit.json quantiles): the incumbent C94-23 walk (candidate
rows in score order, C94 FB gate applied, max 1 open trade per
symbol) where a candidate row is VETOED unless its section-3
feature row (BRIEF16 feature table, computed at the entry time
from M15 bars, generation recipe of work_c196 step1_generate)
satisfies ALL ten stack conditions:

   1. h1_three_dn-c1 : last-completed-H1-bar 3-down pattern
      flag == 1 AND direction term d == +1
   2. rsi-q50-rev    : d * (rsi14 - 50)    <= 0.0
   3. rsi-q65-rev    : d * (rsi14 - 50)    <= -4.622879974335688
   4. stoch-q50-rev  : d * (stoch_k - 50)  <= 0.0
   5. cci-q50-rev    : d * cci20           <= 0.0
   6. willr-q50-cont : d * (willr14 - 0.5) >= 0.0
   7. di-q50-rev     : d * di_diff         <= 0.0
   8. pos-0.5        : (d > 0 and day_pos <= 0.5) or
                       (d < 0 and day_pos >= 0.5)
   9. cci-q65-rev    : d * cci20           <= -0.5537250461819219
  10. macd-q50-rev   : d * macd_h          <= 0.0

Direction term d (the December pool convention, preserved
exactly): d = +1 when the pool row's direction is 'BUY', else
-1 -- December's TREND-fallback rows are stamped 'TREND', so
FB_* candidates ALWAYS take d = -1 here, whatever the resolved
trade direction (the same quirk the C94 FB gate's CLV already
preserves in core.cycle94_best; never "corrected"). Conditions
use the research tolerance (threshold -/+ 1e-12). A row whose
features cannot be computed (no M15 data / NaN) FAILS the
stack, exactly as a NaN fails cond_mask in the research engine.

VERIFIED NUMBERS (research ledgers, cost 2.5, A3 frame;
app-replay verification in FIX_NOTES_20261025_WAIVER_
INTEGRATION.md): DISC (Dec 2016-2023) n31 net +414.18 win
100.00% leftover 100.00 DD 0.00; AUDIT (Dec 2024+2025) n5
net +94.39 win 100.00% leftover 100.00 DD 0.00. Best N 105
(the incumbent's ladder; the candidate is a subset walk of
the same system). Recorded caveat: the candidate survives on
31 + 5 trades -- a perfect score on a handful of trades.

M15 DATA: evaluate takes m15_frames ({symbol: M15 OHLC frame,
naive-UTC DatetimeIndex of bar starts}); fetch_
cycle274_m15_frames() builds it through the cycle78 data path
(local candle repository first, provider chain for misses,
memoised 10 minutes) over the C94 symbol set. Feature values
are computed over the trailing min(1600, available) M15 bars
ending at the entry time -- the research generation used the
full 1600-bar window; live frames carry fewer bars, and the
Wilder/EMA-seeded oscillators converge to the same values
(the pattern, session and rolling-window features are exact
on any window that covers their lookback).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import core.cycle94_best as _c94
from core.cycle94_best import (CYCLE94_CHECK_HOURS,
                               is_cycle94_check_time,
                               select_cycle94_entries)
from core.cycle78_best import fetch_cycle78_m15_frames

CYCLE274_CHECK_HOURS = CYCLE94_CHECK_HOURS
C274_SYMBOLS = list(_c94.C94_SYMBOLS)

# Stack thresholds (BRIEF18 December FIT frame, th_fit.json).
TH_RSI_R65 = -4.622879974335688     # osc_rsi_r65
TH_CCI_R65 = -0.5537250461819219    # osc_cci_r65
# All other stack thresholds are exactly 0.0 in th_fit.json
# (osc_rsi_r50, osc_stoch_r50, osc_cci_r50, osc_willr_c50,
# osc_di_r50, osc_macd_r50 -- medians of the direction-signed
# FIT distributions).


# ------------------------------------------------------------ features --
def _wilder_ewm(x, p):
    """pandas ewm(alpha=1/p, adjust=False) -- the generation
    recipe's Wilder smoothing (seeded at the slice start)."""
    return pd.Series(x).ewm(alpha=1.0 / p,
                             adjust=False).mean().to_numpy()


def _pattern_flags(o, h, l, c):
    """BRIEF16 section-3 pattern flags for the LAST bar
    (verbatim port of step0_benchmark.pattern_flags).
    o/h/l/c are arrays with >= 1 bar; flags use the last 3."""
    out = {k: 0 for k in ('engulf', 'hammer', 'shoot', 'inside',
                          'doji', 'three', 'pin')}
    if len(c) < 3:
        return out
    o1, h1, l1, c1 = o[-1], h[-1], l[-1], c[-1]
    o2, h2, l2, c2 = o[-2], h[-2], l[-2], c[-2]
    body1, body2 = c1 - o1, c2 - o2
    rng1 = h1 - l1
    up_w = h1 - max(o1, c1)
    lo_w = min(o1, c1) - l1
    eng = 0
    if body1 > 0 and body2 < 0 and o1 <= c2 and c1 >= o2:
        eng = 1
    elif body1 < 0 and body2 > 0 and o1 >= c2 and c1 <= o2:
        eng = -1
    out['engulf'] = eng
    out['hammer'] = 1 if (rng1 > 0 and lo_w >= 2 * abs(body1)
                          and up_w <= 0.5 * abs(body1) + 1e-12) else 0
    out['shoot'] = 1 if (rng1 > 0 and up_w >= 2 * abs(body1)
                         and lo_w <= 0.5 * abs(body1) + 1e-12) else 0
    out['inside'] = 1 if (h1 <= h2 and l1 >= l2) else 0
    out['doji'] = 1 if (rng1 > 0 and abs(body1) <= 0.1 * rng1) else 0
    b = np.sign(np.array([c[-3] - o[-3], body2, body1]))
    mono = (c[-3] < c[-2] < c[-1]) or (c[-3] > c[-2] > c[-1])
    out['three'] = int(b[0]) if (b[0] != 0 and (b == b[0]).all()
                                 and mono) else 0
    pin = 0
    if rng1 > 0:
        if lo_w / rng1 >= 0.6:
            pin = 1
        elif up_w / rng1 >= 0.6:
            pin = -1
    out['pin'] = pin
    return out


def stack_features(m15df, ent, entry_px):
    """Section-3 features at entry time `ent` (generation-exact
    port of work_c196/scripts/step1_generate.py feature_vector,
    restricted to the columns the BRIEF18 stacks consume).

    m15df: M15 OHLC frame, naive-UTC DatetimeIndex of bar
    STARTS, columns Open/High/Low/Close. Causal slice = bars
    starting before `ent`, last 1600. entry_px = open of the
    entry bar (the first bar at/after ent). Returns a dict of
    floats (NaN where undefined): rsi14, stoch_k, cci20,
    willr14, macd_h, di_diff, day_pos, hammer, pin_b,
    h1_three_dn."""
    keys = ('rsi14', 'stoch_k', 'cci20', 'willr14', 'macd_h',
            'di_diff', 'day_pos', 'hammer', 'pin_b', 'h1_three_dn')
    nan = float('nan')
    out = {k: nan for k in keys}
    out['hammer'] = 0.0
    out['pin_b'] = 0.0
    out['h1_three_dn'] = 0.0
    if m15df is None or len(m15df) == 0:
        return out
    f = m15df
    idx = pd.to_datetime(f.index)
    if idx.tz is not None:
        idx = idx.tz_convert('UTC').tz_localize(None)
    ts = idx.values.astype('datetime64[ns]').astype(np.int64)
    ent = pd.Timestamp(ent)
    e = int(np.searchsorted(ts, ent.value))
    lo_i = max(0, e - 1600)
    o = f['Open'].to_numpy(float)[lo_i:e]
    h = f['High'].to_numpy(float)[lo_i:e]
    l = f['Low'].to_numpy(float)[lo_i:e]
    c = f['Close'].to_numpy(float)[lo_i:e]
    tsw = ts[lo_i:e]
    n = len(c)
    if n == 0:
        return out
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc),
                                      np.abs(l - pc)))
    atr = _wilder_ewm(tr, 14)
    atr15 = float(atr[-1])
    # --- oscillators (M15) ---
    dc = np.diff(c)
    gain = np.where(dc > 0, dc, 0.0)
    loss = np.where(dc < 0, -dc, 0.0)
    ag = _wilder_ewm(gain, 14)
    al = _wilder_ewm(loss, 14)
    with np.errstate(divide='ignore', invalid='ignore'):
        rsi = 100.0 - 100.0 / (1.0 + np.where(
            al > 0, ag / np.maximum(al, 1e-12), np.inf))
    out['rsi14'] = float(rsi[-1])
    if n >= 14:
        hh14 = h[-14:].max()
        ll14 = l[-14:].min()
        out['stoch_k'] = float((c[-1] - ll14) / (hh14 - ll14) * 100.0) \
            if hh14 - ll14 > 0 else nan
        out['willr14'] = float((hh14 - c[-1]) / (hh14 - ll14)) \
            if hh14 > ll14 else nan
    if n >= 20:
        tp = (h + l + c) / 3.0
        sma20 = tp[-20:].mean()
        md20 = np.abs(tp[-20:] - sma20).mean()
        out['cci20'] = float((tp[-1] - sma20) / (0.015 * md20) / 100.0) \
            if md20 > 0 else nan
    ema12 = pd.Series(c).ewm(span=12, adjust=False).mean().to_numpy()
    ema26 = pd.Series(c).ewm(span=26, adjust=False).mean().to_numpy()
    macd = ema12 - ema26
    sig = pd.Series(macd).ewm(span=9, adjust=False).mean().to_numpy()
    out['macd_h'] = float((macd[-1] - sig[-1]) / atr15) \
        if atr15 > 0 else nan
    pdm = np.where((h[1:] - h[:-1]) > (l[:-1] - l[1:]),
                   np.maximum(h[1:] - h[:-1], 0.0), 0.0)
    ndm = np.where((l[:-1] - l[1:]) > (h[1:] - h[:-1]),
                   np.maximum(l[:-1] - l[1:], 0.0), 0.0)
    tr1 = tr[1:]
    s_tr = _wilder_ewm(tr1, 14)
    s_p = _wilder_ewm(pdm, 14)
    s_n = _wilder_ewm(ndm, 14)
    pdi = 100.0 * s_p / np.maximum(s_tr, 1e-12)
    ndi = 100.0 * s_n / np.maximum(s_tr, 1e-12)
    out['di_diff'] = float((pdi[-1] - ndi[-1]) / 100.0)
    # --- M15 pattern flags (last bar of the slice) ---
    fl = _pattern_flags(o, h, l, c)
    out['hammer'] = float(fl['hammer'])
    out['pin_b'] = 1.0 if fl['pin'] == 1 else 0.0
    # --- last completed H1 bar pattern (256-bar tail resample,
    # clock-aligned bins, generation recipe) ---
    t0i = max(0, n - 256)
    h1df = pd.DataFrame(
        {'Open': o[t0i:], 'High': h[t0i:], 'Low': l[t0i:],
         'Close': c[t0i:]},
        index=pd.to_datetime(tsw[t0i:]))
    if len(h1df):
        h1 = h1df.resample('1h').agg({'Open': 'first', 'High': 'max',
                                      'Low': 'min', 'Close': 'last'})
        h1 = h1[h1.index + pd.Timedelta(hours=1) <= ent]
        if len(h1) >= 3:
            fh = _pattern_flags(
                h1['Open'].to_numpy(float)[-3:],
                h1['High'].to_numpy(float)[-3:],
                h1['Low'].to_numpy(float)[-3:],
                h1['Close'].to_numpy(float)[-3:])
            out['h1_three_dn'] = 1.0 if fh['three'] == -1 else 0.0
    # --- session: day_pos over today's causal bars (UTC day) ---
    day_ns = (ent.value // 86_400_000_000_000) * 86_400_000_000_000
    bar_day = (tsw // 86_400_000_000_000) * 86_400_000_000_000
    tm = bar_day == day_ns
    if tm.any():
        thi = float(h[tm].max())
        tlo = float(l[tm].min())
        rng_today = thi - tlo
        out['day_pos'] = float((entry_px - tlo) / rng_today) \
            if rng_today > 0 else nan
    return out


def _dec_stack_pass(feat, d):
    """The C274 depth-10 stack (all ten conditions, research
    cond_mask semantics; NaN fails)."""
    if feat is None:
        return False
    s_rsi = feat['rsi14'] - 50.0
    s_stoch = feat['stoch_k'] - 50.0
    s_cci = feat['cci20']
    s_willr = feat['willr14'] - 0.5
    s_macd = feat['macd_h']
    s_di = feat['di_diff']
    dp = feat['day_pos']
    if not (feat['h1_three_dn'] == 1.0 and d == 1.0):
        return False
    if not (d * s_rsi <= 0.0 + 1e-12):
        return False
    if not (d * s_rsi <= TH_RSI_R65 + 1e-12):
        return False
    if not (d * s_stoch <= 0.0 + 1e-12):
        return False
    if not (d * s_cci <= 0.0 + 1e-12):
        return False
    if not (d * s_willr >= 0.0 - 1e-12):
        return False
    if not (d * s_di <= 0.0 + 1e-12):
        return False
    pos_ok = (d > 0 and dp <= 0.5 + 1e-12) or \
             (d < 0 and dp >= 0.5 - 1e-12)
    if not pos_ok:
        return False
    if not (d * s_cci <= TH_CCI_R65 + 1e-12):
        return False
    if not (d * s_macd <= 0.0 + 1e-12):
        return False
    return True


def evaluate_cycle274_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None) -> pd.DataFrame:
    """C94-23 signals (C94 FB gate included, via the frozen
    cycle94 module) with the C274 confirmation stack applied:
    rows failing any stack condition are dropped, which is
    exactly the research walk's behaviour (the stack depends
    only on the candidate row, so the walk continues to the
    next row at the check)."""
    sig = _c94.evaluate_cycle94_signals(frames, check_time_utc,
                                        m15_frames=m15_frames)
    if sig is None or len(sig) == 0:
        return sig
    sig = sig.copy()
    feat_cache: dict = {}
    keep = []
    for i, row in sig.iterrows():
        sym = str(row['symbol'])
        if sym not in feat_cache:
            m15df = (m15_frames or {}).get(sym)
            feat_cache[sym] = stack_features(
                m15df, row['entry_candle'], float(row['entry_px'])) \
                if m15df is not None else None
        feat = feat_cache[sym]
        # December direction convention: FB rows are stamped
        # 'TREND' in the research pools -> d = -1 always;
        # non-FB rows take their fixed trade direction.
        if str(row['equation']).startswith('FB_'):
            d = -1.0
        else:
            d = 1.0 if str(row['direction']) == 'BUY' else -1.0
        if _dec_stack_pass(feat, d):
            keep.append(i)
    return sig.loc[keep] if keep else sig.iloc[0:0]


def select_cycle274_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: the frozen C71-04 selection
    (as for C94-23)."""
    return select_cycle94_entries(signals, open_symbols=open_symbols)


def is_cycle274_check_time(ts) -> bool:
    return is_cycle94_check_time(ts)


_M15_FETCH_MEMO = {"ts": None, "frames": None}
_M15_FETCH_TTL_S = 600.0


def fetch_cycle274_m15_frames(state=None):
    """Use the shared current M15 data; do not retain a stale private memo."""
    return fetch_cycle78_m15_frames(state=state, symbols=C274_SYMBOLS)
