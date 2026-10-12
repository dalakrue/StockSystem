from __future__ import annotations

from typing import Any, Mapping, MutableMapping

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


def _first(mapping: Mapping[str, Any] | None, *keys: str, default: Any = None) -> Any:
    m = mapping if isinstance(mapping, Mapping) else {}
    for key in keys:
        value = m.get(key)
        if value not in (None, ""):
            return value
    return default


def _normalize_probability(value: float | None) -> float:
    value = _f(value, 0.0)
    if value > 1.0:
        value /= 100.0
    return max(0.0, min(1.0, value))


def _normalize_direction(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"BUY", "BULL", "LONG", "UP"}:
        return "BUY"
    if text in {"SELL", "BEAR", "SHORT", "DOWN"}:
        return "SELL"
    return "WAIT"


def _weighted_probability(items: list[tuple[float, float]]) -> float | None:
    usable = [(w, v) for w, v in items if w > 0 and v == v]
    if not usable:
        return None
    sw = sum(w for w, _ in usable)
    if sw <= 0:
        return None
    return sum(w * v for w, v in usable) / sw


def _history_frame(state: MutableMapping[str, Any] | None) -> pd.DataFrame:
    for key in (
        "full_metric_history_df_20260618",
        "full_metric_history_df",
        "lunch_metric_history_df",
        "metric_history_df",
    ):
        frame = (state or {}).get(key)
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            df = frame.copy()
            if "Broker Time" not in df.columns:
                for col in ("broker_time", "broker_candle_time", "time", "Date", "datetime"):
                    if col in df.columns:
                        df["Broker Time"] = pd.to_datetime(df[col], utc=True, errors="coerce")
                        break
            else:
                df["Broker Time"] = pd.to_datetime(df["Broker Time"], utc=True, errors="coerce")
            return df
    return pd.DataFrame()


def build_field6_session_bayesian_fusion(
    state: MutableMapping[str, Any] | None,
    source_snapshot: Any | None = None,
) -> dict[str, Any]:
    state = state if isinstance(state, MutableMapping) else {}
    snapshot = source_snapshot or load_canonical_snapshot(state)
    if snapshot is None:
        payload = {
            "status": "NO_CANONICAL_SNAPSHOT",
            "shadow_only": True,
            "decision_role": "INSUFFICIENT_EVIDENCE",
            "identity": {"run_id": "", "generation_id": "", "snapshot_hash": ""},
            "history": [],
            "current": {},
        }
        state["field6_session_bayesian_fusion_20260625"] = payload
        return payload

    identity = freeze_publication_identity(state, snapshot)
    session_contract = resolve_session_contract(state, snapshot)
    records = settled_projection_records(state)
    stats = compute_session_statistics(records) if not records.empty else pd.DataFrame()
    selected_session = session_contract.selected_session
    session_row = {}
    if not stats.empty:
        exact = stats[(stats["session"] == selected_session) & (stats["horizon"] == 1)]
        if exact.empty:
            exact = stats[stats["session"] == selected_session]
        if exact.empty:
            exact = stats[stats["session"] == "GLOBAL_FALLBACK"]
        if not exact.empty:
            session_row = exact.sort_values(["sample_count", "direction_accuracy"], ascending=[False, False]).iloc[0].to_dict()

    metrics = dict(snapshot.metrics)
    sentiment = metrics.get("sentiment") if isinstance(metrics.get("sentiment"), Mapping) else {}
    technical_buy = _normalize_probability(
        _first(metrics, "buy_probability", "bull_probability", "direction_probability", default=None)
        or _first(sentiment, "technical_buy_probability", default=None)
        or metrics.get("confidence")
    )
    technical_sell = _normalize_probability(
        _first(metrics, "sell_probability", "bear_probability", default=None)
        or _first(sentiment, "technical_sell_probability", default=None)
        or max(0.0, 1.0 - technical_buy)
    )
    regime_direction = _normalize_direction(snapshot.regime if snapshot.regime else snapshot.decision)
    regime_buy = _normalize_probability(snapshot.regime_reliability / 100.0 if regime_direction == "BUY" else 1.0 - snapshot.regime_reliability / 100.0 if regime_direction == "SELL" else 0.5)
    regime_sell = _normalize_probability(1.0 - regime_buy if regime_direction in {"BUY", "SELL"} else 0.5)

    eur_impact = _normalize_probability(
        _first(sentiment, "eur_impact_probability", "eur_probability", default=None)
        or _first(sentiment, "euro_probability", default=None)
    )
    usd_impact = _normalize_probability(
        _first(sentiment, "usd_impact_probability", "usd_probability", default=None)
        or _first(sentiment, "dollar_probability", default=None)
    )
    event_importance = _normalize_probability(_first(sentiment, "event_importance", "impact", default=0.0))
    novelty = _normalize_probability(_first(sentiment, "novelty", "novelty_score", default=0.0))
    freshness = _normalize_probability(_first(sentiment, "freshness", "freshness_score", default=0.0))

    if eur_impact <= 0 and usd_impact <= 0:
        sentiment_direction = "NO_NEWS_EVIDENCE"
        sentiment_buy = None
        sentiment_sell = None
    else:
        sentiment_buy = max(0.0, min(1.0, 0.5 + 0.50 * eur_impact - 0.40 * usd_impact))
        sentiment_sell = max(0.0, min(1.0, 0.5 + 0.50 * usd_impact - 0.40 * eur_impact))
        sentiment_direction = "BUY" if sentiment_buy > sentiment_sell else "SELL" if sentiment_sell > sentiment_buy else "WAIT"

    technical_direction = "BUY" if technical_buy > technical_sell else "SELL" if technical_sell > technical_buy else "WAIT"
    regime_direction_label = regime_direction if regime_direction in {"BUY", "SELL"} else "NO_REGIME_EVIDENCE"

    session_edge = _normalize_probability((session_row.get("direction_accuracy") or 0.5))
    session_direction = "BUY" if session_edge >= 0.55 else "SELL" if session_edge <= 0.45 else "WAIT"
    session_status = "INSUFFICIENT_SESSION_EVIDENCE" if int(session_row.get("sample_count") or 0) < 10 else "SESSION_EDGE_AVAILABLE"

    buy_prob = _weighted_probability([
        (0.30 if sentiment_buy is not None else 0.0, sentiment_buy if sentiment_buy is not None else 0.0),
        (0.30, technical_buy),
        (0.25 if regime_direction_label != "NO_REGIME_EVIDENCE" else 0.0, regime_buy),
        (0.15 if session_status == "SESSION_EDGE_AVAILABLE" else 0.0, session_edge),
    ])
    sell_prob = _weighted_probability([
        (0.30 if sentiment_sell is not None else 0.0, sentiment_sell if sentiment_sell is not None else 0.0),
        (0.30, technical_sell),
        (0.25 if regime_direction_label != "NO_REGIME_EVIDENCE" else 0.0, regime_sell),
        (0.15 if session_status == "SESSION_EDGE_AVAILABLE" else 0.0, 1.0 - session_edge),
    ])
    buy_prob = 0.5 if buy_prob is None else buy_prob
    sell_prob = 0.5 if sell_prob is None else sell_prob
    agreement = "AGREE" if len({d for d in (sentiment_direction, technical_direction, regime_direction_label, session_direction) if d in {"BUY","SELL"}}) == 1 else "MIXED"
    protected_decision = snapshot.decision
    direction_confirmation = "YES" if ((protected_decision == "BUY" and buy_prob >= sell_prob) or (protected_decision == "SELL" and sell_prob >= buy_prob) or protected_decision == "WAIT") else "NO"

    if buy_prob >= 0.60 and protected_decision == "BUY":
        decision_role = "ENTRY_CONFIRM"
    elif sell_prob >= 0.60 and protected_decision == "SELL":
        decision_role = "DIRECTION_CONFIRM"
    elif protected_decision == "WAIT" and max(buy_prob, sell_prob) < 0.60:
        decision_role = "WAIT_PROTECT"
    elif abs(buy_prob - sell_prob) < 0.08:
        decision_role = "INSUFFICIENT_EVIDENCE"
    else:
        decision_role = "CONFLICT"

    now_row = {
        "Broker Time": snapshot.broker_candle_time.isoformat(),
        "Session": selected_session,
        "Protected Decision": protected_decision,
        "Sentiment Direction": sentiment_direction,
        "Sentiment Probability": round(max(sentiment_buy or 0.0, sentiment_sell or 0.0), 4) if sentiment_buy is not None else "NO_NEWS_EVIDENCE",
        "Technical Direction": technical_direction if technical_direction != "WAIT" else "NO_TECHNICAL_EVIDENCE",
        "Technical Probability": round(max(technical_buy, technical_sell), 4),
        "Regime Direction": regime_direction_label,
        "Session Edge": round(session_edge, 4) if session_status == "SESSION_EDGE_AVAILABLE" else "INSUFFICIENT_SESSION_EVIDENCE",
        "Fused BUY Probability": round(buy_prob, 4),
        "Fused SELL Probability": round(sell_prob, 4),
        "Agreement": agreement,
        "Decision Role": decision_role,
        "Direction Confirmation": direction_confirmation,
        "Main Support": technical_direction if technical_direction in {"BUY", "SELL"} else sentiment_direction,
        "Main Contradiction": "NO_MAJOR_CONTRADICTION" if decision_role in {"ENTRY_CONFIRM", "DIRECTION_CONFIRM"} else ("TECHNICAL_CONFLICT" if technical_direction not in {"WAIT", protected_decision} else "MIXED_EVIDENCE"),
        "Outcome Status": "PENDING",
        "Realized Direction": "PENDING",
        "Correct": "PENDING",
        "Run ID": identity["run_id"],
    }

    hist_source = _history_frame(state)
    if not hist_source.empty and "Broker Time" in hist_source.columns:
        hist_source = hist_source.dropna(subset=["Broker Time"]).sort_values("Broker Time", ascending=False).head(600)
        rows = []
        for _, row in hist_source.iterrows():
            broker_time = pd.to_datetime(row.get("Broker Time"), utc=True, errors="coerce")
            realized = _normalize_direction(row.get("Actual Direction") or row.get("actual_direction") or row.get("realized_direction"))
            decision = _normalize_direction(row.get("Decision") or row.get("decision") or protected_decision)
            rows.append({
                "Broker Time": broker_time.isoformat() if pd.notna(broker_time) else "",
                "Session": selected_session,
                "Protected Decision": decision,
                "Sentiment Direction": sentiment_direction,
                "Sentiment Probability": now_row["Sentiment Probability"],
                "Technical Direction": now_row["Technical Direction"],
                "Technical Probability": now_row["Technical Probability"],
                "Regime Direction": regime_direction_label,
                "Session Edge": now_row["Session Edge"],
                "Fused BUY Probability": now_row["Fused BUY Probability"],
                "Fused SELL Probability": now_row["Fused SELL Probability"],
                "Agreement": agreement,
                "Decision Role": decision_role,
                "Direction Confirmation": "YES" if realized == decision and realized in {"BUY", "SELL"} else ("PENDING" if realized == "WAIT" else "NO"),
                "Main Support": now_row["Main Support"],
                "Main Contradiction": now_row["Main Contradiction"],
                "Outcome Status": "SETTLED" if realized in {"BUY", "SELL"} else "PENDING",
                "Realized Direction": realized if realized in {"BUY", "SELL"} else "PENDING",
                "Correct": "YES" if realized == decision and realized in {"BUY", "SELL"} else ("PENDING" if realized == "WAIT" else "NO"),
                "Run ID": identity["run_id"],
                "Generation ID": identity["generation_id"],
                "Snapshot Hash": identity["snapshot_hash"],
            })
        history = rows
    else:
        history = []

    payload = {
        "status": "OK",
        "shadow_only": True,
        "identity": identity,
        "session_contract": session_contract.to_dict(),
        "current": {
            "eur_impact_probability": round(eur_impact, 4),
            "usd_impact_probability": round(usd_impact, 4),
            "eurusd_net_buy_probability": round(buy_prob, 4),
            "eurusd_net_sell_probability": round(sell_prob, 4),
            "technical_buy_probability": round(technical_buy, 4),
            "technical_sell_probability": round(technical_sell, 4),
            "regime_direction_probability": round(max(regime_buy, regime_sell), 4),
            "session_historical_edge": round(session_edge, 4) if session_status == "SESSION_EDGE_AVAILABLE" else "INSUFFICIENT_SESSION_EVIDENCE",
            "event_importance": round(event_importance, 4),
            "novelty": round(novelty, 4),
            "evidence_freshness": round(freshness, 4),
            "decision_role": decision_role,
            "row": now_row,
        },
        "decision_role": decision_role,
        "history": history,
    }
    state["field6_session_bayesian_fusion_20260625"] = payload
    return payload
