"""Strategy-only regression tests for the Dynamic TP + Middle Bias Exit scenario."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.hourly_four_symbol_selector_20260928 import (
    MAX_HOLD_HOURS,
    LOW_FREQUENCY_COVERAGE_SYMBOLS,
    add_dynamic_24h_targets,
    attach_hourly_four_selection,
    middle_bias_exit_decision,
)


def candles(n=260):
    x = np.arange(n)
    close = 1.10 + x * 0.00003 + 0.0013 * np.sin(x / 7.0)
    open_ = np.r_[close[0] - 0.00015, close[:-1]]
    high = np.maximum(open_, close) + 0.00035
    low = np.minimum(open_, close) - 0.00025
    return pd.DataFrame({
        'Datetime': pd.date_range('2026-01-01', periods=n, freq='h'),
        'open': open_, 'high': high, 'low': low, 'close': close,
        'ATR': pd.Series(high-low).ewm(alpha=1/14, adjust=False, min_periods=14).mean(),
        'ADX': 28.0,
    })


def test_dynamic_target_is_causal_and_never_longer_than_24h():
    df = candles()
    bias = pd.Series('BUY', index=df.index)
    out = add_dynamic_24h_targets(df, bias, timeframe='H1', symbol='EURUSD')
    assert out['Max Hold Hours'].eq(24).all()
    assert out['Time Exit Hours'].eq(24).all()
    assert out['TP Target Horizon Hours'].dropna().le(24).all()
    assert out['TP Within 24H'].dropna().all()
    before = out.loc[:180, 'Suggested TP'].copy()
    mutated = df.copy()
    mutated.loc[181:, ['open', 'high', 'low', 'close']] *= 3.0
    changed = add_dynamic_24h_targets(mutated, bias, timeframe='H1', symbol='EURUSD')
    pd.testing.assert_series_equal(before, changed.loc[:180, 'Suggested TP'], check_names=False)


def test_middle_bias_owns_target_direction_and_24h_exit_priority():
    df = candles()
    middle = pd.Series('BUY', index=df.index)
    out = add_dynamic_24h_targets(df, middle, timeframe='H1', symbol='EURUSD')
    assert (out['Suggested TP'] >= out['close']).iloc[-30:].all()
    assert (out['Suggested SL'] <= out['close']).iloc[-30:].all()
    assert out['Exit Scenario'].eq('Dynamic TP + Middle Bias Exit').all()

    hold = middle_bias_exit_decision('BUY', 'BUY', position_age_hours=10)
    assert hold['action'] == 'HOLD_TO_DYNAMIC_TP'
    bias_exit = middle_bias_exit_decision('BUY', 'SELL', position_age_hours=10)
    assert bias_exit['action'] == 'EXIT'
    timed = middle_bias_exit_decision('BUY', 'BUY', position_age_hours=24)
    assert timed['action'] == 'EXIT'
    assert timed['reason'] == '24H TIME CAP'


def test_low_frequency_coverage_uses_only_strong_strategy_hits():
    timestamps = pd.date_range('2026-02-01', periods=12, freq='h')
    symbols = ['EURUSD', 'GBPJPY', 'USDCAD', 'EURNZD']
    rows = []
    for t_i, ts in enumerate(timestamps):
        for sym in symbols:
            rows.append({
                'Datetime': ts, 'Symbol': sym,
                'S1 Entry Condition': True,
                'S1 Signal': 'BUY',
                'S1 Score': 82 if sym in LOW_FREQUENCY_COVERAGE_SYMBOLS else 96,
                'Middle Regime Bias': 'BUY',
                'Lower Regime Bias': 'BUY',
                'Higher Standard Regime Bias': 'BUY',
                'Near Entry Score': 78 if sym == 'EURUSD' else 68,
                'TP:SL Price Ratio': 2.0,
                '24H TP Distance': 0.004,
                '24H SL Distance': 0.002,
                'ATR': 0.0015,
                'Entry Noise Ratio': 1.05,
                'TP Price Display': '1.10400', 'SL Price Display': '1.09800',
            })
    frame = pd.DataFrame(rows)
    selected = attach_hourly_four_selection(frame, max_symbols=2)
    counts = selected.loc[selected['Hourly 4 Entry']].groupby('Symbol').size().to_dict()
    # Coverage should be visible for the low-frequency report symbol when its
    # quality is strong and there is a repeated valid opportunity stream.
    assert counts.get('EURUSD', 0) >= 5
    assert selected['Hourly 4 Entry'].groupby(selected['Datetime']).sum().eq(2).all()
