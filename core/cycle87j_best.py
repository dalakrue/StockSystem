"""Cycle 87J -- April: the RR 1:1 programme's standing
best form (Rounds 11/18/20 chain R11C09 -> R18C01 ->
R20C09) over the shipped cycle87i stream (validation
record: work_rr1_validate/results/apr_VALIDATION.md --
VALIDATED under the main gates: EC22-middle no new
non-LCT failure vs 87i's own failed set {13_lct,
14_leftover}, S9 PASS, sizing no-regression, Amendment-1
chain no material regression):

  Stage 1 (R11C09): the 87i delivered stream settled
  through a 12h currency-sharing LOSS-COOLDOWN (a pick
  is skipped when a kept losing pick sharing a currency
  exited within 12h before its entry; raw-walk
  accounting, as graded).
  Stage 2 (R18C01): WORST-5-DAY EXCISION -- the losing
  cap1 rows of the stage-1 set on its five worst
  discovery entry days (fitted 2016-2023, embedded as
  date constants below; live rows are never on those
  dates, so the excision is historical-only).
  Stage 3 (R20C09): PARTNER UNION + EXPOSURE RE-SKIP
  5%: the stage-2 set union the partner additions of
  the 87i reference set (at any entry timestamp where
  the reference keeps >= 1 pick, same-side pool picks
  are added), settled through a second realised-balance
  exposure walk at 5% (START $80, formula lots at the
  carried N = 150/3, raw-walk accounting).
  Every delivered pick's stop is capped at 1 x TP
  (the 1:1 law; outcomes repriced at the cap in the
  research replay, exits re-simulated by the app's
  exit engine -- the Gate-C class behaviour of the
  shipped transform forms).

Gate A (work_rr1_validate/results/apr_gateA.json): the
shipped lib's transform (core/rr1val_lib) reproduces
the research chain BIT-FOR-BIT on the declared pool
basis (1,043 of 1,156 rows kept). The round screens'
hour-balance step was a no-op at every stage of this
chain (final hours [16, 17, 18] throughout), so it is
not re-applied here. Live feeding follows the shipped
combined forms: at each check the candidate group is
the 87f panel surface; each row's base_keep is settled
by stepping a private cycle87i form instance (own
sidecar namespace); the form keeps the full surface
snapshot and re-runs the verified array chain over it
(the chain is causal, so the current check's decisions
equal the research replay). Row identity between the
panel surface and the graded pool is by (symbol,
direction, strategy) at the check timestamp.

Check hours: the April grid (16, 17, 18 UTC) =
22:30 / 23:30 / 00:30 MMT -- identical to cycle87i, so
the install needs no signal/prep job retiming. Sizing:
carried N = 150 (full), shipped at N/3, unchanged.
April stays best-only (second slot empty).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

import core.cycle87f_best as _c87f
import core.cycle87i_best as _c87i
import core.cycle93w_best as _c93w
from core import d21rc_lib as _L
from core import rr1val_lib as _V
from core.new8_candidate import CandidateContext, ensure_m15

SYSTEM_NAME = "cycle87j"
CYCLE87J_CHECK_HOURS = _c87i.CYCLE87I_CHECK_HOURS
MAX_HOLD = 48
N_CARRIED = 150.0
N_USED = N_CARRIED / 3.0

# Stage-2 fitted excision: the stage-1 set's five worst
# discovery entry days (cap1 basis, fitted 2016-2023 in
# work_rr1_validate; losing rows on these days only).
WORST5_DAYS = {"2019-04-04", "2021-04-06", "2022-04-14",
               "2023-04-13", "2023-04-28"}
COOLDOWN_H = 12
RESKIP_FRAC = 0.05


def _state_path():
    from core.new8_candidate import default_state_path
    return default_state_path(SYSTEM_NAME)


def _sidecar(name):
    p = _state_path()
    return os.path.join(os.path.dirname(os.path.abspath(p)),
                        name)


def apply_chain(rows):
    """The verified RR chain over surface rows (dicts
    with entry/exit/sym/side/net/pwv/pv/tp/sl/fout/
    base_keep). Returns the final keep mask. Mirrors
    work_rr1_validate/scripts/spec_apr.py stage for
    stage (hour-balance was a no-op throughout)."""
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
    walk_out = d['net'].copy()
    fout = np.array([r['fout'] for r in rows])
    ref = np.array([r['base_keep'] for r in rows], bool)
    # stage 1: currency loss-cooldown over the reference
    # (raw-walk accounting basis, as graded)
    k1 = _V.loss_cooldown_cur(d, walk_out, COOLDOWN_H, ref)
    # stage 2: worst-5-day losing-row excision
    import datetime as _dt
    drop = np.zeros(n, bool)
    for i in np.where(k1)[0]:
        day = _dt.datetime.utcfromtimestamp(
            int(d['entry'][i])).date().isoformat()
        if day in WORST5_DAYS and fout[i] < 0:
            drop[i] = True
    k2 = k1 & ~drop
    # stage 3: partner union (on the reference) + re-skip
    add1 = _V.partner_add(d['entry'], d['side'], ref, 1,
                          False)
    k3 = _V.exposure_skip(d, walk_out, RESKIP_FRAC, N_USED,
                          prior=k2 | add1)
    return k3


class _Form87J:
    """A private cycle87i form whose delivered stream
    marks the reference set on the 87f panel surface;
    the snapshot is settled through the RR chain above.
    Persisted: the surface snapshot (scalar rows), the
    delivered ledger and the processed checks."""

    def __init__(self, path=None):
        self.path = path or _state_path()
        self.i_form = _c87i._Form87I(
            path=_sidecar('cycle87j_87i.json'))
        # the 87i form's E04 sub-state path is fixed-name
        # in its own module; repoint it into this system's
        # namespace before any stepping so the two forms
        # never share walk state.
        import core.cycle87g_best as _c87g
        self.i_form.g_form = _c87g._Form87G(
            path=_sidecar('cycle87j_e04.json'))
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
        self.i_form.save()
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

    def _lrow(self, r, m15_frames, base_keep):
        bars = _c93w._bars(r['symbol'], m15_frames)
        entry_s = _c93w._ts_s(r['entry_time'])
        exit_s = _c93w._ts_s(r['exit_time'])
        dirsign = 1.0 if str(r['direction']).upper() \
            .startswith('B') else -1.0
        entry_px = float(r.get('entry_px') or 0.0)
        if not entry_px:
            ts_arr = bars[0]
            j = int(np.searchsorted(ts_arr, entry_s))
            entry_px = float(bars[1][min(j, len(ts_arr) - 1)])
        prof = _L.profile_for_sym(
            r['symbol'], entry_s, exit_s, entry_px,
            dirsign, bars)
        majors = {p: _c93w._bars(p, m15_frames)
                  for p in _L.MAJORS}
        pv = _L.pip_value_per_lot(
            r['symbol'], _L.rates_at(majors, exit_s))
        if r.get('gross_pips') is not None:
            raw = float(r['gross_pips']) - _V.COST
        else:
            raw = (float(prof[-1]) if len(prof) else 0.0)
        tp = float(r['tp_pips_used'])
        sl = float(r['sl_pips_used'])
        if base_keep:
            # the 87i delivered row already carries the
            # incumbent's accounting basis (its layers
            # repriced gross_pips); use it verbatim.
            net = raw
        else:
            # partner-surface rows: price the accounting
            # outcome on the incumbent's basis (the 87h
            # stop-tighten-30 accounting of the pool).
            net = float(_V.stop_tighten_arr(
                {'prof': [prof]}, np.array([30.0]),
                np.array([raw]))[0])
        fout = float(_V.stop_tighten_arr(
            {'prof': [prof]}, np.array([min(sl, tp)]),
            np.array([net]))[0])
        return {'entry_s': int(entry_s), 'exit_s': int(exit_s),
                'sym': str(r['symbol']),
                'side': 1 if dirsign > 0 else -1,
                'net': float(net),
                'pwv': float(prof.min()) if len(prof) else 0.0,
                'pv': float(pv), 'tp': tp, 'sl': sl,
                'fout': fout, 'base_keep': bool(base_keep),
                'key': [str(r['symbol']),
                        str(r['direction'])[:1].upper(),
                        str(r.get('strategy',
                                  r.get('equation')))],
                'payload': r}

    def step(self, frames, check_time_utc, m15_frames,
             open_symbols=()):
        chk = pd.Timestamp(check_time_utc)
        if str(chk) in self.processed:
            return [r for r in self.delivered
                    if pd.Timestamp(r['check']) == chk]
        entries = _c87f._base_entries(
            frames, check_time_utc, m15_frames, open_symbols)
        if entries is not None \
                and entries.attrs.get('status'):
            return entries
        # reference set: step the private 87i form
        # directly (its g walk + feed), as its own
        # panel_entries does on the global state.
        m15map = ensure_m15(m15_frames,
                            _c87i._DESIGN_SYMBOLS)
        ctx = CandidateContext(frames, m15map,
                               _c87i.POOL_DESIGNS)
        base_rows = []
        if entries is not None and len(entries):
            for _, r in entries.iterrows():
                dd = dict(r)
                dd['check'] = chk
                if dd.get('entry_time') is None:
                    dd['entry_time'] = chk - pd.Timedelta(
                        minutes=30)
                if dd.get('exit_time') is None:
                    dd['exit_time'] = pd.Timestamp(
                        dd['entry_time']) + pd.Timedelta(
                            hours=int(dd.get('hold_h', 48)))
                if dd.get('strategy') is None:
                    dd['strategy'] = dd.get('equation')
                base_rows.append(dd)
        self.i_form.g_form.state.step(ctx, chk, base_rows)
        self.i_form.feed_new(m15_frames)
        self.i_form.save()
        base_map = {}
        for r in self.i_form.delivered:
            if pd.Timestamp(r['check']) == chk:
                base_map[(
                    str(r.get('symbol')),
                    str(r.get('direction', ''))[:1].upper(),
                    str(r.get('strategy',
                              r.get('equation'))))] = r
        new_rows = []
        if entries is not None and len(entries):
            for _, r in entries.iterrows():
                dd = dict(r)
                dd['check'] = chk
                if dd.get('entry_time') is None:
                    dd['entry_time'] = chk - pd.Timedelta(
                        minutes=30)
                if dd.get('exit_time') is None:
                    dd['exit_time'] = pd.Timestamp(
                        dd['entry_time']) + pd.Timedelta(
                            hours=int(dd.get('hold_h', 48)))
                if dd.get('strategy') is None:
                    dd['strategy'] = dd.get('equation')
                key = (str(dd['symbol']),
                       str(dd['direction'])[:1].upper(),
                       str(dd.get('strategy',
                                  dd.get('equation'))))
                if key in base_map:
                    lr = self._lrow(base_map[key],
                                    m15_frames, True)
                    src = base_map[key]
                else:
                    lr = self._lrow(dd, m15_frames, False)
                    src = dd
                lr['payload'] = {
                    k: (str(v) if isinstance(
                        v, pd.Timestamp) else v)
                    for k, v in src.items()}
                new_rows.append(lr)
        self.rows.extend(new_rows)
        keep = apply_chain(self.rows)
        out = []
        n_old = len(self.rows) - len(new_rows)
        for j, lr in enumerate(self.rows):
            if j < n_old or not keep[j]:
                continue
            dd = dict(lr['payload'])
            for k in ('check', 'entry_time', 'exit_time'):
                if isinstance(dd.get(k), str):
                    dd[k] = pd.Timestamp(dd[k])
            dd['sl_pips_used'] = min(float(dd['sl_pips_used']),
                                     float(dd['tp_pips_used']))
            self.delivered.append(dd)
            out.append(dd)
        self.processed.append(str(chk))
        self.save()
        return out


_STATE = None


def _state():
    global _STATE
    if _STATE is None:
        _STATE = _Form87J()
    return _STATE


def load_87j_state(path=None):
    if path is not None:
        return _Form87J(path=path)
    return _state()


def is_cycle87j_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE87J_CHECK_HOURS and t.minute == 30


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
    return pd.DataFrame([_c87f._signal_row(r) for r in out])


def walk_ledger():
    """The delivered cycle87j stream."""
    return [dict(r) for r in _state().delivered]


def fetch_cycle87j_m15_frames(state=None):
    return _c87i.fetch_cycle87i_m15_frames(state)


def evaluate_cycle87j_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc, m15_frames)


def select_cycle87j_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    if signals is None or not len(signals):
        return signals
    return signals
