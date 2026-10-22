# BRIEF9 — Cycle 116: Ten-Method Overlay Screen (user order 2026-10-22 ~23:21 MMT)

PURPOSE (user's words, operative): test the pasted 10-method proposal end to end, fast,
against the latest 12 systems; give the result fast; DO NOT do the validation step;
the user just wants to know POSSIBLE OR NOT for each overlay.

BASELINE: the standing Book V5 twelve (Feb C85-23, Mar C86-24, Apr C87-24, May C88-03,
Jun C89-21, Jul C78-34, Aug C67-04, Sep C91-15, Oct C92-24, Nov C93-24, Dec C94-23,
Jan C60-03). NOT the Program 5/B research variants. Same engine rules as every round:
@2.5 audit + discovery ledgers, M15 fills SL-first/gap-at-open, 48h cap, permitted pairs.

JUDGING (SCREENING LEVEL — user explicitly waived validation):
- Overlay ON vs OFF, same trades framework; report discovery + 2025 audit: leftover %,
  win %, entries/day, net pips; sizing overlays also: peak margin %, max DD, $ path.
- Verdict per month: POSSIBLE (leftover up, win >80%, ≥2/day kept, DD not materially
  worse) / NOT (no improvement or a guard broken). For sizing-only months the verdict
  is on DD/margin/log-growth improvement at no pip-stat cost.
- NO LCT, NO bootstrap battery, NO chain simulation, NO promotion, NO app, NO Git.
- MCS months (Mar, Dec): the MCS procedure IS the method — report the survivor set.
- Speed first: single pass, no reruns, no parameter search beyond the stated settings.
  Two settings where the proposal states two (Feb 25% and 50%).

THE 12 TESTS (proposal text supplied by the user 2026-10-22; two truncated values
completed by Muse and FLAGGED — report them as completions, do not hide them):

1. FEB C85-23 — CAViaR-style conditional tail overlay. Keep primaries, removed FB legs,
   surviving FB TP x1.75. Rolling 95th-percentile adverse move from M15 returns
   (trailing 20 trading days). While a trade is open and losing, if the forecast
   adverse move > 0.35 x entry H1 ATR, close 25% (variant A) / 50% (variant B) of the
   position at the next H1 open. Compare loss size, leftover, win.
2. NOV C93-24 — Ledoit-Wolf shrinkage covariance (synchronized H1 returns, trailing
   60d) across the pairs the system trades; if a proposed position materially raises
   concentrated currency exposure (marginal portfolio vol +>10% vs trailing median),
   halve its lot. Second overlay: halve lot when the Feb-style adverse-tail forecast
   is elevated. Sizing-path verdict (DD 23.31% is the target stat).
3. MAR C86-24 — Model Confidence Set. Incumbent vs a FIXED challenger set (the named
   C98 challengers with saved ledgers, up to 4: incl. R22), 80% MCS, 1,000 block
   bootstrap draws, 5-day blocks, on per-trade returns. Report who survives.
4. APR C87-24 — Theil-Sen robust slope: median pairwise slope of prior 24 H1 closes,
   normalized by H1 ATR; ranking BONUS (not a veto) in the existing top-3 rerank when
   the candidate's directional slope >= 0.015 ATR/bar.
5. MAY C88-03 — HAR volatility forecast: M15 squared returns -> H1 realized variance;
   forecast next 4h from 1/6/24h lagged variance averages. Sizing-only.
   [COMPLETION — proposal text truncated: lot multiplier = min(1, median/F) with
   F = forecast variance, floored at 0.5.]
6. JUN C89-21 — Rogers-Satchell OHLC volatility over latest 24 H1 bars. If current
   loss >= 0.25 x entry H1 ATR and short-term adverse movement exceeds its trailing
   90th-percentile threshold, one-time 50% partial exit. Target: the 7.78 cost/loss
   ratio (two -102.5 audit losses).
7. JUL C78-34 — Bayesian change-point (lightweight online implementation, hazard
   1/50, documented as a simplification): partial exit 50% only when P(change within
   last 4 H1 bars) >= 0.60 AND position losing AND original H1 direction unsupported.
   Target: the 7.50 cost/loss ratio.
8. AUG C67-04 — Ledoit-Wolf covariance sizing overlay (as Nov test 1), entries frozen.
9. SEP C91-15 — Two-state Gaussian HMM on standardized H1 returns + log high-low
   ranges (fit on discovery, filter forward). Ranking bonus for an eligible candidate
   when the filtered probability of its state >= 0.70 for two consecutive H1 closes.
10. OCT C92-24 — Variance-ratio routing: on otherwise EMPTY checks only, admit an
    existing eligible continuation candidate when [COMPLETION — threshold truncated
    in the proposal: VR(2,8) on H1 closes > 1.0, i.e. trending], directional H1
    momentum positive in candidate direction, M15 directional CLV >= 0.60. The
    candidate never displaces a proven primary. Target: frequency above 2.09/day.
11. JAN C60-03 — Distributionally robust growth sizing: entries frozen; lot
    multipliers 0.25/0.50/0.75/1.00; choose the multiplier maximizing the WORST
    training-year mean log growth subject to peak margin and DD limits.
12. DEC C94-23 — Model Confidence Set (as Mar): incumbent vs fixed challengers with
    saved ledgers (C104 R20, C115 PB23, PB21, up to 4), 80% MCS, 1,000 draws, 5-day
    blocks. Incumbent otherwise unchanged.

DELIVERABLES: ~/workspace/fx/work_ovl/results/<month>.md per month as each finishes
(overlay ON vs OFF table + POSSIBLE/NOT verdict + one-line reason), then
~/workspace/fx/work_ovl/results/SUMMARY.md with all 12 verdicts. Write incrementally —
do not hold everything for the end.
