"""Cycle 86H -- March: the FIX-THE-BLOCKED lane's M1
repair of the Round-5 S18 form over the shipped
cycle86g stream (research verdicts:
work_fix_blocked/results/mar_s18_FIX.md and
mar_m1_VALIDATION.md):

  S18 = drop the incumbent stream's worst discovery
  hour (12 UTC) from the reference set, then PARTNER
  ADDITION: at any entry timestamp where the
  reference set keeps >= 1 pick, every other pool
  pick on a side the reference set keeps is added;
  outcomes are repriced at the SL <= 4 x TP cap
  (core.fixblocked_lib, Gate A bit-exact on the pool
  stream, 446 of 527 kept).
  M1 repair = the hour-12 excision does NOT apply to
  a base pick whose check timestamp (entry + 30 min)
  falls on the LAST calendar day of its month. In
  the historical stream this restores exactly one
  trade (EURAUD SELL, check 2022-03-31 12:30 UTC)
  and removes the single red holdout week
  (2022-W13) that blocked S18 at EC22 check 8_weeks;
  every other property of the form is unchanged.

Live feeding (same pattern as the shipped combined
forms): at each check the candidate group is the
cycle86c combined panel's picks at that check; each
row's base_keep is settled by stepping a private
cycle86g form instance (its own state namespace)
with the same frames -- the rows it delivers are
the reference set; the M1 group layer
(core.fixblocked_lib.GroupPartnerLayerM1) then
decides the delivered union. Inherited caveat (the
same class the cycle86f module documents): the
group is the panel's candidate surface at the
check; row identity between the panel surface and
the graded pool is by (symbol, direction, strategy)
at the check timestamp.

Check hours: the March grid (11, 16, 17 UTC),
unchanged from 86g. Sizing: carried N = 86 (full),
shipped at N/3, unchanged. March stays best-only.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

import core.cycle86c_best as _c86c
import core.cycle86g_best as _c86g
import core.cycle93w_best as _c93w
from core import d21rc_lib as _L
from core import fixblocked_lib as _F
from core.new8_candidate import default_state_path

CYCLE86H_CHECK_HOURS = _c86g.CYCLE86G_CHECK_HOURS
N_CARRIED = 86.0
SYSTEM_NAME = "cycle86h"
CARRIED_N = N_CARRIED / 3.0


class _Form86H:
    """The 86c panel group at each check, settled
    through a private 86g form (base_keep) and the
    M1 group partner layer. Persisted: the 86g
    sub-form's delivered identities per check (for
    idempotent replays) and this form's delivered
    ledger rows."""

    def __init__(self, path=None):
        self.path = path or default_state_path(SYSTEM_NAME)
        self.g_form = _c86g._Form86G(
            path=os.path.join(
                os.path.dirname(os.path.abspath(self.path)),
                'cycle86h_86g_state.json'))
        self.layer = _F.GroupPartnerLayerM1(1, False, 4.0)
        self.delivered = []
        self.processed = []
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
        self.delivered = d.get('delivered', [])
        self.processed = d.get('processed', [])

    def save(self):
        import json
        if not self.path:
            return
        os.makedirs(os.path.dirname(
            os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, 'w') as fh:
            json.dump({'delivered': self.delivered,
                       'processed': self.processed}, fh)

    # --------------------------------------------------- step --
    def step(self, frames, check_time_utc, m15_frames,
             open_symbols=()):
        chk = pd.Timestamp(check_time_utc)
        if str(chk) in self.processed:
            return [r for r in self.delivered
                    if pd.Timestamp(r['check']) == chk]
        # candidate group: the 86c combined panel
        entries = _c86c.panel_entries(
            frames, check_time_utc, m15_frames=m15_frames,
            open_symbols=open_symbols)
        if entries is not None \
                and entries.attrs.get('status'):
            return entries
        # reference set: the private 86g form's
        # deliveries at this check
        g_out = self.g_form.step(frames, check_time_utc,
                                 m15_frames,
                                 open_symbols=open_symbols)
        if isinstance(g_out, pd.DataFrame) \
                and g_out.attrs.get('status'):
            return g_out
        base_keys = set()
        if g_out is not None and len(g_out):
            for r in g_out:
                base_keys.add((
                    str(r.get('symbol')),
                    str(r.get('direction', ''))[:1].upper(),
                    str(r.get('strategy',
                              r.get('equation')))))
        out = []
        if entries is not None and len(entries):
            entry_s = int((chk - pd.Timedelta(
                minutes=30)).value // 10 ** 9)
            exit_s = entry_s + 48 * 3600
            rows, panel_rows = [], []
            for _, r in entries.iterrows():
                row = dict(r)
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
                key = (sym,
                       str(row['direction'])[:1].upper(),
                       str(row.get('strategy',
                                   row.get('equation'))))
                rows.append({
                    'entry_s': entry_s, 'exit_s': exit_s,
                    'side': 1 if dirsign > 0 else -1,
                    'base_keep': key in base_keys,
                    'net': float(row['gross_pips']) - 2.5
                    if row.get('gross_pips') is not None
                    else 0.0,
                    'pwv': float(prof.min())
                    if len(prof) else 0.0,
                    'pv': pv,
                    'tp': float(row['tp_pips_used']),
                    'sl': float(row['sl_pips_used']),
                    'prof': prof})
                panel_rows.append(row)
            res = self.layer.decide_group(rows)
            for row, net in zip(panel_rows, res):
                if net is None:
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
        _STATE = _Form86H()
    return _STATE


def load_86h_state(path=None):
    if path is not None:
        return _Form86H(path=path)
    return _state()


def is_cycle86h_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE86H_CHECK_HOURS and t.minute == 30


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
    """The delivered cycle86h stream (ledger rows)."""
    return [dict(r) for r in _state().delivered]


# ------------------------------------------------- coordinator
def fetch_cycle86h_m15_frames(state=None):
    return _c86g.fetch_cycle86g_m15_frames(state)


def evaluate_cycle86h_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc,
                         m15_frames=m15_frames)


def select_cycle86h_entries(signals: pd.DataFrame,
                            open_symbols=()):
    return _c86c.select_cycle86c_entries(
        signals, open_symbols=open_symbols)
