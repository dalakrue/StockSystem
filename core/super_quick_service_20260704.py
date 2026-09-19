"""Direct service entry for the existing Super Quick multi-symbol transaction."""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

VERSION = "super-quick-service-20260704-v1"


def run_super_quick(state: MutableMapping[str, Any], symbols: Sequence[str]) -> dict[str, Any]:
    """Invoke the existing calculation service directly, never by browser-click simulation."""
    from core.multi_symbol_field10_20260701 import SELECTED_KEY, MAIN_SYMBOL_KEY, run_selected_symbols, normalize_selected
    selected = normalize_selected(symbols)
    if not selected:
        return {"ok": False, "status": "NO_QUALIFIED_SYMBOLS", "version": VERSION}
    state[SELECTED_KEY] = selected
    state[MAIN_SYMBOL_KEY] = selected[0]
    state["settings_calculation_scope_20260625"] = "LUNCH_CORE"

    def _single_symbol_runner() -> Mapping[str, Any]:
        import tabs.home as home
        from core.settings_run_orchestrator_20260617 import run_settings_calculation
        return run_settings_calculation(home.__dict__)

    manifest = run_selected_symbols(state, _single_symbol_runner, scope="LUNCH_CORE")
    return {"ok": bool(manifest.get("completed_symbols")), "status": "COMPLETED" if manifest.get("completed_symbols") else "PARTIAL",
            "manifest": manifest, "version": VERSION}


__all__ = ["VERSION", "run_super_quick"]
