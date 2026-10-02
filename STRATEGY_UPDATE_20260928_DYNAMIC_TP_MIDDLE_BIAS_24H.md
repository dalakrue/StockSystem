# Strategy Update — Dynamic TP + Middle Bias Exit (28 Sep 2026)

This package changes only the strategy / entry-selection / exit-decision layer requested for the Middle Finder app. No backtest engine, optimizer, report generator, or historical-performance calculation was added or changed as part of this upgrade.

## Main scenario

**Dynamic TP + Middle Bias Exit** is now the explicit primary strategy scenario.

- Middle Regime Bias is the single direction owner for the published strategy signal and Dynamic TP/SL target direction.
- Target selection uses completed historical 24-hour range, directional MFE, volatility, trend strength, directional efficiency, momentum and breakout-room evidence.
- The Dynamic TP is explicitly capped by the estimated movement available inside the 24-hour horizon; the displayed horizon is therefore a real constraint rather than a label.
- Suggested TP and SL are exposed in pips and price, together with target horizon and a 24-hour target-confidence field.
- `24H Estimated Net Pip Potential` and `24H ROMAD Proxy` are exposed and included in candidate-selection scoring to emphasize return potential while penalizing noisy / structurally expensive risk.

## Exit rule

The strategy exit order is deterministic:

1. At 24 hours or later: **EXIT — 24H TIME CAP**.
2. Before 24 hours, when current Middle Regime Bias no longer matches the position direction: **EXIT — MIDDLE BIAS LOST / REVERSED**.
3. Otherwise: **HOLD_TO_DYNAMIC_TP — MIDDLE BIAS ALIGNED**.

`Max Hold Hours`, `Time Exit Enabled`, `Time Exit Hours`, and `Exit Scenario` are exported for downstream execution consumers.

## Entry-frequency improvement

For the ten lowest-frequency symbols identified in the supplied review, the selector now applies a quality-gated coverage floor.

A low-frequency symbol can receive additional selection priority only when it has a genuine S1–S110 strategy hit and clears strong score, near-entry, risk-quality and reward/risk thresholds. When its prior valid-opportunity coverage is below 50%, one high-quality replacement is permitted for a weaker selected candidate when the quality utility remains sufficiently close.

The multi-symbol Finder persistence path now concatenates all symbol histories before applying the cross-symbol selector, so each timestamp is actually ranked across the symbol universe rather than receiving an independent per-symbol #1 rank.

## Preserved behavior

- S1–S110 IDs were not expanded or renamed.
- Existing strategy-entry families were not replaced with backtest logic.
- The selector still defaults to four published hourly entry slots.
- Genuine strategy hits remain distinguishable from rank-fill rows.
