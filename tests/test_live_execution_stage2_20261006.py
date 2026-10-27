"""Stage 2 live-execution contract (2026-10-06 fix).

- Entry/TP/SL are rebuilt from CURRENT OHLC on every refresh; a displayed TP
  can never already be passed (requirement 8).
- Bias comes from current OHLC (trend, MA, momentum, volatility, middle
  standard regime), never from a historical TP/SL result (requirement 4).
- Debug table carries the required traceability columns (requirement 7).
- Backtest replay fills at the next H1 open from that candle's OHLC with
  TP/SL computed from the entry; no future candle information (requirement 6).
"""
import numpy as np
import pandas as pd
import pytest

from core import live_execution as lx
from core.monthly_runtime import raw_frame
from core.monthly_backtest import make_tapes, replay_trade, _utc


def _trend_frame(symbol, start_price, drift, n=400, end=None, seed=0):
    rng = np.random.default_rng(seed)
    end = pd.Timestamp('2026-10-06 05:00') if end is None else pd.Timestamp(end)
    times = pd.date_range(end - pd.Timedelta(hours=n - 1), end, freq='h')
    walk = start_price + drift * np.arange(n) + np.cumsum(rng.normal(0, 0.0004, n))
    return pd.DataFrame({'Datetime': times, 'Open': walk,
                         'High': walk + np.abs(rng.normal(0, 0.0006, n)),
                         'Low': walk - np.abs(rng.normal(0, 0.0006, n)),
                         'Close': walk + rng.normal(0, 0.0002, n),
                         'Symbol': symbol})


def _stage1_table():
    return pd.DataFrame([
        {'Symbol': 'EURUSD', 'Direction': 'BUY', 'Active S Column': 'S37',
         'Equation ID': 'EURUSD-10-X1', 'Equation Month': 10,
         'Suggested TP Pips': 50.0, 'Suggested SL Pips': 30.0,
         'Strategy Hit Count': 1,
         'check_at': pd.Timestamp('2026-10-06 06:30', tz='UTC'),
         # Stale check-time snapshot: price has since moved past this TP.
         'Target Reference Price': 1.1000, 'TP Price': 1.1050, 'SL Price': 1.0970,
         'Target Price Basis': 'COMPLETED_CANDLE_CLOSE (INDICATIVE)',
         'Strategy Decision': 'BUY, TP=1.10500, SL=1.09700'},
        {'Symbol': 'GBPUSD', 'Direction': 'SELL', 'Active S Column': 'S42',
         'Equation ID': 'GBPUSD-10-X2', 'Equation Month': 10,
         'Suggested TP Pips': 40.0, 'Suggested SL Pips': 25.0,
         'Strategy Hit Count': 1,
         'check_at': pd.Timestamp('2026-10-06 06:30', tz='UTC'),
         'Target Reference Price': 1.3600, 'TP Price': 1.3560, 'SL Price': 1.3625,
         'Target Price Basis': 'COMPLETED_CANDLE_CLOSE (INDICATIVE)',
         'Strategy Decision': 'SELL, TP=1.35600, SL=1.36250'},
        {'Symbol': 'USDJPY', 'Direction': 'WAIT', 'Active S Column': 'S9',
         'Equation ID': 'USDJPY-10-X3', 'Equation Month': 10,
         'Suggested TP Pips': np.nan, 'Suggested SL Pips': np.nan,
         'Strategy Hit Count': 0,
         'check_at': pd.Timestamp('2026-10-06 06:30', tz='UTC'),
         'Target Reference Price': np.nan, 'TP Price': np.nan, 'SL Price': np.nan,
         'Target Price Basis': 'NONE', 'Strategy Decision': 'None'},
    ])


def _frames():
    return {'EURUSD': _trend_frame('EURUSD', 1.10, 0.00015, seed=1),
            'GBPUSD': _trend_frame('GBPUSD', 1.36, -0.00015, seed=2)}


def test_reprice_rebuilds_entry_tp_sl_from_current_close():
    frames = _frames()
    as_of = pd.Timestamp('2026-10-06 06:30', tz='UTC')
    out = lx.reprice_live_table(_stage1_table(), frames, as_of=as_of)
    eur = out.loc[out.Symbol == 'EURUSD'].iloc[0]
    gbp = out.loc[out.Symbol == 'GBPUSD'].iloc[0]
    # Stage 1 columns untouched.
    assert eur['Active S Column'] == 'S37' and eur['Direction'] == 'BUY'
    assert eur['Equation ID'] == 'EURUSD-10-X1'
    # Entry == current close (latest completed candle), not the stale 1.1000.
    expected_close = float(frames['EURUSD']['Close'].iloc[-1])
    assert eur['Live Current Price'] == pytest.approx(expected_close)
    assert eur['Live Entry Price'] == pytest.approx(eur['Live Current Price'])
    # BUY: TP = entry + 50 pips, SL = entry - 30 pips.
    assert eur['Live TP Price'] == pytest.approx(eur['Live Entry Price'] + 50 * 0.0001)
    assert eur['Live SL Price'] == pytest.approx(eur['Live Entry Price'] - 30 * 0.0001)
    # SELL: TP = entry - 40 pips, SL = entry + 25 pips.
    assert gbp['Live TP Price'] == pytest.approx(gbp['Live Entry Price'] - 40 * 0.0001)
    assert gbp['Live SL Price'] == pytest.approx(gbp['Live Entry Price'] + 25 * 0.0001)
    # Display columns rebuilt from current OHLC.
    assert eur['TP Price'] == pytest.approx(eur['Live TP Price'])
    assert eur['Strategy Decision'] == f"BUY, TP={eur['Live TP Price']:.5f}, SL={eur['Live SL Price']:.5f}"
    assert eur['Target Price Basis'] == 'CURRENT_CANDLE_CLOSE (LIVE_REPRICED)'
    # Non-hit row untouched.
    jpy = out.loc[out.Symbol == 'USDJPY'].iloc[0]
    assert jpy['Strategy Decision'] == 'None' and np.isnan(jpy['Live Entry Price'])


def test_stale_tp_bug_is_gone_requirement_8():
    frames = _frames()
    as_of = pd.Timestamp('2026-10-06 06:30', tz='UTC')
    dbg = lx.build_debug_table(_stage1_table(), frames, as_of=as_of)
    # Before the fix, the stale BUY TP=1.10500 was already passed by the
    # current price (~1.16). After Stage 2 reprice it cannot be.
    assert (dbg.loc[dbg.Direction == 'BUY', 'Current Price'] < dbg.loc[dbg.Direction == 'BUY', 'TP']).all()
    assert (dbg.loc[dbg.Direction == 'SELL', 'Current Price'] > dbg.loc[dbg.Direction == 'SELL', 'TP']).all()
    assert lx.validate_live_prices(dbg).empty


def test_validate_live_prices_flags_passed_tp():
    dbg = pd.DataFrame([{
        'Symbol': 'EURUSD', 'Strategy ID': 'X', 'Month': '10 (October)', 'Equation': 'S1',
        'Signal Time': pd.Timestamp('2026-10-06 06:30', tz='UTC'), 'Direction': 'BUY',
        'Current Price': 1.1600, 'Entry': 1.1600, 'TP': 1.1050, 'SL': 1.1570,
        'Bias Source': 's', 'Bias Direction': 'BUY', 'Final Decision': 'ALLOW BUY'}])
    bad = lx.validate_live_prices(dbg)
    assert len(bad) == 1 and 'already >= TP' in bad.iloc[0]['Violation']


def test_bias_from_current_ohlc_trend_and_regime():
    up = lx.compute_bias(_trend_frame('EURUSD', 1.10, 0.0004, seed=3))
    down = lx.compute_bias(_trend_frame('GBPUSD', 1.36, -0.0004, seed=4))
    assert up['direction'] == 'BUY' and 'EMA50>EMA200' in up['source']
    assert 'middle_standard_regime=bullish' in up['source']
    assert down['direction'] == 'SELL' and 'EMA50<EMA200' in down['source']
    assert 'middle_standard_regime=bearish' in down['source']
    assert 'current_ohlc' in up['source'] and 'current_ohlc' in down['source']
    # Perfectly flat market -> neutral, never forced.
    times = pd.date_range('2026-10-06 00:00', periods=300, freq='h')
    flat = pd.DataFrame({'Datetime': times, 'Open': 1.10, 'High': 1.1005,
                         'Low': 1.0995, 'Close': 1.10, 'Symbol': 'EURUSD'})
    assert lx.compute_bias(flat)['direction'] == 'NEUTRAL'
    # Too few bars -> neutral with a clear source note.
    short = lx.compute_bias(_trend_frame('EURUSD', 1.10, 0.0004, n=30))
    assert short['direction'] == 'NEUTRAL' and 'insufficient_completed_bars' in short['source']


def test_final_decision_allow_and_conflict():
    assert lx.final_decision('BUY', 'BUY') == 'ALLOW BUY'
    assert lx.final_decision('SELL', 'SELL') == 'ALLOW SELL'
    assert lx.final_decision('BUY', 'NEUTRAL') == 'ALLOW BUY (bias neutral)'
    assert lx.final_decision('BUY', 'SELL').startswith('CONFLICT')
    assert lx.final_decision('WAIT', 'BUY') == 'NO_SIGNAL'


def test_debug_table_has_required_columns():
    dbg = lx.build_debug_table(_stage1_table(), _frames(),
                               as_of=pd.Timestamp('2026-10-06 06:30', tz='UTC'))
    required = ['Symbol', 'Strategy ID', 'Month', 'Equation', 'Signal Time',
                'Current Price', 'Entry', 'TP', 'SL',
                'Bias Source', 'Bias Direction']
    assert all(c in dbg.columns for c in required)
    assert len(dbg) == 2  # only hit rows
    assert dbg['Month'].str.contains('October').all()


def _replay_setup():
    # 200 continuous H1 bars on a Wednesday; steady uptrend so the research
    # bias stays bullish and cannot flip a BUY before the barriers resolve.
    n = 200
    start = pd.Timestamp('2026-10-07 00:00')  # Wednesday
    times = pd.date_range(start, start + pd.Timedelta(hours=n - 1), freq='h')
    close = 1.1000 + 0.00005 * np.arange(n)
    df = pd.DataFrame({'Datetime': times, 'Open': close, 'High': close + 0.0004,
                       'Low': close - 0.0004, 'Close': close, 'Symbol': 'EURUSD'})
    i = 30  # Thursday 2026-10-08 06:00 UTC: mid-week, no session-filter gap
    fill = times[i]
    df.loc[df.index[i + 1], ['Open', 'High', 'Low', 'Close']] = [1.1052, 1.1056, 1.1048, 1.1052]
    # Bar i+2 touches BOTH barriers (entry=1.1015 -> TP 1.1065, SL 1.0985):
    # TP wins (validated TP-first rule).
    df.loc[df.index[i + 2], ['Open', 'High', 'Low', 'Close']] = [1.1054, 1.1110, 1.0970, 1.1080]
    raw = raw_frame(df, 'EURUSD')
    tapes = make_tapes(raw)
    signal = {'Symbol': 'EURUSD', 'Equation ID': 'EURUSD-10-X1', 'Active S Column': 'S37',
              'Datetime': fill, 'check_at': fill - pd.Timedelta(minutes=30),
              'Direction': 'BUY', 'Suggested TP Pips': 50.0, 'Suggested SL Pips': 30.0,
              'Max Hold Hours': 48, 'Danger Enabled': False, 'signal_bar_open': times[i - 1]}
    return tapes['EURUSD'], signal, float(df.loc[df.index[i], 'Open'])


def test_backtest_fill_uses_that_candle_ohlc_no_lookahead():
    tape, signal, fill_open = _replay_setup()
    trade = replay_trade(signal, tape)
    assert trade is not None
    # Entry is the fill candle's open (that candle's OHLC), 30 min after check.
    assert trade['entry_at'] == _utc(signal['Datetime'])
    assert trade['entry_at'] == _utc(signal['check_at']) + pd.Timedelta(minutes=30)
    assert trade['entry_price'] == pytest.approx(fill_open)
    # TP/SL are computed from the entry, never loaded from history.
    assert trade['tp_price'] == pytest.approx(fill_open + 50 * 0.0001)
    assert trade['sl_price'] == pytest.approx(fill_open - 30 * 0.0001)
    assert trade['tp_pips'] == 50.0 and trade['sl_pips'] == 30.0
    # TP-first on the dual-touch candle; exit uses only bars >= entry.
    assert trade['exit_reason'] == 'TP' and trade['ambiguous']
    assert trade['exit_price'] == pytest.approx(trade['tp_price'])
    assert trade['exit_at'] >= trade['entry_at']
    assert trade['net_pips'] == pytest.approx(trade['gross_pips'] - 1.0)  # 1 pip spread


def test_backtest_entry_rejects_wrong_fill_time():
    tape, signal, _ = _replay_setup()
    bad = dict(signal, Datetime=signal['Datetime'] + pd.Timedelta(minutes=5))
    with pytest.raises(ValueError):
        replay_trade(bad, tape)
