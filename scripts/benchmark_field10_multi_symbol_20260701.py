"""Synthetic orchestration/persistence benchmark for Field 10 (no live API/model latency)."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import pandas as pd
import psutil

import core.canonical_runtime_20260617 as canonical_runtime
import core.multi_symbol_field10_20260701 as multi


def run(output: Path) -> list[dict]:
    root = Path(tempfile.mkdtemp(prefix="field10_benchmark_"))
    process = psutil.Process(os.getpid())
    original = {
        "cache": multi._cache_path,
        "persist": multi._persist_symbol_evidence,
        "rank": multi._rank_persisted_rows,
        "load": multi.load_field10_tables,
        "canonical": canonical_runtime.get_canonical,
    }
    results: list[dict] = []
    try:
        canonical_runtime.get_canonical = lambda state: state.get("canonical_decision_result_20260617") or {}
        for count in (1, 5, 10):
            scenario = root / f"symbols_{count}"
            scenario.mkdir()
            db = scenario / "field10.sqlite3"
            multi._cache_path = lambda symbol, scenario=scenario: scenario / f"{symbol}.pkl.gz"
            multi._persist_symbol_evidence = lambda state, _db=db, **kwargs: original["persist"](state, path=_db, **kwargs)
            multi._rank_persisted_rows = lambda parent, day, _db=db: original["rank"](parent, day, path=_db)
            multi.load_field10_tables = lambda state=None, parent_run_id=None, symbol=None, _db=db: original["load"](
                state, parent_run_id=parent_run_id, symbol=symbol, path=_db
            )
            symbols = list(multi.SUPPORTED_SYMBOLS[:count])
            state = {multi.SELECTED_KEY: symbols, multi.ACTIVE_KEY: symbols[0], "timeframe": "H1"}
            calls: list[str] = []

            def runner():
                symbol = state["symbol"]
                calls.append(symbol)
                times = pd.date_range("2026-06-06T00:00:00Z", periods=600, freq="h")
                values = pd.Series(range(600), dtype=float) / 100000 + 1.05 + symbols.index(symbol) * 0.01
                state["canonical_completed_ohlc_df_20260617"] = pd.DataFrame({
                    "time": times, "open": values, "high": values + 0.001,
                    "low": values - 0.001, "close": values + 0.0002,
                })
                state["canonical_decision_result_20260617"] = {
                    "run_id": f"RUN-{symbol}", "symbol": symbol, "timeframe": "H1",
                    "source_id": f"SRC-{symbol}", "latest_completed_candle_time": times[-1].isoformat(),
                    "broker_candle_time": "2026-07-01T23:00:00+04:00",
                    "regime": {"higher_regime": "RANGE", "major_regime": "RANGE", "reliability": 82},
                    "final_decision": {"less_risky_decision": "WAIT"},
                }
                state["field3_regime_lifecycle_monitor_20260701"] = {
                    "history_25d": [
                        {
                            "event_time_utc": stamp.isoformat(),
                            "Existing Higher Regime": "RANGE" if i % 3 else "BULL_NORMAL",
                            "Regime Bias": "WAIT" if i % 3 else "BUY",
                            "Data Quality Score": 92 - i % 5,
                            "Calibrated Trust Score": 84 - i % 4,
                            "Bias Reliability Score": 83 - i % 3,
                        }
                        for i, stamp in enumerate(times)
                    ],
                    "data_quality": {"score": 92},
                }
                return {"ok": True, "canonical": {"ok": True}, "calculation_generation": 1}

            rss0 = process.memory_info().rss
            cpu0 = sum(process.cpu_times()[:2])
            started = time.perf_counter()
            manifest = multi.run_selected_symbols(state, runner, scope="QUICK")
            elapsed = time.perf_counter() - started
            rss1 = process.memory_info().rss
            cpu1 = sum(process.cpu_times()[:2])
            cache_bytes = sum(path.stat().st_size for path in scenario.glob("*.pkl.gz"))
            results.append({
                "selected_symbols": count,
                "completed_symbols": manifest.get("completed_symbols"),
                "failed_symbols": manifest.get("failed_symbols"),
                "wall_seconds": round(elapsed, 4),
                "cpu_seconds": round(cpu1 - cpu0, 4),
                "rss_delta_mb": round((rss1 - rss0) / 1048576, 4),
                "compressed_cache_mb": round(cache_bytes / 1048576, 4),
                "hourly_rows": count * 600,
                "runner_calls": len(calls),
                "heat_proxy": manifest.get("resource_report", {}).get("heat_proxy"),
                "test_type": "synthetic Field 10 orchestration/persistence; excludes live API and protected model runtime",
            })
    finally:
        multi._cache_path = original["cache"]
        multi._persist_symbol_evidence = original["persist"]
        multi._rank_persisted_rows = original["rank"]
        multi.load_field10_tables = original["load"]
        canonical_runtime.get_canonical = original["canonical"]
        shutil.rmtree(root, ignore_errors=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


if __name__ == "__main__":
    destination = Path("DELIVERY_20260701_FIELD10_MULTI_SYMBOL/PERFORMANCE_BENCHMARK.json")
    print(json.dumps(run(destination), indent=2))
