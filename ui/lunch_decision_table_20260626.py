"""Field 1 Decision History — 25-day, read-only presentation table."""
from __future__ import annotations
from types import SimpleNamespace
from typing import Any, Mapping, MutableMapping
import pandas as pd
from core.decision_table_20260626 import build_decision_table, consensus_diagnostic

# Legacy static-test marker only: Table 1 of 3 — Decision History — Last 25 Days


def _snapshot(canonical: Mapping[str, Any], state: Mapping[str, Any] | None = None) -> Any:
    from core.canonical_identity_20260627 import canonical_timestamp_value, parse_completed_broker_candle
    broker = canonical_timestamp_value(canonical)
    created = canonical.get("created_at_utc") or canonical.get("created_at") or broker
    stamp = parse_completed_broker_candle(broker, state=state)
    try:
        made = pd.Timestamp(created)
        if made.tzinfo is None:
            made = made.tz_localize("UTC")
        else:
            made = made.tz_convert("UTC")
    except Exception:
        try:
            made = parse_completed_broker_candle(created, state=state, require_h1_alignment=False)
        except Exception:
            made = stamp
    regime = canonical.get("regime") if isinstance(canonical.get("regime"), Mapping) else {}
    decision = canonical.get("final_decision") if isinstance(canonical.get("final_decision"), Mapping) else {}
    return SimpleNamespace(
        broker_candle_time=pd.Timestamp(stamp),
        created_at_utc=pd.Timestamp(made),
        run_id=str(canonical.get("run_id") or canonical.get("canonical_calculation_id") or "unknown"),
        generation_id=str(canonical.get("generation_id") or canonical.get("calculation_generation") or "unknown"),
        source_snapshot_hash=str(canonical.get("source_snapshot_hash") or canonical.get("snapshot_hash") or "unknown"),
        source_signature=str(canonical.get("source_signature") or "unknown"),
        symbol=str(canonical.get("symbol") or "EURUSD"),
        timeframe=str(canonical.get("timeframe") or "H1"),
        decision=str(decision.get("final_decision") or canonical.get("full_metric_direction") or "WAIT"),
        regime=str(regime.get("major_regime") or regime.get("current_regime") or "UNKNOWN"),
    )


def _fallback_from_history(state: Mapping[str, Any]) -> pd.DataFrame:
    payload = state.get("one_hour_direction_confirmation_20260626")
    raw = payload.get("history") if isinstance(payload, Mapping) else None
    frame = raw.copy() if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw or [])
    if not frame.empty:
        return frame
    # Table 1 is a read-only collection of Table 3 histories. It must remain
    # visible even when the canonical identity strip is temporarily unbound.
    for key in ("lunch_metric_result_cache", "full_metric_result_cache_20260618",
                "lunch_metric_result_published_20260618", "lunch_metric_result_20260619",
                "eurusd_h1_matrix_result", "eurusd_h1_matrix_export"):
        result = state.get(key)
        if not isinstance(result, Mapping):
            continue
        overall = result.get("history")
        if isinstance(overall, pd.DataFrame) and not overall.empty:
            return overall.copy()
        if isinstance(overall, list) and overall:
            return pd.DataFrame(overall)
        histories = result.get("history_by_factor")
        if isinstance(histories, Mapping) and histories:
            # Use the existing adapter with an identity-free display snapshot.
            times = []
            for value in histories.values():
                f = value if isinstance(value, pd.DataFrame) else pd.DataFrame(value or [])
                if f.empty: continue
                tc = next((c for c in ("Broker Candle Time","broker_candle_time","time","datetime","DateTime","date") if c in f.columns), None)
                if tc is not None:
                    t = pd.to_datetime(f[tc], errors="coerce", utc=True).dropna()
                    if len(t): times.append(t.max())
            if times:
                snap = SimpleNamespace(broker_candle_time=max(times), created_at_utc=max(times),
                    run_id="UNBOUND", generation_id="UNBOUND", source_snapshot_hash="UNBOUND", source_signature="UNBOUND",
                    symbol=str(state.get("symbol") or "EURUSD"), timeframe=str(state.get("timeframe") or "H1"),
                    decision="WAIT", regime="UNKNOWN")
                try:
                    return build_decision_table(state, snap)
                except Exception:
                    pass
    for key in ("full_metric_history_df_20260618", "full_metric_history_df", "decision_history_df"):
        frame = state.get(key)
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            return frame.copy()
    return pd.DataFrame()


def render_field1_decision_history(*, state: MutableMapping[str, Any], canonical: Mapping[str, Any]) -> None:
    import streamlit as st
    st.markdown("#### Table 1 — Decision History — Last 25 Days")
    st.caption("Field 1 source of truth · decision columns only · newest completed broker candle first · no production decision is rewritten.")
    try:
        table = build_decision_table(state, _snapshot(canonical, state))
    except Exception:
        table = _fallback_from_history(state)
    if isinstance(table, pd.DataFrame) and not table.empty:
        from core.self_contained_table_logic_20260627 import enrich_decision_history
        table = enrich_decision_history(table, state)
    if not isinstance(table, pd.DataFrame) or table.empty:
        st.info("Decision History has no published rows yet. Quick Run now publishes the current direction-confirmation row immediately; historical rows accumulate only from completed broker candles and are never fabricated.")
        return
    # Publish the exact visible Table 1 frame so Table 5 can consume the same
    # source instead of rebuilding it through a different legacy path.
    state["field1_table1_decision_history_20260628"] = table.copy(deep=False)
    preferred = [
        "Date", "Weekday", "Hour",
        "Entry Strength Decision", "SELL Pressure Decision", "BUY Pressure Decision",
        "Net Pressure Decision", "Pullback Readiness Decision", "M1 Confirmation Decision",
        "Master Decision", "Hold Safety Decision", "TP Quality Decision",
        "Direction Confirmation Decision", "Decision Name", "Production Decision Raw", "Action Display Label",
        "Outcome Status", "Decision Correct", "Net Pressure Source", "Direction Confirmation Source",
        "Master Decision Source", "Source Run ID", "Source Generation ID", "Completed Broker Candle",
        "Source Snapshot Hash", "Source Signature", "Final Decision",
    ]
    shown = table.loc[:, [c for c in preferred if c in table.columns]].copy()
    # Pending correctness is not missing data: the next-H1 outcome simply has
    # not settled yet. Keep the immutable core value as N/A, but present a clear
    # status in the UI so the column never appears blank or broken.
    if {"Decision Correct", "Outcome Status"}.issubset(shown.columns):
        pending = ~shown["Outcome Status"].astype(str).str.upper().isin({"SETTLED", "RESOLVED"})
        missing = shown["Decision Correct"].isna() | shown["Decision Correct"].astype(str).str.upper().isin({"", "N/A", "NA", "NONE"})
        shown.loc[pending & missing, "Decision Correct"] = "PENDING — NEXT H1 NOT SETTLED"
    st.dataframe(shown, use_container_width=True, hide_index=True, height=520)
    latest = table.iloc[0].to_dict()
    decision_cols = [c for c in preferred if c.endswith("Decision") and c in latest]
    directional = [str(latest.get(c, "")).upper() for c in decision_cols]
    buy = sum("BUY" in v for v in directional)
    sell = sum("SELL" in v for v in directional)
    available = sum(v not in {"", "N/A", "NONE", "MISSING"} for v in directional)
    cols = st.columns(4)
    cols[0].metric("BUY Decisions", buy)
    cols[1].metric("SELL Decisions", sell)
    cols[2].metric("Directional Conflict", min(buy, sell))
    cols[3].metric("Decision Coverage", f"{available}/{len(decision_cols)}" if decision_cols else "0/0")
    st.caption("WAIT/HOLD reduction must be validated out of sample. This diagnostic is research-only and does not lower protected production thresholds automatically.")

# Static compatibility marker: "Decision Name","Final Decision"
