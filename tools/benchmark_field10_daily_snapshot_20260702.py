"""Reproducible synthetic performance evidence for the immutable Field 10 contract.

This benchmark never calls market APIs. It compares a fresh deterministic
publication with the persisted ALREADY_EXISTS_VALID fast path and read-only UI
operations. It is intentionally not presented as a live-provider end-to-end
benchmark.
"""
from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from core.field10_daily_snapshot_contract_20260702 import (
    load_current_daily_snapshot,
    migrate_daily_snapshot_database,
    publish_daily_snapshot_from_records,
    validate_persisted_snapshot,
)


def _identity() -> dict[str, Any]:
    cutoff = pd.Timestamp("2026-07-02T03:00:00+00:00")
    return {
        "broker_day": "2026-07-02",
        "broker_time": cutoff,
        "cutoff_broker_time": cutoff,
        "latest_completed_h1": cutoff - pd.Timedelta(hours=1),
        "required_cutoff_completed_h1": cutoff - pd.Timedelta(hours=1),
        "locked_until_broker_time": cutoff + pd.Timedelta(days=1),
        "before_cutoff": False,
        "at_or_after_day_end": False,
    }


def _candidate(symbol: str, index: int) -> dict[str, Any]:
    score = 92.0 - index
    return {
        "symbol": symbol,
        "role": "MAIN" if index == 0 else "SECONDARY",
        "daily_grade": "A+" if score >= 85 else "A",
        "institutional_morning_score": score,
        "existing_rank_score": score - 4,
        "eligibility_status": "ELIGIBLE",
        "stable_daily_bias": "BUY" if index % 2 == 0 else "SELL",
        "less_risky_bias": "BUY" if index % 2 == 0 else "SELL",
        "trade_permission": "ALLOWED",
        "higher_standard_regime": "BULL_NORMAL" if index % 2 == 0 else "BEAR_NORMAL",
        "data_quality_grade": "A",
        "data_quality_score": 94.0 - index / 2,
        "regime_probability": 84.0 - index / 3,
        "regime_entropy": 16.0 + index / 3,
        "posterior_margin": 68.0 - index / 4,
        "regime_persistence": 88.0 - index / 3,
        "regime_age": 24.0 + index,
        "expected_regime_duration": 72.0,
        "estimated_remaining_duration": 48.0 - index / 2,
        "transition_risk_1h": 5.0 + index / 3,
        "transition_risk_3h": 10.0 + index / 2,
        "transition_risk_6h": 18.0 + index,
        "calibrated_bias_probability": 82.0 - index / 3,
        "brier_score": 0.15 + index / 1000,
        "forecast_accuracy_1h": 74.0,
        "forecast_accuracy_3h": 70.0,
        "forecast_accuracy_6h": 66.0,
        "technical_bias": "BUY" if index % 2 == 0 else "SELL",
        "technical_reliability": 84.0,
        "sentiment_bias": "BUY" if index % 2 == 0 else "SELL",
        "sentiment_reliability": 72.0,
        "session_bias": "BUY" if index % 2 == 0 else "SELL",
        "session_reliability": 78.0,
        "evidence_agreement": 86.0,
        "conflict_index": 14.0,
        "conformal_coverage": 90.0,
        "conformal_interval_width": 0.002,
        "structural_break_status": "VALID",
        "changepoint_probability": 10.0,
        "spread_percentile": 20.0 + index,
        "cvar_95": -0.01 - index / 10000,
        "correlation_cluster": f"C{index % 3 + 1}",
        "duplicate_exposure_penalty": float(index % 4) * 5.0,
        "frame_validation": {"status": "COMPLETE", "sample_count": 600},
        "identity": {
            "canonical_run_id": f"RUN-{symbol}",
            "source_id": f"SRC-{symbol}",
            "snapshot_hash": f"HASH-{symbol}",
            "child_run_id": f"CHILD-{symbol}",
        },
        "score": {
            "eligibility_reasons": [], "available_weight": 100.0,
            "missing_weight": 0.0, "calculation_status": "COMPLETE",
            "score_confidence": 100.0, "components": {},
        },
        "research_layers": {
            "spa": {"status": "VALID", "candidate_count": 3, "promotion_status": "NOT_PROMOTED"},
            "pbo": {"status": "INSUFFICIENT_SAMPLE", "effective_trial_count": 0, "promotion_eligibility": "BLOCKED"},
        },
    }


def _measure(call: Callable[[], Any], repeats: int) -> dict[str, float]:
    durations: list[float] = []
    peaks: list[int] = []
    for _ in range(repeats):
        tracemalloc.start()
        started = time.perf_counter()
        call()
        durations.append(time.perf_counter() - started)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peaks.append(peak)
    return {
        "repeats": repeats,
        "mean_ms": statistics.mean(durations) * 1000,
        "median_ms": statistics.median(durations) * 1000,
        "min_ms": min(durations) * 1000,
        "max_ms": max(durations) * 1000,
        "mean_peak_kib": statistics.mean(peaks) / 1024,
        "max_peak_kib": max(peaks) / 1024,
    }


def run_benchmark(*, symbols: int = 12, repeats: int = 100, output: Path | None = None) -> dict[str, Any]:
    names = ["EURUSD"] + [f"SYM{i:02d}" for i in range(1, symbols)]
    candidates = [_candidate(symbol, index) for index, symbol in enumerate(names)]
    with tempfile.TemporaryDirectory(prefix="field10_benchmark_") as tmp:
        db = Path(tmp) / "field10.sqlite3"
        migrate_daily_snapshot_database(db)

        def publish() -> dict[str, Any]:
            return publish_daily_snapshot_from_records(
                broker_identity=_identity(), ordered_symbols=names, main_symbol="EURUSD",
                parent_run_id="BENCH-PARENT", candidates=candidates, path=db,
            )

        tracemalloc.start()
        started = time.perf_counter()
        first = publish()
        first_seconds = time.perf_counter() - started
        _, first_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        rerun = _measure(publish, repeats)
        read = _measure(lambda: load_current_daily_snapshot(path=db), repeats)

        before = validate_persisted_snapshot(path=db)

        def display_only() -> None:
            frame = load_current_daily_snapshot(path=db)["current"]
            filtered = frame.loc[frame["Symbol"].astype(str).str.contains("SYM", regex=False)]
            filtered.sort_values(["Daily Rank", "Symbol"], kind="mergesort").to_csv(index=False)

        display = _measure(display_only, repeats)
        after = validate_persisted_snapshot(path=db)
        reduction = 100.0 * (first_seconds - rerun["mean_ms"] / 1000.0) / first_seconds if first_seconds > 0 else None
        memory_reduction = 100.0 * (first_peak - rerun["mean_peak_kib"] * 1024) / first_peak if first_peak > 0 else None
        result = {
            "benchmark_scope": "synthetic deterministic publication and persisted UI fast path; no live APIs",
            "symbol_count": symbols,
            "fresh_publication": {
                "status": first.get("status"), "elapsed_ms": first_seconds * 1000,
                "peak_kib": first_peak / 1024,
            },
            "immutable_rerun_fast_path": rerun,
            "read_only_snapshot_load": read,
            "display_filter_sort_csv": display,
            "rerun_time_reduction_vs_fresh_percent": reduction,
            "rerun_peak_memory_reduction_vs_fresh_percent": memory_reduction,
            "persistence_unchanged_after_display_operations": before == after,
            "content_hash": before.get("content_hash"),
            "python_note": "Results vary by machine and are not a live-provider end-to-end benchmark.",
        }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", type=int, default=12)
    parser.add_argument("--repeats", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_benchmark(symbols=max(2, args.symbols), repeats=max(1, args.repeats), output=args.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
