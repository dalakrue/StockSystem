"""Future upgrade/downgrade architecture registry (2026-06-15).

Small, safe architecture layer for flexible upgrades. It records where stable
features live and exposes a status panel. It never changes trading formulas.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List
import importlib
import streamlit as st
import pandas as pd


@dataclass(frozen=True)
class ArchitectureLayer:
    name: str
    path: str
    purpose: str
    downgrade_safe: bool = True
    heavy: bool = False


ARCHITECTURE_LAYERS: List[ArchitectureLayer] = [
    ArchitectureLayer("App runner", "core.app.runner", "One page shell, style loading, auth, lazy route isolation"),
    ArchitectureLayer("Route registry", "core.app.registry", "Add/remove top tabs without touching page logic"),
    ArchitectureLayer("AntD navigation", "ui.antd_navigation_20260615", "Nested page/subpage state sync"),
    ArchitectureLayer("Liquid app drawer", "ui.main_menu_drawer", "Three-dot sidebar replacement: menu, connector, timer, copy, UI"),
    ArchitectureLayer("Master run/copy rail", "ui.home_master_control_bar_20260615", "Single Run All before Copy Short/Full"),
    ArchitectureLayer("NLP pipeline", "core.nlp_lightweight_20260615", "Local tokenization through generation pipeline", heavy=False),
    ArchitectureLayer("AI Assistant", "tabs.ai_assistant_lite", "Local pattern library, Enter-to-answer, no API"),
    ArchitectureLayer("Alpha/Delta points", "core.alpha_delta_points_20260615", "Display-only blue/red/regime path diagnostics"),
    ArchitectureLayer("Research tab", "tabs.research", "Data analysis/mining/NLP practice, run-gated"),
]


def safe_import_status(module_path: str) -> Dict[str, str]:
    try:
        importlib.import_module(module_path)
        return {"module": module_path, "status": "READY", "note": "import ok"}
    except Exception as exc:
        return {"module": module_path, "status": "SAFE FALLBACK", "note": str(exc).splitlines()[0][:160]}


def architecture_status_frame() -> pd.DataFrame:
    rows = []
    for layer in ARCHITECTURE_LAYERS:
        stat = safe_import_status(layer.path)
        row = asdict(layer)
        row.update(stat)
        rows.append(row)
    return pd.DataFrame(rows)


def upgrade_rules() -> List[str]:
    return [
        "Add future features as a new small file, then register/import defensively.",
        "Do not edit trading formulas directly unless the user explicitly asks.",
        "Keep heavy data mining, charts, and exports behind Run All / section-run gates.",
        "Use session_state feature flags for downgrade: disable a module without deleting it.",
        "Use unique widget keys ending with date/version to avoid duplicate-key crashes.",
        "Primary navigation is Liquid App Drawer + AntD state; native sidebar stays backup only.",
    ]


def render_architecture_upgrade_panel() -> None:
    st.markdown("#### 🏗️ Upgrade / Downgrade Architecture")
    st.caption("Future-proof map. Display-only; it does not change predictions, ML, regime, PowerBI, or copy/export logic.")
    df = architecture_status_frame()
    try:
        from ui.stable_ui_libs_20260615 import modern_table
        modern_table(df, "architecture_status_20260615", height=310)
    except Exception:
        st.dataframe(df, use_container_width=True, hide_index=True, height=310)
    st.markdown("#### Safe upgrade rules")
    for rule in upgrade_rules():
        st.write("• " + rule)
