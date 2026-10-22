# Cycle 116 — January (C60-03) — Distributionally robust growth sizing

Method as specified: entries frozen; lot multipliers 0.25 / 0.50 / 0.75 / 1.00; choose the multiplier maximizing the WORST training-year (2016–2024) mean log growth subject to peak margin ≤ 60% and max DD ≤ 30% on the house policy_path (start $1,000, N=83).

## Discovery sizing paths by multiplier

| Multiplier | Final $ | Peak margin % | Max DD % | Worst-year log growth | Within limits |
|---|---|---|---|---|---|
| 1.00 | $4,209 | 51.31% | 19.88% | 0.066 | yes |
| 0.75 | $3,091 | 36.10% | 18.27% | 0.127 | yes |
| 0.50 | $2,188 | 23.62% | 15.37% | 0.162 | yes |
| 0.25 | $1,493 | 11.85% | 10.16% | 0.180 | yes |

Chosen multiplier: **0.25** (worst-year log growth 0.180 vs 0.066 at 1.00).

Audit path at chosen multiplier: final $1,102, peak margin 8.76%, max DD 2.21% (at 1.00: $1,465, 35.36%, 8.29%).

**Screening caveat:** the robust criterion buys worst-year smoothness with
total growth — discovery final $ falls from $4,209 (1.00×) to $1,493 (0.25×),
and the audit path's peak margin drops to 8.76%, far below the 40–60% sizing
band the standing system was built to. POSSIBLE means the stated criterion
improves, not that the trade is free.

## Verdict: POSSIBLE

One-line reason: multiplier 0.25 raises the worst training year's log growth from 0.066 to 0.180 within the margin/DD limits — robust sizing buys worst-year growth.
