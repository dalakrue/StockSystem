"""Robust compatibility entry point for the decision product engine.

The V9 splitter stores the exact implementation under
``core.decision_product_engine_20260617_v9_parts.implementation``. Some Windows,
OneDrive, ZIP, or GitHub copies can omit or truncate that generated package.
This entry point validates the split namespace and automatically falls back to
the complete standalone implementation without changing calculation logic.
"""

# Future timestamps detected and safely excluded by the preserved implementation.

from __future__ import annotations

from importlib import import_module
from typing import Any, Callable, Mapping

_REQUIRED_PUBLIC = frozenset({
    "normalize_ohlc",
    "validate_data_quality",
    "build_decision_result",
    "serialize_result",
})


def _publish(namespace: Mapping[str, Any]) -> None:
    for name, value in namespace.items():
        if name.startswith("__"):
            continue
        globals()[name] = value


def _validate_namespace(namespace: Any) -> Mapping[str, Any]:
    if not isinstance(namespace, Mapping):
        raise TypeError("decision engine NAMESPACE is not a mapping")
    missing = sorted(name for name in _REQUIRED_PUBLIC if not callable(namespace.get(name)))
    if missing:
        raise ImportError("decision engine split package is incomplete: " + ", ".join(missing))
    return namespace


def _load_implementation(importer: Callable[[str], Any] = import_module) -> tuple[Mapping[str, Any], str, str | None]:
    """Return a validated namespace, source marker, and fallback reason.

    The injectable importer makes normal and missing-package behavior directly
    regression-testable without deleting project files.
    """
    try:
        split = importer("core.decision_product_engine_20260617_v9_parts.implementation")
        namespace = _validate_namespace(getattr(split, "NAMESPACE"))
        return namespace, "v9_parts", None
    except (ModuleNotFoundError, ImportError, AttributeError, TypeError, OSError, SyntaxError) as exc:
        standalone = importer("core.decision_product_engine_20260617_standalone")
        namespace = _validate_namespace(vars(standalone))
        return namespace, "standalone_fallback", f"{type(exc).__name__}: {exc}"


_namespace, IMPLEMENTATION_SOURCE, IMPLEMENTATION_FALLBACK_REASON = _load_implementation()
_publish(_namespace)

__all__ = [name for name in globals() if not name.startswith("_")]
