"""Cycle 85E (R3 Plan C C01) -- February system,
integrated 2026-10-31 from the R3 surgery round
(feb_planC_s1.md; port proof feb_portproof.md; fresh
exact app replay feb_replay.md, PASS).

Definition: cycle85d (the shipped February A16+X12
combined stack, 623 picks) PLUS one further
second-priority layer, the C01 layer:

  * The feb_b9cc03 design's standalone walk (the design
    already ships in core/new8_designs.py and already
    sits in the X12 CASCADE_DESIGNS), taken as a pool
    over the combined 623 base under feb_common.cascade
    occupancy -- NOT build_combined occupancy: pool rows
    in (check, score-desc) order; at most one fill per
    check; a fill is blocked only when the base already
    carries the same symbol AT that check, or when its
    (check, exit) interval overlaps a base row or an
    already-accepted fill on the same symbol; fills are
    restricted to the NEW8 symbols (CADCHF, CADJPY,
    GBPAUD, GBPCAD, GBPCHF, GBPNZD, NZDCHF, NZDJPY).
    With build_combined occupancy the same pool yields
    only 2 fills (98 of 100 NEW8 pool rows die on
    check_busy) -- that form was replayed and rejected
    as NOT the graded construction (feb_replay.md).
  * In the event every accepted fill is a Y3_ pick on
    GBPCAD or GBPCHF (the other NEW8 symbols' pool picks
    collide with the base occupancy).

Validated numbers (winner ledger, replayed EXACT on
the app machinery 2026-10-31 -- module control 623/623,
CC03 standalone walk 284/284, combined 713/713):
DISC n563 net +7503.86, leftover 90.51% (incumbent
88.85%); AUDIT n150 net +656.66, leftover 38.11%
(incumbent 34.85%, strictly greater); LCT vs incumbent
P 86.47% / q05 81.36% (middle PASS); MC middle PASS
(DD p95 193.36 vs incumbent 204.33); PBO 0.00% /
DSR 1.0000; decay PASS. Best N unchanged (104, as
cycle85d).

Live-servability caveat (B-13 Step-4 class, named in
feb_portproof.md): the CC03 equations condition on
M15-volume composites; on the live Twelve Data feed
the fills stay silent until a volume-bearing feed
serves those columns. The research grade and the app
replay are unaffected.
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

CYCLE85E_CHECK_HOURS = CYCLE85B_CHECK_HOURS
PARTNER_DESIGNS = ("feb_p38",)
CASCADE_DESIGNS = ("feb_p38", "feb_e19", "feb_b9cp14",
                   "feb_e07", "feb_b9sb", "feb_b9sbpc",
                   "feb_b9c06", "feb_p07", "feb_b9c03",
                   "feb_b9p13", "feb_b9cc03")
SYSTEM_NAME = "cycle85e"


def evaluate_cycle85e_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the cycle85c signals (the A16 veto acts
    in selection)."""
    return _c85c.evaluate_cycle85c_signals(
        frames, check_time_utc, m15_frames=m15_frames)


def select_cycle85e_entries(signals: pd.DataFrame,
                            open_symbols=(),
                            live_count: int = 0,
                            m15_frames: dict | None = None,
                            check_time_utc=None) -> pd.DataFrame:
    """Base selection: the cycle85c selection verbatim."""
    return _c85c.select_cycle85c_entries(
        signals, open_symbols=open_symbols,
        live_count=live_count, m15_frames=m15_frames,
        check_time_utc=check_time_utc)


def is_cycle85e_check_time(ts) -> bool:
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



NEW8_SYMBOLS = {"CADCHF", "CADJPY", "GBPAUD", "GBPCAD",
                "GBPCHF", "GBPNZD", "NZDCHF", "NZDJPY"}
CC03_DESIGN = "feb_b9cc03"


class CC03CascadeState:
    """C01 layer state (R3 Plan C C01): the feb_b9cc03
    standalone DesignWalk plus the feb_common.cascade
    combine against the combined base rows (module
    incumbent rows + accepted X12 fills).

    Combine rules (feb_common.cascade verbatim, proven
    bit-exact in feb_replay.md): the walk's pick at a
    check becomes a fill only when (a) its symbol is a
    NEW8 symbol, (b) no C01 fill was already accepted at
    that check, (c) the base carries no row with the
    same symbol AT that check, and (d) its (check,
    exit_time) interval overlaps no base row and no
    already-accepted C01 fill on the same symbol.
    """

    def __init__(self):
        self.walk = DesignWalk(DESIGNS[CC03_DESIGN]["equations"],
                               veto=DESIGNS[CC03_DESIGN]["veto"])
        self.fills = []

    # ------------------------------------------------ persist --
    @staticmethod
    def _ser(rows):
        return X12CascadeState._ser(rows)

    @staticmethod
    def _de(rows):
        return X12CascadeState._de(rows)

    def to_dict(self):
        return {
            "fills": self._ser(self.fills),
            "walk": {"picks": self._ser(self.walk.picks),
                     "open_exit": {
                         s: [pd.Timestamp(x).isoformat()
                             for x in xs]
                         for s, xs in self.walk.open_exit.items()}},
        }

    def load_dict(self, data):
        self.fills = self._de(data.get("fills", []))
        wd = data.get("walk") or {}
        self.walk.picks = self._de(wd.get("picks", []))
        self.walk.open_exit = {
            s: [pd.Timestamp(x) for x in xs]
            for s, xs in (wd.get("open_exit") or {}).items()}

    # --------------------------------------------------- step --
    def step(self, ctx, check, base_rows):
        """base_rows: the combined base's rows (dicts with
        check / entry_time / exit_time / symbol). Returns
        the accepted fill or None."""
        chk = pd.Timestamp(check)
        rows = ctx.rows_at(CC03_DESIGN, chk)
        pick = self.walk.step(chk, rows)
        if pick is None:
            return None
        if pick["symbol"] not in NEW8_SYMBOLS:
            return None
        if any(pd.Timestamp(f["check"]) == chk
               for f in self.fills):
            return None
        if any(pd.Timestamp(r["check"]) == chk
               and r["symbol"] == pick["symbol"]
               for r in base_rows):
            return None
        ex = pd.Timestamp(pick["exit_time"])

        def _ov(rows_):
            return any(
                r["symbol"] == pick["symbol"]
                and pd.Timestamp(r["check"]) < ex
                and chk < pd.Timestamp(r["exit_time"])
                for r in rows_)

        if _ov(base_rows) or _ov(self.fills):
            return None
        fill = dict(pick)
        self.fills.append(fill)
        return fill


class Cycle85eState:
    """The full 85E persisted state: the A16 partner layer
    (a MergedWalkState over feb_p38, as in cycle85c), the
    X12 cascade state and the C01 (CC03) cascade state,
    in one JSON document."""

    def __init__(self, path=None):
        self.path = path or default_state_path(SYSTEM_NAME)
        self.partner = MergedWalkState(
            SYSTEM_NAME, PARTNER_DESIGNS, path=None)
        self.cascade = X12CascadeState()
        self.cc03 = CC03CascadeState()

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
            "cc03": self.cc03.to_dict(),
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
        st.cc03.load_dict(data.get("cc03", {}))
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

    def combined_rows(self):
        """The combined base rows for the C01 combine:
        recorded incumbent entries + accepted partner
        picks (partner DOLLARIDX rows excluded, as in
        base_view) + accepted X12 cascade fills."""
        rows = list(self.partner.incumbent_picks) + [
            r for r in self.partner.accepted
            if str(r["symbol"]) != "DOLLARIDX"]
        rows += list(self.cascade.fills)
        return rows

    def step(self, ctx, check, incumbent_entries):
        """One check: partner layer first (records the base
        entries, merges feb_p38), then the X12 cascade
        fill, then the C01 (CC03) cascade fill against
        the combined base. Returns (partner_picks,
        fill_or_None, cc03_fill_or_None)."""
        partner_picks = self.partner.step(
            ctx, check, incumbent_entries)
        checks, intervals = self.base_view()
        fill = self.cascade.step(ctx, check, checks, intervals)
        cc03_fill = self.cc03.step(ctx, check,
                                   self.combined_rows())
        return partner_picks, fill, cc03_fill


def load_state():
    try:
        return Cycle85eState.load()
    except Exception:
        return Cycle85eState()


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check: the vetoed
    cycle85b base entries, plus accepted feb_p38 partner
    picks, plus at most one X12 cascade fill, plus at
    most one C01 (CC03) cascade fill -- settled through
    this system's persisted state."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row)
    from core.new8_features import frame_to_research
    from core.new8_walk import ohlc_from_frame
    sig = evaluate_cycle85e_signals(frames, check_time_utc,
                                    m15_frames=m15_frames)
    if sig is not None and len(sig) == 0 \
            and sig.attrs.get("status"):
        return sig
    entries = select_cycle85e_entries(
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
    partner_picks, fill, cc03_fill = state.step(
        ctx, check_time_utc, entries)
    state.save()
    extra_rows = [r for r in partner_picks
                  if str(r["symbol"]) != "DOLLARIDX"]
    if fill is not None:
        extra_rows.append(fill)
    if cc03_fill is not None:
        extra_rows.append(cc03_fill)
    if extra_rows:
        extra = pd.DataFrame([candidate_signal_row(r)
                              for r in extra_rows])
        entries = (pd.concat([entries, extra],
                             ignore_index=True)
                   if len(entries) else extra)
    return entries if entries is not None else pd.DataFrame()
