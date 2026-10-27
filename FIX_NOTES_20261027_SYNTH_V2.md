# Fix notes — 2026-10-27 — forming-candle synthesis v2

## Problem
At the exact check minute, Twelve Data's H1 series publishes the new hour's
candle minutes after the bar boundary (verified live 2026-10-26: the 17:00 UTC
bar existed by 17:09 UTC, but the app's live refresh at 17:00–17:03 got 0/20).
The 21:30 and 23:30 checks on 2026-10-26 and the 00:30 check on 2026-10-27 all
showed "Price data incomplete — 0/20 symbols had the needed candles".

## Fix v1 (c01c9e1) and why it failed live
`_fetch_c22_frames` learned to synthesize the missing entry candle from the
entry hour's M15 bars (open = first M15 open, which equals the H1 entry open,
so entry prices stay backtest-exact; high/low/close from the partial hour).
v1 fetched M15 through the orchestrator provider chain. In production that
chain raised "ValueError: The truth value of a DataFrame is ambiguous" for
every symbol (live read 2026-10-26 23:51–00:03) and returned empty silently
at the 00:30 check. The chain is unreliable for M15 in production.

## Fix v2 (this build)
The synthesis block no longer uses the provider chain. It fetches M15 through
the same direct call the sidebar loaders use to load 20/20 daily:
`TwelveDataKeyPool.from_state(state).reserve_key(symbol, "M15")` plus
`core.connectors.data_parts.fetchers.fetch_twelve(symbol, key,
interval="15min", bars=120)`, with `mark_success` / `mark_failure` on the
lease. The normalize / slice / aggregate / append steps are unchanged from v1.
No evaluator, equation, or sizing code changed.

## Verification
The original v2 passed a seeded-repo repro (an AUDCAD H1 frame ending 16:00
plus M15 bars to 17:00 produced the appended 17:00 row with Open equal to the
M15 17:00 open, 0.8001, and an empty synthesis-error list). That tree was
lost in a VM restart before the GitHub push could land (the push itself is
blocked on a GitHub approval tap), so this build re-applies the identical
change on top of c04e80f for delivery as a ZIP: the re-applied block lands on
the exact same anchor lines as the original (3284 / 3288 / 3289 / 3298),
`py_compile` passes, and the key-pool / fetch_twelve imports and signatures
were verified live in this tree.

## Proof standard
A retro-evaluation can succeed through the normal H1 path once Twelve has
published the bar. The synthesis itself is only proven at a live check
minute, when the H1 bar is still unpublished but the M15 bars exist.
