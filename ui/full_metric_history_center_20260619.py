"""Progressive-disclosure Full Metric history and settled trust views."""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping

import pandas as pd
import streamlit as st

from core.canonical_runtime_20260617 import get_canonical
from core.compact_canonical_20260619 import ACTIVE_CALCULATION_ID_KEY
from core.performance_store_20260619 import export_frame, query_frame
from core.trust_config_20260619 import TRUST_CONFIG
from core.trust_history_20260619 import get_trust_history_store


def _map(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _history_key(state: Mapping[str, Any]) -> str:
    refs = state.get("disk_backed_frame_refs_20260619")
    if isinstance(refs, Mapping):
        for key in ("full_metric_history_df_20260618", "canonical_priority_table_20260617", "lunch_quick_decision_merged_table_20260617"):
            if key in refs:
                return key
    return "canonical_priority_table_20260617"


def _current_history(state: MutableMapping[str, Any], limit: int = 240) -> pd.DataFrame:
    calc_id = str(state.get(ACTIVE_CALCULATION_ID_KEY) or "")
    if calc_id:
        try:
            frame = query_frame(calc_id, _history_key(state), limit=limit, order_by="Time", descending=True)
            if isinstance(frame, pd.DataFrame) and not frame.empty:
                return frame
        except Exception as exc:
            state["full_metric_history_read_error_20260619"] = str(exc)
    for key in ("full_metric_history_df_20260618", "canonical_priority_table_20260617", "lunch_quick_decision_merged_table_20260617"):
        frame = state.get(key)
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            work = frame.copy(deep=False)
            time_col = next((c for c in work.columns if str(c).strip().lower() in {"time", "timestamp", "datetime", "date"}), None)
            if time_col:
                parsed = pd.to_datetime(work[time_col], errors="coerce", utc=True)
                work = work.assign(__sort_time=parsed).sort_values("__sort_time", ascending=False).drop(columns="__sort_time")
            return work.head(limit)
    return pd.DataFrame()


def _display(frame: pd.DataFrame, *, phone: bool, height: int = 460) -> None:
    if frame.empty:
        st.info("No rows are available for this view yet.")
        return
    visible = frame.head(48 if phone else int(TRUST_CONFIG["maximum_display_rows_desktop"]))
    if phone:
        preferred = [
            "Time", "Decision", "Direction", "Priority Rank", "Priority Label",
            "Master /10", "Entry /10", "Exit Risk /10", "Periodicity Norm Vol",
            "TP First %", "SL First %", "Confidence Sequence",
            "Required Confidence %", "Robust EV pips", "Extreme Risk",
        ]
        chosen = [column for column in preferred if column in visible.columns]
        if chosen:
            visible = visible[chosen]
    st.dataframe(visible, use_container_width=True, hide_index=True, height=height)
    if len(frame) > len(visible):
        st.caption(f"Showing {len(visible):,} newest rows. Full data remains available in the export.")


def _validation_rows(trust: Mapping[str, Any], research: Mapping[str, Any] | None = None) -> pd.DataFrame:
    calibration = _map(_map(trust.get("calibration")).get("calibrated"))
    interval = _map(trust.get("interval"))
    pbo = _map(trust.get("pbo"))
    dsr = _map(trust.get("dsr"))
    spa = _map(trust.get("spa"))
    dm = list(trust.get("dm") or [])
    best_dm = next((x for x in dm if isinstance(x, Mapping) and x.get("status") == "VALID"), {})
    research = _map(research)
    confidence = _map(research.get("confidence_sequence"))
    proper = _map(research.get("proper_scoring"))
    selective = _map(research.get("selective_prediction"))
    evt = _map(research.get("evt_tail"))
    invariance = _map(research.get("invariance"))
    competing = _map(research.get("competing_risk"))
    rows = [
        ("Anytime-valid trust", confidence.get("trust_status", "INSUFFICIENT_DATA"), max([int(_map(v).get("effective_sample_count") or 0) for v in _map(confidence.get("metrics")).values()] or [0]), "Time-uniform sequential boundaries"),
        ("Selective risk–coverage", "PASS" if selective.get("selective_prediction_pass") else "WAIT / FAIL", _map(_map(selective.get("thresholds")).get(selective.get("selected_threshold_group") or "global")).get("sample_count", 0), f"Threshold {selective.get('required_confidence_threshold', '—')}% · coverage {selective.get('expected_coverage', '—')}"),
        ("CRPS skill", proper.get("status", "INSUFFICIENT_DATA"), proper.get("sample_count", 0), f"Mean CRPS {proper.get('mean_crps', '—')} · naive skill {proper.get('skill_vs_naive', '—')}"),
        ("Energy Score", proper.get("status", "INSUFFICIENT_DATA"), proper.get("sample_count", 0), f"Joint {proper.get('joint_energy_score', '—')} · calibration {proper.get('path_calibration', '—')}"),
        ("EVT tail protection", "BLOCK" if evt.get("extreme_risk_block") else ("READY" if evt.get("evt_sample_sufficient") else "DEVELOPING"), evt.get("evt_exceedance_count", 0), f"99% move {evt.get('extreme_move_99', '—')} · {evt.get('fit_method', '—')}"),
        ("Invariant evidence", invariance.get("feature_stability_warning", "INSUFFICIENT_DATA"), invariance.get("stable_environment_count", 0), f"Score {invariance.get('invariance_score', '—')} · robustness test only"),
        ("Competing-risk TP/SL", competing.get("status", "INSUFFICIENT_DATA"), competing.get("effective_sample_count", 0), f"Fallback {competing.get('selected_fallback_level', '—')} · censored kept separate"),
        ("Trust classification", trust.get("trust_classification", "INSUFFICIENT"), trust.get("settled_sample_count", 0), "Settled OOS rows only"),
        ("Probability calibration", calibration.get("status", "UNAVAILABLE"), calibration.get("sample_count", 0), f"Brier {calibration.get('brier_score', '—')} · ECE {calibration.get('expected_calibration_error', '—')}"),
        ("Interval calibration", "VALID" if interval.get("coverage") is not None else "UNAVAILABLE", interval.get("settled_residual_sample_count", 0), f"Coverage {interval.get('coverage', '—')} · width {interval.get('mean_width_pips', '—')} pips"),
        ("Deflated Sharpe Ratio", dsr.get("status", "UNAVAILABLE"), dsr.get("sample_size", 0), dsr.get("reason") or f"Probability {dsr.get('deflated_sharpe_probability', '—')}"),
        ("Probability of Backtest Overfitting", pbo.get("status", "UNAVAILABLE"), pbo.get("tested_configuration_count", 0), pbo.get("reason") or f"PBO {pbo.get('probability_of_backtest_overfitting', '—')} · folds {pbo.get('fold_count', '—')}"),
        ("Diebold–Mariano", best_dm.get("status", "UNAVAILABLE"), best_dm.get("sample_count", 0), best_dm.get("reason") or f"{best_dm.get('method', '—')} vs {best_dm.get('benchmark', '—')}"),
        ("Superior Predictive Ability", spa.get("status", "UNAVAILABLE"), spa.get("sample_count", 0), spa.get("reason") or f"Best {spa.get('best_method', '—')} vs {spa.get('benchmark', '—')}"),
    ]
    return pd.DataFrame(rows, columns=["Validation", "Status", "Sample / configs", "Evidence"])


def render_full_metric_history_center(*, state: MutableMapping[str, Any] | None = None) -> None:
    state = state if state is not None else st.session_state
    canonical = get_canonical(state)
    if not canonical:
        return
    phone = bool(state.get("phone_mode", False))
    trust = _map(canonical.get("trust_validation")) or _map(state.get("settled_trust_summary_20260619"))
    research = _map(canonical.get("research_risk_stack"))
    st.markdown("### Full Metric Detail + History")
    st.caption("Protected central authority · latest completed H1 first · advanced trust evidence uses settled forecasts only.")
    choices = ["Current history", "Settled forecasts", "Regime performance", "Validation scorecard"]
    if phone:
        choice = st.selectbox("History view", choices, key="full_metric_history_center_view_mobile_20260619")
    else:
        choice = st.radio("History view", choices, horizontal=True, key="full_metric_history_center_view_20260619", label_visibility="collapsed")

    try:
        if choice == "Current history":
            frame = _current_history(state, limit=600)
            _display(frame, phone=phone)
            calc_id = str(state.get(ACTIVE_CALCULATION_ID_KEY) or "")
            if calc_id and st.toggle("Prepare complete Full Metric export", value=False, key="full_metric_complete_export_gate_20260619"):
                full = export_frame(calc_id, _history_key(state))
                st.download_button("Download complete Full Metric History CSV", full.to_csv(index=False).encode("utf-8"), "full_metric_history_complete.csv", "text/csv", key="full_metric_complete_export_20260619", use_container_width=True)
        elif choice == "Settled forecasts":
            store = get_trust_history_store()
            settled = store.frame(status="SETTLED", limit=10000)
            if not settled.empty and "forecast_origin_time" in settled:
                settled["forecast_origin_time"] = pd.to_datetime(settled["forecast_origin_time"], errors="coerce", utc=True)
                settled = settled.sort_values("forecast_origin_time", ascending=False)
            _display(settled, phone=phone)
            if not settled.empty:
                st.download_button("Download settled forecast ledger CSV", settled.to_csv(index=False).encode("utf-8"), "settled_forecast_ledger.csv", "text/csv", key="settled_forecast_export_20260619", use_container_width=True)
            pending = store.pending_count()
            st.caption(f"Pending forecasts: {pending}. They are not scored until the target H1 candle has fully closed.")
        elif choice == "Regime performance":
            groups = trust.get("groups") or []
            grouped = pd.DataFrame(groups)
            if not grouped.empty:
                sort_cols = [c for c in ("settled_sample_count", "horizon") if c in grouped]
                grouped = grouped.sort_values(sort_cols, ascending=[False] * len(sort_cols)) if sort_cols else grouped
            _display(grouped, phone=phone)
            if not grouped.empty:
                st.download_button("Download grouped trust CSV", grouped.to_csv(index=False).encode("utf-8"), "regime_session_horizon_trust.csv", "text/csv", key="grouped_trust_export_20260619", use_container_width=True)
        else:
            _display(_validation_rows(trust, research), phone=phone, height=430)
            if int(trust.get("settled_sample_count") or 0) < int(TRUST_CONFIG["minimum_calibration_samples"]):
                st.info("Calibration developing — insufficient settled samples. No fake precise calibrated probability is displayed.")
            with st.expander("Open / Close — reliability bins and statistical details", expanded=False):
                st.json({
                    "calibration": trust.get("calibration", {}),
                    "interval": trust.get("interval", {}),
                    "pbo": trust.get("pbo", {}),
                    "dsr": trust.get("dsr", {}),
                    "dm": trust.get("dm", []),
                    "spa": trust.get("spa", {}),
                    "research_risk_stack": research,
                    "policy": {
                        "validated_min_samples": TRUST_CONFIG["validated_min_samples"],
                        "developing_min_samples": TRUST_CONFIG["developing_min_samples"],
                        "pending_forecasts_scored": False,
                        "original_forecasts_overwritten": False,
                    },
                })
    except Exception as exc:
        calc_id = str(canonical.get("calculation_id") or canonical.get("run_id") or "—")
        st.error(f"Module: Full Metric History · Calculation ID: {calc_id[:24]} · Category: history display failure · Safe action: reopen this view or rerun from Settings after checking Errors / Fix Fast.")
        state["full_metric_history_center_error_20260619"] = repr(exc)


__all__ = ["render_full_metric_history_center"]
