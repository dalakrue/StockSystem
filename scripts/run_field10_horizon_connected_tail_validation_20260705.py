#!/usr/bin/env python3
"""Explicit heavy research-validation command for the Field 10 shadow candidate.

Requires deployment migration and readable exact-symbol runtime caches. It never
promotes the candidate or modifies the immutable parent daily snapshot.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.field10_research_common_20260705 import load_snapshot_contract
from core.field10_research_orchestrator_20260705 import publish_horizon_connected_tail_candidate
from core.multi_symbol_field10_20260701 import DB_PATH


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--snapshot-id", default=None)
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()
    meta, rows = load_snapshot_contract(args.snapshot_id, path=args.db)
    if not meta or not rows:
        report = {"ok": False, "status": "PARENT_SNAPSHOT_UNAVAILABLE"}
    else:
        symbols = args.symbols or [str(row.get("symbol") or "") for row in rows]
        report = publish_horizon_connected_tail_candidate(
            {}, daily_snapshot_id=str(meta.get("daily_snapshot_id") or ""),
            selected_symbols=symbols, path=args.db,
        )
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    print(text)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
