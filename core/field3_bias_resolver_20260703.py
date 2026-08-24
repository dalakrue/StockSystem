"""Robust Field 3 standard-row evidence resolver.

The project publishes Field 3 evidence in several historical shapes: a
three-row summary table, three separate detail frames, lifecycle dictionaries,
and frozen child-contract rows.  This helper resolves one requested standard
without accidentally borrowing a lower/middle row or a different symbol.
It is read-only and never contacts a provider or changes a production decision.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

VERSION = "field3-standard-evidence-resolver-20260703-v1"


def _norm(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def normalize_bias(value: Any) -> str | None:
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    text = str(value).strip().upper()
    if not text:
        return None
    if "BUY" in text or text in {"BULL", "BULLISH", "UP", "LONG"}:
        return "BUY"
    if "SELL" in text or text in {"BEAR", "BEARISH", "DOWN", "SHORT"}:
        return "SELL"
    if any(token in text for token in ("WAIT", "HOLD", "NO TRADE", "BLOCK", "NEUTRAL", "RANGE")):
        return "WAIT"
    return None


def _standard_tokens(standard: str) -> tuple[str, ...]:
    text = str(standard or "higher").strip().lower()
    if text.startswith("low"):
        return ("lower", "low", "1day", "24h", "rolling24h")
    if text.startswith(("mid", "med")):
        return ("middle", "medium", "mid", "5day", "120h")
    return ("higher", "high", "25day", "600h")


def _matches_standard(value: Any, standard: str) -> bool:
    # Standard labels must be scalar.  Stringifying a DataFrame or a nested
    # state mapping is both semantically invalid and can turn a read-only
    # publication check into an unbounded CPU operation.
    if isinstance(value, (Mapping, pd.DataFrame, pd.Series, list, tuple, set)):
        return False
    text = _norm(value)
    return any(_norm(token) in text for token in _standard_tokens(standard))


def _mapping_lookup(record: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    lookup = {_norm(key): key for key in record}
    for alias in aliases:
        key = lookup.get(_norm(alias))
        if key is not None:
            value = record.get(key)
            if value not in (None, ""):
                return value
    return None


def _record_evidence(record: Mapping[str, Any], standard: str, *, context_matched: bool) -> dict[str, Any]:
    standard_value = _mapping_lookup(record, ("Standard", "Regime Standard", "Window", "Standard Name"))
    if standard_value not in (None, "") and not _matches_standard(standard_value, standard):
        return {}
    matched = context_matched or _matches_standard(standard_value, standard)
    specific = tuple(
        f"{token} {suffix}"
        for token in _standard_tokens(standard)
        for suffix in ("standard bias", "bias", "regime bias", "direction", "decision")
    )
    bias_value = _mapping_lookup(record, specific)
    if bias_value in (None, "") and matched:
        bias_value = _mapping_lookup(record, (
            "Regime Bias for Next H1", "Regime Bias", "Less-Risky Bias", "Less Risky Bias",
            "Safer Bias", "Bias", "Direction", "Decision", "Final Action",
        ))
    bias = normalize_bias(bias_value)
    if not matched and bias is None:
        return {}

    regime = _mapping_lookup(record, (
        f"{standard} Standard Regime", f"{standard} Regime", "Regime", "Major Regime",
        "Current Regime", "Existing Higher Regime",
    )) if matched else None
    reliability = _mapping_lookup(record, (
        f"{standard} Reliability", "Calibrated Reliability", "Reliability", "Trust Score",
        "Regime Reliability", "Confidence",
    )) if matched else None
    return {
        "standard": "Lower Standard" if standard.startswith("low") else (
            "Middle Standard" if standard.startswith(("mid", "med")) else "Higher Standard"
        ),
        "bias": bias,
        "raw_bias": bias_value,
        "regime": regime,
        "reliability": reliability,
        "sample_count": _mapping_lookup(record, ("Sample Count", "Samples", "Observation Count")) if matched else None,
        "regime_probability": _mapping_lookup(record, ("Regime Probability", "Probability", "Posterior Probability")) if matched else None,
        "transition_risk_1h": _mapping_lookup(record, ("Transition Risk 1H", "Transition Probability 1H")) if matched else None,
        "transition_risk_3h": _mapping_lookup(record, ("Transition Risk 3H", "Transition Probability 3H")) if matched else None,
        "transition_risk_6h": _mapping_lookup(record, ("Transition Risk 6H", "Transition Probability 6H")) if matched else None,
        "alpha": _mapping_lookup(record, ("Alpha",)) if matched else None,
        "delta": _mapping_lookup(record, ("Delta",)) if matched else None,
        "data_quality": _mapping_lookup(record, ("Data Quality Grade", "Data Quality", "Quality Grade")) if matched else None,
        "broker_time": _mapping_lookup(record, ("Broker Candle Time", "Broker Timestamp", "Broker Time", "Time", "Timestamp")) if matched else None,
        "source_record": dict(record),
        "version": VERSION,
    }


def resolve_standard_evidence(
    value: Any,
    standard: str = "higher",
    *,
    depth: int = 0,
    seen: set[int] | None = None,
    context_matched: bool = False,
) -> dict[str, Any]:
    """Resolve one Field 3 standard row from nested saved evidence.

    Generic ``Regime Bias`` columns are accepted only when the row/key context
    identifies the requested standard. This prevents a lower-standard BUY from
    being mistaken for the higher-standard authority.
    """
    if depth > 8:
        return {}
    seen = seen if seen is not None else set()
    if isinstance(value, (Mapping, list, tuple, pd.DataFrame)):
        marker = id(value)
        if marker in seen:
            return {}
        seen.add(marker)

    if isinstance(value, pd.DataFrame):
        if value.empty:
            return {}
        columns = {_norm(column): column for column in value.columns}
        standard_column = next((columns.get(_norm(alias)) for alias in ("Standard", "Regime Standard", "Window", "Standard Name") if columns.get(_norm(alias)) is not None), None)
        work = value
        matched = context_matched
        if standard_column is not None:
            mask = value[standard_column].map(lambda item: _matches_standard(item, standard))
            work = value.loc[mask]
            matched = True
        if work.empty:
            return {}
        # Newest/current rows are normally first, but scan a bounded set so a
        # sparse first row cannot hide a valid same-standard row.
        best: dict[str, Any] = {}
        for record in work.head(25).to_dict("records"):
            evidence = _record_evidence(record, standard, context_matched=matched)
            if evidence.get("bias") in {"BUY", "SELL"}:
                return evidence
            if evidence and not best:
                best = evidence
        return best

    if isinstance(value, Mapping):
        record = _record_evidence(value, standard, context_matched=context_matched)
        if record.get("bias") in {"BUY", "SELL"}:
            return record

        # Search explicitly-labelled standard containers first.
        prioritized: list[tuple[Any, bool]] = []
        fallback: list[tuple[Any, bool]] = []
        for key, child in value.items():
            key_matches = _matches_standard(key, standard)
            target = prioritized if key_matches else fallback
            target.append((child, context_matched or key_matches))
        best = record if record else {}
        for child, matched in [*prioritized, *fallback]:
            evidence = resolve_standard_evidence(
                child, standard, depth=depth + 1, seen=seen, context_matched=matched
            )
            if evidence.get("bias") in {"BUY", "SELL"}:
                return evidence
            if evidence and not best:
                best = evidence
        return best

    if isinstance(value, (list, tuple)):
        best: dict[str, Any] = {}
        for child in value[:200]:
            evidence = resolve_standard_evidence(
                child, standard, depth=depth + 1, seen=seen, context_matched=context_matched
            )
            if evidence.get("bias") in {"BUY", "SELL"}:
                return evidence
            if evidence and not best:
                best = evidence
        return best
    return {}


def resolve_higher_standard_bias(value: Any) -> str | None:
    return normalize_bias(resolve_standard_evidence(value, "higher").get("bias"))


__all__ = [
    "VERSION", "normalize_bias", "resolve_standard_evidence", "resolve_higher_standard_bias",
]
