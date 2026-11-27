"""Shared, bounded data acquisition for monthly check panels.

Only actual provider bars are stored in SQLite. A partial H1 assembled from M15
is kept in session memory, never as completed H1 history. Its opening price is
used only when the exact hour-start M15 bar exists; there is no quote/ffill path.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
import time

import numpy as np
import pandas as pd

H1_MEMO_KEY = "check_h1_memo_20261027"
M15_MEMO_KEY = "check_m15_memo_20261027"
M5_MEMO_KEY = "check_m5_memo_20261116"
RETRY_SECONDS = 15.0
SUCCESS_SECONDS = 60.0
FETCH_BUDGET_SECONDS = 20.0
# Extra bounded budget for the Twelve Data fallback route
# (user order 2026-11-27): when the repository + Dukascopy
# route cannot serve a symbol/window, the check path may fill
# it from Twelve Data before declaring the window incomplete.
TWELVE_FALLBACK_BUDGET_SECONDS = 90.0
# Deep-history sufficiency for the M15 route. The 1600-bar figure
# was a Twelve Data-era heuristic (one API call returned 2000
# bars); the designs' true needs are far smaller -- 32-bar slot
# features and 48 h / 192-bar pending resolution, with the
# persisted cycle state carrying the rest -- and the Dukascopy
# feed assembles 10 days (~840 M15 bars) per symbol. 400 bars
# (~4.8 trading days) is the floor at which a frame counts as
# deep enough that only the missing tail is fetched.
MIN_DEEP_BARS = 400


def utc_naive(value):
    ts = pd.Timestamp(value)
    return ts.tz_convert("UTC").tz_localize(None) if ts.tzinfo else ts


def normalize_ohlc(frame, min_bars=1):
    """Accept repository, direct-provider, and already-indexed frames."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    out = frame.copy()
    out = out.loc[:, ~out.columns.duplicated(keep="last")]
    names = {str(c).lower(): c for c in out.columns}
    tc = next((names[c] for c in ("time", "open_time", "datetime", "timestamp", "date")
               if c in names), None)
    if tc is not None:
        idx = pd.to_datetime(out.pop(tc), utc=True, errors="coerce")
    elif isinstance(out.index, pd.DatetimeIndex):
        idx = pd.to_datetime(out.index, utc=True, errors="coerce")
    else:
        return None
    out.index = pd.DatetimeIndex(idx).tz_localize(None)
    out = out.rename(columns={c: str(c).title() for c in out.columns
                              if str(c).lower() in ("open", "high", "low", "close", "volume")})
    required = ["Open", "High", "Low", "Close"]
    if not set(required).issubset(out.columns):
        return None
    out[required] = out[required].apply(pd.to_numeric, errors="coerce")
    if "Volume" in out.columns:
        # Twelve wire values carry volume as a string; left
        # unconverted it later breaks the M5->M15 assembly
        # (seg["Volume"].sum() concatenates strings and the
        # float() raises — found by the 2026-11-27 Nov-2025
        # memory-build fix test). Numeric volume is a no-op
        # for repository frames.
        out["Volume"] = pd.to_numeric(out["Volume"],
                                      errors="coerce")
    values = out[required].to_numpy(dtype=float)
    valid = np.isfinite(values).all(axis=1) & (values > 0).all(axis=1)
    valid &= (out.High >= out[["Open", "Close"]].max(axis=1)).to_numpy()
    valid &= (out.Low <= out[["Open", "Close"]].min(axis=1)).to_numpy()
    out = out.loc[valid & ~out.index.isna()].sort_index(kind="stable")
    out = out.loc[~out.index.duplicated(keep="last")]
    return out if len(out) >= min_bars else None


def entry_candle_from_m15(frame, entry, *, asof=None):
    """Exact M15 hour-open; no later-hour or missing-first-bar substitution.

    A historical completed hour requires all four quarter-hours. For a forming
    hour only contiguous, available quarters are used. Signal features always
    come from the preceding completed H1, as required by the monthly engines.
    """
    entry = utc_naive(entry)
    now = utc_naive(asof if asof is not None else pd.Timestamp.now(tz="UTC"))
    if entry != entry.floor("h") or entry > now:
        return None
    data = normalize_ohlc(frame)
    if data is None:
        return None
    end = min(entry + pd.Timedelta(minutes=45), now.floor("15min"))
    required = pd.date_range(entry, end, freq="15min")
    if now < entry + pd.Timedelta(hours=1):
        # The entry OPEN is already exact when only the first quarter has
        # published. Keep the available contiguous prefix of this forming
        # hour; do not wait for later quarters to obtain an unchanged open.
        available = []
        for stamp in required:
            if stamp not in data.index:
                break
            available.append(stamp)
        required = pd.DatetimeIndex(available)
    if len(required) == 0 or not set(required).issubset(data.index):
        return None
    part = data.loc[required]
    row = pd.DataFrame([dict(Open=float(part.Open.iloc[0]), High=float(part.High.max()),
                             Low=float(part.Low.min()), Close=float(part.Close.iloc[-1]))],
                       index=pd.DatetimeIndex([entry]))
    row.attrs["entry_source"] = "DUKASCOPY_M15_HOUR_OPEN"
    row.attrs["is_partial_hour"] = now < entry + pd.Timedelta(hours=1)
    return row


def _repository():
    try:
        from core.data.candle_repository import CandleRepository
        return CandleRepository()
    except Exception:
        return None


def _persist_real(repo, raw, sym, tf, errors):
    if repo is None:
        return
    try:
        from core.data.candle_repository import normalize_frame
        normalized = normalize_frame(raw, symbol=sym, timeframe=tf, provider="DUKASCOPY")
        # Only complete real candles; partial H1 fallback never enters this path.
        normalized = normalized.loc[normalized.is_complete]
        repo.upsert(normalized, require_complete=True)
    except Exception as exc:
        errors.append(f"{sym} {tf}: cache write {type(exc).__name__}")


def _bar_key(frame):
    """Bar-open timestamps of a raw repository frame, for per-bar dedup."""
    names = {str(c).lower(): c for c in frame.columns}
    for cand in ("open_time", "time", "datetime", "timestamp", "date"):
        if cand in names:
            return pd.to_datetime(frame[names[cand]], utc=True, errors="coerce")
    if isinstance(frame.index, pd.DatetimeIndex):
        return pd.Series(pd.to_datetime(frame.index, utc=True), index=frame.index)
    return None


def _dukascopy_rows(raw):
    """Repository rows for the signal path: Dukascopy first, Twelve
    fallback only where Dukascopy has no row for that bar.

    The repository is a shared cache; rows persisted by the old
    Twelve Data route (or any other provider) must never enter a
    check / precheck evaluation (user order 2026-11-16: same
    candles as the chain, no silent substitution). AMENDED by user
    decision 2026-11-25 19:56 MMT: a TWELVE_DATA row tagged
    source_status=FALLBACK_TWELVE (written by twelve_fill.py) may
    fill a bar ONLY when no Dukascopy row exists for that bar;
    Dukascopy always wins where present. Rows without a provider
    tag are excluded -- the safe direction.

    The returned frame carries attrs["data_basis"] ("fallback" if
    any fallback row was admitted, else "dukascopy") and
    attrs["fallback_bars"], so the read layer can label any result
    computed with fallback rows as "fallback data".
    """
    if raw is None or not isinstance(raw, pd.DataFrame) or raw.empty:
        return raw
    if "provider" not in raw.columns:
        return raw.iloc[0:0]
    prov = raw["provider"].astype(str).str.upper()
    is_duka = prov == "DUKASCOPY"
    is_fallback = prov == "TWELVE_DATA"
    if "source_status" in raw.columns:
        is_fallback &= (raw["source_status"].astype(str).str.upper()
                        == "FALLBACK_TWELVE")
    out = raw.loc[is_duka | is_fallback].copy()
    if len(out):
        key = _bar_key(out)
        if key is not None:
            pri = pd.Series(np.where(is_duka.loc[out.index], 0, 1),
                            index=out.index)
            tmp = out.assign(_bk=key.values, _pri=pri.values)
            tmp = tmp.sort_values(["_bk", "_pri"], kind="stable")
            out = tmp.drop_duplicates(subset=["_bk"], keep="first")
            out = out.drop(columns=["_bk", "_pri"])
    n_fb = int(is_fallback.loc[out.index].sum()) if len(out) else 0
    out.attrs["data_basis"] = "fallback" if n_fb else "dukascopy"
    out.attrs["fallback_bars"] = n_fb
    return out


def _direct_fetch(state, symbols, tf, *, deadline, force=False):
    """Evaluation candles from the Dukascopy tick feed (user order
    2026-11-16 21:51 MMT -- the app must suggest like Everest's
    chain, which reads Dukascopy only).

    Same contract as the Twelve Data route this replaces: return
    (frames, errors) by the page budget even if a download hangs;
    every failure is named per symbol. The feed (core/
    dukascopy_feed.py) downloads .bi5 tick hours keylessly,
    aggregates BID M5/M15/H1, caches the assembly in `state`
    across the window's refreshes (tail-only after the first
    assembly), and hard-stops the whole refresh on a 429/503,
    mirroring the chain's rate-limit law. No Twelve Data candles
    enter an evaluation through this route anymore.
    """
    if not symbols:
        return {}, []
    from core.dukascopy_feed import fetch_frames
    return fetch_frames(state, symbols, tf, deadline=deadline,
                        force=force)


def _twelve_fetch(state, symbols, tf, *, end_ts, deadline=None):
    """Twelve Data fallback frames for the check route (user
    order 2026-11-27).

    Dukascopy stays primary: this route is consulted ONLY for
    symbols/windows the repository + Dukascopy route could not
    serve. It mirrors the Replay section's Twelve loader
    (core/replay_section): the same key pool
    (TwelveDataKeyPool.from_state), the same window request,
    the same normalize_ohlc normalization, frames truncated to
    bars starting at or before end_ts. Returned frames are
    normalized; callers merge them UNDER any existing bars
    (existing bars win shared stamps, so a Twelve bar only ever
    fills a gap). Frames carry the replay loader's own basis
    attrs; the fetch functions additionally mark the read
    "fallback" in their diag / basis bookkeeping so the UI can
    label the result "fallback data". Never raises: failures
    come back as per-symbol error notes and the caller keeps
    the honest DATA ERROR gate (28/28 or DATA ERROR).
    """
    frames, errors = {}, []
    if not symbols:
        return frames, errors
    try:
        from core import replay_section as _rs
        pool = _rs._twelve_pool(state)
    except Exception as exc:
        return frames, [f"Twelve Data fallback unavailable: "
                        f"{type(exc).__name__}: {exc}"]
    prev_wait = _rs._TWELVE_WAIT_LIMIT_S
    try:
        for sym in symbols:
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    errors.append(
                        f"{sym} {tf}: Twelve Data fallback "
                        f"skipped (budget exhausted)")
                    continue
                # Bound the pool's per-request wait by the
                # budget this route was given.
                _rs._TWELVE_WAIT_LIMIT_S = max(
                    5.0, min(prev_wait, remaining))
            try:
                frame = _rs._twelve_frame(pool, sym, tf,
                                          utc_naive(end_ts),
                                          errors)
            except Exception as exc:
                frame = None
                errors.append(f"{sym} {tf}: Twelve Data fallback "
                              f"{type(exc).__name__}: {exc}")
            if frame is not None:
                frames[sym] = frame
    finally:
        _rs._TWELVE_WAIT_LIMIT_S = prev_wait
    return frames, errors


def _assemble_m15_from_m5_frame(m5_frame, frame, required):
    """Assemble missing M15 bars from a supplied M5 frame
    (gaps only), the same math as _assemble_m15_gaps but with
    the M5 bars coming from the Twelve fallback instead of the
    repository: open=first open, high=max, low=min, close=last
    close, volume=sum. A stamp already in the frame is never
    touched. Returns (frame, n_assembled)."""
    if m5_frame is None or frame is None or len(frame) == 0:
        return frame, 0
    m5 = normalize_ohlc(m5_frame)
    if m5 is None:
        return frame, 0
    grid = pd.date_range(frame.index.min(), utc_naive(required),
                         freq="15min")
    rows = {}
    for st in grid:
        if st in frame.index:
            continue
        part_idx = pd.date_range(st, periods=3, freq="5min")
        if not part_idx.isin(m5.index).all():
            continue
        part = m5.loc[part_idx]
        row = dict(Open=float(part.Open.iloc[0]),
                   High=float(part.High.max()),
                   Low=float(part.Low.min()),
                   Close=float(part.Close.iloc[-1]))
        if "Volume" in m5.columns:
            row["Volume"] = float(part.Volume.sum())
        rows[st] = row
    if not rows:
        return frame, 0
    add = pd.DataFrame.from_dict(rows, orient="index")
    add.index = pd.DatetimeIndex(add.index)
    return _merge(frame, add, 5000), len(rows)


def _record_load_status(state, tf, frames, requested=()):
    """Honest per-field load status (user order 2026-11-16).

    Records into state["check_data_load_status"][tf][symbol] what
    the data layer could and could not load, judged from the actual
    frames used, so the check/precheck views can SHOW a load failure
    instead of silently presenting a signal next to substituted
    data. Fields tracked: "candles" ("cannot_load" for a requested
    symbol that returned no frame) and "volume" ("cannot_load" when
    the frame has no Volume column or every value is 0/NaN --
    a provider that returns no volume for FX fills a missing
    column with 0, so an all-zero column means volume did NOT
    load; it is not real zero volume. Dukascopy frames carry real
    tick volume and report "loaded"). A frame whose volume has
    any positive value (e.g. a repository frame with real volume)
    reports "loaded". Never raises; never changes any frame.
    """
    try:
        if not isinstance(state, dict):
            return
        book = state.setdefault("check_data_load_status", {})
        if not isinstance(book, dict):
            return
        slot = book.setdefault(tf, {})
        frames = frames or {}
        for sym in requested or ():
            if sym not in frames:
                slot[sym] = {"candles": "cannot_load"}
        for sym, frame in frames.items():
            entry = dict(slot.get(sym) or {})
            entry["candles"] = "loaded"
            vol = "cannot_load"
            try:
                if frame is not None and "Volume" in frame.columns:
                    vals = pd.to_numeric(frame["Volume"], errors="coerce")
                    if bool((vals.fillna(0) > 0).any()):
                        vol = "loaded"
            except Exception:
                vol = "cannot_load"
            entry["volume"] = vol
            slot[sym] = entry
    except Exception:
        pass


def _merge(old, new, limit=400):
    if old is None:
        return new.tail(limit) if new is not None else None
    if new is None:
        return old
    out = pd.concat([old, new])
    return out.loc[~out.index.duplicated(keep="last")].sort_index().tail(limit)


def fetch_check_frames(state, symbols, need_candles=None):
    """Return normalized H1, latest timestamp, and honest per-window readiness."""
    symbols = tuple(symbols)
    need = {utc_naive(c) for c in (() if need_candles is None else need_candles)}
    key = (symbols, tuple(sorted(need)))
    now_mono = time.monotonic()
    force = bool(state.pop("force_signal_refresh", False))
    memo = state.get(H1_MEMO_KEY)
    if not force and isinstance(memo, dict) and memo.get("key") == key:
        ttl = SUCCESS_SECONDS if memo["result"][2]["ready"] == len(symbols) else RETRY_SECONDS
        if now_mono - memo["at"] < ttl:
            return memo["result"]
    if force:
        state.pop(M15_MEMO_KEY, None)
    frames, errors, sources = {}, [], {}
    repo = _repository()
    h1_fallback = False
    for sym in symbols:
        try:
            sel = _dukascopy_rows(repo.load(sym, "H1", limit=400, completed_only=False)) if repo else None
            if sel is not None and getattr(sel, "attrs", {}).get("data_basis") == "fallback":
                h1_fallback = True
            frame = normalize_ohlc(sel, 50)
        except Exception as exc:
            frame = None
            errors.append(f"{sym} H1: cache read {type(exc).__name__}")
        if frame is not None:
            frames[sym] = frame
            sources[sym] = "H1 cache"
    deadline = time.monotonic() + FETCH_BUDGET_SECONDS
    entry = max(need) if need else None
    previous = need - {entry}
    # The common boundary case: completed H1 history exists, only the new
    # entry bar is absent. Go DIRECTLY to M15; do not exhaust keys on late H1.
    only_entry = [s for s in symbols if need and s in frames
                  and entry not in frames[s].index and previous.issubset(frames[s].index)]
    # REPO-FIRST (user order 2026-11-25 21:59 MMT): the live fetch
    # may only fill symbols whose STORED frame lacks the needed
    # candles; a refresh must never re-fetch (and thereby risk
    # discarding) bars the store already holds, so `force` no
    # longer widens the target list.
    h1_targets = [s for s in symbols if s not in frames
                  or (need and not need.issubset(frames[s].index) and s not in only_entry)]
    if h1_targets:
        raw_frames, notes = _direct_fetch(state, h1_targets, "H1", deadline=deadline, force=force)
        errors.extend(notes)
        for sym, raw in raw_frames.items():
            norm = normalize_ohlc(raw, 1)
            merged = _merge(frames.get(sym), norm)
            if merged is not None and len(merged) >= 50:
                frames[sym] = merged
                sources[sym] = "H1 direct"
            _persist_real(repo, raw, sym, "H1", errors)
    synth_targets = [s for s in symbols if need and s in frames
                     and entry not in frames[s].index and previous.issubset(frames[s].index)]
    if synth_targets:
        m15 = fetch_m15_frames(state, synth_targets, deadline=deadline, need_entry=entry, force=force)
        errors.extend(state.get("check_m15_last_errors", []))
        for sym in synth_targets:
            row = entry_candle_from_m15(m15.get(sym), entry)
            if row is not None:
                frames[sym] = _merge(frames[sym], row)
                sources[sym] = "M15 exact hour-open"
            else:
                errors.append(f"{sym}: exact M15 hour-start candle unavailable")
    # Twelve Data fallback (user order 2026-11-27): any symbol
    # the repository + Dukascopy route still cannot serve --
    # no frame at all, or a needed candle missing -- gets its
    # H1 window from Twelve Data (the Replay section's route).
    # Merged UNDER the existing frame: bars already held always
    # win a shared stamp, so Twelve only fills gaps. The gate
    # below is unchanged: 28/28 or DATA ERROR.
    fb_targets = [s for s in symbols if s not in frames
                  or (need and not need.issubset(frames[s].index))]
    if fb_targets:
        fb_end = entry if entry is not None else utc_naive(
            pd.Timestamp.now(tz="UTC")).floor("h")
        fb_frames, fb_notes = _twelve_fetch(
            state, fb_targets, "H1", end_ts=fb_end,
            deadline=time.monotonic() + TWELVE_FALLBACK_BUDGET_SECONDS)
        errors.extend(fb_notes)
        for sym, raw in fb_frames.items():
            norm = normalize_ohlc(raw, 1)
            if norm is None:
                continue
            merged = _merge(norm, frames.get(sym))
            if merged is not None and len(merged) >= 50:
                frames[sym] = merged
                sources[sym] = "H1 twelve fallback"
                h1_fallback = True
    ready_symbols = [s for s in symbols if s in frames
                     and (not need or need.issubset(frames[s].index))]
    latest = max((f.index.max() for f in frames.values()), default=None)
    _sb = state.get("check_data_basis")
    data_basis = ("assembled" if _sb == "assembled"
                  else "fallback" if (h1_fallback or _sb == "fallback")
                  else "dukascopy")
    if data_basis != "dukascopy":
        state["check_data_basis"] = data_basis
    diag = dict(cache=sum(v == "H1 cache" for v in sources.values()),
                live=sum(v != "H1 cache" for v in sources.values()), frames=len(frames),
                ready=len(ready_symbols), required=len(symbols),
                missing_symbols=[s for s in symbols if s not in ready_symbols],
                entry_sources=sources, live_errors=errors[:8],
                data_basis=data_basis)
    _record_load_status(state, "H1", frames, symbols)
    result = frames, latest, diag
    state[H1_MEMO_KEY] = dict(key=key, at=time.monotonic(), result=result)
    return result


_ASSEMBLY_OK = None


def _assembly_selfcheck(repo):
    """Gate (a) for Gate Amendment No.2 (user order 2026-11-25
    21:59 MMT), inside the live path: assemble M15 bars from
    stored M5 on an hour where real M15 exists and compare EVERY
    OHLC field. Assembly is enabled only if the comparison is
    exact; the result is cached per process. If no testable hour
    exists, assembly stays OFF (cannot prove = do not use)."""
    global _ASSEMBLY_OK
    if _ASSEMBLY_OK is not None:
        return _ASSEMBLY_OK
    _ASSEMBLY_OK = False
    try:
        for sym in ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
                    "EURGBP", "AUDNZD"):
            # The comparison target must be DUKASCOPY M15 bars:
            # assembly reproduces the Dukascopy aggregation, and
            # Twelve fallback bars legitimately differ from it
            # (C1 finding) — comparing against them would refuse
            # a sound method.
            raw15 = repo.load(sym, "M15", limit=200,
                              completed_only=False)
            if raw15 is not None and "provider" in raw15.columns:
                raw15 = raw15.loc[
                    raw15["provider"].astype(str).str.upper()
                    == "DUKASCOPY"]
            m15 = normalize_ohlc(raw15)
            m5 = normalize_ohlc(_dukascopy_rows(
                repo.load(sym, "M5", limit=2400, completed_only=False)))
            if m15 is None or m5 is None or len(m15) < 4:
                continue
            hours = sorted({t.floor("h") for t in m15.index},
                           reverse=True)
            for h in hours[:6]:
                stamps = pd.date_range(h, periods=4, freq="15min")
                m5stamps = pd.date_range(h, periods=12, freq="5min")
                if not stamps.isin(m15.index).all() \
                        or not m5stamps.isin(m5.index).all():
                    continue
                ok = True
                for st in stamps:
                    part = m5.loc[pd.date_range(st, periods=3,
                                                freq="5min")]
                    asm = (float(part.Open.iloc[0]),
                           float(part.High.max()),
                           float(part.Low.min()),
                           float(part.Close.iloc[-1]))
                    real = m15.loc[st]
                    if asm != (float(real.Open), float(real.High),
                               float(real.Low), float(real.Close)):
                        ok = False
                        break
                _ASSEMBLY_OK = bool(ok)
                return _ASSEMBLY_OK
    except Exception:
        _ASSEMBLY_OK = False
    return _ASSEMBLY_OK


def _assemble_m15_gaps(repo, sym, frame, required):
    """Gate Amendment No.2: fill MISSING M15 stamps in `frame`
    from stored M5 bars (open=first open, high=max, low=min,
    close=last close, volume=sum). GAPS ONLY — a stamp already
    in the frame is never touched, so precedence Dukascopy M15 >
    Twelve fallback M15 > assembled-from-M5 holds by
    construction. Returns (frame, n_assembled)."""
    if frame is None or repo is None or len(frame) == 0:
        return frame, 0
    try:
        m5 = normalize_ohlc(_dukascopy_rows(
            repo.load(sym, "M5", limit=6000, completed_only=False)))
        if m5 is None:
            return frame, 0
        grid = pd.date_range(frame.index.min(), required,
                             freq="15min")
        rows = {}
        for st in grid:
            if st in frame.index:
                continue
            part_idx = pd.date_range(st, periods=3, freq="5min")
            if not part_idx.isin(m5.index).all():
                continue
            part = m5.loc[part_idx]
            row = dict(Open=float(part.Open.iloc[0]),
                       High=float(part.High.max()),
                       Low=float(part.Low.min()),
                       Close=float(part.Close.iloc[-1]))
            if "Volume" in m5.columns:
                row["Volume"] = float(part.Volume.sum())
            rows[st] = row
        if not rows:
            return frame, 0
        add = pd.DataFrame.from_dict(rows, orient="index")
        add.index = pd.DatetimeIndex(add.index)
        return _merge(frame, add, 5000), len(rows)
    except Exception:
        return frame, 0


def fetch_m15_frames(state, symbols, *, deadline=None, need_entry=None, force=False):
    """Deep, current M15 shared by the entry fallback and all M15 B systems."""
    symbols = tuple(symbols)
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    required = utc_naive(need_entry) if need_entry is not None else now.floor("15min") - pd.Timedelta(minutes=15)
    memo = state.setdefault(M15_MEMO_KEY, {})
    frames, missing, errors = {}, [], []
    basis = {}
    repo = _repository()
    for sym in symbols:
        cached = memo.get(sym)
        frame = cached.get("frame") if isinstance(cached, dict) else None
        sym_basis = cached.get("data_basis") if isinstance(cached, dict) else None
        sufficient = frame is not None and required in frame.index and (need_entry is not None or len(frame) >= MIN_DEEP_BARS)
        if force or not sufficient:
            try:
                raw = _dukascopy_rows(repo.load(sym, "M15", limit=2000, completed_only=False)) if repo else None
                if raw is not None and getattr(raw, "attrs", {}).get("data_basis") == "fallback":
                    sym_basis = "fallback"
                frame = _merge(frame, normalize_ohlc(raw), 5000)
            except Exception:
                pass
        basis[sym] = sym_basis or "dukascopy"
        sufficient = frame is not None and required in frame.index and (need_entry is not None or len(frame) >= MIN_DEEP_BARS)
        if frame is not None:
            frames[sym] = frame
        failed_recently = (isinstance(cached, dict) and cached.get("required") == required
                           and time.monotonic() - cached.get("attempt", 0) < RETRY_SECONDS)
        # REPO-FIRST (user order 2026-11-25 21:59 MMT): live fetch
        # only for symbols whose stored frame is insufficient.
        if not sufficient and not failed_recently:
            missing.append(sym)
    if missing:
        deadline = deadline if deadline is not None else time.monotonic() + FETCH_BUDGET_SECONDS
        raw_frames, errors = _direct_fetch(state, missing, "M15", deadline=deadline, force=force)
        for sym in missing:
            norm = normalize_ohlc(raw_frames.get(sym))
            frame = _merge(frames.get(sym), norm, 5000)
            if frame is not None:
                frames[sym] = frame
            memo[sym] = dict(frame=frame, attempt=time.monotonic(), required=required,
                             data_basis=basis.get(sym, "dukascopy"))
            if sym in raw_frames:
                _persist_real(repo, raw_frames[sym], sym, "M15", errors)
    # Twelve Data fallback (user order 2026-11-27): symbols
    # whose M15 frame is still insufficient after the
    # repository + Dukascopy route get the window from Twelve
    # Data (the Replay section's route), merged UNDER existing
    # bars (existing bars win shared stamps). Remaining gaps
    # in the window are then assembled from Twelve M5 bars,
    # gaps only, exactly as the Replay route does; a frame
    # completed either way is marked basis "fallback" /
    # "assembled" so the read is labelled.
    fb_missing = []
    for sym in symbols:
        frame = frames.get(sym)
        ok = frame is not None and required in frame.index \
            and (need_entry is not None or len(frame) >= MIN_DEEP_BARS)
        if not ok:
            fb_missing.append(sym)
    if fb_missing:
        fb_frames, fb_errors = _twelve_fetch(
            state, fb_missing, "M15", end_ts=required,
            deadline=time.monotonic() + TWELVE_FALLBACK_BUDGET_SECONDS)
        errors.extend(fb_errors)
        still = []
        for sym in fb_missing:
            raw = fb_frames.get(sym)
            if raw is not None:
                norm = normalize_ohlc(raw)
                if norm is not None:
                    frame = _merge(norm, frames.get(sym), 5000)
                    if frame is not None:
                        frames[sym] = frame
                        basis[sym] = "fallback"
                        memo[sym] = dict(
                            frame=frame, attempt=time.monotonic(),
                            required=required, data_basis="fallback")
            frame = frames.get(sym)
            ok = frame is not None and required in frame.index \
                and (need_entry is not None or len(frame) >= MIN_DEEP_BARS)
            if not ok:
                still.append(sym)
        if still:
            m5_frames, m5_errors = _twelve_fetch(
                state, still, "M5", end_ts=required,
                deadline=time.monotonic()
                + TWELVE_FALLBACK_BUDGET_SECONDS)
            errors.extend(m5_errors)
            for sym in still:
                if sym not in m5_frames:
                    continue
                filled, n_asm = _assemble_m15_from_m5_frame(
                    m5_frames[sym], frames.get(sym), required)
                if n_asm:
                    frames[sym] = filled
                    basis[sym] = "assembled"
                    memo[sym] = dict(
                        frame=filled, attempt=time.monotonic(),
                        required=required, data_basis="assembled")
    # Gate Amendment No.2 (user order 2026-11-25 21:59 MMT):
    # assemble any still-missing M15 bars from stored M5 — gaps
    # only, after the exactness self-check inside this path.
    if repo is not None and _assembly_selfcheck(repo):
        for sym in list(frames.keys()):
            filled, n_asm = _assemble_m15_gaps(
                repo, sym, frames[sym], required)
            if n_asm:
                frames[sym] = filled
                basis[sym] = "assembled"
                memo[sym] = dict(frame=filled,
                                 attempt=time.monotonic(),
                                 required=required,
                                 data_basis="assembled")
    state["check_m15_last_errors"] = errors
    if any(basis.get(s) == "assembled" for s in frames):
        state["check_data_basis"] = "assembled"
    elif any(basis.get(s) == "fallback" for s in frames):
        state["check_data_basis"] = "fallback"
    _record_load_status(state, "M15", frames, symbols)
    # 2026-11-16 repair (app migration): the ported cycle modules
    # convert frames through _bars_from_frame, which reads the time
    # from a "Datetime" COLUMN; normalized frames carry the time only
    # in the index, so every module silently received zero bars
    # through this route and no M15-driven panel could ever fire.
    # Return copies that carry the time as a column as well (index
    # kept). Internal consumers are unaffected: the entry-candle
    # synthesis re-normalizes its input, which pops a time column
    # straight back into the index.
    out = {}
    for _sym, _f in frames.items():
        try:
            _o = _f.assign(Datetime=_f.index)
        except Exception:
            _o = _f
        _o.attrs["data_basis"] = basis.get(_sym, "dukascopy")
        out[_sym] = _o
    return out


M15_SLOT_WINDOW_BARS = 32    # _slot_rows: entry bar + the 31 bars before it
M15_FORWARD_BARS = 192       # _trade_outcome: 48 h hold cap on M15


def m15_window_complete(frame, check_ts):
    """True when one symbol's M15 frame holds the full data a
    check-slot evaluation consumes (2026-11-25 gate fix; see
    GATE_FIX_20261125.md / FULLWAY_DIAGNOSIS_20261125.md).

    Per symbol the evaluation (cycle93aj _slot_rows /
    _trade_outcome) reads: the entry bar (the M15 bar opening
    at check - 15m), the 32-bar window ending at that bar
    (pos32 / ATR14 read bars idx-31..idx), and the 48h forward
    window -- the 192 M15 bars after the entry bar -- to
    resolve exits. The old readiness gate counted only two
    H1 candles, so slots stepped with these windows missing
    or shifted by gaps. The backward window is checked by
    exact 15-minute stamps; the forward window positionally
    (trading bars only, exactly as _trade_outcome indexes
    it), so it may legitimately span a weekend.
    """
    data = normalize_ohlc(frame)
    if data is None:
        return False
    entry = utc_naive(check_ts) - pd.Timedelta(minutes=15)
    pos = int(data.index.searchsorted(entry))
    if pos >= len(data) or data.index[pos] != entry:
        return False
    window = pd.date_range(
        entry - pd.Timedelta(minutes=15 * (M15_SLOT_WINDOW_BARS - 1)),
        entry, freq="15min")
    if not window.isin(data.index).all():
        return False
    return len(data) - 1 - pos >= M15_FORWARD_BARS


def fetch_m5_frames(state, symbols, *, deadline=None, force=False):
    """Current M5 frames, repository-first like fetch_m15_frames.

    Added 2026-11-16 (app migration repair): cycle86n's shape
    scores read the single M5 bar ending at each check slot --
    its filed book was driven with M5 supplied -- but the app
    had no M5 route at all, so the panel always ran the design
    with that input missing. Mirrors the M15 route: repository
    cache first, direct provider fetch for the missing symbols,
    memoised per required bar, persisted back to the repository,
    and returned with the time also as a "Datetime" column (the
    modules' _bars_from_frame reads the time from a column).
    """
    if state is None:
        state = {}
    symbols = tuple(symbols)
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    required = now.floor("5min") - pd.Timedelta(minutes=5)
    memo = state.setdefault(M5_MEMO_KEY, {})
    frames, missing, errors = {}, [], []
    basis = {}
    repo = _repository()
    for sym in symbols:
        cached = memo.get(sym)
        frame = cached.get("frame") if isinstance(cached, dict) else None
        sym_basis = cached.get("data_basis") if isinstance(cached, dict) else None
        sufficient = frame is not None and required in frame.index
        if force or not sufficient:
            try:
                raw = _dukascopy_rows(repo.load(sym, "M5", limit=400, completed_only=False)) if repo else None
                if raw is not None and getattr(raw, "attrs", {}).get("data_basis") == "fallback":
                    sym_basis = "fallback"
                frame = _merge(frame, normalize_ohlc(raw), 400)
            except Exception:
                pass
        basis[sym] = sym_basis or "dukascopy"
        sufficient = frame is not None and required in frame.index
        if frame is not None:
            frames[sym] = frame
        failed_recently = (isinstance(cached, dict) and cached.get("required") == required
                           and time.monotonic() - cached.get("attempt", 0) < RETRY_SECONDS)
        # REPO-FIRST (user order 2026-11-25 21:59 MMT), as M15.
        if not sufficient and not failed_recently:
            missing.append(sym)
    if missing:
        deadline = deadline if deadline is not None else time.monotonic() + FETCH_BUDGET_SECONDS
        raw_frames, errors = _direct_fetch(state, missing, "M5", deadline=deadline, force=force)
        for sym in missing:
            norm = normalize_ohlc(raw_frames.get(sym))
            frame = _merge(frames.get(sym), norm, 400)
            if frame is not None:
                frames[sym] = frame
            memo[sym] = dict(frame=frame, attempt=time.monotonic(), required=required,
                             data_basis=basis.get(sym, "dukascopy"))
            if sym in raw_frames:
                _persist_real(repo, raw_frames[sym], sym, "M5", errors)
    # Twelve Data fallback (user order 2026-11-27), as on the
    # H1/M15 routes: symbols still missing the required M5 bar
    # after the repository + Dukascopy route get it from
    # Twelve Data, merged UNDER existing bars.
    fb_missing = [s for s in symbols
                  if frames.get(s) is None
                  or required not in frames[s].index]
    if fb_missing:
        fb_frames, fb_errors = _twelve_fetch(
            state, fb_missing, "M5", end_ts=required,
            deadline=time.monotonic() + TWELVE_FALLBACK_BUDGET_SECONDS)
        errors.extend(fb_errors)
        for sym, raw in fb_frames.items():
            norm = normalize_ohlc(raw)
            if norm is None:
                continue
            frame = _merge(norm, frames.get(sym), 400)
            if frame is not None:
                frames[sym] = frame
                basis[sym] = "fallback"
                memo[sym] = dict(frame=frame,
                                 attempt=time.monotonic(),
                                 required=required,
                                 data_basis="fallback")
    state["check_m5_last_errors"] = errors
    if any(basis.get(s) == "fallback" for s in frames):
        state["check_data_basis"] = "fallback"
    _record_load_status(state, "M5", frames, symbols)
    out = {}
    for _sym, _f in frames.items():
        try:
            _o = _f.assign(Datetime=_f.index)
        except Exception:
            _o = _f
        _o.attrs["data_basis"] = basis.get(_sym, "dukascopy")
        out[_sym] = _o
    return out


def check_refresh_interval_ms(now=None):
    """Align a foreground tab refresh to the next actual UTC check boundary."""
    from core.signal_mode import active_check_hours
    now = utc_naive(now if now is not None else pd.Timestamp.now(tz="UTC"))
    next_checks = []
    for offset in range(8):
        day = now.normalize() + pd.Timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        for hour in active_check_hours():
            check = day + pd.Timedelta(hours=int(hour))
            age = (now-check).total_seconds()
            if 0 <= age < 60:
                return 5000
            if age < 0:
                next_checks.append(-age)
    return max(1000, min(30000, int(min(next_checks)*1000))) if next_checks else 30000
