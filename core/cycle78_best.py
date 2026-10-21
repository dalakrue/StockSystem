"""Cycle 78 (C78-34) -- July H1 system, PROMOTED BY MUSE'S
DECISION 2026-10-21 under the user's standing rule (Program 3,
Top-40 H1+M15 round; the coordinator verdict at the strict
all-16 bar was NO_IMPROVEMENT -- see below).

C66-08 IS FROZEN as the entry engine: checks at 15:00 / 17:00 /
18:00 UTC delegate verbatim to core.cycle66_best (27 equations,
exactly 1 entry/check). Cycle 78 adds ONE at-entry exit layer,
Program 3's July test X30:

    at entry, if ER15(16) <= 0.20 AND r1(1) >= 0, the trade's
    stop-loss distance S is set to 0.90 x S (TP unchanged).

ER15(16) is the efficiency ratio over the 17 M15 closes ending
with the M15 bar that ends at the entry time: |c[j]-c[j-16]| /
sum|c[k]-c[k-1]| (k = j-15..j), computed on completed M15 bars
only (the research availability gate -- bar index j >= 90 and a
finite positive M15 Wilder ATR14 at j -- is preserved; when the
features cannot be computed the trade is left UNMODIFIED, which
is exactly the research harness's fallback outcome; the July
research data had 0 fallbacks). r1(1) is the direction-signed
1-bar H1 momentum at the signal bar (check - 1h30m),
d * (Close[t] - Close[t-1]) / ATR14_H1[t] with d = +1 BUY /
-1 SELL; only its sign enters the rule, so it is computed from
the H1 closes of the frame the app already holds.

Why this system: it is the first July challenger in any round
to clear the paired LCT against C66-08 WHILE improving the
unseen month -- battery 11/12, 15/16 on the Program-3 bar,
failing ONLY check 8 (no red discovery weeks), which C66-08
itself fails (3 red weeks of 44). It passes all four of the
user's priority checks: LCT-middle PASS (paired P 90.56%,
own 5th-percentile 42.18%), unseen leftover 62.48% > 61.20%,
2.96 entries/day, win 95.59%. Unseen net@2.5 +487.7 vs +477.7,
discovery net +3,690.3 vs +3,621.6, stress@4.5 net +351.7.
117 discovery + 18 unseen trades had their stops tightened.
Best N 103 (C78-34's own sizing run: peak margin 48.16%,
max DD 11.30%). C66-08 remains selectable as cycle66.

M15 DATA: evaluate_cycle78_signals takes an optional
m15_frames argument ({symbol: M15 OHLC frame, naive-UTC
DatetimeIndex of bar STARTS, columns Open/High/Low/Close}).
fetch_cycle78_m15_frames() builds it for live use from the
app's local candle repository first, then the provider chain
(the Cycle 22 pattern: never loop fresh provider calls when
the cache has the bars); load_m15_frames_sqlite() reads the
research Dukascopy BID table (fx_data.db ohlc_m15) for
backtest/replay. When no M15 frame is available for a symbol,
that symbol's signals pass through unmodified -- the layer is
simply inactive, C66-08 behaviour. Exit simulation in the
research round ran on M15 bars (SL before TP within a bar, a
gap through the stop fills at the bar open, 48h cap counted
in M15 trading bars); the app emits entries only, as for every
other cycle.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.cycle66_best import (CYCLE66_CHECK_HOURS,
                               evaluate_cycle66_signals,
                               is_cycle66_check_time,
                               select_cycle66_entries)

CYCLE78_CHECK_HOURS = CYCLE66_CHECK_HOURS
X30_ER15_16_MAX = 0.20
X30_SL_FACTOR = 0.90


def _wilder_atr14(o, h, l, c):
    """Wilder ATR14 exactly as the research harness (seed = mean
    of the first 14 true ranges at index 13, then the Wilder
    recurrence). Used only as the feature-availability gate."""
    n = len(c)
    out = np.full(n, np.nan)
    if n <= 14:
        return out
    pc = np.empty(n)
    pc[0] = c[0]
    pc[1:] = c[:-1]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    out[13] = np.mean(tr[:14])
    for i in range(14, n):
        out[i] = (out[i - 1] * 13 + tr[i]) / 14
    return out


def _m15_arrays(m15df):
    f = m15df.copy()
    f.index = pd.to_datetime(f.index)
    if f.index.tz is not None:
        f.index = f.index.tz_convert('UTC').tz_localize(None)
    f = f.sort_index()
    o = f['Open'].to_numpy(dtype=float)
    h = f['High'].to_numpy(dtype=float)
    l = f['Low'].to_numpy(dtype=float)
    c = f['Close'].to_numpy(dtype=float)
    return {'idx': f.index, 'o': o, 'h': h, 'l': l, 'c': c,
            'atr14': _wilder_atr14(o, h, l, c),
            'pos': {t: i for i, t in enumerate(f.index)}}


def _er15_16(m15a, entry_time):
    """ER15(16) at the M15 bar ending at `entry_time`, or None
    when the research availability gate is not met."""
    j = m15a['pos'].get(pd.Timestamp(entry_time)
                         - pd.Timedelta(minutes=15))
    if j is None or j < 90:
        return None
    atr = m15a['atr14'][j]
    if not np.isfinite(atr) or atr <= 0:
        return None
    c = m15a['c']
    seg = c[j - 16:j + 1]
    den = np.abs(np.diff(seg)).sum()
    if den == 0:
        return None
    return abs(seg[-1] - seg[0]) / den


def _r1_1_sign(h1df, sig_stamp, direction):
    """Sign of r1(1) at the signal bar, or None when the two
    closes are unavailable. The ATR denominator is positive,
    so the sign is d * (Close[t] - Close[t-1])."""
    f = h1df
    idx = f.index
    if idx.tz is not None:
        idx = idx.tz_convert('UTC').tz_localize(None)
    pos = idx.get_indexer([pd.Timestamp(sig_stamp)])[0]
    if pos < 1:
        return None
    c = f['Close'].to_numpy(dtype=float)
    d = 1.0 if direction == 'BUY' else -1.0
    return d * (c[pos] - c[pos - 1])


def x30_sl_adjustment(symbol, direction, sig_stamp, entry_stamp,
                      h1df, m15df):
    """True when the X30 condition holds for one C66-08 entry."""
    if m15df is None or h1df is None:
        return False
    er = _er15_16(_m15_arrays(m15df), entry_stamp)
    if er is None or not (er <= X30_ER15_16_MAX):
        return False
    r1 = _r1_1_sign(h1df, sig_stamp, direction)
    if r1 is None or not (r1 >= 0):
        return False
    return True


def evaluate_cycle78_signals(frames: dict, check_time_utc,
                             m15_frames: dict | None = None) -> pd.DataFrame:
    """C66-08 signals with the X30 stop-tightening layer applied.

    `frames` are the H1 frames (as for cycle66); `m15_frames`
    is an optional {symbol: M15 OHLC frame} mapping. Signals for
    symbols without M15 data pass through unmodified. Adds the
    columns 'sl_pips_base' (pre-layer stop) and 'x30_modified'.
    """
    sig = evaluate_cycle66_signals(frames, check_time_utc)
    if sig is None or len(sig) == 0:
        return sig
    sig = sig.copy()
    sig['sl_pips_base'] = sig['sl_pips']
    sig['x30_modified'] = False
    if not m15_frames:
        return sig
    m15_cache = {}
    for i, row in sig.iterrows():
        sym = str(row['symbol'])
        m15df = m15_frames.get(sym)
        if m15df is None or not len(m15df):
            continue
        if sym not in m15_cache:
            m15_cache[sym] = _m15_arrays(m15df)
        er = _er15_16(m15_cache[sym], row['entry_candle'])
        if er is None or not (er <= X30_ER15_16_MAX):
            continue
        r1 = _r1_1_sign(frames[sym], row['signal_candle'],
                        str(row['direction']))
        if r1 is None or not (r1 >= 0):
            continue
        sig.at[i, 'sl_pips'] = float(row['sl_pips']) * X30_SL_FACTOR
        sig.at[i, 'x30_modified'] = True
    return sig


def select_cycle78_entries(signals: pd.DataFrame,
                           open_symbols=()) -> pd.DataFrame:
    """Exactly 1 entry per check: the frozen C66-08 selection."""
    return select_cycle66_entries(signals, open_symbols=open_symbols)


def is_cycle78_check_time(ts) -> bool:
    return is_cycle66_check_time(ts)


def load_m15_frames_sqlite(db_path, symbols=None, start=None, end=None):
    """M15 frames from the research Dukascopy BID table
    (fx_data.db, table ohlc_m15) -- the exact series the X30
    features were researched on. Returns {symbol: frame} with
    a naive-UTC DatetimeIndex of bar starts and Open/High/Low/
    Close columns."""
    import sqlite3
    q = 'SELECT "Datetime", "Open", "High", "Low", "Close" FROM ohlc_m15 WHERE "Symbol"=?'
    args = []
    if start is not None:
        q += ' AND "Datetime" >= ?'
        args.append(str(pd.Timestamp(start)))
    if end is not None:
        q += ' AND "Datetime" < ?'
        args.append(str(pd.Timestamp(end)))
    q += ' ORDER BY "Datetime"'
    if symbols is None:
        with sqlite3.connect(db_path) as conn:
            symbols = [r[0] for r in conn.execute(
                'SELECT DISTINCT "Symbol" FROM ohlc_m15')]
    frames = {}
    with sqlite3.connect(db_path) as conn:
        for sym in symbols:
            df = pd.read_sql_query(q, conn, params=[sym] + args)
            if df.empty:
                continue
            df['Datetime'] = pd.to_datetime(df['Datetime'])
            frames[sym] = df.set_index('Datetime').sort_index()
    return frames


def _normalize_m15_frame(df):
    """Repository/provider frame -> naive-UTC indexed OHLC."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    out = df.copy()
    tcol = next((c for c in ('time', 'open_time', 'Datetime', 'datetime',
                             'timestamp', 'date') if c in out.columns), None)
    if tcol is None and isinstance(out.index, pd.DatetimeIndex):
        idx = out.index
        ts = idx.tz_convert('UTC').tz_localize(None) if idx.tz is not None else idx
        out.index = ts
    elif tcol is None:
        return None
    else:
        ts = pd.to_datetime(out[tcol], errors='coerce')
        try:
            ts = ts.dt.tz_localize('UTC') if ts.dt.tz is None \
                else ts.dt.tz_convert('UTC')
        except Exception:
            return None
        out = out.drop(columns=[tcol])
        out.index = pd.DatetimeIndex(ts).tz_localize(None)
    ren = {c: c.title() for c in ('open', 'high', 'low', 'close')
           if c in out.columns}
    out = out.rename(columns=ren)
    if not all(c in out.columns for c in ('Open', 'High', 'Low', 'Close')):
        return None
    out = out[~out.index.isna()].sort_index()
    out = out[~out.index.duplicated(keep='last')]
    return out if len(out) >= 91 else None


_M15_FETCH_MEMO = {'ts': None, 'frames': None}
_M15_FETCH_TTL_S = 600.0


def fetch_cycle78_m15_frames(state=None, symbols=None):
    """Live M15 frames for the X30 layer: local candle
    repository first (zero API calls), provider chain only for
    symbols the cache cannot serve. Returns {symbol: frame};
    symbols that cannot be served are simply absent (the layer
    stays inactive for them). Results are memoised for 10
    minutes so repeated evaluations never loop provider calls;
    stale memo bars simply fail the entry-time lookup and leave
    trades unmodified."""
    import time
    now = time.monotonic()
    default_symbols = symbols is None
    if default_symbols and _M15_FETCH_MEMO['ts'] is not None \
            and now - _M15_FETCH_MEMO['ts'] < _M15_FETCH_TTL_S:
        return _M15_FETCH_MEMO['frames']
    if symbols is None:
        from core.cycle66_best import CYCLE66_EQUATIONS
        symbols = sorted({e['symbol'] for e in CYCLE66_EQUATIONS})
    frames = {}
    repo = None
    try:
        from core.data.candle_repository import CandleRepository
        repo = CandleRepository()
    except Exception:
        repo = None
    missing = []
    for sym in symbols:
        df = None
        if repo is not None:
            try:
                cached = repo.load(sym, 'M15', limit=200,
                                   completed_only=True)
                df = _normalize_m15_frame(cached)
            except Exception:
                df = None
        if df is None:
            missing.append(sym)
        else:
            frames[sym] = df
    if missing:
        try:
            from core.data.market_data_orchestrator import (
                fetch_forex_candles_provider_chain)
        except Exception:
            fetch_forex_candles_provider_chain = None
        if fetch_forex_candles_provider_chain is not None:
            for sym in missing:
                try:
                    live_df, _status, _trace = \
                        fetch_forex_candles_provider_chain(
                            sym, 'M15', outputsize=200, state=state)
                    df = _normalize_m15_frame(live_df)
                    if df is not None:
                        frames[sym] = df
                except Exception:
                    continue
    if default_symbols:
        _M15_FETCH_MEMO['ts'] = now
        _M15_FETCH_MEMO['frames'] = frames
    return frames
