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
RETRY_SECONDS = 15.0
SUCCESS_SECONDS = 60.0
FETCH_BUDGET_SECONDS = 20.0


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
    row.attrs["entry_source"] = "TWELVE_DATA_M15_HOUR_OPEN"
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
        normalized = normalize_frame(raw, symbol=sym, timeframe=tf, provider="TWELVE_DATA")
        # Only complete real candles; partial H1 fallback never enters this path.
        normalized = normalized.loc[normalized.is_complete]
        repo.upsert(normalized, require_complete=True)
    except Exception as exc:
        errors.append(f"{sym} {tf}: cache write {type(exc).__name__}")


def _direct_fetch(state, symbols, tf, *, deadline, force=False):
    """Reserve credits on the UI thread; workers never touch session state.

    No sleeps or inner retry loop. Return at the page budget even if a provider
    request hangs. Late workers can only update their connector cache; they
    cannot mutate panel frames, the repository, or session state.
    """
    from core.twelve_data_key_pool import TwelveDataKeyPool
    from core.connectors.data_parts.fetchers import fetch_twelve
    pool = TwelveDataKeyPool.from_state(state)
    errors, jobs, frames = [], {}, {}
    if not symbols:
        return frames, errors
    executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="check-candles")
    try:
        for sym in symbols:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                errors.append(f"{sym} {tf}: refresh budget reached")
                break
            lease = pool.reserve_key(symbol=sym, timeframe=tf)
            if lease is None:
                errors.append(f"{sym} {tf}: no API credit available; retry next refresh")
                continue
            future = executor.submit(fetch_twelve, sym, lease.api_key,
                                     interval="1h" if tf == "H1" else "15min", bars=2000,
                                     force_live=force, timeout_seconds=min(4.0, remaining))
            jobs[future] = (sym, lease.alias)
        done, pending = wait(jobs, timeout=max(0.0, deadline - time.monotonic()))
        for future in pending:
            future.cancel()
            errors.append(f"{jobs[future][0]} {tf}: provider deadline reached")
        for future in done:
            sym, alias = jobs[future]
            try:
                raw, ok, message = future.result()
                if ok and isinstance(raw, pd.DataFrame) and not raw.empty:
                    pool.mark_success(alias)
                    frames[sym] = raw
                else:
                    pool.mark_failure(alias, str(message))
                    # Provider bodies/exceptions may contain a URL with credentials.
                    errors.append(f"{sym} {tf}: provider returned no usable candles")
            except Exception as exc:
                errors.append(f"{sym} {tf}: {type(exc).__name__}")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return frames, errors


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
    for sym in symbols:
        try:
            frame = normalize_ohlc(repo.load(sym, "H1", limit=400, completed_only=False), 50) if repo else None
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
    h1_targets = [s for s in symbols if (force and s not in only_entry) or s not in frames
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
    ready_symbols = [s for s in symbols if s in frames
                     and (not need or need.issubset(frames[s].index))]
    latest = max((f.index.max() for f in frames.values()), default=None)
    diag = dict(cache=sum(v == "H1 cache" for v in sources.values()),
                live=sum(v != "H1 cache" for v in sources.values()), frames=len(frames),
                ready=len(ready_symbols), required=len(symbols),
                missing_symbols=[s for s in symbols if s not in ready_symbols],
                entry_sources=sources, live_errors=errors[:8])
    result = frames, latest, diag
    state[H1_MEMO_KEY] = dict(key=key, at=time.monotonic(), result=result)
    return result


def fetch_m15_frames(state, symbols, *, deadline=None, need_entry=None, force=False):
    """Deep, current M15 shared by the entry fallback and all M15 B systems."""
    symbols = tuple(symbols)
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    required = utc_naive(need_entry) if need_entry is not None else now.floor("15min") - pd.Timedelta(minutes=15)
    memo = state.setdefault(M15_MEMO_KEY, {})
    frames, missing, errors = {}, [], []
    repo = _repository()
    for sym in symbols:
        cached = memo.get(sym)
        frame = cached.get("frame") if isinstance(cached, dict) else None
        sufficient = frame is not None and required in frame.index and (need_entry is not None or len(frame) >= 1600)
        if force or not sufficient:
            try:
                raw = repo.load(sym, "M15", limit=2000, completed_only=False) if repo else None
                frame = _merge(frame, normalize_ohlc(raw), 5000)
            except Exception:
                pass
        sufficient = frame is not None and required in frame.index and (need_entry is not None or len(frame) >= 1600)
        if frame is not None:
            frames[sym] = frame
        failed_recently = (isinstance(cached, dict) and cached.get("required") == required
                           and time.monotonic() - cached.get("attempt", 0) < RETRY_SECONDS)
        if force or (not sufficient and not failed_recently):
            missing.append(sym)
    if missing:
        deadline = deadline if deadline is not None else time.monotonic() + FETCH_BUDGET_SECONDS
        raw_frames, errors = _direct_fetch(state, missing, "M15", deadline=deadline, force=force)
        for sym in missing:
            norm = normalize_ohlc(raw_frames.get(sym))
            frame = _merge(frames.get(sym), norm, 5000)
            if frame is not None:
                frames[sym] = frame
            memo[sym] = dict(frame=frame, attempt=time.monotonic(), required=required)
            if sym in raw_frames:
                _persist_real(repo, raw_frames[sym], sym, "M15", errors)
    state["check_m15_last_errors"] = errors
    return frames


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
