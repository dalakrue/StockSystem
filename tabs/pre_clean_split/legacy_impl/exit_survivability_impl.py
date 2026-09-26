"""Compatibility loader for the refactored `tabs/pre_clean_split/legacy_impl/exit_survivability_impl.py` module.

The original large file was split into `exit_survivability_impl_parts/part_*.py` chunks so no
active Python source file exceeds 500 lines. The chunks are executed in
this module namespace to preserve all existing imports and runtime behavior.
"""
from importlib import import_module as _import_module

_PARTS_PACKAGE = (__package__ + '.exit_survivability_impl_parts') if __package__ else 'exit_survivability_impl_parts'
_PART_COUNT = 4

_SOURCE = ""
for _idx in range(_PART_COUNT):
    _part = _import_module(f"{_PARTS_PACKAGE}.part_{_idx:03d}")
    _SOURCE += _part.SOURCE

exec(compile(_SOURCE, __file__, "exec"), globals(), globals())

del _idx, _part, _SOURCE, _import_module, _PARTS_PACKAGE, _PART_COUNT
