# Cycle 116 — Ten-Method Overlay Screen — SUMMARY

Screening level only, per the user's order: single pass, no LCT, no validation
battery, no chain simulation, no promotion, no app changes, no Git. Baseline for
every test: the standing Book V5 system, judged overlay ON vs OFF on the
discovery + 2025 audit ledgers @2.5 (leftover by the house by-trade formula;
all 12 OFF baselines reproduce the published Book V5 numbers exactly, and the
Apr/Sep harness re-walks reproduce their saved winner logs to the pip).

**Result: 2 of 12 POSSIBLE, 10 NOT.**

| Month | System | Method | Verdict | One-line reason |
|---|---|---|---|---|
| Jan | C60-03 | Distributionally robust growth sizing | **POSSIBLE** | The robust criterion (maximize worst training-year log growth within margin/DD limits) selects the 0.25× lot multiplier: worst-year log growth 0.066 → 0.180. Caveat in jan.md: total discovery growth falls $4,209 → $1,493 — worst-year smoothness is bought with most of the growth. |
| Feb | C85-23 | CAViaR conditional-tail partial exit | NOT | Cuts avg loss (audit 50.5 → 40.3 pips at 25%) but cuts recovering trades almost as much: audit leftover 29.35% → 29.13%, discovery 61.36% → 60.44%; the 50% variant also breaks win > 80% on discovery (79.45%). |
| Mar | C86-24 | Model Confidence Set | NOT | MCS survivor set: incumbent + N071 + X28 + X36. R22 — the only challenger with a leftover gain (80.30%) — is the one model eliminated, and its Cycle-98 LCT P was 6.11%; no challenger meets the leftover + win + frequency + LCT gates together. |
| Apr | C87-24 | Theil–Sen robust-slope ranking bonus | NOT | Actively harmful: promoting steep-slope candidates swaps in worse trades — discovery leftover 78.99% → 50.84%, audit 60.26% → 41.91% (reproduction of the standing system was exact before judging). |
| May | C88-03 | HAR volatility-forecast sizing | NOT | Audit max DD 11.71% → 10.68% only, and log growth is given back to buy it (0.549 → 0.500). |
| Jun | C89-21 | Rogers–Satchell partial exit | NOT | It does catch both −102.5 audit losses (−102.5 → −57.7 and → −77.0) and halves avg loss, but it also halves many temporarily-underwater trades: discovery win 94.75% → 84.94%, leftover down on both ledgers (58.20% → 56.97% audit). |
| Jul | C78-34 | Bayesian change-point partial exit | NOT | Trigger almost never fires in the audit year (0 of 68 trades; 18 of 527 discovery): audit identical, discovery leftover 62.30% → 61.84%. |
| Aug | C67-04 | Ledoit–Wolf covariance sizing | NOT | The standing path is already nearly flat (audit max DD 4.80%): the overlay moves it to 4.97% — nothing material to fix at account level. |
| Sep | C91-15 | Two-state HMM ranking bonus | NOT | Bonus awarded to 1,588 candidate rows but changes no audit pick (audit identical) and slightly worsens discovery (leftover 50.51% → 48.36%). |
| Oct | C92-24 | Variance-ratio routing | NOT | Cannot be implemented as specified: at every empty check (11 discovery, 3 audit) the only existing candidates are occupancy-blocked — 0 free candidate rows — so there is no eligible continuation candidate for the VR/momentum/CLV conditions to admit. Ceiling if all 3 audit empty checks could trade: 2.22/day vs 2.09/day. |
| Nov | C93-24 | Ledoit–Wolf covariance + tail-risk lot control | **POSSIBLE** | Audit max DD falls on the house sizing path (LW overlay: 14.36% → 11.25%, 23 of 52 lots scaled, peak margin unchanged; tail overlay: → 7.55%). Caveats in nov.md: the tail rule as specified halves nearly every lot (52/52), so most of its gain is plain half-size at a large final-$ cost; the selective LW overlay is the useful half of the pair. Note the published 23.31% DD was measured on the producing round's marked-equity path; this screen's OFF path is the realized-balance house path (14.36%) — ON/OFF is same-method. |
| Dec | C94-23 | Model Confidence Set | NOT | MCS survivor set: incumbent + PB23 + PB21 (statistically indistinguishable from the incumbent); R20 eliminated. No survivor can be promoted: PB23's LCT P was 77.39% and PB21's 60.06% (Cycle 115), both below the LCT-middle bar — C94-23 stands. |

## Flagged completions (from the brief — truncated in the user's paste)

- **May**: lot multiplier implemented as min(1, trailing-median(F)/F), floored at 0.5, F = HAR forecast variance.
- **October**: variance-ratio threshold implemented as VR(2,8) on H1 closes > 1.0 (trending). The condition was never reached: no admissible candidate exists at any empty check (see oct.md).

## Method notes

- Partial-exit overlays (Feb/Jun/Jul) were applied to the saved ledgers by re-walking each trade's M15 path; a trigger mark was required to lie inside the trade's original TP/SL band and the remainder keeps the original outcome — a screening approximation, stated in each file.
- Sizing overlays (Nov/Aug/May/Jan) ran through the house sizing engine (c104_core.policy_path, start $1,000, each month's standing Best N); lot overlays do not change pip statistics by construction, so those verdicts rest on the DD / margin / log-growth paths.
- MCS (Mar/Dec): per-trade returns aggregated to daily P&L (MCS needs a common time index), circular block bootstrap, 5-day blocks, 1,000 draws, 80% confidence, range-statistic variant referenced to the current best model.
- July's change-point detector is the brief-approved lightweight simplification (Adams–MacKay run-length posterior, hazard 1/50, NIG predictive, run-length cap 260).

Per-month detail: feb.md, mar.md, apr.md, may.md, jun.md, jul.md, aug.md,
sep.md, oct.md, nov.md, dec.md, jan.md in this directory.
