"""Field 10 rank governance utilities.

This module is intentionally configuration-first.  Future rank tuning should alter
RANK_GOVERNANCE_CONFIG or add aliases here instead of rewriting the Field 10 UI.
The Field 10 authority table remains the only trusted rank publisher; this helper
only calculates transparent row scores and gates from already-published evidence.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
import math

from core.system_contract import stable_hash

RANK_GOVERNANCE_VERSION = "20260709.merged_buy_sell_100pip_v3"
FORMULA_VERSION = "authority_score_100pip_regime_transition_priority_v3"

RANK_GOVERNANCE_CONFIG: dict[str, Any] = {
    # User-facing rank priority for Field 10: first prefer symbols whose BUY/SELL
    # bias has the highest estimated chance to travel at least 100 pips in the
    # next completed 4H horizon, then prefer Higher-Standard regime agreement,
    # then prefer low 6H transition risk.  The remaining components keep the
    # table reliable without allowing WAIT/over-filtering to dominate.
    "weights": {
        "probability_100pip_4h": 0.28,
        "higher_standard_regime_bias": 0.22,
        "transition_safety_6h": 0.20,
        "reliability": 0.12,
        "data_quality": 0.07,
        "expected_return": 0.05,
        "tail_event_safety": 0.03,
        "calibration": 0.02,
        "uniqueness": 0.01,
        "session_robustness": 0.00,
    },
    "quality_scores": {
        "A": 100.0,
        "B": 86.0,
        "C": 68.0,
        "D": 42.0,
        "F": 0.0,
        "FAILED": 0.0,
        "UNKNOWN": 45.0,
    },
    "minimum_trusted_score": 72.0,
    "minimum_review_score": 55.0,
    "minimum_trusted_sample": 100,
    "top_n_highlight": 4,
}

UNAVAILABLE_TEXT = {"", "NAN", "NONE", "<NA>", "UNAVAILABLE", "NOT AVAILABLE", "NULL"}


def _is_available(value: Any) -> bool:
    return value is not None and str(value).strip().upper() not in UNAVAILABLE_TEXT


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        n = float(str(value).replace("%", "").replace(",", ""))
        return default if math.isnan(n) or math.isinf(n) else n
    except Exception:
        return default


def _clip(value: Any, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, _num(value, lo)))


def _pct(value: Any, default: float = 50.0) -> float:
    n = _num(value, default)
    if -1.0 <= n <= 1.0:
        n *= 100.0
    return _clip(n, 0.0, 100.0)


def _text(value: Any) -> str:
    return str(value or "").strip().upper()


def _buy_sell_bias(src: Mapping[str, Any], bg: Mapping[str, Any] | None = None) -> str:
    """Force Field 10 final bias to BUY/SELL only.

    The authority table no longer publishes WAIT as a direction.  When source
    evidence says WAIT/neutral, this resolver uses expected-return sign,
    higher-standard regime text, calibrated probability, then a stable symbol
    tie-breaker to choose the least-bad BUY/SELL side while keeping risk gates
    and trust status visible separately.
    """
    maps: tuple[Mapping[str, Any], ...] = (src, bg or {})
    for row in maps:
        for key in (
            "Higher-Standard Regime Bias", "Higher Standard Regime Bias",
            "Field 3 Higher-Standard Bias", "Field 3 Higher Bias",
            "Stable Daily Bias", "Less-Risky Bias", "Final Less-Risky Bias",
            "Final Less-Risky Bias to Hold", "Decision", "Flow Proxy Bias",
        ):
            text = _text(row.get(key))
            if "BUY" in text:
                return "BUY"
            if "SELL" in text:
                return "SELL"
    for key in ("Expected Return 4H", "Expected Return 3H", "Expected Return 6H", "Expected Return 12H", "Net Expected Value", "WeightedNetEV"):
        val = _val(*(maps), keys=(key, f"{key} (%)"), default=None)
        if _is_available(val):
            n = _num(val, 0.0)
            if n > 0:
                return "BUY"
            if n < 0:
                return "SELL"
    p = _pct(_val(*(maps), keys=("Regime Probability", "Calibrated Probability", "Reliability", "Probability Profit 6H"), default=50.0), 50.0)
    if p > 50:
        return "BUY"
    if p < 50:
        return "SELL"
    return "BUY" if int(str(stable_hash([src.get("Symbol") or "", p]))[-1], 16) % 2 == 0 else "SELL"


def _pip_size(symbol: Any) -> float:
    text = _text(symbol).replace("/", "").replace("_", "")
    if text.startswith("XAU") or text.endswith("XAU"):
        return 0.1
    if "JPY" in text:
        return 0.01
    return 0.0001


def _expected_return_4h(src: Mapping[str, Any], bg: Mapping[str, Any]) -> float:
    # Prefer explicit 4H columns.  Otherwise interpolate from 3H/6H/12H windows.
    explicit = _val(bg, src, keys=("Expected Return 4H", "Expected Return 4H (%)"), default=None)
    if _is_available(explicit):
        return _num(explicit, 0.0)
    r3 = _val(bg, src, keys=("Expected Return 3H", "Expected Return 3H (%)"), default=None)
    r6 = _val(bg, src, keys=("Expected Return 6H", "Expected Return 6H (%)"), default=None)
    r12 = _val(bg, src, keys=("Expected Return 12H", "Expected Return 12H (%)"), default=None)
    if _is_available(r3) and _is_available(r6):
        return _num(r3, 0.0) + (_num(r6, 0.0) - _num(r3, 0.0)) / 3.0
    if _is_available(r6):
        return _num(r6, 0.0) * (4.0 / 6.0)
    if _is_available(r12):
        return _num(r12, 0.0) / 3.0
    ev = _val(src, keys=("InstitutionalUtility", "Risk-adjusted Expected Value", "WeightedNetEV", "Net Expected Value"), default=0.0)
    return _num(ev, 0.0) * 0.50


def projected_4h_move_pips(src: Mapping[str, Any], bg: Mapping[str, Any]) -> float:
    symbol = src.get("Symbol") or bg.get("Symbol") or "EURUSD"
    close = _num(_val(src, bg, keys=("Close", "Last Close", "Current Price", "Price"), default=0.0), 0.0)
    expected = _expected_return_4h(src, bg)
    pip = _pip_size(symbol)
    # If expected return is percent-like, convert through price.  If no price is
    # available, keep a conservative percent-to-pip proxy so rank still works.
    if close > 0 and abs(expected) <= 10:
        return round(abs((expected / 100.0) * close) / pip, 2)
    if abs(expected) <= 10:
        return round(abs(expected) * 100.0, 2)
    return round(abs(expected), 2)


def probability_100pip_4h(src: Mapping[str, Any], bg: Mapping[str, Any]) -> dict[str, Any]:
    p_base = _pct(_val(bg, src, keys=("Probability Profit 3H", "Probability Profit 6H", "Calibrated Probability", "Regime Probability", "Reliability"), default=50.0), 50.0)
    pips = projected_4h_move_pips(src, bg)
    transition_6h = _pct(_val(bg, src, keys=("Transition Risk 6H", "Transition Risk 6H (%)"), default=55.0), 55.0)
    # Convert projected movement to a smooth target score; 100 pips is the target.
    distance_score = _clip((pips / 100.0) * 100.0, 0.0, 100.0)
    transition_safety = _clip(100.0 - transition_6h, 0.0, 100.0)
    probability = round(_clip(0.55 * p_base + 0.30 * distance_score + 0.15 * transition_safety), 2)
    priority = round(_clip(0.70 * probability + 0.30 * distance_score), 2)
    status = "100_PIP_TARGET_STRONG" if probability >= 70 and pips >= 100 else "100_PIP_TARGET_POSSIBLE" if probability >= 55 else "100_PIP_TARGET_WEAK"
    return {
        "Probability 100 Pip Move 4H": probability,
        "Projected 4H Move Pips": pips,
        "100 Pip 4H Priority": priority,
        "100 Pip 4H Target Status": status,
        "100 Pip 4H Method": "p_base + expected-return pips + 6H transition safety; H4 target=100 pips",
    }


def higher_standard_regime_bias_score(src: Mapping[str, Any], bg: Mapping[str, Any], final_bias: str) -> float:
    hsb = _val(
        src, bg,
        keys=(
            "Higher-Standard Regime Bias", "Higher Standard Regime Bias",
            "Field 3 Higher-Standard Bias", "Field 3 Higher Bias",
            "Higher Standard Bias", "Higher-Standard Bias",
            "Higher Standard Regime", "Higher-Standard Regime",
        ),
        default="UNAVAILABLE",
    )
    text = _text(hsb)
    if final_bias and final_bias in text:
        return 100.0
    if "BUY" in text or "SELL" in text:
        return 35.0
    p = _pct(_val(bg, src, keys=("Regime Probability", "Calibrated Probability"), default=50.0), 50.0)
    return round(_clip(55.0 + abs(p - 50.0) * 0.9), 2)


def transition_safety_6h_score(src: Mapping[str, Any], bg: Mapping[str, Any]) -> float:
    risk = _pct(_val(bg, src, keys=("Transition Risk 6H", "Transition Risk 6H (%)"), default=55.0), 55.0)
    return round(_clip(100.0 - risk), 2)


def _val(*maps: Mapping[str, Any], keys: Sequence[str], default: Any = "UNAVAILABLE") -> Any:
    for row in maps:
        if not isinstance(row, Mapping):
            continue
        for key in keys:
            if key in row and _is_available(row.get(key)):
                return row.get(key)
    return default


def quality_letter(value: Any) -> str:
    text = str(value or "UNKNOWN").upper().strip()
    if text.startswith("A"):
        return "A"
    if text.startswith("B"):
        return "B"
    if text.startswith("C"):
        return "C"
    if text.startswith("D"):
        return "D"
    if text.startswith("F") or "FAIL" in text or "MISSING" in text:
        return "F"
    return "UNKNOWN"


def data_completeness_score(src: Mapping[str, Any], sample: int, loaded_symbols: int, universe_size: int) -> float:
    quality = quality_letter(_val(src, keys=("Data Quality Grade", "Data Quality"), default="UNKNOWN"))
    q_score = RANK_GOVERNANCE_CONFIG["quality_scores"].get(quality, 45.0)
    sample_score = _clip(sample / 600.0 * 100.0, 0.0, 100.0)
    universe_score = _clip((loaded_symbols / max(1, universe_size)) * 100.0, 0.0, 100.0)
    return round(0.55 * q_score + 0.30 * sample_score + 0.15 * universe_score, 4)


def _expected_return_score(src: Mapping[str, Any], bg: Mapping[str, Any]) -> float:
    # Works for percent-style expected returns and utility-style EV columns.
    candidates = [
        _num(_val(bg, src, keys=("Expected Return 1H", "Expected Return 3H"), default=0.0)),
        _num(_val(bg, src, keys=("Expected Return 6H", "Expected Return 12H"), default=0.0)),
        _num(_val(bg, src, keys=("Expected Return 24H", "Expected Return 36H"), default=0.0)),
        _num(_val(src, keys=("InstitutionalUtility", "Risk-adjusted Expected Value", "WeightedNetEV", "Net Expected Value"), default=0.0)),
    ]
    # Convert a small FX return/utility into a stable 0-100 opportunity score.
    directional_strength = max(abs(x) for x in candidates)
    signed_best = max(candidates, key=lambda x: abs(x)) if candidates else 0.0
    base = 50.0 + max(-35.0, min(35.0, signed_best * 35.0))
    strength_bonus = min(15.0, directional_strength * 25.0)
    return round(_clip(base + strength_bonus), 4)


def _transition_safety_score(src: Mapping[str, Any], bg: Mapping[str, Any]) -> float:
    risks = []
    for window in ("1H", "3H", "6H", "12H", "24H", "36H"):
        v = _val(bg, src, keys=(f"Transition Risk {window}", f"Transition Risk {window} (%)"), default=None)
        if _is_available(v):
            risks.append(_pct(v, 55.0))
    if not risks:
        return 45.0
    near_term = max(risks[:3]) if len(risks) >= 3 else max(risks)
    full_horizon = max(risks)
    return round(_clip(100.0 - (0.70 * near_term + 0.30 * full_horizon)), 4)


def _tail_event_safety_score(src: Mapping[str, Any], bg: Mapping[str, Any]) -> float:
    tail_safety = str(_val(bg, src, keys=("Tail Safety", "Tail-Risk Veto"), default="UNKNOWN")).upper()
    event_permission = str(_val(bg, src, keys=("Event-Risk Permission", "Event Risk Permission"), default="CHECK")).upper()
    absorption = _pct(_val(bg, src, keys=("Absorption Percentage", "News Absorption Score"), default=50.0), 50.0)
    tail_score = 88.0 if "SAFE" in tail_safety or "NO" == tail_safety else 58.0 if "CAUTION" in tail_safety else 25.0 if "VETO" in tail_safety or "YES" == tail_safety else 55.0
    event_score = 90.0 if event_permission == "ALLOW" else 62.0 if event_permission == "CAUTION" else 25.0 if event_permission == "BLOCK" else 55.0
    return round(_clip(0.40 * tail_score + 0.35 * event_score + 0.25 * absorption), 4)


def _calibration_score(src: Mapping[str, Any], bg: Mapping[str, Any]) -> float:
    probability = _pct(_val(bg, src, keys=("Calibrated Probability", "Whole-Day Bias Lock Confidence", "Regime Probability", "Reliability"), default=50.0), 50.0)
    brier = _num(_val(bg, src, keys=("Brier Score", "Brier score"), default=0.25), 0.25)
    ece = _num(_val(bg, src, keys=("Expected Calibration Error", "ECE"), default=0.12), 0.12)
    probability_strength = _clip(abs(probability - 50.0) * 2.0, 0.0, 100.0)
    brier_score = _clip(100.0 - brier * 180.0, 0.0, 100.0)
    ece_score = _clip(100.0 - ece * 220.0, 0.0, 100.0)
    return round(0.35 * probability_strength + 0.40 * brier_score + 0.25 * ece_score, 4)


def _uniqueness_score(src: Mapping[str, Any], bg: Mapping[str, Any]) -> float:
    unique = _val(bg, src, keys=("Unique Opportunity Score",), default=None)
    if _is_available(unique):
        return round(_pct(unique, 70.0), 4)
    penalty = _pct(_val(bg, src, keys=("Duplicate Exposure Penalty", "Correlation penalty using Ledoit-Wolf shrinkage and DCC"), default=15.0), 15.0)
    return round(_clip(100.0 - penalty), 4)


def reliability_grade(score: float) -> str:
    if score >= 88:
        return "A+ INSTITUTIONAL"
    if score >= 78:
        return "A TRUSTED"
    if score >= 68:
        return "B RELIABLE"
    if score >= 55:
        return "C REVIEW"
    if score >= 40:
        return "D DEGRADED"
    return "F DO_NOT_TRUST"


def governance_for_symbol(
    *,
    symbol: str,
    src: Mapping[str, Any],
    bg: Mapping[str, Any],
    sample: int,
    quality: str,
    entry_permission: str,
    publication_status: str,
    loaded_symbols: int,
    universe_size: int,
    snapshot_hash: str,
) -> dict[str, Any]:
    weights = RANK_GOVERNANCE_CONFIG["weights"]
    final_bias = _buy_sell_bias(src, bg)
    p100 = probability_100pip_4h(src, bg)
    high_standard = higher_standard_regime_bias_score(src, bg, final_bias)
    transition_6h = transition_safety_6h_score(src, bg)
    data_quality = data_completeness_score(src, sample, loaded_symbols, universe_size)
    reliability = _pct(_val(bg, src, keys=("Calibrated Probability", "Whole-Day Bias Lock Confidence", "Regime Probability", "Reliability"), default=50.0), 50.0)
    expected_return = _expected_return_score(src, bg)
    transition_safety = _transition_safety_score(src, bg)
    tail_event = _tail_event_safety_score(src, bg)
    calibration = _calibration_score(src, bg)
    uniqueness = _uniqueness_score(src, bg)
    session = _pct(_val(bg, src, keys=("Session Robustness Score", "Session Score"), default=55.0), 55.0)
    components = {
        "probability_100pip_4h": p100["100 Pip 4H Priority"],
        "higher_standard_regime_bias": high_standard,
        "transition_safety_6h": transition_6h,
        "data_quality": data_quality,
        "reliability": reliability,
        "expected_return": expected_return,
        "transition_safety": transition_safety,
        "tail_event_safety": tail_event,
        "calibration": calibration,
        "uniqueness": uniqueness,
        "session_robustness": session,
    }
    raw_score = sum(components[k] * float(weights.get(k, 0.0)) for k in weights)
    q = quality_letter(quality)
    entry_text = str(entry_permission or "").upper()
    hard_block = sample <= 0 or q == "F" or entry_text.startswith("BLOCK")
    partial_penalty = 7.5 if publication_status != "COMPLETE" else 0.0
    sample_penalty = 8.0 if 0 < sample < int(RANK_GOVERNANCE_CONFIG["minimum_trusted_sample"]) else 0.0
    score = round(_clip(raw_score - partial_penalty - sample_penalty), 4)
    if hard_block:
        score = round(min(score, 22.0), 4)
    min_trusted = float(RANK_GOVERNANCE_CONFIG["minimum_trusted_score"])
    min_review = float(RANK_GOVERNANCE_CONFIG["minimum_review_score"])
    if hard_block:
        trust_status = "NOT_TRUSTED_DATA_MISSING_OR_BLOCKED"
        can_trust = "NO"
        placement = "BOTTOM_BLOCKED"
        risk_gate = "BLOCK"
    elif score >= min_trusted and publication_status == "COMPLETE":
        trust_status = "TRUSTED_AUTHORITY"
        can_trust = "YES"
        placement = "TOP_AUTHORITY_CANDIDATE"
        risk_gate = "ALLOW"
    elif score >= min_review:
        trust_status = "REVIEW_AUTHORITY_PARTIAL_OR_MEDIUM_CONFIDENCE"
        can_trust = "CAUTION"
        placement = "MIDDLE_REVIEW"
        risk_gate = "CAUTION"
    else:
        trust_status = "SUPPORTING_ONLY_LOW_CONFIDENCE"
        can_trust = "NO"
        placement = "LOW_CONFIDENCE"
        risk_gate = "CAUTION"
    return {
        "Authority Score": score,
        "Authority Score Components": components,
        **p100,
        "Higher-Standard Regime Bias Priority": round(high_standard, 2),
        "Transition Safety 6H Priority": round(transition_6h, 2),
        "Reliability Grade": reliability_grade(score),
        "Trust Status": trust_status,
        "Can Trust Rank?": can_trust,
        "Authority Placement": placement,
        "Risk Control Gate": risk_gate,
        "Data Completeness %": round(data_quality, 2),
        "Transition Safety %": round(transition_safety, 2),
        "Event/Tail Safety %": round(tail_event, 2),
        "Calibration Quality %": round(calibration, 2),
        "Unique Opportunity %": round(uniqueness, 2),
        "Stable Tie-Breaker": stable_hash([snapshot_hash, symbol]),
        "Rank Governance Version": RANK_GOVERNANCE_VERSION,
        "Formula Version": FORMULA_VERSION,
        "Rank Freeze Reason": "Rank can change only when selected-symbol universe, selected timeframe, or completed selected-timeframe candle changes.",
        "Cross-Section Rank Reason": (
            f"score={score:.2f}; 100pip4H={p100['Probability 100 Pip Move 4H']:.1f}; "
            f"higher_standard={high_standard:.1f}; transition6H_safety={transition_6h:.1f}; "
            f"data={data_quality:.1f}; reliability={reliability:.1f}; publication={publication_status}"
        ),
    }


def sort_key_for_authority(row: Mapping[str, Any]) -> tuple[Any, ...]:
    placement_order = {
        "TOP_AUTHORITY_CANDIDATE": 0,
        "MIDDLE_REVIEW": 1,
        "LOW_CONFIDENCE": 2,
        "BOTTOM_BLOCKED": 3,
    }
    return (
        placement_order.get(str(row.get("Authority Placement") or "LOW_CONFIDENCE"), 2),
        -_num(row.get("100 Pip 4H Priority"), 0.0),
        -_num(row.get("Higher-Standard Regime Bias Priority"), 0.0),
        _num(row.get("Transition Risk 6H"), 55.0),
        -_num(row.get("Transition Safety 6H Priority"), 0.0),
        -_num(row.get("Authority Score"), 0.0),
        -_num(row.get("Whole-Day Bias Lock Confidence"), 0.0),
        -_num(row.get("Evidence Sample Size"), 0.0),
        str(row.get("Stable Tie-Breaker") or row.get("Symbol") or ""),
    )


__all__ = [
    "RANK_GOVERNANCE_VERSION", "FORMULA_VERSION", "RANK_GOVERNANCE_CONFIG",
    "quality_letter", "governance_for_symbol", "sort_key_for_authority", "reliability_grade",
    "probability_100pip_4h", "projected_4h_move_pips",
]
