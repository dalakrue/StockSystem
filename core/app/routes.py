"""Lazy tab router.

This module isolates tab import failures. A bad future tab upgrade should show
an error inside that tab only; it should not break sidebar, styles, database,
or other tabs.
"""

import streamlit as st

from core.app.registry import get_tab_spec
from core.app.imports import import_attr


def _fallback_page(tab_name, error):
    def _show():
        st.error(f"{tab_name} tab could not be imported.")
        st.caption("The rest of the app is still protected. Check the import error below, then fix only that tab file.")
        with st.expander("Import error detail", expanded=True):
            st.code(str(error))
    return _show


def load_tab(tab):
    """Return the active tab render function with per-tab import isolation."""
    spec = get_tab_spec(tab)
    try:
        return import_attr(spec.module, spec.function)
    except Exception as exc:
        return _fallback_page(spec.name, exc)
