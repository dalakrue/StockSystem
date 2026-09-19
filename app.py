"""Preferred Streamlit deployment entry point.

Run with: streamlit run app.py
"""
from __future__ import annotations
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Must run before Streamlit/Tornado creates an event loop on Windows.
try:
    from core.windows_asyncio_compat_20260619 import install_windows_selector_policy
    install_windows_selector_policy()
except Exception:
    pass

# Legacy static contract only; execution no longer imports the old router:
# from adx_dashpoard import main
from core.app_shell import run_app


def _run_startup_migrations() -> None:
    """Apply additive, idempotent database migrations before UI/calculation."""
    try:
        from core.multi_symbol_field10_20260701 import DB_PATH
        from core.timeframe_identity_migration_20260706 import migrate_timeframe_identity
        from core.field10_multi_symbol_repair_migration_20260707 import migrate_field10_multi_symbol_repair
        from core.normalized_multi_symbol_migration_20260707 import migrate_normalized_multi_symbol_schema
        from core.institutional_quant_migration_20260708 import migrate_institutional_quant_schema
        from core.field10_research_migration_20260709 import migrate_field10_research_authority
        migrate_timeframe_identity(DB_PATH, create_backup=True)
        migrate_field10_multi_symbol_repair(DB_PATH)
        migrate_normalized_multi_symbol_schema(DB_PATH)
        migrate_institutional_quant_schema(DB_PATH)
        migrate_field10_research_authority(DB_PATH)
    except Exception as exc:
        # Keep startup available; the calculation orchestrator repeats the migration
        # and exposes a concise incident if the database is genuinely unavailable.
        import logging
        logging.getLogger(__name__).exception("Startup migration failed: %s", type(exc).__name__)

if __name__ == "__main__":
    _run_startup_migrations()
    run_app()
