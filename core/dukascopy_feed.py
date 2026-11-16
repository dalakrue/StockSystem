"""Dukascopy tick feed for check / precheck evaluation candles.

User order 2026-11-16 21:51 MMT: the app's check and precheck
suggestions must match Everest's chain. The chain reads Dukascopy
only; the app read Twelve Data, and on 2026-11-16 the two feeds
disagreed on the deciding bar of the 21:30 November check by
5-6 pips (EURJPY 14:45 UTC), so the app fired a pick the chain
read as a rank-3 near-miss. Same cycle + same candles = same
suggestion; this module gives the app the same candles.

There is NO Dukascopy API key or REST API like Twelve's. This is
the same free, keyless HTTP tick route the machine pipelines use
(live_trader/fetch_dukascopy.py), with the same maths:

  GET https://datafeed.dukascopy.com/datafeed/{SYM}/{YYYY}/{MM0}/{DD}/{HH}h_ticks.bi5
  MM0 = zero-indexed month, HH = UTC hour. Body = LZMA-compressed
  ticks, 20 bytes each, big-endian: int32 ms-offset-from-hour,
  int32 ask, int32 bid, float32 ask-volume, float32 bid-volume.
  Price scale 100000 (1000 for JPY pairs). BID side only.
  Candle volume = sum(bid_volume + ask_volume) per bucket.

RATE LIMIT LAW (mirrors the chain): an HTTP 429 (or 503) aborts
the whole refresh immediately -- no retries, no marching on to
the next hour or symbol. Whatever was assembled is returned and
the failure is named in the errors, so the panel's readiness
floor and load-failure display decide honestly. A symbol whose
download fails is NAMED; Twelve Data candles are never silently
substituted into an evaluation.

Assembly: per symbol, tick hours are downloaded once and
aggregated to M5 / M15 / H1 BID bars, cached in the caller's
state dict (the panel's session state) across the window's
5-minute refreshes. A cold symbol assembles SPAN_DAYS of history
(the designs' true needs are small -- 32-bar slot features and
48 h / 192-bar pending resolution -- and the persisted cycle
state carries the rest); a warm symbol downloads only the new
tail. Interrupted cold assemblies resume on the next refresh:
tail first, then backfill toward the span start, newest first.
"""
from __future__ import annotations

import io
import lzma
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait

import numpy as np
import pandas as pd

FEED = "https://datafeed.dukascopy.com/datafeed"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) fx-stocksystem/1.0"}
FEED_KEY = "dukascopy_feed_v1"
SPAN_DAYS = 10
MAX_WORKERS = 6
HOUR_TIMEOUT = 20.0

_TFS = ("M5", "M15", "H1")
_COLS = ["Open", "High", "Low", "Close", "Volume"]


class RateLimited(Exception):
    """Feed answered 429/503: hard stop for the whole refresh."""


def price_scale(sym: str) -> float:
    return 1000.0 if sym.endswith("JPY") else 100000.0


def hour_url(sym: str, hour: pd.Timestamp) -> str:
    return (f"{FEED}/{sym}/{hour.year}/{hour.month - 1:02d}/"
            f"{hour.day:02d}/{hour.hour:02d}h_ticks.bi5")


def download_hour(sym: str, hour: pd.Timestamp, timeout=HOUR_TIMEOUT):
    """Raw tick array for one UTC hour, or None when the feed has
    no file (404 = hour not posted yet / market closed). Returns
    (array, n_bytes). Raises RateLimited on 429/503."""
    req = urllib.request.Request(hour_url(sym, hour), headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            blob = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, 0
        if e.code in (429, 503):
            raise RateLimited(f"{sym} {hour}: HTTP {e.code}") from e
        raise
    if not blob:
        return None, 0
    raw = lzma.decompress(blob)
    n = len(raw) // 20
    if n == 0:
        return None, len(blob)
    arr = np.frombuffer(raw[: n * 20], dtype=">i4,>i4,>i4,>f4,>f4")
    return arr, len(blob)


def aggregate_hour(sym: str, hour: pd.Timestamp, arr):
    """Ticks -> {"M5": frame, "M15": frame, "H1": frame} of BID
    OHLC + tick volume for one UTC hour. Identical maths to the
    chain fetcher's aggregate_hour, plus the M5 buckets."""
    scale = price_scale(sym)
    ms = arr["f0"].astype(np.int64)
    bid = arr["f2"].astype(np.float64) / scale
    vol = arr["f3"].astype(np.float64) + arr["f4"].astype(np.float64)
    out = {}
    for tf, bucket_ms, n_buckets in (("M5", 300_000, 12),
                                     ("M15", 900_000, 4)):
        bucket = ms // bucket_ms
        rows = []
        for b in range(n_buckets):
            m = bucket == b
            if not m.any():
                continue
            ts = hour + pd.Timedelta(minutes=(5 if tf == "M5" else 15) * b)
            rows.append((ts, bid[m][0], bid[m].max(), bid[m].min(),
                         bid[m][-1], float(vol[m].sum())))
        out[tf] = pd.DataFrame(
            rows, columns=["Datetime"] + _COLS).set_index("Datetime")
    out["H1"] = pd.DataFrame(
        [(hour, bid[0], bid.max(), bid.min(), bid[-1], float(vol.sum()))],
        columns=["Datetime"] + _COLS).set_index("Datetime")
    return out


def trading_hours(start: pd.Timestamp, end: pd.Timestamp):
    """UTC hours in [start, end] when FX is open (skip Sat,
    Sun<21:00, Fri>=21:00). Dukascopy 404s closed hours anyway;
    skipping saves requests."""
    h = start
    while h <= end:
        wd = h.weekday()
        if wd == 5:
            pass
        elif wd == 6 and h.hour < 21:
            pass
        elif wd == 4 and h.hour >= 21:
            pass
        else:
            yield h
        h += pd.Timedelta(hours=1)


def _empty_frame():
    return pd.DataFrame(columns=_COLS,
                        index=pd.DatetimeIndex([], name="Datetime"))


def _merge(old, new):
    if new is None or not len(new):
        return old
    if old is None or not len(old):
        return new
    out = pd.concat([old, new])
    return out.loc[~out.index.duplicated(keep="last")].sort_index()


class _SymbolCache:
    __slots__ = ("frames", "have_from", "have_through", "missed")

    def __init__(self):
        self.frames = {}
        self.have_from = None     # oldest hour attempted (incl. 404)
        self.have_through = None  # newest hour attempted (incl. 404)
        self.missed = set()       # hour stamps that returned no file


def _cache_for(book, sym):
    cache = book.get(sym)
    if cache is None:
        cache = _SymbolCache()
        book[sym] = cache
    return cache


def _hours_between(a, b):
    return list(trading_hours(a, b)) if a <= b else []


def fetch_frames(state, symbols, tf, *, deadline=None, force=False,
                 now_utc=None, downloader=None):
    """Assemble Dukascopy frames for `symbols` at timeframe `tf`.

    Returns (frames, errors) in the runtime's _direct_fetch
    contract: frames maps symbol -> normalized-shape DataFrame
    (DatetimeIndex, Open/High/Low/Close/Volume); errors names
    every symbol/hour failure honestly. `downloader` is injectable
    for offline proofs (same signature as download_hour).
    """
    tf = str(tf).upper()
    if tf not in _TFS:
        return {}, [f"Dukascopy feed: unsupported timeframe {tf}"]
    downloader = downloader or download_hour
    if state is None:
        state = {}
    # `state` is the panel's session state (a plain dict in the
    # offline harnesses, st.session_state in the app -- both
    # support setdefault/get, which is all the cache needs).
    book = state.setdefault(FEED_KEY, {})
    stats = book.setdefault("_stats", {"files": 0, "bytes": 0,
                                       "seconds": 0.0})
    now = (pd.Timestamp(now_utc) if now_utc is not None
           else pd.Timestamp.now(tz="UTC").tz_localize(None))
    end_hour = now.floor("h")
    span_start = (end_hour - pd.Timedelta(days=SPAN_DAYS)).floor("h")
    errors = []

    # ---- plan the downloads, per symbol -------------------------
    plan = {}  # sym -> list of hours, priority order (tail first)
    for sym in symbols:
        cache = _cache_for(book, sym)
        hours = []
        if cache.have_through is None:
            hours = _hours_between(span_start, end_hour)
            # newest first: the deciding bars land before the
            # deadline even if the deep backfill is cut short.
            hours = list(reversed(hours))
        else:
            tail = _hours_between(cache.have_through + pd.Timedelta(hours=1),
                                  end_hour)
            hours.extend(tail)
            if cache.have_from is not None and cache.have_from > span_start:
                back = _hours_between(span_start,
                                      cache.have_from - pd.Timedelta(hours=1))
                hours.extend(reversed(back))
            if force:
                recent = _hours_between(end_hour - pd.Timedelta(hours=1),
                                        end_hour)
                hours = recent + [h for h in hours if h not in recent]
        # The current hour's file may appear after an earlier 404:
        # never let a remembered miss suppress it.
        plan[sym] = [h for h in hours
                     if h == end_hour or h not in cache.missed]

    jobs = [(sym, h) for sym in symbols for h in plan[sym]]
    # Interleave symbols round-robin (plans are newest-first) so a
    # deadline cut leaves every symbol with its recent bars rather
    # than finishing some symbols' deep history first.
    jobs.sort(key=lambda j: plan[j[0]].index(j[1]))
    rate_limited = None
    started = time.monotonic()
    if jobs:
        executor = ThreadPoolExecutor(max_workers=MAX_WORKERS,
                                      thread_name_prefix="dukascopy-feed")
        try:
            pending = {}
            idx = 0
            BATCH = MAX_WORKERS * 4
            while idx < len(jobs) or pending:
                while (idx < len(jobs) and len(pending) < BATCH
                       and rate_limited is None):
                    if deadline is not None and time.monotonic() > deadline:
                        idx = len(jobs)  # stop submitting; drain below
                        break
                    sym, hour = jobs[idx]
                    idx += 1
                    pending[executor.submit(downloader, sym, hour)] = (sym, hour)
                if not pending:
                    break
                done, _ = wait(list(pending), timeout=0.5,
                               return_when="FIRST_COMPLETED")
                if not done:
                    if deadline is not None and time.monotonic() > deadline:
                        for fut in pending:
                            fut.cancel()
                        for sym in {s for s, _h in pending.values()}:
                            errors.append(
                                f"{sym} {tf}: refresh budget reached")
                        pending.clear()
                        break
                    continue
                for fut in done:
                    sym, hour = pending.pop(fut)
                    cache = _cache_for(book, sym)
                    try:
                        arr, nbytes = fut.result()
                    except RateLimited as exc:
                        rate_limited = exc
                        errors.append(
                            f"{sym} {tf}: Dukascopy rate limit "
                            f"({exc}); refresh stopped")
                        continue
                    except Exception as exc:
                        errors.append(
                            f"{sym} {tf}: Dukascopy download failed "
                            f"({type(exc).__name__}) at {hour:%Y-%m-%d %H:%M} UTC")
                        continue
                    stats["files"] += 1
                    stats["bytes"] += int(nbytes)
                    if arr is None:
                        if hour != end_hour:
                            cache.missed.add(hour)
                    else:
                        try:
                            agg = aggregate_hour(sym, hour, arr)
                        except Exception as exc:
                            errors.append(
                                f"{sym} {tf}: Dukascopy aggregation failed "
                                f"({type(exc).__name__}) at {hour:%Y-%m-%d %H:%M} UTC")
                            continue
                        for _tf, frame in agg.items():
                            cache.frames[_tf] = _merge(
                                cache.frames.get(_tf), frame)
                    if cache.have_from is None or hour < cache.have_from:
                        cache.have_from = hour
                    if cache.have_through is None or hour > cache.have_through:
                        cache.have_through = hour
                if rate_limited is not None:
                    for fut in pending:
                        fut.cancel()
                    pending.clear()
                    break
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
    stats["seconds"] += time.monotonic() - started

    # ---- serve the requested timeframe from the cache -----------
    frames = {}
    trim_from = span_start - pd.Timedelta(days=1)
    for sym in symbols:
        cache = _cache_for(book, sym)
        frame = cache.frames.get(tf)
        if frame is None or not len(frame):
            if not any(e.startswith(f"{sym} ") for e in errors):
                errors.append(f"{sym} {tf}: no Dukascopy candles available")
            continue
        frame = frame.loc[frame.index >= trim_from]
        cache.frames[tf] = frame
        frames[sym] = frame
    return frames, errors


def feed_stats(state):
    """Cumulative (files, bytes, seconds) of this session's feed —
    used by the timing proofs; harmless in the app."""
    try:
        stats = (state or {}).get(FEED_KEY, {}).get("_stats", {})
        return (int(stats.get("files", 0)), int(stats.get("bytes", 0)),
                float(stats.get("seconds", 0.0)))
    except Exception:
        return (0, 0, 0.0)
