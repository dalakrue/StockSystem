"""Deterministic fixed-share tracker for existing forecast experts."""
from __future__ import annotations

from typing import Any, Mapping
import math
import numpy as np
import pandas as pd

from core.research_validation_common_20260621 import clip, stable_hash, utc_now_iso

VERSION = "fixed-share-expert-tracker-20260621-v1"


def _normalise(weights: Mapping[str, Any], experts: list[str], floor: float, ceiling: float) -> dict[str, float]:
    if not experts:
        return {}
    values = np.asarray([max(0.0, float(weights.get(expert, 0.0) or 0.0)) for expert in experts], dtype=float)
    if values.sum() <= 0:
        values[:] = 1.0 / len(values)
    else:
        values /= values.sum()
    for _ in range(12):
        values = np.clip(values, floor, ceiling)
        values /= max(float(values.sum()), 1e-12)
    return {expert: float(value) for expert, value in zip(experts, values)}


def fixed_share_update(
    previous_state: Mapping[str, Any] | None,
    settled_losses: Mapping[str, Any],
    *,
    settlement_id: str,
    settled_at: Any,
    learning_rate: float = 0.8,
    share_rate: float = 0.02,
    minimum_weight: float = 0.03,
    maximum_weight: float = 0.80,
    maximum_hourly_weight_change: float = 0.12,
    loss_cap: float = 10.0,
) -> dict[str, Any]:
    previous = dict(previous_state or {})
    experts = sorted(str(name) for name, value in settled_losses.items() if value is not None and math.isfinite(float(value)))
    if not experts:
        return {"version": VERSION, "status": "NO_VALID_SETTLED_LOSSES", "updated": False, "weights": dict(previous.get("weights") or {}), "promotion_allowed": False}
    if str(previous.get("last_settlement_id") or "") == str(settlement_id):
        return {"version": VERSION, "status": "IDEMPOTENT_DUPLICATE_IGNORED", "updated": False, "weights": dict(previous.get("weights") or {}), "promotion_allowed": False}
    timestamp = pd.Timestamp(settled_at)
    timestamp = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
    previous_time = pd.to_datetime(previous.get("updated_at"), errors="coerce", utc=True)
    if pd.notna(previous_time) and timestamp <= previous_time:
        return {"version": VERSION, "status": "NON_CHRONOLOGICAL_SETTLEMENT_IGNORED", "updated": False, "weights": dict(previous.get("weights") or {}), "promotion_allowed": False}
    prior = _normalise(previous.get("weights") or {}, experts, minimum_weight, maximum_weight)
    losses = {expert: clip(settled_losses[expert], 0.0, loss_cap, loss_cap) / max(loss_cap, 1e-12) for expert in experts}
    raw = np.asarray([prior[expert] * math.exp(-float(learning_rate) * losses[expert]) for expert in experts], dtype=float)
    raw /= max(float(raw.sum()), 1e-12)
    shared = (1.0 - share_rate) * raw + share_rate / len(experts)
    previous_values = np.asarray([prior[expert] for expert in experts], dtype=float)
    delta = np.clip(shared - previous_values, -maximum_hourly_weight_change, maximum_hourly_weight_change)
    bounded = previous_values + delta
    new = _normalise({expert: value for expert, value in zip(experts, bounded)}, experts, minimum_weight, maximum_weight)
    history_rows = []
    for expert in experts:
        row = {
            "settlement_id": str(settlement_id), "settled_at": timestamp.isoformat(), "expert_id": expert,
            "previous_weight": prior[expert], "new_weight": new[expert], "settled_loss": losses[expert],
            "learning_rate": float(learning_rate), "share_rate": float(share_rate),
            "minimum_weight": float(minimum_weight), "maximum_weight": float(maximum_weight),
            "maximum_hourly_weight_change": float(maximum_hourly_weight_change), "calculation_version": VERSION,
        }
        row["record_key"] = "EWH-" + stable_hash(row)[:24]
        history_rows.append(row)
    state = {
        "version": VERSION,
        "state_id": "ETS-" + stable_hash([settlement_id, new])[:24],
        "updated_at": timestamp.isoformat(),
        "last_settlement_id": str(settlement_id),
        "weights": new,
        "update_count": int(previous.get("update_count") or 0) + 1,
        "mode": "SHADOW",
        "promotion_allowed": False,
    }
    comparison = {
        "comparison_id": "ETC-" + stable_hash([settlement_id, prior, new, losses])[:24],
        "settlement_id": str(settlement_id),
        "settled_at": timestamp.isoformat(),
        "previous_weights": prior,
        "shadow_weights": new,
        "settled_losses": losses,
        "maximum_absolute_change": max(abs(new[e] - prior[e]) for e in experts),
        "normalization_error": abs(sum(new.values()) - 1.0),
        "calculation_version": VERSION,
    }
    return {"version": VERSION, "status": "SHADOW_UPDATED", "updated": True, "weights": new, "state": state, "history_rows": history_rows, "comparison": comparison, "promotion_allowed": False}


__all__ = ["VERSION", "fixed_share_update"]
