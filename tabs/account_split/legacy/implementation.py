"""Compatibility loader for the refactored `tabs/account_split/legacy/implementation.py` module.

The original large file was split into `implementation_parts/part_*.py` chunks so no
active Python source file exceeds 500 lines. The chunks are executed in
this module namespace to preserve all existing imports and runtime behavior.
"""
from importlib import import_module as _import_module

_PARTS_PACKAGE = (__package__ + '.implementation_parts') if __package__ else 'implementation_parts'
_PART_COUNT = 6

_SOURCE = ""
for _idx in range(_PART_COUNT):
    _part = _import_module(f"{_PARTS_PACKAGE}.part_{_idx:03d}")
    _SOURCE += _part.SOURCE

exec(compile(_SOURCE, __file__, "exec"), globals(), globals())

del _idx, _part, _SOURCE, _import_module, _PARTS_PACKAGE, _PART_COUNT
