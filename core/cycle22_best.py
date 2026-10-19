"""Cycle 22 winner module: F1-P4 (C18-A3 execution upgrade, new broad champion).

F1-P4 = C18-A3's 26 equations VERBATIM (same checks, symbols, gates,
TP/SL multiples, scores) with two execution upgrades, both frozen from
Cycle 15 precedents -- NO re-mining, NO thresholds touched on unseen:

  1. TIGHTER TRAILING EXITS: once price moves +1.0xATR favorable, the stop
     ratchets to trail the favorable extreme by 0.3xATR (SL-first on
     same-bar ambiguity; initial TP/SL still apply; stop only tightens,
     never loosens; trailing updates apply from the next bar; 48h cap).
  2. DYNAMIC k (FS-C01 Rule A): k=3 if >=4 candidates, k=2 if >=2, else k=1
     (top-k by score per check, max 1 open trade per symbol).

Unseen (2025-10-05 -> 2026-10-05), SL-first, 1-pip costs:
  667 trades / +2,799.56 net pips / RoMAD 7.72 / Sharpe 6.55 /
  DD -362.51 / EV +4.20 / win 77.4%%. 10-check PASS (10/10), overfit PASS,
  used_unseen_for_selection=False. Net at 3-pip costs: +1,465.56.
  Chronological 10y (2016-01-01 -> 2026-10-05) at best N=120, $2,000 start:
  min equity +$1,195.25 -- SURVIVES (C18-A3 ruins at -$996.81).

Promoted by explicit user approval 2026-10-19 as the new DEFAULT
live-signal system ("new broad champion"), replacing C18-A3. C18-A3
(core/cycle18_best.py) and FT-C01 (core/cycle12_best.py) are KEPT
byte-identical and remain selectable via set_active_system('cycle18' /
'ft-c01'); see core/signal_mode.py for the router.

Source of truth: ~/workspace/fx/work_c22/results/comparison_table.csv (F1-P4 row)
Trade logs: ~/workspace/fx/work_c22/families/famF1/out/P4_*_log.csv
Rebuild: 667 / +2799.5625 / RoMAD 7.7226 -- exact match, see FIX_NOTES_20261019_CYCLE22.md

LIVE-EXECUTION NOTE (same caveat as Cycle 15): trailing exits assume the
broker/platform can manage a ratcheting stop per the policy above. If the
platform cannot trail, fall back to fixed exits (the initial TP/SL from
evaluate_cycle22_signals) -- that degrades to C18-A3 behavior.
"""
from __future__ import annotations

import pandas as pd

# The 26 equations are C18-A3's, imported -- single source of truth, so the
# equation set cannot drift from the researched champion. F1-P4 changed ONLY
# execution (trailing + dynamic k), never the equations.
from core.cycle18_best import (
    C18_EQUATIONS as C22_EQUATIONS,
    CYCLE18_CHECK_HOURS as CYCLE22_CHECK_HOURS,
    CYCLE18_SYMBOLS_N as CYCLE22_SYMBOLS_N,
    MAX_HOLD_HOURS,
    BASE_SPREAD_PIPS,
    TP_CLIP,
    SL_CLIP,
    evaluate_cycle18_signals,
    is_cycle18_check_time,
)

CYCLE22_VERSION = "cycle22-f1p4-v1"

# --- F1-P4 execution parameters (frozen; verified by exact rebuild) ---
EXIT_MODE_DEFAULT = "trailing"   # 'trailing' (F1-P4) | 'fixed' (C18-A3 behavior)
TRAIL_TRIGGER_ATR = 1.0          # trailing activates after +1.0xATR favorable
TRAIL_DIST_ATR = 0.3             # SL trails favorable extreme by 0.3xATR


def dynamic_k_rule(n_candidates: int) -> int:
    """Frozen FS-C01 Rule A: k=3 if >=4 candidates, k=2 if >=2, else k=1."""
    n = int(n_candidates)
    return 3 if n >= 4 else (2 if n >= 2 else 1)


def evaluate_cycle22_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate F1-P4 equations at one check time (h:30 UTC).

    Identical to C18-A3 evaluation (same 26 equations); only the exit
    management and entry selection differ. Returns one row per firing
    equation with TP/SL already clipped; each row also carries atr_pips
    so the live executor can arm the trailing stop (trigger 1.0xATR,
    distance 0.3xATR).
    """
    return evaluate_cycle18_signals(frames, check_time_utc)


def select_cycle22_entries(signals: pd.DataFrame, open_symbols=(),
                           k=None, dynamic: bool = True) -> pd.DataFrame:
    """Select F1-P4 entries: dynamic Rule A by default (the researched system).

    Top-k by score at this check, max 1 open trade per symbol.
    dynamic=True -> k = RuleA(len(signals)) reproduces F1-P4
    (unseen 667 trades / +2799.56 / RoMAD 7.72).
    Pass dynamic=False, k=2 to select like C18-A3 (fixed top-2).
    """
    if signals is None or len(signals) == 0:
        return signals.iloc[0:0] if signals is not None else pd.DataFrame()
    kk = dynamic_k_rule(len(signals)) if (dynamic and k is None) else k
    held = {str(s).upper() for s in (open_symbols or ())}
    out = []
    for _, row in signals.sort_values("score", ascending=False).iterrows():
        if kk is not None and len(out) >= kk:
            break
        if str(row["symbol"]).upper() in held:
            continue
        out.append(row)
        held.add(str(row["symbol"]).upper())
    return pd.DataFrame(out)


def is_cycle22_check_time(ts) -> bool:
    """True if ts (UTC) is at one of the F1-P4 check hours (:30)."""
    return is_cycle18_check_time(ts)
