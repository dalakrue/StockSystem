"""Cycle 78F -- July: RR 1:1 chain cycle R18C08 (the
cycle78e stream settled through the Rounds 11/18 chain
R11C01 -> R18C08, stops capped at 1 x TP), installed
under the LOWERED STANDARD (user order 2026-11-06;
validation record:
work_rr1_lowered_validate/results/jul_R18C08_VALIDATION.md
-- VALIDATED under the lowered standard on the raw
path basis: red lines PASS (DISC +2984.93 / AUDIT
+364.15 @2.5), EC22 failed {13_lct, 14_leftover} only
(the tolerated carve-out; AUDIT win 70.41 passes the
user's 70.0 floor, red weeks within the lowered <=2
allowance, DSR >= 0.50 lowered arm), S9 mc9 PASS,
Gate A bit-exact PASS, sizing PASS under the lowered
absolute arm (peak 37.64% <= 60% at carried N = 103;
incumbent 78e peak 28.98%), Amendment-1 chain NOT
APPLICABLE (July is not a COMBINED chain-universe
month). It replaces cycle78e.

  Stage 1 (R11C01): the 78e stream settled through a
  realised-balance EXPOSURE-SKIP at 6% (formula lots
  at the carried N = 103/3, raw-walk accounting).
  Stage 2 (R18C08): a 12h currency-sharing
  LOSS-COOLDOWN on the cap1 outcome.
  The round screens' hour-balance step was a no-op at
  both stages (final hours [15, 17, 18], nothing
  dropped, no replacements admitted), so it is not
  re-applied here -- the Gate-A class behaviour of the
  shipped transform forms. Every delivered pick's
  stop is capped at 1 x TP (the 1:1 law; exits
  re-simulated by the app's exit engine).

Live feeding: at each check the form takes the
cycle78e panel entries (which step the 78e E09 state
-- after this install nothing else steps it), converts
them to stream rows and re-runs the verified array
chain over the accumulated snapshot (the chain is
causal, so the current check's decisions equal the
research replay). Panel rows carry the programme's
48h exit convention.

Check hours: the July grid (15, 17, 18 UTC) =
21:30 / 23:30 / 00:30 MMT -- identical to cycle78e, so
the install needs no signal/prep job retiming.
Sizing: carried N = 103 (full), shipped at N/3,
unchanged.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

import core.cycle78e_best as _c78e
import core.cycle93w_best as _c93w
from core import d21rc_lib as _L
from core import rr1val_lib as _V

SYSTEM_NAME = "cycle78f"
CYCLE78F_CHECK_HOURS = _c78e.CYCLE78E_CHECK_HOURS
MAX_HOLD = 48
N_CARRIED = 103.0
N_USED = N_CARRIED / 3.0

EXP_FRAC = 0.06
COOLDOWN_H = 12


def _state_path():
    from core.new8_candidate import default_state_path
    return default_state_path(SYSTEM_NAME)


def apply_chain(rows):
    """The verified R11C01 -> R18C08 chain over stream
    rows (dicts with entry/exit/sym/side/net/pwv/pv/
    tp/sl/fout). Mirrors work_rr1_validate/scripts/
    spec_jul.py stages with the R18C08 design."""
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
    k2 = _V.loss_cooldown_cur(d, fout, COOLDOWN_H, k1)
    return k2


class _Form78F:
    """The cycle78e panel stream settled through the
    RR chain. Persisted: the stream snapshot (scalar
    rows), the delivered ledger and the processed
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
        _STATE = _Form78F()
    return _STATE


def load_78f_state(path=None):
    if path is not None:
        return _Form78F(path=path)
    return _state()


def is_cycle78f_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE78F_CHECK_HOURS and t.minute == 30


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
    """The delivered cycle78f stream."""
    return [dict(r) for r in _state().delivered]


def fetch_cycle78f_m15_frames(state=None):
    return _c78e.fetch_cycle78e_m15_frames(state)


def evaluate_cycle78f_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc, m15_frames)


def select_cycle78f_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    if signals is None or not len(signals):
        return signals
    return signals
