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
        migrate_timeframe_identity(DB_PATH, create_backup=True)
        migrate_field10_multi_symbol_repair(DB_PATH)
        migrate_normalized_multi_symbol_schema(DB_PATH)
        migrate_institutional_quant_schema(DB_PATH)
    except Exception as exc:
        # Keep startup available; the calculation orchestrator repeats the migration
        # and exposes a concise incident if the database is genuinely unavailable.
        import logging
        logging.getLogger(__name__).exception("Startup migration failed: %s", type(exc).__name__)

def _start_startup_work_in_background() -> None:
    """Speed fix 2026-11-28 (user order: the app must open in 1-5 s
    outside check windows): everything heavy that used to run
    synchronously before the UI now starts on daemon threads.

    - The candle-cache restore (an ~890 MB rebuild on a cold boot)
      starts immediately and overlaps the runner's local startup.
    - The startup migrations run once per DB file version per
      process instead of on every rerun (two of them re-scan the
      whole candle store per call -- ~49 s on a small VM). No
      calculation can outrun its migration: CandleRepository still
      runs the deployment migration synchronously on construction,
      and the calculation orchestrator repeats it, exactly as
      _run_startup_migrations' own note describes.
    """
    try:
        from core.multi_symbol_field10_20260701 import DB_PATH
        try:
            from core.data.cache_boot import ensure_cache_db_async
            ensure_cache_db_async(DB_PATH)
        except Exception:
            pass
        try:
            _st = DB_PATH.stat()
            stamp = (_st.st_size, _st.st_mtime_ns)
        except Exception:
            stamp = None
        from core.startup_once_20261128 import claim
        if claim("startup_migrations", stamp):
            import threading
            threading.Thread(
                target=_run_startup_migrations, daemon=True,
                name="startup_migrations").start()
    except Exception:
        pass


if __name__ == "__main__":
    _start_startup_work_in_background()
    run_app()
