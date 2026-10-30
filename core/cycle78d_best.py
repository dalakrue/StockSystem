"""Cycle 78D (R2 D3) -- July IMPROVED system, integrated
2026-10-30 from 20-Cycle Round R2 (jul_planA_s1_attempt4.md).

Definition (ledger form, run_jul_attempt4.py verbatim):
  base  = cycle78 incumbent stream with four legs pruned
          post-selection (no fall-through):
          FB_AUDUSD_h17_0_G (the C18 prune),
          FB_EURUSD_h15_0_G + FB_USDJPY_h15_2_G (T7 base),
          mom_USDCAD_h15_momB_T1.5_A1.0_1.25x8 (CARRIER_2).
  C18   = PLANB cand1 (design 'jul_p07') walk rows added at
          checks the UNPRUNED incumbent never took (check
          rule only, no symbol-overlap rule -- the attempt-4
          construction), applied before the T7/C2 prunes.
  fill  = B04 second-best: priority cascade over the 14 Jul
          pool design walks (run_jul_planB_s1.cascade,
          reversed-chrono order, max 1 pick per check, global
          symbol-interval conflict vs taken fills), with the
          CARRIER_1 leg q_wt1_lt75_GBPNZD_h15_0.9x7.0_H48_2
          dropped from the cascade output before the merge
          (attempt-4 code: sb_no_c1 = sb04 minus that leg;
          the cascade itself still takes those rows, so they
          block replacements exactly as in the research
          ledger), merged second-priority vs the pruned base
          by attempt-4 combine() (check_busy + symbol
          overlap vs base and accepted fills).

Published battery (research ledger; re-graded on the
app-replayed ledger at integration): DISC leftover 89.11%,
AUDIT 77.01%, LCT Jul 100.00/80.05, MC verbatim flag TRUE
(DD p95 172.54 <= own cap 188.51), PBO 20% / DSR 1.0000
(canonical family-10), decay not FAIL.
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from core.cycle78_best import (CYCLE78_CHECK_HOURS,
                               evaluate_cycle78_signals,
                               is_cycle78_check_time,
                               select_cycle78_entries)
from core.new8_walk import MAX_HOLD

SYSTEM_NAME = "cycle78d"
CYCLE78D_CHECK_HOURS = CYCLE78_CHECK_HOURS

PRUNE_LEGS = (
    "FB_AUDUSD_h17_0_G",                      # C18 prune
    "FB_EURUSD_h15_0_G", "FB_USDJPY_h15_2_G",  # T7 base
    "mom_USDCAD_h15_momB_T1.5_A1.0_1.25x8",   # CARRIER_2
)
CARRIER_1 = "q_wt1_lt75_GBPNZD_h15_0.9x7.0_H48_2"

# Pool designs in run_jul_planB_s1 POOL_FILES (chrono) order,
# mapped to their DESIGNS keys (upload/designs_jul.py).
POOL_ORDER = (
    ("cand1", "jul_c12"), ("cand2", "jul_c05"),
    ("PLANB_cand1", "jul_p07"), ("PLANB_cand2", "jul_p38"),
    ("PLANB9_cand1", "jul_b9_c07"), ("PLANB9_cand2", "jul_b9_c06"),
    ("PLANB9_partner", "jul_b9_c17"),
    ("PLANB9C_cand1", "jul_b9c_c05"),
    ("PLANB9C_cand2", "jul_b9c_c03"),
    ("PLANB9C_partner", "jul_b9c_c16"),
    ("ROUND3_cand1", "jul_r3_d26"), ("ROUND3_cand2", "jul_r3_d21"),
    ("ROUND4_cand1", "jul_r4_e07"), ("ROUND4_cand2", "jul_r4_e02"),
)
DESIGN_NAMES = tuple(dn for _, dn in POOL_ORDER)
CASCADE_ORDER = tuple(reversed(DESIGN_NAMES))  # B04


# ================================================= ledger form --
def build_c18(incumbent, planb_cand1_walk):
    """Attempt-4 C18: prune FB_AUDUSD_h17_0_G from the
    incumbent; add PLANB cand1 walk rows whose check the
    unpruned incumbent never took."""
    inc = incumbent.sort_values("check").reset_index(drop=True)
    keep = inc[inc["strategy"] != "FB_AUDUSD_h17_0_G"]
    add = planb_cand1_walk[
        ~planb_cand1_walk["check"].isin(set(inc["check"]))].copy()
    for c in inc.columns:
        if c not in add.columns:
            add[c] = np.nan
    out = pd.concat([keep, add[inc.columns]], ignore_index=True) \
        .sort_values("check").reset_index(drop=True)
    out["entry_time"] = out["check"] - pd.Timedelta(minutes=30)
    out["exit_time"] = pd.to_datetime(out["exit_time"])
    return out


def cascade_b04(design_walks):
    """run_jul_planB_s1.cascade(reversed(chrono)) verbatim.
    design_walks: {src label: walk ledger frame} for the
    POOL_ORDER sources; frames carry check / entry_time /
    exit_time / symbol."""
    rows_by_check = {}
    order = [src for src, _ in reversed(POOL_ORDER)]
    by_src = design_walks
    for nm in order:
        for _, r in by_src[nm].iterrows():
            rows_by_check.setdefault(r["check"], []).append(r)
    # rows_by_check lists were appended in scan order per
    # check only if designs are iterated in scan order; the
    # loop above does exactly that (reversed chrono).
    taken, taken_iv = [], []
    for chk in sorted(rows_by_check):
        got = 0
        for r in rows_by_check[chk]:
            if got >= 1:
                break
            if any(r["symbol"] == s and r["entry_time"] < x
                   and e < r["exit_time"] for s, e, x in taken_iv):
                continue
            taken.append(r)
            taken_iv.append((r["symbol"], r["entry_time"],
                             r["exit_time"]))
            got += 1
    if not taken:
        return by_src[order[0]].iloc[0:0].copy()
    return pd.DataFrame(taken).sort_values("check") \
        .reset_index(drop=True)


def combine(base, sb):
    """run_jul_attempt4.combine verbatim (second-priority
    merge: check_busy + symbol overlap vs base, accepted
    rows extend occupancy). Returns (combined, n_accepted,
    drops)."""
    base_checks = set(base["check"])
    iv = {}
    for _, r in base.iterrows():
        iv.setdefault(r["symbol"], []).append((r["entry_time"],
                                               r["exit_time"]))

    def ov(sym, e, x):
        return any(e < xx and ee < x for ee, xx in iv.get(sym, []))
    acc, drops = [], dict(check_busy=0, symbol_overlap=0)
    for _, r in sb.sort_values("check").iterrows():
        if r["check"] in base_checks:
            drops["check_busy"] += 1
            continue
        if ov(r["symbol"], r["entry_time"], r["exit_time"]):
            drops["symbol_overlap"] += 1
            continue
        acc.append(r)
        iv.setdefault(r["symbol"], []).append((r["entry_time"],
                                               r["exit_time"]))
    keep = list(base.columns)
    parts = [base[keep]]
    if acc:
        acc_df = pd.DataFrame(acc)
        for c in keep:
            if c not in acc_df.columns:
                acc_df[c] = np.nan
        parts.append(acc_df[keep])
    comb = pd.concat(parts, ignore_index=True) \
        .sort_values("check").reset_index(drop=True)
    return comb, len(acc), drops


def build_d3(incumbent, planb_cand1_walk, design_walks):
    """Full D3 ledger from the incumbent stream + the 14
    design walks ({src: frame}; design_walks['PLANB_cand1']
    must be the same frame as planb_cand1_walk)."""
    c18 = build_c18(incumbent, planb_cand1_walk)
    sb04 = cascade_b04(design_walks)
    t7_base = c18[~c18["strategy"].isin(
        ["FB_EURUSD_h15_0_G", "FB_USDJPY_h15_2_G"])] \
        .reset_index(drop=True)
    base_no_c2 = t7_base[t7_base["strategy"]
                         != "mom_USDCAD_h15_momB_T1.5_A1.0_1.25x8"] \
        .reset_index(drop=True)
    sb_no_c1 = sb04[sb04["strategy"] != CARRIER_1] \
        .reset_index(drop=True)
    d3, _nacc, _drops = combine(base_no_c2, sb_no_c1)
    return d3


# ================================================== panel form --
def _default_state_path():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "data", "walk_ledgers_new8",
                        f"{SYSTEM_NAME}.json")


class JulD3State:
    """Persisted streaming state for cycle78d (panel path).

    Holds one DesignWalk per pool design (each stepped once
    per check; the jul_p07 pick feeds both the C18 layer and
    the cascade, exactly as its ledger row does in research),
    the recorded base picks, the cascade's taken intervals
    (CARRIER_1 rows included -- taken, then dropped) and the
    accepted D3 fills. Veto factories are (re)bound from the
    CandidateContext on each step (m15 / adx25 / dxv need
    context data; d1v is DesignWalk's inline rule)."""

    def __init__(self, path=None):
        from core.new8_designs import DESIGNS
        try:
            from designs_jul import add_jul_designs
            add_jul_designs(DESIGNS)
        except Exception:
            pass
        from core.new8_walk import DesignWalk
        self.path = path
        self.designs = DESIGNS
        self.walks = {dn: DesignWalk(DESIGNS[dn]["equations"],
                                     veto=DESIGNS[dn]["veto"])
                      for _src, dn in POOL_ORDER}
        self.base_all_checks = []   # unpruned incumbent checks
        self.base_picks = []        # pruned base + C18 adds
        self.cascade_taken = []     # (symbol, entry, exit)
        self.fills = []             # accepted D3 fills
        self._bound_ctx = None

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
        for n, wd in (data.get("walks") or {}).items():
            if n not in st.walks:
                continue
            st.walks[n].picks = de(wd.get("picks", []))
            st.walks[n].open_exit = {
                s: [pd.Timestamp(x) for x in xs]
                for s, xs in (wd.get("open_exit") or {}).items()}
        return st

    # -------------------------------------------------- exits --
    def _sim_exit(self, ctx, row):
        from core.new8_features import pip_size_new8
        from core.new8_walk import sim_fixed_vec
        oc = ctx.ohlc.get(row["symbol"])
        if oc is None:
            return False
        ent_pos = oc["pos_of"].get_indexer(
            [pd.Timestamp(row["entry_time"])])[0]
        if ent_pos < 0:
            return False
        pip = pip_size_new8(row["symbol"])
        r = sim_fixed_vec(oc["o"], oc["h"], oc["l"], oc["c"],
                          np.array([ent_pos]), row["direction"],
                          np.array([row["tp_pips_used"]]),
                          np.array([row["sl_pips_used"]]), pip,
                          max_hold=int(row.get("max_hold", MAX_HOLD)),
                          cost=2.5)
        row["exit_px"] = float(r["exit_px"][0])
        row["exit_time"] = pd.Timestamp(oc["dt"][r["exit_pos"][0]])
        row["exit_reason"] = str(r["exit_reason"][0])
        row["hold_h"] = int(r["hold_h"][0])
        row["gross_pips"] = float(r["gross_pips"][0])
        row["net_pips"] = float(r["net_pips"][0])
        return ent_pos + int(row.get("max_hold", MAX_HOLD)) - 1 \
            < len(oc["c"])

    def _refresh_exits(self, ctx):
        for row in self.base_picks + self.fills:
            if row.get("exit_final"):
                continue
            if self._sim_exit(ctx, row):
                row["exit_final"] = True

    # -------------------------------------------------- vetoes --
    def _bind(self, ctx):
        if self._bound_ctx is ctx:
            return
        from core.new8_walk import (make_adx25v, make_dxv,
                                    make_m15v, wilder_adx14)
        for _src, dn in POOL_ORDER:
            d = self.designs[dn]
            w = self.walks[dn]
            if d["veto"] == "m15":
                mc = {}
                for e in d["equations"]:
                    s = e["symbol"]
                    if s in ctx.m15:
                        f = ctx.m15[s]
                        mc[s] = (f.index.view("int64"),
                                 f["Close"].to_numpy(float))
                w.veto_fn = make_m15v(mc) if mc else None
            elif d["veto"] == "adx25":
                am = {}
                for e in d["equations"]:
                    s = e["symbol"]
                    if s in ctx.frames:
                        f = ctx.frames[s]
                        am[s] = (f.index, wilder_adx14(
                            f["High"].to_numpy(float),
                            f["Low"].to_numpy(float),
                            f["Close"].to_numpy(float)))
                w.veto_fn = make_adx25v(am, d["veto_threshold"]) \
                    if am else None
            elif d["veto"] == "dxv":
                w.veto_fn = make_dxv(ctx._dx_mom) \
                    if getattr(ctx, "_dx_mom", None) is not None \
                    else None
            # 'd1v' / None: DesignWalk inline / no veto.
        self._bound_ctx = ctx

    # ---------------------------------------------------- step --
    def step(self, ctx, check, incumbent_entries):
        """One check. incumbent_entries: the cycle78 selected
        entries (signal frame, UNPRUNED) at this check. The
        prune, C18 layer, B04 cascade and D3 combine are all
        applied here. Returns accepted non-base rows (C18 add
        + at most one fill) as walk-format dicts."""
        chk = pd.Timestamp(check)
        ent = chk - pd.Timedelta(minutes=30)
        self._bind(ctx)
        self._refresh_exits(ctx)
        emitted = []
        # -- record base: all checks (C18 exclusion set) + kept
        if incumbent_entries is not None \
                and len(incumbent_entries):
            if chk not in self.base_all_checks:
                self.base_all_checks.append(chk)
            for _, e in incumbent_entries.iterrows():
                strat = str(e.get("equation", e.get("strategy", "")))
                if strat in PRUNE_LEGS:
                    continue
                if any(pd.Timestamp(r["check"]) == chk
                       for r in self.base_picks):
                    continue
                row = dict(
                    check=chk, entry_time=ent,
                    symbol=str(e["symbol"]),
                    direction=str(e["direction"]), strategy=strat,
                    score=float(e["score"]) if "score" in e
                    and pd.notna(e["score"]) else float("nan"),
                    entry_px=float(e["entry_px"]),
                    tp_pips_used=float(e["tp_pips"]),
                    sl_pips_used=float(e["sl_pips"]),
                    exit_px=None, exit_time=ent + pd.Timedelta(
                        hours=MAX_HOLD),
                    exit_reason=None, hold_h=None, gross_pips=None,
                    net_pips=None, exit_final=False)
                if self._sim_exit(ctx, row):
                    row["exit_final"] = True
                self.base_picks.append(row)
        # -- step every design walk once
        picks = {}
        for _src, dn in POOL_ORDER:
            picks[dn] = self.walks[dn].step(chk, ctx.rows_at(dn, chk))
        # -- C18 layer: PLANB cand1 at checks the unpruned
        #    incumbent never took (check rule only)
        p07 = picks.get("jul_p07")
        if p07 is not None and chk not in self.base_all_checks:
            add = dict(p07)
            add["exit_final"] = not p07.get("provisional_exit", False)
            add.pop("provisional_exit", None)
            self.base_picks.append(add)
            emitted.append(add)
        # -- B04 cascade over the 14 picks (reversed chrono)
        cand = None
        for dn in CASCADE_ORDER:
            p = picks.get(dn)
            if p is None:
                continue
            if any(p["symbol"] == s and p["entry_time"] < x
                   and e < p["exit_time"]
                   for s, e, x in self.cascade_taken):
                continue
            self.cascade_taken.append(
                (p["symbol"], pd.Timestamp(p["entry_time"]),
                 pd.Timestamp(p["exit_time"])))
            if p["strategy"] != CARRIER_1:
                cand = p
            break
        # -- D3 combine for the cascade candidate
        if cand is not None:
            busy = any(pd.Timestamp(r["check"]) == chk
                       for r in self.base_picks)
            ovl = any(cand["symbol"] == r["symbol"]
                      and cand["entry_time"] < r["exit_time"]
                      and r["entry_time"] < cand["exit_time"]
                      for r in self.base_picks + self.fills)
            if not busy and not ovl:
                fill = dict(cand)
                fill["exit_final"] = not cand.get(
                    "provisional_exit", False)
                fill.pop("provisional_exit", None)
                self.fills.append(fill)
                emitted.append(fill)
        return emitted


def load_jul_state(path=None):
    p = path or _default_state_path()
    try:
        return JulD3State.load(p)
    except Exception:
        return JulD3State(path=p)


def is_cycle78d_check_time(ts) -> bool:
    return is_cycle78_check_time(ts)


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full D3 entries for one check: pruned cycle78 base
    entries plus the C18 add / B04 fill accepted through this
    system's persisted state."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row)
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
    state = load_jul_state()
    ctx = CandidateContext(frames, m15_frames, DESIGN_NAMES)
    accepted = state.step(ctx, check_time_utc, entries)
    state.save()
    if accepted:
        extra = pd.DataFrame([candidate_signal_row(r)
                              for r in accepted])
        kept = (pd.concat([kept, extra], ignore_index=True)
                if len(kept) else extra)
    return kept if kept is not None else pd.DataFrame()


# ------------------------------------------------- coordinator
# fold-in wrappers (2026-10-30): the July single panel and the
# signal router call the evaluate/select pair; both delegate
# to this module's panel_entries (the gated D3 construction).
def fetch_cycle78d_m15_frames(state=None):
    from core.cycle78_best import fetch_cycle78_m15_frames
    try:
        return fetch_cycle78_m15_frames(state)
    except TypeError:
        return fetch_cycle78_m15_frames()


def evaluate_cycle78d_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    """Final D3 entries for the check, as the signals frame
    (panel_entries already applies the prune + state fills)."""
    return panel_entries(frames, check_time_utc,
                         m15_frames=m15_frames)


def select_cycle78d_entries(signals: pd.DataFrame,
                            open_symbols=()):
    """Open-symbol filter over the evaluated D3 entries."""
    if signals is None or len(signals) == 0:
        return signals
    if signals.attrs.get("status"):
        return signals
    open_set = {str(s).upper() for s in (open_symbols or ())}
    if not open_set or "symbol" not in signals.columns:
        return signals
    return signals[~signals["symbol"].astype(str)
                   .str.upper().isin(open_set)]
