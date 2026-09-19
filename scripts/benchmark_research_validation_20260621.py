"""Bounded synthetic benchmark for the 2026-06-21 validation layer."""
from __future__ import annotations
import json, os, sys, time, tracemalloc
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
import psutil

os.environ.setdefault("ADX_TEST_PROFILE", "fast")
from core.canonical_data_validation_20260621 import validate_source_frame
from core.research_validation_layer_20260621 import build_research_validation_transaction


def fixtures():
    now = pd.Timestamp("2026-06-21T10:30:00Z")
    idx = pd.date_range(end=now.floor("h") - pd.Timedelta(hours=1), periods=720, freq="h", tz="UTC")
    base = 1.15 + np.sin(np.arange(720) / 24) * 0.001
    frame = pd.DataFrame({"open": base, "high": base + 0.001, "low": base - 0.001, "close": base + 0.0001, "adx": 20, "atr_percentile": 50}, index=idx)
    validation = validate_source_frame(frame, now=now, max_staleness_hours=1000)
    canonical_rows, method_rows = [], []
    times = pd.date_range("2026-01-01", periods=3000, freq="h", tz="UTC")
    for i, target in enumerate(times):
        actual = 1.14 + np.sin(i / 50) * 0.002; horizon = (i % 6) + 1
        canonical_rows.append({"calculation_id": f"C{i}", "forecast_origin_time": target - pd.Timedelta(hours=1), "target_time": target, "settlement_timestamp": target, "horizon": horizon, "predicted_close": actual + 0.0002, "actual_close": actual, "forecast_origin_price": actual - 0.00005, "record_status": "SETTLED", "lower_band": actual - 0.001, "upper_band": actual + 0.001, "session": ("ASIA", "LONDON", "NEW_YORK")[i % 3], "h1_regime": ("RANGE", "BULL", "BEAR")[i % 3], "event_risk_status": ("LOW", "MEDIUM")[i % 2]})
        for model, error in (("canonical", 0.00020), ("xgboost", 0.00015), ("lstm", 0.00018), ("prophet", 0.00025)):
            method_rows.append({"calculation_id": f"C{i}", "forecast_origin_time": target - pd.Timedelta(hours=1), "target_time": target, "settlement_timestamp": target, "horizon": horizon, "method": model, "predicted_close": actual + error, "actual_close": actual, "absolute_error": error, "record_status": "SETTLED"})
    canonical = {"run_id": "BENCH", "canonical_calculation_id": "BENCH", "calculation_generation": 1, "symbol": "EURUSD", "timeframe": "H1", "latest_completed_candle_time": idx[-1].isoformat(), "market": {"latest_completed_candle_time": idx[-1].isoformat()}, "forecasts": {"horizons": {}}, "regime": {"major_regime": "RANGE"}, "reliability": {}, "metadata": {}, "final_decision": {"final_decision": "WAIT", "directional_market_view": "WAIT", "less_risky_decision": "WAIT"}}
    return frame, validation, pd.DataFrame(canonical_rows), pd.DataFrame(method_rows), canonical


def main():
    frame, validation, settled, methods, canonical = fixtures()
    process = psutil.Process()
    runs = []
    for _ in range(3):
        rss_before = process.memory_info().rss
        tracemalloc.start(); started = time.perf_counter()
        _, _, summary = build_research_validation_transaction(canonical, completed_h1=frame, settled_predictions=settled, settled_method_predictions=methods, preflight_validation=validation, previous={})
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
        rss_after = process.memory_info().rss
        runs.append({"elapsed_seconds": elapsed, "tracemalloc_peak_bytes": peak, "rss_delta_bytes": rss_after - rss_before, "cpa_rows": summary["cpa_rows"], "spa_rows": summary["spa_rows"]})
    result = {"profile": os.environ.get("ADX_TEST_PROFILE"), "fixture": {"completed_h1_rows": 720, "settled_canonical_rows": 3000, "settled_method_rows": 12000}, "runs": runs, "median_elapsed_seconds": float(np.median([r["elapsed_seconds"] for r in runs])), "max_tracemalloc_peak_bytes": max(r["tracemalloc_peak_bytes"] for r in runs), "max_rss_delta_bytes": max(r["rss_delta_bytes"] for r in runs)}
    path = Path("reports/RESEARCH_VALIDATION_BENCHMARK_20260621.json")
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
