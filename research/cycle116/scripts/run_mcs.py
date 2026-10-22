"""Cycle 116 / Mar + Dec: Model Confidence Set (Hansen-Lunde-Nason),
range-statistic variant referenced to the current best model.
Per-trade returns aggregated to daily P&L (trades are timestamped; MCS
needs a common time index — stated adaptation), loss = -P&L, circular
block bootstrap, block = 5 days, B = 1000, confidence 80%, seed 20261101.
"""
import sys, os
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ovl_lib as L

RNG = np.random.default_rng(20261101)
B, BLOCK, CONF = 1000, 5, 0.80
OUT = '/home/hatch/workspace/fx/work_ovl/results'


def daily_matrix(models):
    """models: dict name -> combined ledger df. Returns (dates, P&L matrix)."""
    series = {}
    for name, d in models.items():
        g = d.groupby(d['check'].dt.normalize())['net_pips'].sum()
        series[name] = g
    all_dates = sorted(set().union(*[set(s.index) for s in series.values()]))
    idx = pd.DatetimeIndex(all_dates)
    M = np.column_stack([series[n].reindex(idx).fillna(0.0).to_numpy(float)
                         for n in models])
    return idx, M


def block_bootstrap_means(D, B, block, rng):
    """D: T x K differential series (loss_i - loss_best). Returns bootstrap
    means of the CENTERED series, B x K."""
    T, K = D.shape
    Dc = D - D.mean(axis=0)
    nblocks = int(np.ceil(T / block))
    out = np.empty((B, K))
    for b in range(B):
        starts = rng.integers(0, T, size=nblocks)
        rows = (starts[:, None] + np.arange(block)[None, :]) % T
        rows = rows.ravel()[:T]
        out[b] = Dc[rows].mean(axis=0)
    return out


def mcs(loss, names):
    """loss: T x M (higher = worse). Returns (survivors, elimination log)."""
    alive = list(range(loss.shape[1]))
    log = []
    while len(alive) > 1:
        sub = loss[:, alive]
        best_local = int(np.argmin(sub.mean(axis=0)))
        best = alive[best_local]
        others = [a for a in alive if a != best]
        D = loss[:, others] - loss[:, [best]]
        dbar = D.mean(axis=0)
        boot = block_bootstrap_means(D, B, BLOCK, RNG)
        se = boot.std(axis=0, ddof=1)
        se = np.where(se > 0, se, np.inf)
        tvals = dbar / se
        maxstat = (boot / se).max(axis=1)
        crit = np.quantile(maxstat, CONF)
        worst_local = int(np.argmax(tvals))
        if tvals[worst_local] > crit:
            elim = others[worst_local]
            log.append((names[elim], float(tvals[worst_local]), float(crit)))
            alive.remove(elim)
        else:
            log.append((None, float(tvals.max()), float(crit)))
            break
    return [names[a] for a in alive], log


def run(month, challengers, gates_note, extra):
    sysname, N, dp, up = L.MONTHS[month]
    inc = pd.concat([L.load_log(dp), L.load_log(up)], ignore_index=True)
    models = {f'{sysname} (incumbent)': inc}
    for name, (cd, cu) in challengers.items():
        models[name] = pd.concat([L.load_log(cd), L.load_log(cu)],
                                 ignore_index=True)
    idx, P = daily_matrix(models)
    loss = -P
    names = list(models.keys())
    survivors, log = mcs(loss, names)
    avg = {n: float(P[:, i].mean()) for i, n in enumerate(names)}
    lines = [f'# Cycle 116 — {month} ({sysname}) — Model Confidence Set overlay\n',
             'Method as specified: incumbent vs a fixed challenger set with saved ledgers, '
             '80% MCS, 1,000 block-bootstrap draws, 5-day blocks, on per-trade returns '
             '(aggregated to daily P&L — trades are timestamped and MCS needs a common time '
             'index; zero on days a model does not trade). Range-statistic variant referenced '
             'to the current best model. The standing system is unchanged; MCS only arbitrates '
             'the challenger set.\n',
             f'Days in the common index: {len(idx)} '
             f'({idx.min().date()} to {idx.max().date()}).\n',
             '| Model | Avg daily net pips | MCS outcome |\n|---|---|---|']
    for n in names:
        oc = 'SURVIVES' if n in survivors else 'eliminated'
        lines.append(f'| {n} | {avg[n]:+.3f} | {oc} |')
    lines.append('\nElimination steps (model, t, 80% critical value):')
    for e in log:
        if e[0] is None:
            lines.append(f'- stop: max t {e[1]:.2f} <= crit {e[2]:.2f} — no further elimination')
        else:
            lines.append(f'- eliminated {e[0]}: t {e[1]:.2f} > crit {e[2]:.2f}')
    lines.append(f'\n**MCS survivor set: {", ".join(survivors)}**\n')
    lines += extra(survivors, avg)
    open(f'{OUT}/{month.lower()}.md', 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    print(month.upper(), 'DONE')


C98 = '/home/hatch/workspace/fx/work_c98/results/logs'
C104 = '/home/hatch/workspace/fx/work_c104/results/logs'
C115 = '/home/hatch/workspace/fx/work_c115/results/logs'

if __name__ == '__main__':
    which = sys.argv[1]
    if which == 'mar':
        ch = {
            'R22 (C98 rank 19)': (f'{C98}/proc_019_disc.csv', f'{C98}/proc_019_unseen.csv'),
            'N071 (C98 rank 78)': (f'{C98}/proc_078_disc.csv', f'{C98}/proc_078_unseen.csv'),
            'X28 (C98 rank 41)': (f'{C98}/proc_041_disc.csv', f'{C98}/proc_041_unseen.csv'),
            'X36 (C98 rank 49)': (f'{C98}/proc_049_disc.csv', f'{C98}/proc_049_unseen.csv'),
        }

        def extra(survivors, avg):
            chal_surv = [s for s in survivors if 'incumbent' not in s]
            return ['## Verdict: NOT\n',
                    'One-line reason: survivor set = '
                    + (', '.join(survivors))
                    + '. No surviving challenger can be promoted under the standing rules: '
                      'R22 (the only challenger with a leftover gain, 80.30%) carries LCT '
                      'P 6.11% from Cycle 98 — the MCS arbitrates the set but cannot repair '
                      'March\'s documented selection problem (PBO HIGH), and no challenger '
                      'meets the leftover + win + frequency + LCT gates together.']
        run('Mar', ch, '', extra)
    else:
        ch = {
            'R20 (C104)': (f'{C104}/proc_013_disc.csv', f'{C104}/proc_013_unseen.csv'),
            'PB23 (C115)': (f'{C115}/proc_020_PB23_disc.csv', f'{C115}/proc_020_PB23_audit.csv'),
            'PB21 (C115)': (f'{C115}/proc_018_PB21_disc.csv', f'{C115}/proc_018_PB21_audit.csv'),
        }

        def extra(survivors, avg):
            return ['## Verdict: NOT\n',
                    'One-line reason: survivor set = '
                    + (', '.join(survivors))
                    + '. No surviving challenger can be promoted under the standing rules: '
                      'R20\'s LCT P was 2.12% (Cycle 104), PB23\'s 77.39% and PB21\'s 60.06% '
                      '(Cycle 115) — all below the LCT-middle bar (P ≥ 80%), so the MCS '
                      'changes no decision for December; C94-23 stands.']
        run('Dec', ch, '', extra)
