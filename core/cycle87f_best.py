"""Cycle 87F -- April Plan E winner E04 in true code form.

Construction (planE_slate apr bind, graded in
work_r5_20cyc/results/apr_planE_FINAL_VALIDATION.md):
the shipped 87e<-87s COMBINED stream ->
  PCOL concurrency cap (<= 1 open in the {EURCHF, USDCHF}
  group and <= 1 in the {CADJPY, USDJPY} group, per
  direction) ->
  CONS3 consensus fills: pool rows whose (check, symbol,
  direction) key appears in >= 3 independent pool families
  enter through the research cascade (one fill per check,
  at the incumbent best hours 16/17/18 UTC only).

The 43 pool designs live in core.new8_designs (37 ported
for this install + 6 pre-existing designs reused by
reference: apr_b12c_c08, apr_b12c_c19, apr_b7_c04,
apr_b8_c07, apr_b9c, apr_b9c_c03); features by
core.new8_features. Everything is computed from market
data at runtime -- no research artefacts are read.

Because the form's base IS the combined stream, this
module composes the second-best (cycle87s, design
apr_pvsb) internally: April's second-best slot is empty
while 87f is the best (the cycle93t precedent). Check
hours (16, 17, 18, 19) UTC = 22:30 / 23:30 / 00:30 /
01:30 MMT -- the month's combined grid is unchanged.
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from core.new8_candidate import CandidateContext, ensure_m15
from core.new8_designs import DESIGNS
from core.new8_walk import DesignWalk
import core.cycle87e_best as _c87e
import core.cycle87s_best as _c87s

SYSTEM_NAME = "cycle87f"
CYCLE87F_CHECK_HOURS = (16, 17, 18, 19)
FILL_HOURS = (16, 17, 18)
MIN_AGREE = 3
PCOL_CAP = 1
PCOL_COR = {"EURCHF": "EURCHF+USDCHF",
            "USDCHF": "EURCHF+USDCHF",
            "CADJPY": "CADJPY+USDJPY",
            "USDJPY": "CADJPY+USDJPY"}

# family -> pool designs (app names), in the research
# assembly's family order (planE_slate pool files for Apr;
# cascade representative order depends on it).
POOL_FAMILIES = {
    "B13A": ["apr_b13a_cand1", "apr_b13a_cand2",
             "apr_b13a_partner"],
    "B13C": ["apr_b13c_cand1", "apr_b13c_cand2",
             "apr_b13c_partner"],
    "B13S": ["apr_b13s_cand1"],
    "PLANB12C": ["apr_b12c_c08", "apr_planb12c_cand2",
                 "apr_b12c_c19"],
    "PLANB12": ["apr_planb12_cand1", "apr_planb12_cand2",
                "apr_planb12_partner"],
    "PLANB2SB": ["apr_planb2sb_cand1"],
    "PLANB2": ["apr_planb2_cand1", "apr_planb2_cand2"],
    "PLANB3": ["apr_planb3_cand1", "apr_planb3_cand2",
               "apr_planb3_partner"],
    "PLANB4": ["apr_planb4_cand1", "apr_planb4_cand2",
               "apr_planb4_partner"],
    "PLANB6": ["apr_planb6_cand1", "apr_planb6_cand2",
               "apr_planb6_partner"],
    "PLANB7": ["apr_planb7_cand1", "apr_b7_c04",
               "apr_planb7_partner"],
    "PLANB8": ["apr_b8_c07", "apr_planb8_cand2",
               "apr_planb8_partner"],
    "PLANB9C": ["apr_b9c", "apr_b9c_c03",
                "apr_planb9c_partner"],
    "PLANB9": ["apr_planb9_cand1", "apr_planb9_cand2",
               "apr_planb9_partner"],
    "PLANB": ["apr_planb_cand1", "apr_planb_cand2"],
    "ROUND3": ["apr_round3_cand1", "apr_round3_cand2"],
    "ROUND4": ["apr_round4_cand1", "apr_round4_cand2"],
}
POOL_DESIGNS = [d for v in POOL_FAMILIES.values() for d in v]
_DESIGN_SYMBOLS = tuple(sorted(
    {e["symbol"] for n in POOL_DESIGNS
     for e in DESIGNS[n]["equations"]}))


def _default_state_path():
    from core.new8_walk import default_state_path
    return default_state_path(SYSTEM_NAME)


# ------------------------------------------------- ledger form --
def _prep(df):
    df = df.copy()
    for c in ("check", "entry_time", "exit_time"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c])
    if "entry_time" not in df.columns:
        df["entry_time"] = df["check"] - pd.Timedelta(minutes=30)
    df["net"] = df["gross_pips"] - 2.5
    return df.sort_values("check", kind="stable") \
        .reset_index(drop=True)


def pcol_ledger(df, cor_map=PCOL_COR, cap=PCOL_CAP):
    """planE_transforms.pcol verbatim."""
    df = _prep(df)
    opens = []
    drop = np.zeros(len(df), dtype=bool)
    for i in range(len(df)):
        r = df.iloc[i]
        g = cor_map.get(r["symbol"], r["symbol"])
        opens = [o for o in opens if o[0] > r["check"]]
        n = sum(1 for o in opens
                if o[1] == g and o[2] == r["direction"])
        if n >= cap:
            drop[i] = True
            continue
        opens.append((r["exit_time"], g, r["direction"]))
    return df[~drop].reset_index(drop=True)


def _cascade(base, sources, hours=None):
    """planE_transforms.cascade verbatim (the second-
    priority fill cascade)."""
    base = _prep(base)
    taken = [(r["check"], r["exit_time"], r["symbol"])
             for _, r in base.iterrows()]
    by_check_sym = {}
    for c, e, s in taken:
        by_check_sym.setdefault(c, set()).add(s)
    pool = pd.concat(sources, ignore_index=True)
    pool["check"] = pd.to_datetime(pool["check"])
    pool["exit_time"] = pd.to_datetime(pool["exit_time"])
    pool = pool.sort_values(["check", "score"],
                            ascending=[True, False],
                            kind="stable")
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
        if any(s == r["symbol"] and c < e
               and r["exit_time"] > cc for (cc, e, s) in taken):
            continue
        fills.append(r)
        used.add(c)
        taken.append((c, r["exit_time"], r["symbol"]))
    if not fills:
        return base.drop(columns=["net"])
    out = pd.concat([base.drop(columns=["net"]),
                     pd.DataFrame(fills)], ignore_index=True)
    out = out.sort_values("check", kind="stable") \
        .reset_index(drop=True)
    out["net"] = out["gross_pips"] - 2.5
    return out


def cons_fills_ledger(base, walks, min_agree=MIN_AGREE,
                      hours=FILL_HOURS):
    """planE_transforms.cons_fills verbatim."""
    base = _prep(base)
    fam_rows = {}
    for fam, dns in POOL_FAMILIES.items():
        rows = [_prep(walks[d]) for d in dns if d in walks]
        if rows:
            fam_rows[fam] = pd.concat(rows, ignore_index=True)
    keys = {}
    for fam, df in fam_rows.items():
        for k in set(zip(df["check"], df["symbol"],
                         df["direction"])):
            keys.setdefault(k, set()).add(fam)
    good = {k for k, fs in keys.items() if len(fs) >= min_agree}
    srcs = []
    for fam, df in fam_rows.items():
        m = df[["check", "symbol", "direction"]].apply(tuple, axis=1).isin(good)
        if m.any():
            srcs.append(df[m])
    return _cascade(base, srcs, hours=hours)


def build_e04(base, walks):
    """The graded E04 construction over a combined base
    stream + the 43 pool walks (dict name -> ledger)."""
    return cons_fills_ledger(pcol_ledger(base), walks)


# --------------------------------------------- streaming form --
# stcv thresholds for apr_planb4_partner, frozen from the
# mine_planb4 two-pass over the era (unvetoed walk -> FIT
# (<=2020) picks -> stc at check-90m quantiles; 167 picks,
# 110 FIT): the module binds them as constants.
STCV_BOUNDS = {"apr_planb4_partner": (11.904050095535885,
                                      86.68648123639984)}


class AprE04State:
    """43 pool DesignWalks + the streaming PCOL + CONS3
    stage over the combined (87e + 87s) base stream.

    Persisted: the pool walks, the PCOL open list, the
    kept rows (post-PCOL base + fills) and the fills.
    step() takes the composed base rows for the check
    (ledger-form dicts) and returns the delivered rows
    for the check (kept base rows + at most one fill)."""

    def __init__(self, path=None):
        self.path = path or _default_state_path()
        self.designs = {dn: DESIGNS[dn] for dn in POOL_DESIGNS}
        self.walks = {dn: DesignWalk(dd["equations"],
                                     veto=dd.get("veto"))
                      for dn, dd in self.designs.items()}
        self._bound_ctx = None
        self.pcol_opens = []
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
        self.pcol_opens = [(pd.Timestamp(x), g, dr)
                           for x, g, dr in d.get("pcol_opens", [])]
        for n, wd in (d.get("walks") or {}).items():
            if n not in self.walks:
                continue
            self.walks[n].picks = self._de(wd.get("picks", []))
            self.walks[n].open_exit = {
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
                "pcol_opens": [[x.isoformat(), g, dr]
                               for x, g, dr in self.pcol_opens],
                "walks": {n: {"picks": self._ser(w.picks),
                              "open_exit": {
                                  s: [pd.Timestamp(x).isoformat()
                                      for x in xs]
                                  for s, xs in w.open_exit.items()}}
                          for n, w in self.walks.items()}}
        with open(self.path, "w") as fh:
            json.dump(data, fh)
        return self.path

    # -------------------------------------------------- vetoes --
    def _bind(self, ctx):
        if self._bound_ctx is ctx:
            return
        from core.new8_walk import make_m15v

        def feat_at(sym, col, t):
            f = ctx.feats[sym]
            loc = f.index.get_indexer([pd.Timestamp(t)])[0]
            if loc < 0 or col not in f:
                return float("nan")
            return float(f[col].iloc[loc])

        def agree(col):
            def vf(eq, tr, ent_t):
                v = feat_at(eq["symbol"], col,
                            pd.Timestamp(ent_t)
                            - pd.Timedelta(minutes=60))
                if not np.isfinite(v):
                    return False
                dd = 1 if tr["direction"] == "BUY" else -1
                return not (dd * v > 0)
            return vf

        def cf3v():
            def vf(eq, tr, ent_t):
                v = feat_at(eq["symbol"], "cf3_stack",
                            pd.Timestamp(ent_t)
                            - pd.Timedelta(minutes=60))
                if not np.isfinite(v):
                    return False
                if tr["direction"] == "BUY":
                    return v < 2
                return v > -2
            return vf

        def extreme(col, lo, hi):
            def vf(eq, tr, ent_t):
                v = feat_at(eq["symbol"], col,
                            pd.Timestamp(ent_t)
                            - pd.Timedelta(minutes=60))
                if not np.isfinite(v):
                    return False
                if tr["direction"] == "BUY":
                    return False if hi is None else v > hi
                return False if lo is None else v < lo
            return vf

        for dn, w in self.walks.items():
            v = self.designs[dn].get("veto")
            if not v:
                continue
            fns = []
            for p in str(v).split("+"):
                if p == "m15":
                    mc = {}
                    for e in self.designs[dn]["equations"]:
                        s = e["symbol"]
                        if s in ctx.m15:
                            f = ctx.m15[s]
                            mc[s] = (f.index.view("int64"),
                                     f["Close"].to_numpy(float))
                    fns.append(make_m15v(mc) if mc else
                               (lambda eq, tr, ent_t: False))
                elif p == "cfv":
                    fns.append(agree("cf_stack"))
                elif p == "cf2v":
                    fns.append(agree("cf2_stack"))
                elif p == "h4v":
                    fns.append(agree("h4_state"))
                elif p == "cf3v":
                    fns.append(cf3v())
                elif p == "stcv":
                    lo, hi = STCV_BOUNDS[dn]
                    fns.append(extreme("stc", lo, hi))
                # 'd1v' / 'coolv': DesignWalk inline.
            if len(fns) == 1:
                w.veto_fn = fns[0]
            elif fns:
                def vf(eq, tr, ent_t, fns=fns):
                    return any(f(eq, tr, ent_t) for f in fns)
                w.veto_fn = vf
        self._bound_ctx = ctx

    # ---------------------------------------------------- step --
    def step(self, ctx, check, base_rows):
        chk = pd.Timestamp(check)
        self._bind(ctx)
        for dn, w in self.walks.items():
            w.step(chk, ctx.rows_at(dn, chk))
        # -- PCOL over the base rows (stream order)
        kept_base = []
        for r in base_rows:
            g = PCOL_COR.get(r["symbol"], r["symbol"])
            self.pcol_opens = [o for o in self.pcol_opens
                               if o[0] > chk]
            n = sum(1 for o in self.pcol_opens
                    if o[1] == g and o[2] == r["direction"])
            if n >= PCOL_CAP:
                continue
            self.pcol_opens.append(
                (pd.Timestamp(r["exit_time"]), g, r["direction"]))
            kept_base.append(r)
        # -- CONS3 stage
        fam_rows = {}
        for fam, dns in POOL_FAMILIES.items():
            rows = []
            for dn in dns:
                w = self.walks[dn]
                if w.picks and pd.Timestamp(
                        w.picks[-1]["check"]) == chk:
                    rows.append(w.picks[-1])
            fam_rows[fam] = rows
        fams_by_key = {}
        for fam, rows in fam_rows.items():
            for r in rows:
                fams_by_key.setdefault(
                    (r["symbol"], r["direction"]), set()).add(fam)
        good = {k for k, fs in fams_by_key.items()
                if len(fs) >= MIN_AGREE}
        fill = None
        if good and chk.hour in FILL_HOURS:
            taken = [(pd.Timestamp(r["check"]),
                      pd.Timestamp(r["exit_time"]), r["symbol"])
                     for r in self.kept]
            base_syms = {r["symbol"] for r in kept_base}
            cands = [r for rows in fam_rows.values()
                     for r in rows
                     if (r["symbol"], r["direction"]) in good]
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
        out = list(kept_base)
        self.kept.extend(kept_base)
        if fill is not None:
            self.fills.append(fill)
            self.kept.append(fill)
            out.append(fill)
        self.processed.append(str(chk))
        return out


def load_e04_state(path=None):
    p = path or _default_state_path()
    try:
        return AprE04State(path=p)
    except Exception:
        return AprE04State(path=p)


def is_cycle87f_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE87F_CHECK_HOURS and t.minute == 30


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


def _base_entries(frames, check_time_utc, m15_frames,
                  open_symbols):
    """The combined base for one check: cycle87e's panel
    entries; if the best is silent, cycle87s's pick (the
    app's combined-delivery rule, internalised)."""
    entries = _c87e.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    if entries is not None and len(entries):
        return entries
    sig = _c87s.evaluate_cycle87s_signals(
        frames, check_time_utc, m15_frames=m15_frames)
    if sig is None or not len(sig):
        return pd.DataFrame()
    return _c87s.select_cycle87s_entries(
        sig, open_symbols=open_symbols)


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full E04 entries for one check: the combined
    87e<-87s base entries settled through PCOL + the
    CONS3 stage over this system's persisted pool walks."""
    entries = _base_entries(frames, check_time_utc,
                            m15_frames, open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    m15map = ensure_m15(m15_frames, _DESIGN_SYMBOLS)
    ctx = CandidateContext(frames, m15map, POOL_DESIGNS)
    chk = pd.Timestamp(check_time_utc)
    base_rows = []
    if entries is not None and len(entries):
        for _, r in entries.iterrows():
            d = dict(r)
            d["check"] = chk
            if d.get("entry_time") is None:
                d["entry_time"] = chk - pd.Timedelta(minutes=30)
            if d.get("exit_time") is None:
                d["exit_time"] = pd.Timestamp(d["entry_time"]) \
                    + pd.Timedelta(hours=int(d.get("hold_h", 48)))
            if "strategy" not in d or d.get("strategy") is None:
                d["strategy"] = d.get("equation")
            base_rows.append(d)
    state = load_e04_state()
    kept = state.step(ctx, chk, base_rows)
    state.save()
    if not kept:
        return pd.DataFrame()
    return pd.DataFrame([_signal_row(r) for r in kept
                         if "entry_px" in r])


# ------------------------------------------------- coordinator --
def fetch_cycle87f_m15_frames(state=None):
    from core.cycle87e_best import fetch_cycle87e_m15_frames
    try:
        return fetch_cycle87e_m15_frames(state)
    except TypeError:
        return fetch_cycle87e_m15_frames()


def evaluate_cycle87f_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    """Final E04 entries for the check, as the signals
    frame (panel_entries already applies the full form)."""
    return panel_entries(frames, check_time_utc,
                         m15_frames=m15_frames)


def select_cycle87f_entries(signals: pd.DataFrame,
                            open_symbols=()):
    """Open-symbol filter over the evaluated E04 entries."""
    if signals is None or len(signals) == 0:
        return signals
    if signals.attrs.get("status"):
        return signals
    open_set = {str(s).upper() for s in (open_symbols or ())}
    if not open_set or "symbol" not in signals.columns:
        return signals
    return signals[~signals["symbol"].astype(str)
                   .str.upper().isin(open_set)]
