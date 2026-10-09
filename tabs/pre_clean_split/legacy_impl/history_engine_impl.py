"""Compatibility loader for the refactored `tabs/pre_clean_split/legacy_impl/history_engine_impl.py` module.

The original large file was split into `history_engine_impl_parts/part_*.py` chunks so no
active Python source file exceeds 500 lines. The chunks are executed in
this module namespace to preserve all existing imports and runtime behavior.
"""
from importlib import import_module as _import_module
from pathlib import Path as _Path

_PARTS_PACKAGE = (__package__ + '.history_engine_impl_parts') if __package__ else 'history_engine_impl_parts'
_parts_dir = _Path(__file__).resolve().with_name("history_engine_impl_parts")
_part_names = [path.stem for path in sorted(_parts_dir.glob("part_*.py")) if path.stem != "__init__"]
if not _part_names:
    raise ModuleNotFoundError(f"No history engine source parts found in {_parts_dir}")

_SOURCE = ""
for _part_name in _part_names:
    _part = _import_module(f"{_PARTS_PACKAGE}.{_part_name}")
    _SOURCE += _part.SOURCE

exec(compile(_SOURCE, __file__, "exec"), globals(), globals())

del _part_name, _part_names, _parts_dir, _part, _SOURCE, _import_module, _PARTS_PACKAGE, _Path
