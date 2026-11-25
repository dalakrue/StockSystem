"""Cold-boot restore of the candle cache from repo-shipped gzip parts.

The live candle DB (data/multi_symbol_field10_20260701.sqlite3, ~150 MB)
cannot be committed to git directly (GitHub rejects files over 100 MB),
so a compressed snapshot of it ships as base64 text parts under
data/cache_parts/ (see manifest.json there; the push route accepts
UTF-8 text only, hence the encoding). On a cold boot — a fresh
Streamlit Cloud checkout carries only a ~0.5 MB empty placeholder DB —
this module rebuilds the real DB from the parts before the repository
reads it. It is a no-op whenever a populated candle store is already
present, and it never raises: on any failure the app proceeds with
whatever store it has, exactly as it did before this module existed.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path

_PARTS_DIRNAME = "cache_parts"
_MANIFEST_NAME = "manifest.json"


def _candle_rows(db_path: Path) -> int | None:
    """Row count of the candles table, or None if unreadable/absent."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        try:
            row = conn.execute("SELECT COUNT(*) FROM candles").fetchone()
            return int(row[0]) if row else None
        finally:
            conn.close()
    except Exception:
        return None


def ensure_cache_db(db_path) -> bool:
    """Restore db_path from data/cache_parts if it is missing/empty.

    Returns True when a restore happened. Never raises.
    """
    tmp_gz = None
    tmp_db = None
    try:
        db_path = Path(db_path)
        if db_path.exists() and db_path.stat().st_size > 0 and _candle_rows(db_path):
            return False  # a populated candle store is already present

        parts_dir = db_path.parent / _PARTS_DIRNAME
        manifest_path = parts_dir / _MANIFEST_NAME
        if not manifest_path.exists():
            return False
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        part_names = sorted(manifest.get("parts") or [])
        if not part_names:
            return False

        tmp_gz = db_path.with_name(db_path.name + ".restore.gz")
        tmp_db = db_path.with_name(db_path.name + ".restore-tmp")
        encoded = b"".join((parts_dir / name).read_bytes() for name in part_names)
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
