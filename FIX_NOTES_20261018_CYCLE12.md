# Fix notes — Cycle 12 (2026-10-18): BEST S4 module + delete 07 UTC check + check-time banner

Base: copy of `Forex_App_Main_System__10.zip`
(SHA-256 `db53ddcadd34165b8f7b21c0401707fb847b9da1fd35fc0d757f22972616c46f`).
The original zip was NOT modified. This zip is `Forex_App_Fixed_S1_S240_Cycle12__12.zip`.

## 1. What changed (and only this)

| File | Change | SHA-256 before → after (first 12) |
|---|---|---|
| `core/cycle12_best.py` | NEW. BEST equations verbatim (see §2). | new → `7ca7b531c5d2` |
| `core/improved_strategy_config.py` | `GOOD_HOURS` (6,7,10,11,12,13) → (6,10,11,12,13). | `3693b8c1b53a` → `a05d52b2b520` |
| `core/execution_policy_20261003.py` | Default `check_hours` → (6,10,11,12,13); validation 6 → 5 checks. | `4ac3db531a68` → `13d2d6f5ab14` |
| `config/audited_execution.json` | `check_hours` [6,7,10,11,12,13] → [6,10,11,12,13] (same one-line format). | `9304a1b104bb` → `75ad192ee071` |
| `core/exit_engine_20261010.py` | `CHECK_HOURS` → (6,10,11,12,13) + docstring line. | `866864c1cd40` → `f81b92378b80` |
| `core/monthly_backtest.py` | Docstring only: scheduled checks list. | `f6cba47815eb` → `83a606fd538a` |
| `core/monthly_runtime.py` | Comment only: check-hour list. | `8358e27bcd32` → `3ebed887b9f8` |
| `ui/field3_multisymbol_regime_summary_20260722.py` | BIG check banner + Myanmar/MetaTrader/Entry-Check columns (see §3). | `52af6011064f` → `94f9c645fbc1` |
| `tests/test_upgrade8_master_command_20261009.py` | Policy check-hours assertion → 5-hour schedule. | `561d86e9de86` → `a85e0b193c5b` |
| `tests/test_monthly_equations_integration.py` | 3 hour-set assertions → 5-hour schedule. | `d1a980aba3ce` → `3628722ab53a` |
| `tests/test_cycle12_best_20261018.py` | NEW. 9 tests (equations, clocks, selection, reproduction). | new → `d128f427b2bf` |

S1–S240 mapping, equations, ranking, stats: byte-identical (verified by
`diff -rq` between the base tree and this tree — only the files above
differ, plus these two new files). `PACKAGE_MANIFEST.json` entries for the
changed/added files were refreshed.

## 2. BEST equations (verbatim from `~/workspace/fx/work_c12/best_system.json`)

All SELL at 18:30 UTC (= 01:00 AM Myanmar next day). Signal features from
the last completed H1 candle (17:00 UTC); entry = open of the 18:00 candle.
TP/SL = ATR14 multiples clipped TP [10,500] / SL [5,100]. SL-first, 48h cap.

- BEST1 AUDNZD: mom24 > 1.0 AND ATR-ratio < 1.0, TP 1.25×, SL 2.5×
- BEST2 AUDCHF: mom24 > 1.0 AND ATR-ratio < 1.0, TP 1.75×, SL 1.5×
- BEST3 AUDCAD: mom24 > 2.0 AND ATR-ratio < 1.0, TP 1.5×, SL 1.0×
- BEST4 NZDCAD: mom24 > 1.25 AND ATR-ratio < 0.9, TP 1.5×, SL 1.0×

Default selection: top-2 per check by score, max 1 open trade per symbol
(headline BEST: unseen +1,164.21 pips / 163 trades / RoMAD 40.39).
Uncapped (every qualifying entry, `k=None`) PASSED the full 10-check
(unseen +1,296.72 / 186 trades / RoMAD 33.97) but LOWERS RoMAD, so it is
an opt-in mode, never the default.

## 3. Banner + columns (above Middle Standard Regime Ranking)

- BIG banner: ✅ YES — ENTRY CHECK TIME / ⏸ NO — NOT A CHECK TIME, which
  module owns the check, Myanmar + MetaTrader + UTC clocks, UPDATED/STALE
  data flag (latest completed candle within 90 min?), next check time.
- Middle table gains Myanmar Time, MetaTrader Time, Entry Check Time
  (Yes/No) columns. One check-time condition for the new module:
  `core.cycle12_best.is_entry_check_time` (old 06/10/11/12/13 :30 UTC +
  Cycle-12 18:30 UTC, weekdays). MetaTrader = UTC+3 summer / UTC+2 winter
  (approx Oct 25 → Mar 29; verify vs broker Market Watch).

## 4. Verification (all numbers from mining / re-runs, none invented)

- Feature parity: module mom24/ATR-ratio/ATR14 match c12_engine (b11_core
  definitions) exactly (max diff 0.0) on AUDNZD full history.
- Backtest reproduction: capped unseen 163 trades, net +1,164.21 (exact);
  uncapped unseen 186 trades, +1,296.72 (exact). Trade-by-trade diff of
  all 163 capped unseen trades: 0 differences in net/gross/reason/hold/
  entry/exit. Mining DD/RoMAD use as-stored (symbol-grouped) log order;
  exit-order recomputation gives DD −26.05 / RoMAD 44.69 — the module uses
  exit-order. Net/trades/EV/PF/Sharpe are order-invariant.
- Delete-2pm A/B (app `replay_portfolio`, same code except hour set,
  entries 2022-10-05 → 2026-10-05): before (6 checks) net +5,492.87,
  5,711 trades, RoMAD 3.62, DD −1,516.61; after (5 checks) net +6,284.95,
  5,286 trades, RoMAD 4.72, DD −1,332.88. Change: net +792.08 (+14.42%),
  trades −425, RoMAD +1.09, DD 183.73 shallower. The 07 UTC check's own
  trades netted −681.96 (558 trades); +110.12 of the gain is re-selection
  at other checks. S4 unaffected (18:30 UTC only).
- Tests: 9 new Cycle-12 tests pass. Existing monthly-integration +
  upgrade8 suites: failure set identical to the base tree (4 failed +
  8 errors, all pre-existing environment gaps: this VM lacks the
  Asia/Rangoon tz alias and Jinja2). Zero new failures.
- Smoke: live Streamlit launch not possible in this VM (Streamlit not
  installed; Jinja2 missing — original tree fails identically). Banner +
  time-column functions exercised directly with a fake Streamlit object
  (recent/old/Cycle-12/07-deleted/NaT/empty cases) — all pass.

## 5. Caveats

- BEST was chosen by ranking on UNSEEN RoMAD → UNSEEN is not fully
  untouched; 10-check PASS is optimistic to some degree. Paper-trade
  before any live use. Regime bucketing uses the battery full-sample
  median (mild lookahead in bucketing only).
- Pre-existing finding (not changed here): the __10 zip's bundled
  verification trade log uses a different schedule (checks at
  01/05/09/11/13/15 UTC) and exit settings (24h cap, fixed TP/SL,
  2.5-pip costs) than the current code, so it was NOT used as the
  delete-2pm baseline — both arms were re-run from the same current code.
