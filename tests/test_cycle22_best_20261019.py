"""Tests for core/cycle22_best.py (Cycle 22 winner F1-P4). Mirrors the
test discipline of tests/test_cycle18_best_20261019.py.

F1-P4 = C18-A3's 26 equations VERBATIM + trailing exits
(trigger 1.0xATR favorable, trail 0.3xATR) + dynamic k (FS-C01 Rule A).
Unseen: 667 trades / +2799.56 net / RoMAD 7.72.
"""
import numpy as np
import pandas as pd

from core.cycle22_best import (
    C22_EQUATIONS, CYCLE22_CHECK_HOURS, CYCLE22_SYMBOLS_N,
    CYCLE22_VERSION, EXIT_MODE_DEFAULT, TRAIL_TRIGGER_ATR, TRAIL_DIST_ATR,
    dynamic_k_rule, evaluate_cycle22_signals, select_cycle22_entries,
    is_cycle22_check_time,
)
from core import cycle18_best
from core import signal_mode


def _synth_frame(n=120, seed=0):
    rng = np.random.default_rng(seed)
    close = 1.1000 + np.cumsum(rng.normal(0, 0.0015, n))
    hi = close + np.abs(rng.normal(0, 0.001, n))
    lo = close - np.abs(rng.normal(0, 0.001, n))
    op = np.roll(close, 1); op[0] = close[0]
    idx = pd.date_range('2026-09-01', periods=n, freq='h', tz='UTC')
    return pd.DataFrame({'Open': op, 'High': hi, 'Low': lo, 'Close': close}, index=idx)


def test_equation_set_identical_to_c18a3():
    # F1-P4 uses C18-A3's equations verbatim: single source of truth.
    assert C22_EQUATIONS is cycle18_best.C18_EQUATIONS
    assert len(C22_EQUATIONS) == 26, f'want 26, got {len(C22_EQUATIONS)}'
    syms = {e['symbol'] for e in C22_EQUATIONS}
    assert len(syms) == 20 == CYCLE22_SYMBOLS_N, f'want 20 symbols, got {len(syms)}'
    hours = {e['hour'] for e in C22_EQUATIONS}
    assert len(hours) >= 4, f'want >=4 hours, got {hours}'
    assert set(hours) <= set(CYCLE22_CHECK_HOURS)


def test_f1p4_execution_params():
    # Frozen researched values: tighter trail 0.3xATR after 1.0xATR favorable.
    assert EXIT_MODE_DEFAULT == 'trailing'
    assert TRAIL_TRIGGER_ATR == 1.0, f'want 1.0, got {TRAIL_TRIGGER_ATR}'
    assert TRAIL_DIST_ATR == 0.3, f'want 0.3, got {TRAIL_DIST_ATR}'
    assert CYCLE22_VERSION == 'cycle22-f1p4-v1'


def test_dynamic_k_rulea():
    assert dynamic_k_rule(4) == 3
    assert dynamic_k_rule(7) == 3
    assert dynamic_k_rule(3) == 2
    assert dynamic_k_rule(2) == 2
    assert dynamic_k_rule(1) == 1
    assert dynamic_k_rule(0) == 1


def test_check_time_helper():
    assert is_cycle22_check_time(pd.Timestamp('2026-10-19 10:30', tz='UTC'))
    assert is_cycle22_check_time(pd.Timestamp('2026-10-19 18:30', tz='UTC'))
    assert not is_cycle22_check_time(pd.Timestamp('2026-10-19 09:30', tz='UTC'))
    assert not is_cycle22_check_time(pd.Timestamp('2026-10-19 10:00', tz='UTC'))


def test_evaluate_matches_c18_on_synth_frames():
    frames = {e['symbol']: _synth_frame(seed=hash(e['symbol']) % 999)
              for e in C22_EQUATIONS}
    sig22 = evaluate_cycle22_signals(frames, pd.Timestamp('2026-10-19 10:30', tz='UTC'))
    sig18 = cycle18_best.evaluate_cycle18_signals(
        frames, pd.Timestamp('2026-10-19 10:30', tz='UTC'))
    assert isinstance(sig22, pd.DataFrame)
    # Same equations -> identical signal sets (evaluation unchanged by F1-P4).
    assert len(sig22) == len(sig18)
    if len(sig22):
        assert set(sig22['equation']) == set(sig18['equation'])
        assert ((sig22['tp_pips'] >= 10.0) & (sig22['tp_pips'] <= 500.0)).all()
        assert ((sig22['sl_pips'] >= 5.0) & (sig22['sl_pips'] <= 100.0)).all()
        assert (sig22['atr_pips'] > 0).all()  # trailing executor needs atr_pips
    empty = evaluate_cycle22_signals(frames, pd.Timestamp('2026-10-19 09:30', tz='UTC'))
    assert len(empty) == 0


def test_select_dynamic_k():
    rows = pd.DataFrame([
        {'symbol': 'EURUSD', 'score': 9.0}, {'symbol': 'GBPUSD', 'score': 7.0},
        {'symbol': 'USDJPY', 'score': 8.0}, {'symbol': 'AUDUSD', 'score': 6.0},
        {'symbol': 'EURUSD', 'score': 5.0},
    ])
    # 5 candidates -> Rule A k=3, max 1 per symbol
    sel = select_cycle22_entries(rows)
    assert len(sel) == 3
    assert list(sel['symbol']) == ['EURUSD', 'USDJPY', 'GBPUSD']
    # 2 candidates -> k=2
    sel2 = select_cycle22_entries(rows.iloc[:2])
    assert len(sel2) == 2
    # 1 candidate -> k=1
    sel1 = select_cycle22_entries(rows.iloc[:1])
    assert len(sel1) == 1
    # fixed-k override still available (C18-A3 style)
    selk = select_cycle22_entries(rows, k=2, dynamic=False)
    assert len(selk) == 2


def test_router_defaults_to_cycle22_all_modes_available():
    assert signal_mode.active_system() == 'cycle22'
    assert 'cycle22' in signal_mode.describe_active()
    for mode in ('cycle18', 'ft-c01', 'cycle22'):
        signal_mode.set_active_system(mode)
        assert signal_mode.active_system() == mode
        assert mode in signal_mode.describe_active()
    signal_mode.set_active_system('cycle22')  # restore default
    assert signal_mode.active_system() == 'cycle22'
    try:
        signal_mode.set_active_system('nope')
    except ValueError:
        pass
    else:
        raise AssertionError('expected ValueError for unknown system')
    assert signal_mode.active_system() == 'cycle22'


def test_c18_and_ftc01_modules_untouched():
    assert hasattr(cycle18_best, 'C18_EQUATIONS')
    assert len(cycle18_best.C18_EQUATIONS) == 26  # C18-A3 intact
    from core import cycle12_best
    assert hasattr(cycle12_best, 'BEST_EQUATIONS')
    assert len(cycle12_best.BEST_EQUATIONS) == 4  # FT-C01 intact
