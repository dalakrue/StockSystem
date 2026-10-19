"""Future Safety Guard: session state initialization and validation."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List
import streamlit as st

try:
    from ui.navigation_registry import normalize_active_tab, fallback_tab
except Exception:
    def normalize_active_tab(tab): return str(tab or "Settings")
    def fallback_tab(): return "Settings"

REQUIRED_SESSION_DEFAULTS = {
    "active_page": "Settings",
    "active_inner_tab": "",
    "menu_open": False,
    "new7_main_menu_drawer_open": False,
    "ui_navigation_click_ts": 0.0,
    "fast_tab_switch_active": False,
    "future_safety_guard_ready": False,
    "future_safety_last_check": 0.0,
}

def init_future_safety_guard() -> None:
    for key, value in REQUIRED_SESSION_DEFAULTS.items():
        st.session_state.setdefault(key, value)
    current = st.session_state.get("tab_choice", st.session_state.get("active_page", fallback_tab()))
    fixed = normalize_active_tab(current)
    st.session_state["tab_choice"] = fixed
    st.session_state["active_page"] = fixed
    st.session_state["future_safety_guard_ready"] = True
    st.session_state["future_safety_last_check"] = time.time()

def set_active_page(tab: str) -> str:
    fixed = normalize_active_tab(tab)
    st.session_state["tab_choice"] = fixed
    st.session_state["active_page"] = fixed
    st.session_state["menu_open"] = False
    st.session_state["new7_main_menu_drawer_open"] = False
    st.session_state["ui_navigation_click_ts"] = time.time()
    st.session_state["fast_tab_switch_active"] = True
    return fixed

def required_file_check(project_root: str | Path | None = None) -> Dict[str, object]:
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[1]
    required = [
        "adx_dashpoard.py", "main.py", "app.py", "core/app/runner.py", "core/app/registry.py", "core/navigation.py",
        "ui/navigation_registry.py", "ui/main_menu_drawer.py", "ui/mobile_css.py", "ui/ui_health_check.py", "ui/error_boundary.py",
    ]
    missing: List[str] = [str(p) for p in required if not (root / p).exists()]
    return {"ok": not missing, "missing": missing, "root": str(root)}

def safe_export_dir(project_root: str | Path | None = None) -> Path:
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[1]
    export_dir = root / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir

def validate_export_path(filename: str, project_root: str | Path | None = None) -> Path:
    safe_name = Path(str(filename or "export.txt")).name.replace("\x00", "")
    if not safe_name:
        safe_name = "export.txt"
    return safe_export_dir(project_root) / safe_name
