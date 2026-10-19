"""Compatibility wrapper for the permanent future-proof main-page drawer.

The real drawer now lives in ui.main_menu_drawer. This module keeps the old
import path working without duplicating Menu / Close controls.
"""
from __future__ import annotations


def render_stable_main_menu_panel(current_tab=None):
    from ui.main_menu_drawer import render_main_menu_drawer
    return render_main_menu_drawer(current_tab)
