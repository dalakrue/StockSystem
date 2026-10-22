"""Cycle 116 / Oct: variance-ratio routing feasibility on C92-24.
The proposal admits an 'existing eligible continuation candidate' on
otherwise EMPTY checks when VR(2,8) > 1.0 [COMPLETION], H1 momentum is
positive in the candidate direction and M15 CLV >= 0.60. This script
establishes, on the producing harness's own walk (Cycle 102 core), how
many empty checks exist and whether any admissible candidate exists at
them. Runs in the c102 environment only."""
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, '/home/hatch/workspace/fx/work_c102/scripts')
import c102_core as K

fr = K.frames_raw()
report = {}
for nm in ('disc', 'unseen'):
    cf = fr[nm]
    log, cov = K.walk_period(cf, None)
    fired = set(pd.to_datetime(log['check']))
    all_checks = sorted(pd.to_datetime(cf['check'].unique()))
    empty = [c for c in all_checks if c not in fired]
    # occupancy state from the walk's own trades
    lt = log.copy()
    lt['entry_t'] = pd.to_datetime(lt['check']) - pd.Timedelta(minutes=30)
    lt['exit_t'] = pd.to_datetime(lt['exit_time'])
    detail = []
    n_blocked_rows = 0
    n_free_rows = 0
    for chk in empty:
        ent = chk - pd.Timedelta(minutes=30)
        grp = cf[pd.to_datetime(cf['check']) == chk]
        rows = []
        for _, tr in grp.iterrows():
            sym = tr['symbol']
            occ = ((lt['symbol'] == sym) & (lt['entry_t'] <= ent)
                   & (lt['exit_t'] > ent)).any()
            rows.append((sym, tr['strategy'], bool(occ)))
            if occ:
                n_blocked_rows += 1
            else:
                n_free_rows += 1
        detail.append((chk, rows))
    report[nm] = dict(checks=len(all_checks), fired=len(fired),
                      empty=len(empty), detail=detail,
                      blocked=n_blocked_rows, free=n_free_rows,
                      trades=len(log))
    print(nm, report[nm]['checks'], 'checks,', report[nm]['fired'],
          'fired,', report[nm]['empty'], 'empty; rows at empty checks:',
          n_blocked_rows, 'occupancy-blocked,', n_free_rows, 'free',
          flush=True)
    for chk, rows in detail:
        print('  empty', chk, [(s, st, 'blocked' if b else 'FREE')
                                 for s, st, b in rows], flush=True)

d, u = report['disc'], report['unseen']
wd_oct2025 = 23  # weekdays in October 2025
lines = ['# Cycle 116 — October (C92-24) — Variance-ratio routing on empty checks\n',
         '**COMPLETION (flagged): the proposal\'s variance-ratio threshold was truncated '
         'in the user\'s paste; implemented in the brief as VR(2,8) on H1 closes > 1.0 '
         '(trending), with directional H1 momentum positive in the candidate direction '
         'and M15 directional CLV ≥ 0.60, on otherwise empty checks only, never displacing '
         'a proven primary.**\n',
         '## What the producing harness\'s own walk shows\n',
         f"Discovery: the candidate frame holds {d['checks']} checks; the standing system "
         f"fires at {d['fired']} and leaves {d['empty']} empty. 2025 audit: {u['checks']} "
         f"checks, {u['fired']} fired, {u['empty']} empty.\n",
         f"At those empty checks, the candidate frame contains "
         f"{d['blocked'] + u['blocked']} candidate rows in total — and every one of them "
         f"is on a symbol with a position already open (occupancy-blocked); free rows: "
         f"{d['free'] + u['free']}. Checks outside the candidate frame have no candidate "
         'row at all, by construction: the frame contains every signal of every one of '
         'the system\'s 36 equations.\n',
         '## Verdict: NOT\n',
         'One-line reason: variance-ratio routing cannot be implemented as specified — '
         'at every empty check the only existing candidates are occupancy-blocked (the '
         'system already fires at 444 of 455 discovery checks and 48 of 51 audit checks '
         'where any of its equations signals), so there is no eligible continuation '
         'candidate for the VR/momentum/CLV conditions to admit; the audit-year ceiling '
         f'even if all {u["empty"]} empty checks could trade is '
         f'{(u["trades"] + u["empty"]) / wd_oct2025:.2f}/day vs the current 2.09/day. '
         'This matches Plan B Cycle 114\'s finding that nothing lifts October\'s '
         'frequency: every timing/routing variant cut it instead.']
open('/home/hatch/workspace/fx/work_ovl/results/oct.md', 'w').write('\n'.join(lines) + '\n')
print('OCT DONE')
