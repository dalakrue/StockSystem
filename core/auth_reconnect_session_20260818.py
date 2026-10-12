"""Opaque persistent authentication leases for Streamlit reconnects.

Streamlit keeps login state in a WebSocket session.  A long calculation can
cause a browser/mobile connection to reconnect with a new session, which used
to send an already-authenticated user back to Login.  This module stores only a
hash of a random bearer token in the existing authentication SQLite database.
No password, API key, or signed calculation data is placed in the URL.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any
import hashlib
import secrets
import sqlite3
import time


VERSION = "auth-reconnect-session-20260818-v1"
ACCOUNT_TTL_SECONDS = 7 * 24 * 60 * 60
GUEST_TTL_SECONDS = 12 * 60 * 60


def _connect(path: str | Path) -> sqlite3.Connection:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(target), timeout=8)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS auth_sessions ("
        "token_hash TEXT PRIMARY KEY, "
        "email TEXT NOT NULL, "
        "guest INTEGER NOT NULL DEFAULT 0, "
        "created_at REAL NOT NULL, "
        "expires_at REAL NOT NULL, "
        "last_seen REAL NOT NULL)"
    )
    connection.commit()
    return connection


def _token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def issue_session(
    path: str | Path,
    *,
    email: str,
    guest: bool,
    now: float | None = None,
    ttl_seconds: float | None = None,
) -> str:
    """Create one opaque reconnect lease and return its browser token."""
    created = float(time.time() if now is None else now)
    ttl = float(ttl_seconds or (GUEST_TTL_SECONDS if guest else ACCOUNT_TTL_SECONDS))
    ttl = max(300.0, min(ttl, 30 * 24 * 60 * 60))
    token = secrets.token_urlsafe(32)
    clean_email = "Guest" if guest else str(email or "").strip().lower()
    if not clean_email:
        raise ValueError("A reconnect session requires an authenticated identity.")
    with closing(_connect(path)) as connection:
        connection.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (created,))
        connection.execute(
            "INSERT INTO auth_sessions(token_hash,email,guest,created_at,expires_at,last_seen) VALUES(?,?,?,?,?,?)",
            (_token_hash(token), clean_email, int(bool(guest)), created, created + ttl, created),
        )
        connection.commit()
    return token


def restore_session(path: str | Path, token: str, *, now: float | None = None) -> dict[str, Any] | None:
    """Resolve a non-expired opaque lease and refresh its last-seen time."""
    clean_token = str(token or "").strip()
    if not clean_token:
        return None
    checked = float(time.time() if now is None else now)
    with closing(_connect(path)) as connection:
        row = connection.execute(
            "SELECT email,guest,created_at,expires_at FROM auth_sessions WHERE token_hash=?",
            (_token_hash(clean_token),),
        ).fetchone()
        if not row or float(row[3]) < checked:
            connection.execute("DELETE FROM auth_sessions WHERE token_hash=?", (_token_hash(clean_token),))
            connection.commit()
            return None
        connection.execute(
            "UPDATE auth_sessions SET last_seen=? WHERE token_hash=?",
            (checked, _token_hash(clean_token)),
        )
        connection.commit()
    return {
        "email": str(row[0]),
        "guest": bool(row[1]),
        "created_at": float(row[2]),
        "expires_at": float(row[3]),
        "version": VERSION,
    }


def revoke_session(path: str | Path, token: str) -> bool:
    clean_token = str(token or "").strip()
    if not clean_token:
        return False
    with closing(_connect(path)) as connection:
        cursor = connection.execute(
            "DELETE FROM auth_sessions WHERE token_hash=?",
            (_token_hash(clean_token),),
        )
        connection.commit()
        return bool(cursor.rowcount)


__all__ = [
    "VERSION", "ACCOUNT_TTL_SECONDS", "GUEST_TTL_SECONDS",
    "issue_session", "restore_session", "revoke_session",
]
