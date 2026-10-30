# WAVE 0 — PREP (20-Cycle Round R2) — 2026-10-30

Brief: ~/workspace/fx/work_20cyc_r2/BRIEF.md §8. All facts below were
measured this run (2026-10-30 ~01:00–01:20 MMT) from local sources.
No live app opened. No GitHub push.

## (a) DXY — BLOCKED-DATA (Twelve Data rate limit, hard stop)

- Probe run: `python3 ~/workspace/fx/work_29load/download_dxy.py probe`
  → **HTTP Error 429: Too Many Requests** from api.twelvedata.com
  (traceback in download_dxy.py call() → urlopen).
- Per the standing provider rule, a 429 is a HARD STOP for that
  provider in this attempt: the fetch was NOT retried, no further
  Twelve Data calls were made, and no DXY rows were loaded.
- DB state verified by indexed query (Symbol='DXY'):
  ohlc_h1 = **0 rows**, ohlc_m15 = **0 rows**. DXY does NOT exist
  in fx_data.db. Nonzero-volume share: N/A (no rows).
- Consequence for this round: **no candidate may claim a real
  Twelve Data DXY feature.** Per brief §6/§8, dollar legs must use
  the DOLLARIDX-labelled control (Dukascopy) and say so on the
  face of every result that uses it. The two must never be
  confused. DXY fetch is to be re-attempted only in a later
  attempt when the provider limit has reset (parent to schedule);
  it is NOT retried inside this attempt.
- Control on record — DOLLARIDX (Dukascopy, indexed query):
  H1 **47,486 rows**, 2017-12-01 00:00:00 → 2026-10-26 15:00:00;
  M15 **189,222 rows**, 2017-12-01 00:45:00 → 2026-10-26 15:00:00.
  2024 sample volume: H1 5,426/5,426 nonzero; M15 21,683/21,683
  nonzero. NOTE: DOLLARIDX depth (from Dec 2017) is materially
  shorter than the 28 FX symbols (from Jan 2015) — any
  DOLLARIDX-leg result must state this.
- Dukascopy IDX data was NOT deleted (brief §8: the 2026-10-27
  deletion order is not re-issued; live Nov b7 legs still read it).

## (b) 28-symbol frame audit — PASS, no gaps

Universe = check1_symbols.json (20 base + NEW8: CADCHF, CADJPY,
GBPAUD, GBPCAD, GBPCHF, GBPNZD, NZDCHF, NZDJPY). Indexed queries
(Symbol, Datetime) on fx_data.db, COUNT/MIN/MAX per symbol:

| Symbol | H1 rows | M15 rows | First (both) | Last H1 | Last M15 |
|---|---|---|---|---|---|
| AUDCAD | 73,735 | 294,832 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| AUDCHF | 73,729 | 294,835 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| AUDJPY | 73,741 | 294,872 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| AUDNZD | 73,725 | 294,814 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| AUDUSD | 73,739 | 294,901 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| CHFJPY | 73,703 | 294,548 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| EURAUD | 73,729 | 294,808 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| EURCAD | 73,756 | 294,880 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| EURCHF | 73,736 | 294,829 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| EURGBP | 73,750 | 294,912 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| EURJPY | 73,737 | 294,873 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| EURNZD | 73,673 | 294,358 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| EURUSD | 73,759 | 294,933 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| GBPJPY | 73,733 | 294,847 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| GBPUSD | 73,743 | 294,898 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| NZDCAD | 73,706 | 294,664 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| NZDUSD | 73,735 | 294,828 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| USDCAD | 73,755 | 294,901 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| USDCHF | 73,752 | 294,854 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| USDJPY | 73,757 | 294,923 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| CADCHF | 73,720 | 294,777 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| CADJPY | 73,756 | 294,915 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| GBPAUD | 73,702 | 294,579 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| GBPCAD | 73,725 | 294,658 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| GBPCHF | 73,714 | 294,685 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| GBPNZD | 73,619 | 293,912 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| NZDCHF | 73,709 | 294,715 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |
| NZDJPY | 73,723 | 294,783 | 2015-01-01 22:00 | 2026-10-29 17:00+00 | 2026-10-29 17:45+00 |

- All 28 present on BOTH timeframes, full 2015→2026-10-29 span.
  GAPS: none.
- Volume usable (2024 calendar-year sample, indexed range query):
  EURUSD H1 6,250/6,250 nonzero, M15 24,994/24,998 nonzero;
  CADCHF (NEW8) H1 6,249/6,249 nonzero, M15 24,974/24,977
  nonzero. Volume columns are real Dukascopy tick volume and are
  usable in combinations on research frames. (Live-app caveat
  stands from 2026-10-29: Twelve Data live M15 volume is
  all-zero/NaN, so volume-dependent equations stay silent live —
  research use is unaffected.)

## (c) Check-time map (MMT, entry-time naming) — read FRESH from registry

Source: ~/workspace/fx/work_29load/Forex_App_Updated/core/
signal_mode.py — MONTH_SYSTEMS + MONTH_SECOND_BEST +
active_check_hours(), read this run. Entry-time naming: label =
UTC entry hour + 6:30 (the panel/signal label convention).
Office = 09:00–17:00 MMT; a :30 check is IN-OFFICE if its label
falls in [09:00, 17:00).

| Month | Best | Best checks MMT (flag) | Second-best | Second checks MMT (flag) | Combined distinct checks | S2 free slot |
|---|---|---|---|---|---|---|
| Jan | cycle60b | 17:30 OFF · 19:30 OFF · 23:30 OFF | cycle60 | same 3 | 3 | 07:30 and 00:30 both free |
| Feb | cycle85b | 17:30 OFF · 19:30 OFF · 22:30 OFF | — none — | — | 3 | 07:30 and 00:30 both free |
| Mar | cycle86c | 17:30 OFF · 22:30 OFF · 23:30 OFF | cycle86s | 17:30 · 18:30 OFF · 22:30 · 23:30 | 4 | 07:30 and 00:30 both free |
| Apr | cycle87c | 22:30 OFF · 23:30 OFF · 00:30 OFF | cycle87s | + 01:30 OFF | 4 | 07:30 free (00:30 used) |
| May | cycle88n | **16:30 IN-OFFICE** · 22:30 OFF · 00:30 OFF | cycle88 | same 3 | 3 | 07:30 free (00:30 used) |
| Jun | cycle89p | 07:30 OFF · 21:30 OFF · 00:30 OFF | cycle89 (contained) | same 3 | 3 | **NONE — both slots used (S2 impossible, brief §5)** |
| Jul | cycle78 | 21:30 OFF · 23:30 OFF · 00:30 OFF | — none — | — | 3 | 07:30 free (00:30 used) |
| Aug | cycle67 | 07:30 OFF · **12:30 IN-OFFICE** · 22:30 OFF · 23:30 OFF · 00:30 OFF | cycle67p | same 5 | 5 | **NONE — both slots used** |
| Sep | cycle91p | 07:30 OFF · **16:30 IN-OFFICE** · 17:30 OFF | cycle91s | + 08:30 OFF | 4 | 00:30 free (07:30 used) |
| Oct | cycle92 | 21:30 OFF · 23:30 OFF · 00:30 OFF | cycle92e | same 3 | 3 | 07:30 free (00:30 used) |
| Nov | cycle93r | **15:30 IN-OFFICE** · 19:30 OFF · 21:30 OFF | cycle93s | + **16:30 IN-OFFICE** | 4 | 07:30 and 00:30 both free |
| Dec | cycle94c | **16:30 IN-OFFICE** · 17:30 OFF · 19:30 OFF | cycle94s | + 20:30 OFF | 4 | 07:30 and 00:30 both free |

Ordered office fixes (brief §4) confirmed against this map:
Nov best 15:30 IN-OFFICE (+ second-best adds 16:30 IN-OFFICE) ·
May 16:30 IN-OFFICE · Dec 16:30 IN-OFFICE · Sep 16:30 IN-OFFICE.
Additional finding NOT in the brief's ordered list: **Aug has a
12:30 IN-OFFICE check** (both best and second) — flagged for the
parent; no fix ordered for Aug in this round.
Scenario-2 slot availability: Jun = NO SLOT (brief-known); Aug =
also NO SLOT (uses both 07:30 and 00:30) — report, do not invent
a slot. All other months have at least one free slot as listed.

## Wave 0 verdict

- 28-symbol audit: PASS. Check-time map: DONE (reference for
  §4/§5). DXY: **BLOCKED-DATA** (429 hard stop) — all dollar work
  in this round runs on the DOLLARIDX-labelled control until a
  later attempt can fetch DXY; every affected result file must
  carry that label.
- Next (brief §7 step 2): Scenario 1 Plan A, 20 cycles each —
  Jan (DSR ≥0.90 target), Feb (DSR + MC DD arm + loss-cluster),
  Jul (MC DD arm). Workers launched from this file.
