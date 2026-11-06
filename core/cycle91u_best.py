"""Cycle cycleR4sep -- sep: PATH-FIX ROUND 4
winner C05 (buildable-universe programme,
work_rr1_pathfix_r17/GATES.md). Construction, stage for
stage as graded (research record:
work_rr1_pathfix_r4/results/sep_grade.json):

  base = KW over the incumbent lineage
  panel surface (module-provenance rows only; fill /
  mined-supply rows are not part of the surface),
  restricted to check hours [1, 11, 18] UTC;
  unions = ['admG:0.58:6:-1']; fitted excisions
  (DISCOVERY-fitted, frozen as constants below):
  [{'kind': 'wkx', 'k': 6, 'fit': [[2020, 36], [2019, 40], [2021, 35], [2023, 38], [2023, 36], [2021, 36]]}]; windowed week repair = True;
  sequential rules = [['maxopen', 26]]; exposure skip
  = 0.082. Every delivered pick's stop is
  capped at 1 x TP (the 1:1 law); outcomes on the
  path basis (M15 High/Low walk, first touch,
  same-bar -> stop).

Gate A: apply_chain below, run over the canonical
pool build, reproduces the research stream
BIT-EXACTLY (validation record in the round's
validate/sep/VALIDATION.md). Live feeding follows
the shipped transform-form pattern (as cycle87j):
at each check the candidate group is the incumbent
lineage panel surface; base_keep is settled by
stepping a private incumbent form instance; the
form keeps the full surface snapshot and re-runs
this verified array chain over it (the chain is
causal, so the current check's decisions equal the
research replay). The per-lineage surface plumbing
is wired on this skeleton at install; apply_chain
and the constants are the verified core.


INSTALL (2026-11-06): wired live as cycle91u, replacing cycle91t
(VALIDATED under the LOWERED STANDARD, user order 2026-11-06;
validation record work_rr1_newcombo_r4/validate/sep/VALIDATION.md).
The apply_chain core and constants below are the Gate-A skeleton
verbatim; the live-feeding form at the bottom of this file wires
it to the cycle91r panel surface (see the wiring note there).
Check hours CHANGE: (1, 11, 18) UTC, dropping the 02 UTC check.
"""

from __future__ import annotations

import datetime as _dt

import numpy as np

from core import rr1val_lib as _V

SYSTEM_NAME = "cycle91u"
CYCLE91U_CHECK_HOURS = (1, 11, 18)
CHECK_HOURS = (1, 11, 18)
MAX_HOLD = 48
N_CARRIED = 83.0
N_USED = N_CARRIED / 3.0
EC22_MONTH = 9
BASE_KIND = "KW"
BASE_CELLS60 = []
ADM60_CELLS = []
ADM70_CELLS = []
ADM60S_CELLS = []
ADM60Z_CELLS = []
BASE_CELLS65 = []
ADM65_CELLS = []
ADM60Z20_CELLS = []
PRE = []
BASE_GEN_CELLS = []
ADM_GEN_CELLS = {'admG:0.58:6:-1': [['CADCHF', 18], ['CADJPY', 11], ['CHFJPY', 1], ['EURAUD', 18], ['EURUSD', 18], ['GBPAUD', 1], ['GBPNZD', 1], ['NZDCAD', 11], ['NZDCAD', 18]]}
ADM70Z_CELLS = []
UNIONS = ['admG:0.58:6:-1']
EXCISE = [{'kind': 'wkx', 'k': 6, 'fit': [[2020, 36], [2019, 40], [2021, 35], [2023, 38], [2023, 36], [2021, 36]]}]
WINREP = True
RULES = [['maxopen', 26]]
SKIP_FRAC = 0.082


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


def is_cycle91u_check_time(ts) -> bool:
    import pandas as pd
    t = pd.Timestamp(ts)
    return t.hour in CHECK_HOURS and t.minute == 30



# ------------------------------------------------------------------
# Live feeding (install wiring, 2026-11-06): the transform-form
# pattern of cycle91t / cycle78f / cycle87j. At each check the
# form takes the cycle91r panel entries (which step the 91r
# OfficeAlt state -- after this install nothing else steps it;
# this form REPLACES cycle91t, whose state is not stepped),
# converts them to stream rows and re-runs the verified array
# chain above over the accumulated snapshot (the chain is
# causal, so the current check's decisions equal the research
# replay).
#
# Row fields for apply_chain:
#   base_keep   -- True for every surface row: on the canonical
#                  pool the incumbent stream IS the surface
#                  (laneEXT keep_base = all rows, pool
#                  keep_base sum 596 of 596).
#   winner_keep -- the KW reference set: the pool's keep_winner,
#                  i.e. the RR 1:1 winner chain R12C13 -> R18C02
#                  over the 91r stream -- which is EXACTLY the
#                  shipped cycle91t chain. Verified on the
#                  canonical pool: cycle91t.apply_chain over the
#                  pool rows reproduces keep_winner BIT-EXACTLY
#                  (442 kept, 0 differing rows), so _winner_keep
#                  below is the pool field itself, produced live
#                  by the incumbent module's own verified chain
#                  (a pure function -- the 91t form state is
#                  never stepped).
#   pout        -- the cap1 (1:1) outcome of the row, computed in
#                  _lrow exactly as cycle91t computes fout
#                  (stop_tighten_arr at min(sl, tp)).
#   is_fill / office -- False for every surface row (pool sums:
#                  is_fill 0, office 0).
#
# Check hours CHANGE with this install: the form's grid is
# (1, 11, 18) UTC = 07:30 / 17:30 / 00:30 MMT; the 91r/91t grid's
# 02 UTC (08:30 MMT) check is dropped. panel_entries is only
# called at this form's check times, so the 91r state is never
# stepped at 02 UTC under this form (the hour-dropping install
# pattern, as cycle91r itself dropped the 10 UTC slot).
# ------------------------------------------------------------------

import os

import pandas as pd

import core.cycle91r_best as _c91r
import core.cycle91t_best as _c91t
import core.cycle93w_best as _c93w
from core import d21rc_lib as _L


def _state_path():
    from core.new8_candidate import default_state_path
    return default_state_path(SYSTEM_NAME)


def _winner_keep(rows):
    """The KW reference keep over the accumulated snapshot:
    the shipped cycle91t chain (see the wiring note above)."""
    if not rows:
        return np.zeros(0, bool)
    return np.asarray(_c91t.apply_chain(rows), bool)


class _Form91U:
    """The cycle91r panel stream settled through the
    new-combo R4 C05 chain. Persisted: the stream snapshot
    (scalar rows), the delivered ledger and the processed
    checks."""

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
                for k in ('check', 'entry_time', 'exit_time'):
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

    def _lrow(self, r, m15_frames):
        chk = pd.Timestamp(r['check'])
        entry_t = pd.Timestamp(r.get('entry_candle')
                               ) if r.get('entry_candle') is not None \
            else chk - pd.Timedelta(minutes=30)
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
            entry_px = float(bars[1][min(j, len(ts_arr) - 1)])
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
        return {'entry_s': entry_s, 'exit_s': exit_s,
                'sym': sym,
                'side': 1 if dirsign > 0 else -1,
                'net': float(net),
                'pwv': float(prof.min()) if len(prof) else 0.0,
                'pv': float(pv), 'tp': tp, 'sl': sl,
                'fout': fout}

    def step(self, frames, check_time_utc, m15_frames,
             open_symbols=()):
        chk = pd.Timestamp(check_time_utc)
        if str(chk) in self.processed:
            return [r for r in self.delivered
                    if pd.Timestamp(r['check']) == chk]
        entries = _c91r.panel_entries(
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
                new_rows.append(self._lrow(dd, m15_frames))
                payloads.append(dd)
        self.rows.extend(new_rows)
        wk = _winner_keep(self.rows)
        chain_rows = []
        for i, r in enumerate(self.rows):
            cr = dict(r)
            cr['pout'] = r['fout']
            cr['base_keep'] = True
            cr['winner_keep'] = bool(wk[i])
            cr['is_fill'] = False
            cr['office'] = False
            chain_rows.append(cr)
        keep = apply_chain(chain_rows)
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
        _STATE = _Form91U()
    return _STATE


def load_91u_state(path=None):
    if path is not None:
        return _Form91U(path=path)
    return _state()


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
    """The delivered cycle91u stream."""
    return [dict(r) for r in _state().delivered]


def fetch_cycle91u_m15_frames(state=None):
    return _c91r.fetch_cycle91r_m15_frames(state)


def evaluate_cycle91u_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc, m15_frames)


def select_cycle91u_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    if signals is None or not len(signals):
        return signals
    return signals
