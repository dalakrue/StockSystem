System 2 Upgrade Patch

- S1-S20 logic preserved.
- Adds additive S21-S30 opportunity layer.
- Adds dynamic TP/SL proposal columns:
Symbol, Strategy, Direction, Probability Score, Suggested TP, Suggested SL, RR, Confidence.
- Finder integration uses the shared core.strategy_audit_20260924 S1-S110 engine directly.
- Backtesting engine must compare fixed TP40/SL20 against dynamic results using unseen data.
