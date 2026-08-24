"""Main account module with lazy implementation loading."""

import streamlit as st


def show():
    try:
        from .legacy.implementation import show as _show
        return _show()
    except Exception as exc:
        st.error("Account module failed to load safely.")
        with st.expander("Show Account import/runtime error", expanded=True):
            st.exception(exc)


__all__ = ["show"]
