"""Cycle 85B (C85-23 + C96-N082 + BRIEF22 C19 stack) --
February H1 system, integrated 2026-10-27 on the user's
order (two-phase update, Phase 1c).

Definition: the shipped February system cycle85 (C85-23
on the frozen C56-15 engine + C96-N082, core
.cycle85_best, frozen) plus the BRIEF22 Plan B C19 stack:
  1. C05 EURUSD price-vol veto (eligibility, fall-through):
     EURUSD candidate rows are ineligible at a check when
     volr > 1.643 (the FIT q90, frozen), where volr = M15
     Wilder ATR14 at the last completed bar before entry /
     median of M15 ATR14 over the trailing 96 M15 bars
     (lib22_feb.volr_of verbatim; price-only, stateless,
     computable from <= ~111 M15 bars).
  2. Loose score-gated dual partner (lib22_feb.walk_multi
     + run22_feb.sf_score_gate verbatim): after the
     primary pick, one partner pick -- the first remaining
     eligible row in walk (score) order on a DIFFERENT
     symbol with score >= 959 (the FIT-pool q40, frozen),
     only when the live position count after the primary
     is below the cap of 3.

Validated numbers (BRIEF22 February, @2.5): C19 = SMALL
improvement (gates pass; the audit-leftover materiality
clause missed -- the known unseen caveat) -- DISC n385
net +3,715.92, win 96.36%, leftover 76.92% (control
66.21%, +10.71); AUDIT n105 net +296.42, leftover 25.63%
(control 28.22%); LCT P 96.63% / q05 60.13% (middle +
strict). App replay EXACT against brief22 val_logs/
C19_disc.csv + C19_audit.csv -- see work_29load/
UPDATE_20261027.md. February stays best-only (the H485
second best remains fidelity-blocked, not installed).
Best N unchanged (104, as C85-23 + C96-N082).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import core.cycle85_best as _c85
from core.cycle85_best import (CYCLE85_CHECK_HOURS,
                               is_cycle85_check_time)

CYCLE85B_CHECK_HOURS = CYCLE85_CHECK_HOURS
VOLR_MAX = 1.643
PARTNER_SCORE_MIN = 959.0
PARTNER_CAP = 3

_ATR_MEMO: dict = {}


def _m15_atr14(m15: pd.DataFrame):
    """Wilder ATR14 over an M15 frame (p2lib._wilder
    verbatim: EWM alpha=1/14, adjust=False, of the true
    range with pc[0] = c[0]), memoised on a frame
    fingerprint. Returns (timestamps, atr) numpy arrays."""
    idx = pd.to_datetime(m15.index)
    key = (len(m15), idx[0], idx[-1],
           float(m15["Close"].sum()))
    got = _ATR_MEMO.get(key)
    if got is not None:
        return got
    c = m15["Close"].to_numpy(dtype=float)
    h = m15["High"].to_numpy(dtype=float)
    lo = m15["Low"].to_numpy(dtype=float)
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - lo, np.maximum(np.abs(h - pc),
                                       np.abs(lo - pc)))
    atr = pd.Series(tr).ewm(alpha=1.0 / 14, adjust=False) \
        .mean().to_numpy()
    got = (idx.to_numpy(), atr)
    if len(_ATR_MEMO) > 32:
        _ATR_MEMO.clear()
    _ATR_MEMO[key] = got
    return got


def volr_eurusd(m15_frames, check_time_utc) -> float:
    """The C05 volr for EURUSD at one check (lib22_feb
    .volr_of verbatim): b0 = the M15 entry bar (check -
    30min); now = atr[b0-1]; med = median(atr[b0-97:b0-1]);
    NaN when not computable (row not vetoed)."""
    m15 = (m15_frames or {}).get("EURUSD")
    if m15 is None or len(m15) == 0:
        return float("nan")
    ts, atr = _m15_atr14(m15)
    ent = (pd.Timestamp(check_time_utc)
           - pd.Timedelta(minutes=30)).value
    b0 = int(np.searchsorted(ts.astype("datetime64[ns]")
                             .astype(np.int64), ent))
    if b0 < 100 or b0 - 1 >= len(atr):
        return float("nan")
    now = float(atr[b0 - 1])
    med = float(np.median(atr[b0 - 97:b0 - 1]))
    return now / med if med > 0 else float("nan")


def _eurusd_m15(m15_frames):
    if m15_frames is not None and "EURUSD" in m15_frames:
        return m15_frames
    try:
        from core.cycle78_best import fetch_cycle78_m15_frames
        got = fetch_cycle78_m15_frames(symbols=("EURUSD",))
        if got:
            out = dict(m15_frames or {})
            out.update(got)
            return out
    except Exception:
        pass
    return m15_frames


def _m15_for(m15_frames, sym):
    if m15_frames is not None and sym in m15_frames:
        return m15_frames
    try:
        from core.cycle78_best import fetch_cycle78_m15_frames
        got = fetch_cycle78_m15_frames(symbols=(sym,))
        if got:
            out = dict(m15_frames or {})
            out.update(got)
            return out
    except Exception:
        pass
    return m15_frames


def _primary_counts_live(row, m15_frames) -> bool:
    """Whether the primary pick still counts as live AFTER
    its entry for the partner cap -- walk_multi's live_after
    filter (exit_time > entry time) applied to the primary
    itself. A primary whose barrier is touched within its
    first M15 entry bar exits AT the entry time (the pool
    sim's bar-start stamp) and does not count. Judged on
    the primary symbol's M15 entry bar, the same basis the
    research sim used; missing M15 -> counts as live (the
    conservative fallback)."""
    from core.cycle56_best import _pip_size
    sym = str(row["symbol"])
    m15 = (m15_frames or {}).get(sym)
    if m15 is None or len(m15) == 0:
        return True
    ent = pd.Timestamp(row["entry_candle"])
    pos = m15.index.get_indexer([ent])[0]
    if pos < 0:
        return True
    bar = m15.iloc[pos]
    pip = _pip_size(sym)
    entry = float(row["entry_px"])
    tp = float(row["tp_pips"]) * pip
    sl = float(row["sl_pips"]) * pip
    if str(row["direction"]) == "BUY":
        touched = float(bar["High"]) >= entry + tp \
            or float(bar["Low"]) <= entry - sl
    else:
        touched = float(bar["Low"]) <= entry - tp \
            or float(bar["High"]) >= entry + sl
    return not touched


def evaluate_cycle85b_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the frozen cycle85 signals (the layer
    is pure H1; M15 enters only through the C05 veto in
    selection)."""
    return _c85.evaluate_cycle85_signals(
        frames, check_time_utc, m15_frames=m15_frames)


def select_cycle85b_entries(signals: pd.DataFrame,
                            open_symbols=(),
                            live_count: int = 0,
                            m15_frames: dict | None = None,
                            check_time_utc=None) -> pd.DataFrame:
    """C19 selection: C05 veto (fall-through) -> frozen
    C85 primary pick -> score-gated dual partner.

    live_count = positions open at the entry time BEFORE
    this check's picks (the router's convention, as for
    cycle60b's dual: the count of distinct open symbols).
    The partner fires only when the live count AFTER the
    primary (walk_multi's live_after: the primary counts
    only when its exit is after the entry time) is below
    the cap of 3."""
    if signals is None or len(signals) == 0:
        return signals.iloc[0:0] if signals is not None \
            else pd.DataFrame()
    chk = check_time_utc
    if chk is None and "entry_candle" in signals.columns:
        chk = pd.Timestamp(signals["entry_candle"].iloc[0]) \
            + pd.Timedelta(minutes=30)
    sig = signals
    if chk is not None:
        v = volr_eurusd(_eurusd_m15(m15_frames), chk)
        if np.isfinite(v) and v > VOLR_MAX:
            sig = sig[sig["symbol"] != "EURUSD"]
            if len(sig) == 0:
                return sig.iloc[0:0]
    primary = _c85.select_cycle85_entries(
        sig, open_symbols=open_symbols)
    if primary is None or len(primary) == 0:
        return primary if primary is not None \
            else pd.DataFrame()
    prow = primary.iloc[0]
    m15f = _m15_for(m15_frames, str(prow["symbol"]))
    live_after = live_count + (1 if _primary_counts_live(
        prow, m15f) else 0)
    if live_after >= PARTNER_CAP:
        return primary
    held = {str(s).upper() for s in (open_symbols or ())}
    psym = str(primary["symbol"].iloc[0]).upper()
    ranked = sig.sort_values("score", ascending=False,
                             kind="mergesort")
    for _, row in ranked.iterrows():
        sym = str(row["symbol"]).upper()
        if sym == psym or sym in held:
            continue
        if float(row["score"]) >= PARTNER_SCORE_MIN:
            return pd.concat([primary, row.to_frame().T],
                             ignore_index=True)
    return primary


def is_cycle85b_check_time(ts) -> bool:
    return is_cycle85_check_time(ts)
