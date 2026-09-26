"""Cached-only Lunch search over one canonical result and normalized histories.

This module deliberately has no dependency on the Settings orchestrator or any
calculator.  It searches immutable published objects and bounded analytical
history projections only.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import isfinite
from typing import Any, Iterable, Mapping, MutableMapping, Sequence
import re

import pandas as pd

VERSION = "lunch-search-20260621-v1"
MAX_RESULTS = 80
MAX_RECENT_SEARCHES = 8
_SENSITIVE = ("api_key", "apikey", "secret", "password", "access_token", "refresh_token", "authorization")

ALIASES: dict[str, tuple[str, ...]] = {
    "wrong prediction": ("direction correct false", "prediction error", "actual direction", "predicted direction"),
    "regime changed": ("transition", "previous regime", "new regime", "change probability"),
    "similar bullish days": ("similar day", "bull", "h+1 direction buy", "h+3 direction buy"),
    "low reliability": ("low reliability", "reliability", "regime trust", "forecast reliability"),
    "xgboost disagreement": ("xgboost", "forecast disagreement", "forecast spread", "conflict"),
    "exit risk": ("exit risk", "exit_risk"),
    "bear normal": ("bear_normal", "bear normal"),
    "bull normal": ("bull_normal", "bull normal"),
}

HISTORY_TABLES = (
    "regime_transition_history",
    "post_transition_outcome_history",
    "prediction_calibration_history",
    "drift_detector_history",
    "decision_audit_history",
)


@dataclass(frozen=True)
class SearchResult:
    score: float
    source: str
    field: str
    value: str
    timestamp: str = ""
    run_id: str = ""
    context: str = ""

    def as_dict(self) -> dict[str, Any]:
        row = asdict(self)
        return {
            "Score": round(float(row["score"]), 2),
            "Source": row["source"],
            "Field / Path": row["field"],
            "Value": row["value"],
            "Timestamp": row["timestamp"],
            "Run ID": row["run_id"],
            "Context": row["context"],
        }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _norm(value: Any) -> str:
    text = str(value or "").lower().replace("_", " ").replace("-", " ")
    return " ".join(re.findall(r"[a-z0-9.+]+", text))


def _redacted_path(path: str) -> bool:
    compact = str(path).lower().replace(" ", "_")
    return any(token in compact for token in _SENSITIVE)


def _safe_text(value: Any, maximum: int = 600) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and not isfinite(value):
        return ""
    text = str(value).replace("\n", " ").strip()
    return text[:maximum]


def _timestamp_from_row(row: Mapping[str, Any]) -> str:
    for key in ("timestamp", "transition_time", "time", "Time", "date", "Date", "datetime", "latest_completed_candle_time"):
        value = row.get(key)
        if value not in (None, ""):
            parsed = pd.to_datetime(value, errors="coerce", utc=True)
            return parsed.isoformat() if pd.notna(parsed) else _safe_text(value, 80)
    return ""


def _run_id_from_row(row: Mapping[str, Any]) -> str:
    for key in ("run_id", "canonical_run_id", "canonical_calculation_id", "calculation_id", "Run ID"):
        if row.get(key) not in (None, ""):
            return _safe_text(row.get(key), 120)
    return ""


def _flatten(value: Any, *, source: str, path: str = "", depth: int = 0, limit: int = 5000) -> list[dict[str, Any]]:
    """Flatten bounded published objects without exposing credentials."""
    if depth > 8 or limit <= 0:
        return []
    rows: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in list(value.items())[:700]:
            child_path = f"{path}.{key}" if path else str(key)
            if _redacted_path(child_path):
                continue
            rows.extend(_flatten(child, source=source, path=child_path, depth=depth + 1, limit=limit - len(rows)))
            if len(rows) >= limit:
                break
    elif isinstance(value, pd.DataFrame):
        frame = value.head(120)
        for _, series in frame.iterrows():
            record = series.to_dict()
            timestamp = _timestamp_from_row(record)
            run_id = _run_id_from_row(record)
            context = " | ".join(f"{k}: {_safe_text(v, 120)}" for k, v in list(record.items())[:12] if not _redacted_path(str(k)))
            for column, cell in record.items():
                field = f"{path}.{column}" if path else str(column)
                if _redacted_path(field):
                    continue
                rows.append({"source": source, "field": field, "value": _safe_text(cell), "timestamp": timestamp, "run_id": run_id, "context": context})
                if len(rows) >= limit:
                    break
            if len(rows) >= limit:
                break
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(list(value)[:150]):
            rows.extend(_flatten(child, source=source, path=f"{path}[{index}]", depth=depth + 1, limit=limit - len(rows)))
            if len(rows) >= limit:
                break
    else:
        rows.append({"source": source, "field": path or source, "value": _safe_text(value), "timestamp": "", "run_id": "", "context": ""})
    return rows[:limit]


def _canonical(state: MutableMapping[str, Any]) -> Mapping[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        value = get_canonical(state)
        if isinstance(value, Mapping) and value:
            return value
    except Exception:
        pass
    for key in ("canonical_decision_result", "canonical_decision_result_20260617", "canonical_result_20260617", "canonical_result"):
        value = state.get(key)
        if isinstance(value, Mapping) and value:
            return value
    return {}


def _history_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        from core.regime_trust_store_20260621 import default_store
        store = default_store()
        for table in HISTORY_TABLES:
            try:
                frame = store.query(table, limit=220)
            except Exception:
                continue
            rows.extend(_flatten(frame, source=table, path=table, limit=1800))
    except Exception:
        pass
    return rows


def collect_search_rows(state: MutableMapping[str, Any]) -> list[dict[str, Any]]:
    canonical = _canonical(state)
    rows = _flatten(canonical, source="Canonical Result", path="canonical", limit=6500)
    # Explicit cached aliases support older generations without creating copies.
    for key, label in (
        ("similar_day_intelligence_20260619", "Similar-Day Intelligence"),
        ("nlp_result_cache_20260617", "NLP Results"),
        ("lunch_metric_result_cache", "Lunch Full Metric"),
        ("canonical_priority_table_20260617", "Priority History"),
    ):
        value = state.get(key)
        if value is not None:
            rows.extend(_flatten(value, source=label, path=key, limit=1800))
    rows.extend(_history_rows())
    return rows[:12000]


def _expanded_query(query: str) -> tuple[str, list[str]]:
    normalized = _norm(query)
    phrases = [normalized]
    for alias, expansions in ALIASES.items():
        alias_norm = _norm(alias)
        if alias_norm in normalized or normalized in alias_norm:
            phrases.extend(_norm(item) for item in expansions)
    return normalized, [p for p in dict.fromkeys(phrases) if p]


def _numeric_condition(query: str) -> tuple[str, str, float] | None:
    match = re.search(r"(.+?)\s+(above|over|greater than|below|under|less than|at least|at most)\s+(-?\d+(?:\.\d+)?)", query, re.I)
    if not match:
        return None
    field = _norm(match.group(1))
    operator = match.group(2).lower()
    return field, operator, float(match.group(3))


def _numeric_value(value: str) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _condition_matches(condition: tuple[str, str, float] | None, field_text: str, value: str) -> bool:
    if condition is None:
        return True
    field, operator, threshold = condition
    if not all(token in field_text for token in field.split()):
        return False
    number = _numeric_value(value)
    if number is None:
        return False
    if operator in {"above", "over", "greater than"}:
        return number > threshold
    if operator in {"below", "under", "less than"}:
        return number < threshold
    if operator == "at least":
        return number >= threshold
    return number <= threshold


def search_cached_lunch(
    query: str, state: MutableMapping[str, Any], *, maximum_results: int = MAX_RESULTS,
) -> pd.DataFrame:
    normalized, phrases = _expanded_query(query)
    columns = ["Score", "Source", "Field / Path", "Value", "Timestamp", "Run ID", "Context"]
    if not normalized:
        return pd.DataFrame(columns=columns)
    condition = _numeric_condition(query)
    tokens = [token for token in normalized.split() if token not in {"last", "latest", "the", "a", "an"}]
    results: list[SearchResult] = []
    for row in collect_search_rows(state):
        field = _safe_text(row.get("field"), 300)
        value = _safe_text(row.get("value"), 600)
        context = _safe_text(row.get("context"), 600)
        source = _safe_text(row.get("source"), 120)
        field_text = _norm(field)
        haystack = _norm(" ".join((source, field, value, context)))
        if not _condition_matches(condition, field_text, value):
            continue
        score = 0.0
        exact_value = _norm(value)
        exact_field = _norm(field.split(".")[-1])
        if normalized in {exact_value, exact_field}:
            score = 100.0
        elif normalized and normalized in haystack:
            score = 91.0
        else:
            matched_phrase = max((len(p.split()) for p in phrases if p and p in haystack), default=0)
            token_hits = sum(1 for token in tokens if token in haystack)
            if matched_phrase:
                score = 72.0 + min(16.0, matched_phrase * 3.0)
            elif tokens and token_hits == len(tokens):
                score = 70.0
            elif tokens and token_hits >= max(1, len(tokens) - 1):
                score = 52.0 + 4.0 * token_hits
        if condition is not None and _condition_matches(condition, field_text, value):
            score = max(score, 94.0 if all(t in field_text for t in condition[0].split()) else 74.0)
        if not score:
            continue
        if source in HISTORY_TABLES:
            score += 2.0
        if "last" in normalized or "latest" in normalized:
            score += 1.0 if row.get("timestamp") else 0.0
        results.append(SearchResult(
            score=min(score, 100.0), source=source, field=field, value=value,
            timestamp=_safe_text(row.get("timestamp"), 80), run_id=_safe_text(row.get("run_id"), 120), context=context,
        ))
    # Exact score first, then newest timestamp, then stable source/path ordering.
    def key(item: SearchResult) -> tuple[Any, ...]:
        parsed = pd.to_datetime(item.timestamp, errors="coerce", utc=True)
        stamp = parsed.value if pd.notna(parsed) else -1
        return (-item.score, -stamp, item.source, item.field, item.value)
    dedup: dict[tuple[str, str, str, str], SearchResult] = {}
    for item in sorted(results, key=key):
        dedup.setdefault((item.source, item.field, item.value, item.timestamp), item)
    selected = list(dedup.values())[: max(1, min(int(maximum_results), MAX_RESULTS))]
    return pd.DataFrame([item.as_dict() for item in selected], columns=columns)


def remember_search(state: MutableMapping[str, Any], query: str) -> list[str]:
    cleaned = " ".join(str(query or "").split())[:120]
    recent = [str(item) for item in list(state.get("lunch_recent_searches_20260621") or []) if str(item).strip()]
    if cleaned:
        recent = [cleaned] + [item for item in recent if item.casefold() != cleaned.casefold()]
    recent = recent[:MAX_RECENT_SEARCHES]
    state["lunch_recent_searches_20260621"] = recent
    return recent


__all__ = [
    "VERSION", "MAX_RESULTS", "MAX_RECENT_SEARCHES", "SearchResult",
    "collect_search_rows", "search_cached_lunch", "remember_search",
]
