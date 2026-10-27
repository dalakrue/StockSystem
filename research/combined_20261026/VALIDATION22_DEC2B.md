# BRIEF22 Workstream B — DECEMBER second-best validation

**VERDICT: SMALL — no VALIDATED alternative second best for
December.** The single screen-positive design (B10) passes every
core gate but misses the materiality bar by a wide margin
(discovery leftover gain +0.17 vs the required +5.00). December's
designated second best therefore remains the BRIEF18 cycle274
stack; B10 stands as December's recorded BRIEF22-2B best (SMALL).
Nothing integrated; app untouched; no GitHub push.

Control = December C20a (C94-23 + C06 vol veto + C16 re-entry;
BRIEF21 VALIDATED-HUGE). All gates per BRIEF21.md locked set +
both addendums, judged COMBINED (C20a first priority + second
best filling only measured gaps) vs C20a alone.

## Measured gap space (before any design work)

Grid: 660 December checks (2016–2025 business days × stamps
10:30/11:30/13:30 ledger UTC); the C196 pool covers 639. C20a
trades at 620 checks → **40 silent checks** (DISC 32, AUDIT 8).

- **Class A** (silent checks, pool rows): only 14/40 silent
  checks carry any gate_ok row; 40 free gate_ok rows full-frame
  (DISC 34), **100% of them veto-shadowed** (vol_z > 1.12 — the
  C06 veto is what silenced those checks; measured, never used
  as a design gate here). Raw DISC outcome n34 net +26.14,
  win 88.24%, leftover +8.29 (dilutive vs 66.20). The other 26
  silent checks are fresh-leg territory only.
- **Class B** (symbols C20a never trades): C20a trades 16/18
  pool symbols. Undetected = **AUDUSD, EURAUD**: 383 gate_ok
  rows (DISC 302 / AUDIT 81), all interval-free vs C20a. Raw
  DISC leftover **−60.68** (net −1377.98), AUDIT −32.63.
  Measured at B01: **all 302 DISC rows are FB fallback rows** —
  no scored momentum equations exist on these symbols; the FB
  scores are −1e9 sentinels, so score-based designs are empty
  by construction on this class.
- **Class C**: no off-grid pool rows exist; fresh legs only.
  Extra stamps screened: 12:30 (B13–B15), 09:30 (B16).

## The 20 cycles (discovery screen; screen-positive = combined
DISC leftover gain > 0 AND holdout gain ≥ 0)

Class B — all fail: B01 raw −30.06 · B02 momentum-aligned
−19.62 · B03 trend-aligned −19.88 · B04 direction skim (no FIT
direction > 0 → empty) · B05 ADX≥25 −12.30 (least-bad) ·
B06 pat_score −21.02 · B07 (symbol, stamp) FIT cells (none
qualify → empty) · B08 TP≥15 geometry (no such rows → empty).
The undetected-symbol FB layer is toxic under every stateless
skim tried — the same FB-layer pattern January's Plan B found.

Class A — B09 all gate_ok rows −0.36 (12 legs) ·
**B10 mom-only rows: SCREEN-POSITIVE, +0.17 / holdout +0.08
(3 legs)** · B11/B12 fresh legs at silent checks −22.84/−22.60
(legs' standalone leftover −188.79/−176.36 — fresh signals at
checks the incumbent's machinery rejects are decisively bad).

Class C — B13 12:30 thr 0.50 −35.09 · B14 thr 0.25 −38.04 ·
B15 12:30 undetected-only −24.37 · B16 09:30 −39.31. (12:30
fresh legs are mildly negative per trade in discovery,
leftover −5.88, but numerous — 569 legs; their audit legs were
positive, +37.29, but the screen is discovery-only and the
discovery failure is decisive.)

Compositions B17–B19 unavailable (only one screen-positive
design existed, class A only) — recorded DOES NOT WORK with
that explanation. B20 froze F1 = B10.

## F1 = B10 validated (combined vs C20a)

Design: at C20a's silent checks only, take the incumbent
machinery's own scored momentum rows (gate_ok, best score per
check), partner cap 3, C20a occupancy absolute priority,
conflict-free by construction and verified in the combined
ledger (conflict_free TRUE, max concurrency 7 = C20a's).

| | Combined (C20a + B10) | C20a |
|---|---|---|
| DISC | n653 net +4513.50 win 94.95% leftover **66.37** | n650 net +4479.75 win 94.92% leftover 66.20 |
| AUDIT | n157 net +1135.57 win 96.18% leftover 75.39 | identical (0 audit legs) |
| DISC worst-5 cluster | −169.24 | −169.24 |
| DISC max consec losses | 2 | 2 |
| DISC floating DD | 14.43% | 14.43% |

Gates:
- Red lines: PASS (audit net +1135.57 > 0; battery red_disc
  TRUE).
- LCT-middle: **PASS** — paired P 96.40%, candidate q05 55.16%
  (strict also passes; the 3 legs are pure winners sitting in
  early discovery blocks).
- EC22-middle: **PASS on the battery convention** — counts
  15 vs 15 (basis excludes waived 15_epd and report-only
  20_dsr; both sides fail identically 14_leftover — an equality
  artifact, 75.39 vs 75.39 — 15_epd and 20_dsr). Benchmark note:
  BRIEF21 recorded C20a at 16 vs C94-23's 14 under the
  C94-23-control battery; with C20a itself as control the same
  convention yields 15, and the candidate matches it.
- Leftover strictly above: PASS (+0.17). Win > 80% both
  frames: PASS. Entries/day ≥ 2: PASS (DISC 3.84, AUDIT 3.65).
- Monte Carlo gate: PASS — paired chain 2,500 paths, median
  final ratio 1.1635× (uncapped-compounding amplification of 3
  pure winners in the resample pool; direction only is
  meaningful), P(call) 0.0000 vs 0.0000.
- **Materiality: FAIL** — discovery leftover gain +0.17 <
  +5.00 required (audit clause passes at equality, 75.39 ≥
  75.39, zero audit legs).
- Overfit (addendum 1): PBO 2.50% (not HIGH) — passes; DSR
  0.0383 report-only.

## Winner's standalone ledger stats (for the record)

B10 legs: **3 trades, all class A, all discovery, all TP
winners**: EURGBP SELL 2018-12-20 11:30 (+11.21 net pips),
EURNZD SELL 2019-12-04 10:30 (+15.04), EURNZD SELL 2021-12-31
13:30 (+7.50). Standalone: n3 net +33.75, win 100%, leftover
100.00; audit legs 0. Gap classes filled: A = 3 (DISC) / 0
(AUDIT); B = 0; C = 0; no extra check time used.

## App-expressibility of B10

Fully expressible: it reuses the incumbent's own per-check
scored momentum rows (the app's existing signal machinery) at
checks where the incumbent stack produced no trade; the rule
is stateless per check (gate_ok + best score + symbol
occupancy vs the frozen incumbent set), price-based features
only, no closed-trade-ledger state, no re-entry construction,
no tick-volume statistic. (The veto-shadow fact — all silent-
check pool rows carry vol_z > 1.12 — was measured for the gap
map only and is NOT part of the design.)

## Bottom line

December's gap space is real but nearly empty of quality: 40
silent checks whose pool content is the veto's own shadow, two
undetected symbols served only by a losing FB fallback layer,
and fresh-signal space that loses decisively at every stamp
tried. The one quality fragment — scored mom rows at silent
checks — is worth +0.17 discovery leftover over 8 years.
**SMALL, not a validated second best.**
