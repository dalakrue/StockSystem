"""Create the additive 2026-06-21 research-validation tables.

This migration is idempotent. It does not alter or delete existing tables.
"""
from __future__ import annotations

import argparse
import sys
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.research_validation_store_20260621 import SCHEMAS, ensure_schema
from services.canonical_snapshot_store import DB_PATH, connect


def migrate(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_schema(conn)
        conn.commit()
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if str(integrity).lower() != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: {integrity}")
        present = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = sorted(set(SCHEMAS) - present)
        if missing:
            raise RuntimeError(f"Migration incomplete; missing tables: {missing}")
        print(f"Migration complete: {db_path}")
        print(f"Added/verified {len(SCHEMAS)} additive tables; integrity_check=ok")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()
    migrate(args.db.resolve())


if __name__ == "__main__":
    main()
