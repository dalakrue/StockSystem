# RESULT — 20-Cycle Round R2 (round close, 2026-10-30)

Research level only. Nothing in this file is integrated: no app
push, no GitHub push, no cron change was made by this round
(BRIEF §10). All figures below are read from the result files in
`results/` (56 files, 57 INDEX rows); the file named in each row
is the source of truth.

## 1. Headline

**What was ordered (BRIEF.md, locked 2026-10-30):** all 12 months,
20 cycles per month per plan — Plan A (improve best), Plan B
(create second-best), Plan C (Plan A again, different combos,
M15-heavy) — under two scenarios (S1 = current check times;
S2 = +1 created off-hours slot, 07:30 or 00:30 MMT only). Goal:
a 12-month best system passing the EnoughConfidence test at
MIDDLE level so it can go demo → small live at Best N ÷3.
Sizing was NOT a gate (user's ÷3 chained ruling, 2026-10-29).

**Locked gates (fixed before the run, never moved):** LCT-middle
P ≥ 80% AND q05 ≥ 20% · AUDIT (unseen) leftover strictly >
incumbent, or the small-improvement rule (not below, tie counts,
strongest LCT first) · win > 80% · entries/day ≥ 2 · AUDIT net
positive · Monte Carlo middle PASS on all arms (own-relative
`mc9_verbatim` flag governs) · PBO ≤ 50% (canonical basis) ·
DSR ≥ 0.90 · decay not FAIL · primary-12 battery counts as a
score, priority conditions mandatory. **Red lines, never
waivable: never promote an unseen-losing or discovery-collapsed
system.** Second-best: standalone epd > 2.5, best's checks + ≤1
new off-hours slot, combined delta > 0, combine-safety within
−2.00 AUDIT-leftover pts and MC arms not worse. Check-time
changes graded IMPROVE / ACCEPTABLE / DOWNGRADE by the §2 class
rule; only IMPROVE/ACCEPTABLE adoptable.

**Plain outcome counts:**

- **6 of 12 months end the round with a §2-passing candidate of
  record:** Feb, Mar, Apr, Jul, Oct, Dec (§2 table).
- **5 months NO IMPROVEMENT:** Jan, May, Jun, Aug, Sep —
  incumbents stand.
- **1 month's ledger winner REJECTED at verification:** Nov
  (C02) — incumbent stands.
- **Second-bests created: 2** (Feb X12, Jul B04 — both folded
  into their month's candidate form). May's second-best: NOT
  created (structural, §4).
- **Scenario 2: 0 slots adopted in 10 eligible months** (Jun and
  Aug have no free slot — both already use 07:30 + 00:30).
- **Office fixes: 0 adopted** of the 4 ordered (Nov, May, Dec,
  Sep) — every in-office check stands.
- **EC-failing months fixed: 2 of 3** (Feb ✓, Jul ✓, Jan ✗ —
  §3). **The 12-month system as a whole is still NOT
  EC-passing** (§3).
- **DXY: BLOCKED-DATA the entire round** — Twelve Data returned
  HTTP 429 on the Wave 0 probe; DXY loaded 0 rows and was never
  used. Every dollar leg in R2 is labelled Dukascopy DOLLARIDX
  (H1 47,486 / M15 189,222 rows, from 2017-12-01 only).

## 2. Per-month table

Leftover = net ÷ gross wins (by-trade, @2.5 spread). "Before →
after" is incumbent → candidate of record. Sources in brackets.

| Month | Incumbent | R2 outcome | Key numbers (candidate of record) |
|---|---|---|---|
| Jan | 60b+60 | **NO IMPROVEMENT** — EC still open | Incumbent DISC 29.82% / AUDIT 70.06%, DSR 0.8630 < 0.90 is its only failing EC item [jan_planA_s1.md]. D08 leg-ban fixes DSR (0.9947, LCT 99.59/48.19, MC all-pass) but AUDIT leftover falls 70.06→62.30% — fails the unseen gate. PC06 (M15 veto) fixes DSR without that cost (DSR 0.9256, AUDIT 70.94%, LCT 95.96/23.27) but MC DD p95 402.13 vs own cap 342.98 (miss 59.15); closest prune V04 misses DD by 3.58 with AUDIT epd 1.761 < 2 [jan_planC_s1.md, jan_planC_s1_attempt2.md]. S2 at BOTH slots failed (§4). |
| Feb | 85b (no second) | **IMPROVED — replay-verified** + **SECOND-BEST CREATED** | **A16+X12 combined:** DISC 76.90→**83.88%**, AUDIT 37.28→**42.28%**, nets +7004.02/+663.88, LCT vs incumbent 96.54/81.62, MC flag TRUE (DD p95 202.99 ≤ own cap 226.07; step-test cap 219.48 also passed), PBO 0.00% / DSR 1.0000 (family-22), decay WEAKENED = incumbent's class [feb_combined_best_s1.md]. Fallback **A16 alone** (tighter DD): DISC 82.62%, AUDIT 41.21%, LCT 96.40/71.83, DD p95 171.39 vs cap 189.56 [feb_planA2_s1.md]. X12 standalone: DISC 87.79%, epd 2.850/2.927 [feb_planB_s1.md + addenda]. |
| Mar | 86c+86s | **IMPROVED-at-simulated-replay** | **M18:** DISC 78.27→**79.89%**, AUDIT 22.99→**46.52%**, AUDIT net +338.25→+492.55, LCT 81.72/70.70, MC PASS (DD p95 190.02 vs own cap 225.84, cluster p95 106.64), PBO 0.00% / DSR 1.0000 (canonical family-21), decay WEAKENED-not-FAIL; LOO-robust (46.52→44.86 without its best AUDIT trade) [mar_attempt2_s1.md]. First winner PC14 was REJECTED at simulated fall-through (§4) [mar_verify.md]. |
| Apr | 87c+87s | **IMPROVED-at-simulated-replay** | **C19-sim** (strongest simulated form): DISC 85.26→**90.58%**, AUDIT 71.26→**76.25%**, AUDIT net +1929.49→+2153.64 (highest of any Apr form), LCT 96.82/82.72, MC PASS (DD p95 177.90), PBO 0.00% / DSR 1.0000, decay PASS. **C20-sim:** DISC 90.37%, AUDIT 76.11%, net +2135.68, LCT 95.42/82.35, DD p95 180.04 vs cap 246.65 — all gates pass [apr_verify.md]. |
| May | 88n (+88 contained) | **NO IMPROVEMENT** | Incumbent DISC 95.30% / AUDIT 79.54% stands. Plan B: best B03 combined AUDIT leftover 79.54→61.97% misses the −2.00 tolerance by 15.57 pts, LCT P 69.68% FAIL — second-best NOT created [may_planB_s1.md]. Plan C: 12/20 forms beat AUDIT leftover (to 100.00%) but all fail epd ≥ 2; finals hit the structural LCT ceiling P 69.68% (§4); closest second-best attempt F16 misses combine-safety by 2.63 pts [may_planC_s1.md]. Office: drop/add/replace 16:30 all DOWNGRADE [may_planB_s1.md, may_planA_s2.md]. |
| Jun | 89p (+89 contained) | **NO IMPROVEMENT** | Incumbent DISC 70.81% / AUDIT 46.65%, epd exactly 3.000, MC PASS. Closest D01 veto: DISC 81.42%, AUDIT 51.27%, LCT 98.25/71.36, PBO 0.00% / DSR 0.9996 — fails the MC DD arm alone (p95 166.37 vs own cap 153.75, cap-trap). Partners saturated or combine-unsafe. S2 impossible (both slots used) [jun_planA_s1.md]. |
| Jul | 78 (no second) | **IMPROVED (ledger level, Jul convention)** + **SECOND-BEST CREATED** | **D3:** DISC 66.10→**89.11%**, AUDIT 64.97→**77.01%**, AUDIT net +1140.61, win 97.25/95.45, epd 2.925/2.870, LCT 100.00/80.05, MC flag TRUE (DD obs 125.67 → p95 172.54 ≤ own cap 188.51), PBO 20.00% / DSR 1.0000 (canonical family-10), decay not FAIL, 0 DISC full-stops remain [jul_planA_s1_attempt4.md]. Second-best **B04** created standalone (DISC 97.02%, epd 2.920/2.870) and folded into the D3 lineage [jul_planB_s1.md]. Jul has no app-replay machinery; its incumbent ledger reproduces the step test exactly, so ledger level is Jul's verification convention. |
| Aug | 67+67p | **NO IMPROVEMENT** | Incumbent rebuilt exact: 766 picks, DISC 96.75% / AUDIT 86.94%, only 5 losses in 766 trades — no loss cluster exists to fix. Best slate LCT is C02 at P 69.68% < 80; the only AUDIT-beating form (C06, 90.97%) has LCT P 0.00%. S2 impossible (both slots used). The 12:30 IN-OFFICE check was flagged, not in the ordered fix list [aug_planA_s1.md]. |
| Sep | 91p+91s | **NO IMPROVEMENT** | Incumbent DISC 68.60% / AUDIT 69.49%, MC PASS. Plan A veto forms fail AUDIT leftover or LCT; partners accepted 0 [sep_planA_s1.md]. Office: created 00:30 replacement **S13 grades ACCEPTABLE** under the class rule (REP AUDIT leftover 70.00%, +0.51; net −29.97 inside the −115.23 line; MC TRUE; cluster improves −153.10→−129.82; DSR 0.9998; decay PASS) **but DISC leftover −14.94 (53.66%) and LCT P 0.00% FAIL — NOT adopted** (decision §4); as an ADDITION S13 is a DOWNGRADE (AUDIT 68.00%, LCT 0.00, MC FALSE) [sep_office_s1.md, sep_s2.md]. An earlier S1 18:30 ACCEPTABLE was withdrawn after mined S2 confirmation exposed a lookahead suspect in that baseline [sep_planA_s2.md]. |
| Oct | 92+92e | **IMPROVED — construction-verified** | **C14:** DISC 86.96→**87.68%**, AUDIT 72.41→**73.35%**, AUDIT net +1118.43→+1171.05 (no debit), LCT 100.00/81.05, MC PASS (DD p95 175.21 vs own cap 213.45), PBO 0.00% / DSR 1.0000, decay PASS. Fresh re-merge of the partner walk reproduces the published combined exactly (700 picks, 43 accepted, 0 duplicates, 0 overlaps, C155 dual-pick untouched) [oct_verify.md]. C01 veto also passes at simulated level (AUDIT 74.46%, LCT 100.00/98.72) but its net stays −10.23 below incumbent and base-stream fall-through is unmodelled — C14 is the form carried [oct_verify.md]. |
| Nov | 93r+93s | **REJECTED-at-verification** (ledger winner did not survive) | C02 veto: ledger DISC 77.05→83.43%, AUDIT 43.44→44.03%, LCT 97.87/72.80, MC TRUE — then simulated fall-through (86 refills, AUDIT refill net −159.43) cuts AUDIT leftover to **30.93% < 43.44**; extended all-pool sim worse (25.64%). Incumbent stands [nov_planA_s1.md, nov_verify.md]. Office: 40/40 created replacement forms DOWNGRADE at both slots; Nov keeps 15:30 + 16:30 [nov_office_s1.md]. |
| Dec | 94c+94s | **IMPROVED-at-simulated-replay** | **D19:** DISC 78.43→**80.93%**, AUDIT 53.02→**57.65%**, AUDIT net +1090.28→+1161.63, LCT 95.21/75.89, MC PASS (DD p95 239.00 vs own cap 269.61, cluster p95 139.91), PBO 0.00% / DSR 1.0000 (canonical family-21), decay WEAKENED-not-FAIL [dec_attempt2_s1.md]. First winner C07 was REJECTED at simulated fall-through (§4) [dec_verify.md]. Office: NONE — 16:30 is AUDIT-critical (dropping it cuts AUDIT leftover to 38.88%) [dec_planC_s1.md]. |

## 3. EC re-grade (vs the 2026-10-29 EnoughConfidence step test)

The step test's three edge failures, and where R2 leaves them:

| Month | Step-test failure | R2 result | EC now |
|---|---|---|---|
| Feb | MC DD arm 228.72 vs cap 219.48 AND DSR 0.1819 | A16+X12 combined: DD p95 **202.99** (passes the fixed step cap 219.48 and its own cap 226.07), DSR **1.0000**; A16 alone DD p95 171.39, DSR 1.0000 | **PASSING FORM EXISTS — YES** |
| Jul | MC DD arm 233.91 vs cap 215.72 | D3: DD p95 **172.54** ≤ own cap 188.51, MC flag TRUE, DSR 1.0000, PBO 20.00% | **PASSING FORM EXISTS — YES** (ledger level, Jul convention) |
| Jan | DSR 0.8630 < 0.90 | No form passes all gates: DSR-fixing forms (D08 0.9947, PC06 0.9256) fail the unseen gate or the MC DD arm (miss 59.15; closest variant miss 3.58 but AUDIT epd 1.761 < 2) | **NO — Jan remains open, incumbent stands** |

**Honest whole-system statement: the 12-month system is still
NOT EC-passing as a whole.** Two of the three failing months now
have passing forms, but (a) **January remains open** — no R2
form fixes its DSR without breaking the unseen gate, entries,
or the drawdown arm; and (b) **May passes only under the user's
standing LCT waiver** (its LCT-middle failure is structural —
§4 — not a candidate defect). The other nine months' incumbents
already passed edge+sizing under the ÷3-chained ruling before
this round; R2 changes none of them for the worse (no incumbent
was replaced at research level), and where R2 found verified or
simulated-passing forms (Mar, Apr, Oct, Dec) those forms raise
the month's margins on the measured arms — Mar AUDIT leftover
22.99→46.52%, Dec 53.02→57.65%, Apr 71.26→76.25% (C19-sim),
Oct 72.41→73.35% with net above incumbent — subject to the
integration verification in §5. A finished round is not a
passed round: Jan is the blocker, May is a waiver, and nothing
above is live until §5 is executed.

## 4. Cross-cutting findings

**Veto fall-through — the round's central lesson.** Of the six
ledger-level veto winners sent to a fall-through test, **five
died**: Feb C08 (replay AUDIT 36.80% vs 37.28%, LCT 78.14%),
Dec C07 (simulated AUDIT 47.60% vs 53.02%), Mar PC14 (one
−102.50 unseen refill erases the gain: 21.18% vs 22.99%),
Mar PC08 (simulated AUDIT 8.50%), Nov C02 (simulated AUDIT
30.93% vs 43.44%). **Apr is the sole survivor** — C20/C19 pass
at simulated-replay with refills net-positive on BOTH segments
(C20-sim AUDIT refill net +133.34). (Oct C01 also passed its
simulated test, AUDIT 74.46%, but carries an AUDIT-net debit
and unmodelled base-stream fall-through, so it is not carried.)
The pattern is mechanical: a veto's ledger gain is the value of
the slots it empties, and the system's own next layers refill
those slots with weaker trades. **Screening THROUGH fall-through
— veto + partner fills graded on the refilled ledger (the Feb
A16 method), or refill-inside-the-screen (Dec D19, Mar M18) —
is the only trustworthy veto method.** Every surviving R2
candidate was produced that way.

**Scenario 2 failed totally.** No slot was added in any month.
Jan was created at both slots (00:30: slot cycle +1,214.10 DISC
/ −233.20 AUDIT — regime flip; 07:30: unseen-neutral, dilutes).
Feb, Mar, Apr, May, Jul, Sep, Oct, Nov, Dec additions all grade
DOWNGRADE or fail LCT/MC — the 07:30 and 00:30 hours carry **no
transferable edge** for this system in any month tested, and
added slots repeatedly import loss clusters (e.g. Feb S2 worst
cluster −102.50→−307.50; Mar S2 −102.50→−163.34). One
ACCEPTABLE-class form exists (Apr S19: combined AUDIT leftover
+1.04, MC all-pass) but it fails LCT-middle (P 13.21%) and was
not adopted under the locked gates. Two validations of the
pre-registered **stability guard** (select on early-DISC, require
positive late-DISC tail): it blocked Jan 07:30's unguarded
winner S16 on DISC evidence alone (early net −4.40; S16's AUDIT
was −27.35% — the exact trap the 00:30 run fell into), and it
blocked Oct's entire 07:30 slate (0/20 eligible, every
early-DISC net negative). The guard works as a filter; it
cannot create edge where none exists.

**Office fixes: NONE adopted.** Nov (40/40 created replacements
DOWNGRADE), Dec (16:30 is AUDIT-critical), May (drop/add/replace
all DOWNGRADE) measured NONE. Sep produced one ACCEPTABLE-class
replacement (S13, §2 table) which was **declined**: it meets the
check-time class rule on its face but zeroes the robustness
proof (LCT P 0.00%) and cuts discovery leftover by 14.94 pts —
a downgrade in substance. All four in-office checks stand
(Nov 15:30 + 16:30, May 16:30, Dec 16:30, Sep 16:30; Aug 12:30
was flagged, never ordered).

**DXY blocked all round.** Twelve Data HTTP 429 on the first
Wave 0 probe call (hard provider stop, no retry); DXY = 0 rows.
All R2 dollar legs use labelled Dukascopy DOLLARIDX only
(H1 47,486 / M15 189,222 rows, from 2017-12-01, no volume
conditions on it). Any future DXY work needs a fresh data load
first [wave0.md].

**May's LCT ceiling is structural.** Three independent
measurements (the E07 waiver record, Plan B's B03, Plan C's
finals) land on paired P = **69.68% exactly**. The construction
caps any candidate at **≤ 70.37%**: the incumbent's own
resampled DISC leftover reaches ~100% in the blocks a candidate
cannot win, so even a DISC-perfect candidate wins only 69.68%
of paired resamples [may_planC_s1.md, may_planB_s1.md]. **May
cannot pass LCT-middle (P ≥ 80%) in this frame by
construction** — its EC pass continues to rest on the user's
standing waiver, and no further May LCT search in this frame
can change that.

**Two smaller measured facts.** (a) The own-relative MC DD cap
creates a cap-trap for prune forms (the cap falls with observed
DD — Jun D01, Jan V04, Jul attempts 1–3 all died there); Jul's
full-stop-density prune (attempt 4) is the one measured way
through it. (b) Cooldowns and stack limits RAISE observed DD
(Jul, Sep) — they delete the small wins that interrupt DD
paths. Cluster control by pruning carrier legs works; cluster
control by post-loss state rules does not.

## 5. Integration package spec — NOT executed

Candidates of record, their app-code forms, and what still
stands between them and the app. **Fresh exact gate replay per
candidate is required before any push**: build the app-code
form, replay the incumbent control exactly first, then replay
the new form and re-grade the full §2 battery on the replay
ledger. A candidate that fails its fresh replay is not pushed.

| Candidate | App-code form to build | Verification still required |
|---|---|---|
| **Feb A16+X12** (fallback: A16 alone) | Cycle85b base + veto rule dropping FB_EURUSD_h16_1 picks before selection (the C08 veto as an app rule) + PLANB cand2 partner design merged second-priority against the vetoed base (45 accepted at research replay) + **X12 second-best layer**: the union of 11 prior Feb mined designs, second-priority at the best's own checks (17:30/19:30/22:30 MMT), no new slot | A16 and X12-vs-incumbent were verified through the app-replay driver with fall-through at research level; the COMBINED form's app-code expression still needs its own fresh exact replay (control first) before push |
| **Jul D3** | Cycle78 base with the C18 prune set {FB_EURUSD_h15_0_G, FB_USDJPY_h15_2_G} + the two D3 carrier legs pruned at source (the B04 fill leg q_wt1_lt75_GBPNZD_h15_0.9x7.0_H48_2 and the base leg mom_USDCAD_h15_momB_T1.5_A1.0_1.25x8) + **B04 second-best fill** (reverse-chronological union of 15 prior Jul designs) recomputed against the pruned base (165 accepted) | Ledger level only (Jul convention — no app-replay machinery exists for Jul). Fresh exact gate replay of the app-code form against the cycle78 control is required; if the app form cannot reproduce D3's ledger, D3 does not ship |
| **Dec D19** | Cycle94c+94s combined + **PC03 M15 veto** (mom4_mom96_vol M15-confirmation veto from dec_planC_s1.md) applied to the base stream + **PLANB12C cand1 partner** merged second-priority | Simulated-replay level only (no true app-code driver exists for the full Dec combined; unmodelled: base-stream next-signal fall-through, open-position cascades, refill feature status). Fresh exact replay required before push |
| **Mar M18** | Cycle86c+86s combined + **PC14 mask** (M15 confirmation veto: aligned BB z ≤ 1.0 & aligned range-pos ≤ 0.85 & aligned mom16 > −0.35) + **EURAUD h12 b6v slot veto** (the slot that was DISC +782.31 / AUDIT −346.06) | Simulated-replay level only (same unmodelled gaps as Dec). Fresh exact replay required before push |
| **Apr C19-sim / C20-sim** | Cycle87c+87s combined + veto of slot **FB_NZDUSD_h17_0**; C19 adds the **PLANB9C cand1 partner** merged after the system's own layer refills (9 accepted simulated; the C20 form's PLANB cand2 partner accepts 0 once fall-through is modelled, so the veto itself is C20's operative form). Exact C19 definition: apr_planA_s1.md (C19 = C01 veto + PLANB9C cand1, 25 fills at ledger level) as graded simulated in apr_verify.md | Simulated-replay level only (harness2/3 replay candidate layers only; base-stream fall-through and cascades unmodelled). Fresh exact replay required before push |
| **Oct C14** | Cycle92+92e combined (REF657, C155 dual-pick untouched) + **PLANB9 cand2 partner** design merged second-priority, incumbent-priority occupancy (43 accepted, all at checks empty in the incumbent) | Construction-verified (re-merge reproduces the combined exactly). Residual gap: no app-side walk gate for the PLANB9 cand2 design exists on disk — the partner walk is a stored research walk. Fresh exact replay of the app form required before push |

**Standing warnings (BRIEF §10, repeated because they bind
whoever executes this):**

- **Warn before any app push — a push wipes the pasted Twelve
  Data key.** The durable fix is Streamlit Secrets, which only
  the user can set; it has not been done.
- **Archive the research to GitHub before integrating** — this
  work dir (BRIEF, INDEX, results/, runners) is the record the
  integration must be checked against.
- **Live signal crons are NOT switched by this round.** Chat
  signals keep using the month-best registry read fresh
  (`core/signal_mode.py` MONTH_SYSTEMS) until a separate order
  switches them.
- **Do not open the live Streamlit app to verify** — verify via
  local code, gates, and records (each app open burns Twelve
  Data credits).
- Integration order is a decision for the parent/user, not
  taken here. Feb (replay-verified) and Oct
  (construction-verified) carry the strongest evidence; Dec,
  Mar, Apr carry simulated-level evidence with named unmodelled
  gaps; Jul carries ledger-level evidence under its own
  convention.
