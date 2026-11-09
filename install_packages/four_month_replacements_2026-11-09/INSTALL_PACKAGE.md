# Install package — four month replacements (prepared 2026-11-09)

**Status: research picks, middle-validated on stored frames. NOT VALIDATED / NOT
INSTALLABLE until the canonical anchor (Step 1–2 below) passes on the main
machine. Sizing not graded. Nothing in this package changes the live app by
itself — it is the exact, filed evidence for the four replacements the user
ordered on 2026-11-09 (profit may tie or dip slightly where risk or another
requirement improves).**

Series evidence behind the picks: Rounds 1–130 (10,800+ designs). Of 12 months,
only Dec / Apr / Mar / Feb hold a design that is ACCEPTABLE under the middle
validation rule AND improves at least one statistic over its fixed Round-30
base. The other 8 months hold no replaceable design (Jan/Jun have above-base
designs that failed the battery; May/Aug/Nov never filed an acceptable;
Jul/Sep/Oct validated sets are the standing form itself).

## The four picks

| Month | Design | AUDIT net (vs base) | AUDIT leftover | AUDIT win | AUDIT epd | DSR | PBO | EC22 failed | Red DISC wks |
|---|---|---|---|---|---|---|---|---|---|
| Dec | **R44A10** | **+948.29 (+931.63)** | 50.22% (49.84%) | — | 3.356 (3.333) | 1.000 | 1.000 * | {13_lct, 14_leftover, 19_pbo} | 1 |
| Apr | **R108A09** | +2,777.48 (+2,809.98) | 74.04% (74.91%) | 95.41% (95.85%) | 4.955 (4.930) | 1.000 | 0.000 | {13_lct, 14_leftover} | 0 |
| Mar | **R34A10** | +760.39 (+760.39) tie | 75.39% (75.39%) | tie | tie | 0.759 | 0.000 | {13_lct, 14_leftover} | 0 |
| Feb | **R34A08** | +1,140.42 (+1,140.42) tie | 66.23% (66.23%) | 95.38% | tie | 1.000 | 0.000 | {13_lct, 14_leftover} | 0 |

\* PBO failure is tolerated under the user's middle-validation rule
(2026-11-08 23:13 MMT) while Monte Carlo §9 middle + EC22-middle pass.

### December — R44A10 (the only above-base champion in the whole series)
- Improves profit (+16.66), leftover (+0.38 pts) and entries/day over the base.
- Monte Carlo §9: PASS. Construction: December Round 44 minimal-change family
  (see round6_r44/GATES_R6R44.md and the design description in the grade file).
- Kept set: `masks/grade_r6r44_dec.json` + `masks/masks_r6r44_dec.npz`
  (mask hash in picks_detail.json).

### April — R108A09 (best risk pick of all 175 April champions, verified by scan)
- Chosen over the other 174 April champions because it improves the MOST
  statistics (6 of 22) including BOTH Monte Carlo risk lines, at the standard
  April give-back of −32.50 (−1.16%) AUDIT net:
  improved = AUDIT entries/day, AUDIT kept, DISC entries/day, §9 DD p95,
  §9 max-consecutive-loss p95, PBO.
- Monte Carlo §9: P(profit) 1.000, DD p95 117.35 vs cap 153.75,
  max-consec-loss p95 1.0, PASS. Worst-case AUDIT +2,577.59.
- Construction: worst-week shield quota adds (Round 108). DISC leftover
  77.48% (base 78.19%).
- Kept set: `masks/grade_r6r108_apr.json` + `masks/masks_r6r108_apr.npz`,
  mask hash a95c4b5b9c8859f9d1f68c9818bd2d5e.

### March — R34A10 (cleanest of the 4 March champions: R34A09, R34A10, R39A06, R39A07)
- Ties the base on every AUDIT headline (+760.39, leftover 75.39%); champion
  under the lowered standard. Cleanest overfit profile of the four:
  PBO 0.000, DSR 0.759, red DISC weeks 0. DISC net +3,822.28, leftover 76.77%.
- Alternate: R39A07 (DISC net +3,882.45, DSR 0.679, PBO 0.045).
- Kept set: `masks/grade_r6r34_mar.json` + `masks/masks_r6r34_mar.npz`.

### February — R34A08 (best of the 2 February champions: R34A08, R34A10)
- Ties the base on AUDIT (+1,140.42, leftover 66.23%, win 95.38%) with the
  stronger discovery ledger of the two: DISC net +6,679.41, leftover 82.78%
  (R34A10: +6,605.98 / 82.70%). DSR 1.000, PBO 0.000, red DISC weeks 0.
- Kept set: `masks/grade_r6r34_feb.json` + `masks/masks_r6r34_feb.npz`.

## Anchor checklist — MUST pass on the main machine before any install

Per the user's cycle-process law (2026-11-07) and validation-last rule:

1. Load the canonical `fx_data.db` from the main machine — it must load
   28/28 symbols. (This research machine's copy is the 2026-only extract;
   every month is BLOCKED-DATA here, which is why the anchor is owed.)
2. **Step 1 anchor, per month:** reproduce the CURRENT app cycle's answer
   key EXACTLY from the canonical pool (kept / win / net, PATH basis).
   Any mismatch = BLOCKED-DATA for that month — stop, do not install,
   do not substitute or repair a pool.
3. **Step 2 candidate check, per month:** reproduce the pick's filed
   kept / win / net from the same canonical pool, using the grade JSON and
   mask in `masks/`. Any mismatch = stop for that month.
4. Only with Steps 2+3 exact: build the cycle definition from the kept set
   on the main system, register it as the month's best (best-only), and
   push in a window the user names. **A push restarts the app and wipes
   the pasted Twelve Data key** — re-paste the key or set Streamlit
   Secrets `[api_keys]` immediately after.
5. After install, run one full check cycle for the month and compare the
   live signal against the expected form before trading on it.

## Files in this package
- `INSTALL_PACKAGE.md` — this brief.
- `picks_detail.json` — full filed statistics and battery results for the
  four picks (source: the rounds' grade JSONs, extracted 2026-11-09).
- `candidates_dec_mar_feb.json` — all Dec/Mar/Feb champion candidates
  compared (the pick rationale).
- `april_champions_scan.json` — all 175 April champions with their improved
  statistics (the scan R108A09 was picked from).
- `masks/` — the four grade JSONs and kept-set mask files, copied unchanged
  from round6_r44 / round6_r108 / round6_r34.

## What this package is not
- Not an app update. The live registry changes only through Step 4 above,
  on the main machine, after the anchor.
- Not a sizing change. Sizing was not graded anywhere in the series.
- November is NOT in this package: it holds no replaceable design
  (best research form +1,100.49 is itself unvalidated; best fill +1,082.57
  failed the battery on DSR + red DISC weeks).
