"""Versioned exit engine for the 2026-10-10 pooled-exits research improvement.

ONE engine shared across replay, portfolio accounting, live indication and
exports (command section 5). Entry logic is NEVER touched here: signals come
from the frozen ``core.monthly_runtime.build_history`` and are passed in.

ENGINE_VERSION = "exit-engine-20261010-v1"

Scenarios
---------
* ``baseline_current_exits`` — the app's original stored exits, taken from the
  signal frame's own ``Suggested TP Pips`` / ``Suggested SL Pips`` columns
  (mode A: fixed pips or completed-signal-ATR-multiplier, resolved at signal
  build time), with the legacy 48h hold cap and the legacy 1-pip admission
  gate ``(TP - 1) >= 0.5 * SL``. This is the "before" comparison leg.
* ``pooled_exits_research`` — pooled TP/SL from the command document Table 1
  (``Forex_Detailed_App_Improvement_Command.docx``; the
  ``Forex_Additional_Research.zip`` evidence package was never uploaded, so
  the doc text is the sole config source):
      EURJPY  TP 30 / SL 50 (fixed pips)
      EURNZD  TP 30 / SL 50 (fixed pips)
      USDJPY  TP 50 / SL 20 (fixed pips)
      GBPJPY  TP = 3 x ATR14 (clip 10-500 pips), SL = 2 x ATR14 (clip 10-100 pips)
  Entry gate ``(TP - 3) / (SL + 3) >= 0.5`` (3-pip research cost). Missing or
  nonpositive pre-entry ATR rejects the GBPJPY entry with a reason code.
  All other pairs are REJECTED in this named scenario. live_enabled = False.
  This is a NAMED EXPERIMENT, never a silent default change.

Both scenarios: 48h hold cap, original causal bias/danger/Friday rules,
check hours 06/07/10/11/12/13 UTC at minute 30, max 4 entries/check,
1 holding/symbol, max 20 holdings. Ranking logic unchanged.

Evaluation order per H1 bar (section 5 of the command):
  1. OPEN_CHECKS  — adverse gap through the stop  -> fill at the OBSERVED
                     open (never a fabricated stop quote), stop_gap=True;
                     favourable gap through the target -> fill at target
                     (TP gap capped at the target under this research policy).
  2. HOLD_CAP     — elapsed >= 48h -> close at the bar open.
  3. BIAS_FLIP / DANGER — from previously completed-bar information only.
  4. BARRIERS     — intrabar TP/SL touch; SL_FIRST default (conservative
                     stress view used by all selection/readiness gates),
                     TP_FIRST kept as the labelled historical view.
  5. FRIDAY_CLOSE — Friday 16:00 New-York bar -> close at the bar close.
                     Barriers are evaluated BEFORE the Friday close: a barrier
                     hit earlier in that bar always wins.

Ambiguous trades (one H1 candle touches both barriers) are flagged and carry
P/L under EACH priority: net_pips_sl_first / net_pips_tp_first. net_pips
follows the run's chosen priority.

Outcome states: CLOSED_KNOWN (finite exit price) / UNRESOLVED_UNKNOWN
(censored — P/L unknown, never converted to zero profit). A missing path is
UNKNOWN/CENSORED, never a zero-profit or a completed winning trade.

Costs: flat round-trip sensitivity {1, 3, 5} pips deducted EXACTLY ONCE per
trade: net_pips = gross_pips - cost_pips. These are labelled
"sensitivity — NOT a measured broker cost" (zero broker-verified rows exist).
Admission gates are scenario-fixed (baseline: legacy 1-pip gate; pooled: the
3-pip entry gate) so the 1/3/5 cost runs share identical trade sets and the
cost comparison is not confounded by admission changes.

R definitions (never mixed):
  * initial-stop R  = net_pips / SL_pips  (per trade; portfolio mean reported)
  * cost-inclusive R = net_pips / (SL_pips + cost_pips) (reported separately)
Never compare initial-stop R with cost-inclusive R as if the same risk unit.

Readiness flags per strategy row (section 19): data_quality_passed,
causal_replay_passed, development_screen_passed, fresh_evaluation_passed,
execution_model_verified, paper_forward_passed, live_approved.
live_approved stays FALSE everywhere in this deliverable.
The pooled scenario passes ONLY development_screen_passed (limited screen;
its CI includes losses and its 5-pip cost result is negative — both recorded).
"""
from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from core.monthly_backtest import make_tapes, TRADE_COLUMNS
from core.monthly_runtime import raw_frame, build_history, ENGINE_VERSION
from core.execution_policy_20261003 import checks_between
from core.improved_strategy_config import K_ENTRIES_PER_CHECK, MAX_HOLD_HOURS
from core import tpsl_price_calc_20261009 as _tpx

# ---------------------------------------------------------------- constants --
ENGINE_VERSION_EXIT = "exit-engine-20261010-v1"
CENSORSHIP_POLICY = "research_release_unknown"
EXIT_EVAL_ORDER = ("OPEN_CHECKS", "HOLD_CAP", "BIAS_FLIP", "DANGER", "BARRIERS", "FRIDAY_CLOSE")

SCENARIO_BASELINE = "baseline_current_exits"
SCENARIO_POOLED = "pooled_exits_research"

CHECK_HOURS = (6, 7, 10, 11, 12, 13)   # UTC hours; checks at minute 30
HOLD_CAP_HOURS = 48                     # 48h cap for both scenarios
COST_SCENARIOS_PIPS = (1.0, 3.0, 5.0)  # flat round-trip sensitivity set
COST_SENSITIVITY_LABEL = "sensitivity — NOT a measured broker cost"

# Pooled exits — SOLE source: command document Table 1 (the evidence ZIP was
# never uploaded). Shared across each pair's 12 months.
POOLED_CONFIG: Dict[str, dict] = {
    "EURJPY": {"tp_pips": 30.0, "sl_pips": 50.0, "basis": "FIXED_PIPS"},
    "EURNZD": {"tp_pips": 30.0, "sl_pips": 50.0, "basis": "FIXED_PIPS"},
    "USDJPY": {"tp_pips": 50.0, "sl_pips": 20.0, "basis": "FIXED_PIPS"},
    "GBPJPY": {"tp_mult": 3.0, "sl_mult": 2.0,
               "tp_clip": (10.0, 500.0), "sl_clip": (10.0, 100.0),
               "basis": "ATR14_MULTIPLIER"},
}
GATE_COST_PIPS = 3.0        # entry gate cost assumption (section 6)
GATE_MIN_RR = 0.5           # (TP - 3) / (SL + 3) >= 0.5
BASELINE_GATE_COST = 1.0    # legacy admission-gate convention

# The 27 rebuilt entry/exit combinations: FAILED training qualification
# (five past-only walk-forward folds admitted none). Kept DISABLED —
# diagnostics only, separate rule version.
REBUILT_FAMILY_VERSION = "rebuilt-entry-exit-v1"
REBUILT_FAMILY_COUNT = 27
REBUILT_FAMILY_STATUS = "REJECTED"
REBUILT_FAMILY_REASON = (
    "FAILED training qualification: all 27 rebuilt entry/exit combinations "
    "failed the training screen and the five past-only walk-forward selection "
    "folds admitted no candidate. DISABLED — diagnostics only."
)

# Strategy statuses (command Table 2).
STATUS_REJECTED = "REJECTED"
STATUS_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
STATUS_DEVELOPMENT_CANDIDATE = "DEVELOPMENT_CANDIDATE"
STATUS_PAPER_PENDING = "PAPER_PENDING"
STATUS_FRESH_VALIDATED = "FRESH_VALIDATED"

READINESS_FLAGS = (
    "data_quality_passed",
    "causal_replay_passed",
    "development_screen_passed",
    "fresh_evaluation_passed",
    "execution_model_verified",
    "paper_forward_passed",
    "live_approved",
)

BROKER_VERIFIED_ROWS = 0  # this source has zero broker-verified rows

EXTRA_TRADE_COLUMNS = [
    "trade_id", "scenario", "exit_mode", "intrabar_priority", "cost_scenario",
    "cost_total_pips", "fee_pips", "swap_pips",
    "censorship_policy", "outcome_state",
    "net_pips_sl_first", "net_pips_tp_first",
    "gross_pips_sl_first", "gross_pips_tp_first",
    "initial_stop_R", "cost_inclusive_R",
    "tp_basis", "sl_basis", "atr_pips", "atr_bar_time",
    "entry_gate", "entry_gate_rr", "config_hash",
    "target_reference", "broker_verified_rows",
]


# ------------------------------------------------------------ config -------
def pooled_config_canonical() -> str:
    """Canonical JSON of the pooled config (config-hash input)."""
    return json.dumps(POOLED_CONFIG, sort_keys=True, separators=(",", ":"))


def config_hash() -> str:
    """SHA-256 over pooled config + gate + engine version + eval order."""
    payload = json.dumps({
        "pooled_config": json.loads(pooled_config_canonical()),
        "gate_cost_pips": GATE_COST_PIPS,
        "gate_min_rr": GATE_MIN_RR,
        "engine_version": ENGINE_VERSION_EXIT,
        "exit_eval_order": list(EXIT_EVAL_ORDER),
        "hold_cap_hours": HOLD_CAP_HOURS,
        "check_hours": list(CHECK_HOURS),
        "baseline_gate_cost": BASELINE_GATE_COST,
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


# ------------------------------------------------------------ entry gate ----
def entry_gate(tp_pips: float, sl_pips: float,
               cost_pips: float = GATE_COST_PIPS) -> Tuple[bool, float, str]:
    """(TP - cost) / (SL + cost) >= 0.5. Returns (passed, rr, reason_code)."""
    if not np.isfinite(tp_pips) or not np.isfinite(sl_pips) or sl_pips <= 0:
        return False, float("nan"), "REJECT_INVALID_TP_SL"
    rr = (tp_pips - cost_pips) / (sl_pips + cost_pips)
    if rr >= GATE_MIN_RR:
        return True, rr, "PASS"
    return False, rr, "REJECT_REWARD_RISK"


def resolve_pooled_exits(symbol: str, atr_pips, atr_bar_time) -> dict:
    """Resolve pooled TP/SL for one check. Rejections carry a reason code.

    Returns either {'tp_pips','sl_pips','basis','atr_pips','atr_bar_time',
    'gate_rr'} or {'rejected': <reason>}. No silent fallbacks.
    """
    cfg = POOLED_CONFIG.get(symbol)
    if cfg is None:
        return {"rejected": "REJECT_PAIR_NOT_IN_SCENARIO"}
    if cfg["basis"] == "FIXED_PIPS":
        tp, sl = float(cfg["tp_pips"]), float(cfg["sl_pips"])
        atr_out, atr_ts = np.nan, None
    else:  # GBPJPY: ATR14 multiplier with clips, pre-entry available ATR only
        if atr_pips is None or (isinstance(atr_pips, float) and np.isnan(atr_pips)):
            return {"rejected": "REJECT_ATR_MISSING"}
        a = float(atr_pips)
        if not np.isfinite(a) or a <= 0:
            return {"rejected": "REJECT_ATR_NONPOSITIVE"}
        lo, hi = cfg["tp_clip"]
        tp = min(max(cfg["tp_mult"] * a, lo), hi)
        lo, hi = cfg["sl_clip"]
        sl = min(max(cfg["sl_mult"] * a, lo), hi)
        atr_out, atr_ts = a, atr_bar_time
    ok, rr, reason = entry_gate(tp, sl, GATE_COST_PIPS)
    if not ok:
        return {"rejected": reason}
    return {"tp_pips": tp, "sl_pips": sl, "basis": cfg["basis"],
            "atr_pips": atr_out, "atr_bar_time": atr_ts, "gate_rr": rr}


def resolve_baseline_exits(signal: dict) -> dict:
    """Original stored exits from the signal frame's own columns (mode A)."""
    tp = float(signal.get("Suggested TP Pips", np.nan))
    sl = float(signal.get("Suggested SL Pips", np.nan))
    ok, rr, reason = entry_gate(tp, sl, BASELINE_GATE_COST)
    if not ok:
        return {"rejected": "REJECT_REWARD_RISK_LEGACY" if reason == "REJECT_REWARD_RISK" else reason}
    return {"tp_pips": tp, "sl_pips": sl, "basis": "ORIGINAL_STORED_EXIT",
            "atr_pips": np.nan, "atr_bar_time": None, "gate_rr": rr}


# ------------------------------------------------------------ ATR at check --
def atr_available_at_check(tape: dict, check) -> Tuple[float, object]:
    """Latest completed bar whose availability is no later than the check.

    Fast path normally lands on entry index i-2; the availability lookup is
    the causal general form (retains the slow path when availability is
    delayed). Returns (atr_pips, bar_open_time) or (nan, None).
    """
    check = pd.Timestamp(check)
    if check.tzinfo is None:
        check = check.tz_localize("UTC")
    else:
        check = check.tz_convert("UTC")
    avail = tape.get("availability")
    atr = tape.get("atr")
    if avail is None or atr is None:
        return np.nan, None
    mask = np.asarray(pd.DatetimeIndex(avail) <= check)
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return np.nan, None
    j = int(idx[-1])
    a = float(atr[j])
    if not np.isfinite(a) or a <= 0:
        return np.nan, None
    pip = tape["pip"]
    bar_open = tape["times"][j]
    if getattr(bar_open, "tzinfo", None) is None:
        bar_open = pd.Timestamp(bar_open).tz_localize("UTC")
    return a / pip, bar_open


# ------------------------------------------------------------ single trade --
def _utc(t):
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def replay_trade_engine(signal: dict, tape: dict, *, exits: dict,
                        priority: str = "SL_FIRST",
                        cost_pips: float = 1.0,
                        hold_hours: int = HOLD_CAP_HOURS,
                        scenario: str = SCENARIO_POOLED,
                        exit_mode: str = "",
                        end_time=None) -> dict | None:
    """Single-trade exit replay with the section-5 evaluation order.

    ``exits``: resolved dict from resolve_pooled_exits / resolve_baseline_exits
    (must NOT contain 'rejected'). Returns None only when exits are invalid
    (defensive; admission gates should already exclude these).
    """
    if priority not in ("SL_FIRST", "TP_FIRST"):
        raise ValueError(f"priority must be SL_FIRST or TP_FIRST, got {priority!r}")
    if float(cost_pips) not in COST_SCENARIOS_PIPS:
        raise ValueError(f"cost_pips must be one of {COST_SCENARIOS_PIPS}, got {cost_pips!r}")
    if exits is None or "rejected" in exits:
        return None
    tp, sl = float(exits["tp_pips"]), float(exits["sl_pips"])
    if not np.isfinite(tp + sl) or tp <= 0 or sl <= 0:
        return None
    entry_at = _utc(signal["Datetime"])
    check = _utc(signal["check_at"])
    if entry_at != check + pd.Timedelta(minutes=30):
        raise ValueError("Replay fill must be 30 minutes after the UTC check")
    i = tape["lookup"].get(entry_at)
    if i is None:
        return None
    side = 1 if signal["Direction"] == "BUY" else -1
    pip = tape["pip"]
    px = float(tape["prices"][i, 0])
    _tp = _tpx.target_prices(px, side, tp, sl, signal["Symbol"],
                             price_basis="INDICATIVE")
    target, stop = float(_tp["tp_price"]), float(_tp["sl_price"])
    hold = int(hold_hours)
    danger = bool(signal.get("Danger Enabled", False))
    cost = float(cost_pips)
    limit = _utc(end_time) if end_time is not None else None
    price = np.nan
    xt = entry_at
    reason = "CENSORED"
    ambiguous = False
    stop_gap = False
    times = tape["times"]
    for j in range(i, len(times)):
        at = _utc(times[j])
        op, hi, lo, cl = (float(v) for v in tape["prices"][j])
        if (limit is not None and at >= limit) or (j > i and at - _utc(times[j - 1]) != pd.Timedelta(hours=1)):
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
        # 2. HOLD_CAP (scheduled exit at the bar open).
        if at - entry_at >= pd.Timedelta(hours=hold):
            price = op
            xt = at
            reason = "HOLD_CAP"
            break
        # 3. BIAS_FLIP / DANGER from previously completed-bar info only.
        known = (bool(tape["exit_known"][j]) if "exit_known" in tape
                 else j > 0 and pd.notna(tape["availability"][j - 1]) and _utc(tape["availability"][j - 1]) <= at)
        if j > i and known:
            bias = tape["exit_bias"][j] if "exit_bias" in tape else tape["bias"][j - 1]
            if bias == -side:
                price = op
                xt = at
                reason = "BIAS_FLIP"
                break
            po, ph, pl, pc = (float(v) for v in tape["prices"][j - 1])
            atr = tape["exit_atr"][j] if "exit_atr" in tape else tape["atr"][j - 1]
            rng = tape["exit_range"][j] if "exit_range" in tape else ph - pl
            body = tape["exit_body"][j] if "exit_body" in tape else pc - po
            if danger and np.isfinite(atr) and atr > 0 and rng > 3 * atr and side * body < -0.5 * atr:
                price = op
                xt = at
                reason = "DANGER"
                break
        # 4. BARRIERS — intrabar touch; SL_FIRST default, TP_FIRST labelled view.
        hit_sl = lo <= stop if side > 0 else hi >= stop
        hit_tp = hi >= target if side > 0 else lo <= target
        if hit_sl or hit_tp:
            ambiguous = bool(hit_sl and hit_tp)
            if priority == "SL_FIRST":
                price = stop if hit_sl else target
                reason = "SL" if hit_sl else "TP"
            else:  # TP_FIRST — explicitly-labelled historical view
                price = target if hit_tp else stop
                reason = "TP" if hit_tp else "SL"
            xt = at + pd.Timedelta(hours=1)
            break
        # 5. FRIDAY_CLOSE — barriers evaluated first; never a future Friday
        #    price before a barrier hit earlier in that bar.
        if bool(tape["friday"][j]):
            price = cl
            xt = at + pd.Timedelta(hours=1)
            reason = "FRIDAY_CLOSE"
            break
        if j + 1 == len(times):
            xt = at + pd.Timedelta(hours=1)
            break
        if _utc(times[j + 1]) - at != pd.Timedelta(hours=1):
            xt = _utc(times[j + 1])
            break
    gross = side * (price - px) / pip if np.isfinite(price) else np.nan
    net = gross - cost if np.isfinite(gross) else np.nan  # deducted EXACTLY ONCE
    # Ambiguous trades carry P/L under EACH priority.
    if ambiguous:
        gross_sl_first = side * (stop - px) / pip
        gross_tp_first = side * (target - px) / pip
        net_sl_first = gross_sl_first - cost
        net_tp_first = gross_tp_first - cost
    else:
        gross_sl_first = gross_tp_first = gross
        net_sl_first = net_tp_first = net
    net_pips = net_sl_first if priority == "SL_FIRST" else net_tp_first
    outcome = "CLOSED_KNOWN" if np.isfinite(price) else "UNRESOLVED_UNKNOWN"
    r_stop = net_pips / sl if np.isfinite(net_pips) else np.nan          # initial-stop R
    r_cost = net_pips / (sl + cost) if np.isfinite(net_pips) else np.nan  # cost-inclusive R (labelled separately)
    atr_ts = exits.get("atr_bar_time")
    return dict(
        Symbol=signal["Symbol"],
        **{"Equation ID": signal["Equation ID"], "Active S Column": signal["Active S Column"]},
        check_at=check, entry_at=entry_at, exit_at=xt,
        entry_side="BUY" if side == 1 else "SELL", entry_price=px,
        tp_price=target, sl_price=stop, exit_price=price, exit_reason=reason,
        gross_pips=gross, net_pips=net_pips, tp_pips=tp, sl_pips=sl,
        hold_hours=(xt - entry_at).total_seconds() / 3600, max_hold_hours=hold,
        danger=danger, spread_pips=cost, slippage_pips=0.0,
        fee_pips=0.0, swap_pips=0.0,
        ambiguous=ambiguous, stop_gap=stop_gap, censored=not np.isfinite(price),
        signal_bar_open=signal.get("signal_bar_open"), research_only=True,
        trade_id=None, scenario=scenario, exit_mode=exit_mode,
        intrabar_priority=priority, cost_scenario=f"flat_{cost:g}pip",
        cost_total_pips=cost,
        censorship_policy=CENSORSHIP_POLICY, outcome_state=outcome,
        net_pips_sl_first=net_sl_first, net_pips_tp_first=net_tp_first,
        gross_pips_sl_first=gross_sl_first, gross_pips_tp_first=gross_tp_first,
        initial_stop_R=r_stop, cost_inclusive_R=r_cost,
        tp_basis=exits.get("basis", ""), sl_basis=exits.get("basis", ""),
        atr_pips=exits.get("atr_pips", np.nan), atr_bar_time=atr_ts,
        entry_gate="PASS", entry_gate_rr=float(exits.get("gate_rr", np.nan)),
        config_hash=config_hash(),
        target_reference="next H1 open (research reference; executable fills need bid/ask)",
        broker_verified_rows=BROKER_VERIFIED_ROWS,
    )


def _improved_rank_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Same ranking frame helper as the frozen engines (ranking is entry logic;
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


def run_portfolio(raw, *, signals: pd.DataFrame, scenario: str,
                  cost_pips: float = 1.0, priority: str = "SL_FIRST",
                  hold_hours: int = HOLD_CAP_HOURS,
                  entry_start=None, entry_end=None,
                  research_end=None) -> dict:
    """Portfolio replay through the versioned exit engine.

    ``signals`` must be the prebuilt frame from build_history (the SAME frame
    for every scenario — this keeps entry signals identical across the
    before/after comparison). Ranking, K=4/check, no-duplicate-symbol and the
    20-holding cap are unchanged entry-layer rules.
    """
    if scenario not in (SCENARIO_BASELINE, SCENARIO_POOLED):
        raise ValueError(f"unknown scenario {scenario!r}")
    if priority not in ("SL_FIRST", "TP_FIRST"):
        raise ValueError("priority must be SL_FIRST or TP_FIRST")
    if float(cost_pips) not in COST_SCENARIOS_PIPS:
        raise ValueError(f"cost_pips must be one of {COST_SCENARIOS_PIPS}")
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
    cfg_hash = config_hash()
    exit_mode = ("pooled_exits_research_v1" if scenario == SCENARIO_POOLED
                 else "baseline_current_exits_v1")
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
                    tape = tapes.get(row.Symbol)
                    if tape is None:
                        continue
                    sig = row.to_dict()
                    if scenario == SCENARIO_POOLED:
                        atr_pips, atr_ts = atr_available_at_check(tape, check)
                        exits = resolve_pooled_exits(row.Symbol, atr_pips, atr_ts)
                    else:
                        exits = resolve_baseline_exits(sig)
                    key = f"{row.Symbol}:{row['Equation ID']}"
                    if "rejected" in exits:
                        rejected.append(f"{key}:{exits['rejected']}")
                        continue
                    trade = replay_trade_engine(
                        sig, tape, exits=exits, priority=priority,
                        cost_pips=float(cost_pips), hold_hours=hold_hours,
                        scenario=scenario, exit_mode=exit_mode,
                        end_time=research_end)
                    if trade is None:
                        rejected.append(f"{key}:REJECT_INVALID_EXITS")
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
    for c in EXTRA_TRADE_COLUMNS:
        if c not in ledger.columns:
            ledger[c] = np.nan
    return dict(trades=ledger, checks=pd.DataFrame(decisions), tapes=tapes,
                signals=columns,
                meta=dict(scenario=scenario, cost_pips=float(cost_pips),
                          priority=priority, hold_hours=hold_hours,
                          engine_version=ENGINE_VERSION_EXIT,
                          strategy_engine=ENGINE_VERSION,
                          config_hash=cfg_hash,
                          max_concurrent_holdings=maximum,
                          eval_order=" > ".join(EXIT_EVAL_ORDER),
                          censorship_policy=CENSORSHIP_POLICY))


# ---------------------------------------------------------------- metrics ---
def portfolio_metrics(ledger: pd.DataFrame, *, cost_pips: float,
                      priority: str = "SL_FIRST") -> dict:
    """Honest portfolio metrics. Drawdown aggregates simultaneous exits first."""
    tr = ledger.copy() if len(ledger) else ledger
    n = len(tr)
    net_col = "net_pips_sl_first" if priority == "SL_FIRST" else "net_pips_tp_first"
    closed = tr.loc[~tr["censored"].fillna(False).astype(bool)] if n else tr
    nc = len(closed)
    net = float(closed[net_col].sum()) if nc else 0.0
    wins = closed.loc[closed[net_col] > 0] if nc else closed
    losses = closed.loc[closed[net_col] < 0] if nc else closed
    win_rate = float(len(wins) / nc * 100) if nc else float("nan")
    avg_win = float(wins[net_col].mean()) if len(wins) else float("nan")
    avg_loss = float(losses[net_col].mean()) if len(losses) else float("nan")
    gp = float(wins[net_col].sum()) if len(wins) else 0.0
    gl = float(-losses[net_col].sum()) if len(losses) else 0.0
    pf = gp / gl if gl > 0 else float("nan")
    ev = float(net / nc) if nc else float("nan")
    # initial-stop R = net_pips / SL_pips per trade (labelled); portfolio mean.
    r_stop = (closed[net_col] / closed["sl_pips"]).replace([np.inf, -np.inf], np.nan)
    mean_r = float(r_stop.mean()) if nc else float("nan")
    total_r = float(closed[net_col].sum() / closed["sl_pips"].sum()) if nc and closed["sl_pips"].sum() else float("nan")
    # cost-inclusive R reported separately, never mixed with initial-stop R.
    r_cost = (closed[net_col] / (closed["sl_pips"] + cost_pips)).replace([np.inf, -np.inf], np.nan)
    mean_r_cost = float(r_cost.mean()) if nc else float("nan")
    # realized drawdown on closed-trade equity, simultaneous exits aggregated.
    dd = 0.0
    if nc:
        ordered = closed.sort_values("exit_at", kind="mergesort")
        agg = ordered.groupby("exit_at", sort=True)[net_col].sum()
        eq = agg.cumsum()
        peak = np.maximum.accumulate(np.r_[0.0, eq.to_numpy()])[1:]
        dd = float(np.minimum.accumulate(eq.to_numpy() - peak).min())
    romad = float(net / -dd) if dd < 0 else float("nan")
    # max consecutive losses
    mcl = 0
    cur = 0
    if nc:
        for v in closed.sort_values("exit_at", kind="mergesort")[net_col].to_numpy():
            cur = cur + 1 if v < 0 else 0
            mcl = max(mcl, cur)
    mix = closed["exit_reason"].value_counts().to_dict() if nc else {}
    unknown = int(tr["censored"].fillna(False).astype(bool).sum()) if n else 0
    ambiguous = int(closed["ambiguous"].fillna(False).astype(bool).sum()) if nc else 0
    return {
        "attempts": n, "closed_trades": nc, "unknown_outcomes": unknown,
        "net_pips": round(net, 2),
        "net_pips_tp_first_view": round(float(closed["net_pips_tp_first"].sum()), 2) if nc else 0.0,
        "win_rate_pct": round(win_rate, 2) if nc else float("nan"),
        "avg_win_pips": round(avg_win, 2) if nc else float("nan"),
        "avg_loss_pips": round(avg_loss, 2) if nc else float("nan"),
        "profit_factor": round(pf, 4) if nc and np.isfinite(pf) else float("nan"),
        "expected_value_pips": round(ev, 4) if nc else float("nan"),
        "mean_initial_stop_R_per_trade": round(mean_r, 4) if nc else float("nan"),
        "total_initial_stop_R": round(total_r, 4) if nc else float("nan"),
        "mean_cost_inclusive_R_per_trade": round(mean_r_cost, 4) if nc else float("nan"),
        "realized_drawdown_pips": round(dd, 2),
        "romad": round(romad, 4) if np.isfinite(romad) else float("nan"),
        "max_consecutive_losses": mcl,
        "ambiguous_trades": ambiguous,
        "exit_mix": {k: int(v) for k, v in mix.items()},
        "r_definitions": {
            "initial_stop_R": "net_pips / SL_pips per trade (1 planned stop = 1 R); "
                              "portfolio reports mean per-trade and total (sum net / sum SL).",
            "cost_inclusive_R": "net_pips / (SL_pips + cost_pips) per trade — "
                                "reported separately, never compared with initial-stop R.",
        },
    }


# ------------------------------------------------------------ cache key -----
def cache_key(*, scenario: str, cost_pips: float, priority: str,
              data_sha256: str, entry_start: str, entry_end: str) -> str:
    """Full input identity. Any change invalidates cached results."""
    payload = json.dumps({
        "scenario": scenario, "cost_pips": float(cost_pips), "priority": priority,
        "data_sha256": data_sha256, "entry_start": entry_start, "entry_end": entry_end,
        "config_hash": config_hash(), "engine_version": ENGINE_VERSION_EXIT,
        "strategy_engine": ENGINE_VERSION,
        "hold_cap_hours": HOLD_CAP_HOURS, "check_hours": list(CHECK_HOURS),
        "k_per_check": K_ENTRIES_PER_CHECK, "max_holdings": 20,
        "eval_order": list(EXIT_EVAL_ORDER),
        "censorship_policy": CENSORSHIP_POLICY,
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


class StaleCacheError(Exception):
    """Raised when a cached result's key does not match current inputs."""


def assert_cache_fresh(stored_key: str, **kwargs) -> None:
    expected = cache_key(**kwargs)
    if stored_key != expected:
        raise StaleCacheError(
            f"stale cache: stored key {stored_key[:16]}… != current {expected[:16]}…; "
            "data, exits, rules, costs, priority, schedule or sizing changed — recompute")


# ------------------------------------------------------------ status rows ---
def build_status_rows(registry_entries: List[dict],
                      pooled_samples: Dict[str, dict] | None = None,
                      data_quality_passed: bool = True) -> pd.DataFrame:
    """All-240 strategy status rows for the pooled scenario + 27 rebuilt rows.

    pooled_samples: (symbol, month) -> {'closed': int, 'unknown': int} from the
    pooled portfolio run.
    """
    pooled_samples = pooled_samples or {}
    rows: List[dict] = []
    pooled_syms = set(POOLED_CONFIG)
    for e in registry_entries:
        sym, month = e["symbol"], int(e["month"])
        s = e["s_column"]
        in_scenario = sym in pooled_syms
        samples = pooled_samples.get((sym, month), {})
        if in_scenario:
            status = STATUS_DEVELOPMENT_CANDIDATE
            reason = ("Passed the limited pooled development screen at pair level "
                      "(EURJPY/EURNZD/GBPJPY/USDJPY pooled exits). A symbol-level "
                      "pooled screen is NOT a statistical approval of this individual "
                      "monthly strategy; CI includes losses; 5-pip cost result negative.")
            dev = True
        else:
            status = STATUS_REJECTED
            reason = ("Pair not eligible in the named pooled_exits_research scenario "
                      "(EURJPY/EURNZD/GBPJPY/USDJPY only).")
            dev = False
        cfg = POOLED_CONFIG.get(sym, {})
        rows.append({
            "s_column": s, "equation_id": e["equation_id"], "symbol": sym,
            "myanmar_month": month, "direction": e["direction"],
            "rule_version": "monthly-equation-v1 (original entry equations, unchanged)",
            "tp_pips": cfg.get("tp_pips", np.nan) if cfg.get("basis") == "FIXED_PIPS" else np.nan,
            "sl_pips": cfg.get("sl_pips", np.nan) if cfg.get("basis") == "FIXED_PIPS" else np.nan,
            "tp_basis": cfg.get("basis", "NOT_ASSIGNED") if in_scenario else "NOT_ASSIGNED",
            "sl_basis": cfg.get("basis", "NOT_ASSIGNED") if in_scenario else "NOT_ASSIGNED",
            "samples_closed_trades": int(samples.get("closed", 0)),
            "samples_unknown": int(samples.get("unknown", 0)),
            "status": status, "rejection_reason": "" if in_scenario else reason,
            "status_note": reason if in_scenario else "",
            "data_quality_passed": bool(data_quality_passed),
            "causal_replay_passed": True,
            "development_screen_passed": dev,
            "fresh_evaluation_passed": False,
            "execution_model_verified": False,
            "paper_forward_passed": False,
            "live_approved": False,
        })
    for k in range(1, REBUILT_FAMILY_COUNT + 1):
        rows.append({
            "s_column": f"RB{k:02d}", "equation_id": f"rebuilt-combo-{k:02d}",
            "symbol": "", "myanmar_month": "", "direction": "",
            "rule_version": REBUILT_FAMILY_VERSION,
            "tp_pips": np.nan, "sl_pips": np.nan,
            "tp_basis": "DISABLED", "sl_basis": "DISABLED",
            "samples_closed_trades": 0, "samples_unknown": 0,
            "status": REBUILT_FAMILY_STATUS, "rejection_reason": REBUILT_FAMILY_REASON,
            "status_note": "",
            "data_quality_passed": bool(data_quality_passed),
            "causal_replay_passed": False,
            "development_screen_passed": False,
            "fresh_evaluation_passed": False,
            "execution_model_verified": False,
            "paper_forward_passed": False,
            "live_approved": False,
        })
    df = rows and pd.DataFrame(rows)
    order = sorted([r for r in rows if r["s_column"].startswith("S")],
                   key=lambda r: int(r["s_column"][1:]))
    order += [r for r in rows if r["s_column"].startswith("RB")]
    return pd.DataFrame(order)


# ------------------------------------------------------------ exports -------
def export_metadata(*, data_sha256: str, zip_sha256: str, registry_sha256: str,
                    scenario: str, cost_pips: float, priority: str,
                    entry_start: str, entry_end: str, seeds: dict,
                    trial_budget: dict, ledger_sha256: str = "") -> dict:
    """Reproduction metadata carried with EVERY export."""
    return {
        "source_csv_sha256": data_sha256,
        "original_zip_sha256": zip_sha256,
        "exit_registry_sha256": registry_sha256,
        "pooled_scenario_sha256": hashlib.sha256(
            pooled_config_canonical().encode()).hexdigest(),
        "ledger_sha256": ledger_sha256,
        "engine_version": ENGINE_VERSION_EXIT,
        "strategy_engine": ENGINE_VERSION,
        "scenario": scenario,
        "scenario_config_hash": config_hash(),
        "cost_pips": float(cost_pips),
        "cost_label": COST_SENSITIVITY_LABEL,
        "intrabar_priority": priority,
        "seeds": seeds,
        "trial_budget": trial_budget,
        "entry_window_utc": {"start": entry_start, "end": entry_end},
        "check_schedule": "UTC hours 06/07/10/11/12/13 at minute 30",
        "portfolio_limits": {"k_per_check": K_ENTRIES_PER_CHECK,
                             "max_holdings": 20, "one_holding_per_symbol": True},
        "hold_cap_hours": HOLD_CAP_HOURS,
        "exit_eval_order": list(EXIT_EVAL_ORDER),
        "censorship_policy": CENSORSHIP_POLICY,
        "broker_verified_rows": BROKER_VERIFIED_ROWS,
        "r_definitions": {
            "initial_stop_R": "net_pips / SL_pips",
            "cost_inclusive_R": "net_pips / (SL_pips + cost_pips) — labelled separately",
        },
        "cache_key": cache_key(scenario=scenario, cost_pips=cost_pips,
                               priority=priority, data_sha256=data_sha256,
                               entry_start=entry_start, entry_end=entry_end),
    }


def signals_fingerprint(signals: pd.DataFrame) -> str:
    """Canonical fingerprint of the entry-signal frame (proves runs share it)."""
    cols = ["check_at", "Symbol", "Equation ID", "Active S Column", "Direction",
            "Strategy Hit Count"]
    sub = signals[[c for c in cols if c in signals]].copy()
    sub = sub.sort_values([c for c in cols if c in sub.columns], kind="mergesort")
    return hashlib.sha256(sub.to_csv(index=False).encode()).hexdigest()
