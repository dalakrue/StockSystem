# Middle Standard hourly-capped risk filter

The Middle Standard Regime Ranking now exposes the exact hybrid execution
columns requested:

- `Risk_Score = (Regime Maturity Score × Avg Regime Candle Count Before Regime Change) ÷ Candle After Regime Start`
- `Is_Potential_Block` — `True` when `Risk_Score >= 1.0`
- `Hourly_Block_Count` — actual blocks issued so far in that calendar hour
- `Final_Action` — `BLOCK` for the first four potential blocks in an hour, then `ALLOW`; scores below 1.0 are always `ALLOW`
- `Hour` — the hour bucket used for the rolling quota

The counter resets automatically for each new hour. Rows are evaluated in
chronological order with stable input order as the tie-breaker, then returned
in the existing youngest-candle-first ranking order. The previous weighted
risk columns remain available as diagnostics, while `Final_Action` is the
authoritative capped execution gate and forces `RAS Decision = DISALLOW` only
for rows that are actually blocked.
