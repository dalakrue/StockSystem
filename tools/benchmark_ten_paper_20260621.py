"""Reproducible synthetic performance benchmark for the ten-paper shadow layer.

This measures implementation overhead only. It is not evidence of trading accuracy,
profitability, or production performance on the user's future data.
"""
from __future__ import annotations

import json
import os
import sqlite3
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any, Callable
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from core.research_validation_layer_20260621 import build_research_validation_transaction
from core.research_validation_store_20260621 import BUNDLE_KEY, insert_research_validation_bundle
from core.ten_paper_research_layers_20260621 import build_ten_paper_research_transaction

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

OUTPUT = ROOT / "PERFORMANCE_MEASUREMENTS_20260621_TEN_PAPER.json"


def make_evidence(n: int = 384) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(20260621)
    idx = pd.date_range("2025-12-01", periods=n, freq="h", tz="UTC")
    close = 1.1 + np.cumsum(rng.normal(0.0, 0.0002, n))
    h1 = pd.DataFrame({
        "open": close - rng.normal(0.0, 0.00004, n),
        "high": close + rng.uniform(0.0001, 0.0004, n),
        "low": close - rng.uniform(0.0001, 0.0004, n),
        "close": close,
        "volume": rng.integers(100, 2500, n),
    }, index=idx)
    settled = pd.DataFrame({
        "calculation_id": [f"BENCH-{i:05d}" for i in range(n)],
        "forecast_origin_time": idx - pd.Timedelta(hours=1), "target_time": idx,
        "record_status": "SETTLED", "horizon": np.resize([1, 2, 3, 4, 5, 6], n),
        "session": np.resize(["ASIA", "LONDON", "NEW_YORK"], n),
        "h1_regime": np.resize(["BULL", "BEAR", "RANGE"], n),
        "h4_regime": np.resize(["BULL", "RANGE"], n), "d1_regime": np.resize(["BULL", "BEAR"], n),
        "full_metric_direction": np.resize(["BUY", "SELL", "WAIT"], n),
        "final_decision": np.resize(["BUY", "SELL", "WAIT"], n),
        "raw_confidence": rng.uniform(.4, .9, n), "calibrated_confidence": rng.uniform(.42, .86, n),
        "required_probability_threshold": rng.uniform(.5, .7, n),
        "expected_favorable_movement": rng.uniform(1, 12, n), "expected_adverse_movement": rng.uniform(1, 10, n),
        "predicted_close": close + rng.normal(0, .0003, n), "actual_close": close,
        "absolute_error_pips": rng.uniform(0, 12, n), "squared_error": rng.uniform(0, 144, n),
        "direction_correct": rng.integers(0, 2, n), "interval_hit": rng.integers(0, 2, n),
        "maximum_favorable_excursion": rng.uniform(0, 15, n), "maximum_adverse_excursion": rng.uniform(0, 12, n),
        "tp_touched": rng.integers(0, 2, n), "sl_touched": rng.integers(0, 2, n),
        "data_quality_status": np.resize(["PASS", "PASS", "WARNING"], n),
        "priority": rng.integers(1, 15, n), "knn_score": rng.uniform(0, 100, n),
        "greedy_rank": rng.integers(1, 15, n), "model_agreement": rng.uniform(.3, 1, n),
        "exit_risk": rng.uniform(0, 10, n), "reliability_score": rng.uniform(0, 100, n),
        "similarity_score": rng.uniform(0, 1, n), "nlp_reliability": rng.uniform(0, 100, n),
    })
    canonical = {
        "canonical_calculation_id": "BENCH-CANONICAL", "run_id": "BENCH-RUN", "calculation_generation": 1,
        "symbol": "EURUSD", "timeframe": "H1", "latest_completed_candle_time": idx[-1].isoformat(),
        "data_signature": "BENCH-DATA", "last_close": float(close[-1]),
        "master_score": 6.2, "entry_score": 6.0, "buy_score": 6.5, "sell_score": 3.2,
        "hold_safety": 5.9, "tp_quality": 5.4, "exit_risk": 3.1, "trend_capacity_remaining": 5.2,
        "data_quality": {"score": 92}, "reliability": {"score": 76, "conflict_score": 12},
        "priority": {"knn_score": 72, "greedy_rank": 2, "forecast_agreement": 70},
        "nlp": {"reliability": 55}, "regime": {"major_regime": "BULL"},
        "final_decision": {"final_decision": "BUY", "tradeability_decision": "BUY", "calibrated_confidence": .74, "uncertainty_pct": 26},
        "research_calibration": {"validation_status": "PASS"},
    }
    return canonical, h1, settled


def percentile(values: list[float], p: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), p)) if values else 0.0


def measure(name: str, fn: Callable[[], tuple[Any, Any, Any]], repeats: int = 7) -> tuple[dict[str, Any], tuple[Any, Any, Any]]:
    durations: list[float] = []
    peaks: list[int] = []
    rss_deltas: list[float] = []
    last = None
    process = psutil.Process(os.getpid()) if psutil else None
    for _ in range(repeats):
        rss_before = process.memory_info().rss if process else 0
        tracemalloc.start(); started = time.perf_counter()
        last = fn()
        durations.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
        peaks.append(int(peak))
        rss_after = process.memory_info().rss if process else 0
        rss_deltas.append((rss_after - rss_before) / (1024 * 1024) if process else 0.0)
    payload = last[0] if isinstance(last, tuple) and last else last
    serialized = len(json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8"))
    return {
        "name": name, "repeats": repeats, "mean_ms": statistics.mean(durations),
        "p50_ms": percentile(durations, 50), "p95_ms": percentile(durations, 95),
        "min_ms": min(durations), "max_ms": max(durations),
        "peak_allocation_bytes_max": max(peaks), "peak_allocation_bytes_p95": int(percentile([float(x) for x in peaks], 95)),
        "process_rss_delta_mb_mean": statistics.mean(rss_deltas), "process_rss_delta_mb_max": max(rss_deltas),
        "serialized_payload_bytes": serialized,
    }, last


def write_measure(bundle: dict[str, Any]) -> dict[str, Any]:
    fd, name = tempfile.mkstemp(suffix=".sqlite3"); os.close(fd)
    statements = {"select": 0, "insert": 0, "update": 0, "other": 0}
    conn = sqlite3.connect(name)
    def trace(sql: str) -> None:
        prefix = sql.lstrip().split(" ", 1)[0].lower()
        if prefix in statements: statements[prefix] += 1
        else: statements["other"] += 1
    conn.set_trace_callback(trace)
    start = time.perf_counter(); conn.execute("BEGIN IMMEDIATE")
    result = insert_research_validation_bundle(conn, bundle.get(BUNDLE_KEY, {})); conn.commit()
    elapsed = (time.perf_counter() - start) * 1000.0
    size = Path(name).stat().st_size
    conn.close(); Path(name).unlink(missing_ok=True)
    return {"write_time_ms": elapsed, "database_reads": statements["select"], "inserts": statements["insert"], "updates": statements["update"], "sql_other": statements["other"], "database_bytes": size, "insert_result": result}


def main() -> None:
    canonical, h1, settled = make_evidence()
    def baseline():
        return build_research_validation_transaction(canonical, completed_h1=h1, settled_predictions=settled, settled_method_predictions=pd.DataFrame(), previous={})
    def new_layer():
        return build_ten_paper_research_transaction(canonical, completed_h1=h1, settled_predictions=settled, settled_method_predictions=pd.DataFrame(), previous={})
    def combined():
        base_canonical, base_bundle, base_summary = baseline()
        after_canonical, ten_bundle, ten_summary = build_ten_paper_research_transaction(base_canonical, completed_h1=h1, settled_predictions=settled, settled_method_predictions=pd.DataFrame(), previous={})
        merged = dict(base_bundle)
        custom = merged.setdefault(BUNDLE_KEY, {})
        for table, rows in ten_bundle.get(BUNDLE_KEY, {}).items(): custom.setdefault(table, []).extend(rows)
        return after_canonical, merged, {"baseline": base_summary, "ten_paper": ten_summary}

    before_metrics, before_result = measure("existing_research_validation_before", baseline)
    layer_metrics, layer_result = measure("ten_paper_layer_only", new_layer)
    after_metrics, after_result = measure("combined_after", combined)
    report = {
        "benchmark_version": "ten-paper-benchmark-20260621-v1", "synthetic_rows": len(settled),
        "python_version": os.sys.version, "measurements": [before_metrics, layer_metrics, after_metrics],
        "incremental_overhead_mean_ms": after_metrics["mean_ms"] - before_metrics["mean_ms"],
        "before_database_write": write_measure(before_result[1]),
        "ten_paper_database_write": write_measure(layer_result[1]),
        "after_database_write": write_measure(after_result[1]),
        "claims": {"cpu_ram_reduction_claimed": False, "production_benefit_verified": False, "measurement_scope": "synthetic bounded evidence on this container"},
    }
    OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
