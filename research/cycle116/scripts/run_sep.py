"""Cycle 116 / Sep: two-state HMM regime-persistence ranking bonus on C91-15.
Rebuilds the standing system with the producing harness (c91 build_logs:
hour-1 FB cuts + X30B M15 resim), verifies reproduction, then re-runs the
walk with an order_fn that adds the harness's own bonus scale (+400) to a
candidate when the filtered probability of one HMM state (fit on discovery,
filtered forward) has stayed >= 0.70 for the two H1 closes before the check
(same state both closes) for that candidate's symbol."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, '/home/hatch/workspace/fx/work_c91/scripts')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ovl_lib as L
import hmm2
import c91_lib as K
import designs91 as Dz

sysname, N, dp, up = L.MONTHS['Sep']
saved_d_df, saved_u_df = L.load_log(dp), L.load_log(up)
symbols = sorted(set(saved_d_df['symbol']) | set(saved_u_df['symbol']))
params, probs = hmm2.load(symbols)
print('HMM params: A=', params['A'].round(3).tolist(), 'mu=',
      params['mu'].round(2).tolist(), flush=True)


def persistent(sym, chk):
    """True when one state's filtered prob >= 0.70 at both of the last two
    completed H1 closes before the check (entry = chk - 30m)."""
    P = probs[sym]
    ent = pd.Timestamp(chk) - pd.Timedelta(minutes=30)
    i = P.index.searchsorted(ent, side='right') - 1  # bar stamped ent-1h
    if i < 1:
        return False
    a = P.iloc[i].to_numpy(float)
    b = P.iloc[i - 1].to_numpy(float)
    return bool((a.max() >= 0.70) and (b.max() >= 0.70)
                and (a.argmax() == b.argmax()))


BONUS = 400.0
n_bonus_rows = [0]


def order_fn(chk, grp):
    key = grp['eff'].to_numpy(float).copy()
    syms = grp['symbol'].to_numpy()
    for j in range(len(grp)):
        if persistent(syms[j], chk):
            key[j] += BONUS
            n_bonus_rows[0] += 1
    return list(np.argsort(-key, kind='stable'))


def build(order):
    cands = K.get_cands()
    eqs = Dz.eqs_without(Dz.FB_H1)
    tw = Dz.TWEAKS['X30B']
    out = {}
    for gname, per in [('d', 'disc'), ('u', 'audit')]:
        picks = K.walk(cands, gname, eqs=eqs, bonus=400.0, order_fn=order)
        log, _ = K.resim_log(picks, tw)
        out[per] = log
    return out


def prep(df):
    d = df.copy()
    d['check'] = pd.to_datetime(d['check'])
    d['exit_time'] = pd.to_datetime(d['exit_time'])
    d['net_pips'] = d['gross_pips'] - L.COST
    return d


off = build(None)
saved_d, saved_u = L.stats(saved_d_df), L.stats(saved_u_df)
off_d, off_u = L.stats(prep(off['disc'])), L.stats(prep(off['audit']))
repro_ok = (abs(off_d['net'] - saved_d['net']) < 0.5
            and abs(off_u['net'] - saved_u['net']) < 0.5
            and off_d['trades'] == saved_d['trades']
            and off_u['trades'] == saved_u['trades'])
print('repro', repro_ok, off_d['net'], saved_d['net'], off_u['net'],
      saved_u['net'], flush=True)

on = build(order_fn)
on_d, on_u = L.stats(prep(on['disc'])), L.stats(prep(on['audit']))

improved = (repro_ok and on_u['leftover'] > off_u['leftover']
            and on_d['leftover'] > off_d['leftover']
            and on_u['win'] > 80 and on_d['win'] > 80)
verdict = 'POSSIBLE' if improved else 'NOT'
lines = ['# Cycle 116 — September (C91-15) — Two-state HMM regime-persistence ranking bonus\n',
         'Method as specified: two-state Gaussian HMM on standardized H1 returns + log '
         'high–low ranges, fit on discovery, filtered forward. An eligible candidate gets '
         'a ranking bonus (the harness\'s own +400 bonus scale, added in the walk\'s '
         'order_fn) when the filtered probability of its market state has stayed ≥ 0.70 '
         'for two consecutive H1 closes before the check (same state at both closes). '
         'The standing fallback cuts and X30B stop logic are preserved.\n',
         f'HMM fit: transition matrix {params["A"].round(3).tolist()}, state means '
         f'{params["mu"].round(2).tolist()} (standardized [return, log-range]). '
         f'Candidate rows awarded the bonus during the walks: {n_bonus_rows[0]}.\n',
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
