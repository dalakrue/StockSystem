# Fix notes — Cycle 16 (2026-10-18): 26 processes, no honest improvement — app UNCHANGED

Base: copy of `Forex_App_Fixed_S1_S240_Cycle15__15.zip`
(SHA-256 `c17b673001a43988...`). The C15 zip was NOT modified.
This zip is `Forex_App_Fixed_S1_S240_Cycle16__16.zip`.

## 1. Verdict: NO UPGRADE — FT-C01 retained

Cycle 16 ran 26 processes across 6 new dimensions (multi-timeframe H4/D1,
currency-strength intermarket filters, regime-adaptive trailing, Friday/
weekend handling, 6 new check times, misc exit/selection innovations).
20/26 pass the 10-check battery. Best C16 process FZ-C03 (dynamic-k RuleB:
k=4 if n>=4 else 2 if n>=2 else 1) reaches unseen RoMAD 45.07 vs FT-C01
44.52 (+1.2%), DD identical (-28.82), but Sharpe slightly worse
(16.36 vs 16.71).

A 5,000-resample bootstrap head-to-head on unseen gives
P(FZ-C03 RoMAD > FT-C01 RoMAD) = 0.497 — a coin flip. The +1.2% comes from
a 4-point k-rule grid and 4 extra unseen trades; it is selection noise,
not an honest beat. Per the strict upgrade rule (upgrade only on an
honest RoMAD beat with no worse drawdown), the app is NOT upgraded.

## 2. What changed (and only this)

| File | Change |
|---|---|
| `FIX_NOTES_20261018_CYCLE16.md` | NEW (this file). |
| `PACKAGE_MANIFEST.json` | Entry for the new file refreshed. |

Equations (FT-C01: 4 SELL mean-reversion + trailing 1.25/0.4 + dynamic k
RuleA), S1–S240 mapping, ranking, stats, check hours: byte-identical
(verified by `diff -rq` — only the two files above differ).
Sizing recommendation unchanged: N = $20.00 (no re-run, no new winner).

## 3. Cycle 16 findings (honest negatives)

- Family U (multi-timeframe): H4-momentum filter hurt unseen (38.40); D1 cap near-neutral (44.10); H4-vol filter vacuous.
- Family V (currency strength): best 41.20; discovery gain did not transfer; USD-regime filtering destroys edge (17.03).
- Family W (adaptive trailing): best 44.35 (tied); volatile bucket empty by construction (all equations gate atr_ratio<1.0); breakeven hybrid clearly worse (36.34).
- Family X (Friday/weekend): 3 honest failures; Friday 6h weekend-close flat (44.45). Friday was never broken.
- Family Y (new hours 22/0/1/2/3/4 UTC): ALL 6 FAIL the 10-check. No viable new hour; 18:30 UTC stands.
- Family Z (misc): only FZ-C03 above baseline (+1.2%, noise — not promoted).

## 4. Verification

- FT-C01 reproduction from this tree: 167 / +1283.12 / 44.52 (exact).
- App tests: C12 equation suite 9/9 + 3 FT-C01 tests pass; monthly-integration
  + upgrade8 suites show only the pre-existing environmental failures
  (Rangoon tz alias, pyarrow/Jinja2) — zero new failures.
- Uploaded C12/C13/C14/C15 zips untouched.

## 5. Caveats (unchanged)

- Paper trading before any live use. Trailing exits assume the broker/
  platform can manage a ratcheting stop; the app retains fixed-exit mode.
- Cycle 13 + 14 + 16: 166 new processes have now failed to beat FT-C01
  on RoMAD (C15's FT-C01 remains the only promoted improvement).
