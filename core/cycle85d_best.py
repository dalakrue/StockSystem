"""Cycle 85D (R2 A16+X12 combined) -- February system,
integrated 2026-10-30 from 20-Cycle Round R2
(feb_planB_s1.md + addenda, feb_combined_best_s1.md).

Definition: cycle85c (the shipped February A16 stack:
FB_EURUSD_h16_1 slot veto with fall-through over the frozen
cycle85b selection, plus the PLANB cand2 partner design
'feb_p38' merged second-priority) PLUS the X12 cascade as a
second-priority fill layer:

  * The cascade is a UNION of 11 prior Feb mined designs,
    walked single-pick at the best's own check times with
    priority by marginal combined quality (the X12 order):
    feb_p38 > feb_e19 > feb_b9cp14 > feb_e07 > feb_b9sb >
    feb_b9sbpc > feb_b9c06 > feb_p07 > feb_b9c03 > feb_b9p13
    > feb_b9cc03. Each design keeps its own walk157 walk
    (score order, own symbol occupancy, own veto); at each
    check the cascade takes AT MOST ONE pick -- the first
    design pick (in cascade priority) whose symbol is not
    open in the cascade's own taken intervals.
  * A cascade pick becomes a FILL only under the research
    combine rules against the A16 base (the vetoed cycle85b
    base entries plus accepted feb_p38 partner picks):
    the base must be silent at that check and the pick's
    symbol interval must not overlap any base row or any
    already-accepted fill.
  * DOLLARIDX rows are occupancy-only throughout: they walk
    inside their designs and inside the cascade's taken
    intervals exactly as in research, but are NEVER emitted
    as trades (this system trades no dollar-index symbol).
    The research combined ledger (631 picks) carries 8
    DOLLARIDX fill rows; the module form therefore emits
    the remaining 623 picks, set-identical to the research
    combined ledger on every non-dollar pick (gated).

Requires the DESIGNS entries from designs_feb.py
(feb_p07, feb_e07, feb_e19, feb_b9c03, feb_b9c06, feb_b9p13,
feb_b9cc03, feb_b9cp14, feb_b9sb, feb_b9sbpc) folded into
core/new8_designs.py alongside the existing feb_p38.

Validated numbers (research combined ledger, replayed
EXACT on the app machinery 2026-10-30 -- all 14 pool design
walks exact, X12 standalone 576/576 exact, combined
631/631 exact): DISC n501 net +7004.02, leftover 83.88%
(incumbent 76.90%); AUDIT n130 net +663.88, leftover
42.28% (incumbent 37.28%, strictly greater); LCT vs
incumbent P 96.54% / q05 81.62% (middle + strict PASS);
MC verbatim flag TRUE (DD p95 202.99 vs own cap 226.07);
PBO 0.00% / DSR 1.0000 (stated family of 22); decay
WEAKENED = the incumbent's own class. Best N unchanged
(104, as cycle85c).
"""

from __future__ import annotations

import json
import os

import pandas as pd

import core.cycle85c_best as _c85c
from core.cycle85b_best import (CYCLE85B_CHECK_HOURS,
                                is_cycle85b_check_time)
from core.new8_candidate import MergedWalkState, default_state_path
from core.new8_designs import DESIGNS
from core.new8_walk import DesignWalk

CYCLE85D_CHECK_HOURS = CYCLE85B_CHECK_HOURS
PARTNER_DESIGNS = ("feb_p38",)
CASCADE_DESIGNS = ("feb_p38", "feb_e19", "feb_b9cp14",
                   "feb_e07", "feb_b9sb", "feb_b9sbpc",
                   "feb_b9c06", "feb_p07", "feb_b9c03",
                   "feb_b9p13", "feb_b9cc03")
SYSTEM_NAME = "cycle85d"


def evaluate_cycle85d_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the cycle85c signals (the A16 veto acts
    in selection)."""
    return _c85c.evaluate_cycle85c_signals(
        frames, check_time_utc, m15_frames=m15_frames)


def select_cycle85d_entries(signals: pd.DataFrame,
                            open_symbols=(),
                            live_count: int = 0,
                            m15_frames: dict | None = None,
                            check_time_utc=None) -> pd.DataFrame:
    """Base selection: the cycle85c selection verbatim."""
    return _c85c.select_cycle85c_entries(
        signals, open_symbols=open_symbols,
        live_count=live_count, m15_frames=m15_frames,
        check_time_utc=check_time_utc)


def is_cycle85d_check_time(ts) -> bool:
    return is_cycle85b_check_time(ts)


# ==================================================== cascade --
class X12CascadeState:
    """Persisted X12 cascade state.

    walks: one DesignWalk per cascade design (each design's
    own walk157 occupancy + veto, advanced at EVERY check
    whether or not its pick is used -- the research pool
    ledgers are standalone walks).
    taken: the cascade's standalone picks (walk_sb rule: at
    most one per check, cascade priority, symbol not open in
    taken). Dropped-at-merge picks still occupy `taken`,
    exactly as in research.
    fills: the subset of taken picks accepted by the combine
    rules against the A16 base.
    """

    def __init__(self, design_names=CASCADE_DESIGNS):
        self.design_names = list(design_names)
        self.walks = {n: DesignWalk(DESIGNS[n]["equations"],
                                    veto=DESIGNS[n]["veto"])
                      for n in self.design_names}
        self.taken = []
        self.fills = []

    # ------------------------------------------------ persist --
    @staticmethod
    def _ser(rows):
        out = []
        for r in rows:
            d = dict(r)
            for k in ("check", "entry_time", "exit_time"):
                if d.get(k) is not None:
                    d[k] = pd.Timestamp(d[k]).isoformat()
            out.append(d)
        return out

    @staticmethod
    def _de(rows):
        out = []
        for r in rows:
            d = dict(r)
            for k in ("check", "entry_time", "exit_time"):
                if d.get(k) is not None:
                    d[k] = pd.Timestamp(d[k])
            out.append(d)
        return out

    def to_dict(self):
        return {
            "taken": self._ser(self.taken),
            "fills": self._ser(self.fills),
            "walks": {n: {"picks": self._ser(w.picks),
                          "open_exit": {
                              s: [pd.Timestamp(x).isoformat()
                                  for x in xs]
                              for s, xs in w.open_exit.items()}}
                      for n, w in self.walks.items()},
        }

    def load_dict(self, data):
        self.taken = self._de(data.get("taken", []))
        self.fills = self._de(data.get("fills", []))
        for n, wd in (data.get("walks") or {}).items():
            if n not in self.walks:
                continue
            self.walks[n].picks = self._de(wd.get("picks", []))
            self.walks[n].open_exit = {
                s: [pd.Timestamp(x) for x in xs]
                for s, xs in (wd.get("open_exit") or {}).items()}

    # --------------------------------------------------- step --
    def step(self, ctx, check, base_checks, base_intervals):
        """base_checks: set of checks the A16 base occupies.
        base_intervals: {symbol: [(entry_time, exit_time)]}
        over ALL recorded A16 base rows (partner DOLLARIDX
        rows excluded -- the research A16 ledger excludes
        them, so they do not busy the merge)."""
        chk = pd.Timestamp(check)
        ent = chk - pd.Timedelta(minutes=30)
        # 1) advance every design walk; collect picks in
        #    cascade priority order.
        picks = []
        for name in self.design_names:
            rows = ctx.rows_at(name, chk)
            pick = self.walks[name].step(chk, rows)
            if pick is not None:
                picks.append(pick)
        # 2) walk_sb rule: first pick whose symbol is not
        #    open in the cascade's taken intervals.
        open_syms = {r["symbol"] for r in self.taken
                     if pd.Timestamp(r["exit_time"]) > ent}
        cand = None
        for pick in picks:
            if pick["symbol"] in open_syms:
                continue
            cand = pick
            break
        if cand is None:
            return None
        self.taken.append(dict(cand))
        # 3) combine rules vs the A16 base + accepted fills.
        if chk in base_checks:
            return None
        if str(cand["symbol"]) == "DOLLARIDX":
            return None  # occupancy-only; never emitted
        ex = pd.Timestamp(cand["exit_time"])

        def _ov(intervals):
            return any(e < ex and ent < x for e, x in intervals)

        if _ov(base_intervals.get(cand["symbol"], [])):
            return None
        fill_iv = {}
        for r in self.fills:
            fill_iv.setdefault(r["symbol"], []).append(
                (pd.Timestamp(r["entry_time"]),
                 pd.Timestamp(r["exit_time"])))
        if _ov(fill_iv.get(cand["symbol"], [])):
            return None
        fill = dict(cand)
        self.fills.append(fill)
        return fill


class Cycle85dState:
    """The full 85D persisted state: the A16 partner layer
    (a MergedWalkState over feb_p38, as in cycle85c) plus
    the X12 cascade state, in one JSON document."""

    def __init__(self, path=None):
        self.path = path or default_state_path(SYSTEM_NAME)
        self.partner = MergedWalkState(
            SYSTEM_NAME, PARTNER_DESIGNS, path=None)
        self.cascade = X12CascadeState()

    def save(self):
        os.makedirs(os.path.dirname(
            os.path.abspath(self.path)), exist_ok=True)
        def ser(rows):
            out = []
            for r in rows:
                d = dict(r)
                for k in ("check", "entry_time", "exit_time"):
                    if d.get(k) is not None:
                        d[k] = pd.Timestamp(d[k]).isoformat()
                out.append(d)
            return out

        data = {
            "system": SYSTEM_NAME,
            "incumbent_picks": ser(self.partner.incumbent_picks),
            "accepted": ser(self.partner.accepted),
            "partner_walks": {
                n: {"picks": ser(w.picks),
                    "open_exit": {
                        s: [pd.Timestamp(x).isoformat()
                            for x in xs]
                        for s, xs in w.open_exit.items()}}
                for n, w in self.partner.walks.items()},
            "cascade": self.cascade.to_dict(),
        }
        with open(self.path, "w") as fh:
            json.dump(data, fh)
        return self.path

    @classmethod
    def load(cls, path=None):
        p = path or default_state_path(SYSTEM_NAME)
        with open(p) as fh:
            data = json.load(fh)
        st = cls(path=p)

        def de(rows):
            out = []
            for r in rows:
                d = dict(r)
                for k in ("check", "entry_time", "exit_time"):
                    if d.get(k) is not None:
                        d[k] = pd.Timestamp(d[k])
                out.append(d)
            return out

        st.partner.incumbent_picks = de(
            data.get("incumbent_picks", []))
        st.partner.accepted = de(data.get("accepted", []))
        for n, wd in (data.get("partner_walks") or {}).items():
            if n not in st.partner.walks:
                continue
            st.partner.walks[n].picks = de(wd.get("picks", []))
            st.partner.walks[n].open_exit = {
                s: [pd.Timestamp(x) for x in xs]
                for s, xs in (wd.get("open_exit") or {}).items()}
        st.cascade.load_dict(data.get("cascade", {}))
        return st

    # --------------------------------------------------- step --
    def base_view(self):
        """(checks, intervals) of the recorded A16 base for
        the combine test: incumbent entries + accepted
        partner picks, partner DOLLARIDX rows excluded
        (the research A16 ledger excludes them)."""
        checks = set()
        intervals = {}
        rows = list(self.partner.incumbent_picks) + [
            r for r in self.partner.accepted
            if str(r["symbol"]) != "DOLLARIDX"]
        for r in rows:
            checks.add(pd.Timestamp(r["check"]))
            intervals.setdefault(r["symbol"], []).append(
                (pd.Timestamp(r["entry_time"]),
                 pd.Timestamp(r["exit_time"])))
        return checks, intervals

    def step(self, ctx, check, incumbent_entries):
        """One check: partner layer first (records the base
        entries, merges feb_p38), then the cascade fill.
        Returns (partner_picks, fill_or_None)."""
        partner_picks = self.partner.step(
            ctx, check, incumbent_entries)
        checks, intervals = self.base_view()
        fill = self.cascade.step(ctx, check, checks, intervals)
        return partner_picks, fill


def load_state():
    try:
        return Cycle85dState.load()
    except Exception:
        return Cycle85dState()


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check: the vetoed
    cycle85b base entries, plus accepted feb_p38 partner
    picks, plus at most one X12 cascade fill -- settled
    through this system's persisted state."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row)
    from core.new8_features import frame_to_research
    from core.new8_walk import ohlc_from_frame
    sig = evaluate_cycle85d_signals(frames, check_time_utc,
                                    m15_frames=m15_frames)
    if sig is not None and len(sig) == 0 \
            and sig.attrs.get("status"):
        return sig
    entries = select_cycle85d_entries(
        sig, open_symbols=open_symbols,
        live_count=len({str(s).upper()
                        for s in (open_symbols or ())}),
        m15_frames=m15_frames, check_time_utc=check_time_utc)
    if entries is None:
        entries = pd.DataFrame()
    state = load_state()
    ctx = CandidateContext(
        frames, m15_frames,
        PARTNER_DESIGNS + tuple(
            n for n in CASCADE_DESIGNS if n not in PARTNER_DESIGNS))
    for sym, fr in ctx.frames.items():
        if sym not in ctx.ohlc and fr is not None and len(fr):
            try:
                rfr, _ = frame_to_research(fr)
                ctx.ohlc[sym] = ohlc_from_frame(rfr)
            except Exception:
                pass
    partner_picks, fill = state.step(ctx, check_time_utc,
                                     entries)
    state.save()
    extra_rows = [r for r in partner_picks
                  if str(r["symbol"]) != "DOLLARIDX"]
    if fill is not None:
        extra_rows.append(fill)
    if extra_rows:
        extra = pd.DataFrame([candidate_signal_row(r)
                              for r in extra_rows])
        entries = (pd.concat([entries, extra],
                             ignore_index=True)
                   if len(entries) else extra)
    return entries if entries is not None else pd.DataFrame()
