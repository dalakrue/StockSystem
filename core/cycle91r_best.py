"""Cycle 91R -- September B-13 OfficeAlt in true code form.

Construction (graded in work_r5_20cyc/results/
sep_b13_officealt_VALIDATION.md): the shipped cycle91q
combined stream with the office-hour check REMOVED
(entry hour 10 UTC = 16:30 MMT) and the replacement
slot 18 UTC (00:30 MMT) mined by design sep_b13o02
(B13O candidate1 / C02, 30 equations, hours (11, 18),
veto none), composed by validate_new8.build_combined
verbatim: a candidate pick is delivered only at a
check where the base is silent and with no same-symbol
interval overlap against the base or an accepted pick.

The candidate's era walk is exact in the app tree
(204/204 rows including scores, after the 2026-11-01
score fix). Check hours (1, 2, 11, 18) UTC =
07:30 / 08:30 / 17:30 / 00:30 MMT -- the month's
16:30 MMT slot is replaced by 00:30 MMT. The
second-best stays cycle91s (the base stream is the
91q form, which already contains the 91s layer as
shipped).

Panel-form note: base spans are tracked with the
programme's 48h hold convention (the panel signal
rows carry no simulated exit); the ledger form uses
real exits. The candidate leg's picks condition on
volume-derived columns and are expected to stay
silent in live Twelve panels (B-13 port-lane
finding); the 91q base leg is unaffected.
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

import core.cycle91q_best as _c91q
from core.new8_candidate import CandidateContext, ensure_m15
from core.new8_designs import DESIGNS
from core.new8_walk import DesignWalk

SYSTEM_NAME = "cycle91r"
CYCLE91R_CHECK_HOURS = (1, 2, 11, 18)
BASE_HOURS = (1, 2, 11)
CAND_DESIGN = "sep_b13o02"
OFFICE_ENTRY_HOUR = 10
_DESIGN_SYMBOLS = tuple(sorted(
    {e["symbol"] for e in DESIGNS[CAND_DESIGN]["equations"]}))


def _default_state_path():
    from core.new8_walk import default_state_path
    return default_state_path(SYSTEM_NAME)


# ------------------------------------------------- ledger form --
def build_officealt(inc, cand):
    """validate_new8.build_combined verbatim over the
    incumbent stream minus its office-hour rows."""
    inc = inc.copy()
    for c in ("check", "entry_time", "exit_time"):
        inc[c] = pd.to_datetime(inc[c])
    eh = (inc["check"] - pd.Timedelta(minutes=30)).dt.hour
    base = inc[eh != OFFICE_ENTRY_HOUR].reset_index(drop=True)
    cand = cand.copy()
    for c in ("check", "entry_time", "exit_time"):
        if c in cand.columns:
            cand[c] = pd.to_datetime(cand[c])
    if "entry_time" not in cand.columns:
        cand["entry_time"] = cand["check"] - pd.Timedelta(minutes=30)
    inc_checks = set(base["check"])
    inc_by_sym = {s: g[["entry_time", "exit_time"]].values
                  for s, g in base.groupby("symbol")}
    acc_by_sym = {}
    drops = dict(check_busy=0, symbol_overlap=0)

    def overlaps(arr, e, x):
        if arr is None or len(arr) == 0:
            return False
        return bool(((arr[:, 0] < x) & (e < arr[:, 1])).any())

    acc_rows = []
    for _, r in cand.sort_values("check").iterrows():
        e, x, sym = r["entry_time"], r["exit_time"], r["symbol"]
        if r["check"] in inc_checks:
            drops["check_busy"] += 1
            continue
        if overlaps(inc_by_sym.get(sym), e, x):
            drops["symbol_overlap"] += 1
            continue
        arr = acc_by_sym.get(sym)
        if arr is not None and overlaps(np.array(arr), e, x):
            drops["symbol_overlap"] += 1
            continue
        acc_rows.append(r)
        acc_by_sym.setdefault(sym, []).append((e, x))
    keep = [c for c in ("check", "symbol", "direction",
                        "strategy", "entry_time", "exit_time",
                        "exit_reason", "entry_px", "exit_px",
                        "tp_pips_used", "sl_pips_used",
                        "gross_pips", "src") if c in base.columns
            or c in cand.columns]
    base_k = base.copy()
    base_k["src"] = "incumbent"
    parts = [base_k[[c for c in keep if c in base_k.columns]]]
    if acc_rows:
        acc = pd.DataFrame(acc_rows)
        acc["src"] = "cand1"
        parts.append(acc[[c for c in keep if c in acc.columns]])
    comb = pd.concat(parts).sort_values("check") \
        .reset_index(drop=True)
    return comb, drops, len(acc_rows)


# --------------------------------------------- streaming form --
class SepOfficeAltState:
    """One DesignWalk for sep_b13o02 + build_combined
    bookkeeping over the delivered 91q base rows.

    Persisted: the candidate walk, the base check set,
    the delivered spans, the kept rows and the accepted
    candidate fills. step() takes the base ledger rows
    for the check (empty at 18 UTC) and returns the
    delivered rows for the check."""

    def __init__(self, path=None):
        self.path = path or _default_state_path()
        d = DESIGNS[CAND_DESIGN]
        self.walk = DesignWalk(d["equations"], veto=d.get("veto"))
        self.base_checks = []
        self.spans = []        # (entry, exit, symbol) delivered
        self.kept = []
        self.fills = []
        self.processed = []
        self._load()

    # ------------------------------------------------ persist --
    @staticmethod
    def _de(rows):
        out = []
        for r in rows:
            r = dict(r)
            for k in ("check", "entry_time", "exit_time"):
                if r.get(k) is not None:
                    r[k] = pd.Timestamp(r[k])
            out.append(r)
        return out

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

    def _load(self):
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path) as fh:
                d = json.load(fh)
        except Exception:
            return
        self.kept = self._de(d.get("kept", []))
        self.fills = self._de(d.get("fills", []))
        self.processed = list(d.get("processed", []))
        self.base_checks = [str(x) for x in d.get("base_checks", [])]
        self.spans = [(pd.Timestamp(a), pd.Timestamp(b), s)
                      for a, b, s in d.get("spans", [])]
        wd = d.get("walk") or {}
        self.walk.picks = self._de(wd.get("picks", []))
        self.walk.open_exit = {
            s: [pd.Timestamp(x) for x in xs]
            for s, xs in (wd.get("open_exit") or {}).items()}

    def save(self):
        if not self.path:
            return None
        os.makedirs(os.path.dirname(
            os.path.abspath(self.path)), exist_ok=True)
        data = {"system": SYSTEM_NAME,
                "kept": self._ser(self.kept),
                "fills": self._ser(self.fills),
                "processed": self.processed,
                "base_checks": self.base_checks,
                "spans": [[a.isoformat(), b.isoformat(), s]
                          for a, b, s in self.spans],
                "walk": {"picks": self._ser(self.walk.picks),
                         "open_exit": {
                             s: [pd.Timestamp(x).isoformat()
                                 for x in xs]
                             for s, xs in self.walk.open_exit.items()}}}
        with open(self.path, "w") as fh:
            json.dump(data, fh)
        return self.path

    # ---------------------------------------------------- step --
    def step(self, ctx, check, base_rows):
        chk = pd.Timestamp(check)
        pick = self.walk.step(chk, ctx.rows_at(CAND_DESIGN, chk)) \
            if ctx is not None else None
        out = []
        if base_rows:
            self.base_checks.append(str(chk))
            for r in base_rows:
                self.spans.append((pd.Timestamp(r["entry_time"]),
                                   pd.Timestamp(r["exit_time"]),
                                   r["symbol"]))
                self.kept.append(r)
                out.append(r)
        if pick is not None:
            e = pd.Timestamp(pick["entry_time"])
            x = pd.Timestamp(pick["exit_time"])
            busy = str(chk) in self.base_checks
            ov = any(s == pick["symbol"] and a < x and e < b
                     for (a, b, s) in self.spans)
            if not busy and not ov:
                fill = dict(pick)
                self.fills.append(fill)
                self.kept.append(fill)
                self.spans.append((e, x, pick["symbol"]))
                out.append(fill)
        self.processed.append(str(chk))
        return out


def load_officealt_state(path=None):
    p = path or _default_state_path()
    try:
        return SepOfficeAltState(path=p)
    except Exception:
        return SepOfficeAltState(path=p)


def is_cycle91r_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE91R_CHECK_HOURS and t.minute == 30


# ------------------------------------------------- panel form --
def _signal_row(r):
    return {"check": pd.Timestamp(r["check"]),
            "symbol": r["symbol"],
            "equation": r["strategy"],
            "direction": r["direction"],
            "score": float("nan"),
            "entry_px": float(r["entry_px"]),
            "tp_pips": float(r["tp_pips_used"]),
            "sl_pips": float(r["sl_pips_used"]),
            "signal_candle": pd.Timestamp(r["check"])
            - pd.Timedelta(hours=1, minutes=30),
            "entry_candle": pd.Timestamp(r["entry_time"])}


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full OfficeAlt entries for one check: the cycle91q
    base entries (at 01/02/11 UTC only -- the office-hour
    slot is gone) plus the sep_b13o02 candidate pick when
    the base is silent and it overlaps nothing delivered."""
    chk = pd.Timestamp(check_time_utc)
    base_entries = pd.DataFrame()
    if chk.hour in BASE_HOURS:
        base_entries = _c91q.panel_entries(
            frames, check_time_utc, m15_frames=m15_frames,
            open_symbols=open_symbols)
        if base_entries is not None and \
                base_entries.attrs.get("status"):
            return base_entries
    m15map = ensure_m15(m15_frames, _DESIGN_SYMBOLS)
    ctx = CandidateContext(frames, m15map, (CAND_DESIGN,))
    base_rows = []
    if base_entries is not None and len(base_entries):
        for _, r in base_entries.iterrows():
            ent = pd.Timestamp(r.get("entry_candle", chk)
                               ) if pd.notna(r.get("entry_candle")) \
                else chk - pd.Timedelta(minutes=30)
            base_rows.append({
                "check": chk, "symbol": r["symbol"],
                "direction": r["direction"],
                "strategy": r.get("equation"),
                "entry_time": ent,
                "exit_time": ent + pd.Timedelta(hours=48)})
    state = load_officealt_state()
    state.step(ctx, chk, base_rows)
    state.save()
    rows = []
    if base_entries is not None and len(base_entries):
        rows.extend([dict(r) for _, r in base_entries.iterrows()])
    if state.fills and pd.Timestamp(
            state.fills[-1]["check"]) == chk:
        rows.append(_signal_row(state.fills[-1]))
    return pd.DataFrame(rows)


# ------------------------------------------------- coordinator --
def fetch_cycle91r_m15_frames(state=None):
    from core.cycle91_best import fetch_cycle91_m15_frames
    return fetch_cycle91_m15_frames()


def evaluate_cycle91r_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    """Final OfficeAlt entries for the check, as the
    signals frame (panel_entries applies the full form)."""
    return panel_entries(frames, check_time_utc,
                         m15_frames=m15_frames)


def select_cycle91r_entries(signals: pd.DataFrame,
                            open_symbols=()):
    """Open-symbol filter over the evaluated entries."""
    if signals is None or len(signals) == 0:
        return signals
    if signals.attrs.get("status"):
        return signals
    open_set = {str(s).upper() for s in (open_symbols or ())}
    if not open_set or "symbol" not in signals.columns:
        return signals
    return signals[~signals["symbol"].astype(str)
                   .str.upper().isin(open_set)]
