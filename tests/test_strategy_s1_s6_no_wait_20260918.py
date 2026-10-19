from __future__ import annotations

import numpy as np
import pandas as pd

from core.fixed_fx_universe_20260918 import TARGET_FX_SYMBOLS
from core.super_quick_field3_20260722 import _build_middle_finder_history, _extract_loaded_frames
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
    decisions = exported["Strategy Decision"].astype(str)
    assert "Strategy Decision" in exported.columns
    assert int(exported["Hourly 4 Entry"].sum()) == 4
    assert int(decisions.ne("None").sum()) == int((exported["Hourly 4 Entry"] & exported.unique_family_count.gt(0)).sum())
    assert not exported.loc[exported.entry_origin.eq("RANK_FILL"),"entry_eligible"].any()
    assert decisions.loc[exported["Hourly 4 Entry"] & exported.unique_family_count.gt(0)].str.match(r"(?:BUY|SELL|NEUTRAL|BLOCKED)-\d+ TP .+ SL .+").all()
    assert decisions.loc[exported["Hourly 4 Entry"] & exported.unique_family_count.gt(0)].str.match(r"(?:BUY|SELL)-\d+ TP .+ SL .+").all()
    assert decisions.loc[~exported["Hourly 4 Entry"]].eq("None").all()
    assert not decisions.str.contains("WAIT", regex=False).any()



def test_historical_finder_exports_all_s1_s50_audit_fields() -> None:
    frame = _candles(7, rows=180)
    history = _build_middle_finder_history({"EURUSD": frame}, timeframe="H1")
    assert not history.empty
    assert "Strategy Decision" in history.columns
    for number in range(1, 51):
        label = f"S{number}"
        assert f"{label} Entry Condition" in history.columns
        assert f"{label} Signal" in history.columns
        assert f"{label} Reason" in history.columns
        assert f"{label} Score" in history.columns
        assert not history[f"{label} Signal"].astype(str).str.contains("NO DATA|WAIT", case=False, regex=True).any()
    assert not history["Strategy Decision"].astype(str).str.contains("NO DATA|WAIT", case=False, regex=True).any()
    # A single-symbol Finder has one available symbol, so the selector publishes
    # one selected row rather than inventing three unavailable symbols.
    assert int(history["Hourly 4 Entry"].sum()) == history["Datetime"].nunique()
    assert int(history["Strategy Decision"].ne("None").sum()) == int(history.unique_family_count.gt(0).sum())
    assert history.loc[history["Hourly 4 Entry"] & history.unique_family_count.gt(0), "Strategy Decision"].str.match(r"(?:BUY|SELL|NEUTRAL|BLOCKED)-\d+ TP .+ SL .+").all()
    selected = history.loc[history["Hourly 4 Entry"], "Strategy Decision"]
    actionable = selected.str.startswith(("BUY-", "SELL-"))
    assert selected.loc[actionable].str.contains(r"TP [0-9.]+ SL [0-9.]+", regex=True).all()
    # A neutral/blocked row has no valid target direction; do not fabricate a
    # BUY-style price pair merely to fill the display slot.
    assert selected.loc[~actionable].eq('None').all()


def test_strategy_decision_can_publish_s9_s10_and_s11_s15() -> None:
    from core.pullback_engine_s1_s3_upgrade import strategy_decision
    results = {
        f"S{number}": {"signal": "NO ENTRY"}
        for number in range(1, 51)
    }
    results["S9"] = {"signal": "BUY", "entry_condition": True}
    results["S10"] = {"signal": "BUY", "entry_condition": True}
    results["S11"] = {"signal": "BUY", "entry_condition": True}
    results["S15"] = {"signal": "BUY", "entry_condition": True}
    decision = strategy_decision(results)
    assert decision == "BUY-4 TP40 SL20"
