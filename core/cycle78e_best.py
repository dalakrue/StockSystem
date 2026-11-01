"""Cycle 78E -- July Plan E E09 system (2026-11-01 install).

Form (Plan E winner E09 = E17, VALIDATED as IMPROVE over
cycle78d; validation file
work_r5_20cyc/results/jul_planE_FINAL_VALIDATION.md):

    cycle78d stream (JulD3State, unchanged)
      -> CONS3 consensus fills: a (check, symbol, direction)
         key must appear in >= 3 of the 9 July pool families
         (20 pool design walks); the agreed rows enter through
         the second-priority cascade (<= 1 per check, symbol
         not taken at the check by the base, no same-symbol
         interval overlap), at the incumbent hours (15, 17, 18)
      -> CCAP cluster cap: drop a later same-(symbol, day)
         entry once the running kept loss mass for that key
         reaches 100 pips (binds nowhere on the 2016-2025 era;
         E09 == E17 stream).

The pool walks are computed from market data at runtime
(DesignWalk over DESIGNS; the 8 B13 pool designs were ported
into core/new8_designs.py with this install -- transcription
and walk gates in work_plane_port). No research artefacts are
read at runtime.

Panel form: JulE09State composes the shipped JulD3State and
adds the 8 B13 DesignWalks plus the streaming CONS3/CCAP
stage. The ledger-form build (build_e09) is the exact
construction; the streaming stage follows the same rules in
check order (the shipped cycle78d cascade has the same
streaming semantics).
"""

import json
import os

import numpy as np
import pandas as pd

from core.cycle78_best import (evaluate_cycle78_signals,
                               is_cycle78_check_time,
                               select_cycle78_entries)
from core.cycle78d_best import (DESIGN_NAMES as _D3_DESIGN_NAMES,
                                JulD3State)
from core.new8_walk import MAX_HOLD  # noqa: F401  (re-export)

SYSTEM_NAME = "cycle78e"
JULY_CHECK_HOURS_UTC = (15, 17, 18)
CYCLE78E_CHECK_HOURS = JULY_CHECK_HOURS_UTC

POOL_FAMILIES = {
    "PLANB": ("jul_p07", "jul_p38"),
    "PLANB9": ("jul_b9_c07", "jul_b9_c06", "jul_b9_c17"),
    "PLANB9C": ("jul_b9c_c05", "jul_b9c_c03", "jul_b9c_c16"),
    "ROUND3": ("jul_r3_d26", "jul_r3_d21"),
    "ROUND4": ("jul_r4_e07", "jul_r4_e02"),
    "B13A": ("jul_b13a_c07", "jul_b13a_c01", "jul_b13a_c13"),
    "B13C": ("jul_b13c_c09", "jul_b13c_c04", "jul_b13c_c14"),
    "B13S": ("jul_b13s_c10",),
    "B13SB": ("jul_b13sb_r16",),
}
B13_DESIGN_NAMES = ("jul_b13a_c07", "jul_b13a_c01", "jul_b13a_c13",
                    "jul_b13c_c09", "jul_b13c_c04", "jul_b13c_c14",
                    "jul_b13s_c10", "jul_b13sb_r16")
DESIGN_NAMES = tuple(_D3_DESIGN_NAMES) + B13_DESIGN_NAMES
MIN_AGREE = 3
CCAP_AMOUNT = 100.0
COST = 2.5


# ================================================= ledger form ==
def cons_fills_ledger(base, pool_frames_by_family,
                      min_agree=MIN_AGREE, hours=JULY_CHECK_HOURS_UTC):
    """planE_transforms.cons_fills + cascade, verbatim semantics
    on walk-format frames (check / exit_time / symbol /
    direction / score / gross_pips)."""
    base = base.copy()
    base["check"] = pd.to_datetime(base["check"])
    if "exit_time" in base.columns:
        base["exit_time"] = pd.to_datetime(base["exit_time"])
    base = base.sort_values("check", kind="stable") \
        .reset_index(drop=True)

    def _as_frame(p):
        if isinstance(p, (list, tuple)):
            return pd.concat(list(p), ignore_index=True)
        return p

    pool_frames_by_family = {fam: _as_frame(p) for fam, p in
                             pool_frames_by_family.items()}
    frames = []
    for fam, p in pool_frames_by_family.items():
        p = p.copy()
        p["check"] = pd.to_datetime(p["check"])
        p["_fam"] = fam
        frames.append(p[["check", "symbol", "direction", "_fam"]]
                      .drop_duplicates())
    keys = pd.concat(frames, ignore_index=True)
    agree = keys.groupby(["check", "symbol", "direction"])["_fam"] \
        .nunique()
    good = set(agree[agree >= min_agree].index)
    reps = []
    for fam, p in pool_frames_by_family.items():
        p = p.copy()
        p["check"] = pd.to_datetime(p["check"])
        m = np.array([(c, s, d) in good for c, s, d in
                      zip(p["check"], p["symbol"], p["direction"])])
        reps.append(p[m])
    taken = [(r["check"], r["exit_time"], r["symbol"])
             for _, r in base.iterrows()]
    by_check_sym = {}
    for c, e, s in taken:
        by_check_sym.setdefault(c, set()).add(s)
    pool = pd.concat(reps, ignore_index=True)
    pool["check"] = pd.to_datetime(pool["check"])
    pool["exit_time"] = pd.to_datetime(pool["exit_time"])
    pool = pool.sort_values(["check", "score"],
                            ascending=[True, False], kind="stable")
    fills = []
    used = set()
    for _, r in pool.iterrows():
        c = r["check"]
        if hours is not None and c.hour not in hours:
            continue
        if c in used:
            continue
        if r["symbol"] in by_check_sym.get(c, set()):
            continue
        if any(s == r["symbol"] and c < e and r["exit_time"] > cc
               for (cc, e, s) in taken):
            continue
        fills.append(r)
        used.add(c)
        taken.append((c, r["exit_time"], r["symbol"]))
    if not fills:
        return base, dict(fills=0, agreed_keys=len(good))
    out = pd.concat([base, pd.DataFrame(fills)], ignore_index=True)
    out = out.sort_values("check", kind="stable") \
        .reset_index(drop=True)
    return out, dict(fills=len(fills), agreed_keys=len(good))


def ccap_ledger(df, amount=CCAP_AMOUNT):
    """planE_transforms.ccap(scope='symbol_day'), verbatim
    semantics: drop a later entry whose (symbol, check-day)
    running kept loss mass already reaches `amount`."""
    df = df.copy()
    df["check"] = pd.to_datetime(df["check"])
    df = df.sort_values("check", kind="stable").reset_index(drop=True)
    net = df["gross_pips"] - COST
    day = df["check"].dt.date
    key = list(zip(df["symbol"], day))
    mass = {}
    drop = np.zeros(len(df), dtype=bool)
    for i in range(len(df)):
        k = key[i]
        if mass.get(k, 0.0) >= amount:
            drop[i] = True
            continue
        if net.iat[i] < 0:
            mass[k] = mass.get(k, 0.0) + abs(net.iat[i])
    return df[~drop].reset_index(drop=True), \
        dict(dropped=int(drop.sum()), amount=amount,
             scope="symbol_day")


def build_e09(incumbent, pool_walks_by_family):
    """Full E09 ledger from the cycle78d stream + the 20 pool
    walks ({family: [walk frames]})."""
    out, info1 = cons_fills_ledger(incumbent, pool_walks_by_family)
    out, info2 = ccap_ledger(out)
    out["entry_time"] = out["check"] - pd.Timedelta(minutes=30)
    out["net"] = out["gross_pips"] - COST
    return out, dict(cons=info1, ccap=info2)


# ================================================== panel form ==
def _default_state_path():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "data", "walk_ledgers_new8",
                        f"{SYSTEM_NAME}.json")


class JulE09State(JulD3State):
    """JulD3State (cycle78d stream) + the CONS3/CCAP stage.

    Extra persisted state: the 8 B13 pool DesignWalks, the
    accepted E09 fills (pre-CCAP), and the CCAP running loss
    mass per (symbol, day). step() returns the accepted
    NON-BASE rows for the panel (D3 extras that survive CCAP,
    plus the E09 fill when it survives); a base row dropped by
    CCAP at the current check is reported via
    self.last_base_dropped (strategy id or None)."""

    def __init__(self, path=None):
        super().__init__(path=path)
        from core.new8_designs import DESIGNS
        from core.new8_walk import DesignWalk
        self.b13_walks = {
            dn: DesignWalk(DESIGNS[dn]["equations"],
                           veto=DESIGNS[dn]["veto"])
            for dn in B13_DESIGN_NAMES}
        self.e09_fills = []
        self.ccap_mass = {}
        self.last_base_dropped = None
        self.last_kept_base = []

    # ------------------------------------------------ persist --
    def save(self, path=None):
        p = path or self.path
        if not p:
            return None
        os.makedirs(os.path.dirname(os.path.abspath(p)),
                    exist_ok=True)

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
            "base_all_checks": [pd.Timestamp(c).isoformat()
                                for c in self.base_all_checks],
            "base_picks": ser(self.base_picks),
            "fills": ser(self.fills),
            "cascade_taken": [
                [s, pd.Timestamp(e).isoformat(),
                 pd.Timestamp(x).isoformat()]
                for s, e, x in self.cascade_taken],
            "walks": {n: {"picks": ser(w.picks),
                          "open_exit": {
                              s: [pd.Timestamp(x).isoformat()
                                  for x in xs]
                              for s, xs in w.open_exit.items()}}
                      for n, w in self.walks.items()},
            "b13_walks": {n: {"picks": ser(w.picks),
                              "open_exit": {
                                  s: [pd.Timestamp(x).isoformat()
                                      for x in xs]
                                  for s, xs in w.open_exit.items()}}
                          for n, w in self.b13_walks.items()},
            "e09_fills": ser(self.e09_fills),
            "ccap_mass": {f"{s}|{d}": v
                          for (s, d), v in self.ccap_mass.items()},
        }
        with open(p, "w") as fh:
            json.dump(data, fh)
        return p

    @classmethod
    def load(cls, path):
        with open(path) as fh:
            data = json.load(fh)
        st = cls(path=path)

        def de(rows):
            out = []
            for r in rows:
                d = dict(r)
                for k in ("check", "entry_time", "exit_time"):
                    if d.get(k) is not None:
                        d[k] = pd.Timestamp(d[k])
                out.append(d)
            return out

        st.base_all_checks = [pd.Timestamp(c)
                              for c in data.get("base_all_checks", [])]
        st.base_picks = de(data.get("base_picks", []))
        st.fills = de(data.get("fills", []))
        st.cascade_taken = [
            (s, pd.Timestamp(e), pd.Timestamp(x))
            for s, e, x in data.get("cascade_taken", [])]
        for store, walks in (("walks", st.walks),
                             ("b13_walks", st.b13_walks)):
            for n, wd in (data.get(store) or {}).items():
                if n not in walks:
                    continue
                walks[n].picks = de(wd.get("picks", []))
                walks[n].open_exit = {
                    s: [pd.Timestamp(x) for x in xs]
                    for s, xs in (wd.get("open_exit") or {}).items()}
        st.e09_fills = de(data.get("e09_fills", []))
        st.ccap_mass = {}
        for k, v in (data.get("ccap_mass") or {}).items():
            s, d = k.rsplit("|", 1)
            st.ccap_mass[(s, pd.Timestamp(d).date())] = float(v)
        return st

    # ---------------------------------------------------- step --
    def _ccap_admit(self, row):
        """CCAP gate for one merged-stream row (in order).
        Returns True when the row is kept."""
        gross = row.get("gross_pips")
        if gross is None or (isinstance(gross, float)
                             and np.isnan(gross)):
            return True  # provisional exit: admitted, no mass yet
        net = float(gross) - COST
        k = (row["symbol"], pd.Timestamp(row["check"]).date())
        if self.ccap_mass.get(k, 0.0) >= CCAP_AMOUNT:
            return False
        if net < 0:
            self.ccap_mass[k] = self.ccap_mass.get(k, 0.0) + abs(net)
        return True

    def step(self, ctx, check, incumbent_entries):
        chk = pd.Timestamp(check)
        n_base0 = len(self.base_picks)
        n_fill0 = len(self.fills)
        emitted = super().step(ctx, check, incumbent_entries)
        # -- step the B13 pool walks for this check
        for dn, w in self.b13_walks.items():
            w.step(chk, ctx.rows_at(dn, chk))
        # -- pool rows at this check, by family
        fam_rows = {}
        for fam, dns in POOL_FAMILIES.items():
            rows = []
            for dn in dns:
                w = self.walks.get(dn) or self.b13_walks.get(dn)
                if w is not None and w.picks \
                        and pd.Timestamp(w.picks[-1]["check"]) == chk:
                    rows.append(w.picks[-1])
            fam_rows[fam] = rows
        # -- agreement: (symbol, direction) in >= MIN_AGREE families
        fams_by_key = {}
        for fam, rows in fam_rows.items():
            for r in rows:
                fams_by_key.setdefault(
                    (r["symbol"], r["direction"]), set()).add(fam)
        good = {k for k, fs in fams_by_key.items()
                if len(fs) >= MIN_AGREE}
        fill = None
        if good and chk.hour in JULY_CHECK_HOURS_UTC:
            taken = [(pd.Timestamp(r["check"]),
                      pd.Timestamp(r["exit_time"]), r["symbol"])
                     for r in self.base_picks + self.fills
                     + self.e09_fills]
            base_syms = {r["symbol"] for r in
                         self.base_picks + self.fills
                         if pd.Timestamp(r["check"]) == chk}
            cands = [r for rows in fam_rows.values() for r in rows
                     if (r["symbol"], r["direction"]) in good]
            # stable sort by score desc; ties keep the family /
            # design order above (the ledger concat order).
            cands.sort(key=lambda r: -float(r["score"]))
            for r in cands:
                if r["symbol"] in base_syms:
                    continue
                if any(s == r["symbol"] and chk < e
                       and pd.Timestamp(r["exit_time"]) > cc
                       for (cc, e, s) in taken):
                    continue
                fill = dict(r)
                break
        # -- merged order at this check: D3 base rows (incl. the
        #    C18 add), D3 fills, then the E09 fill; CCAP gates
        #    each in order
        new_base = self.base_picks[n_base0:]
        new_fills = self.fills[n_fill0:]
        self.last_base_dropped = None
        dropped_ids = set()
        emitted_ids = {id(r) for r in emitted}
        for r in new_base:
            if not self._ccap_admit(r):
                dropped_ids.add(id(r))
                if id(r) not in emitted_ids:
                    # a true base pick: the panel must drop it
                    self.last_base_dropped = r["strategy"]
        for r in new_fills:
            if not self._ccap_admit(r):
                dropped_ids.add(id(r))
        kept_extras = [r for r in emitted
                       if id(r) not in dropped_ids]
        self.last_kept_base = [
            r for r in new_base
            if id(r) not in dropped_ids and id(r) not in emitted_ids]
        if fill is not None:
            self.e09_fills.append(fill)
            if self._ccap_admit(fill):
                kept_extras.append(fill)
        return kept_extras


def load_e09_state(path=None):
    p = path or _default_state_path()
    try:
        return JulE09State.load(p)
    except Exception:
        return JulE09State(path=p)


def is_cycle78e_check_time(ts) -> bool:
    return is_cycle78_check_time(ts)


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full E09 entries for one check: pruned cycle78 base
    entries plus the D3 extras and the CONS3 fill accepted
    through this system's persisted state (CCAP applied)."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row)
    from core.cycle78d_best import PRUNE_LEGS
    sig = evaluate_cycle78_signals(frames, check_time_utc,
                                   m15_frames=m15_frames)
    if sig is not None and len(sig) == 0 and sig.attrs.get("status"):
        return sig
    entries = select_cycle78_entries(
        sig, open_symbols=open_symbols,
        live_count=len({str(s).upper() for s in (open_symbols or ())}),
        m15_frames=m15_frames, check_time_utc=check_time_utc)
    if entries is None:
        entries = pd.DataFrame()
    kept = entries
    if len(entries) and "equation" in entries.columns:
        kept = entries[~entries["equation"].astype(str)
                       .isin(PRUNE_LEGS)]
    state = load_e09_state()
    ctx = CandidateContext(frames, m15_frames, DESIGN_NAMES)
    accepted = state.step(ctx, check_time_utc, entries)
    state.save()
    if state.last_base_dropped is not None and len(kept):
        kept = kept[kept["equation"].astype(str)
                    != state.last_base_dropped]
    if accepted:
        extra = pd.DataFrame([candidate_signal_row(r)
                              for r in accepted])
        kept = (pd.concat([kept, extra], ignore_index=True)
                if len(kept) else extra)
    return kept if kept is not None else pd.DataFrame()


# ------------------------------------------------- coordinator
# fold-in wrappers: the July single panel and the signal router
# call the evaluate/select pair; both delegate to this module's
# panel_entries (the gated E09 construction).
def fetch_cycle78e_m15_frames(state=None):
    from core.cycle78_best import fetch_cycle78_m15_frames
    try:
        return fetch_cycle78_m15_frames(state)
    except TypeError:
        return fetch_cycle78_m15_frames()


def evaluate_cycle78e_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    """Final E09 entries for the check, as the signals frame
    (panel_entries already applies the prune + state fills)."""
    return panel_entries(frames, check_time_utc,
                         m15_frames=m15_frames)


def select_cycle78e_entries(signals: pd.DataFrame,
                            open_symbols=()):
    """Open-symbol filter over the evaluated E09 entries."""
    if signals is None or len(signals) == 0:
        return signals
    if signals.attrs.get("status"):
        return signals
    open_set = {str(s).upper() for s in (open_symbols or ())}
    if not open_set or "symbol" not in signals.columns:
        return signals
    return signals[~signals["symbol"].astype(str)
                   .str.upper().isin(open_set)]
