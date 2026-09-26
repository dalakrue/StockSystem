"""Read-only Decision 11: Medium-Standard Regime Bias.

This module consumes the already calculated canonical payload.  It does not
fetch data, train a model, or alter the protected ten-decision engine.
"""
from __future__ import annotations

from typing import Any, Mapping


WEIGHTS = {
    "regime_alignment": 0.30,
    "regime_reliability": 0.20,
    "adx_di": 0.15,
    "volatility_suitability": 0.10,
    "forecast_agreement": 0.10,
    "market_quality": 0.10,
    "conflict_penalty": 0.05,
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if out == out else default
    except Exception:
        return default


def _pct(value: Any, default: float = 50.0) -> float:
    out = _number(value, default)
    if 0 <= out <= 1:
        out *= 100.0
    return max(0.0, min(100.0, out))


def _direction(value: Any) -> float:
    text = str(value or "").upper()
    if any(token in text for token in ("BULL", "BUY", "UP", "LONG")):
        return 1.0
    if any(token in text for token in ("BEAR", "SELL", "DOWN", "SHORT")):
        return -1.0
    return 0.0


def _find(payload: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    wanted = {str(name).lower().replace("_", " ") for name in names}
    stack = [payload]
    visited: set[int] = set()
    while stack:
        item = stack.pop(0)
        if id(item) in visited:
            continue
        visited.add(id(item))
        for key, value in item.items():
            normalized = str(key).lower().replace("_", " ")
            if normalized in wanted:
                return value
            if isinstance(value, Mapping) and len(stack) < 120:
                stack.append(value)
    return default


def build_medium_standard_regime_bias(canonical: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build a deterministic support decision from existing canonical values."""
    canonical = _mapping(canonical)
    regime = _mapping(canonical.get("regime"))
    final = _mapping(canonical.get("final_decision"))
    reliability = _mapping(canonical.get("reliability"))

    h1 = regime.get("h1_regime", _find(canonical, "h1 regime", default=regime.get("major_regime", "UNKNOWN")))
    h4 = regime.get("h4_regime", _find(canonical, "h4 regime", default="UNKNOWN"))
    d1 = regime.get("d1_regime", _find(canonical, "d1 regime", default="UNKNOWN"))
    regime_votes = [_direction(h1), _direction(h4), _direction(d1)]
    regime_signal = sum(regime_votes) / 3.0

    rel_pct = _pct(
        regime.get("regime_reliability", regime.get("reliability", reliability.get("overall_reliability", _find(canonical, "reliability", default=50))))
    )
    regime_reliability = regime_signal * (rel_pct / 100.0)

    adx = _number(_find(canonical, "adx", "adx value", default=20.0), 20.0)
    plus_di = _number(_find(canonical, "plus di", "+di", "plus_di", default=0.0), 0.0)
    minus_di = _number(_find(canonical, "minus di", "-di", "minus_di", default=0.0), 0.0)
    di_signal = 0.0
    if abs(plus_di - minus_di) > 1e-9:
        di_signal = max(-1.0, min(1.0, (plus_di - minus_di) / max(abs(plus_di) + abs(minus_di), 1.0)))
    adx_strength = max(0.0, min(1.0, (adx - 12.0) / 28.0))
    adx_di_signal = di_signal * adx_strength

    volatility = _pct(_find(canonical, "volatility suitability", "volatility score", "market quality", default=50.0))
    volatility_signal = regime_signal * (volatility / 100.0)

    forecast_agreement_raw = _find(canonical, "forecast agreement", "forecast_agreement", default=50.0)
    forecast_direction = _direction(_find(canonical, "forecast direction", "directional market view", default=final.get("directional_market_view", "WAIT")))
    forecast_signal = forecast_direction * (_pct(forecast_agreement_raw) / 100.0)

    market_quality = _pct(_find(canonical, "market quality", "market_quality", default=50.0))
    market_signal = (regime_signal or forecast_direction) * (market_quality / 100.0)

    conflict_text = str(_find(canonical, "conflict status", "conflict warning", default="") or "")
    counter_text = str(_find(canonical, "counter trend", "counter-trend", default="") or "")
    has_conflict = any(token in (conflict_text + " " + counter_text).upper() for token in ("CONFLICT", "TRUE", "YES", "COUNTER"))
    conflict_signal = -(regime_signal or forecast_direction) if has_conflict else 0.0

    components = {
        "regime_alignment": regime_signal,
        "regime_reliability": regime_reliability,
        "adx_di": adx_di_signal,
        "volatility_suitability": volatility_signal,
        "forecast_agreement": forecast_signal,
        "market_quality": market_signal,
        "conflict_penalty": conflict_signal,
    }
    signed = sum(WEIGHTS[name] * components[name] for name in WEIGHTS)
    signed = max(-1.0, min(1.0, signed))
    strength = abs(signed)
    score = round(5.0 + signed * 5.0, 2)

    # WAIT remains deliberately easier to reach than an unsupported directional label.
    if strength < 0.16 or market_quality < 30 or rel_pct < 30:
        decision = "WAIT"
    else:
        decision = "BUY" if signed > 0 else "SELL"
    confidence = "Strong" if strength >= 0.58 and rel_pct >= 60 else "Moderate" if strength >= 0.30 and rel_pct >= 45 else "Weak"

    ranked = sorted(((abs(value * WEIGHTS[name]), name, value) for name, value in components.items()), reverse=True)
    primary_name = ranked[0][1] if ranked else "regime_alignment"
    primary_label = primary_name.replace("_", " ").title()
    primary_reason = f"{primary_label} supplied the strongest existing-canonical contribution."
    warning = "Conflict or counter-trend evidence reduced the bias." if has_conflict else "No canonical conflict penalty is active."

    return {
        "decision_number": 11,
        "name": "Medium-Standard Regime Bias",
        "decision": decision,
        "score": score,
        "confidence_class": confidence,
        "primary_reason": primary_reason,
        "conflict_warning": warning,
        "signed_bias": round(signed, 4),
        "inputs": {
            "h1_regime": str(h1), "h4_regime": str(h4), "d1_regime": str(d1),
            "regime_reliability_pct": round(rel_pct, 2), "adx": round(adx, 3),
            "plus_di": round(plus_di, 3), "minus_di": round(minus_di, 3),
            "market_quality_pct": round(market_quality, 2),
        },
        "weights": dict(WEIGHTS),
        "components": {key: round(value, 4) for key, value in components.items()},
        "read_only_support": True,
        "protected_ten_decisions_changed": False,
    }


__all__ = ["WEIGHTS", "build_medium_standard_regime_bias"]
