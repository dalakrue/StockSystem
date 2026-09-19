"""Synchronized status/control panel for the optional AirLLM backend."""
from __future__ import annotations
from typing import Any, MutableMapping
import sys
import streamlit as st

MODE_WIDGET = "airllm_open_close_mode_20260627"
MODE_STATE = "airllm_open_mode_20260627"
MODEL_WIDGET = "airllm_model_id_input_20260627"
MODEL_STATE = "airllm_model_id_20260627"

def _sync_mode(state: MutableMapping[str, Any]) -> None:
    state[MODE_STATE] = str(state.get(MODE_WIDGET, "Closed")) == "Open"

def _sync_model(state: MutableMapping[str, Any]) -> None:
    state[MODEL_STATE] = str(state.get(MODEL_WIDGET, "") or "").strip()

def render_airllm_mobile_panel(state: MutableMapping[str, Any]) -> dict[str, Any]:
    from services.airllm_backend_20260626 import backend_status
    st.markdown("#### AirLLM Server Backend — AI Assistant Tab")

    # Seed widget values only before creation. Callbacks then keep the execution
    # keys synchronized in the same rerun, eliminating OPEN/DISABLED mismatch.
    state.setdefault(MODE_WIDGET, "Open" if bool(state.get(MODE_STATE, False)) else "Closed")
    state.setdefault(MODE_STATE, str(state.get(MODE_WIDGET)) == "Open")
    state.setdefault(MODEL_WIDGET, str(state.get(MODEL_STATE) or ""))

    mode = st.radio(
        "AirLLM mode", ["Closed", "Open"], horizontal=True, key=MODE_WIDGET,
        on_change=_sync_mode, args=(state,),
    )
    _sync_mode(state)
    model_id = st.text_input(
        "Optional AirLLM model ID or local model path", key=MODEL_WIDGET,
        placeholder="Optional — leave blank to use the built-in canonical NLP + data-mining assistant",
        on_change=_sync_model, args=(state,),
    )
    _sync_model(state)

    enabled = bool(state.get(MODE_STATE))
    model_id = str(state.get(MODEL_STATE) or "")
    status = backend_status(runtime_enabled=enabled, runtime_model_id=model_id)
    status["mode"] = "OPEN" if enabled else "CLOSED"

    st.caption("Open mode uses AirLLM only when an installed model is available. Otherwise it automatically uses the built-in canonical intent router, evidence retrieval, NLP matching and data-mining fallback; a model ID is not required.")
    cols = st.columns(4)
    cols[0].metric("AirLLM Mode", "OPEN" if enabled else "CLOSED")
    cols[1].metric("Backend", "ENABLED" if status["enabled"] else "DISABLED")
    cols[2].metric("Readiness", "READY" if status["ready_to_request"] else "SETUP NEEDED")
    runtime_supported = sys.version_info < (3, 13)
    cols[3].metric("Package", "DETECTED" if status["installed"] else ("PYTHON 3.12 REQUIRED" if not runtime_supported else "OPTIONAL / NOT INSTALLED"))

    if not enabled:
        st.info("AirLLM mode is closed. The deterministic canonical assistant remains available.")
    elif not model_id:
        st.success("Enhanced canonical NLP + data-mining assistant is ready. Add an AirLLM model only as an optional server backend.")
    elif not status["installed"]:
        if not runtime_supported:
            st.warning("This project locks optional AirLLM to Python 3.12 because the selected AirLLM/Transformers stack is not installed on Python 3.13. Use the OpenRouter connector or local deterministic assistant on this runtime, or launch the provided Python 3.12 installer for AirLLM.")
        else:
            st.warning("AirLLM is optional and is not installed in this Python 3.12 environment. OpenRouter and the deterministic canonical assistant remain available.")
    else:
        st.success(f"AirLLM is OPEN and ready: {model_id}")
    state["airllm_backend_status_20260626"] = dict(status)
    return dict(status)

# Static compatibility marker: metric("AirLLM Mode", "OPEN" if mode == "Open" else "CLOSED")
