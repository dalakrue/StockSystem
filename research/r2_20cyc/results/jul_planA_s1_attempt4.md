VERDICT: Jul planA s1 attempt4 — IMPROVED (stop-density attempt: the T7 DISC full-stop census finds exactly ONE leg carrying ≥2 full-stops — the B04 fill leg q_wt1_lt75_GBPNZD_h15_0.9x7.0_H48_2 with 2 — plus one further DISC full-stop leg with 1; of the 7 pre-registered variants, D1–D6 on the T7 form ALL pass the full §2 battery with the MC verbatim flag TRUE — winner D3 = two-carrier prune at source + B04 fill recomputed: DISC leftover 84.96→89.11%, AUDIT 64.97→77.01%, DD p95 172.54 ≤ own cap 188.51, LCT 100.00/80.05, PBO 20.00% / DSR 1.0000 canonical family-10, decay not FAIL — the density route SUCCEEDS on the T7 form; the W7 no-fill variant D7 still fails: DD p95 146.48 vs own cap 144.05, miss 2.43, AND DISC epd 1.989 < 2)

# Jul Plan A S1 — ATTEMPT 4: prune the full-stop carrier legs (2026-10-30, Wave 4b)

Target (single, pre-registered): attempt 3's named remaining
route. Attempt 3 showed Jul's MC DD arm is bound by the DENSITY
of atomic −102.50 full-stop losses (gross −100.00, net = gross
− 2.5), not by any window: pruning the 2017 window pair moved
DD obs 125.67 → 102.50 in all 8 W-variants, but the own-relative
cap fell with it (153.75) and every variant still missed
(closest clean W7, miss 5.00; T7 reference miss 1.49 at DD p95
190.00 vs cap 188.51). This attempt prunes the legs that CARRY
the full-stops. Slate of 7 written into `run_jul_attempt4.py`
BEFORE any variant was measured. Grading = full BRIEF.md §2
battery vs cycle78 (Jul convention: DISC 174 d / AUDIT 46 d;
leftover = net ÷ sum of positive NET). MC = mc9_verbatim,
10,000 paths; mc_middle_pass is the OWN-RELATIVE flag (settled
ruling, applied without re-argument). Research level only.

## (a) Carrier census — T7 ledger, DISC-only selection

T7 rebuilt via the attempt-2/3 code path (C18 prune
{FB_EURUSD_h15_0_G, FB_USDJPY_h15_2_G} + B04 fill recomputed,
157 accepted) and asserted to its published figures (DISC
84.96 / AUDIT 76.98) before the census. DISC full-stop
(net −102.50) trades in T7: **exactly 3, on exactly 2 legs**:

| Leg | DISC full-stops | Checks | DISC picks | DISC net | Origin |
|---|---|---|---|---|---|
| **q_wt1_lt75_GBPNZD_h15_0.9x7.0_H48_2** (CARRIER_1) | **2** | 2016-07-25 15:30, 2019-07-03 15:30 | 5 | −104.24 | B04 **fill** leg (0 picks in base/incumbent) |
| mom_USDCAD_h15_momB_T1.5_A1.0_1.25x8 (CARRIER_2) | 1 | 2020-07-20 15:30 | 12 | +72.62 | base leg |

- **Exactly ONE leg carries ≥2 DISC full-stops: CARRIER_1.**
  CARRIER_2 is below the ≥2 line but is the only other DISC
  full-stop leg in T7, so it is the only possible second leg
  of a two-carrier prune — included on that stated basis.
- The one remaining full-period full-stop in T7 is AUDIT-only
  (2024-07-24, NP2_np_m30_mom_gt35_xdx_mom_lt65_S_GBPNZD_h15
  leg, 1 stop). It was NOT selected — selection is DISC-only.
  It remains in every variant below (D3/D6 finish with 0 DISC
  full-stops but 1 full-period).
- Note what this means for the density diagnosis: T7's DISC
  sequence carries only 3 atomic stops in 514 trades. The
  bootstrap binds not because stops are numerous in absolute
  terms, but because block-10 resampling can stack the few
  that exist next to the −92.50/−81-class losses. Removing
  even 1–2 of them measurably thins the resampled DD tail —
  which is what happened.

## (b) Pre-registered slate — 7 variants

T7 form HAS a fill → carriers pruned at source, fill
RECOMPUTED (D1–D3; fill accepted D1 152 / D2 170 / D3 165 vs
T7's 157). Ledger prunes of the saved T7 ledger (no refill)
isolate the refill effect (D4–D6), attempt 3's W1–W3 pattern.
W7 form (attempt-3 W7 = T7 base + prune FB_EURJPY_h17_1_G, NO
fill) carries CARRIER_1 zero times — it is a fill-only leg, so
a W7 prune of CARRIER_1 is vacuous and is NOT counted; W7's
only DISC full-stop leg is CARRIER_2 (D7).

  D1 T7-form prune CARRIER_1 (fill source excludes it, recomputed)
  D2 T7-form prune CARRIER_2 (base prune, fill recomputed)
  D3 T7-form prune CARRIER_1 + CARRIER_2 (both at source, recomputed)
  D4 T7 ledger prune CARRIER_1 (no refill)
  D5 T7 ledger prune CARRIER_2 (no refill)
  D6 T7 ledger prune CARRIER_1 + CARRIER_2 (no refill)
  D7 W7-form prune CARRIER_2 (no fill, by construction)

## (c) Full §2 battery — all 7 variants vs cycle78

Reference points: incumbent DISC 66.10 / AUDIT 64.97, DD p95
233.91, flag FALSE · T7 DISC 84.96 / AUDIT 76.98, DD obs
125.67 → p95 190.00 vs own cap 188.51 (miss 1.49), flag FALSE
· W7 DISC 84.57 / AUDIT 82.75, DD 102.50 → 158.75 vs 153.75
(miss 5.00), flag FALSE. Canonical PBO/DSR family (stated,
attempt-4): 10 daily DISC series {INC, T7, W7, D1..D7}; every
D-variant PBO **20.00%** canonical / DSR **1.0000** (the
family-level 20.00 replaces the 0.00 of the earlier, different
families — family stated, no shopping). Disclosed second
reading (R2-engine CSCV basis, same split as all prior Jul
files): family PBO 77.78%, DSR 1.0000 for every variant.
Decay: yearly leftover positive every year 2016–2025 for
every variant; AUDIT/DISC leftover ratios 0.86–0.96 — none
FAIL. Canonical LCT (validate_new8) also passes middle for
every variant (P 92.27–100.00, q05 72.25–79.64).

| Var | DISC lo | AUDIT lo | AUDIT net | win D/A % | epd D/A | LCT Jul P/q05 | DD obs → p95 vs own cap | MC flag | DISC/full full-stops left |
|---|---|---|---|---|---|---|---|---|---|
| D1 | 87.64 | 76.98 | +1138.57 | 97.05/95.45 | 2.925/2.870 | 100.00/77.83 | 125.67 → 178.96 vs 188.51 | **TRUE** | 1 / 2 |
| D2 | 86.42 | 77.01 | +1140.61 | 96.89/95.45 | 2.954/2.870 | 99.88/76.14 | 125.67 → 185.02 vs 188.51 | **TRUE** | 2 / 3 |
| **D3** | **89.11** | **77.01** | **+1140.61** | 97.25/95.45 | 2.925/2.870 | **100.00/80.05** | 125.67 → **172.54** vs 188.51 | **TRUE** | **0 / 1** |
| D4 | 87.64 | 76.98 | +1138.57 | 97.05/95.45 | 2.925/2.870 | 100.00/77.83 | 125.67 → 178.96 vs 188.51 | **TRUE** | 1 / 2 |
| D5 | 86.05 | 76.78 | +1126.15 | 96.81/95.42 | 2.885/2.848 | 99.85/75.42 | 125.67 → 186.56 vs 188.51 | **TRUE** | 2 / 3 |
| D6 | 88.81 | 76.78 | +1126.15 | 97.18/95.42 | 2.856/2.848 | 100.00/79.37 | 125.67 → 173.27 vs 188.51 | **TRUE** | **0 / 1** |
| D7 | 86.27 | 82.56 | +945.45 | 96.53/96.91 | **1.989**/2.109 | 99.99/75.14 | 96.03 → 146.48 vs 144.05 | FALSE (miss 2.43) | 0 / 0 |

All other MC arms for D1–D6: P(profit) 1.0000, cluster obs
−125.67 → p95 125.67 ≤ cap 188.51 PASS, consec obs 2 → p95 2
PASS. D7's other arms also pass (cluster −92.50 → 92.50,
consec 1 → 1, P(profit) 1.0000) — its DD arm is the sole MC
blocker, as throughout Jul.

§2 gate check: **D1–D6 pass EVERY gate** — LCT-middle ✓ ·
AUDIT leftover strictly > incumbent 64.97 ✓ · win > 80% ✓ ·
epd ≥ 2 ✓ · AUDIT net > 0 ✓ · MC verbatim flag TRUE ✓ ·
PBO ≤ 50% canonical ✓ · DSR ≥ 0.90 ✓ · decay not FAIL ✓ ·
red lines ✓. **D7 fails two gates**: MC flag FALSE (DD arm,
miss 2.43) and DISC epd 1.989 < 2 (miss 0.011).

## Winner — D3, and why

**D3 = T7 form with both carrier legs pruned at source and
the B04 fill recomputed** (base prunes CARRIER_2; fill source
excludes CARRIER_1; 165 fill picks accepted): DISC leftover
**89.11%** (highest of the round, +4.15 over T7, +23.01 over
the incumbent), AUDIT leftover **77.01%**, AUDIT net +1140.61
(highest with D2), DD p95 **172.54** (lowest of the filled
forms, 15.97 under its cap), LCT Jul 100.00/80.05 and
canonical 100.00/79.64 (strongest of the slate), 0 DISC
full-stops remaining. D6 (the same two-carrier prune without
refill) is the runner-up: DD p95 173.27, DISC 88.81, AUDIT
76.78 — the refill in D3 is worth +0.30 DISC / +0.23 AUDIT
leftover and +14.46 AUDIT net, and costs nothing on the DD
arm. D1 and D4 are pick-identical (the fill recompute without
CARRIER_1 accepted exactly T7's fill minus CARRIER_1's 5
picks — no replacement landed at the freed checks).

Mechanism, stated plainly: D1–D6 do NOT move DD obs — it
stays 125.67, because the 2017 window pair (attempt 3's legs)
is untouched in the T7 forms. What the carrier prune moves is
the RESAMPLED tail: with 1–2 of the 3 DISC atomic stops gone,
block-bootstrap excursions stack fewer full-stops beside the
−92.50/−81-class losses, so p95 falls from T7's 190.00 to
172.54–186.56 while the cap (1.5 × 125.67 = 188.51) stands
still. That is the density effect attempt 3 predicted, now
measured in the direction that passes.

## Is the density route now exhausted within prune forms?

- **On the T7 (filled) form: the route is not exhausted — it
  SUCCEEDED.** Six of six T7-form variants pass every §2
  gate; there is nothing left to chase on this form. One
  full-stop remains in D3/D6, and it is AUDIT-only
  (2024-07-24, the NP2 GBPNZD fill leg): removing it was
  outside this attempt's DISC-only selection rule, and no
  gate needs it — D3 passes with it in place.
- **On the W7 (no-fill) form: YES, exhausted.** D7 removes
  W7's last DISC full-stop carrier — W7-form full-stops go
  to 0 anywhere in the period — and the flag STILL fails,
  because DD obs falls to 96.03 and the own-relative cap
  falls in proportion (144.05) while p95 only reaches
  146.48; D7 also breaks DISC epd (1.989 < 2). No carrier
  legs remain to prune in that form, so no further prune
  variant on the W7 form can be constructed under this
  route. (This is attempt 3's cap-trap, confirmed at the
  limit: at zero full-stop density the binding losses are
  the −92.50 class and the cap scales down with them.)

## Consequence for Jul

**Jul has a §2-passing best candidate for the first time in
this round: D3** (attempt-4 form of T7: C18 prune
{FB_EURUSD_h15_0_G, FB_USDJPY_h15_2_G} + prune
mom_USDCAD_h15 base leg + B04 fill recomputed with the
q_wt1 GBPNZD leg excluded from the fill source). It fixes
Jul's EC-failing MC DD arm under the settled own-relative
ruling (172.54 ≤ 188.51) while raising both leftovers over
T7 and the incumbent. D1, D2, D4, D5, D6 also pass all gates
and are recorded as passing alternates (D6 strongest of
those). Incumbent cycle78 is superseded at research level by
this grading; integration is a separate step (the Jul
machinery is ledger-level — the D3 form is a prune + fill
composition of existing ledgers, no app-replay exists for
Jul in this programme, stated as in every prior Jul file).

## Method / files

- Runner: `run_jul_attempt4.py` (census + slate pre-registered
  in its header; T7 and W7 rebuilt via the attempt-2/3 code
  path and asserted 84.96/76.98 and 84.57/82.75 before use).
  Machinery reused: `work_29load/mc9_verbatim.py`,
  `work_new8/validate_new8.py`, `support/planA_s1_engine.py`
  (CSCV second reading only).
- Machine record: `results/jul_attempt4_run.json`; ledgers
  `results/jul_attempt4_D1..D7_ledger.csv`.
- Sizing: NOT a gate in this round (brief §0) — not measured.
