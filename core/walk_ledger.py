"""Stateful walk ledger -- the app-side memory the BRIEF21 C20a
systems need (built 2026-10-26 on the user's order).

Why this exists: the BRIEF21 winners (Nov/Dec/Apr C20a) stack a
TP-continuation RE-ENTRY partner (research "C16") on a base walk.
A re-entry leg is defined on the base walk's CLOSED-TRADE ledger:
for each base trade that exited at TP, at the first grid check
strictly after its exit_time, re-enter the same symbol/direction
if a candidate row exists there and the leg's full flight
interval conflicts with no base/kept trade on the symbol. The
stateless per-check panels have no such input (see
FIX_NOTES_20261026_BRIEF21_INTEGRATION.md); this module is the
persisted pick ledger that carries it.

What it provides:
  * record_pick(...) -- append a pick (check, symbol, direction,
    equation/strategy, score, entry, TP, SL, kind) with its exit
    outcome. The outcome can be supplied by the caller (the era
    replay harness attaches the research pool row's recorded
    outcome -- the same ground truth the research walk itself
    consumed) or simulated from M15 bars with the research
    barrier rules (simulate_m15_exit: gap-through at the open,
    SL before TP inside a bar, TIME at the cap bar b0+191 close;
    exit_time = hour floor of the exit bar start; hold_h =
    ceil((exit_bar-b0+1)/4)).
  * Occupancy queries in the research walk's semantics:
    open_symbols_at(ent) (symbols with any recorded exit after
    ent), live_positions_at(ent), entry_free / interval_free on
    a symbol's [entry, exit) intervals.
  * reentry_legs(candidate_rows, grid_checks) -- the research
    build_reentry pass over the recorded BASE picks: TP exits
    in exit_time order; trigger check = first grid check
    strictly after exit_time; candidate row per (check, symbol)
    chosen by the month rule ('max_score' for November,
    'first' for December/April group order); direction must
    match (resolved side); entry must be free and the leg's
    full interval conflict-free vs base + already-kept legs.
    Kept legs are recorded with kind='reentry' and strategy
    'P16_reentry'.
  * JSON persistence under data/ so panel sessions accumulate
    the ledger across checks.

Live-use note (also in FIX_NOTES_20261026_BRIEF21_APP_
INTEGRATION.md): a re-entry leg's conflict test covers the
whole base ledger the ledger holds. A panel walking live
finalises legs from the picks recorded so far; the era replay
in the integration proof runs the same code over the complete
era ledger, which is the research construction verbatim.
"""

from __future__ import annotations

import json
import math
import os

import numpy as np
import pandas as pd

REENTRY_STRATEGY = "P16_reentry"
CAP_BARS = 191  # 48h of M15 bars: exit cap bar = entry bar + 191


def pip_size(symbol: str) -> float:
    """Research pip convention (c70_engine.pip_size)."""
    return 0.01 if "JPY" in str(symbol).upper() else 0.0001


def simulate_m15_exit(m15, symbol, entry_time, entry_px, direction,
                      tp_pips, sl_pips):
    """Barrier exit simulation on M15 bars, research-exact
    (p2lib.sim_trade with no hooks / barrier_sim_p semantics).

    m15: dict symbol -> dict of numpy arrays with keys
    'ts' (int64 ns), 'o', 'h', 'l', 'c'. Entry bar b0 = first
    bar starting at/after entry_time (the entry instant is a
    bar start in this system). Returns dict(exit_px, exit_time
    (hour floor of exit bar start), exit_reason, hold_h,
    gross_pips, exit_bar)."""
    A = m15[symbol]
    ts, o, h, l, c = A["ts"], A["o"], A["h"], A["l"], A["c"]
    d = 1 if str(direction).upper() == "BUY" else -1
    pip = pip_size(symbol)
    ent_ns = pd.Timestamp(entry_time).value
    b0 = int(np.searchsorted(ts, ent_ns))
    if b0 >= len(c):
        raise ValueError(f"no M15 bar at/after {entry_time} for {symbol}")
    tp_px = entry_px + d * float(tp_pips) * pip
    sl_px = entry_px - d * float(sl_pips) * pip
    last = min(b0 + CAP_BARS, len(c) - 1)
    j = b0
    res = None
    while j <= last:
        if d > 0:
            if o[j] <= sl_px:
                res = (float(d * (o[j] - entry_px) / pip), j,
                       float(o[j]), "SL")
                break
            if o[j] >= tp_px:
                res = (float(d * (tp_px - entry_px) / pip), j,
                       float(tp_px), "TP")
                break
            hsl, htp = l[j] <= sl_px, h[j] >= tp_px
        else:
            if o[j] >= sl_px:
                res = (float(d * (o[j] - entry_px) / pip), j,
                       float(o[j]), "SL")
                break
            if o[j] <= tp_px:
                res = (float(d * (tp_px - entry_px) / pip), j,
                       float(tp_px), "TP")
                break
            hsl, htp = h[j] >= sl_px, l[j] <= tp_px
        if hsl:
            res = (float(d * (sl_px - entry_px) / pip), j,
                   float(sl_px), "SL")
            break
        if htp:
            res = (float(d * (tp_px - entry_px) / pip), j,
                   float(tp_px), "TP")
            break
        if j == last:
            res = (float(d * (c[j] - entry_px) / pip), j,
                   float(c[j]), "TIME")
            break
        j += 1
    gross, jb, exit_px, reason = res
    exit_time = pd.Timestamp(ts[jb]).floor("h")
    hold_h = math.ceil((jb - b0 + 1) / 4)
    return dict(exit_px=float(exit_px), exit_time=exit_time,
                exit_reason=reason, hold_h=int(hold_h),
                gross_pips=float(gross), exit_bar=int(jb),
                entry_bar=int(b0))


def m15_arrays_from_frame(df: pd.DataFrame) -> dict:
    """Normalise an M15 DataFrame (Datetime index or column,
    Open/High/Low/Close[/Volume]) to the array dict used here
    and by the veto features."""
    f = df.copy()
    if "Datetime" in f.columns:
        f = f.set_index("Datetime")
    f.index = pd.to_datetime(f.index)
    if f.index.tz is not None:
        f.index = f.index.tz_convert("UTC").tz_localize(None)
    f = f.sort_index()
    out = {"ts": f.index.to_numpy().astype("datetime64[ns]")
           .astype(np.int64),
           "o": f["Open"].to_numpy(float),
           "h": f["High"].to_numpy(float),
           "l": f["Low"].to_numpy(float),
           "c": f["Close"].to_numpy(float)}
    if "Volume" in f.columns:
        out["v"] = f["Volume"].to_numpy(float)
    return out


VOLZ_MIN_BARS = 387  # causal M15 bars needed for the full
# 384-point rolling-sum window (see below)


def vol_z_at(m15_arrays, entry_time):
    """The C06 vol_z feature, exactly as generated for the
    research pools (work_c193/scripts/step1_generate.py
    feature_vector, F-VOL): causal slice = M15 bars strictly
    before the entry bar, last 1600 bars; rolling 4-bar volume
    sums over the last 384 start positions; vol_z = (last sum
    - median) / IQR of those sums.

    m15_arrays: array dict from m15_arrays_from_frame (must
    carry 'v'). Returns None when the causal slice has fewer
    than VOLZ_MIN_BARS bars or no volume (the statistic is not
    computable as defined); NaN when IQR <= 0 (the research
    value in that case -- comparisons against it are False,
    i.e. no veto, matching the research veto's NaN handling).
    """
    if "v" not in m15_arrays:
        return None
    ts = m15_arrays["ts"]
    v = m15_arrays["v"]
    ent_ns = pd.Timestamp(entry_time).value
    e = int(np.searchsorted(ts, ent_ns))  # first bar >= entry
    lo = max(0, e - 1600)
    vv = v[lo:e]
    n = len(vv)
    if n < VOLZ_MIN_BARS:
        return None
    cs = np.concatenate([[0.0], np.cumsum(vv)])
    idx = np.arange(max(3, n - 384), n)
    rolls = cs[idx + 1] - cs[idx - 3]
    med = np.median(rolls)
    iqr = np.percentile(rolls, 75) - np.percentile(rolls, 25)
    if iqr <= 0:
        return float("nan")
    return float((rolls[-1] - med) / iqr)


class WalkLedger:
    """Persisted pick ledger for one system's walk.

    Picks are dicts with the research ledger's fields: check,
    symbol, direction (resolved BUY/SELL), direction_stamp
    (the raw stamp when it differs, e.g. December/April FB
    'TREND'), strategy, score, entry_px, exit_px, tp_pips_used,
    sl_pips_used, gross_pips, net_pips (gross - cost),
    exit_reason, hold_h, exit_time, kind ('base' | 'dual' |
    'reentry'). entry_time is always check - 30min.
    """

    def __init__(self, system: str, cost: float = 2.5, path=None):
        self.system = str(system)
        self.cost = float(cost)
        self.path = path
        self.picks: list[dict] = []
        # (check, symbol, strategy) of TP exits whose re-entry
        # attempt has been consumed (live streaming path only).
        self.consumed: set = set()

    # ------------------------------------------------ record --
    def record_pick(self, check, symbol, direction, strategy,
                    score, entry_px, tp_pips, sl_pips,
                    kind="base", direction_stamp=None,
                    outcome=None, m15=None):
        """Append one pick. `outcome` (dict with exit_px,
        exit_time, exit_reason, hold_h, gross_pips) wins when
        given; else the exit is simulated from `m15` arrays;
        else the exit fields stay None (pending, live use --
        call update_exits when bars arrive)."""
        check = pd.Timestamp(check)
        ent = check - pd.Timedelta(minutes=30)
        row = dict(check=check, entry_time=ent,
                   symbol=str(symbol), direction=str(direction),
                   direction_stamp=(str(direction_stamp)
                                    if direction_stamp is not None
                                    else str(direction)),
                   strategy=str(strategy),
                   score=float(score) if score is not None
                   and pd.notna(score) else float("nan"),
                   entry_px=float(entry_px),
                   tp_pips_used=float(tp_pips),
                   sl_pips_used=float(sl_pips),
                   kind=str(kind),
                   exit_px=None, exit_time=None, exit_reason=None,
                   hold_h=None, gross_pips=None, net_pips=None)
        if outcome is not None:
            self._attach(row, outcome)
        elif m15 is not None:
            self._attach(row, simulate_m15_exit(
                m15, row["symbol"], ent, row["entry_px"],
                row["direction"], row["tp_pips_used"],
                row["sl_pips_used"]))
        self.picks.append(row)
        return row

    def _attach(self, row, outcome):
        row["exit_px"] = float(outcome["exit_px"])
        row["exit_time"] = pd.Timestamp(outcome["exit_time"])
        row["exit_reason"] = str(outcome["exit_reason"])
        row["hold_h"] = int(outcome["hold_h"])
        row["gross_pips"] = float(outcome["gross_pips"])
        row["net_pips"] = row["gross_pips"] - self.cost

    def update_exits(self, m15):
        """Simulate exits for pending picks (live use)."""
        for row in self.picks:
            if row["exit_time"] is None and row["symbol"] in m15:
                try:
                    self._attach(row, simulate_m15_exit(
                        m15, row["symbol"], row["entry_time"],
                        row["entry_px"], row["direction"],
                        row["tp_pips_used"], row["sl_pips_used"]))
                except Exception:
                    pass
        return self

    def has_pick(self, check, symbol, kind=None) -> bool:
        check = pd.Timestamp(check)
        for r in self.picks:
            if r["check"] == check and r["symbol"] == str(symbol) \
                    and (kind is None or r["kind"] == kind):
                return True
        return False

    @staticmethod
    def due_grid_check(exit_time, grid_hours):
        """First grid check (hour in grid_hours, minute 30)
        strictly after exit_time."""
        t = pd.Timestamp(exit_time).floor("h") + pd.Timedelta(minutes=30)
        if t <= pd.Timestamp(exit_time):
            t += pd.Timedelta(hours=1)
        while t.hour not in grid_hours:
            t += pd.Timedelta(hours=1)
        return t

    def due_reentry_legs(self, check, candidate_rows, grid_hours,
                         rule="first", m15=None):
        """Streaming C16 re-entry for the live panel path.

        For every recorded TP exit (base/dual) whose first grid
        check after its exit_time is exactly `check`, attempt the
        leg from `candidate_rows` at this check (same candidate
        rule and full-interval occupancy as the batch
        reentry_legs). A trigger whose due check has already
        passed unevaluated is consumed without a leg -- the
        research walk gets exactly one attempt per trigger, at
        its due check. A trigger whose candidate exists but
        whose exit cannot be simulated (no M15 for the symbol)
        is NOT consumed; the next evaluated check retries it.
        Returns the recorded leg rows."""
        check = pd.Timestamp(check)
        by_sym = {}
        for r in candidate_rows or []:
            by_sym.setdefault(str(r["symbol"]), []).append(r)
        legs = []
        for t in self.tp_exits():
            key = (t["check"], t["symbol"], t["strategy"])
            if key in self.consumed:
                continue
            due = self.due_grid_check(t["exit_time"], grid_hours)
            if due > check:
                continue
            if due < check:
                self.consumed.add(key)
                continue
            cands = by_sym.get(t["symbol"]) or []
            if not cands:
                self.consumed.add(key)
                continue
            if rule == "max_score":
                cand = max(cands, key=lambda r: float(r["score"]))
            else:
                cand = cands[0]
            ent = check - pd.Timedelta(minutes=30)
            outcome = None
            if m15 is not None and t["symbol"] in m15:
                try:
                    outcome = simulate_m15_exit(
                        m15, t["symbol"], ent,
                        float(cand["entry_px"]),
                        str(cand["direction"]),
                        float(cand["tp_pips"]), float(cand["sl_pips"]))
                except Exception:
                    outcome = None
            if outcome is None:
                continue  # retry at the next evaluated check
            if not self.entry_free(t["symbol"], ent) \
                    or not self.interval_free(
                        t["symbol"], ent,
                        pd.Timestamp(outcome["exit_time"])):
                self.consumed.add(key)
                continue
            leg = self.record_pick(
                check, t["symbol"], cand["direction"],
                REENTRY_STRATEGY, cand.get("score"),
                cand["entry_px"], cand["tp_pips"], cand["sl_pips"],
                kind="reentry",
                direction_stamp=cand.get("direction_stamp"),
                outcome=outcome)
            self.consumed.add(key)
            legs.append(leg)
        return legs

    # ------------------------------------------------ queries --
    def _closed(self):
        return [r for r in self.picks if r["exit_time"] is not None]

    def open_symbols_at(self, ent_t) -> tuple:
        """Symbols with any recorded exit strictly after ent_t
        (the walk occupancy predicate: a symbol is free iff ALL
        its recorded exits are <= ent_t)."""
        ent_t = pd.Timestamp(ent_t)
        syms = {r["symbol"] for r in self._closed()
                if r["exit_time"] > ent_t}
        return tuple(sorted(syms))

    def live_positions_at(self, ent_t) -> list:
        """Recorded picks (entry <= ent_t) still open at ent_t:
        exit_time > ent_t. (All picks in an in-order walk have
        entry <= the current ent_t.)"""
        ent_t = pd.Timestamp(ent_t)
        return [r for r in self._closed()
                if r["entry_time"] <= ent_t and r["exit_time"] > ent_t]

    def symbol_intervals(self, symbol, kinds=None):
        out = []
        for r in self._closed():
            if r["symbol"] != symbol:
                continue
            if kinds is not None and r["kind"] not in kinds:
                continue
            out.append((r["entry_time"], r["exit_time"]))
        return out

    def entry_free(self, symbol, ent_t) -> bool:
        """Research free_at: no interval with a <= ent < b."""
        ent_t = pd.Timestamp(ent_t)
        return all(not (a <= ent_t < b)
                   for a, b in self.symbol_intervals(symbol))

    def interval_free(self, symbol, ent_t, exit_t) -> bool:
        """Research interval_free: the whole flight [ent, ex)
        intersects no recorded interval on the symbol."""
        ent_t, exit_t = pd.Timestamp(ent_t), pd.Timestamp(exit_t)
        return all(exit_t <= a or ent_t >= b
                   for a, b in self.symbol_intervals(symbol))

    def tp_exits(self, kinds=("base", "dual")):
        """Closed picks with exit_reason == 'TP', in exit_time
        order (stable), restricted to the given kinds (the
        research build_reentry runs on the BASE log, which for
        April includes its dual picks -- both are 'base log'
        rows there; kinds default covers both)."""
        rows = [r for r in self._closed()
                if r["exit_reason"] == "TP" and r["kind"] in kinds]
        return sorted(rows, key=lambda r: r["exit_time"])

    # ------------------------------------------------ re-entry --
    def reentry_legs(self, candidate_rows, grid_checks,
                     rule="first"):
        """The research build_reentry pass, on this ledger's
        recorded base picks.

        candidate_rows: iterable of dicts, the era candidate
        rows (pool rows in live use = evaluated signal rows),
        each with check, symbol, direction (resolved),
        direction_stamp, strategy, score, entry_px, exit_px,
        tp_pips_used, sl_pips_used, gross_pips, exit_reason,
        hold_h, exit_time. They are indexed per (check, symbol):
        rule='max_score' keeps the highest-score row (November:
        max eq score across eff tabs, first max wins ties);
        rule='first' keeps the first row in the given order
        (December: first gate-ok row in group order; April:
        first row in group order).
        grid_checks: sorted iterable of the system's grid check
        stamps; the trigger check is the first one STRICTLY
        after the base trade's exit_time.

        Kept legs are recorded into the ledger (kind='reentry',
        strategy='P16_reentry') and returned as a DataFrame.
        Occupancy starts from ALL recorded base/dual intervals
        (the completed base log, as in research) plus kept legs.
        """
        checks = [pd.Timestamp(c) for c in grid_checks]
        by_key: dict = {}
        for r in candidate_rows:
            k = (pd.Timestamp(r["check"]), str(r["symbol"]))
            if rule == "max_score":
                cur = by_key.get(k)
                if cur is None or float(r["score"]) > float(cur["score"]):
                    by_key[k] = r
            else:
                if k not in by_key:
                    by_key[k] = r
        occ: dict = {}
        for r in self._closed():
            if r["kind"] in ("base", "dual"):
                occ.setdefault(r["symbol"], []).append(
                    (r["entry_time"], r["exit_time"]))

        def free_at(sym, ent):
            return all(not (a <= ent < b) for a, b in occ.get(sym, []))

        def interval_free(sym, ent, ex):
            return all(ex <= a or ent >= b for a, b in occ.get(sym, []))

        kept = []
        for r in self.tp_exits():
            nxt = None
            for c in checks:
                if c > r["exit_time"]:
                    nxt = c
                    break
            if nxt is None:
                continue
            ent2 = nxt - pd.Timedelta(minutes=30)
            sym = r["symbol"]
            if not free_at(sym, ent2):
                continue
            row = by_key.get((nxt, sym))
            if row is None:
                continue
            if str(row["direction"]) != r["direction"]:
                continue
            if not interval_free(sym, ent2,
                                 pd.Timestamp(row["exit_time"])):
                continue
            leg = self.record_pick(
                nxt, sym, row["direction"], REENTRY_STRATEGY,
                row.get("score"), row["entry_px"],
                row["tp_pips_used"], row["sl_pips_used"],
                kind="reentry",
                direction_stamp=row.get("direction_stamp",
                                        row["direction"]),
                outcome=dict(exit_px=row["exit_px"],
                             exit_time=row["exit_time"],
                             exit_reason=row["exit_reason"],
                             hold_h=row["hold_h"],
                             gross_pips=row["gross_pips"]))
            kept.append(leg)
            occ.setdefault(sym, []).append(
                (ent2, pd.Timestamp(row["exit_time"])))
        return self.frame(kept)

    # ------------------------------------------------ frames --
    def frame(self, rows=None) -> pd.DataFrame:
        """Ledger rows as a DataFrame in the research ledger's
        column order, sorted by (check, exit_time) -- the
        research combine() order."""
        rows = self.picks if rows is None else rows
        cols = ["check", "symbol", "direction", "strategy",
                "score", "entry_px", "exit_px", "tp_pips_used",
                "sl_pips_used", "gross_pips", "net_pips",
                "exit_reason", "hold_h", "exit_time", "kind",
                "direction_stamp", "entry_time"]
        if not rows:
            return pd.DataFrame(columns=cols)
        df = pd.DataFrame(rows)[cols]
        df["check"] = pd.to_datetime(df["check"])
        df["exit_time"] = pd.to_datetime(df["exit_time"])
        return df.sort_values(["check", "exit_time"],
                              kind="stable").reset_index(drop=True)

    def base_frame(self) -> pd.DataFrame:
        return self.frame([r for r in self.picks
                           if r["kind"] in ("base", "dual")])

    # ------------------------------------------------ persist --
    def save(self, path=None):
        p = path or self.path
        if not p:
            return None
        os.makedirs(os.path.dirname(os.path.abspath(p)),
                    exist_ok=True)
        rows = []
        for r in self.picks:
            d = dict(r)
            for k in ("check", "entry_time", "exit_time"):
                d[k] = (None if r[k] is None
                        else pd.Timestamp(r[k]).isoformat())
            rows.append(d)
        with open(p, "w") as fh:
            json.dump(dict(system=self.system, cost=self.cost,
                           picks=rows,
                           consumed=[[pd.Timestamp(c).isoformat(), s, st]
                                     for c, s, st in
                                     sorted(self.consumed)]), fh)
        return p

    @classmethod
    def load(cls, path, system=None):
        with open(path) as fh:
            d = json.load(fh)
        led = cls(system or d["system"], cost=d.get("cost", 2.5),
                  path=path)
        for r in d["picks"]:
            for k in ("check", "entry_time", "exit_time"):
                r[k] = (None if r[k] is None
                        else pd.Timestamp(r[k]))
            led.picks.append(r)
        for c, s, st in d.get("consumed", []):
            led.consumed.add((pd.Timestamp(c), s, st))
        return led


def settle_panel_check(system, check, entries, candidate_rows,
                       grid_hours, rule, m15_frames, path=None):
    """Panel-path ledger settle for one check (live use).

    Loads the system's persisted walk ledger, records the base
    entries (idempotent per check+symbol+kind), simulates exits
    of recorded picks from `m15_frames` (DataFrames), settles
    re-entry legs due at this check, saves the ledger, and
    returns the leg signal rows produced at this check (a list
    of signal-row dicts, possibly empty). Legs finalize from
    recorded picks so far: a leg can only appear once its
    trigger trade's exit has been simulated from arrived bars.
    """
    path = path or default_ledger_path(system)
    try:
        led = WalkLedger.load(path)
    except Exception:
        led = WalkLedger(system, path=path)
    m15 = {}
    for s, f in (m15_frames or {}).items():
        if f is not None and len(f):
            try:
                m15[s] = m15_arrays_from_frame(f)
            except Exception:
                pass
    check = pd.Timestamp(check)
    if entries is not None and len(entries):
        for i, r in enumerate(entries.to_dict("records")):
            kind = "base" if i == 0 else "dual"
            if not led.has_pick(check, r["symbol"], kind=kind):
                led.record_pick(
                    check, r["symbol"], r["direction"],
                    r.get("equation", r.get("strategy")),
                    r.get("score"), r["entry_px"], r["tp_pips"],
                    r["sl_pips"], kind=kind,
                    direction_stamp=r.get("direction_stamp"))
    led.update_exits(m15)
    cand = []
    if candidate_rows is not None and len(candidate_rows):
        for r in candidate_rows.to_dict("records"):
            cand.append(dict(
                symbol=r["symbol"], direction=r["direction"],
                score=r.get("score"), entry_px=r["entry_px"],
                tp_pips=r["tp_pips"], sl_pips=r["sl_pips"],
                direction_stamp=r.get("direction_stamp")))
    legs = led.due_reentry_legs(check, cand, grid_hours,
                                rule=rule, m15=m15)
    led.save()
    return [dict(check=check, symbol=l["symbol"],
                 direction=l["direction"],
                 equation=REENTRY_STRATEGY,
                 strategy=REENTRY_STRATEGY, score=l["score"],
                 entry_px=l["entry_px"],
                 tp_pips=l["tp_pips_used"],
                 sl_pips=l["sl_pips_used"]) for l in legs]


def default_ledger_path(system: str) -> str:
    """data/walk_ledgers/<system>.json inside the app tree."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "data", "walk_ledgers",
                        f"{system}.json")
