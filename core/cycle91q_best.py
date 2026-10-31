"""Cycle 91Q (R3 surgery winner R04_dropNeg_refill)
-- September system, integrated 2026-10-31 from the
R3 surgery round (sep_r3.md; port proof
sep_portproof.md; design-append replay
sep_append_replay.md).

Definition: the shipped September combined stream
(cycle91p best + cycle91s second-best, the 677-pick
combined research base) with ONE further surgery
layer:

  * DROP every pick of the two discovery-negative
    strategies FB_NZDUSD_h11_1 (23 picks) and
    FB_GBPJPY_h10_2 (4 picks) from the combined
    ledger;
  * REFILL by the research cascade (run_sep_r3.py
    cascade verbatim -- NOT build_combined): the
    standalone walks of the seven pool designs
    (sep_b2sb_r15, sep_b9c, sep_b9c_c04, sep_b9c_c13,
    sep_b9sb, sep_b9, sep_b9_c15 -- concatenated in
    filename order; sep_b9c / sep_b9 / sep_b9sb
    already ship, sep_b2sb_r15 / sep_b9c_c04 /
    sep_b9c_c13 / sep_b9_c15 are appended to
    core.new8_designs for this wave), sorted by
    (check asc, score desc, stable); a pool row is
    accepted iff its check hour is in {1, 2, 10, 11},
    its check is not occupied by the (dropped) base,
    no fill was already accepted at that check, and
    its (check, exit_time) interval overlaps no base
    row and no accepted fill on the same symbol.
    30 fills in the graded form.

Registry shape: 91q replaces 91p as September's
best; the second-best stays cycle91s (the graded
combined base includes the 91s stream exactly as
the standing best+second combined delivery does).

Graded numbers (research ledger, @2.5 -- the app
form is replayed bit-exact against this ledger in
sep_append_replay.md): DISC n489 net +4514.00,
leftover 73.83% (incumbent 68.60%); AUDIT n191 net
+1219.70, leftover 72.40% (incumbent 69.49%); win
95.77 / 95.59; epd 3.181 / 3.163; LCT-middle 88.35 /
65.96 PASS; MC middle TRUE (DD p95 245.95 vs cap
287.72, cluster p95 153.10); PBO 20.0% / DSR
0.9999; decay PASS. Classification: IMPROVE.
Best N unchanged (83, as cycle91p).
"""

from __future__ import annotations

import json
import os

import pandas as pd

import core.cycle91n_best as _c91n
import core.cycle91p_best as _c91p
from core.cycle91n_best import CYCLE91N_CHECK_HOURS
from core.new8_candidate import (MergedWalkState,
                                 default_state_path)
from core.new8_designs import DESIGNS
from core.new8_walk import DesignWalk

CYCLE91Q_CHECK_HOURS = (1, 2, 10, 11)
BASE_DESIGNS = ("sep_b9", "sep_b9c")
POOL_DESIGNS = ("sep_b2sb_r15", "sep_b9c", "sep_b9c_c04",
                "sep_b9c_c13", "sep_b9sb", "sep_b9",
                "sep_b9_c15")
CASCADE_HOURS = {1, 2, 10, 11}
DROP_STRATEGIES = ("FB_NZDUSD_h11_1", "FB_GBPJPY_h10_2")
SYSTEM_NAME = "cycle91q"
_DESIGN_SYMBOLS = _c91p._DESIGN_SYMBOLS
_POOL_SYMBOLS = tuple(sorted(
    {e["symbol"] for n in POOL_DESIGNS
     for e in DESIGNS[n]["equations"]} | set(_DESIGN_SYMBOLS)))


def evaluate_cycle91q_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the cycle91p signals verbatim."""
    return _c91p.evaluate_cycle91p_signals(
        frames, check_time_utc, m15_frames=m15_frames)


def select_cycle91q_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Base selection: the cycle91p selection verbatim."""
    return _c91p.select_cycle91p_entries(
        signals, open_symbols=open_symbols)


def is_cycle91q_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE91Q_CHECK_HOURS and t.minute == 30


# ------------------------------------------------ cascade --
def cascade(base: pd.DataFrame, pool: pd.DataFrame,
            hours) -> pd.DataFrame:
    """run_sep_r3.py cascade verbatim (same construction
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


def build_cycle91q_ledger(base: pd.DataFrame, walks: dict) \
        -> pd.DataFrame:
    """The graded R04 construction: drop the two
    negative strategies from the recorded combined
    (91p+91s) ledger, then the research cascade over
    the concatenated pool walks (POOL_DESIGNS order =
    stored-ledger filename order)."""
    b = base.copy()
    for c in ("check", "exit_time"):
        b[c] = pd.to_datetime(b[c])
    b = b[~b["strategy"].isin(DROP_STRATEGIES)] \
        .reset_index(drop=True)
    pool = pd.concat([walks[n] for n in POOL_DESIGNS],
                     ignore_index=True)
    return cascade(b, pool, CASCADE_HOURS)


class PoolCascadeState:
    """Streaming form of the research cascade (see
    core.cycle87e_best.PoolCascadeState -- identical
    rules, September pool)."""

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


class Cycle91qState:
    """The full 91Q persisted state: the cycle91p merged
    walk state (own namespace 'cycle91q', so the base
    stream's occupancy is settled by this system) plus
    the pool cascade state, in one JSON document."""

    def __init__(self, path=None):
        self.path = path or default_state_path(SYSTEM_NAME)
        self.merged = MergedWalkState(SYSTEM_NAME,
                                      BASE_DESIGNS, path=None)
        self.pool = PoolCascadeState()

    def save(self):
        os.makedirs(os.path.dirname(
            os.path.abspath(self.path)), exist_ok=True)
        ser = PoolCascadeState._ser
        data = {
            "system": SYSTEM_NAME,
            "incumbent_picks": ser(self.merged.incumbent_picks),
            "accepted": ser(self.merged.accepted),
            "partner_walks": {
                n: {"picks": ser(w.picks),
                    "open_exit": {
                        s: [pd.Timestamp(x).isoformat()
                            for x in xs]
                        for s, xs in w.open_exit.items()}}
                for n, w in self.merged.walks.items()},
            "pool": self.pool.to_dict(),
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
        de = PoolCascadeState._de
        st.merged.incumbent_picks = de(
            data.get("incumbent_picks", []))
        st.merged.accepted = de(data.get("accepted", []))
        for n, wd in (data.get("partner_walks") or {}).items():
            if n not in st.merged.walks:
                continue
            st.merged.walks[n].picks = de(wd.get("picks", []))
            st.merged.walks[n].open_exit = {
                s: [pd.Timestamp(x) for x in xs]
                for s, xs in (wd.get("open_exit") or {}).items()}
        st.pool.load_dict(data.get("pool", {}))
        return st

    def base_view(self):
        """The recorded combined base rows for the
        cascade: incumbent entries + accepted B-9 picks,
        with the dropped strategies' rows removed (the
        research drop is a ledger-level filter; the
        underlying walks' occupancy is untouched)."""
        rows = list(self.merged.incumbent_picks) \
            + list(self.merged.accepted)
        return [r for r in rows
                if str(r.get("strategy")) not in DROP_STRATEGIES]

    def step(self, ctx, check, incumbent_entries):
        """One check: the 91p merged layer first (records
        the base entries, merges sep_b9 / sep_b9c), then
        the R04 cascade fill against the dropped base
        view. Returns (accepted_partner_picks,
        fill_or_None)."""
        accepted = self.merged.step(ctx, check,
                                    incumbent_entries)
        fill = self.pool.step(ctx, check, self.base_view())
        return accepted, fill


def load_state():
    try:
        return Cycle91qState.load()
    except Exception:
        return Cycle91qState()


def _entry_strategy(row):
    for c in ("strategy", "equation"):
        if c in row and pd.notna(row[c]):
            return str(row[c])
    return None


def _cand_m15(m15_frames):
    from core.new8_candidate import ensure_m15
    return ensure_m15(_c91p._m15(m15_frames), _POOL_SYMBOLS)


# ------------------------------------------------- panel form --
def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check: the cycle91n
    panel entries plus accepted B-9 picks (the 91p
    construction, own state namespace), with the two
    dropped strategies' picks removed, plus at most
    one R04 cascade fill -- settled through this
    system's persisted state."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row)
    from core.new8_features import frame_to_research
    from core.new8_walk import ohlc_from_frame
    m15_frames = _c91p._m15(m15_frames)
    entries = _c91n.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    if entries is None:
        entries = pd.DataFrame()
    state = load_state()
    ctx = CandidateContext(frames, _cand_m15(m15_frames),
                           tuple(dict.fromkeys(
                               BASE_DESIGNS + POOL_DESIGNS)))
    for sym, fr in ctx.frames.items():
        if sym not in ctx.ohlc and fr is not None and len(fr):
            try:
                rfr, _ = frame_to_research(fr)
                ctx.ohlc[sym] = ohlc_from_frame(rfr)
            except Exception:
                pass
    accepted, fill = state.step(ctx, check_time_utc, entries)
    state.save()
    kept = entries
    if len(entries):
        mask = [(_entry_strategy(r) not in DROP_STRATEGIES)
                for _, r in entries.iterrows()]
        kept = entries[mask]
    extra_rows = [r for r in (accepted or [])
                  if str(r.get("strategy")) not in DROP_STRATEGIES]
    if fill is not None:
        extra_rows.append(fill)
    if extra_rows:
        extra = pd.DataFrame([candidate_signal_row(r)
                              for r in extra_rows])
        kept = (pd.concat([kept, extra], ignore_index=True)
                if len(kept) else extra)
    return kept if kept is not None else pd.DataFrame()
