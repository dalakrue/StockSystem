"""cycle94i — December risk-reduction tranche C2
(work_riskopt5, validate-and-replace lane
work_riskopt5_validate, 2026-11-03): the shipped
cycle94h stream (94g+94s combined + D21-RC layer)
with the tranche's C2 surgery on top:

1. cluster-skip 12h: an entry delivered by the 94h
   layer is skipped when a KEPT trade sharing a
   currency (base or quote) opened within the
   previous 12 hours (designs.cluster_skip verbatim,
   core/riskopt5_lib.ClusterLayer);
2. every kept trade's assigned stop capped at
   min(stop, 4 x TP), repriced on the trade's
   M15-close floating profile from the RAW outcome
   (designs.stop_tighten_arr verbatim) — the exact
   per-trade basis.

Gate A (work_riskopt5_validate/results/dec_gateA.json):
the shipped lib's decision functions reproduce the
research candidate stream BIT-FOR-BIT (464 of 1,252
kept), array form and incremental layer alike.
Check hours (10,11,13,14) UTC = the 94h combined
grid, unchanged. Carried N 150 unchanged. The
combined stream stays internalised; the registry
second slot stays empty.
"""
from __future__ import annotations

import json
import os

import pandas as pd

import core.cycle94e_best as _c94e
import core.cycle94g_best as _c94g
import core.cycle94h_best as _c94h
from core import d21rc_lib as _L
from core import riskopt5_lib as _R
from core.new8_candidate import CandidateContext, \
    default_state_path, ensure_m15

CYCLE94I_CHECK_HOURS = _c94h.CYCLE94H_CHECK_HOURS
N_CARRIED = 150.0
SYSTEM_NAME = "cycle94i"

_DESIGN_SYMBOLS = _c94h._DESIGN_SYMBOLS
_POOL_DESIGN_NAMES = _c94h._POOL_DESIGN_NAMES
_SECOND_DESIGN = _c94h._SECOND_DESIGN


class _Form94I:
    """94h's composed base (E03 state + 94s second +
    D21-RC StreamLayer, in _Form94H) settled through
    the tranche ClusterLayer. Persisted: the 94h form
    state (its own sidecar via _Form94H with the 94i
    state path), the cluster layer's kept history and
    the delivered ledger rows."""

    def __init__(self, path=None):
        self.path = path or default_state_path(SYSTEM_NAME)
        self.base = _c94h._Form94H(
            path=_c94h._sidecar("cycle94i_94h.json"))
        self.base.e03 = _c94g.DecE03State(
            path=_c94h._sidecar("cycle94i_e03.json"))
        self.base.e03.form94 = _c94g._FormState(
            path=_c94h._sidecar("cycle94i_form94.json"))
        self.cluster = _R.ClusterLayer()
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
        self.cluster.kept = [
            (int(e), (str(c[0]), str(c[1])))
            for e, c in d.get("cluster_kept", [])]
        self.delivered = d.get("delivered", [])
        self.processed = d.get("processed", [])

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as fh:
            json.dump({
                "cluster_kept": [[e, list(c)]
                                 for e, c in self.cluster.kept],
                "delivered": self.delivered,
                "processed": self.processed}, fh)

    # --------------------------------------------------- step --
    def step(self, frames, check_time_utc, m15_frames,
             open_symbols=()):
        chk = pd.Timestamp(check_time_utc)
        if str(chk) in self.processed:
            return [r for r in self.delivered
                    if pd.Timestamp(r["check"]) == chk]
        # Candidate generation identical to _Form94H.step
        # (94g E03 + 94s combined merge), then BOTH layers
        # decide on the RAW candidate: the D21-RC layer
        # first (the shipped 94h keep decision), then the
        # cluster layer, whose cap-4 repricing runs from
        # the raw outcome in a single step — exactly the
        # research composition Gate A proved bit-exact.
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
            base_rows = self.base.e03.form94.step(
                ctxs, check_time_utc, entries)
            ctx = CandidateContext(frames, m15map,
                                   _POOL_DESIGN_NAMES)
            cand_rows = self.base.e03.step(
                ctx, check_time_utc, base_rows)
            self.base.e03.save()
        if not cand_rows:
            ctx2 = CandidateContext(frames, m15map,
                                    (_SECOND_DESIGN,))
            rows = ctx2.rows_at(_SECOND_DESIGN, chk)
            open_set = {str(s).upper()
                        for s in (open_symbols or ())}
            rows = [r for r in rows
                    if str(r["symbol"]).upper()
                    not in open_set]
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
            cand = self.base._candidate(row, m15map)
            if self.base.layer.decide(cand) is None:
                continue
            net_out = self.cluster.decide({
                "entry_s": cand["entry_s"],
                "sym": str(row["symbol"]),
                "net": cand["net"],
                "tp": cand["tp"], "sl": cand["sl"],
                "prof": cand["prof"]})
            if net_out is None:
                continue
            row["sl_pips_used"] = min(
                float(row["sl_pips_used"]),
                4.0 * float(row["tp_pips_used"]))
            row["gross_pips"] = net_out + _R.COST
            row["net_pips"] = net_out
            ser = dict(row)
            for k in ("check", "entry_time", "exit_time"):
                if k in ser:
                    ser[k] = str(ser[k])
            self.delivered.append(ser)
            out.append(row)
        self.base.save()
        self.processed.append(str(chk))
        self.save()
        return out


_STATE = None


def _state():
    global _STATE
    if _STATE is None:
        _STATE = _Form94I()
    return _STATE


def load_94i_state(path=None):
    if path is not None:
        return _Form94I(path=path)
    return _state()


def is_cycle94i_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE94I_CHECK_HOURS and t.minute == 30


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
    import core.cycle94f_best as _c94f
    return pd.DataFrame([_c94f._signal_row(r) for r in kept])


def walk_ledger():
    """The delivered cycle94i stream (ledger rows)."""
    return [dict(r) for r in _state().delivered]


# ------------------------------------------------- coordinator
def fetch_cycle94i_m15_frames(state=None):
    return _c94g.fetch_cycle94g_m15_frames(state)


def evaluate_cycle94i_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc,
                         m15_frames=m15_frames)


def select_cycle94i_entries(signals: pd.DataFrame,
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
