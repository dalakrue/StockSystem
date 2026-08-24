"""Small SQLite helpers for render-safe, fail-closed reads."""
from __future__ import annotations
from pathlib import Path
import sqlite3
from collections.abc import Iterable


def connect_readonly(path: Path | str, *, timeout: float = 8.0, row_factory=sqlite3.Row) -> sqlite3.Connection:
    resolved = Path(path).resolve()
    conn = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True, timeout=timeout)
    conn.row_factory = row_factory
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={max(1, int(timeout * 1000))}")
    return conn


def missing_tables(path: Path | str, required: Iterable[str]) -> list[str]:
    try:
        with connect_readonly(path) as conn:
            present = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except Exception:
        return sorted(set(required))
    return sorted(set(required) - present)
