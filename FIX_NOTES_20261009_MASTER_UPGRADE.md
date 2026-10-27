# FIX NOTES — 2026-10-09 — Master Upgrade (__8)

Source: `FOREX_App_Upgrade_Master_Command.docx` (2026-10-09) +
`DE7BF1ED-285F-489F-A5C1-26DFA3410277-Forex_240_Research_Bundle(1).zip`
(2026-10-08 research: 120 provisional equations, 30,240 trials, 13 scenarios).
Base: `Forex_App_Fixed_S1_S240_RawSplitRanges__7.zip` (preserved; untouched).

## What changed (app behavior)

1. **Explicit target display columns** — `core/live_execution.py`
   - New `target_display_columns(entry, side, symbol, tp_pips, sl_pips, atr_pips)`
     with the exact contract formulas (pip 0.01 JPY / 0.0001 else;
     TP_price = entry + side·TP_pips·pip; SL_price = entry − side·SL_pips·pip;
     Gross_RR = TP/SL; Net_RR = (TP−1)/(SL+1)). Raises on invalid input.
   - New `atr14_pips(frame, symbol)` diagnostic.
   - `reprice_live_table` now writes, per hit row (display only, zero P/L effect):
     TP Pips, SL Pips, Gross Reward Risk, Net Reward Risk,
     TP Min/Max Pips, SL Min/Max Pips, ATR14 Pips, TP/SL ATR Multiple.
   - `debug_rows` / `build_debug_table` carry the same columns.
2. **Quote-based rows are never re-priced by a refresh.** Rows admitted from an
   executable broker quote keep their stored entry/TP/SL across refreshes
   (explicit guard + idempotency test). Only new candidate indications without
   a quote are rebuilt from the current completed candle (indicative).
3. **Versioned research candidate pack** — new `core/research_pack/`
   - `candidate_equations_120_v1.json` (sha256-verified copy of the research
     JSON), `candidate_runtime_v1.py` (verbatim inference reference),
     `loader.py` (single-load, read-only, validates all 120 specs),
     `pack_manifest.json` (provenance, freeze time, Strict_Valid=false).
   - JSON key k (zero-based) maps to S{k+1} in `core/equation_column_map.json`.
   - **Not wired into live ranking defaults.** Research-only evaluation path;
     all 120 keep Strict_Valid=false (no fresh unseen validation exists).
   - Rollback: delete `core/research_pack/` — nothing else imports it.
4. **New tests** — `tests/test_upgrade8_master_command_20261009.py` (16 tests,
   all pass): EURJPY SELL reference reproduced exactly (entry 176.81995,
   TP 170.4292857143 pips → 175.1156571429, SL 10 → 176.91995,
   gross RR 17.0429, net RR 15.4027); invalid-input rejection; quote-row
   idempotency; pack integrity + inference contract; policy preservation.

## Deliberate decisions (validated settings kept, conflicts documented)

- **Check hours stay 06/07/10/11/12/13 UTC** (`core/execution_policy_20261003.py`
  unchanged). The research bundle was mined under 04/08/12/14/16/18 UTC; our
  2026-10-07 A/B tests found 04/08/14/16/18 net-negative. Per standing rule,
  the validated schedule is kept; the bundle schedule is available only as a
  separately-labeled alternative scenario, never the default.
- **max_new_symbols stays 4** (validated K_ENTRIES_PER_CHECK=4; k=5/6 tested
  worse unseen). The command's one-symbol-per-check policy is the research
  replay rule, not the app default — changing it would alter live trading
  results without A/B evidence.
- **Candidate pack is NOT the default** (command's own rule: unverified
  candidates must not be approved for live use in defaults/exports).
- **No new mining cycles run.** The bundle's declared budget (4 cycles, 30,240
  trials) was spent honestly with all failures reported; further cycles need a
  new recorded budget and fresh unseen data (none exists).

## Verification

- Independent ledger reconciliation: all 13 scenario net-pip totals in
  `research/scenario_comparison.csv` match `trade_history_all_scenarios.csv`
  row sums exactly (e.g. E: 42,974.85; Baseline: 20,261.79). Ledger rows =
  closed trades + censored entries (Baseline 3,914 = 3,650 + 264).
- 4y CSV audit: 531,840 rows, 20 symbols, 2022-10-05 06:00 → 2026-10-05 06:00
  UTC — matches the research manifest.
- Test suites: new 16/16 pass; `test_live_execution_stage2_20261006.py` +
  `test_monthly_equations_integration.py` failure sets are byte-identical to
  pristine __7 (4 failed + 8 errors pre-existing: pytz `Asia/Rangoon` env
  issue and unrelated legacy failures). Zero regressions.
- Strategy engine untouched: S1–S240 mapping, equations, ranking, exits
  unchanged; only display + research-pack + tests added.

## Rollback

- Full: restore `Forex_App_Fixed_S1_S240_RawSplitRanges__7.zip`.
- Surgical: `git checkout` the two edited files (`core/live_execution.py`),
  or delete `core/research_pack/` and `tests/test_upgrade8_master_command_20261009.py`.
