from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import sqlite3
import shutil

from core.history_evidence_store_20260620 import SPECS
from services.canonical_snapshot_store import DB_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description="Drop only additive 2026-06-20 history evidence objects.")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--confirm", action="store_true", help="Required when dropping additive tables")
    parser.add_argument("--restore-backup", action="store_true", help="Restore the byte-exact .before_history_20260620.bak database")
    args = parser.parse_args()
    path = Path(args.db)
    if args.restore_backup:
        backup = path.with_suffix(path.suffix + ".before_history_20260620.bak")
        if not backup.exists():
            raise FileNotFoundError(f"Rollback backup not found: {backup}")
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(path) + suffix)
            if sidecar.exists():
                sidecar.unlink()
        shutil.copy2(backup, path)
        print(f"Restored byte-exact canonical database backup: {backup} -> {path}")
        return 0
    if not args.confirm:
        print("No changes made. Use --restore-backup or re-run with --confirm after making a database backup.")
        return 2
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        conn.execute("BEGIN IMMEDIATE")
        for spec in SPECS:
            conn.execute(f'DROP TABLE IF EXISTS "{spec.name}"')
        conn.execute("DROP TABLE IF EXISTS history_catalog")
        conn.execute("DROP TABLE IF EXISTS history_watermarks")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print("Dropped only additive 2026-06-20 evidence tables. Canonical runs/snapshots remain intact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
