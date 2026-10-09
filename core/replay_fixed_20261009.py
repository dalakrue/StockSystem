"""Fixed replay engine wrapper for the 2026-10-09 exit-registry work.

Reuses the frozen entry/signal machinery WITHOUT modification:
  * ``core.monthly_runtime.build_history``  — signal generation (entry logic,
    READ-ONLY; never touched)
  * ``core.monthly_backtest.make_tapes``    — per-symbol H1 tapes
  * ``core.monthly_backtest.metrics``       — realized closed-trade metrics
  * ``core.execution_policy_20261003.checks_between`` — check schedule
  * ``core.improved_strategy_config``       — K_ENTRIES_PER_CHECK, rank_score

What this module changes (exits only):
  * intrabar priority is a parameter: SL_FIRST (default) or TP_FIRST
    (explicitly-labelled legacy comparison mode);
  * per-trade TP/SL/hold/danger are passed in explicitly (registry-driven),
    never read from ``signal['Suggested TP Pips']``;
  * evaluation order is explicit and config-driven (see EXIT_EVAL_ORDER).

EVALUATION ORDER (per H1 bar), documented here and in the code:
  1. OPEN_CHECKS   — adverse gap through the stop  -> fill at the OBSERVED
                     open (never a fabricated stop quote), stop_gap=True;
                     favourable gap through the target -> fill at target.
  2. FRIDAY_CLOSE  — Friday 16:00 New-York bar -> close at the bar close.
  3. HOLD_CAP      — elapsed time >= hold_hours -> close at the bar open.
  4. BIAS_FLIP / DANGER — from completed-bar information only
                     (bias flips against the side; danger = range > 3x ATR
                     with adverse body < -0.5x ATR, when enabled).
  5. BARRIERS      — intrabar TP/SL touch; SL-first by default.

Deliberate deviation from legacy ``core/monthly_backtest.py`` ::
``replay_trade``: legacy evaluated Friday close AFTER intrabar barriers; this
engine evaluates all scheduled exits before barriers, as specified. The gap
rule, censorship handling and once-deducted cost are preserved.

Ambiguous trades (one H1 candle touches both barriers) are flagged and carry
P/L under EACH priority: net_pips_sl_first / net_pips_tp_first; net_pips
follows the run's chosen priority.

Outcome states: CLOSED_KNOWN (finite exit price) / UNRESOLVED_UNKNOWN
(censored — P/L unknown, never converted to zero profit). OPEN_MARKED exists
in the taxonomy for live books; replay never leaves positions open.
Censorship policy: 'research_release_unknown' — research bookkeeping releases
a censored interval at the next observed quote with UNKNOWN P/L; this is not
proof a live holding closed.

Entry-signal identity: the caller builds signals ONCE with build_history and
passes the same frame to the legacy and the fixed run; admission (ranking,
K per check, no duplicate symbol) is unchanged, so entry signals are
identical. Signals whose equation fails the mode-D risk gate are skipped at
admission with a machine-readable reason recorded per check.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from core.monthly_backtest import make_tapes, metrics, TRADE_COLUMNS
from core.monthly_runtime import raw_frame, build_history, ENGINE_VERSION
from core.execution_policy_20261003 import checks_between
from core.improved_strategy_config import K_ENTRIES_PER_CHECK
from core import cost_model_20261009 as _cost

ENGINE_WRAPPER_VERSION = "replay-fixed-20261009-v1"
CENSORSHIP_POLICY = "research_release_unknown"
EXIT_EVAL_ORDER = ("OPEN_CHECKS", "FRIDAY_CLOSE", "HOLD_CAP", "BIAS_FLIP", "DANGER", "BARRIERS")

EXTRA_TRADE_COLUMNS = [
    "trade_id", "exit_mode", "intrabar_priority", "cost_scenario",
    "censorship_policy", "outcome_state",
    "net_pips_sl_first", "net_pips_tp_first",
]


def _utc(t):
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def replay_trade_fixed(signal: dict, tape: dict, *, tp_pips: float, sl_pips: float,
                       hold_hours: int, danger_enabled: bool,
                       priority: str = "SL_FIRST",
                       cost_scenario: str = "legacy_1pip",
                       exit_mode: str = "D_active_compatible",
                       end_time=None) -> dict | None:
    """Single-trade exit replay with explicit exits and intrabar priority.

    See module docstring for the evaluation order. Returns None when the exit
    parameters are invalid (defensive; overrides are pre-gated by the
    registry's risk gate).
    """
    if priority not in ("SL_FIRST", "TP_FIRST"):
        raise ValueError(f"priority must be SL_FIRST or TP_FIRST, got {priority!r}")
    entry_at = _utc(signal["Datetime"])
    check = _utc(signal["check_at"])
    if entry_at != check + pd.Timedelta(minutes=30):
        raise ValueError("Replay fill must be 30 minutes after the UTC check")
    i = tape["lookup"].get(entry_at)
    if i is None:
        return None
    side = 1 if signal["Direction"] == "BUY" else -1
    tp = float(tp_pips)
    sl = float(sl_pips)
    pip = tape["pip"]
    cost = _cost.total_cost_pips(cost_scenario, fill_type="OHLC_MID")
    if not np.isfinite(tp + sl) or (tp - cost) < 0.5 * sl:
        return None  # defensive: registry risk gate should already exclude these
    px = float(tape["prices"][i, 0])
    target = px + side * tp * pip
    stop = px - side * sl * pip
    hold = int(hold_hours)
    danger = bool(danger_enabled)
    limit = _utc(end_time) if end_time is not None else tape["times"][-1] + pd.Timedelta(hours=1)
    price = np.nan
    xt = entry_at
    reason = "CENSORED"
    ambiguous = False
    stop_gap = False
    for j in range(i, len(tape["times"])):
        at = tape["times"][j]
        op, hi, lo, cl = tape["prices"][j]
        if at >= limit or (j > i and at - tape["times"][j - 1] != pd.Timedelta(hours=1)):
            xt = at
            break
        if not np.isfinite([op, hi, lo, cl]).all():
            xt = at
            break
        # 1. OPEN_CHECKS — gaps fill at the observed open, never fabricated.
        if side * (op - stop) <= 0:
            price = op
            xt = at
            reason = "SL"
            stop_gap = not np.isclose(op, stop, rtol=0, atol=1e-12)
            break
        if side * (op - target) >= 0:
            price = target
            xt = at
            reason = "TP"
            break
        # 2. FRIDAY_CLOSE (scheduled exit, before barriers).
        if tape["friday"][j]:
            price = cl
            xt = at + pd.Timedelta(hours=1)
            reason = "FRIDAY_CLOSE"
            break
        # 3. HOLD_CAP (scheduled exit).
        if at - entry_at >= pd.Timedelta(hours=hold):
            price = op
            xt = at
            reason = "HOLD_CAP"
            break
        # 4. BIAS_FLIP / DANGER from completed-bar info only.
        known = (bool(tape["exit_known"][j]) if "exit_known" in tape
                 else j > 0 and pd.notna(tape["availability"][j - 1]) and tape["availability"][j - 1] <= at)
        if j > i and known:
            bias = tape["exit_bias"][j] if "exit_bias" in tape else tape["bias"][j - 1]
            if bias == -side:
                price = op
                xt = at
                reason = "BIAS_FLIP"
                break
            po, ph, pl, pc = tape["prices"][j - 1]
            atr = tape["exit_atr"][j] if "exit_atr" in tape else tape["atr"][j - 1]
            rng = tape["exit_range"][j] if "exit_range" in tape else ph - pl
            body = tape["exit_body"][j] if "exit_body" in tape else pc - po
            if danger and rng > 3 * atr and side * body < -0.5 * atr:
                price = op
                xt = at
                reason = "DANGER"
                break
        # 5. BARRIERS — intrabar touch; SL_FIRST default, TP_FIRST legacy mode.
        hit_sl = lo <= stop if side > 0 else hi >= stop
        hit_tp = hi >= target if side > 0 else lo <= target
        if hit_sl or hit_tp:
            ambiguous = bool(hit_sl and hit_tp)
            if priority == "SL_FIRST":
                price = stop if hit_sl else target
                reason = "SL" if hit_sl else "TP"
            else:  # TP_FIRST — explicitly-labelled legacy comparison mode
                price = target if hit_tp else stop
                reason = "TP" if hit_tp else "SL"
            xt = at + pd.Timedelta(hours=1)
            break
        if j + 1 == len(tape["times"]):
            xt = at + pd.Timedelta(hours=1)
            break
        if tape["times"][j + 1] - at != pd.Timedelta(hours=1):
            xt = tape["times"][j + 1]
            break
    gross = side * (price - px) / pip if np.isfinite(price) else np.nan
    net = _cost.net_pips(gross, cost_scenario, fill_type="OHLC_MID")
    # Ambiguous trades carry P/L under EACH priority.
    if ambiguous:
        gross_sl = side * (stop - px) / pip
        gross_tp = side * (target - px) / pip
        net_sl_first = _cost.net_pips(gross_sl, cost_scenario, fill_type="OHLC_MID")
        net_tp_first = _cost.net_pips(gross_tp, cost_scenario, fill_type="OHLC_MID")
    else:
        net_sl_first = net_tp_first = net
    outcome = "CLOSED_KNOWN" if np.isfinite(price) else "UNRESOLVED_UNKNOWN"
    return dict(
        Symbol=signal["Symbol"],
        **{"Equation ID": signal["Equation ID"], "Active S Column": signal["Active S Column"]},
        check_at=check, entry_at=entry_at, exit_at=xt,
        entry_side="BUY" if side == 1 else "SELL", entry_price=px,
        tp_price=target, sl_price=stop, exit_price=price, exit_reason=reason,
        gross_pips=gross, net_pips=net, tp_pips=tp, sl_pips=sl,
        hold_hours=(xt - entry_at).total_seconds() / 3600, max_hold_hours=hold,
        danger=danger, spread_pips=1.0, slippage_pips=0.0,
        ambiguous=ambiguous, stop_gap=stop_gap, censored=not np.isfinite(price),
        signal_bar_open=signal.get("signal_bar_open"), research_only=True,
        exit_mode=exit_mode, intrabar_priority=priority, cost_scenario=cost_scenario,
        censorship_policy=CENSORSHIP_POLICY, outcome_state=outcome,
        net_pips_sl_first=net_sl_first, net_pips_tp_first=net_tp_first,
    )


def _improved_rank_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Same ranking frame helper as legacy replay (ranking is entry logic;
    reproduced, not changed)."""
    from core.improved_strategy_config import rank_score as _rs
    f = frame.copy()
    if "Improved Rank" not in f.columns:
        _ck = f.get("check_at")
        hrs = (pd.to_datetime(_ck, utc=True, errors="coerce").dt.hour.fillna(-1).astype(int)
               if _ck is not None else pd.Series(-1, index=f.index))
        base = pd.to_numeric(f.get("ranking_score", pd.Series(0, index=f.index)), errors="coerce").fillna(0)
        f["Improved Rank"] = [_rs(s, int(h), r) for s, h, r in zip(f["Symbol"].astype(str), hrs, base)]
    return f


def replay_portfolio_fixed(raw, *, signals: pd.DataFrame,
                           exit_overrides: Dict[Tuple[str, str], dict],
                           priority: str = "SL_FIRST",
                           cost_scenario: str = "legacy_1pip",
                           hold_hours: int = 48,
                           exit_mode: str = "D_active_compatible",
                           entry_start=None, entry_end=None,
                           research_end=None) -> dict:
    """Portfolio replay with registry-driven exits.

    ``signals`` must be the prebuilt frame from build_history (the SAME frame
    passed to the legacy run) — this is what keeps entry signals identical.
    ``exit_overrides``: (symbol, equation_id) -> {'tp_pips','sl_pips'} or
    {'rejected': <machine-readable reason>}. Rejected equations are skipped at
    admission; the reason is recorded per check.
    """
    if priority not in ("SL_FIRST", "TP_FIRST"):
        raise ValueError("priority must be SL_FIRST or TP_FIRST")
    raw = raw_frame(raw)
    columns = signals.copy()
    if "Strategy Engine" not in columns or not columns["Strategy Engine"].eq(ENGINE_VERSION).all():
        raise ValueError("Stale strategy cache; rebuild S1–S240")
    start = _utc(entry_start) if entry_start is not None else _utc(raw.Datetime.min())
    end = _utc(entry_end) if entry_end is not None else _utc(raw.Datetime.max())
    tapes = make_tapes(raw)
    opportunities = columns.loc[columns["Strategy Hit Count"].eq(1)].copy()
    opportunities["check_at"] = pd.to_datetime(opportunities.check_at, utc=True, format="mixed")
    opportunities = opportunities.loc[opportunities.check_at.between(start, end)]
    opportunities = _improved_rank_frame(opportunities)
    bycheck = {t: g for t, g in opportunities.groupby("check_at", sort=True)}
    held: Dict[str, pd.Timestamp] = {}
    trades: List[dict] = []
    decisions: List[dict] = []
    maximum = 0
    for check in checks_between(start, end):
        fill = check + pd.Timedelta(minutes=30)
        held = {s: x for s, x in held.items() if x > check}
        group = bycheck.get(check, pd.DataFrame())
        admitted: List[dict] = []
        rejected: List[str] = []
        if len(group):
            ranked = (group.sort_values(["Improved Rank", "Symbol", "Equation ID"],
                                        ascending=[False, True, True], kind="mergesort")
                           .drop_duplicates("Symbol"))
            top = ranked.Symbol.head(K_ENTRIES_PER_CHECK).tolist()
            if len(held) < 20:
                for _, row in ranked.iterrows():
                    if row.Symbol in held:
                        continue
                    if len(admitted) >= K_ENTRIES_PER_CHECK or len(held) + len(admitted) >= 20:
                        break
                    key = (row.Symbol, row["Equation ID"])
                    ov = exit_overrides.get(key)
                    if ov is None:
                        rejected.append(f"{row.Symbol}:{row['Equation ID']}:NO_REGISTRY_ENTRY")
                        continue
                    if "rejected" in ov:
                        rejected.append(f"{row.Symbol}:{row['Equation ID']}:{ov['rejected']}")
                        continue
                    tape = tapes.get(row.Symbol)
                    trade = (replay_trade_fixed(row.to_dict(), tape, tp_pips=ov["tp_pips"],
                                                sl_pips=ov["sl_pips"], hold_hours=hold_hours,
                                                danger_enabled=bool(row.get("Danger Enabled", False)),
                                                priority=priority, cost_scenario=cost_scenario,
                                                exit_mode=exit_mode, end_time=research_end)
                             if tape else None)
                    if trade is None:
                        continue
                    trade["trade_id"] = len(trades) + 1
                    trades.append(trade)
                    held[trade["Symbol"]] = trade["exit_at"]
                    maximum = max(maximum, len(held))
                    admitted.append(trade)
            reason = ("ENTRY" if admitted else "MAX_20_HOLDINGS" if len(held) >= 20
                      else "TOP_FOUR_HELD")
        else:
            top = []
            reason = "NO_TRIGGER"
        decisions.append(dict(check_at=check, fill_at=fill, top_four=",".join(top),
                              held_symbols=",".join(sorted(set(held) - {t["Symbol"] for t in admitted})),
                              selected=",".join(t["Symbol"] for t in admitted),
                              equation_id=",".join(t["Equation ID"] for t in admitted),
                              exit_rejections=";".join(rejected), reason=reason))
    cols = TRADE_COLUMNS + EXTRA_TRADE_COLUMNS
    ledger = pd.DataFrame(trades) if trades else pd.DataFrame(columns=cols)
    if len(ledger) and not set(EXTRA_TRADE_COLUMNS).issubset(ledger.columns):
        for c in EXTRA_TRADE_COLUMNS:
            if c not in ledger.columns:
                ledger[c] = np.nan
    result = metrics(ledger)
    result["Max Concurrent Holdings"] = maximum
    reused_start = _utc("2025-10-01")
    reused_end = _utc("2026-10-05 07:00")
    reused = ledger.loc[ledger.entry_at.ge(reused_start) & ledger.entry_at.lt(reused_end)] if len(ledger) else ledger
    result["Reused-test metrics"] = metrics(reused)
    result["Engine"] = ENGINE_VERSION
    result["Engine Wrapper"] = ENGINE_WRAPPER_VERSION
    result["Exit Eval Order"] = " > ".join(EXIT_EVAL_ORDER)
    result["Intrabar Priority"] = priority
    result["Censorship Policy"] = CENSORSHIP_POLICY
    return dict(trades=ledger, checks=pd.DataFrame(decisions), metrics=result,
                signals=columns, tapes=tapes)


def signals_fingerprint(signals: pd.DataFrame) -> str:
    """Canonical fingerprint of the entry-signal frame (proves two runs used
    identical entry signals)."""
    import hashlib
    cols = ["check_at", "Symbol", "Equation ID", "Active S Column", "Direction", "Strategy Hit Count"]
    sub = signals[[c for c in cols if c in signals]].copy()
    sub = sub.sort_values([c for c in cols if c in sub.columns], kind="mergesort")
    canon = sub.to_csv(index=False)
    return __import__("hashlib").sha256(canon.encode()).hexdigest()


def admission_fingerprint(checks: pd.DataFrame) -> Dict[pd.Timestamp, str]:
    """check_at -> selected symbols mapping, for cross-run admission comparison."""
    return {pd.Timestamp(r.check_at): r.selected for r in checks.itertuples()}
