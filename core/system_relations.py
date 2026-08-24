"""File/tab/connection relationship hub."""
from __future__ import annotations

import importlib
from typing import Dict, List

import pandas as pd
import streamlit as st

RELATION_ROWS: List[Dict[str, str]] = [
    {"Layer": "Entry", "File": "main.py / adx_dashpoard.py", "Responsibility": "Starts core.app_shell.run_app"},
    {"Layer": "App shell", "File": "core/app/runner.py", "Responsibility": "Page config, refresh cycle, route load, safe page execution"},
    {"Layer": "Navigation", "File": "core/navigation.py", "Responsibility": "Sidebar tabs, connector settings, timer, download center"},
    {"Layer": "Connection", "File": "core/connectors/data_connectors.py", "Responsibility": "MT5, Doo bridge, TwelveData, fallback, OHLC normalization"},
    {"Layer": "Database", "File": "core/storage/database.py", "Responsibility": "CSV + SQLite mirror, exports, cache, table browser"},
    {"Layer": "UI/UX", "File": "core/ui/styles.py + core/ui/effects.py", "Responsibility": "Ocean glass CSS, popups, global HUD, phone layout"},
    {"Layer": "Home", "File": "tabs/home.py -> tabs/home_split/*", "Responsibility": "Command center, risk panels, Doo Prime home analytics"},
    {"Layer": "Engine", "File": "tabs/engine.py -> tabs/engine_split/*", "Responsibility": "Combined engine, original engine/prelive/backtest-compatible tools"},
    {"Layer": "Train Data", "File": "tabs/train_data.py", "Responsibility": "Training snapshots, cache, incremental learning view"},
    {"Layer": "Pre Original", "File": "tabs/pre_original.py -> tabs/pre_clean_split/*", "Responsibility": "API-free emergency pre-trade/exit/history modules"},
    {"Layer": "Profile", "File": "tabs/profile.py -> tabs/profile_dashboard_split/*", "Responsibility": "Profile state, strategy settings, notes/history"},
]

IMPORT_CHECKS = {
    "app runner": "core.app.runner",
    "navigation": "core.navigation",
    "connectors": "core.data_connectors",
    "database": "core.database",
    "ui styles": "core.styles",
    "ui effects": "core.ui.effects",
    "home tab": "tabs.home",
    "engine tab": "tabs.engine",
    "train data tab": "tabs.train_data",
    "pre original tab": "tabs.pre_original",
    "profile tab": "tabs.profile",
}


def relation_dataframe() -> pd.DataFrame:
    return pd.DataFrame(RELATION_ROWS)


def import_health_dataframe() -> pd.DataFrame:
    rows = []
    for label, module in IMPORT_CHECKS.items():
        try:
            importlib.import_module(module)
            rows.append({"Component": label, "Module": module, "Status": "OK", "Error": ""})
        except Exception as exc:
            rows.append({"Component": label, "Module": module, "Status": "ERROR", "Error": str(exc)[:220]})
    return pd.DataFrame(rows)


def render_system_relation_hub(compact: bool = True) -> None:
    rel = relation_dataframe()
    health = import_health_dataframe()
    ok = int((health["Status"] == "OK").sum()) if not health.empty else 0
    total = int(len(health)) if not health.empty else 0
    st.markdown(
        f'''
        <div class="qx-relation-hub">
          <b>File - Tab - Connection Hub</b><br>
          <span>{ok}/{total} core modules import cleanly. Sidebar connector is the single shared source; tabs consume session dataframe and database helpers.</span>
        </div>
        ''',
        unsafe_allow_html=True,
    )
    if compact:
        with st.expander("Open relationship map", expanded=False):
            st.dataframe(rel, use_container_width=True, hide_index=True)
            st.dataframe(health, use_container_width=True, hide_index=True)
    else:
        st.dataframe(rel, use_container_width=True, hide_index=True)
        st.dataframe(health, use_container_width=True, hide_index=True)
