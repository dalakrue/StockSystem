"""cycle94h — December D21-RC (validate-and-replace lane,
2026-11-03): the shipped combined December stream
(cycle94g E03 + cycle94s second, standing combined
delivery) with the robustness-fix D21-RC layer on top:

1. exposure-skip: an entry is skipped when the open
   adverse exposure plus the candidate's would exceed
   10% of the realised balance (formula walk at
   N = 150/3, start $80 — research lane
   designs.exposure_skip verbatim, core/d21rc_lib);
2. every assigned stop capped at min(stop, 5 x TP),
   repriced on the trade's M15-close floating profile
   (designs.stop_tighten_arr verbatim).

Validated 2026-11-03 (work_rob_validate/results/
dec_VALIDATION.md): Gate A exact replay bit-for-bit,
Section-9 PASS, LCT-middle PASS, EC22 18/18 raw 16/16
house, DSR 1.0, PBO 0.0%. The combined stream is
internalised (94s contributes only at checks the best
left silent, incl. the 14:00 UTC fourth slot), so the
registry second slot is emptied, April-87f precedent.
Check hours (10,11,13,14) UTC = the incumbent combined
grid, unchanged. Carried N 150 unchanged.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

import core.cycle93w_best as _c93w
import core.cycle94e_best as _c94e
import core.cycle94f_best as _c94f
import core.cycle94g_best as _c94g
import core.cycle94s_best as _c94s
from core import d21rc_lib as _L
from core.new8_candidate import (CandidateContext,
                                 default_state_path,
                                 ensure_m15)

CYCLE94H_CHECK_HOURS = (10, 11, 13, 14)
N_CARRIED = 150.0
SYSTEM_NAME = "cycle94h"

_DESIGN_SYMBOLS = _c94g._DESIGN_SYMBOLS
_POOL_DESIGN_NAMES = _c94g.POOL_DESIGN_NAMES
_SECOND_DESIGN = _c94s.DESIGN


def _sidecar(name):
    base = os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))
    return os.path.join(base, "data", "walk_ledgers_new8",
                        name)


def _dirsign(r):
    d = str(r.get("direction", "")).upper()
    if d == "BUY":
        return 1
    if d == "SELL":
        return -1
    g = float(r.get("gross_pips", 0.0))
    mv = float(r.get("exit_px", 0.0)) - float(r.get("entry_px", 0.0))
    s = np.sign(g) * np.sign(mv)
    return int(s) if s != 0 else 1


class _Form94H:
    """DecE03State (own sidecar state) + the 94s second
    (combined-delivery merge) settled through the D21-RC
    StreamLayer. Persisted: the E03 state (its sidecar),
    the layer state and the delivered ledger rows."""

    def __init__(self, path=None):
        self.path = path or default_state_path(SYSTEM_NAME)
        self.e03 = _c94g.DecE03State(
            path=_sidecar("cycle94h_e03.json"))
        self.e03.form94 = _c94g._FormState(
            path=_sidecar("cycle94h_form94.json"))
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
    def _candidate(self, r, m15map):
        ent = pd.Timestamp(r["entry_time"])
        ext = pd.Timestamp(r["exit_time"])
        sign = _dirsign(r)
        bars = _c93w._bars(r["symbol"], m15map)
        prof = _L.profile_for_sym(
            r["symbol"], int(ent.timestamp()),
            int(ext.timestamp()), float(r["entry_px"]),
            sign, bars)
        majors = {p: _c93w._bars(p, m15map)
                  for p in _L.MAJORS}
        pv = _L.pip_value_per_lot(
            r["symbol"], _L.rates_at(majors,
                                     int(ext.timestamp())))
        return {
            "entry_s": int(ent.timestamp()),
            "exit_s": int(ext.timestamp()),
            "net": float(r["gross_pips"]) - 2.5,
            "pwv": float(min(prof)) if len(prof) else 0.0,
            "pv": pv,
            "tp": float(r["tp_pips_used"]),
            "sl": float(r["sl_pips_used"]),
            "prof": prof}

    def step(self, frames, check_time_utc, m15_frames,
             open_symbols=()):
        chk = pd.Timestamp(check_time_utc)
        if str(chk) in self.processed:
            return [r for r in self.delivered
                    if pd.Timestamp(r["check"]) == chk]
        entries = pd.DataFrame()
        if chk.hour in _c94g.CYCLE94G_CHECK_HOURS:
            entries = _c94e.panel_entries(
                frames, check_time_utc, m15_frames=m15_frames,
                open_symbols=open_symbols)
            if entries is not None \
                    and entries.attrs.get("status"):
                return entries
        m15map = ensure_m15(m15_frames, _DESIGN_SYMBOLS)
        ctxs = {}
        for sym, fr in frames.items():
            if fr is not None and len(fr):
                try:
                    ctxs[sym] = _c94g._win_ctx(
                        sym, fr, m15map.get(sym))
                except Exception:
                    pass
        cand_rows = []
        if chk.hour in _c94g.CYCLE94G_CHECK_HOURS:
            base_rows = self.e03.form94.step(
                ctxs, check_time_utc, entries)
            ctx = CandidateContext(frames, m15map,
                                   _POOL_DESIGN_NAMES)
            cand_rows = self.e03.step(ctx, check_time_utc,
                                      base_rows)
            self.e03.save()
        if not cand_rows:
            # combined delivery: the second contributes only
            # when the best is silent at this check
            ctx2 = CandidateContext(frames, m15map,
                                    (_SECOND_DESIGN,))
            rows = ctx2.rows_at(_SECOND_DESIGN, chk)
            open_set = {str(s).upper()
                        for s in (open_symbols or ())}
            rows = [r for r in rows
                    if str(r["symbol"]).upper() not in open_set]
            if rows:
                rows.sort(key=lambda r: -float(r["score"]))
                cand_rows = [rows[0]]
        out = []
        for r in cand_rows:
            row = dict(r)
            row.setdefault("check", chk)
            if row.get("entry_time") is None:
                row["entry_time"] = chk - pd.Timedelta(
                    minutes=30)
            net_out = self.layer.decide(
                self._candidate(row, m15map))
            if net_out is None:
                continue
            row["sl_pips_used"] = min(
                float(row["sl_pips_used"]),
                5.0 * float(row["tp_pips_used"]))
            row["gross_pips"] = net_out + _L.COST
            row["net_pips"] = net_out
            ser = dict(row)
            for k in ("check", "entry_time", "exit_time"):
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
        _STATE = _Form94H()
    return _STATE


def load_94h_state(path=None):
    if path is not None:
        return _Form94H(path=path)
    return _state()


def is_cycle94h_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE94H_CHECK_HOURS and t.minute == 30


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
    return pd.DataFrame([_c94f._signal_row(r) for r in kept])


def walk_ledger():
    """The delivered D21-RC stream (ledger rows)."""
    return [dict(r) for r in _state().delivered]


# ------------------------------------------------- coordinator
def fetch_cycle94h_m15_frames(state=None):
    return _c94g.fetch_cycle94g_m15_frames(state)


def evaluate_cycle94h_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc,
                         m15_frames=m15_frames)


def select_cycle94h_entries(signals: pd.DataFrame,
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
