"""Narrow Windows asyncio compatibility for local Streamlit startup.

Python 3.13 on Windows can emit a noisy, benign ``ConnectionResetError: [WinError 10054]`` from
``_ProactorBasePipeTransport._call_connection_lost`` when a browser tab,
websocket, or HTTP peer closes a connection.  The exception is raised by the
Proactor transport callback after the peer has already gone away; it is not a
trading-calculation failure.

The safest project-local prevention is to select the Windows selector policy
*before Streamlit/Tornado creates its server loop*.  ``sitecustomize.py`` imports
this module during Python startup.  Non-Windows platforms are unchanged.
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any


def install_windows_selector_policy() -> dict[str, Any]:
    """Install the selector policy only on Windows and return diagnostic state.

    No exceptions are hidden.  This function changes only the event-loop policy
    chosen for loops created after installation.  It does not intercept or
    suppress application, network, database, or calculation exceptions.
    """
    result: dict[str, Any] = {
        "platform": sys.platform,
        "installed": False,
        "policy": type(asyncio.get_event_loop_policy()).__name__,
    }
    if sys.platform != "win32":
        result["reason"] = "non-Windows platform"
        return result

    policy_type = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy_type is None:
        result["reason"] = "selector policy unavailable"
        return result

    current = asyncio.get_event_loop_policy()
    if isinstance(current, policy_type):
        result.update({"installed": True, "policy": type(current).__name__, "reason": "already active"})
        return result

    asyncio.set_event_loop_policy(policy_type())
    os.environ.setdefault("ADX_WINDOWS_ASYNCIO_POLICY", "selector")
    result.update({
        "installed": True,
        "policy": type(asyncio.get_event_loop_policy()).__name__,
        "reason": "prevents benign Proactor connection-reset callback noise",
    })
    return result


__all__ = ["install_windows_selector_policy"]
