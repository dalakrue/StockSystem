import streamlit as st
from core.global_upgrade import render_page_shell, render_tab_footer
import pandas as pd
from core.ui.compact import render_metric_cards
from core.full_system_upgrade import render_database_upgrade_panel

from core.database import (
    database_health,
    database_relationship_summary,
    list_data_files,
    read_table,
    backup_all_data,
    compact_csv,
    repair_csv,
    delete_data_file,
    export_all_to_excel,
    save_market_cache,
    vacuum_sqlite,
)
from core.system_contract import render_relationship_matrix, timing_dataframe, system_events_dataframe


def _download_csv_button(df: pd.DataFrame, filename: str):
    """Local downloads are intentionally disabled; sidebar Download Center owns exports."""
    st.caption("⬇️ Download is centralized in the sidebar Download Center. This Database view is read-only.")


def show():
    render_page_shell(
        "Database",
        "Read-only backend and export relationship center. Downloads stay centralized in the sidebar.",
        "🗄️",
    )
    render_database_upgrade_panel()
    st.title("🗄️ Database Center")
    st.caption("Read-only backend view. Results auto-save from Home, Doo Prime, Engine, Train Data, and Profile. Download/export controls are centralized in the sidebar.")

    with st.expander("🔗 Open database + backend relationship", expanded=False):
        render_relationship_matrix(location="database", compact=True)
        health = database_relationship_summary()
        st.json(health)
        timing = timing_dataframe()
        if not timing.empty:
            with st.expander("⏱ Open tab timing table", expanded=False):
                st.dataframe(timing, use_container_width=True, hide_index=True)
        events = system_events_dataframe(80)
        if not events.empty:
            with st.expander("📜 Open system events table", expanded=False):
                st.dataframe(events, use_container_width=True, hide_index=True, height=240)

    health = database_relationship_summary()
    render_metric_cards([
        {"label": "Data Files", "value": health.get("files", 0)},
        {"label": "CSV Files", "value": health.get("csv_files", 0)},
        {"label": "Size KB", "value": health.get("total_size_kb", 0)},
        {"label": "SQLite Rows", "value": health.get("sqlite_event_rows", 0)},
    ])
    st.caption("✅ Auto-backend active: tables are written by result engines; no manual Save/Backup/Download buttons are shown here.")

    files = list_data_files()
    if files.empty:
        st.info("No database files found yet. Open Home, Doo Prime, Engine, or Train Data once; results will auto-save when available.")
        return

    with st.expander("📁 Open data files index", expanded=False):
        st.dataframe(files, use_container_width=True, hide_index=True)

    csv_files = files[files["type"].astype(str).str.upper().eq("CSV")].copy()
    tables = csv_files["table"].astype(str).tolist() if not csv_files.empty else []
    if not tables:
        st.warning("No CSV tables available to preview yet.")
        return

    left, right = st.columns([2, 1])
    with left:
        table = st.selectbox("Preview table", tables, key="database_table_choice")
    with right:
        limit = st.number_input("Rows to preview", min_value=50, max_value=50000, value=1000, step=50, key="database_limit")

    df = read_table(table, limit=int(limit))
    if df.empty:
        st.warning("This table has no readable rows yet or may need repair.")
        return

    search = st.text_input("Quick filter text", value="", key="database_search")
    view = df.copy()
    if search.strip():
        mask = view.astype(str).apply(lambda col: col.str.contains(search.strip(), case=False, na=False)).any(axis=1)
        view = view[mask]
    st.caption(f"Showing {len(view):,} row(s) from `{table}`. Use sidebar Download Center for CSV/Excel export.")
    with st.expander("📋 Open selected file rows", expanded=True):
        st.dataframe(view, use_container_width=True, hide_index=True)

    with st.expander("📊 Open auto summary", expanded=False):
        st.write("Columns:", list(view.columns))
        numeric = view.select_dtypes(include="number")
        if not numeric.empty:
            st.dataframe(numeric.describe().T, use_container_width=True)
        else:
            st.info("No numeric columns found for summary.")
