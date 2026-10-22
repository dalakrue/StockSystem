"""Cycle 116 / Sep report stage: stats on the isolated build's CSVs,
reproduction check against the saved C91-15 winner logs, verdict, sep.md."""
import pickle
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ovl_lib as L

base = '/home/hatch/workspace/fx/work_ovl/cache'
with open(f'{base}/hmm_sep.pkl', 'rb') as f:
    HMM = pickle.load(f)
A = np.round(HMM['params']['A'], 3).tolist()
MU = np.round(HMM['params']['mu'], 2).tolist()


def prep(path):
    d = pd.read_csv(path)
    d['check'] = pd.to_datetime(d['check'])
    d['exit_time'] = pd.to_datetime(d['exit_time'])
    d['net_pips'] = d['gross_pips'] - L.COST
    return d


sysname, N, dp, up = L.MONTHS['Sep']
saved_d, saved_u = L.stats(L.load_log(dp)), L.stats(L.load_log(up))
off_d = L.stats(prep(f'{base}/sep_off_disc.csv'))
off_u = L.stats(prep(f'{base}/sep_off_audit.csv'))
on_d = L.stats(prep(f'{base}/sep_on_disc.csv'))
on_u = L.stats(prep(f'{base}/sep_on_audit.csv'))
repro_ok = (abs(off_d['net'] - saved_d['net']) < 0.5
            and abs(off_u['net'] - saved_u['net']) < 0.5
            and off_d['trades'] == saved_d['trades']
            and off_u['trades'] == saved_u['trades'])
improved = (repro_ok and on_u['leftover'] > off_u['leftover']
            and on_d['leftover'] > off_d['leftover']
            and on_u['win'] > 80 and on_d['win'] > 80)
verdict = 'POSSIBLE' if improved else 'NOT'
lines = ['# Cycle 116 — September (C91-15) — Two-state HMM regime-persistence ranking bonus\n',
         'Method as specified: two-state Gaussian HMM on standardized H1 returns + log '
         'high–low ranges, fit on discovery (EM, diagonal covariances), filtered forward. '
         'An eligible candidate gets a ranking bonus (the harness\'s own +400 bonus scale, '
         'added in the walk\'s order function) when the filtered probability of its market '
         'state has stayed ≥ 0.70 for two consecutive H1 closes before the check (same state '
         'at both closes). The standing fallback cuts and X30B stop logic are preserved. '
         'Build ran in the isolated Cycle-91 harness environment; reproduction of the '
         'standing system was verified before judging the overlay.\n',
         f'HMM fit: transition matrix {A}, state means (standardized [return, log-range]) '
         f'{MU}.\n',
         f'Harness reproduction of the standing system: {"PASS" if repro_ok else "FAIL"} '
         f'(walk OFF disc net {off_d["net"]:+.1f} vs saved {saved_d["net"]:+.1f}; audit net '
         f'{off_u["net"]:+.1f} vs saved {saved_u["net"]:+.1f}).\n']
for lab, o, n in [('Discovery', off_d, on_d), ('2025 audit', off_u, on_u)]:
    lines.append(f'## {lab}\n\n{L.TABLE_HEAD}')
    lines.append(L.fmt_row('OFF', o))
    lines.append(L.fmt_row('ON', n))
    lines.append('')
lines.append(f'## Verdict: {verdict}\n')
lines.append(f"One-line reason: audit leftover {off_u['leftover']:.2f}% -> {on_u['leftover']:.2f}%, "
             f"discovery leftover {off_d['leftover']:.2f}% -> {on_d['leftover']:.2f}%; "
             + ('regime-persistence bonus improves leftover on both ledgers with win intact.' if improved
                else 'no leftover improvement on both ledgers at screening level.'))
open('/home/hatch/workspace/fx/work_ovl/results/sep.md', 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
