"""Read-only session lens for Lunch Field 1.

This never changes the protected Full Metric decision.  It exposes the same
Auto/Manual session contract used by Field 2 and shows the current exact-run
session-conditioned projection evidence beside Field 1.
"""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping

import pandas as pd


def _identity(canonical: Mapping[str, Any], session_code: str) -> str:
    return "|".join(
        str(canonical.get(key) or "")
        for key in ("run_id", "calculation_generation", "snapshot_hash", "latest_completed_candle_time")
    ) + f"|{session_code}"


def render_field1_session_lens(state: MutableMapping[str, Any], canonical: Mapping[str, Any]) -> None:
    import streamlit as st

    from core.session_context_20260625 import SESSION_SELECTION_KEY
    from ui.shared_fx_session_selector_20260625 import (
        get_shared_fx_session_contract,
        session_contract_metrics,
    )

    st.markdown("#### Shared FX Session Lens — Current Data Only")
    contract = get_shared_fx_session_contract(state, canonical, location="field1")
    cols = st.columns(4)
    for column, (label, value) in zip(cols, session_contract_metrics(contract)):
        column.metric(label, value)

    selected = str(state.get(SESSION_SELECTION_KEY) or "AUTO")
    cache_key = _identity(canonical, selected)
    cache = state.get("field1_session_lens_cache_20260625")
    payload: Mapping[str, Any] = {}
    if isinstance(cache, Mapping) and cache.get("key") == cache_key:
        payload = cache.get("payload") if isinstance(cache.get("payload"), Mapping) else {}
    else:
        try:
            from core.less_risky_projection_20260625 import extract_saved_projection_horizons
            from core.session_adaptive_projection_20260625 import build_session_adjusted_projection

            base = extract_saved_projection_horizons(state, canonical)
            payload = build_session_adjusted_projection(state, canonical, base, selected)
            state["field1_session_lens_cache_20260625"] = {"key": cache_key, "payload": payload}
        except Exception as exc:
            state["field1_session_lens_error_20260625"] = f"{type(exc).__name__}: {exc}"
            payload = {}

    horizons = payload.get("horizons") if isinstance(payload.get("horizons"), pd.DataFrame) else pd.DataFrame()
    if not horizons.empty:
        cards = st.columns(min(3, len(horizons)))
        for card, (_, row) in zip(cards, horizons.head(3).iterrows()):
            horizon = int(row.get("horizon") or 0)
            prediction = row.get("Session Prediction")
            base = row.get("Base Prediction")
            try:
                value = f"{float(prediction):.5f}"
            except Exception:
                value = "—"
            try:
                delta = f"base {float(base):.5f}"
            except Exception:
                delta = None
            card.metric(f"Session-Adjusted H+{horizon}", value, delta)
        st.caption(
            "Field 1 decision formulas remain unchanged. These cards are a bounded, completed-H1 "
            "session lens shared with Field 2; manual selection never rewrites historical rows."
        )
    else:
        st.caption("Session contract is active; no exact-run projected horizons were available for current-only cards.")


__all__ = ["render_field1_session_lens"]
