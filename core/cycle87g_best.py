"""cycle87g -- April: the SL4-10CYC round's D6 form
over the shipped cycle87f stream (research verdict:
work_sl4_10cyc/results/apr_VERDICT.md; validation
record: work_sl4_validate/results/apr_VALIDATION.md).
This module is built FRESH for D6; it replaces the
never-registered riskopt5-C4 (stop-60) local port of
the same name -- different form, do not confuse them.

  1. stop-tighten 30p: if a trade's gross floating
     path reaches -30 before its outcome point, it
     exits at -30 (designs.stop_tighten verbatim,
     core/sl4v_lib.Stop30CapLayer);
  2. every trade's assigned stop then capped at
     min(stop, 4 x TP) as the final step, repriced on
     the same profile (designs.stop_tighten_arr
     verbatim).

Gate A (work_sl4_validate/results/apr_gateA.json): the
shipped lib's decision functions reproduce the research
candidate stream BIT-FOR-BIT (all 1,156 rows), array
form and incremental layer alike. DECLARED BASIS:
April has no complete exact per-trade TP/SL basis --
exact reconstruction was attempted in the validation
lane and covers only 1,108 of 1,156 rows (48 pvote-era
rows unrecoverable) -- so the research stream, this
port's historical replay, and the ratio audit carry
the declared POOL basis (stageA.ratio_screen_arrays
group stand-ins; the lib derives a row's pool stamps
from its own gross via the baked group medians). The
pool substitute was authorised by the user on
2026-11-03 (work_sl4_validate GATES Amendment 1) for
this candidate. Live rows carry the composition as a
stop of min(shipped stop, 30 pips, 4 x shipped TP),
re-simulated by the app's exit engine.
Check hours (16,17,18,19) UTC = the 87f grid,
unchanged. Carried N 150 unchanged. The combined
stream stays internalised; the registry second slot
stays empty.
"""
from __future__ import annotations

import pandas as pd

import core.cycle87f_best as _c87f
from core import sl4v_lib as _S
from core.new8_candidate import CandidateContext, ensure_m15

CYCLE87G_CHECK_HOURS = _c87f.CYCLE87F_CHECK_HOURS
N_CARRIED = 150.0
SYSTEM_NAME = "cycle87g"

_DESIGN_SYMBOLS = _c87f._DESIGN_SYMBOLS
POOL_DESIGNS = _c87f.POOL_DESIGNS


def _sidecar(name):
    import os
    from core.new8_candidate import default_state_path
    p = default_state_path(SYSTEM_NAME)
    return os.path.join(os.path.dirname(
        os.path.abspath(p)), name)


class _Form87G:
    """87f's E04 state (own sidecar) whose delivered
    rows carry the D6 stop composition."""

    def __init__(self, path=None):
        self.state = _c87f.AprE04State(
            path=path or _sidecar('cycle87g_e04.json'))
        self.layer = _S.Stop30CapLayer()

    def save(self):
        return self.state.save()


_STATE = None


def _state():
    global _STATE
    if _STATE is None:
        _STATE = _Form87G()
    return _STATE


def load_87g_state(path=None):
    if path is not None:
        return _Form87G(path=path)
    return _state()


def is_cycle87g_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE87G_CHECK_HOURS and t.minute == 30


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full D6 entries for one check: the combined
    87e<-87s base entries settled through this form's
    E04 state (PCOL + CONS3, as 87f), then each kept
    row's stop composed to min(stop, 30 pips, 4 x TP)
    -- the live expression of stop-tighten 30p + the
    SL <= 4 cap (Gate A proves the lib transform on the
    canonical stream)."""
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
    kept = form.state.step(ctx, chk, base_rows)
    form.save()
    out = []
    for r in kept:
        if "entry_px" not in r:
            continue
        d = dict(r)
        d["sl_pips_used"] = min(float(r["sl_pips_used"]),
                                _S.APR_STOP_PIPS,
                                4.0 * float(r["tp_pips_used"]))
        out.append(d)
    if not out:
        return pd.DataFrame()
    return pd.DataFrame([_c87f._signal_row(r) for r in out])


def walk_ledger():
    """The delivered cycle87g stream (kept E04 rows)."""
    return [dict(r) for r in _state().state.kept]


# ------------------------------------------------- coordinator
def fetch_cycle87g_m15_frames(state=None):
    return _c87f.fetch_cycle87f_m15_frames(state)


def evaluate_cycle87g_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc,
                         m15_frames=m15_frames)


def select_cycle87g_entries(signals: pd.DataFrame,
                            open_symbols=()):
    return _c87f.select_cycle87f_entries(
        signals, open_symbols=open_symbols)
