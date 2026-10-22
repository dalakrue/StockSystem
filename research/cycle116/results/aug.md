# Cycle 116 — August (C67-04) — Ledoit–Wolf covariance sizing overlay

Method as specified: entries frozen; Ledoit–Wolf shrinkage covariance of synchronized H1 returns (trailing 60d); halve the lot when a proposed position's marginal portfolio-vol uplift exceeds 1.10× the trailing median uplift. Account-level concentration check only — the standing system is untouched. Paths use the house policy_path (start $1,000, N=121).

## Sizing paths

| Path | Trades lot-scaled | Final $ (start $1,000) | Peak margin % | Max DD % | Margin call |
|---|---|---|---|---|---|
| disc OFF | — | $106,288 | 45.94% | 0.19% | False |
| disc ON (LW) | 199 | $48,510 | 32.77% | 0.34% | False |
| audit OFF | — | $1,294 | 37.07% | 4.80% | False |
| audit ON (LW) | 14 | $1,250 | 23.59% | 4.97% | False |

Lot-scaling triggers — discovery: 199, audit: 14.

## Verdict: NOT

One-line reason: audit max DD 4.80% -> 4.97%, peak margin 37.07% -> 23.59% (final $ 1,294 -> 1,250); the standing path is already so flat that covariance lot control changes nothing material.
