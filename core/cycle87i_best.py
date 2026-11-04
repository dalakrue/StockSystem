"""cycle87i -- April: the ROUND 5 PHASE 2 form T4
over the shipped cycle87h stream (research verdict:
work_r5_sl3_10cyc/results/apr_VERDICT.md; validation
record: work_r5_validate9/results/
apr_t4_VALIDATION.md):

  DROP WORST DISC HOUR + EXPOSURE-SKIP 10% + CAP3:
  the cycle87h delivered stream with its 19 UTC
  rows never delivered, settled through a second
  realised-balance walk (START $80, formula lots at
  the carried N = 150/3). A pick is skipped when the
  open adverse exposure of kept picks (|pwv| x pv x
  lot, fixed at each pick's entry) plus the
  candidate's own would exceed 10% of the realised
  balance (designs.exposure_skip verbatim on the
  prior = the hour-dropped 87h stream). The walk's
  accounting outcome is the trade's
  stop-tightened-at-30p outcome -- the 87h form's
  own basis -- and each delivered pick's outcome is
  that outcome repriced at the SL <= 3xTP cap
  (core/r5v9_lib.ExposureLayerV9, mult 3.0 -- the
  form's own SL<=3 law).

Gate A (work_r5_validate9/results/apr_t4_gateA.json):
the shipped lib's transform + layer reproduce the
research candidate stream BIT-FOR-BIT (1,082 of
1,156 rows), array form and incremental layer
alike. DECLARED BASIS: April's stream rides the
declared POOL basis authorised by the user on
2026-11-03 for the 87g install; the T4 candidate
is graded on that same declared basis, stated
plainly in the validation record. Install
selection: April had three passers in the lane
(S18 4x, T9 3x, T4 3x); under the user-ordered
precedence (2026-11-04) an SL<=3 passer installs
over an SL<=4 passer, and within the 3x class the
highest AUDIT leftover installs -- T4 (87.97) over
T9 (84.95). Check hours (16,17,18,19) UTC = the
87f grid, unchanged. Carried N 150 unchanged. The
combined stream stays internalised; the registry
second slot stays empty. Live rows carry the
composition as a stop of min(shipped stop, 30
pips, 3 x shipped TP), re-simulated by the app's
exit engine.
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
from core import r5v9_lib as _V
from core.new8_candidate import CandidateContext, ensure_m15

CYCLE87I_CHECK_HOURS = _c87f.CYCLE87F_CHECK_HOURS
N_CARRIED = 150.0
SYSTEM_NAME = "cycle87i"
DROP_HOUR_UTC = 19

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


class _Form87I:
    """A cycle87g form (own E04 sidecar) settled
    through the 87h 6% exposure layer (walk_cap 30),
    whose delivered rows at hours other than 19 UTC
    are settled through the T4 10% exposure layer at
    the 3xTP cap. Persisted: both layer states, the
    mid (87h) stream, the delivered ledger and the
    filtered rows."""

    def __init__(self, path=None):
        self.path = path or _state_path()
        self.g_form = _c87g._Form87G(
            path=_sidecar('cycle87i_e04.json'))
        self.layer1 = _R.ExposureLayerR2(
            N_CARRIED / 3.0, 0.06, walk_cap=30.0)
        self.layer2 = _V.ExposureLayerV9(
            N_CARRIED / 3.0, 0.10, 3.0, walk_cap=30.0)
        self.mid = []
        self.delivered = []
        self.filtered = []
        self.hour_dropped = []
        self.fed1 = 0
        self.fed2 = 0
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
        self.mid = de(d.get('mid', []))
        self.delivered = de(d.get('delivered', []))
        self.filtered = de(d.get('filtered', []))
        self.hour_dropped = de(d.get('hour_dropped', []))
        self.fed1 = int(d.get('fed1', 0))
        self.fed2 = int(d.get('fed2', 0))
        for attr, lay in (('layer1', d.get('layer1', {})),
                          ('layer2', d.get('layer2', {}))):
            layer = getattr(self, attr)
            layer.bal = float(lay.get('bal', _R.START))
            layer.profit = float(lay.get('profit', 0.0))
            layer.open_kept = [(int(e), float(a)) for e, a in
                               lay.get('open_kept', [])]
            layer._pending_exits = [
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
                d.pop('_lrow2', None)
                for k in ('check', 'entry_time', 'exit_time'):
                    if d.get(k) is not None:
                        d[k] = pd.Timestamp(d[k]).isoformat()
                out.append(d)
            return out

        def lay(layer):
            return dict(
                bal=layer.bal, profit=layer.profit,
                open_kept=[[e, a] for e, a in
                           layer.open_kept],
                pending_exits=[[e, n, p, l] for e, n, p, l in
                               layer._pending_exits])
        data = dict(
            system=SYSTEM_NAME,
            mid=ser(self.mid),
            delivered=ser(self.delivered),
            filtered=ser(self.filtered),
            hour_dropped=ser(self.hour_dropped),
            fed1=self.fed1, fed2=self.fed2,
            layer1=lay(self.layer1), layer2=lay(self.layer2))
        with open(self.path, 'w') as fh:
            json.dump(data, fh)

    # ---------------------------------------------------- feed --
    def _lrow(self, r, m15_frames):
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
            net = float(r['gross_pips']) - _R.COST
        else:
            net = (float(prof[-1]) if len(prof) else 0.0)
        return {'entry_s': entry_s, 'exit_s': exit_s,
                'net': net,
                'pwv': float(prof.min()) if len(prof) else 0.0,
                'pv': pv,
                'tp': float(r['tp_pips_used']),
                'sl': float(r['sl_pips_used']),
                'prof': prof}

    def feed_new(self, m15_frames):
        """Stage 1: settle every not-yet-fed 87g kept
        row through the 87h 6% layer (the 87h stream).
        Stage 2: settle every not-yet-fed 87h row
        whose entry hour is not 19 UTC through the T4
        10% layer at the 3xTP cap (the 87i stream);
        19 UTC rows are the dropped hour -- recorded,
        never fed."""
        kept = list(self.g_form.state.kept)
        for r in kept[self.fed1:]:
            lrow = self._lrow(r, m15_frames)
            out = self.layer1.decide(lrow)
            if out is None:
                self.filtered.append(r)
            else:
                d = dict(r)
                d['gross_pips'] = float(out) + _R.COST
                d['sl_pips_used'] = min(
                    float(r['sl_pips_used']),
                    30.0,
                    4.0 * float(r['tp_pips_used']))
                d['_lrow2'] = lrow
                self.mid.append(d)
            self.fed1 += 1
        for d in self.mid[self.fed2:]:
            lrow = d.pop('_lrow2', None)
            if lrow is None:
                lrow = self._lrow(d, m15_frames)
            if (lrow['entry_s'] % 86400) // 3600 \
                    == DROP_HOUR_UTC:
                self.hour_dropped.append(d)
            else:
                out = self.layer2.decide(lrow)
                if out is None:
                    self.filtered.append(d)
                else:
                    dd = dict(d)
                    dd['gross_pips'] = float(out) + _R.COST
                    dd['sl_pips_used'] = min(
                        float(d['sl_pips_used']),
                        3.0 * float(d['tp_pips_used']))
                    self.delivered.append(dd)
            self.fed2 += 1


_STATE = None


def _state():
    global _STATE
    if _STATE is None:
        _STATE = _Form87I()
    return _STATE


def load_87i_state(path=None):
    if path is not None:
        return _Form87I(path=path)
    return _state()


def reset_form_state():
    """Remove the persisted 87i stream state (gate use)."""
    for p in (_state_path(), _sidecar('cycle87i_e04.json')):
        if os.path.exists(p):
            os.remove(p)


def is_cycle87i_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE87I_CHECK_HOURS and t.minute == 30


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full T4 entries for one check: the combined
    87e<-87s base entries settled through this form's
    87g (E04 + stop-30 + cap4) state, then the 6%
    exposure-skip (the 87h stream), then the
    hour-drop + 10% exposure-skip at the 3xTP cap --
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
    """The delivered cycle87i stream."""
    return [dict(r) for r in _state().delivered]


# ------------------------------------------------- coordinator
def fetch_cycle87i_m15_frames(state=None):
    return _c87f.fetch_cycle87f_m15_frames(state)


def evaluate_cycle87i_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc,
                         m15_frames=m15_frames)


def select_cycle87i_entries(signals: pd.DataFrame,
                            open_symbols=()):
    return _c87f.select_cycle87f_entries(
        signals, open_symbols=open_symbols)
