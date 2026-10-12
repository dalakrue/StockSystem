"""Symbol-local calculation subprocess. Only file paths cross process boundaries."""
def compute_symbol(symbol, input_path, output_path, timeframe, strict_only=False):
    import pandas as pd
    from core.super_quick_field3_20260722 import _build_middle_finder_history
    candles = pd.read_parquet(input_path)
    result = _build_middle_finder_history({symbol: candles}, timeframe=timeframe,
                                         apply_selection=False, output_mode='BACKTEST_FAST',strict_only=strict_only)
    if len(result) != len(candles):
        raise RuntimeError('Strategy result does not retain every source candle')
    result.to_parquet(output_path, index=False, compression='zstd')
    return output_path


def cpu_workers():
    import os
    from pathlib import Path
    requested = max(1, min(2, int(os.environ.get('BUILD_CPU_WORKERS', '2'))))
    # Keep one process in constrained containers to avoid duplicating scientific
    # Python imports alongside Streamlit. Explicit requests are still bounded.
    for name in ('/sys/fs/cgroup/memory.max', '/sys/fs/cgroup/memory/memory.limit_in_bytes'):
        try:
            limit = Path(name).read_text().strip()
            if limit != 'max' and int(limit) < 1_500_000_000:
                return 1
        except (OSError, ValueError):
            pass
    return requested
