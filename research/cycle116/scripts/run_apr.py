"""Cycle 116 / Apr: Theil-Sen robust-slope ranking bonus on C87-24.
Rebuilds the standing system with the producing harness (c87 walk_log:
bans + M18 rerank), verifies reproduction against the saved winner logs,
then adds ONE more rerank step of the harness's own form: within the
post-M18 top-3, candidates whose directional Theil-Sen slope (median
pairwise slope of prior 24 H1 closes, normalized by H1 ATR) >= 0.015
ATR/bar are promoted to the front (stable). Bonus, not a veto."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, '/home/hatch/workspace/fx/work_c87/scripts')
sys.path.insert(0, '/home/hatch/workspace/fx/work_c75/scripts')
sys.path.insert(0, '/home/hatch/workspace/fx/work_c63/scripts')
sys.path.insert(0, '/home/hatch/workspace/fx/work_c40/scripts')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ovl_lib as L
from c75_run import cands, do_walk, m_rerank

FB_EURGBP = 'FB_EURGBP_h18_1'
FB_GBPUSD = 'FB_GBPUSD_h16_1'
BANS = {FB_EURGBP, FB_GBPUSD, 'FB_USDCHF_h18_2'}


def ts_slope(sym, chk):
    """Directional-ready Theil-Sen slope per bar, ATR-normalized, from the
    24 H1 closes completed at the check (entry = chk - 30m)."""
    ent = chk - pd.Timedelta(minutes=30)
    g = L.h1(sym)
    i = g.index.searchsorted(ent, side='right') - 1
    if i < 24:
        return np.nan
    c = g['Close'].iloc[i - 23:i + 1].to_numpy(float)
    ii, jj = np.triu_indices(24, k=1)
    slopes = (c[jj] - c[ii]) / (jj - ii)
    atr = L.atr_at(sym, ent)
    if not np.isfinite(atr) or atr <= 0:
        return np.nan
    return float(np.median(slopes) / atr)


def ts_rerank(chk, grows, per):
    top3 = grows[:3]
    passers = []
    for r in top3:
        try:
            sym = r['symbol']
        except Exception:
            sym = str(r['strategy']).split('_')[1]
        d = 1 if r['direction'] == 'BUY' else -1
        s = ts_slope(sym, chk)
        if np.isfinite(s) and d * s >= 0.015:
            passers.append(r)
    if not passers:
        return grows
    ps = {id(r) for r in passers}
    return passers + [r for r in grows if id(r) not in ps]


def walk(per, extra_ts=False):
    cdf = cands(per)
    banned = {(c, s) for c, s in zip(cdf['check'], cdf['strategy'])
              if s in BANS}
    fns = [m_rerank('M18')]
    if extra_ts:
        fns.append(ts_rerank)

    def rr(chk, grows, per, _fns=fns):
        for fn in _fns:
            grows = fn(chk, grows, per)
        return grows
    return do_walk(cdf, per, rerank=rr, banned=banned)


def prep(df):
    d = df.copy()
    d['check'] = pd.to_datetime(d['check'])
    d['exit_time'] = pd.to_datetime(d['exit_time'])
    d['net_pips'] = d['gross_pips'] - L.COST
    return d


res = {}
for per, lname in [('d', 'disc'), ('u', 'audit')]:
    off = prep(walk(per, extra_ts=False))
    on = prep(walk(per, extra_ts=True))
    res[lname] = {'OFF': L.stats(off), 'ON': L.stats(on)}
    changed = int((off['strategy'].to_numpy() != on['strategy'].to_numpy()).sum()) \
        if len(off) == len(on) else -1
    res[lname]['picks_changed'] = changed

sysname, N, dp, up = L.MONTHS['Apr']
saved_d, saved_u = L.stats(L.load_log(dp)), L.stats(L.load_log(up))
repro_ok = (abs(res['disc']['OFF']['net'] - saved_d['net']) < 0.5
            and abs(res['audit']['OFF']['net'] - saved_u['net']) < 0.5
            and res['disc']['OFF']['trades'] == saved_d['trades']
            and res['audit']['OFF']['trades'] == saved_u['trades'])

a_off, a_on = res['audit']['OFF'], res['audit']['ON']
d_off, d_on = res['disc']['OFF'], res['disc']['ON']
improved = (repro_ok and a_on['leftover'] > a_off['leftover']
            and d_on['leftover'] > d_off['leftover']
            and a_on['win'] > 80 and d_on['win'] > 80)
verdict = 'POSSIBLE' if improved else 'NOT'
lines = ['# Cycle 116 — April (C87-24) — Theil–Sen robust-slope ranking bonus\n',
         'Method as specified: keep the existing top-three ranking and corridor conditions; '
         'calculate a robust (Theil–Sen, median pairwise) slope from the preceding 24 H1 '
         'closes normalized by H1 ATR; use it as a ranking bonus, not a veto — implemented in '
         'the harness\'s own rerank form: within the post-M18 top-3, candidates with '
         'directional slope ≥ 0.015 ATR/bar are promoted to the front (stable order).\n',
         f'Harness reproduction of the standing system: {"PASS" if repro_ok else "FAIL"} '
         f'(walk OFF disc net {res["disc"]["OFF"]["net"]:+.1f} vs saved {saved_d["net"]:+.1f}; '
         f'audit net {res["audit"]["OFF"]["net"]:+.1f} vs saved {saved_u["net"]:+.1f}).\n']
for lname, lab in [('disc', 'Discovery'), ('audit', '2025 audit')]:
    lines.append(f'## {lab}\n\n{L.TABLE_HEAD}')
    lines.append(L.fmt_row('OFF', res[lname]['OFF']))
    lines.append(L.fmt_row('ON', res[lname]['ON']))
    lines.append(f"\nPicks changed by the bonus: {res[lname]['picks_changed']}.\n")
lines.append(f'## Verdict: {verdict}\n')
lines.append(f"One-line reason: audit leftover {a_off['leftover']:.2f}% -> {a_on['leftover']:.2f}%, "
             f"discovery leftover {d_off['leftover']:.2f}% -> {d_on['leftover']:.2f}% with "
             f"{res['audit']['picks_changed']} audit picks changed; "
             + ('the slope bonus improves leftover on both ledgers with win intact.' if improved
                else 'no leftover improvement on both ledgers at screening level.'))
open('/home/hatch/workspace/fx/work_ovl/results/apr.md', 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
