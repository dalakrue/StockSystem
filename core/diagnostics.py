"""Future Safety Guard diagnostics. Reads UI/app status only."""
from __future__ import annotations

from pathlib import Path
from typing import Dict
import streamlit as st

try:
    from ui.navigation_registry import registry_diagnostics, is_valid_tab, fallback_tab
except Exception:
    def registry_diagnostics(): return {"items": 0, "unique_keys": False, "unique_tabs": False, "tabs": [], "keys": []}
    def is_valid_tab(tab): return bool(tab)
    def fallback_tab(): return "Lunch"
try:
    from core.state_manager import required_file_check, safe_export_dir
except Exception:
    def required_file_check(project_root=None): return {"ok": False, "missing": ["core.state_manager failed"], "root": ""}
    def safe_export_dir(project_root=None): return Path("exports")

def startup_diagnostics(project_root: str | Path | None = None) -> Dict[str, object]:
    nav = registry_diagnostics()
    files = required_file_check(project_root)
    active = st.session_state.get("active_page", st.session_state.get("tab_choice", fallback_tab()))
    try:
        export_dir = safe_export_dir(project_root)
        export_ok = export_dir.exists() and export_dir.is_dir()
    except Exception:
        export_ok = False
        export_dir = ""
    return {
        "navigation_registry": bool(nav.get("items")) and bool(nav.get("unique_keys")) and bool(nav.get("unique_tabs")),
        "nav": nav,
        "active_page_valid": is_valid_tab(active),
        "required_files": bool(files.get("ok")),
        "missing_files": files.get("missing", []),
        "session_state_ready": bool(st.session_state.get("future_safety_guard_ready", False)),
        "export_path_ok": export_ok,
        "export_dir": str(export_dir),
        "css_loaded": bool(st.session_state.get("future_mobile_css_loaded", False)),
        "sidebar_backup": True,
    }

def status_label(ok: bool) -> str:
    return "PASS" if ok else "WARNING"

def duplicate_widget_key_scan(project_root: str | Path | None = None) -> Dict[str, object]:
    """Best-effort static detector for repeated literal Streamlit widget keys."""
    import re
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[1]
    pattern = re.compile(r"key\s*=\s*['\"]([^'\"]+)['\"]")
    hits: Dict[str, list] = {}
    for path in root.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for match in pattern.finditer(text):
            key = match.group(1)
            hits.setdefault(key, []).append(str(path.relative_to(root)))
    duplicates = {k: v for k, v in hits.items() if len(v) > 1}
    return {"ok": not duplicates, "duplicate_count": len(duplicates), "duplicates": duplicates}
