"""NEW8 candidate evaluation + merged-walk panel state
(2026-10-27).

CandidateContext builds the NEW8 feature frames for a design's
symbols from the app frames (H1 + optional M15 + the dollar
frame for the xdx context columns) via core.new8_features, and
evaluates design equations at one check in the research tab
semantics (conditions on the signal-bar feature row, ATR-sized
TP/SL with the research clips, H1 barrier exit via
core.new8_walk.sim_fixed_vec).

MergedWalkState is the panel-path state for a merged BEST
system (incumbent + candidate design(s)): it records incumbent
picks and candidate walk picks check by check in evaluation
order and applies validate_new8.build_combined's rules in
streaming form (same-check drop; interval-overlap drop vs
recorded incumbent and accepted-candidate intervals). The era
replay gate runs the batch functions in core.new8_walk over
the full era and is exact; the streaming path necessarily
judges overlaps against picks recorded so far, the same live
approximation the BRIEF21 walk ledger documents.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from core.new8_designs import DESIGNS
from core.new8_features import (build_symbol_features,
                                frame_to_research, m30_from_m15,
                                pip_size_new8)
from core.new8_walk import (MAX_HOLD, DesignWalk, ohlc_from_frame,
                            sim_fixed_vec)

DOLLAR_KEYS = ("DXY", "DOLLARIDX")

# Plan B-7 cross-symbol baskets (build_features_planb7
# verbatim): each symbol's basket = the pairs sharing its
# base currency; the USD basket is signed (USD as quote
# currency counts negative).
B7_BASKETS = {
    'EUR': ['EURUSD', 'EURGBP', 'EURJPY', 'EURCHF', 'EURCAD',
            'EURAUD', 'EURNZD'],
    'GBP': ['GBPUSD', 'GBPJPY', 'GBPCHF', 'GBPCAD', 'GBPAUD',
            'GBPNZD'],
    'USD': ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDJPY',
            'USDCHF', 'USDCAD'],
    'JPY': ['USDJPY', 'EURJPY', 'GBPJPY', 'AUDJPY', 'CHFJPY',
            'CADJPY', 'NZDJPY'],
    'CHF': ['USDCHF', 'EURCHF', 'GBPCHF', 'AUDCHF', 'CADCHF',
            'NZDCHF'],
    'AUD': ['AUDUSD', 'AUDJPY', 'AUDCHF', 'AUDCAD', 'AUDNZD',
            'EURAUD', 'GBPAUD'],
    'NZD': ['NZDUSD', 'NZDJPY', 'NZDCHF', 'NZDCAD', 'EURNZD',
            'GBPNZD', 'AUDNZD'],
    'CAD': ['USDCAD', 'EURCAD', 'GBPCAD', 'AUDCAD', 'NZDCAD',
            'CADJPY', 'CADCHF'],
}
B7_USD_SIGNS = {'EURUSD': -1.0, 'GBPUSD': -1.0, 'AUDUSD': -1.0,
                'NZDUSD': -1.0, 'USDJPY': 1.0, 'USDCHF': 1.0,
                'USDCAD': 1.0}


def _b7_basket_of(sym):
    if sym in DOLLAR_KEYS or sym == 'DOLLARIDX':
        return 'USD'
    return sym[:3]


def b7_context(frames):
    """Cross-symbol context for the Plan B-7 feature block
    (build_features_planb7.main verbatim): basket momentum /
    signed-RSI series per currency basket and the dollar
    momentum / deviation / RSI series, all on the EURUSD
    frame index. Returns {symbol: {'bm','br','dm','dd','dr'}}
    with Series on that reference index (the feature builder
    reindexes to each symbol's own index). Base features are
    computed for every frame present; missing members simply
    drop out of the basket means (research semantics)."""
    base = {}
    for sym, h1 in frames.items():
        if h1 is None or len(h1) == 0:
            continue
        try:
            bf = build_symbol_features(sym, h1, ())
        except Exception:
            continue
        if 'ema_dev' not in bf:
            # The research frames carry ema_dev from the r4
            # block: (Close - EMA200) / atr14, verbatim.
            cl = bf['Close']
            bf['ema_dev'] = (cl - cl.ewm(
                span=200, adjust=False).mean()) / bf['atr14']
        base[sym] = bf
    if 'EURUSD' not in base:
        return {}
    ref_idx = base['EURUSD'].index

    def _col(sym, col):
        s = base[sym][col]
        return pd.Series(s.to_numpy(), index=s.index)

    basket_mom, basket_rsi = {}, {}
    for code, members in B7_BASKETS.items():
        moms, rsis = {}, {}
        for m in members:
            if m not in base:
                continue
            sgn = B7_USD_SIGNS.get(m, 1.0) if code == 'USD' \
                else 1.0
            moms[m] = _col(m, 'mom24').reindex(ref_idx) * sgn
            rsis[m] = ((_col(m, 'rsi14') - 50.0) / 50.0) \
                .reindex(ref_idx) * sgn
        basket_mom[code] = pd.DataFrame(moms).mean(axis=1) \
            if moms else pd.Series(np.nan, index=ref_idx)
        basket_rsi[code] = pd.DataFrame(rsis).mean(axis=1) \
            if rsis else pd.Series(np.nan, index=ref_idx)
    dx_key = next((k for k in DOLLAR_KEYS if k in base), None)
    if dx_key is not None:
        d_mom = _col(dx_key, 'mom24').reindex(ref_idx)
        d_dev = _col(dx_key, 'ema_dev').reindex(ref_idx)
        d_rsi = ((_col(dx_key, 'rsi14') - 50.0) / 50.0) \
            .reindex(ref_idx)
    else:
        d_mom = d_dev = d_rsi = pd.Series(np.nan, index=ref_idx)
    out = {}
    for sym in frames:
        b = _b7_basket_of(sym)
        if b not in basket_mom:
            continue
        out[sym] = {'bm': basket_mom[b], 'br': basket_rsi[b],
                    'dm': d_mom, 'dd': d_dev, 'dr': d_rsi}
    return out


def _norm_frame(df):
    """App frame -> Datetime-indexed naive-UTC frame."""
    if df is None or len(df) == 0:
        return None
    f = df.copy()
    if "Datetime" in f.columns:
        f = f.set_index("Datetime")
    f.index = pd.to_datetime(f.index)
    if f.index.tz is not None:
        f.index = f.index.tz_convert("UTC").tz_localize(None)
    return f.sort_index()


def ensure_m15(m15_frames, symbols):
    """Top up M15 frames for candidate symbols through the
    app's shared cycle78 M15 path (repository first, provider
    chain for misses, memoised). Symbols the path cannot
    serve stay absent -- the affected feature columns stay
    NaN and equations reading them simply do not fire.
    Never raises."""
    out = dict(m15_frames or {})
    missing = [s for s in symbols if s not in out]
    if missing:
        try:
            from core.cycle78_best import fetch_cycle78_m15_frames
            got = fetch_cycle78_m15_frames(symbols=tuple(missing))
            for s, f in (got or {}).items():
                if f is not None and len(f):
                    out[s] = f
        except Exception:
            pass
    return out


class CandidateContext:
    """Feature frames + ohlc arrays for a set of designs over
    one frames snapshot. Built once per panel evaluation."""

    def __init__(self, frames, m15_frames=None, design_names=()):
        self.frames = {str(s).upper(): _norm_frame(f)
                       for s, f in (frames or {}).items()
                       if f is not None and len(f)}
        self.m15 = {str(s).upper(): _norm_frame(f)
                    for s, f in (m15_frames or {}).items()
                    if f is not None and len(f)}
        self.design_names = tuple(design_names)
        groups = set()
        syms = set()
        for name in self.design_names:
            d = DESIGNS[name]
            groups.update(d["groups"])
            syms.update(e["symbol"] for e in d["equations"])
        self.groups = tuple(g for g in
                            ("r4", "planb", "b2cf", "b3", "b4",
                             "b5", "b6v", "b7")
                            if g in groups)
        self.symbols = sorted(syms)
        self._dx_mom = self._build_dx_mom() if "r4" in groups \
            else None
        self._b7 = b7_context(self.frames) if "b7" in groups \
            else {}
        self.feats = {}
        self.ohlc = {}
        for sym in self.symbols:
            self._build(sym)

    def _dollar_frame(self):
        for k in DOLLAR_KEYS:
            if k in self.frames:
                return self.frames[k]
        return None

    def _build_dx_mom(self):
        dx = self._dollar_frame()
        if dx is None:
            return None
        f = build_symbol_features("DOLLARIDX", dx, ())
        return f["mom24"]

    def _build(self, sym):
        h1 = self.frames.get(sym)
        if h1 is None:
            return
        m15 = self.m15.get(sym)
        m30 = m30_from_m15(m15) if m15 is not None else None
        self.feats[sym] = build_symbol_features(
            sym, h1, self.groups, m15=m15, m30=m30,
            dx_mom=self._dx_mom, b7ctx=self._b7.get(sym))
        fr, _ = frame_to_research(h1)
        self.ohlc[sym] = ohlc_from_frame(fr)

    # -------------------------------------------------- rows --
    def rows_at(self, design_name, check):
        """{eq_id: tab-row dict} for one design at one check,
        in c70_sim.evaluate_candidate semantics (single-check
        slice). Rows carry the research tab fields plus
        'provisional_exit' (True when the frame ends inside
        the 48h exit window -- live use only; era frames are
        complete)."""
        d = DESIGNS[design_name]
        chk = pd.Timestamp(check)
        sig_t = chk - pd.Timedelta(hours=1, minutes=30)
        ent_t = chk - pd.Timedelta(minutes=30)
        out = {}
        for eq in d["equations"]:
            if eq["hour"] != chk.hour:
                continue
            sym = eq["symbol"]
            feat = self.feats.get(sym)
            oc = self.ohlc.get(sym)
            if feat is None or oc is None:
                continue
            pos = feat.index.get_indexer([sig_t])[0]
            if pos < 0:
                continue
            row = feat.iloc[pos]
            ok = True
            for col, op, val in eq["conditions"]:
                v = row[col]
                if not np.isfinite(v):
                    ok = False
                    break
                if op == ">" and not (v > val):
                    ok = False
                    break
                if op == "<" and not (v < val):
                    ok = False
                    break
                if op == ">=" and not (v >= val):
                    ok = False
                    break
                if op == "<=" and not (v <= val):
                    ok = False
                    break
            if not ok:
                continue
            atr = float(row["atr14"])
            pip = pip_size_new8(sym)
            tp = float(np.clip(eq["tp_mult"] * atr / pip,
                               10.0, 500.0))
            sl = float(np.clip(eq["sl_mult"] * atr / pip,
                               5.0, 100.0))
            ent_pos = oc["pos_of"].get_indexer([ent_t])[0]
            if ent_pos < 0:
                continue
            direction = eq["direction"]
            if direction == "TREND":
                mom = float(row["mom24"])
                direction = "BUY" if mom > 0 else "SELL"
            r = sim_fixed_vec(oc["o"], oc["h"], oc["l"], oc["c"],
                              np.array([ent_pos]), direction,
                              np.array([tp]), np.array([sl]), pip,
                              max_hold=MAX_HOLD, cost=2.5)
            out[eq["id"]] = dict(
                check=chk, symbol=sym, direction=direction,
                entry_px=float(r["entry_px"][0]),
                exit_px=float(r["exit_px"][0]),
                tp_pips_used=tp, sl_pips_used=sl,
                gross_pips=float(r["gross_pips"][0]),
                net_pips=float(r["net_pips"][0]),
                exit_reason=str(r["exit_reason"][0]),
                hold_h=int(r["hold_h"][0]),
                exit_time=pd.Timestamp(oc["dt"][r["exit_pos"][0]]),
                entry_time=ent_t,
                provisional_exit=bool(
                    ent_pos + MAX_HOLD - 1 >= len(oc["c"])))
        return out

    def signal_frame(self, design_name, check):
        """Candidate rows at one check in the app signal-frame
        shape (one row per firing equation)."""
        d = DESIGNS[design_name]
        chk = pd.Timestamp(check)
        rows = self.rows_at(design_name, chk)
        out = []
        for eq in d["equations"]:
            tr = rows.get(eq["id"])
            if tr is None:
                continue
            out.append({
                "check": chk, "symbol": eq["symbol"],
                "equation": eq["id"], "direction": tr["direction"],
                "score": float(eq["score"]),
                "entry_px": tr["entry_px"],
                "tp_pips": tr["tp_pips_used"],
                "sl_pips": tr["sl_pips_used"],
                "signal_candle": chk - pd.Timedelta(
                    hours=1, minutes=30),
                "entry_candle": chk - pd.Timedelta(minutes=30),
            })
        return pd.DataFrame(out)


def select_walk_pick(signals, open_symbols=()):
    """Standalone candidate-system selection (second-best
    modules): top-1 by score (stable), skipping symbols with
    an open position -- the walk157 single pick under the
    panel's occupancy."""
    if signals is None or len(signals) == 0:
        return signals.iloc[0:0] if signals is not None \
            else pd.DataFrame()
    held = {str(s).upper() for s in (open_symbols or ())}
    out = []
    for _, row in signals.sort_values("score", ascending=False,
                                      kind="mergesort").iterrows():
        if str(row["symbol"]).upper() in held:
            continue
        out.append(row)
        break
    return pd.DataFrame(out).reset_index(drop=True) if out \
        else signals.iloc[0:0]


# ==================================================== merged walk --
class MergedWalkState:
    """Persisted streaming state for one merged BEST system.

    incumbent_picks: recorded incumbent entries (signal-row
    dicts enriched with H1-sim exit fields when computable).
    walks: {design_name: DesignWalk}. accepted: candidate picks
    kept by the merge. Intervals are judged on the recorded
    rows' [entry_time, exit_time); a pick whose exit is not yet
    computable from the frames at hand carries exit_time =
    entry + 48h provisionally (updated on later calls)."""

    def __init__(self, system, design_names, path=None):
        self.system = str(system)
        self.design_names = list(design_names)
        self.path = path
        self.incumbent_picks = []
        self.accepted = []
        self.walks = {n: DesignWalk(DESIGNS[n]["equations"],
                                    veto=DESIGNS[n]["veto"])
                      for n in self.design_names}

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
            "system": self.system,
            "incumbent_picks": ser(self.incumbent_picks),
            "accepted": ser(self.accepted),
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
    def load(cls, path, system, design_names):
        with open(path) as fh:
            data = json.load(fh)
        st = cls(system, design_names, path=path)

        def de(rows):
            out = []
            for r in rows:
                d = dict(r)
                for k in ("check", "entry_time", "exit_time"):
                    if d.get(k) is not None:
                        d[k] = pd.Timestamp(d[k])
                out.append(d)
            return out

        st.incumbent_picks = de(data.get("incumbent_picks", []))
        st.accepted = de(data.get("accepted", []))
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
        """(Re)compute a recorded pick's exit from the context's
        current H1 bars (sim_fixed_vec semantics). Returns True
        when the exit is final (window fully inside the frame)."""
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
                          max_hold=MAX_HOLD, cost=2.5)
        row["exit_px"] = float(r["exit_px"][0])
        row["exit_time"] = pd.Timestamp(oc["dt"][r["exit_pos"][0]])
        row["exit_reason"] = str(r["exit_reason"][0])
        row["hold_h"] = int(r["hold_h"][0])
        row["gross_pips"] = float(r["gross_pips"][0])
        row["net_pips"] = float(r["net_pips"][0])
        return ent_pos + MAX_HOLD - 1 < len(oc["c"])

    def refresh_exits(self, ctx):
        for row in self.incumbent_picks + self.accepted:
            if row.get("exit_final"):
                continue
            if self._sim_exit(ctx, row):
                row["exit_final"] = True
        for w in self.walks.values():
            w.open_exit = {}
            for row in w.picks:
                w.open_exit.setdefault(row["symbol"], []).append(
                    pd.Timestamp(row["exit_time"]))
        # candidate walk picks and accepted rows are the same
        # objects' copies; keep walk occupancy in step with the
        # accepted rows' refreshed exits where they correspond
        acc_by_key = {(r["check"], r["strategy"]): r
                      for r in self.accepted}
        for w in self.walks.values():
            for row in w.picks:
                a = acc_by_key.get((row["check"], row["strategy"]))
                if a is not None:
                    row["exit_time"] = a["exit_time"]
            w.open_exit = {}
            for row in w.picks:
                w.open_exit.setdefault(row["symbol"], []).append(
                    pd.Timestamp(row["exit_time"]))

    # --------------------------------------------------- step --
    def _record_incumbent(self, ctx, check, entries):
        chk = pd.Timestamp(check)
        have = {(pd.Timestamp(r["check"]), r["symbol"])
                for r in self.incumbent_picks}
        for _, e in entries.iterrows():
            key = (chk, str(e["symbol"]))
            if key in have:
                continue
            ent = chk - pd.Timedelta(minutes=30)
            row = dict(
                check=chk, entry_time=ent, symbol=str(e["symbol"]),
                direction=str(e["direction"]),
                strategy=str(e.get("equation",
                                   e.get("strategy", ""))),
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
            self.incumbent_picks.append(row)
            have.add(key)

    def _merge_accept(self, cand_row):
        """build_combined rules vs the recorded state."""
        chk = cand_row["check"]
        if any(pd.Timestamp(r["check"]) == chk
               for r in self.incumbent_picks):
            return False
        # A row accepted earlier IN THIS CHECK by a previous
        # design also busies the check: in the research
        # two-stage merge, the second design's reference frame
        # is the first stage's combined ledger, whose checks
        # all drop later candidates (build_combined check_busy
        # is symbol-independent).
        if any(pd.Timestamp(r["check"]) == chk
               for r in self.accepted):
            return False
        ent, ex = cand_row["entry_time"], cand_row["exit_time"]
        sym = cand_row["symbol"]
        for r in self.incumbent_picks:
            if r["symbol"] == sym and ent < r["exit_time"] \
                    and r["entry_time"] < ex:
                return False
        for r in self.accepted:
            if r["symbol"] == sym and ent < r["exit_time"] \
                    and r["entry_time"] < ex:
                return False
        return True

    def step(self, ctx, check, incumbent_entries):
        """One check of the merged walk. incumbent_entries: the
        incumbent system's selected entries (signal frame) at
        this check (may be empty). Returns the accepted
        candidate rows (list of walk-format dicts)."""
        self.refresh_exits(ctx)
        if incumbent_entries is not None \
                and len(incumbent_entries):
            self._record_incumbent(ctx, check, incumbent_entries)
        out = []
        for name in self.design_names:
            rows = ctx.rows_at(name, check)
            pick = self.walks[name].step(check, rows)
            if pick is None:
                continue
            if self._merge_accept(pick):
                acc = dict(pick)
                acc["exit_final"] = not pick.get(
                    "provisional_exit", False)
                acc.pop("provisional_exit", None)
                self.accepted.append(acc)
                out.append(acc)
        return out


def default_state_path(system: str) -> str:
    """data/walk_ledgers_new8/<system>.json inside the app
    tree (kept apart from the BRIEF21 ledger directory)."""
    base = os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))
    return os.path.join(base, "data", "walk_ledgers_new8",
                        f"{system}.json")


def load_state(system, design_names):
    path = default_state_path(system)
    try:
        return MergedWalkState.load(path, system, design_names)
    except Exception:
        return MergedWalkState(system, design_names, path=path)


def candidate_signal_row(row):
    """An accepted candidate walk row as an app signal row."""
    return {"check": row["check"], "symbol": row["symbol"],
            "equation": row["strategy"],
            "direction": row["direction"], "score": row["score"],
            "entry_px": row["entry_px"],
            "tp_pips": row["tp_pips_used"],
            "sl_pips": row["sl_pips_used"],
            "signal_candle": row["check"] - pd.Timedelta(
                hours=1, minutes=30),
            "entry_candle": row["entry_time"]}
