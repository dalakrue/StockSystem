"""Future-proof App Shell helpers. Display/control layer only."""
from __future__ import annotations
from ui.mobile_css import inject_mobile_css
from ui.main_menu_drawer import render_main_menu_drawer
from ui.top_status_bar import render_top_status_bar
from ui.ui_health_check import render_ui_health_check
from ui.sidebar_fallback_panel import render_sidebar_fallback_panel
__all__ = ["inject_mobile_css", "render_main_menu_drawer", "render_top_status_bar", "render_ui_health_check", "render_sidebar_fallback_panel"]
