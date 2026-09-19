"""Mobile-safe CSV/ZIP export panel for Field 10 authority snapshots."""
from __future__ import annotations
from collections.abc import Mapping, MutableMapping
from typing import Any
import pandas as pd


def render_mobile_export_panel(st, state: MutableMapping[str, Any]) -> None:
    from core.field10_unified_authority_20260709 import (
        UNIFIED_TABLE_KEY, SESSION_TABLE_KEY, NEWS_TABLE_KEY, DINNER_TABLE_KEY, VIZ_TABLE_KEY,
        SUPPORTING_TABLE_KEY, MERGED_TABLE_KEY, BACKGROUND_TABLE_KEY, UNIFIED_SNAPSHOT_KEY, authority_csv_bytes, full_snapshot_zip_bytes,
    )
    from core.background_function_registry import function_status_frame

    snapshot = state.get(UNIFIED_SNAPSHOT_KEY) if isinstance(state.get(UNIFIED_SNAPSHOT_KEY), Mapping) else {}
    snapshot_hash = str(snapshot.get("snapshot_hash") or "no_snapshot")
    broker_day = str(snapshot.get("broker_day") or "unknown_day")
    timeframe = str(snapshot.get("timeframe") or "H4")
    with st.expander("Open / Close — CSV Export and Phone Download Panel", expanded=False):
        st.caption("Normal expander only: no full-screen modal, no trapped download mode, no heavy recalculation.")
        if st.button("Exit Download Mode", key=f"exit_download_mode_{snapshot_hash}", use_container_width=True):
            state["mobile_download_mode_20260709"] = False
            state["mobile_export_panel_open_20260709"] = False
            st.success("Download mode closed. Current tab and selected symbol are preserved.")
        if st.button("Close Export Panel", key=f"close_export_panel_{snapshot_hash}", use_container_width=True):
            state["mobile_export_panel_open_20260709"] = False
            st.info("Export panel closed.")
        downloads = [
            ("Download Field 10 Merged Authority + Entry Timing CSV", MERGED_TABLE_KEY, "field10_merged_authority_entry_timing_rank"),
            ("Download Field 10 Unified Rank CSV", UNIFIED_TABLE_KEY, "field10_unified_rank"),
            ("Download Field 10 Session Rank CSV", SESSION_TABLE_KEY, "field10_session_rank"),
            ("Download Field 10 News Event Rank CSV", NEWS_TABLE_KEY, "field10_news_event_rank"),
            ("Download Field 10 Supporting Evidence Entry Timing CSV", SUPPORTING_TABLE_KEY, "field10_supporting_evidence_entry_timing_rank"),
            ("Download Dinner Research Evidence CSV", DINNER_TABLE_KEY, "dinner_research_evidence"),
            ("Download Visualization CSV", VIZ_TABLE_KEY, "data_visualization"),
            ("Download Background Function Status CSV", BACKGROUND_TABLE_KEY, "background_function_status"),
        ]
        for label, key, prefix in downloads:
            frame = state.get(key)
            if key == BACKGROUND_TABLE_KEY and not isinstance(frame, pd.DataFrame):
                frame = function_status_frame(snapshot_hash)
            if isinstance(frame, pd.DataFrame) and not frame.empty:
                st.download_button(
                    label,
                    data=authority_csv_bytes(frame, snapshot),
                    file_name=f"{prefix}_{broker_day}_{timeframe}_{snapshot_hash}.csv".replace("/", "_"),
                    mime="text/csv",
                    use_container_width=True,
                    key=f"download_{prefix}_{snapshot_hash}",
                )
            else:
                st.caption(f"{label}: unavailable until a current snapshot is materialized.")
        st.download_button(
            "Download Full Snapshot Evidence ZIP",
            data=full_snapshot_zip_bytes(state),
            file_name=f"full_snapshot_export_{broker_day}_{timeframe}_{snapshot_hash}.zip".replace("/", "_"),
            mime="application/zip",
            use_container_width=True,
            key=f"download_full_snapshot_zip_{snapshot_hash}",
        )
