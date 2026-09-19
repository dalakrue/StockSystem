"""Single-run, research-only CRCEF-SV publisher.

This module consumes one frozen canonical generation after all protected
publishers finish.  It never writes into protected production structures and
never turns missing data into invented scores.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import time
import tracemalloc
from typing import Any, Iterable, Mapping, MutableMapping

import numpy as np
import pandas as pd

from research_quant.canonical_adapter import adapt_canonical, feature_hash
from research_quant.config import DEFAULT_CONFIG
from research_quant.fusion.crcef_sv import fuse_evidence, uncertainty_score
from research_quant.fusion.evidence_registry import Evidence
from research_quant.fusion.selective_policy import select_action
from research_quant.meta_labeling.action_policy import expected_utility
from research_quant.meta_labeling.actionability_model import estimate_actionability
from research_quant.meta_labeling.primary_direction_adapter import direction_value, production_direction
from research_quant.multifractal.msm_model import msm_summary
from research_quant.multifractal.volatility_capacity import risk_capacity
from research_quant.multifractal.volatility_components import volatility_components
from research_quant.persistence.research_store import store_audit_row, store_canonical_snapshot, store_research_result
from research_quant.schemas import PromotionStatus, ResearchEnvelope, ResearchStatus, immutable_payload

MODEL_NAME = "Canonical Regime-Calibrated Evidence Fusion with Selective Validation"
MODEL_VERSION = "CRCEF-SV-1.0.0"
STATE_KEY = "crcef_sv_research_20260627"

DECISION_KEYS = {
    "decision", "master decision", "master_decision", "final decision", "final_decision",
    "technical bias", "technical_bias", "less risky bias", "less_risky_bias",
    "direction", "entry decision", "entry_decision", "action",
}
ALLOWED = {"BUY", "SELL", "WAIT", "WAIT PULLBACK", "HOLD"}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _bounded01(value: Any, default: float | None = None) -> float | None:
    number = _finite(value)
    if number is None:
        return default
    if number > 1.0 and number <= 100.0:
        number /= 100.0
    return float(np.clip(number, 0.0, 1.0))


def _normalise_label(value: Any) -> str | None:
    text = str(value or "").strip().upper().replace("_", " ")
    aliases = {
        "HOLD & PROTECT": "HOLD", "HOLD AND PROTECT": "HOLD",
        "WAIT/PULLBACK": "WAIT PULLBACK", "PULLBACK": "WAIT PULLBACK",
        "STRONG BUY": "BUY", "WEAK BUY": "BUY", "STRONG SELL": "SELL", "WEAK SELL": "SELL",
    }
    text = aliases.get(text, text)
    return text if text in ALLOWED else None


def _walk_decisions(value: Any, path: str = "canonical") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def walk(obj: Any, current: str) -> None:
        if isinstance(obj, Mapping):
            for key, child in obj.items():
                key_text = str(key).strip().lower()
                child_path = f"{current}.{key}"
                if key_text in DECISION_KEYS:
                    label = _normalise_label(child)
                    if label and (child_path, label) not in seen:
                        seen.add((child_path, label))
                        found.append((child_path, label))
                elif isinstance(child, Mapping):
                    walk(child, child_path)
        # DataFrames are deliberately not recursively interpreted here: their
        # historical rows must be handled by dedicated leakage-safe modules.

    walk(value, path)
    return found


def _find_frame(canonical: Mapping[str, Any], state: Mapping[str, Any]) -> pd.DataFrame:
    candidates: list[Any] = []
    market = _mapping(canonical.get("market"))
    for source in (canonical, market, state):
        for key in ("ohlc_df", "df", "last_df", "dv_pp_df", "lunch_5layer_powerbi_df", "market_frame"):
            candidates.append(source.get(key))
    frames = [item for item in candidates if isinstance(item, pd.DataFrame) and not item.empty]
    if not frames:
        return pd.DataFrame()
    return max(frames, key=len)


def _close_column(frame: pd.DataFrame) -> str | None:
    normalized = {str(column).strip().lower(): str(column) for column in frame.columns}
    return next((normalized[name] for name in ("close", "c", "last", "price") if name in normalized), None)


def _regime_values(canonical: Mapping[str, Any], state: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for source in (canonical, _mapping(canonical.get("regime")), state):
        for key in ("regime_history", "regime_states", "state_history"):
            candidate = source.get(key)
            if isinstance(candidate, (list, tuple, pd.Series)):
                values.extend(str(item) for item in candidate if str(item).strip())
            elif isinstance(candidate, pd.DataFrame) and not candidate.empty:
                column = next((c for c in candidate.columns if "regime" in str(c).lower()), None)
                if column is not None:
                    values.extend(candidate[column].dropna().astype(str).tolist())
    current = str(canonical.get("regime") or _mapping(canonical.get("regime_summary")).get("regime") or "").strip()
    if current:
        values.append(current)
    return values[-600:]


def _existing_probability(canonical: Mapping[str, Any]) -> float | None:
    final = _mapping(canonical.get("final_decision"))
    for source in (final, canonical, _mapping(canonical.get("powerbi")), _mapping(canonical.get("reliability"))):
        for key in (
            "calibrated_probability", "direction_probability", "probability",
            "confidence", "reliability", "reliability_score", "forecast_agreement",
        ):
            value = _bounded01(source.get(key))
            if value is not None:
                return value
    return None


def _existing_scalar(canonical: Mapping[str, Any], names: Iterable[str]) -> float | None:
    pending = [canonical]
    visited: set[int] = set()
    wanted = {name.lower() for name in names}
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        for key, value in current.items():
            if str(key).lower() in wanted:
                number = _finite(value)
                if number is not None:
                    return number
            elif isinstance(value, Mapping):
                pending.append(value)
    return None


def _research_payload(canonical: Mapping[str, Any], state: Mapping[str, Any]) -> tuple[dict[str, Any], list[str], int]:
    config = DEFAULT_CONFIG
    primary = production_direction(canonical)
    decisions = _walk_decisions(canonical)
    quality_flags: list[str] = []
    evidence: list[Evidence] = []

    explicit_probability = _existing_probability(canonical)
    if explicit_probability is None:
        quality_flags.append("CALIBRATION_NOT_AVAILABLE_FOR_THIS_GENERATION")
        direction_probability = 0.5
        calibration_quality = 0.0
    else:
        direction_probability = explicit_probability
        # Existing confidence is evidence only. It is not falsely relabelled as
        # a newly fitted calibrated probability.
        calibration_quality = 0.5
        quality_flags.append("EXISTING_CONFIDENCE_USED_AS_UNCALIBRATED_INPUT")

    for path, label in decisions:
        numeric = direction_value(label)
        if numeric == 0:
            continue
        evidence.append(Evidence(path, numeric, quality_score=max(0.25, direction_probability), calibration_quality=calibration_quality))
    if primary in {"BUY", "SELL"}:
        evidence.insert(0, Evidence("Production Direction Adapter", direction_value(primary), 1.0, calibration_quality=max(calibration_quality, 0.5)))

    frame = _find_frame(canonical, state)
    close_name = _close_column(frame)
    volatility: dict[str, Any] = {}
    normalized_width = 1.0
    expected_move = None
    if close_name and len(frame) >= 8:
        closes = pd.to_numeric(frame[close_name], errors="coerce").dropna()
        returns = closes.pct_change().dropna()
        components = volatility_components(returns)
        volatility = {**components, **msm_summary(components)}
        variance = _finite(volatility.get("combined_forecast_variance"))
        immediate = _finite(components.get("immediate"))
        latest_close = _finite(closes.iloc[-1]) if not closes.empty else None
        if variance is not None and latest_close is not None:
            expected_move = latest_close * math.sqrt(max(variance, 0.0))
            volatility["expected_move_1h"] = expected_move
            volatility["expected_move_3h"] = expected_move * math.sqrt(3)
            volatility["expected_move_6h"] = expected_move * math.sqrt(6)
            volatility["risk_capacity"] = risk_capacity(expected_move, variance)
            normalized_width = float(np.clip(math.sqrt(max(variance, 0.0)) / max(abs(returns.std(ddof=0)), 1e-12), 0, 1))
    else:
        quality_flags.append("VOLATILITY_INSUFFICIENT_DATA")

    fusion = fuse_evidence(evidence, temperature=config.softmax_temperature)
    coverage = float(fusion["coverage"])
    conflict = float(fusion["conflict"])
    drift_level = _bounded01(_existing_scalar(canonical, ("drift_level", "drift_magnitude")), 0.0) or 0.0
    coverage_error = _bounded01(_existing_scalar(canonical, ("coverage_error", "conformal_coverage_error")), 0.0) or 0.0
    missing_penalty = float(np.clip(len(quality_flags) / 8.0, 0.0, 1.0))
    uncertainty = uncertainty_score(
        direction_probability=direction_probability,
        conflict=conflict,
        drift_level=drift_level,
        normalized_interval_width=normalized_width,
        coverage_error=coverage_error,
        missing_data_penalty=missing_penalty,
    )

    actionability_features = {
        "calibrated_probability": direction_probability,
        "coverage": coverage,
        "conflict": conflict,
        "drift_level": drift_level,
        "normalized_interval_width": normalized_width,
        "normalized_spread": _bounded01(_existing_scalar(canonical, ("normalized_spread", "spread_ratio")), 0.0) or 0.0,
    }
    actionability = estimate_actionability(actionability_features)
    expected_gain = abs(_finite(_existing_scalar(canonical, ("expected_gain", "expected_return", "expected_move_1h"))) or 0.0)
    if expected_gain == 0.0 and expected_move is not None:
        expected_gain = abs(expected_move)
    expected_loss = abs(_finite(_existing_scalar(canonical, ("expected_loss", "downside_risk", "stop_distance"))) or expected_gain or 1.0)
    transaction_cost = abs(_finite(_existing_scalar(canonical, ("transaction_cost", "spread"))) or 0.0)
    utility = expected_utility(
        direction_probability, expected_gain, expected_loss, transaction_cost,
        uncertainty / 100.0 * max(expected_loss, 1e-12),
        (_bounded01(_existing_scalar(canonical, ("transition_risk", "regime_transition_risk")), 0.0) or 0.0) * max(expected_loss, 1e-12),
    )

    entry_favourable = bool(_existing_scalar(canonical, ("entry_location_favourable",)))
    if "entry_location_favourable" not in canonical:
        entry_favourable = primary not in {"WAIT PULLBACK"}
    shadow = select_action(
        float(fusion["direction_fusion_score"]),
        direction_probability if float(fusion["direction_fusion_score"]) >= 0 else 1 - direction_probability,
        direction_probability if float(fusion["direction_fusion_score"]) < 0 else 1 - direction_probability,
        actionability, utility, uncertainty,
        primary_decision=primary, entry_location_favourable=entry_favourable,
        maximum_uncertainty_pct=config.maximum_uncertainty_pct,
    )

    # Preserve maintenance semantics even when evidence is incomplete.
    if primary == "HOLD":
        shadow = "HOLD"
    elif primary == "WAIT PULLBACK":
        shadow = "WAIT PULLBACK"

    regime_states = _regime_values(canonical, state)
    regime_result: dict[str, Any]
    if len(regime_states) >= 2:
        from research_quant.regime.markov_switching import summarize_markov_regime
        regime_result = summarize_markov_regime(regime_states)
    else:
        regime_result = {"current_regime": regime_states[-1] if regime_states else "UNAVAILABLE", "sample_size": len(regime_states), "status": "INSUFFICIENT_DATA"}
        quality_flags.append("REGIME_LIFECYCLE_INSUFFICIENT_DATA")

    payload = {
        "production_decision": primary,
        "production_decision_unchanged": True,
        "research_shadow_decision": shadow,
        "direction_fusion_score": float(fusion["direction_fusion_score"]),
        "buy_evidence": float(fusion["buy_evidence"]),
        "sell_evidence": float(fusion["sell_evidence"]),
        "conflict": conflict,
        "coverage": coverage,
        "raw_direction_probability": explicit_probability,
        "research_calibrated_probability": None,
        "calibration_status": "INSUFFICIENT_DATA" if explicit_probability is None else "NOT_REFIT_THIS_GENERATION",
        "actionability_probability": actionability,
        "expected_utility": utility,
        "uncertainty_pct": uncertainty,
        "regime_relevance": 1.0 - (_bounded01(regime_result.get("1h_transition_probability"), 0.0) or 0.0),
        "drift_penalty": drift_level,
        "prediction_interval_width": None,
        "nlp_event_contribution": 0.0,
        "technical_contribution": float(fusion["direction_fusion_score"]),
        "volatility_contribution": volatility,
        "regime_lifecycle": regime_result,
        "evidence_weights": fusion["weights"],
        "evidence_sources": [{"path": path, "label": label} for path, label in decisions],
        "decision_reason": "Research-only selective fusion from available exact-run evidence.",
        "rejection_reason": "" if shadow in {"BUY", "SELL", "HOLD"} else "Actionability, utility, uncertainty, timing, or data sufficiency did not pass the research policy.",
        "research_reliability": float(np.clip((coverage + (1 - uncertainty / 100.0) + direction_probability) / 3.0, 0, 1)),
        "promotion_eligibility": False,
        "promotion_status": PromotionStatus.RESEARCH_ONLY.value,
        "research_modules": {
            "cpcv_pbo": "IMPLEMENTED_AWAITING_SETTLED_CANDIDATE_SAMPLE",
            "probability_calibration": "IMPLEMENTED_AWAITING_SEPARATE_CALIBRATION_AND_TEST_WINDOWS",
            "meta_labeling": "RESEARCH_ONLY",
            "markov_regime": regime_result.get("status", "RESEARCH_ONLY"),
            "multiscale_volatility": "RESEARCH_ONLY" if volatility else "INSUFFICIENT_DATA",
            "enbpi": "IMPLEMENTED_AWAITING_OUT_OF_SAMPLE_RESIDUALS",
            "bellman_conformal": "IMPLEMENTED_AWAITING_BASE_INTERVALS",
            "adwin": "IMPLEMENTED_AWAITING_SETTLED_MONITOR_STREAMS",
            "tft": "OPTIONAL_MODEL_UNAVAILABLE_UNLESS_ARTIFACT_CONFIGURED",
            "nlp_event_memory": "IMPLEMENTED_AWAITING_SETTLED_EVENT_RESPONSES",
        },
    }
    sample_size = max(len(frame), len(regime_states), len(decisions))
    return payload, quality_flags, sample_size


def build_crcef_sv_result(canonical: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    normalized = adapt_canonical(canonical, state)
    payload, flags, sample_size = _research_payload(normalized, state)
    input_hash = feature_hash({
        "identity": {key: normalized.get(key) for key in (
            "run_id", "generation_id", "symbol", "timeframe",
            "completed_broker_candle", "source_snapshot_hash", "source_signature"
        )},
        "production_decision": payload["production_decision"],
        "evidence_sources": payload["evidence_sources"],
    })
    status = ResearchStatus.RESEARCH_ONLY.value
    reason = "Shadow publication; production decision is immutable."
    if not payload["evidence_sources"] and payload["production_decision"] == "WAIT":
        status = ResearchStatus.INSUFFICIENT_DATA.value
        reason = "No directional evidence was published for this exact generation."
    envelope = ResearchEnvelope(
        run_id=str(normalized["run_id"]), generation_id=str(normalized["generation_id"]),
        symbol=str(normalized["symbol"]), timeframe=str(normalized["timeframe"]),
        completed_broker_candle=pd.Timestamp(normalized["completed_broker_candle"]).to_pydatetime(),
        model_name=MODEL_NAME, model_version=MODEL_VERSION, research_mode=True,
        source_snapshot_hash=str(normalized["source_snapshot_hash"]), input_feature_hash=input_hash,
        created_at_broker_time=pd.Timestamp(normalized["completed_broker_candle"]).to_pydatetime(),
        status=status, reason=reason, sample_size=sample_size,
        quality_flags=tuple(sorted(set(flags))), payload=immutable_payload(payload),
    )
    result = envelope.to_dict()
    result["source_signature"] = str(normalized["source_signature"])
    return result


def publish_crcef_sv_research(state: MutableMapping[str, Any], canonical: Mapping[str, Any] | None = None) -> dict[str, Any]:
    start = time.perf_counter()
    tracemalloc.start()
    try:
        if canonical is None or not isinstance(canonical, Mapping) or not canonical:
            from core.canonical_runtime_20260617 import get_canonical
            from core.canonical_lookup_20260626 import resolve_canonical
            protected_canonical = get_canonical(state)
            canonical = resolve_canonical(state, preferred=protected_canonical)
        if not isinstance(canonical, Mapping) or not canonical:
            result = {"ok": False, "status": ResearchStatus.INSUFFICIENT_DATA.value, "reason": "Canonical generation is unavailable.", "production_decision_unchanged": True}
            state[STATE_KEY] = result
            return result
        result = build_crcef_sv_result(canonical, state)
        result["ok"] = True
        # Separate key only: do not attach to or mutate the protected canonical.
        state[STATE_KEY] = result
        state["crcef_sv_run_id_20260627"] = result.get("run_id")
        try:
            store_canonical_snapshot(result, dict(canonical))
            store_research_result(result)
        except Exception as persistence_exc:
            result.setdefault("quality_flags", []).append(f"PERSISTENCE_WARNING:{type(persistence_exc).__name__}")
        return result
    except Exception as exc:
        result = {
            "ok": False, "status": ResearchStatus.MODEL_UNAVAILABLE.value,
            "reason": f"{type(exc).__name__}: {exc}", "production_decision_unchanged": True,
            "promotion_status": PromotionStatus.RESEARCH_ONLY.value,
        }
        state[STATE_KEY] = result
        return result
    finally:
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result = state.get(STATE_KEY)
        if isinstance(result, MutableMapping) and result.get("run_id"):
            output_hash = sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()
            audit = {
                "run_id": result.get("run_id"), "generation_id": result.get("generation_id"),
                "broker_candle": result.get("completed_broker_candle"), "module": "CRCEF-SV",
                "model_version": MODEL_VERSION, "input_hash": result.get("input_feature_hash", ""),
                "output_hash": output_hash, "data_window": "exact frozen canonical generation",
                "sample_size": result.get("sample_size", 0), "status": result.get("status", "RESEARCH_ONLY"),
                "warnings": result.get("quality_flags", []), "runtime_seconds": time.perf_counter() - start,
                "peak_memory_mb": peak / (1024 * 1024), "validation_status": "PENDING_SETTLED_HISTORY",
                "promotion_status": PromotionStatus.RESEARCH_ONLY.value,
            }
            result["audit"] = audit
            try:
                store_audit_row(audit)
            except Exception:
                pass


__all__ = ["MODEL_NAME", "MODEL_VERSION", "STATE_KEY", "build_crcef_sv_result", "publish_crcef_sv_research"]
