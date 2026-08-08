# Compact wrapper for Pre Original tab. Original implementation is preserved.
from core.global_upgrade import render_page_shell, render_tab_footer
from .pre_clean_split.pre_original import show as _original_show


def show():
    # Duplicate cleanup: keep one page header only. The repeated pro-tools,
    # relationship, and background expanders were removed from the wrapper;
    # original tab logic still renders below unchanged.
    render_page_shell(
        'Pre Original',
        'API-free emergency/pre-trade workspace with the same global UI and preserved original logic.',
        '🧾',
    )
    _original_show()
    render_tab_footer('Pre Original')
