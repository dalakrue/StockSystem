"""On-demand controls for the single canonical copy/export service."""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping

import pandas as pd
import streamlit as st

from core.canonical_lookup_20260626 import resolve_canonical
from core.compact_canonical_20260619 import get_compact_summary
from services.canonical_exports import (
    all_text,
    build_short_payload,
    generation_identity,
    machine_json,
    payload_stats,
)
from services.current_canonical_copy_20260625 import (
    build_current_full_payload,
    build_current_short_payload,
)


def _m(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _cache_key(kind: str, location: str) -> str:
    # Shared text identity by generation; locations only affect widget keys.
    return f"canonical_copy_{kind}_payload_20260621"


def render_canonical_copy_export(
    *,
    state: MutableMapping[str, Any] | None = None,
    plan: Mapping[str, Any] | None = None,
    readiness: Mapping[str, Any] | None = None,
    location: str = "lunch",
    compact: bool = False,
) -> None:
    state = state if state is not None else st.session_state
    canonical = resolve_canonical(state)
    summary = get_compact_summary(state)
    plan = dict(plan or state.get("position_sizing_plan_20260619") or {})
    readiness = dict(readiness or state.get("system_readiness_snapshot_20260621") or {})
    if not canonical:
        st.info("Copy/export becomes available after a successful Run Calculation.")
        return
    identity = generation_identity(canonical)
    if not compact:
        st.markdown("#### Copy current Fields 1–3 — no history")

    cols = st.columns(3)
    prepare_short = cols[0].button("📋 Prepare Short", key=f"{location}_canonical_short_prepare_20260621", use_container_width=True)
    prepare_all = cols[1].button("📋 Prepare All Current", key=f"{location}_canonical_all_prepare_20260621", use_container_width=True)
    prepare_json = cols[2].button("⬇️ Prepare JSON", key=f"{location}_canonical_json_prepare_20260621", use_container_width=True)

    try:
        if prepare_short:
            text, stats = build_current_short_payload(state, canonical)
            state[_cache_key("short", location)] = {"identity": identity, "text": text, "stats": stats.__dict__}
        if prepare_all:
            # Generated only on explicit press and cached by canonical identity.
            text, stats = build_current_full_payload(state, canonical)
            state[_cache_key("all", location)] = {"identity": identity, "text": text, "stats": stats.__dict__}
        if prepare_json:
            text = machine_json(canonical, summary, plan)
            state["canonical_export_json_payload_20260621"] = {"identity": identity, "text": text}
    except Exception as exc:
        st.error(f"Copy/export preparation failed safely: {type(exc).__name__}: {exc}")

    for kind, label in (("short", "Copy prepared Short Current"), ("all", "Copy prepared Full Current")):
        item = state.get(_cache_key(kind, location))
        if not isinstance(item, Mapping) or item.get("identity") != identity:
            continue
        text = str(item.get("text") or "")
        stats = _m(item.get("stats")) or payload_stats(text).__dict__
        st.caption(f"{label}: {stats.get('characters', len(text)):,} characters · {stats.get('lines', len(text.splitlines()))} lines · ~{stats.get('estimated_tokens', 0):,} estimated tokens")
        from ui.copy_tools import central_copy_button
        central_copy_button(label, text, f"{location}_canonical_copy_{kind}_{identity[:16]}", show_fallback=True)

    export_item = state.get("canonical_export_json_payload_20260621")
    if isinstance(export_item, Mapping) and export_item.get("identity") == identity:
        st.download_button(
            "Download complete canonical generation JSON",
            str(export_item.get("text") or "").encode("utf-8"),
            file_name=f"eurusd_h1_generation_{canonical.get('calculation_generation')}.json",
            mime="application/json",
            use_container_width=True,
            key=f"{location}_canonical_export_download_20260621",
        )


def render_direct_canonical_copy_buttons(
    *,
    state: MutableMapping[str, Any] | None = None,
    location: str = "menu",
    compact: bool = True,
    include_full: bool = True,
) -> None:
    """Render stable one-tap Copy Short / Copy Full controls.

    Payloads are serialized once per canonical generation and then reused on
    every Streamlit rerun. This prevents the former full-payload rebuild on each
    Lunch interaction, while preserving the exact current-generation content.
    """
    state = state if state is not None else st.session_state
    # July 2026 current-result repair: Copy Short and Copy Full must use the
    # same current selected-symbol/run object as Field 3, Field 10, NLP and CSV.
    # This path intentionally runs before the old single-symbol canonical
    # identity guard so multi-symbol copy cannot be blocked by a stale EURUSD/H1
    # canonical mismatch.
    try:
        from core.current_result_sync_20260708 import (
            build_current_result, current_short_copy_text, current_full_copy_text,
            CURRENT_RUN_ID_KEY, CURRENT_SIGNATURE_KEY,
        )
        build_current_result(state, reason="copy_buttons_render")
        identity = str(state.get(CURRENT_RUN_ID_KEY) or state.get(CURRENT_SIGNATURE_KEY) or "current")
        from ui.copy_tools import central_copy_button
        short_payload = current_short_copy_text(state)
        full_payload = current_full_copy_text(state) if include_full else ""
        st.markdown("**Current multi-symbol result copy**")
        central_copy_button("Copy Short", short_payload, f"{location}_current_short_{identity[:16]}", height=82, show_fallback=False)
        if include_full:
            central_copy_button("Copy Full", full_payload, f"{location}_current_full_{identity[:16]}", height=82, show_fallback=False)
        return
    except Exception as current_copy_exc_20260708:
        state["current_copy_render_error_20260708"] = f"{type(current_copy_exc_20260708).__name__}: {current_copy_exc_20260708}"
    try:
        from core.symbol_context_20260702 import resolve_symbol_context
        from core.multi_symbol_field10_20260701 import activate_symbol_result, normalize_symbol
        context = resolve_symbol_context(state, "Lunch")
        current_symbol = normalize_symbol(resolve_canonical(state).get("symbol") if resolve_canonical(state) else "")
        if current_symbol != context.lunch_display_symbol:
            activation = activate_symbol_result(state, context.lunch_display_symbol)
            state["copy_symbol_activation_20260702"] = activation
        canonical = resolve_canonical(state)
        context = resolve_symbol_context(state, "Lunch")
        canonical_symbol = normalize_symbol(canonical.get("symbol") if canonical else "")
        canonical_candle = str(
            canonical.get("completed_broker_candle")
            or canonical.get("broker_candle_time")
            or canonical.get("latest_completed_candle_time")
            or ""
        )
        canonical_hash = str(canonical.get("snapshot_hash") or canonical.get("source_snapshot_hash") or "")
        expected_candle = str(context.completed_broker_candle or "")
        expected_hash = str(context.snapshot_hash or "")
        mismatches = {}
        if canonical_symbol != context.lunch_display_symbol:
            mismatches["symbol"] = {"expected": context.lunch_display_symbol, "actual": canonical_symbol}
        if expected_candle and canonical_candle and pd.Timestamp(canonical_candle) != pd.Timestamp(expected_candle):
            mismatches["completed_broker_candle"] = {"expected": expected_candle, "actual": canonical_candle}
        if expected_hash and canonical_hash and canonical_hash != expected_hash:
            mismatches["snapshot_hash"] = {"expected": expected_hash, "actual": canonical_hash}
        if mismatches:
            state["copy_identity_diagnostic_20260702"] = {"ok": False, "mismatches": mismatches}
            canonical = {}
        else:
            state["copy_identity_diagnostic_20260702"] = {"ok": True}
            state["copy_active_symbol_20260702"] = context.lunch_display_symbol
    except Exception as exc:
        canonical = resolve_canonical(state)
        context = None
        state["copy_symbol_activation_error_20260702"] = f"{type(exc).__name__}: {exc}"
    if not canonical:
        from ui.copy_tools import central_copy_button
        startup_short = "ADX Quant Pro — system open; no canonical calculation published yet. Use Settings → Quick Run Fields 1–3 + Open Lunch."
        startup_full = startup_short + "\nCopy controls are operational. Current decision/history values remain unavailable until a completed H1 calculation is published."
        central_copy_button("Copy Short", startup_short, f"{location}_startup_short_20260626", height=82, show_fallback=False)
        if include_full:
            central_copy_button("Copy Full", startup_full, f"{location}_startup_full_20260626", height=82, show_fallback=False)
        st.caption("Copy is available from startup; Quick Run replaces this status text with the current canonical payload.")
        return

    identity = context.copy_fingerprint() if context is not None else (generation_identity(canonical) or "current")
    cache_key = "direct_current_copy_payloads_20260702_v3"
    cached = state.get(cache_key)
    if not isinstance(cached, Mapping) or cached.get("identity") != identity:
        try:
            short_payload, short_stats = build_current_short_payload(state, canonical)
            full_payload = ""
            full_stats = None
            if include_full:
                full_payload, full_stats = build_current_full_payload(state, canonical)
            cached = {
                "identity": identity,
                "short_payload": short_payload,
                "short_stats": short_stats,
                "full_payload": full_payload,
                "full_stats": full_stats,
            }
            state[cache_key] = cached
            state["copy_payload_cache_short_20260702"] = {"fingerprint": identity, "text": short_payload}
            if include_full:
                state["copy_payload_cache_full_20260702"] = {"fingerprint": identity, "text": full_payload}
        except Exception as exc:
            st.caption(f"Copy unavailable safely: {type(exc).__name__}: {str(exc)[:90]}")
            return

    from ui.copy_tools import central_copy_button
    short_payload = str(cached.get("short_payload") or "")
    short_stats = cached.get("short_stats")
    full_payload = str(cached.get("full_payload") or "")
    full_stats = cached.get("full_stats")

    active_symbol = context.lunch_display_symbol if context is not None else str(canonical.get("symbol") or "EURUSD")
    st.markdown(f"**Current Fields 1–3 + Field 10 Copy — {active_symbol}**")
    # Always stack clipboard components. Separate rows eliminate iframe overlap
    # and make both controls reliable on narrow phones and desktop browsers.
    if short_stats is not None:
        st.caption(f"Short: {short_stats.lines} lines · ~{short_stats.estimated_tokens:,} tokens")
    central_copy_button("Copy Short", short_payload, f"{location}_direct_short_{identity[:16]}", height=82, show_fallback=False)
    if include_full:
        if full_stats is not None:
            st.caption(f"Full: {full_stats.lines} lines · ~{full_stats.estimated_tokens:,} tokens")
        central_copy_button("Copy Full", full_payload, f"{location}_direct_full_{identity[:16]}", height=82, show_fallback=False)


__all__ = ["render_canonical_copy_export", "render_direct_canonical_copy_buttons"]
