VERDICT: Apr planA s1 — IMPROVED

# Apr — Plan A, Scenario 1 (20 cycles) — 20-Cycle Round R2

**⚠ LEDGER-LEVEL ONLY — winner is VETO-BASED = fall-through-SUSPECT
(ruling in force; Feb C08 precedent: ledger veto gain did NOT survive
app replay). App replay REQUIRED before any integration. Nothing
promoted by this worker; research level only.**

Incumbent (read fresh from registry): Apr best cycle87c + second
cycle87s; checks 22:30/23:30/00:30 MMT, second adds 01:30 — all
off-hours. Rebuilt as Apr_PVOTE_combined.csv (902) merged
second-priority with the R13 ledger MONTH_Apr_PVOTESB_pc_ledger.csv
(124 picks, 44 accepted, drops check_busy 80 / symbol_overlap 0,
DOLLARIDX excluded 0) = 946 picks. Rebuild reproduces the record
EXACTLY: DISC n747 net +6620.36, AUDIT n199 net +1929.49, and MC
DD p95 221.12 vs cap 246.65 (EC step record). All stats canonical
by-trade (validate_new8 seg_stats @2.5). April was already EC PASS
— improvement only, all locked §2 gates applied.

## Numbers block — incumbent vs winner C20

C20 = C01 + PLANB cand2 partner: veto of the single worst DISC
loss-cluster slot **FB_NZDUSD_h17_0** (65 picks dropped) + 2
accepted partner fills from MONTH_Apr_PLANB_cand2_ledger.csv.

| Measure | Incumbent 87c+87s | C20 (winner) |
|---|---|---|
| DISC leftover | 85.26% | **90.56%** |
| AUDIT leftover | 71.26% | **78.92%** (strictly > ✓) |
| AUDIT net | +1929.49 | **+2064.49** (> 0 ✓) |
| DISC net | +6620.36 | +6732.29 |
| Win % (DISC/AUDIT) | 97.72 / 94.47 | 98.43 / 95.60 (> 80 ✓) |
| Entries/day (DISC/AUDIT) | 4.420 / 4.523 | 4.148 / 4.136 (≥ 2 ✓) |
| LCT P / q05 | — | **99.59% / 81.34%** (middle ✓, strict ✓) |
| MC P(profit) | 1.0000 | 1.0000 |
| MC DD obs / p95 vs own cap | 164.43 / 221.12 vs 246.65 | 164.43 / **174.91** vs 246.65 ✓ |
| MC cluster obs / p95 vs cap | −102.50 / 103.30 vs 153.75 | −102.50 / **102.50** vs 153.75 ✓ |
| MC consec obs / p95 | 1 / 2 | 1 / **1** ✓ |
| MC middle (mc9_verbatim) | PASS | PASS (all arms) |
| PBO | 0.00% (EC record) | 0.00% (≤ 50 ✓) |
| DSR | 1.0000 (EC record) | 1.0000 (≥ 0.90 ✓; family = incumbent + C01..C20, 21 trials, DISC daily) |
| Decay | PASS (this-run engine) | PASS (not FAIL ✓) |

Own-relative cap ruling: DD cap = 1.5 × DD obs = 246.65 governs;
it coincides with the EC step cap 246.65 for both forms (DD obs
unchanged at 164.43). Sizing NOT a gate (brief §0/§2).

## Loss-cluster mechanism + before/after arms

Mechanism (explicit, pre-registered): **slot veto of the worst
DISC loss-cluster slots** of the combined ledger (slot identity
measured on DISC only), optionally refilled by partner fills.
Worst slots: FB_NZDUSD_h17_0 (worst), FB_EURAUD_h18_0 (second).

Before → after (C20): DD p95 221.12 → 174.91 (cap 246.65);
cluster p95 103.30 → 102.50 (cap 153.75); consec p95 2 → 1;
DD obs unchanged 164.43 (the vetoed slots were not in the worst
DD window). Pure-veto C02 (both slots): DD p95 → 164.43, cluster
p95 102.50, consec p95 1.
Stateful cluster controls all FAIL: C08 cooldown-1 AUDIT leftover
69.29% < 71.26; C09 symbol-block-48h 70.70% < 71.26; C10
stack-limit-2 AUDIT 73.52% but LCT P 0.00% FAIL.

## All 20 cycles (canonical by-trade @2.5; DISC / AUDIT leftover)

- C01 veto worst slot: 90.51 / 78.47 — **passes ALL gates** (alternate)
- C02 veto worst-2 slots: 94.46 / 76.41 — **passes ALL gates**
  (alternate; highest DISC leftover, LCT 96.82/90.18, DD p95 164.43)
- C03 veto rsi/macd/vol_z: 74.04 / 63.80 — fail
- C04 veto rsi/mom/atr-band: 74.52 / 60.51, AUDIT epd 1.909 — fail
- C05 veto mom>0 + DOLLARIDX-labelled leg + rsi: 80.14 / 47.37 — fail
- C06 veto bb/rsi/vol_z/clv: 77.04 / 83.47 — AUDIT highest of the
  round but LCT P 4.56% FAIL (DSR 0.9095, MC PASS) — rejected
- C07 veto mom + EURUSD leg + DOLLARIDX-labelled leg + vol_z:
  80.90 / 63.09 — fail
- C08 cooldown-1: 84.88 / 69.29 — fail (AUDIT < incumbent)
- C09 symbol-block-48h: 85.21 / 70.70 — fail (AUDIT < incumbent)
- C10 stack-limit-2: 84.11 / 73.52 — LCT P 0.00% FAIL
- C11–C18 partners (PLANB c1/c2, PLANB9 c1/c2, PLANB9C c1/c2,
  PLANB12 c1/c2): accepted **0** each — combined saturated,
  ledgers identical to incumbent
- C19 = C01 + PLANB9C cand1 (25 fills): 90.94 / 73.21 — **passes
  ALL gates** (alternate; most additive form, LCT 100.00/82.40,
  DD p95 178.04)
- C20 = C01 + PLANB cand2 (2 fills): 90.56 / 78.92 — **WINNER**
  (highest AUDIT leftover + AUDIT net among all-gate passers)

Validated alternates' full arms: C01 MC DD p95 174.60, cluster
102.50, consec 1, PBO 0.00/DSR 1.0000, decay PASS; C02 MC DD p95
164.43, cluster 102.50, consec 1, PBO 0.00/DSR 1.0000, decay PASS;
C19 MC DD p95 178.04, cluster 102.50, consec 1, PBO 0.00/DSR
1.0000, decay PASS.

## Caveats

- Every all-gate passer is veto-based → **fall-through-SUSPECT**:
  at app replay the vetoed slots' checks may be refilled by
  lower-priority layers (Feb C08 failed exactly this way; its fix
  needed partner fills). C19/C20 carry partner fills, C01/C02 do
  not. **App replay REQUIRED before integration** — verdict is
  IMPROVED at ledger level only.
- DXY BLOCKED-DATA (Wave 0, Twelve Data 429, 0 rows): C05/C07
  dollar legs are DOLLARIDX-labelled only (Dukascopy H1, no
  volume condition, data from 2017-12-01 — materially shorter
  than the 2015-start FX frame). No DXY claimed anywhere.
- H1 primary throughout; H1-bar clv proxy used in C06 (M15
  confirmation is Plan C's lane, not run here).
- Files: run_apr_planA_s1.py, run_apr_planA_s1_post.py,
  results/apr_planA_s1_run.json, results/apr_planA_s1_canon.json,
  results/apr_planA_s1_extra.json, results/apr_planA_s1_*_ledger.csv.
