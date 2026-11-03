"""cycle87h -- April: the 10-CYCLE ROUND 2 lead form
R1 over the shipped cycle87g stream (research
verdict: work_10cyc_r2/results/apr_VERDICT.md;
validation record: work_r2_validate/results/
apr_VALIDATION.md):

  EXPOSURE-SKIP 6%: a realised-balance walk over the
  cycle87g delivered stream (START $80, formula lots
  at the carried N = 150/3). A pick is skipped when
  the open adverse exposure of kept picks (|pwv| x pv
  x lot, fixed at each pick's entry) plus the
  candidate's own would exceed 6% of the realised
  balance. The walk's accounting outcome is the
  trade's stop-tightened-at-30p outcome -- the 87g
  form's own basis (designs.stop_tighten verbatim) --
  and each delivered pick's outcome is that outcome
  repriced at the SL <= 4xTP cap (designs.
  stop_tighten_arr verbatim, core/r2val_lib.
  ExposureLayerR2, prior = the 87g stream).

Gate A (work_r2_validate/results/apr_gateA.json):
the shipped lib's transform + layer reproduce the
research candidate stream BIT-FOR-BIT (1,126 of
1,156 rows), array form and incremental layer
alike. DECLARED BASIS: April's stream rides the
declared POOL basis authorised by the user on
2026-11-03 for the 87g install (48 pvote-era rows'
exact TP/SL unrecoverable); the R1 candidate is
graded on that same declared basis, stated plainly
in the validation record. Check hours (16,17,18,19)
UTC = the 87f grid, unchanged. Carried N 150
unchanged. The combined stream stays internalised;
the registry second slot stays empty. Live rows
carry the composition as a stop of min(shipped
stop, 30 pips, 4 x shipped TP), re-simulated by
the app's exit engine.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

import core.cycle87f_best as _c87f
import core.cycle87g_best as _c87g
import core.cycle93w_best as _c93w
from core import d21rc_lib as _L
from core import r2val_lib as _R
from core.new8_candidate import CandidateContext, ensure_m15

CYCLE87H_CHECK_HOURS = _c87f.CYCLE87F_CHECK_HOURS
N_CARRIED = 150.0
SYSTEM_NAME = "cycle87h"

_DESIGN_SYMBOLS = _c87f._DESIGN_SYMBOLS
POOL_DESIGNS = _c87f.POOL_DESIGNS


def _sidecar(name):
    from core.new8_candidate import default_state_path
    p = default_state_path(SYSTEM_NAME)
    return os.path.join(os.path.dirname(
        os.path.abspath(p)), name)


def _state_path():
    from core.new8_candidate import default_state_path
    return default_state_path(SYSTEM_NAME)


class _Form87H:
    """A cycle87g form (own E04 sidecar) whose kept
    rows are settled through the 6% exposure layer."""

    def __init__(self, path=None):
        self.path = path or _state_path()
        self.g_form = _c87g._Form87G(
            path=_sidecar('cycle87h_e04.json'))
        self.layer = _R.ExposureLayerR2(
            N_CARRIED / 3.0, 0.06, walk_cap=30.0)
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
        self.g_form.save()
        if not self.path:
            return
        os.makedirs(os.path.dirname(
            os.path.abspath(self.path)), exist_ok=True)

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

    # ---------------------------------------------------- feed --
    def feed_new(self, m15_frames):
        """Settle every not-yet-fed 87g kept row through
        the exposure layer, in stream order."""
        kept = list(self.g_form.state.kept)
        for r in kept[self.fed:]:
            bars = _c93w._bars(r['symbol'], m15_frames)
            entry_s = _c93w._ts_s(r['entry_time'])
            exit_s = _c93w._ts_s(r['exit_time'])
            dirsign = 1.0 if str(r['direction']).upper() \
                .startswith('B') else -1.0
            entry_px = float(r.get('entry_px') or 0.0)
            if not entry_px:
                ts_arr = bars[0]
                j = int(np.searchsorted(ts_arr, entry_s))
                entry_px = float(
                    bars[1][min(j, len(ts_arr) - 1)])
            prof = _L.profile_for_sym(
                r['symbol'], entry_s, exit_s, entry_px,
                dirsign, bars)
            majors = {p: _c93w._bars(p, m15_frames)
                      for p in _L.MAJORS}
            pv = _L.pip_value_per_lot(
                r['symbol'], _L.rates_at(majors, exit_s))
            if r.get('gross_pips') is not None:
                net = float(r['gross_pips']) - _R.COST
            else:
                net = (float(prof[-1]) if len(prof) else 0.0)
            lrow = {'entry_s': entry_s, 'exit_s': exit_s,
                    'net': net,
                    'pwv': float(prof.min())
                    if len(prof) else 0.0,
                    'pv': pv,
                    'tp': float(r['tp_pips_used']),
                    'sl': float(r['sl_pips_used']),
                    'prof': prof}
            out = self.layer.decide(lrow)
            if out is None:
                self.filtered.append(r)
            else:
                d = dict(r)
                d['gross_pips'] = float(out) + _R.COST
                d['sl_pips_used'] = min(
                    float(r['sl_pips_used']),
                    30.0,
                    4.0 * float(r['tp_pips_used']))
                self.delivered.append(d)
            self.fed += 1


_STATE = None


def _state():
    global _STATE
    if _STATE is None:
        _STATE = _Form87H()
    return _STATE


def load_87h_state(path=None):
    if path is not None:
        return _Form87H(path=path)
    return _state()


def reset_form_state():
    """Remove the persisted 87h stream state (gate use)."""
    for p in (_state_path(), _sidecar('cycle87h_e04.json')):
        if os.path.exists(p):
            os.remove(p)


def is_cycle87h_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE87H_CHECK_HOURS and t.minute == 30


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full R1 entries for one check: the combined
    87e<-87s base entries settled through this form's
    87g (E04 + stop-30 + cap4) state, then the 6%
    exposure-skip over the 87g delivered stream --
    only survivors are delivered."""
    entries = _c87f._base_entries(frames, check_time_utc,
                                  m15_frames, open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    m15map = ensure_m15(m15_frames, _DESIGN_SYMBOLS)
    ctx = CandidateContext(frames, m15map, POOL_DESIGNS)
    chk = pd.Timestamp(check_time_utc)
    base_rows = []
    if entries is not None and len(entries):
        for _, r in entries.iterrows():
            d = dict(r)
            d["check"] = chk
            if d.get("entry_time") is None:
                d["entry_time"] = chk - pd.Timedelta(
                    minutes=30)
            if d.get("exit_time") is None:
                d["exit_time"] = pd.Timestamp(
                    d["entry_time"]) + pd.Timedelta(
                        hours=int(d.get("hold_h", 48)))
            if "strategy" not in d \
                    or d.get("strategy") is None:
                d["strategy"] = d.get("equation")
            base_rows.append(d)
    form = _state()
    form.g_form.state.step(ctx, chk, base_rows)
    form.feed_new(m15_frames)
    form.save()
    out = [r for r in form.delivered
           if pd.Timestamp(r['check']) == chk
           and "entry_px" in r]
    if not out:
        return pd.DataFrame()
    return pd.DataFrame([_c87f._signal_row(r) for r in out])


def walk_ledger():
    """The delivered cycle87h stream."""
    return [dict(r) for r in _state().delivered]


# ------------------------------------------------- coordinator
def fetch_cycle87h_m15_frames(state=None):
    return _c87f.fetch_cycle87f_m15_frames(state)


def evaluate_cycle87h_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc,
                         m15_frames=m15_frames)


def select_cycle87h_entries(signals: pd.DataFrame,
                            open_symbols=()):
    return _c87f.select_cycle87f_entries(
        signals, open_symbols=open_symbols)
