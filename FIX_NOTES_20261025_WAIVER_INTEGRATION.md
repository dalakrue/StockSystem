# Fix notes — Waiver integration (2026-10-25): September + December SECOND-BEST systems integrated; February + July NOT integrated (blocked, with proof)

User order 2026-10-25 ~17:42 MMT: "I can ignore chain and DSR
test, continue" — the chain floor and DSR are waived as promotion
blockers for the four candidates that passed every other term of
the standing middle battery (audit judging, corrected LCT
confidence, EC22 counts, priorities 13-16, red lines):
Feb H485_veto, Dec BRIEF18 C274 stack, Jul BRIEF18 C407 stack,
Sep BRIEF18 C287 stack. Follow-up order ~18:03 MMT: the four are
labelled in the app as that month's SECOND-BEST system (incumbents
stay best/default). Research snapshot archived to the repo BEFORE
these commits: research/waiver_20261025/ (WAIVER_ORDER.md is the
record of the order, the definitions and the outcomes).

INTEGRATED: December (cycle274) and September (cycle287) — both
replay-verified EXACT through the app code path (below).
NOT INTEGRATED: February (H485_veto) and July (C407 stack) —
each is impossible to reproduce exactly in the app; the proof is
recorded below and in the archive. Nothing was approximated.
The 12 incumbents, MONTH_SYSTEMS defaults, all panels' month
default and the live signal crons are untouched.

## 1. December — cycle274 (C274 stack), SECOND-BEST system

Definition: the standing C94-23 walk verbatim (C71-04 engine +
FB-pick gate, core/cycle94_best UNCHANGED), keeping an evaluated
row only where the BRIEF18 Block A depth-10 confirmation stack
passes. Stack (research condition indices [96, 1, 3, 7, 13, 18,
31, 56, 15, 25]): H1 three-down pattern aligned counter-trend
BUY; RSI14 reversal (d*(rsi14-50) <= 0); RSI14 reversal deep
(d*(rsi14-50) <= -4.622879974335688); Stoch reversal (<= 0);
CCI20 reversal (<= 0); Williams %R continuation (d*(willr14-0.5)
>= 0); DI-diff reversal (<= 0); session position pos-0.5;
CCI20 reversal deep (d*cci20 <= -0.5537250461819219); MACD-h
reversal (<= 0). Features are computed generation-exact (the
work_c196 step1 recipe: causal M15 slice ending at entry,
Wilder EWM alpha 1/14, 1600-bar window) inside
core/cycle274_best.py. December quirk PRESERVED: FB rows are
direction-stamped 'TREND' in the research pools, i.e. d = -1 for
every FB row in every stack direction term — the port keeps
exactly that (it is also how the incumbent's FB gate CLV
behaves). Selection = cycle94's own selection over the filtered
signals, so the walk semantics are the research walk's.

Verification (app code path replayed over the research era
frames, occupancy evolved from the walk's own picks):
- Control (cycle94 vs recorded C94-23 ledger): 634/634 picks,
  keys exact; TP max diff 3.6e-15, SL 1.4e-14, entry 0.0.
- Candidate (cycle274 vs recorded C274 ledger): 36/36 picks,
  keys exact; TP max diff 3.55e-15, SL 0.0, entry 0.0;
  directions re-checked individually 0/36 diffs.
- Segment stats from the app picks (cost 2.5): DISC n31
  net +414.18 leftover 100.00; AUDIT (2024+2025) n5 net +94.39
  leftover 100.00 — exact targets.

Live-window note: research features use the full 1600-bar
causal window; the live panel's M15 frames carry fewer bars.
The Wilder/EMA-seeded indicators converge to the same values
well inside the available window; the pattern, session and
rolling features are exact on any sufficient window. This is
the same class of live/research window difference the standing
M15-dependent systems already carry.

## 2. September — cycle287 (C287 stack), SECOND-BEST system

Definition: the standing C91-15 walk verbatim (C59-18 engine
minus 3 hour-1 FB legs + X30B overlay, all inside
core/cycle91_best UNCHANGED), keeping an evaluated row only
where the BRIEF18 depth-3 stack passes (indices [73, 81, 1]):
M15 hammer aligned BUY (d = +1), M15 pin-bar aligned BUY
(d = +1), RSI14 reversal (d*(rsi14-50) <= 0), with d from the
row's resolved direction (September pools assert
direction == resolved direction for every row). Features are
shared with cycle274 (core/cycle274_best.stack_features).

Verification (same harness):
- Control (cycle91 vs recorded C91-15 ledger): 550/550 picks,
  keys exact; TP max diff 3.6e-15, entry 0.0; app SL equals the
  finalized log's sl_pips_used on all 550 (max diff 1.3e-12) —
  the pool-side SL column is pre-X30B-resim, the app and the
  finalized log agree.
- Candidate (cycle287 vs recorded C287 ledger): 14/14 picks,
  keys exact; TP max diff 1.8e-15, entry 0.0; app SL equals
  the finalized log on all 14 (max diff 1.0e-12).
- Segment stats (cost 2.5): DISC n12 net +90.34 leftover
  100.00; AUDIT n2 net +15.00 leftover 100.00 — exact targets.
  September's evidence is the thinnest of the four (12 + 2
  trades); the panel label and router description say so.

## 3. February — H485_veto: NOT INTEGRATED (blocked, with proof)

H485's recorded ledger is a SUBSET of the control walk: the
plain C85-23 walk's 482 picks minus its EURUSD rows = 313
picks, row-for-row identical (verified: keys, gross, exit_time;
the N082 split-exit transform touches exactly 16 picked rows,
all EURUSD — FB_EURUSD_h11_0 / FB_EURUSD_h16_1 — so the veto
removes every N082-modified row and no N082 machinery is
needed for this comparison).

The subset definition embeds the CONTROL walk's occupancy:
vetoed EURUSD trades still hold EURUSD inside that walk, so at
14 checks the control walk fell through to non-EURUSD picks
that exist only because a vetoed trade was occupying EURUSD
(10 of them FB_GBPUSD_h11_1 at 11:30; first divergence at pick
69: recorded FB_GBPUSD_h11_1 @ 2018-02-05 11:30, where the
app-semantics walk's selection is the EURUSD leg itself,
vetoed to empty). An app panel can only apply the veto at
selection under the system's own occupancy (the live-faithful
semantics); replaying exactly that through the app code path
yields 300 picks, not 313, and different segment statistics.
Reproducing the recorded walk would require phantom-occupancy
state — the panel tracking positions the user never took —
which the stateless panels do not have. Per the integration
brief (stop, report, do not approximate), February was NOT
integrated. A veto-at-selection module was built and measured
(the 300-pick walk) and is retained in the research work
records only; it is not in the app tree. February's second-best
designation stands in the research record (archive
WAIVER_ORDER.md). The February control replay itself is exact
(cycle85: 482/482 picks, keys exact, TP/SL/entry diffs ~1e-14).

## 4. July — C407 stack: NOT INTEGRATED (blocked, with proof)

The C407 candidate's pick sequence is defined by the C101
tiered jul_walk (first non-FB eligible, else first eligible)
over the C101/N082 candidate pools, whose scoring/order differ
from the app's July walk: 13 of the candidate's 42 recorded
trades are not picks of the app's C78-34 walk at their checks
(the 29 shared rows agree exactly on gross and exit — the
blocker is pick identity, not exits). Reproducing it would
mean integrating a different walk and pool set as a separate
system, which the recorded battery candidate is not. NOT
integrated; recorded in the archive in full.

## 5. Changes in this push

- core/cycle274_best.py (NEW) — December second-best system.
- core/cycle287_best.py (NEW) — September second-best system.
- core/signal_mode.py — registers cycle274/cycle287 as
  selectable systems (SYSTEM_CYCLE274/287, MONTH_SECOND_BEST
  {9: cycle287, 12: cycle274}, Best N 83/105 = the incumbents'
  values, set/describe/evaluate/select/check-hours branches).
  MONTH_SYSTEMS is byte-identical to before (asserted in the
  smoke test); the 12 incumbent branches are unmodified.
- ui/field3_multisymbol_regime_summary_20260722.py — two new
  panels cloned from the September/December incumbent panels
  (own session-state keys, own download buttons), registered
  in _SIGNAL_PANELS with SECOND-BEST labels, and APPENDED to
  _MONTH_PANEL_ORDER (the list is month-indexed by position
  for the reminders; the original 12 entries keep their
  positions and remain the defaults).
- This file.

## 6. Untouched, verified

- Incumbent core modules (cycle60/67/78/85/86/87/88/89/91/92/
  93/94_best.py and their frozen engines): not edited (file
  timestamps predate this job; the control replays above
  reproduce the recorded incumbent ledgers exactly through
  the current tree).
- Router smoke test on the final tree: all 14 systems
  set/describe/Best-N/check-hours OK; MONTH_SYSTEMS ==
  the 12 incumbents; cycle485 and cycle407 are rejected as
  unknown systems.
- Router end-to-end: evaluate+select through signal_mode for
  cycle274 and cycle287 at recorded candidate checks returns
  the recorded picks.
- Live signal crons: unchanged — they call the C92-24 adapter
  (live_trader/signals92.py), which does not reference the
  new systems; the October dual-pick remains app-side only.
