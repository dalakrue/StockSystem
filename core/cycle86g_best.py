"""Cycle 86G -- March: the SL4-10CYC round's D5 form
over the shipped cycle86f stream (research verdict:
work_sl4_10cyc/results/mar_VERDICT.md; validation
record: work_sl4_validate/results/mar_VALIDATION.md):

  1. EXPOSURE-SKIP 12.5%: a realised-balance walk over
     the 86f delivered stream (START $80, formula lots
     at the carried N = 86/3). A pick is skipped when
     the open adverse exposure of kept picks (|pwv| x
     pv x lot, fixed at each pick's entry) plus the
     candidate's own would exceed 12.5% of the realised
     balance (designs.exposure_skip verbatim,
     core/sl4v_lib.ExposureLayer).
  2. RATIO CAP: every delivered pick's stop is capped
     at min(stop, 4 x its target) on the EXACT per-trade
     basis (rebuilt 527/527 in the validation lane);
     the delivered row carries the capped sl_pips_used
     (its exit is re-simulated by the app's exit engine
     with the capped stop, the same Gate-C class
     behaviour as the shipped D21-RC forms' caps).

Gate A (work_sl4_validate/results/mar_gateA.json): the
shipped lib's transform + layer reproduce the research
candidate stream BIT-FOR-BIT (456 of 527 kept), array
form and incremental layer alike, on the exact basis.
Check hours: the March grid (11, 16, 17 UTC), unchanged
from 86f. Sizing: carried N = 86 (full), shipped at
N/3, unchanged. March stays best-only (no second slot).
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

import core.cycle86f_best as _c86f
import core.cycle93w_best as _c93w
from core import d21rc_lib as _L
from core import sl4v_lib as _S
from core.new8_candidate import default_state_path

CYCLE86G_CHECK_HOURS = _c86f.CYCLE86F_CHECK_HOURS
N_CARRIED = 86.0
SYSTEM_NAME = "cycle86g"
CARRIED_N = N_CARRIED / 3.0


def _sidecar(name):
    p = default_state_path(SYSTEM_NAME)
    return os.path.join(os.path.dirname(
        os.path.abspath(p)), name)


class _Form86G:
    """The 86f panel form (its stream state kept in this
    form's sidecar namespace) settled through the
    exposure layer. Persisted: the layer state and the
    delivered ledger rows."""

    def __init__(self, path=None):
        self.path = path or default_state_path(SYSTEM_NAME)
        self.layer = _S.ExposureLayer(CARRIED_N)
        self.delivered = []
        self.processed = []
        self._load()

    # ------------------------------------------------ persist --
    def _load(self):
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path) as fh:
                d = json.load(fh)
        except Exception:
            return
        lay = d.get('layer', {})
        self.layer.bal = float(lay.get('bal', _S.START))
        self.layer.profit = float(lay.get('profit', 0.0))
        self.layer.open_kept = [(int(e), float(a))
                                for e, a in
                                lay.get('open_kept', [])]
        self.layer._pending_exits = [
            (int(e), float(n), float(p), float(l))
            for e, n, p, l in lay.get('pending_exits', [])]
        self.delivered = d.get('delivered', [])
        self.processed = d.get('processed', [])

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(
            os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, 'w') as fh:
            json.dump({
                'layer': dict(
                    bal=self.layer.bal,
                    profit=self.layer.profit,
                    open_kept=[[e, a] for e, a in
                               self.layer.open_kept],
                    pending_exits=[[e, n, p, l] for e, n, p, l
                                   in
                                   self.layer._pending_exits]),
                'delivered': self.delivered,
                'processed': self.processed}, fh)

    # --------------------------------------------------- step --
    def step(self, frames, check_time_utc, m15_frames,
             open_symbols=()):
        chk = pd.Timestamp(check_time_utc)
        if str(chk) in self.processed:
            return [r for r in self.delivered
                    if pd.Timestamp(r['check']) == chk]
        # 86f panel form under this form's state namespace
        orig = _c86f.SYSTEM_NAME
        _c86f.SYSTEM_NAME = 'cycle86g_86f'
        try:
            entries = _c86f.panel_entries(
                frames, check_time_utc,
                m15_frames=m15_frames,
                open_symbols=open_symbols)
        finally:
            _c86f.SYSTEM_NAME = orig
        if entries is not None \
                and entries.attrs.get('status'):
            return entries
        out = []
        if entries is not None and len(entries):
            for _, r in entries.iterrows():
                row = dict(r)
                entry_s = int((chk - pd.Timedelta(
                    minutes=30)).value // 10 ** 9)
                exit_s = entry_s + 48 * 3600
                sym = str(row['symbol'])
                bars = _c93w._bars(sym, m15_frames)
                dirsign = 1.0 if str(row['direction']) \
                    .upper().startswith('B') else -1.0
                entry_px = float(row.get('entry_px') or 0.0)
                if not entry_px:
                    ts_arr = bars[0]
                    j = int(np.searchsorted(ts_arr, entry_s))
                    entry_px = float(
                        bars[1][min(j, len(ts_arr) - 1)])
                prof = _L.profile_for_sym(
                    sym, entry_s, exit_s, entry_px, dirsign,
                    bars)
                majors = {p: _c93w._bars(p, m15_frames)
                          for p in _L.MAJORS}
                pv = _L.pip_value_per_lot(
                    sym, _L.rates_at(majors, exit_s))
                lrow = {'entry_s': entry_s,
                        'exit_s': exit_s,
                        'net': float(row['gross_pips']) - _S.COST
                        if row.get('gross_pips') is not None
                        else 0.0,
                        'pwv': float(prof.min())
                        if len(prof) else 0.0,
                        'pv': pv,
                        'tp': float(row['tp_pips_used']),
                        'sl': float(row['sl_pips_used']),
                        'prof': prof}
                if self.layer.decide(lrow) is None:
                    continue
                row['sl_pips_used'] = min(
                    float(row['sl_pips_used']),
                    4.0 * float(row['tp_pips_used']))
                row.setdefault('check', chk)
                ser = dict(row)
                for k in ('check', 'entry_time',
                          'exit_time'):
                    if k in ser:
                        ser[k] = str(ser[k])
                self.delivered.append(ser)
                out.append(row)
        self.processed.append(str(chk))
        self.save()
        return out


_STATE = None


def _state():
    global _STATE
    if _STATE is None:
        _STATE = _Form86G()
    return _STATE


def load_86g_state(path=None):
    if path is not None:
        return _Form86G(path=path)
    return _state()


def is_cycle86g_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE86G_CHECK_HOURS and t.minute == 30


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    st = _state()
    kept = st.step(frames, check_time_utc, m15_frames,
                   open_symbols=open_symbols)
    if isinstance(kept, pd.DataFrame):
        return kept
    if not kept:
        return pd.DataFrame()
    rows = []
    for r in kept:
        d = dict(r)
        d.setdefault('strategy', d.get('equation'))
        rows.append(d)
    return pd.DataFrame(rows)


def walk_ledger():
    """The delivered cycle86g stream (ledger rows)."""
    return [dict(r) for r in _state().delivered]


# ------------------------------------------------- coordinator
def fetch_cycle86g_m15_frames(state=None):
    return _c86f.fetch_cycle86f_m15_frames(state)


def evaluate_cycle86g_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc,
                         m15_frames=m15_frames)


def select_cycle86g_entries(signals: pd.DataFrame,
                            open_symbols=()):
    return _c86f.select_cycle86f_entries(
        signals, open_symbols=open_symbols)
