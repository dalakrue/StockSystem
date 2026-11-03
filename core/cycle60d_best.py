"""cycle60d — January DIFFWAY W1 (validate-and-replace
lane, 2026-11-03): the shipped cycle60c stream with ONE
change plus a tighter ratio cap:

1. design excision: picks of the design
   mom_AUDUSD_h13_momS_T0.75_A1.0_0.75x8 are never
   delivered. The excision is a pure mask over the
   60c delivered stream — the underlying D21-RC
   exposure walk still processes the excised design's
   picks (they occupied exposure and credited P&L in
   the incumbent walk, exactly as in the research
   lane), only their delivery is suppressed
   (core/dwval_lib);
2. every assigned stop capped at min(stop, 4 x TP)
   (was 5 x TP in 60c), repriced on the trade's
   M15-close floating profile.

Validated 2026-11-03 (work_diffway_validate/results/
jan_VALIDATION.md): Gate A exact replay bit-for-bit
(array + layer), exact ratio audit clean (post-cap
max ratio 4.000000), research: DD 80.73 -> 40.79,
worst pair -72.92 -> -33.29, injection 3/5 -> 6/9,
AUDIT net +802.05 -> +860.28. Check hours
(11,13,17) UTC unchanged. Carried N 83 unchanged.
The combined stream stays internalised (cycle60
contributes only at checks the best left silent), so
the registry second slot stays emptied.

Candidate enrichment is cycle60c's, verbatim: a pick's
ledger row (exit, gross) is simulated on the pick's
M15-close profile with the first-hit rule at its
assigned TP/SL and its hold cap.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

import core.cycle60_best as _c60
import core.cycle60b_best as _c60b
import core.cycle93w_best as _c93w
from core import d21rc_lib as _L
from core import dwval_lib as _DW
from core.new8_candidate import default_state_path

CYCLE60D_CHECK_HOURS = _c60.CYCLE60_CHECK_HOURS
N_CARRIED = 83.0
SYSTEM_NAME = "cycle60d"
BAR_S = 900


class _Form60D:
    """60b picks (or the cycle60 second's pick when the
    best is silent) settled through the D21-RC
    StreamLayer. Persisted: the layer state and the
    delivered ledger rows."""

    def __init__(self, path=None):
        self.path = path or default_state_path(SYSTEM_NAME)
        self.layer = _DW.StreamLayer4(N_CARRIED / 3.0)
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
    def _enrich(self, pick, chk, m15_frames):
        """Ledger row for one signal pick: first-hit exit
        on the M15-close profile at the assigned TP/SL."""
        ent = chk - pd.Timedelta(minutes=30)
        entry_s = int(ent.timestamp())
        hold_h = float(pick.get("hold_h", 48) or 48)
        cap_s = entry_s + int(hold_h * 3600)
        sign = 1 if str(pick["direction"]).upper() \
            .startswith("B") else -1
        bars = _c93w._bars(pick["symbol"], m15_frames)
        prof = _L.profile_for_sym(
            pick["symbol"], entry_s, cap_s,
            float(pick["entry_px"]), sign, bars)
        tp = float(pick["tp_pips"])
        sl = float(pick["sl_pips"])
        gross = float(prof[-1]) if len(prof) else 0.0
        exit_s = entry_s + (len(prof) - 1) * BAR_S \
            if len(prof) else cap_s
        for k in range(1, len(prof)):
            if prof[k] >= tp:
                gross, exit_s = tp, entry_s + k * BAR_S
                break
            if prof[k] <= -sl:
                gross, exit_s = -sl, entry_s + k * BAR_S
                break
        majors = {p: _c93w._bars(p, m15_frames)
                  for p in _L.MAJORS}
        pv = _L.pip_value_per_lot(
            pick["symbol"], _L.rates_at(majors, exit_s))
        return {"entry_s": entry_s, "exit_s": exit_s,
                "net": gross - _L.COST,
                "pwv": float(min(prof)) if len(prof) else 0.0,
                "pv": pv, "tp": tp, "sl": sl, "prof": prof,
                "gross": gross}

    def step(self, frames, check_time_utc, m15_frames,
             open_symbols=()):
        chk = pd.Timestamp(check_time_utc)
        if str(chk) in self.processed:
            return [r for r in self.delivered
                    if pd.Timestamp(r["check"]) == chk]
        sig = _c60b.evaluate_cycle60b_signals(
            frames, check_time_utc, m15_frames=m15_frames)
        if sig is not None and sig.attrs.get("status"):
            return sig
        picks = _c60b.select_cycle60b_entries(
            sig, open_symbols=open_symbols)
        if picks is None or not len(picks):
            sig2 = _c60.evaluate_cycle60_signals(
                frames, check_time_utc)
            picks = _c60.select_cycle60_entries(
                sig2, open_symbols=open_symbols)
        out = []
        if picks is not None and len(picks):
            for _, p in picks.iterrows():
                pick = dict(p)
                enr = self._enrich(pick, chk, m15_frames)
                net_out = self.layer.decide(enr)
                if net_out is None:
                    continue
                if _DW.is_vetoed_jan(pick.get("equation")):
                    continue
                row = {"check": chk,
                       "symbol": pick["symbol"],
                       "direction": pick["direction"],
                       "strategy": pick.get("equation"),
                       "score": float(pick.get("score", 0.0)),
                       "entry_time": pd.Timestamp(
                           enr["entry_s"], unit="s", tz="UTC"),
                       "exit_time": pd.Timestamp(
                           enr["exit_s"], unit="s", tz="UTC"),
                       "entry_px": float(pick["entry_px"]),
                       "tp_pips_used": enr["tp"],
                       "sl_pips_used": min(enr["sl"],
                                           4.0 * enr["tp"]),
                       "gross_pips": net_out + _L.COST,
                       "net_pips": net_out}
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
        _STATE = _Form60D()
    return _STATE


def load_60d_state(path=None):
    if path is not None:
        return _Form60D(path=path)
    return _state()


def is_cycle60d_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE60D_CHECK_HOURS and t.minute == 30


def _signal_row(r):
    return {"check": pd.Timestamp(r["check"]),
            "symbol": r["symbol"],
            "equation": r["strategy"],
            "direction": r["direction"],
            "score": float(r.get("score", 0.0)),
            "entry_px": float(r["entry_px"]),
            "tp_pips": float(r["tp_pips_used"]),
            "sl_pips": float(r["sl_pips_used"]),
            "signal_candle": pd.Timestamp(r["check"])
            - pd.Timedelta(hours=1, minutes=30),
            "entry_candle": pd.Timestamp(r["entry_time"])}


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
    return pd.DataFrame([_signal_row(r) for r in kept])


def walk_ledger():
    """The delivered D21-RC stream (ledger rows)."""
    return [dict(r) for r in _state().delivered]


# ------------------------------------------------- coordinator
def fetch_cycle60d_m15_frames(state=None):
    try:
        return _c60b.fetch_cycle60b_m15_frames(state)
    except TypeError:
        return _c60b.fetch_cycle60b_m15_frames()


def evaluate_cycle60d_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc,
                         m15_frames=m15_frames)


def select_cycle60d_entries(signals: pd.DataFrame,
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
