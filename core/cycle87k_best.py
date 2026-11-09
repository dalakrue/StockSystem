"""Cycle 87K -- April: design R108A09 (Round 108
worst-week shield, shield-quota adds + near-miss
fill) over the shipped cycle87i stream / 87f panel
surface.

Built on Everest from design R108A09 under the
user's explicit order of 2026-11-09 (anchor proof
skipped on his scoped waiver). NOT VALIDATED.

The design (filed spec: fx_research/round6_r108
SLATE_R6R108_APR.md + grade_r6r108_apr.json): kept =
the base set (R3A07 over the stored April pool) +
shield-quota adds + the near-miss fill. The shield
classification is computed from the base's kept DISC
trades only: WNET_w = summed net of base DISC trades
by ISO week of entry; RED weeks have WNET < 0; the
worst-week set WW = the up-to-3 most negative red
weeks; WSYM = symbols whose base trades sum < 0
inside a WW week; RSYM = the same over all red
weeks; POST weeks = the earliest frame week after
each WW week. Bands by priority: WEEK-tainted /
SYMBOL-tainted / POST / CLEAN. The quota pool caps
each band at its top-4 rows by the balanced (1,1,1)
confluence score (legs sH/sM/sF from the research
parts() formulas; scales fitted on the incumbent
DISC keeps: qH = 73.28 pips, qM = 11.74 pips); adds
are the pool ranked by that score, up to +14 under
the overlap rule (kept wins, <= 1 open/symbol), DISC
rows only. Then the near-miss fill: every check slot
(a distinct entry timestamp among non-dollar form
rows) left empty is filled with the slot's nearest
row by balanced score (single attempt per slot;
occupancy law applies). For April the base holds
zero red DISC weeks, so WW is empty, every DISC
addable row is CLEAN, and the quota pool is the
top-4 CLEAN rows. Filed grade targets (stored
frame): DISC kept 873, win 97.59%, net +10503.40;
AUDIT kept 218, win 95.41%, net +2777.48, leftover
74.04%, epd 4.955. Build verification on this
machine (module code over the stored stream +
stored bar features + the recomputed R3A07 base):
reproduced exactly -- see
fx_research/install_build_2026-11-09/apr/.

Live mapping (same architecture as the shipped 87j
form): the candidate group is the 87f panel surface;
each row's base flag is settled by stepping a
private cycle87i form instance (own sidecar
namespace), and the accumulated snapshot is settled
through the design rule above (the rule is causal,
so the current check's decisions equal the research
replay on the same rows). The H1 leg is aggregated
from the M15 bars and the M15 leg read directly;
the app has no live M5 feed, so the M5 leg is
computed from the entry M15 bar's OHLC (the finest
live bar) -- the stored-frame verification uses the
true stored M5 windows and is exact. Check hours:
the April grid (16, 17, 18 UTC) = 22:30 / 23:30 /
00:30 MMT -- identical to cycle87j, so the install
needs no signal/prep job retiming. Sizing: carried
N = 150 (full), shipped at N/3, unchanged. April
stays best-only (second slot empty).
"""

from __future__ import annotations

import datetime as _dt
import os

import numpy as np
import pandas as pd

import core.cycle87f_best as _c87f
import core.cycle87i_best as _c87i
import core.cycle93w_best as _c93w
from core import d21rc_lib as _L
from core import rr1val_lib as _V
from core.new8_candidate import CandidateContext, ensure_m15

SYSTEM_NAME = "cycle87k"
CYCLE87K_CHECK_HOURS = _c87i.CYCLE87I_CHECK_HOURS
MAX_HOLD = 48
N_CARRIED = 150.0
N_USED = N_CARRIED / 3.0

CHECK_HOURS = (16, 17, 18)

# R108A09 fitted constants (DISC-fitted, frozen in
# the filed slate): leg scales from the incumbent
# DISC keeps, the add target, the per-band quota
# (ceil(14 / 4)) and the single fill attempt.
QH = 73.28000000000033
QM = 11.740000000000531
ADD_K = 14
QUOTA_PER_BAND = 4
FILL_ATTEMPTS = 1


def _state_path():
    from core.new8_candidate import default_state_path
    return default_state_path(SYSTEM_NAME)


def _sidecar(name):
    p = _state_path()
    return os.path.join(os.path.dirname(os.path.abspath(p)),
                        name)


def _leg_scores(h1_drift, dev, m5o, m5h, m5l, m5c,
                side, pip):
    """The research confluence legs (parts()/
    features() formulas, scales QH/QM). Scalar or
    array inputs; returns (sH, sM, sF)."""
    side = np.asarray(side, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        rng = (m5h - m5l) / pip
        body = (m5c - m5o) / pip
        loc = np.where(side > 0,
                       (m5c - m5l) / (m5h - m5l),
                       (m5h - m5c) / (m5h - m5l))
        bodyr = np.where(rng > 0, body / rng, 0.0)
    sH = np.clip(0.5 + side * h1_drift / (2 * QH), 0, 1)
    sM = np.clip(0.5 + side * dev / (2 * QM), 0, 1)
    sF = np.clip(0.5 * np.nan_to_num(loc, nan=0.5) + 0.25
                 + 0.25 * side
                 * np.nan_to_num(bodyr, nan=0.0), 0, 1)
    sH = np.nan_to_num(sH, nan=0.5)
    sM = np.nan_to_num(sM, nan=0.5)
    return sH, sM, sF


def _balanced(sH, sM, sF):
    return (np.asarray(sH, dtype=float)
            + np.asarray(sM, dtype=float)
            + np.asarray(sF, dtype=float)) / 3.0


def _ranked(score, cand_idx):
    """Indices of cand_idx sorted by score desc,
    stable (research ranked_by semantics)."""
    cand_idx = list(cand_idx)
    order = np.argsort(
        -np.asarray([score[i] for i in cand_idx],
                    dtype=float), kind="stable")
    return [cand_idx[int(j)] for j in order]


def _design_keep(rows):
    """The R108A09 selection over ledger rows (dicts
    with entry_s/exit_s/sym/net/base_keep/bal/disc):
    base kept; shield-quota adds (DISC addable rows,
    top-QUOTA_PER_BAND per shield band by balanced
    score, ranked globally, overlap fill to ADD_K);
    then the near-miss fill of every empty check slot
    (single attempt, occupancy law). Returns the keep
    mask."""
    n = len(rows)
    keep = np.zeros(n, dtype=bool)
    if n == 0:
        return keep
    entry = np.array([int(r['entry_s']) for r in rows],
                     dtype=np.int64)
    exit_ = np.array([int(r['exit_s']) for r in rows],
                     dtype=np.int64)
    sym = [str(r['sym']) for r in rows]
    base = np.array([bool(r.get('base_keep', False))
                     for r in rows], bool)
    disc = np.array([bool(r.get('disc', False))
                     for r in rows], bool)
    bal = np.array([float(r.get('bal', 0.0))
                    for r in rows], dtype=float)
    hr = (entry % 86400) // 3600
    form = np.isin(hr, list(CHECK_HOURS))
    dollar = np.array(['DOLLARIDX' in s for s in sym])
    keep = base.copy()

    def wk_of(ts):
        iso = _dt.datetime.utcfromtimestamp(
            int(ts)).isocalendar()
        return (int(iso[0]), int(iso[1]))

    def monday(wk):
        return _dt.date.fromisocalendar(wk[0], wk[1], 1)

    row_wk = [wk_of(t) for t in entry]
    wnet = {}
    for i in np.where(base & disc)[0]:
        w = row_wk[int(i)]
        wnet[w] = wnet.get(w, 0.0) + float(rows[int(i)]['net'])
    red = sorted([w for w in wnet if wnet[w] < 0],
                 key=lambda w: (wnet[w], monday(w)))
    ww = red[:3]
    wwset = set(ww)

    def sym_losses(weeks):
        acc = {}
        for i in np.where(base & disc)[0]:
            w = row_wk[int(i)]
            if w in weeks:
                key = (w, sym[int(i)])
                acc[key] = acc.get(key, 0.0) \
                    + float(rows[int(i)]['net'])
        return {s for (w, s), v in acc.items() if v < 0}

    wsym = sym_losses(wwset)
    fw = sorted({row_wk[int(i)] for i in
                 np.where(form & (~dollar) & disc)[0]})
    postset = set()
    for w in ww:
        mw = monday(w)
        later = [wk for wk in fw if monday(wk) > mw]
        if later:
            cand = min(later, key=monday)
            if cand not in wwset:
                postset.add(cand)
    inww = np.array([row_wk[i] in wwset for i in range(n)])
    symt = np.array([sym[i] in wsym for i in range(n)])
    postw = np.array([row_wk[i] in postset for i in range(n)])

    addable = form & (~dollar) & (~base)
    dadd = addable & disc
    bands = [dadd & inww,
             dadd & (~inww) & symt,
             dadd & (~inww) & (~symt) & postw,
             dadd & (~inww) & (~symt) & (~postw)]
    pool = np.zeros(n, dtype=bool)
    for band in bands:
        rk_b = _ranked(bal, np.where(band)[0])
        for i in rk_b[:QUOTA_PER_BAND]:
            pool[i] = True
    rk = _ranked(bal, np.where(pool)[0])

    taken = [(int(entry[i]), int(exit_[i]), sym[i])
             for i in np.where(keep)[0]]
    added = 0
    for i in rk:
        if added >= ADD_K:
            break
        if keep[i]:
            continue
        e, x, s = int(entry[i]), int(exit_[i]), sym[i]
        if any(s == s2 and e < x2 and e2 < x
               for (e2, x2, s2) in taken):
            continue
        taken.append((e, x, s))
        keep[i] = True
        added += 1

    # near-miss fill: every empty check slot takes
    # its nearest non-kept form row by balanced
    # score (single attempt per slot).
    slots = {}
    for i in np.where(form & (~dollar))[0]:
        slots.setdefault(int(entry[int(i)]),
                         []).append(int(i))
    occupied = {int(entry[int(i)])
                for i in np.where(keep)[0]}
    for ts in sorted(slots):
        if ts in occupied:
            continue
        cands = [i for i in slots[ts] if not keep[i]]
        if not cands:
            continue
        cands.sort(key=lambda i: (-bal[i], i))
        for i in cands[:FILL_ATTEMPTS]:
            e, x, s = int(entry[i]), int(exit_[i]), sym[i]
            if any(s == s2 and e < x2 and e2 < x
                   for (e2, x2, s2) in taken):
                continue
            taken.append((e, x, s))
            keep[i] = True
            occupied.add(ts)
            break
    return keep


def _live_legs(sym, side, entry_s, m15_frames):
    """Leg scores for one live ledger row from the
    symbol's M15 frame (the entry M15 bar stands in
    for the M5 window -- the app has no live M5
    feed). Neutral legs when bars are unavailable."""
    pip = 0.01 if 'JPY' in sym else 0.0001
    df = None
    if m15_frames and sym in m15_frames \
            and m15_frames[sym] is not None \
            and len(m15_frames[sym]):
        df = m15_frames[sym]
    if df is None:
        return 0.5, 0.5, 0.5
    try:
        tcol = next(c for c in df.columns
                    if c.lower() in ('datetime', 'time',
                                     'timestamp'))
        ts = (pd.to_datetime(df[tcol], utc=True)
              .astype('int64') // 10 ** 9).to_numpy(
                  np.int64)
        o = df['Open'].to_numpy(np.float64)
        h = df['High'].to_numpy(np.float64)
        l = df['Low'].to_numpy(np.float64)
        c = df['Close'].to_numpy(np.float64)
    except Exception:
        return 0.5, 0.5, 0.5
    j = int(np.searchsorted(ts, entry_s, side='right')) - 1
    if j < 0:
        return 0.5, 0.5, 0.5
    m15w = c[max(0, j - 7):j + 1]
    dev = (c[j] - float(np.mean(m15w))) / pip
    h1_idx = [i for i in range(j + 1)
              if ts[i] % 3600 == 2700]
    if len(h1_idx) >= 13:
        h1_drift = (c[h1_idx[-1]] - c[h1_idx[-13]]) / pip
    elif h1_idx:
        h1_drift = (c[h1_idx[-1]] - c[h1_idx[0]]) / pip
    else:
        h1_drift = 0.0
    sH, sM, sF = _leg_scores(h1_drift, dev, o[j], h[j],
                             l[j], c[j], side, pip)
    return float(sH), float(sM), float(sF)


class _Form87K:
    """A private cycle87i form whose delivered stream
    marks the reference set on the 87f panel surface;
    the snapshot is settled through the R108A09
    design rule above. Persisted: the surface
    snapshot (scalar rows), the delivered ledger and
    the processed checks."""

    def __init__(self, path=None):
        self.path = path or _state_path()
        self.i_form = _c87i._Form87I(
            path=_sidecar('cycle87k_87i.json'))
        import core.cycle87g_best as _c87g
        self.i_form.g_form = _c87g._Form87G(
            path=_sidecar('cycle87k_e04.json'))
        self.rows = []
        self.delivered = []
        self.processed = []
        self._load()

    def _load(self):
        import json
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path) as fh:
                d = json.load(fh)
        except Exception:
            return
        self.rows = d.get('rows', [])
        self.processed = d.get('processed', [])
        out = []
        for r in d.get('delivered', []):
            r = dict(r)
            for k in ('check', 'entry_time', 'exit_time'):
                if r.get(k) is not None:
                    r[k] = pd.Timestamp(r[k])
            out.append(r)
        self.delivered = out

    def save(self):
        import json
        self.i_form.save()
        if not self.path:
            return
        os.makedirs(os.path.dirname(
            os.path.abspath(self.path)), exist_ok=True)

        def ser(rows):
            out = []
            for r in rows:
                dd = dict(r)
                for k in ('check', 'entry_time',
                          'exit_time'):
                    if dd.get(k) is not None:
                        dd[k] = pd.Timestamp(
                            dd[k]).isoformat()
                out.append(dd)
            return out
        with open(self.path, 'w') as fh:
            json.dump({'system': SYSTEM_NAME,
                       'rows': self.rows,
                       'delivered': ser(self.delivered),
                       'processed': self.processed}, fh)

    def _lrow(self, r, m15_frames, base_keep):
        bars = _c93w._bars(r['symbol'], m15_frames)
        entry_s = _c93w._ts_s(r['entry_time'])
        exit_s = _c93w._ts_s(r['exit_time'])
        dirsign = 1.0 if str(r['direction']).upper() \
            .startswith('B') else -1.0
        entry_px = float(r.get('entry_px') or 0.0)
        if not entry_px:
            ts_arr = bars[0]
            j = int(np.searchsorted(ts_arr, entry_s))
            entry_px = float(bars[1][min(j, len(ts_arr) - 1)])
        prof = _L.profile_for_sym(
            r['symbol'], entry_s, exit_s, entry_px,
            dirsign, bars)
        majors = {p: _c93w._bars(p, m15_frames)
                  for p in _L.MAJORS}
        pv = _L.pip_value_per_lot(
            r['symbol'], _L.rates_at(majors, exit_s))
        if r.get('gross_pips') is not None:
            raw = float(r['gross_pips']) - _V.COST
        else:
            raw = (float(prof[-1]) if len(prof) else 0.0)
        tp = float(r['tp_pips_used'])
        sl = float(r['sl_pips_used'])
        if base_keep:
            net = raw
        else:
            net = float(_V.stop_tighten_arr(
                {'prof': [prof]}, np.array([30.0]),
                np.array([raw]))[0])
        fout = float(_V.stop_tighten_arr(
            {'prof': [prof]}, np.array([min(sl, tp)]),
            np.array([net]))[0])
        sH, sM, sF = _live_legs(str(r['symbol']), dirsign,
                                int(entry_s), m15_frames)
        year = _dt.datetime.utcfromtimestamp(
            int(entry_s)).year
        return {'entry_s': int(entry_s), 'exit_s': int(exit_s),
                'sym': str(r['symbol']),
                'side': 1 if dirsign > 0 else -1,
                'net': float(net),
                'pwv': float(prof.min()) if len(prof) else 0.0,
                'pv': float(pv), 'tp': tp, 'sl': sl,
                'fout': fout, 'base_keep': bool(base_keep),
                'bal': float(_balanced(sH, sM, sF)),
                'disc': bool(2016 <= year <= 2023),
                'key': [str(r['symbol']),
                        str(r['direction'])[:1].upper(),
                        str(r.get('strategy',
                                  r.get('equation')))],
                'payload': r}

    def step(self, frames, check_time_utc, m15_frames,
             open_symbols=()):
        chk = pd.Timestamp(check_time_utc)
        if str(chk) in self.processed:
            return [r for r in self.delivered
                    if pd.Timestamp(r['check']) == chk]
        entries = _c87f._base_entries(
            frames, check_time_utc, m15_frames, open_symbols)
        if entries is not None \
                and entries.attrs.get('status'):
            return entries
        m15map = ensure_m15(m15_frames,
                            _c87i._DESIGN_SYMBOLS)
        ctx = CandidateContext(frames, m15map,
                               _c87i.POOL_DESIGNS)
        base_rows = []
        if entries is not None and len(entries):
            for _, r in entries.iterrows():
                dd = dict(r)
                dd['check'] = chk
                if dd.get('entry_time') is None:
                    dd['entry_time'] = chk - pd.Timedelta(
                        minutes=30)
                if dd.get('exit_time') is None:
                    dd['exit_time'] = pd.Timestamp(
                        dd['entry_time']) + pd.Timedelta(
                            hours=int(dd.get('hold_h', 48)))
                if dd.get('strategy') is None:
                    dd['strategy'] = dd.get('equation')
                base_rows.append(dd)
        self.i_form.g_form.state.step(ctx, chk, base_rows)
        self.i_form.feed_new(m15_frames)
        self.i_form.save()
        base_map = {}
        for r in self.i_form.delivered:
            if pd.Timestamp(r['check']) == chk:
                base_map[(
                    str(r.get('symbol')),
                    str(r.get('direction', ''))[:1].upper(),
                    str(r.get('strategy',
                              r.get('equation'))))] = r
        new_rows = []
        if entries is not None and len(entries):
            for _, r in entries.iterrows():
                dd = dict(r)
                dd['check'] = chk
                if dd.get('entry_time') is None:
                    dd['entry_time'] = chk - pd.Timedelta(
                        minutes=30)
                if dd.get('exit_time') is None:
                    dd['exit_time'] = pd.Timestamp(
                        dd['entry_time']) + pd.Timedelta(
                            hours=int(dd.get('hold_h', 48)))
                if dd.get('strategy') is None:
                    dd['strategy'] = dd.get('equation')
                key = (str(dd['symbol']),
                       str(dd['direction'])[:1].upper(),
                       str(dd.get('strategy',
                                  dd.get('equation'))))
                if key in base_map:
                    lr = self._lrow(base_map[key],
                                    m15_frames, True)
                    src = base_map[key]
                else:
                    lr = self._lrow(dd, m15_frames, False)
                    src = dd
                lr['payload'] = {
                    k: (str(v) if isinstance(
                        v, pd.Timestamp) else v)
                    for k, v in src.items()}
                new_rows.append(lr)
        self.rows.extend(new_rows)
        keep = _design_keep(self.rows)
        out = []
        n_old = len(self.rows) - len(new_rows)
        for j, lr in enumerate(self.rows):
            if j < n_old or not keep[j]:
                continue
            dd = dict(lr['payload'])
            for k in ('check', 'entry_time', 'exit_time'):
                if isinstance(dd.get(k), str):
                    dd[k] = pd.Timestamp(dd[k])
            dd['sl_pips_used'] = min(float(dd['sl_pips_used']),
                                     float(dd['tp_pips_used']))
            self.delivered.append(dd)
            out.append(dd)
        self.processed.append(str(chk))
        self.save()
        return out


_STATE = None


def _state():
    global _STATE
    if _STATE is None:
        _STATE = _Form87K()
    return _STATE


def load_87k_state(path=None):
    if path is not None:
        return _Form87K(path=path)
    return _state()


def is_cycle87k_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE87K_CHECK_HOURS and t.minute == 30


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    form = _state()
    out = form.step(frames, check_time_utc, m15_frames,
                    open_symbols)
    if isinstance(out, pd.DataFrame):
        return out
    if not out:
        return pd.DataFrame()
    return pd.DataFrame([_c87f._signal_row(r) for r in out])


def walk_ledger():
    """The delivered cycle87k stream."""
    return [dict(r) for r in _state().delivered]


def fetch_cycle87k_m15_frames(state=None):
    return _c87i.fetch_cycle87i_m15_frames(state)


def evaluate_cycle87k_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc, m15_frames)


def select_cycle87k_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    if signals is None or not len(signals):
        return signals
    return signals
