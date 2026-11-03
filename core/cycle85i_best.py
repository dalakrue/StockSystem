"""cycle85i -- February: the 10-CYCLE ROUND 2 lead
form R9 over the shipped cycle85g stream (research
verdict: work_10cyc_r2/results/feb_VERDICT.md;
validation record: work_r2_validate/results/
feb_VALIDATION.md):

  1. the cycle85g form itself (the 85f E09 stream
     settled through the D21-RC exposure-skip walk,
     stops capped at min(stop, 5 x TP)), stepped over
     the FULL 85g check grid (11, 13, 16 UTC) so the
     walk is the incumbent's own;
  2. CHECK-HOUR DROP: picks from the 11:30 UTC check
     are walked but NEVER delivered -- February runs
     on two checks, (13, 16) UTC = 19:30 / 22:30 MMT;
  3. RATIO CAP 4x: every delivered pick's stop is
     capped at min(stop, 4 x its target) and its gross
     repriced on the same M15-close profile
     (designs.stop_tighten_arr verbatim,
     core/r2val_lib).

Gate A (work_r2_validate/results/feb_gateA.json):
the shipped transform + layer reproduce the research
candidate stream BIT-FOR-BIT (432 of 684 pool rows),
array form and incremental layer alike, exact basis.
Carried N 104 unchanged, shipped at N/3. The
second-best slot stays empty, as under 85g.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

import core.cycle85e_best as _c85e
import core.cycle85f_best as _c85f
import core.cycle93w_best as _c93w
from core import d21rc_lib as _L
from core import r2val_lib as _R
from core.new8_candidate import default_state_path

CYCLE85G_HOURS = (11, 13, 16)
CYCLE85I_CHECK_HOURS = (13, 16)
N_CARRIED = 104.0
SYSTEM_NAME = "cycle85i"


def _sidecar(name):
    base = os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))
    return os.path.join(base, "data", "walk_ledgers_new8",
                        name)


class _Form85I:
    """The 85g composition (85f _FormState + D21-RC
    StreamLayer) under 85i sidecars, stepped over the
    full 85g grid in order; hour-11 output is walked,
    never delivered, and delivered rows are repriced
    at the 4x cap. Persisted: the 85f state (its
    sidecar), the layer state and the delivered
    ledger rows."""

    def __init__(self, path=None):
        self.path = path or default_state_path(SYSTEM_NAME)
        self.f_state = _c85f._FormState(
            path=_sidecar("cycle85i_form85f.json"))
        self.layer = _L.StreamLayer(N_CARRIED / 3.0)
        self.mask = _R.MaskLayerR2()
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
        lay = d.get("layer", {})
        self.layer.bal = float(lay.get("bal", _L.START))
        self.layer.profit = float(lay.get("profit", 0.0))
        self.layer.open_kept = [(int(e), float(a)) for e, a in
                                 lay.get("open_kept", [])]
        self.layer._pending_exits = [
            (int(e), float(n), float(p), float(l))
            for e, n, p, l in lay.get("pending_exits", [])]
        self.delivered = d.get("delivered", [])
        self.processed = d.get("processed", [])

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as fh:
            json.dump({"layer": {
                "bal": self.layer.bal,
                "profit": self.layer.profit,
                "open_kept": [[e, a] for e, a in
                              self.layer.open_kept],
                "pending_exits": [[e, n, p, l]
                                  for e, n, p, l in
                                  self.layer._pending_exits]},
                       "delivered": self.delivered,
                       "processed": self.processed}, fh)

    # --------------------------------------------------- step --
    def _step_one(self, frames, ts, m15_frames, open_symbols):
        """One 85g-grid check through the composition.
        Returns (status_frame_or_None, delivered_rows)
        where delivered_rows are the 85i (cap-4) rows if
        ts is a delivered hour, else []."""
        chk = pd.Timestamp(ts)
        entries = _c85e.panel_entries(
            frames, ts, m15_frames=m15_frames,
            open_symbols=open_symbols)
        if entries is not None and entries.attrs.get("status"):
            return entries, None
        ctxs = {}
        for sym, fr in frames.items():
            if fr is not None and len(fr):
                try:
                    ctxs[sym] = _c85f._win_ctx(sym, fr)
                except Exception:
                    pass
        kept = self.f_state.step(ctxs, ts, entries)
        out = []
        for r in kept:
            row = dict(r)
            ent = pd.Timestamp(row["entry_time"])
            ext = pd.Timestamp(row["exit_time"])
            sign = 1 if str(row["direction"]).upper() \
                .startswith("B") else -1
            bars = _c93w._bars(row["symbol"], m15_frames)
            prof = _L.profile_for_sym(
                row["symbol"], int(ent.timestamp()),
                int(ext.timestamp()),
                float(row["entry_px"]), sign, bars)
            majors = {p: _c93w._bars(p, m15_frames)
                      for p in _L.MAJORS}
            pv = _L.pip_value_per_lot(
                row["symbol"],
                _L.rates_at(majors, int(ext.timestamp())))
            net_out = self.layer.decide({
                "entry_s": int(ent.timestamp()),
                "exit_s": int(ext.timestamp()),
                "net": float(row["gross_pips"]) - _L.COST,
                "pwv": float(min(prof)) if len(prof) else 0.0,
                "pv": pv,
                "tp": float(row["tp_pips_used"]),
                "sl": float(row["sl_pips_used"]),
                "prof": prof})
            if net_out is None:
                continue
            if chk.hour not in CYCLE85I_CHECK_HOURS:
                continue  # walked, never delivered
            net4 = self.mask.decide({
                "entry_s": int(ent.timestamp()),
                "exit_s": int(ext.timestamp()),
                "net": float(net_out),
                "pwv": float(min(prof)) if len(prof) else 0.0,
                "pv": pv,
                "tp": float(row["tp_pips_used"]),
                "sl": float(row["sl_pips_used"]),
                "prof": prof})
            row["sl_pips_used"] = min(
                float(row["sl_pips_used"]),
                4.0 * float(row["tp_pips_used"]))
            row["gross_pips"] = float(net4) + _R.COST
            row["net_pips"] = float(net4)
            ser = dict(row)
            for k in ("check", "entry_time", "exit_time"):
                if k in ser:
                    ser[k] = str(ser[k])
            self.delivered.append(ser)
            out.append(row)
        self.processed.append(str(chk))
        self.save()
        return None, out

    def step(self, frames, check_time_utc, m15_frames,
             open_symbols=()):
        chk = pd.Timestamp(check_time_utc)
        if str(chk) in self.processed:
            return [r for r in self.delivered
                    if pd.Timestamp(r["check"]) == chk]
        result = []
        for h in CYCLE85G_HOURS:
            ts = chk.normalize() + pd.Timedelta(
                hours=h, minutes=30)
            if ts > chk:
                break
            if str(ts) in self.processed:
                if ts == chk:
                    result = [r for r in self.delivered
                              if pd.Timestamp(r["check"]) == chk]
                continue
            status, out = self._step_one(
                frames, ts, m15_frames, open_symbols)
            if status is not None:
                if ts == chk:
                    return status
                continue
            if ts == chk:
                result = out
        return result


_STATE = None


def _state():
    global _STATE
    if _STATE is None:
        _STATE = _Form85I()
    return _STATE


def load_85i_state(path=None):
    if path is not None:
        return _Form85I(path=path)
    return _state()


def reset_form_state():
    """Remove the persisted 85i stream state (gate use)."""
    for p in (default_state_path(SYSTEM_NAME),
              _sidecar("cycle85i_form85f.json")):
        if os.path.exists(p):
            os.remove(p)


def is_cycle85i_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE85I_CHECK_HOURS and t.minute == 30


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
    return pd.DataFrame([_c85f._signal_row(r) for r in kept])


def walk_ledger():
    """The delivered cycle85i stream (ledger rows)."""
    return [dict(r) for r in _state().delivered]


# ------------------------------------------------- coordinator
def fetch_cycle85i_m15_frames(state=None):
    return _c85f.fetch_cycle85f_m15_frames(state) \
        if hasattr(_c85f, "fetch_cycle85f_m15_frames") \
        else _c85e.fetch_cycle85e_m15_frames(state)


def evaluate_cycle85i_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc,
                         m15_frames=m15_frames)


def select_cycle85i_entries(signals: pd.DataFrame,
                            open_symbols=()):
    if signals is None or len(signals) == 0:
        return signals
    if signals.attrs.get("status"):
        return signals
    open_set = {str(s).upper() for s in (open_symbols or ())}
    if not open_set or "symbol" not in signals.columns:
        return signals
    return signals[~signals["symbol"].astype(str)
                   .str.upper().isin(open_set)]
