# Compact wrapper for Engine tab. Original implementation is preserved.
from core.global_upgrade import render_page_shell, render_tab_footer
from core.full_system_upgrade import render_engine_upgrade_panel
from .engine_split.combined_engine import show as _original_show


def show():
    # V24: Train Data and Database moved to the top-level "Other" inner
    # workspace. Engine now renders only the preserved original engine logic to
    # avoid duplicate inner navigation and extra RAM use.
    render_page_shell('Engine', 'Decision engine workspace. Runs only after Other -> Run Calculate.', '⚡')
    render_engine_upgrade_panel()
    _original_show()
    render_tab_footer('Engine')
