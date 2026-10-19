#!/usr/bin/env python3
"""Back up, migrate, and verify the unified Field 10 SQLite database."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.multi_symbol_field10_20260701 import DB_PATH  # noqa: E402
from core.field10_unified_migration_20260703 import migrate_and_verify_field10  # noqa: E402


def sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Backup already exists: {destination}")
    with sqlite3.connect(str(source), timeout=30) as src, sqlite3.connect(str(destination), timeout=30) as dst:
        src.backup(dst)
        integrity = str(dst.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            raise RuntimeError(f"Backup integrity check failed: {integrity}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path(DB_PATH), help="Field 10 SQLite database")
    parser.add_argument("--backup", type=Path, default=None, help="Explicit backup destination")
    parser.add_argument("--no-backup", action="store_true", help="Skip backup only when an external verified backup already exists")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database = args.database.expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if database.exists() and not args.no_backup:
        backup = args.backup.expanduser().resolve() if args.backup else (
            ROOT / "backups" / f"{database.stem}.pre_crowd_final_20260704{database.suffix or '.sqlite3'}"
        )
        sqlite_backup(database, backup)

    report = migrate_and_verify_field10(database)
    output = {
        "ok": bool(report.get("ok")),
        "database": str(database),
        "backup": None if backup is None else str(backup),
        "migration": report,
    }
    print(json.dumps(output, indent=2, sort_keys=True, default=str))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
