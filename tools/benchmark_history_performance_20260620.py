"""Reproducible local performance benchmark for the 2026-06-20 upgrade.

The closed-Lunch before/after comparison is a controlled dispatch benchmark: the
same deterministic DataFrame workload is injected into every renderer slot. It
measures work caused by UI structure, not live market/API latency. Other sections
measure the real new history pipeline, SQLite projection, M4 payload, allocations
and RSS using synthetic completed EURUSD H1 data.
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
import tracemalloc
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import psutil

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ORIGINAL = ROOT.parent / "originals" / "lunch_four_core_fields_20260619.py"
OUTPUT = ROOT / "PERFORMANCE_MEASUREMENTS_20260620_HISTORY_FIRST.json"


class _Context:
    def __enter__(self): return self
    def __exit__(self, *args): return False


class _Column:
    def metric(self, *args, **kwargs): return None


class FakeStreamlit:
    def __init__(self, open_key: str | None = None, workspace: str = "4A — Similar-Day, Pattern Intelligence + All Current Data"):
        self.session_state: dict[str, Any] = {}
        self.open_key = open_key
        self.workspace = workspace
    def markdown(self, *args, **kwargs): return None
    def caption(self, *args, **kwargs): return None
    def info(self, *args, **kwargs): return None
    def warning(self, *args, **kwargs): return None
    def error(self, *args, **kwargs): return None
    def code(self, *args, **kwargs): return None
    def expander(self, *args, **kwargs): return _Context()
    def columns(self, n, *args, **kwargs):
        count = n if isinstance(n, int) else len(n)
        return [_Column() for _ in range(count)]
    def toggle(self, *args, **kwargs): return kwargs.get("key") == self.open_key
    def radio(self, *args, **kwargs): return self.workspace
    def selectbox(self, label, options, *args, **kwargs): return options[0]
    def button(self, *args, **kwargs): return False


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _workload_factory(counter: dict[str, int], name: str):
    base = pd.DataFrame({
        "x": np.arange(40_000, dtype=np.int32),
        "y": np.sin(np.arange(40_000, dtype=np.float64) / 17.0),
    })
    def work(*args, **kwargs):
        counter[name] = counter.get(name, 0) + 1
        projected = base[["x", "y"]].copy(deep=False)
        _ = projected["y"].rolling(24, min_periods=1).mean().iloc[-1]
        return None
    return work


def _patch_renderer_slots(module, counter: dict[str, int]):
    names = (
        "_render_medium_standard_bias", "_render_full_metric_history", "_render_powerbi",
        "_render_regime_history", "_render_current_data", "_render_regime_combined_logic",
        "_render_ai_assistant_lazy", "_render_workspace_4a", "_render_workspace_4b",
    )
    for name in names:
        if hasattr(module, name):
            setattr(module, name, _workload_factory(counter, name))


def _measure(callable_, iterations: int = 20) -> dict[str, Any]:
    process = psutil.Process()
    rss_before = process.memory_info().rss
    tracemalloc.start()
    started = time.perf_counter()
    for _ in range(iterations):
        callable_()
    duration = time.perf_counter() - started
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss_after = process.memory_info().rss
    return {
        "iterations": iterations,
        "total_ms": round(duration * 1000, 3),
        "mean_ms": round(duration * 1000 / iterations, 3),
        "python_peak_bytes": int(peak),
        "rss_before_mb": round(rss_before / 1024 / 1024, 3),
        "rss_after_mb": round(rss_after / 1024 / 1024, 3),
        "rss_delta_mb": round((rss_after - rss_before) / 1024 / 1024, 3),
    }


def benchmark_lunch_dispatch() -> dict[str, Any]:
    fake_similar = SimpleNamespace(render_similar_day_intelligence=lambda *a, **k: None)
    fake_browser = SimpleNamespace(render_history_evidence_browser=lambda *a, **k: None)
    sys.modules["ui.similar_day_renderer_20260619"] = fake_similar
    sys.modules["ui.history_evidence_browser_20260620"] = fake_browser

    before = _load(ORIGINAL, "_benchmark_lunch_before")
    before_counter: dict[str, int] = {}
    before.st = FakeStreamlit()
    _patch_renderer_slots(before, before_counter)
    # Similar-Day was imported inside the original field body; inject the same workload.
    fake_similar.render_similar_day_intelligence = _workload_factory(before_counter, "similar_day_renderer")
    before_result = _measure(lambda: before.render_lunch_six_core_fields(state={}), iterations=25)
    before_result["heavy_renderer_calls"] = int(sum(before_counter.values()))
    before_result["calls_per_rerun"] = round(sum(before_counter.values()) / 25, 3)

    after = _load(ROOT / "ui" / "lunch_four_core_fields_20260619.py", "_benchmark_lunch_after")
    after_counter: dict[str, int] = {}
    after.st = FakeStreamlit()
    _patch_renderer_slots(after, after_counter)
    after_result = _measure(lambda: after.render_lunch_six_core_fields(state={}), iterations=25)
    after_result["heavy_renderer_calls"] = int(sum(after_counter.values()))
    after_result["calls_per_rerun"] = round(sum(after_counter.values()) / 25, 3)

    fields: dict[str, Any] = {}
    for label, key, workspace in (
        ("Field 1", "lunch_gate_field1_20260620", "4A — Similar-Day, Pattern Intelligence + All Current Data"),
        ("Field 2", "lunch_gate_field2_20260620", "4A — Similar-Day, Pattern Intelligence + All Current Data"),
        ("Field 3", "lunch_gate_field3_20260620", "4A — Similar-Day, Pattern Intelligence + All Current Data"),
        ("Field 4A", "lunch_gate_field45_20260620", "4A — Similar-Day, Pattern Intelligence + All Current Data"),
        ("Field 4B", "lunch_gate_field45_20260620", "4B — Regime Summary + Combined Logic"),
        ("Field 6", "lunch_gate_field6_20260620", "4A — Similar-Day, Pattern Intelligence + All Current Data"),
    ):
        counter: dict[str, int] = {}
        after.st = FakeStreamlit(open_key=key, workspace=workspace)
        _patch_renderer_slots(after, counter)
        result = _measure(lambda: after.render_lunch_six_core_fields(state={}), iterations=10)
        result["calls_per_rerun"] = round(sum(counter.values()) / 10, 3)
        fields[label] = result
    return {"before_closed": before_result, "after_closed": after_result, "after_individual_fields": fields}


def synthetic_fixture():
    idx = pd.date_range("2026-05-01", periods=720, freq="h", tz="UTC")
    rng = np.random.default_rng(20)
    close = 1.15 + np.cumsum(np.sin(np.arange(len(idx)) / 15) * 1e-5 + rng.normal(0, 2e-5, len(idx)))
    frame = pd.DataFrame({"time": idx, "open": close-1e-5, "high": close+6e-5, "low": close-6e-5, "close": close})
    canonical = {
        "canonical_calculation_id": "BENCH-CALC", "run_id": "BENCH-RUN", "calculation_generation": 1,
        "symbol": "EURUSD", "timeframe": "H1", "source": "BENCHMARK",
        "latest_completed_candle_time": idx[-1].isoformat(), "data_signature": "bench-signature",
        "final_decision": {"final_decision": "WAIT", "directional_market_view": "BUY"},
        "regime": {"major_regime": "BULL_NORMAL", "alpha": 1.2, "delta": .2, "reliability": 74},
        "forecasts": {"horizons": {f"{h}h": {"horizon_hours": h, "point_forecast": float(close[-1]+h*1e-5), "lower_bound": float(close[-1]-7e-5), "upper_bound": float(close[-1]+7e-5)} for h in range(1,7)}},
        "reliability": {"score": 74}, "data_quality": {"score": 99}, "master_score": 5.4,
    }
    priority = pd.DataFrame([{"Time": idx[-1], "Priority Score": 81, "Priority": "A"}])
    paths = {
        "red": pd.DataFrame({"red_path": close[-1] + np.arange(1,7)*1e-5}),
        "yellow": pd.DataFrame({"yellow_path": close[-1] + np.arange(1,7)*2e-5}),
        "blue": pd.DataFrame({"blue_path": close[-1] + np.arange(1,7)*.5e-5}),
    }
    return canonical, frame, priority, paths


def benchmark_pipeline_db_and_payload() -> dict[str, Any]:
    from core.history_research_pipeline_20260620 import build_history_research_transaction
    from core.history_evidence_store_20260620 import append_history_bundle, export_history, query_history
    from core.research_evidence_algorithms_20260620 import m4_downsample
    canonical, frame, priority, paths = synthetic_fixture()
    process = psutil.Process(); rss_before = process.memory_info().rss
    tracemalloc.start(); started = time.perf_counter()
    _, bundle, summary = build_history_research_transaction(canonical, completed_h1=frame, priority_table=priority, calibrated_bundle=paths)
    pipeline_ms = (time.perf_counter()-started)*1000
    _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    rss_after = process.memory_info().rss
    db = Path(tempfile.mkdtemp()) / "benchmark.sqlite3"
    started = time.perf_counter(); append_history_bundle(bundle, db_path=db); write_ms = (time.perf_counter()-started)*1000
    query_times = {}
    for rows in (48, 120):
        started = time.perf_counter(); data = query_history("similar_day_outcome_history", limit=rows, db_path=db); elapsed=(time.perf_counter()-started)*1000
        query_times[str(rows)] = {"ms": round(elapsed,3), "rows": len(data), "csv_payload_bytes": len(data.to_csv(index=False).encode())}
    started=time.perf_counter(); full=export_history("similar_day_outcome_history",db_path=db); full_ms=(time.perf_counter()-started)*1000

    points = pd.DataFrame({"time": pd.date_range("2025-01-01", periods=10_000, freq="h", tz="UTC"), "value": np.sin(np.arange(10_000)/19)})
    raw_bytes = len(points.to_json(orient="records", date_format="iso").encode())
    started=time.perf_counter(); display=m4_downsample(points,x_col="time",y_col="value",max_points=400); m4_ms=(time.perf_counter()-started)*1000
    display_bytes=len(display.to_json(orient="records",date_format="iso").encode())
    return {
        "history_research_transaction": {
            "duration_ms": round(pipeline_ms,3), "rows_prepared": summary["total_rows"],
            "python_peak_bytes": int(summary.get("python_peak_bytes", peak)), "rss_delta_mb": round((rss_after-rss_before)/1024/1024,3),
            "cache_diagnostics": summary.get("cache", {}),
        },
        "sqlite": {"atomic_write_ms": round(write_ms,3), "bounded_queries": query_times, "full_export_query_ms": round(full_ms,3), "full_export_rows":len(full)},
        "m4_plot_payload": {
            "raw_rows": len(points), "display_rows": len(display), "raw_bytes": raw_bytes,
            "display_bytes": display_bytes, "reduction_pct": round((1-display_bytes/raw_bytes)*100,3), "aggregation_ms": round(m4_ms,3),
        },
    }


def main() -> int:
    result = {
        "measurement_scope": "Local synthetic completed-H1 workload; no live API/network latency and no browser DOM profiler.",
        "python": sys.version,
        "lunch_dispatch": benchmark_lunch_dispatch(),
        "pipeline_database_payload": benchmark_pipeline_db_and_payload(),
        "limitations": [
            "Settings full calculation time cannot be reproduced without the user's authenticated market connector and exact live input generation.",
            "Closed-Lunch before/after uses identical injected renderer work to isolate UI dispatch behavior.",
            "RSS is process-level and may retain allocator pages after a benchmark phase.",
        ],
    }
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
