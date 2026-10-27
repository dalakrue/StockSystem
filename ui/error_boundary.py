"""Safe UI section wrapper. Calculation logic is left untouched."""
from __future__ import annotations
from typing import Callable, Any
import streamlit as st

def safe_section(title: str, render_func: Callable[..., Any], *args, **kwargs) -> Any:
    try:
        return render_func(*args, **kwargs)
    except Exception as exc:
        st.warning(f"{title} failed to display, but the app is still running.")
        with st.container():
            show = st.checkbox("Show technical error", key=f"safe_section_error_{abs(hash(title)) % 100000}")
            if show:
                st.exception(exc)
        return None
