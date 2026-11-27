"""Moved-since-entry figure for displayed picks (user order
2026-11-28): every calculated signal shows, beside its entry,
how far the price has moved since that entry — "moved:
+X.X pips" — measured against the LATEST price available
locally: the newest completed bar's close for the symbol in
the app's own candle store (M15 preferred, H1 fallback).

Local read only: a read-only sqlite query on the store DB —
no provider calls, no repository instantiation (so no
cache-boot side effects on a render path). Direction-aware:
BUY gains when price rises, SELL gains when it falls. When
no later price exists the figure is None and callers render
"moved: —" — a number is never fabricated.

A short-lived module cache (30 s) keeps a page render that
shows several picks of one symbol to one store read.
"""
from __future__ import annotations

import time as _time

_CACHE: dict = {}
_TTL_SECONDS = 30.0


def _pip_size(symbol) -> float:
    try:
        from core.cycle12_best import pip_size as _ps
        return float(_ps(str(symbol).upper()))
    except Exception:
        return 0.01 if "JPY" in str(symbol).upper() else 0.0001


def _db_path():
    try:
        from core.data.deployment_migrations_20260705 import (
            DEFAULT_DB_PATH)
        return DEFAULT_DB_PATH
    except Exception:
        return None


def latest_stored_close(symbol):
    """Newest completed bar's close for ``symbol`` in the
    local candle store (M15 preferred over H1 by bar end
    time), or None when the store holds no bar for it.
    Never raises."""
    try:
        sym = str(symbol or "").upper().replace("/", "").strip()
        if not sym:
            return None
        now = _time.monotonic()
        hit = _CACHE.get(sym)
        if hit is not None and now - hit[0] < _TTL_SECONDS:
            return hit[1]
        price = None
        path = _db_path()
        if path is not None:
            import sqlite3 as _sq
            from pathlib import Path as _Path
            p = _Path(path)
            if p.exists():
                conn = _sq.connect(
                    f"file:{p}?mode=ro", uri=True, timeout=5)
                try:
                    best_end = None
                    for tf, minutes in (("M15", 15), ("H1", 60)):
                        try:
                            row = conn.execute(
                                "SELECT close, broker_open_time,"
                                " broker_close_time FROM candles"
                                " WHERE symbol=? AND timeframe=?"
                                " AND is_complete=1 ORDER BY"
                                " broker_open_time DESC LIMIT 1",
                                (sym, tf)).fetchone()
                        except Exception:
                            row = None
                        if not row:
                            continue
                        close_v, open_t, close_t = row
                        end = str(close_t or "")
                        if not end:
                            # Derive the bar end from its open
                            # so M15 and H1 compare fairly.
                            try:
                                import pandas as _pd
                                end = str(_pd.Timestamp(open_t)
                                          + _pd.Timedelta(
                                              minutes=minutes))
                            except Exception:
                                end = str(open_t or "")
                        if best_end is None or end > best_end:
                            best_end = end
                            price = float(close_v)
                finally:
                    conn.close()
        _CACHE[sym] = (now, price)
        return price
    except Exception:
        return None


def moved_pips(symbol, direction, entry, latest=None):
    """Signed pips the price has moved IN THE PICK'S FAVOUR
    since ``entry``: (latest − entry) for BUY, (entry −
    latest) for SELL, in pips (0.01 JPY / 0.0001 else).
    ``latest`` may be supplied by the caller (e.g. from
    already-loaded frames); otherwise the local store's
    newest close is used. None when no price is available.
    Never raises."""
    try:
        e = float(entry)
        if latest is None:
            latest = latest_stored_close(symbol)
        if latest is None:
            return None
        latest = float(latest)
        raw = (latest - e) if str(direction).upper() == "BUY" \
            else (e - latest)
        return round(raw / _pip_size(symbol), 1)
    except Exception:
        return None


def moved_text(symbol, direction, entry, latest=None):
    """"moved: +X.X pips" / "moved: -X.X pips", or
    "moved: —" when no later price exists."""
    v = moved_pips(symbol, direction, entry, latest=latest)
    if v is None:
        return "moved: \u2014"
    return f"moved: {v:+.1f} pips"
