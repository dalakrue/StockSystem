"""Static guard for the single GlobalSymbolContext symbol authority."""
from __future__ import annotations

import ast
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

PROTECTED_KEYS = {
    "symbol", "selected_symbol", "canonical_display_symbol_20260709",
    "multi_symbol_selected_20260701", "multi_symbol_main_symbol_20260702",
    "connector_symbol_20260702", "calculation_symbol_20260702",
    "connector_symbol", "calculation_symbol", "settings_main_symbol", "settings_main_symbol_20260702",
}
APPROVED_FILES = {"core/global_symbol_compat.py"}
EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", "delivery", "backup", "backups"}

@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    key: str
    operation: str


def _literal_key(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _is_state_base(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id in {"state", "session_state"}
    return isinstance(node, ast.Attribute) and node.attr == "session_state"


def _targets(node: ast.AST) -> Iterable[tuple[str, int, str]]:
    if isinstance(node, ast.Subscript) and _is_state_base(node.value):
        key = _literal_key(node.slice)
        if key in PROTECTED_KEYS:
            yield key, node.lineno, "assignment"
    elif isinstance(node, (ast.Tuple, ast.List)):
        for item in node.elts:
            yield from _targets(item)


def scan_symbol_authority(root: str | Path) -> list[Violation]:
    root = Path(root)
    violations: list[Violation] = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel in APPROVED_FILES or any(part.lower() in EXCLUDED_PARTS for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=rel)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for key, line, op in _targets(target):
                        violations.append(Violation(rel, line, key, op))
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and _is_state_base(node.func.value):
                if node.func.attr in {"setdefault", "pop"} and node.args:
                    key = _literal_key(node.args[0])
                    if key in PROTECTED_KEYS:
                        violations.append(Violation(rel, node.lineno, key, node.func.attr))
                if node.func.attr == "update" and node.args and isinstance(node.args[0], ast.Dict):
                    for key_node in node.args[0].keys:
                        key = _literal_key(key_node) if key_node is not None else None
                        if key in PROTECTED_KEYS:
                            violations.append(Violation(rel, node.lineno, key, "update"))
    return sorted(violations, key=lambda v: (v.file, v.line, v.key))


def report(root: str | Path) -> dict:
    violations = scan_symbol_authority(root)
    return {"ok": not violations, "protected_keys": sorted(PROTECTED_KEYS), "approved_files": sorted(APPROVED_FILES),
            "violations": [asdict(v) for v in violations]}

__all__ = ["PROTECTED_KEYS", "APPROVED_FILES", "Violation", "scan_symbol_authority", "report"]
