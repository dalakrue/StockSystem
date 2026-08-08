import time
import streamlit as st

from core.common import DEFAULT_TABS, log_event
from core.styles import request_close_sidebar
from core.ui_relationship import mark_navigation, sync_shared_connection_signature
from core.ui.effects import queue_ui_popup
from core.data_connectors import manual_connect
from core.websocket_feed import render_websocket_panel, websocket_status
from core.system_upgrade import sidebar_health_card, add_snapshot_button
from core.system_contract import render_sidebar_mini_contract, record_system_event
from core.system_relations import render_system_relation_hub
from core.global_upgrade import render_sidebar_upgrade_panel, render_sidebar_pro_header, data_quality, get_live_df
from core.ui.compact import render_metric_cards

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    def st_autorefresh(*args, **kwargs):
        return None


from .state import _safe_log_event
from .timer import _safe_rerun

def _priority_rank(table_name):
    priority = [
        "emergency_exit_decisions",
        "doo_exit_alerts",
        "doo_prime_account_history",
        "training_data_cache",
        "training_snapshots",
        "latest_market_cache",
        "engine_mix_snapshots",
        "home_snapshots",
        "risk_snapshots",
        "prelive_snapshots",
        "pre_manual_runs",
        "runtime_snapshots",
        "system_events",
    ]
    name = str(table_name or "")
    try:
        return priority.index(name)
    except ValueError:
        return len(priority) + 10

def _sidebar_download_center():
    try:
        from core.database import list_data_files, read_table, export_all_to_excel
    except Exception as exc:
        st.caption(f"Database download tools unavailable: {exc}")
        return

    files = list_data_files()
    if files is None or files.empty:
        st.caption("No saved database files yet. Results will auto-save after data appears.")
        return

    csv_files = files[files["type"].astype(str).str.upper().eq("CSV")].copy()
    if csv_files.empty:
        st.caption("No CSV tables available yet.")
        return

    csv_files["priority"] = csv_files["table"].map(_priority_rank)
    csv_files = csv_files.sort_values(["priority", "modified"], ascending=[True, False]).reset_index(drop=True)

    st.caption("Highest-priority trading/risk tables appear first. Most results auto-save; use this center for exports.")
    labels = [f"{r.table} · rows≈{r.rows_est} · {r.modified}" for r in csv_files.itertuples()]
    choice = st.selectbox("Download table", labels, key="sidebar_download_table_choice")
    idx = labels.index(choice) if choice in labels else 0
    table = str(csv_files.iloc[idx]["table"])
    limit = st.number_input("Rows to include", min_value=50, max_value=50000, value=5000, step=50, key="sidebar_download_limit")
    df = read_table(table, limit=int(limit))
    if df is None or df.empty:
        st.caption("Selected table has no readable rows yet.")
    else:
        st.download_button(
            "⬇️ Download selected CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{table}_export.csv",
            mime="text/csv",
            use_container_width=True,
            key="sidebar_download_selected_csv",
        )
    if st.button("📦 Build Excel export", use_container_width=True, key="sidebar_export_excel"):
        out = export_all_to_excel()
        if out:
            st.success(f"Excel export created: {out}")
        else:
            st.warning("Excel export failed safely.")

def _disconnect_shared_state(reason="manual disconnect"):
    """One safe disconnect path used by all sidebar buttons."""
    for k in [
        "connected", "source", "last_df", "last_fetch", "doo_deep_results",
        "doo_deep_last_refresh", "system_demo_guard_used", "last_connection_error",
        "last_connection_message", "last_connection_rows",
    ]:
        st.session_state.pop(k, None)
    st.session_state.connected = False
    st.session_state.source = "DISCONNECTED"
    st.session_state.last_connection_message = reason
    try:
        record_system_event("connection", reason, "OK", "Global sidebar disconnected shared data", persist=True)
    except Exception:
        pass
    queue_ui_popup("Connector disconnected", "All tabs are now waiting for shared data", "info")

def _sidebar_deep_sync_from_shared():
    """Refresh Home/Doo/Data Modeling blocks from the already-loaded dataframe."""
    try:
        df = get_live_df()
        if df is None or df.empty:
            st.warning("No shared dataframe yet. Connect or refresh data first.")
            return
        try:
            from tabs.home_split.doo_prime_deep import refresh_deep_doo_from_shared
            refresh_deep_doo_from_shared()
        except Exception as exc:
            st.session_state.doo_deep_sync_warning = str(exc)
            st.warning(f"Deep sync skipped safely: {exc}")
            return
        st.session_state.doo_deep_auto_fetch = True
        st.session_state.doo_data_modeling_ready = True
        st.toast("Doo/Data Modeling synced from shared dataframe", icon="✅")
        queue_ui_popup("Deep sync complete", "Home, Doo Prime, and modeling data are aligned", "success")
    except Exception as exc:
        st.warning(f"Deep sync failed safely: {exc}")

def _sidebar_one_click_console():
    """Visible sidebar command center.

    It does not duplicate connector logic. It sets the desired mode, then calls
    the same _connect_now() function used by existing sidebar buttons.
    """
    with st.expander("⚡ One-click sidebar command center", expanded=True):
        df = get_live_df()
        q = data_quality(df)
        render_metric_cards([
            {"label": "Rows", "value": f"{q.get('rows',0):,}", "delta": q.get("status", "NO DATA")},
            {"label": "Source", "value": st.session_state.get("source", "OFF"), "delta": st.session_state.get("timeframe", "M1")},
            {"label": "Symbol", "value": st.session_state.get("symbol", "XAUUSD")},
        ])

        r1 = st.columns(3)
        with r1[0]:
            if st.button("🏦 MT5/Doo 600", use_container_width=True, key="sidebar_pro_mt5_600"):
                st.session_state.connector_mode = "mt5"
                st.session_state.connector_bars = 600
                _connect_now("MT5/Doo quick connect", quick=True)
        with r1[1]:
            if st.button("🌉 Doo Bridge", use_container_width=True, key="sidebar_pro_doo_bridge"):
                st.session_state.connector_mode = "doo_bridge"
                st.session_state.connector_bars = 600
                _connect_now("Doo Bridge quick connect", quick=True)
        with r1[2]:
            if st.button("🌐 Finnhub + Twelve fallback", use_container_width=True, key="sidebar_pro_twelve_600"):
                st.session_state.connector_mode = "twelve_pool"
                st.session_state.connector_bars = 600
                _connect_now("Twelve Data key-pool connect", quick=True)

        r2 = st.columns(3)
        with r2[0]:
            if st.button("🔁 Refresh current", use_container_width=True, key="sidebar_pro_refresh_current"):
                _connect_now("Current connector refresh", quick=True)
        with r2[1]:
            if st.button("🧠 Sync modeling", use_container_width=True, key="sidebar_pro_deep_sync"):
                _sidebar_deep_sync_from_shared()
        with r2[2]:
            if st.button("⛔ Disconnect", use_container_width=True, key="sidebar_pro_disconnect"):
                _disconnect_shared_state("one-click sidebar disconnect")
        st.caption("Use this first: it controls the shared dataframe used by Home, Engine, Train Data, Database, and Profile.")

