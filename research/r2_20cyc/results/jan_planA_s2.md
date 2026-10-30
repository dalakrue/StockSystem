VERDICT: Jan planA s2 — NO IMPROVEMENT

# Jan Plan A Scenario 2 — 20 cycles CREATED for one added off-hours slot
# (R2, brief §2/§3/§5/§9). Run 2026-10-30. This is CREATION of native
# equations for the new hour — NOT a replay of incumbent equations at
# the new hour (the 2026-10-29 replay, 0 improve / 4 downgrade, is not
# repeated). Machinery: validate_new8 verbatim (seg_stats, split_seg,
# lct, round_pbo_dsr, daily_pnl) + mc9_verbatim.mc_test (block 10,
# 10,000 paths, seed 20261101, net = gross − 2.5) + planA_s1_engine
# (pbo_cscv, full_decay). Leftover = by-trade convention, identical to
# Plan A/C S1 (DISC days 176, AUDIT days 46). Scripts: ../run_jan_s2.py
# (died silently after S19 — no traceback; S01–S19 slot ledgers were
# already on disk) + ../run_jan_s2_finish.py (S20 + merge + grading).
# Raw: jan_s2_run.json, jan_s2_S01..S20_slot_ledger.csv,
# jan_s2_form_{i,ii,iii}_*_ledger.csv, jan_s2_study_*_ledger.csv.
# DXY: BLOCKED-DATA (Wave 0, Twelve 429) — no DXY claimed. The dollar
# legs in S08/S20 are DOLLARIDX-labelled (Dukascopy H1, mom only, NO
# volume condition, data from 2017-12-01). H1 primary: entries AT the
# new check bar open; M15 = confirmation features only. 28 symbols.
# Slot stored-check convention (Dec/Sep S2 runs): 07:30 MMT → entry
# bar 01:00 UTC; 00:30 MMT → entry bar 18:00 UTC. Per check, ONE pick:
# the strongest |direction momentum| among passing symbols (the
# programme's per-check scale). Merge = second-priority: a slot pick
# is dropped only if the base form holds the same symbol open at
# slot entry.

## Slot choice — BOTH free slots screened, choice on DISC evidence only
January uses neither 07:30 nor 00:30 MMT (incumbent checks 17:30 /
19:30 / 23:30 MMT), so both were screened with two pre-registered
probe equations (P-base: mom4 dir + M15 mom4 align + M15 vol_z > −1,
TP20/SL100 · P-mom16: mom16 dir + M15 mom4 align + H1 vol_z > −0.5,
TP20/SL100), one pick per check, 28 symbols:
| slot | median H1 vol at slot bars | median H1 range | P-base DISC leftover | P-mom16 DISC leftover |
|---|---|---|---|---|
| 07:30 MMT (01:00 UTC) | 5,626.0 | 14.25 pips | 15.38% (n 170, net +457.6, win 82.35%) | 0.90% (n 167, net +26.3) |
| 00:30 MMT (18:00 UTC) | 5,642.3 | 12.35 pips | 7.32% (n 176, net +222.4) | 22.77% (n 173, net +685.5, win 84.97%) |
CHOSEN: **00:30 MMT** — best probe DISC leftover 22.77% vs 15.38%
at 07:30; the 18:00 UTC bar is the US-session close / rollover hour,
where January's 16-hour momentum actually carries (07:30 MMT =
01:00 UTC is the thin Asian-open hour: its mom16 probe is flat).

## The 20 creations at 00:30 MMT (pre-registered before results)
S01 mom4+M15mom+M15vol · S02 mom16+M15mom+H1vol · S03 mom4+H1 RSI
band+M15mom · S04 mom4+H1 BB+M15 vol band · S05 mom16+RSI+BB+M15mom ·
S06 mom4+MACD+EMA+M15mom · S07 mom24+ATR band+M15vol, TP30 · S08
mom4+DOLLARIDX leg (labelled)+M15mom · S09 mom4+EURUSD corr leg+
M15mom+H1vol · S10 mom16+M15 RSI/BB/vol bands · S11 mom4+strict
all-confirm · S12 mom4+M15mom, TP10/SL60 · S13 mom16+M15mom+H1vol,
TP10/SL60 · S14 mom4+H1 RSI band+M15mom, TP30/SL100 · S15 mom24+EMA+
M15 RSI band, SL60 · S16 mom4+M15mom+POST-LOSS SYMBOL COOLDOWN
(cluster control) · S17 mom16+M15mom+POST-LOSS GLOBAL SKIP-1
(cluster control) · S18 mom4+H1 vol_z∈[0,3]+M15mom · S19 mom16+H1
BB≤0.8+M15 vol band · S20 mom4&mom16 agree+M15mom+DOLLARIDX leg
loose (labelled). Every rule = 3–4 indicators × thresholds, volume
columns included, per brief §3.

Standalone slot results (DISC leftover/net · AUDIT leftover/net)
and INC-combined leftovers — the decisive pattern is in the last
two columns: **no creation's combined AUDIT leftover comes within
12 pts of the incumbent's 70.06%**:
| cycle | slot DISC left/net | slot AUDIT left/net | comb DISC left | comb AUDIT left/net |
|---|---|---|---|---|
| S01 | 7.32 / +222.4 | −0.72 / −8.4 | 20.36 | 34.50 / +741.48 |
| S02 | 22.77 / +685.5 | −0.71 / −8.0 | 27.30 | 35.00 / +741.88 |
| S03 | 16.01 / +486.5 | −10.04 / −117.7 | 24.12 | 29.63 / +632.18 |
| S04 | −6.97 / −212.6 | 9.75 / +111.6 | 14.60 | 40.39 / +861.48 |
| S05 | 10.24 / +313.7 | 2.64 / +30.7 | 23.24 | 36.30 / +780.58 |
| S06 | 21.62 / +622.9 | −1.47 / −17.0 | 26.38 | 39.40 / +835.38 |
| S07 | −16.33 / −772.6 | 14.32 / +254.9 | 6.14 | 37.56 / +977.28 |
| S08 | 7.72 / +234.5 | −24.96 / −292.7 | 20.90 | 21.50 / +457.18 |
| S09 | −2.40 / −72.6 | −0.72 / −8.4 | 16.36 | 34.50 / +741.48 |
| S10 | −18.90 / −580.2 | 29.87 / +350.2 | 9.86 | 50.82 / +1100.08 |
| S11 | 6.34 / +192.3 | −17.54 / −205.7 | 20.22 | 25.50 / +544.18 |
| S12 | 22.32 / +294.6 | 6.73 / +33.8 | 27.69 | 49.76 / +783.68 |
| S13 | 8.24 / +108.1 | −11.07 / −54.7 | 24.84 | 44.37 / +695.18 |
| S14 | 25.66 / +1214.1 | −12.66 / −233.2 | 28.05 | 23.68 / +614.18 |
| S15 | −14.61 / −444.2 | −16.87 / −197.8 | 11.68 | 25.87 / +552.08 |
| S16 (cooldown) | 9.53 / +257.8 | 24.60 / +254.0 | 21.96 | 49.17 / +1003.88 |
| S17 (skip-1) | 21.02 / +559.3 | 6.73 / +63.3 | 26.83 | 41.88 / +813.18 |
| S18 | 6.11 / +177.1 | 13.15 / +147.3 | 21.99 | 42.06 / +879.68 |
| S19 | −28.38 / −866.6 | 44.58 / +513.4 | 6.68 | 57.72 / +1263.28 |
| S20 | 14.49 / +440.2 | −36.56 / −428.7 | 23.72 | 19.87 / +418.68 |
Selection (pre-registered, DISC-only): among cycles with standalone
DISC net > 0, the one maximising INC-combined DISC leftover =
**S14** (28.05%). Note S19 posts the best combined AUDIT leftover
(57.72%) but its standalone DISC net is −866.6 — DISC-collapsed,
red-line ineligible, and 57.72% still fails the unseen gate.

## Created cycle S14 standalone (the selected creation)
Rule: direction = H1 mom4 sign; keep only if direction-signed H1
RSI sits in its band AND M15 mom4 (1h) aligns; TP30 / SL100, hold
≤ 48 H1 bars, SL-first. DISC: n 176, net +1214.10, win 80.11%,
leftover 25.66%, epd 1.000. AUDIT: n 67, net −233.20, win 65.67%,
leftover −12.66%, epd 1.457. **The created slot flow is itself
AUDIT-losing** — January at 00:30 MMT does not repeat its DISC
behaviour in 2024–25, the same regime flip that killed Plan A D08,
now measured at the new hour with native equations.

## FORM I — incumbent 60b+60 + S14 (the target form)
Frequency headroom IS restored — that half of the target lands:
entries/day 2.972/2.935 → **3.955 DISC / 4.370 AUDIT**. Everything
else fails:
- DISC: n 696, net +2441.73, win 89.22%, leftover 29.82% → **28.05%**
  (DOWN — even the DISC leftover falls, because the slot's TP30/SL100
  picks carry full-stop losses the incumbent's mix does not).
- AUDIT: n 201, net +749.88 → +614.18, win 95.56% → 86.07% (>80 ✓),
  leftover 70.06% → **23.68%** (Δ −46.38) ✗✗.
- LCT (paired, DISC): P 49.05% / q05 13.97% — middle FAIL.
- MC arms BEFORE → AFTER: P(profit) 0.9999 → 0.9991 · DD obs
  459.29 → 523.27, DD p95 527.91 (cap 688.94) → **888.28 vs OWN cap
  784.91 (= 1.5 × 523.27) FAIL** · cluster obs −201.82 → **−304.32**,
  cluster p95 205.00 → 304.32 vs cap 456.48 PASS · consec obs/p95
  3/3 → 4/4 (cap 6) PASS. mc9 flag FALSE on the DD arm.
- PBO 25.00% canonical (family N = 21: incumbent + 20 combined) ✓ ·
  CSCV second reading on the 20-cycle combined family = **66.67%
  FAIL** (disclosed, same basis split as Plan C). DSR **0.9151**
  ≥ 0.90 ✓ (family N = 21, daily Sharpe 0.2297) — the DSR gate
  passes, but it is the only EC item that does.
- Decay PASS.
- Loss-cluster mechanism + before/after: the explicit controls were
  S16 (post-loss same-symbol cooldown) and S17 (post-loss global
  skip-1) INSIDE the slot flow; S16-combined is the best
  AUDIT-preserving variant (AUDIT leftover 49.17%, net +1003.88,
  DISC leftover 21.96%) and still fails the unseen gate by 21 pts.
  For S14 the slot IMPORTS a new loss cluster: combined worst
  cluster obs −201.82 → −304.32 and consec 3 → 4 — the 00:30 flow's
  own full-stop pairs land adjacent to incumbent losses.

## FORM II — PC06 form + S14 (the second variant, as ordered)
PC06 (DISC leftover 39.02%, AUDIT 70.94%, epd 2.369/2.109 — no
frequency headroom) + S14 slot flow:
- DISC: n 591, net +2527.26, win 89.34%, leftover 32.22%, epd 3.358.
- AUDIT: n 163, net +406.15, win 83.44%, leftover 70.94% → **17.52%**
  ✗✗, epd 3.543. Frequency restored (3.358/3.543), leftover destroyed.
- LCT vs incumbent: P 56.95% / q05 17.07% — middle FAIL.
- MC: P(profit) 0.9997 · DD obs 538.27, DD p95 **848.39 vs OWN cap
  807.41 FAIL** (PC06's own-cap miss, 402.13 vs 342.98, is NOT
  repaired — it grows) · cluster obs −304.32, p95 304.32 vs cap
  456.48 PASS · consec 4/4 PASS. Flag FALSE.
- PBO 10.00% / DSR 0.9889 (family-5: INC, PC06, V04, form II,
  form III) · decay PASS.

## FORM III — V04 form + S14 (attempt-2's closest, for completeness)
- DISC: n 527, net +2501.56, leftover 33.85%, epd 2.994 · AUDIT:
  n 147, net +316.34, win 82.31%, leftover **14.29%** ✗, epd 3.196.
- LCT P 58.16% / q05 19.15% FAIL · MC DD p95 **723.36 vs OWN cap
  690.42 FAIL**, cluster p95 304.32 PASS, consec 4/4 · PBO 10.00% /
  DSR 0.9936 (family-5; corrected index — the finish log's 0.9889
  for this form was a substring bug, recomputed) · decay WEAKENED.

## §2 check-time-change grade (BOTH gradings reported)
1. Promotion gates (§2 top): Form I FAILS LCT-middle, AUDIT
   leftover (strictly-> and small-improvement both), MC DD arm;
   passes win, epd, AUDIT net > 0, DSR, canonical PBO, decay.
   Forms II/III fail the same core set. NO form is promotable.
2. Check-time class rule (§2 bottom): IMPROVE requires AUDIT
   leftover up AND DISC leftover not down — both are down.
   DOWNGRADE triggers: AUDIT leftover down 46.38 pts (> 0.5 pt) ✓
   AND AUDIT net down −135.70, worse than −max(25, 10% × 749.88 =
   74.99) ✓ (win 86.07% stays > 80%, that arm alone is clean).
   **Grade: DOWNGRADE** — the added 00:30 slot may NOT be adopted
   for January under the class rule.

## Verdict reasoning (gates locked in brief §2 — none moved)
The parent's named route was run in full: both free slots screened,
20 native creations mined at the stronger slot, three base forms
graded. The route's premise — that January's problem is frequency
headroom — is half right: the slot restores entries/day with room
to spare (3.96/4.37 combined). But the 00:30 January flow is a
regime-flip flow: DISC-positive (best standalone +1214.10) and
AUDIT-negative (best-DISC pick −233.20; 11 of 20 creations AUDIT-
negative standalone), and its full-stop loss pairs import a new
worst cluster (−304.32) that breaks the MC DD own-cap in every
combined form. January's EC failure is therefore NOT a frequency
problem that a new hour can fix; it is the same unseen-instability
seen in Plan A (D08) and Plan C (PC06), now confirmed at a third,
independent hour with native equations. With veto+prune exhausted
(attempt 2) and Scenario 2 creation now measured, January has no
remaining named route in this round. Incumbent cycle60b + cycle60
stands unchanged; PC06 and V04 stand as research forms. Research
level only — nothing pushed, nothing integrated.

## Numbers block (contract §9) — incumbent vs Form I (INC + S14)
- DISC leftover: 29.82% → 28.05% · AUDIT leftover: 70.06% → 23.68% ·
  AUDIT net: +749.88 → +614.18 · win: 95.56% → 86.07% (AUDIT) ·
  entries/day: 2.972/2.935 → 3.955/4.370 (DISC/AUDIT)
- LCT P/q05: — (incumbent is the reference) → 49.05% / 13.97%
- MC: P(profit) 0.9999 → 0.9991 · DD p95 527.91 vs cap 688.94 →
  888.28 vs OWN cap 784.91 FAIL · cluster p95 205.00 vs cap 302.73
  → 304.32 vs cap 456.48 · consec p95 3 → 4
- PBO: 40.00% (EC record) → 25.00% canonical (CSCV second reading
  66.67%) · DSR: 0.8630 (EC record, family N=4) → 0.9151 (this
  run's family N=21) · decay: PASS → PASS
- Slot chosen: 00:30 MMT (both slots screened on DISC probes,
  22.77% vs 15.38% best leftover). Created cycle: S14 (mom4 +
  H1 RSI band + M15 mom confirm, TP30/SL100) — standalone DISC
  n 176 / net +1214.10 / leftover 25.66% / win 80.11% / epd 1.000;
  AUDIT n 67 / net −233.20 / leftover −12.66% / win 65.67% /
  epd 1.457.
- PC06-variant (Form II): DISC leftover 32.22% · AUDIT leftover
  17.52% · AUDIT net +406.15 · win 83.44% · epd 3.358/3.543 ·
  LCT 56.95/17.07 · MC DD p95 848.39 vs OWN cap 807.41 FAIL ·
  PBO 10.00% / DSR 0.9889 (family-5) · decay PASS.
- Loss-cluster mechanism: S16 post-loss symbol cooldown + S17
  post-loss global skip-1 (explicit, inside the slot flow);
  S14 combined cluster arm BEFORE → AFTER: worst cluster obs
  −201.82 → −304.32 (the slot imports its own cluster), consec
  3 → 4; S16-combined AUDIT leftover 49.17% is the best any
  cluster-controlled variant preserves — still 21 pts short.
- Trial count: 2 probes × 2 slots + 20 creations pre-registered;
  PBO/DSR family N = 21 (incumbent + 20 INC-combined forms);
  family-5 for Forms II/III. DXY: BLOCKED-DATA, not used, not
  claimed; S08/S20 dollar legs are DOLLARIDX-labelled only.
