# Cycle 116 — Dec (C94-23) — Model Confidence Set overlay

Method as specified: incumbent vs a fixed challenger set with saved ledgers, 80% MCS, 1,000 block-bootstrap draws, 5-day blocks, on per-trade returns (aggregated to daily P&L — trades are timestamped and MCS needs a common time index; zero on days a model does not trade). Range-statistic variant referenced to the current best model. The standing system is unchanged; MCS only arbitrates the challenger set.

Days in the common index: 213 (2016-12-01 to 2025-12-31).

| Model | Avg daily net pips | MCS outcome |
|---|---|---|
| C94-23 (incumbent) | +17.543 | SURVIVES |
| R20 (C104) | +12.722 | eliminated |
| PB23 (C115) | +17.593 | SURVIVES |
| PB21 (C115) | +17.786 | SURVIVES |

Elimination steps (model, t, 80% critical value):
- eliminated R20 (C104): t 3.00 > crit 1.40
- stop: max t 0.48 <= crit 1.12 — no further elimination

**MCS survivor set: C94-23 (incumbent), PB23 (C115), PB21 (C115)**

## Verdict: NOT

One-line reason: survivor set = C94-23 (incumbent), PB23 (C115), PB21 (C115). No surviving challenger can be promoted under the standing rules: R20's LCT P was 2.12% (Cycle 104), PB23's 77.39% and PB21's 60.06% (Cycle 115) — all below the LCT-middle bar (P ≥ 80%), so the MCS changes no decision for December; C94-23 stands.
