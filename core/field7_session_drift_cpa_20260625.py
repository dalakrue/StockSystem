from __future__ import annotations

import math
from typing import Any, MutableMapping

import pandas as pd

from core.canonical.snapshot import load_canonical_snapshot
from core.publication_identity_20260625 import freeze_publication_identity
from core.session_context_20260625 import resolve_session_contract
from core.session_projection_store_20260625 import settled_projection_records, compute_session_statistics


def _f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if out == out else default
    except Exception:
        return default


def _z_pvalue_from_stat(stat: float) -> float:
    return max(0.0, min(1.0, math.erfc(abs(stat) / math.sqrt(2.0))))


def build_field7_session_drift_cpa(
    state: MutableMapping[str, Any] | None,
    source_snapshot: Any | None = None,
) -> dict[str, Any]:
    state = state if isinstance(state, MutableMapping) else {}
    snapshot = source_snapshot or load_canonical_snapshot(state)
    if snapshot is None:
        payload = {
            "status": "NO_CANONICAL_SNAPSHOT",
            "shadow_only": True,
            "history": [],
            "current": {},
            "identity": {"run_id": "", "generation_id": "", "snapshot_hash": ""},
        }
        state["field7_session_drift_cpa_20260625"] = payload
        return payload

    identity = freeze_publication_identity(state, snapshot)
    contract = resolve_session_contract(state, snapshot)
    records = settled_projection_records(state)
    if records.empty:
        payload = {
            "status": "NO_SETTLED_EVIDENCE",
            "shadow_only": True,
            "history": [],
            "current": {"research_decision_role": "INSUFFICIENT_EVIDENCE"},
            "identity": identity,
            "session_contract": contract.to_dict(),
        }
        state["field7_session_drift_cpa_20260625"] = payload
        return payload

    records = records.copy()
    if 'origin_time' not in records.columns and 'forecast_origin_time' in records.columns:
        records['origin_time'] = records['forecast_origin_time']
    records["origin_time"] = pd.to_datetime(records["origin_time"], utc=True, errors="coerce")
    records["session"] = records["session"].fillna("GLOBAL_FALLBACK")
    records["horizon"] = records["horizon"].astype(int)
    records["base_loss"] = records["base_error"].abs()
    stats = compute_session_statistics(records)

    selected = contract.selected_session
    current_rows = records[(records["session"] == selected) & (records["horizon"] == 1)].sort_values("origin_time")
    if len(current_rows) < 5:
        current_rows = records[records["horizon"] == 1].sort_values("origin_time")
    n = int(len(current_rows))
    if n >= 2:
        split = max(1, n // 2)
        pre = current_rows.iloc[:split]["base_loss"]
        post = current_rows.iloc[split:]["base_loss"]
        pre_mean = float(pre.mean()) if len(pre) else 0.0
        post_mean = float(post.mean()) if len(post) else 0.0
        change = post_mean - pre_mean
        drift_status = "DRIFT_DETECTED" if abs(change) > max(0.0002, 0.20 * pre_mean) else "STABLE"
        effective_window = n
    else:
        pre_mean = post_mean = change = 0.0
        drift_status = "INSUFFICIENT_EVIDENCE"
        effective_window = n

    session_stats = stats[(stats["session"] == selected) & (stats["horizon"] == 1)] if not stats.empty else pd.DataFrame()
    bias = _f(session_stats["median_signed_residual"].iloc[0], 0.0) if not session_stats.empty else 0.0
    comparable = current_rows.copy()
    if 'base_predicted' not in comparable.columns and 'base_prediction' in comparable.columns:
        comparable['base_predicted'] = comparable['base_prediction']
    comparable["session_predicted"] = comparable["base_predicted"] + bias
    comparable["session_loss"] = (comparable["actual"] - comparable["session_predicted"]).abs()
    comparable["loss_diff"] = comparable["base_loss"] - comparable["session_loss"]
    comparable_count = int(comparable["loss_diff"].notna().sum())
    if comparable_count < 40:
        cpa_stat = 0.0
        p_value = 1.0
        cpa_status = "INSUFFICIENT_EVIDENCE"
        preferred = "GLOBAL_FALLBACK"
    else:
        diffs = comparable["loss_diff"].dropna()
        mean_diff = float(diffs.mean())
        std_diff = float(diffs.std(ddof=1) or 0.0)
        cpa_stat = mean_diff / (std_diff / math.sqrt(len(diffs))) if std_diff > 0 and len(diffs) > 1 else 0.0
        p_value = _z_pvalue_from_stat(cpa_stat)
        cpa_status = "SESSION_EDGE_CONFIRMED" if cpa_stat > 0 and p_value < 0.10 else "NO_CLEAR_EDGE"
        preferred = "SESSION_ADAPTIVE" if cpa_status == "SESSION_EDGE_CONFIRMED" else "BASE_PROTECTED"

    if comparable_count < 40:
        role = "INSUFFICIENT_EVIDENCE"
    elif drift_status == "DRIFT_DETECTED":
        role = "DRIFT_BLOCK"
    elif preferred == "SESSION_ADAPTIVE":
        role = "EDGE_CONFIRMED"
    elif selected == "GLOBAL_FALLBACK":
        role = "GLOBAL_FALLBACK"
    else:
        role = "EDGE_DEGRADED"

    latest = comparable.sort_values("origin_time", ascending=False).head(600)
    history = []
    for _, row in latest.iterrows():
        history.append({
            "Broker Time": row["origin_time"].isoformat() if pd.notna(row["origin_time"]) else "",
            "Session": row.get("session") or selected,
            "Horizon": int(row.get("horizon") or 1),
            "Base Loss": round(_f(row.get("base_loss")), 6),
            "Session Loss": round(_f(row.get("session_loss")), 6),
            "Loss Difference": round(_f(row.get("loss_diff")), 6),
            "Effective ADWIN Window": effective_window,
            "Drift Status": drift_status,
            "Drift Magnitude": round(change, 6),
            "CPA Statistic": round(cpa_stat, 6),
            "CPA P-value": round(p_value, 6),
            "Preferred Forecast": preferred,
            "Research Decision Role": role,
            "Direction Confirmation": "YES" if _f(row.get("session_loss"), 1.0) <= _f(row.get("base_loss"), 1.0) else "NO",
            "Data Quality": "SETTLED_ONLY",
            "Settlement Status": str(row.get("settlement_status") or "FULLY_SETTLED"),
            "Run ID": identity["run_id"],
            "Generation ID": identity["generation_id"],
            "Snapshot Hash": identity["snapshot_hash"],
        })

    payload = {
        "status": "OK",
        "shadow_only": True,
        "identity": identity,
        "session_contract": contract.to_dict(),
        "current": {
            "drift_status": drift_status,
            "effective_window_length": effective_window,
            "pre_change_mean_loss": round(pre_mean, 6),
            "post_change_mean_loss": round(post_mean, 6),
            "change_magnitude": round(change, 6),
            "detected_time": snapshot.broker_candle_time.isoformat(),
            "recovery_state": "RECOVERING" if drift_status == "DRIFT_DETECTED" and change < 0 else ("DEGRADED" if drift_status == "DRIFT_DETECTED" else "STABLE"),
            "cpa_statistic": round(cpa_stat, 6),
            "cpa_p_value": round(p_value, 6),
            "preferred_forecast": preferred,
            "research_decision_role": role,
            "comparable_count": comparable_count,
        },
        "history": history,
    }
    state["field7_session_drift_cpa_20260625"] = payload
    return payload
