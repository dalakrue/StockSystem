from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.pullback_engine_s1_s3_upgrade import STRATEGY_NAMES, evaluate_pullback_strategies, strategy_decision
from core.super_quick_field3_20260722 import _build_fast_historical_strategy_audit
from ui.field3_multisymbol_regime_summary_20260722 import _canonical_middle_export_frame


def _frame(rows: int = 240) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    close = 1.10 + np.cumsum(rng.normal(0, 0.0008, rows))
    return pd.DataFrame(
        {
            "open_time": pd.date_range("2026-01-01", periods=rows, freq="h"),
            "open": close,
            "high": close + 0.001,
            "low": close - 0.001,
            "close": close + rng.normal(0, 0.0002, rows),
            "volume": 1000 + rng.integers(0, 200, rows),
        }
    )


def test_strategy_contract_is_s1_to_s110() -> None:
    assert list(STRATEGY_NAMES) == [f"S{i}" for i in range(1, 111)]
    result = evaluate_pullback_strategies(_frame(), "BUY", "BUY")
    assert set(result) == set(STRATEGY_NAMES)
    assert strategy_decision(result) != ""  # explicit None is allowed


def test_fast_finder_audit_is_causal_and_has_s1_s20() -> None:
    frame = _frame(600)
    bias = pd.Series(["BUY"] * len(frame))
    audit = _build_fast_historical_strategy_audit(frame, bias, bias)
    assert "Strategy Decision" in audit.columns
    for label in STRATEGY_NAMES:
        assert f"{label} Entry Condition" in audit.columns
        assert f"{label} Signal" in audit.columns
        assert f"{label} Reason" in audit.columns
        assert f"{label} Score" in audit.columns
    # Future-candle mutations must not change a prior audit row.
    changed = frame.copy()
    changed.loc[599, "close"] += 0.25
    audit_changed = _build_fast_historical_strategy_audit(changed, bias, bias)
    pd.testing.assert_series_equal(
        audit.iloc[300], audit_changed.iloc[300], check_names=False
    )


def test_symbol_is_first_in_middle_export_contract() -> None:
    frame = pd.DataFrame(
        {
            "Strategy Decision": ["BUY S1,S16"],
            "Avg Regime Candle Rank": [1],
            "Symbol": ["EURUSD"],
            "S1 Signal": ["BUY"],
            "S16 Signal": ["BUY"],
        }
    )
    exported = _canonical_middle_export_frame(frame)
    assert exported.columns[0] == "Symbol"
    assert exported.columns[1] == "Strategy Decision"
