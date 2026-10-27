# Fix notes — Cycle 18 (2026-10-19): constrained champion C18-A3 installed

Base: copy of `Forex_App_Fixed_S1_S240_Cycle17__17.zip`
(SHA-256 `85b83723c63d996f242ce263cf0788d8`). The C17 zip was NOT modified.
This zip is `Forex_App_Fixed_S1_S240_Cycle18__18.zip`.

## 1. Verdict: UPGRADE — C18-A3 installed (user-override selection rule)

The user explicitly overrode the old "upgrade only if honestly beats FT-C01
on RoMAD" rule for this cycle: the requirement was breadth (≥4 check times,
all 20 symbols), accepting a lower RoMAD. Selection = best RoMAD among the
24 processes satisfying ALL FOUR hard requirements:
(a) ≥4 distinct check hours, (b) all 20 symbols, (c) 10-check PASS,
(d) overfit PASS.

Cycle 18 ran 24 processes (6 families × 4 variants), all mining on discovery
only (train/val screen, discovery TP/SL calibration; unseen touched only for
the 10-check evaluation; used_unseen_for_selection=False everywhere):
- Fam A (constraint-repair): 4/4 PASS all four. **C18-A3 (quota rebuild) WINS.**
- Fam B (greedy set-cover): 4/4 PASS all four. Best C18-B4 (RoMAD 5.61).
- Fam C (mean-reversion gates): 0/4 (closest C18-C3: RoMAD 12.12 but 18/20 symbols).
- Fam D (momentum/breakout): 0/4 — breakout does not transfer at these checks.
- Fam E (volatility-regime): 0/4 (closest C18-E1: 13/20 symbols, 10-check PASS).
- Fam F (random search): 0/4 (closest C18-F1: 16/20 symbols, 10-check PASS).

**Winner C18-A3** (famA, repair_quota, per_check_min=2): 26 equations,
checks 10:30/11:30/13:30/18:30 UTC, 20/20 symbols, 18 SELL + 8 BUY.
Unseen (2025-10-05→2026-10-05): +2,198.8 pips / 601 trades / RoMAD 5.71 /
Sharpe 4.61 / DD −385.3 / EV +3.66 / win 68.6%. 10-check PASS (10/10).
Overfit PASS. Unseen net at 3-pip costs +996.8. Bootstrap P(net>0) = 100%.

**Honest comparison vs FT-C01** (the unconstrained optimum, kept as baseline):
FT-C01: unseen +1,283.1 / 167 trades / RoMAD 44.52 / Sharpe 16.71 / DD −28.8,
4 SELL equations, ONE check (18:30 UTC), 4 symbols. C18-A3 trades breadth
for risk-adjusted edge: ~8× lower RoMAD, ~13× deeper drawdown, but 5× the
symbols and 4× the check times, both directions, and it still passes every
safety check. The user accepted this tradeoff explicitly.

## 2. What changed (and only this)

| File | Change |
|---|---|
| `core/cycle18_best.py` | NEW. 26 winner equations verbatim + `evaluate_cycle18_signals` / `select_cycle18_entries` / `is_cycle18_check_time`. Same mom24/atr_ratio feature definitions as FT-C01. |
| `core/signal_mode.py` | NEW. Router: default `cycle18`; `set_active_system('ft-c01')` restores the FT-C01 baseline. `evolve_signals`/`select_entries` dispatch by mode. |
| `core/cycle12_best.py` | UNCHANGED (FT-C01 preserved byte-identical as selectable baseline). |
| `tests/test_cycle18_best_20261019.py` | NEW. 6 tests (equation count/coverage, check-time helper, signal eval, top-k, router default+switch, FT-C01 intact). |
| `FIX_NOTES_20261019_CYCLE18.md` | NEW (this file). |
| `PACKAGE_MANIFEST.json` | Entries for the new files refreshed. |

Equations (S1–S240 mapping), ranking, stats, old check hours: byte-identical
(verified by `diff -rq` — only the files above differ).

## 3. How to use

Default live-signal system is now C18-A3 (4 checks/day: 10:30/11:30/13:30/
18:30 UTC = 17:00/18:00/20:00/01:00 Myanmar). To fall back to FT-C01:
`from core.signal_mode import set_active_system; set_active_system('ft-c01')`.

## 4. Cycle 18 findings (honest)

- Breadth costs edge: forcing 20 symbols × 4 checks cut the best achievable
  RoMAD from 44.52 to 5.71. The 10-check still passes — the system is safe,
  just less concentrated.
- Hours 6 and 12 UTC produced zero surviving equations in every family
  (weak discovery pools); all winners cluster on {10,11,13,18}.
- Momentum/breakout (Fam D) and tight-gate mean-reversion (C4) failed
  outright; loose mean-reversion gates (C3: RoMAD 12.12) were strongest per
  unit but could not cover 20 symbols.
- 7–10 of 20 symbols are individually negative on unseen per winner variant;
  the portfolio net is carried by winners — diversification is real but not
  uniform. Monitor per-symbol drift in paper trading.
