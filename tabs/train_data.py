"""Train Data tab compatibility wrapper.

The full implementation now lives under `tabs/train/` so future ML/data
upgrades can be isolated without editing the root tab file or app registry.
"""

import streamlit as st
from core.full_system_upgrade import render_train_upgrade_panel


def show():
    render_train_upgrade_panel()
    try:
        from ui.train_data_overview_20260619 import render_train_data_overview
        render_train_data_overview(state=st.session_state)
    except Exception as exc:
        st.warning(f"Train Data canonical overview skipped safely: {exc}")
    try:
        from tabs.train.train_data_legacy import show as _show
        return _show()
    except Exception as exc:
        st.error("Train Data tab could not be loaded safely.")
        with st.expander("Show Train Data import/runtime error", expanded=True):
            st.exception(exc)


__all__ = ["show"]
