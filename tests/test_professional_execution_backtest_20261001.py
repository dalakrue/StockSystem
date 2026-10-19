from io import BytesIO
import zipfile

import pandas as pd

from core.professional_execution_backtest_20261001 import (
    build_professional_backtest_bundle,
    evaluate_execution_backtest,
)


def _signal(**updates):
    row = {
        "Datetime": pd.Timestamp("2026-01-01 00:00", tz="UTC"),
        "Symbol": "EURUSD",
        "Hourly 4 Entry": True,
        "Strategy Decision": "BUY-3 TP 1.10200 SL 1.09800",
        "Middle Regime Bias": "BUY",
        "Close Price": 1.10000,
        "Suggested TP Price": 1.10200,
        "Suggested SL Price": 1.09800,
    }
    row.update(updates)
    return pd.DataFrame([row])


def _candles(highs, lows, closes, *, symbol="EURUSD"):
    times = pd.date_range("2026-01-01 00:00", periods=len(highs), freq="h", tz="UTC")
    return pd.DataFrame({
        "Datetime": times,
        "Symbol": symbol,
        "Open Price": closes,
        "High Price": highs,
        "Low Price": lows,
        "Close Price": closes,
    })


def test_future_tp_uses_unselected_continuous_candles_and_spread():
    movie = _candles(
        [1.1005, 1.1030, 1.1010],
        [1.0995, 1.0990, 1.0995],
        [1.1000, 1.1025, 1.1005],
    )
    result = evaluate_execution_backtest(_signal(), movie, finder_rows=_signal(), spread_pips=2)
    assert result.iloc[0]["Exit Reason"] == "TP_HIT"
    assert result.iloc[0]["Backtest Valid"]
    assert result.iloc[0]["Gross Pips"] == 20.0
    assert result.iloc[0]["Net Pips"] == 18.0
    assert result.iloc[0]["MFE Pips"] == 30.0


def test_same_candle_tp_sl_is_conservative_and_bias_flip_uses_close():
    ambiguous = _candles(
        [1.1005, 1.1030], [1.0995, 1.0970], [1.1000, 1.1005]
    )
    first = evaluate_execution_backtest(_signal(), ambiguous)
    assert first.iloc[0]["Exit Reason"] == "SL_HIT_AMBIGUOUS_CANDLE"
    assert first.iloc[0]["TP And SL Same Candle"]
    assert first.iloc[0]["Net Pips"] == -22.0

    no_barrier = _candles(
        [1.1005, 1.1010], [1.0995, 1.0990], [1.1000, 1.1007]
    )
    bias = pd.DataFrame({
        "Datetime": no_barrier["Datetime"],
        "Symbol": "EURUSD",
        "Middle Regime Bias": ["BUY", "SELL"],
    })
    second = evaluate_execution_backtest(_signal(), no_barrier, finder_rows=bias)
    assert second.iloc[0]["Exit Reason"] == "MIDDLE_BIAS_EXIT"
    assert second.iloc[0]["Middle Bias At Exit"] == "SELL"
    assert second.iloc[0]["Net Pips"] == 5.0


def test_incomplete_tail_is_not_counted_as_a_finished_trade():
    movie = _candles(
        [1.1005, 1.1010], [1.0995, 1.0990], [1.1000, 1.1002]
    )
    result = evaluate_execution_backtest(_signal(), movie)
    assert result.iloc[0]["Exit Reason"] == "INSUFFICIENT_FUTURE_DATA"
    assert not result.iloc[0]["Backtest Valid"]
    assert pd.isna(result.iloc[0]["Net Pips"])


def test_realized_post_sl_rebound_to_original_tp_is_audited():
    movie = _candles(
        [1.1005, 1.1008, 1.1030],
        [1.0995, 1.0975, 1.0990],
        [1.1000, 1.0985, 1.1025],
    )
    result = evaluate_execution_backtest(_signal(), movie)
    assert result.iloc[0]["Exit Reason"] == "SL_HIT"
    assert result.iloc[0]["Post-SL Rebound Evaluated"]
    assert result.iloc[0]["Post-SL Rebound To TP"]
    assert result.iloc[0]["TP Price"] == 1.10200
    assert result.iloc[0]["SL Price"] == 1.09800


def test_bundle_contains_signals_all_symbols_future_bias_and_results():
    eur = _candles(
        [1.1005, 1.1030], [1.0995, 1.0990], [1.1000, 1.1025]
    )
    gbp = _candles(
        [1.2505, 1.2510], [1.2495, 1.2490], [1.2500, 1.2502], symbol="GBPUSD"
    )
    movie = pd.concat([eur, gbp], ignore_index=True)
    bias = pd.DataFrame({
        "Datetime": list(eur["Datetime"]) + list(gbp["Datetime"]),
        "Symbol": ["EURUSD"] * 2 + ["GBPUSD"] * 2,
        "Middle Regime Bias": ["BUY"] * 4,
    })
    payload, trades, summary = build_professional_backtest_bundle(
        _signal(), movie, finder_rows=bias,
        entry_start="2026-01-01 00:00Z", entry_end="2026-01-01 00:00Z",
    )
    assert summary["candle_symbols"] == 2
    assert len(trades) == 1
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        assert set(archive.namelist()) == {
            "01_hourly_signals.csv", "02_all_symbol_candles.csv",
            "03_middle_bias_timeline.csv", "04_execution_backtest.csv",
            "05_summary.json", "README.txt",
        }
        candle_csv = pd.read_csv(archive.open("02_all_symbol_candles.csv"))
        assert set(candle_csv["Symbol"]) == {"EURUSD", "GBPUSD"}
