"""Read-only canonical identity strip shared by all five decision displays."""
from __future__ import annotations
from typing import Any, Mapping
import streamlit as st

IDENTITY_KEYS = {
    "run_id": ("run_id", "canonical_calculation_id"),
    "generation_id": ("generation_id", "calculation_generation"),
    "source_snapshot_hash": ("source_snapshot_hash", "snapshot_hash"),
    "symbol": ("symbol",),
    "timeframe": ("timeframe",),
    "completed_broker_candle": ("broker_candle_time", "latest_completed_candle_time", "completed_candle_identity"),
    "source_signature": ("source_signature",),
}

def _raw(value: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if value.get(key) not in (None, ""):
            return value.get(key)
    return None

def _value(canonical: Mapping[str, Any], *keys: str) -> str:
    value = _raw(canonical, tuple(keys))
    return str(value) if value not in (None, "") else "Unavailable — canonical value was not published"

def identity_mismatches(canonical: Mapping[str, Any], observed: Mapping[str, Any] | None) -> list[str]:
    """Return identity differences without mutating either payload."""
    if not isinstance(observed, Mapping) or not observed:
        return []
    mismatches: list[str] = []
    for label, aliases in IDENTITY_KEYS.items():
        expected = _raw(canonical, aliases)
        actual = _raw(observed, aliases)
        if actual not in (None, "") and expected not in (None, "") and str(actual) != str(expected):
            mismatches.append(f"{label}: Field 1={expected!s} field={actual!s}")
    return mismatches

def render_lunch_identity_strip(canonical: Mapping[str, Any], *, field_label: str, observed_identity: Mapping[str, Any] | None = None) -> None:
    # Recover the same already-published identity from compatible state aliases.
    # This is read-only and never starts or republishes a calculation.
    try:
        from core.canonical_lookup_20260626 import resolve_canonical
        canonical = resolve_canonical(st.session_state, preferred=canonical)
    except Exception:
        canonical = dict(canonical or {})
    mismatches = identity_mismatches(canonical, observed_identity)
    if mismatches:
        st.error("🔴 OUT-OF-SYNC — " + " | ".join(mismatches))
    st.markdown(f"##### Canonical Snapshot Identity — {field_label}")
    cols = st.columns(4)
    cols[0].metric("run_id", _value(canonical, "run_id", "canonical_calculation_id")[:24])
    cols[1].metric("generation_id", _value(canonical, "generation_id", "calculation_generation")[:24])
    cols[2].metric("Symbol / Timeframe", f"{_value(canonical, 'symbol')} / {_value(canonical, 'timeframe')}")
    try:
        from core.shared_broker_time_20260622 import shared_broker_time_provider
        shared_clock = shared_broker_time_provider(st.session_state, canonical=canonical)
        completed_display = str(shared_clock.get("shared_broker_time_display") or _value(canonical, "broker_candle_time", "latest_completed_candle_time"))
    except Exception:
        completed_display = _value(canonical, "broker_candle_time", "latest_completed_candle_time")
    cols[3].metric("Completed Broker Candle", completed_display[:38])
    st.caption("source snapshot hash: " + _value(canonical, "source_snapshot_hash", "snapshot_hash"))
    st.caption("source signature: " + _value(canonical, "source_signature"))
    st.caption("This identity is read-only and originates from Field 1. Opening or switching fields never recalculates Field 1.")
