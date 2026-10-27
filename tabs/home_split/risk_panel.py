# Future-upgrade split module.
# Safe re-export for risk_panel from unchanged original implementation.
# Does not modify original code.

try:
    from .implementation import risk_panel
except Exception as exc:
    import streamlit as st

    def risk_panel():
        st.markdown("### 🛡️ Risk Inner Tab")
        st.error("Original risk_panel could not be imported.")
        st.caption(f"Import error: {exc}")


__all__ = [
    "risk_panel",
]