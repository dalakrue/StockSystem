from __future__ import annotations

import numpy as np
import pandas as pd

from core.fixed_fx_universe_20260918 import TARGET_FX_SYMBOLS
from core.super_quick_field3_20260722 import _extract_loaded_frames
from ui.field3_multisymbol_regime_summary_20260722 import (
    STATIC_PULLBACK_COLUMNS,
    _attach_live_pullback_data,
    _canonical_middle_export_frame,
)


def _candles(seed: int, rows: int = 160) -> pd.DataFrame:
    x = np.arange(rows, dtype=float)
    close = 1.0 + seed * 0.01 + 0.00012 * x + 0.0025 * np.sin(x / 6.0 + seed)
    times = pd.date_range("2026-09-10", periods=rows, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "open_time": times,
            "open": close - 0.0002,
            "high": close + 0.0006,
            "low": close - 0.0006,
            "close": close,
            "volume": 1000 + x,
        }
    )


def test_super_quick_reads_all_merged_canonical_frames() -> None:
    state = {
        # Simulate the old failure: the most recent selector report is empty or
        # contains only a subset, while the merged canonical map has all 20.
        "market_data_run_results_20260705": {"results": {}},
        "canonical_symbol_candles": {
            symbol: _candles(index)
            for index, symbol in enumerate(TARGET_FX_SYMBOLS)
        },
    }
    frames, failures = _extract_loaded_frames(state, list(TARGET_FX_SYMBOLS))
    assert set(frames) == set(TARGET_FX_SYMBOLS)
    assert failures == {}
    assert all(len(frame) >= 50 for frame in frames.values())


def test_live_field3_recalculates_all_s1_s6_without_wait() -> None:
    state = {
        "canonical_symbol_candles": {
            symbol: _candles(index)
            for index, symbol in enumerate(TARGET_FX_SYMBOLS)
        }
    }
    ranking = pd.DataFrame(
        [
            {
                "Avg Regime Candle Rank": index + 1,
                "Symbol": symbol,
                "Lower Regime Bias": "BUY" if index % 3 else "SELL",
                "Middle Regime Bias": "BUY" if index % 2 == 0 else "SELL",
                "Higher Standard Regime Bias": "BUY" if index % 2 == 0 else "SELL",
                "Candle After Regime Start": index + 2,
                "RAS Decision": "ALLOW",
            }
            for index, symbol in enumerate(TARGET_FX_SYMBOLS)
        ]
    )

    out = _attach_live_pullback_data(ranking, state)
    exported = _canonical_middle_export_frame(out)

    assert len(exported) == 20
    assert not exported.astype(str).eq("WAIT").any().any()
    for column in STATIC_PULLBACK_COLUMNS:
        assert column in exported.columns
        assert pd.api.types.is_numeric_dtype(exported[column])
        assert exported[column].between(0, 100).all()
    assert exported["Strategy Decision"].astype(str).str.contains(r"S[1-6]", regex=True).all()
