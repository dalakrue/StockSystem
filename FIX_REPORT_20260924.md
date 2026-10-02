# Middle Standard S1-S110 Fix Report — 2026-09-24

## Strategy layer
- S1-S92 shared entry-quality thresholds are relaxed by exactly 30% while preserving higher/middle bias agreement, ATR stability, DMI direction agreement, and completed-candle causality.
- S93-S110 add 18 distinct Middle Standard pullback/reclaim families: EMA34, EMA100, EMA10/20 ribbon, VWAP+EMA, 48-bar midpoint, shallow/deep Fibonacci, 12-bar liquidity sweep, 30-bar level rejection, pivot reclaim, Stochastic reset, MACD zero retest, Williams %R reset, MFI reset, ADX contraction recovery, ATR envelope re-entry, two-candle EMA50 reversal, and multi-zone confluence.
- S93-S110 use a separate Middle Standard quality gate and are explicitly new-only: an S93-S110 condition is suppressed when any S1-S92 entry condition already fired on the same completed candle. This creates genuine extra-opportunity rows rather than renamed duplicates.
- All S1-S110 strategies are present in the shared engine, ranking table, Finder history/audit, and Strategy Decision output.
- Strategy Decision is driven directly by per-strategy `Entry Condition` flags. A single qualifying strategy is sufficient to publish BUY/SELL bias for the symbol.

## Twelve Data loading
- Default connector request reduced to 600 candles.
- Strategy warm-up floor is 220 candles so EMA100/48-bar/Fibonacci/oscillator structures have sufficient causal history.
- Twelve Data source requests are capped at 5,000 candles.
- H4 loading automatically requests H1 source data and resamples after fetching.
- Existing local Twelve Data cache is checked before a new quota reservation/request.

## Finder / ranking integration
- Finder history and the Middle Standard ranking table consume the same S1-S110 audit contract.
- Strategy signal/condition/reason/score columns are generated for all 110 strategies.
- Historical rows that predate S1-S110 are marked `NO DATA` rather than being silently backfilled with legacy values.

## Cleanup
- Removed the obsolete AI Assistant, OpenRouter backend, AirLLM panel, research folders/benchmarks, old router-part bundle, obsolete architecture registry, and unused legacy UI surfaces that were not part of the current Field 3 + Settings application.
- Removed the old Field-5 assistant renderer and its dangling imports.
- Removed unused Strategy Decision helper/threshold code and other no-op cleanup layers.
- Removed unused refresh imports.
- Removed AirLLM deployment requirements and OpenRouter sample secret/config/status entries.

## Validation
- `python -m compileall -q .` — PASS.
- Focused S1-S110/Finder regression: 16 PASS, 10 deselected (dependency-limited tests excluded because this execution environment does not provide Streamlit/Parquet engines).
- Dedicated S1-S20/Finder contract: 3 PASS.
- 25 multi-seed stress paths produced new-only hits for all 18 of S93-S110 (18/18 strategies); total new-only rows in that validation: 920.
- Single-condition Strategy Decision contract verified for S93, S100/S104-style cases: one qualifying entry condition produces one-sided BUY/SELL bias.

## Environment note
The repository requirements still declare `streamlit` and `pyarrow`; the current container used for validation does not have those optional runtime/test packages installed. The related tests were therefore not claimed as passed.
