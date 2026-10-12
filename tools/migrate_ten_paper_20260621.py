"""Idempotent migration/rollback utility for the ten-paper shadow schema."""
from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "canonical_runtime.sqlite3"
MIGRATION = ROOT / "migrations" / "20260621_ten_paper_shadow_layers.sql"
EXPECTED_COLUMNS = {
    "model_x_knockoff_feature_history": {"train_start", "train_end", "test_start", "test_end", "test_effect", "test_sample_support"},
    "flexible_loss_history": {"train_start", "train_end", "test_start", "test_end"},
    "provenance_node": {"natural_key", "payload_hash"},
}
COLUMN_DECLARATIONS = {
    "model_x_knockoff_feature_history": {
        "train_start": "TEXT", "train_end": "TEXT", "test_start": "TEXT", "test_end": "TEXT",
        "test_effect": "REAL", "test_sample_support": "INTEGER",
    },
    "flexible_loss_history": {
        "train_start": "TEXT", "train_end": "TEXT", "test_start": "TEXT", "test_end": "TEXT",
    },
    "provenance_node": {"natural_key": "TEXT", "payload_hash": "TEXT"},
}

EXPECTED_TABLES = {
    "model_x_knockoff_feature_history", "online_fdr_test_history", "online_fdr_state",
    "reject_option_history", "flexible_loss_history", "model_explanation_cache",
    "monotonicity_validation_history", "delta_maintenance_history", "exact_delta_state",
    "provenance_node", "provenance_edge", "metamorphic_test_history",
    "calm_operation_classification", "evidence_gate_history", "research_paper_run",
}


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup_database(db_path: Path) -> Path:
    backup = db_path.with_name(f"{db_path.name}.before_ten_paper_{timestamp()}.bak")
    if db_path.exists():
        source = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        target = sqlite3.connect(str(backup))
        try:
            source.backup(target)
        finally:
            target.close(); source.close()
    else:
        backup.touch()
    return backup


def verify(db_path: Path) -> tuple[bool, list[str]]:
    connection = sqlite3.connect(str(db_path))
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = sorted(EXPECTED_TABLES - tables)
        missing_columns: list[str] = []
        for table, required in EXPECTED_COLUMNS.items():
            if table not in tables:
                continue
            existing = {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}
            missing_columns.extend(f"{table}.{column}" for column in sorted(required - existing))
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        problems = missing + missing_columns + ([] if quick_check == "ok" else [f"quick_check={quick_check}"])
        return not problems, problems
    finally:
        connection.close()


def migrate(db_path: Path, make_backup: bool) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    backup = backup_database(db_path) if make_backup else None
    connection = sqlite3.connect(str(db_path), timeout=30)
    try:
        connection.executescript(MIGRATION.read_text(encoding="utf-8"))
        for table, additions in COLUMN_DECLARATIONS.items():
            existing = {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}
            for column, declaration in additions.items():
                if column not in existing:
                    connection.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {declaration}')
        connection.execute("PRAGMA user_version=20260621")
        connection.commit()
    except Exception:
        connection.rollback()
        if backup and backup.exists() and backup.stat().st_size:
            connection.close(); shutil.copy2(backup, db_path)
        raise
    finally:
        try: connection.close()
        except Exception: pass
    ok, problems = verify(db_path)
    print(f"Database: {db_path}")
    if backup: print(f"Backup: {backup}")
    print(f"Verification: {'PASS' if ok else 'FAIL'}")
    if problems: print("Problems: " + ", ".join(problems))
    return 0 if ok else 2


def rollback(db_path: Path, backup: Path) -> int:
    if not backup.exists() or backup.stat().st_size == 0:
        raise FileNotFoundError(f"Usable backup not found: {backup}")
    safety = db_path.with_name(f"{db_path.name}.before_rollback_{timestamp()}.bak")
    if db_path.exists(): shutil.copy2(db_path, safety)
    shutil.copy2(backup, db_path)
    connection = sqlite3.connect(str(db_path))
    try:
        check = connection.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        connection.close()
    print(f"Restored: {backup} -> {db_path}")
    print(f"Pre-rollback safety copy: {safety}")
    print(f"Quick check: {check}")
    return 0 if check == "ok" else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--backup", action="store_true", help="Create a consistent SQLite backup before migration.")
    parser.add_argument("--rollback", type=Path, help="Restore the named backup instead of migrating.")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    db = args.db.resolve()
    if args.rollback: return rollback(db, args.rollback.resolve())
    if args.verify_only:
        ok, problems = verify(db); print("PASS" if ok else "FAIL"); print("\n".join(problems)); return 0 if ok else 2
    return migrate(db, args.backup)


if __name__ == "__main__":
    raise SystemExit(main())
