"""Cycle 94E (R3 surgery winner P15_PLANB4_cand1)
-- December system, integrated 2026-10-31 from the
R3 surgery round (dec_r3.md; port proof
dec_portproof.md; design-append replay
dec_append_replay.md).

Registry shape (stated per the install order): a
FOLD-IN on cycle94d, per the 85d / 78d precedent --
94e replaces 94d as December's best and carries the
P15 partner layer inside the same module; the
second-best stays cycle94s.

Definition: cycle94d (the shipped December D19
form, 908 picks) PLUS the P15 partner layer:

  * the standalone walk of the PLANB4 candidate1
    design 'dec_b4_c08' (30 equations, S-CLU3 --
    appended to core.new8_designs for this wave),
    taken as a pool over the 94d ledger under the
    research cascade (run_dec_r3.py cascade verbatim
    -- NOT 94d's build_combined refills): pool rows
    in (check asc, score desc, stable) order; a row
    is accepted iff its check hour is in
    {10, 11, 13, 14}, its check is not occupied by
    the base, no fill was already accepted at that
    check, and its (check, exit_time) interval
    overlaps no base row and no accepted fill on the
    same symbol. 5 fills in the graded form, no
    drops.

Graded numbers (research ledger, @2.5 -- the app
form is replayed bit-exact against this ledger in
dec_append_replay.md): DISC n736 net +8282.15,
leftover 81.19% (incumbent 80.93%); AUDIT n177 net
+1176.96, leftover 57.96% (incumbent 57.65%); win
96.19 / 93.30; epd 4.194 / 3.978; LCT-middle 87.92 /
76.07 PASS; MC middle TRUE (DD p95 and cluster p95
identical to the incumbent); PBO 0.00% / DSR
1.0000 (family-41); decay WEAKENED (not FAIL).
Classification: IMPROVE (SMALL). Best N unchanged
(105, as cycle94d).

Live-servability caveat: 3 of the 5 fills are
DOLLARIDX-symbol picks; like every dollar leg in
this programme they stay silent on the live feed
until a dollar series is served. The research
grade and the app replay are unaffected. The
December 16:30 office-hour replacement target
stays OPEN (P15 keeps the incumbent hours).
"""

from __future__ import annotations

import json
import os

import pandas as pd

import core.cycle94d_best as _c94d
from core.cycle94d_best import (CYCLE94D_CHECK_HOURS,
                                build_cycle94d_ledger,
                                evaluate_cycle94d_signals,
                                fetch_cycle94d_m15_frames,
                                is_cycle94d_check_time,
                                select_cycle94d_entries)
from core.new8_candidate import default_state_path
from core.new8_designs import DESIGNS
from core.new8_walk import DesignWalk

CYCLE94E_CHECK_HOURS = CYCLE94D_CHECK_HOURS
POOL_DESIGNS = ("dec_b4_c08",)
CASCADE_HOURS = {10, 11, 13, 14}
SYSTEM_NAME = "cycle94e"
_POOL_SYMBOLS = tuple(sorted({e["symbol"] for n in POOL_DESIGNS
                              for e in DESIGNS[n]["equations"]}))


def evaluate_cycle94e_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the cycle94d signals verbatim."""
    return evaluate_cycle94d_signals(frames, check_time_utc,
                                     m15_frames=m15_frames)


def select_cycle94e_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Base selection: the cycle94d selection verbatim."""
    return select_cycle94d_entries(signals,
                                   open_symbols=open_symbols)


def is_cycle94e_check_time(ts) -> bool:
    return is_cycle94d_check_time(ts)


def fetch_cycle94e_m15_frames(state=None):
    return fetch_cycle94d_m15_frames(state=state)


# ------------------------------------------------ cascade --
def cascade(base: pd.DataFrame, pool: pd.DataFrame,
            hours) -> pd.DataFrame:
    """run_dec_r3.py cascade verbatim (same construction
    as cycle87e's)."""
    taken = [(r.check, r.exit_time, r.symbol)
             for r in base.itertuples()]
    busy = set(base["check"])
    used = set()
    fills = []
    pool = pool.sort_values(["check", "score"],
                            ascending=[True, False],
                            kind="stable")
    for r in pool.itertuples():
        if r.check.hour not in hours:
            continue
        if r.check in busy or r.check in used:
            continue
        ov = False
        for (c, e, s) in taken:
            if s == r.symbol and c < r.exit_time \
                    and r.check < e:
                ov = True
                break
        if ov:
            continue
        fills.append(r._asdict())
        taken.append((r.check, r.exit_time, r.symbol))
        used.add(r.check)
    out = pd.concat([base, pd.DataFrame(fills)],
                    ignore_index=True) if fills else \
        base.copy()
    out = out.sort_values("check", kind="stable") \
        .reset_index(drop=True)
    out["net_pips"] = out["gross_pips"] - 2.5
    return out


def build_cycle94e_ledger(incumbent: pd.DataFrame,
                          walks94d: dict, m15_frames: dict,
                          pool_walk: pd.DataFrame) \
        -> pd.DataFrame:
    """The graded P15 construction: the cycle94d D19
    ledger (PC03 veto + dec_rg / dec_rgc refill +
    dec_b12c partner, via build_cycle94d_ledger), then
    the research cascade of the dec_b4_c08 walk over
    it."""
    base, _acc = build_cycle94d_ledger(incumbent, walks94d,
                                       m15_frames)
    return cascade(base, pool_walk, CASCADE_HOURS)


class PoolCascadeState:
    """Streaming form of the research cascade (see
    core.cycle87e_best.PoolCascadeState -- identical
    rules, December pool)."""

    def __init__(self, design_names=POOL_DESIGNS,
                 hours=CASCADE_HOURS):
        self.design_names = list(design_names)
        self.hours = set(hours)
        self.walks = {n: DesignWalk(DESIGNS[n]["equations"],
                                    veto=DESIGNS[n]["veto"])
                      for n in self.design_names}
        self.fills = []
        self._bound_ctx = None

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
            "fills": self._ser(self.fills),
            "walks": {n: {"picks": self._ser(w.picks),
                          "open_exit": {
                              s: [pd.Timestamp(x).isoformat()
                                  for x in xs]
                              for s, xs in w.open_exit.items()}}
                      for n, w in self.walks.items()},
        }

    def load_dict(self, data):
        self.fills = self._de(data.get("fills", []))
        for n, wd in (data.get("walks") or {}).items():
            if n not in self.walks:
                continue
            self.walks[n].picks = self._de(wd.get("picks", []))
            self.walks[n].open_exit = {
                s: [pd.Timestamp(x) for x in xs]
                for s, xs in (wd.get("open_exit") or {}).items()}

    def _bind(self, ctx):
        if self._bound_ctx is ctx:
            return
        from core.new8_walk import make_adx25v, wilder_adx14
        for n in self.design_names:
            d = DESIGNS[n]
            if d["veto"] == "adx25":
                am = {}
                for e in d["equations"]:
                    s = e["symbol"]
                    if s in ctx.frames:
                        f = ctx.frames[s]
                        am[s] = (f.index, wilder_adx14(
                            f["High"].to_numpy(float),
                            f["Low"].to_numpy(float),
                            f["Close"].to_numpy(float)))
                self.walks[n].veto_fn = make_adx25v(
                    am, d["veto_threshold"]) if am else None
        self._bound_ctx = ctx

    def step(self, ctx, check, base_rows):
        chk = pd.Timestamp(check)
        self._bind(ctx)
        picks = []
        for name in self.design_names:
            rows = ctx.rows_at(name, chk)
            pick = self.walks[name].step(chk, rows)
            if pick is not None:
                picks.append(pick)
        if chk.hour not in self.hours:
            return None
        if any(pd.Timestamp(r["check"]) == chk
               for r in base_rows):
            return None
        if any(pd.Timestamp(f["check"]) == chk
               for f in self.fills):
            return None
        picks.sort(key=lambda p: -float(p["score"]))
        taken = [(pd.Timestamp(r["check"]),
                  pd.Timestamp(r["exit_time"]), r["symbol"])
                 for r in base_rows] + \
            [(pd.Timestamp(f["check"]),
              pd.Timestamp(f["exit_time"]), f["symbol"])
             for f in self.fills]
        for pick in picks:
            ex = pd.Timestamp(pick["exit_time"])
            ov = False
            for (c, e, s) in taken:
                if s == pick["symbol"] and c < ex and chk < e:
                    ov = True
                    break
            if ov:
                continue
            fill = dict(pick)
            self.fills.append(fill)
            return fill
        return None


class Cycle94eState:
    """The full 94E persisted state: the recorded
    cycle94d base rows plus the P15 pool cascade
    state, in one JSON document."""

    def __init__(self, path=None):
        self.path = path or default_state_path(SYSTEM_NAME)
        self.base_rows = []
        self.pool = PoolCascadeState()

    def save(self):
        os.makedirs(os.path.dirname(
            os.path.abspath(self.path)), exist_ok=True)
        data = {"system": SYSTEM_NAME,
                "base_rows": PoolCascadeState._ser(self.base_rows),
                "pool": self.pool.to_dict()}
        with open(self.path, "w") as fh:
            json.dump(data, fh)
        return self.path

    @classmethod
    def load(cls, path=None):
        p = path or default_state_path(SYSTEM_NAME)
        with open(p) as fh:
            data = json.load(fh)
        st = cls(path=p)
        st.base_rows = PoolCascadeState._de(
            data.get("base_rows", []))
        st.pool.load_dict(data.get("pool", {}))
        return st

    def step(self, ctx, check, base_entries):
        """One check: record this check's base entries
        (signal-row dicts), then the P15 cascade fill
        against all recorded base rows + fills."""
        chk = pd.Timestamp(check)
        for r in base_entries or ():
            d = dict(r)
            d["check"] = pd.Timestamp(d.get("check", chk))
            if d.get("entry_time") is None:
                d["entry_time"] = chk - pd.Timedelta(minutes=30)
            if d.get("exit_time") is None:
                d["exit_time"] = pd.Timestamp(d["entry_time"]) \
                    + pd.Timedelta(hours=48)
            self.base_rows.append(d)
        return self.pool.step(ctx, chk, self.base_rows)


def load_state():
    try:
        return Cycle94eState.load()
    except Exception:
        return Cycle94eState()


def _cand_m15(m15_frames):
    from core.new8_candidate import ensure_m15
    return ensure_m15(m15_frames, _POOL_SYMBOLS)


# ------------------------------------------------- panel form --
def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check: the cycle94d
    panel entries, plus at most one P15 cascade fill
    -- settled through this system's persisted
    state."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row)
    from core.new8_features import frame_to_research
    from core.new8_walk import ohlc_from_frame
    entries = _c94d.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    if entries is None:
        entries = pd.DataFrame()
    state = load_state()
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           POOL_DESIGNS)
    for sym, fr in ctx.frames.items():
        if sym not in ctx.ohlc and fr is not None and len(fr):
            try:
                rfr, _ = frame_to_research(fr)
                ctx.ohlc[sym] = ohlc_from_frame(rfr)
            except Exception:
                pass
    base_dicts = [dict(r) for _, r in entries.iterrows()] \
        if len(entries) else []
    fill = state.step(ctx, check_time_utc, base_dicts)
    state.save()
    if fill is not None:
        extra = pd.DataFrame([candidate_signal_row(fill)])
        entries = (pd.concat([entries, extra],
                             ignore_index=True)
                   if len(entries) else extra)
    return entries if entries is not None else pd.DataFrame()
