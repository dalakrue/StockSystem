import streamlit as st

try:
    from core.ui_helpers import choice_buttons
except Exception:
    choice_buttons = None

try:
    from .helpers import init_profile_state
except Exception as e:
    init_profile_state = None
    INIT_ERROR = e
else:
    INIT_ERROR = None

try:
    from .styles import profile_css
except Exception as e:
    profile_css = None
    CSS_ERROR = e
else:
    CSS_ERROR = None

try:
    from .tabs import (
        render_overview_tab,
        render_edit_profile_tab,
        render_risk_checklist_tab,
        render_data_health_tab,
        render_saved_notes_tab,
        render_history_tab,
        render_settings_tab,
        render_train_data_tab,
        render_profile_score_tab,
        render_daily_plan_tab,
        render_performance_tab,
        render_guide_tab,
        render_activity_log_tab,
        render_system_health_tab,
    )
except Exception as e:
    TAB_IMPORT_ERROR = e

    def _fallback_tab(name):
        st.error(f"{name} could not load.")
        st.exception(TAB_IMPORT_ERROR)

    def render_overview_tab(): _fallback_tab("Overview")
    def render_edit_profile_tab(): _fallback_tab("Edit Profile")
    def render_risk_checklist_tab(): _fallback_tab("Risk Checklist")
    def render_data_health_tab(): _fallback_tab("Data Health")
    def render_saved_notes_tab(): _fallback_tab("Notes")
    def render_history_tab(): _fallback_tab("History")
    def render_settings_tab(): _fallback_tab("Settings")
    def render_train_data_tab(): _fallback_tab("Train Data")
    def render_profile_score_tab(): _fallback_tab("Profile Score")
    def render_daily_plan_tab(): _fallback_tab("Daily Plan")
    def render_performance_tab(): _fallback_tab("Performance")
    def render_guide_tab(): _fallback_tab("Guide")
    def render_activity_log_tab(): _fallback_tab("Activity Log")
    def render_system_health_tab(): _fallback_tab("System Health")


def _safe_render(name, func):
    try:
        func()
    except Exception as exc:
        st.error(f"{name} crashed, but Profile Dashboard stayed alive.")
        st.exception(exc)


def show():
    try:
        if init_profile_state:
            init_profile_state()
        elif INIT_ERROR:
            st.warning(f"Profile init failed: {INIT_ERROR}")
    except Exception as exc:
        st.warning(f"Profile state repair skipped: {exc}")

    try:
        if profile_css:
            profile_css()
        elif CSS_ERROR:
            st.caption(f"Profile CSS skipped: {CSS_ERROR}")
    except Exception as exc:
        st.caption(f"Profile CSS skipped safely: {exc}")

    st.markdown("# 👤 Quant Profile Dashboard")
    st.caption("Fast mode: only the selected Profile section renders. Tables inside sections stay in open/close fields where available.")

    names = [
        "📄 Overview", "✏️ Edit Profile", "🛡️ Risk Checklist", "🧪 Data Health",
        "📝 Notes", "📊 History", "⚙️ Settings", "🧠 Train Memory",
        "🧭 Profile Score", "🗓️ Daily Plan", "📈 Performance",
        "📘 Guide", "📘 Activity", "🧰 System Health",
    ]
    funcs = [
        render_overview_tab, render_edit_profile_tab, render_risk_checklist_tab, render_data_health_tab,
        render_saved_notes_tab, render_history_tab, render_settings_tab, render_train_data_tab,
        render_profile_score_tab, render_daily_plan_tab, render_performance_tab,
        render_guide_tab, render_activity_log_tab, render_system_health_tab,
    ]
    if callable(choice_buttons):
        choice = choice_buttons("Open Profile section", names, key="profile_lazy_section", columns=3, default=names[0])
    else:
        choice = st.selectbox("Open Profile section", names, key="profile_lazy_section")
    idx = names.index(choice) if choice in names else 0
    _safe_render(choice, funcs[idx])

