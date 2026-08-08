"""Compatibility loader for split Home module.

Original source was divided into small chunk modules for future CSS/UIUX
and feature upgrades while keeping runtime behavior identical.
"""

from importlib import import_module as _import_module

_PART_MODULES = ['part_01', 'part_02', 'part_03', 'part_04', 'part_05', 'part_06']


def _load_original_source():
    chunks = []
    base = __package__ + ".doo_prime_deep_parts"
    for name in _PART_MODULES:
        chunks.append(_import_module(base + "." + name).PART)
    return "".join(chunks)


_ORIGINAL_SOURCE = _load_original_source()
exec(compile(_ORIGINAL_SOURCE, __file__, "exec"), globals(), globals())

# 2026-06-02 Finder UI/UX + adaptive 10-point reversal upgrade.
# Non-destructive: wraps existing functions after the split legacy source loads.
try:
    from .finder_uiux_upgrade import install as _install_finder_uiux_upgrade
    _install_finder_uiux_upgrade(globals())
except Exception:
    pass

# 2026-06-02 Finder/Home calculation sync + Arrow dataframe fix.
try:
    from .finder_home_sync_patch import install as _install_finder_home_sync_patch
    _install_finder_home_sync_patch(globals())
except Exception:
    pass


# 2026-06-02 Full correctness patch for Home/Finder 10-point reversal and Last Time >= 7/10.
try:
    from .reversal_engine_full_correct_patch import install as _install_reversal_engine_full_correct_patch
    _install_reversal_engine_full_correct_patch(globals())
except Exception:
    pass

# 2026-06-03 Home 25D table + Finder day-only 7/10 history upgrade.
try:
    from .home_finder_reversal_history_upgrade import install as _install_home_finder_reversal_history_upgrade
    _install_home_finder_reversal_history_upgrade(globals())
except Exception:
    pass

try:
    __all__
except NameError:
    __all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]


# 2026-06-03 V4 reversal cooldown + quality compression + fast Finder cache.
try:
    from .reversal_cooldown_quality_upgrade import install as _install_reversal_cooldown_quality_upgrade
    _install_reversal_cooldown_quality_upgrade(globals())
except Exception:
    pass

# 2026-06-03 Professional terminal UI/UX layer: wraps Finder in one open/close
# glass field and adds dynamic background support without touching calculations.
try:
    from .pro_terminal_uiux import install as _install_pro_terminal_uiux
    _install_pro_terminal_uiux(globals())
except Exception:
    pass

# 2026-06-03 V5: screenshot-style Home/inner-tab UI and one-field metric collapse.
try:
    from .v5_home_uiux_metric_collapse_patch import install as _install_v5_home_uiux_metric_collapse_patch
    _install_v5_home_uiux_metric_collapse_patch(globals())
except Exception:
    pass

# 2026-06-04 V12 causal no-future reversal engine: locked history rows.
try:
    from .causal_reversal_v12_patch import install as _install_causal_reversal_v12_patch
    _install_causal_reversal_v12_patch(globals())
except Exception:
    pass

# 2026-06-04 V13: locked table collection display for Home/Finder.
try:
    from .v13_locked_history_tables_patch import install as _install_v13_locked_history_tables_patch
    _install_v13_locked_history_tables_patch(globals())
except Exception:
    pass

# 2026-06-04 V14: Phase Transition Detector for early breakout preparation.
# Non-destructive: enriches V13 locked Home/Finder tables with causal/no-future
# market-structure columns without replacing the old 10-Reversal Decision.
try:
    from .v14_phase_transition_detector import install as _install_v14_phase_transition_detector
    _install_v14_phase_transition_detector(globals())
except Exception:
    pass
# 2026-06-04 V19: one-field 10-Reversal UI + compact now/prev/prev-prev metric.
try:
    from .v19_one_field_reversal_metric_patch import install as _install_v19_one_field_reversal_metric_patch
    _install_v19_one_field_reversal_metric_patch(globals())
except Exception:
    pass

