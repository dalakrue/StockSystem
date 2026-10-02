"""Reproducible 10,000-row full/compact engine equality and memory benchmark.
Run from project root: python benchmarks/fast_backtest_benchmark_20261002.py
"""
import json
from pathlib import Path
import statistics
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from core.super_quick_field3_20260722 import _build_middle_finder_history


def main():
    n = 10000
    rng = np.random.default_rng(7)
    close = 1.1 + np.cumsum(rng.normal(0, .00012, n))
    op = np.r_[close[0], close[:-1]]
    candles = pd.DataFrame({'open_time': pd.date_range('2024-01-01', periods=n, freq='h', tz='UTC'),
        'open': op, 'high': np.maximum(op, close)+.0003, 'low': np.minimum(op, close)-.0003,
        'close': close, 'volume': rng.integers(10, 100, n)})
    timings = {'FULL': [], 'BACKTEST_FAST': []}
    results, outputs = {}, {}
    for repetition in range(3):
        for mode in timings:
            started = time.perf_counter()
            output = _build_middle_finder_history({'EURUSD': candles}, timeframe='H1', apply_selection=False, output_mode=mode)
            timings[mode].append(time.perf_counter() - started)
            outputs[mode] = output
            results[mode] = dict(rows=len(output), columns=len(output.columns), memory_bytes=int(output.memory_usage(deep=True).sum()))
    for column in outputs['BACKTEST_FAST']:
        pd.testing.assert_series_equal(outputs['FULL'][column], outputs['BACKTEST_FAST'][column], check_dtype=False, check_categorical=False)
    for mode in timings:
        results[mode]['runs_seconds'] = [round(value, 3) for value in timings[mode]]
        results[mode]['median_seconds'] = round(statistics.median(timings[mode]), 3)
    results['retained_fields_equal'] = True
    results['calculation_time_reduction_percent'] = round(100 * (1-statistics.median(timings['BACKTEST_FAST'])/statistics.median(timings['FULL'])), 1)
    results['retained_dataframe_memory_reduction_percent'] = round(100*(1-results['BACKTEST_FAST']['memory_bytes']/results['FULL']['memory_bytes']), 1)
    print(json.dumps(results, indent=2))
    Path('benchmarks/FAST_BACKTEST_MEASUREMENTS_20261002.json').write_text(json.dumps(results, indent=2)+'\n')

if __name__ == '__main__':
    main()
