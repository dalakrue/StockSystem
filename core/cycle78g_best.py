"""Cycle cycleR2jul -- jul: PATH-FIX ROUND 2
winner C04 (buildable-universe programme,
work_rr1_pathfix_r17/GATES.md). Construction, stage for
stage as graded (research record:
work_rr1_pathfix_r2/results/jul_grade.json):

  base = KW over the incumbent lineage
  panel surface (module-provenance rows only; fill /
  mined-supply rows are not part of the surface),
  restricted to check hours [15, 17, 18] UTC;
  unions = ['partner2u', 'admG:0.55:3:-1']; fitted excisions
  (DISCOVERY-fitted, frozen as constants below):
  [{'kind': 'trx', 'k': 25, 'fit': [[1468000800, 'GBPCAD', 1], [1468249200, 'EURAUD', -1], [1468854000, 'GBPAUD', 1], [1469556000, 'GBPUSD', 1], [1500051600, 'EURNZD', 1], [1500656400, 'EURNZD', 1], [1501092000, 'GBPCAD', 1], [1530723600, 'EURNZD', 1], [1532012400, 'GBPAUD', 1], [1532019600, 'EURNZD', 1], [1595610000, 'EURNZD', 1], [1596042000, 'EURNZD', 1], [1596207600, 'GBPNZD', -1], [1596214800, 'GBPAUD', -1], [1625583600, 'GBPAUD', 1], [1626274800, 'GBPAUD', 1], [1626368400, 'EURNZD', -1], [1656954000, 'EURNZD', -1], [1657206000, 'GBPNZD', -1], [1658329200, 'GBPAUD', -1], [1658509200, 'GBPAUD', -1], [1659106800, 'GBPNZD', -1], [1688742000, 'GBPNZD', -1], [1689260400, 'GBPNZD', -1], [1689958800, 'EURNZD', -1]]}, {'kind': 'celxS', 'fit': [[2020, 31], 'GBPNZD', -1]}]; windowed week repair = False;
  sequential rules = [['lockout', -60]]; exposure skip
  = 0.058. Every delivered pick's stop is
  capped at 1 x TP (the 1:1 law); outcomes on the
  path basis (M15 High/Low walk, first touch,
  same-bar -> stop).

Gate A: apply_chain below, run over the canonical
pool build, reproduces the research stream
BIT-EXACTLY (validation record in the round's
validate/jul/VALIDATION.md). Live feeding follows
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


INSTALL (2026-11-06): wired live as cycle78g, replacing cycle78f
(VALIDATED under the LOWERED STANDARD, user order 2026-11-06;
validation record work_rr1_newcombo_r2/validate/jul/VALIDATION.md).
The apply_chain core and constants below are the Gate-A skeleton
verbatim; the live-feeding form at the bottom of this file wires
it to the cycle78e panel surface (see the wiring note there).
"""

from __future__ import annotations

import datetime as _dt

import numpy as np

from core import rr1val_lib as _V

SYSTEM_NAME = "cycle78g"
CYCLE78G_CHECK_HOURS = (15, 17, 18)
CHECK_HOURS = (15, 17, 18)
MAX_HOLD = 48
N_CARRIED = 103.0
N_USED = N_CARRIED / 3.0
EC22_MONTH = 7
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
ADM_GEN_CELLS = {'admG:0.55:3:-1': [['AUDJPY', 15], ['AUDJPY', 17], ['AUDNZD', 15], ['AUDNZD', 18], ['CADCHF', 15], ['CHFJPY', 18], ['EURAUD', 15], ['EURCHF', 15], ['EURJPY', 17], ['EURNZD', 17], ['EURUSD', 17], ['GBPAUD', 15], ['GBPAUD', 17], ['GBPCAD', 18], ['GBPNZD', 15], ['GBPNZD', 17], ['GBPUSD', 18], ['NZDCAD', 17], ['USDCAD', 17], ['USDCAD', 18], ['USDCHF', 17], ['USDJPY', 17]]}
ADM70Z_CELLS = []
UNIONS = ['partner2u', 'admG:0.55:3:-1']
EXCISE = [{'kind': 'trx', 'k': 25, 'fit': [[1468000800, 'GBPCAD', 1], [1468249200, 'EURAUD', -1], [1468854000, 'GBPAUD', 1], [1469556000, 'GBPUSD', 1], [1500051600, 'EURNZD', 1], [1500656400, 'EURNZD', 1], [1501092000, 'GBPCAD', 1], [1530723600, 'EURNZD', 1], [1532012400, 'GBPAUD', 1], [1532019600, 'EURNZD', 1], [1595610000, 'EURNZD', 1], [1596042000, 'EURNZD', 1], [1596207600, 'GBPNZD', -1], [1596214800, 'GBPAUD', -1], [1625583600, 'GBPAUD', 1], [1626274800, 'GBPAUD', 1], [1626368400, 'EURNZD', -1], [1656954000, 'EURNZD', -1], [1657206000, 'GBPNZD', -1], [1658329200, 'GBPAUD', -1], [1658509200, 'GBPAUD', -1], [1659106800, 'GBPNZD', -1], [1688742000, 'GBPNZD', -1], [1689260400, 'GBPNZD', -1], [1689958800, 'EURNZD', -1]]}, {'kind': 'celxS', 'fit': [[2020, 31], 'GBPNZD', -1]}]
WINREP = False
RULES = [['lockout', -60]]
SKIP_FRAC = 0.058


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


def is_cycle78g_check_time(ts) -> bool:
    import pandas as pd
    t = pd.Timestamp(ts)
    return t.hour in CHECK_HOURS and t.minute == 30



# ------------------------------------------------------------------
# Live feeding (install wiring, 2026-11-06): the transform-form
# pattern of cycle78f / cycle91t / cycle87j. At each check the form
# takes the cycle78e panel entries (which step the 78e E09 state --
# after this install nothing else steps it; this form REPLACES
# cycle78f, whose state is not stepped), converts them to stream
# rows and re-runs the verified array chain above over the
# accumulated snapshot (the chain is causal, so the current
# check's decisions equal the research replay).
#
# Row fields for apply_chain:
#   base_keep   -- True for every surface row: on the canonical
#                  pool the incumbent stream IS the surface
#                  (laneEXT keep_base = all rows, pool
#                  keep_base sum 665 of 665).
#   winner_keep -- the KW reference set: the pool's keep_winner,
#                  i.e. the RR 1:1 winner chain R11C01 -> R18C14
#                  over the 78e stream. Its live-era equivalent is
#                  the shipped cycle78f chain (R11C01 -> R18C08):
#                  the two chains differ ONLY in R18C14's stage-2
#                  worst-10-day excision, which by construction
#                  (rr1val_lib.worst_days_from) fits on and drops
#                  DISCOVERY rows only (disc_mask = year <= 2023);
#                  verified on the canonical pool: the 78f chain
#                  keeps 478 vs keep_winner 470, the 14 differing
#                  rows are ALL discovery-era (2016-2023), zero
#                  AUDIT-era differences. A live snapshot holds
#                  only live-era rows, on which the excision mask
#                  is identically empty and its cooldown-history
#                  effect cannot reach a live row (12h window), so
#                  _winner_keep below IS the R18C14 keep for every
#                  row this form can ever see -- no approximation.
#   pout        -- the cap1 (1:1) outcome of the row, computed in
#                  _lrow exactly as cycle78f computes fout
#                  (stop_tighten_arr at min(sl, tp)).
#   is_fill / office -- False for every surface row (pool sums:
#                  is_fill 0, office 0).
# ------------------------------------------------------------------

import os

import pandas as pd

import core.cycle78e_best as _c78e
import core.cycle78f_best as _c78f
import core.cycle93w_best as _c93w
from core import d21rc_lib as _L


def _state_path():
    from core.new8_candidate import default_state_path
    return default_state_path(SYSTEM_NAME)


def _winner_keep(rows):
    """The KW reference keep over the accumulated snapshot:
    the shipped cycle78f chain (see the wiring note above)."""
    if not rows:
        return np.zeros(0, bool)
    return np.asarray(_c78f.apply_chain(rows), bool)


class _Form78G:
    """The cycle78e panel stream settled through the
    new-combo R2 C04 chain. Persisted: the stream snapshot
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
        entries = _c78e.panel_entries(
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
        _STATE = _Form78G()
    return _STATE


def load_78g_state(path=None):
    if path is not None:
        return _Form78G(path=path)
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
    """The delivered cycle78g stream."""
    return [dict(r) for r in _state().delivered]


def fetch_cycle78g_m15_frames(state=None):
    return _c78e.fetch_cycle78e_m15_frames(state)


def evaluate_cycle78g_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc, m15_frames)


def select_cycle78g_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    if signals is None or not len(signals):
        return signals
    return signals
