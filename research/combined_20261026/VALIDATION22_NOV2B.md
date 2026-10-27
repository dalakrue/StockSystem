# BRIEF22 Workstream B — NOVEMBER second best: VALIDATION22_NOV2B

## VERDICT: NO SECOND BEST for November

Control = November C20a (C93-24 + C06 vol veto + C16 re-entry): DISC n436 net +5128.59 win 92.20% leftover 69.12 · AUDIT n100 net +678.37 win 88.00% leftover 46.39; checks (ledger UTC) 09:30/13:30/15:30; N=83; cost @2.5; A3 frame (DISC 2016-2023, AUDIT 2024+2025 read once).

20 cycles run (B01-B20). Only the class-A pool-bench family screened positive on discovery (B01-B04, combined DISC leftover delta +0.86 to +1.41 vs C20a 69.12). Every fresh-signal design (gap-check, undetected-symbol, extra-check, and all stacks) screened strongly negative (-9.74 to -43.06). The two finalists were validated as COMBINED systems (C20a first priority + second best) under the locked BRIEF21 gates; BOTH fail core gates (LCT-middle and EC22 count) and both materiality clauses. No alternative second best is designated for November.

## Gap map (from brief21/logs/c20a.csv; gap_map.json)

- Grid = 645 checks (Nov 2016-2025 x 09:30/13:30/15:30 UTC). C20a trades at 450; **195 silent** (DISC 159, AUDIT 36; silent by stamp DISC 09:30=11, 13:30=61, 15:30=87).
- C20a trades only 9 of 20 symbols. Undetected (11): AUDJPY, CHFJPY, EURCAD, EURCHF, EURGBP, EURJPY, GBPJPY, NZDCAD, NZDUSD, USDCAD, USDJPY. The incumbent pool has ZERO effective rows for them at grid checks - class B is reachable only by fresh signals.
- Pool rows at silent checks: 125; fb-pass AND interval-free = 89 (DISC 62, AUDIT 27) over 65 checks; ALL 89 carry vol_z > 1.50 - this population IS the C06 veto shadow (at every silent check, every fb-pass row was veto-suppressed). 130 silent checks have no free pool row at all.

## Discovery screens (combined vs C20a; audit unread)

| cycle | design | legs | classes | dDISC LO | dHOLDOUT LO | screen |
|---|---|---|---|---|---|---|
| B01 | GapBench pool top-1 at silent checks | 62 | {'A': 62} | +1.01 | -1.07 | POSITIVE |
| B02 | GapBench TP x0.80 | 63 | {'A': 63} | +0.86 | -0.83 | POSITIVE |
| B03 | GapBench score-gated | 42 | {'A': 42} | +0.90 | +0.06 | POSITIVE |
| B04 | GapBench dual (2/check) | 80 | {'A': 80} | +1.41 | +1.35 | POSITIVE |
| B05 | GapFresh 0.25 silent checks | 194 | {'A': 194} | -21.15 | -21.42 | fail |
| B06 | GapFresh 0.50 | 192 | {'A': 192} | -20.18 | -21.42 | fail |
| B07 | GapFresh 0.25 silent 15:30 only | 106 | {'A': 106} | -9.74 | -7.83 | fail |
| B08 | GapFresh 0.25 detected syms only | 176 | {'A': 176} | -25.15 | -33.02 | fail |
| B09 | UndetFresh 0.25 all checks | 621 | {'B': 434, 'A': 187} | -35.58 | -34.60 | fail |
| B10 | UndetFresh 0.50 | 605 | {'B': 422, 'A': 183} | -35.02 | -35.27 | fail |
| B11 | UndetFresh JPY5 0.25 | 526 | {'B': 366, 'A': 160} | -39.46 | -41.39 | fail |
| B12 | UndetFresh 0.25 partner cap 2 | 454 | {'B': 321, 'A': 133} | -33.74 | -26.86 | fail |
| B13 | ExtraFresh 0.25 @17:30 (FIT-chosen) | 215 | {'C': 215} | -24.25 | -26.43 | fail |
| B14 | ExtraFresh 0.50 @17:30 | 213 | {'C': 213} | -24.51 | -26.93 | fail |
| B15 | Stack A+B fresh 0.25 | 623 | {'B': 434, 'A': 189} | -36.68 | -36.42 | fail |
| B16 | Stack A+B+C fresh 0.25 | 787 | {'B': 407, 'C': 195, 'A': 185} | -43.06 | -38.52 | fail |
| B17 | Stack A+B+C fresh 0.50 | 775 | {'B': 398, 'C': 194, 'A': 183} | -42.52 | -39.43 | fail |
| B18 | Stack A+B+C + pool bench | 793 | {'B': 412, 'C': 195, 'A': 186} | -41.81 | -39.98 | fail |
| B19 | Stack A+B+C TP x0.80 legs | 816 | {'B': 428, 'C': 200, 'A': 188} | -40.15 | -41.75 | fail |
| B20 | Finalists frozen (F1=B04, F2=B01) | - | - | - | - | - |

Extra check time: candidates 07:30 / 11:30 / 17:30 UTC scored on FIT standalone leftover (-30.47 / -55.89 / +0.97) - **17:30 UTC frozen** as the one extra check; used only by B13/B14/B16-B19, all screen-negative, so no finalist uses an extra check.

## Finalist F1 = B04 (combined C20a + second best)

Design: GapBench DUAL: at each check where C20a takes no trade, admit up to 2 fb-pass pool rows (distinct symbols, eq-score order), full-interval conflict-free vs C20a + admitted legs, live cap 6. Gap classes filled: {'AUDIT_A': 22, 'DISC_A': 58} (DISC_A / AUDIT_A legs); class B 0, class C 0; extra check not used.

- COMBINED DISC n494 net +6369.43 win 92.31% leftover 70.53 (FIT 74.64 / HOLDOUT 64.08 leftover), DD 9.12%, floatDD 13.28%, peak margin 5.99% @1:1000, clusters max_consec 2 worst5 -111.80
- COMBINED AUDIT n122 net +552.82 win 86.07% leftover 30.00, epd 2.976, DD 29.00%, floatDD 30.32%, clusters max_consec 3 worst5 -260.18
- Control DISC n436 net +5128.59 win 92.20% leftover 69.12 · AUDIT n100 net +678.37 win 88.00% leftover 46.39
- LCT-middle: P 70.51% (need >=80) q05 53.99% (need >=20) -> FAIL
- EC22-middle count 12 vs C20a 15 (BRIEF21 basis, excl. waived 15 + report-only 20)
- EC checks differing from control (cand, ctrl): {'3_boot': (False, True), '8_weeks': (False, True), '13_lct': (False, True)}
- Monte Carlo paired chain (2500 paths): median-final ratio 334.1805x (uncapped-compounding artifact; P(call) is the robust half) P(call) 0.0000 vs 0.0000 -> PASS; median peak 6.19% vs 6.14%, median DD 11.01% vs 10.32%
- PBO 0.00% (not HIGH) · DSR 1.0000 vs ctrl 0.9998 (report-only)
- Sizing guard: peak margin 5.99% / max DD 29.55% -> pass_a2 True (ctrl 6.02% / 19.43%)
- Red lines: audit net > 0 True, unseen True, discovery True · conflict-free True (max concurrency 5) · role audit clean True
- Materiality: DISC leftover gain +1.41 (need >= +5) FAIL · audit leftover 30.00 vs C20a 46.39 (need >=) FAIL
- Gates: {'red_audit_net': True, 'red_unseen': True, 'red_disc': True, 'lct_middle': False, 'ec22_count': False, 'leftover_disc_gt': True, 'win_disc_gt80': True, 'win_audit_gt80': True, 'epd_disc': True, 'epd_audit': True, 'mc_median': True, 'mc_pcall': True, 'mat_disc_lo': False, 'mat_audit_lo': False, 'conflict_free': True, 'role_clean': True}
- **F1 verdict: NO SECOND BEST**

Second best STANDALONE (B04 legs alone): DISC n58 net +1240.84 win 93.10% leftover 77.29, clusters max_consec 1 worst5 -51.04 · AUDIT n22 net -125.55 win 77.27% leftover -32.45, clusters max_consec 2 worst5 -160.29

## Finalist F2 = B01 (combined C20a + second best)

Design: GapBench: at each check where C20a takes no trade, admit the single top fb-pass pool row (eq-score order), full-interval conflict-free vs C20a + admitted legs, live cap 6. Gap classes filled: {'AUDIT_A': 19, 'DISC_A': 43} (DISC_A / AUDIT_A legs); class B 0, class C 0; extra check not used.

- COMBINED DISC n479 net +6067.72 win 92.28% leftover 70.13 (FIT 75.29 / HOLDOUT 61.66 leftover), DD 9.33%, floatDD 14.33%, peak margin 5.99% @1:1000, clusters max_consec 2 worst5 -111.80
- COMBINED AUDIT n119 net +744.41 win 87.39% leftover 41.37, epd 2.902, DD 16.61%, floatDD 24.38%, clusters max_consec 2 worst5 -148.62
- Control DISC n436 net +5128.59 win 92.20% leftover 69.12 · AUDIT n100 net +678.37 win 88.00% leftover 46.39
- LCT-middle: P 59.67% (need >=80) q05 56.08% (need >=20) -> FAIL
- EC22-middle count 13 vs C20a 15 (BRIEF21 basis, excl. waived 15 + report-only 20)
- EC checks differing from control (cand, ctrl): {'8_weeks': (False, True), '13_lct': (False, True)}
- Monte Carlo paired chain (2500 paths): median-final ratio 224.8476x (uncapped-compounding artifact; P(call) is the robust half) P(call) 0.0000 vs 0.0000 -> PASS; median peak 6.17% vs 6.14%, median DD 10.57% vs 10.52%
- PBO 0.00% (not HIGH) · DSR 1.0000 vs ctrl 0.9998 (report-only)
- Sizing guard: peak margin 5.99% / max DD 16.62% -> pass_a2 True (ctrl 6.02% / 19.43%)
- Red lines: audit net > 0 True, unseen True, discovery True · conflict-free True (max concurrency 5) · role audit clean True
- Materiality: DISC leftover gain +1.01 (need >= +5) FAIL · audit leftover 41.37 vs C20a 46.39 (need >=) FAIL
- Gates: {'red_audit_net': True, 'red_unseen': True, 'red_disc': True, 'lct_middle': False, 'ec22_count': False, 'leftover_disc_gt': True, 'win_disc_gt80': True, 'win_audit_gt80': True, 'epd_disc': True, 'epd_audit': True, 'mc_median': True, 'mc_pcall': True, 'mat_disc_lo': False, 'mat_audit_lo': False, 'conflict_free': True, 'role_clean': True}
- **F2 verdict: NO SECOND BEST**

Second best STANDALONE (B01 legs alone): DISC n43 net +939.13 win 93.02% leftover 76.45, clusters max_consec 1 worst5 -58.18 · AUDIT n19 net +66.04 win 84.21% leftover 19.48, clusters max_consec 2 worst5 -71.71

## Why no second best

1. The only gap population with any discovery quality is the C06 veto shadow (class A). Its discovery gain (+1.01 / +1.41 leftover) sits inside LCT noise: paired P 59.67% (F2) / 70.51% (F1) < 80%.
2. It costs EC22 checks against C20a's own marks (F1 loses 3_boot and 8_weeks; F2 loses 8_weeks; both lose 13_lct with the LCT).
3. Unseen, the shadow does not pay: F1's audit legs are net-negative standalone (-125.55; combined audit leftover 46.39 -> 30.00); F2's are positive but dilutive (+66.04; combined audit leftover 41.37 < 46.39). The veto was earning its keep precisely at the checks it silenced.
4. Fresh-signal filling is decisively negative in every gap class (A -9.74 to -25.15, B -33.74 to -39.46, C -24.25/-24.51, stacks -36.68 to -43.06): at the frozen C20a geometry, November's silent checks and undetected symbols carry no fresh edge. This matches BRIEF21, where the same fresh family (C19) screened -27.72 on the incumbent frame.

## App-expressibility (of the finalist designs, for the record)

GapBench legs are computable at a single check from data the app already fetches: the incumbent pool equations + fb gate (H1/M15 price features, identical to the C93-24 panels), eq-score ordering (static table), and symbol occupancy from CURRENT open positions (live app state, the October dual-pick selector pattern). The trigger "C20a produced no trade at this check" is known at decision time. NO vol_z / tick volume (the bench deliberately does not re-apply C06), NO closed-trade-ledger state, NO re-entry construction. The design is expressible; it failed on quality gates, not on expressibility. The fresh families are likewise expressible (H1 bias from H1 bars; M15 EMA20/ATR14 within a 200-bar window) and failed on quality.

## Files

brief22/nov2b/: gap_map.json, lib22b.py, run22b.py, state22b.json, results/B01-B20.txt, results/validation22_nov2b.json, logs/ (per-cycle combined + legs CSVs; f1/f2 finalists), validate22_nov2b.py. Status: brief22/STATUS22_NOV2B.md. NO integration, NO GitHub push (verdict only).
