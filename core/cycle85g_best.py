"""cycle85g — February D21-RC (validate-and-replace lane,
2026-11-03): cycle85f's pick stream with the
robustness-fix D21-RC layer on top:

1. exposure-skip: an entry is skipped when the open
   adverse exposure plus the candidate's would exceed
   10% of the realised balance (formula walk at
   N = 104/3, start $80 — research lane
   designs.exposure_skip verbatim, core/d21rc_lib);
2. every assigned stop capped at min(stop, 5 x TP),
   repriced on the trade's M15-close floating profile
   (designs.stop_tighten_arr verbatim).

Validated 2026-11-03 (work_rob_validate/results/
feb_VALIDATION.md): Gate A exact replay bit-for-bit,
Section-9 PASS, LCT-middle PASS (P 87.73), EC22 18/18
raw 16/16 house, DSR 1.0, PBO 0.0%. Check hours
(11,13,16) UTC unchanged. Carried N 104 unchanged.
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
from core.new8_candidate import default_state_path

CYCLE85G_CHECK_HOURS = _c85f.CYCLE85F_CHECK_HOURS
N_CARRIED = 104.0
SYSTEM_NAME = "cycle85g"


def _sidecar(name):
    base = os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))
    return os.path.join(base, "data", "walk_ledgers_new8",
                        name)


class _Form85G:
    """A cycle85f _FormState (own sidecar state) settled
    through the D21-RC StreamLayer. Persisted: the 85f
    state (its sidecar), the layer state and the
    delivered ledger rows."""

    def __init__(self, path=None):
        self.path = path or default_state_path(SYSTEM_NAME)
        self.f_state = _c85f._FormState(
            path=_sidecar("cycle85g_form85f.json"))
        self.layer = _L.StreamLayer(N_CARRIED / 3.0)
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
    def step(self, frames, check_time_utc, m15_frames,
             open_symbols=()):
        chk = pd.Timestamp(check_time_utc)
        if str(chk) in self.processed:
            return [r for r in self.delivered
                    if pd.Timestamp(r["check"]) == chk]
        entries = _c85e.panel_entries(
            frames, check_time_utc, m15_frames=m15_frames,
            open_symbols=open_symbols)
        if entries is not None and entries.attrs.get("status"):
            return entries
        ctxs = {}
        for sym, fr in frames.items():
            if fr is not None and len(fr):
                try:
                    ctxs[sym] = _c85f._win_ctx(sym, fr)
                except Exception:
                    pass
        kept = self.f_state.step(ctxs, check_time_utc,
                                 entries)
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
            row["sl_pips_used"] = min(
                float(row["sl_pips_used"]),
                5.0 * float(row["tp_pips_used"]))
            row["gross_pips"] = net_out + _L.COST
            row["net_pips"] = net_out
            ser = dict(row)
            for k in ("check", "entry_time", "exit_time"):
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
        _STATE = _Form85G()
    return _STATE


def load_85g_state(path=None):
    if path is not None:
        return _Form85G(path=path)
    return _state()


def is_cycle85g_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE85G_CHECK_HOURS and t.minute == 30


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
    """The delivered D21-RC stream (ledger rows)."""
    return [dict(r) for r in _state().delivered]


# ------------------------------------------------- coordinator
def fetch_cycle85g_m15_frames(state=None):
    return _c85f.fetch_cycle85f_m15_frames(state) \
        if hasattr(_c85f, "fetch_cycle85f_m15_frames") \
        else _c85e.fetch_cycle85e_m15_frames(state)


def evaluate_cycle85g_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc,
                         m15_frames=m15_frames)


def select_cycle85g_entries(signals: pd.DataFrame,
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
