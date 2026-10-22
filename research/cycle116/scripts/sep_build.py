"""Cycle 116 / Sep build stage — runs ONLY in the c91 environment
(importing the ovl/c104 modules in the same process corrupts the c91
harness through sys.path/module collisions). Reads the HMM filtered
probabilities from the ovl cache pickle, builds OFF (standing C91-15)
and ON (HMM regime-persistence order_fn bonus) logs, dumps both to CSV.
"""
import pickle
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, '/home/hatch/workspace/fx/work_c91/scripts')
import c91_lib as K
import designs91 as Dz

with open('/home/hatch/workspace/fx/work_ovl/cache/hmm_sep.pkl', 'rb') as f:
    HMM = pickle.load(f)
PROBS = HMM['probs']
PARAMS = HMM['params']


def persistent(sym, chk):
    P = PROBS[sym]
    ent = pd.Timestamp(chk) - pd.Timedelta(minutes=30)
    i = P.index.searchsorted(ent, side='right') - 1
    if i < 1:
        return False
    a = P.iloc[i].to_numpy(float)
    b = P.iloc[i - 1].to_numpy(float)
    return bool(a.max() >= 0.70 and b.max() >= 0.70
                and a.argmax() == b.argmax())


COUNT = [0]


def order_fn(chk, grp):
    key = grp['eff'].to_numpy(float).copy()
    syms = grp['symbol'].to_numpy()
    for j in range(len(grp)):
        if persistent(syms[j], chk):
            key[j] += 400.0
            COUNT[0] += 1
    return list(np.argsort(-key, kind='stable'))


def build(order):
    cands = K.get_cands()
    eqs = Dz.eqs_without(Dz.FB_H1)
    tw = Dz.TWEAKS['X30B']
    out = {}
    for gname in ('d', 'u'):
        picks = K.walk(cands, gname, eqs=eqs, bonus=400.0, order_fn=order)
        log, _ = K.resim_log(picks, tw)
        out[gname] = log
    return out


off = build(None)
on = build(order_fn)
base = '/home/hatch/workspace/fx/work_ovl/cache'
off['d'].to_csv(f'{base}/sep_off_disc.csv', index=False)
off['u'].to_csv(f'{base}/sep_off_audit.csv', index=False)
on['d'].to_csv(f'{base}/sep_on_disc.csv', index=False)
on['u'].to_csv(f'{base}/sep_on_audit.csv', index=False)
print('bonus rows awarded:', COUNT[0])
print('A:', np.round(PARAMS['A'], 3).tolist())
print('mu:', np.round(PARAMS['mu'], 2).tolist())
print('off trades:', len(off['d']), len(off['u']),
      'on trades:', len(on['d']), len(on['u']))
