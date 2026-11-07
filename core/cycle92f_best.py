"""Cycle 92F -- October: RR 1:1 NEW-COMBO
Round 1 winner C04 over the cycle92c stream surface
(KW base = the R18C12 winner set, produced live by
the shipped cycle92d chain kept below as _inc_chain;
adm60 union + trx15/wkx2 fitted excisions + lockout
-40 rule + exposure-skip 3.5%, stops capped at 1 x
TP). INSTALL 2026-11-07 (user order: app runs the
best VALIDATED RR 1:1 cycle per month): VALIDATED
under the FULL STANDARD (Round 1 was graded under
the full in-round standard; its only failing arm
was sizing), sizing arm re-graded under the
2026-11-07 live-rules sizing law (0.01 lots, 48h
cap, 1:1000; live candidate peak 2.04% vs live
incumbent peak 3.51%, delta -1.47 within the +2
full-standard tolerance); origin cycle: NC R1 C04
(the only FULL-standard validated October form --
it outranks every lowered-standard candidate).
It replaces cycle92d (the R18C12 composition
install). Path record (work_rr1_newcombo_r1
validate/oct/VALIDATION.md): DISC +2432.00 /
AUDIT +621.27 @2.5,
AUDIT win 87.10, Gate A bit-exact (kept 406, fill
0, office 0). Check hours (15, 17, 18 UTC) = 21:30
/ 23:30 / 00:30 MMT -- identical to cycle92d, no
job retiming. Sizing: carried N = 83, shipped at
N/3, unchanged. Live feeding: the cycle92d wiring
(cycle92c panel; base_keep True stream rows) with
the two-stage settlement described above;
OFFICE_HOURS carried as a tuple."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

import core.cycle92c_best as _c92c
import core.cycle93w_best as _c93w
from core import d21rc_lib as _L
from core import rr1val_lib as _V

SYSTEM_NAME = "cycle92f"
CYCLE92F_CHECK_HOURS = (15, 17, 18)
SURFACE_GRID = (15, 17, 18)
MAX_HOLD = 48
N_CARRIED = 83.0
N_USED3 = 27.666666666666668
REFHR = {15: 1003.8517857141721, 17: 1791.1188571427956, 18: 2010.3694999999443}
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
    """The proven R11C01 -> R18C12 chain over the October stream rows. Mirrors work_rr1_validate/scripts/spec_oct.py; bit-exact vs the rounds' saved streams."""
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

    k1 = _V.exposure_skip(d, walk, 0.06, N_USED3,
                          prior=ref)
    k1 = hb(k1)
    k2 = _V.exposure_skip(d, walk, 0.04, N_USED3, prior=k1)
    keep = hb(k2)
    return keep


import datetime as _dt


CHECK_HOURS = (15, 17, 18)
N_USED = N_CARRIED / 3.0
EC22_MONTH = 10
BASE_KIND = "KW"
BASE_CELLS60 = []
ADM60_CELLS = [['AUDJPY', 17], ['AUDNZD', 18], ['CHFJPY', 18], ['EURCHF', 18], ['GBPJPY', 17], ['GBPJPY', 18], ['GBPNZD', 17], ['GBPNZD', 18], ['GBPUSD', 15], ['NZDCAD', 17], ['NZDCAD', 18], ['NZDCHF', 18]]
ADM70_CELLS = []
ADM60S_CELLS = []
ADM60Z_CELLS = []
BASE_CELLS65 = []
ADM65_CELLS = []
ADM60Z20_CELLS = []
PRE = []
ADM70Z_CELLS = []
UNIONS = ['adm60']
EXCISE = [{'kind': 'trx', 'k': 15, 'fit': [[1476378000, 'GBPNZD', -1], [1476468000, 'CHFJPY', -1], [1476810000, 'GBPNZD', -1], [1539280800, 'CHFJPY', -1], [1539799200, 'GBPNZD', -1], [1541008800, 'GBPNZD', -1], [1570208400, 'GBPNZD', -1], [1633539600, 'GBPNZD', -1], [1634839200, 'CHFJPY', -1], [1666803600, 'EURJPY', 1], [1666976400, 'GBPJPY', -1], [1696266000, 'GBPNZD', -1], [1696356000, 'GBPNZD', -1], [1697209200, 'EURCAD', -1], [1698256800, 'CHFJPY', -1]]}, {'kind': 'wkx', 'k': 2, 'fit': [[2023, 41], [2020, 41]]}]
WINREP = False
RULES = [['lockout', -40]]
SKIP_FRAC = 0.035


def _cellmask(sym_a, hr_a, cells):
    cs = {(s, h) for s, h in cells}
    return np.array([(str(s), int(h)) in cs
                     for s, h in zip(sym_a, hr_a)])


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
    if BASE_KIND == 'KB':
        cur = KBH.copy()
    elif BASE_KIND == 'KW':
        cur = KWH.copy()
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
        elif u == 'adm65':
            cur = cur | (UH & _cellmask(sym, hr,
                                        ADM65_CELLS))
        elif u == 'adm60z20':
            cur = cur | (UH & _cellmask(sym, hr,
                                        ADM60Z20_CELLS))
        elif u == 'adm70z':
            cur = cur | (UH & _cellmask(sym, hr,
                                        ADM70Z_CELLS))
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
        entries = _c92c.panel_entries(
            frames, check_time_utc, m15_frames=m15_frames,
            open_symbols=open_symbols)
        if entries is not None \
                and entries.attrs.get('status'):
            return entries
        new_rows, payloads = [], []
        if entries is not None and len(entries):
            for _, r in entries.iterrows():
                dd = dict(r)
                dd.setdefault('check', chk)
                new_rows.append(self._lrow(dd, m15_frames,
                                           True))
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


def is_cycle92f_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE92F_CHECK_HOURS and t.minute == 30


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
    """The delivered cycle92f stream."""
    return [dict(r) for r in _state().delivered]


def fetch_cycle92f_m15_frames(state=None):
    from core.cycle89_best import fetch_cycle89_m15_frames
    return fetch_cycle89_m15_frames()


def evaluate_cycle92f_signals(frames: dict, check_time_utc,
                               m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc, m15_frames)


def select_cycle92f_entries(signals: pd.DataFrame,
                             open_symbols=()) -> pd.DataFrame:
    if signals is None or not len(signals):
        return signals
    return signals
