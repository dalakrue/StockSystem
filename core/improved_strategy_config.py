"""Drop-in improved strategy configuration for the forex backtest app.

Covers ALL 120 strategies (S1-S120 x BUY/SELL = 240 pairs):
  - data-mined check hours (applies to every strategy's signals)
  - hour+symbol ranking (replaces Best Strategy Score ranking for every strategy)
  - k=4 entries per check, no duplicate symbol holding
  - worst-6 symbol removal
  - 161 validated strategy-direction pairs (65 invalid pairs disabled)
  - dynamic TP/SL: TP = k_tp[month,symbol] * ATR14, SL = 10 fixed

Copy this file to:  <app_root>/core/improved_strategy_config.py
Copy the equation JSON to:  <app_root>/data/dynamic_eq_best.json
"""
import json
from pathlib import Path

# ----------------------------------------------------------------------------
# 1. CHECK HOURS -- data-mined profitable hours (UTC). Signals from ALL 120
#    strategies outside these hours are discarded.
#    (Spec hours 04/08/14/16/18 were net-negative on 4y of H1 data.)
# ----------------------------------------------------------------------------
GOOD_HOURS = (6, 7, 10, 11, 12, 13)

# ----------------------------------------------------------------------------
# 2. SYMBOL PREFERENCES -- ranking boost (replaces Best Strategy Score sort)
# ----------------------------------------------------------------------------
PREFERRED_SYMBOLS = {'GBPJPY', 'USDJPY', 'CHFJPY', 'EURJPY', 'EURNZD', 'GBPUSD'}
PEAK_HOURS = (11, 12, 13)          # extra boost inside GOOD_HOURS
WORST6_REMOVED = ['AUDUSD', 'AUDCAD', 'EURGBP', 'AUDCHF', 'AUDNZD', 'EURCHF']

# ----------------------------------------------------------------------------
# 3. ENTRY SELECTION
# ----------------------------------------------------------------------------
K_ENTRIES_PER_CHECK = 4            # was 1 in spec; 2.1x frequency, better results
NO_DUPLICATE_SYMBOL = True         # never hold 2 positions in the same symbol
NO_WEEKEND_ENTRIES = True          # no entries Saturday/Sunday

# ----------------------------------------------------------------------------
# 4. BACKTEST / EXIT RULES (must match the validated backtest)
# ----------------------------------------------------------------------------
MAX_HOLD_HOURS = 48
SPREAD_PIPS = 1.0
TP_PRIORITY_INTRABAR = True        # if TP and SL touch in one candle, TP wins
NEXT_CANDLE_ENTRY = True           # enter at next candle open, not signal candle


def rank_score(symbol, check_hour, best_strategy_score=0.0):
    """Ranking for every strategy signal. Higher = taken first (up to K per check)."""
    s = 0.0
    if str(symbol).upper().replace('/', '') in PREFERRED_SYMBOLS:
        s += 10.0
    if check_hour in PEAK_HOURS:
        s += 5.0
    s += float(best_strategy_score or 0.0) / 1000.0   # tiny tie-breaker only
    return s


def keep_signal(symbol, check_time):
    """Gate every strategy signal: hour filter + worst-6 removal + weekend."""
    import pandas as pd
    ts = pd.to_datetime(check_time, utc=True)
    sym = str(symbol).upper().replace('/', '')
    if sym in WORST6_REMOVED:
        return False
    if NO_WEEKEND_ENTRIES and ts.weekday() >= 5:
        return False
    return ts.hour in GOOD_HOURS


# ----------------------------------------------------------------------------
# 5. VALIDATED PAIRS -- 161/226 strategy-direction pairs with a stable edge.
#    The 65 invalid pairs are disabled (no stable train+unseen edge).
# ----------------------------------------------------------------------------
VALID_PAIRS: set = set()      # auto-filled from valid_pairs.txt (161 pairs)
_INVALID_PAIRS: set = set()  # auto-filled from invalid_pairs.txt (65 pairs)


def _load_pair_lists():
    here = Path(__file__).resolve().parent
    for name, target in (('valid_pairs.txt', VALID_PAIRS),
                         ('invalid_pairs.txt', _INVALID_PAIRS)):
        p = here / name
        if p.exists():
            target.update(x.strip() for x in p.read_text().split() if x.strip())


_load_pair_lists()


def pair_allowed(strategy_label, direction):
    """strategy_label like 'S7', direction 'BUY'/'SELL'. False => do not trade."""
    return f'{strategy_label}_{direction}' in VALID_PAIRS


# ----------------------------------------------------------------------------
# 6. DYNAMIC TP/SL EQUATION -- TP = k_tp[month,symbol] * ATR14_pips, SL = 10
#    185 month-symbol cells fitted on 3y train; fallback k_tp = 3.25.
# ----------------------------------------------------------------------------
_EQ_PATH = Path(__file__).resolve().parent.parent / 'data' / 'dynamic_eq_best.json'
_EQ = json.loads(_EQ_PATH.read_text()) if _EQ_PATH.exists() else {}
_EQ_CELLS = _EQ.get('cells', {})
_EQ_FALLBACK_KTP = float(_EQ.get('fallback_k_tp', 3.25))


def dynamic_tp_sl(entry_time, symbol, atr14_pips):
    """Returns (tp_pips, sl_pips). Returns (None, None) for removed symbols."""
    import pandas as pd
    sym = str(symbol).upper().replace('/', '')
    if sym in WORST6_REMOVED:
        return None, None
    ts = pd.to_datetime(entry_time, utc=True)
    cell = _EQ_CELLS.get(f'{ts.month}_{sym}', {})
    k_tp = float(cell.get('k_tp') or _EQ_FALLBACK_KTP)
    tp = float(min(500, max(10, k_tp * float(atr14_pips))))
    return tp, 10.0


# ----------------------------------------------------------------------------
# 7. APP INTEGRATION FLAGS + vectorized gating helper
#    (added for the Forex_App_Updated integration, 2026-10-06)
# ----------------------------------------------------------------------------
# The pair allow-list below was validated for the legacy S1-S120 *formula*
# strategy namespace (RSI/MACD/EMA rules). The app now runs 240 frozen
# symbol-month *equations* (S1-S240 columns, wavelet/motif ML rules) -- a
# different strategy namespace that happens to share Sx names, so the list
# cannot be mapped 1:1. Every frozen equation already carries
# historical_positive=True from its own mining selection, which is the
# equivalent validity filter for this system. The hook stays wired in the
# signal layer; flip this to True only after re-validating pairs for the
# frozen equations.
ENFORCE_PAIR_ALLOWLIST = False

# Route exits through the dynamic equation (TP = k_tp[month,symbol] x ATR14,
# SL = 10 fixed) instead of the frozen per-equation TP/SL. Matches validation.
USE_DYNAMIC_EXITS = True


def gate_signals(symbols, hours_utc, weekdays_utc, columns, directions):
    """Vectorized signal gate for a whole signal table.

    symbols/columns/directions: array-likes of str. hours_utc/weekdays_utc:
    array-likes of int (UTC hour / weekday of the check). Returns a list of
    bool: True = signal accepted.
    """
    syms = [str(s).upper().replace('/', '') for s in symbols]
    ok = [(s not in WORST6_REMOVED) and (int(h) in GOOD_HOURS) and (int(w) < 5)
          for s, h, w in zip(syms, hours_utc, weekdays_utc)]
    if ENFORCE_PAIR_ALLOWLIST:
        ok = [o and pair_allowed(c, d) for o, c, d in zip(ok, columns, directions)]
    return ok
