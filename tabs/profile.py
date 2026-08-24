# Compact wrapper for Profile tab. Original implementation is preserved.
from core.global_upgrade import render_page_shell, render_tab_footer
from core.full_system_upgrade import render_profile_upgrade_panel
try:
    from .profile_dashboard_split.profile import show as _original_show
except Exception:
    from .profile_dashboard_split.profile_dashboard import show as _original_show


def show():
    # Duplicate cleanup: keep one page header only. The repeated pro-tools,
    # relationship, and background expanders were removed from the wrapper;
    # original tab logic still renders below unchanged.
    render_page_shell(
        'Profile',
        'Profile, system settings, tab relationship status, UI mode, and upgrade health dashboard.',
        '👤',
    )
    render_profile_upgrade_panel()
    _original_show()
    render_tab_footer('Profile')
