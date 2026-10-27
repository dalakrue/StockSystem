"""Cycle 87B (BRIEF21 C20a) -- April IMPROVED system,
integrated 2026-10-26 on the user's order to build the stateful
walk layer (core/walk_ledger.py). PROMOTED 2026-10-26: the
app replay is EXACT against the validated C20a ledger (see
FIX_NOTES_20261026_BRIEF21_APP_INTEGRATION.md); this system is
April's BEST (MONTH_SYSTEMS[4]) and the old C87-24 is April's
second priority in the combined layer.

Definition (BRIEF21 April, validated HUGE 2026-10-26):
C87-24 (core.cycle87_best, frozen) + two layers:

  C12 score-gated dual-pick: a second pick at the same check,
  taken from the walk's remaining candidates (rem) in WALK
  ORDER -- the first rem row whose eq score >= MED_SCORE
  (1000.3404785714285, the median of the discovery pool's
  positive scores) -- blocked when 3 or more positions are
  live after the primary pick (len(live_after) >= 3).
  rem = the reranked occupancy-eligible candidates minus the
  primary minus the symbols live after the primary. A primary
  whose own flight ends at its entry instant (exit_time ==
  entry time, e.g. a TP inside the entry bar, hour-floored)
  is NOT live after, so it does not block its own symbol: the
  dual can be a second variant of the primary's symbol. This
  outcome-aware rule is the research apr_walk + sf_score
  semantics exactly (cyc_lib.apr_walk / run21_apr.sf_score).

  C16 TP-continuation re-entry partner, driven by the walk
  ledger (core/walk_ledger.py), rule 'first'.

Candidate order (research-exact): the pool group order is
(eff desc, stable over pool row order); eff == eq score for
every candidate, and the app engine emits tied candidates in
the same order as the pool, so a stable score-descending sort
of the evaluate output reproduces the group order; the M18
rerank (top-3 passers moved to the front, order preserved)
is then applied exactly as in core.cycle87_best's selection.

Validated numbers (C20a, @2.5): DISC n710 net +6033.02
leftover 84.47; AUDIT n187 net +1971.36 leftover 79.06.
"""

from __future__ import annotations

import pandas as pd

from core.cycle87_best import (
    CYCLE87_CHECK_HOURS,
    evaluate_cycle87_signals,
    fetch_cycle87_m15_frames,
    is_cycle87_check_time,
)

MED_SCORE = 1000.3404785714285
DUAL_CAP = 3
CYCLE87B_CHECK_HOURS = CYCLE87_CHECK_HOURS
GRID_HOURS = CYCLE87_CHECK_HOURS

SYSTEM_NAME = "cycle87b"
REENTRY_RULE = "first"


def evaluate_cycle87b_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """C87-24 candidate signals (post-ban, m18_pass flags) --
    the frozen incumbent evaluation, unchanged."""
    return evaluate_cycle87_signals(frames, check_time_utc,
                                    m15_frames=m15_frames)


def ranked_candidates(signals: pd.DataFrame,
                      open_symbols=()) -> pd.DataFrame:
    """The walk's eligible candidate list, in walk order:
    stable score-descending order (== research pool group
    order), M18 rerank applied (top-3 passers to the front,
    order preserved), then the occupancy filter (a candidate
    whose symbol is open is ineligible)."""
    if signals is None or len(signals) == 0:
        return (signals.iloc[0:0] if signals is not None
                else pd.DataFrame())
    held = {str(s).upper() for s in (open_symbols or ())}
    ordered = signals.sort_values("score", ascending=False,
                                  kind="mergesort").reset_index(
                                      drop=True)
    n = len(ordered)
    passers = [k for k in range(min(3, n))
               if bool(ordered.iloc[k].get("m18_pass", False))]
    if passers:
        pset = set(passers)
        order = passers + [k for k in range(n) if k not in pset]
    else:
        order = list(range(n))
    rows = [ordered.iloc[k] for k in order
            if str(ordered.iloc[k]["symbol"]).upper() not in held]
    if not rows:
        return ordered.iloc[0:0]
    return pd.DataFrame(rows).reset_index(drop=True)


def select_cycle87b_entries(
        signals: pd.DataFrame, open_symbols=(),
        live_after: int | None = None,
        primary_live: bool = True) -> pd.DataFrame:
    """C20a selection: the primary pick (walk elig[0]) plus
    the C12 dual pick when the gate passes.

    live_after = number of positions live after the primary
    pick is appended (its research definition: recorded picks
    with exit_time > the check's entry time, the primary
    included iff its own exit is after the entry time). When
    live_after is None (a plain live call, where the primary
    has by definition just been entered and is live), it
    defaults to len(open symbols) + 1 and primary_live=True.
    The replay harness passes the exact values from the walk
    ledger / pool outcomes.
    """
    elig = ranked_candidates(signals, open_symbols=open_symbols)
    if len(elig) == 0:
        return elig
    primary = elig.iloc[0]
    if live_after is None:
        live_after = len({str(s).upper()
                          for s in (open_symbols or ())}) + 1
        primary_live = True
    if live_after >= DUAL_CAP:
        return pd.DataFrame([primary]).reset_index(drop=True)
    rem = elig.iloc[1:]
    if primary_live:
        rem = rem[rem["symbol"].astype(str).str.upper()
                  != str(primary["symbol"]).upper()]
    for _, row in rem.iterrows():
        if float(row["score"]) >= MED_SCORE:
            return pd.DataFrame([primary, row]).reset_index(
                drop=True)
    return pd.DataFrame([primary]).reset_index(drop=True)


def candidate_rows_at(signals: pd.DataFrame) -> pd.DataFrame:
    """Re-entry candidate rows for a check: the first row per
    symbol in walk order (reranked, BEFORE the occupancy
    filter) -- the app counterpart of the research pool group
    row the build_reentry pass reads (rule 'first')."""
    if signals is None or len(signals) == 0:
        return (signals.iloc[0:0] if signals is not None
                else pd.DataFrame())
    ordered = signals.sort_values("score", ascending=False,
                                  kind="mergesort").reset_index(
                                      drop=True)
    n = len(ordered)
    passers = [k for k in range(min(3, n))
               if bool(ordered.iloc[k].get("m18_pass", False))]
    if passers:
        pset = set(passers)
        order = passers + [k for k in range(n) if k not in pset]
    else:
        order = list(range(n))
    seen = set()
    rows = []
    for k in order:
        r = ordered.iloc[k]
        s = str(r["symbol"]).upper()
        if s in seen:
            continue
        seen.add(s)
        rows.append(r)
    if not rows:
        return ordered.iloc[0:0]
    return pd.DataFrame(rows).reset_index(drop=True)


def is_cycle87b_check_time(ts) -> bool:
    return is_cycle87_check_time(ts)


def fetch_cycle87b_m15_frames(state=None):
    """Live M15 frames for the M18 rerank: the incumbent's
    fetch (shared cycle78 data path underneath)."""
    return fetch_cycle87_m15_frames(state=state)


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full C20a entries for one check (live panel path): the
    primary pick + the C12 dual pick + any C16 re-entry leg
    due at this check, settled through the persisted walk
    ledger (core.walk_ledger.settle_panel_check).

    The dual gate is outcome-aware: the primary's exit is
    simulated from the M15 frames first (walk-ledger
    simulation), and live_after / the primary's own-symbol
    block follow the research rule exactly.
    """
    from core.walk_ledger import (WalkLedger, default_ledger_path,
                                  m15_arrays_from_frame,
                                  settle_panel_check,
                                  simulate_m15_exit)
    if m15_frames is None:
        m15_frames = fetch_cycle87b_m15_frames()
    sig = evaluate_cycle87b_signals(frames, check_time_utc,
                                    m15_frames=m15_frames)
    if sig is None:
        return pd.DataFrame()
    check = pd.Timestamp(check_time_utc)
    ent_t = check - pd.Timedelta(minutes=30)
    path = default_ledger_path(SYSTEM_NAME)
    try:
        led = WalkLedger.load(path)
    except Exception:
        led = WalkLedger(SYSTEM_NAME, path=path)
    open_syms = tuple(set(led.open_symbols_at(ent_t))
                      | {str(s).upper() for s in (open_symbols
                                                  or ())})
    elig = ranked_candidates(sig, open_symbols=open_syms)
    entries = elig.iloc[0:0]
    if len(elig):
        primary = elig.iloc[0]
        # Simulate the primary's exit from the M15 frames to
        # apply the outcome-aware dual gate.
        prim_live = True
        live_after = len(led.live_positions_at(ent_t)) + 1
        try:
            m15a = {}
            for s, f in (m15_frames or {}).items():
                if f is not None and len(f):
                    m15a[s] = m15_arrays_from_frame(f)
            sym = str(primary["symbol"])
            if sym in m15a:
                arr = {sym: m15a[sym]}
                res = simulate_m15_exit(
                    arr, sym, ent_t, float(primary["entry_px"]),
                    str(primary["direction"]),
                    float(primary["tp_pips"]),
                    float(primary["sl_pips"]))
                if res is not None:
                    prim_live = bool(
                        pd.Timestamp(res["exit_time"]) > ent_t)
                    live_after = (len(led.live_positions_at(
                        ent_t)) + (1 if prim_live else 0))
        except Exception:
            pass
        entries = select_cycle87b_entries(
            sig, open_symbols=open_syms, live_after=live_after,
            primary_live=prim_live)
    cands = candidate_rows_at(sig)
    legs = settle_panel_check(SYSTEM_NAME, check, entries,
                              cands, GRID_HOURS, REENTRY_RULE,
                              m15_frames, path=path)
    if legs:
        extra = pd.DataFrame(legs)
        entries = (pd.concat([entries, extra], ignore_index=True)
                   if len(entries) else extra)
    return entries
