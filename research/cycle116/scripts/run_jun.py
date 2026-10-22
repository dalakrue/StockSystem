"""Cycle 116 / Jun: Rogers-Satchell volatility partial-exit overlay on C89-21.
RS vol over latest 24 H1 bars is the yardstick: short-term adverse movement
= adverse 4h close move in units of RS-vol24; trigger when the current loss
>= 0.25 x entry H1 ATR and that z-score exceeds its trailing 90th percentile
(480 H1 bars). One-time 50% partial exit at the mark (an H1 open)."""
import sys, os
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ovl_lib as L
from partial_walk import apply_partial

sysname, N, dp, up = L.MONTHS['Jun']
disc, un = L.load_log(dp), L.load_log(up)

_RS = {}


def rs_frame(sym):
    if sym not in _RS:
        g = L.h1(sym)
        rs2 = (np.log(g['High'] / g['Open']) * np.log(g['High'] / g['Close'])
               + np.log(g['Low'] / g['Open']) * np.log(g['Low'] / g['Close']))
        vol24 = np.sqrt(rs2.rolling(24, min_periods=24).mean())
        out = pd.DataFrame({'close': g['Close'], 'vol24': vol24})
        for dirn, lab in [(1, 'zbuy'), (-1, 'zsell')]:
            adv = (-dirn * (g['Close'] - g['Close'].shift(4))
                   / (vol24 * g['Close']))
            out[lab] = adv
            out[lab + '_thr'] = adv.rolling(480, min_periods=240).quantile(0.90)
        _RS[sym] = out
    return _RS[sym]


def trig(ctx):
    if ctx['float_pips'] > -0.25 * ctx['atr_pips']:
        return False
    f = rs_frame(ctx['sym'])
    t = ctx['mark_t']
    i = f.index.searchsorted(t, side='right') - 1
    if i < 0:
        return False
    z = f['zbuy' if ctx['dirn'] > 0 else 'zsell'].iloc[i]
    thr = f['zbuy_thr' if ctx['dirn'] > 0 else 'zsell_thr'].iloc[i]
    return np.isfinite(z) and np.isfinite(thr) and z > thr


res = {}
big = []
for name, d in [('disc', disc), ('audit', un)]:
    res[name] = {'OFF': L.stats(d)}
    on, tg, _ = apply_partial(d, 0.50, trig)
    res[name]['ON'] = L.stats(on)
    res[name]['trig'] = int(tg.sum())
    if name == 'audit':
        for i in np.where(tg)[0]:
            r0, r1 = d.iloc[i], on.iloc[i]
            if r0['net_pips'] < -80:
                big.append((r0['check'], r0['symbol'], r0['direction'],
                            float(r0['net_pips']), float(r1['net_pips'])))

a_off, a_on = res['audit']['OFF'], res['audit']['ON']
d_off, d_on = res['disc']['OFF'], res['disc']['ON']
improved = (a_on['leftover'] > a_off['leftover'] and d_on['leftover'] > d_off['leftover']
            and a_on['win'] > 80 and d_on['win'] > 80)
verdict = 'POSSIBLE' if improved else 'NOT'
lines = []
lines.append('# Cycle 116 — June (C89-21) — Rogers–Satchell volatility partial-exit overlay\n')
lines.append('Method as specified: Rogers–Satchell OHLC volatility over the latest 24 H1 bars '
             'is the yardstick. If the current loss ≥ 0.25 × entry H1 ATR and the short-term '
             'adverse movement (adverse 4h close move in RS-vol units) exceeds its trailing '
             '90th-percentile threshold, take a one-time 50% partial exit at that H1 open. '
             'Target stat: the expensive losing trades behind the 7.78 cost/loss ratio.\n')
for name, lab in [('disc', 'Discovery'), ('audit', '2025 audit')]:
    lines.append(f'## {lab}\n\n{L.TABLE_HEAD}')
    lines.append(L.fmt_row('OFF', res[name]['OFF']))
    lines.append(L.fmt_row('ON', res[name]['ON']))
    lines.append(f"\nTrades triggering the overlay: {res[name]['trig']}.\n")
if big:
    lines.append('The large audit losses the overlay caught (net pips OFF -> ON):')
    for b in big:
        lines.append(f'- {b[0]} {b[1]} {b[2]}: {b[3]:.1f} -> {b[4]:.1f}')
    lines.append('')
lines.append(f'## Verdict: {verdict}\n')
lines.append(f"One-line reason: audit leftover {a_off['leftover']:.2f}% -> {a_on['leftover']:.2f}%, "
             f"discovery leftover {d_off['leftover']:.2f}% -> {d_on['leftover']:.2f}%, audit avg loss "
             f"{a_off['avg_loss']:.1f} -> {a_on['avg_loss']:.1f} pips; "
             + ('leftover improves on both ledgers with win intact.' if improved
                else 'no leftover improvement on both ledgers at screening level.'))
open('/home/hatch/workspace/fx/work_ovl/results/jun.md', 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
