import streamlit as st
import pandas as pd

from .constants import GUIDE_TEXT
from .helpers import (
    safe_df,
    safe_append,
    safe_log,
    download_button,
    data_health_box,
    filter_df,
)


def render_overview_tab():
    st.markdown('<div class="profile-card">', unsafe_allow_html=True)
    st.subheader("Trading Intelligence Overview")

    history = safe_df("backtest_results")
    timer = safe_df("timer_history")
    saved_notes = safe_df("saved_notes")

    c = st.columns(4)
    c[0].metric("Saved Backtests", len(history))
    c[1].metric("Timer Records", len(timer))
    c[2].metric(
        "Saved Notes",
        len(saved_notes) if not saved_notes.empty else len(st.session_state.get("notes", [])),
    )
    c[3].metric("Activity Logs", len(st.session_state.get("activity_log", [])))

    st.divider()

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("### 👤 Profile")
        st.write("Name:", st.session_state.get("profile_name", "Quant Trader"))
        st.write("Goal:", st.session_state.get("profile_goal", "12H Hold Strategy"))
    with c2:
        st.markdown("### ⚙️ Engine")
        st.write("Auto Entry:", "ON" if st.session_state.get("setting_auto_entry") else "OFF")
        st.write("Exit Alerts:", "ON" if st.session_state.get("setting_exit_alerts") else "OFF")
        st.write("Risk Engine:", "ON" if st.session_state.get("setting_risk_active") else "OFF")
    with c3:
        st.markdown("### 📱 UI")
        st.write("Phone Mode:", "ON" if st.session_state.get("phone_mode") else "OFF")
        st.write("Risk Mode:", st.session_state.get("risk_mode", "Balanced"))

    if not history.empty:
        st.markdown("### Latest Backtest Results")
        st.dataframe(history.tail(15), use_container_width=True)
        download_button(history, "⬇️ Download Backtest CSV", "backtest_results.csv")
    else:
        st.info("No backtest results saved yet.")

    st.markdown("</div>", unsafe_allow_html=True)


def render_market_core_logic_tab():
    st.markdown('<div class="profile-card">', unsafe_allow_html=True)
    st.markdown(GUIDE_TEXT)
    st.info("This guide keeps the original reading material and adds the upgraded ML/history-matching explanation.")
    st.markdown("</div>", unsafe_allow_html=True)


def render_guide_tab():
    st.markdown('<div class="profile-card">', unsafe_allow_html=True)

    search_guide = st.text_input("Search guide text", key="guide_search")

    if search_guide.strip():
        parts = GUIDE_TEXT.splitlines()
        matches = [line for line in parts if search_guide.lower() in line.lower()]
        st.success(f"Found {len(matches)} matching lines")
        for line in matches[:100]:
            st.markdown(f"- {line}")
    else:
        st.markdown(GUIDE_TEXT)

    st.markdown("</div>", unsafe_allow_html=True)


def render_saved_notes_tab():
    st.subheader("Saved Notes")

    note = st.text_area("Write / edit note", key="profile_note_text", height=160)

    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("💾 Save Note", key="save_note", use_container_width=True):
            if note.strip():
                row = {
                    "time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "note": note.strip(),
                }
                st.session_state.notes.insert(0, row)
                safe_append("saved_notes", row)
                safe_log("Saved profile note")
                st.success("Note saved")
                st.rerun()
            else:
                st.warning("Write a note first.")

    with c2:
        if st.button("🧹 Clear Text Box", key="clear_note_box", use_container_width=True):
            st.session_state.profile_note_text = ""
            st.rerun()

    with c3:
        if st.button("🗑️ Delete Session Notes", key="delete_notes", use_container_width=True):
            st.session_state.notes = []
            safe_log("Deleted session notes")
            st.success("Session notes deleted")
            st.rerun()

    saved = safe_df("saved_notes")

    note_search = st.text_input("Search saved notes", key="note_search")
    filtered_notes = filter_df(saved, note_search)

    if not filtered_notes.empty:
        st.dataframe(filtered_notes.tail(100), use_container_width=True)
        download_button(filtered_notes, "⬇️ Download Notes CSV", "saved_notes.csv")
    else:
        st.info("No saved notes found.")

    if st.session_state.get("notes"):
        st.markdown("### Session Notes")
        for i, n in enumerate(st.session_state.get("notes", [])):
            with st.expander(f"{n.get('time', 'unknown')} — note {i + 1}"):
                st.write(n.get("note", ""))


def render_edit_profile_tab():
    st.subheader("Edit Profile")

    name = st.text_input(
        "Profile name",
        value=st.session_state.get("profile_name", "Quant Trader"),
        key="edit_profile_name",
    )

    style = st.selectbox(
        "Trading style",
        ["12H Hold", "NY Session", "London Out", "Scalp", "Swing"],
        key="edit_profile_style",
    )

    goal = st.text_input(
        "Main trading goal",
        value=st.session_state.get("profile_goal", "12H Hold Strategy"),
        key="edit_profile_goal",
    )

    risk_mode = st.selectbox(
        "Risk mode",
        ["Conservative", "Balanced", "Aggressive"],
        index=["Conservative", "Balanced", "Aggressive"].index(
            st.session_state.get("risk_mode", "Balanced")
        ),
        key="edit_risk_mode",
    )

    if st.button("✅ Update Profile", key="update_profile", use_container_width=True):
        st.session_state.profile_name = name
        st.session_state.profile_goal = goal
        st.session_state.risk_mode = risk_mode

        row = {
            "time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "name": name,
            "style": style,
            "goal": goal,
            "risk_mode": risk_mode,
        }

        safe_append("profile_changes", row)
        safe_log("Updated profile")
        st.success("Profile updated")


def render_trade_history_tab():
    st.subheader("Trade / System History")

    history_names = [
        "engine_mix_snapshots",
        "prelive_snapshots",
        "pre_manual_runs",
        "risk_snapshots",
        "doo_prime_account_history",
        "backtest_results",
        "timer_history",
        "profile_changes",
        "saved_notes",
    ]

    history_search = st.text_input("Search all history tables", key="history_search")

    for name in history_names:
        df = safe_df(name)
        with st.expander(f"{name} — {len(df)} rows"):
            filtered = filter_df(df, history_search)
            if filtered.empty:
                st.info("No data found.")
            else:
                st.dataframe(filtered.tail(300), use_container_width=True)
                download_button(filtered, f"⬇️ Download {name}", f"{name}.csv")


def render_settings_tab():
    st.subheader("System Settings")

    st.session_state.setting_auto_entry = st.toggle(
        "Auto Entry Engine",
        value=st.session_state.get("setting_auto_entry", True),
        key="toggle_auto_entry",
    )

    st.session_state.setting_exit_alerts = st.toggle(
        "Exit Engine Alerts",
        value=st.session_state.get("setting_exit_alerts", True),
        key="toggle_exit_alerts",
    )

    st.session_state.setting_risk_active = st.toggle(
        "Risk Engine Active",
        value=st.session_state.get("setting_risk_active", True),
        key="toggle_risk_active",
    )

    st.session_state.setting_phone_mode = bool(st.session_state.get("phone_mode", False))
    st.metric("Display Mode", "Phone" if st.session_state.setting_phone_mode else "Laptop", "Change from ⋮ Menu")

    st.info("Settings are stored safely in session_state and will not break original modules.")

    st.caption("✅ Settings snapshots auto-save in the active Profile dashboard. Manual Save button removed.")


def render_activity_log_tab():
    st.subheader("Activity Log")

    logs = pd.DataFrame(st.session_state.get("activity_log", []))

    if logs.empty:
        saved_logs = safe_df("activity_log")
        if not saved_logs.empty:
            logs = saved_logs

    if logs.empty:
        st.info("No activity logs yet.")
    else:
        st.dataframe(logs, use_container_width=True)
        download_button(logs, "⬇️ Download Activity Log", "activity_log.csv")

    if st.button("🧹 Clear Session Activity Log", key="clear_activity_log", use_container_width=True):
        st.session_state.activity_log = []
        st.success("Session activity log cleared")
        st.rerun()


def render_train_data_tab():
    st.subheader("Train Data From Exited/Saved Results")

    df = safe_df("backtest_results")

    if df.empty:
        st.warning("No saved backtest results yet.")
    else:
        st.dataframe(df.tail(200), use_container_width=True)

        c1, c2 = st.columns(2)

        with c1:
            train_rows = st.number_input(
                "Rows to load into training memory",
                min_value=50,
                max_value=5000,
                value=min(500, max(50, len(df))),
                step=50,
                key="train_rows_count",
            )

        with c2:
            st.metric("Available Rows", len(df))

        if st.button("🧪 Train Memory From Saved Results", key="train_saved", use_container_width=True):
            selected = df.tail(int(train_rows))
            st.session_state.training_rows = selected.to_dict("records")
            safe_log(f"Loaded {len(selected)} rows into training memory")
            st.success(f"Loaded {len(selected)} rows into training memory")

        if st.session_state.get("training_rows"):
            st.success(f"Training memory active: {len(st.session_state.training_rows)} rows")


def render_system_health_tab():
    st.subheader("System Health Check")

    check_files = [
        "backtest_results",
        "timer_history",
        "saved_notes",
        "profile_changes",
        "settings_history",
        "engine_mix_snapshots",
        "prelive_snapshots",
        "risk_snapshots",
    ]

    cols = st.columns(2)

    for i, name in enumerate(check_files):
        df = safe_df(name)
        with cols[i % 2]:
            data_health_box(name, df)

    st.divider()

    st.markdown("### Session State Keys")
    ss = pd.DataFrame(
        [{"key": k, "type": type(v).__name__, "preview": str(v)[:120]} for k, v in st.session_state.items()]
    )

    st.dataframe(ss, use_container_width=True)

    download_button(ss, "⬇️ Download Session State Preview", "session_state_preview.csv")
