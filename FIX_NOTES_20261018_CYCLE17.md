# Fix notes — Cycle 17 (2026-10-18): 40 processes, no honest improvement — app UNCHANGED

Base: copy of `Forex_App_Fixed_S1_S240_Cycle16__16.zip`
(SHA-256 `1d4b4275509990c8...`). The C16 zip was NOT modified.
This zip is `Forex_App_Fixed_S1_S240_Cycle17__17.zip`.

## 1. Verdict: NO UPGRADE — FT-C01 retained

Cycle 17 ran 40 processes across 16 weakness perspectives (worst-10
equations by max DD, RoMAD, Sharpe, win rate, trade count, gross pips,
total TP pips, total SL pips, profit factor, recovery factor,
trades/week, avg hold time, avg pips/trade, max consecutive wins, max
consecutive losses, worst single loss), re-mining improved versions of
the weakest equations from all prior cycles (C12–C16 pool: 185 unique
equations). 18/40 pass the 10-check battery.

Best C17 process by RoMAD among 10-check PASS is C17-SL1 (tighter stops
on the worst-SL-loss equations): unseen +1,267.81 pips / 206 trades /
RoMAD 44.64 vs FT-C01's +1,283.12 / 167 / 44.52 (+0.27%), DD −28.40 vs
−28.82 (no worse), but Sharpe worse (12.80 vs 16.71) and net slightly
lower.

A 5,000-resample bootstrap head-to-head on unseen gives
P(C17-SL1 RoMAD > FT-C01 RoMAD) = 0.576 — barely better than a coin
flip, 90% interval [−27.3, +36.4]. The +0.27% is selection noise, not
an honest beat (same standard applied in Cycle 16, where FZ-C03 at
P=0.497 was rejected). Per the strict upgrade rule (upgrade only on an
honest RoMAD beat), the app is NOT upgraded.

Next-best honest results: C17-CL3 (cooldown after consecutive losses:
+1,286.7 / RoMAD 38.78), C17-SL4 (wider TP: +2,658.7 net but RoMAD
32.38, DD −82.1 — raw net without risk-adjusted edge).

## 2. What changed (and only this)

| File | Change |
|---|---|
| `FIX_NOTES_20261018_CYCLE17.md` | NEW (this file). |
| `PACKAGE_MANIFEST.json` | Entry for the new file refreshed. |

Equations (FT-C01: 4 SELL mean-reversion + trailing 1.25/0.4 + dynamic k
RuleA), S1–S240 mapping, ranking, stats, check hours: byte-identical
(verified by `diff -rq` — only the two files above differ).
Sizing recommendation unchanged: N = $20.00 (no re-run, no new winner).

## 3. Cycle 17 findings (honest negatives)

- Improving the worst equations per perspective mostly fails: 22/40
  processes fail the 10-check. The worst legs are worst for a reason —
  re-mining rarely rescues them (e.g., C17-RC2: only 1 of 12 re-mined
  variants passed screening; C17-EV1: discovery EV gain collapsed to
  +3.2 unseen — textbook overfit).
- Tighter stops (SL1) matched FT-C01's RoMAD but could not honestly
  beat it; wider TP (SL4) doubled net but at 2× drawdown.
- Cooldown after consecutive losses (CL3) is the most structurally
  interesting PASS (+1,286.7 / RoMAD 38.78) but still below FT-C01.
- Tail-risk caps (WL1/WL2) pass but at much lower RoMAD (6.6/18.2).
- 206 new processes across C13/C14/C16/C17 have now failed to beat
  FT-C01 on RoMAD; C15's FT-C01 remains the only promoted improvement.
