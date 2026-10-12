# Audited H1 application — 3 October 2026

This package updates the attached application and includes regression checks,
an audit runner, a code diff and a Word report. Read this file before older dated
upgrade notes, which describe earlier behavior.

## Start the application

Use Python 3.12, create a virtual environment, then run:

```sh
python -m pip install -r requirements.txt
streamlit run app.py
```

Keep your existing provider and account configuration. No new credentials are
included. Original application modules and supplied data are preserved. Finder
has raw all-symbol OHLC, calculated first-half and second-half downloads, and an
optional complete calculated CSV. The halves split at the requested time-window
midpoint; concatenate them to recover the complete export without a duplicate
boundary.

## Current execution policy

`config/audited_execution.json` owns the policy: UTC checks at 04:00, 08:00,
12:00, 14:00, 16:00 and 18:00; skip Sunday and Monday entries; at most two new
symbols per check; four display slots; maximum 24 elapsed hours. `Asia/Rangoon`
uses those actual local times, including half-hour UTC checks. An H1 bar is
available at its close, then filled at the next executable open. Stale signals
and missing execution quotes are rejected or censored. The NY weekly calendar
is a conservative session proxy, not proof of a broker-executable quote.

The 103-pip / 2.9-ATR stop ceiling and other thresholds are declared research
defaults, not optimized recommendations. Required structural stops exceeding
the budget are rejected. Relaxation defaults to 0; 0, .10, .20 and .40 can be
compared in training only.

## What changed

- TP columns include 21 boolean checks, pass counts, rejection reasons,
  conditional reach forecasts and separate research/live eligibility.
- Thirty duplicate strategy IDs remain as aliases without votes. S87–S90 are
  disabled for contradictory gates. There are 86 possible canonical owners;
  actual activity must be measured. Missing real volume disables volume rules.
- Typed fields own execution. STRATEGY, RESCUE and RANK_FILL are explicit.
  Zero-hit display slots show `None` and cannot become orders. Held symbols are
  skipped; the third and fourth candidates are inspected.
- Portfolio replay, fixed-grid search, final-pair labels, offline chronological
  classifier calibration, empirical forecasts and account-risk utilities are
  included. Portfolio H1 ambiguity is TP-first; SL-first is a separate stress.
  Target forecasting uses the conservative SL-first convention.
- Labels require the full interval and mature after the endpoint bar closes:
  normally 25 hours after entry for a 24-hour holding limit. This availability
  delay prevents endpoint-open lookahead.

## Evidence and limitations

The attachment lacks the referenced 283,516-row, 20-symbol two-year OHLC dataset.
The claimed TP=77 / SL=103 winner, 38,104 weekend rows and unprofitable
241,081-pair validation search have **not been reproduced**. Old saved state is
not substituted for that dataset. Portfolio improvement, conditional forecast
intervals and live acceptance are unmeasured.

Broker bid/ask and lower-timeframe paths, an untouched post-freeze forward
period, longer independent training history and account inputs are also missing.
Four separate regime-specific strategy gates, a rank-fill counterfactual, true
walk-forward refitting, a controlled legacy comparison, DSR/PBO and empirical
currency correlations remain incomplete. The report records these gaps.
**No live configuration qualifies in this delivery.**

Live `entry_eligible` stays false without verified broker data, calibrated model
evidence and a matching independent acceptance manifest. The offline runner
does not generate that manifest. Money/percent results require currency,
equity, lot rules, conversion quotes and broker pip values.

## Reproduce the checks

```sh
python -m pip install -r requirements-test.txt
python -m pytest tests -q --junitxml=reports/verification.xml
python research/audit_runner.py --output reports/attachment_audit
```

With the actual research CSVs:

```sh
python research/audit_runner.py --csv first.csv --csv second.csv --output reports/research_run --full-suite --exhaustive-grid
```

The large run performs full regeneration and training-selected removals, eight
scenarios over three splits, weekly block bootstrap, cost/intrabar stresses,
target sensitivity, symbol reallocation and ablations. The exhaustive grid is
the new engine's research grid, not reproduction of the missing legacy policy.
Pairs above the stop budget are search diagnostics only. Classification fits
matured pre-2025 labels; validation/2026 are evaluated without fitting them.
Research CSVs do not automatically prove broker prices or untouched forward data.

See `reports/20261003_delivery/Audit_Report.docx`, `verification_results.json`,
`input_inventory.json`, `changed_files.json`, and `code_changes.diff`. The
scenario table records 96 blocked combinations. Empty CSVs explicitly named
templates contain no fabricated trades or performance.
