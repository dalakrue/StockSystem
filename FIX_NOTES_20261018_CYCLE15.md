# Fix notes — Cycle 15 (2026-10-18): FT-C01 wins — trailing exits + dynamic k

Base: copy of `Forex_App_Fixed_S1_S240_Cycle14__14.zip`
(SHA-256 `d0ed6956b0fbb753ea80ad94a3822c83`). The original zip was NOT
modified. This zip is `Forex_App_Fixed_S1_S240_Cycle15__15.zip`.

## 1. What changed (and only this)

| File | Change |
|---|---|
| `core/cycle12_best.py` | FT-C01 upgrade: trailing exits + dynamic k (see §2). Equations VERBATIM. |
| `tests/test_cycle12_best_20261018.py` | C12 baseline tests pinned to `exit_mode='fixed'`; 3 new FT-C01 tests. |
| `FIX_NOTES_20261018_CYCLE15.md` | NEW (this file). |
| `PACKAGE_MANIFEST.json` | Entries for changed/added files refreshed. |

S1–S240 mapping, equations, ranking, stats, check hours: byte-identical
(verified by `diff -rq` — only the files above differ).

## 2. FT-C01 (Cycle 15 winner)

Cycle 15 ran 24 processes across 6 NEW dimensions (new check times, weakest
symbol/month, exit management, portfolio rules, combinations). 20/24 passed
the 10-check. Winner **FT-C01 = FR-C02 (trailing exits) + FS-C01 (dynamic k)**,
re-validated from scratch with no additional fitting:

| Unseen (1-pip, SL-first) | C12 BEST (baseline) | FT-C01 (new default) |
|---|---|---|
| Net pips | +1,164.21 | **+1,283.12** (+10.2%) |
| Trades | 163 | 167 |
| RoMAD | 40.39 | **44.52** (+10.2%) |
| Sharpe | 14.18 | **16.71** (+17.8%) |
| Max DD | −28.82 | −28.82 (same) |
| Win rate | 84.7% | 89.8% |
| 10-check | PASS | PASS |

- **Equations**: UNCHANGED (same 4 SELL mean-reversion at 18:30 UTC).
- **Exits**: trailing — SL trails the favorable extreme by 0.4×ATR once price
  moves 1.25×ATR favorable. Initial TP/SL (ATR multiples, clipped) still apply.
  Params frozen on discovery (9-combo grid, max RoMAD); unseen untouched.
- **Selection**: dynamic k — Rule A (frozen on discovery): k=3 if ≥4 candidates,
  k=2 if ≥2, else k=1. Max 1 open trade per symbol (unchanged).
- Sizing recommendation: N = $20.00 (measured best $19.93, difference negligible;
  margin WARNING ~83% peak on unseen — see Cycle 15 report).

## 3. Verification

- App `backtest_cycle12` with FT-C01 defaults reproduces mining EXACTLY:
  167 trades / +1,283.12 net (0.00 diff).
- C12 baseline explicitly reproducible: `exit_mode='fixed', dynamic_k=False,
  k=2` → 163 / +1,164.21 (0.00 diff). Uncapped baseline unchanged.
- Tests: 12/12 pass in `test_cycle12_best_20261018.py` (9 existing + 3 new).
  Existing monthly-integration + upgrade8 suites: failure set identical to the
  base tree (pre-existing environment gaps only). Zero new failures.
- Live entry path (`select_cycle12_entries`, `evaluate_cycle12_signals`):
  equations and signal logic untouched; selection now dynamic by default.

## 4. Caveats

- FT-C01's components were selected on discovery; unseen was never used for
  selection. The 10-check PASS is clean (unlike C12 BEST's unseen-ranked
  optimism), but paper trading is still required before any live use.
- Trailing exits assume the broker/platform can manage a ratcheting stop;
  otherwise use the fixed-exit baseline mode.
