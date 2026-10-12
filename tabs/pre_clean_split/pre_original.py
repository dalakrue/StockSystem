import streamlit as st

try:
    from core.ui_helpers import choice_buttons
except Exception:
    choice_buttons = None

from .timer import timer_panel
from .history_tab import advanced_history_tab
from .pretrade import pretrade_check_tab
from .exit_survivability import exit_survivability_tab


def _safe_run(title, func):
    """
    Runs each inner tab safely.
    If one tab has an error, the whole Pre tab will not crash.
    """
    try:
        func()
    except Exception as exc:
        st.error(f"{title} failed to load.")
        with st.expander("Show error detail"):
            st.exception(exc)


def show():
    st.markdown("# ✅ Clean Independent Pre Tab")
    st.caption(
        "Advanced History Match + Pre-Trade Check + Exit Survivability. "
        "Fast mode: only the selected Pre section renders."
    )

    with st.expander("⏱ Open Timer Panel", expanded=False):
        _safe_run("Timer Panel", timer_panel)

    sections = ["🧠 Advanced History Match", "📋 Pre-Trade Check", "🔥 Exit Survivability"]
    if callable(choice_buttons):
        section = choice_buttons(
            "Open Pre inner section",
            sections,
            key="pre_original_lazy_section",
            columns=3,
            default="🧠 Advanced History Match",
            help_text="Only the selected Pre section renders for faster switching.",
        )
    else:
        section = st.radio(
            "Open Pre inner section",
            sections,
            horizontal=True,
            key="pre_original_lazy_section",
        )

    if section == "🧠 Advanced History Match":
        _safe_run("Advanced History Match", advanced_history_tab)
    elif section == "📋 Pre-Trade Check":
        _safe_run("Pre-Trade Check", pretrade_check_tab)
    else:
        _safe_run("Exit Survivability", exit_survivability_tab)


if __name__ == "__main__":
    show()
