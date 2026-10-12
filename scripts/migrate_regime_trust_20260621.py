"""Initialize or safely migrate the regime-trust DuckDB sidecar.

Usage:
    python scripts/migrate_regime_trust_20260621.py
    python scripts/migrate_regime_trust_20260621.py --database data/custom.duckdb

The script never touches the protected canonical SQLite snapshot.  When a
legacy table is incompatible, the database is backed up, the table is renamed,
the current schema is created, and only matching columns are copied forward.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.regime_trust_store_20260621 import DB_PATH, RegimeTrustStore, TABLE_COLUMNS


def _columns(conn, table: str) -> list[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
    except Exception:
        return []
    return [str(row[1]) for row in rows]


def migrate(database: Path) -> dict[str, object]:
    database = database.resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if database.exists() and database.stat().st_size:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = database.with_suffix(database.suffix + f".bak-{stamp}")
        shutil.copy2(database, backup)

    # Open without invoking RegimeTrustStore first so incompatible legacy tables
    # can be renamed before CREATE TABLE IF NOT EXISTS is evaluated.
    import duckdb

    migrated: list[str] = []
    preserved: dict[str, int] = {}
    conn = duckdb.connect(str(database))
    try:
        conn.execute("BEGIN TRANSACTION")
        for table, expected_tuple in TABLE_COLUMNS.items():
            expected = list(expected_tuple)
            present = _columns(conn, table)
            if present and present != expected:
                legacy = f"{table}__legacy_20260621"
                suffix = 1
                existing = {str(row[0]) for row in conn.execute("SHOW TABLES").fetchall()}
                while legacy in existing:
                    suffix += 1
                    legacy = f"{table}__legacy_20260621_{suffix}"
                conn.execute(f'ALTER TABLE "{table}" RENAME TO "{legacy}"')
                migrated.append(table)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        conn.close()
        if backup and backup.exists():
            shutil.copy2(backup, database)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass

    store = RegimeTrustStore(database)
    conn = store.connect()
    try:
        tables = {str(row[0]) for row in conn.execute("SHOW TABLES").fetchall()}
        for table, expected_tuple in TABLE_COLUMNS.items():
            candidates = sorted(name for name in tables if name.startswith(f"{table}__legacy_20260621"))
            if not candidates:
                continue
            legacy = candidates[-1]
            old_columns = set(_columns(conn, legacy))
            common = [column for column in expected_tuple if column in old_columns]
            if common:
                cols = ",".join(f'"{column}"' for column in common)
                before = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                conn.execute(f'INSERT OR IGNORE INTO "{table}" ({cols}) SELECT {cols} FROM "{legacy}"')
                after = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                preserved[table] = max(0, after - before)
    finally:
        conn.close()

    return {
        "ok": True,
        "database": str(database),
        "backup": str(backup) if backup else None,
        "migrated_tables": migrated,
        "preserved_rows": preserved,
        "schema_tables": list(TABLE_COLUMNS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DB_PATH)
    args = parser.parse_args()
    result = migrate(args.database)
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
