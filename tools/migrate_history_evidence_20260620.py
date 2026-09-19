from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import shutil
import sqlite3

from core.history_evidence_store_20260620 import SPECS, ensure_history_schema
from services.canonical_snapshot_store import DB_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the additive 2026-06-20 history evidence schema.")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--backup", action="store_true")
    args = parser.parse_args()
    path = Path(args.db)
    path.parent.mkdir(parents=True, exist_ok=True)
    if args.backup and path.exists():
        backup = path.with_suffix(path.suffix + ".before_history_20260620.bak")
        shutil.copy2(path, backup)
        print(f"Backup: {backup}")
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_history_schema(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f"Created/verified {len(SPECS)} additive history tables in {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
