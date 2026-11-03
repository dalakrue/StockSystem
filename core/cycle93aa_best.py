"""Cycle 93AA -- November: the 10-CYCLE ROUND 2 lead
form R1 over the shipped cycle93x stream (research
verdict: work_10cyc_r2/results/nov_VERDICT.md;
validation record: work_r2_validate/results/
nov_VALIDATION.md):

  EXPOSURE-SKIP 6%: a second realised-balance walk
  over the cycle93x delivered stream (START $80,
  formula lots at the carried N = 100/3). A pick is
  skipped when the open adverse exposure of kept
  picks (|pwv| x pv x lot, fixed at each pick's
  entry) plus the candidate's own would exceed 6%
  of the realised balance -- the 93x form's own 7.5%
  rule, tightened to 6% (designs.exposure_skip
  verbatim, core/r2val_lib.ExposureLayerR2, prior =
  the 93x stream). Delivered rows keep the 93x form's
  own 4xTP-capped stop (the cap is unchanged; exits
  are re-simulated by the app's exit engine, the same
  Gate-C class behaviour as the 93x form).

Gate A (work_r2_validate/results/nov_gateA.json):
the shipped lib's transform + layer reproduce the
research candidate stream BIT-FOR-BIT (497 of 769
pool rows), array form and incremental layer alike,
on the exact basis. Check hours: the November grid
(9, 10, 13, 15 UTC) -- identical to cycle93x, so an
install needs no signal/prep job retiming. Sizing:
carried N = 100 (full), shipped at N/3, unchanged
from the incumbent. The second-best slot stays
empty (93x internalised the combined stream; 93aa
inherits it).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

import core.cycle93r_best as _c93r
import core.cycle93t_best as _c93t
import core.cycle93x_best as _c93x
from core import d21rc_lib as _L
from core import r2val_lib as _R
from core.cycle93x_best import (evaluate_cycle93x_signals,
                                select_cycle93x_entries)

SYSTEM_NAME = "cycle93aa"
CYCLE93AA_CHECK_HOURS = _c93x.CYCLE93X_CHECK_HOURS
MAX_HOLD = 48
CARRIED_N = 100.0 / 3.0

SYMS = _c93x.SYMS


def _state_path():
    from core.new8_candidate import default_state_path
    return default_state_path(SYSTEM_NAME)


class _Form:
    """A cycle93x state object (own sidecar chain)
    whose delivered stream is settled through the
    6% exposure layer. The 93x sub-form is stepped
    for every check in order so its internal walk is
    the incumbent's own; this form's layer then
    decides each delivered row in stream order."""

    def __init__(self, path=None):
        self.path = path or _state_path()
        self.x_state = _c93x._Form(
            path=self.path + '.93xstate.json')
        self.layer = _R.ExposureLayerR2(CARRIED_N, 0.06)
        self.delivered = []
        self.filtered = []
        self.fed = 0
        self._load()

    # ------------------------------------------------ persist --
    def _load(self):
        import json
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path) as fh:
                d = json.load(fh)
        except Exception:
            return

        def de(rows):
            out = []
            for r in rows:
                r = dict(r)
                for k in ('check', 'entry_time', 'exit_time'):
                    if r.get(k) is not None:
                        r[k] = pd.Timestamp(r[k])
                out.append(r)
            return out
        self.delivered = de(d.get('delivered', []))
        self.filtered = de(d.get('filtered', []))
        self.fed = int(d.get('fed', 0))
        lay = d.get('layer', {})
        self.layer.bal = float(lay.get('bal', _R.START))
        self.layer.profit = float(lay.get('profit', 0.0))
        self.layer.open_kept = [(int(e), float(a)) for e, a in
                                lay.get('open_kept', [])]
        self.layer._pending_exits = [
            (int(e), float(n), float(p), float(l))
            for e, n, p, l in lay.get('pending_exits', [])]

    def save(self):
        import json
        if not self.path:
            return
        os.makedirs(os.path.dirname(
            os.path.abspath(self.path)), exist_ok=True)
        self.x_state.save()

        def ser(rows):
            out = []
            for r in rows:
                d = dict(r)
                for k in ('check', 'entry_time', 'exit_time'):
                    if d.get(k) is not None:
                        d[k] = pd.Timestamp(d[k]).isoformat()
                out.append(d)
            return out
        data = dict(
            system=SYSTEM_NAME,
            delivered=ser(self.delivered),
            filtered=ser(self.filtered),
            fed=self.fed,
            layer=dict(
                bal=self.layer.bal, profit=self.layer.profit,
                open_kept=[[e, a] for e, a in
                           self.layer.open_kept],
                pending_exits=[[e, n, p, l] for e, n, p, l in
                               self.layer._pending_exits]))
        with open(self.path, 'w') as fh:
            json.dump(data, fh)

    # ---------------------------------------------------- step --
    def step(self, ohlc, frames, check, inc_entries,
             m15_frames=None):
        chk = pd.Timestamp(check)
        self.x_state.step(ohlc, frames, check, inc_entries,
                          m15_frames=m15_frames)
        # feed every not-yet-fed 93x delivered row, in
        # stream order, through the 6% layer
        new = self.x_state.delivered[self.fed:]
        for row in new:
            bars = _c93x._bars(row['symbol'], m15_frames)
            entry_s = _c93x._ts_s(row['entry_time'])
            exit_s = _c93x._ts_s(row['exit_time'])
            dirsign = 1.0 if str(row['direction']).upper() \
                .startswith('B') else -1.0
            entry_px = float(row.get('entry_px') or 0.0)
            if not entry_px:
                ts_arr = bars[0]
                j = int(np.searchsorted(ts_arr, entry_s))
                entry_px = float(
                    bars[1][min(j, len(ts_arr) - 1)])
            prof = _L.profile_for_sym(
                row['symbol'], entry_s, exit_s, entry_px,
                dirsign, bars)
            majors = {p: _c93x._bars(p, m15_frames)
                      for p in _L.MAJORS}
            pv = _L.pip_value_per_lot(
                row['symbol'], _L.rates_at(majors, exit_s))
            lrow = {'entry_s': entry_s, 'exit_s': exit_s,
                    'net': float(row['gross_pips']) - _R.COST,
                    'pwv': float(prof.min())
                    if len(prof) else 0.0,
                    'pv': pv,
                    'tp': float(row['tp_pips_used']),
                    'sl': float(row['sl_pips_used']),
                    'prof': prof}
            if self.layer.decide(lrow) is None:
                self.filtered.append(row)
            else:
                self.delivered.append(row)
            self.fed += 1
        self.save()
        return [r for r in self.delivered
                if pd.Timestamp(r['check']) == chk]


def _load_form_state():
    return _Form()


def reset_form_state():
    """Remove the persisted 93aa stream state (gate use)."""
    for p in (_state_path(),
              _state_path() + '.93xstate.json',
              _state_path() + '.93xstate.json.wstate.json',
              _state_path()
              + '.93xstate.json.wstate.json.ustate.json'):
        if os.path.exists(p):
            os.remove(p)


def walk_ledger():
    """The delivered picks recorded by the form's state,
    as a research-ledger DataFrame (gate use)."""
    st = _Form()
    rows = [dict(check=r['check'], symbol=r['symbol'],
                 direction=r['direction'],
                 strategy=r['strategy'],
                 entry_time=r['entry_time'],
                 exit_time=r['exit_time'],
                 gross_pips=r['gross_pips'])
            for r in st.delivered]
    df = pd.DataFrame(rows)
    if len(df):
        df = df.sort_values('check').reset_index(drop=True)
    return df


# -------------------------------------------------- panel API --
def evaluate_cycle93aa_signals(frames: dict, check_time_utc,
                               m15_frames: dict | None = None
                               ) -> pd.DataFrame:
    """Base signals: the cycle93x chain (the transformed
    form is produced by panel_entries)."""
    return evaluate_cycle93x_signals(
        frames, check_time_utc, m15_frames=m15_frames)


def select_cycle93aa_entries(signals: pd.DataFrame,
                             open_symbols=()) -> pd.DataFrame:
    return select_cycle93x_entries(signals,
                                   open_symbols=open_symbols)


def is_cycle93aa_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE93AA_CHECK_HOURS and t.minute == 30


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full form entries for one check: the cycle93r base
    entries settled through the cycle93x form state,
    then this form's 6% exposure-skip over the 93x
    delivered stream -- only survivors are delivered."""
    from core.new8_features import frame_to_research
    from core.new8_walk import ohlc_from_frame
    entries = _c93r.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    ohlc = {}
    for sym, fr in frames.items():
        if fr is not None and len(fr):
            try:
                rfr, _ = frame_to_research(fr)
                ohlc[sym] = ohlc_from_frame(rfr)
            except Exception:
                pass
    st = _load_form_state()
    delivered = st.step(ohlc, frames, check_time_utc,
                        entries, m15_frames=m15_frames)
    if not delivered:
        return pd.DataFrame()
    return pd.DataFrame(
        [_c93t._signal_row(r) for r in delivered])
