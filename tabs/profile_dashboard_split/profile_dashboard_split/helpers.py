import streamlit as st
import pandas as pd

from core.database import append_csv, read_csv
from core.common import log_event


def safe_df(name):
    try:
        df = read_csv(name)
        if df is None:
            return pd.DataFrame()
        return df
    except Exception as e:
        st.warning(f"Could not load {name}: {e}")
        return pd.DataFrame()


def safe_append(name, row):
    try:
        append_csv(name, row)
        return True
    except Exception as e:
        st.error(f"Could not save to {name}: {e}")
        return False


def safe_log(msg):
    try:
        log_event(msg)
    except Exception:
        st.session_state.setdefault("activity_log", [])
        st.session_state.activity_log.insert(
            0,
            {"time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"), "event": msg},
        )


def init_profile_state():
    defaults = {
        "notes": [],
        "activity_log": [],
        "profile_name": "Quant Trader",
        "phone_mode": False,
        "profile_goal": "12H Hold Strategy",
        "risk_mode": "Balanced",
        "setting_auto_entry": True,
        "setting_exit_alerts": True,
        "setting_risk_active": True,
        "setting_phone_mode": False,
    }

    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def download_button(df, label, filename):
    if isinstance(df, pd.DataFrame) and not df.empty:
        st.caption(f"⬇️ `{filename}` export is available from the sidebar Download Center.")


def data_health_box(name, df):
    rows = 0 if df is None else len(df)
    cols = 0 if df is None or df.empty else len(df.columns)

    if rows == 0:
        status = "EMPTY"
        cls = "status-warn"
    elif rows < 20:
        status = "LOW DATA"
        cls = "status-warn"
    else:
        status = "READY"
        cls = "status-good"

    st.markdown(
        f"""
        <div class="profile-card">
            <div class="mini-title">{name}</div>
            <div class="big-value">{rows} rows / {cols} cols</div>
            <div class="{cls}">{status}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def filter_df(df, search_text=""):
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    if search_text.strip():
        s = search_text.strip().lower()
        mask = out.astype(str).apply(
            lambda col: col.str.lower().str.contains(s, na=False)
        ).any(axis=1)
        out = out[mask]

    return out
