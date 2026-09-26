"""Small encrypted credential vault for local/restart persistence.

Streamlit Cloud users should still prefer ``st.secrets`` because redeployments
may replace the local filesystem. The vault is never used as a cache key and
never returns secret material in status reports.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import os
import sqlite3
import tempfile

from cryptography.fernet import Fernet, InvalidToken

from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH, migrate_deployment_schema

ROOT = Path(__file__).resolve().parents[2]
VAULT_DIR = ROOT / "data" / ".credential_vault"
KEY_PATH = VAULT_DIR / "vault.key"
DATA_PATH = VAULT_DIR / "credentials.enc"


def _chmod_private(path: Path) -> None:
    try:
        path.chmod(0o600)
    except Exception:
        pass


def _fernet() -> Fernet:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    if not KEY_PATH.exists():
        temp = KEY_PATH.with_suffix(".tmp")
        temp.write_bytes(Fernet.generate_key())
        _chmod_private(temp)
        os.replace(temp, KEY_PATH)
    _chmod_private(KEY_PATH)
    return Fernet(KEY_PATH.read_bytes().strip())


def _read_all() -> dict[str, str]:
    if not DATA_PATH.exists():
        return {}
    try:
        raw = _fernet().decrypt(DATA_PATH.read_bytes())
        data = json.loads(raw.decode("utf-8"))
        return {str(k): str(v) for k, v in data.items() if str(v)} if isinstance(data, dict) else {}
    except (InvalidToken, ValueError, OSError, json.JSONDecodeError):
        return {}


def _write_all(values: dict[str, str]) -> None:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    encrypted = _fernet().encrypt(json.dumps(values, sort_keys=True).encode("utf-8"))
    fd, name = tempfile.mkstemp(prefix="credentials-", suffix=".tmp", dir=str(VAULT_DIR))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encrypted)
            handle.flush()
            os.fsync(handle.fileno())
        temp = Path(name)
        _chmod_private(temp)
        os.replace(temp, DATA_PATH)
        _chmod_private(DATA_PATH)
    finally:
        try:
            Path(name).unlink(missing_ok=True)
        except Exception:
            pass


def credential_fingerprint(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16] if value else ""


def save_credential(provider: str, value: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    provider = str(provider or "").strip().upper()
    value = str(value or "").strip()
    if not provider or not value:
        return {"ok": False, "provider": provider, "status": "EMPTY_CREDENTIAL"}
    values = _read_all()
    values[provider] = value
    _write_all(values)
    path = Path(db_path or DEFAULT_DB_PATH)
    migrate_deployment_schema(path)
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(path), timeout=10) as conn:
        conn.execute(
            """INSERT INTO api_connection_state(provider,configured,connected,secret_fingerprint,last_status,updated_at)
               VALUES(?,1,0,?,'CONFIGURED',?)
               ON CONFLICT(provider) DO UPDATE SET configured=1,
               secret_fingerprint=excluded.secret_fingerprint,last_status='CONFIGURED',updated_at=excluded.updated_at""",
            (provider, credential_fingerprint(value), now),
        )
        conn.commit()
    return {"ok": True, "provider": provider, "status": "SAVED", "fingerprint": credential_fingerprint(value)}


def load_credential(provider: str) -> str:
    return _read_all().get(str(provider or "").strip().upper(), "")


def delete_credential(provider: str, *, db_path: str | Path | None = None) -> None:
    name = str(provider or "").strip().upper()
    values = _read_all()
    values.pop(name, None)
    _write_all(values)
    path = Path(db_path or DEFAULT_DB_PATH)
    migrate_deployment_schema(path)
    with sqlite3.connect(str(path), timeout=10) as conn:
        conn.execute(
            "UPDATE api_connection_state SET configured=0,connected=0,last_status='DISCONNECTED',updated_at=? WHERE provider=?",
            (datetime.now(timezone.utc).isoformat(), name),
        )
        conn.commit()


def mark_connection(
    provider: str,
    *,
    connected: bool,
    status: str,
    error_code: str = "",
    configured: bool | None = None,
    db_path: str | Path | None = None,
) -> None:
    """Persist connection health without assuming the key lives in the vault.

    Streamlit Secrets are intentionally not copied into the encrypted local
    vault. Therefore a provider can be configured and validated even when
    ``load_credential`` is empty.
    """
    name = str(provider or "").strip().upper()
    path = Path(db_path or DEFAULT_DB_PATH)
    migrate_deployment_schema(path)
    now = datetime.now(timezone.utc).isoformat()
    is_configured = bool(connected) if configured is None else bool(configured)
    if configured is None and not is_configured:
        is_configured = bool(load_credential(name))
    with sqlite3.connect(str(path), timeout=10) as conn:
        conn.execute(
            """INSERT INTO api_connection_state(
                   provider,configured,connected,last_success_at,last_failure_at,
                   last_status,last_error_code,updated_at
               ) VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(provider) DO UPDATE SET
                   configured=excluded.configured,
                   connected=excluded.connected,
                   last_success_at=CASE WHEN excluded.connected=1 THEN excluded.last_success_at ELSE api_connection_state.last_success_at END,
                   last_failure_at=CASE WHEN excluded.connected=0 THEN excluded.last_failure_at ELSE api_connection_state.last_failure_at END,
                   last_status=excluded.last_status,
                   last_error_code=excluded.last_error_code,
                   updated_at=excluded.updated_at""",
            (
                name, int(is_configured), int(bool(connected)),
                now if connected else None, None if connected else now,
                str(status)[:120], str(error_code)[:120], now,
            ),
        )
        conn.commit()


def restore_into_state(state: Any) -> dict[str, bool]:
    mappings = {
        "TWELVE_DATA_KEY_1": "twelve_api_key_1",
        "TWELVE_DATA": "twelve_api_key",
        "TWELVE_DATA_KEY_2": "twelve_api_key_2",
        "FINNHUB": "finnhub_api_key",
        "ALPHA_VANTAGE": "alpha_vantage_api_key",
        "FRED": "fred_api_key",
    }
    restored: dict[str, bool] = {}
    for provider, key in mappings.items():
        if str(state.get(key) or "").strip():
            restored[provider] = False
            continue
        value = load_credential(provider)
        if value:
            state[key] = value
            state[f"{key}_source"] = "vault"
            restored[provider] = True
        else:
            restored[provider] = False
    return restored


def status(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    path = Path(db_path or DEFAULT_DB_PATH)
    migrate_deployment_schema(path)
    with sqlite3.connect(str(path), timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM api_connection_state ORDER BY provider").fetchall()
    return [dict(row) for row in rows]


__all__ = [
    "save_credential", "load_credential", "delete_credential", "mark_connection",
    "restore_into_state", "status", "credential_fingerprint",
]
