# Advanced Middle Regime Migration 2026-09-26

Integrated additive upgrade:
- H4 trend confirmation layer
- ADX regime quality filter
- currency strength compatibility fields
- entry score fields
- ATR TP/SL framework
- ATR trailing + bias reversal exit framework
- meta quality probability fields

New output columns:
Symbol, Direction, Entry Time, Entry Score, Currency Strength,
ADX, ATR, Suggested TP, Suggested SL, Risk Reward, Exit Method,
Quality Probability.

Existing S1-S110 and finder architecture remain untouched.
The new layer is imported as an enrichment stage.
