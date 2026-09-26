"""Disabled PRO CONTROL sidebar patch.

V11 restores the native Streamlit sidebar open/close control.  This module is
kept only so old imports do not fail, but it no longer injects any button,
JavaScript, backdrop, forced hide, or forced open behavior.
"""
from __future__ import annotations


def install_v7_sidebar_patch() -> None:
    """No-op: native Streamlit sidebar is used."""
    return None
