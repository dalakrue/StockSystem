"""Masked, restart-persistent controls for limited fallback providers.

The controls only store encrypted credentials. Provider validation and market
requests remain owned by the explicit Settings calculation workflow, so widget
reruns and expander opens cannot consume API allowance.
"""
from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any


def render_optional_provider_connectors(state: MutableMapping[str, Any]) -> None:
    import streamlit as st

    from core.connectors.credential_vault import (
        delete_credential,
        load_credential,
        save_credential,
    )

    alpha_configured = bool(str(state.get("alpha_vantage_api_key") or load_credential("ALPHA_VANTAGE") or "").strip())
    fred_configured = bool(str(state.get("fred_api_key") or load_credential("FRED") or "").strip())

    with st.container(border=True):
        st.markdown("### 🔐 Limited Fallback and Macro Connectors")
        cols = st.columns(2)
        cols[0].metric("Alpha Vantage — Plan D", "CONFIGURED" if alpha_configured else "OPTIONAL")
        cols[1].metric("FRED Macro", "CONFIGURED" if fred_configured else "OPTIONAL")
        st.caption(
            "Credentials are masked and encrypted for restart restoration. Saving a key does not fetch data; "
            "validation occurs only inside the explicit calculation workflow."
        )

        with st.expander("Open / Close — Secure optional API credentials", expanded=False):
            alpha_value = st.text_input(
                "Alpha Vantage API key",
                type="password",
                value="",
                key="settings_alpha_vantage_secret_20260705",
                autocomplete="off",
                help="Plan D only. The key is never printed, logged, or used as a cache key.",
            )
            alpha_cols = st.columns(2)
            if alpha_cols[0].button("Save Alpha Vantage securely", key="save_alpha_vantage_20260705", use_container_width=True):
                result = save_credential("ALPHA_VANTAGE", alpha_value)
                if result.get("ok"):
                    state["alpha_vantage_api_key"] = alpha_value.strip()
                    st.success("Alpha Vantage credential saved securely. It will be restored after reruns and restarts.")
                else:
                    st.warning("Enter a non-empty Alpha Vantage key before saving.")
            if alpha_cols[1].button("Forget Alpha Vantage key", key="forget_alpha_vantage_20260705", use_container_width=True):
                delete_credential("ALPHA_VANTAGE")
                state.pop("alpha_vantage_api_key", None)
                st.success("Saved Alpha Vantage credential removed.")

            fred_value = st.text_input(
                "FRED API key",
                type="password",
                value="",
                key="settings_fred_secret_20260705",
                autocomplete="off",
                help="Used only for cached macro observations during the explicit calculation workflow.",
            )
            fred_cols = st.columns(2)
            if fred_cols[0].button("Save FRED securely", key="save_fred_20260705", use_container_width=True):
                result = save_credential("FRED", fred_value)
                if result.get("ok"):
                    state["fred_api_key"] = fred_value.strip()
                    st.success("FRED credential saved securely. It will be restored after reruns and restarts.")
                else:
                    st.warning("Enter a non-empty FRED key before saving.")
            if fred_cols[1].button("Forget FRED key", key="forget_fred_20260705", use_container_width=True):
                delete_credential("FRED")
                state.pop("fred_api_key", None)
                st.success("Saved FRED credential removed.")


__all__ = ["render_optional_provider_connectors"]
