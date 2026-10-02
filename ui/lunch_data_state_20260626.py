"""Explicit missing/low-confidence state banners for Lunch fields."""
from __future__ import annotations
from typing import Any, Mapping
import streamlit as st
from core.research_result_state_20260626 import classify_research_result


def canonical_identity(canonical: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        canonical.get("run_id") or canonical.get("canonical_calculation_id"),
        canonical.get("generation_id") or canonical.get("calculation_generation"),
        canonical.get("source_snapshot_hash") or canonical.get("snapshot_hash"),
    )

def render_state(value: Any, *, label: str, canonical: Mapping[str, Any]) -> dict[str, str]:
    result=classify_research_result(value, canonical_identity=canonical_identity(canonical))
    state=result["state"]
    text=f"{label}: {state} — {result['reason']}"
    if state == "valid result": st.success(text)
    elif state == "valid but low-confidence result": st.warning(text)
    elif state in {"unsettled future outcome","insufficient observations"}: st.info(text)
    else: st.error(text)
    return result
