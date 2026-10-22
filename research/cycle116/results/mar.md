# Cycle 116 — Mar (C86-24) — Model Confidence Set overlay

Method as specified: incumbent vs a fixed challenger set with saved ledgers, 80% MCS, 1,000 block-bootstrap draws, 5-day blocks, on per-trade returns (aggregated to daily P&L — trades are timestamped and MCS needs a common time index; zero on days a model does not trade). Range-statistic variant referenced to the current best model. The standing system is unchanged; MCS only arbitrates the challenger set.

Days in the common index: 222 (2016-03-01 to 2025-03-31).

| Model | Avg daily net pips | MCS outcome |
|---|---|---|
| C86-24 (incumbent) | +14.552 | SURVIVES |
| R22 (C98 rank 19) | +10.642 | eliminated |
| N071 (C98 rank 78) | +14.211 | SURVIVES |
| X28 (C98 rank 41) | +14.946 | SURVIVES |
| X36 (C98 rank 49) | +13.892 | SURVIVES |

Elimination steps (model, t, 80% critical value):
- eliminated R22 (C98 rank 19): t 2.12 > crit 1.41
- stop: max t 0.96 <= crit 1.18 — no further elimination

**MCS survivor set: C86-24 (incumbent), N071 (C98 rank 78), X28 (C98 rank 41), X36 (C98 rank 49)**

## Verdict: NOT

One-line reason: survivor set = C86-24 (incumbent), N071 (C98 rank 78), X28 (C98 rank 41), X36 (C98 rank 49). No surviving challenger can be promoted under the standing rules: R22 (the only challenger with a leftover gain, 80.30%) carries LCT P 6.11% from Cycle 98 — the MCS arbitrates the set but cannot repair March's documented selection problem (PBO HIGH), and no challenger meets the leftover + win + frequency + LCT gates together.
