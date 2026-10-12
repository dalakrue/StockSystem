"""Error-isolated renderer dispatcher for one selected field."""
from __future__ import annotations

import logging
import time
from typing import Any

try:
    import streamlit as st
except ModuleNotFoundError:  # Unit tests can exercise routing without the UI package.
    st = None

LOGGER = logging.getLogger("quant_v11.lunch")


def log_field_error(*, field_id: str, run_id: str, broker_candle_time: str, operation: str, duration: float, error: Exception) -> None:
    LOGGER.exception(
        "lunch_field_failure",
        extra={
            "run_id": run_id,
            "broker_candle_time": broker_candle_time,
            "field_id": field_id,
            "operation": operation,
            "duration": duration,
            "status": "ERROR",
            "error_type": type(error).__name__,
        },
    )


def safe_render_field(definition: Any, context: Any) -> None:
    global st
    if st is None:
        import streamlit as st_runtime
        st = st_runtime
    started = time.perf_counter()
    try:
        errors = definition.validate(context)
        if errors:
            for error in errors:
                st.warning(error)
            return
        view_model = definition.build_view_model(context)
        definition.render(view_model)
        LOGGER.info(
            "lunch_field_rendered",
            extra={
                "run_id": context.snapshot.run_id,
                "broker_candle_time": context.snapshot.broker_candle_time.isoformat(),
                "field_id": definition.field_id,
                "operation": "render",
                "duration": time.perf_counter() - started,
                "status": "OK",
                "error_type": "",
            },
        )
    except Exception as exc:
        log_field_error(
            field_id=definition.field_id,
            run_id=context.snapshot.run_id,
            broker_candle_time=context.snapshot.broker_candle_time.isoformat(),
            operation="render",
            duration=time.perf_counter() - started,
            error=exc,
        )
        st.error(f"{definition.title} could not be displayed. Other Lunch fields remain available.")
        with st.expander("Technical error details", expanded=False):
            st.code(f"{type(exc).__name__}: {exc}")
