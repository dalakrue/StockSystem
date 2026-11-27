"""Store the OHLC the app loads (user order 2026-11-28).

Wherever the app loads candles from Twelve Data — the
check/precheck routes' Twelve fallback, the Replay section's
loader, and the manual Calculate flows that run on it — the
loaded bars are persisted into the app's candle store, so
loaded data ACCUMULATES locally: a later read finds the bars
in the store (the check route reads the repository first)
instead of spending Twelve credits re-fetching them.

Semantics: INSERT OR IGNORE against the store's
UNIQUE(symbol, timeframe, broker_open_time) — a bar already
in the store is NEVER overwritten, whatever the new copy
says; existing bars always win. Rows are provider-labelled
(TWELVE_DATA) with the load path's source_status, so the
check route's fallback bookkeeping can still tell exactly
which bars came from Twelve and a read that uses them is
labelled "fallback data" as before.

Safety contract (the signal path depends on it):
- NEVER raises. Every failure is swallowed and reported as
  zero rows stored.
- The write itself runs on a daemon thread
  (store_loaded_ohlc_async): callers hand over the frames
  they already hold, the (cheap) record extraction happens
  inline, and no evaluation ever waits on the database.
- A missing store file or a missing candles table is a
  silent no-op — this helper never creates a store.
"""
from __future__ import annotations

import os
import sqlite3
import threading

import pandas as pd

_TF_MINUTES = {"H1": 60, "M15": 15, "M5": 5}

_INSERT_SQL = (
    "INSERT OR IGNORE INTO candles("
    "symbol,timeframe,broker_open_time,broker_close_time,"
    "open,high,low,close,volume,provider,fetched_at,"
    "is_complete,broker_time,data_quality_score,"
    "validation_status,source_status,run_id,provider_symbol,"
    "provider_key_alias,data_age_seconds) "
    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")


def _db_path(db_path=None):
    """The app's candle store path: explicit argument, else
    the FOREX_CANDLE_STORE_DB override (tests), else the
    repository's own DEFAULT_DB_PATH — the same file every
    reader uses."""
    if db_path:
        return str(db_path)
    env = os.environ.get("FOREX_CANDLE_STORE_DB")
    if env:
        return env
    try:
        from core.data.deployment_migrations_20260705 import (
            DEFAULT_DB_PATH)
        return str(DEFAULT_DB_PATH)
    except Exception:
        return None


def _frame_records(symbol, frame, tf, provider, source_status,
                   run_id, now):
    """Candle-row tuples for one normalized frame (Datetime
    index, Open/High/Low/Close[/Volume] columns). Invalid
    rows (non-finite / non-positive / broken OHLC) are
    skipped, mirroring the repository's validation. A bar
    counts complete only when its close time has passed."""
    step = pd.Timedelta(minutes=_TF_MINUTES[tf])
    out = []
    try:
        idx = frame.index
        if "Datetime" in frame.columns and not isinstance(
                idx, pd.DatetimeIndex):
            idx = pd.DatetimeIndex(frame["Datetime"])
        cols = {str(c).lower(): c for c in frame.columns}
        o = frame[cols["open"]]
        h = frame[cols["high"]]
        l = frame[cols["low"]]
        c = frame[cols["close"]]
        v = (pd.to_numeric(frame[cols["volume"]],
                           errors="coerce")
             if "volume" in cols else None)
        for i, ts in enumerate(idx):
            try:
                ts = pd.Timestamp(ts)
                # Stamps are written in the repository's own
                # format — tz-aware UTC ISO ("...+00:00") —
                # so the store's UNIQUE(symbol, timeframe,
                # broker_open_time) key collides with bars
                # the repository itself wrote, and INSERT OR
                # IGNORE truly never duplicates a bar.
                if ts.tzinfo is None:
                    ts = ts.tz_localize("UTC")
                else:
                    ts = ts.tz_convert("UTC")
                ov, hv, lv, cv = (float(o.iloc[i]),
                                  float(h.iloc[i]),
                                  float(l.iloc[i]),
                                  float(c.iloc[i]))
            except Exception:
                continue
            if not all(pd.notna(x) and x > 0
                       for x in (ov, hv, lv, cv)):
                continue
            if hv < max(ov, cv) or lv > min(ov, cv) or hv < lv:
                continue
            vol = None
            if v is not None:
                try:
                    vv = float(v.iloc[i])
                    vol = vv if pd.notna(vv) else None
                except Exception:
                    vol = None
            close_ts = ts + step
            complete = 1 if close_ts <= now else 0
            out.append((
                str(symbol), tf, ts.isoformat(),
                close_ts.isoformat(), ov, hv, lv, cv, vol,
                str(provider), now.isoformat(), complete,
                ts.isoformat(),
                100.0 if complete else 75.0, "VALID",
                str(source_status), str(run_id), str(symbol),
                "", max(0.0, (now - ts).total_seconds())))
    except Exception:
        return out
    return out


def _extract(frames, tf, provider, source_status, run_id):
    records = []
    if tf not in _TF_MINUTES or not frames:
        return records
    now = pd.Timestamp.now(tz="UTC")
    for sym, frame in frames.items():
        if frame is None or len(frame) == 0:
            continue
        records.extend(_frame_records(
            sym, frame, tf, provider, source_status, run_id,
            now))
    return records


def _write(records, path):
    """INSERT OR IGNORE one batch; returns rows actually
    inserted. Never raises."""
    if not records or not path:
        return 0
    try:
        if not os.path.isfile(path):
            return 0
        conn = sqlite3.connect(path, timeout=30)
        try:
            conn.execute("PRAGMA busy_timeout=30000")
            before = conn.total_changes
            conn.executemany(_INSERT_SQL, records)
            conn.commit()
            return conn.total_changes - before
        finally:
            conn.close()
    except Exception:
        return 0


def store_loaded_ohlc(frames, tf, *, provider="TWELVE_DATA",
                      source_status="LOADED_TWELVE",
                      run_id="store_loaded_ohlc", db_path=None):
    """Synchronously persist loaded bars (INSERT OR IGNORE).
    frames: {symbol: normalized frame}. Returns
    {"seen": n_bars, "inserted": n_new}. Never raises."""
    try:
        records = _extract(frames, tf, provider, source_status,
                           run_id)
        inserted = _write(records, _db_path(db_path))
        return {"seen": len(records), "inserted": inserted}
    except Exception:
        return {"seen": 0, "inserted": 0}


def store_loaded_ohlc_async(frames, tf, *,
                            provider="TWELVE_DATA",
                            source_status="LOADED_TWELVE",
                            run_id="store_loaded_ohlc",
                            db_path=None):
    """Fire-and-forget variant for signal paths: records are
    extracted inline (cheap), the database write runs on a
    daemon thread. Returns True iff a write was scheduled.
    Never raises."""
    try:
        records = _extract(frames, tf, provider, source_status,
                           run_id)
        if not records:
            return False
        path = _db_path(db_path)
        if not path:
            return False
        thread = threading.Thread(
            target=_write, args=(records, path), daemon=True,
            name=f"store-loaded-{tf}")
        thread.start()
        return True
    except Exception:
        return False
