# WAVE 0 — DATA AND FACTS GATE (20-Cycle Round R2, BRIEF §8)
# Run: 2026-10-30 ~01:00–01:20 MMT. All numbers below were measured
# this run; nothing is carried or fabricated.

VERDICT: Wave 0 — PARTIAL / DXY BLOCKED-DATA (Twelve Data HTTP 429 on the probe; DXY-dependent work blocked, all other Wave 0 items complete and Plan A S1 for Jan/Feb/Jul is NOT blocked on non-DXY legs)

## 1. DXY (Twelve Data) — BLOCKED-DATA, honestly reported

- Ran the probe exactly as locked: `python3 ~/workspace/fx/work_29load/download_dxy.py probe`
  (symbol DXY, interval 1h, outputsize 5, via the registered
  custom.twelvedata credential surrogate).
- Result: **HTTP Error 429: Too Many Requests** from api.twelvedata.com
  on the FIRST probe call. Per the standing provider rule a 429 is a
  hard stop for that provider in this run — the fetch was NOT started
  and NOT retried.
- Therefore: **DXY was NOT loaded.** fx_data.db contains NO symbol
  'DXY' in ohlc_h1 or ohlc_m15 (verified by indexed query this run:
  only 'DOLLARIDX' matches the dollar-index names).
- No coverage figures exist for Twelve DXY, so none are reported.
  Rows / first / last / nonzero-volume share for DXY = **not measured
  (no data returned)**.
- Consequence per BRIEF §6/§8: every DXY-dependent candidate in this
  round is BLOCKED-DATA. Work that does not need DXY proceeds, using
  the Dukascopy series under its own name **DOLLARIDX** only, always
  labelled as Dukascopy (never confused with Twelve DXY), with its
  measured coverage: H1 47,486 rows 2017-12-01 00:00 → 2026-10-26
  15:00, volume nonzero 47,476/47,486 (99.98%, but on Dukascopy's
  own incomparable scale — programme rule: no volume conditions on
  DOLLARIDX picks, pip provisional 0.01); M15 189,222 rows
  2017-12-01 00:45 → 2026-10-26 15:00, volume nonzero
  189,209/189,222 = **99.99%** (full group-by audit, latest state).
  NOTE: an earlier pass tonight measured DOLLARIDX M15 volume at
  1.14% nonzero — that was the pre-reload state of the series;
  the series was evidently reloaded with real volume during the
  night and the 1.14% figure is withdrawn.
- Dukascopy IDX data was NOT deleted (BRIEF §8: the 2026-10-27
  deletion order is not re-issued; live Nov b7 legs still read it).

## 2. 28-symbol frame audit (fx_data.db, indexed per-symbol queries)

**CORRECTION (same night, after the coordinator's cross-check in
wave0_prep.md flagged a discrepancy):** the §2 figures in the first
version of this file came from an indexed pass that caught the DB
in a transient mid-reload state (parallel lanes are rebuilding /
extending fx_data.db tonight; row counts and even the H1 head date
moved between passes). The figures below are the RE-VERIFIED ones:
H1 re-audited in full this night (all 30 names, indexed), M15
re-measured directly for EURUSD, USDJPY, CADCHF, AUDCAD, AUDCHF
and DOLLARIDX (full M15 re-audit was abandoned under severe DB
contention — 2 symbols in 4 minutes — and is a named gap; the
coordinator's prep independently gives M15 ≈294k rows/symbol,
matching every direct re-measurement below). Where the first
version was wrong it is corrected, not silently replaced:
the NEW8 H1 "<1% volume" claim and the "2.6–2.9M M15 rows" claim
were BOTH artefacts of the transient state and are withdrawn.

All 28 traded symbols are PRESENT on both H1 and M15. No symbol is
missing on either timeframe.

### H1 (ohlc_h1) — RE-VERIFIED in full (indexed, this night)
- All 28 FX symbols: 73,619–73,759 rows each, first
  2015-01-01 22:00:00, last 2026-10-29 17:00:00+00:00
  (live-appended, tz-suffixed tail).
- Volume nonzero in the full 2024 calendar-year window:
  **100% for every one of the 28 symbols** (6,226–6,250 of
  6,226–6,250 rows per symbol), NEW8 crosses included. H1 volume
  is usable across the whole 28-symbol universe.
- DOLLARIDX: 47,486 rows, 2017-12-01 00:00:00 → 2026-10-26
  15:00:00; 2024 volume nonzero 5,426/5,426 (100%, Dukascopy
  scale — see §1). Materially shorter history than the FX
  symbols: no 2016 – Nov-2017 data.
- DXY: 0 rows (see §1).

### M15 (ohlc_m15) — directly re-measured subset (indexed)
- EURUSD 294,933 · USDJPY 294,923 · CADCHF 294,777 · AUDCAD
  294,832 · AUDCHF 294,835 rows; first 2015-01-01 22:00:00, last
  2026-10-29 17:45:00+00:00. 2024 volume nonzero ≈100%
  (AUDCAD 24,975/24,978; AUDCHF 24,985/24,988; CADCHF
  24,974/24,977).
- DOLLARIDX M15: 189,222 rows, 2017-12-01 00:45 → 2026-10-26
  15:00, volume nonzero 189,209/189,222 = 99.99%.
- FULL M15 table (late-arriving complete group-by audit, current
  state — supersedes the subset above and closes the subset
  gap): all 28 FX symbols 293,912–294,933 rows each, first
  2015-01-01 22:00:00, last 2026-10-29 17:45:00+00:00, volume
  nonzero ≥99.99% for every symbol (worst case EURUSD
  294,929/294,933; GBPAUD and GBPCAD and GBPNZD and NZDJPY at
  exactly 100%). M15 volume is usable across the whole universe
  (with the standing zero-median guard caution below). The same
  audit confirms H1 full-period volume nonzero = rows − ~93 per
  symbol (99.87%) for all 28.
- Standing caution (2026-10-29 IndexError lesson) still applies
  to any M15-volume column: guard empty/zero-median windows.

### Gap list (complete, corrected)
1. **DXY (Twelve Data): absent, both timeframes — 429-blocked.**
2. DOLLARIDX history starts 2017-12-01 (no 2016–2017-11 data) —
   the only real coverage gap in the database. Its volume is
   present (≈100% nonzero, both timeframes) but on Dukascopy's
   own scale: programme rule stands — no volume conditions on
   DOLLARIDX picks, pip provisional.
3. No other gaps: all 28 symbols × H1 + M15 OHLC present;
   volume nonzero ≥99.87% (H1, full period) and ≥99.99% (M15,
   full period) for every symbol in the latest full audit.

## 3. Check-time map (registry read FRESH this run)

Source: `core/signal_mode.py` MONTH_SYSTEMS + MONTH_SECOND_BEST in
~/workspace/fx/work_29load/Forex_App_Updated (the shipped tree),
hours resolved via live_trader/signals_month.py `check_hours_utc`
(the module's own *_CHECK_HOURS). Naming: entry-time naming —
entry hour h UTC → entry time (h+6):30 MMT; the check label is
h:30 UTC. Office = 09:00–17:00 MMT.

| Month | Best (second) | Best check times MMT (entry naming) | Flags | Second-best extra times |
|---|---|---|---|---|
| Jan | cycle60b (cycle60) | 17:30, 19:30, 23:30 | all OFF-HOURS | none (same hours) |
| Feb | cycle85b (none) | 17:30, 19:30, 22:30 | all OFF-HOURS | — no second-best — |
| Mar | cycle86c (cycle86s) | 17:30, 22:30, 23:30 | all OFF-HOURS | +18:30 (off) |
| Apr | cycle87c (cycle87s) | 22:30, 23:30, 00:30 | all OFF-HOURS | +01:30 (off) |
| May | cycle88n (cycle88) | **16:30**, 22:30, 00:30 | **16:30 IN-OFFICE** | none |
| Jun | cycle89p (cycle89) | 07:30, 21:30, 00:30 | all OFF-HOURS; **uses BOTH allowed S2 slots → Scenario 2 impossible (BRIEF §5)** | none |
| Jul | cycle78 (none) | 21:30, 23:30, 00:30 | all OFF-HOURS | — no second-best — |
| Aug | cycle67 (cycle67p) | 07:30, **12:30**, 22:30, 23:30, 00:30 | **12:30 IN-OFFICE** (5 checks; not in BRIEF §4's ordered fix list — flagged here only) | none |
| Sep | cycle91p (cycle91s) | 07:30, **16:30**, 17:30 | **16:30 IN-OFFICE** | +08:30 (off) |
| Oct | cycle92 (cycle92e) | 21:30, 23:30, 00:30 | all OFF-HOURS | none |
| Nov | cycle93r (cycle93s) | **15:30**, 19:30, 21:30 | **15:30 IN-OFFICE** (BRIEF §4: first check, ordered fix) | +16:30 (also IN-OFFICE) |
| Dec | cycle94c (cycle94s) | **16:30**, 17:30, 19:30 | **16:30 IN-OFFICE** (ordered fix) | +20:30 (off) |

Registry at this read (matches BRIEF §1 record): Jan 60b+60 ·
Feb 85b (no second) · Mar 86c+86s · Apr 87c+87s · May 88n+88 ·
Jun 89p+89 · Jul 78 (no second) · Aug 67+67p · Sep 91p+91s ·
Oct 92+92e · Nov 93r+93s · Dec 94c+94s.

Scenario-2 slot availability from the map (BRIEF §5): Jun uses
BOTH allowed slots (07:30 + 00:30) → S2 impossible; **Aug also
uses both (07:30 + 00:30 among its 5 checks) → S2 impossible for
Aug too** (coordinator prep concurs). Every other month has at
least one of 07:30 / 00:30 free.

## 4. What Wave 0 blocks / does not block
- BLOCKED: any candidate whose features need Twelve DXY.
- NOT BLOCKED: Plan A S1 for Jan/Feb/Jul on FX symbols + volume
  columns (majors H1/M15, NEW8 M15 with guards) + correlated-symbol
  legs + labelled Dukascopy DOLLARIDX legs (H1 only, no volume
  conditions, provisional pip flagged).
- Sizing is not a gate in this round (BRIEF §0, chained ÷3 ruling).
