# Future-upgrade split module.
# Re-exports functions from the unchanged original implementation.
# Safe wrapper added so Doo Prime panel does not crash the full app.

import streamlit as st


try:
    from .implementation import doo_prime_panel as _impl_doo_prime_panel
except Exception as _import_error:
    _impl_doo_prime_panel = None


def doo_prime_panel(*args, **kwargs):
    if _impl_doo_prime_panel is None:
        st.error("Doo Prime panel could not be loaded.")
        with st.expander("Show import error"):
            st.write(str(_import_error))
        return None

    try:
        return _impl_doo_prime_panel(*args, **kwargs)
    except Exception as exc:
        st.error("Doo Prime panel crashed.")
        with st.expander("Show error detail"):
            st.exception(exc)
        return None