#!/usr/bin/env python3
"""Apply and verify the additive 2026-07-05 ADX Quant Pro migrations."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.complete_repair_20260705 import DEFAULT_DB_PATH, migrate_complete_repair_schema
from core.field11_similar_path_simulator_20260702 import DB_PATH as FIELD11_DB_PATH, migrate_field11_database


def table_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    with sqlite3.connect(path) as conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        counts: dict[str, int] = {}
        for table in tables:
            safe = table.replace('"', '""')
            try:
                counts[table] = int(conn.execute(f'SELECT COUNT(*) FROM "{safe}"').fetchone()[0])
            except sqlite3.DatabaseError:
                counts[table] = -1
        return counts


def integrity(path: Path) -> str:
    with sqlite3.connect(path) as conn:
        return str(conn.execute("PRAGMA integrity_check").fetchone()[0])


def run(main_db: Path, field11_db: Path) -> dict[str, Any]:
    before_main = table_counts(main_db)
    before_field11 = table_counts(field11_db)
    main_first = migrate_complete_repair_schema(main_db, create_backup=True)
    main_second = migrate_complete_repair_schema(main_db, create_backup=False)
    field11_first = migrate_field11_database(field11_db)
    field11_second = migrate_field11_database(field11_db)
    after_main = table_counts(main_db)
    after_field11 = table_counts(field11_db)
    preserved = all(after_main.get(name, -1) >= count for name, count in before_main.items() if count >= 0)
    preserved_field11 = all(after_field11.get(name, -1) >= count for name, count in before_field11.items() if count >= 0)
    return {
        "main_database": str(main_db),
        "field11_database": str(field11_db),
        "main_migration_first": main_first,
        "main_migration_second": main_second,
        "field11_migration_first": field11_first,
        "field11_migration_second": field11_second,
        "main_integrity_check": integrity(main_db),
        "field11_integrity_check": integrity(field11_db),
        "main_existing_rows_preserved": preserved,
        "field11_existing_rows_preserved": preserved_field11,
        "main_counts_before": before_main,
        "main_counts_after": after_main,
        "field11_counts_before": before_field11,
        "field11_counts_after": after_field11,
        "idempotent": bool(main_first.get("ok") and main_second.get("ok") and field11_first.get("ok") and field11_second.get("ok")),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--field11-db", type=Path, default=FIELD11_DB_PATH)
    parser.add_argument("--output", type=Path, default=Path("reports/database_migration_20260705.json"))
    args = parser.parse_args()
    report = run(args.main_db, args.field11_db)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["idempotent"] and report["main_integrity_check"] == "ok" and report["field11_integrity_check"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
