# Continuous All-Symbol H1 Export and 40% Entry-Filter Fix

## Fixed behavior

- **Fast Strategy Build is H1-only** and requests exactly two years.
- The prepared CSV contains **every calculated H1 candle row for every requested symbol**. For a 20-symbol build, each exported H1 timestamp contains exactly 20 rows.
- `Open Price`, `Highest Price`, `Lowest Price`, and `Close Price` are present on every exported candle row.
- The four selected entries remain visible through `Hourly 4 Entry`, `Hourly Selection Rank`, `Hourly Entry Origin`, and `Strategy Decision`. Unselected rows are no longer deleted from the CSV.
- The worker refuses to publish an incomplete CSV when a timestamp is missing any requested symbol. Partial builds remain resumable and do not create a misleading continuous export.
- S1-S120 shared entry-quality/admissibility filters and selector quality floors use an exact **40% relaxation**. Invalid OHLC, higher/middle direction disagreement, structure misalignment, DMI direction mismatch, and a purely one-way move with no preceding pullback are still blocked.

## Backtest use

Use the rows where `Hourly 4 Entry = True` as entries. Use the later rows for the same symbol as the uninterrupted future H1 path for TP, SL, Middle Bias exit, and the 24-hour maximum holding rule.

## Validation contract

- No duplicate `Symbol + Datetime` rows.
- All requested symbols occur at every exported H1 timestamp.
- Exactly four rows per timestamp are marked `Hourly 4 Entry = True` when at least four symbols are present.
- Continuous OHLC and all S1-S120 condition/score columns are included in the direct CSV.
