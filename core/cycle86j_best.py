"""Cycle 86J -- March: RR 1:1 4-month lane (TRI)
Round 2 winner C02 over the incumbent lineage panel
surface (KW base = the cycle86i winner set, produced
live by the shipped cycle86i chain kept below as
_inc_chain; unions h1a h1mom 0.55 + m15a m15mom 0.55
+ m5a mom 0.55 + adm60; fitted excisions tfx
(m15vol bucket 1) + m5x (aln bucket 0), DISCOVERY-only;
stops capped at 1 x TP). INSTALL 2026-11-07 (user
order: "Install March C02 now as-is"): VALIDATED
under the LOWERED STANDARD -- battery failed
{13_lct, 14_leftover, 16_win, 20_dsr} at full
thresholds, PASS under the lowered standard; S9 mc9
PASS (P_profit 1.0, DD p95 66.88); Gate A bit-exact
(kept 378, fill 0, office 0). SIZING NOT GRADED --
the TRI lane ran under the user's no-sizing order
(2026-11-07) and the install is as-is: no sizing
number is claimed for this form. It replaces
cycle86i (the R19C03 NEAREST composition install).
Path record (work_rr1_4mo_r2/validate/mar/
VALIDATION.md + validation.json): AUDIT net +220.90
@2.5 (path basis, M5 walk), AUDIT epd 2.15, win
70.24, DSR 0.5622, PBO 0.0%. Check hours
(11, 16, 17 UTC) = 17:30 / 22:30 / 23:30 MMT --
CHANGED vs cycle86i (the 18:30 MMT / 12 UTC check
is dropped; exactly-3-checks form). Sizing: carried
N = 86, shipped at N/3, unchanged. Live feeding: the
cycle86i wiring (cycle86c panel + private cycle86h
reference form) with the two-stage settlement;
OFFICE_HOURS carried as a tuple (the 86i copy's str
form is a TypeError on first _lrow); transform rows
carry the b_* bucket fields as constant 0 -- the
chain reads them only inside DISCOVERY-only
excisions, so the constant is decision-inert live
(pool proof: AUDIT segment identical under zeroed
buckets; see work_rr1_mar_install/PROOFS.json)."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

import core.cycle86c_best as _c86c
import core.cycle86h_best as _c86h
import core.cycle93w_best as _c93w
from core import d21rc_lib as _L
from core import rr1val_lib as _V

SYSTEM_NAME = "cycle86j"
CYCLE86J_CHECK_HOURS = (11, 16, 17)
SURFACE_GRID = (11, 16, 17)
MAX_HOLD = 48
N_CARRIED = 86.0
N_USED3 = 28.666666666666668
REFHR = {11: 1183.211071428534, 12: 36.42549999999994, 16: 1901.618214285709, 17: 808.4738571428497}
OFFICE_HOURS = ()


def _state_path():
    from core.new8_candidate import default_state_path
    return default_state_path(SYSTEM_NAME)


def _sidecar(name):
    from core.new8_candidate import default_state_path
    base = default_state_path(SYSTEM_NAME)
    return os.path.join(os.path.dirname(
        os.path.abspath(base)), name)


def _inc_chain(rows):
    """The proven R11C02 -> R19C03 chain over the March pool rows. Mirrors work_rr1_validate/scripts/spec_mar.py; bit-exact vs the rounds' saved streams."""
    n = len(rows)
    if n == 0:
        return np.zeros(0, bool)
    d = {'entry': np.array([r['entry_s'] for r in rows],
                           dtype=np.int64),
         'exit': np.array([r['exit_s'] for r in rows],
                          dtype=np.int64),
         'sym': np.array([r['sym'] for r in rows]),
         'side': np.array([r['side'] for r in rows],
                          dtype=np.int64),
         'net': np.array([r['net'] for r in rows]),
         'pv': np.array([r['pv'] for r in rows]),
         'pwv': np.array([r['pwv'] for r in rows]),
         'prof': [np.zeros(0) for _ in rows]}
    entry = d['entry']
    hr = (entry % 86400) // 3600
    discm = np.array([r['year'] for r in rows]) <= 2023
    walk = d['net'].copy()
    fout = np.array([r['fout'] for r in rows])
    sl = np.array([r['sl'] for r in rows])
    tp = np.array([r['tp'] for r in rows])
    ref = np.array([r['base_keep'] for r in rows], bool)
    off = np.array([r['off'] for r in rows], bool)
    is_fill = np.array([r.get('is_fill', False)
                        for r in rows], bool)
    repl = ((~ref) & (~off) & np.isin(hr, [1, 18])) \
        | (is_fill & ~off)

    def hb(k):
        return _V.hour_balance(k, hr, REFHR, discm, walk,
                               repl)

    k1 = _V.exposure_skip(d, walk, 0.10, N_USED3,
                          prior=ref)
    k1 = hb(k1)
    wd5, _w = _V.worst_days_from(entry, k1, fout, discm, 5)
    wt3 = _V.worst_trades_from(k1, fout, discm, 3)
    k2 = k1 & ~wd5 & ~wt3
    keep = hb(k2)
    return keep


import datetime as _dt


CHECK_HOURS = (11, 16, 17)
N_USED = N_CARRIED / 3.0
EC22_MONTH = 3
BASE_KIND = "KW"
BASE_CELLS60 = []
ADM60_CELLS = [['AUDUSD', 16], ['CHFJPY', 11], ['CHFJPY', 16], ['EURCHF', 16], ['EURGBP', 16], ['NZDCHF', 16], ['USDCAD', 16], ['USDCHF', 11], ['USDJPY', 16]]
ADM70_CELLS = []
ADM60S_CELLS = []
ADM60Z_CELLS = []
BASE_CELLS65 = []
ADM65_CELLS = []
ADM60Z20_CELLS = []
PRE = []
BASE_GEN_CELLS = []
ADM_GEN_CELLS = {}
ADM70Z_CELLS = []
M5CELLS = {}
TFCELLS = {}
TFA_CELLS = {'h1a:h1mom:0:0.55': [['EURGBP', 16], ['EURNZD', 16], ['NZDCAD', 11], ['NZDCAD', 17], ['NZDUSD', 17]], 'm15a:m15mom:0:0.55': [['AUDNZD', 16], ['CHFJPY', 11], ['CHFJPY', 16], ['EURNZD', 16], ['USDCAD', 11], ['USDCHF', 11], ['USDJPY', 16]]}
M5A_CELLS = {'m5a:mom:0:0.55': [['AUDNZD', 16], ['CHFJPY', 11], ['CHFJPY', 16], ['EURNZD', 16], ['NZDUSD', 17], ['USDCAD', 16]]}
UNIONS = ['h1a:h1mom:0:0.55', 'm15a:m15mom:0:0.55', 'm5a:mom:0:0.55', 'adm60']
EXCISE = [{'kind': 'tfx', 'feat': 'm15vol', 'bucket': 1}, {'kind': 'm5x', 'feat': 'aln', 'bucket': 0}]
WINREP = False
RULES = []
SKIP_FRAC = 0.0


def _cellmask(sym_a, hr_a, cells):
    cs = {(s, h) for s, h in cells}
    return np.array([(str(s), int(h)) in cs
                     for s, h in zip(sym_a, hr_a)])


def _cellmask_m5(sym_a, hr_a, bk_a, cells):
    cs = {(s, h, b) for s, h, b in cells}
    return np.array([(str(s), int(h), int(b)) in cs
                     for s, h, b in zip(sym_a, hr_a, bk_a)])


def _cellmask3(sym_a, hr_a, side_a, cells):
    cs = {(s, h, sd) for s, h, sd in cells}
    return np.array([(str(s), int(h), int(sd)) in cs
                     for s, h, sd in zip(sym_a, hr_a,
                                         side_a)])


def _iso_weeks(entry_a):
    out = []
    for t in entry_a:
        iso = _dt.datetime.utcfromtimestamp(
            int(t)).isocalendar()
        out.append((iso[0], iso[1]))
    return out


def _maxopen(d, cap, prior):
    import heapq
    entry = d['entry']
    exit_ = d['exit']
    keep = np.zeros(len(entry), dtype=bool)
    opens = []
    for i in np.argsort(entry, kind='stable'):
        if not prior[i]:
            continue
        while opens and opens[0] <= entry[i]:
            heapq.heappop(opens)
        if len(opens) < cap:
            keep[i] = True
            heapq.heappush(opens, int(exit_[i]))
    return keep


def apply_chain(rows):
    """The verified chain over surface rows (dicts with
    entry_s/exit_s/sym/side/net/pv/pwv/pout/base_keep/
    is_fill/office). Returns the final keep mask."""
    n = len(rows)
    if n == 0:
        return np.zeros(0, bool)
    entry = np.array([r['entry_s'] for r in rows],
                     dtype=np.int64)
    exit_ = np.array([r['exit_s'] for r in rows],
                     dtype=np.int64)
    sym = np.array([r['sym'] for r in rows])
    side = np.array([r['side'] for r in rows],
                    dtype=np.int64)
    d = {'entry': entry, 'exit': exit_, 'sym': sym,
         'side': side,
         'net': np.array([r['net'] for r in rows]),
         'pv': np.array([r['pv'] for r in rows]),
         'pwv': np.array([r['pwv'] for r in rows])}
    pout = np.array([r['pout'] for r in rows])
    base_keep = np.array([r['base_keep'] for r in rows],
                         bool)
    winner_keep = np.array([r.get('winner_keep', False)
                            for r in rows], bool)
    is_fill = np.array([r.get('is_fill', False)
                        for r in rows], bool)
    office = np.array([r.get('office', False)
                       for r in rows], bool)
    years = np.array([_dt.datetime.utcfromtimestamp(
        int(t)).year for t in entry])
    discm = years <= 2023
    hr = (entry % 86400) // 3600
    U = ~is_fill & ~office
    inH = np.isin(hr, list(CHECK_HOURS))
    UH = U & inH
    KBH = base_keep & UH
    KWH = winner_keep & UH
    REF = KWH if BASE_KIND == 'KW' else KBH
    bk = {f: np.array([r['b_' + f] for r in rows],
                        dtype=np.int64)
           for f in ('mom', 'rng', 'vol', 'aln',
                     'h1mom', 'h1rng', 'h1aln',
                     'm15mom', 'm15rng', 'm15vol')}
    if BASE_KIND == 'KB':
        cur = KBH.copy()
    elif BASE_KIND == 'KW':
        cur = KWH.copy()
    elif BASE_KIND.startswith('H1C:') or             BASE_KIND.startswith('M15C:'):
        _p = BASE_KIND.split(':')
        cur = UH & _cellmask_m5(sym, hr, bk[_p[1]],
                                [tuple(c) for c in
                                 TFCELLS.get(BASE_KIND, [])])
    elif BASE_KIND.startswith('M5C:'):
        _p = BASE_KIND.split(':')
        cur = UH & _cellmask_m5(sym, hr, bk[_p[1]],
                                [tuple(c) for c in
                                 M5CELLS.get(BASE_KIND, [])])
    elif BASE_KIND.startswith('ADMG:'):
        cur = UH & _cellmask(sym, hr, BASE_GEN_CELLS)
    elif BASE_KIND == 'ADM65':
        cur = UH & _cellmask(sym, hr, BASE_CELLS65)
    else:
        cur = UH & _cellmask(sym, hr, BASE_CELLS60)
    for u in UNIONS:
        if u == 'partner1':
            cur = cur | (_V.partner_add(
                entry, side, REF, 1, False) & UH)
        elif u == 'partner2u':
            cur = cur | (_V.partner_add(
                entry, side, REF, 2, True) & UH)
        elif u == 'adm60':
            cur = cur | (UH & _cellmask(sym, hr,
                                        ADM60_CELLS))
        elif u == 'adm70':
            cur = cur | (UH & _cellmask(sym, hr,
                                        ADM70_CELLS))
        elif u == 'adm60s':
            cur = cur | (UH & _cellmask3(sym, hr, side,
                                         ADM60S_CELLS))
        elif u == 'adm60z':
            cur = cur | (UH & _cellmask(sym, hr,
                                        ADM60Z_CELLS))
        elif u.startswith('admG:'):
            cur = cur | (UH & _cellmask(
                sym, hr, [tuple(c) for c in
                          ADM_GEN_CELLS.get(u, [])]))
        elif u == 'adm65':
            cur = cur | (UH & _cellmask(sym, hr,
                                        ADM65_CELLS))
        elif u == 'adm60z20':
            cur = cur | (UH & _cellmask(sym, hr,
                                        ADM60Z20_CELLS))
        elif u == 'adm70z':
            cur = cur | (UH & _cellmask(sym, hr,
                                        ADM70Z_CELLS))
        elif u.startswith('h1c:') or u.startswith('m15c:'):
            _p = u.split(':')
            cur = cur | (UH & _cellmask_m5(
                sym, hr, bk[_p[1]],
                [tuple(c) for c in TFCELLS.get(u, [])]))
        elif u.startswith('h1a:') or u.startswith('m15a:'):
            cur = cur | (UH & _cellmask(
                sym, hr,
                [tuple(c) for c in TFA_CELLS.get(u, [])]))
        elif u.startswith('m5c:'):
            _p = u.split(':')
            cur = cur | (UH & _cellmask_m5(
                sym, hr, bk[_p[1]],
                [tuple(c) for c in M5CELLS.get(u, [])]))
        elif u.startswith('m5a:'):
            cur = cur | (UH & _cellmask(
                sym, hr,
                [tuple(c) for c in M5A_CELLS.get(u, [])]))
    for name, par in PRE:
        if name == 'loss_cooldown':
            cur = _V.loss_cooldown_cur(d, pout, par,
                                       prior=cur)
        elif name == 'cooldown':
            cur = _V.cooldown_prior(d, pout, par,
                                    prior=cur)
        elif name == 'lockout':
            cur = _V.lockout_prior(d, pout, par,
                                   prior=cur)
        elif name == 'daycap':
            cur = _V.daycap_prior(d, par, prior=cur)
        elif name.startswith('m5keep:'):
            _p = name.split(':')
            cur = cur & np.isin(
                bk[_p[1]], [int(x) for x in _p[2].split(',')])
        elif name.startswith('h1keep:') or                 name.startswith('m15keep:'):
            _p = name.split(':')
            cur = cur & np.isin(
                bk[_p[1]], [int(x) for x in _p[2].split(',')])
        elif name == 'cluster':
            cur = _V.cluster_skip(d, par, 'window',
                                  prior=cur)
        elif name == 'cluster_open':
            cur = _V.cluster_skip(d, par, 'open',
                                  prior=cur)
        elif name == 'daily_lockout':
            cur = _V.daily_lockout(d, pout, par,
                                   prior=cur)
        elif name == 'maxopen':
            cur = _maxopen(d, par, cur)
        elif name == 'wklock':
            cur = _V.week_lockout_seq(entry, pout, par, cur)
    _wk = None
    for ex in EXCISE:
        if ex['kind'] in ('wkx', 'celx', 'celxS') and _wk is None:
            _wk = _iso_weeks(entry)
        if ex['kind'] == 'wkx':
            wset = {tuple(w) for w in ex['fit']}
            drop = np.array([bool(cur[i]) and discm[i]
                             and pout[i] < 0
                             and _wk[i] in wset
                             for i in range(n)])
            cur = cur & ~drop
        elif ex['kind'] == 'dyx':
            day = entry // 86400
            dset = set(ex['fit'])
            drop = np.array([bool(cur[i]) and discm[i]
                             and pout[i] < 0
                             and int(day[i]) in dset
                             for i in range(n)])
            cur = cur & ~drop
        elif ex['kind'] == 'celx' and ex.get('fit'):
            cw = tuple(ex['fit'][0])
            cs = ex['fit'][1]
            drop = np.array([bool(cur[i]) and discm[i]
                             and pout[i] < 0
                             and _wk[i] == cw
                             and str(sym[i]) == cs
                             for i in range(n)])
            cur = cur & ~drop
        elif ex['kind'] == 'celx2':
            cur = cur & ~(discm & _cellmask(
                sym, hr, [tuple(c) for c in ex['fit']]))
        elif ex['kind'] == 'tfx' and ex.get('bucket') is not None:
            drop = np.array([bool(cur[i]) and discm[i]
                             and pout[i] < 0
                             and int(bk[ex['feat']][i])
                             == int(ex['bucket'])
                             for i in range(n)])
            cur = cur & ~drop
        elif ex['kind'] == 'm5x' and ex.get('bucket') is not None:
            drop = np.array([bool(cur[i]) and discm[i]
                             and pout[i] < 0
                             and int(bk[ex['feat']][i])
                             == int(ex['bucket'])
                             for i in range(n)])
            cur = cur & ~drop
        elif ex['kind'] == 'symx':
            cur = cur & ~np.isin(sym, list(ex['fit']))
        elif ex['kind'] == 'symx8':
            cur = cur & ~np.isin(sym, list(ex['fit']))
        elif ex['kind'] == 'celxS' and ex.get('fit'):
            cw = tuple(ex['fit'][0])
            cs = ex['fit'][1]
            cd = int(ex['fit'][2])
            drop = np.array([bool(cur[i]) and discm[i]
                             and pout[i] < 0
                             and _wk[i] == cw
                             and str(sym[i]) == cs
                             and int(side[i]) == cd
                             for i in range(n)])
            cur = cur & ~drop
        elif ex['kind'] == 'trx':
            ks = {(int(k[0]), str(k[1]), int(k[2]))
                  for k in ex['fit']}
            drop = np.array([bool(cur[i])
                             and (int(entry[i]),
                                  str(sym[i]),
                                  int(side[i])) in ks
                             for i in range(n)])
            cur = cur & ~drop
    if WINREP:
        cur = _V.windowed_week_repair(
            entry, exit_, cur, pout, discm, EC22_MONTH)
    for name, par in RULES:
        if name == 'loss_cooldown':
            cur = _V.loss_cooldown_cur(d, pout, par,
                                       prior=cur)
        elif name == 'cooldown':
            cur = _V.cooldown_prior(d, pout, par,
                                    prior=cur)
        elif name == 'lockout':
            cur = _V.lockout_prior(d, pout, par,
                                   prior=cur)
        elif name == 'daycap':
            cur = _V.daycap_prior(d, par, prior=cur)
        elif name.startswith('m5keep:'):
            _p = name.split(':')
            cur = cur & np.isin(
                bk[_p[1]], [int(x) for x in _p[2].split(',')])
        elif name.startswith('h1keep:') or                 name.startswith('m15keep:'):
            _p = name.split(':')
            cur = cur & np.isin(
                bk[_p[1]], [int(x) for x in _p[2].split(',')])
        elif name == 'cluster':
            cur = _V.cluster_skip(d, par, 'window',
                                  prior=cur)
        elif name == 'cluster_open':
            cur = _V.cluster_skip(d, par, 'open',
                                  prior=cur)
        elif name == 'daily_lockout':
            cur = _V.daily_lockout(d, pout, par,
                                   prior=cur)
        elif name == 'maxopen':
            cur = _maxopen(d, par, cur)
        elif name == 'wklock':
            cur = _V.week_lockout_seq(entry, pout, par, cur)
    if SKIP_FRAC:
        cur = _V.exposure_skip(d, pout, SKIP_FRAC,
                               N_USED, prior=cur)
    return cur & U


class _Form:
    """The surface stream settled through the verified
    chain. Persisted: the stream snapshot (scalar rows),
    the delivered ledger and the processed checks."""

    def __init__(self, path=None):
        self.path = path or _state_path()
        self.rows = []
        self.delivered = []
        self.processed = []
        self.inc = _c86h._Form86H(
            path=_sidecar('cycle86j_86h.json'))
        self._load()

    def _load(self):
        import json
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path) as fh:
                d = json.load(fh)
        except Exception:
            return
        self.rows = d.get('rows', [])
        self.processed = d.get('processed', [])
        out = []
        for r in d.get('delivered', []):
            r = dict(r)
            for k in ('check', 'entry_time', 'exit_time'):
                if r.get(k) is not None:
                    r[k] = pd.Timestamp(r[k])
            out.append(r)
        self.delivered = out

    def save(self):
        import json
        if not self.path:
            return
        os.makedirs(os.path.dirname(
            os.path.abspath(self.path)), exist_ok=True)

        def ser(rows):
            out = []
            for r in rows:
                dd = dict(r)
                for k in ('check', 'entry_time',
                          'exit_time'):
                    if dd.get(k) is not None:
                        dd[k] = pd.Timestamp(
                            dd[k]).isoformat()
                out.append(dd)
            return out
        with open(self.path, 'w') as fh:
            json.dump({'system': SYSTEM_NAME,
                       'rows': self.rows,
                       'delivered': ser(self.delivered),
                       'processed': self.processed}, fh)

    def _lrow(self, r, m15_frames, base_keep):
        chk = pd.Timestamp(r['check'])
        entry_t = pd.Timestamp(r.get('entry_candle')
                               ) if r.get('entry_candle') \
            is not None else chk - pd.Timedelta(
                minutes=30)
        entry_s = int(entry_t.value // 10 ** 9)
        exit_s = entry_s + MAX_HOLD * 3600
        sym = str(r['symbol'])
        bars = _c93w._bars(sym, m15_frames)
        dirsign = 1.0 if str(r['direction']).upper() \
            .startswith('B') else -1.0
        entry_px = float(r.get('entry_px') or 0.0)
        if not entry_px:
            ts_arr = bars[0]
            j = int(np.searchsorted(ts_arr, entry_s))
            entry_px = float(bars[1][min(j,
                                         len(ts_arr) - 1)])
        prof = _L.profile_for_sym(sym, entry_s, exit_s,
                                  entry_px, dirsign, bars)
        majors = {p: _c93w._bars(p, m15_frames)
                   for p in _L.MAJORS}
        pv = _L.pip_value_per_lot(
            sym, _L.rates_at(majors, exit_s))
        if r.get('gross_pips') is not None:
            net = float(r['gross_pips']) - _V.COST
        else:
            net = (float(prof[-1]) if len(prof) else 0.0)
        tp = float(r['tp_pips'])
        sl = float(r['sl_pips'])
        fout = float(_V.stop_tighten_arr(
            {'prof': [prof]}, np.array([min(sl, tp)]),
            np.array([net]))[0])
        hr = (entry_s % 86400) // 3600
        return {'entry_s': entry_s, 'exit_s': exit_s,
                 'sym': sym,
                 'side': 1 if dirsign > 0 else -1,
                 'net': float(net),
                 'pwv': float(prof.min())
                 if len(prof) else 0.0,
                 'pv': float(pv), 'tp': tp, 'sl': sl,
                 'fout': fout,
                 'base_keep': bool(base_keep),
                 'year': int(entry_t.year),
                 'off': bool(hr in OFFICE_HOURS),
                 'is_fill': False}

    def step(self, frames, check_time_utc, m15_frames,
             open_symbols=()):
        chk = pd.Timestamp(check_time_utc)
        if str(chk) in self.processed:
            return [r for r in self.delivered
                    if pd.Timestamp(r['check']) == chk]
        entries = _c86c.panel_entries(
            frames, check_time_utc, m15_frames=m15_frames,
            open_symbols=open_symbols)
        if entries is not None \
                and entries.attrs.get('status'):
            return entries
        inc_out = self.inc.step(frames, check_time_utc,
                                m15_frames,
                                open_symbols=open_symbols)
        if isinstance(inc_out, pd.DataFrame):
            return inc_out

        def key(r):
            return (str(r.get('symbol')),
                    str(r.get('direction')),
                    str(r.get('strategy')
                        or r.get('equation') or ''))
        delivered_keys = {key(r) for r in inc_out}
        new_rows, payloads = [], []
        if entries is not None and len(entries):
            for _, r in entries.iterrows():
                dd = dict(r)
                dd.setdefault('check', chk)
                new_rows.append(self._lrow(
                    dd, m15_frames,
                    key(dd) in delivered_keys))
                payloads.append(dd)
        self.rows.extend(new_rows)
        wk = _inc_chain(self.rows)
        trows = []
        for i, r in enumerate(self.rows):
            tr = dict(r)
            tr['pout'] = r['fout']
            tr['base_keep'] = True
            tr['winner_keep'] = bool(wk[i])
            tr['is_fill'] = False
            tr['office'] = bool(r.get('off', False))
            for _f in ('mom', 'rng', 'vol', 'aln',
                       'h1mom', 'h1rng', 'h1aln',
                       'm15mom', 'm15rng', 'm15vol'):
                tr['b_' + _f] = 0
            trows.append(tr)
        keep = apply_chain(trows)
        out = []
        n_old = len(self.rows) - len(new_rows)
        for j, dd in enumerate(payloads):
            if not keep[n_old + j]:
                continue
            dd['sl_pips'] = min(float(dd['sl_pips']),
                                float(dd['tp_pips']))
            dd['exit_time'] = pd.Timestamp(
                dd.get('entry_candle', chk)) \
                + pd.Timedelta(hours=MAX_HOLD)
            self.delivered.append(dd)
            out.append(dd)
        self.processed.append(str(chk))
        self.save()
        return out


_STATE = None


def _state():
    global _STATE
    if _STATE is None:
        _STATE = _Form()
    return _STATE


def load_state_form(path=None):
    if path is not None:
        return _Form(path=path)
    return _state()


def is_cycle86j_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE86J_CHECK_HOURS and t.minute == 30


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    form = _state()
    out = form.step(frames, check_time_utc, m15_frames,
                    open_symbols)
    if isinstance(out, pd.DataFrame):
        return out
    if not out:
        return pd.DataFrame()
    return pd.DataFrame(out)


def walk_ledger():
    """The delivered cycle86j stream."""
    return [dict(r) for r in _state().delivered]


def fetch_cycle86j_m15_frames(state=None):
    from core.cycle89_best import fetch_cycle89_m15_frames
    return fetch_cycle89_m15_frames()


def evaluate_cycle86j_signals(frames: dict, check_time_utc,
                               m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc, m15_frames)


def select_cycle86j_entries(signals: pd.DataFrame,
                             open_symbols=()) -> pd.DataFrame:
    if signals is None or not len(signals):
        return signals
    return signals
