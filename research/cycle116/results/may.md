# Cycle 116 — May (C88-03) — HAR volatility-forecast sizing overlay

Method as specified: M15 squared returns aggregated to H1 realized variance; HAR forecast of the next 4h from lagged 1/6/24h variance averages. Sizing-only. **COMPLETION (flagged): the proposal's lot multiplier was truncated in the user's paste; implemented as multiplier = min(1, trailing-median(F)/F), floored at 0.5**, F = forecast variance. May's ceiling result makes this a sizing experiment only — no promotion gate is attempted. Paths: house policy_path (start $1,000, N=66).

## Sizing paths

| Path | Trades lot-scaled | Final $ (start $1,000) | Peak margin % | Max DD % | Margin call |
|---|---|---|---|---|---|
| disc OFF | — | $301,018 | 46.69% | 0.13% | False |
| disc ON (HAR) | 218 | $91,290 | 44.02% | 0.30% | False |
| audit OFF | — | $1,732 | 44.83% | 11.71% | False |
| audit ON (HAR) | 27 | $1,649 | 41.13% | 10.68% | False |

Audit log growth: OFF 0.549 -> ON 0.500.

## Verdict: NOT

One-line reason: audit max DD 11.71% -> 10.68%, peak margin 44.83% -> 41.13%, log growth 0.549 -> 0.500; no material DD improvement, or growth is given back to buy it.
