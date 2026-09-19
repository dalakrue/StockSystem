"""Project-local Python startup compatibility.

Python imports ``sitecustomize`` automatically when this project directory is
on ``sys.path``.  This runs before ``python -m streamlit`` starts the Tornado
server, which is early enough to choose the stable Windows selector event loop.
"""
from __future__ import annotations

try:
    from core.windows_asyncio_compat_20260619 import install_windows_selector_policy

    WINDOWS_ASYNCIO_COMPAT = install_windows_selector_policy()
except Exception as exc:  # startup must never be blocked by an optional compatibility hook
    WINDOWS_ASYNCIO_COMPAT = {"installed": False, "error": f"{type(exc).__name__}: {exc}"}
