"""Cycle 92D -- October: RR 1:1 chain cycle R18C12 (R11C01 -> R18C12) over the cycle92c merged stream (every stream row is a reference row) -- the programme's cleanest near-miss. COMPOSITION INSTALL -- user order 2026-11-06 (system-wide RR 1:1 replacement): installed as the month's NEAREST RR 1:1 cycle. This is NOT a validation pass; the blocking arms below stand as recorded. Blocking arm (board validation): 8_weeks ALONE. EC22 otherwise clean, DSR 1.0, S9 mc9 PASS, Gate A bit-exact in the validation lane. Path numbers: DISC +2,123.49 / AUDIT +581.85 @2.5, AUDIT win 85.87, entries/day exactly 2.0, kept 420. Check hours (15, 17, 18 UTC) = 21:30 / 23:30 / 00:30 MMT -- identical to cycle92c, no job retiming. Sizing: carried N = 83, shipped at N/3, unchanged."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

import core.cycle92c_best as _c92c
import core.cycle93w_best as _c93w
from core import d21rc_lib as _L
from core import rr1val_lib as _V

SYSTEM_NAME = "cycle92d"
CYCLE92D_CHECK_HOURS = (15, 17, 18)
SURFACE_GRID = (15, 17, 18)
MAX_HOLD = 48
N_CARRIED = 83.0
N_USED3 = 27.666666666666668
REFHR = {15: 1003.8517857141721, 17: 1791.1188571427956, 18: 2010.3694999999443}
OFFICE_HOURS = '()'


def _state_path():
    from core.new8_candidate import default_state_path
    return default_state_path(SYSTEM_NAME)


def _sidecar(name):
    from core.new8_candidate import default_state_path
    base = default_state_path(SYSTEM_NAME)
    return os.path.join(os.path.dirname(
        os.path.abspath(base)), name)


def apply_chain(rows):
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
        _STATE = _Form()
    return _STATE


def load_state_form(path=None):
    if path is not None:
        return _Form(path=path)
    return _state()


def is_cycle92d_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE92D_CHECK_HOURS and t.minute == 30


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
    """The delivered cycle92d stream."""
    return [dict(r) for r in _state().delivered]


def fetch_cycle92d_m15_frames(state=None):
    from core.cycle89_best import fetch_cycle89_m15_frames
    return fetch_cycle89_m15_frames()


def evaluate_cycle92d_signals(frames: dict, check_time_utc,
                               m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc, m15_frames)


def select_cycle92d_entries(signals: pd.DataFrame,
                             open_symbols=()) -> pd.DataFrame:
    if signals is None or not len(signals):
        return signals
    return signals
