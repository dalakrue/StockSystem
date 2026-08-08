import streamlit as st

from .helpers import init_profile_state
from .styles import profile_css
from .tabs import (
    render_overview_tab,
    render_market_core_logic_tab,
    render_guide_tab,
    render_saved_notes_tab,
    render_edit_profile_tab,
    render_trade_history_tab,
    render_settings_tab,
    render_activity_log_tab,
    render_train_data_tab,
    render_system_health_tab,
)


def show():
    init_profile_state()
    profile_css()

    st.markdown("# 👤 Quant Profile Dashboard")

    tabs = st.tabs([
        "📄 Overview",
        "🧠 Market Core Logic",
        "📘 Guide",
        "📝 Saved Notes Viewer",
        "✏️ Edit Profile",
        "📊 Trade History",
        "⚙️ Settings",
        "📘 Activity Log",
        "🧪 Train Data",
        "🧰 System Health",
    ])

    with tabs[0]:
        render_overview_tab()

    with tabs[1]:
        render_market_core_logic_tab()

    with tabs[2]:
        render_guide_tab()

    with tabs[3]:
        render_saved_notes_tab()

    with tabs[4]:
        render_edit_profile_tab()

    with tabs[5]:
        render_trade_history_tab()

    with tabs[6]:
        render_settings_tab()

    with tabs[7]:
        render_activity_log_tab()

    with tabs[8]:
        render_train_data_tab()

    with tabs[9]:
        render_system_health_tab()
