"""Read-only Field 3 publication validators.

The validators report whether the current canonical generation contains the
three required regime standards. They never replace or fabricate evidence.
"""
from __future__ import annotations
from typing import Any, Mapping, MutableMapping
import pandas as pd


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def render_field3_validators(state: MutableMapping[str, Any], canonical: Mapping[str, Any]) -> None:
    import streamlit as st
    from ui.lunch_four_core_fields_20260619 import _published_regime_tables

    tables = _published_regime_tables(state, canonical)
    rows = []
    for label, aliases in (
        ("Lower Standard", ("lower", "lower_standard", "1d")),
        ("Middle Standard", ("middle", "middle_standard", "5d")),
        ("Higher Standard", ("higher", "higher_standard", "25d")),
    ):
        value = next((tables.get(key) for key in aliases if key in tables), None)
        frame = value if isinstance(value, pd.DataFrame) else pd.DataFrame(value or [])
        rows.append({
            "Standard": label,
            "Published": not frame.empty,
            "Rows": int(len(frame)),
            "Status": "PASS" if not frame.empty else "MISSING",
        })
    report = pd.DataFrame(rows)
    with st.expander("Open / Close — Field 3 Publication Validators", expanded=False):
        st.caption("Validation is tied to the active canonical run and checks publication presence only.")
        st.dataframe(report, use_container_width=True, hide_index=True)
        if not bool(report["Published"].all()):
            st.warning("One or more regime-standard history tables were not published for this generation.")


__all__ = ["render_field3_validators"]
