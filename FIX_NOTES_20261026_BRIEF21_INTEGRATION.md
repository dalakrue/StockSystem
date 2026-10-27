# Fix notes — BRIEF21 integration attempt (2026-10-26): all three validated winners BLOCKED on app fidelity, with proof; incumbents untouched

BRIEF21 (user order 2026-10-26) validated three material
improvements at the locked middle standard: November C20a,
December C20a, April C20a (records:
fx/work_m15mine/brief21/VALIDATION21_NOV.md, VALIDATION21_DEC.md,
apr/VALIDATION21_APR.md). This job tried to integrate each into
this local app copy under the same standard as the 2026-10-25
waiver integration: the app code path must replay the validated
ledger EXACTLY (discovery + audit n / net / leftover). Where it
cannot, the month is left untouched and the proof recorded —
nothing is approximated in. That is what happened for February
and July in the waiver round; it happens here for all three,
for the reasons proven below. NO app code was changed by this
job (this notes file is the only addition); the router smoke
test on the untouched tree passes (12 incumbents +
cycle287/cycle274 second-bests, MONTH_SYSTEMS and
MONTH_SECOND_BEST byte-identical, all set/describe/Best-N/
check-hours branches OK). Live signal crons are untouched —
they call the C92-24 adapter, which references none of this.

## The shared blocker: C16 TP-continuation re-entry (all 3 winners)

Every BRIEF21 winner is a stack whose top layer is the C16
re-entry partner. Its legs are defined ON THE RECORDED BASE
WALK'S CLOSED-TRADE LEDGER (research build_reentry, identical
in the Nov/Dec/Apr runners): for each base trade with
exit_reason == 'TP', take the first grid check strictly after
its exit_time; if a candidate pool row for the same symbol and
direction exists at that check and the leg's full flight
interval conflicts with no base/kept trade on the symbol, the
row becomes a partner leg.

The app pattern has no input that carries this state. The
router's evaluators receive (frames, check_time_utc); its
selectors receive (signals, open_symbols) — currently-open
symbol names only. Panels call evaluators at a single check
with open_symbols=() (see the cycle274/cycle287 panels in
ui/field3_multisymbol_regime_summary_20260722.py). No module or
panel in the tree reads or tracks closed-trade exits (no
exit_reason input exists in cycle87/93/94_best.py or the
panel file). A re-entry leg therefore cannot be emitted by any
app code path: the trigger (a specific past trade exited at
TP, and this check is the first grid check after that exit)
and the conflict test (full-interval occupancy of the whole
base ledger) are functions of walk history the stateless
panels do not have. This is the February H485 class of
blocker, one level deeper: there the recorded ledger embedded
the control walk's occupancy; here the candidate's legs embed
the base walk's exit ledger.

Quantified from the validated ledgers on disk (strategy ==
'P16_reentry' rows; nets are ledger net_pips sums @2.5):

- November C20a: 76 of 436 DISC trades are re-entry legs
  (17.4%); 14 of 100 AUDIT trades. Ledger decomposition DISC:
  control 407 / +5069.85 -> vetoed base 360 / +4248.90 ->
  validated 436 / +5128.59. AUDIT: 105 / +604.60 -> 86 /
  +525.39 -> 100 / +678.37.
- December C20a: 157 of 650 DISC (24.2%); 30 of 157 AUDIT.
  DISC: control 505 / +2839.75 -> vetoed base 493 / +3030.60
  -> validated 650 / +4479.75. AUDIT: 129 / +896.87 -> 127 /
  +881.75 -> 157 / +1135.57.
- April C20a: 162 of 710 DISC (22.8%); 45 of 187 AUDIT.
  DISC: control 502 / +3889.03 -> dual-pick base 548 /
  +4465.40 -> validated 710 / +6033.02. AUDIT: 132 /
  +1102.07 -> 142 / +1277.04 -> 187 / +1971.36.

An app-side system without the re-entry layer IS the
incumbent walk (already the default in all three months) —
integrating the remainder under the winner's name would
publish a different, unvalidated system. Per the brief: STOP,
do not approximate.

## November + December, second blocker: the C06 vol_z veto

C06 drops incumbent walk rows whose pool feature vol_z
exceeds the FIT 90th percentile of incumbent picks (Nov 1.50,
Dec 1.12). vol_z is a VOLUME statistic (work_c193/scripts/
step1_generate.py feature_vector, the recipe behind the
C193/C196 pool feature tables the BRIEF21 runners read):
rolling 4-bar sums of M15 tick volume over the last 384 bars
of the causal slice (up to 1600 bars), vol_z = (last sum -
median) / IQR of those sums, on Dukascopy volume.

The app's live M15 path cannot compute it: fetch_
cycle78_m15_frames (the shared data path every M15-dependent
module uses) loads limit=200 bars from the local repository
or outputsize=200 from the provider chain — fewer bars than
the statistic's 384-point window, and provider (Twelve Data)
forex volume is not Dukascopy tick volume, so even the window
contents would differ. Unlike the cycle274 stack's price
oscillators — Wilder/EMA-seeded values that converge to the
research values well inside 200 bars, which is why that
integration was faithful — vol_z is a rank statistic over a
specific 384-point volume distribution: truncating the window
changes the median and IQR themselves, and with them which
rows are vetoed. The veto is not cosmetic: it removes 47 of
407 DISC picks in November (19 of 105 AUDIT) and 12 of 505
DISC picks in December (2 of 129 AUDIT), with walk fall-through
reshaping the rest. A veto computed on a truncated/different
volume series is a different system.

## April, secondary note: the C12 score-gated dual-pick

April has no veto — its base layer is C12 (second pick at the
same check, different symbol, eq score >= 1000 = median of the
pool's positive eq scores, concurrency cap 3 counted on the
walk's live occupancy). This layer is the closest of the three
to the panel pattern (the October dual-pick precedent puts a
second pick in the selector, gated on open_symbols). It is not
integrated either: the validated April winner is the C12+C16
STACK (C12 alone was never validated as a winner; the C16-only
stack C20b rated SMALL and is itself blocked by the re-entry
blocker above). Publishing C12 alone under a BRIEF21 label
would again be an unvalidated system wearing a validated name.

## Per-month outcome

- November (C93-24 + C06 + C16): BLOCKED — re-entry state
  (Blocker 1) and vol_z data (Blocker 2). Incumbent cycle93
  stands, untouched.
- December (C94-23 + C06 + C16): BLOCKED — same two blockers.
  Incumbent cycle94 stands; the December SECOND-BEST cycle274
  from the waiver round is unaffected and remains selectable.
  (The C20a re-entry's TREND/FB side resolution by the
  incumbent's mom24 rule is research-walk machinery; it was
  never reached, because Blocker 1 stops the design earlier.)
- April (C87-24 + C12 + C16): BLOCKED — re-entry state
  (Blocker 1). Incumbent cycle87 stands, untouched.

## What would unblock them (recorded, not done)

A stateful walk layer inside the app: panels would need to
persist the system's own pick ledger (entries, exits, exit
reasons) across checks and feed closed-trade state into the
selector — a new pattern no current module uses — plus, for
Nov/Dec, an M15 volume feed comparable to Dukascopy tick
volume at >= 387 bars depth. Until the user orders that
machinery, the three winners live as validated research
systems (ledgers + builders in fx/work_m15mine/brief21/),
available for forward paper evaluation exactly as recorded.
