"""Remove only the additive 2026-06-21 research-validation tables.

The rollback is intentionally explicit and requires --confirm. Back up the
SQLite file first. Existing canonical tables and snapshots are untouched.
"""
from __future__ import annotations

import argparse
import sys
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.research_validation_store_20260621 import SCHEMAS
from services.canonical_snapshot_store import DB_PATH


def rollback(db_path: Path, confirm: bool) -> None:
    if not confirm:
        raise SystemExit("Refusing destructive rollback without --confirm")
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = db_path.with_name(f"{db_path.name}.before_research_rollback_{stamp}.bak")
    shutil.copy2(db_path, backup)
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("BEGIN IMMEDIATE")
        for table in sorted(SCHEMAS):
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        conn.commit()
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if str(integrity).lower() != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: {integrity}")
        print(f"Rollback complete: {db_path}")
        print(f"Backup retained: {backup}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    rollback(args.db.resolve(), args.confirm)


if __name__ == "__main__":
    main()
