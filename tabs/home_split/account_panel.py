# Future-upgrade split module.
# Re-exports functions from the unchanged original implementation.
# Safe wrapper added so missing functions do not crash the full app.

import streamlit as st

try:
    from .implementation import doo_prime_account_panel as _doo_prime_account_panel
except Exception as _import_error:
    _doo_prime_account_panel = None


def doo_prime_account_panel(*args, **kwargs):
    if _doo_prime_account_panel is None:
        st.error("Doo Prime account panel could not be loaded.")
        with st.expander("Show import error"):
            st.write(str(_import_error))
        return None

    try:
        return _doo_prime_account_panel(*args, **kwargs)
    except Exception as exc:
        st.error("Doo Prime account panel crashed.")
        with st.expander("Show error detail"):
            st.exception(exc)
        return None