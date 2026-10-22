"""Cycle 116 / Feb: CAViaR-style conditional-tail partial-exit overlay on C85-23."""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ovl_lib as L
import tail_series as T
from partial_walk import apply_partial

tail = T.load()
sysname, N, dp, up = L.MONTHS['Feb']
disc, un = L.load_log(dp), L.load_log(up)


def trig(ctx):
    if ctx['float_pips'] >= 0:
        return False
    f = T.adv95_at(tail, ctx['sym'], ctx['dirn'], ctx['mark_t'])
    return np.isfinite(f) and f > 0.35 * ctx['atr_pips']


res = {}
for name, d in [('disc', disc), ('audit', un)]:
    res[name] = {'OFF': L.stats(d)}
    for frac, lab in [(0.25, 'A25'), (0.50, 'B50')]:
        on, tg, _ = apply_partial(d, frac, trig)
        res[name][lab] = L.stats(on)
        res[name][lab + '_trig'] = int(tg.sum())

lines = []
lines.append('# Cycle 116 — February (C85-23) — CAViaR-style conditional-tail overlay\n')
lines.append('Method as specified: rolling 95th-percentile adverse 1h move from M15 returns '
             '(trailing 20 trading days, H1 grid). While a trade is open and losing, if the '
             'forecast adverse move > 0.35 × entry H1 ATR, close 25% (variant A) / 50% '
             '(variant B) at the next H1 open. Screening pass on saved ledgers; partial-exit '
             'remainder keeps the original outcome (trigger marks required inside the TP/SL band).\n')
for name, lab in [('disc', 'Discovery'), ('audit', '2025 audit')]:
    lines.append(f'## {lab}\n\n{L.TABLE_HEAD}')
    for k in ['OFF', 'A25', 'B50']:
        lines.append(L.fmt_row(k, res[name][k]))
    lines.append(f"\nTrades triggering the overlay: A {res[name]['A25_trig']}, "
                 f"B {res[name]['B50_trig']} (same trigger set, different fraction).\n")

a_off, a_a, a_b = res['audit']['OFF'], res['audit']['A25'], res['audit']['B50']
d_off, d_a, d_b = res['disc']['OFF'], res['disc']['A25'], res['disc']['B50']
best = max([('A', a_a, d_a), ('B', a_b, d_b)],
           key=lambda x: (x[1]['leftover'] + x[2]['leftover']))
improved = (best[1]['leftover'] > a_off['leftover'] and
            best[2]['leftover'] > d_off['leftover'] and
            best[1]['win'] > 80 and best[2]['win'] > 80)
verdict = 'POSSIBLE' if improved else 'NOT'
lines.append(f"## Verdict: {verdict}\n")
lines.append(f"One-line reason: best variant ({best[0]}) moves audit leftover "
             f"{a_off['leftover']:.2f}% -> {best[1]['leftover']:.2f}% and discovery leftover "
             f"{d_off['leftover']:.2f}% -> {best[2]['leftover']:.2f}%, audit avg loss "
             f"{a_off['avg_loss']:.1f} -> {best[1]['avg_loss']:.1f} pips; "
             + ('leftover improves on both ledgers with win rate intact.' if improved
                else 'no leftover improvement on both ledgers — the tail cuts cost more on the trades that recover than they save on the trades that fail.'))
open('/home/hatch/workspace/fx/work_ovl/results/feb.md', 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
