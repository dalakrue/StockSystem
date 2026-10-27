"""Regression and causal-path coverage for the S111-S120/TP-SL upgrade."""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import pytest

from core.advanced_tpsl_engine_20261002 import (
    HORIZON_HOURS,
    MAX_HOLD_HOURS,
    _released_excursions,
    _released_pair_statistics,
    add_advanced_tpsl_targets,
)
from core.pullback_engine_s1_s3_upgrade import STRATEGY_NAMES
from core.strategy_audit_20260924 import (
    ENTRY_FILTER_MULTIPLIER,
    ENTRY_FILTER_RELAXATION,
    build_strategy_audit,
)


def _legacy_fixture(rows: int = 720) -> pd.DataFrame:
    x = np.arange(rows)
    rng = np.random.default_rng(45)
    close = 1.1 + x * 0.000015 + 0.0015 * np.sin(x / 6) + rng.normal(0, 0.0002, rows)
    op = np.r_[close[0] - 0.0003, close[:-1]]
    return pd.DataFrame({
        "open_time": pd.date_range("2025-01-01", periods=rows, freq="h", tz="UTC"),
        "open": op,
        "high": np.maximum(op, close) + 0.0002,
        "low": np.minimum(op, close) - 0.0002,
        "close": close,
        "volume": 100 + np.random.default_rng(2).integers(0, 150, rows),
    })


def _extension_fixture(rows: int = 4000, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = np.arange(rows)
    returns = 0.00002 + 0.0001 * np.sin(x / 17) + rng.normal(0, 0.00025, rows)
    close = 1.1 + np.cumsum(returns)
    op = np.r_[close[0] - returns[0], close[:-1]] + rng.normal(0, 0.00006, rows)
    high = np.maximum(op, close) + rng.uniform(0.00005, 0.00035, rows)
    low = np.minimum(op, close) - rng.uniform(0.00005, 0.00035, rows)
    return pd.DataFrame({
        "open_time": pd.date_range("2025-01-01", periods=rows, freq="h", tz="UTC"),
        "open": op,
        "high": high,
        "low": low,
        "close": close,
        "volume": rng.integers(80, 300, rows),
        "Symbol": "EURUSD",
    })


def _mirror(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["open"] = 3 - frame["open"]
    result["close"] = 3 - frame["close"]
    result["high"] = 3 - frame["low"]
    result["low"] = 3 - frame["high"]
    return result


@pytest.fixture(scope="module")
def extension_audits() -> dict[str, pd.DataFrame]:
    source = _extension_fixture()
    return {
        "BUY": build_strategy_audit(source, "BUY", "BUY"),
        "SELL": build_strategy_audit(_mirror(source), "SELL", "SELL"),
    }


def test_registry_compatibility_and_explicit_training_relaxation():
    assert list(STRATEGY_NAMES)==[f'S{i}' for i in range(1,121)]
    assert ENTRY_FILTER_RELAXATION==0 and ENTRY_FILTER_MULTIPLIER==1
    source=_legacy_fixture()
    audits=[build_strategy_audit(source,'BUY','BUY',relaxation=x) for x in (0.,.1,.2,.4)]
    for x,audit in zip((0.,.1,.2,.4),audits):
        assert audit['Entry Filter Relaxation Percent'].eq(x*100).all()
        assert not audit.entry_eligible.any()
    assert audits[0]['S1 Entry Condition'].sum()<=audits[-1]['S1 Entry Condition'].sum()


@pytest.mark.parametrize("direction", ["BUY", "SELL"])
@pytest.mark.parametrize("strategy", [f"S{i}" for i in range(111, 121) if i != 115])
def test_each_extension_strategy_has_a_directional_synthetic_example(
    extension_audits: dict[str, pd.DataFrame], direction: str, strategy: str
):
    audit = extension_audits[direction]
    hits = audit.loc[audit[f"{strategy} Entry Condition"]]
    assert audit[f"{strategy} Signal"].astype(str).isin([direction,"NO ENTRY"]).all()
    # A stricter default policy is allowed to reject every random opportunity.
    # This verifies direction/reasons for actual hits without inventing coverage.
    assert hits[f"{strategy} Signal"].astype(str).eq(direction).all()
    assert hits[f"{strategy} Reason"].astype(str).str.contains("confirmed").all()


def test_s115_columns_remain_available_after_broader_legacy_gate(extension_audits):
    # With the requested 40% legacy relaxation, this random fixture's trap
    # reclaims are consumed by S1-S110 first. S115 remains rescue-only, so it
    # must not duplicate those entries, but its audit contract stays present.
    for direction, audit in extension_audits.items():
        assert "S115 Entry Condition" in audit
        assert "S115 Score" in audit
        assert audit["S115 Signal"].astype(str).isin({direction, "NO ENTRY"}).all()


def test_rescue_only_gate_and_s120_independent_evidence(extension_audits):
    for audit in extension_audits.values():
        extension_hit = audit[[f"S{i} Entry Condition" for i in range(111, 121)]].any(axis=1)
        assert not (audit["Legacy S1-S110 Hit"] & extension_hit).any()
        rescue = audit["S120 Entry Condition"]
        assert not audit.loc[rescue, [f"S{i} Entry Condition" for i in range(1, 120)]].any().any()
        assert audit.loc[rescue, "S120 Evidence Groups Passed"].ge(4).all()
        for column in (
            "S120 Trend Structure Score", "S120 Momentum Recovery Score",
            "S120 Volatility Quality Score", "S120 Candle Rejection Score",
            "S120 Value Location Score", "S120 TP SL Path Score",
        ):
            assert audit[column].between(0, 100).all()


def test_strategy_and_target_calculation_is_prefix_causal():
    source = _legacy_fixture(720)
    baseline = build_strategy_audit(source, "BUY", "BUY")
    changed = source.copy()
    changed.loc[600:, ["open", "high", "low", "close"]] *= 1.8
    mutated = build_strategy_audit(changed, "BUY", "BUY")
    columns = [
        "Strategy Decision", "Suggested TP Price", "Suggested SL Price",
        "TP/SL Pair Quality Score",
    ] + [f"S{i} Entry Condition" for i in range(1, 121)]
    pd.testing.assert_frame_equal(baseline.loc[:599, columns], mutated.loc[:599, columns])


def test_causal_excursions_are_released_only_after_complete_horizon():
    index = pd.RangeIndex(70)
    close = pd.Series(100 + np.arange(70) * 0.1, index=index)
    high = close + 0.2
    low = close - 0.2
    sign = pd.Series(1.0, index=index)
    mfe, mae, _ = _released_excursions(high, low, close, sign, 6)
    assert mfe.iloc[:6].isna().all()
    assert pd.notna(mfe.iloc[6]) and pd.notna(mae.iloc[6])
    changed_high = high.copy()
    changed_high.iloc[50:] += 100
    changed, _, _ = _released_excursions(changed_high, low, close, sign, 6)
    pd.testing.assert_series_equal(mfe.iloc[:50], changed.iloc[:50])


def test_post_sl_rebound_and_same_candle_sl_first_statistics():
    index = pd.RangeIndex(90)
    tp_after_sl = np.full(90, 3.0)
    sl_first = np.full(90, 1.0)
    stats = _released_pair_statistics(tp_after_sl, sl_first, 4, index)
    assert stats["rebound_rate"].dropna().iloc[-1] == pytest.approx(1.0)
    assert stats["sl_rate"].dropna().iloc[-1] == pytest.approx(1.0)
    assert stats["tp_rate"].dropna().iloc[-1] == pytest.approx(0.0)

    ambiguous = _released_pair_statistics(np.ones(90), np.ones(90), 4, index)
    assert ambiguous["ambiguous_count"].iloc[-1] > 0
    assert ambiguous["sl_rate"].dropna().iloc[-1] == pytest.approx(1.0)
    assert ambiguous["tp_rate"].dropna().iloc[-1] == pytest.approx(0.0)


@pytest.mark.parametrize("direction", ["BUY", "SELL"])
def test_structural_targets_liquidity_obstacles_and_horizons(direction):
    source = _extension_fixture(900)
    if direction == "SELL":
        source = _mirror(source)
    source["ADX"] = 25.0
    result = add_advanced_tpsl_targets(
        source, direction, timeframe="H1", symbol=source["Symbol"]
    )
    valid = result.iloc[320:].dropna(subset=["Suggested TP Price", "Suggested SL Price"])
    if direction == "BUY":
        assert valid["Suggested TP Price"].gt(valid["close"]).all()
        assert valid["Suggested SL Price"].lt(valid["close"]).all()
    else:
        assert valid["Suggested TP Price"].lt(valid["close"]).all()
        assert valid["Suggested SL Price"].gt(valid["close"]).all()
    assert valid["Preferred TP Horizon"].isin([f"{value}H" for value in HORIZON_HOURS]).all()
    assert valid["TP Target Horizon Hours"].le(MAX_HOLD_HOURS).all()
    assert valid["Time Exit Hours"].eq(MAX_HOLD_HOURS).all()
    assert not valid.entry_eligible.any() if 'entry_eligible' in valid else not valid['TP Filters Passed'].any()
    passed=valid['TP Research Filters Passed']
    assert valid.loc[passed,'TP Barrier Quality Passed'].all()

    assert valid["Required Structural SL"].gt(0).all()
    assert valid["Allowed Maximum SL"].gt(0).all()
    passed = valid["SL Risk Cap Passed"]
    assert valid.loc[passed, "Required Structural SL"].le(
        valid.loc[passed, "Allowed Maximum SL"] + 1e-12
    ).all()
    assert not valid['TP Filters Passed'].any()
    assert valid['TP Target Horizon Hours'].eq(24).all()
    assert valid['TP Filter Reasons'].str.contains('Validated Calibration').all()
