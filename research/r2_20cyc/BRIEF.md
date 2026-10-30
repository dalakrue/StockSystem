# BRIEF — 20-Cycle Round R2 (user order 2026-10-30 ~00:52 MMT, this chat)

Supersedes the Nov–May-only scope of the 2026-10-27/28/29 issues of this
order. Where this brief and an older brief disagree, this brief wins.

## 0. Scope as ordered (readback — locked)

- ALL 12 months. 20 cycles per month per plan. Double cycle process:
  TWO scenarios (see §5).
- Goal: a 12-month best-cycle system whose every month passes the
  EnoughConfidence overall test at MIDDLE level (good enough, NOT high
  quality), so the system can go to demo → small live confidently.
- Position sizing is NOT a gate in this round: the user has decided
  Best N ÷3. Step readiness is judged on the CHAINED-account ÷3
  simulation (annual stop-out 3.47% combined / 2.04% best-alone,
  touch-30% 4.08% / 2.57%, both under his 5% line — user ruling
  2026-10-29). The standalone-month peak-margin-vs-60% line is a
  fresh-start WARNING only; never block a promotion on it.
- The only real problem to fix is EDGE confidence: the 3 EC-failing
  months from the 2026-10-29 step test (work_29load/
  ENOUGHCONFIDENCE_STEP_20261029.md, app 6f2b4ca0):
  Jan DSR 0.8630 < 0.90 · Feb MC DD arm 228.72 vs cap 219.48 AND
  DSR 0.1819 · Jul MC DD arm 233.91 vs cap 215.72.
  SMALL-LIVE-READY today = 0/12 on the old convention; on the user's
  ÷3 chained ruling the other 9 pass edge+sizing (May carries its
  LCT-waiver asterisk). This round must move Jan/Feb/Jul to EC pass
  WITHOUT breaking the other 9.

## 1. Incumbents (read FRESH from the app registry every run — never hardcode)

Registry: core/signal_mode.py MONTH_SYSTEMS in the app tree.
Record at brief time (push 01bfcb5b): Jan 60b+60 · Feb 85b (no second)
· Mar 86c+86s · Apr 87c+87s · May 88n (+88 contained) · Jun 89p (+89
contained) · Jul 78 (no second) · Aug 67+67p · Sep 91p+91s ·
Oct 92+92e · Nov 93r+93s · Dec 94c+94s.
Second-best audit (2026-10-29): gaps = Feb, May (Jun borderline at
exactly 3.000 epd, second contained). Feb/Jul have NO second-best.

## 2. Locked gates — fixed BEFORE the run, never moved after results

Promotion of a new BEST (per month), all required:
- LCT-middle: paired P ≥ 80% AND own 5th-pct leftover ≥ 20%.
- Unseen (AUDIT) leftover strictly > incumbent, OR the small-
  improvement rule (2026-10-22): leftover not below incumbent (tie
  counts) with the strongest LCT first among qualifying candidates.
- Win rate > 80% · entries/day ≥ 2 · AUDIT net positive.
- RED LINES (never waivable): never promote an unseen-losing or
  discovery-collapsed system.

EnoughConfidence-middle overall pass (per month, for the step):
- Primary 12 counts as a SCORE (Feb 9/12 promotion precedent);
  priority conditions 13–16 mandatory; PBO not-HIGH ≤ 50%;
  DSR ≥ 0.90; Monte Carlo middle PASS on ALL arms incl. DD arm and
  loss-cluster arms; decay not FAIL.
- Middle overfit is ALLOWED if the middle robustness battery passes
  (user order). High quality is NOT required anywhere in this round.

Second-best acceptance (per month), all required:
- Standalone entries/day > 2.5 (user order, this round) and medium
  quality is enough — the full best-promotion bar does NOT apply.
- Fires ONLY inside the best's check times + at most ONE new
  off-hours check time (§4). Second priority: it is used only when
  the best is silent at that check, for symbols the best cannot
  detect, or at its one new check time.
- COMBINED delta > 0 measured (combined picks strictly more than
  best-alone picks) AND combine-safety: combined MC + EC not worse
  than best-alone beyond the −2.00 AUDIT-leftover tolerance.
- A second-best is CREATED only where the best's entries/day < 3
  (standing rule) — Feb 2.391 and May 2.062 are the ordered gaps;
  Jul 2.828 also qualifies if Plan B capacity allows.

Check-time change acceptance (office replacement + Scenario 2):
- Class rule from the 2026-10-29 added-check calculation:
  IMPROVE = AUDIT leftover up AND discovery leftover not down.
  DOWNGRADE = AUDIT leftover down > 0.5 pt, OR win < 80%, OR AUDIT
  net down worse than −max(25 pips, 10% of current AUDIT net).
  ACCEPTABLE = everything else. Only IMPROVE or ACCEPTABLE may be
  adopted, and only when the user asked for that month's change.

## 3. Creative space — ordered, use it fully

- Multi-combinations NOT tried before: 3–4 indicators × 3–4
  thresholds combined in one equation; more confirmation layers.
- Half the Plan A cycles improve the best directly; half build
  combinable partners.
- Volume columns in combinations (H1 volume + M15 volume, more
  variants than before).
- Correlated-symbol combinations (cross-symbol confirmation legs).
- USD Dollar Index (Twelve Data DXY) as a feature INSTEAD of
  Dukascopy DOLLARIDX — see §6 data gate.
- 28-symbol coverage: extend best systems from the 20-symbol base
  to all 28 (NEW8: CADCHF, CADJPY, GBPAUD, GBPCAD, GBPCHF, GBPNZD,
  NZDCHF, NZDJPY) where a candidate can serve them.
- Indicators not tried before are explicitly wanted — bias the
  search toward novelty, not toward re-tuning known legs.
- LOSS-CLUSTER FIXING is a headline mechanism: every Plan A/C wave
  must include candidates with an explicit loss-cluster control
  (e.g. post-loss cooldown, cluster cap, correlated-symbol block,
  same-direction stack limit) and report the MC cluster/consec arms
  before vs after. The aim is a GOOD Monte Carlo result, honestly
  measured — the MC gates in §2 still apply exactly as written.

## 4. Office-hours rule (hard)

- Myanmar office hours = 09:00–17:00 MMT. No NEW check time may fall
  inside them. Added slots may only be 07:30 or 00:30 MMT (standing
  boundary) unless a cycle is CREATED for another off-hours :30 slot
  and the user is told which slot was used.
- Ordered office-time fixes (find a non-office check time whose
  cycle is ACCEPTABLE or IMPROVE, §2):
  Nov — first check 15:30 MMT is in office hours; also maximise
  overall stats. · May — first check 16:30 in office hours; also
  find an acceptable alternative beside the 16:30 slot.
  Dec — 16:30 check in office hours. · Sep — office-hour check
  (map it in Wave 0, then fix the same way).

## 5. The two scenarios (both run, reported separately)

- SCENARIO 1 — no check-time change: Plans A + B + C at each month's
  CURRENT check times.
- SCENARIO 2 — plus one check time: 20 cycles/month CREATED for one
  added off-hours slot (07:30 or 00:30 MMT, whichever the month does
  not already use). This is CREATION of new equations designed for
  that hour — NOT a replay of the incumbent's equations at the new
  hour. That replay was already calculated 2026-10-29
  (work_new8/ADDED_CHECK_CALC_20261029.md): 0 IMPROVE / 2 NEUTRAL /
  4 DOWNGRADE / 4 not reproducible — do not repeat it as if new.
  Jun already uses both slots → Scenario 2 impossible under the
  standing rule; report that, do not invent a slot. Aug (5 checks)
  and Sep (4 checks) are lower priority for Scenario 2 but stay in
  scope per the user's order.

## 6. Plans

- PLAN A (improve best): 20 cycles/month, §3 creative space, H1
  primary (standing rule: H1 stays primary; M15/M30 are confirmation
  only, never a standalone system or an entry-timing shift).
- PLAN B (create second-best): another 20 cycles/month per improved
  month, aimed at §2 second-best acceptance. Must use volume-column
  combinations, DXY (not Dukascopy IDX), and correlated-symbol
  combinations heavily. If Plan B cannot meet its requirements but
  a second-best is possible from threshold multi-combinations,
  build it from those (user fallback, restated this round).
- PLAN C (Plan A again, different): 20 cycles/month with DIFFERENT
  indicator×threshold combinations than Plan A, heavy M15 candles +
  M15 volume, still under the H1-primary rule (M15 = confirmation
  and feature source). Priority order: Dec, Jan, Mar, Jul FIRST,
  then the other 8. Includes a per-month M15/H1 behaviour study:
  what patterns actually exist in that month on M15 vs H1, written
  to the month's result file before its Plan C cycles run.

## 7. Priority order for the whole round

1. Wave 0 prep (§8) — blocks everything that needs DXY.
2. EC fixes: Jan (DSR), Feb (DSR + MC DD + second-best), Jul
   (MC DD — improve max DD until EC passes).
3. Plan C priority months: Dec, Jan, Mar, Jul.
4. Nov overall improvement + office fix; May second-best + office
   fix; Dec + Sep office fixes.
5. Remaining months: Apr, Jun, Aug, Sep, Oct — improvement search
   still runs (huge improvement wanted), no month is skipped.
6. Scenario 2 for every month with a free off-hours slot.

## 8. Wave 0 — data and facts gate (do FIRST, report before mining)

- DXY: ~/workspace/fx/work_29load/download_dxy.py exists but NO
  checkpoint or load stats exist — DXY was never loaded. Run its
  probe, then fetch; load whatever depth Twelve Data actually
  returns into fx_data.db as symbol DXY (H1 + M15, OHLCV) and
  report rows / first / last / nonzero-volume share. Never fabricate
  coverage. If DXY depth is materially shorter than DOLLARIDX,
  say so in every result that uses it and keep a DOLLARIDX-labelled
  control so the two are never confused. Do NOT delete Dukascopy
  IDX data in this round (the 2026-10-27 deletion order is NOT
  re-issued here; the live Nov b7 legs still read it).
- 28-symbol frame audit: confirm all 28 symbols present on H1 + M15
  in fx_data.db with usable volume fields; list any gaps.
- Check-time map: per month, best + second-best check times in MMT
  (entry-time naming), each flagged IN-OFFICE or OFF-HOURS, read
  from the registry code. This map is the reference for §4/§5.
- Use indexed queries only — fx_data.db is 1.9 GB; full scans stall.

## 9. Result contract (durable — write files FIRST, message second)

- Work dir: ~/workspace/fx/work_20cyc_r2/
- Per month × plan × scenario, one file:
  results/<mon>_<planA|planB|planC>_<s1|s2>.md
- Every result file OPENS with exactly one verdict line:
  VERDICT: <mon> <plan> <scenario> — IMPROVED | SMALL-IMPROVED |
  SECOND-BEST CREATED | NO IMPROVEMENT | REJECTED | BLOCKED-DATA
  followed by the numbers block: incumbent vs candidate DISC
  leftover, AUDIT leftover, AUDIT net, win %, entries/day, LCT P /
  q05, MC arms (P(profit), DD p95 vs cap, cluster p95 vs cap,
  consec p95), PBO, DSR, decay class, and the loss-cluster
  mechanism used. A file that exists without numbers is NOT a
  result — progress counts only from numbers written.
- INDEX.md in the work dir lists every result path + its verdict
  line; update it as each file lands.
- Report each month's verdict as soon as it lands — never batch
  all results for the end (standing user order).
- Time discipline (standing user order): middle-enough confidence
  is sufficient; do not chase extra certainty; if a wave cannot
  finish, deliver what is done with the gaps named.

## 10. Integration

- Promote ONLY §2-passing winners. Muse decides promotions and
  reports the decision + numbers (standing order — no permission
  asks). Archive research to GitHub before integrating; verify any
  integration by exact replay (control first, then new form).
- Warn before any app push: a push wipes the pasted Twelve Data key
  (Streamlit law). Do not open the live Streamlit app for checks —
  verify via local code, gates and records.
- Live signal crons are NOT switched by this round without a
  separate order.
