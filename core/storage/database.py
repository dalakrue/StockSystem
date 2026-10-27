from pathlib import Path
import json
import tempfile
import shutil
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Optional

import pandas as pd


# -----------------------------------------------------------------------------
# Safe database layer for the whole Streamlit app.
# Keeps the original CSV/JSON behavior, but adds stronger validation, backups,
# SQLite event mirror, table browser helpers, pruning, and repair utilities.
# -----------------------------------------------------------------------------

# Store data beside the project files, not in whatever folder Streamlit was launched from.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "quant_app.sqlite3"
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

_MAX_SAFE_ROWS_DEFAULT = 250_000


def _safe_name(name: Any) -> str:
    safe_name = str(name or "default").strip()
    for bad in ["/", "\\", "..", ":", "*", "?", '"', "<", ">", "|", "\n", "\r", "\t"]:
        safe_name = safe_name.replace(bad, "_")
    safe_name = "_".join([x for x in safe_name.split("_") if x != ""])
    return safe_name or "default"


def _csv_path(name: Any) -> Path:
    return DATA_DIR / f"{_safe_name(name)}.csv"


def _json_path(name: Any) -> Path:
    return DATA_DIR / f"{_safe_name(name)}.json"


def _now_text() -> str:
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean_scalar(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp,)):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, (dict, list, tuple, set)):
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            return str(value)
    return value


def _clean_row(row: Any) -> Dict[str, Any]:
    if row is None:
        row = {}
    if not isinstance(row, dict):
        row = {"value": row}
    clean = {str(k or "value").strip() or "value": _clean_scalar(v) for k, v in row.items()}
    clean.setdefault("saved_at", _now_text())
    return clean


def _atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, encoding=encoding, suffix=path.suffix, dir=str(path.parent)) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    shutil.move(str(tmp_path), str(path))
    return True


@contextmanager
def _connect_sqlite():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30, check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT NOT NULL,
                saved_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_app_events_table_saved ON app_events(table_name, saved_at)")
        yield conn
        conn.commit()
    finally:
        conn.close()


def _sqlite_append(name: Any, row: Dict[str, Any]) -> bool:
    try:
        table_name = _safe_name(name)
        payload = json.dumps(row, ensure_ascii=False, default=str)
        with _connect_sqlite() as conn:
            conn.execute(
                "INSERT INTO app_events(table_name, saved_at, payload_json) VALUES (?, ?, ?)",
                (table_name, str(row.get("saved_at") or _now_text()), payload),
            )
        return True
    except Exception:
        return False


def append_csv(name: Any, row: Any) -> bool:
    """Append one row to CSV and mirror the same row into SQLite.

    Existing callers keep working exactly the same. Returns False instead of
    raising, so one broken row cannot crash the trading dashboard.
    """
    path = _csv_path(name)
    try:
        row = _clean_row(row)
        df = pd.DataFrame([row])
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, mode="a", index=False, header=not path.exists(), encoding="utf-8-sig")
        _sqlite_append(name, row)
        return True
    except Exception:
        return False


def append_event(name: Any, row: Any) -> bool:
    return append_csv(name, row)


def read_csv(name: Any, limit: Optional[int] = None) -> pd.DataFrame:
    path = _csv_path(name)
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except Exception:
        try:
            df = pd.read_csv(path)
        except Exception:
            return pd.DataFrame()
    if limit is not None:
        try:
            df = df.tail(int(limit)).reset_index(drop=True)
        except Exception:
            pass
    return df


def read_table(name: Any, limit: int = 1000, prefer_sqlite: bool = False) -> pd.DataFrame:
    """Read a logical app table from CSV or SQLite mirror."""
    table_name = _safe_name(name)
    if prefer_sqlite and DB_PATH.exists():
        try:
            with _connect_sqlite() as conn:
                raw = pd.read_sql_query(
                    "SELECT saved_at, payload_json FROM app_events WHERE table_name=? ORDER BY id DESC LIMIT ?",
                    conn,
                    params=(table_name, int(limit)),
                )
            if raw.empty:
                return pd.DataFrame()
            rows = []
            for _, r in raw.iloc[::-1].iterrows():
                item = json.loads(r.get("payload_json", "{}"))
                item.setdefault("saved_at", r.get("saved_at"))
                rows.append(item)
            return pd.DataFrame(rows)
        except Exception:
            pass
    return read_csv(table_name, limit=limit)


def overwrite_csv(name: Any, rows: Iterable[Dict[str, Any]]) -> bool:
    path = _csv_path(name)
    try:
        if rows is None:
            rows = []
        df = pd.DataFrame(list(rows))
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8-sig", suffix=".csv", dir=str(DATA_DIR)) as tmp:
            tmp_path = Path(tmp.name)
        df.to_csv(tmp_path, index=False, encoding="utf-8-sig")
        shutil.move(str(tmp_path), str(path))
        return True
    except Exception:
        return False


def save_json(name: Any, obj: Any) -> bool:
    path = _json_path(name)
    try:
        text = json.dumps(obj, indent=2, default=str, ensure_ascii=False)
        return _atomic_write_text(path, text, encoding="utf-8")
    except Exception:
        return False


def load_json(name: Any, default: Any = None) -> Any:
    path = _json_path(name)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def delete_data_file(name: Any, file_type: str = "csv") -> bool:
    try:
        file_type = str(file_type or "csv").lower().strip()
        path = _json_path(name) if file_type == "json" else _csv_path(name)
        if path.exists():
            backup_file(path)
            path.unlink()
        return True
    except Exception:
        return False


def backup_file(path: Path) -> Optional[Path]:
    try:
        if not path.exists() or not path.is_file():
            return None
        stamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        out = BACKUP_DIR / f"{path.stem}_{stamp}{path.suffix}"
        shutil.copy2(path, out)
        return out
    except Exception:
        return None


def backup_all_data() -> Optional[Path]:
    try:
        stamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        out = BACKUP_DIR / f"quant_data_backup_{stamp}"
        out.mkdir(parents=True, exist_ok=True)
        for p in DATA_DIR.glob("*"):
            if p.is_file() and p.suffix.lower() in [".csv", ".json", ".sqlite3", ".db"]:
                shutil.copy2(p, out / p.name)
        return out
    except Exception:
        return None


def list_data_files() -> pd.DataFrame:
    try:
        files = []
        for p in sorted(DATA_DIR.glob("*")):
            if not p.is_file():
                continue
            if p.suffix.lower() not in [".csv", ".json", ".sqlite3", ".db"]:
                continue
            stat = p.stat()
            rows = None
            cols = None
            if p.suffix.lower() == ".csv":
                try:
                    sample = pd.read_csv(p, encoding="utf-8-sig", nrows=5)
                    cols = len(sample.columns)
                    # Fast row estimate without fully loading massive file.
                    with p.open("rb") as f:
                        rows = max(0, sum(1 for _ in f) - 1)
                except Exception:
                    rows = None
            files.append({
                "name": p.name,
                "table": p.stem,
                "type": p.suffix.replace(".", "").upper(),
                "rows_est": rows,
                "columns": cols,
                "size_kb": round(stat.st_size / 1024, 2),
                "modified": pd.Timestamp.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })
        return pd.DataFrame(files)
    except Exception:
        return pd.DataFrame()


def list_tables() -> pd.DataFrame:
    files = list_data_files()
    if files.empty:
        return files
    return files[files["type"].isin(["CSV", "JSON", "SQLITE3", "DB"])].reset_index(drop=True)


def database_health() -> Dict[str, Any]:
    files = list_data_files()
    total_size = float(files["size_kb"].sum()) if not files.empty and "size_kb" in files else 0.0
    csv_count = int((files["type"] == "CSV").sum()) if not files.empty and "type" in files else 0
    json_count = int((files["type"] == "JSON").sum()) if not files.empty and "type" in files else 0
    sqlite_ok = False
    sqlite_rows = 0
    try:
        with _connect_sqlite() as conn:
            sqlite_ok = True
            sqlite_rows = int(conn.execute("SELECT COUNT(*) FROM app_events").fetchone()[0])
    except Exception:
        sqlite_ok = False
    return {
        "data_dir": str(DATA_DIR.resolve()),
        "files": int(len(files)) if files is not None else 0,
        "csv_files": csv_count,
        "json_files": json_count,
        "total_size_kb": round(total_size, 2),
        "sqlite_path": str(DB_PATH),
        "sqlite_ok": sqlite_ok,
        "sqlite_event_rows": sqlite_rows,
        "checked_at": _now_text(),
    }


def compact_csv(name: Any, keep_last: int = _MAX_SAFE_ROWS_DEFAULT) -> bool:
    """Keep only the latest N rows of a CSV table after creating a backup."""
    try:
        keep_last = max(100, int(keep_last))
        path = _csv_path(name)
        if not path.exists():
            return True
        df = read_csv(name)
        if len(df) <= keep_last:
            return True
        backup_file(path)
        df.tail(keep_last).to_csv(path, index=False, encoding="utf-8-sig")
        return True
    except Exception:
        return False


def repair_csv(name: Any) -> bool:
    """Attempt to read and rewrite a CSV cleanly. Creates backup first."""
    try:
        path = _csv_path(name)
        if not path.exists():
            return True
        backup_file(path)
        df = read_csv(name)
        if df.empty:
            return False
        df.to_csv(path, index=False, encoding="utf-8-sig")
        return True
    except Exception:
        return False


def export_all_to_excel(output_path: Optional[str] = None) -> Optional[str]:
    try:
        if output_path is None:
            stamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
            output_path = str(DATA_DIR / f"database_export_{stamp}.xlsx")
        files = list_data_files()
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            files.to_excel(writer, index=False, sheet_name="index")
            for _, row in files.iterrows():
                if row.get("type") != "CSV":
                    continue
                table = str(row.get("table"))
                df = read_csv(table, limit=5000)
                sheet = table[:31] or "table"
                df.to_excel(writer, index=False, sheet_name=sheet)
        return output_path
    except Exception:
        return None


def file_exists(name: Any, file_type: str = "csv") -> bool:
    file_type = str(file_type or "csv").lower().strip()
    path = _json_path(name) if file_type == "json" else _csv_path(name)
    return path.exists()


def clear_all_data() -> bool:
    try:
        backup_all_data()
        for p in DATA_DIR.glob("*"):
            if p.is_file() and p.suffix.lower() in [".csv", ".json"]:
                p.unlink()
        return True
    except Exception:
        return False


# -----------------------------------------------------------------------------
# 2026 relationship/database upgrade helpers
# These functions are additive. Existing CSV/JSON callers continue to work.
# -----------------------------------------------------------------------------
def append_rows_csv(name: Any, rows: Iterable[Dict[str, Any]]) -> int:
    """Append many rows safely and mirror them into SQLite.

    Returns the number of successfully appended rows.  This is useful for tabs
    that need to save a batch without reimplementing CSV logic.
    """
    saved = 0
    try:
        for row in rows or []:
            if append_csv(name, row):
                saved += 1
    except Exception:
        pass
    return saved


def save_market_cache(df: pd.DataFrame, name: Any = "latest_market_cache", max_rows: int = 5000) -> bool:
    """Persist the current shared market dataframe as a compact cache CSV."""
    try:
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return False
        max_rows = max(100, int(max_rows or 5000))
        out = df.tail(max_rows).copy()
        path = _csv_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(path, index=False, encoding="utf-8-sig")
        append_csv("database_events", {"event": "save_market_cache", "table": _safe_name(name), "rows": len(out)})
        return True
    except Exception:
        return False


def load_market_cache(name: Any = "latest_market_cache", limit: Optional[int] = None) -> pd.DataFrame:
    return read_csv(name, limit=limit)


def vacuum_sqlite() -> bool:
    try:
        with _connect_sqlite() as conn:
            conn.execute("VACUUM")
        return True
    except Exception:
        return False


def database_relationship_summary() -> Dict[str, Any]:
    """Return one compact backend/database health object for UI diagnostics."""
    health = database_health()
    files = list_data_files()
    latest_csv = ""
    latest_modified = ""
    try:
        if not files.empty and "modified" in files.columns:
            newest = files.sort_values("modified", ascending=False).iloc[0]
            latest_csv = str(newest.get("name", ""))
            latest_modified = str(newest.get("modified", ""))
    except Exception:
        pass
    health.update({
        "latest_file": latest_csv,
        "latest_modified": latest_modified,
        "append_api": "append_csv + append_rows_csv",
        "cache_api": "save_market_cache/load_market_cache",
        "backup_dir": str(BACKUP_DIR.resolve()),
    })
    return health


def migrate_field10_database_20260704(path: Path | str | None = None) -> Dict[str, Any]:
    """Storage-layer entry point for the additive Field 10 evidence migration."""
    from core.field10_unified_migration_20260703 import migrate_and_verify_field10
    from core.multi_symbol_field10_20260701 import DB_PATH as FIELD10_DB_PATH

    return migrate_and_verify_field10(path or FIELD10_DB_PATH)


def field10_database_health_20260704(path: Path | str | None = None) -> Dict[str, Any]:
    """Return integrity/FK/schema status without exposing credentials or row payloads."""
    from core.field10_unified_migration_20260703 import MIGRATION_VERSION
    from core.multi_symbol_field10_20260701 import DB_PATH as FIELD10_DB_PATH

    db_path = Path(path or FIELD10_DB_PATH)
    if not db_path.exists():
        return {"ok": False, "status": "DATABASE_NOT_FOUND", "path": str(db_path),
                "migration_version": MIGRATION_VERSION}
    try:
        with sqlite3.connect(str(db_path), timeout=30) as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
            foreign_key_issues = int(len(conn.execute("PRAGMA foreign_key_check").fetchall()))
            migration_rows = 0
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='field10_schema_migration_audit_20260703'"
            ).fetchone():
                migration_rows = int(conn.execute(
                    "SELECT COUNT(*) FROM field10_schema_migration_audit_20260703 WHERE migration_version=?",
                    (MIGRATION_VERSION,),
                ).fetchone()[0])
        return {
            "ok": integrity.lower() == "ok" and foreign_key_issues == 0 and migration_rows > 0,
            "status": "PASS" if integrity.lower() == "ok" and foreign_key_issues == 0 and migration_rows > 0 else "CHECK",
            "path": str(db_path), "integrity_check": integrity,
            "foreign_key_issue_count": foreign_key_issues,
            "migration_version": MIGRATION_VERSION, "migration_audit_rows": migration_rows,
        }
    except Exception as exc:
        return {"ok": False, "status": "ERROR", "path": str(db_path),
                "migration_version": MIGRATION_VERSION, "error": type(exc).__name__}
