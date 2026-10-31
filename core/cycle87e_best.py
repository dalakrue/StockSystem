"""Cycle 87E (R3 surgery winner R01_dropNegStrat_refill)
-- April system, integrated 2026-10-31 from the R3
surgery round (apr_r3.md; port proof
apr_portproof.md; design-append replay
apr_append_replay.md).

Definition: cycle87d (the shipped April C19-app form,
924 picks) with ONE further surgery layer:

  * DROP every pick of the single discovery-negative
    strategy mom_EURAUD_h16_momS_T1.5_A1.0_0.3x3
    (7 picks) from the 87d ledger;
  * REFILL by the research cascade (run_apr_r3.py
    cascade verbatim -- NOT build_combined and NOT
    feb_common.cascade): the standalone walks of the
    six pool designs appended to core.new8_designs for
    this wave (apr_b12c_c08, apr_b12c_c19, apr_b7_c04,
    apr_b8_c07, apr_b9c_c03, apr_c05 -- concatenated in
    filename order), sorted by (check asc, score desc,
    stable); a pool row is accepted iff its check hour
    is in {16, 17, 18, 19}, its check is not occupied
    by the (dropped) base, no fill was already accepted
    at that check, and its (check, exit_time) interval
    overlaps no base row and no accepted fill on the
    same symbol. 17 fills in the graded form.

Graded numbers (research ledger, @2.5 -- the app form
is replayed bit-exact against this ledger in
apr_append_replay.md): DISC n745 net +7521.06,
leftover 92.19% (incumbent 91.24%); AUDIT n189 net
+2101.00, leftover 76.32% (incumbent 76.25%); win
98.65 / 95.36; epd 4.379 / 4.409; LCT-middle 99.59 /
84.83 PASS; MC middle TRUE (DD p95 174.76); PBO
0.00% / DSR 1.0000; decay PASS. Classification:
IMPROVE (SMALL). Best N unchanged (104, as cycle87d).

Live-servability caveat: 6 of the 17 fills are
DOLLARIDX-symbol picks from apr_c05 (the dollar-
included sibling of the shipped apr_q09); like every
dollar leg in this programme they stay silent on the
live feed until a dollar series is served. The
research grade and the app replay are unaffected.
"""

from __future__ import annotations

import json
import os

import pandas as pd

import core.cycle87d_best as _c87d
from core.cycle87d_best import (CYCLE87D_CHECK_HOURS,
                                evaluate_cycle87d_signals,
                                fetch_cycle87d_m15_frames,
                                is_cycle87d_check_time,
                                select_cycle87d_entries)
from core.new8_candidate import default_state_path
from core.new8_designs import DESIGNS
from core.new8_walk import DesignWalk

CYCLE87E_CHECK_HOURS = CYCLE87D_CHECK_HOURS
POOL_DESIGNS = ("apr_b12c_c08", "apr_b12c_c19", "apr_b7_c04",
                "apr_b8_c07", "apr_b9c_c03", "apr_c05")
CASCADE_HOURS = {16, 17, 18, 19}
DROP_STRATEGIES = ("mom_EURAUD_h16_momS_T1.5_A1.0_0.3x3",)
SYSTEM_NAME = "cycle87e"
_POOL_SYMBOLS = tuple(sorted({e["symbol"] for n in POOL_DESIGNS
                              for e in DESIGNS[n]["equations"]}))


def evaluate_cycle87e_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the cycle87d signals verbatim."""
    return evaluate_cycle87d_signals(frames, check_time_utc,
                                     m15_frames=m15_frames)


def select_cycle87e_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    """Base selection: the cycle87d selection verbatim."""
    return select_cycle87d_entries(signals,
                                   open_symbols=open_symbols)


def is_cycle87e_check_time(ts) -> bool:
    return is_cycle87d_check_time(ts)


def fetch_cycle87e_m15_frames(state=None):
    return fetch_cycle87d_m15_frames(state=state)


# ------------------------------------------------ cascade --
def cascade(base: pd.DataFrame, pool: pd.DataFrame,
            hours) -> pd.DataFrame:
    """run_apr_r3.py cascade verbatim: fills from the
    pool over the base under (check, score-desc) order,
    one fill per check, no same-symbol overlap vs the
    base or earlier fills."""
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
        fills.append(r._asdict() if hasattr(r, "_asdict")
                     else dict(r))
        taken.append((r.check, r.exit_time, r.symbol))
        used.add(r.check)
    out = pd.concat([base, pd.DataFrame(fills)],
                    ignore_index=True) if fills else \
        base.copy()
    out = out.sort_values("check", kind="stable") \
        .reset_index(drop=True)
    out["net_pips"] = out["gross_pips"] - 2.5
    return out


def build_cycle87e_ledger(base: pd.DataFrame, walks: dict) \
        -> pd.DataFrame:
    """The graded R01 construction: drop the negative
    strategy from the recorded cycle87d ledger, then the
    research cascade over the concatenated pool walks
    (POOL_DESIGNS order = stored-ledger filename order)."""
    b = base.copy()
    for c in ("check", "exit_time"):
        b[c] = pd.to_datetime(b[c])
    b = b[~b["strategy"].isin(DROP_STRATEGIES)] \
        .reset_index(drop=True)
    pool = pd.concat([walks[n] for n in POOL_DESIGNS],
                     ignore_index=True)
    return cascade(b, pool, CASCADE_HOURS)


class PoolCascadeState:
    """Streaming form of the research cascade: one
    DesignWalk per pool design (each design's own
    walk157 occupancy + veto, advanced at EVERY check
    whether or not its pick is used -- the research pool
    ledgers are standalone walks), plus the accepted
    fills. step() receives the base rows (post-drop) as
    recorded dicts with check / entry_time / exit_time /
    symbol; with the full recorded base view this
    reproduces the batch cascade bit-exact (the gate
    pattern of feb_replay / gate_feb_85e)."""

    def __init__(self, design_names=POOL_DESIGNS,
                 hours=CASCADE_HOURS):
        self.design_names = list(design_names)
        self.hours = set(hours)
        self.walks = {n: DesignWalk(DESIGNS[n]["equations"],
                                    veto=DESIGNS[n]["veto"])
                      for n in self.design_names}
        self.fills = []
        self._bound_ctx = None

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

    # -------------------------------------------------- vetoes --
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

    # --------------------------------------------------- step --
    def step(self, ctx, check, base_rows):
        """base_rows: the (post-drop) base rows as dicts.
        Returns the accepted fill at this check or None
        (at most one fill per check, cascade rules)."""
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


class Cycle87eState:
    """The full 87E persisted state: the recorded
    (post-drop) base rows plus the pool cascade state,
    in one JSON document."""

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
        (signal-row dicts, post-drop), then the cascade
        fill against all recorded base rows + fills."""
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
        return Cycle87eState.load()
    except Exception:
        return Cycle87eState()


def _entry_strategy(row):
    for c in ("strategy", "equation"):
        if c in row and pd.notna(row[c]):
            return str(row[c])
    return None


def _cand_m15(m15_frames):
    from core.new8_candidate import ensure_m15
    return ensure_m15(m15_frames, _POOL_SYMBOLS)


# ------------------------------------------------- panel form --
def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full merged entries for one check: the cycle87d
    panel entries with the dropped strategy's picks
    removed, plus at most one R01 cascade fill --
    settled through this system's persisted state."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row)
    from core.new8_features import frame_to_research
    from core.new8_walk import ohlc_from_frame
    entries = _c87d.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    if entries is None:
        entries = pd.DataFrame()
    kept = entries
    if len(entries):
        mask = [(_entry_strategy(r) not in DROP_STRATEGIES)
                for _, r in entries.iterrows()]
        kept = entries[mask]
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
    base_dicts = [dict(r) for _, r in kept.iterrows()] \
        if len(kept) else []
    fill = state.step(ctx, check_time_utc, base_dicts)
    state.save()
    if fill is not None:
        extra = pd.DataFrame([candidate_signal_row(fill)])
        kept = (pd.concat([kept, extra], ignore_index=True)
                if len(kept) else extra)
    return kept if kept is not None else pd.DataFrame()
