"""Reproducible same-candle ARERT cache benchmark using deterministic synthetic H1 data."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
import tempfile
import time
import tracemalloc

import numpy as np
import pandas as pd


def make_fixture(n: int = 900):
    idx = pd.date_range("2026-05-01", periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(20260628)
    returns = rng.normal(0.0, 0.00055, n) + np.sin(np.arange(n) / 80.0) * 0.00008
    close = 1.15 * np.cumprod(1.0 + returns)
    open_ = np.r_[close[0], close[:-1]]
    market = pd.DataFrame({
        "Time": idx,
        "Open": open_,
        "High": np.maximum(open_, close) + rng.uniform(0.00005, 0.00035, n),
        "Low": np.minimum(open_, close) - rng.uniform(0.00005, 0.00035, n),
        "Close": close,
        "Volume": rng.integers(100, 2000, n),
    })
    labels = np.where(pd.Series(returns).rolling(5, min_periods=1).mean() >= 0, "BUY", "SELL")
    decisions = pd.DataFrame({
        "Broker Candle Time": idx,
        "Master Decision": labels,
        "Technical Bias": labels,
        "Pressure Decision": np.where(returns >= 0, "BUY", "SELL"),
        "Hold Safety Decision": np.where(np.abs(returns) < 0.00035, "WAIT FOR PULLBACK", "HOLD & PROTECT"),
    })
    news_idx = idx[::8]
    news = pd.DataFrame({
        "Time": news_idx,
        "Title": [f"event-{i}" for i in range(len(news_idx))],
        "Sentiment": rng.uniform(-1, 1, len(news_idx)),
        "Impact": rng.uniform(0, 100, len(news_idx)),
    })
    canonical = {
        "run_id": "benchmark-run",
        "generation_id": "benchmark-generation",
        "symbol": "EURUSD",
        "timeframe": "H1",
        "completed_broker_candle": idx[-1],
        "ohlc_df": market,
        "snapshot_hash": "benchmark-snapshot",
        "final_decision": {"final_decision": "BUY", "confidence": 70.0},
    }
    state = {
        "field1_table1_decision_history_20260628": decisions,
        "finnhub_ranked_news_20260626": news,
    }
    return state, canonical


def measured(fn):
    tracemalloc.start()
    started = time.perf_counter()
    value = fn()
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return value, elapsed, peak / 1024 / 1024


def main() -> None:
    output = Path("reports/PERFORMANCE_BENCHMARK_20260628.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        os.environ["ARERT_RESEARCH_DB_PATH"] = str(Path(temp) / "benchmark.sqlite3")
        from research_quant.arert_lab import MODULE_CATALOG, run_arert_research
        import research_quant.arert_store as store
        db_path = Path(temp) / "benchmark.sqlite3"
        original = store.persist_arert_envelope
        store.persist_arert_envelope = lambda envelope: original(envelope, db_path)
        state, canonical = make_fixture()
        first, first_seconds, first_peak = measured(lambda: run_arert_research(state, canonical, MODULE_CATALOG.keys()))
        second, second_seconds, second_peak = measured(lambda: run_arert_research(state, canonical, MODULE_CATALOG.keys()))
        time_reduction = 100.0 * (1.0 - second_seconds / first_seconds) if first_seconds else 0.0
        first_module_peak = max((float(row.get("peak_memory_mb") or 0.0) for row in first.get("benchmarks", [])), default=0.0)
        cached_module_peak = max((float(row.get("peak_memory_mb") or 0.0) for row in second.get("benchmarks", [])), default=0.0)
        memory_reduction = 100.0 * (1.0 - cached_module_peak / first_module_peak) if first_module_peak else 0.0
        payload = {
            "benchmark": "same completed candle, same snapshot, all 20 ARERT modules",
            "fixture": "deterministic synthetic 900-row EURUSD-like H1 series; no live-performance claim",
            "first_run_seconds": round(first_seconds, 6),
            "cached_run_seconds": round(second_seconds, 6),
            "wall_time_reduction_pct": round(time_reduction, 2),
            "outer_tracemalloc_note": "The runner uses per-module tracemalloc, so module peaks are the valid comparable measurement.",
            "first_run_max_module_peak_memory_mb": round(first_module_peak, 4),
            "cached_run_max_module_peak_memory_mb": round(cached_module_peak, 4),
            "module_calculation_peak_memory_reduction_pct": round(memory_reduction, 2),
            "first_run_cache_hits": sum(bool(row.get("cache_hit")) for row in first.get("benchmarks", [])),
            "cached_run_cache_hits": sum(bool(row.get("cache_hit")) for row in second.get("benchmarks", [])),
            "module_count": len(MODULE_CATALOG),
            "database_persisted": bool(second.get("database", {}).get("ok")),
            "production_values_modified": bool(second.get("production_values_modified")),
            "interpretation": "Measures repeated same-candle research calculation only. It does not prove device-wide mobile CPU/RAM reduction.",
        }
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
