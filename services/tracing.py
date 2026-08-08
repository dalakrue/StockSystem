"""Lightweight bounded process/run tracing."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import os, time
from typing import Any, MutableMapping

TRACE_KEY = "bounded_run_trace_20260619"
MAX_TRACE_ROWS = 120


def resources() -> dict[str, float | None]:
    try:
        import psutil
        p = psutil.Process(os.getpid())
        return {"process_rss_mb": round(p.memory_info().rss / 1024 / 1024, 3), "cpu_pct": round(p.cpu_percent(interval=None), 3)}
    except Exception:
        return {"process_rss_mb": None, "cpu_pct": None}


def record(state: MutableMapping[str, Any], *, run_id: Any, generation: Any, stage: str, started_at: str, ended_at: str, duration_ms: float, success: bool, rows_processed: int = 0, cache_status: str = "", detail: str = "") -> dict[str, Any]:
    row = {"run_id": run_id, "generation": generation, "stage": stage, "start_time": started_at, "end_time": ended_at, "duration_ms": round(duration_ms, 3), "success": bool(success), "rows_processed": int(rows_processed), "cache_status": cache_status, **resources(), "detail": str(detail)[:300]}
    rows = list(state.get(TRACE_KEY) or [])
    rows.append(row); state[TRACE_KEY] = rows[-MAX_TRACE_ROWS:]
    return row


@contextmanager
def trace_stage(state: MutableMapping[str, Any], stage: str, *, run_id: Any = None, generation: Any = None, rows_processed: int = 0, cache_status: str = ""):
    start_iso = datetime.now(timezone.utc).isoformat(); start = time.perf_counter(); error = ""
    try:
        yield
    except Exception as exc:
        error = repr(exc); raise
    finally:
        end_iso = datetime.now(timezone.utc).isoformat()
        record(state, run_id=run_id, generation=generation, stage=stage, started_at=start_iso, ended_at=end_iso, duration_ms=(time.perf_counter()-start)*1000, success=not error, rows_processed=rows_processed, cache_status=cache_status, detail=error)

__all__ = ["TRACE_KEY", "MAX_TRACE_ROWS", "resources", "record", "trace_stage"]
