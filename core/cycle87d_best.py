"""Cycle 87D -- April candidate, Round R2 winner
C19-sim in its SHIPPABLE dollar-free app form,
validated 2026-10-30 on the upload tree
(work_20cyc_r2/upload/VERDICT_APR.md; gate script
upload/gate_apr.py, machine record upload/gate_apr.json).

Definition: the shipped April combined stream
(cycle87c best + cycle87s second-best combined layer:
research base 897 + apr_q09 / apr_pvote / apr_pvsb
walks under core.new8_walk.build_combined occupancy =
the 946-pick incumbent) with ONE slot vetoed at ledger
level -- FB_NZDUSD_h17_0 (65 picks removed, 55 checks
freed) -- refilled in app order from the candidate
walks (apr_q09 -> apr_pvote -> apr_pvsb, apr_sim refill
rule), then the PLANB9C cand1 partner design
('apr_b9c', 45 equations, S-CLU3DC) merged
second-priority (merge_partner verbatim).

Why this form: the simulated C19 ledger (921 picks)
replayed through app code gives 924 picks, because the
shipped apr_q09 design excludes the 11 dollar equations
(2026-10-27 dollar purge -- dollar is never traded), so
its walk substitutes FX picks at 6 checks where the
stored full walk took a DOLLARIDX equation. That
app-true 924-pick form was re-graded as the candidate
and passes EVERY locked gate (@2.5):

  DISC  n731 net +7359.92, leftover 91.24% (inc 85.26),
        win 98.50%, epd 4.325
  AUDIT n193 net +2153.64, leftover 76.25% (inc 71.26,
        strictly above), win 95.34%, epd 4.386
  LCT P 100.0% / q05 82.96% (middle + strict PASS)
  MC middle PASS (P(profit) 1.0, DD p95 177.22,
     cluster p95 102.50, consec p95 1)
  PBO 0.00% / DSR 1.0000, decay PASS
  (simulated C19 for comparison: DISC leftover 90.58%,
   AUDIT 76.25% / +2153.64, LCT 96.82 / 82.72 -- the
   app-true form's extra refills are all DISC and
   net-positive; AUDIT is identical.)

Refills in the graded construction: q09 31, pvote 4,
pvsb 0; partner accepted 8. The veto+refill-only
alternate (C20-app, 916 picks) also passes all gates
but is NOT selected -- C19-app takes precedence.

Design data frozen in core.new8_designs ('apr_q09',
'apr_pvote', 'apr_pvsb', 'apr_b9c'). Registry wiring
(core.signal_mode) is central and NOT done here.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import core.cycle87c_best as _c87c
from core.cycle87c_best import (CYCLE87C_CHECK_HOURS,
                                evaluate_cycle87c_signals,
                                is_cycle87c_check_time,
                                select_cycle87c_entries)

CYCLE87D_CHECK_HOURS = CYCLE87C_CHECK_HOURS
REFILL_DESIGNS = ("apr_q09", "apr_pvote", "apr_pvsb")
PARTNER_DESIGN = "apr_b9c"
DESIGNS = REFILL_DESIGNS + (PARTNER_DESIGN,)
SYSTEM_NAME = "cycle87d"
VETO_STRATEGY = "FB_NZDUSD_h17_0"
_DESIGN_SYMBOLS = ("AUDJPY", "AUDUSD", "CADCHF", "CADJPY",
                   "CHFJPY", "EURCHF", "EURNZD", "GBPAUD",
                   "GBPJPY", "NZDCHF", "NZDJPY", "USDCHF",
                   "USDJPY")
_COLS = ["check", "symbol", "direction", "strategy",
         "entry_time", "exit_time", "gross_pips"]


def evaluate_cycle87d_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    return evaluate_cycle87c_signals(frames, check_time_utc,
                                     m15_frames=m15_frames)


def select_cycle87d_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    return select_cycle87c_entries(signals,
                                   open_symbols=open_symbols)


def is_cycle87d_check_time(ts) -> bool:
    return is_cycle87c_check_time(ts)


def fetch_cycle87d_m15_frames(state=None):
    from core.cycle87_best import fetch_cycle87_m15_frames
    return fetch_cycle87_m15_frames()


# ------------------------------------------------ ledger form --
def prep(df: pd.DataFrame) -> pd.DataFrame:
    """gate_apr.prep verbatim: normalise timestamps, add
    entry_time (check - 30m) when absent, net_pips @2.5."""
    df = df.copy()
    for c in ("check", "exit_time"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c].astype(str).str.replace(
                r"\+00:00$", "", regex=True))
    if "entry_time" not in df.columns:
        df["entry_time"] = df["check"] - pd.Timedelta(minutes=30)
    df["entry_time"] = pd.to_datetime(df["entry_time"].astype(str)
                                      .str.replace(r"\+00:00$", "",
                                                   regex=True))
    df = df.sort_values("check", kind="stable").reset_index(drop=True)
    df["net_pips"] = df["gross_pips"] - 2.5
    return df


def walk_pool(walk: pd.DataFrame) -> pd.DataFrame:
    """A raw candidate walk frame -> the prep'd pool frame
    gate_apr.walk_pool builds from walk_<layer>.csv."""
    w = walk.copy()
    for c in ("check", "exit_time"):
        w[c] = pd.to_datetime(w[c])
    w["entry_time"] = w["check"] - pd.Timedelta(minutes=30)
    return prep(w[_COLS])


def _overlaps(arr, e, x):
    if arr is None or len(arr) == 0:
        return False
    a = np.asarray(arr)
    return bool(((a[:, 0] < x) & (e < a[:, 1])).any())


def refill(stream: pd.DataFrame, cand: pd.DataFrame):
    """gate_apr.refill verbatim (apr_sim refill rule):
    accept candidate rows, in check order, only at checks
    carrying no pick in the current stream and with no
    symbol time-overlap vs the stream or earlier refills.
    Returns (stream, accepted_rows_list)."""
    S = stream.copy()
    checks = set(S["check"])
    by_sym = {s: [tuple(v) for v in g[["entry_time", "exit_time"]]
                  .values] for s, g in S.groupby("symbol")}
    acc = []
    for _, r in cand.sort_values("check", kind="stable").iterrows():
        if r["check"] in checks:
            continue
        if _overlaps(by_sym.get(r["symbol"]), r["entry_time"],
                     r["exit_time"]):
            continue
        acc.append(r)
        checks.add(r["check"])
        by_sym.setdefault(r["symbol"], []).append(
            (r["entry_time"], r["exit_time"]))
    if acc:
        S = pd.concat([S, pd.DataFrame(acc)], ignore_index=True) \
            .sort_values("check", kind="stable").reset_index(drop=True)
    return S, acc


def merge_partner(cand: pd.DataFrame, base: pd.DataFrame):
    """gate_apr.merge_partner verbatim: second-priority
    merge of a prep'd partner pool over `base` (dollar
    rows excluded; check_busy / symbol_overlap drops).
    Returns (combined, n_accepted, drops, n_dollar)."""
    cand = prep(cand)
    n_dollar = int((cand.symbol == "DOLLARIDX").sum())
    cand = cand[cand.symbol != "DOLLARIDX"]
    inc_checks = set(base["check"])
    inc_by_sym = {s: g[["entry_time", "exit_time"]].values
                  for s, g in base.groupby("symbol")}
    acc_by_sym, acc = {}, []
    drops = dict(check_busy=0, symbol_overlap=0)

    def ov(arr, e, x):
        return arr is not None and len(arr) and bool(
            ((arr[:, 0] < x) & (e < arr[:, 1])).any())

    for _, r in cand.sort_values("check", kind="stable").iterrows():
        if r["check"] in inc_checks:
            drops["check_busy"] += 1
            continue
        a2 = np.array(acc_by_sym.get(r.symbol, [])).reshape(-1, 2) \
            if acc_by_sym.get(r.symbol) else None
        if ov(inc_by_sym.get(r.symbol), r.entry_time, r.exit_time) \
                or ov(a2, r.entry_time, r.exit_time):
            drops["symbol_overlap"] += 1
            continue
        acc.append(r)
        acc_by_sym.setdefault(r.symbol, []).append(
            (r.entry_time, r.exit_time))
    acc_df = pd.DataFrame(acc)
    acc_df = acc_df[_COLS] if len(acc_df) else base[_COLS].iloc[0:0]
    comb = pd.concat([base[_COLS], acc_df], ignore_index=True) \
        .sort_values("check", kind="stable").reset_index(drop=True)
    comb["net_pips"] = comb["gross_pips"] - 2.5
    return comb, len(acc), drops, n_dollar


def _new_rows(walk: pd.DataFrame, stream: pd.DataFrame):
    keys = set(zip(stream["check"], stream["strategy"]))
    return walk[[k not in keys
                 for k in zip(walk["check"], walk["strategy"])]]


def build_cycle87d_ledger(combined: pd.DataFrame, walks: dict,
                          partner: bool = True):
    """The graded C19-app construction (gate_apr verbatim):
    veto VETO_STRATEGY from the incumbent combined stream,
    refill in app order apr_q09 -> apr_pvote -> apr_pvsb
    from the walks, then (partner=True) merge the apr_b9c
    partner walk last. `walks` maps design name -> raw
    walk frame (walk_<layer>.csv shape). With
    partner=False this builds the C20-app alternate.
    Returns (ledger, details)."""
    stream = prep(combined[_COLS])
    vetoed = stream[~stream.strategy.isin([VETO_STRATEGY])] \
        .reset_index(drop=True)
    details = {"veto_removed": int(len(stream) - len(vetoed))}
    pools = {n: walk_pool(walks[n]) for n in DESIGNS}
    sim = vetoed
    det = {}
    for nm, key in (("q09", "apr_q09"), ("pvote", "apr_pvote"),
                    ("pvsb", "apr_pvsb")):
        sim, acc = refill(sim, _new_rows(pools[key], sim))
        det[nm] = len(acc)
    details["refills"] = det
    if partner:
        sim, pacc, pdrops, pdol = merge_partner(pools[PARTNER_DESIGN],
                                                sim)
        details["partner"] = dict(accepted=int(pacc), drops=pdrops,
                                   dollar=int(pdol))
    return sim, details


# ------------------------------------------------- panel form --
def _cand_m15(m15_frames):
    """The candidate designs' M15 legs need M15 (with
    Volume) for their symbols; top up via the shared path."""
    from core.new8_candidate import ensure_m15
    return ensure_m15(m15_frames, _DESIGN_SYMBOLS)


def _entry_strategy(row):
    for c in ("strategy", "equation"):
        if c in row and pd.notna(row[c]):
            return str(row[c])
    return None


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """One-check form of the same construction: cycle87c
    panel entries; drop a pick whose strategy is
    FB_NZDUSD_h17_0; if no entry remains, refill at this
    check from CandidateContext rows_at of apr_q09,
    apr_pvote, apr_pvsb, then apr_b9c (priority order) --
    the first row whose symbol is not open and which is
    not the vetoed strategy."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row)
    entries = _c87c.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    vetoed_strategy = None
    if entries is not None and len(entries):
        keep = []
        for i, r in entries.iterrows():
            if _entry_strategy(r) == VETO_STRATEGY:
                vetoed_strategy = VETO_STRATEGY
            else:
                keep.append(i)
        if vetoed_strategy is not None:
            entries = entries.loc[keep]
    if entries is not None and len(entries):
        return entries
    ctx = CandidateContext(frames, _cand_m15(m15_frames), DESIGNS)
    for name in DESIGNS:
        rows = ctx.rows_at(name, pd.Timestamp(check_time_utc))
        for eq_id, row in rows.items():
            if eq_id == vetoed_strategy:
                continue
            if row["symbol"] in tuple(open_symbols or ()):
                continue
            return pd.DataFrame([candidate_signal_row(row)])
    return entries if entries is not None else pd.DataFrame()
