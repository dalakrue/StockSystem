"""Headless, reproducible performance measurements for the six-field upgrade.

The harness never contacts a connector and never starts the protected
calculation transaction. It measures pure/service paths available in CI and
labels live Streamlit-only actions explicitly.
"""
from __future__ import annotations

import ast
import gc
import importlib.util
import json
import os
import py_compile
import statistics
import sys
import time
import tracemalloc
import types
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import psutil

ROOT = Path(__file__).resolve().parents[1]
ORIGINALS = ROOT.parent / "originals"
OUT = ROOT / "PERFORMANCE_MEASUREMENTS_20260621_SIX_FIELD.json"


@dataclass
class Measurement:
    action: str
    variant: str
    status: str
    wall_ms: float | None
    cpu_ms: float | None
    peak_alloc_kib: float | None
    rss_delta_kib: float | None
    notes: str = ""


def measure(action: str, variant: str, fn: Callable[[], Any], repeats: int = 5, notes: str = "") -> tuple[Measurement, Any]:
    proc = psutil.Process(os.getpid())
    walls: list[float] = []
    cpus: list[float] = []
    peaks: list[float] = []
    rss_deltas: list[float] = []
    result: Any = None
    for _ in range(max(1, repeats)):
        gc.collect()
        before_rss = proc.memory_info().rss
        tracemalloc.start()
        cpu0 = time.process_time()
        wall0 = time.perf_counter()
        result = fn()
        walls.append((time.perf_counter() - wall0) * 1000)
        cpus.append((time.process_time() - cpu0) * 1000)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        after_rss = proc.memory_info().rss
        peaks.append(peak / 1024)
        rss_deltas.append((after_rss - before_rss) / 1024)
    return Measurement(
        action=action,
        variant=variant,
        status="MEASURED_HEADLESS",
        wall_ms=round(statistics.median(walls), 4),
        cpu_ms=round(statistics.median(cpus), 4),
        peak_alloc_kib=round(max(peaks), 2),
        rss_delta_kib=round(max(rss_deltas), 2),
        notes=notes,
    ), result


def not_measured(action: str, variant: str, notes: str) -> Measurement:
    return Measurement(action, variant, "NOT_MEASURED_LIVE", None, None, None, None, notes)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_streamlit() -> types.ModuleType:
    module = types.ModuleType("streamlit")
    module.session_state = {}
    module.fragment = lambda f: f
    module.cache_data = lambda *a, **k: (lambda f: f) if not (a and callable(a[0])) else a[0]
    module.cache_resource = module.cache_data
    module.rerun = lambda: None
    return module


def fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], pd.DataFrame]:
    rng = np.random.default_rng(20260621)
    end = pd.Timestamp("2026-06-21T05:00:00Z")
    times = pd.date_range(end=end, periods=1200, freq="h", tz="UTC")
    close = 1.16 + np.cumsum(rng.normal(0, 0.00018, len(times)))
    history = pd.DataFrame({
        "time": times,
        "open": np.r_[close[0], close[:-1]],
        "high": close + 0.0002,
        "low": close - 0.0002,
        "close": close,
        "regime": np.where(np.arange(len(times)) % 2, "BULL_NORMAL", "BEAR_NORMAL"),
        "reliability": rng.uniform(50, 90, len(times)),
        "decision": np.where(np.arange(len(times)) % 3, "WAIT", "BUY"),
        **{f"unused_metric_{i}": rng.normal(size=len(times)) for i in range(45)},
    })
    canonical: dict[str, Any] = {
        "schema_version": "2026.06.21",
        "run_id": "run-six-field-20260621",
        "canonical_calculation_id": "calc-six-field-20260621",
        "calculation_generation": 77,
        "checksum": "fixture-checksum",
        "symbol": "EURUSD",
        "timeframe": "H1",
        "latest_completed_candle_time": end.isoformat(),
        "last_close": float(close[-1]),
        "final_decision": {
            "final_decision": "WAIT", "less_risky_decision": "WAIT", "directional_market_view": "BUY",
            "selected_horizon": 6, "supporting_reasons": ["Regime is constructive", "Forecast paths agree", "Risk gate remains conservative"],
            "blocking_reasons": ["Entry score below protected threshold"], "conflict_warning": "No material conflict",
            "error_estimate_pct": 0.08, "decision_expiry_time": "2026-06-21T06:00:00Z",
        },
        "regime": {"major_regime": "BULL_NORMAL", "reliability": 72.4, "start_time": "2026-06-20T18:00:00Z"},
        "forecasts": {"horizons": {"6h": {"direction": "BUY", "lower_bound": 1.1580, "upper_bound": 1.1640, "confidence": 69.0}}},
        "data_quality": {"freshness": "CURRENT"},
        "large_history": history,
        "nested_payload": {f"series_{i}": history[["time", "close"]] for i in range(6)},
    }
    summary = {
        "calculation_id": "calc-six-field-20260621",
        "identity": {"symbol": "EURUSD", "timeframe": "H1", "run_id": canonical["run_id"], "calculation_generation": 77, "latest_completed_candle_time": end.isoformat()},
        "decision": {"current_decision": "WAIT", "less_risky_bias": "WAIT", "main_reason": "Protected entry threshold is not met", "conflict_status": "NONE"},
        "scores": {"master": 6.4, "entry": 5.8, "hold": 6.1, "tp": 5.9, "exit_risk": 4.2},
        "priority": {"opportunity_quality": "WATCH", "current_rank": 5, "knn_priority": 66},
        "regime": {"directional_regime": "BULL_NORMAL", "regime_reliability": 72.4},
        "uncertainty": {"combined": 28.0, "error_estimate_pct": 0.08},
        "projection": {"current_close": float(close[-1]), "direction": "BUY", "selected_horizon": 6, "lower_band": 1.1580, "upper_band": 1.1640},
        "validation": {"data_freshness": "CURRENT", "stale_status": "CURRENT"},
    }
    plan = {"status": "WARNING", "recommended_lots": 0.02, "planned_risk_pct": 0.5, "planned_dollar_loss": 3.5, "margin_estimate": 28.0, "reason": "WAIT blocks a new position", "inputs": {"stop_loss_pips": 18}}
    return canonical, summary, plan, history


def recursive_size(value: Any, seen: set[int] | None = None) -> int:
    seen = seen or set()
    ident = id(value)
    if ident in seen:
        return 0
    seen.add(ident)
    if isinstance(value, pd.DataFrame):
        return int(value.memory_usage(deep=True).sum())
    if isinstance(value, pd.Series):
        return int(value.memory_usage(deep=True))
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        size += sum(recursive_size(k, seen) + recursive_size(v, seen) for k, v in value.items())
    elif isinstance(value, (list, tuple, set, frozenset)):
        size += sum(recursive_size(x, seen) for x in value)
    return size


def state_inventory(state: dict[str, Any]) -> dict[str, Any]:
    frames: list[tuple[str, int]] = []
    for key, value in state.items():
        if isinstance(value, pd.DataFrame):
            frames.append((str(key), int(value.memory_usage(deep=True).sum())))
    largest = sorted(((str(k), recursive_size(v)) for k, v in state.items()), key=lambda x: x[1], reverse=True)[:10]
    cache = state.get("adaptive_presentation_cache_20260621")
    return {
        "approximate_bytes": recursive_size(state),
        "cache_entries": len(cache) if isinstance(cache, dict) else 0,
        "dataframe_count": len(frames),
        "largest_retained_objects": [{"key": k, "bytes": b} for k, b in largest],
    }


def main() -> None:
    sys.path.insert(0, str(ROOT))
    canonical, summary, plan, history = fixture()
    measurements: list[Measurement] = []

    old_exports = load_module(ORIGINALS / "services_canonical_exports.py", "baseline_canonical_exports_20260621")
    from services import canonical_exports as new_exports

    # Startup proxies: syntax-load the real entry point and the principal Lunch module.
    for variant, paths in (
        ("before", [ROOT / "app.py", Path(ORIGINALS / "ui_lunch_four_core_fields_20260619.py")]),
        ("after", [ROOT / "app.py", ROOT / "ui/lunch_four_core_fields_20260619.py"]),
    ):
        m, _ = measure("Cold startup", variant, lambda p=paths: [compile(Path(x).read_text(encoding="utf-8"), str(x), "exec") for x in p], repeats=3, notes="Headless syntax-load proxy; Streamlit runtime unavailable in benchmark container.")
        measurements.append(m)
        compiled = [compile(Path(x).read_text(encoding="utf-8"), str(x), "exec") for x in paths]
        m, _ = measure("Warm startup", variant, lambda c=compiled: tuple(code.co_name for code in c), repeats=20, notes="Warm compiled-code reuse proxy.")
        measurements.append(m)

    # Menu open source parse, old and new.
    for variant, path in (("before", ORIGINALS / "ui_liquid_menu_popup_20260615.py"), ("after", ROOT / "ui/liquid_menu_popup_20260615.py")):
        source = Path(path).read_text(encoding="utf-8")
        m, _ = measure("Menu open", variant, lambda s=source: ast.parse(s), repeats=10, notes="Headless menu source parse; no browser layout timing.")
        measurements.append(m)

    # History projection demonstrates selected columns/25-day/completed-H1 pushdown.
    from core.history_query_20260621 import project_completed_h1
    baseline_history = lambda: history.loc[pd.to_datetime(history["time"], utc=True).between(pd.Timestamp("2026-05-27T05:00:00Z"), pd.Timestamp("2026-06-21T05:00:00Z"))].sort_values("time", ascending=False).head(600).copy()
    after_history = lambda: project_completed_h1(history, days=25, columns=["time", "regime", "reliability", "decision"], maximum_rows=600, completed_h1="2026-06-21T05:00:00Z", descending=True)
    for variant, fn in (("before", baseline_history), ("after", after_history)):
        m, _ = measure("Field 3 history open", variant, fn, repeats=7, notes="Actual bounded DataFrame query; before retains all columns, after projects selected columns.")
        measurements.append(m)

    # Copy builders, actual old/new service implementations.
    for action, variant, fn in (
        ("Copy Short", "before", lambda: old_exports.short_text(canonical, summary, plan)),
        ("Copy Short", "after", lambda: new_exports.short_text(canonical, summary, plan)),
        ("Copy All", "before", lambda: old_exports.all_text(canonical, summary, plan)),
        ("Copy All", "after", lambda: new_exports.all_text(canonical, summary, plan)),
    ):
        m, _ = measure(action, variant, fn, repeats=7, notes="Actual canonical export service on identical representative generation.")
        measurements.append(m)

    # Field gate callback timings; content-specific heavy work is covered by the history/copy/AI rows.
    sys.modules.setdefault("streamlit", fake_streamlit())
    lunch = load_module(ROOT / "ui/lunch_four_core_fields_20260619.py", "bench_lunch_six_20260621")
    for index in range(1, 7):
        state = {f"lunch_field_widget_{index}_20260621": True}
        m, _ = measure(f"Field {index} open", "after", lambda i=index, s=state: lunch._sync_field_gate(i, s), repeats=30, notes="Actual non-widget/session-state load-gate callback; renderer cost is measured by relevant service rows.")
        measurements.append(m)
        state[f"lunch_field_widget_{index}_20260621"] = False
        m, _ = measure(f"Field {index} close", "after", lambda i=index, s=state: lunch._sync_field_gate(i, s), repeats=30, notes="Actual close callback; no renderer import or calculation transaction.")
        measurements.append(m)

    # Refresh Data with an injected existing connector result; no network and no calculation.
    refresh = load_module(ROOT / "core/app/refresh.py", "bench_refresh_20260621")
    refresh.refresh_now = lambda **kwargs: (history.tail(600).copy(deep=False), True, "BENCH_CONNECTOR", "Headless connector fixture")
    refresh_state = {"symbol": "EURUSD", "timeframe": "H1", "canonical_result_20260617": canonical, "canonical_calculation_generation_20260617": 77}
    m, _ = measure("Refresh Data", "after", lambda: refresh.refresh_data(refresh_state), repeats=5, notes="Actual public refresh orchestration with connector function injected; no network and no Run Calculation.")
    measurements.append(m)
    measurements.append(not_measured("Refresh Data", "before", "No separate public Refresh Data action existed in the baseline menu."))

    # AI actual local pipeline with DB retrieval replaced by an empty settled-evidence fixture.
    from core import ai_grounded_pipeline_20260621 as pipeline
    pipeline.load_settled_evidence = lambda *a, **k: []
    ai_state: dict[str, Any] = {}
    for action, question in (
        ("AI simple question", "Why is the current decision WAIT?"),
        ("AI complex question", "Explain regime reliability, Power BI path, similar days, conflict, risk sizing and data freshness with limitations."),
    ):
        m, _ = measure(action, "after", lambda q=question: pipeline.answer_question(q, canonical=canonical, summary=summary, plan=plan, state=ai_state), repeats=5, notes="Actual local lexical retrieval/planning/critic/calibration pipeline; settled DB evidence intentionally empty.")
        measurements.append(m)
        measurements.append(not_measured(action, "before", "Baseline assistant did not expose the same ten-stage grounded local pipeline."))

    # Tab switching is a pure navigation-state update by design.
    nav_state = {"active_page": "Lunch", "ui_navigation_click_ts": 0.0}
    m, _ = measure("Tab switching", "after", lambda: nav_state.update(active_page="Dinner", ui_navigation_click_ts=time.time()), repeats=50, notes="Session-state route update only; browser rerender not measured.")
    measurements.append(m)
    measurements.append(not_measured("Tab switching", "before", "Comparable browser rerender timing is unavailable without Streamlit."))

    # Reduce RAM actual reconstructable cache clear.
    from core.adaptive_presentation_cache_20260621 import cache_put, clear_reconstructable
    ram_state: dict[str, Any] = {"canonical_result_20260617": canonical, "settled_evidence": [{"id": i} for i in range(100)]}
    for i in range(32):
        cache_put(ram_state, f"item-{i}", {"values": list(range(1000))})
    m, _ = measure("Reduce RAM", "after", lambda: clear_reconstructable(ram_state), repeats=1, notes="Actual bounded presentation-cache clear; canonical result and settled evidence retained.")
    measurements.append(m)
    measurements.append(not_measured("Reduce RAM", "before", "Old action used multiple ad-hoc session keys; no stable pure baseline service existed."))

    # The protected calculation is validated by tests but not benchmarked without live connectors/Streamlit.
    measurements.append(not_measured("Run Calculation", "before", "Protected transaction intentionally not executed in a headless fixture benchmark."))
    measurements.append(not_measured("Run Calculation", "after", "Protected transaction intentionally not executed in a headless fixture benchmark; source hash and regression parity are reported separately."))

    # Snapshot final retained state metrics.
    final_state = {
        "canonical_result_20260617": canonical,
        "summary": summary,
        "position_sizing_plan_20260619": plan,
        "ai_conversation_memory_20260621": ai_state.get("ai_conversation_memory_20260621", []),
        **refresh_state,
    }
    output = {
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "environment": {"python": sys.version.split()[0], "streamlit_available": False, "process_pid": os.getpid()},
        "scope": "Headless service/control-path benchmark. No network, no browser paint, no protected Run Calculation transaction.",
        "measurements": [asdict(item) for item in measurements],
        "session_state_inventory": state_inventory(final_state),
        "copy_short_stats": asdict(new_exports.build_short_payload(canonical, summary, plan)[1]),
        "copy_all_characters": len(new_exports.all_text(canonical, summary, plan)),
        "baseline_copy_all_characters": len(old_exports.all_text(canonical, summary, plan)),
    }
    OUT.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
