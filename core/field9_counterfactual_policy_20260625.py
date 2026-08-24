from __future__ import annotations

from typing import Any, MutableMapping

import pandas as pd

from core.canonical.snapshot import load_canonical_snapshot
from core.publication_identity_20260625 import freeze_publication_identity
from core.session_context_20260625 import resolve_session_contract
from core.session_projection_store_20260625 import settled_projection_records

ACTIONS = ("BUY", "WAIT", "SELL")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if out == out else default
    except Exception:
        return default


def _direction_from_number(value: float) -> str:
    if value > 0:
        return "BUY"
    if value < 0:
        return "SELL"
    return "WAIT"


def build_field9_counterfactual_policy(
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
            "label": "COUNTERFACTUAL POLICY EVIDENCE — NOT EXECUTED-TRADE PROOF",
        }
        state["field9_counterfactual_policy_20260625"] = payload
        return payload

    identity = freeze_publication_identity(state, snapshot)
    contract = resolve_session_contract(state, snapshot)
    records = settled_projection_records(state)
    if records.empty:
        payload = {
            "status": "NO_SETTLED_EVIDENCE",
            "shadow_only": True,
            "history": [],
            "current": {"decision_role": "COUNTERFACTUAL_UNPROVEN"},
            "identity": identity,
            "label": "COUNTERFACTUAL POLICY EVIDENCE — NOT EXECUTED-TRADE PROOF",
        }
        state["field9_counterfactual_policy_20260625"] = payload
        return payload

    records = records.copy()
    if 'origin_time' not in records.columns and 'forecast_origin_time' in records.columns:
        records['origin_time'] = records['forecast_origin_time']
    records["origin_time"] = pd.to_datetime(records["origin_time"], utc=True, errors="coerce")
    records["actual_return"] = records["actual"] - records["current_price"]
    records["historical_action"] = records["actual_return"].apply(_direction_from_number)
    prop = records["historical_action"].value_counts(normalize=True).reindex(ACTIONS, fill_value=0.0)
    clip_threshold = 0.05
    prop = prop.clip(lower=clip_threshold)
    prop = prop / prop.sum()

    spread = max(0.0, _f(state.get("spread_pips") or state.get("estimated_spread_pips"), 1.0))
    tx_cost = max(0.0, _f(state.get("estimated_transaction_cost_pips"), 0.4))
    slip = max(0.0, _f(state.get("estimated_slippage_pips"), 0.2))
    total_cost_pips = spread + tx_cost + slip

    pip_scale = 10000.0
    after_cost = {}
    for action in ACTIONS:
        if action == "BUY":
            reward = records["actual_return"] * pip_scale - total_cost_pips
        elif action == "SELL":
            reward = -records["actual_return"] * pip_scale - total_cost_pips
        else:
            reward = pd.Series(0.0, index=records.index)
        after_cost[action] = reward

    mu = {action: float(after_cost[action].mean()) for action in ACTIONS}
    dr = {}
    for action in ACTIONS:
        indicator = (records["historical_action"] == action).astype(float)
        pi = float(prop[action])
        correction = ((indicator / pi) * (after_cost[action] - mu[action])).fillna(0.0)
        dr[action] = float((mu[action] + correction).mean())

    production = snapshot.decision if snapshot.decision in ACTIONS else "WAIT"
    best_action = max(ACTIONS, key=lambda a: dr[a])
    production_value = dr[production]
    best_value = dr[best_action]
    regret = best_value - production_value
    uncertainty = float(pd.Series(list(dr.values())).std(ddof=0) or 0.0)

    if best_action == "BUY" and regret <= 0.25:
        role = "BUY_VALUE_CONFIRM"
    elif best_action == "SELL" and regret <= 0.25:
        role = "SELL_VALUE_CONFIRM"
    elif best_action == "WAIT" and regret <= 0.50:
        role = "WAIT_LOW_REGRET"
    elif uncertainty > max(1.0, 0.50 * abs(best_value)):
        role = "PRODUCTION_ACTION_UNSTABLE"
    else:
        role = "COUNTERFACTUAL_UNPROVEN"

    stabilities = []
    if len(records) >= 20:
        records = records.sort_values("origin_time")
        for start in range(0, max(1, len(records) - 19), max(1, len(records) // 5)):
            window = records.iloc[start:start + max(20, len(records) // 2)]
            if len(window) < 10:
                continue
            local_best = max(
                ACTIONS,
                key=lambda a: float((window["actual_return"] * pip_scale).mean()) if a == "BUY" else (
                    float((-window["actual_return"] * pip_scale).mean()) if a == "SELL" else 0.0
                ),
            )
            stabilities.append(local_best == best_action)
    stability = float(sum(stabilities) / len(stabilities)) if stabilities else 0.0

    recent = records.sort_values("origin_time", ascending=False).head(600)
    history = []
    for _, row in recent.iterrows():
        history.append({
            "Broker Time": row["origin_time"].isoformat() if pd.notna(row["origin_time"]) else "",
            "Session": row.get("session") or contract.selected_session,
            "Production Decision": production,
            "Shadow Preferred Action": best_action,
            "BUY Propensity": round(float(prop["BUY"]), 6),
            "WAIT Propensity": round(float(prop["WAIT"]), 6),
            "SELL Propensity": round(float(prop["SELL"]), 6),
            "BUY DR Value": round(dr["BUY"], 6),
            "WAIT DR Value": round(dr["WAIT"], 6),
            "SELL DR Value": round(dr["SELL"], 6),
            "Production Value": round(production_value, 6),
            "Best Counterfactual Value": round(best_value, 6),
            "Regret": round(regret, 6),
            "After-Cost EV": round(best_value, 6),
            "Stability": round(stability, 6),
            "Direction Confirmation": "YES" if best_action == production else "NO",
            "Decision Role": role,
            "Evidence Count": int(len(records)),
            "Maturity Status": str(row.get("settlement_status") or "FULLY_SETTLED"),
            "Run ID": identity["run_id"],
            "Generation ID": identity["generation_id"],
            "Snapshot Hash": identity["snapshot_hash"],
        })

    payload = {
        "status": "OK",
        "shadow_only": True,
        "identity": identity,
        "session_contract": contract.to_dict(),
        "label": "COUNTERFACTUAL POLICY EVIDENCE — NOT EXECUTED-TRADE PROOF",
        "current": {
            "buy_propensity": round(float(prop["BUY"]), 6),
            "wait_propensity": round(float(prop["WAIT"]), 6),
            "sell_propensity": round(float(prop["SELL"]), 6),
            "buy_dr_value": round(dr["BUY"], 6),
            "wait_dr_value": round(dr["WAIT"], 6),
            "sell_dr_value": round(dr["SELL"], 6),
            "production_action_value": round(production_value, 6),
            "best_counterfactual_value": round(best_value, 6),
            "production_regret": round(regret, 6),
            "action_value_uncertainty": round(uncertainty, 6),
            "stability": round(stability, 6),
            "minimum_evidence_count": int(len(records)),
            "decision_role": role,
            "clip_threshold": clip_threshold,
            "after_cost_components_pips": {
                "spread": round(spread, 6),
                "estimated_transaction_cost": round(tx_cost, 6),
                "available_slippage_estimate": round(slip, 6),
            },
        },
        "history": history,
    }
    state["field9_counterfactual_policy_20260625"] = payload
    return payload
