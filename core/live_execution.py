"""Stage 2 — live market execution layer.

The frozen month-symbol equation strategy (Stage 1: S1-S240 mapping,
symbol+month equation, BUY/SELL direction, score, ranking) is NEVER modified
here. This module only re-prices what Stage 1 already decided, using CURRENT
OHLC data only:

- current price = close of the latest COMPLETED H1 candle at refresh time
- entry         = current price (BUY and SELL alike)
- TP/SL prices  = entry +/- pip distances (fixed or dynamic pip distances
                  resolved by Stage 1); always calculated from the CURRENT
                  entry. Historical TP/SL prices are never loaded.
- bias          = computed from current OHLC only (trend EMA fast/slow,
                  momentum, ATR volatility, lightweight middle standard
                  regime). Never taken from a historical TP/SL result.
- final decision = ALLOW when the strategy direction agrees with the bias
                  (or the bias is neutral); CONFLICT when they oppose.

No fitting, no optimization, no order sending.
"""
from __future__ import annotations

import calendar

import numpy as np
import pandas as pd

STAGE2_VERSION = 'live-execution-stage2-20261006-v1'

MIN_BARS_FOR_BIAS = 60
MOMENTUM_LOOKBACK = 24
ATR_SPAN = 14


def _as_of(as_of=None) -> pd.Timestamp:
    t = pd.Timestamp.now(tz='UTC') if as_of is None else pd.Timestamp(as_of)
    if t.tzinfo is None:
        t = t.tz_localize('UTC')
    return t.tz_convert('UTC')


def _completed_bars(frame: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Only bars that fully closed at or before ``as_of`` (Datetime + 1h <= as_of)."""
    g = frame.copy()
    g['Datetime'] = pd.to_datetime(g['Datetime'], utc=True, format='mixed').dt.tz_localize(None)
    done = g['Datetime'] + pd.Timedelta(hours=1) <= as_of.tz_localize(None)
    return g.loc[done].sort_values('Datetime').reset_index(drop=True)


def latest_completed_close(frame: pd.DataFrame, as_of=None):
    """(price, bar_open_time) of the latest completed H1 candle, or (nan, NaT)."""
    t = _as_of(as_of)
    g = _completed_bars(frame, t)
    if g.empty:
        return np.nan, pd.NaT
    price = pd.to_numeric(g['Close'], errors='coerce').iloc[-1]
    return (float(price) if np.isfinite(price) else np.nan, g['Datetime'].iloc[-1])


def pip_size(symbol: str) -> float:
    return .01 if str(symbol).upper().endswith('JPY') else .0001


def atr14_pips(frame: pd.DataFrame, symbol: str = '') -> float:
    """ATR(14) of completed bars, expressed in pips. NaN when unavailable.

    Uses the symbol's own pip size. Pure OHLC diagnostic; display only.
    """
    g = frame.copy()
    closes = pd.to_numeric(g.get('Close'), errors='coerce')
    hi = pd.to_numeric(g.get('High'), errors='coerce')
    lo = pd.to_numeric(g.get('Low'), errors='coerce')
    prev = closes.shift(1)
    tr = pd.concat([hi - lo, (hi - prev).abs(), (lo - prev).abs()], axis=1).max(axis=1)
    atr = tr.rolling(ATR_SPAN).mean()
    val = float(atr.iloc[-1]) if len(atr) and np.isfinite(atr.iloc[-1]) else np.nan
    if not np.isfinite(val):
        return np.nan
    if not symbol and 'Symbol' in g:
        symbol = str(g['Symbol'].iloc[0])
    return val / pip_size(symbol)


def target_display_columns(entry_price, side, symbol, tp_pips, sl_pips,
                           atr_pips=None, tp_bounds=(10, 200), sl_bounds=(10, 100)):
    """Explicit, unit-labeled target display columns (display only — zero
    backtest effect). Formulas per the strategy contract:

        pip      = 0.01 for JPY quotes, 0.0001 otherwise
        side     = +1 BUY, -1 SELL
        TP_price = entry_price + side * TP_pips * pip
        SL_price = entry_price - side * SL_pips * pip
        Gross_RR = TP_pips / SL_pips
        Net_RR   = (TP_pips - 1) / (SL_pips + 1)   (1-pip spread each side)

    A target PRICE is never a pip distance. Raises ValueError on invalid
    input instead of silently displaying a wrong target.
    """
    entry = float(entry_price)
    tp = float(tp_pips)
    sl = float(sl_pips)
    if not np.isfinite([entry, tp, sl]).all() or min(entry, tp, sl) <= 0:
        raise ValueError('invalid entry price or pip distances')
    if side not in (1, -1):
        raise ValueError('side must be +1 (BUY) or -1 (SELL)')
    pip = pip_size(symbol)
    tp_price = entry + side * tp * pip
    sl_price = entry - side * sl * pip
    out = {
        'TP Pips': tp,
        'SL Pips': sl,
        'TP Price': tp_price,
        'SL Price': sl_price,
        'Gross Reward Risk': tp / sl,
        'Net Reward Risk': (tp - 1) / (sl + 1),
        'TP Min Pips': float(tp_bounds[0]),
        'TP Max Pips': float(tp_bounds[1]),
        'SL Min Pips': float(sl_bounds[0]),
        'SL Max Pips': float(sl_bounds[1]),
    }
    a = float(atr_pips) if atr_pips is not None else np.nan
    out['ATR14 Pips'] = a
    out['TP ATR Multiple'] = tp / a if np.isfinite(a) and a > 0 else np.nan
    out['SL ATR Multiple'] = sl / a if np.isfinite(a) and a > 0 else np.nan
    return out


def compute_bias(frame: pd.DataFrame, as_of=None) -> dict:
    """Bias from CURRENT OHLC only: trend, moving averages, momentum,
    volatility and a lightweight middle standard regime.

    Returns dict(direction, source, trend, momentum, regime, volatility,
    ema_fast, ema_slow, bars_used). direction in BUY/SELL/NEUTRAL.
    """
    t = _as_of(as_of)
    out = dict(direction='NEUTRAL', source='no_completed_ohlc', trend=0, momentum=0,
               regime='neutral', volatility='unknown', ema_fast=None, ema_slow=None,
               bars_used=0, as_of=t.isoformat())
    g = _completed_bars(frame, t)
    closes = pd.to_numeric(g.get('Close'), errors='coerce').dropna()
    n = len(closes)
    out['bars_used'] = n
    if n < MIN_BARS_FOR_BIAS:
        out['source'] = f'insufficient_completed_bars(n={n}<{MIN_BARS_FOR_BIAS})'
        return out
    if n >= 200:
        f_span, s_span = 50, 200
    else:  # adaptive spans on shorter histories; still current-OHLC only
        f_span, s_span = max(10, n // 4), max(30, n // 2)
    ef = float(closes.ewm(span=f_span, adjust=False).mean().iloc[-1])
    es = float(closes.ewm(span=s_span, adjust=False).mean().iloc[-1])
    close = float(closes.iloc[-1])
    out['ema_fast'], out['ema_slow'] = ef, es
    trend = 1 if ef > es else (-1 if ef < es else 0)
    lookback = min(MOMENTUM_LOOKBACK, n - 1)
    ref = float(closes.iloc[-1 - lookback])
    momentum = 1 if close > ref else (-1 if close < ref else 0)
    hi = pd.to_numeric(g['High'], errors='coerce')
    lo = pd.to_numeric(g['Low'], errors='coerce')
    prev = closes.shift(1)
    tr = pd.concat([hi - lo, (hi - prev).abs(), (lo - prev).abs()], axis=1).max(axis=1)
    atr = tr.rolling(ATR_SPAN).mean()
    atr_now = float(atr.iloc[-1]) if np.isfinite(atr.iloc[-1]) else np.nan
    atr_med = float(atr.iloc[-48:].median()) if atr.iloc[-48:].notna().any() else np.nan
    if np.isfinite(atr_now) and np.isfinite(atr_med) and atr_med > 0:
        volatility = 'high' if atr_now > 1.5 * atr_med else ('low' if atr_now < 0.67 * atr_med else 'normal')
    else:
        volatility = 'unknown'
    # Middle standard regime, derived from current OHLC only: price and the
    # moving averages must agree for a directional regime label.
    if trend > 0 and close > ef:
        regime, regime_vote = 'bullish', 1
    elif trend < 0 and close < ef:
        regime, regime_vote = 'bearish', -1
    else:
        regime, regime_vote = 'neutral', 0
    score = 2 * trend + 2 * regime_vote + 1 * momentum
    direction = 'BUY' if score > 0 else ('SELL' if score < 0 else 'NEUTRAL')
    trend_txt = f'EMA{f_span}>EMA{s_span}' if trend > 0 else (f'EMA{f_span}<EMA{s_span}' if trend < 0 else f'EMA{f_span}=EMA{s_span}')
    mom_txt = f'momentum({lookback}h)=' + ('up' if momentum > 0 else 'down' if momentum < 0 else 'flat')
    out.update(direction=direction, trend=trend, momentum=momentum, regime=regime,
               volatility=volatility,
               source=(f'current_ohlc: {trend_txt}, {mom_txt}, '
                       f'middle_standard_regime={regime}, volatility(ATR{ATR_SPAN})={volatility}'))
    return out


def final_decision(strategy_direction: str, bias_direction: str) -> str:
    """Combine the Stage 1 strategy direction with the current-OHLC bias."""
    if strategy_direction not in ('BUY', 'SELL'):
        return 'NO_SIGNAL'
    if bias_direction == 'NEUTRAL':
        return f'ALLOW {strategy_direction} (bias neutral)'
    if bias_direction == strategy_direction:
        return f'ALLOW {strategy_direction}'
    return f'CONFLICT — strategy {strategy_direction} vs bias {bias_direction}'


def _decision_text(side, tp, sl) -> str:
    if side not in ('BUY', 'SELL'):
        return 'None'

    def fmt(x):
        v = pd.to_numeric(x, errors='coerce')
        return f'{float(v):.5f}' if pd.notna(v) and np.isfinite(v) else 'unavailable'

    return f'{side}, TP={fmt(tp)}, SL={fmt(sl)}'


def reprice_live_table(table: pd.DataFrame, frames: dict, as_of=None) -> pd.DataFrame:
    """Stage 2 re-pricing applied on EVERY ranking-table refresh.

    Stage 1 columns (Active S Column, Equation ID, Direction, scores, ranks)
    are left untouched. For every strategy hit row, Entry/TP/SL are rebuilt
    from the current OHLC close and the already-resolved pip distances.
    """
    t = _as_of(as_of)
    out = table.copy()
    lookup = {str(k).upper().replace('/', ''): v for k, v in (frames or {}).items()}
    for col, default in (('Live Current Price', np.nan), ('Live Entry Price', np.nan),
                         ('Live TP Price', np.nan), ('Live SL Price', np.nan),
                         ('Live Current Candle', pd.NaT)):
        if col not in out.columns:
            out[col] = default
    # Section-11 explicit target display columns (display only; they never
    # change signal eligibility, admission, exits or P/L).
    for col in ('TP Pips', 'SL Pips', 'Gross Reward Risk', 'Net Reward Risk',
                'TP Min Pips', 'TP Max Pips', 'SL Min Pips', 'SL Max Pips',
                'ATR14 Pips', 'TP ATR Multiple', 'SL ATR Multiple'):
        if col not in out.columns:
            out[col] = np.nan
    out['Live Bias'] = 'NEUTRAL'
    out['Live Bias Source'] = ''
    out['Live Final Decision'] = 'NO_SIGNAL'
    out['Live Entry Basis'] = ''
    out['Live Reprice Time'] = t.tz_localize(None)
    out['Live Stage'] = STAGE2_VERSION

    hit = out.get('Strategy Hit Count', pd.Series(0, index=out.index)).astype(int).eq(1)
    quote_col = pd.to_numeric(out.get('Actual Entry Quote', pd.Series(np.nan, index=out.index)),
                              errors='coerce')
    for i in out.index[hit]:
        symbol = str(out.at[i, 'Symbol'])
        frame = lookup.get(symbol.upper().replace('/', ''))
        if frame is None:
            continue
        price, bar = latest_completed_close(frame, t)
        bias = compute_bias(frame, t)
        out.at[i, 'Live Bias'] = bias['direction']
        out.at[i, 'Live Bias Source'] = bias['source']
        out.at[i, 'Live Final Decision'] = final_decision(out.at[i, 'Direction'], bias['direction'])
        out.at[i, 'Live Current Price'] = price
        out.at[i, 'Live Current Candle'] = bar
        side = 1 if out.at[i, 'Direction'] == 'BUY' else (-1 if out.at[i, 'Direction'] == 'SELL' else 0)
        if side == 0:
            continue
        tp_pips = pd.to_numeric(out.at[i, 'Suggested TP Pips'], errors='coerce')
        sl_pips = pd.to_numeric(out.at[i, 'Suggested SL Pips'], errors='coerce')
        if not (np.isfinite(tp_pips) and np.isfinite(sl_pips)):
            continue
        pip = pip_size(symbol)
        quote = float(quote_col.at[i]) if np.isfinite(quote_col.at[i]) else np.nan
        # Held/admitted rows priced from an executable broker quote are never
        # re-priced by a refresh: the stored entry/TP/SL stand. Only new
        # candidate indications without a quote are rebuilt from the current
        # completed candle (indicative reference, never a fill).
        basis_quote = np.isfinite(quote)
        if basis_quote:
            # Executable broker quote at the check: the actual fill evidence.
            # Entry/TP/SL stay quote-based (journal admission path); the live
            # current price is still shown for reference.
            entry = quote
            out.at[i, 'Live Entry Price'] = entry
            out.at[i, 'Live Entry Basis'] = 'EXECUTABLE_QUOTE'
            out.at[i, 'Live TP Price'] = out.at[i, 'TP Price']
            out.at[i, 'Live SL Price'] = out.at[i, 'SL Price']
            out.at[i, 'Strategy Decision'] = _decision_text(
                out.at[i, 'Direction'], out.at[i, 'TP Price'], out.at[i, 'SL Price'])
            tp_price = float(pd.to_numeric(out.at[i, 'TP Price'], errors='coerce'))
            sl_price = float(pd.to_numeric(out.at[i, 'SL Price'], errors='coerce'))
        else:
            # No executable quote: rebuild Entry/TP/SL from CURRENT OHLC so a
            # displayed TP can never already be passed at refresh time.
            if not np.isfinite(price):
                continue
            entry = float(price)
            tp_price = entry + side * float(tp_pips) * pip
            sl_price = entry - side * float(sl_pips) * pip
            out.at[i, 'Live Entry Price'] = entry
            out.at[i, 'Live Entry Basis'] = 'CURRENT_CANDLE_CLOSE'
            out.at[i, 'Live TP Price'] = tp_price
            out.at[i, 'Live SL Price'] = sl_price
            # The strategy decision display is rebuilt from current OHLC, so a TP
            # can never already be passed at display time.
            out.at[i, 'Target Reference Price'] = entry
            out.at[i, 'TP Price'] = tp_price
            out.at[i, 'SL Price'] = sl_price
            for c in ('Suggested TP', 'Suggested TP Price', 'tp_price', 'TP_Price'):
                out.at[i, c] = tp_price
            for c in ('Suggested SL', 'Suggested SL Price', 'sl_price', 'SL_Price'):
                out.at[i, c] = sl_price
            out.at[i, 'TP Price Display'] = f'{tp_price:.5f}'
            out.at[i, 'SL Price Display'] = f'{sl_price:.5f}'
            out.at[i, 'Target Price Basis'] = 'CURRENT_CANDLE_CLOSE (LIVE_REPRICED)'
            out.at[i, 'Strategy Decision'] = _decision_text(out.at[i, 'Direction'], tp_price, sl_price)
        # Explicit target display columns. Display only: they describe the
        # priced target; they never alter eligibility, admission, exits or P/L.
        try:
            disp = target_display_columns(
                entry, side, symbol, float(tp_pips), float(sl_pips),
                atr_pips=atr14_pips(frame, symbol))
        except ValueError:
            continue
        for c, v in disp.items():
            if c in ('TP Price', 'SL Price'):
                # 'TP Price'/'SL Price' keep the authoritative priced values
                # set above; the display dict must agree with them.
                continue
            out.at[i, c] = v
        out.at[i, 'Live Entry Basis'] = ('EXECUTABLE_QUOTE' if basis_quote
                                         else 'CURRENT_CANDLE_CLOSE')
    return out


def _month_label(month) -> str:
    try:
        m = int(month)
        return f'{m} ({calendar.month_name[m]})' if 1 <= m <= 12 else str(month)
    except (TypeError, ValueError):
        return str(month)


def debug_rows(repriced: pd.DataFrame) -> pd.DataFrame:
    """Debug rows from an already Stage-2-repriced table (no double reprice)."""
    hit = repriced.get('Strategy Hit Count', pd.Series(0, index=repriced.index)).astype(int).eq(1)
    rows = []
    for i in repriced.index[hit]:
        r = repriced.loc[i]
        rows.append({
            'Symbol': r['Symbol'],
            'Strategy ID': r.get('Equation ID', ''),
            'Month': _month_label(r.get('Equation Month', '')),
            'Equation': f"{r.get('Active S Column', '')}",
            'Signal Time': r.get('check_at', ''),
            'Direction': r.get('Direction', ''),
            'Current Price': r.get('Live Current Price', np.nan),
            'Entry': r.get('Live Entry Price', np.nan),
            'Entry Basis': r.get('Live Entry Basis', ''),
            'TP': r.get('Live TP Price', np.nan),
            'SL': r.get('Live SL Price', np.nan),
            'TP Pips': r.get('TP Pips', np.nan),
            'SL Pips': r.get('SL Pips', np.nan),
            'Gross Reward Risk': r.get('Gross Reward Risk', np.nan),
            'Net Reward Risk': r.get('Net Reward Risk', np.nan),
            'ATR14 Pips': r.get('ATR14 Pips', np.nan),
            'TP ATR Multiple': r.get('TP ATR Multiple', np.nan),
            'SL ATR Multiple': r.get('SL ATR Multiple', np.nan),
            'Target Price Basis': r.get('Target Price Basis', ''),
            'Bias Source': r.get('Live Bias Source', ''),
            'Bias Direction': r.get('Live Bias', ''),
            'Final Decision': r.get('Live Final Decision', ''),
        })
    cols = ['Symbol', 'Strategy ID', 'Month', 'Equation', 'Signal Time', 'Direction',
            'Current Price', 'Entry', 'Entry Basis', 'TP', 'SL',
            'TP Pips', 'SL Pips', 'Gross Reward Risk', 'Net Reward Risk',
            'ATR14 Pips', 'TP ATR Multiple', 'SL ATR Multiple',
            'Target Price Basis', 'Bias Source', 'Bias Direction', 'Final Decision']
    return pd.DataFrame(rows, columns=cols)


def build_debug_table(table: pd.DataFrame, frames: dict, as_of=None) -> pd.DataFrame:
    """Debug table: Symbol | Strategy ID | Month | Equation | Signal Time |
    Direction | Current Price | Entry | TP | SL | Bias Source | Bias Direction |
    Final Decision."""
    return debug_rows(reprice_live_table(table, frames, as_of=as_of))


def validate_live_prices(debug: pd.DataFrame) -> pd.DataFrame:
    """Requirement 8 check: for every suggested trade, BUY needs
    current price < TP and SELL needs current price > TP. Any row failing
    this means the TP was already passed at display time (bug still exists).

    Returns the violating rows with a 'Violation' reason column (empty = pass).
    """
    bad = []
    for _, r in debug.iterrows():
        row = r.to_dict()
        price, tp, entry = r.get('Current Price'), r.get('TP'), r.get('Entry')
        if not (np.isfinite(price) and np.isfinite(tp)):
            bad.append({**row, 'Violation': 'missing price/TP'})
            continue
        direction = str(r.get('Direction', ''))
        if direction == 'BUY' and not (price < tp):
            bad.append({**row, 'Violation': 'BUY: current price already >= TP'})
        elif direction == 'SELL' and not (price > tp):
            bad.append({**row, 'Violation': 'SELL: current price already <= TP'})
        # Re-priced rows must use the current price as entry; executable-quote
        # rows keep the actual quote as entry by design.
        if (r.get('Entry Basis') == 'CURRENT_CANDLE_CLOSE' and np.isfinite(entry)
                and not np.isclose(entry, price, rtol=0, atol=1e-9)):
            bad.append({**row, 'Violation': 'entry != current price'})
    cols = list(debug.columns) + ['Violation']
    return pd.DataFrame(bad, columns=cols)
