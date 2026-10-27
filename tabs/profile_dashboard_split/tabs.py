import json
import streamlit as st
import pandas as pd

try:
    from .constants import GUIDE_TEXT
except Exception:
    GUIDE_TEXT = "Guide text could not load."

from .helpers import (
    safe_df,
    safe_append,
    safe_log,
    download_button,
    data_health_box,
    filter_df,
    get_live_df,
    safe_number,
    safe_dataframe_summary,
    compact_status,
    profile_snapshot_dict,
    profile_readiness_score,
    summarize_numeric_table,
)


def _now():
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")


def _len_df(df):
    return len(df) if isinstance(df, pd.DataFrame) else 0


def _download_json(obj, label, filename):
    st.caption(f"⬇️ `{filename}` export is centralized in the sidebar Download Center / database export area.")


def _latest_price(df):
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    for col in ["close", "bid", "price", "Close", "last"]:
        if col in df.columns:
            return safe_number(df[col].dropna().iloc[-1], None) if not df[col].dropna().empty else None
    return None


def _account_metrics():
    snap = st.session_state.get("account_snapshot", {})
    if not isinstance(snap, dict):
        snap = {}
    margin_level = safe_number(snap.get("margin_level") or snap.get("margin_level_pct") or snap.get("margin_level_percent"), 0)
    equity = safe_number(snap.get("equity"), 0)
    balance = safe_number(snap.get("balance"), 0)
    floating = safe_number(snap.get("profit") or snap.get("floating_pl") or snap.get("floating"), 0)
    positions = st.session_state.get("doo_positions", [])
    pos_count = len(positions) if isinstance(positions, list) else 0
    return snap, margin_level, equity, balance, floating, pos_count




def _profile_decision_state(margin_level, pos_count, live_rows):
    min_margin = float(st.session_state.get("profile_min_margin_level", 150.0) or 150.0)
    max_pos = int(st.session_state.get("profile_max_positions", 20) or 20)
    problems = []
    if not live_rows:
        problems.append("market data not loaded")
    if margin_level and margin_level < min_margin:
        problems.append(f"margin below plan ({margin_level:.2f}% < {min_margin:.2f}%)")
    if pos_count > max_pos:
        problems.append(f"too many positions ({pos_count} > {max_pos})")
    if not bool(st.session_state.get("setting_risk_active", True)):
        problems.append("risk engine toggle off")
    if problems:
        return "CAUTION", problems
    return "READY", ["profile settings, data, and risk rules are aligned"]


def _render_profile_control_strip():
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Source", st.session_state.get("source", "DISCONNECTED"))
    c2.metric("Symbol", st.session_state.get("symbol", "XAUUSD"))
    c3.metric("Timeframe", st.session_state.get("timeframe", "M1"))
    c4.metric("Phone Mode", "ON" if st.session_state.get("phone_mode", False) else "OFF")

def render_overview_tab():
    st.markdown('<div class="profile-card">', unsafe_allow_html=True)
    st.subheader("Trading Profile Command Center")

    live_df = get_live_df()
    notes = safe_df("saved_notes")
    engine = safe_df("engine_mix_snapshots")
    risk = safe_df("risk_snapshots")
    snap, margin_level, equity, balance, floating, pos_count = _account_metrics()
    price = _latest_price(live_df)

    c = st.columns(5)
    c[0].metric("Profile", st.session_state.get("profile_name", "Quant Trader"))
    c[1].metric("Goal", st.session_state.get("profile_goal", "12H Hold Strategy"))
    c[2].metric("Live Rows", f"{_len_df(live_df):,}")
    c[3].metric("Latest Price", "N/A" if price is None else f"{price:,.5f}")
    c[4].metric("Risk Mode", st.session_state.get("risk_mode", "Balanced"))

    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Equity", f"{equity:,.2f}" if equity else "N/A")
    c2.metric("Balance", f"{balance:,.2f}" if balance else "N/A")
    c3.metric("Floating P/L", f"{floating:,.2f}" if floating else "N/A")
    c4.metric("Margin Level %", f"{margin_level:,.2f}" if margin_level else "N/A")

    st.markdown(
        f"""
        <span class="profile-pill">Positions: {pos_count}</span>
        <span class="profile-pill">Connected: {st.session_state.get('source', 'DISCONNECTED')}</span>
        <span class="profile-pill">Symbol: {st.session_state.get('symbol', 'XAUUSD')}</span>
        <span class="profile-pill">Timeframe: {st.session_state.get('timeframe', 'M1')}</span>
        <span class="profile-pill">Notes: {_len_df(notes)}</span>
        <span class="profile-pill">Engine snapshots: {_len_df(engine)}</span>
        <span class="profile-pill">Risk snapshots: {_len_df(risk)}</span>
        """,
        unsafe_allow_html=True,
    )

    status, reasons = _profile_decision_state(margin_level, pos_count, _len_df(live_df))
    st.divider()
    d1, d2 = st.columns([1, 2])
    d1.metric("Profile Decision State", status)
    with d2:
        st.markdown("**Why:** " + "; ".join(reasons))
        st.caption("This is a Profile readiness check only. It does not open/close trades or change connector logic.")

    st.info("Profile tab is now a control center: it summarizes live data, account state, settings, saved notes, training memory, and app health without changing other tabs.")
    st.markdown("</div>", unsafe_allow_html=True)


def render_edit_profile_tab():
    st.subheader("Edit Trader Profile")
    c1, c2 = st.columns(2)
    with c1:
        name = st.text_input("Profile name", value=st.session_state.get("profile_name", "Quant Trader"), key="edit_profile_name")
        goal = st.text_input("Main trading goal", value=st.session_state.get("profile_goal", "12H Hold Strategy"), key="edit_profile_goal")
        style = st.selectbox("Trading style", ["12H Hold", "London Out", "NY Session", "Scalp", "Swing", "Custom"], index=0, key="edit_profile_style")
    with c2:
        risk_options = ["Safe", "Balanced", "Aggressive"]
        current = st.session_state.get("risk_mode", "Balanced")
        if current == "Conservative":
            current = "Safe"
        if current not in risk_options:
            current = "Balanced"
        risk_mode = st.selectbox("Risk mode", risk_options, index=risk_options.index(current), key="edit_risk_mode")
        max_risk = st.number_input("Max risk per idea %", 0.1, 10.0, float(st.session_state.get("profile_max_risk_pct", 1.0)), 0.1, key="edit_max_risk")
        min_margin = st.number_input("Minimum safe margin level %", 30.0, 1000.0, float(st.session_state.get("profile_min_margin_level", 150.0)), 5.0, key="edit_min_margin")

    if st.button("✅ Save Profile", key="save_profile_upgrade", use_container_width=True):
        st.session_state.profile_name = name.strip() or "Quant Trader"
        st.session_state.profile_goal = goal.strip() or "12H Hold Strategy"
        st.session_state.profile_style = style
        st.session_state.risk_mode = risk_mode
        st.session_state.profile_max_risk_pct = float(max_risk)
        st.session_state.profile_min_margin_level = float(min_margin)
        row = {"time": _now(), "name": st.session_state.profile_name, "goal": st.session_state.profile_goal, "style": style, "risk_mode": risk_mode, "max_risk_pct": max_risk, "min_margin_level": min_margin}
        safe_append("profile_changes", row)
        safe_log("Updated upgraded profile settings")
        st.success("Profile saved")


def render_risk_checklist_tab():
    st.subheader("Personal Risk Checklist")
    snap, margin_level, equity, balance, floating, pos_count = _account_metrics()
    min_margin = float(st.session_state.get("profile_min_margin_level", 150.0))
    max_pos = int(st.session_state.get("profile_max_positions", 20))

    checks = [
        ("Margin above personal minimum", margin_level >= min_margin if margin_level else False, f"Current {margin_level:.2f}% / minimum {min_margin:.2f}%" if margin_level else "No account snapshot"),
        ("Position count inside plan", pos_count <= max_pos, f"Current {pos_count} / max {max_pos}"),
        ("Risk engine active", bool(st.session_state.get("setting_risk_active", True)), "Toggle in Settings"),
        ("Exit alerts active", bool(st.session_state.get("setting_exit_alerts", True)), "Toggle in Settings"),
        ("Market data loaded", not get_live_df().empty, f"Rows: {_len_df(get_live_df()):,}"),
    ]
    for label, ok, detail in checks:
        st.markdown(f"{'✅' if ok else '⚠️'} **{label}** — {detail}")

    status = "READY" if all(ok for _, ok, _ in checks) else "CAUTION"
    st.metric("Profile Risk Status", status)
    try:
        last = float(st.session_state.get("profile_risk_checklist_last_auto_save", 0) or 0)
        import time as _time
        if _time.time() - last >= 60:
            row = {"time": _now(), "status": status, "margin_level": margin_level, "positions": pos_count, "risk_mode": st.session_state.get("risk_mode", "Balanced")}
            safe_append("profile_risk_checklist", row)
            st.session_state.profile_risk_checklist_last_auto_save = _time.time()
    except Exception:
        pass
    st.caption("✅ Auto-save active: Profile risk checklist snapshots save every 60 seconds. Manual Save button removed.")


def render_data_health_tab():
    st.subheader("Data Health")
    tables = ["home_snapshots", "engine_mix_snapshots", "prelive_snapshots", "pre_manual_runs", "risk_snapshots", "doo_prime_account_history", "saved_notes", "timer_history", "profile_changes", "settings_history", "profile_risk_checklist"]
    cols = st.columns(3)
    for i, name in enumerate(tables):
        with cols[i % 3]:
            data_health_box(name, safe_df(name))
    st.divider()
    live_df = get_live_df()
    st.markdown("### Current Connected DataFrame")
    live_summary = safe_dataframe_summary(live_df)
    hc1, hc2, hc3, hc4 = st.columns(4)
    hc1.metric("Rows", f"{live_summary['rows']:,}")
    hc2.metric("Columns", f"{live_summary['cols']:,}")
    hc3.metric("Missing %", f"{live_summary['missing_pct']:.2f}%")
    hc4.metric("Duplicate Rows", f"{live_summary['duplicate_rows']:,}")
    st.caption(f"Latest timestamp detected: {live_summary['latest_time']}")
    data_health_box("last_df/session market data", live_df)
    if not live_df.empty:
        with st.expander("📊 Open live data health table", expanded=False):
            st.dataframe(live_df.tail(120), use_container_width=True)
        download_button(live_df.tail(5000), "⬇️ Download latest market rows", "latest_market_rows.csv")


def render_saved_notes_tab():
    st.subheader("Notes / Trade Journal")
    st.session_state.setdefault("notes", [])
    note_type = st.selectbox("Note type", ["Market plan", "Exit plan", "Mistake review", "System idea", "General"], key="profile_note_type")
    note = st.text_area("Write note", key="profile_note_text", height=150)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 Save Note", key="save_note", use_container_width=True):
            if note.strip():
                row = {"time": _now(), "type": note_type, "symbol": st.session_state.get("symbol", "XAUUSD"), "note": note.strip()}
                st.session_state.notes.insert(0, row)
                safe_append("saved_notes", row)
                safe_log("Saved profile note")
                st.success("Note saved")
            else:
                st.warning("Write a note first.")
    with c2:
        if st.button("🧹 Clear Text", key="clear_note_box", use_container_width=True):
            st.session_state.profile_note_text = ""
            st.rerun()

    saved = safe_df("saved_notes")
    search = st.text_input("Search notes", key="note_search")
    filtered = filter_df(saved, search)
    if not filtered.empty:
        with st.expander("📝 Open notes table", expanded=False):
            st.dataframe(filtered.tail(200), use_container_width=True)
        download_button(filtered, "⬇️ Download notes", "saved_notes.csv")
    else:
        st.info("No saved notes found yet.")


def render_history_tab():
    st.subheader("History Explorer")
    history_names = ["home_snapshots", "engine_mix_snapshots", "prelive_snapshots", "pre_manual_runs", "risk_snapshots", "doo_prime_account_history", "profile_risk_checklist", "profile_changes", "settings_history", "saved_notes", "timer_history", "training_data", "mix_history", "backtest_results"]
    search = st.text_input("Search all history tables", key="history_search")
    for name in history_names:
        df = safe_df(name)
        with st.expander(f"{name} — {_len_df(df):,} rows"):
            filtered = filter_df(df, search)
            if filtered.empty:
                st.info("No data found.")
            else:
                with st.expander("📊 Open history table", expanded=False):
                    st.dataframe(filtered.tail(300), use_container_width=True)
                download_button(filtered, f"⬇️ Download {name}", f"{name}.csv")


def render_settings_tab():
    st.subheader("Profile Settings")
    _render_profile_control_strip()
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.session_state.setting_auto_entry = st.toggle("Auto Entry Engine", value=bool(st.session_state.get("setting_auto_entry", True)), key="toggle_auto_entry")
        st.session_state.setting_exit_alerts = st.toggle("Exit Engine Alerts", value=bool(st.session_state.get("setting_exit_alerts", True)), key="toggle_exit_alerts")
        st.session_state.setting_risk_active = st.toggle("Risk Engine Active", value=bool(st.session_state.get("setting_risk_active", True)), key="toggle_risk_active")
        st.session_state.profile_trade_journal_auto_save = st.toggle("Trade Journal Auto Save", value=bool(st.session_state.get("profile_trade_journal_auto_save", True)), key="toggle_journal_auto_save")
    with c2:
        st.metric("Display Mode", "Phone" if bool(st.session_state.get("phone_mode", False)) else "Laptop", "Change from ⋮ Menu")
        st.session_state.profile_max_positions = st.number_input("Max open positions warning", 1, 500, int(st.session_state.get("profile_max_positions", 20)), 1, key="profile_max_positions_input")
        st.session_state.profile_min_margin_level = st.number_input("Minimum safe margin level %", 30.0, 1000.0, float(st.session_state.get("profile_min_margin_level", 150.0)), 5.0, key="profile_min_margin_setting")

    row = {
        "time": _now(),
        "auto_entry": st.session_state.setting_auto_entry,
        "exit_alerts": st.session_state.setting_exit_alerts,
        "risk_active": st.session_state.setting_risk_active,
        "journal_auto_save": st.session_state.profile_trade_journal_auto_save,
        "phone_mode": st.session_state.phone_mode,
        "risk_mode": st.session_state.get("risk_mode", "Balanced"),
        "max_positions": st.session_state.profile_max_positions,
        "min_margin_level": st.session_state.profile_min_margin_level,
    }
    if st.button("💾 Save Settings Snapshot Now", key="save_profile_settings_now", use_container_width=True):
        safe_append("settings_history", row)
        safe_log("Saved profile settings snapshot")
        st.success("Profile settings snapshot saved")

    try:
        last = float(st.session_state.get("profile_settings_last_auto_save", 0) or 0)
        import time as _time
        if _time.time() - last >= 60:
            safe_append("settings_history", row)
            st.session_state.profile_settings_last_auto_save = _time.time()
    except Exception:
        pass
    st.caption("✅ Auto-save active: Profile settings snapshots save every 60 seconds. Use the button for immediate save.")

def render_train_data_tab():
    st.subheader("Training Memory")
    sources = ["engine_mix_snapshots", "prelive_snapshots", "pre_manual_runs", "risk_snapshots", "backtest_results"]
    source = st.selectbox("Training source", sources, key="profile_train_source")
    df = safe_df(source)
    if df.empty:
        st.warning(f"No saved rows in {source} yet.")
        return
    rows = st.number_input("Rows to load", 1, min(5000, len(df)), min(500, len(df)), key="profile_train_rows")
    with st.expander("🧠 Open train-memory data table", expanded=False):
        st.dataframe(df.tail(int(rows)), use_container_width=True)
    if st.button("🧠 Load Into Session Training Memory", key="profile_load_training", use_container_width=True):
        selected = df.tail(int(rows)).to_dict("records")
        st.session_state.training_rows = selected
        safe_log(f"Loaded {len(selected)} rows from {source} into training memory")
        st.success(f"Training memory active: {len(selected):,} rows")



def render_profile_score_tab():
    st.subheader("Profile Score / Readiness Gate")
    snap = profile_snapshot_dict()
    score, state, rules = profile_readiness_score(snap)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Profile Score", f"{score}/100")
    c2.metric("State", state)
    c3.metric("Source", snap.get("source", "DISCONNECTED"))
    c4.metric("Live Rows", f"{int(snap.get('live_rows', 0)):,}")
    st.caption("This score is a safety/readiness gate only. It never sends trade orders.")
    rules_df = pd.DataFrame(rules)
    st.dataframe(rules_df, use_container_width=True, hide_index=True)
    if st.button("💾 Save Profile Score Snapshot", key="save_profile_score_snapshot", use_container_width=True):
        row = dict(snap)
        row.update({"score": score, "state": state})
        safe_append("profile_score_history", row)
        safe_log(f"Saved profile score snapshot: {score}/100 {state}")
        st.success("Profile score snapshot saved")


def render_daily_plan_tab():
    st.subheader("Daily Trading Plan")
    st.caption("Use this as your pre-session checklist before relying on Engine / Home / Doo Prime analysis.")
    c1, c2 = st.columns(2)
    with c1:
        session = st.selectbox("Main session", ["Asia", "London", "New York", "London + New York Mix", "Custom"], key="profile_plan_session")
        bias = st.selectbox("Prepared bias", ["WAIT", "BUY only if confirmed", "SELL only if confirmed", "Both hedge management", "Emergency reduce only"], key="profile_plan_bias")
        max_loss = st.number_input("Max pain / loss limit today", 0.0, 1000000.0, float(st.session_state.get("profile_daily_max_loss", 0.0) or 0.0), 1.0, key="profile_daily_max_loss_input")
    with c2:
        exit_rule = st.text_area("Exit rule for today", value=st.session_state.get("profile_today_exit_rule", "Do not close one full side unless margin and directional confirmation agree."), height=110, key="profile_today_exit_rule_input")
        invalidation = st.text_area("Invalidation / stop condition", value=st.session_state.get("profile_today_invalidation", "If margin level approaches emergency zone, reduce paired BUY+SELL exposure first."), height=110, key="profile_today_invalidation_input")
    checks = {
        "Market data connected": st.checkbox("Market data connected", value=bool(st.session_state.get("connected", False)), key="plan_check_connected"),
        "Doo/MT5 account checked": st.checkbox("Doo/MT5 account checked", value=bool(st.session_state.get("account_snapshot", {})), key="plan_check_account"),
        "Margin rule reviewed": st.checkbox("Margin rule reviewed", value=False, key="plan_check_margin"),
        "Exit rule written": bool(str(exit_rule).strip()),
        "Invalidation written": bool(str(invalidation).strip()),
    }
    ready_count = sum(1 for v in checks.values() if bool(v))
    st.metric("Plan Completeness", f"{ready_count}/{len(checks)}")
    if st.button("💾 Save Daily Plan", key="save_profile_daily_plan", use_container_width=True):
        st.session_state.profile_daily_max_loss = float(max_loss)
        st.session_state.profile_today_exit_rule = str(exit_rule)
        st.session_state.profile_today_invalidation = str(invalidation)
        row = {"time": _now(), "session": session, "bias": bias, "max_loss": max_loss, "exit_rule": exit_rule, "invalidation": invalidation, "ready_count": ready_count, "total_checks": len(checks), "symbol": st.session_state.get("symbol", "XAUUSD")}
        safe_append("profile_daily_plans", row)
        safe_log("Saved daily trading plan")
        st.success("Daily plan saved")


def render_performance_tab():
    st.subheader("Profile Performance Summary")
    tables = ["profile_score_history", "profile_daily_plans", "profile_risk_checklist", "risk_snapshots", "engine_mix_snapshots", "saved_notes"]
    source = st.selectbox("Table to summarize", tables, key="profile_perf_source")
    df = safe_df(source)
    if df.empty:
        st.info(f"No rows found in {source} yet.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Rows", f"{len(df):,}")
    c2.metric("Columns", f"{len(df.columns):,}")
    c3.metric("Latest Saved", str(df.tail(1).get("time", df.tail(1).get("saved_at", pd.Series(["N/A"]))).iloc[0])[:32] if len(df) else "N/A")
    search = st.text_input("Search performance table", key="profile_perf_search")
    filtered = filter_df(df, search)
    with st.expander("📊 Open performance table", expanded=False):
        st.dataframe(filtered.tail(500), use_container_width=True)
    summary = summarize_numeric_table(filtered)
    if not summary.empty:
        st.markdown("### Numeric Summary")
        st.dataframe(summary, use_container_width=True, hide_index=True)
    download_button(filtered, f"⬇️ Download {source}", f"{source}.csv")


def render_guide_tab():
    st.subheader("Guide / Logic Library")
    search = st.text_input("Search guide", key="guide_search")
    if search.strip():
        matches = [line for line in GUIDE_TEXT.splitlines() if search.lower() in line.lower()]
        st.success(f"Found {len(matches)} matching lines")
        for line in matches[:120]:
            st.markdown(f"- {line}")
    else:
        st.markdown(GUIDE_TEXT)


def render_activity_log_tab():
    st.subheader("Activity Log")
    logs = pd.DataFrame(st.session_state.get("activity_log", []))
    if logs.empty:
        st.info("No session activity yet.")
    else:
        with st.expander("📘 Open activity log table", expanded=False):
            st.dataframe(logs, use_container_width=True)
        download_button(logs, "⬇️ Download activity log", "activity_log.csv")
    if st.button("🧹 Clear Session Activity", key="clear_activity_log", use_container_width=True):
        st.session_state.activity_log = []
        st.success("Activity cleared")
        st.rerun()


def render_system_health_tab():
    st.subheader("System Diagnostics")
    keys = []
    for k, v in st.session_state.items():
        keys.append({"key": k, "type": type(v).__name__, "preview": str(v)[:160]})
    df = pd.DataFrame(keys)
    with st.expander("🧰 Open system health table", expanded=False):
        st.dataframe(df, use_container_width=True)
    download_button(df, "⬇️ Download session diagnostics", "session_diagnostics.csv")
    export = {"time": _now(), "symbol": st.session_state.get("symbol"), "source": st.session_state.get("source"), "connected": st.session_state.get("connected"), "profile_name": st.session_state.get("profile_name"), "risk_mode": st.session_state.get("risk_mode"), "session_keys": list(st.session_state.keys())}
    _download_json(export, "⬇️ Download profile JSON snapshot", "profile_snapshot.json")

# Backward compatible aliases used by old imports
render_market_core_logic_tab = render_guide_tab
render_trade_history_tab = render_history_tab
