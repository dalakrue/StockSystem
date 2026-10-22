"""Shared CAViaR-style adverse-tail forecast (Feb test 1, reused by Nov B):
for each symbol, on the H1 grid, the trailing-20-trading-day (480 hourly
changes) 95th percentile of adverse 1-hour moves, in pips, per direction.
Causal: window ends at the timestamp it is stamped on."""
import os, pickle, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ovl_lib as L

CACHE = '/home/hatch/workspace/fx/work_ovl/cache/adv95.pkl'


def build():
    import sqlite3
    con = sqlite3.connect(L.DB)
    syms = [r[0] for r in con.execute(
        'SELECT DISTINCT Symbol FROM ohlc_m15 ORDER BY Symbol')]
    con.close()
    out = {}
    for sym in syms:
        g = L.h1(sym)
        pip = L.pip_size(sym)
        d = g['Close'].diff() / pip  # 1h change in pips
        adv_buy = (-d).rolling(480, min_periods=240).quantile(0.95)
        adv_sell = d.rolling(480, min_periods=240).quantile(0.95)
        out[sym] = pd.DataFrame({'buy': adv_buy, 'sell': adv_sell})
        print('tail', sym, len(g), flush=True)
    with open(CACHE, 'wb') as f:
        pickle.dump(out, f)
    return out


def load():
    if os.path.exists(CACHE):
        with open(CACHE, 'rb') as f:
            return pickle.load(f)
    return build()


def adv95_at(tail, sym, dirn, t):
    """Forecast adverse 1h move (pips) as of time t (last value <= t)."""
    s = tail[sym]['buy' if dirn > 0 else 'sell']
    i = s.index.searchsorted(t, side='right') - 1
    if i < 0:
        return np.nan
    return float(s.iloc[i])


if __name__ == '__main__':
    build()
