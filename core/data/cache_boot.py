"""Cold-boot restore of the candle cache from gzip parts.

The live candle DB (data/multi_symbol_field10_20260701.sqlite3, ~150 MB)
cannot be committed to git directly (GitHub rejects files over 100 MB),
so a compressed snapshot of it ships as base64 text parts (see
manifest.json; the push route accepts UTF-8 text only, hence the
encoding). Since 2026-11-28 the snapshot lives in the separate data
repo dalakrue/fx-data under cache_parts/ -- StockSystem itself no
longer carries the ~165 MB of parts. On a cold boot -- a fresh
Streamlit Cloud checkout carries only a ~0.5 MB empty placeholder DB --
this module downloads the parts from fx-data and rebuilds the real DB
before the repository reads it. A locally present copy of the parts
(data/cache_parts/ next to the DB) is still honoured as a fallback
when it exists. The restore is a no-op whenever a populated candle
store is already present, and it never raises: on any failure the app
proceeds with whatever store it has, exactly as it did before this
module existed.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import urllib.request
from pathlib import Path

_PARTS_DIRNAME = "cache_parts"
_MANIFEST_NAME = "manifest.json"
_REMOTE_PARTS_BASE = (
    "https://raw.githubusercontent.com/dalakrue/fx-data/main/cache_parts"
)
_DOWNLOAD_TIMEOUT_SECONDS = 60


def _fetch_bytes(url: str) -> bytes | None:
    """GET url as bytes, or None on any failure. Never raises."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "stocksystem-cache-boot"})
        with urllib.request.urlopen(
                req, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as resp:
            return resp.read()
    except Exception:
        return None


def _candle_counts(db_path: Path) -> dict[str, int] | None:
    """Per-timeframe candle row counts, or None if unreadable/absent."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        try:
            return {str(tf): int(n) for tf, n in conn.execute(
                "SELECT timeframe, COUNT(*) FROM candles GROUP BY timeframe")}
        finally:
            conn.close()
    except Exception:
        return None


def _store_matches_manifest(db_path: Path, manifest: dict) -> bool:
    """True when the on-disk store already holds at least the snapshot.

    Fix 2026-11-25 (20-of-28 bug): the old check accepted ANY non-empty
    candles table as "populated", so a store holding only part of the
    universe (e.g. the old 20-symbol set) blocked the restore forever
    and the app could never load the missing symbols from cache. A
    store that has been freshened by live loads holds MORE rows than
    the snapshot and still counts as matching -- it is never replaced.
    """
    counts = manifest.get("counts") or {}
    if not counts:
        return False
    if not db_path.exists() or db_path.stat().st_size <= 0:
        return False
    existing = _candle_counts(db_path)
    if existing is None:
        return False
    return all(int(existing.get(tf, 0)) >= int(n) for tf, n in counts.items())


def ensure_cache_db(db_path) -> bool:
    """Restore db_path from the cache snapshot if it is missing or holds
    less than the snapshot (per-timeframe candle counts).

    Parts are read from a locally present data/cache_parts/ when one
    exists (fallback), otherwise downloaded from dalakrue/fx-data.
    Returns True when a restore happened. Never raises.
    """
    tmp_gz = None
    tmp_db = None
    try:
        db_path = Path(db_path)

        parts_dir = db_path.parent / _PARTS_DIRNAME
        manifest_path = parts_dir / _MANIFEST_NAME
        local = manifest_path.exists()
        if local:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            raw_manifest = _fetch_bytes(
                _REMOTE_PARTS_BASE + "/" + _MANIFEST_NAME)
            if raw_manifest is None:
                return False
            manifest = json.loads(raw_manifest.decode("utf-8"))
        if _store_matches_manifest(db_path, manifest):
            return False  # store already holds at least the snapshot
        part_names = sorted(manifest.get("parts") or [])
        if not part_names:
            return False

        tmp_gz = db_path.with_name(db_path.name + ".restore.gz")
        tmp_db = db_path.with_name(db_path.name + ".restore-tmp")
        if local:
            encoded = b"".join(
                (parts_dir / name).read_bytes() for name in part_names)
        else:
            blobs = []
            for name in part_names:
                blob = _fetch_bytes(_REMOTE_PARTS_BASE + "/" + name)
                if blob is None:
                    return False  # a part is unreachable; keep the old store
                blobs.append(blob)
            encoded = b"".join(blobs)
        raw_gz = base64.b64decode(encoded, validate=True) \
            if manifest.get("encoding") == "base64" else encoded
        digest = hashlib.sha256()
        digest.update(raw_gz)
        with open(tmp_gz, "wb") as out:
            out.write(raw_gz)
        expected = str(manifest.get("gz_sha256") or "")
        if expected and digest.hexdigest() != expected:
            return False  # parts are incomplete/corrupt; keep the old store

        with gzip.open(tmp_gz, "rb") as src, open(tmp_db, "wb") as dst:
            shutil.copyfileobj(src, dst, length=1 << 20)

        counts = manifest.get("counts") or {}
        if counts:
            conn = sqlite3.connect(f"file:{tmp_db}?mode=ro", uri=True, timeout=10)
            try:
                actual = dict(conn.execute(
                    "SELECT timeframe, COUNT(*) FROM candles GROUP BY timeframe"))
            finally:
                conn.close()
            if any(int(actual.get(tf, 0)) != int(n) for tf, n in counts.items()):
                return False  # reassembled store does not match the manifest

        os.replace(tmp_db, db_path)
        tmp_db = None
        return True
    except Exception:
        return False
    finally:
        for tmp in (tmp_gz, tmp_db):
            try:
                if tmp is not None and Path(tmp).exists():
                    Path(tmp).unlink()
            except Exception:
                pass
