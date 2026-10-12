"""Master-upgrade __8 tests (2026-10-09).

Covers the command's app-side requirements:
- Section 11: explicit, unit-labeled target display columns with exact
  pip/price formulas (EURJPY SELL reference reproduced to the pip).
- Executable-quote rows are NEVER re-priced by a refresh; new candidate
  indications reprice from the current completed candle only.
- core/research_pack: versioned 120-equation pack loads once, keeps
  Strict_Valid=false, and is NOT wired into live defaults.
- Execution policy keeps the validated schedule: 06/07/10/11/12/13 UTC,
  weekend skip, max 4 new symbols per check (validated k=4).
"""
import numpy as np
import pandas as pd
import pytest

from core import live_execution as lx


# ---------------------------------------------------------------------------
# Section 11: explicit target display columns
# ---------------------------------------------------------------------------

def test_target_columns_eurjpy_sell_reference():
    # Command reference: EURJPY SELL, entry 176.81995, ATR14 = 30.9871428571
    # JPY pips, 5.5x ATR TP -> 170.4292857143 pips, SL 10 pips.
    d = lx.target_display_columns(176.81995, -1, 'EURJPY',
                                  170.4292857143, 10.0,
                                  atr_pips=30.9871428571)
    assert d['TP Pips'] == pytest.approx(170.4292857143)
    assert d['SL Pips'] == pytest.approx(10.0)
    # Target PRICE, not a pip distance: ~1.70429 yen below entry.
    assert d['TP Price'] == pytest.approx(175.1156571429, rel=1e-9)
    assert d['SL Price'] == pytest.approx(176.91995, rel=1e-9)
    assert d['Gross Reward Risk'] == pytest.approx(17.0429285714, rel=1e-9)
    assert d['Net Reward Risk'] == pytest.approx(15.4026623377, rel=1e-9)
    assert d['TP Min Pips'] == 10 and d['TP Max Pips'] == 200
    assert d['SL Min Pips'] == 10 and d['SL Max Pips'] == 100
    assert d['ATR14 Pips'] == pytest.approx(30.9871428571)
    assert d['TP ATR Multiple'] == pytest.approx(5.5, rel=1e-9)
    assert d['SL ATR Multiple'] == pytest.approx(10.0 / 30.9871428571, rel=1e-9)


def test_target_columns_buy_signs():
    d = lx.target_display_columns(1.1000, 1, 'EURUSD', 50.0, 30.0)
    assert d['TP Price'] == pytest.approx(1.1050)
    assert d['SL Price'] == pytest.approx(1.0970)
    assert d['Gross Reward Risk'] == pytest.approx(50.0 / 30.0)
    assert d['Net Reward Risk'] == pytest.approx(49.0 / 31.0)


def test_target_columns_pip_size_jpy_vs_fx():
    jpy = lx.target_display_columns(150.00, 1, 'USDJPY', 100.0, 50.0)
    fx = lx.target_display_columns(1.1000, 1, 'EURUSD', 100.0, 50.0)
    assert jpy['TP Price'] == pytest.approx(151.00)   # 100 * 0.01
    assert fx['TP Price'] == pytest.approx(1.1100)     # 100 * 0.0001


@pytest.mark.parametrize('entry,side,sym,tp,sl', [
    (0.0, 1, 'EURUSD', 50.0, 30.0),          # non-positive entry
    (1.1, 0, 'EURUSD', 50.0, 30.0),          # bad side
    (1.1, 1, 'EURUSD', -5.0, 30.0),          # negative TP
    (1.1, 1, 'EURUSD', np.nan, 30.0),        # NaN distance
])
def test_target_columns_reject_invalid(entry, side, sym, tp, sl):
    with pytest.raises(ValueError):
        lx.target_display_columns(entry, side, sym, tp, sl)


def test_display_columns_do_not_change_pricing():
    # Display helper is pure: same inputs -> same outputs, no side effects.
    a = lx.target_display_columns(176.81995, -1, 'EURJPY', 170.4292857143, 10.0)
    b = lx.target_display_columns(176.81995, -1, 'EURJPY', 170.4292857143, 10.0)
    assert a == b


# ---------------------------------------------------------------------------
# Reprice behavior: quote rows frozen, indication rows repriced
# ---------------------------------------------------------------------------

def _frame(symbol, price, n=120):
    times = pd.date_range(pd.Timestamp('2026-10-08 12:00') - pd.Timedelta(hours=n - 1),
                          periods=n, freq='h')
    return pd.DataFrame({'Datetime': times, 'Open': price, 'High': price + 0.0005,
                         'Low': price - 0.0005, 'Close': price, 'Symbol': symbol})


def _hit_row(symbol, direction, tp_pips, sl_pips, quote=np.nan):
    return {'Symbol': symbol, 'Direction': direction, 'Active S Column': 'S1',
            'Equation ID': f'{symbol}-10-X', 'Equation Month': 10,
            'Suggested TP Pips': tp_pips, 'Suggested SL Pips': sl_pips,
            'Strategy Hit Count': 1,
            'check_at': pd.Timestamp('2026-10-08 13:30', tz='UTC'),
            'Target Reference Price': 1.1000, 'TP Price': 1.1050, 'SL Price': 1.0970,
            'Target Price Basis': 'COMPLETED_CANDLE_CLOSE (INDICATIVE)',
            'Actual Entry Quote': quote,
            'Strategy Decision': 'stale'}


def test_executable_quote_row_never_reprices():
    as_of = pd.Timestamp('2026-10-08 13:30', tz='UTC')
    table = pd.DataFrame([_hit_row('EURUSD', 'BUY', 50.0, 30.0, quote=1.1010)])
    frames = {'EURUSD': _frame('EURUSD', 1.1200)}  # market moved away
    once = lx.reprice_live_table(table, frames, as_of=as_of)
    twice = lx.reprice_live_table(once, frames, as_of=as_of)
    r1, r2 = once.iloc[0], twice.iloc[0]
    assert r1['Live Entry Basis'] == 'EXECUTABLE_QUOTE'
    # Stored quote-based entry/TP/SL stand across refreshes.
    assert r1['Live Entry Price'] == pytest.approx(1.1010)
    assert r2['Live Entry Price'] == pytest.approx(1.1010)
    assert r2['Live TP Price'] == pytest.approx(r1['Live TP Price'])
    assert r2['Live SL Price'] == pytest.approx(r1['Live SL Price'])
    # Display columns describe the quote-based target.
    assert r2['TP Pips'] == pytest.approx(50.0)
    assert r2['Gross Reward Risk'] == pytest.approx(50.0 / 30.0)
    assert r2['Net Reward Risk'] == pytest.approx(49.0 / 31.0)


def test_indication_row_reprices_and_carries_display_columns():
    as_of = pd.Timestamp('2026-10-08 13:30', tz='UTC')
    table = pd.DataFrame([_hit_row('EURUSD', 'BUY', 50.0, 30.0)])
    frames = {'EURUSD': _frame('EURUSD', 1.1200)}
    out = lx.reprice_live_table(table, frames, as_of=as_of)
    r = out.iloc[0]
    assert r['Live Entry Basis'] == 'CURRENT_CANDLE_CLOSE'
    assert r['Live Entry Price'] == pytest.approx(1.1200)
    assert r['Live TP Price'] == pytest.approx(1.1200 + 50 * 0.0001)
    assert r['Live SL Price'] == pytest.approx(1.1200 - 30 * 0.0001)
    assert r['TP Pips'] == pytest.approx(50.0)
    assert r['SL Pips'] == pytest.approx(30.0)
    assert r['Gross Reward Risk'] == pytest.approx(50.0 / 30.0)
    assert r['Net Reward Risk'] == pytest.approx(49.0 / 31.0)
    assert r['TP Min Pips'] == 10 and r['TP Max Pips'] == 200
    assert r['SL Min Pips'] == 10 and r['SL Max Pips'] == 100
    assert np.isfinite(r['ATR14 Pips']) and r['ATR14 Pips'] > 0
    assert r['TP ATR Multiple'] == pytest.approx(50.0 / r['ATR14 Pips'])
    assert r['Target Price Basis'] == 'CURRENT_CANDLE_CLOSE (LIVE_REPRICED)'


def test_debug_table_carries_target_columns():
    as_of = pd.Timestamp('2026-10-08 13:30', tz='UTC')
    table = pd.DataFrame([_hit_row('EURUSD', 'BUY', 50.0, 30.0)])
    frames = {'EURUSD': _frame('EURUSD', 1.1200)}
    dbg = lx.build_debug_table(table, frames, as_of=as_of)
    for col in ('TP Pips', 'SL Pips', 'Gross Reward Risk', 'Net Reward Risk',
                'ATR14 Pips', 'TP ATR Multiple', 'SL ATR Multiple',
                'Target Price Basis'):
        assert col in dbg.columns, col
    assert dbg.iloc[0]['Gross Reward Risk'] == pytest.approx(50.0 / 30.0)


def test_atr14_pips_jpy_scaling():
    n = 120
    times = pd.date_range(pd.Timestamp('2026-10-08 12:00') - pd.Timedelta(hours=n - 1),
                          periods=n, freq='h')
    fr = pd.DataFrame({'Datetime': times, 'Open': 150.0, 'High': 150.5,
                       'Low': 149.5, 'Close': 150.0, 'Symbol': 'USDJPY'})
    a = lx.atr14_pips(fr, 'USDJPY')
    # True range ~1.0 price units = 100 JPY pips; ATR(14) of a flat 1.0 range.
    assert a == pytest.approx(100.0, rel=0.05)


# ---------------------------------------------------------------------------
# Research pack: versioned, single-load, research-only
# ---------------------------------------------------------------------------

def test_research_pack_loads_once_with_120_equations():
    from core.research_pack import load_pack, get_equation, replaced_s_ids, PACK_VERSION
    p1 = load_pack()
    p2 = load_pack()
    assert p1 is p2  # loaded exactly once
    assert p1['version'] == PACK_VERSION
    assert len(p1['equations']) == 120
    assert p1['manifest']['fresh_unseen_available'] is False
    ids = replaced_s_ids()
    assert len(ids) == 120 and ids[0].startswith('S') and len(set(ids)) == 120
    # Key mapping: zero-based key 2 -> S3 (spot check against Strategy field).
    eq = get_equation(2)
    assert eq['s_id'] == 'S3'
    assert eq['spec']['Strategy'] == 'S3'
    for spec in p1['equations'].values():
        assert spec['strict_valid'] is False
        assert spec['side'] in (1, -1)


def test_research_pack_inference_contract():
    import sys
    sys.path.insert(0, 'core/research_pack')
    import candidate_runtime_v1 as cr
    from core.research_pack import get_equation
    spec = get_equation(2)['spec']
    model = spec['model']
    feats = model['features']
    # Synthetic finite features -> finite prediction, finite clip applied.
    x = pd.DataFrame(np.zeros((3, len(feats))), columns=feats)
    pred = cr.predict_candidate(x, model)
    assert np.isfinite(pred).all() and len(pred) == 3
    side, score = cr.candidate_signal(x, spec)
    assert set(np.unique(side)) <= {spec['side'], 0}
    # Non-finite feature coordinate -> no signal from that row.
    x2 = x.copy()
    x2.iloc[0, 0] = np.inf
    side2, _ = cr.candidate_signal(x2, spec)
    assert side2[0] == 0
    # Exit distances honor the 10..200 / 10..100 clamps.
    tp, sl = cr.candidate_distances(np.array([5.0, 1000.0]), spec)
    assert (tp >= 10).all() and (tp <= 200).all()
    assert (sl >= 10).all() and (sl <= 100).all()


def test_research_pack_not_wired_into_defaults():
    # No default import path may pull the candidate pack into live ranking.
    import subprocess
    code = ("import core.monthly_runtime, core.live_execution, "
            "core.execution_policy_20261003; "
            "import sys; "
            "print('research_pack' in str([m for m in sys.modules]))")
    out = subprocess.run(['python3', '-c', code], capture_output=True, text=True,
                         cwd='.', timeout=120)
    assert out.returncode == 0, out.stderr[-500:]
    assert 'False' in out.stdout


# ---------------------------------------------------------------------------
# Execution policy: validated settings preserved
# ---------------------------------------------------------------------------

def test_execution_policy_keeps_validated_schedule():
    from core.execution_policy_20261003 import get_policy
    p = get_policy()
    # Validated profitable check hours (A/B tested 2026-10-07); the research
    # bundle's 04/08/12/14/16/18 UTC schedule is kept as a labeled alternative
    # scenario, not the app default.
    assert tuple(p.check_hours) == (6, 7, 10, 11, 12, 13)
    assert tuple(p.skip_entry_weekdays) == (5, 6)  # no weekend entries
    assert p.max_new_symbols == 4  # validated K_ENTRIES_PER_CHECK=4
    assert p.max_hold_hours == 48
    assert p.spread_pips == 1.0
