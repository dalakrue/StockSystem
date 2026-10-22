"""Cycle 116 shared library: standing V5 winner ledgers, stats, bar data,
house sizing path (c104_core.policy_path). Screening-level only."""
from __future__ import annotations
import os, sys, json, sqlite3
import numpy as np
import pandas as pd

FX = '/home/hatch/workspace/fx'
sys.path.insert(0, f'{FX}/work_c104/scripts')
import c104_core as K  # noqa: E402  (policy_path, at_cost, pip machinery)

DB = f'{FX}/fx_data.db'
COST = 2.5

MONTHS = {  # month -> (system, bestN, disc_log, unseen_log)
    'Jan': ('C60-03', 83,  f'{FX}/work_c60/results/C60-03_disc_log.csv',  f'{FX}/work_c60/results/C60-03_unseen_log.csv'),
    'Feb': ('C85-23', 104, f'{FX}/work_c85/results/WINNER_disc_log.csv',  f'{FX}/work_c85/results/WINNER_unseen_log.csv'),
    'Mar': ('C86-24', 86,  f'{FX}/work_c86/results/WINNER_disc_log.csv',  f'{FX}/work_c86/results/WINNER_unseen_log.csv'),
    'Apr': ('C87-24', 104, f'{FX}/work_c87/results/C87-24_disc_log.csv',  f'{FX}/work_c87/results/C87-24_unseen_log.csv'),
    'May': ('C88-03', 66,  f'{FX}/work_c88/results/C88-03_disc_log.csv',  f'{FX}/work_c88/results/C88-03_unseen_log.csv'),
    'Jun': ('C89-21', 84,  f'{FX}/work_c89/results/WINNER_disc_log.csv',  f'{FX}/work_c89/results/WINNER_unseen_log.csv'),
    'Jul': ('C78-34', 103, f'{FX}/work_c78/results/WINNER_disc_log.csv',  f'{FX}/work_c78/results/WINNER_unseen_log.csv'),
    'Aug': ('C67-04', 121, f'{FX}/work_c67/results/C67-04_disc_log.csv',  f'{FX}/work_c67/results/C67-04_unseen_log.csv'),
    'Sep': ('C91-15', 83,  f'{FX}/work_c91/results/C91-15_disc_log.csv',  f'{FX}/work_c91/results/C91-15_unseen_log.csv'),
    'Oct': ('C92-24', 83,  f'{FX}/work_c92/results/WINNER_disc_log.csv',  f'{FX}/work_c92/results/WINNER_unseen_log.csv'),
    'Nov': ('C93-24', 83,  f'{FX}/work_c93/results/WINNER_disc_log.csv',  f'{FX}/work_c93/results/WINNER_unseen_log.csv'),
    'Dec': ('C94-23', 105, f'{FX}/work_c94/results/WINNER_disc_log.csv',  f'{FX}/work_c94/results/WINNER_unseen_log.csv'),
}


def pip_size(sym):
    return 0.01 if 'JPY' in sym else 0.0001


def load_log(path):
    d = pd.read_csv(path)
    d = K.at_cost(d, COST)  # net_pips := gross_pips - 2.5 (house convention)
    d['check'] = pd.to_datetime(d['check'])
    d['exit_time'] = pd.to_datetime(d['exit_time'])
    d['entry_t'] = d['check'] - pd.Timedelta(minutes=30)
    if 'tdir' in d.columns:
        d['dirn'] = np.where(d['tdir'] == 'BUY', 1, -1)
    else:
        # direction implied by the ledger's own arithmetic:
        # gross_pips = dirn * (exit-entry)/pip_size
        dp = (d['exit_px'] - d['entry_px']).to_numpy(float)
        gp = d['gross_pips'].to_numpy(float)
        with np.errstate(divide='ignore', invalid='ignore'):
            s = np.sign(gp / dp)
        s[~np.isfinite(s)] = 0
        base = np.where(d['direction'] == 'BUY', 1,
                        np.where(d['direction'] == 'SELL', -1, 0))
        d['dirn'] = np.where(s != 0, s, base)
    return d


def stats(d, days=None):
    """House stats on a ledger frame (net_pips already @2.5)."""
    n = len(d)
    if n == 0:
        return dict(trades=0, net=0.0, win=0.0, leftover=0.0, avg_win=0.0,
                    avg_loss=0.0, gross_win=0.0, gross_loss=0.0, epd=0.0)
    net = d['net_pips'].to_numpy(float)
    wins = net[net > 0]
    losses = net[net < 0]
    gw = wins.sum()
    gl = -losses.sum()
    # house leftover (calibrated: Feb audit = 29.3510 exactly):
    # by-trade formula on net@2.5: (W - R*L)/N*100, R = avg_loss/avg_win
    if len(wins) and len(losses):
        R = (-losses.mean()) / wins.mean()
        leftover = (len(wins) - R * len(losses)) / n * 100.0
    elif len(losses) == 0:
        leftover = 100.0
    else:
        leftover = 0.0
    out = dict(trades=n, net=float(net.sum()), win=float((net > 0).mean() * 100),
               leftover=float(leftover),
               avg_win=float(wins.mean()) if len(wins) else 0.0,
               avg_loss=float(-losses.mean()) if len(losses) else 0.0,
               gross_win=float(gw), gross_loss=float(gl))
    out['epd'] = float(n / days) if days else 0.0
    return out


def weekdays_in(year, month):
    import calendar
    return sum(1 for d in range(1, calendar.monthrange(year, month)[1] + 1)
               if pd.Timestamp(year, month, d).weekday() < 5)


# ---------------------------------------------------------------- bars
_M15 = {}
_H1 = {}
_ATR = {}


def m15(sym):
    if sym not in _M15:
        con = sqlite3.connect(DB)
        q = ("SELECT Datetime, Open, High, Low, Close FROM ohlc_m15 "
             "WHERE Symbol=? ORDER BY Datetime")
        d = pd.read_sql_query(q, con, params=(sym,), parse_dates=['Datetime'])
        con.close()
        d = d.set_index('Datetime')
        _M15[sym] = d
    return _M15[sym]


def h1(sym):
    if sym not in _H1:
        d = m15(sym)
        g = d.groupby(pd.Grouper(freq='1h')).agg(
            Open=('Open', 'first'), High=('High', 'max'),
            Low=('Low', 'min'), Close=('Close', 'last')).dropna()
        _H1[sym] = g
    return _H1[sym]


def atr14_h1(sym):
    """Wilder ATR14 on resampled H1 (ewm alpha=1/14, house convention)."""
    if sym not in _ATR:
        g = h1(sym)
        pc = g['Close'].shift(1)
        tr = pd.concat([g['High'] - g['Low'], (g['High'] - pc).abs(),
                        (g['Low'] - pc).abs()], axis=1).max(axis=1)
        _ATR[sym] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    return _ATR[sym]


def atr_at(sym, t):
    s = atr14_h1(sym)
    i = s.index.searchsorted(t, side='right') - 1
    if i < 0:
        return np.nan
    return float(s.iloc[i])


def sorted_sizing_frame(log):
    """Replicates policy_path's internal sort so cap_fn indices align."""
    d = K.at_cost(log, COST).reset_index(drop=True)
    d['entry_t'] = pd.to_datetime(d['check']) - pd.Timedelta(minutes=30)
    d['exit_t'] = pd.to_datetime(d['exit_time'])
    return d.sort_values(['entry_t', 'exit_t'], kind='mergesort') \
            .reset_index(drop=True)


def sizing(log, N, start=1000.0, mult_map=None, global_mult=None):
    """Run the house policy_path. mult_map: dict/array of per-trade lot
    multipliers aligned to sorted_sizing_frame(log) row order."""
    cap_fn = None
    if mult_map is not None:
        arr = np.asarray(mult_map, dtype=float)
        cap_fn = lambda state, i, lot: lot * float(arr[i])  # noqa: E731
    mult_fn = None
    if global_mult is not None:
        mult_fn = lambda t: global_mult  # noqa: E731
    return K.policy_path(log, start, N, mult_fn=mult_fn, cap_fn=cap_fn)


def fmt_row(label, s):
    return (f"| {label} | {s['trades']} | {s['net']:+.1f} | {s['win']:.2f}% | "
            f"{s['leftover']:.2f}% | {s['avg_win']:.1f} | {s['avg_loss']:.1f} |")


TABLE_HEAD = ("| Ledger | Trades | Net pips | Win % | Leftover % | Avg win | "
              "Avg loss |\n|---|---|---|---|---|---|---|")
