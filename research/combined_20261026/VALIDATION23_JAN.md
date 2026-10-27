JANUARY BRIEF23 VERDICT: VALIDATED-HUGE — C20_STACK (C10 base + C17 dual-pick partner)

Incumbent: C60-03 (N=83). Frame A3: DISC 2016–2023 (FIT 2016–2020,
HOLDOUT 2021–2023), AUDIT 2024+2025 (read once, here). Cost @2.5.
Exact raw-price replay only. Baseline probe-verified: the BRIEF21
walk157 machinery reproduces the c194 control ledger exactly
(n 513/132), and this round's control re-walk matches the locked
figures (DISC leftover 24.25). Gates: BRIEF23.md LOCKED (identical
to BRIEF21/22): red lines, LCT-middle, EC22-middle, Monte Carlo
paired gate, materiality; middle overfit allowed (PBO MEDIUM-or-
better passes, DSR report-only). All designs app-expressible from
the start (stateless per check, price features within H1 /
≤200-bar M15, no closed-trade-ledger state, no re-entry, no
tick-volume statistics).

## WINNER: C20_STACK = C10 + C17

C10 (Phase A multi-combination of the two strongest Phase A
components, C02 × C09) rewrites ONLY the FB fallback layer:
1. **Breadth veto (C02)**: veto every FB pick whose entry
   breadth_m15 > 0.4 (breadth_m15 = cross-symbol mean of M15
   above-EMA20 at the check; 0.4 = FIT first-tercile cut). This
   is the stateless separator BRIEF21+22 missed: on discovery,
   FB trades entered at breadth ≤0.4 sit at leftover +44.0 (FIT)
   / +100.0 (HOLDOUT), while breadth >0.4 FB trades bleed in
   BOTH segments (FIT −87.0/−73.3, HO −11.9/−0.3) — it separates
   bleeder from recoverer AT ENTRY, so no exit rule has to
   guess, and the audit segment is not asked to pay for a stall.
2. **Geometry + conditional stall (C09)**, on the FB trades
   that survive: SL ×0.60 for all FB rows; plus a 24h stall cut
   applied ONLY to FB trades with pat_score > 0 (the segment
   that bleeds in both FIT and HOLDOUT), sparing pat ≤0 slow
   trades to recover.
3. C17 partner on top: score-gated dual-pick (second pick at the
   same check, different symbol, eq score ≥ 972 = median
   positive eq score, concurrency cap 5) — 10 legs on DISC,
   restoring frequency above the ≥2/day floor. Conflict-free
   verified (incumbent priority, max concurrency 3).

## Gate table — C20_STACK vs control C60-03

| Gate | Control | C20_STACK | Result |
|---|---|---|---|
| DISC leftover | 24.25 | **64.23 (+39.98)** | PASS |
| DISC n / net / win | 513 / +1046.61 / 92.20 | 355 / +1984.54 / 95.21 | — |
| DISC epd (≥2) | 2.915 | 2.017 | PASS |
| FIT / HOLDOUT leftover | 13.61* / 42.20* | 63.53 / 65.35 | both segments up |
| AUDIT leftover (≥ incumbent) | 67.13 | **67.50** | PASS |
| AUDIT n / net / win | 132 / +703.87 / 95.45 | 101 / +550.18 / 96.04 | net > 0 PASS |
| AUDIT epd (≥2) | 2.87 | 2.196 | PASS |
| LCT-middle: paired P ≥80% | — | **100.00%** | PASS |
| LCT-middle: own q05 ≥20% | — | **55.20%** (strict also passes) | PASS |
| EC22-middle count | 14 | **15** | PASS (cand fails only {8_weeks, 20_dsr-report-only}; control fails {8_weeks, 14_leftover, 20_dsr}) |
| Monte Carlo median final | 1.00× | **182.09×** (uncapped-chain compounding artifact, identical-method paired comparison — directionally decisive, magnitude not literal) | PASS |
| Monte Carlo P(call) ≤ ctrl +2pts | 0.0008 | **0.0000** | PASS |
| Materiality: DISC gain ≥ +5 | — | +39.98 | PASS |
| Materiality: audit leftover ≥ inc | — | 67.50 ≥ 67.13 | PASS |
| Red lines: audit net >0; DISC not collapsed | — | +550.18; DISC LO 64.23 | PASS |
| Overfit: PBO not-HIGH | — | 2.50% | PASS; DSR 0.1745 report-only |
| Conflict-free / max concurrency | — | yes / 3 | PASS |

*Control FIT/HOLDOUT leftovers per BRIEF22 record basis.

Honest note on audit net: audit NET falls (+550.18 vs +703.87)
because the stack takes 31 fewer audit trades — the vetoed
high-breadth FB trades were net-positive in aggregate on the
audit years even though their leftover was dilutive. Every
locked gate is computed on leftover/win/frequency, and all
pass; the red line (audit net > 0) passes with a wide margin.
This is the mirror of BRIEF22's failure: there the stall cut
raised discovery but CUT audit net below control and dropped
audit leftover by 11.93 pts; here audit leftover RISES.

## Loss clusters (scored objective)

| Frame | Stat | Control | C20_STACK |
|---|---|---|---|
| DISC | max consecutive losses | 3 | **2** |
| DISC | worst rolling 5-trade window | −255.61 | **−103.10** |
| DISC | floating DD | 28.09% | **12.05%** |
| DISC | account DD | 26.61%* | **6.77%** |
| AUDIT | max consecutive losses | 2 | **1** |
| AUDIT | worst rolling 5-trade window | −61.42 | **−60.33** |
| AUDIT | floating DD | 14.62% | **10.40%** |

*Control account DD per this round's disc bundle (26.61 cash DD
basis in screen records). Clusters improve on every measure in
both frames — consistent with the Monte Carlo result (median
chain DD 9.45% vs control 24.25%, P(call) 0.0000 vs 0.0008).

## Also validated / also-rans

- C10 (the base alone) and C02 (breadth veto alone): DISC
  leftover 63.33 / 60.41, but epd 1.96 < 2.0 — both fail the
  locked frequency gate deterministically, so neither is a
  SMALL verdict; the C17 partner's 10 legs are what lift the
  stack to 2.017/day. (Their full batteries were not run: the
  first 3-finalist validation process died under parallel
  month workloads — machine memory exhaustion, no traceback —
  and the stack-only rerun completed cleanly; the epd failure
  is arithmetic from the screen ledgers, not a battery output.)
- C07 (FB bias-flip exit, DISC +9.59) failed the discovery
  screen on the holdout margin (dHO −5.73) — segment flip,
  correctly caught, not validated.

## 20-cycle screen record (discovery dLO vs control 24.25)

Phase A (improve): C01 FB pat>0 veto +2.39 · C02 FB breadth>0.4
veto **+36.16** POSITIVE · C03 veto pat∧breadth +0.11 · C04 veto
breadth∧pat∧rsi_slope +3.01 · C05 FB stall24 only pat>0 −0.52 ·
C06 FB stall24 only breadth>0.4 +5.34 POSITIVE · C07 FB bias-flip
exit +9.59 (holdout −5.73, screen-caught) · C08 C04 veto + C05
stall +4.39 · C09 rsi∧breadth veto × FB SL0.60 × pat-stall +7.99
POSITIVE · C10 composition C02×C09 **+39.08** POSITIVE.
Phase B (partners, judged combined): C11 dual median +1.17 ·
C12 dual median+pat≤0 +0.91 · C13 dual median+breadth≤0.4 +0.39 ·
C14 dual Q75 +0.78 · C15 dual median+counter +0.52 · C16 fresh
extra-check 15:00 UTC −11.99 (fresh-signal family closed for
January, third round running) · C17 dual median cap5 **+1.29**
(best partner) · C18 dual same-dir +0.78 · C19 dual tightest
+0.39 · C20 STACK (C10 + C17) **+39.98**, finalist.

The pattern is decisive: in January the multi-combination that
works is veto × geometry × conditional-exit stacked on the FB
layer, plus a small score-gated dual-pick for frequency. The
stall family alone (BRIEF22's engine) is worth +5 to +8; the
entry-time breadth veto alone is worth +36 — because it removes
the bleeders before entry in every segment instead of trading
one segment off against another at exit time.

## App-expressibility check (winner)

- Breadth veto: at a check, breadth_m15 = mean over the 20
  symbols of (M15 close > M15 EMA20) at the last completed M15
  bar — stateless, computed from the same 20-symbol M15 set the
  January panel already fetches for its equations; threshold
  0.4 is a static FIT-fitted constant in config. FB scope =
  static equation identities.
- SL ×0.60: per-equation static geometry for the FB equations.
- Conditional stall: per-trade exit rule on the trade's OWN
  bars since entry + its entry pat_score (a static entry-time
  feature recorded at entry); no other trade's history.
- Dual-pick: the October precedent selector (check's own
  candidate rows + live symbol/count occupancy only), score
  threshold 972 a static constant, cap 5.
- No closed-trade-ledger state, no re-entry construction, no
  tick-volume statistic (vol_z never used). Every component is
  computable at a single check from H1 bars or M15 bars within
  the app's reach.

## Verdict

**VALIDATED-HUGE.** January improves for the first time in
three rounds: discovery leftover 24.25 → 64.23 (+39.98, nearly
8× the +5 materiality bar), audit leftover 67.13 → 67.50, LCT
q05 55.20 (the clause that killed both prior rounds at
18.99/16.56 now passes even the strict line), EC22 15 vs 14,
Monte Carlo both clauses, loss clusters better on every
measure in both frames. Promotion decided under the middle
standard per standing orders; integration LOCAL only, nothing
pushed (per orders).
