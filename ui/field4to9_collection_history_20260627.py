"""Dinner read-only aggregation for original Fields 4, 6, 7, 8 and 9.

The module discovers already-published timestamped data, keeps every original
bias/decision column for audit, and adds a compact explicit summary.  It never
runs a calculation and never fabricates a historical row.
"""
from __future__ import annotations

from typing import Any, Iterator, Mapping, MutableMapping
import re

import pandas as pd

_TIME_TOKENS = ("broker candle", "broker time", "completed candle", "timestamp", "datetime", "event time", "time", "date")
_VALUE_TOKENS = ("decision", "bias", "direction", "action", "signal", "priority", "stance", "recommendation", "outlook", "label", "trend")
_EXCLUDED_DIRECTION = ("confidence", "reliability", "rank", "probability", "coverage", "score", "strength", "quality", "uncertainty", "error", "percent", "pct")
_GENERATED_KEYS = ("field4to9_collection_history", "field4_self_calculated", "field5_self_calculated", "generated table 4", "generated table 5")
_FIELDS = ("field4", "field_4", "field 4", "field6", "field_6", "field 6", "field7", "field_7", "field 7", "field8", "field_8", "field 8", "field9", "field_9", "field 9", "dinner", "regime", "pattern")
_MAX_SCAN_DEPTH = 5
_MAX_SOURCE_ROWS = 650
_MIN_NONBLANK_DISPLAY_VALUES = 2
_DEFAULT_MAX_DISPLAY_COLUMNS = 38
_FIELD_LABELS = ("Field 4", "Field 6", "Field 7", "Field 8", "Field 9")


def _norm(value: Any) -> str:
    try:
        if value is None or pd.isna(value):
            value = ""
    except Exception:
        pass
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def _first_nonmissing(*values: Any, default: Any = None) -> Any:
    """Coalesce scalar metadata without truth-testing pandas NA."""
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value.strip().upper() in {"", "N/A", "NA", "NONE", "NAN", "UNAVAILABLE", "—", "-"}:
            continue
        try:
            missing = pd.isna(value)
            if isinstance(missing, bool) and missing:
                continue
        except Exception:
            pass
        return value
    return default


def _is_generated(path: str) -> bool:
    normalized = _norm(path)
    return any(_norm(token) in normalized for token in _GENERATED_KEYS)


def _field_related(path: str) -> bool:
    normalized = _norm(path)
    return any(_norm(token) in normalized for token in _FIELDS)


def _walk(obj: Any, path: str = "", seen: set[int] | None = None, depth: int = 0) -> Iterator[tuple[str, pd.DataFrame]]:
    """Yield bounded published frames only; never traverse an unbounded session graph."""
    seen = seen or set()
    if depth > _MAX_SCAN_DEPTH:
        return
    if id(obj) in seen:
        return
    seen.add(id(obj))
    if isinstance(obj, pd.DataFrame):
        if not obj.empty:
            yield path or "root", obj.tail(_MAX_SOURCE_ROWS)
        return
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            yield from _walk(value, f"{path}.{key}" if path else str(key), seen, depth + 1)
    elif isinstance(obj, (list, tuple)):
        if obj and all(isinstance(item, Mapping) for item in obj):
            try:
                frame = pd.DataFrame(obj).tail(_MAX_SOURCE_ROWS)
                if not frame.empty:
                    yield path or "records", frame
            except Exception:
                pass
        for index, value in enumerate(obj):
            if isinstance(value, (Mapping, list, tuple, pd.DataFrame)):
                yield from _walk(value, f"{path}[{index}]", seen, depth + 1)




def _parse_time_series(series: pd.Series) -> pd.Series:
    """Parse only plausible temporal source columns without noisy guessing."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce", utc=True)
    sample = series.dropna().astype(str).str.strip().head(32)
    if sample.empty:
        return pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns, UTC]")
    plausible = sample.str.match(
        r"^(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4}|\d{10,13}$)",
        na=False,
    )
    if float(plausible.mean()) < 0.5:
        return pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns, UTC]")
    return pd.to_datetime(series, errors="coerce", utc=True, format="mixed")


def _time_col(frame: pd.DataFrame):
    for column in frame.columns:
        name = _norm(column)
        words = set(name.split())
        looks_temporal = (
            name in _TIME_TOKENS
            or name in {"published at", "created at", "updated at", "forecast origin broker time", "target broker time"}
            or "timestamp" in words or "datetime" in words
            or ("time" in words and not {"timeframe", "runtime"}.intersection(words))
            or ("date" in words and len(words) <= 4)
            or ("candle" in words and ("broker" in words or "completed" in words))
        )
        if looks_temporal:
            parsed = _parse_time_series(frame[column])
            if parsed.notna().any():
                return column, parsed
    if isinstance(frame.index, pd.DatetimeIndex):
        return "__index__", pd.Series(pd.to_datetime(frame.index, utc=True), index=frame.index)
    return None, None


def _broker_display(series: pd.Series, state: Mapping[str, Any] | None = None) -> pd.Series:
    try:
        from core.shared_broker_time_20260622 import resolve_broker_clock
        resolved = resolve_broker_clock(state or {}, event_time_utc=series.max())
        tzinfo = resolved.get("broker_tzinfo")
        if tzinfo is not None:
            return series.dt.tz_convert(tzinfo)
    except Exception:
        pass
    # Compatibility-only display fallback when no broker configuration exists.
    return series.dt.tz_convert("Asia/Yangon")


def _field_from_path(path: str) -> str | None:
    normalized = _norm(path)
    for number in (4, 6, 7, 8, 9):
        if re.search(rf"\bfield\s*{number}\b", normalized) or f"field{number}" in normalized:
            return f"Field {number}"
    if "regime" in normalized or "dinner" in normalized:
        return "Field 4"
    if any(token in normalized for token in ("sentiment", "news", "nlp", "future strategy")):
        return "Field 6"
    if "scientific" in normalized:
        return "Field 7"
    if "integrated history" in normalized or "accuracy history" in normalized:
        return "Field 8"
    if any(token in normalized for token in ("regret", "decision impact", "stability")):
        return "Field 9"
    return None


def _direction(value: Any) -> str:
    text = _norm(value).upper()
    if "WAIT PULLBACK" in text or text == "PULLBACK":
        return "WAIT PULLBACK"
    if re.search(r"\bHOLD\b", text) or "PROTECT" in text:
        return "HOLD"
    buy = bool(re.search(r"\b(BUY|BULL|UP|LONG)\b", text))
    sell = bool(re.search(r"\b(SELL|BEAR|DOWN|SHORT)\b", text))
    if buy and sell:
        return "WAIT"
    if buy:
        return "BUY"
    if sell:
        return "SELL"
    return "WAIT"


def _protective_action(value: Any) -> Any:
    """Map existing evidence to the requested protective action vocabulary.

    This never replaces the raw Dinner publication.  It is an additive display
    interpretation: directional evidence means protect/hold the existing thesis;
    neutral, conflicting, or pullback evidence means wait for a pullback.
    """
    normalized = _direction(value)
    if normalized in {"BUY", "SELL", "HOLD"}:
        return "HOLD & PROTECT"
    if normalized in {"WAIT", "WAIT PULLBACK"}:
        return "WAIT FOR PULLBACK"
    return pd.NA


def _protective_series(series: pd.Series) -> pd.Series:
    """Translate repeated categorical evidence once per distinct value."""
    try:
        unique_values = pd.unique(series.dropna())
        mapping = {value: _protective_action(value) for value in unique_values}
        return series.map(mapping)
    except Exception:
        return series.map(_protective_action)


def _add_protective_action_columns(table: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(table, pd.DataFrame) or table.empty:
        return table
    work = table.copy(deep=False)
    # Keep a stable 20-column audit schema in storage. Columns with no genuine
    # source remain NA and are automatically omitted by the compact display.
    action_labels = [
        *[
            f"Action {index:02d} — {field} {kind}"
            for index, (field, kind) in enumerate(
                [(field, kind) for field in _FIELD_LABELS for kind in ("Bias", "Decision")], start=1
            )
        ],
        "Action 11 — Technical Consensus",
        "Action 12 — Production Master",
        "Action 13 — Research Shadow",
        "Action 14 — NLP Event",
        "Action 15 — Regime",
        "Action 16 — Forecast",
        "Action 17 — Conflict Guard",
        "Action 18 — Coverage Guard",
        "Action 19 — Evidence Balance",
        "Action 20 — Final Protective Action",
    ]
    action_values: dict[str, pd.Series] = {
        label: pd.Series(pd.NA, index=work.index, dtype="object") for label in action_labels
    }
    field_sources = [
        (f"Action {index:02d} — {field} {kind}", f"{field} {kind}")
        for index, (field, kind) in enumerate(
            [(field, kind) for field in _FIELD_LABELS for kind in ("Bias", "Decision")], start=1
        )
    ]
    for label, source in field_sources:
        if source in work.columns:
            action_values[label] = _protective_series(work[source])
    direct_specs = (
        ("Action 11 — Technical Consensus", "Technical Consensus"),
        ("Action 12 — Production Master", "Production Master Decision"),
        ("Action 13 — Research Shadow", "Research Shadow Action"),
        ("Action 14 — NLP Event", "NLP Event Bias"),
        ("Action 15 — Regime", "Regime Bias"),
        ("Action 16 — Forecast", "Forecast Bias"),
    )
    for label, source in direct_specs:
        if source in work.columns:
            action_values[label] = _protective_series(work[source])

    if "Conflict" in work.columns:
        conflict = pd.to_numeric(work["Conflict"], errors="coerce")
        action_values["Action 17 — Conflict Guard"] = pd.Series(
            pd.NA, index=work.index, dtype="object"
        ).mask(conflict.notna() & (conflict < 0.35), "HOLD & PROTECT").mask(
            conflict.notna() & (conflict >= 0.35), "WAIT FOR PULLBACK"
        )
    if "Coverage" in work.columns:
        coverage = pd.to_numeric(work["Coverage"], errors="coerce")
        action_values["Action 18 — Coverage Guard"] = pd.Series(
            pd.NA, index=work.index, dtype="object"
        ).mask(coverage.notna() & (coverage >= 0.60), "HOLD & PROTECT").mask(
            coverage.notna() & (coverage < 0.60), "WAIT FOR PULLBACK"
        )
    if {"BUY Evidence", "SELL Evidence"}.issubset(work.columns):
        buy = pd.to_numeric(work["BUY Evidence"], errors="coerce")
        sell = pd.to_numeric(work["SELL Evidence"], errors="coerce")
        available = buy.notna() | sell.notna()
        action_values["Action 19 — Evidence Balance"] = pd.Series(
            pd.NA, index=work.index, dtype="object"
        ).mask(available & (buy != sell), "HOLD & PROTECT").mask(
            available & (buy == sell), "WAIT FOR PULLBACK"
        )
    final_source = work.get("Technical Consensus")
    if isinstance(final_source, pd.Series):
        final_action = _protective_series(final_source)
        if "Conflict" in work.columns:
            conflict = pd.to_numeric(work["Conflict"], errors="coerce")
            final_action = final_action.mask(conflict >= 0.35, "WAIT FOR PULLBACK")
        action_values["Action 20 — Final Protective Action"] = final_action

    # Insert after the compact time/identity prefix, keeping all raw columns.
    prefix = [
        column for column in (
            "Broker Candle", "Broker Date", "Weekday", "Broker Hour",
            "Symbol", "Timeframe", "Broker Candle Time", "Date", "Hour",
        ) if column in work.columns
    ]
    remainder = [column for column in work.columns if column not in prefix]
    actions = pd.DataFrame(action_values, index=work.index)
    return pd.concat([work.loc[:, prefix], actions, work.loc[:, remainder]], axis=1)


def _source_columns(base: pd.DataFrame) -> list[str]:
    columns: list[str] = []
    for column in base.columns:
        name = _norm(column)
        if column in {"Broker Candle Time", "Date", "Weekday", "Hour", "Source Coverage"}:
            continue
        if str(column).startswith("Action "):
            # Protective action columns are display-only derivatives, not
            # independent source evidence for the legacy research audit.
            continue
        if _is_generated(column):
            continue
        if not any(token in name for token in _VALUE_TOKENS):
            continue
        if any(token in name for token in _EXCLUDED_DIRECTION):
            continue
        columns.append(column)
    return columns


def _raw_collection(state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    seen_paths: set[str] = set()
    roots = {
        key: value for key, value in state.items()
        if _field_related(str(key)) and not _is_generated(str(key))
        and not any(token in _norm(key) for token in ("cache manifest", "disk backed", "training", "model object", "raw news"))
    }
    if canonical:
        for key in ("field4", "field6", "field7", "field8", "field9", "dinner", "research_shadow", "crcef_sv"):
            if key in canonical:
                roots[f"canonical.{key}"] = canonical[key]
    for root, obj in roots.items():
        for path, frame in _walk(obj, root):
            if path in seen_paths or _is_generated(path):
                continue
            seen_paths.add(path)
            _, stamp = _time_col(frame)
            if stamp is None:
                continue
            columns = [column for column in frame.columns if any(token in _norm(column) for token in _VALUE_TOKENS)]
            if not columns:
                continue
            part = pd.DataFrame({"Broker Candle Time UTC": stamp})
            for column in columns:
                part[f"{path} · {column}"] = frame[column].to_numpy()
            part = part.dropna(subset=["Broker Candle Time UTC"]).drop_duplicates("Broker Candle Time UTC", keep="last")
            parts.append(part)
    if not parts:
        return pd.DataFrame()
    output = parts[0]
    for part in parts[1:]:
        output = output.merge(part, on="Broker Candle Time UTC", how="outer")
    return output.sort_values("Broker Candle Time UTC", ascending=False).drop_duplicates("Broker Candle Time UTC")


def _first_value(row: pd.Series, columns: list[str]) -> tuple[Any, str]:
    for column in columns:
        value = row.get(column)
        if pd.notna(value) and str(value).strip() not in {"", "N/A", "None", "nan"}:
            return value, column
    return pd.NA, "N/A — source not published"


def _consensus(values: list[str]) -> tuple[str, float, float, float, float]:
    valid = [value for value in values if value in {"BUY", "SELL", "WAIT", "WAIT PULLBACK", "HOLD"}]
    if not valid:
        return "WAIT", 0.0, 0.0, 0.0, 0.0
    buy = valid.count("BUY")
    sell = valid.count("SELL")
    if buy and sell:
        decision = "WAIT"
    elif buy:
        decision = "BUY"
    elif sell:
        decision = "SELL"
    elif "WAIT PULLBACK" in valid:
        decision = "WAIT PULLBACK"
    elif "HOLD" in valid:
        decision = "HOLD"
    else:
        decision = "WAIT"
    conflict = min(buy, sell) / max(buy, sell, 1)
    coverage = len(valid) / len(_FIELD_LABELS)
    return decision, float(buy), float(sell), round(float(conflict), 4), round(float(coverage), 4)


def _cache_identity(state: Mapping[str, Any], canonical: Mapping[str, Any] | None) -> tuple[str, str, str]:
    canonical = canonical or {}
    return (
        str(_first_nonmissing(canonical.get("run_id"), state.get("canonical_run_id_20260617"), default="")),
        str(_first_nonmissing(canonical.get("generation_id"), canonical.get("calculation_generation"), state.get("canonical_calculation_generation_20260617"), default="")),
        str(_first_nonmissing(canonical.get("source_snapshot_hash"), canonical.get("snapshot_hash"), default="")),
    )


def _nonblank_mask(frame: pd.DataFrame) -> pd.DataFrame:
    """Treat N/A-like strings as missing for display pruning only."""
    if frame.empty:
        return frame.notna()
    mask = frame.notna()
    for column in frame.select_dtypes(include="object").columns:
        cleaned = frame[column].astype(str).str.strip().str.lower()
        mask[column] = mask[column] & ~cleaned.isin({"", "n/a", "na", "none", "nan", "unavailable", "—", "-"})
    return mask


def compact_dinner_history_for_display(table: pd.DataFrame, *, max_columns: int = _DEFAULT_MAX_DISPLAY_COLUMNS) -> pd.DataFrame:
    """Keep useful repeated evidence; full unpruned data remains available for audit/export."""
    if not isinstance(table, pd.DataFrame) or table.empty:
        return pd.DataFrame() if not isinstance(table, pd.DataFrame) else table
    action_columns = [column for column in table.columns if str(column).startswith("Action ")]
    mandatory = [
        "Broker Candle", "Broker Date", "Weekday", "Broker Hour", "Symbol", "Timeframe",
        *action_columns,
        "Protective Action", "Protective Action Reason", "Protective Validation Status",
        "Production Master Decision", "Technical Consensus", "BUY Evidence", "SELL Evidence",
        "Conflict", "Coverage",
    ]
    preferred = [
        *[item for field in _FIELD_LABELS for item in (f"{field} Bias", f"{field} Decision")],
        "NLP Event Bias", "Regime Bias", "Volatility State", "Forecast Bias",
        "Calibrated Probability", "Actionability", "Expected Utility", "Uncertainty", "Research Reliability",
        "Source Coverage",
        *[f"{field} History Quality" for field in _FIELD_LABELS],
    ]
    mask = _nonblank_mask(table)
    counts = mask.sum(axis=0).to_dict()
    # Time/identity and core evidence always remain. Action columns are shown only
    # when they contain genuine repeated source evidence.
    core_mandatory = [column for column in mandatory if column in table.columns and not str(column).startswith("Action ")]
    useful_actions = [
        column for column in action_columns
        if counts.get(column, 0) >= _MIN_NONBLANK_DISPLAY_VALUES
    ]
    front = [column for column in ("Broker Candle", "Broker Date", "Weekday", "Broker Hour", "Symbol", "Timeframe") if column in core_mandatory]
    core_tail = [column for column in core_mandatory if column not in front]
    retained = front + useful_actions + core_tail
    retained = retained[: max(1, int(max_columns))]
    for column in preferred:
        if len(retained) >= int(max_columns):
            break
        if column in table.columns and column not in retained and counts.get(column, 0) >= _MIN_NONBLANK_DISPLAY_VALUES:
            retained.append(column)
    # Remaining source columns are ranked by useful populated rows, then original order.
    remaining = [
        column for column in table.columns
        if column not in retained and counts.get(column, 0) >= _MIN_NONBLANK_DISPLAY_VALUES
        and not column.endswith(" Source Column")
        and column not in {"Broker Candle Time", "Date", "Hour", "Run ID", "Generation ID", "Source Snapshot Hash", "Source Signature"}
    ]
    remaining.sort(key=lambda column: (-int(counts.get(column, 0)), list(table.columns).index(column)))
    target = max(10, min(int(max_columns), max(10, (len(table.columns) + 1) // 2)))
    retained.extend(remaining[: max(0, target - len(retained))])
    retained = list(dict.fromkeys(retained))[: int(max_columns)]
    return table.loc[:, retained].copy(deep=False)


def _candidate_quality(frame: pd.DataFrame, column: str) -> tuple[int, int, int]:
    """Rank genuine row-level history above current-snapshot constants."""
    series = frame[column] if column in frame.columns else pd.Series(dtype="object")
    mask = series.notna() & ~series.astype(str).str.strip().str.upper().isin({"", "N/A", "NA", "NONE", "NAN", "UNAVAILABLE", "—", "-"})
    usable = series.loc[mask]
    populated = int(mask.sum())
    unique = int(usable.astype(str).nunique(dropna=True)) if populated else 0
    variable_bonus = 1 if unique > 1 else 0
    # Sort descending by variable history, then coverage, then unique count.
    return variable_bonus, populated, unique


def _rank_candidates(
    frame: pd.DataFrame, columns: list[str], quality_cache: Mapping[str, tuple[int, int, int]] | None = None
) -> list[str]:
    quality_cache = quality_cache or {}
    return sorted(columns, key=lambda c: quality_cache[c] if c in quality_cache else _candidate_quality(frame, c), reverse=True)


def _numeric_from_row(row: pd.Series, aliases: tuple[str, ...]) -> float | None:
    normalized = {re.sub(r"[^a-z0-9]+", " ", str(c).lower()).strip(): c for c in row.index}
    for alias in aliases:
        wanted = re.sub(r"[^a-z0-9]+", " ", alias.lower()).strip()
        candidates = [c for name, c in normalized.items() if wanted == name or wanted in name]
        for column in candidates:
            value = pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]
            if pd.notna(value):
                return float(value)
    return None


def _four_way_protective_action(row: pd.Series) -> tuple[str, str]:
    """Research/display-only protective policy using only same-row evidence.

    It never changes the production direction.  Missing evidence produces a
    conservative label rather than a fabricated score.
    """
    direction = _direction(row.get("Production Master Decision"))
    if direction == "WAIT":
        direction = _direction(row.get("Technical Consensus"))
    coverage = _numeric_from_row(row, ("Coverage", "Source Coverage", "Data Coverage"))
    conflict = _numeric_from_row(row, ("Conflict", "Conflict Score"))
    uncertainty = _numeric_from_row(row, ("Uncertainty", "Uncertainty %"))
    reliability = _numeric_from_row(row, ("Research Reliability", "Reliability", "Confidence"))
    agreement = _numeric_from_row(row, ("Model Agreement", "Directional Agreement", "Prediction Agreement"))

    # Normalize common percentage/count representations without inventing data.
    if coverage is not None and coverage > 1.0:
        coverage = coverage / 100.0 if coverage <= 100 else None
    if conflict is not None and conflict > 1.0:
        conflict = conflict / 100.0 if conflict <= 100 else None
    if uncertainty is not None and uncertainty <= 1.0:
        uncertainty *= 100.0
    if reliability is not None and reliability <= 1.0:
        reliability *= 100.0
    if agreement is not None and agreement <= 1.0:
        agreement *= 100.0

    if coverage is None or coverage < 0.40:
        return "NO TRADE", "Insufficient same-candle source coverage; no missing value was fabricated."
    if conflict is not None and conflict >= 0.50:
        return "NO TRADE", "High same-candle directional conflict blocks action."
    if uncertainty is not None and uncertainty >= 70.0:
        return "NO TRADE", "Published uncertainty is too high for an allowed action."
    if direction in {"WAIT", "WAIT PULLBACK"}:
        return "WAIT FOR PULLBACK", "Published direction is neutral, mixed, or explicitly waiting for pullback."
    if reliability is not None and reliability >= 70.0 and (agreement is None or agreement >= 60.0) and (conflict is None or conflict < 0.25):
        return "ALLOWED", "Directional evidence has adequate coverage, reliability, agreement, and low conflict."
    return "HOLD AND PROTECT", "Direction is published, but evidence is not strong enough for a new ALLOWED action."


def _numeric_series_from_aliases(frame: pd.DataFrame, aliases: tuple[str, ...]) -> pd.Series:
    """Return the first finite numeric publication per row for ordered aliases."""
    result = pd.Series(float("nan"), index=frame.index, dtype="float64")
    normalized = {column: re.sub(r"[^a-z0-9]+", " ", str(column).lower()).strip() for column in frame.columns}
    ordered: list[str] = []
    for alias in aliases:
        wanted = re.sub(r"[^a-z0-9]+", " ", alias.lower()).strip()
        exact = [column for column, name in normalized.items() if name == wanted]
        partial = [column for column, name in normalized.items() if wanted in name and column not in exact]
        for column in [*exact, *partial]:
            if column not in ordered:
                ordered.append(column)
    for column in ordered:
        incoming = pd.to_numeric(frame[column], errors="coerce")
        result = result.where(result.notna(), incoming)
        if result.notna().all():
            break
    return result


def _add_final_protective_result(table: pd.DataFrame) -> pd.DataFrame:
    """Add the four-label protective result using vectorized same-row evidence."""
    if not isinstance(table, pd.DataFrame) or table.empty:
        return table
    work = table.copy(deep=False)
    production = work.get("Production Master Decision", pd.Series(pd.NA, index=work.index, dtype="object"))
    technical = work.get("Technical Consensus", pd.Series(pd.NA, index=work.index, dtype="object"))
    direction = production.map(_direction)
    missing_production = production.isna() | production.astype(str).str.strip().str.upper().isin({"", "N/A", "NA", "NONE", "NAN", "UNAVAILABLE", "—", "-"})
    direction = direction.where(~missing_production, technical.map(_direction))

    coverage = _numeric_series_from_aliases(work, ("Coverage", "Source Coverage", "Data Coverage"))
    conflict = _numeric_series_from_aliases(work, ("Conflict", "Conflict Score"))
    uncertainty = _numeric_series_from_aliases(work, ("Uncertainty", "Uncertainty %"))
    reliability = _numeric_series_from_aliases(work, ("Research Reliability", "Reliability", "Confidence"))
    agreement = _numeric_series_from_aliases(work, ("Model Agreement", "Directional Agreement", "Prediction Agreement"))

    coverage = coverage.where(coverage <= 1.0, coverage.where(coverage > 100.0, coverage / 100.0))
    conflict = conflict.where(conflict <= 1.0, conflict.where(conflict > 100.0, conflict / 100.0))
    uncertainty = uncertainty.where(uncertainty > 1.0, uncertainty * 100.0)
    reliability = reliability.where(reliability > 1.0, reliability * 100.0)
    agreement = agreement.where(agreement > 1.0, agreement * 100.0)

    action = pd.Series("HOLD AND PROTECT", index=work.index, dtype="object")
    reason = pd.Series(
        "Direction is published, but evidence is not strong enough for a new ALLOWED action.",
        index=work.index, dtype="object",
    )
    allowed = (
        reliability.ge(70.0)
        & (agreement.isna() | agreement.ge(60.0))
        & (conflict.isna() | conflict.lt(0.25))
    )
    action.loc[allowed] = "ALLOWED"
    reason.loc[allowed] = "Directional evidence has adequate coverage, reliability, agreement, and low conflict."

    wait_mask = direction.isin({"WAIT", "WAIT PULLBACK"})
    action.loc[wait_mask] = "WAIT FOR PULLBACK"
    reason.loc[wait_mask] = "Published direction is neutral, mixed, or explicitly waiting for pullback."

    high_uncertainty = uncertainty.ge(70.0)
    high_conflict = conflict.ge(0.50)
    low_coverage = coverage.isna() | coverage.lt(0.40)
    action.loc[high_uncertainty] = "NO TRADE"
    reason.loc[high_uncertainty] = "Published uncertainty is too high for an allowed action."
    action.loc[high_conflict] = "NO TRADE"
    reason.loc[high_conflict] = "High same-candle directional conflict blocks action."
    action.loc[low_coverage] = "NO TRADE"
    reason.loc[low_coverage] = "Insufficient same-candle source coverage; no missing value was fabricated."

    work["Protective Action"] = action
    work["Protective Action Reason"] = reason
    work["Protective Validation Status"] = "VALID FOUR-LABEL OUTPUT"
    return work


def build_field4to9_collection_history(state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None) -> pd.DataFrame:
    identity = _cache_identity(state, canonical)
    cached_identity = state.get("field4to9_collection_history_identity_20260628")
    cached = state.get("field4to9_collection_history_full_20260628")
    if cached_identity == identity and isinstance(cached, pd.DataFrame):
        return cached.copy(deep=False)
    raw = _raw_collection(state, canonical)
    if raw.empty:
        return pd.DataFrame(columns=[
            "Broker Candle", "Broker Date", "Weekday", "Broker Hour", "Symbol", "Timeframe",
            *[item for field in _FIELD_LABELS for item in (f"{field} Bias", f"{field} Decision", f"{field} Source Column")],
            "Technical Consensus", "BUY Evidence", "SELL Evidence", "Conflict", "Coverage",
            "Production Master Decision", "Research Shadow Action", "Run ID", "Generation ID",
        ])

    latest = raw["Broker Candle Time UTC"].max()
    if canonical:
        try:
            from core.canonical_identity_20260627 import canonical_timestamp_value, parse_completed_broker_candle
            candidate = parse_completed_broker_candle(canonical_timestamp_value(canonical), state=state)
        except Exception:
            candidate = pd.NaT
        if pd.notna(candidate):
            latest = candidate
    raw = raw.loc[raw["Broker Candle Time UTC"].between(latest - pd.Timedelta(days=25), latest)].copy()
    raw_columns = [column for column in raw.columns if column != "Broker Candle Time UTC"]
    # Column discovery is invariant across rows. The former implementation
    # recomputed normalization, field routing and eligibility thousands of
    # times per 25-day table, which dominated Dinner opening time.
    eligible_source_columns = set(_source_columns(raw))
    quality_by_column = {column: _candidate_quality(raw, column) for column in eligible_source_columns}
    field_column_plan: dict[str, tuple[list[str], list[str], list[str]]] = {}
    for field in _FIELD_LABELS:
        candidates = [
            column for column in raw_columns
            if column in eligible_source_columns and _field_from_path(column) == field
        ]
        decisions = [column for column in candidates if any(token in _norm(column) for token in ("decision", "action", "signal", "recommendation", "label"))]
        biases = [column for column in candidates if any(token in _norm(column) for token in ("bias", "direction", "stance", "outlook", "trend", "priority"))]
        field_column_plan[field] = (
            _rank_candidates(raw, candidates, quality_by_column),
            _rank_candidates(raw, decisions, quality_by_column),
            _rank_candidates(raw, biases, quality_by_column),
        )

    rows: list[dict[str, Any]] = []
    canonical = canonical or {}
    final = canonical.get("final_decision") if isinstance(canonical.get("final_decision"), Mapping) else {}
    research = state.get("crcef_sv_research_20260627") if isinstance(state.get("crcef_sv_research_20260627"), Mapping) else {}
    research = research or (canonical.get("crcef_sv") if isinstance(canonical.get("crcef_sv"), Mapping) else {})
    research = research or (canonical.get("research_shadow") if isinstance(canonical.get("research_shadow"), Mapping) else {})
    if isinstance(research.get("payload"), Mapping):
        research = research["payload"]
    for _, source_row in raw.iterrows():
        candle = pd.Timestamp(source_row["Broker Candle Time UTC"])
        row: dict[str, Any] = {"Broker Candle Time UTC": candle}
        field_decisions: list[str] = []
        for field in _FIELD_LABELS:
            candidates, decision_candidates, bias_candidates = field_column_plan[field]
            decision_value, decision_source = _first_value(source_row, decision_candidates or candidates)
            bias_value, bias_source = _first_value(source_row, bias_candidates or candidates)
            normalized = _direction(decision_value if pd.notna(decision_value) else bias_value)
            row[f"{field} Bias"] = bias_value
            row[f"{field} Decision"] = decision_value if pd.notna(decision_value) else normalized
            selected_source = decision_source if pd.notna(decision_value) else bias_source
            row[f"{field} Source Column"] = selected_source
            quality = quality_by_column.get(selected_source, (0, 0, 0))
            row[f"{field} History Quality"] = (
                "ROW-VARYING HISTORY" if quality[0] else
                "CONSTANT PUBLISHED SOURCE" if quality[1] >= 2 else
                "SPARSE PUBLISHED SOURCE" if quality[1] == 1 else
                "SOURCE NOT PUBLISHED"
            )
            field_decisions.append(normalized)
        consensus, buy, sell, conflict, coverage = _consensus(field_decisions)
        row["Technical Consensus"] = consensus
        row["BUY Evidence"] = buy
        row["SELL Evidence"] = sell
        row["Conflict"] = conflict
        row["Coverage"] = coverage
        row["Symbol"] = str(_first_nonmissing(canonical.get("symbol"), state.get("symbol"), default="EURUSD"))
        row["Timeframe"] = str(_first_nonmissing(canonical.get("timeframe"), state.get("timeframe"), default="H1"))
        is_current = candle == latest
        row["Production Master Decision"] = (
            _first_nonmissing(final.get("final_decision"), final.get("decision"), canonical.get("full_metric_direction"))
            if is_current else pd.NA
        )
        row["Research Shadow Action"] = (
            _first_nonmissing(research.get("research_shadow_decision"), research.get("shadow_action"))
            if is_current else pd.NA
        )
        row["NLP Event Bias"] = research.get("nlp_event_contribution") if is_current else pd.NA
        row["Regime Bias"] = research.get("regime_relevance") if is_current else pd.NA
        row["Volatility State"] = research.get("volatility_state") if is_current else pd.NA
        row["Forecast Bias"] = research.get("forecast_bias") if is_current else pd.NA
        row["Calibrated Probability"] = _first_nonmissing(research.get("research_calibrated_probability"), research.get("calibrated_direction_probability")) if is_current else pd.NA
        row["Actionability"] = research.get("actionability_probability") if is_current else pd.NA
        row["Expected Utility"] = research.get("expected_utility") if is_current else pd.NA
        row["Uncertainty"] = _first_nonmissing(research.get("uncertainty_pct"), research.get("uncertainty")) if is_current else pd.NA
        row["Research Reliability"] = research.get("research_reliability") if is_current else pd.NA
        row["Run ID"] = canonical.get("run_id") if is_current else pd.NA
        row["Generation ID"] = _first_nonmissing(canonical.get("generation_id"), canonical.get("calculation_generation")) if is_current else pd.NA
        row["Source Snapshot Hash"] = _first_nonmissing(canonical.get("source_snapshot_hash"), canonical.get("snapshot_hash")) if is_current else pd.NA
        row["Source Signature"] = canonical.get("source_signature") if is_current else pd.NA
        # Retain every original source publication after the compact columns.
        for column in raw_columns:
            row[column] = source_row.get(column)
        rows.append(row)

    output = pd.DataFrame(rows).sort_values("Broker Candle Time UTC", ascending=False)
    local = _broker_display(output["Broker Candle Time UTC"], state)
    output.insert(0, "Broker Candle", local)
    output.insert(1, "Broker Date", local.dt.strftime("%Y-%m-%d"))
    output.insert(2, "Weekday", local.dt.strftime("%A"))
    output.insert(3, "Broker Hour", local.dt.strftime("%H:%M"))
    # Compatibility aliases retained for existing exports/tests.
    output.insert(4, "Broker Candle Time", local)
    output.insert(5, "Date", local.dt.strftime("%Y-%m-%d"))
    output.insert(6, "Hour", local.dt.strftime("%H:%M"))
    output.drop(columns=["Broker Candle Time UTC"], inplace=True)
    evidence = [column for column in raw_columns if column in output]
    output["Source Coverage"] = output[evidence].notna().sum(axis=1) if evidence else 0
    output = output.reset_index(drop=True)
    output = _add_protective_action_columns(output)
    output = _add_final_protective_result(output)
    if isinstance(state, MutableMapping):
        state["field4to9_collection_history_identity_20260628"] = identity
        state["field4to9_collection_history_full_20260628"] = output
    return output


def _category(column: str) -> str:
    field = _field_from_path(column)
    if field:
        return field
    name = _norm(column)
    if any(token in name for token in ("sentiment", "nlp", "news")):
        return "Sentiment"
    if "regime" in name:
        return "Regime"
    if any(token in name for token in ("pattern", "mining")):
        return "Pattern"
    return "Technical"


def build_self_calculated_field45_tables(state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None):
    """Legacy research-only audit builder; never used as Dinner production truth."""
    base = build_field4to9_collection_history(state, canonical)
    source = _source_columns(base)
    audit = pd.DataFrame([{"Category": _category(column), "Source Column": column, "Direction Eligible": True} for column in source])
    rows4: list[dict[str, Any]] = []
    rows5: list[dict[str, Any]] = []
    for _, record in base.iterrows():
        categories: dict[str, tuple[float, int]] = {}
        for category in ["Technical", "Sentiment", "Regime", "Pattern", *_FIELD_LABELS]:
            values = [_direction(record[column]) for column in source if _category(column) == category and pd.notna(record[column])]
            buy, sell, total = values.count("BUY"), values.count("SELL"), len(values)
            categories[category] = (0.0 if not total else (buy - sell) / total, total)
        active = [value for value, count in categories.values() if count]
        score = sum(active) / len(active) if active else 0.0
        conflict = any(value > 0 for value in active) and any(value < 0 for value in active)
        decision = "WAIT" if conflict else ("BUY" if score > 0.15 else "SELL" if score < -0.15 else "WAIT")
        rows4.append({
            "Broker Candle Time": record.get("Broker Candle Time"),
            **{f"{key} Category Score": round(value, 4) for key, (value, _) in categories.items()},
            "Table 4 Decision": decision, "Conflict": conflict,
            "Coverage Categories": sum(1 for _, count in categories.values() if count),
            "Source Column Count": len(source),
        })
        rows5.append({
            "Broker Candle Time": record.get("Broker Candle Time"), "Integrated Decision": decision,
            "BUY Categories": sum(value > 0 for value, count in categories.values() if count),
            "SELL Categories": sum(value < 0 for value, count in categories.values() if count),
            "WAIT Categories": sum(value == 0 for value, count in categories.values() if count),
            "Conflict": conflict, "Integrated Score": round(score, 4), "Source Column Count": len(source),
        })
    return pd.DataFrame(rows4), pd.DataFrame(rows5), audit


def render_field4to9_collection_history(state: MutableMapping[str, Any], canonical: Mapping[str, Any] | None = None):
    import streamlit as st
    table = build_field4to9_collection_history(state, canonical)
    st.markdown("### Dinner Combined History — Last 25 Broker Days")
    st.caption(
        "Newest completed MetaTrader broker candle first. The final protective result uses only ALLOWED, WAIT FOR PULLBACK, HOLD AND PROTECT, or NO TRADE. Original BUY/SELL/WAIT values, source columns, and the legacy display-only action translations remain available for audit; no row is fabricated."
    )
    if table.empty:
        st.info("No timestamped Dinner publications are available for this canonical generation.")
    else:
        display = compact_dinner_history_for_display(
            table, max_columns=int(state.get("dinner_history_max_columns_20260628", _DEFAULT_MAX_DISPLAY_COLUMNS) or _DEFAULT_MAX_DISPLAY_COLUMNS)
        )
        removed = max(0, len(table.columns) - len(display.columns))
        st.caption(f"Compact display: {len(display.columns)} useful columns shown; {removed} blank/single-row/audit-only columns omitted from this view.")
        st.dataframe(display, use_container_width=True, hide_index=True, height=430)
        state["field4to9_collection_history_display_20260628"] = display
    state["field4to9_collection_history_20260627"] = table
    return table


def render_self_calculated_field45_tables(state: MutableMapping[str, Any], canonical: Mapping[str, Any] | None = None):
    """Legacy audit renderer retained but not placed above Dinner production data."""
    import streamlit as st
    table4, table5, audit = build_self_calculated_field45_tables(state, canonical)
    st.markdown("### Research-only Category Evidence Audit")
    st.dataframe(table4, use_container_width=True, hide_index=True)
    st.dataframe(table5, use_container_width=True, hide_index=True)
    with st.expander("Source-column audit — exact original inputs", expanded=False):
        st.dataframe(audit, use_container_width=True, hide_index=True)
    state["field4_self_calculated_table_20260627"] = table4
    state["field5_self_calculated_table_20260627"] = table5
    state["field45_source_column_audit_20260627"] = audit
    return table4, table5


__all__ = [
    "build_field4to9_collection_history", "render_field4to9_collection_history",
    "build_self_calculated_field45_tables", "render_self_calculated_field45_tables",
    "_direction", "_source_columns", "_protective_action", "_add_protective_action_columns",
    "_four_way_protective_action", "_add_final_protective_result", "compact_dinner_history_for_display",
]
