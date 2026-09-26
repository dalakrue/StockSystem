"""Bounded synthetic benchmark for the additive regime-trust and Lunch search layers."""
from __future__ import annotations

from pathlib import Path
import json
import statistics
import tempfile
import time
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.lunch_search_20260621 import search_cached_lunch
from core.regime_transition_trust_20260621 import build_regime_transition_trust
from core.regime_trust_store_20260621 import RegimeTrustStore

OUT = ROOT / "PERFORMANCE_MEASUREMENTS_20260621_REGIME_TRUST.json"


def fixture():
    rng = np.random.default_rng(20260621)
    times = pd.date_range("2026-05-20", periods=768, freq="h", tz="UTC")
    returns = np.r_[rng.normal(0, 0.00007, 500), rng.normal(0.00002, 0.00018, 268)]
    close = 1.15 + np.cumsum(returns)
    frame = pd.DataFrame({
        "Time": times, "Open": close - 0.00002, "High": close + 0.00018,
        "Low": close - 0.00018, "Close": close,
    })
    regimes = ["RANGE_NORMAL"] * 220 + ["BULL_COMPRESSION"] * 260 + ["BULL_EXPANSION"] * 288
    priority = pd.DataFrame({"Time": times, "Regime": regimes, "Priority Rank": np.tile(np.arange(1, 15), 55)[:768]})
    settled = pd.DataFrame({
        "confidence": np.linspace(0.53, 0.84, 180),
        "predicted_direction": ["BUY"] * 180,
        "actual_direction": ["BUY"] * 132 + ["SELL"] * 48,
        "actual_inside_interval": [1] * 158 + [0] * 22,
        "absolute_close_error": np.abs(rng.normal(0.00034, 0.00011, 180)),
    })
    canonical = {
        "run_id": "BENCH-RUN", "canonical_calculation_id": "BENCH-RUN",
        "calculation_generation": 44, "latest_completed_candle_time": times[-1],
        "shared_result_schema_version": "2.0.0",
        "regime": {"major_regime": "BULL_EXPANSION", "previous_regime": "BULL_COMPRESSION", "reliability": 78},
        "final_decision": {"final_decision": "BUY", "directional_market_view": "BUY", "less_risky_decision": "BUY"},
        "reliability": {"score": 75}, "risk": {"exit_risk": 5.4},
        "forecasts": {
            "selected": {"point_forecast": float(close[-1] + 0.00045), "lower_bound": float(close[-1] - 0.0007), "upper_bound": float(close[-1] + 0.0011), "confidence_pct": 73, "direction": "BUY"},
            "models": {
                "LSTM": {"forecast": float(close[-1] + 0.0007), "confidence": 75},
                "Transformer": {"forecast": float(close[-1] + 0.00045), "confidence": 72},
                "XGBoost": {"forecast": float(close[-1] + 0.00015), "confidence": 69},
                "Prophet": {"forecast": float(close[-1] - 0.00005), "confidence": 61},
            },
        },
    }
    return canonical, frame, priority, settled


def measure(function, repeats=20):
    values = []
    result = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = function()
        values.append((time.perf_counter() - started) * 1000.0)
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return {
        "repeats": repeats,
        "mean_ms": statistics.fmean(values),
        "median_ms": statistics.median(values),
        "p95_ms": p95,
        "min_ms": min(values),
        "max_ms": max(values),
    }, result


def main() -> int:
    canonical, frame, priority, settled = fixture()
    trust_stats, trust_result = measure(
        lambda: build_regime_transition_trust(canonical, completed_h1=frame, priority_table=priority, settled_predictions=settled),
        repeats=20,
    )
    output, evidence, bundle = trust_result
    state = {"canonical_decision_result": output}
    search_stats, search_result = measure(lambda: search_cached_lunch("XGBoost disagreement", state), repeats=30)

    with tempfile.TemporaryDirectory() as directory:
        store = RegimeTrustStore(Path(directory) / "benchmark.duckdb")
        insert_stats, first = measure(lambda: store.append_bundle(bundle), repeats=1)
        duplicate_stats, duplicate = measure(lambda: store.append_bundle(bundle), repeats=20)
        query_stats, query = measure(lambda: store.transition_matches("BULL_COMPRESSION", "BULL_EXPANSION", limit=5), repeats=30)
        db_bytes = (Path(directory) / "benchmark.duckdb").stat().st_size

    report = {
        "benchmark_version": "regime-trust-benchmark-20260621-v1",
        "synthetic_h1_rows": len(frame),
        "settled_prediction_rows": len(settled),
        "measurements": {
            "evidence_build_once_per_calculation": trust_stats,
            "cached_lunch_search_submission": search_stats,
            "duckdb_first_incremental_write": insert_stats,
            "duckdb_duplicate_idempotent_write": duplicate_stats,
            "duckdb_projected_top5_transition_query": query_stats,
        },
        "results": {
            "search_rows": len(search_result),
            "transition_query_rows": len(query),
            "first_insert": first,
            "duplicate_insert": duplicate,
            "database_bytes": db_bytes,
            "protected_regime_unchanged": evidence.get("protected_regime_unchanged"),
            "protected_decision_unchanged": evidence.get("protected_decision_unchanged"),
        },
        "interpretation": "The evidence build runs only on Run Calculation. Search and projected DuckDB reads are lightweight cached/display paths and do not invoke the trading calculator.",
    }
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
