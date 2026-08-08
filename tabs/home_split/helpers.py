# Future-upgrade split module.
# Re-exports functions from the unchanged original implementation.
# Safe wrappers added so utility import/runtime errors do not crash the full app.

import time
import streamlit as st


try:
    from .implementation import _safe_num as _impl_safe_num
except Exception as _safe_num_import_error:
    _impl_safe_num = None

try:
    from .implementation import _safe_int as _impl_safe_int
except Exception as _safe_int_import_error:
    _impl_safe_int = None

try:
    from .implementation import _safe_text as _impl_safe_text
except Exception as _safe_text_import_error:
    _impl_safe_text = None

try:
    from .implementation import _safe_append_csv as _impl_safe_append_csv
except Exception as _safe_append_csv_import_error:
    _impl_safe_append_csv = None

try:
    from .implementation import _safe_read_csv as _impl_safe_read_csv
except Exception as _safe_read_csv_import_error:
    _impl_safe_read_csv = None

try:
    from .implementation import _safe_rerun as _impl_safe_rerun
except Exception as _safe_rerun_import_error:
    _impl_safe_rerun = None

try:
    from .implementation import _safe_log_event as _impl_safe_log_event
except Exception as _safe_log_event_import_error:
    _impl_safe_log_event = None

try:
    from .implementation import _safe_close_sidebar as _impl_safe_close_sidebar
except Exception as _safe_close_sidebar_import_error:
    _impl_safe_close_sidebar = None

try:
    from .implementation import _save_once_per_60_seconds as _impl_save_once_per_60_seconds
except Exception as _save_once_import_error:
    _impl_save_once_per_60_seconds = None


def _fallback_show_error(name, error):
    try:
        st.warning(f"{name} fallback used.")
        with st.expander(f"Show {name} import error"):
            st.write(str(error))
    except Exception:
        pass


def _safe_num(value, default=0.0):
    if _impl_safe_num is not None:
        try:
            return _impl_safe_num(value, default)
        except Exception:
            pass

    try:
        if value is None:
            return float(default)

        if isinstance(value, str):
            value = value.strip().replace(",", "")
            if value == "":
                return float(default)

        return float(value)
    except Exception:
        return float(default)


def _safe_int(value, default=0):
    if _impl_safe_int is not None:
        try:
            return _impl_safe_int(value, default)
        except Exception:
            pass

    try:
        return int(float(_safe_num(value, default)))
    except Exception:
        return int(default)


def _safe_text(value, default=""):
    if _impl_safe_text is not None:
        try:
            return _impl_safe_text(value, default)
        except Exception:
            pass

    try:
        if value is None:
            return str(default)
        return str(value).strip()
    except Exception:
        return str(default)


def _safe_append_csv(*args, **kwargs):
    if _impl_safe_append_csv is not None:
        try:
            return _impl_safe_append_csv(*args, **kwargs)
        except Exception as exc:
            st.warning(f"_safe_append_csv failed: {exc}")
            return False

    _fallback_show_error("_safe_append_csv", _safe_append_csv_import_error)
    return False


def _safe_read_csv(*args, **kwargs):
    if _impl_safe_read_csv is not None:
        try:
            return _impl_safe_read_csv(*args, **kwargs)
        except Exception as exc:
            st.warning(f"_safe_read_csv failed: {exc}")

    _fallback_show_error("_safe_read_csv", _safe_read_csv_import_error)

    try:
        import pandas as pd
        return pd.DataFrame()
    except Exception:
        return None


def _safe_rerun():
    if _impl_safe_rerun is not None:
        try:
            return _impl_safe_rerun()
        except Exception:
            pass

    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def _safe_log_event(message):
    if _impl_safe_log_event is not None:
        try:
            return _impl_safe_log_event(message)
        except Exception:
            pass

    try:
        st.session_state.setdefault("activity_log", [])
        st.session_state.activity_log.insert(
            0,
            {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event": str(message),
            },
        )
        st.session_state.activity_log = st.session_state.activity_log[:500]
    except Exception:
        pass


def _safe_close_sidebar():
    if _impl_safe_close_sidebar is not None:
        try:
            return _impl_safe_close_sidebar()
        except Exception:
            pass

    try:
        st.markdown(
            "<script>window.parent.postMessage('close-sidebar','*');</script>",
            unsafe_allow_html=True,
        )
    except Exception:
        pass


def _save_once_per_60_seconds(key="default_save_key"):
    if _impl_save_once_per_60_seconds is not None:
        try:
            return _impl_save_once_per_60_seconds(key)
        except Exception:
            pass

    now = time.time()
    state_key = f"_save_once_60_{key}"
    last = st.session_state.get(state_key, 0)

    try:
        if now - float(last) >= 60:
            st.session_state[state_key] = now
            return True
    except Exception:
        st.session_state[state_key] = now
        return True

    return False