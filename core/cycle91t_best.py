"""Cycle 91T -- September: the RR 1:1 programme's
standing best form (Rounds 12/18 chain R12C13 ->
R18C02) over the shipped cycle91r stream (validation
record: work_rr1_validate/results/sep_VALIDATION.md --
VALIDATED under the main gates: EC22-middle failed set
identical to 91r's own {13_lct, 14_leftover}, S9 PASS,
sizing inside the +2-pt tolerance at +1.32 pts):

  Stage 1 (R12C13): the 91r stream settled through a
  realised-balance EXPOSURE-SKIP at 8% (START $80,
  formula lots at the carried N = 83/3, raw-walk
  accounting). (The research design's group-size>=3
  admission term is vacuous on this basis: the stream
  is the incumbent's full ledger, so every row is a
  reference row.)
  Stage 2 (R18C02): WORST-10-DAY EXCISION -- the losing
  cap1 rows of the stage-1 set on its ten worst
  discovery entry days (fitted 2016-2023, embedded as
  date constants below; historical-only).
  Every delivered pick's stop is capped at 1 x TP
  (the 1:1 law; exits re-simulated by the app's exit
  engine -- the Gate-C class behaviour of the shipped
  transform forms).

Gate A (work_rr1_validate/results/sep_gateA.json): the
shipped lib's transform (core/rr1val_lib) reproduces
the research chain BIT-FOR-BIT on the incumbent stream
basis (442 of 596 rows kept). The round screens'
hour-balance step was a no-op at every stage (final
hours [1, 2, 11, 18] throughout), so it is not
re-applied here. Live feeding: at each check the form
takes the cycle91r panel entries (which step the 91r
OfficeAlt state -- after this install nothing else
steps it), converts them to stream rows and re-runs
the verified array chain over the accumulated
snapshot (the chain is causal, so the current check's
decisions equal the research replay). Panel rows
carry the programme's 48h exit convention, as in the
shipped forms. September's second-best stays
cycle91s (the base stream internalises it, as under
91r).

Check hours: the September grid (1, 2, 11, 18 UTC) =
07:30 / 08:30 / 17:30 / 00:30 MMT -- identical to
cycle91r, so the install needs no signal/prep job
retiming. Sizing: carried N = 83 (full), shipped at
N/3, unchanged.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

import core.cycle91r_best as _c91r
import core.cycle93w_best as _c93w
from core import d21rc_lib as _L
from core import rr1val_lib as _V

SYSTEM_NAME = "cycle91t"
CYCLE91T_CHECK_HOURS = _c91r.CYCLE91R_CHECK_HOURS
MAX_HOLD = 48
N_CARRIED = 83.0
N_USED = N_CARRIED / 3.0

WORST10_DAYS = {"2017-09-26", "2017-09-27", "2018-09-19",
                "2018-09-26", "2019-09-03", "2020-09-11",
                "2021-09-13", "2022-09-21", "2022-09-27",
                "2023-09-07"}
EXP_FRAC = 0.08


def _state_path():
    from core.new8_candidate import default_state_path
    return default_state_path(SYSTEM_NAME)


def apply_chain(rows):
    """The verified RR chain over stream rows (dicts
    with entry/exit/sym/side/net/pwv/pv/tp/sl/fout).
    Mirrors work_rr1_validate/scripts/spec_sep.py."""
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
    ref = np.ones(n, bool)
    k1 = _V.exposure_skip(d, walk_out, EXP_FRAC, N_USED,
                          prior=ref)
    import datetime as _dt
    drop = np.zeros(n, bool)
    for i in np.where(k1)[0]:
        day = _dt.datetime.utcfromtimestamp(
            int(d['entry'][i])).date().isoformat()
        if day in WORST10_DAYS and fout[i] < 0:
            drop[i] = True
    return k1 & ~drop


class _Form91T:
    """The cycle91r panel stream settled through the RR
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
        keep = apply_chain(self.rows)
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
        _STATE = _Form91T()
    return _STATE


def load_91t_state(path=None):
    if path is not None:
        return _Form91T(path=path)
    return _state()


def is_cycle91t_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE91T_CHECK_HOURS and t.minute == 30


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
    """The delivered cycle91t stream."""
    return [dict(r) for r in _state().delivered]


def fetch_cycle91t_m15_frames(state=None):
    return _c91r.fetch_cycle91r_m15_frames(state)


def evaluate_cycle91t_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc, m15_frames)


def select_cycle91t_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    if signals is None or not len(signals):
        return signals
    return signals
