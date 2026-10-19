from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ui.field3_multisymbol_regime_summary_20260722 import (
    STRATEGY_DECISION_COLUMN,
    _attach_live_pullback_data,
    _middle_age_ranking,
)


ROOT = Path(__file__).resolve().parents[1]


def _ranking() -> pd.DataFrame:
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
    return pd.DataFrame(
        {
            "Symbol": symbols,
            "Lower Candle After Regime Start": [1, 2, 3, 4],
            "Middle Candle After Regime Start": [5, 6, 7, 8],
            "Higher Candle After Regime Start": [10, 11, 12, 13],
            "Lower Regime": ["BULL"] * 4,
            "Lower Bias": ["BUY"] * 4,
            "Middle Regime": ["BULL"] * 4,
            "Middle Bias": ["BUY"] * 4,
            "Higher Regime": ["BULL"] * 4,
            "Higher Bias": ["BUY"] * 4,
            "Completed Candle": pd.to_datetime(["2026-09-27 14:00"] * 4, utc=True),
            "Timeframe": ["H1"] * 4,
        }
    )


def _candles() -> pd.DataFrame:
    count = 240
    index = np.arange(count)
    close = 1.10 + index * 0.0001 + 0.001 * np.sin(index / 5)
    opened = np.r_[close[0] - 0.0002, close[:-1]]
    return pd.DataFrame(
        {
            "open_time": pd.date_range("2026-09-10", periods=count, freq="h", tz="UTC"),
            "open": opened,
            "high": np.maximum(opened, close) + 0.0004,
            "low": np.minimum(opened, close) - 0.0004,
            "close": close,
            "volume": 100 + index,
        }
    )


def test_middle_ranking_has_one_strategy_decision_column() -> None:
    middle = _middle_age_ranking(_ranking())
    assert list(middle.columns).count(STRATEGY_DECISION_COLUMN) == 1
    assert not middle.columns.duplicated().any()


def test_live_audit_accepts_legacy_duplicate_labels() -> None:
    middle = _middle_age_ranking(_ranking())
    legacy = pd.concat(
        [middle, middle[[STRATEGY_DECISION_COLUMN]].copy()],
        axis=1,
    )
    candles = _candles()
    state = {
        "timeframe": "H1",
        "canonical_symbol_candles": {
            symbol: candles.copy() for symbol in _ranking()["Symbol"]
        },
    }
    result = _attach_live_pullback_data(legacy, state)
    assert not result.empty
    assert not result.columns.duplicated().any()
    assert list(result.columns).count(STRATEGY_DECISION_COLUMN) == 1
    assert int(result["Hourly 4 Entry"].sum()) == 4


def test_safe_cache_view_code_is_removed() -> None:
    source = (ROOT / "tabs" / "field3_page_20260722.py").read_text(encoding="utf-8")
    assert "safe cached view" not in source.lower()
    assert "fallback = state.get" not in source
