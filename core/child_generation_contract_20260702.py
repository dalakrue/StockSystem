"""Immutable child-generation publication contract for Field 10.

The contract freezes already calculated Field 1 Table 4 and Field 3 evidence.
Publication never activates a symbol, modifies Streamlit widget/session identity,
contacts a provider, or recalculates a protected field.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import sqlite3

import pandas as pd

from core.sqlite_readonly_20260704 import connect_readonly

from core.symbol_context_20260702 import SymbolContext, normalize_symbol
from core.generation_registry_20260702 import calculate_valid_until, file_sha256

PUBLICATION_VERSION = "child-generation-publication-20260702-v1"
MANDATORY_STANDARDS = ("Lower Standard", "Middle Standard", "Higher Standard")
PUBLICATION_STATUSES = (
    "INSERTED", "ALREADY_EXISTS_VALID", "REPAIRED_FROM_VALID_SNAPSHOT",
    "MISSING_TABLE4_CURRENT", "MISSING_TABLE4_HISTORY", "MISSING_FIELD3_LOWER",
    "MISSING_FIELD3_MIDDLE", "MISSING_FIELD3_HIGHER", "IDENTITY_CONFLICT",
    "SNAPSHOT_CONFLICT", "DATABASE_FAILURE", "PARTIAL", "COMPLETED",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _norm(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def _json_safe(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()
    if isinstance(value, (pd.Series,)):
        return {str(k): _json_safe(v) for k, v in value.to_dict().items()}
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    try:
        if bool(pd.isna(value)):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


@dataclass(frozen=True, slots=True)
class FrozenFrame:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]

    @classmethod
    def from_frame(cls, frame: pd.DataFrame | None) -> "FrozenFrame":
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            return cls((), ())
        work = frame.copy(deep=True)
        columns = tuple(str(c) for c in work.columns)
        rows = tuple(tuple(_json_safe(v) for v in row) for row in work.itertuples(index=False, name=None))
        return cls(columns, rows)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(list(self.rows), columns=list(self.columns))

    def records(self) -> list[dict[str, Any]]:
        return [dict(zip(self.columns, row)) for row in self.rows]

    def __len__(self) -> int:
        return len(self.rows)


@dataclass(frozen=True, slots=True)
class ChildGenerationBundle:
    context: SymbolContext
    canonical: Mapping[str, Any]
    field1_table4_current: FrozenFrame
    field1_table4_history: FrozenFrame
    field1_table4_source_status: str
    field3_lower_current: FrozenFrame
    field3_middle_current: FrozenFrame
    field3_higher_current: FrozenFrame
    field3_lower_history: FrozenFrame
    field3_middle_history: FrozenFrame
    field3_higher_history: FrozenFrame
    completed_broker_candle: str
    source_frame_signature: Mapping[str, Any]
    data_quality: Mapping[str, Any]
    protected_final_action: str
    trade_permission: str
    runtime_snapshot_path: str
    runtime_snapshot_sha256: str
    calculation_timing: Mapping[str, Any]
    resource_metrics: Mapping[str, Any]
    calculation_status: str

    def identity_tuple(self) -> tuple[str, ...]:
        c = self.context
        return (
            str(c.parent_run_id or ""), str(c.child_run_id or ""), c.lunch_display_symbol,
            c.timeframe, str(c.canonical_run_id or ""), str(c.source_id or ""),
            str(c.snapshot_hash or ""), self.completed_broker_candle,
        )

    def fingerprint(self) -> str:
        payload = {
            "identity": self.identity_tuple(),
            "snapshot_sha256": self.runtime_snapshot_sha256,
            "table4_current": self.field1_table4_current.records(),
            "field3": {
                "lower": self.field3_lower_current.records(),
                "middle": self.field3_middle_current.records(),
                "higher": self.field3_higher_current.records(),
            },
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _canonical_identity(canonical: Mapping[str, Any], context: SymbolContext) -> tuple[str, str, str, str]:
    run_id = str(canonical.get("run_id") or canonical.get("canonical_calculation_id") or context.canonical_run_id or "")
    source_id = str(canonical.get("source_id") or canonical.get("data_source_id") or canonical.get("source_snapshot_hash") or context.source_id or "")
    snapshot_hash = str(canonical.get("snapshot_hash") or canonical.get("source_snapshot_hash") or context.snapshot_hash or "")
    candle = canonical.get("completed_broker_candle") or canonical.get("broker_candle_time") or canonical.get("latest_completed_candle_time") or canonical.get("completed_candle") or context.completed_broker_candle
    stamp = pd.to_datetime(candle, errors="coerce", utc=True)
    return run_id, source_id, snapshot_hash, "" if pd.isna(stamp) else pd.Timestamp(stamp).floor("h").isoformat()


def _find_time_column(frame: pd.DataFrame) -> str | None:
    exact = {_norm(c): str(c) for c in frame.columns}
    for alias in ("brokercandletime", "brokertimestamp", "completedbrokercandle", "timestamp", "datetime", "time"):
        if alias in exact:
            return exact[alias]
    return next((str(c) for c in frame.columns if "time" in _norm(c)), None)


def _current_table4(frame: pd.DataFrame, candle: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    tc = _find_time_column(frame)
    if not tc:
        return frame.head(1).copy(deep=True)
    times = pd.to_datetime(frame[tc], errors="coerce", utc=True).dt.floor("h")
    target = pd.to_datetime(candle, errors="coerce", utc=True)
    if not pd.isna(target):
        exact = frame.loc[times == pd.Timestamp(target).floor("h")]
        if not exact.empty:
            return exact.head(1).copy(deep=True)
    order = times.sort_values(ascending=False).index
    return frame.loc[order].head(1).copy(deep=True)


def _standard_name(value: Any) -> str | None:
    text = _norm(value)
    if "lower" in text or text in {"low", "1day", "rolling24h"}:
        return "Lower Standard"
    if "middle" in text or "medium" in text or text in {"5day"}:
        return "Middle Standard"
    if "higher" in text or text in {"high", "25day"}:
        return "Higher Standard"
    return None


def _standard_frames(state: Mapping[str, Any], candle: str) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    current: dict[str, pd.DataFrame] = {}
    history: dict[str, pd.DataFrame] = {}
    summary = state.get("regime_standard_table_20260617")
    if isinstance(summary, pd.DataFrame) and not summary.empty:
        standard_col = next((str(c) for c in summary.columns if "standard" in _norm(c)), None)
        if standard_col:
            for _, row in summary.iterrows():
                name = _standard_name(row.get(standard_col))
                if name and name not in current:
                    current[name] = pd.DataFrame([row.to_dict()])
    details = state.get("regime_standard_detail_tables_published_20260618")
    if not isinstance(details, Mapping):
        details = state.get("regime_standard_detail_tables_20260617")
    if isinstance(details, Mapping):
        for key, value in details.items():
            name = _standard_name(key)
            if not name or not isinstance(value, pd.DataFrame) or value.empty:
                continue
            history[name] = value.copy(deep=True)
            if name not in current:
                current[name] = _current_table4(value, candle)
    lifecycle = state.get("field3_regime_lifecycle_monitor_20260701")
    if isinstance(lifecycle, Mapping):
        histories = lifecycle.get("history_by_standard") or lifecycle.get("standards")
        if isinstance(histories, Mapping):
            for key, value in histories.items():
                name = _standard_name(key)
                frame = value if isinstance(value, pd.DataFrame) else pd.DataFrame(value or [])
                if name and not frame.empty:
                    history.setdefault(name, frame.copy(deep=True))
                    current.setdefault(name, _current_table4(frame, candle))

    # Secondary LUNCH_CORE children publish this exact-symbol, exact-timeframe
    # three-standard object. It is calculated from the already activated frame
    # with provider access disabled, so accepting it here cannot borrow data or
    # trigger work during rendering/reload validation.
    local = state.get("field3_local_symbol_snapshot_20260703")
    if isinstance(local, Mapping) and bool(local.get("ok")):
        summary = local.get("summary")
        summary_frame = summary.copy(deep=True) if isinstance(summary, pd.DataFrame) else pd.DataFrame(summary or [])
        if not summary_frame.empty:
            standard_col = next((str(c) for c in summary_frame.columns if "standard" in _norm(c)), None)
            if standard_col:
                for _, row in summary_frame.iterrows():
                    name = _standard_name(row.get(standard_col))
                    if name:
                        current.setdefault(name, pd.DataFrame([row.to_dict()]))
        details = local.get("details")
        if isinstance(details, Mapping):
            for key, value in details.items():
                name = _standard_name(key)
                frame = value.copy(deep=True) if isinstance(value, pd.DataFrame) else pd.DataFrame(value or [])
                if name and not frame.empty:
                    history.setdefault(name, frame)
                    current.setdefault(name, _current_table4(frame, candle))
    return current, history


def build_child_generation_bundle(
    *, state: MutableMapping[str, Any], canonical: Mapping[str, Any], context: SymbolContext,
    runtime_snapshot_path: Path | str, calculation_status: str,
    calculation_timing: Mapping[str, Any] | None = None,
    resource_metrics: Mapping[str, Any] | None = None,
) -> ChildGenerationBundle:
    """Freeze genuine already-calculated artifacts for one child generation."""
    canonical = dict(canonical or {})
    run_id, source_id, snapshot_hash, candle = _canonical_identity(canonical, context)
    canonical_symbol = normalize_symbol(canonical.get("symbol") or context.calculation_symbol or context.lunch_display_symbol)
    if canonical_symbol != context.lunch_display_symbol:
        raise ValueError(f"IDENTITY_CONFLICT: canonical={canonical_symbol} context={context.lunch_display_symbol}")
    if context.canonical_run_id and run_id != str(context.canonical_run_id):
        raise ValueError("IDENTITY_CONFLICT: canonical run ID mismatch")
    if context.source_id and source_id != str(context.source_id):
        raise ValueError("IDENTITY_CONFLICT: source ID mismatch")
    if context.snapshot_hash and snapshot_hash != str(context.snapshot_hash):
        raise ValueError("SNAPSHOT_CONFLICT: snapshot hash mismatch")
    if not all((context.parent_run_id, context.child_run_id, run_id, source_id, snapshot_hash, candle)):
        raise ValueError("IDENTITY_CONFLICT: incomplete child identity tuple")

    from ui.lunch_next_hour_bias_history_20260626 import build_field1_table4_publication
    table4, source_status = build_field1_table4_publication(state=state, canonical=canonical)
    table4 = table4.copy(deep=True) if isinstance(table4, pd.DataFrame) else pd.DataFrame()
    current4 = _current_table4(table4, candle)
    standards_current, standards_history = _standard_frames(state, candle)

    quality: Mapping[str, Any] = {}
    try:
        from core.multi_symbol_field10_20260701 import assess_data_quality
        quality = dict(assess_data_quality(state, canonical))
    except Exception as exc:
        quality = {"grade": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"}
    final = _mapping(canonical.get("final_decision"))
    protected_action = str(final.get("final_decision") or final.get("less_risky_decision") or canonical.get("decision") or "UNAVAILABLE").upper()
    permission = str(final.get("trade_permission") or canonical.get("trade_permission") or "CHECK").upper()
    try:
        from core.runtime_state_cache_20260628 import build_source_signature
        signature = dict(build_source_signature(state))
    except Exception:
        signature = {}
    snapshot = Path(runtime_snapshot_path)
    checksum = file_sha256(snapshot) if snapshot.is_file() else ""
    if not checksum:
        raise ValueError("SNAPSHOT_CONFLICT: runtime snapshot is missing")

    updated_context = SymbolContext(
        settings_main_symbol=context.settings_main_symbol,
        connector_symbol=context.connector_symbol,
        calculation_symbol=context.calculation_symbol,
        lunch_display_symbol=context.lunch_display_symbol,
        active_snapshot_symbol=context.lunch_display_symbol,
        selected_symbols=context.selected_symbols,
        timeframe=context.timeframe,
        parent_run_id=context.parent_run_id,
        child_run_id=context.child_run_id,
        canonical_run_id=run_id,
        source_id=source_id,
        snapshot_hash=snapshot_hash,
        completed_broker_candle=candle,
        generation_status=context.generation_status,
        valid_until=context.valid_until or calculate_valid_until(candle, context.timeframe),
    )
    return ChildGenerationBundle(
        context=updated_context, canonical=_json_safe(canonical),
        field1_table4_current=FrozenFrame.from_frame(current4),
        field1_table4_history=FrozenFrame.from_frame(table4),
        field1_table4_source_status=str(source_status),
        field3_lower_current=FrozenFrame.from_frame(standards_current.get("Lower Standard")),
        field3_middle_current=FrozenFrame.from_frame(standards_current.get("Middle Standard")),
        field3_higher_current=FrozenFrame.from_frame(standards_current.get("Higher Standard")),
        field3_lower_history=FrozenFrame.from_frame(standards_history.get("Lower Standard")),
        field3_middle_history=FrozenFrame.from_frame(standards_history.get("Middle Standard")),
        field3_higher_history=FrozenFrame.from_frame(standards_history.get("Higher Standard")),
        completed_broker_candle=candle, source_frame_signature=_json_safe(signature),
        data_quality=_json_safe(quality), protected_final_action=protected_action,
        trade_permission=permission, runtime_snapshot_path=str(snapshot.resolve()),
        runtime_snapshot_sha256=checksum, calculation_timing=_json_safe(calculation_timing or {}),
        resource_metrics=_json_safe(resource_metrics or {}), calculation_status=str(calculation_status).upper(),
    )


def _connect(path: Path | str) -> sqlite3.Connection:
    db = Path(path); db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), timeout=8.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    return conn


def migrate_child_publication_contract(path: Path | str) -> dict[str, Any]:
    with _connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS child_generation_registry (
                parent_run_id TEXT NOT NULL, child_run_id TEXT NOT NULL, symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL, canonical_run_id TEXT NOT NULL, source_id TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL, completed_broker_candle TEXT NOT NULL,
                valid_until TEXT NOT NULL, runtime_snapshot_path TEXT NOT NULL,
                runtime_snapshot_sha256 TEXT NOT NULL, bundle_fingerprint TEXT NOT NULL,
                calculation_status TEXT NOT NULL, publication_status TEXT NOT NULL,
                diagnostic TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,completed_broker_candle)
            );
            CREATE TABLE IF NOT EXISTS field1_table4_current_evidence (
                parent_run_id TEXT NOT NULL, child_run_id TEXT NOT NULL, symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL, canonical_run_id TEXT NOT NULL, source_id TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL, broker_timestamp TEXT NOT NULL, evidence_json TEXT NOT NULL,
                source_status TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,broker_timestamp)
            );
            CREATE TABLE IF NOT EXISTS field1_table4_history_evidence (
                parent_run_id TEXT NOT NULL, child_run_id TEXT NOT NULL, symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL, canonical_run_id TEXT NOT NULL, snapshot_hash TEXT NOT NULL,
                broker_timestamp TEXT NOT NULL, row_number INTEGER NOT NULL, evidence_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,broker_timestamp,row_number)
            );
            CREATE TABLE IF NOT EXISTS field3_standard_evidence (
                parent_run_id TEXT NOT NULL, child_run_id TEXT NOT NULL, symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL, canonical_run_id TEXT NOT NULL, snapshot_hash TEXT NOT NULL,
                broker_timestamp TEXT NOT NULL, standard TEXT NOT NULL, evidence_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,broker_timestamp,standard)
            );
            CREATE TABLE IF NOT EXISTS field3_history_evidence (
                parent_run_id TEXT NOT NULL, child_run_id TEXT NOT NULL, symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL, canonical_run_id TEXT NOT NULL, snapshot_hash TEXT NOT NULL,
                broker_timestamp TEXT NOT NULL, standard TEXT NOT NULL, row_number INTEGER NOT NULL,
                evidence_json TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,broker_timestamp,standard,row_number)
            );
            CREATE TABLE IF NOT EXISTS child_runtime_snapshot_metadata (
                parent_run_id TEXT NOT NULL, child_run_id TEXT NOT NULL, symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL, canonical_run_id TEXT NOT NULL, snapshot_hash TEXT NOT NULL,
                broker_timestamp TEXT NOT NULL, runtime_snapshot_path TEXT NOT NULL,
                runtime_snapshot_sha256 TEXT NOT NULL, source_signature_json TEXT NOT NULL,
                timing_json TEXT NOT NULL, resource_json TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,broker_timestamp)
            );
            CREATE TABLE IF NOT EXISTS publication_diagnostics (
                diagnostic_id INTEGER PRIMARY KEY AUTOINCREMENT, parent_run_id TEXT, child_run_id TEXT,
                symbol TEXT, timeframe TEXT, canonical_run_id TEXT, snapshot_hash TEXT,
                broker_timestamp TEXT, status TEXT NOT NULL, detail_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_child_registry_lookup
                ON child_generation_registry(parent_run_id,symbol,timeframe,completed_broker_candle DESC);
            CREATE INDEX IF NOT EXISTS idx_field1_history_symbol_time
                ON field1_table4_history_evidence(symbol,timeframe,broker_timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_field3_history_symbol_time
                ON field3_history_evidence(symbol,timeframe,broker_timestamp DESC,standard);
            """
        )
        # Existing installations may predate the diagnostic publication column.
        cols = {row[1] for row in conn.execute("PRAGMA table_info(field10_integrated_evidence_history)")}
        if cols and "publication_status" not in cols:
            conn.execute("ALTER TABLE field10_integrated_evidence_history ADD COLUMN publication_status TEXT")
        conn.commit()
    return {"ok": True, "status": "MIGRATED", "version": PUBLICATION_VERSION, "path": str(path)}


def _lookup(record: Mapping[str, Any], *aliases: str) -> Any:
    keys = {_norm(k): k for k in record}
    for alias in aliases:
        key = keys.get(_norm(alias))
        if key is not None:
            value = record.get(key)
            if value not in (None, ""):
                return value
    return None


def _bias(value: Any) -> str | None:
    text = str(value or "").upper()
    if any(v in text for v in ("BUY", "BULL", "LONG", "UP")): return "BUY"
    if any(v in text for v in ("SELL", "BEAR", "SHORT", "DOWN")): return "SELL"
    if any(v in text for v in ("WAIT", "HOLD", "NEUTRAL", "FLAT")): return "WAIT"
    return None


def _number(value: Any, percent: bool = False) -> float | None:
    try: number = float(value)
    except Exception: return None
    if pd.isna(number): return None
    if percent and abs(number) > 1: number /= 100.0
    return number


def _first_record(frame: FrozenFrame) -> dict[str, Any]:
    records = frame.records()
    return records[0] if records else {}


def _integrated_values(bundle: ChildGenerationBundle, publication_status: str) -> dict[str, Any]:
    c = bundle.context; row = _first_record(bundle.field1_table4_current)
    higher = _first_record(bundle.field3_higher_current)
    final = _mapping(bundle.canonical.get("final_decision"))
    current_session = _lookup(row, "Current Session", "Session") or bundle.canonical.get("current_session") or bundle.canonical.get("session")
    technical = _bias(_lookup(row, "Technical Bias for Next H1", "Technical Bias"))
    sentiment = _bias(_lookup(row, "Sentiment Bias for Next H1", "Sentiment Bias"))
    session_bias = _bias(_lookup(row, "Session Bias for Next H1", "Session Bias"))
    data_mining = _bias(_lookup(row, "Data Mining Bias for Next H1", "Data-Mining Bias", "Data Mining Bias"))
    regime_bias = _bias(_lookup(row, "Regime Bias for Next H1", "Regime Bias") or _lookup(higher, "Regime Bias", "Bias"))
    combined = _bias(_lookup(row, "Combined Next-Hour Direction", "Existing Combined Evidence Bias"))
    components = [x for x in (technical, sentiment, session_bias, data_mining, regime_bias) if x]
    agreement = None
    conflict = None
    if components:
        top = max(components.count("BUY"), components.count("SELL"), components.count("WAIT"))
        agreement = top / len(components)
        conflict = 1.0 - agreement
    candle = pd.Timestamp(bundle.completed_broker_candle)
    return {
        "parent_run_id": str(c.parent_run_id), "child_run_id": str(c.child_run_id),
        "canonical_run_id": str(c.canonical_run_id), "symbol": c.lunch_display_symbol,
        "role": "MAIN" if c.lunch_display_symbol == c.settings_main_symbol else "SECONDARY",
        "timeframe": c.timeframe, "broker_timestamp": bundle.completed_broker_candle,
        "broker_date": candle.strftime("%Y-%m-%d"), "broker_hour": int(candle.hour), "rank": None,
        "current_session": str(current_session or "UNAVAILABLE"),
        "technical_bias": technical, "technical_source": "FIELD1_TABLE4",
        "technical_reliability": _number(_lookup(row, "Technical Reliability", "Technical Reliability %"), True),
        "sentiment_bias": sentiment, "sentiment_source": "FIELD1_TABLE4",
        "sentiment_reliability": _number(_lookup(row, "Sentiment Reliability", "Sentiment Reliability %"), True),
        "session_bias": session_bias, "session_source": "FIELD1_TABLE4",
        "session_reliability": _number(_lookup(row, "Session Reliability", "Session Reliability %"), True),
        "regime_bias": regime_bias, "regime_source": "SAVED_FIELD3_HIGHER",
        "higher_standard_regime": _lookup(higher, "Regime", "Higher Standard Regime"),
        "regime_probability": _number(_lookup(higher, "Regime Probability", "Probability"), True),
        "regime_entropy": _number(_lookup(higher, "Regime Entropy", "Entropy")),
        "regime_posterior_margin": _number(_lookup(higher, "Posterior Margin", "Regime Posterior Margin")),
        "expected_regime_duration": _number(_lookup(higher, "Expected Duration")),
        "data_mining_bias": data_mining, "data_mining_source": "FIELD1_TABLE4",
        "combined_evidence_bias": combined, "evidence_available_count": len(components),
        "evidence_agreement": agreement, "conflict_index": conflict,
        "transition_risk_1h": _number(_lookup(higher, "Transition Risk 1H"), True),
        "transition_risk_3h": _number(_lookup(higher, "Transition Risk 3H"), True),
        "transition_risk_6h": _number(_lookup(higher, "Transition Risk 6H"), True),
        "transition_risk_24h": _number(_lookup(higher, "Transition Risk 24H", "Transition Probability 24H"), True),
        "expected_return_12h": _number(_lookup(higher, "Expected Return 12H (%)", "Expected Return 12H")),
        "expected_return_24h": _number(_lookup(higher, "Expected Return 24H (%)", "Expected Return 24H")),
        "expected_return_36h": _number(_lookup(higher, "Expected Return 36H (%)", "Expected Return 36H")),
        "drift_status": str(_lookup(higher, "Drift Status") or "UNAVAILABLE"),
        "calibrated_reliability": _number(_lookup(higher, "Calibrated Reliability", "Reliability"), True),
        "data_quality_grade": str(bundle.data_quality.get("grade") or bundle.data_quality.get("data_quality_grade") or "UNAVAILABLE"),
        "trade_permission": str(bundle.trade_permission), "validation_permission": str(bundle.trade_permission),
        "protected_final_action": str(bundle.protected_final_action),
        "explanation": str(_lookup(row, "Explanation") or final.get("explanation") or "Protected outputs copied from saved Field 1 and Field 3 evidence."),
        "source_id": str(c.source_id), "snapshot_hash": str(c.snapshot_hash),
        "calculation_version": PUBLICATION_VERSION, "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "publication_status": publication_status,
    }


def validate_bundle(bundle: ChildGenerationBundle) -> tuple[str, list[str]]:
    missing: list[str] = []
    if bundle.calculation_status not in {"COMPLETED", "SUCCESS", "OK"}: missing.append("PROTECTED_CALCULATION")
    if len(bundle.field1_table4_current) < 1: return "MISSING_TABLE4_CURRENT", ["Field 1 Table 4 current row"]
    if len(bundle.field1_table4_history) < 1: return "MISSING_TABLE4_HISTORY", ["Field 1 Table 4 history"]
    if len(bundle.field3_lower_current) < 1: return "MISSING_FIELD3_LOWER", ["Field 3 Lower Standard"]
    if len(bundle.field3_middle_current) < 1: return "MISSING_FIELD3_MIDDLE", ["Field 3 Middle Standard"]
    if len(bundle.field3_higher_current) < 1: return "MISSING_FIELD3_HIGHER", ["Field 3 Higher Standard"]
    if not Path(bundle.runtime_snapshot_path).is_file(): return "SNAPSHOT_CONFLICT", ["runtime snapshot file"]
    if file_sha256(bundle.runtime_snapshot_path) != bundle.runtime_snapshot_sha256: return "SNAPSHOT_CONFLICT", ["runtime snapshot checksum"]
    identity = bundle.identity_tuple()
    if any(not value for value in identity): return "IDENTITY_CONFLICT", ["identity tuple"]
    if missing: return "PARTIAL", missing
    return "COMPLETED", []


def _insert_json_rows(conn: sqlite3.Connection, table: str, bundle: ChildGenerationBundle, standard: str | None, frame: FrozenFrame) -> None:
    c = bundle.context; created = pd.Timestamp.now(tz="UTC").isoformat()
    for number, record in enumerate(frame.records()):
        if table == "field1_table4_history_evidence":
            conn.execute(
                f"INSERT OR REPLACE INTO {table}(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,broker_timestamp,row_number,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (c.parent_run_id,c.child_run_id,c.lunch_display_symbol,c.timeframe,c.canonical_run_id,c.snapshot_hash,bundle.completed_broker_candle,number,json.dumps(record,sort_keys=True,default=str),created),
            )
        else:
            conn.execute(
                f"INSERT OR REPLACE INTO {table}(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,broker_timestamp,standard,row_number,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (c.parent_run_id,c.child_run_id,c.lunch_display_symbol,c.timeframe,c.canonical_run_id,c.snapshot_hash,bundle.completed_broker_candle,standard,number,json.dumps(record,sort_keys=True,default=str),created),
            )


def publish_child_generation_to_field10(bundle: ChildGenerationBundle, *, path: Path | str, repair: bool = False) -> dict[str, Any]:
    """Atomically publish one immutable bundle and verify the exact identity."""
    from core.field10_integrated_evidence_20260702 import migrate_integrated_evidence_database, TABLE_NAME
    migrate_integrated_evidence_database(path); migrate_child_publication_contract(path)
    validation_status, missing = validate_bundle(bundle)
    c = bundle.context; now = pd.Timestamp.now(tz="UTC").isoformat()
    diagnostic = {"missing": missing, "bundle_fingerprint": bundle.fingerprint(), "version": PUBLICATION_VERSION}
    if validation_status != "COMPLETED":
        try:
            with _connect(path) as conn:
                conn.execute("INSERT INTO publication_diagnostics(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,broker_timestamp,status,detail_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (c.parent_run_id,c.child_run_id,c.lunch_display_symbol,c.timeframe,c.canonical_run_id,c.snapshot_hash,bundle.completed_broker_candle,validation_status,json.dumps(diagnostic,sort_keys=True),now))
                conn.commit()
        except Exception:
            pass
        return {"ok": False, "status": validation_status, "missing_artifacts": missing, "identity": bundle.identity_tuple()}
    desired_status = "REPAIRED_FROM_VALID_SNAPSHOT" if repair else "INSERTED"
    try:
        with _connect(path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE parent_run_id=? AND child_run_id=? AND symbol=? AND timeframe=? AND canonical_run_id=? AND snapshot_hash=? AND broker_timestamp=?",
                (c.parent_run_id,c.child_run_id,c.lunch_display_symbol,c.timeframe,c.canonical_run_id,c.snapshot_hash,bundle.completed_broker_candle),
            ).fetchone()[0]
            status = "ALREADY_EXISTS_VALID" if existing else desired_status
            conn.execute(
                """INSERT OR REPLACE INTO child_generation_registry(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,source_id,snapshot_hash,completed_broker_candle,valid_until,runtime_snapshot_path,runtime_snapshot_sha256,bundle_fingerprint,calculation_status,publication_status,diagnostic,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (c.parent_run_id,c.child_run_id,c.lunch_display_symbol,c.timeframe,c.canonical_run_id,c.source_id,c.snapshot_hash,bundle.completed_broker_candle,c.valid_until or calculate_valid_until(bundle.completed_broker_candle,c.timeframe),bundle.runtime_snapshot_path,bundle.runtime_snapshot_sha256,bundle.fingerprint(),bundle.calculation_status,"PARTIAL",json.dumps(diagnostic,sort_keys=True),now,now),
            )
            current4 = _first_record(bundle.field1_table4_current)
            conn.execute(
                "INSERT OR REPLACE INTO field1_table4_current_evidence(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,source_id,snapshot_hash,broker_timestamp,evidence_json,source_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (c.parent_run_id,c.child_run_id,c.lunch_display_symbol,c.timeframe,c.canonical_run_id,c.source_id,c.snapshot_hash,bundle.completed_broker_candle,json.dumps(current4,sort_keys=True,default=str),bundle.field1_table4_source_status,now),
            )
            _insert_json_rows(conn,"field1_table4_history_evidence",bundle,None,bundle.field1_table4_history)
            standards = (("Lower Standard",bundle.field3_lower_current,bundle.field3_lower_history),("Middle Standard",bundle.field3_middle_current,bundle.field3_middle_history),("Higher Standard",bundle.field3_higher_current,bundle.field3_higher_history))
            for standard,current,history in standards:
                conn.execute(
                    "INSERT OR REPLACE INTO field3_standard_evidence(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,broker_timestamp,standard,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (c.parent_run_id,c.child_run_id,c.lunch_display_symbol,c.timeframe,c.canonical_run_id,c.snapshot_hash,bundle.completed_broker_candle,standard,json.dumps(_first_record(current),sort_keys=True,default=str),now),
                )
                _insert_json_rows(conn,"field3_history_evidence",bundle,standard,history)
            values = _integrated_values(bundle,status)
            columns = list(values); placeholders = ",".join("?" for _ in columns)
            conn.execute(f"INSERT OR IGNORE INTO {TABLE_NAME}({','.join(columns)}) VALUES({placeholders})",tuple(values[k] for k in columns))
            if existing:
                conn.execute(f"UPDATE {TABLE_NAME} SET publication_status=? WHERE parent_run_id=? AND child_run_id=? AND symbol=? AND timeframe=? AND canonical_run_id=? AND snapshot_hash=? AND broker_timestamp=?",
                    (status,c.parent_run_id,c.child_run_id,c.lunch_display_symbol,c.timeframe,c.canonical_run_id,c.snapshot_hash,bundle.completed_broker_candle))
            conn.execute(
                "INSERT OR REPLACE INTO child_runtime_snapshot_metadata(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,broker_timestamp,runtime_snapshot_path,runtime_snapshot_sha256,source_signature_json,timing_json,resource_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (c.parent_run_id,c.child_run_id,c.lunch_display_symbol,c.timeframe,c.canonical_run_id,c.snapshot_hash,bundle.completed_broker_candle,bundle.runtime_snapshot_path,bundle.runtime_snapshot_sha256,json.dumps(bundle.source_frame_signature,sort_keys=True,default=str),json.dumps(bundle.calculation_timing,sort_keys=True,default=str),json.dumps(bundle.resource_metrics,sort_keys=True,default=str),now),
            )
            verified = conn.execute(
                f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE parent_run_id=? AND child_run_id=? AND symbol=? AND timeframe=? AND canonical_run_id=? AND snapshot_hash=? AND broker_timestamp=?",
                (c.parent_run_id,c.child_run_id,c.lunch_display_symbol,c.timeframe,c.canonical_run_id,c.snapshot_hash,bundle.completed_broker_candle),
            ).fetchone()[0]
            standards_count = conn.execute(
                "SELECT COUNT(DISTINCT standard) FROM field3_standard_evidence WHERE parent_run_id=? AND child_run_id=? AND symbol=? AND timeframe=? AND canonical_run_id=? AND snapshot_hash=? AND broker_timestamp=?",
                (c.parent_run_id,c.child_run_id,c.lunch_display_symbol,c.timeframe,c.canonical_run_id,c.snapshot_hash,bundle.completed_broker_candle),
            ).fetchone()[0]
            current_count = conn.execute(
                "SELECT COUNT(*) FROM field1_table4_current_evidence WHERE parent_run_id=? AND child_run_id=? AND symbol=? AND timeframe=? AND canonical_run_id=? AND snapshot_hash=? AND broker_timestamp=?",
                (c.parent_run_id,c.child_run_id,c.lunch_display_symbol,c.timeframe,c.canonical_run_id,c.snapshot_hash,bundle.completed_broker_candle),
            ).fetchone()[0]
            history_count = conn.execute(
                "SELECT COUNT(*) FROM field1_table4_history_evidence WHERE parent_run_id=? AND child_run_id=? AND symbol=? AND timeframe=? AND canonical_run_id=? AND snapshot_hash=? AND broker_timestamp=?",
                (c.parent_run_id,c.child_run_id,c.lunch_display_symbol,c.timeframe,c.canonical_run_id,c.snapshot_hash,bundle.completed_broker_candle),
            ).fetchone()[0]
            if verified < 1 or standards_count != 3 or current_count < 1 or history_count < 1:
                raise RuntimeError(f"mandatory verification failed integrated={verified}, standards={standards_count}, table4_current={current_count}, history={history_count}")
            conn.execute("UPDATE child_generation_registry SET publication_status=?,updated_at=? WHERE parent_run_id=? AND child_run_id=? AND symbol=? AND timeframe=? AND canonical_run_id=? AND snapshot_hash=? AND completed_broker_candle=?",
                ("COMPLETED" if status == "INSERTED" else status,now,c.parent_run_id,c.child_run_id,c.lunch_display_symbol,c.timeframe,c.canonical_run_id,c.snapshot_hash,bundle.completed_broker_candle))
            conn.execute("INSERT INTO publication_diagnostics(parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,snapshot_hash,broker_timestamp,status,detail_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (c.parent_run_id,c.child_run_id,c.lunch_display_symbol,c.timeframe,c.canonical_run_id,c.snapshot_hash,bundle.completed_broker_candle,status,json.dumps({**diagnostic,"verified_count":verified,"standards_count":standards_count,"history_count":history_count},sort_keys=True),now))
            conn.commit()
        return {"ok": True, "status": status, "completion_status": "COMPLETED", "verified_count": int(verified), "field3_standard_count": int(standards_count), "table4_history_rows": int(history_count), "identity": bundle.identity_tuple(), "bundle_fingerprint": bundle.fingerprint()}
    except sqlite3.IntegrityError as exc:
        return {"ok": False,"status":"IDENTITY_CONFLICT","error":f"{type(exc).__name__}: {exc}","identity":bundle.identity_tuple()}
    except Exception as exc:
        return {"ok":False,"status":"DATABASE_FAILURE","error":f"{type(exc).__name__}: {exc}","identity":bundle.identity_tuple()}


__all__ = [
    "FrozenFrame", "ChildGenerationBundle", "PUBLICATION_STATUSES", "PUBLICATION_VERSION",
    "build_child_generation_bundle", "migrate_child_publication_contract",
    "publish_child_generation_to_field10", "validate_bundle",
    "load_child_contract_tables", "load_latest_child_contract_tables",
]


def _decode_evidence_rows(rows: Sequence[tuple[Any, ...]], json_index: int, extra: Mapping[str, Any] | None = None) -> pd.DataFrame:
    decoded: list[dict[str, Any]] = []
    for row in rows:
        try:
            item = json.loads(str(row[json_index]))
            if isinstance(item, Mapping):
                record = dict(item)
                if extra:
                    record = {**dict(extra), **record}
                decoded.append(record)
        except Exception:
            continue
    return pd.DataFrame(decoded)


def load_child_contract_tables(
    *, path: Path | str, parent_run_id: str, symbol: str, timeframe: str = "H1",
    child_run_id: str | None = None,
) -> dict[str, Any]:
    """Load exact saved Field 1/3 artifacts and publication diagnostics."""
    symbol = normalize_symbol(symbol); params: list[Any] = [parent_run_id, symbol, str(timeframe).upper()]
    child_clause = ""
    if child_run_id:
        child_clause = " AND child_run_id=?"; params.append(child_run_id)
    with connect_readonly(path) as conn:
        generation = conn.execute(
            f"SELECT parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,source_id,snapshot_hash,completed_broker_candle,valid_until,runtime_snapshot_path,runtime_snapshot_sha256,calculation_status,publication_status,diagnostic FROM child_generation_registry WHERE parent_run_id=? AND symbol=? AND timeframe=?{child_clause} ORDER BY completed_broker_candle DESC,updated_at DESC LIMIT 1",
            params,
        ).fetchone()
        if not generation:
            return {"ok": False, "status": "NO_CHILD_GENERATION", "table4_current": pd.DataFrame(), "table4_history": pd.DataFrame(), "field3_current": pd.DataFrame(), "field3_history": pd.DataFrame(), "diagnostics": pd.DataFrame()}
        names = ["parent_run_id","child_run_id","symbol","timeframe","canonical_run_id","source_id","snapshot_hash","completed_broker_candle","valid_until","runtime_snapshot_path","runtime_snapshot_sha256","calculation_status","publication_status","diagnostic"]
        meta = dict(zip(names,generation))
        identity = (meta["parent_run_id"],meta["child_run_id"],meta["symbol"],meta["timeframe"],meta["canonical_run_id"],meta["snapshot_hash"],meta["completed_broker_candle"])
        q = "parent_run_id=? AND child_run_id=? AND symbol=? AND timeframe=? AND canonical_run_id=? AND snapshot_hash=? AND broker_timestamp=?"
        current_rows = conn.execute(f"SELECT evidence_json FROM field1_table4_current_evidence WHERE {q}",identity).fetchall()
        history_rows = conn.execute(f"SELECT evidence_json FROM field1_table4_history_evidence WHERE {q} ORDER BY row_number",identity).fetchall()
        standard_rows = conn.execute(f"SELECT standard,evidence_json FROM field3_standard_evidence WHERE {q} ORDER BY CASE standard WHEN 'Lower Standard' THEN 1 WHEN 'Middle Standard' THEN 2 ELSE 3 END",identity).fetchall()
        field3_current_records=[]
        for standard,evidence_json in standard_rows:
            try:
                record=json.loads(evidence_json); record={"Standard":standard, **(record if isinstance(record,dict) else {})}; field3_current_records.append(record)
            except Exception: pass
        history3_rows = conn.execute(f"SELECT standard,evidence_json FROM field3_history_evidence WHERE {q} ORDER BY standard,row_number",identity).fetchall()
        field3_history_records=[]
        for standard,evidence_json in history3_rows:
            try:
                record=json.loads(evidence_json); record={"Standard":standard, **(record if isinstance(record,dict) else {})}; field3_history_records.append(record)
            except Exception: pass
        diag_rows = conn.execute("SELECT status,detail_json,created_at FROM publication_diagnostics WHERE parent_run_id=? AND child_run_id=? AND symbol=? ORDER BY diagnostic_id DESC LIMIT 50",(meta["parent_run_id"],meta["child_run_id"],meta["symbol"])).fetchall()
        diagnostics=[]
        for status,detail,created in diag_rows:
            try: parsed=json.loads(detail)
            except Exception: parsed={"detail":detail}
            diagnostics.append({"Status":status,"Created At":created,"Detail":json.dumps(parsed,sort_keys=True,default=str)})
    return {
        "ok": True,"status": meta["publication_status"],"metadata":meta,
        "table4_current":_decode_evidence_rows(current_rows,0),
        "table4_history":_decode_evidence_rows(history_rows,0),
        "field3_current":pd.DataFrame(field3_current_records),
        "field3_history":pd.DataFrame(field3_history_records),
        "diagnostics":pd.DataFrame(diagnostics),
    }


def load_latest_child_contract_tables(
    *, path: Path | str, symbol: str, timeframe: str = "H1",
) -> dict[str, Any]:
    """Load the newest completed exact-symbol child across all parent runs.

    The three Settings buttons intentionally create independent parent runs.
    Field 10 is cumulative, so a later group must still recover the verified
    Higher-Standard evidence published by an earlier group.
    """
    symbol = normalize_symbol(symbol)
    timeframe = str(timeframe or "H1").upper()
    try:
        with connect_readonly(path) as conn:
            row = conn.execute(
                """SELECT parent_run_id,child_run_id
                   FROM child_generation_registry
                   WHERE symbol=? AND timeframe=?
                     AND UPPER(COALESCE(publication_status,'')) IN
                         ('COMPLETED','INSERTED','ALREADY_EXISTS_VALID','REPAIRED_FROM_VALID_SNAPSHOT')
                   ORDER BY completed_broker_candle DESC,updated_at DESC
                   LIMIT 1""",
                (symbol, timeframe),
            ).fetchone()
    except Exception as exc:
        return {
            "ok": False, "status": "LATEST_CHILD_LOOKUP_FAILED", "symbol": symbol,
            "timeframe": timeframe, "error": f"{type(exc).__name__}: {exc}",
            "table4_current": pd.DataFrame(), "table4_history": pd.DataFrame(),
            "field3_current": pd.DataFrame(), "field3_history": pd.DataFrame(),
            "diagnostics": pd.DataFrame(),
        }
    if not row:
        return {
            "ok": False, "status": "NO_COMPLETED_CHILD_GENERATION", "symbol": symbol,
            "timeframe": timeframe, "table4_current": pd.DataFrame(),
            "table4_history": pd.DataFrame(), "field3_current": pd.DataFrame(),
            "field3_history": pd.DataFrame(), "diagnostics": pd.DataFrame(),
        }
    result = load_child_contract_tables(
        path=path, parent_run_id=str(row[0]), child_run_id=str(row[1]),
        symbol=symbol, timeframe=timeframe,
    )
    result["lookup_scope"] = "LATEST_COMPLETED_EXACT_SYMBOL_ACROSS_PARENT_RUNS"
    return result


def self_heal_field10_from_snapshot(
    *, path: Path | str, parent_run_id: str, symbol: str, timeframe: str = "H1",
    completed_broker_candle: str | None = None,
) -> dict[str, Any]:
    """Republish genuine saved artifacts only; never contacts APIs or recalculates."""
    migrate_child_publication_contract(path)
    symbol = normalize_symbol(symbol)
    clauses=["parent_run_id=?","symbol=?","timeframe=?"]
    params: list[Any]=[parent_run_id,symbol,str(timeframe).upper()]
    if completed_broker_candle:
        stamp=pd.to_datetime(completed_broker_candle,errors="coerce",utc=True)
        if not pd.isna(stamp):
            clauses.append("completed_broker_candle=?"); params.append(pd.Timestamp(stamp).floor("h").isoformat())
    with _connect(path) as conn:
        row=conn.execute(
            "SELECT parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,source_id,snapshot_hash,completed_broker_candle,valid_until,runtime_snapshot_path,runtime_snapshot_sha256,calculation_status FROM child_generation_registry WHERE "+" AND ".join(clauses)+" ORDER BY completed_broker_candle DESC,updated_at DESC LIMIT 1",params
        ).fetchone()
    if not row:
        return {"ok":False,"status":"NO_CHILD_GENERATION","selected_symbol":symbol,"parent_run_id":parent_run_id,"missing_artifact":"child generation registry"}
    names=["parent_run_id","child_run_id","symbol","timeframe","canonical_run_id","source_id","snapshot_hash","completed_broker_candle","valid_until","runtime_snapshot_path","runtime_snapshot_sha256","calculation_status"]
    meta=dict(zip(names,row)); snapshot=Path(meta["runtime_snapshot_path"])
    if not snapshot.is_file():
        return {"ok":False,"status":"SNAPSHOT_CONFLICT",**meta,"missing_artifact":"runtime snapshot file"}
    actual=file_sha256(snapshot)
    if actual != meta["runtime_snapshot_sha256"]:
        return {"ok":False,"status":"SNAPSHOT_CONFLICT",**meta,"missing_artifact":"runtime snapshot checksum","expected":meta["runtime_snapshot_sha256"],"actual":actual}
    try:
        import gzip
        from core.serialization_compat_20260702 import loads as serializer_loads
        payload=serializer_loads(gzip.decompress(snapshot.read_bytes()))
        cached_state=dict(_mapping(payload).get("state") or {})
        canonical={}
        for key in ("canonical_decision_result_20260617","canonical_result_20260617","last_valid_canonical_decision_result_20260617"):
            if isinstance(cached_state.get(key),Mapping): canonical=dict(cached_state[key]); break
        if not canonical:
            return {"ok":False,"status":"SNAPSHOT_CONFLICT",**meta,"missing_artifact":"canonical object in runtime snapshot"}
        context=SymbolContext(
            settings_main_symbol=normalize_symbol(cached_state.get("multi_symbol_main_symbol_20260702") or symbol),
            connector_symbol=normalize_symbol(cached_state.get("connector_symbol_20260702") or cached_state.get("multi_symbol_main_symbol_20260702") or symbol),
            calculation_symbol=symbol,lunch_display_symbol=symbol,active_snapshot_symbol=symbol,
            selected_symbols=tuple(cached_state.get("multi_symbol_selected_20260701") or [symbol]),
            timeframe=meta["timeframe"],parent_run_id=meta["parent_run_id"],child_run_id=meta["child_run_id"],
            canonical_run_id=meta["canonical_run_id"],source_id=meta["source_id"],snapshot_hash=meta["snapshot_hash"],
            completed_broker_candle=meta["completed_broker_candle"],generation_status=meta["calculation_status"],valid_until=meta["valid_until"],
        )
        bundle=build_child_generation_bundle(state=cached_state,canonical=canonical,context=context,runtime_snapshot_path=snapshot,calculation_status=meta["calculation_status"])
        return publish_child_generation_to_field10(bundle,path=path,repair=True)
    except Exception as exc:
        return {"ok":False,"status":"SNAPSHOT_CONFLICT",**meta,"publication_exception":f"{type(exc).__name__}: {exc}"}


__all__.extend(["load_child_contract_tables", "self_heal_field10_from_snapshot"])


def list_valid_child_generations(*, path: Path | str, parent_run_id: str | None = None) -> list[dict[str, Any]]:
    migrate_child_publication_contract(path)
    clauses=["publication_status IN ('COMPLETED','ALREADY_EXISTS_VALID','REPAIRED_FROM_VALID_SNAPSHOT')"]
    params=[]
    if parent_run_id:
        clauses.append("parent_run_id=?"); params.append(parent_run_id)
    with _connect(path) as conn:
        rows=conn.execute(
            "SELECT parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,source_id,snapshot_hash,completed_broker_candle,valid_until,publication_status,runtime_snapshot_path FROM child_generation_registry WHERE "+" AND ".join(clauses)+" ORDER BY updated_at DESC",params
        ).fetchall()
    names=["parent_run_id","child_run_id","symbol","timeframe","canonical_run_id","source_id","snapshot_hash","completed_broker_candle","valid_until","publication_status","runtime_snapshot_path"]
    seen=set(); result=[]
    for row in rows:
        item=dict(zip(names,row)); key=(item["symbol"],item["timeframe"])
        if key in seen: continue
        seen.add(key); result.append(item)
    return result


__all__.append("list_valid_child_generations")
