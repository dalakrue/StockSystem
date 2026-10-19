import os
import math
import streamlit as st


def safe_rerun():
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def safe_num(x, default=0.0):
    try:
        if x is None:
            return float(default)

        if isinstance(x, str):
            x = x.strip().replace(",", "")
            if x == "":
                return float(default)

        value = float(x)

        if math.isnan(value) or math.isinf(value):
            return float(default)

        return value

    except Exception:
        return float(default)


def safe_int(x, default=0):
    try:
        return int(safe_num(x, default))
    except Exception:
        return int(default)


def safe_pct(x, default=0.0):
    return safe_num(x, default) / 100.0


def clamp(value, low, high, default=0.0):
    value = safe_num(value, default)
    return max(low, min(high, value))


def get_secret_or_env(*names, default=""):
    for name in names:
        try:
            v = st.secrets.get(name, None)
            if v is not None and str(v).strip() != "":
                return str(v).strip()
        except Exception:
            pass

        try:
            v = os.getenv(name)
            if v is not None and str(v).strip() != "":
                return str(v).strip()
        except Exception:
            pass

    return default