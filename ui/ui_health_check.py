"""UI Health Check panel for future problem solving."""
from __future__ import annotations
import streamlit as st

try:
    from core.diagnostics import startup_diagnostics, status_label, duplicate_widget_key_scan
except Exception:
    def startup_diagnostics(project_root=None): return {"diagnostics_import": False}
    def status_label(ok): return "WARNING"

def render_ui_health_check(project_root=None, compact: bool = True) -> None:
    st.session_state.setdefault("show_ui_health_check", False)
    if compact:
        if st.button("🧪 UI Health Check", key="future_ui_health_check_toggle", use_container_width=True):
            st.session_state["show_ui_health_check"] = not st.session_state.get("show_ui_health_check", False)
    else:
        st.session_state["show_ui_health_check"] = True
    if not st.session_state.get("show_ui_health_check", False):
        return
    d = startup_diagnostics(project_root)
    checks = [
        ("Navigation Registry", d.get("navigation_registry", False)),
        ("Active Page", d.get("active_page_valid", False)),
        ("Required Files", d.get("required_files", False)),
        ("Session State", d.get("session_state_ready", False)),
        ("Export Path", d.get("export_path_ok", False)),
        ("Mobile CSS", d.get("css_loaded", False)),
        ("Sidebar Backup", d.get("sidebar_backup", False)),
    ]
    st.markdown('<div class="new7-health-card"><b>🧪 System UI Health Check</b></div>', unsafe_allow_html=True)
    for name, ok in checks:
        st.write(f"{status_label(bool(ok))} — {name}")
    missing = d.get("missing_files") or []
    if missing:
        st.warning("Missing future-proof files: " + ", ".join(map(str, missing)))
    dup = duplicate_widget_key_scan(project_root)
    if dup.get("ok"):
        st.write("PASS — Duplicate Static Widget Keys")
    else:
        st.warning(f"WARNING — {dup.get('duplicate_count')} repeated literal widget keys found. Existing legacy duplicates are reported for future cleanup, not auto-changed.")
