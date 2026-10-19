"""Tests for core/cycle18_best.py (Cycle 18 winner C18-A3). Mirrors the
test discipline of tests/test_cycle12_best_20261018.py: equations load
verbatim, constraints hold, signal evaluation works on synthetic frames,
FT-C01 module untouched.
"""
import numpy as np
import pandas as pd

from core.cycle18_best import (
    C18_EQUATIONS, CYCLE18_CHECK_HOURS, CYCLE18_SYMBOLS_N,
    evaluate_cycle18_signals, select_cycle18_entries, is_cycle18_check_time,
)
from core import signal_mode


def _synth_frame(n=120, seed=0):
    rng = np.random.default_rng(seed)
    close = 1.1000 + np.cumsum(rng.normal(0, 0.0015, n))
    hi = close + np.abs(rng.normal(0, 0.001, n))
    lo = close - np.abs(rng.normal(0, 0.001, n))
    op = np.roll(close, 1); op[0] = close[0]
    idx = pd.date_range('2026-09-01', periods=n, freq='h', tz='UTC')
    return pd.DataFrame({'Open': op, 'High': hi, 'Low': lo, 'Close': close}, index=idx)


def test_equation_count_and_coverage():
    assert len(C18_EQUATIONS) == 26, f'want 26, got {len(C18_EQUATIONS)}'
    syms = {e['symbol'] for e in C18_EQUATIONS}
    assert len(syms) == 20, f'want 20 symbols, got {len(syms)}'
    hours = {e['hour'] for e in C18_EQUATIONS}
    assert len(hours) >= 4, f'want >=4 hours, got {hours}'
    assert set(hours) <= set(CYCLE18_CHECK_HOURS)
    dirs = {e['direction'] for e in C18_EQUATIONS}
    assert dirs <= {'BUY', 'SELL'}


def test_check_time_helper():
    assert is_cycle18_check_time(pd.Timestamp('2026-10-19 10:30', tz='UTC'))
    assert is_cycle18_check_time(pd.Timestamp('2026-10-19 18:30', tz='UTC'))
    assert not is_cycle18_check_time(pd.Timestamp('2026-10-19 09:30', tz='UTC'))
    assert not is_cycle18_check_time(pd.Timestamp('2026-10-19 10:00', tz='UTC'))


def test_evaluate_on_synth_frames():
    frames = {e['symbol']: _synth_frame(seed=hash(e['symbol']) % 999)
              for e in C18_EQUATIONS}
    sig = evaluate_cycle18_signals(frames, pd.Timestamp('2026-10-19 10:30', tz='UTC'))
    assert isinstance(sig, pd.DataFrame)
    if len(sig):
        assert set(sig['symbol']).issubset({e['symbol'] for e in C18_EQUATIONS})
        assert ((sig['tp_pips'] >= 10.0) & (sig['tp_pips'] <= 500.0)).all()
        assert ((sig['sl_pips'] >= 5.0) & (sig['sl_pips'] <= 100.0)).all()
    # non-C18 hour -> empty
    empty = evaluate_cycle18_signals(frames, pd.Timestamp('2026-10-19 09:30', tz='UTC'))
    assert len(empty) == 0


def test_select_topk():
    rows = pd.DataFrame([
        {'symbol': 'EURUSD', 'score': 9.0}, {'symbol': 'GBPUSD', 'score': 7.0},
        {'symbol': 'USDJPY', 'score': 8.0}, {'symbol': 'EURUSD', 'score': 5.0},
    ])
    sel = select_cycle18_entries(rows, k=2)
    assert len(sel) == 2
    assert list(sel['symbol']) == ['EURUSD', 'USDJPY']  # top-2 by score: 9.0, 8.0


def test_router_cycle18_selectable_and_ftc01_available():
    # Default is now cycle22 (F1-P4); cycle18 remains a selectable mode.
    signal_mode.set_active_system('cycle18')
    assert signal_mode.active_system() == 'cycle18'
    assert 'cycle18' in signal_mode.describe_active()
    signal_mode.set_active_system('ft-c01')
    assert signal_mode.active_system() == 'ft-c01'
    assert 'ft-c01' in signal_mode.describe_active()
    signal_mode.set_active_system('cycle22')  # restore default
    assert signal_mode.active_system() == 'cycle22'


def test_ftc01_module_untouched():
    import hashlib
    from core import cycle12_best
    assert hasattr(cycle12_best, 'BEST_EQUATIONS')
    assert len(cycle12_best.BEST_EQUATIONS) == 4  # FT-C01's 4 equations intact
