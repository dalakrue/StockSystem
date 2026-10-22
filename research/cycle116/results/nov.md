# Cycle 116 — November (C93-24) — Ledoit–Wolf covariance + tail-risk lot control

Method as specified: Ledoit–Wolf shrinkage covariance of synchronized H1 returns (trailing 60d) across the pairs the system trades; halve the lot when a proposed position's marginal portfolio-vol uplift exceeds 1.10× the trailing median uplift. Second overlay: halve the lot when the February-style adverse-tail forecast is elevated (> 0.35 × entry H1 ATR). Sizing-only: pip statistics are unchanged by construction; the target stat is the 23.31% sizing drawdown. Paths use the house policy_path (start $1,000, N=83, realized-balance equity).

## Sizing paths

| Path | Trades lot-scaled | Final $ (start $1,000) | Peak margin % | Max DD % | Margin call |
|---|---|---|---|---|---|
| disc OFF | — | $436,267 | 48.19% | 23.23% | False |
| disc ON (LW) | 194 | $136,554 | 36.13% | 21.64% | False |
| disc ON (tail) | 459 | $24,009 | 24.07% | 11.64% | False |
| disc ON (LW+tail) | 460 | $22,236 | 24.03% | 11.64% | False |
| audit OFF | — | $1,406 | 35.70% | 14.36% | False |
| audit ON (LW) | 23 | $1,303 | 35.70% | 11.25% | False |
| audit ON (tail) | 52 | $1,198 | 17.96% | 7.55% | False |
| audit ON (LW+tail) | 52 | $1,198 | 17.96% | 7.55% | False |

Lot-scaling triggers — discovery: LW 194, tail 459; audit: LW 23, tail 52.

**Screening caveats (read before acting):** (1) The OFF path here is the house
realized-balance path (audit max DD 14.36%); the published 23.31% target figure
came from the producing round's marked-equity machinery — the ON/OFF comparison
above is same-method, the level differs. (2) The tail overlay as specified is
barely selective: the 95th-percentile adverse 1h move exceeds 0.35 × entry ATR
for almost every entry, so it halves 52 of 52 audit lots (459 of 460 discovery)
— most of its DD improvement is the arithmetic of half size, bought with a large
final-$ give-back on the discovery path ($436,267 -> $24,009). The LW covariance
overlay is the selective one (23 of 52 audit lots): audit DD 14.36% -> 11.25%,
peak margin unchanged 35.70%, final $1,406 -> $1,303.

## Verdict: POSSIBLE

One-line reason: best overlay (ON (tail)) moves audit max DD 14.36% -> 7.55% and peak margin 35.70% -> 17.96% (final $ 1,406 -> 1,198); drawdown improves at no pip-stat cost.
