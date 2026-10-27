# Fix notes — Cycle 22 (2026-10-19): F1-P4 installed as new broad champion

Base: copy of `Forex_App_Fixed_S1_S240_Cycle18__18.zip`
(SHA-256 `bee599515a8754e6c5385bfa1a87d9f89ef6a7b25182ce0afc9163f21cd6436a`).
The C18 zip was NOT modified. This zip is
`Forex_App_Fixed_S1_S240_Cycle22__22.zip`.

## 1. Verdict: UPGRADE — F1-P4 installed (user-approved promotion)

Cycle 22 ran 40 processes (8 families) for up to 4 hours hunting for a
broad system (≥4 checks, 20 symbols) that beats Cycle 17's FT-C01 overall.
None cleared that bar (the hunt proved breadth and RoMAD-44 structurally
incompatible in this design space). BUT the best attempt, **F1-P4**
(famF1: C18-A3 + execution upgrades), honestly beats the CURRENT app
champion C18-A3 on every metric, and the user explicitly approved
promoting it as the "new broad champion".

**F1-P4** = C18-A3's 26 equations VERBATIM (same checks 10:30/11:30/13:30/
18:30 UTC, same 20 symbols, same mom24/atr_ratio gates, same TP/SL
multiples, same scores) + two frozen execution upgrades (no re-mining):
1. Tighter trailing exits: stop ratchets to trail the favorable extreme by
   0.3×ATR once price moves +1.0×ATR favorable (SL-first, initial TP/SL
   still apply, 48h cap).
2. Dynamic k (FS-C01 Rule A): k=3 if ≥4 candidates, k=2 if ≥2, else k=1.

Unseen (2025-10-05→2026-10-05), SL-first, 1-pip: **667 trades / +2,799.56
net pips / RoMAD 7.72 / Sharpe 6.55 / DD −362.51 / EV +4.20 / win 77.4%**.
10-check PASS (10/10), overfit PASS, used_unseen_for_selection=False.
Net at 3-pip costs: +1,465.56. Chronological 10y at best N=120 ($2,000
start): min equity +$1,195.25 — SURVIVES (C18-A3 ruins at −$996.81).

Rebuild check (independent, from frozen spec): 667 trades / +2799.5625 net /
RoMAD 7.7226 — EXACT match with the reported numbers.

**Honest comparison vs C18-A3** (previous default, kept as selectable mode):
net +2,799.6 vs +2,198.8 (+27%), RoMAD 7.72 vs 5.71 (+35%), DD −362.5 vs
−385.3 (shallower), win 77.4% vs 68.6%, 3-pip net +1,465.6 vs +996.8, and
10y survival vs 10y ruin. Strictly better on every dimension.

## 2. What changed (and only this)

- ADDED `core/cycle22_best.py`: F1-P4 module. The 26 equations are IMPORTED
  from `core.cycle18_best` (single source of truth — the set cannot drift);
  new code = trailing constants (TRAIL_TRIGGER_ATR=1.0, TRAIL_DIST_ATR=0.3),
  `dynamic_k_rule` (Rule A), `evaluate_cycle22_signals`,
  `select_cycle22_entries` (dynamic Rule A default), `is_cycle22_check_time`.
- MODIFIED `core/signal_mode.py`: default active system is now `cycle22`
  (F1-P4); `set_active_system()` accepts 'cycle22' / 'cycle18' / 'ft-c01';
  `describe_active()` documents all three; `select_entries(..., k=None)`
  applies Rule A for cycle22.
- ADDED `tests/test_cycle22_best_20261019.py`: 9 tests (equation identity,
  trailing params, Rule A, check-time helper, evaluate parity with C18 on
  synthetic frames, dynamic-k selection, router default + all three modes,
  C18/FT-C01 modules untouched).
- MODIFIED `tests/test_cycle18_best_20261019.py`: router test updated for
  the new default (cycle22); C18 select/evaluate tests unchanged.
- ADDED this file.

PRESERVED (verified by diff): S1–S240 mapping, all existing equations
(`core/cycle18_best.py` and `core/cycle12_best.py` byte-identical),
ranking logic, performance statistics. Only the 5 files above differ
from the C18 tree.

## 3. Live-execution note

Trailing exits assume the broker/platform can manage a ratcheting stop:
once favorable excursion ≥ 1.0×ATR, move the stop to (favorable extreme ∓
0.3×ATR), only ever tightening, checked SL-first each bar, 48h cap. If the
platform cannot trail, run fixed exits (initial TP/SL from the signal) —
that degrades gracefully to C18-A3 behavior. Paper-trade before live,
same standing rule (4–8 weeks).

## 2026-10-19 AMENDMENT — check-time banner fix (user-reported)
The "Next entry check" banner and the YES/NO check-time indicator in
ui/field3_multisymbol_regime_summary_20260722.py were still computed over the
OLD 6-check schedule (06:30/10:30/11:30/12:30/13:30 UTC) after the default
system switched to cycle22 (10:30/11:30/13:30/18:30 UTC). Symptom: at
01:44 UTC the banner showed next check 13:00 MMT (06:30 UTC) instead of the
correct 17:00 MMT (10:30 UTC).
Fix: core/signal_mode.py gained active_check_hours() + is_active_check_time();
the banner's next-check computation, entry-check indicator, and "which
system" label now follow the ACTIVE system (cycle22/cycle18/ft-c01).
Verified: next check from 2026-10-19 01:44 UTC = 10:30 UTC = 17:00 MMT.

## 2026-10-19 UI POLISH (user-requested)
- Redesigned the check-time banner: compact gradient card, responsive clamp()
  typography, wrapping flexbox clocks, glowing status dot — mobile-friendly,
  ~40% less vertical space.
- Moved the two download buttons (CSV + colored Excel) from ABOVE the Middle
  Standard Regime Ranking table to BELOW it (full-width mobile stack).
- Shortened freshness pill text.
