"""Compatibility loader for the refactored `core/pro_terminal_uiux.py` module.

The original large file was split into `pro_terminal_uiux_parts/part_*.py` chunks so no
active Python source file exceeds 500 lines. The chunks are executed in
this module namespace to preserve all existing imports and runtime behavior.
"""
from importlib import import_module as _import_module

_PARTS_PACKAGE = (__package__ + '.pro_terminal_uiux_parts') if __package__ else 'pro_terminal_uiux_parts'
_PART_COUNT = 2

_SOURCE = ""
for _idx in range(_PART_COUNT):
    _part = _import_module(f"{_PARTS_PACKAGE}.part_{_idx:03d}")
    _SOURCE += _part.SOURCE

exec(compile(_SOURCE, __file__, "exec"), globals(), globals())

del _idx, _part, _SOURCE, _import_module, _PARTS_PACKAGE, _PART_COUNT

# 2026-06-09 lighter button state patch
try:
    from .pro_terminal_uiux_patch_20260609 import apply as _apply_pro_terminal_uiux_patch_20260609
    _apply_pro_terminal_uiux_patch_20260609(globals())
    del _apply_pro_terminal_uiux_patch_20260609
except Exception:
    pass


# 2026-06-15 long-term central copy engine override.
# All existing imports of core.pro_terminal_uiux.render_mobile_copy_button now
# route to ui.copy_tools.central_copy_button with a download/text fallback.
try:
    from ui.copy_tools import central_copy_button as _new7_central_copy_button_20260615
    def render_mobile_copy_button(label: str, text: str, key: str) -> None:  # type: ignore[no-redef]
        _new7_central_copy_button_20260615(label, text, key, show_fallback=True)
except Exception:
    pass
