from __future__ import annotations
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.h4_acceptance_workflow_20260706 import run_offline_h4_acceptance

if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "offline_h4_acceptance_20260706"
    result = run_offline_h4_acceptance(target)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    raise SystemExit(0 if result.get("ok") else 1)
