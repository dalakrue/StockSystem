VERDICT: Feb planA s2 — NO IMPROVEMENT

# Feb Plan A Scenario 2 — 20 cycles CREATED for one added off-hours slot (2026-10-30)

CREATION, not replay: all 20 equations were designed natively for
the new hour (H1 momentum direction + M15 confirmation, features
from bars strictly before the entry bar, entry at the entry-bar
open, H1 exit SL-first, hold ≤ 48 bars, one pick per check =
strongest |direction momentum| among passing symbols, 28 symbols).
The 2026-10-29 incumbent-replay calc was NOT repeated. Research
level only — no app push, no GitHub push, crons untouched.

## Base of record (stated, per task order)

**A16+X12 combined** (`feb_combined_best_s1.md` — Feb's promotion
candidate of record; its file exists, so it outranks A16-alone and
the incumbent). This runner ASSERTED the base before mining:
incumbent replay DISC 76.90% / AUDIT 37.28% (490 picks), A16
82.62% / 41.21% (480), A16+X12 **83.88% / 42.28%** (631 picks,
DISC net +7004.02, AUDIT net +663.88). Feb convention throughout:
leftover = net_pips / sum(gross wins); segment days DISC 160 /
AUDIT 41. DXY: BLOCKED-DATA (Wave 0, Twelve 429) — the only
dollar legs used (S08/S20) are DOLLARIDX-labelled (Dukascopy H1
mom24, mom only, NO volume condition), exactly as ordered.

## Slot choice — 00:30 MMT (screened, DISC-only)

Feb uses neither 07:30 nor 00:30; both were screened with two
pre-registered probes (P-base mom4, P-mom16; Feb H1 bars at the
hour, DISC years): 07:30 — median H1 volume 5900.8, median range
14.3 pips, probe DISC leftover **−40.14% / −38.15%**; 00:30 —
volume 5640.5, range 12.1 pips, probe DISC leftover −30.76% /
**−17.92%**. 00:30 is the stronger (less negative) slot on DISC
evidence and was chosen; all 20 cycles were created for 00:30
(entry bar 18:00 UTC, stored check 18:30 UTC; Jan-31 18:00 bar
remaps to the Feb-01 00:30 check). Plain fact: BOTH off-hours
slots are hostile to native momentum creation for Feb — every
probe is DISC-negative before any cycle is tuned.

## Winner of the slate — S05 (the only DISC-eligible cycle)

Pre-registered selection: maximise BASE+S2 combined DISC
leftover among cycles with standalone DISC net > 0. **Only S05
qualifies** (mom16 dir + H1 RSI band −15..+25 + H1 BB ≤ 1.2 +
M15 mom align, TP20/SL100): standalone DISC n 167 / net +173.30 /
leftover 6.41% / win 80.84% / epd 1.044; standalone AUDIT n 63 /
net +36.80 / leftover 3.76% / win 77.78% / epd 1.537. Merged
second-priority against the base (same-symbol-open drop):
**223 of 230 slot picks accepted**.

## Numbers block — base A16+X12 vs base + S05 (clean, like-for-like)

Convention note (measured, disclosed): the slot engine's span
includes Feb 2026 (20 S05 picks, all accepted), which the base's
AUDIT segment (2024+2025) never contained. Headline grading below
EXCLUDES those 20 picks (ledger
`feb_s2_combined_ledger_clean2025.csv`); the as-run figures are
in the footnote — the 2026 picks flatter AUDIT, so the clean
grade is the honest one and it is worse.

| Metric | Base A16+X12 | Base + S05 (clean) |
|---|---|---|
| Total picks | 631 | 834 (631 + 203 accepted ≤2025) |
| DISC n / net | 501 / +7004.02 | 661 / +7054.82 |
| DISC leftover | 83.88% | **64.65%** (−19.23) |
| DISC win % / epd | 97.80% / 3.131 | 93.49% / 4.131 |
| AUDIT n / net | 130 / +663.88 | 173 / **+452.08** (−211.80) |
| AUDIT leftover | 42.28% | **20.64%** (−21.64) |
| AUDIT win % / epd | 88.46% / 3.171 | 84.39% / 4.220 |
| LCT P / q05 (DISC, paired vs base) | — | **0.00% / 56.72%** — middle FAIL |
| LCT P / q05 (paired vs incumbent, as-run) | — | 9.34% / 56.72% — FAIL |
| MC P(profit) | 1.0000 | 1.0000 |
| MC DD obs → p95 vs own cap (1.5×obs) | 150.71 → 202.99 vs 226.07 PASS | 356.98 → **461.73 vs 535.47** (flag PASS, obs ×2.37) |
| MC cluster obs → p95 vs cap | −102.50 → 105.50 vs 153.75 PASS | **−307.50 → 307.50** vs 461.25 (flag PASS, obs ×3.0) |
| MC consec obs → p95 | 2 → 2 PASS | 3 → 3 PASS |
| MC middle (verbatim flag) | TRUE | TRUE (own-relative only — see mechanism) |
| PBO / DSR (canonical, stated family of 22) | 80.00% / 1.0000 (in-family ref) | **80.00% / 1.0000** — PBO FAIL (>50%) |
| Decay | WEAKENED (exp<50%; leftover fall>20) | WEAKENED — same class, not FAIL |
| Red lines | — | PASS (AUDIT net +452.08 > 0, no discovery collapse) |

Stated family for PBO/DSR = 22 daily DISC series {INC replay +
BASE + 20 BASE+S2 combined variants}, winner at its own index,
validate_new8 verbatim — no family shopping. (In this family the
base's own ref PBO also reads 80.00%; the family is dominated by
the 20 dilutive slot variants. Disclosed second reading,
R2-engine CSCV: PBO 11.51%, DSR combined 0.9981 — not the gate.)
As-run (2026-inclusive) combined: DISC 64.65% (identical),
AUDIT leftover 27.48%, AUDIT net +700.68, MC DD p95 460.07,
cluster p95 307.50 — same verdict on every arm.

## §2 check-time grade vs the base — DOWNGRADE (not adopted)

- AUDIT leftover 42.28% → 20.64% = **−21.64 pts** (> 0.5-pt line) → DOWNGRADE arm 1 fires.
- AUDIT net +663.88 → +452.08 = **−211.80**, worse than −max(25, 10% × 663.88 = 66.39) → DOWNGRADE arm 3 fires.
- Win: combined 93.49% / 84.39% both > 80% (arm 2 does not fire; the slot standalone AUDIT win 77.78% is itself < 80%).
- DISC leftover also falls (83.88% → 64.65%), so IMPROVE is impossible on its first condition.
- Best-gates re-check on the combined: LCT-middle FAIL (P 0.00 vs base, 9.34 vs incumbent) · PBO FAIL · MC flag passes only own-relative while every absolute arm worsens ×2–3 · win/epd/AUDIT-net/decay/red-lines pass. The combined does NOT clear §2.

**No slot is adopted for Feb. A16+X12 stands unchanged as Feb's
candidate of record.**

## Loss-cluster mechanism — explicit, before vs after

The slot's mechanism was supposed to ADD diversification at an
empty hour; the two dedicated cluster-control cycles were S16
(post-loss same-symbol cooldown: standalone DISC leftover
−30.30%, AUDIT +13.55%) and S17 (post-loss global skip-1:
DISC −35.14%, AUDIT +23.17%) — both DISC-losing standalone, both
combined forms still DOWNGRADE (combined AUDIT leftover 32.42% /
34.84% vs base 42.28%). For the selected S05 the cluster effect
is the opposite of control: base worst cluster −102.50 → combined
**−307.50** (three atomic −102.50 full-stop losses now stack —
the 00:30 slot's losses land inside the base's holding windows),
cluster p95 105.50 → 307.50, DD obs 150.71 → 356.98, max consec
2 → 3. MC arms before/after are in the numbers block; the
verbatim flag stays TRUE only because the own-relative caps
(1.5× obs) inflate with the damage — under the governing ruling
that is a PASS on paper and a ×3 cluster worsening in fact, and
it is reported as both.

## All 20 created cycles at 00:30 (standalone DISC/AUDIT leftover · combined-with-base DISC/AUDIT leftover)

Every combined form grades DOWNGRADE vs the base (AUDIT leftover
down > 0.5 pt in all 20; best combined is S13, ineligible under
the pre-registered standalone-net rule at DISC net −88.90, and
even it reads DISC 71.19% / AUDIT 36.67% — both below base):

- S01 mom4+M15mom+M15vol: −30.76 / −7.29 · comb 57.70 / 25.25
- S02 mom16+M15mom+H1vol: −17.92 / +18.12 · comb 60.21 / 32.35
- S03 mom4+RSI+M15mom: −19.51 / +4.19 · comb 59.68 / 27.61
- S04 mom4+BB+M15vol band: −22.70 / +5.63 · comb 59.24 / 27.70
- **S05 mom16+RSI+BB+M15mom: +6.41 / +3.76 · comb 64.65 / 27.48 (as-run) — SELECTED, DOWNGRADE**
- S06 mom4+MACD+EMA+M15mom: −9.63 / −78.52 · comb 63.23 / 4.55
- S07 mom24+ATR+M15vol TP30: −6.64 / +19.13 · comb 57.26 / 31.84
- S08 mom4+DOLLARIDX leg+M15mom: −31.07 / +10.64 · comb 57.47 / 30.49
- S09 mom4+EURUSD corr+H1vol: −12.64 / −7.43 · comb 61.48 / 23.36
- S10 mom16+M15 RSI/BB/vol: −39.03 / −16.65 · comb 56.70 / 19.85
- S11 strict all-confirm: −17.41 / −30.55 · comb 60.73 / 16.82
- S12 mom4+M15mom TP10/SL60: −35.04 / −19.90 · comb 66.58 / 29.58
- S13 mom16+M15mom+H1vol TP10/SL60: −6.13 / +5.30 · comb 71.19 / 36.67 (best combined, ineligible)
- S14 mom4+RSI+M15mom TP30: −12.23 / +5.74 · comb 56.37 / 26.50
- S15 mom24+EMA+M15 RSI TP20/SL60: −10.35 / −36.38 · comb 63.23 / 14.87
- S16 cluster ctrl symbol-cooldown: −30.30 / +13.55 · comb 61.51 / 32.42
- S17 cluster ctrl global skip-1: −35.14 / +23.17 · comb 60.59 / 34.84
- S18 mom4+H1 vol∈[0,3]+M15mom: −9.13 / +19.76 · comb 63.10 / 33.64
- S19 mom16+BB≤0.8+M15vol band: −53.36 / −21.24 · comb 52.67 / 18.81
- S20 mom4&16 agree+DOLLARIDX loose: −24.10 / +11.89 · comb 60.33 / 31.12

Pattern, stated plainly: at 00:30 (and worse at 07:30) Feb
momentum continuation wins only ~74–81% of trades against a
TP20/SL100 (or TP10/SL60) asymmetry that needs > 85% — the hour
mean-reverts against the H1 momentum direction on DISC, while
AUDIT (2024–25) is mildly positive for several forms (S02 +18.12,
S17 +23.17 standalone). That DISC/AUDIT sign flip is exactly the
regime pattern this programme does not promote on. The untested
route for a Feb off-hours slot is a native MEAN-REVERSION
direction at 00:30 — outside this slate's pre-registered
momentum forms; named, not run.

## Method / files

- Runners: `run_feb_planA_s2.py` (pre-registered slate in its
  header; process killed by a service restart after S12) +
  `run_feb_planA_s2_resume.py` (identical except cached ledgers
  S01–S12/study are reloaded; S13–S20 + all grading computed
  fresh). Machinery reused: `work_new8/validate_new8.py` (LCT,
  PBO/DSR, daily_pnl), `work_29load/mc9_verbatim.py`,
  `support/planA_s1_engine.py` (CSCV second reading).
- Machine record: `results/feb_s2_run.json` (+
  `feb_s2_clean_grade.json`); ledgers: `feb_s2_S01..S20_slot_
  ledger.csv`, `feb_s2_study_*_ledger.csv`,
  `feb_s2_combined_ledger.csv` (as-run) and
  `feb_s2_combined_ledger_clean2025.csv` (headline grade).
- Sizing: NOT a gate in this round (brief §0) — not measured.
