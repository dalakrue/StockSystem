"""Run every test file separately with the bounded fast research profile.

Separating files prevents a single long-lived Streamlit/import test from
obscuring progress. The script returns non-zero on failures or timeouts.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = sorted((ROOT / "tests").glob("test_*.py"))
LOG_DIR = ROOT / "reports" / "test_logs" / "all_files_20260621"
SUMMARY = ROOT / "reports" / "FAST_TEST_BATCH_SUMMARY_20260621.json"


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["ADX_TEST_PROFILE"] = "fast"
    rows = []
    started = time.perf_counter()
    for index, path in enumerate(TESTS, 1):
        relative = path.relative_to(ROOT).as_posix()
        print(f"[{index:02d}/{len(TESTS):02d}] {relative}", flush=True)
        t0 = time.perf_counter()
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", relative],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )
            status = "PASS" if completed.returncode == 0 else "FAIL"
            output = (completed.stdout or "") + (completed.stderr or "")
            returncode = completed.returncode
        except subprocess.TimeoutExpired as exc:
            status = "TIMEOUT"
            output = ((exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
            output += ((exc.stderr or b"").decode() if isinstance(exc.stderr, bytes) else (exc.stderr or ""))
            returncode = 124
        duration = time.perf_counter() - t0
        (LOG_DIR / f"{path.stem}.log").write_text(output, encoding="utf-8")
        rows.append({"file": relative, "status": status, "returncode": returncode, "duration_seconds": round(duration, 3), "tail": output[-500:]})
        print(f"    {status} {duration:.2f}s", flush=True)
    payload = {
        "python": sys.version,
        "test_profile": "fast",
        "file_count": len(rows),
        "pass_files": sum(r["status"] == "PASS" for r in rows),
        "fail_files": sum(r["status"] == "FAIL" for r in rows),
        "timeout_files": sum(r["status"] == "TIMEOUT" for r in rows),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "results": rows,
    }
    SUMMARY.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("file_count", "pass_files", "fail_files", "timeout_files", "duration_seconds")}, indent=2))
    return 0 if payload["fail_files"] == 0 and payload["timeout_files"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
