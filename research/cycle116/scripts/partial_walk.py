"""Generic intratrade partial-exit walk (Feb / Jun / Jul overlays).

For each trade in a ledger, step through H1 opens strictly inside
(entry_t, exit_time). At each mark, price = Open of the M15 bar stamped
at that hour (the fill price for a close at that H1 open). A trigger
function decides (once) to close `frac` of the position at that mark;
the remainder keeps the trade's original outcome (the trigger mark is
required to lie inside the trade's TP/SL band, so the original path is
not contradicted). Screening-level approximation, stated in reports.

trigger_fn(ctx) -> bool, ctx keys: sym, dirn, entry_px, pip, atr_pips,
mark_t, mark_px, float_pips (gross, at mark), bars_seen (list of H1
closes up to mark), trade row.
Returns: new gross_pips array, n_triggered.
"""
import numpy as np
import pandas as pd
import ovl_lib as L


def apply_partial(d, frac, trigger_fn):
    gross = d['gross_pips'].to_numpy(float).copy()
    trig = np.zeros(len(d), dtype=bool)
    trig_px = np.full(len(d), np.nan)
    bars_cache = {}
    for i, r in d.iterrows():
        sym = r['symbol']
        if sym not in bars_cache:
            bars_cache[sym] = L.m15(sym)
        bars = bars_cache[sym]
        pip = L.pip_size(sym)
        dirn = int(r['dirn'])
        entry = float(r['entry_px'])
        et, xt = r['entry_t'], r['exit_time']
        atr_pips = L.atr_at(sym, et) / pip
        t = et + pd.Timedelta(hours=1)
        seen_closes = []
        done = False
        while t < xt and not done:
            if t in bars.index:
                px = float(bars.at[t, 'Open'])
                fp = dirn * (px - entry) / pip
                h1c = L.h1(sym)
                j = h1c.index.searchsorted(t, side='right') - 1
                if j >= 0:
                    seen_closes.append(float(h1c['Close'].iloc[j]))
                # trigger mark must be inside the original TP/SL band,
                # else the trade would already have exited
                if -float(r['sl_pips_used']) < fp < float(r['tp_pips_used']):
                    ctx = dict(sym=sym, dirn=dirn, entry_px=entry, pip=pip,
                               atr_pips=atr_pips, mark_t=t, mark_px=px,
                               float_pips=fp, closes=seen_closes, row=r)
                    if trigger_fn(ctx):
                        gross[i] = frac * fp + (1 - frac) * gross[i]
                        trig[i] = True
                        trig_px[i] = px
                        done = True
            t += pd.Timedelta(hours=1)
    out = d.copy()
    out['gross_pips'] = gross
    out['net_pips'] = gross - L.COST
    return out, trig, trig_px
