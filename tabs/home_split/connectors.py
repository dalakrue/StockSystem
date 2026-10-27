# Future-upgrade split module.
# Re-exports functions from the unchanged original implementation.
# Safe wrappers added so one broken import/function does not crash the full app.

import streamlit as st


try:
    from .implementation import _safe_manual_connect as _impl_safe_manual_connect
except Exception as _manual_import_error:
    _impl_safe_manual_connect = None


try:
    from .implementation import _safe_mt5_account_info as _impl_safe_mt5_account_info
except Exception as _mt5_import_error:
    _impl_safe_mt5_account_info = None


try:
    from .implementation import _normalize_account_info as _impl_normalize_account_info
except Exception as _normalize_import_error:
    _impl_normalize_account_info = None


try:
    from .implementation import _safe_quant_stack as _impl_safe_quant_stack
except Exception as _quant_import_error:
    _impl_safe_quant_stack = None


def _show_import_error(title, error):
    st.error(f"{title} could not be loaded.")
    with st.expander("Show import error"):
        st.write(str(error))


def _safe_manual_connect(*args, **kwargs):
    if _impl_safe_manual_connect is None:
        _show_import_error("_safe_manual_connect", _manual_import_error)
        return None, False, "IMPORT_FAILED", str(_manual_import_error)

    try:
        return _impl_safe_manual_connect(*args, **kwargs)
    except Exception as exc:
        st.error("_safe_manual_connect crashed.")
        with st.expander("Show error detail"):
            st.exception(exc)
        return None, False, "RUNTIME_FAILED", str(exc)


def _safe_mt5_account_info(*args, **kwargs):
    if _impl_safe_mt5_account_info is None:
        _show_import_error("_safe_mt5_account_info", _mt5_import_error)
        return {}, False, str(_mt5_import_error)

    try:
        return _impl_safe_mt5_account_info(*args, **kwargs)
    except Exception as exc:
        st.error("_safe_mt5_account_info crashed.")
        with st.expander("Show error detail"):
            st.exception(exc)
        return {}, False, str(exc)


def _normalize_account_info(*args, **kwargs):
    if _impl_normalize_account_info is None:
        _show_import_error("_normalize_account_info", _normalize_import_error)
        return {}

    try:
        return _impl_normalize_account_info(*args, **kwargs)
    except Exception as exc:
        st.error("_normalize_account_info crashed.")
        with st.expander("Show error detail"):
            st.exception(exc)
        return {}


def _safe_quant_stack(*args, **kwargs):
    if _impl_safe_quant_stack is None:
        _show_import_error("_safe_quant_stack", _quant_import_error)
        return {
            "bias": "WAIT",
            "safe_pct": 1,
            "scale10": 0.1,
            "error": str(_quant_import_error),
        }

    try:
        return _impl_safe_quant_stack(*args, **kwargs)
    except Exception as exc:
        st.error("_safe_quant_stack crashed.")
        with st.expander("Show error detail"):
            st.exception(exc)
        return {
            "bias": "WAIT",
            "safe_pct": 1,
            "scale10": 0.1,
            "error": str(exc),
        }