"""One shared Auto/Manual FX-session selector for Lunch Fields 1 and 2.

The widget stores internal session codes, not display labels.  Renderers read the
same state key, so changing the selector in either field immediately changes the
read-only session contract and Field 2 shadow projection without recalculating the
protected central path.
"""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from core.session_context_20260625 import (
    SESSION_OPTIONS,
    SESSION_WIDGET_KEY,
    SESSION_SELECTION_KEY,
    SESSION_EFFECTIVE_KEY,
    SESSION_AUTO_KEY,
    SESSION_MODE_KEY,
    normalize_session_selection,
    resolve_session_contract,
)

VISIBLE_SESSION_CODES = (
    "AUTO",
    "SYDNEY",
    "TOKYO",
    "TOKYO_SYDNEY_OVERLAP",
    "TOKYO_LONDON_OVERLAP",
    "LONDON",
    "LONDON_NEW_YORK_OVERLAP",
    "NEW_YORK",
    "GLOBAL_FALLBACK",
)


def render_shared_fx_session_selector(
    state: MutableMapping[str, Any],
    canonical: Mapping[str, Any] | None = None,
    *,
    location: str,
) -> dict[str, Any]:
    """Render the shared selector and return its canonical session contract."""
    import streamlit as st

    canonical = canonical if isinstance(canonical, Mapping) else {}
    current = normalize_session_selection(state.get(SESSION_SELECTION_KEY))
    if bool(state.get("hide_shared_fx_session_selector_20260709", True)):
        selected = current if current in VISIBLE_SESSION_CODES else "AUTO"
        state[SESSION_SELECTION_KEY] = selected
        contract = resolve_session_contract(state, canonical, selected).to_dict()
        state[SESSION_AUTO_KEY] = contract.get("detected_session")
        state[SESSION_EFFECTIVE_KEY] = contract.get("selected_session")
        state[SESSION_MODE_KEY] = contract.get("session_mode")
        state["shared_fx_session_contract_20260625"] = contract
        state[f"shared_fx_session_contract_{location}_20260625"] = contract
        return contract
    widget_key = SESSION_WIDGET_KEY
    # Keep the widget-owned key separate from the canonical selection key.
    # This prevents StreamlitAPIException from mutating a widget key after the
    # widget has already been instantiated during the same rerun.
    if widget_key not in state:
        state[widget_key] = current if current in VISIBLE_SESSION_CODES else "AUTO"

    def _commit_selection() -> None:
        state[SESSION_SELECTION_KEY] = normalize_session_selection(state.get(widget_key))

    selected = st.selectbox(
        "Shared FX Session Selector",
        options=list(VISIBLE_SESSION_CODES),
        index=list(VISIBLE_SESSION_CODES).index(state.get(widget_key, "AUTO")) if state.get(widget_key, "AUTO") in VISIBLE_SESSION_CODES else 0,
        format_func=lambda code: SESSION_OPTIONS.get(code, code),
        key=widget_key,
        on_change=_commit_selection,
        help=(
            "Auto uses the immutable latest completed canonical candle. Manual selection changes only "
            "the leakage-safe session-conditioned shadow/evidence layer; the protected production path "
            "and Field 1 source-of-truth formulas are not rewritten."
        ),
    )
    st.caption("Changing this selector applies the shared session lens immediately from saved data; no market refresh is started.")
    selected = normalize_session_selection(selected)
    # Do not assign the widget-backed key here. The selectbox return value is
    # already authoritative for this run; the callback persists it safely.
    state[SESSION_SELECTION_KEY] = selected
    contract = resolve_session_contract(state, canonical, selected).to_dict()
    state[SESSION_AUTO_KEY] = contract.get("detected_session")
    state[SESSION_EFFECTIVE_KEY] = contract.get("selected_session")
    state[SESSION_MODE_KEY] = contract.get("session_mode")
    state["shared_fx_session_contract_20260625"] = contract
    state[f"shared_fx_session_contract_{location}_20260625"] = contract
    return contract



def get_shared_fx_session_contract(
    state: MutableMapping[str, Any],
    canonical: Mapping[str, Any] | None = None,
    *,
    location: str,
) -> dict[str, Any]:
    """Return the shared contract without creating another Streamlit widget."""
    canonical = canonical if isinstance(canonical, Mapping) else {}
    selected = normalize_session_selection(state.get(SESSION_SELECTION_KEY))
    contract = resolve_session_contract(state, canonical, selected).to_dict()
    state[SESSION_AUTO_KEY] = contract.get("detected_session")
    state[SESSION_EFFECTIVE_KEY] = contract.get("selected_session")
    state[SESSION_MODE_KEY] = contract.get("session_mode")
    state["shared_fx_session_contract_20260625"] = contract
    state[f"shared_fx_session_contract_{location}_20260625"] = contract
    return contract

def session_contract_metrics(contract: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Compact metrics shared by Fields 1 and 2."""
    return [
        ("Detected Session", str(contract.get("detected_session") or "—")),
        ("Effective Session", str(contract.get("selected_session") or "—")),
        ("Mode", str(contract.get("session_mode") or "—")),
        ("Canonical Candle", str(contract.get("broker_candle_time") or "—")[:19]),
    ]


__all__ = [
    "VISIBLE_SESSION_CODES",
    "render_shared_fx_session_selector",
    "get_shared_fx_session_contract",
    "session_contract_metrics",
]
