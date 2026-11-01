"""Cycle 94G -- December Plan E E03 system (2026-11-01
install).

Form (Plan E winner E03, VALIDATED as ACCEPT over cycle94f;
validation file
work_r5_20cyc/results/dec_planE_FINAL_VALIDATION.md):

    cycle94f stream (shipped _FormState, unchanged)
      -> PCOL concurrency cap: at most 1 concurrent open
         position in the correlated group {GBPJPY, USDJPY}
         per direction (binds nowhere on the 2016-2025 era)
      -> CONS3 consensus fills: a (check, symbol, direction)
         key must appear in >= 3 of the 20 December pool
         families (48 pool design walks); the agreed rows
         enter through the second-priority cascade (<= 1 per
         check, symbol not taken at the check by the base,
         no same-symbol interval overlap), at the incumbent
         hours (10, 11, 13) UTC.

The pool walks are computed from market data at runtime
(DesignWalk over DESIGNS; the 45 new pool designs were
ported into core/new8_designs.py with this install --
transcription and walk gates in work_plane_port; 3 pool
designs already existed: dec_b12c, dec_b4_c08, dec_b6sb2).
No research artefacts are read at runtime.

Panel form: DecE03State composes the shipped cycle94f
_FormState and adds the 48 pool DesignWalks plus the
streaming PCOL/CONS3 stage. The stage is causal in check
order (agreement is counted per check across families;
the cascade and the PCOL cap only use prior kept rows),
so the streaming form follows the ledger construction
(build_e03) rule for rule.
"""

import json
import os

import numpy as np
import pandas as pd

import core.cycle94e_best as _c94e
import core.cycle94f_best as _c94f
from core.cycle94f_best import (_DESIGN_SYMBOLS, _FormState,
                                _signal_row, _win_ctx)
from core.new8_candidate import default_state_path, ensure_m15

SYSTEM_NAME = "cycle94g"
DEC_CHECK_HOURS_UTC = (10, 11, 13)
CYCLE94G_CHECK_HOURS = DEC_CHECK_HOURS_UTC

POOL_FAMILIES = {
    'B13A': ('dec_b13a_cand1', 'dec_b13a_cand2', 'dec_b13a_partner'),
    'B13C': ('dec_b13c_cand1', 'dec_b13c_cand2', 'dec_b13c_partner'),
    'B13O': ('dec_b13o_cand1',),
    'B13S': ('dec_b13s_cand1',),
    'PLANB12C': ('dec_b12c', 'dec_planb12c_cand2', 'dec_planb12c_partner'),
    'PLANB12': ('dec_planb12_cand1', 'dec_planb12_cand2', 'dec_planb12_partner'),
    'PLANB2': ('dec_planb2_cand1', 'dec_planb2_cand2'),
    'PLANB3': ('dec_planb3_cand1', 'dec_planb3_cand2', 'dec_planb3_partner'),
    'PLANB4': ('dec_b4_c08', 'dec_planb4_cand2', 'dec_planb4_partner'),
    'PLANB5': ('dec_planb5_cand1', 'dec_planb5_cand2', 'dec_planb5_partner'),
    'PLANB6SB2': ('dec_b6sb2',),
    'PLANB6SB': ('dec_planb6sb_cand1',),
    'PLANB6': ('dec_planb6_cand1', 'dec_planb6_cand2', 'dec_planb6_partner'),
    'PLANB7': ('dec_planb7_cand1', 'dec_planb7_cand2', 'dec_planb7_partner'),
    'PLANB8': ('dec_planb8_cand1', 'dec_planb8_cand2', 'dec_planb8_partner'),
    'PLANB9C': ('dec_planb9c_cand1', 'dec_planb9c_cand2', 'dec_planb9c_partner'),
    'PLANB9': ('dec_planb9_cand1', 'dec_planb9_cand2', 'dec_planb9_partner'),
    'PLANB': ('dec_planb_cand1', 'dec_planb_cand2'),
    'ROUND3': ('dec_round3_cand1', 'dec_round3_cand2'),
    'ROUND4': ('dec_round4_cand1', 'dec_round4_cand2'),
}
POOL_DESIGN_NAMES = tuple(n for v in POOL_FAMILIES.values()
                          for n in v)
MIN_AGREE = 3
PCOL_COR = {"USDJPY": "GBPJPY+USDJPY",
            "GBPJPY": "GBPJPY+USDJPY"}
PCOL_CAP = 1
COST = 2.5


# ================================================= ledger form ==
def pcol_ledger(df, cor_map=PCOL_COR, cap=PCOL_CAP):
    """planE_transforms.pcol verbatim semantics: no more
    than `cap` concurrent open positions in the same COR
    group AND same direction. Open = check <= t < exit."""
    df = df.copy()
    df["check"] = pd.to_datetime(df["check"])
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df = df.sort_values("check", kind="stable") \
        .reset_index(drop=True)
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
    return df[~drop].reset_index(drop=True), \
        dict(dropped=int(drop.sum()), cap=cap)


def cons_fills_ledger(base, pool_frames_by_family,
                      min_agree=MIN_AGREE,
                      hours=DEC_CHECK_HOURS_UTC):
    """planE_transforms.cons_fills + cascade, verbatim
    semantics on walk-format frames."""
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


def build_e03(base, pool_walks_by_family):
    """Full E03 ledger from the cycle94f stream + the 48
    pool walks ({family: [walk frames]})."""
    out, info1 = pcol_ledger(base)
    out, info2 = cons_fills_ledger(out, pool_walks_by_family)
    out["entry_time"] = out["check"] - pd.Timedelta(minutes=30)
    out["net"] = out["gross_pips"] - COST
    return out, dict(pcol=info1, cons=info2)


# ================================================== panel form ==
def _default_state_path():
    return default_state_path(SYSTEM_NAME)


def _form94_path():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "data", "walk_ledgers_new8",
                        "cycle94g_form94.json")


class DecE03State:
    """cycle94f _FormState + 48 pool DesignWalks + the
    streaming PCOL/CONS3 stage.

    Persisted: the embedded 94f form state (its own file),
    the pool walks, the PCOL open list, the final kept
    rows (post-PCOL base + fills) and the delivered fills.
    step() takes the 94f-kept ledger rows for the check
    and returns the final delivered ledger rows."""

    def __init__(self, path=None):
        self.path = path or _default_state_path()
        self.form94 = _FormState(path=_form94_path())
        from core.new8_designs import DESIGNS
        from core.new8_walk import DesignWalk
        self.designs = {dn: DESIGNS[dn] for dn in POOL_DESIGN_NAMES}
        self.walks = {dn: DesignWalk(dd["equations"],
                                     veto=dd.get("veto"))
                      for dn, dd in self.designs.items()}
        self._bound_ctx = None
        self.pcol_opens = []   # (exit_time, group, direction)
        self.kept = []         # final delivered ledger rows
        self.fills = []        # CONS3 fills delivered
        self.processed = []
        self._load()

    # ------------------------------------------------ persist --
    def _load(self):
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path) as fh:
                d = json.load(fh)
        except Exception:
            return

        def de(rows):
            out = []
            for r in rows:
                r = dict(r)
                for k in ("check", "entry_time", "exit_time"):
                    if r.get(k) is not None:
                        r[k] = pd.Timestamp(r[k])
                out.append(r)
            return out
        self.kept = de(d.get("kept", []))
        self.fills = de(d.get("fills", []))
        self.processed = list(d.get("processed", []))
        self.pcol_opens = [
            (pd.Timestamp(x), g, dr)
            for x, g, dr in d.get("pcol_opens", [])]
        for n, wd in (d.get("walks") or {}).items():
            if n not in self.walks:
                continue
            self.walks[n].picks = de(wd.get("picks", []))
            self.walks[n].open_exit = {
                s: [pd.Timestamp(x) for x in xs]
                for s, xs in (wd.get("open_exit") or {}).items()}

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(
            os.path.abspath(self.path)), exist_ok=True)

        def ser(rows):
            out = []
            for r in rows:
                d = dict(r)
                for k in ("check", "entry_time", "exit_time"):
                    if d.get(k) is not None:
                        d[k] = pd.Timestamp(d[k]).isoformat()
                out.append(d)
            return out
        data = dict(
            system=SYSTEM_NAME,
            kept=ser(self.kept), fills=ser(self.fills),
            processed=self.processed,
            pcol_opens=[[x.isoformat(), g, dr]
                        for x, g, dr in self.pcol_opens],
            walks={n: {"picks": ser(w.picks),
                       "open_exit": {
                           s: [pd.Timestamp(x).isoformat()
                               for x in xs]
                           for s, xs in w.open_exit.items()}}
                   for n, w in self.walks.items()})
        with open(self.path, "w") as fh:
            json.dump(data, fh)
        self.form94.save()

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

        for dn, w in self.walks.items():
            v = self.designs[dn].get("veto")
            if v == "m15":
                mc = {}
                for e in self.designs[dn]["equations"]:
                    s = e["symbol"]
                    if s in ctx.m15:
                        f = ctx.m15[s]
                        mc[s] = (f.index.view("int64"),
                                 f["Close"].to_numpy(float))
                w.veto_fn = make_m15v(mc) if mc else None
            elif v == "cfv":
                w.veto_fn = agree("cf_stack")
            elif v == "cf2v":
                w.veto_fn = agree("cf2_stack")
            elif v == "cf3v":
                w.veto_fn = cf3v()
            # 'd1v' / None: DesignWalk inline / no veto.
        self._bound_ctx = ctx

    # ---------------------------------------------------- step --
    def step(self, ctx, check, base_rows):
        chk = pd.Timestamp(check)
        self._bind(ctx)
        # -- step the pool walks for this check
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
        # -- pool rows at this check, by family
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
        if good and chk.hour in DEC_CHECK_HOURS_UTC:
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


def load_e03_state(path=None):
    p = path or _default_state_path()
    try:
        return DecE03State(path=p)
    except Exception:
        return DecE03State(path=p)


def is_cycle94g_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE94G_CHECK_HOURS and t.minute == 30


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full E03 entries for one check: the cycle94f kept
    rows for the check, settled through PCOL + the CONS3
    stage over this system's persisted pool walks."""
    entries = _c94e.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    m15map = ensure_m15(m15_frames, _DESIGN_SYMBOLS)
    ctxs = {}
    for sym, fr in frames.items():
        if fr is not None and len(fr):
            try:
                ctxs[sym] = _win_ctx(sym, fr, m15map.get(sym))
            except Exception:
                pass
    state = load_e03_state()
    base_rows = state.form94.step(ctxs, check_time_utc, entries)
    from core.new8_candidate import CandidateContext
    ctx = CandidateContext(frames, m15map, POOL_DESIGN_NAMES)
    kept = state.step(ctx, check_time_utc, base_rows)
    state.save()
    if not kept:
        return pd.DataFrame()
    return pd.DataFrame([_signal_row(r) for r in kept])


# ------------------------------------------------- coordinator
def fetch_cycle94g_m15_frames(state=None):
    from core.cycle94e_best import fetch_cycle94e_m15_frames
    try:
        return fetch_cycle94e_m15_frames(state)
    except TypeError:
        return fetch_cycle94e_m15_frames()


def evaluate_cycle94g_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    """Final E03 entries for the check, as the signals
    frame (panel_entries already applies the full form)."""
    return panel_entries(frames, check_time_utc,
                         m15_frames=m15_frames)


def select_cycle94g_entries(signals: pd.DataFrame,
                            open_symbols=()):
    """Open-symbol filter over the evaluated E03 entries."""
    if signals is None or len(signals) == 0:
        return signals
    if signals.attrs.get("status"):
        return signals
    open_set = {str(s).upper() for s in (open_symbols or ())}
    if not open_set or "symbol" not in signals.columns:
        return signals
    return signals[~signals["symbol"].astype(str)
                   .str.upper().isin(open_set)]
