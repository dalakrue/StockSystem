"""Robust loader for V9 split-module compatibility wrappers.

The V9 project keeps large implementations in ``*_v9_parts/part_*.py`` files.
Some Windows/OneDrive copies were missing the generated ``implementation.py``
module even though the source parts were present.  This loader reconstructs the
original module directly from the part files, so wrappers no longer depend on
that generated intermediary file.

It does not alter calculation source: the exact stored source lines are joined,
compiled with the original wrapper path, and executed in one shared namespace.
"""
from __future__ import annotations

import ast
import linecache
import re
from pathlib import Path
from types import MappingProxyType
from typing import Any, MutableMapping

_METADATA_NAMES = frozenset(
    {
        "__name__",
        "__package__",
        "__file__",
        "__builtins__",
        "__spec__",
        "__loader__",
        "__cached__",
    }
)


def _read_source_lines(part_file: Path) -> list[str]:
    """Read the literal ``SOURCE_LINES`` assignment without importing the part."""
    text = part_file.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(part_file))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "SOURCE_LINES" for target in targets):
                try:
                    value = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    namespace: dict[str, Any] = {"__builtins__": __builtins__}
                    exec(compile(text, str(part_file), "exec"), namespace, namespace)
                    value = namespace.get("SOURCE_LINES")
                if not isinstance(value, list) or not all(isinstance(line, str) for line in value):
                    raise TypeError(f"{part_file}: SOURCE_LINES must be list[str]")
                return value
    raise AttributeError(f"{part_file}: SOURCE_LINES assignment was not found")



def _declared_module_name(parts_dir: Path, fallback: str) -> str:
    """Use the original module identity recorded by the V9 splitter."""
    implementation = parts_dir / "implementation.py"
    if implementation.is_file():
        try:
            text = implementation.read_text(encoding="utf-8")
            match = re.search(r'["\']__name__["\']\s*:\s*["\']([^"\']+)["\']', text)
            if match:
                return match.group(1)
        except Exception:
            pass
    if fallback == "_home_joined":
        return "tabs._home_joined"
    return fallback

def _load_split_source(wrapper_file: str | Path, module_name: str) -> tuple[Path, Path, str, str]:
    """Return wrapper path, parts directory, source text, and execution identity."""
    wrapper_path = Path(wrapper_file).resolve()
    stem_candidates = [wrapper_path.stem]
    without_date = re.sub(r"_20\d{6}$", "", wrapper_path.stem)
    if without_date not in stem_candidates:
        stem_candidates.append(without_date)
    # Prefer the generated V9 chunks, but also accept the archived non-V9
    # split directory. This prevents Streamlit Cloud failures when a deploy or
    # Git operation omits generated folders while retaining the archive.
    candidate_dirs: list[Path] = []
    for stem in stem_candidates:
        candidate_dirs.append(wrapper_path.with_name(f"{stem}_v9_parts"))
        candidate_dirs.append(wrapper_path.with_name(f"{stem}_parts"))

    parts_dir: Path | None = None
    part_files: list[Path] = []
    for candidate in candidate_dirs:
        files = sorted(candidate.glob("part_*.py")) if candidate.is_dir() else []
        if files:
            parts_dir = candidate
            part_files = files
            break

    if parts_dir is None or not part_files:
        # Protected wrappers may retain their original file hash. For those
        # modules, an exact standalone copy can be deployed beside the wrapper
        # and used only when generated split folders are missing.
        standalone_candidates = [
            wrapper_path.with_name(f"{stem}_standalone.py")
            for stem in stem_candidates
        ]
        standalone = next((path for path in standalone_candidates if path.is_file()), None)
        if standalone is not None:
            source = standalone.read_text(encoding="utf-8")
            if not source.strip():
                raise ImportError(f"Standalone fallback is empty for {module_name}: {standalone}")
            return wrapper_path, standalone.parent, source, module_name
        searched = ", ".join(str(path) for path in [*candidate_dirs, *standalone_candidates])
        raise ModuleNotFoundError(
            f"Split source is missing for {module_name}. Searched: {searched}. "
            "Deploy the complete repository or include its standalone fallback."
        )

    source_lines: list[str] = []
    for part_file in part_files:
        source_lines.extend(_read_source_lines(part_file))
    source = "".join(source_lines)
    if not source.strip():
        raise ImportError(f"V9 source parts are empty for {module_name}: {parts_dir}")
    execution_name = _declared_module_name(parts_dir, module_name)
    return wrapper_path, parts_dir, source, execution_name


def _register_linecache(wrapper_path: Path, source: str) -> None:
    """Expose reconstructed source to inspect, tracebacks, and debuggers."""
    linecache.cache[str(wrapper_path)] = (
        len(source), None, source.splitlines(keepends=True), str(wrapper_path)
    )


def load_split_namespace(wrapper_file: str | Path, module_name: str) -> dict[str, Any]:
    """Rebuild the implementation in an isolated namespace."""
    wrapper_path, _parts_dir, source, execution_name = _load_split_source(
        wrapper_file, module_name
    )
    package_name = execution_name.rpartition(".")[0]
    namespace: dict[str, Any] = {
        "__name__": execution_name,
        "__package__": package_name,
        "__file__": str(wrapper_path),
        "__builtins__": __builtins__,
    }
    _register_linecache(wrapper_path, source)
    exec(compile(source, str(wrapper_path), "exec"), namespace, namespace)
    return namespace


def export_split_namespace(
    target_globals: MutableMapping[str, Any],
    wrapper_file: str | Path,
    module_name: str,
) -> None:
    """Execute the exact split source directly in the real module namespace.

    Direct execution is important: function globals, monkeypatching, reloads, and
    module-level caches must all refer to the imported wrapper module itself.
    """
    wrapper_path, _parts_dir, source, execution_name = _load_split_source(
        wrapper_file, module_name
    )
    target_globals["__package__"] = execution_name.rpartition(".")[0]
    target_globals["__file__"] = str(wrapper_path)
    _register_linecache(wrapper_path, source)
    exec(compile(source, str(wrapper_path), "exec"), target_globals, target_globals)
    target_globals.setdefault(
        "__all__",
        [
            name for name in target_globals
            if not name.startswith("__") and name != "_export_split_namespace"
        ],
    )


LOADER_METADATA_NAMES = MappingProxyType({name: True for name in sorted(_METADATA_NAMES)})

__all__ = ["load_split_namespace", "export_split_namespace", "LOADER_METADATA_NAMES"]
