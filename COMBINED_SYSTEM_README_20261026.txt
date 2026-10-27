COMBINED SYSTEM — BEST + SECOND BEST, AND BEST N DIVIDED BY 3
StockSystem app package, updated 2026-10-26 (BRIEF21 + BRIEF23
integration build)
==============================================================

WHAT CHANGED (plain language)
-----------------------------
1) Combined Best + Second-Best rule: at each check time, the
   month's BEST cycle runs FIRST. If the Best cycle has an entry
   at that check, you see it, labelled "BEST". ONLY when the Best
   cycle has NO entry at that check does the Second-Best cycle
   run; its entry is labelled "SECOND BEST". If neither has an
   entry, there is no trade at that check.

2) Four months got their validated improved systems as the new
   BEST (each one copied into the app EXACTLY — the app replay
   reproduces the research record trade-for-trade):
   - January:  Cycle 60B (BRIEF23 C20_STACK improved)
   - April:    Cycle 87B (BRIEF21 C20a improved)
   - November: Cycle 93B (BRIEF21 C20a improved)
   - December: Cycle 94B (BRIEF21 C20a improved)
   In those four months the OLD system is now the Second
   priority: it runs only when the improved Best is silent at
   a check. September's combined pair (Cycle 91 + Cycle 287)
   is unchanged.

3) Position sizing: Best N is divided by 3 for every month
   (the sizing you chose from the 25 Oct simulation). The app
   shows Best N with 2 decimals, e.g. May shows 22.00.

4) Check-time freshness fix: signals now appear at the exact
   check time; if the saved data is missing the check candle,
   the app downloads fresh data at once instead of waiting.

WHERE YOU SEE IT IN THE APP
---------------------------
- The "Signal system" list has new choices at the end:
  "January COMBINED", "April COMBINED", "November COMBINED",
  the standalone improved panels "January (BRIEF23 C20_STACK
  Improved)", "April (BRIEF21 C20a Improved)", "November
  (BRIEF21 C20a Improved)" and "December (BRIEF21 C20a
  Improved)", alongside the earlier "September COMBINED" and
  "December COMBINED". Open a COMBINED panel to use the
  combined rule for that month. The pick is labelled BEST
  (green) or SECOND BEST (orange), with a "Source" column.
- A short text at the top of the signals area explains the
  rule on every panel.
- All the old panels are still there, unchanged, and every old
  system is still selectable on its own. In January, April,
  November and December the app now opens on the improved
  Best system (that is the promotion you ordered); the old
  system for those months is one click away in the list.

BEST N TABLE (full N -> N divided by 3, now active)
---------------------------------------------------
  January    Cycle 60B (C20_STACK)  83  -> 27.67
  February   Cycle 85  (C85-23)    104  -> 34.67
  March      Cycle 86  (C86-24)     86  -> 28.67
  April      Cycle 87B (C20a)      104  -> 34.67
  May        Cycle 88  (C88-03)     66  -> 22.00
  June       Cycle 89  (C89-21)     84  -> 28.00
  July       Cycle 78  (C78-34)    103  -> 34.33
  August     Cycle 67  (C67-04)    121  -> 40.33
  September  Cycle 91  (C91-15)     83  -> 27.67
  October    Cycle 92  (C92-24)     83  -> 27.67
  November   Cycle 93B (C20a)       83  -> 27.67
  December   Cycle 94B (C20a)      105  -> 35.00

  (January's improved system uses the old Cycle 60 Best N —
  no separate Best N was recorded for it in the research.)
  The lot formula is unchanged: lot grows by 0.01 for every
  N dollars of realized profit — with N now one third of
  before, lots grow three times faster. That is exactly the
  divided-by-3 setting from your simulation.

PRIORITY ORDER, MONTH BY MONTH (combined panels)
------------------------------------------------
  January    1st Cycle 60B (BRIEF23 C20_STACK IMPROVED)
             2nd Cycle 60 (C60-03, old system) — only when
             1st is silent at the check
  April      1st Cycle 87B (BRIEF21 C20a IMPROVED)
             2nd Cycle 87 (C87-24, old system) — only when
             1st is silent
  September  1st Cycle 91 (C91-15)
             2nd Cycle 287 (C287) — only when 1st is silent
  November   1st Cycle 93B (BRIEF21 C20a IMPROVED)
             2nd Cycle 93 (C93-24, old system) — only when
             1st is silent
  December   1st Cycle 94B (BRIEF21 C20a IMPROVED)
             2nd Cycle 94 (C94-23, old system) — only when
             1st is silent. Cycle 274 stays in the app as a
             selectable standalone system, but it is no
             longer December's combined second priority
             (your order, 2026-10-26).

  The other months run Best-only in the combined sense: their
  recorded second bests are research-only and could not be
  copied into the app exactly:
  February   Second best H485 — proven not reproducible in
             the app exactly. Not approximated.
  July       Second best C407 — its record comes from a
             different walk than the app's July system.
             Not approximated.
  Mar, May, Jun, Aug, Oct — their recorded second bests are
             research candidates that never passed the full
             judging; they were never integrated.

THE IMPROVED SYSTEMS (validated research, now in the app)
---------------------------------------------------------
Full records are inside this package in the folder
research/combined_20261026/ and in
FIX_NOTES_20261026_BRIEF21_APP_INTEGRATION.md.

  - November C20a (BRIEF21): C93-24 + a volatility-shock
    veto + a re-entry partner that continues after winning
    trades close. Research: discovery n436 net +5128.59
    leftover 69.12; audit n100 net +678.37 leftover 46.39.
    App replay: EXACT (536 picks, trade-for-trade).
  - December C20a (BRIEF21): same construction on C94-23.
    Discovery n650 net +4479.75 leftover 66.20; audit n157
    net +1135.57 leftover 75.39. App replay: EXACT (807 picks).
  - April C20a (BRIEF21): C87-24 + a score-gated second pick
    + the re-entry partner. Discovery n710 net +6033.02
    leftover 84.47; audit n187 net +1971.36 leftover 79.06.
    App replay: EXACT (897 picks).
  - January C20_STACK (BRIEF23): C60-03 + an FB breadth veto
    + tighter FB stops + a stall cut + a score-gated second
    pick. Discovery n355 net +1984.54 win 95.21% leftover
    64.23; audit n101 net +550.18 leftover 67.50. App replay:
    EXACT (456 picks; one stop-loss value on one 2024 trade
    differs because the old research data had a missing
    candle that has since been fixed in the database — the
    trade itself, its entry, target, exit and profit are
    identical; see the FIX_NOTES for the proof).

  The re-entry partner needs the app to remember closed
  trades. That memory now exists: a walk ledger saved in the
  app's data folder (data/walk_ledgers/). November and
  December also need a long M15 history WITH volume for
  their veto (at least 387 M15 bars per symbol). If that
  history is not available at a check, the improved system
  shows NO entry for that check and says why — it never
  silently trades a different, un-vetoed pick.

WHAT DID NOT CHANGE
-------------------
- The 12 original Best systems and their equations: untouched
  (still selectable; four of them are now Second priority in
  their month's combined panel).
- October's dual-pick inside Cycle 92: untouched.
- Your live signal messages (the cron signals): untouched.
  They do not use the part of the code that changed.
- Nothing was uploaded to GitHub. This ZIP is yours to upload.

Full technical detail: FIX_NOTES_20261026_BRIEF21_APP_INTEGRATION.md
FIX_NOTES_20261026_COMBINED_NDIV3.md
FIX_NOTES_20261025_WAIVER_INTEGRATION.md
FIX_NOTES_20261026_BRIEF21_INTEGRATION.md
ROUND_CLOSE_BRIEF21.md
SECOND_BEST_ALL12.md
VALIDATION23_JAN.md
VALIDATION22_APR2B.md
VALIDATION22_DEC2B.md
VALIDATION22_FEB.md
VALIDATION22_JAN.md
VALIDATION22_MAR.md
VALIDATION22_MAY.md
VALIDATION22_NOV2B.md
