"""Authoritative Field 10 daily locked rank authority layer.

Additive repair: reads existing Field 10 rows, adds research-background evidence,
and publishes one trusted table. Legacy tables remain supporting evidence only.
"""
from __future__ import annotations
from collections.abc import Mapping, MutableMapping, Sequence
from datetime import datetime, timezone, timedelta
from io import BytesIO
from typing import Any
import json, os, sqlite3, zipfile
import pandas as pd
from core.system_contract import RunSnapshot, Field10ViewModel, DinnerViewModel, VisualizationViewModel, ExportManifest, PublicationStatus, ordered_unique, stable_hash
from core.background_function_registry import compute_background_frame, function_status_frame
from core.field10_rank_governance_20260709 import governance_for_symbol, sort_key_for_authority
from core.reliable_quant_contract_20260717 import (
    build_authority_identity,
    canonical_completed_candle,
    canonical_utc_iso,
    expected_net_value,
    normalize_symbol as normalize_contract_symbol,
    normalize_timeframe,
    settled_target_probability,
    stable_contract_hash,
)

UNIFIED_TABLE_KEY = "field10_unified_daily_locked_rank_20260709"
UNIFIED_SNAPSHOT_KEY = "field10_unified_snapshot_20260709"
SESSION_TABLE_KEY = "field10_eight_session_entry_map_20260709"
NEWS_TABLE_KEY = "field10_news_event_absorption_rank_20260709"
BACKGROUND_TABLE_KEY = "field10_research_background_evidence_20260709"
DINNER_TABLE_KEY = "dinner_research_background_evidence_20260709"
VIZ_TABLE_KEY = "data_visualization_view_materialized_20260709"
SUPPORTING_TABLE_KEY = "field10_supporting_evidence_entry_timing_rank_20260709"
MERGED_TABLE_KEY = "field10_merged_authority_supporting_entry_rank_20260709"
EXPORT_MANIFEST_KEY = "field10_export_manifest_20260709"
SYNC_STATUS_KEY = "field10_dinner_visualization_sync_20260709"
AUTHORITY_IDENTITY_KEY = "field10_authority_identity_20260717"
PARITY_STATUS_KEY = "field10_cross_device_parity_status_20260717"
REQUIRED_TRUST_FIELDS = (
    "daily_snapshot_id", "parent_run_id", "generation_id", "broker_day", "timeframe", "completed_broker_candle",
    "ordered_symbol_universe", "loaded_symbol_count", "failed_symbol_count", "universe_hash", "snapshot_hash",
    "authority_key", "canonical_symbol", "provider_symbol", "broker_timezone_policy", "source_id",
    "source_snapshot_hash", "data_revision", "feature_schema_hash", "cross_device_parity_status", "publication_mode",
    "symbol", "rank", "stable_daily_bias", "less_risky_bias", "entry_permission", "data_quality_grade",
    "sample_count", "provider_used", "evidence_source", "publication_status",
)
SESSION_NAMES = ("Sydney Open/Core","Sydney-Tokyo Overlap","Tokyo Core","Asia-London Transition","London Core","London-New York Overlap","New York Core","New York Late/Rollover Risk")

TIMEFRAME_MINUTES = {
    "M1": 1, "M5": 5, "M10": 10, "M15": 15, "M30": 30,
    "H1": 60, "H2": 120, "H3": 180, "H4": 240, "H6": 360,
    "H8": 480, "H12": 720, "D1": 1440,
}

TRANSITION_RISK_WINDOWS = ("1H", "3H", "6H", "12H", "24H", "36H")
EXPECTED_RETURN_WINDOWS = ("1H", "3H", "4H", "6H", "12H", "24H", "36H")
PROBABILITY_WINDOWS = ("1H", "3H", "4H", "6H", "12H")


def _timeframe_minutes(timeframe: str) -> int:
    text = normalize_timeframe(timeframe)
    return int(TIMEFRAME_MINUTES.get(text, 240 if text == "H4" else 60))


def _normalize_completed_candle_for_timeframe(completed: Any, timeframe: str) -> str:
    """Lock the publication watermark to the selected timeframe boundary.

    If the UI/calculation cache contains an H1 watermark while the user selected
    H4, Field 10 must not refresh every hour.  The display authority floors the
    watermark to the selected timeframe boundary, so H4 stays on the same
    completed H4 candle until the next H4 boundary is available.
    """
    text = str(completed or "").strip()
    if not text or text.upper() in {"UNAVAILABLE", "NONE", "NAN", "<NA>"}:
        return "UNAVAILABLE"
    try:
        ts = pd.to_datetime(text, errors="coerce", utc=True)
        if pd.isna(ts):
            return text
        minutes = _timeframe_minutes(timeframe)
        floored = ts.floor(f"{minutes}min") if minutes < 1440 else ts.floor("D")
        return canonical_completed_candle(floored.isoformat(), timeframe)
    except Exception:
        return text


def _next_refresh_after_candle(completed: Any, timeframe: str) -> str:
    text = str(completed or "").strip()
    if not text or text.upper() in {"UNAVAILABLE", "NONE", "NAN", "<NA>"}:
        return "UNAVAILABLE"
    try:
        ts = pd.to_datetime(text, errors="coerce")
        if pd.isna(ts):
            return "UNAVAILABLE"
        return (ts + timedelta(minutes=_timeframe_minutes(timeframe))).isoformat()
    except Exception:
        return "UNAVAILABLE"


def _refresh_gate_label(timeframe: str) -> str:
    text = normalize_timeframe(timeframe)
    return f"REFRESH_ONLY_AFTER_{text}_CANDLE_END"


def _snapshot_symbol_list(snapshot: Mapping[str, Any]) -> list[str]:
    raw = snapshot.get("ordered_symbol_universe")
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, list):
                return ordered_unique(decoded, limit=12)
        except Exception:
            pass
        return ordered_unique(raw.replace("→", ",").split(","), limit=12)
    return ordered_unique(raw or [], limit=12)


def _candle_identity(value: Any, timeframe: str) -> str:
    """Return a timezone-normalized completed-candle identity for comparisons.

    Providers and the warm cache use a mixture of ``Z``, ``+00:00`` and naive
    ISO strings.  Comparing those raw strings made a valid persisted H4 row
    look different after reconnect.  The authority layer compares UTC values
    after applying the selected-timeframe floor instead.
    """
    normalized = _normalize_completed_candle_for_timeframe(value, timeframe)
    try:
        stamp = pd.to_datetime(normalized, errors="coerce", utc=True)
        return "UNAVAILABLE" if pd.isna(stamp) else pd.Timestamp(stamp).isoformat()
    except Exception:
        return str(normalized or "UNAVAILABLE")


def _authority_db_path() -> Any:
    """Resolve the durable authority database without changing the default.

    The environment override makes the read/write path testable and supports a
    mounted durable volume in deployment.  Desktop users continue to use the
    packaged Field 10 database.
    """
    try:
        from core.field10_research_migration_20260709 import DEFAULT_DB_PATH
        override = str(os.environ.get("ADX_FIELD10_AUTHORITY_DB_PATH") or "").strip()
        return override or DEFAULT_DB_PATH
    except Exception:
        return "data/multi_symbol_field10_20260701.sqlite3"


def _cross_device_parity_status() -> str:
    """Report whether the configured authority is plausibly shared.

    A local SQLite path is durable for one process or machine, but it cannot
    prove phone/laptop parity.  The status is intentionally explicit instead
    of presenting local persistence as a distributed authority.
    """
    shared = str(os.environ.get("ADX_SHARED_AUTHORITY_URI") or os.environ.get("ADX_FIELD10_SHARED_AUTHORITY_URI") or "").strip()
    if shared:
        return "SHARED_AUTHORITY_CONFIGURED"
    return "CROSS_DEVICE_PARITY_UNVERIFIED"


def _json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        decoded = json.loads(str(value or "{}"))
        return dict(decoded) if isinstance(decoded, Mapping) else {}
    except Exception:
        return {}


def _json_row_frame(rows: Sequence[Any]) -> pd.DataFrame:
    decoded: list[dict[str, Any]] = []
    for value in rows:
        row = _json_mapping(value)
        if row:
            decoded.append(row)
    return pd.DataFrame(decoded) if decoded else pd.DataFrame()


def _load_persisted_authority(
    state: MutableMapping[str, Any], *, symbols: Sequence[str], timeframe: str, completed: str,
    ensure_schema: bool = True,
) -> dict[str, Any] | None:
    """Load the exact published authority before any fresh ranking work.

    A browser reconnect is allowed to lose Session State, but it must not lose
    the immutable Field 10 result.  This loader accepts a row only when all of
    the publication identity matches: timeframe, completed candle and ordered
    selected-symbol universe.  It deliberately refuses a nearest/older row.
    """
    expected_symbols = list(symbols)
    expected_tf = normalize_timeframe(timeframe)
    expected_candle = _candle_identity(completed, expected_tf)
    if not expected_symbols or expected_candle == "UNAVAILABLE":
        return None
    try:
        db_path = _authority_db_path()
        if ensure_schema:
            from core.field10_research_migration_20260709 import migrate_field10_research_authority
            if not migrate_field10_research_authority(db_path).get("ok"):
                return None
        if not ensure_schema:
            if not os.path.exists(str(db_path)):
                return None
            conn = sqlite3.connect(f"file:{os.path.abspath(str(db_path))}?mode=ro", uri=True, timeout=8.0)
        else:
            conn = sqlite3.connect(str(db_path), timeout=8.0)
        conn.row_factory = sqlite3.Row
    except Exception as exc:
        state["field10_durable_restore_error_20260717"] = f"{type(exc).__name__}: {exc}"
        return None

    try:
        candidates = conn.execute(
            "SELECT * FROM field10_unified_rank_snapshot "
            "WHERE timeframe=? AND publication_status IN ('COMPLETE','PARTIAL_READY','RESEARCH_ONLY','INSUFFICIENT_DATA') "
            "ORDER BY created_at_broker_time DESC, daily_snapshot_id DESC",
            (expected_tf,),
        ).fetchall()
        selected: sqlite3.Row | None = None
        selected_symbols: list[str] = []
        symbol_rows: list[sqlite3.Row] = []
        for candidate in candidates:
            candidate_mapping = dict(candidate)
            candidate_symbols = _snapshot_symbol_list(candidate_mapping)
            if candidate_symbols != expected_symbols:
                continue
            if _candle_identity(candidate["completed_broker_candle"], expected_tf) != expected_candle:
                continue
            rows = conn.execute(
                "SELECT * FROM field10_unified_rank_symbol "
                "WHERE daily_snapshot_id=? ORDER BY rank ASC, symbol ASC",
                (candidate["daily_snapshot_id"],),
            ).fetchall()
            row_symbols = [_norm_symbol(row["symbol"]) for row in rows]
            # An exact authority row must cover the whole selected universe;
            # silently loading a partial subset is the same class of bug as
            # showing a stale secondary-symbol ranking.  Persisted rows are
            # ordered by final rank, so their row order is intentionally not
            # required to match the user's selected-symbol order; that order
            # is already frozen in the parent snapshot identity.
            if (
                len(rows) != len(expected_symbols)
                or len(set(row_symbols)) != len(row_symbols)
                or set(row_symbols) != set(expected_symbols)
            ):
                continue
            selected = candidate
            selected_symbols = candidate_symbols
            symbol_rows = rows
            break
        if selected is None:
            return None

        snapshot = dict(selected)
        if str(snapshot.get("cross_device_parity_status") or "").strip() == "":
            snapshot["cross_device_parity_status"] = _cross_device_parity_status()
        snapshot["ordered_symbol_universe"] = selected_symbols
        snapshot["why_trust"] = _json_mapping(selected["why_trust_json"])
        snapshot["why_trust"].update({
            "refresh gate": _refresh_gate_label(expected_tf),
            "next allowed refresh": _next_refresh_after_candle(completed, expected_tf),
            "reuse reason": "Exact durable Field 10 authority snapshot restored; no reconnect-time recomputation was allowed.",
            "restore source": "field10_unified_rank_snapshot SQLite authority store",
        })
        table = _json_row_frame([row["row_json"] for row in symbol_rows])
        if table.empty or "Symbol" not in table.columns:
            return None
        table["Symbol"] = table["Symbol"].map(_norm_symbol)
        table = table[table["Symbol"].isin(expected_symbols)].copy()
        table = table.sort_values(
            by=[c for c in ("Rank", "Symbol") if c in table.columns],
            kind="mergesort",
        ).reset_index(drop=True)
        table_symbols = ordered_unique(table["Symbol"].tolist(), limit=12)
        if (
            len(table_symbols) != len(expected_symbols)
            or len(set(table_symbols)) != len(table_symbols)
            or set(table_symbols) != set(expected_symbols)
        ):
            return None

        child_frames: dict[str, pd.DataFrame] = {}
        for key, table_name in (
            (SESSION_TABLE_KEY, "field10_daily_session_rank"),
            (NEWS_TABLE_KEY, "field10_daily_news_event_rank"),
            (BACKGROUND_TABLE_KEY, "field10_research_background_evidence"),
            (DINNER_TABLE_KEY, "dinner_research_background_evidence"),
            (VIZ_TABLE_KEY, "visualization_view_materialized"),
        ):
            rows = conn.execute(
                f"SELECT row_json FROM {table_name} WHERE daily_snapshot_id=? ORDER BY id ASC",
                (selected["daily_snapshot_id"],),
            ).fetchall()
            child_frames[key] = _json_row_frame([row["row_json"] for row in rows])

        # Rebuild only the two display compositions from persisted rows.  This
        # is presentation assembly, not a calculation or API call.
        snap_model = RunSnapshot(
            parent_run_id=str(snapshot.get("parent_run_id") or ""),
            generation_id=str(snapshot.get("generation_id") or ""),
            daily_snapshot_id=str(snapshot.get("daily_snapshot_id") or ""),
            broker_day=str(snapshot.get("broker_day") or _broker_day(completed)),
            broker_time=str(snapshot.get("completed_broker_candle") or completed),
            timeframe=expected_tf,
            completed_broker_candle=str(snapshot.get("completed_broker_candle") or completed),
            ordered_symbol_universe=selected_symbols,
            loaded_symbol_count=int(snapshot.get("loaded_symbol_count") or len(expected_symbols)),
            failed_symbol_count=int(snapshot.get("failed_symbol_count") or 0),
            provider_summary=str(snapshot.get("provider_summary") or "persisted Field 10 authority"),
            data_quality_summary=str(snapshot.get("publication_status") or "PARTIAL_READY"),
            input_hash=str(snapshot.get("input_hash") or ""),
            output_hash=str(snapshot.get("output_hash") or ""),
            snapshot_hash=str(snapshot.get("snapshot_hash") or ""),
            publication_status=str(snapshot.get("publication_status") or "PARTIAL_READY"),
            created_at_broker_time=str(snapshot.get("created_at_broker_time") or ""),
            model_version=str(snapshot.get("model_version") or "field10_research_authority_20260709"),
            formula_version=str(snapshot.get("formula_version") or "non_destructive_v1"),
        )
        session = child_frames.get(SESSION_TABLE_KEY, pd.DataFrame())
        news = child_frames.get(NEWS_TABLE_KEY, pd.DataFrame())
        supporting = build_supporting_evidence_entry_timing_table(table, session, news, snap_model)
        merged = build_merged_authority_supporting_table(table, supporting, snap_model)
        export = build_export_manifest(snap_model)
        why = dict(snapshot["why_trust"])
        state[UNIFIED_TABLE_KEY] = table
        state[UNIFIED_SNAPSHOT_KEY] = snapshot
        state[AUTHORITY_IDENTITY_KEY] = _json_mapping(snapshot.get("authority_identity_json"))
        state[PARITY_STATUS_KEY] = snapshot.get("cross_device_parity_status") or _cross_device_parity_status()
        state[SESSION_TABLE_KEY] = session
        state[NEWS_TABLE_KEY] = news
        state[BACKGROUND_TABLE_KEY] = child_frames.get(BACKGROUND_TABLE_KEY, pd.DataFrame())
        state[DINNER_TABLE_KEY] = child_frames.get(DINNER_TABLE_KEY, pd.DataFrame())
        state[VIZ_TABLE_KEY] = child_frames.get(VIZ_TABLE_KEY, pd.DataFrame())
        state[SUPPORTING_TABLE_KEY] = supporting
        state[MERGED_TABLE_KEY] = merged
        state[EXPORT_MANIFEST_KEY] = export
        state["field10_authority_view_model_20260709"] = Field10ViewModel(
            snapshot_hash=snap_model.snapshot_hash,
            rows=merged.to_dict(orient="records"),
            supporting_rows=supporting.to_dict(orient="records"),
            publication_status=snap_model.publication_status,
            trusted_reason=str(why.get("authority rule") or "Exact durable authority identity restored."),
        )
        state["dinner_view_model_20260709"] = DinnerViewModel(
            snapshot_hash=snap_model.snapshot_hash,
            rows=state[DINNER_TABLE_KEY].to_dict(orient="records"),
            publication_status=snap_model.publication_status,
        )
        state["visualization_view_model_20260709"] = VisualizationViewModel(
            snapshot_hash=snap_model.snapshot_hash,
            rank_rows=state[VIZ_TABLE_KEY].to_dict(orient="records"),
            risk_rows=state[VIZ_TABLE_KEY].to_dict(orient="records"),
            session_rows=session.to_dict(orient="records"),
            publication_status=snap_model.publication_status,
        )
        state["field10_durable_restore_status_20260717"] = {
            "status": "RESTORED_EXACT_AUTHORITY",
            "daily_snapshot_id": snap_model.daily_snapshot_id,
            "timeframe": expected_tf,
            "completed_broker_candle": snap_model.completed_broker_candle,
            "symbols": selected_symbols,
        }
        return {
            "snapshot": snapshot,
            "why_trust": why,
            "table": table,
            "merged": merged,
            "background": state[BACKGROUND_TABLE_KEY],
            "session": session,
            "news": news,
            "supporting": supporting,
            "dinner": state[DINNER_TABLE_KEY],
            "visualization": state[VIZ_TABLE_KEY],
            "export_manifest": export,
            "reused_same_candle": True,
            "reused_from": "DURABLE_FIELD10_AUTHORITY_SQLITE",
        }
    except Exception as exc:
        state["field10_durable_restore_error_20260717"] = f"{type(exc).__name__}: {exc}"
        return None
    finally:
        conn.close()


def load_saved_field10_authority(state: MutableMapping[str, Any] | None = None) -> dict[str, Any] | None:
    """Read the exact Field 10 publication without migration, fetching or calculation.

    This is the only entry point used by Lunch Field 10/12 display adapters.
    Settings/background materialization calls ``build_unified_field10_authority``;
    opening a display surface can only restore an exact saved identity.
    """
    state = state if state is not None else {}
    symbols, timeframe = _symbols(state), _tf(state)
    completed = _normalize_completed_candle_for_timeframe(_completed(state, pd.DataFrame()), timeframe)
    if not symbols or completed == "UNAVAILABLE":
        return None
    cached = _reuse_same_candle_authority(state, symbols=symbols, timeframe=timeframe, completed=completed)
    if cached is not None:
        cached["reused_from"] = "IN_MEMORY_FIELD10_AUTHORITY"
        return cached
    return _load_persisted_authority(state, symbols=symbols, timeframe=timeframe, completed=completed, ensure_schema=False)


def _reuse_same_candle_authority(state: Mapping[str, Any], *, symbols: Sequence[str], timeframe: str, completed: str) -> dict[str, Any] | None:
    """Return the already-published Field 10 authority while the candle is unchanged.

    This is the practical fix for the user's H4 concern: when H4 is selected,
    opening Lunch or receiving fresh H1/sub-candle cache noise cannot alter the
    trusted Field 10 table.  The trusted table can change only when the selected
    timeframe completed-candle watermark changes or the selected symbol universe
    changes.
    """
    snapshot = state.get(UNIFIED_SNAPSHOT_KEY)
    table = state.get(UNIFIED_TABLE_KEY)
    if not isinstance(snapshot, Mapping) or not isinstance(table, pd.DataFrame) or table.empty:
        return None
    if normalize_timeframe(snapshot.get("timeframe")) != normalize_timeframe(timeframe):
        return None
    if _candle_identity(snapshot.get("completed_broker_candle"), timeframe) != _candle_identity(completed, timeframe):
        return None
    cached_symbols = _snapshot_symbol_list(snapshot)
    if cached_symbols != list(symbols):
        return None
    why = dict(snapshot.get("why_trust") or {})
    why["refresh gate"] = _refresh_gate_label(timeframe)
    why["next allowed refresh"] = _next_refresh_after_candle(completed, timeframe)
    why["reuse reason"] = "Selected timeframe candle is unchanged; Field 10 authority table was reused instead of recomputed."
    state[PARITY_STATUS_KEY] = snapshot.get("cross_device_parity_status") or _cross_device_parity_status()
    return {
        "snapshot": dict(snapshot),
        "why_trust": why,
        "table": table,
        "background": state.get(BACKGROUND_TABLE_KEY) if isinstance(state.get(BACKGROUND_TABLE_KEY), pd.DataFrame) else pd.DataFrame(),
        "session": state.get(SESSION_TABLE_KEY) if isinstance(state.get(SESSION_TABLE_KEY), pd.DataFrame) else pd.DataFrame(),
        "news": state.get(NEWS_TABLE_KEY) if isinstance(state.get(NEWS_TABLE_KEY), pd.DataFrame) else pd.DataFrame(),
        "supporting": state.get(SUPPORTING_TABLE_KEY) if isinstance(state.get(SUPPORTING_TABLE_KEY), pd.DataFrame) else pd.DataFrame(),
        "dinner": state.get(DINNER_TABLE_KEY) if isinstance(state.get(DINNER_TABLE_KEY), pd.DataFrame) else pd.DataFrame(),
        "visualization": state.get(VIZ_TABLE_KEY) if isinstance(state.get(VIZ_TABLE_KEY), pd.DataFrame) else pd.DataFrame(),
        "export_manifest": state.get(EXPORT_MANIFEST_KEY) if isinstance(state.get(EXPORT_MANIFEST_KEY), Mapping) else {},
        "reused_same_candle": True,
    }

def _norm_symbol(v: Any) -> str:
    return normalize_contract_symbol(v)

def _tf(state: Mapping[str, Any]) -> str:
    for k in ("canonical_ranking_timeframe","selected_timeframe","settings_timeframe","timeframe","last_connected_timeframe"):
        t = str(state.get(k) or "").strip().upper()
        if t and t.lower() not in {"nan","none","not available"}:
            return normalize_timeframe(t)
    return "H4"

def _symbols(state: Mapping[str, Any]) -> list[str]:
    vals: list[Any] = []
    for k in ("adx_current_selected_symbols_20260708","canonical_ranking_symbols","canonical_selected_symbols","multi_symbol_configured_union_20260706","multi_symbol_selected_20260701","multi_symbol_first_selected_20260706","multi_symbol_second_selected_20260706","multi_symbol_third_selected_20260706"):
        v = state.get(k)
        if isinstance(v, str): vals.append(v)
        elif isinstance(v, Sequence): vals.extend(list(v))
    return ordered_unique(vals or [state.get("symbol") or "EURUSD"], limit=12)

def _val(row: Mapping[str, Any], *cols: str, default: Any="UNAVAILABLE") -> Any:
    for c in cols:
        if c in row:
            v = row.get(c)
            if v is not None and str(v).strip() and str(v).lower() not in {"nan","none","<na>"}:
                return v
    return default

def _num(v: Any, default: float=0.0) -> float:
    try:
        n = float(v)
        return default if pd.isna(n) else n
    except Exception:
        return default

def _bias(row: Mapping[str, Any]) -> str:
    """Return BUY/SELL only for the Field 10 authority direction.

    WAIT is removed from the final rank/bias surface.  Risk is shown through
    Entry Permission, Risk Control Gate, Trust Status and transition-risk columns
    instead of becoming a third bias option.
    """
    for c in (
        "Higher-Standard Regime Bias", "Higher Standard Regime Bias",
        "Field 3 Higher-Standard Bias", "Field 3 Higher Bias",
        "Stable Daily Bias", "Less-Risky Bias", "Final Less-Risky Bias",
        "Final Less-Risky Bias to Hold", "Decision", "Flow Proxy Bias",
    ):
        t = str(row.get(c) or "").upper()
        if "BUY" in t:
            return "BUY"
        if "SELL" in t:
            return "SELL"
    for c in ("Expected Return 4H", "Expected Return 3H", "Expected Return 6H", "Expected Return 12H", "Net Expected Value", "WeightedNetEV"):
        v = row.get(c)
        try:
            n = float(str(v).replace("%", "").replace(",", ""))
            if pd.notna(n):
                if n > 0:
                    return "BUY"
                if n < 0:
                    return "SELL"
        except Exception:
            pass
    try:
        p = float(str(_val(row, "Regime Probability", "Calibrated Probability", "Reliability", "Probability Profit 6H", default=50)).replace("%", ""))
        return "BUY" if p >= 50 else "SELL"
    except Exception:
        pass
    # A missing direction is evidence failure, not a license to create a
    # deterministic-looking BUY/SELL value from the symbol name or row index.
    return "UNAVAILABLE"


def _no_wait_text(value: Any, *, fallback: str = "CAUTION") -> str:
    text = str(value or "").strip()
    up = text.upper()
    if not text or up in {"WAIT", "WAIT / LOWER_PRIORITY", "NO_TRADE_WAIT", "NEUTRAL"}:
        return fallback
    return text.replace("WAIT", fallback)


def _source(state: Mapping[str, Any], symbols: Sequence[str]) -> pd.DataFrame:
    candidates = [state.get("field10_institutional_ranking_20260708"), state.get("field10_consolidated_table_20260707")]
    cr = state.get("adx_current_canonical_result_20260708")
    if isinstance(cr, Mapping): candidates.append(cr.get("field10"))
    for frame in candidates:
        if isinstance(frame, pd.DataFrame) and not frame.empty and "Symbol" in frame.columns:
            out = frame.copy(); out["Symbol"] = out["Symbol"].map(_norm_symbol)
            out = out[out["Symbol"].isin(symbols)].drop_duplicates("Symbol", keep="first")
            if not out.empty: return out.reset_index(drop=True)
    return pd.DataFrame({"Symbol": list(symbols)})

def _completed(state: Mapping[str, Any], frame: pd.DataFrame) -> str:
    """Return a single completed-candle watermark for the authority snapshot.

    Prefer explicit broker/selected-timeframe state values.  If only row-level
    candle times exist, use the latest valid row time and let the timeframe
    normalizer floor it to H4/D1/etc.  This avoids the old first-row problem
    where one stale symbol could freeze the whole ranking to an older candle.
    """
    for k in (
        "completed_broker_candle",
        "latest_completed_candle_for_run_20260705",
        "shared_broker_candle_time_20260622",
        "latest_completed_higher_timeframe_candle_20260709",
    ):
        if state.get(k):
            return str(state.get(k))
    candidates: list[pd.Timestamp] = []
    for c in ("Completed Broker Candle", "Time", "Latest Candle", "Latest Candle Time", "Broker Timestamp", "Broker Candle Time"):
        if c in frame.columns and frame[c].notna().any():
            parsed = pd.to_datetime(frame[c].dropna(), errors="coerce", utc=True)
            parsed = parsed.dropna()
            if not parsed.empty:
                candidates.extend(list(parsed))
    if candidates:
        return max(candidates).isoformat()
    return "UNAVAILABLE"

def _broker_day(completed: str) -> str:
    dt = pd.to_datetime(pd.Series([completed]), errors="coerce", utc=True).iloc[0]
    return str(dt.date()) if pd.notna(dt) else datetime.now(timezone.utc).date().isoformat()

def _rank(row: Mapping[str, Any], fallback: int) -> int:
    for c in ("Rank","Final Rank","Daily Rank","Session Rank","Technical/Fundamental Rank"):
        n = pd.to_numeric(pd.Series([row.get(c)]), errors="coerce").iloc[0] if c in row else pd.NA
        if pd.notna(n): return int(n)
    return fallback

def _pick_window_value(bg: Mapping[str, Any], src: Mapping[str, Any], family: str, window: str, default: Any = "UNAVAILABLE") -> Any:
    """Exact-row lookup for horizon columns.

    Super Quick must publish every visible transition/probability/expected-return
    horizon without requiring a second Quick/Full pass.  This helper reads the
    background value first and then exact-symbol source aliases only; it never
    borrows from another symbol.
    """
    compact = f"{family} {window}"
    percent = f"{compact} (%)"
    for key in (compact, percent, f"{family.replace(' ', '-')} {window}"):
        if key in bg and str(bg.get(key)).strip() and str(bg.get(key)).lower() not in {"nan", "none", "<na>"}:
            return bg.get(key)
    return _val(src, compact, percent, f"Field 3 Higher • {compact}", f"Latest Run • {compact}", f"Integrated • {compact}", f"Field 3 Higher • {percent}", f"Latest Run • {percent}", f"Integrated • {percent}", default=default)


def _window_columns(bg: Mapping[str, Any], src: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for window in TRANSITION_RISK_WINDOWS:
        out[f"Transition Risk {window}"] = _pick_window_value(bg, src, "Transition Risk", window)
    for window in EXPECTED_RETURN_WINDOWS:
        out[f"Expected Return {window}"] = _pick_window_value(bg, src, "Expected Return", window)
    for window in PROBABILITY_WINDOWS:
        out[f"Probability Profit {window}"] = _pick_window_value(bg, src, "Probability Profit", window)
        out[f"Probability Reach EV {window}"] = _pick_window_value(bg, src, "Probability Profit", window)
    return out


def _authority_identity_for(
    state: Mapping[str, Any], source: pd.DataFrame, symbols: Sequence[str], timeframe: str, completed: str,
):
    """Build the full immutable identity used by persistence and parity checks."""
    records = source.to_dict(orient="records") if isinstance(source, pd.DataFrame) else []
    provider_values = sorted({str(row.get("Provider Used") or row.get("Provider") or "UNAVAILABLE") for row in records})
    provider = ",".join(provider_values) if provider_values else "UNAVAILABLE"
    source_id = state.get("source_id") or state.get("field10_source_id") or state.get("source_snapshot_id")
    if not source_id:
        source_id = next((row.get("Source ID") or row.get("source_id") for row in records if row.get("Source ID") or row.get("source_id")), None)
    data_revision = state.get("data_revision") or state.get("market_data_revision")
    if not data_revision:
        data_revision = next((row.get("Data Revision") or row.get("data_revision") for row in records if row.get("Data Revision") or row.get("data_revision")), None)
    source_hash = state.get("source_snapshot_hash") or state.get("field10_source_snapshot_hash") or stable_contract_hash(records)
    feature_schema_hash = state.get("feature_schema_hash") or stable_contract_hash(sorted(str(column) for column in source.columns))
    return build_authority_identity(
        canonical_symbol=state.get("canonical_symbol") or state.get("symbol") or (symbols[0] if symbols else ""),
        provider_symbol=state.get("provider_symbol") or (symbols[0] if symbols else ""),
        selected_timeframe=timeframe,
        broker_timezone_policy=state.get("broker_timezone_policy") or state.get("broker_timezone") or "UTC_INTERNAL_EXPLICIT_BROKER_ANCHOR",
        completed_candle_close_utc=completed,
        ordered_selected_symbols=symbols,
        provider=provider,
        source_id=source_id,
        source_snapshot_hash=source_hash,
        data_revision=data_revision,
        feature_schema_hash=feature_schema_hash,
        model_version=state.get("model_version") or "field10_research_authority_20260717",
        formula_version=state.get("formula_version") or "authority_score_100pip_regime_transition_priority_v3",
    )


def _research_outcome_fields(src: Mapping[str, Any], bg: Mapping[str, Any]) -> dict[str, Any]:
    """Read settled-label evidence only; never infer a target probability."""
    lookup = dict(bg)
    lookup.update(src)
    target_value = _val(
        lookup,
        "Probability Target Reached", "Target Reach Probability", "Settled Target Probability",
        "probability_target_reached", "p_target", default="UNAVAILABLE",
    )
    sample_value = _val(
        lookup, "Settled Sample Size", "settled_sample_size", "Outcome Sample Size", "Settled Outcomes", default=0,
    )
    try:
        settled_sample = int(float(sample_value))
    except (TypeError, ValueError):
        settled_sample = 0
    try:
        target_probability = float(str(target_value).replace("%", ""))
        if target_probability > 1:
            target_probability /= 100.0
        if not 0 <= target_probability <= 1:
            raise ValueError
    except (TypeError, ValueError):
        target_probability = None
    if target_probability is None:
        target_status = "INSUFFICIENT_SETTLED_OUTCOMES"
    elif settled_sample < 100:
        target_status = "INSUFFICIENT_SETTLED_OUTCOMES"
    else:
        target_status = "SETTLED_OUTCOME_ESTIMATE"
    mfe = _val(lookup, "Expected MFE", "expected_MFE", "Median MFE", default="UNAVAILABLE")
    mae = _val(lookup, "Expected MAE", "expected_MAE", "Median MAE", default="UNAVAILABLE")
    utility = expected_net_value(
        probability_target_reached=target_probability,
        expected_mfe=mfe,
        expected_mae=mae,
        spread_cost=_val(lookup, "Spread Cost", "spread_cost", default=0.0),
        slippage_cost=_val(lookup, "Slippage Cost", "slippage_cost", default=0.0),
        event_penalty=_val(lookup, "Event Penalty", "event_penalty", default=0.0),
        uncertainty_penalty=_val(lookup, "Uncertainty Penalty", "uncertainty_penalty", default=0.0),
        cvar_penalty=_val(lookup, "CVaR Penalty", "cvar_penalty", default=0.0),
        dependency_penalty=_val(lookup, "Dependency Penalty", "dependency_penalty", default=0.0),
        data_quality_penalty=_val(lookup, "Data Quality Penalty", "data_quality_penalty", default=0.0),
        stale_data_penalty=_val(lookup, "Stale Data Penalty", "stale_data_penalty", default=0.0),
        transition_penalty=_val(lookup, "Transition Penalty", "transition_penalty", default=0.0),
    )
    event_permission = str(_val(lookup, "Event-Risk Permission", "Event Risk Permission", default="UNAVAILABLE")).upper()
    event_state = str(_val(lookup, "Event Risk State", "Event State", default="UNAVAILABLE")).upper()
    source_event = str(_val(lookup, "Event Type", "event_type", default="")).upper()
    if any(token in source_event for token in ("CPI", "PPI")) and event_permission in {"", "UNAVAILABLE", "ALLOW"}:
        # A CPI/PPI record without a complete point-in-time event contract is
        # not a safe neutral value.
        event_permission = "BLOCK"
        event_state = "DATA_UNAVAILABLE"
    trade_permission = "BLOCK_RESEARCH_ONLY" if target_status != "SETTLED_OUTCOME_ESTIMATE" else "ALLOW"
    no_trade_reason = "Target probability requires settled future outcomes." if trade_permission != "ALLOW" else ""
    if event_permission == "BLOCK":
        trade_permission = "BLOCK_EVENT_RISK"
        no_trade_reason = "Scheduled event uncertainty or shock window is active."
    return {
        "Probability Target Reached": target_probability if target_probability is not None and settled_sample >= 100 else "UNAVAILABLE",
        "Probability Target Reached Status": target_status,
        "Settled Sample Size": settled_sample,
        "Expected MFE": mfe,
        "Expected MAE": mae,
        "Expected Net Value": utility if utility is not None and target_status == "SETTLED_OUTCOME_ESTIMATE" else "UNAVAILABLE",
        "Uncertainty": _val(lookup, "Uncertainty", "Prediction Uncertainty", "uncertainty", default="UNAVAILABLE"),
        "Event Risk": event_state,
        "Event Risk Permission": event_permission,
        "Trade Permission": trade_permission,
        "No-Trade Reason": no_trade_reason,
        "Publication Mode": "PRODUCTION_READY" if trade_permission == "ALLOW" else "RESEARCH_ONLY",
    }

def build_unified_field10_authority(state: MutableMapping[str, Any] | None = None, *, source_frame: pd.DataFrame | None = None, persist: bool = True) -> dict[str, Any]:
    state = state if state is not None else {}
    symbols, tf = _symbols(state), _tf(state)
    source = source_frame.copy() if isinstance(source_frame, pd.DataFrame) and not source_frame.empty else _source(state, symbols)
    if "Symbol" not in source.columns: source["Symbol"] = symbols[:len(source)] if len(source) else symbols
    source["Symbol"] = source["Symbol"].map(_norm_symbol)
    source = source[source["Symbol"].isin(symbols)].drop_duplicates("Symbol", keep="first")
    missing = [s for s in symbols if s not in set(source["Symbol"])]
    if missing: source = pd.concat([source, pd.DataFrame({"Symbol":missing})], ignore_index=True)
    # Preserve the user-selected symbol order as an input identity.  Ranking
    # itself is later deterministic and does not depend on provider row order.
    source["__symbol_order"] = source["Symbol"].map({symbol: index for index, symbol in enumerate(symbols)})
    source = source.sort_values("__symbol_order", kind="mergesort").drop(columns="__symbol_order")
    source = source.reset_index(drop=True)
    raw_completed = _completed(state, source)
    completed = _normalize_completed_candle_for_timeframe(raw_completed, tf)
    reused = _reuse_same_candle_authority(state, symbols=symbols, timeframe=tf, completed=completed)
    if reused is not None:
        return reused
    persisted = _load_persisted_authority(state, symbols=symbols, timeframe=tf, completed=completed)
    if persisted is not None:
        return persisted
    broker_day = _broker_day(completed)
    parent_run_id = str(state.get("multi_symbol_parent_run_id_20260701") or state.get("adx_current_run_id_20260708") or f"RUN-{stable_hash(symbols+[tf,broker_day])}")
    generation_id = str(state.get("current_generation_id") or state.get("generation_id") or parent_run_id)
    loaded = 0
    for _, r in source.iterrows():
        row = r.to_dict(); status = str(_val(row,"Load Status","Loaded Status","Publication","Validation Status","Ranking Result", default="")).upper(); sample = _num(_val(row,"Sample Count","Rows","Candle Count", default=0),0)
        loaded += int(sample > 0 or any(t in status for t in ("READY","LOADED","PUBLISHED","SUCCESS","CACHE","VALIDATED")))
    failed = max(0, len(symbols)-loaded)
    status = (
        "RESEARCH_ONLY" if loaded == 0 else
        PublicationStatus.COMPLETE.value if symbols and loaded == len(symbols) and failed == 0 else
        PublicationStatus.PARTIAL_READY.value
    )
    identity = _authority_identity_for(state, source, symbols, tf, completed)
    parity_status = _cross_device_parity_status()
    universe_hash = stable_hash(symbols)
    candle_hash = stable_hash([tf, completed])[:10]
    # The completed candle is part of the durable identity.  Without it, two
    # H4 publications on the same broker day overwrite each other and a
    # reconnect can retrieve the wrong same-day rank.
    daily_snapshot_id = f"F10-{broker_day}-{tf}-{universe_hash}-{candle_hash}-{identity.authority_key[:10]}"
    output_hash = stable_contract_hash({"authority_key": identity.authority_key, "source": source.to_dict(orient="records")})
    snapshot_hash = stable_contract_hash({"authority_key": identity.authority_key, "output_hash": output_hash, "publication_status": status})
    snap = RunSnapshot(
        parent_run_id=parent_run_id, generation_id=generation_id, daily_snapshot_id=daily_snapshot_id,
        broker_day=broker_day, broker_time=str(state.get("broker_time") or completed), timeframe=tf,
        completed_broker_candle=completed, ordered_symbol_universe=list(symbols), loaded_symbol_count=loaded,
        failed_symbol_count=failed, provider_summary=identity.provider, data_quality_summary=status,
        input_hash=stable_contract_hash(identity.to_dict()), output_hash=output_hash,
        snapshot_hash=snapshot_hash, publication_status=status,
        created_at_broker_time=str(state.get("broker_time") or datetime.now(timezone.utc).isoformat()),
        model_version=identity.model_version, formula_version=identity.formula_version,
    )
    background = compute_background_frame(source, symbols); bgmap = {str(x.get("Symbol")):x for x in background.to_dict(orient="records")}
    rows: list[dict[str, Any]] = []
    for i, (_, r) in enumerate(source.iterrows(), start=1):
        src = r.to_dict(); sym = _norm_symbol(src.get("Symbol")); bg = bgmap.get(sym,{})
        legacy_rank = _rank(src,i); bias = _bias({**src, **bg}); less = _bias({"Less-Risky Bias": _val(src,"Less-Risky Bias","Final Less-Risky Bias","Final Less-Risky Bias to Hold", default=bias)})
        sample = int(_num(_val(src,"Sample Count","Rows","Candle Count", default=0),0)); quality = str(_val(src,"Data Quality Grade","Data Quality", default="UNKNOWN"))
        entry = _no_wait_text(_val(src,"Entry Permission","Final Entry Permission","Trade Permission", default="ALLOW" if status == "COMPLETE" else "CAUTION_PARTIAL_READY"), fallback="CAUTION")
        no_trade = "" if status == "COMPLETE" and not entry.upper().startswith("BLOCK") else str(_val(src,"Failure Reason","No-Trade Reason","Reason", default="Partial/missing symbol evidence or blocking permission."))
        window_values = _window_columns(bg, src)
        provider = _val(src,"Provider Used","Data Provider Used","Actual Candle Provider", default="UNAVAILABLE")
        governance = governance_for_symbol(
            symbol=sym, src={**src, **window_values}, bg=bg, sample=sample, quality=quality,
            entry_permission=entry, publication_status=status, loaded_symbols=loaded,
            universe_size=len(symbols), snapshot_hash=snap.snapshot_hash,
        )
        outcome_fields = _research_outcome_fields({**src, **window_values}, bg)
        if outcome_fields.get("No-Trade Reason"):
            no_trade = str(outcome_fields["No-Trade Reason"])
        if status != PublicationStatus.COMPLETE.value and not no_trade:
            no_trade = "Partial or degraded symbol publication."
        row = {
            "Rank Star": "", "Rank": legacy_rank, "Legacy Rank": legacy_rank, "Symbol": sym, "Timeframe": tf, "timeframe": tf, "Completed Broker Candle": completed, "Next Allowed Refresh": _next_refresh_after_candle(completed, tf), "Refresh Gate": _refresh_gate_label(tf),
            "Stable Daily Bias": bias, "Less-Risky Bias": less, "Entry Permission": entry,
            "Direction Bias": bias, "Direction Bias Status": "PUBLISHED_LEGACY_DIRECTION" if bias in {"BUY", "SELL"} else "INSUFFICIENT_DATA",
            "Higher-Standard Regime Bias": _val(src, "Higher-Standard Regime Bias", "Higher Standard Regime Bias", "Field 3 Higher-Standard Bias", "Field 3 Higher Bias", default=bias),
            "Whole-Day Bias Lock Confidence": bg.get("Calibrated Probability", _val(src,"Reliability", default="UNAVAILABLE")),
            "Regime Probability": bg.get("Regime Probability","UNAVAILABLE"), "Posterior Margin": bg.get("Posterior Margin","UNAVAILABLE"), "Regime Entropy": bg.get("Regime Entropy","UNAVAILABLE"),
            **window_values,
            "CVaR 95%": bg.get("CVaR 95%","UNAVAILABLE"), "Tail Safety": bg.get("Tail Safety","UNAVAILABLE"), "Best Session 1": bg.get("Best Session 1","UNAVAILABLE"), "Best Session 2": bg.get("Best Session 2","UNAVAILABLE"), "Session Robustness Score": bg.get("Session Robustness Score","UNAVAILABLE"),
            "News Sentiment Bias": bg.get("News Sentiment Bias","UNAVAILABLE"), "Active High-Impact Event": bg.get("Active High-Impact Event","UNAVAILABLE"), "Impact Remaining": bg.get("Impact Remaining","UNAVAILABLE"), "Absorption Percentage": bg.get("Absorption Percentage","UNAVAILABLE"), "Absorption Status": bg.get("Absorption Status","UNAVAILABLE"), "Event-Risk Permission": bg.get("Event-Risk Permission","UNAVAILABLE"),
            "Correlation Cluster": bg.get("Correlation Cluster","UNAVAILABLE"), "Duplicate Exposure Penalty": bg.get("Duplicate Exposure Penalty","UNAVAILABLE"), "Unique Opportunity Score": bg.get("Unique Opportunity Score","UNAVAILABLE"), "Calibrated Probability": bg.get("Calibrated Probability","UNAVAILABLE"), "Brier Score": bg.get("Brier Score","UNAVAILABLE"), "Conformal Coverage": bg.get("Conformal Coverage","UNAVAILABLE"), "Expected Calibration Error": bg.get("Expected Calibration Error","UNAVAILABLE"),
            **governance,
            **outcome_fields,
            "Data Quality Grade": quality, "Evidence Sample Size": sample, "Provider Used": provider, "Snapshot Hash": snap.snapshot_hash, "Rank Explanation": f"Authority Score ranks the symbol; legacy rank is supporting only. Trusted through {snap.snapshot_hash}.", "No-Trade Reason": no_trade,
            "daily_snapshot_id": daily_snapshot_id, "parent_run_id": parent_run_id, "generation_id": generation_id, "broker_day": broker_day, "completed_broker_candle": completed, "ordered_symbol_universe": " → ".join(symbols), "loaded_symbol_count": loaded, "failed_symbol_count": failed, "universe_hash": universe_hash, "snapshot_hash": snap.snapshot_hash,
            "authority_key": identity.authority_key, "canonical_symbol": identity.canonical_symbol, "provider_symbol": identity.provider_symbol,
            "broker_timezone_policy": identity.broker_timezone_policy, "source_id": identity.source_id,
            "source_snapshot_hash": identity.source_snapshot_hash, "data_revision": identity.data_revision,
            "feature_schema_hash": identity.feature_schema_hash, "cross_device_parity_status": parity_status,
            "publication_mode": outcome_fields.get("Publication Mode") or "RESEARCH_ONLY",
            "rank": legacy_rank, "symbol": sym, "stable_daily_bias": bias, "less_risky_bias": less, "entry_permission": entry, "data_quality_grade": quality, "sample_count": sample, "provider_used": provider, "evidence_source": "FIELD10_UNIFIED_AUTHORITY_GOVERNED_SCORE_V2", "publication_status": status,
        }
        rows.append(row)
    if rows:
        rows = sorted(rows, key=sort_key_for_authority)
        for final_rank, row in enumerate(rows, start=1):
            row["Rank"] = final_rank
            row["rank"] = final_rank
            row["Rank Star"] = f"★ {final_rank}" if final_rank <= 4 else ""
            row["Authority Placement"] = "TOP_4_AUTHORITY" if final_rank <= 4 and row.get("Authority Placement") == "TOP_AUTHORITY_CANDIDATE" else row.get("Authority Placement")
    table = pd.DataFrame(rows).reset_index(drop=True) if rows else pd.DataFrame(columns=list(REQUIRED_TRUST_FIELDS))
    why = {
        "snapshot hash": snap.snapshot_hash, "authority key": identity.authority_key,
        "broker candle": completed, "raw latest candle input": raw_completed, "timeframe": tf,
        "refresh gate": _refresh_gate_label(tf), "next allowed refresh": _next_refresh_after_candle(completed, tf),
        "loaded symbols": loaded, "failed symbols": failed, "data quality": snap.data_quality_summary,
        "publication status": status, "publication mode": "RESEARCH_ONLY" if status != "COMPLETE" else "RESEARCH_ONLY",
        "cross-device parity": parity_status, "last calculation time": snap.created_at_broker_time,
        "locked until": "selected timeframe candle changes; daily rank also locked until broker 23:00",
        "ranking method": "Governed Authority Score v3: legacy 100-pip/4H overlay is supporting evidence; settled target utility is the production promotion contract.",
        "legacy rank role": "Legacy ranks are preserved as Legacy Rank only; they cannot set final authority placement.",
        "legacy probability disclosure": "Probability 100 Pip Move 4H is a legacy heuristic overlay, not a settled target probability.",
        "authority rule": "Field 10 is the canonical rank publisher. Field 12 are read-only adapters; risk, uncertainty, data quality and trade permission remain separate gates.",
    }
    session = build_session_table(table, snap); news = build_news_event_table(table, snap); supporting = build_supporting_evidence_entry_timing_table(table, session, news, snap); merged = build_merged_authority_supporting_table(table, supporting, snap); dinner = build_dinner_background_table(table, background, snap); viz = build_visualization_table(table, snap)
    export = build_export_manifest(snap)
    snapshot_payload = snap.to_dict() | {
        "why_trust": why, "authority_key": identity.authority_key,
        "authority_identity": identity.to_dict(), "authority_identity_json": json.dumps(identity.to_dict(), sort_keys=True),
        "canonical_symbol": identity.canonical_symbol, "provider_symbol": identity.provider_symbol,
        "broker_timezone_policy": identity.broker_timezone_policy, "source_id": identity.source_id,
        "source_snapshot_hash": identity.source_snapshot_hash, "data_revision": identity.data_revision,
        "feature_schema_hash": identity.feature_schema_hash,
        "cross_device_parity_status": parity_status, "publication_mode": why["publication mode"],
    }
    state[UNIFIED_TABLE_KEY]=table; state[UNIFIED_SNAPSHOT_KEY]=snapshot_payload; state[AUTHORITY_IDENTITY_KEY]=identity.to_dict(); state[PARITY_STATUS_KEY]=parity_status; state[SESSION_TABLE_KEY]=session; state[NEWS_TABLE_KEY]=news; state[SUPPORTING_TABLE_KEY]=supporting; state[MERGED_TABLE_KEY]=merged; state[BACKGROUND_TABLE_KEY]=background; state[DINNER_TABLE_KEY]=dinner; state[VIZ_TABLE_KEY]=viz; state[EXPORT_MANIFEST_KEY]=export
    state["field10_authority_view_model_20260709"] = Field10ViewModel(snapshot_hash=snap.snapshot_hash, rows=merged.to_dict(orient="records"), supporting_rows=supporting.to_dict(orient="records"), publication_status=status, trusted_reason=why["authority rule"])
    state["dinner_view_model_20260709"] = DinnerViewModel(snapshot_hash=snap.snapshot_hash, rows=dinner.to_dict(orient="records"), publication_status=status)
    state["visualization_view_model_20260709"] = VisualizationViewModel(snapshot_hash=snap.snapshot_hash, rank_rows=viz.to_dict(orient="records"), risk_rows=viz.to_dict(orient="records"), session_rows=session.to_dict(orient="records"), publication_status=status)
    if persist: persist_authority_tables(state)
    return {"snapshot":snapshot_payload,"why_trust":why,"table":table,"merged":merged,"background":background,"session":session,"news":news,"supporting":supporting,"dinner":dinner,"visualization":viz,"export_manifest":export}



def build_merged_authority_supporting_table(unified: pd.DataFrame, supporting: pd.DataFrame, snap: RunSnapshot) -> pd.DataFrame:
    """First visible Field 10 surface: authority rank + supporting timing evidence.

    This merges the former two display sections into one table while preserving
    the supporting-only role of session/news/event evidence.
    """
    if not isinstance(unified, pd.DataFrame) or unified.empty:
        return pd.DataFrame()
    authority = unified.copy()
    support_cols = [
        "Symbol", "Best Entry Session", "Session Score", "News Sentiment Bias",
        "High-Impact Event", "Event-Risk Permission", "Absorption Status",
        "Impact Remaining", "Entry Timing Permission", "Trust Role",
        "Can Override Authority Bias?",
    ]
    if isinstance(supporting, pd.DataFrame) and not supporting.empty and "Symbol" in supporting.columns:
        support = supporting[[c for c in support_cols if c in supporting.columns]].drop_duplicates("Symbol", keep="first").copy()
        rename = {c: f"Timing • {c}" for c in support.columns if c != "Symbol"}
        support = support.rename(columns=rename)
        merged = authority.merge(support, on="Symbol", how="left")
    else:
        merged = authority
    merged.insert(0, "Merged Surface", "AUTHORITY_PLUS_ENTRY_TIMING")
    merged["Final Bias Rule"] = "BUY_SELL_ONLY_NO_WAIT"
    merged["Ranking Priority 1"] = "Probability 100 Pip Move 4H"
    merged["Ranking Priority 2"] = "Higher-Standard Regime Bias Priority"
    merged["Ranking Priority 3"] = "Transition Risk 6H"
    merged["Supporting Evidence Role"] = "ENTRY_TIMING_EXPLANATION_ONLY_NO_OVERRIDE"
    merged["snapshot_hash"] = snap.snapshot_hash
    return merged

def build_supporting_evidence_entry_timing_table(unified: pd.DataFrame, session: pd.DataFrame, news: pd.DataFrame, snap: RunSnapshot) -> pd.DataFrame:
    """One supporting rank table for evidence, vetoes and entry timing.

    This table has a different purpose from the authority table: it explains
    *when* and *why* to be careful.  It deliberately repeats the authority rank
    and daily bias but never publishes a separate final direction.
    """
    if not isinstance(unified, pd.DataFrame) or unified.empty:
        return pd.DataFrame()
    best_session = {}
    if isinstance(session, pd.DataFrame) and not session.empty and {"Symbol", "Session Name"}.issubset(session.columns):
        tmp = session.copy()
        tmp["_rank"] = pd.to_numeric(tmp.get("Session Rank"), errors="coerce")
        tmp = tmp.sort_values(["Symbol", "_rank"], kind="mergesort")
        best_session = tmp.groupby("Symbol").head(1).set_index("Symbol").to_dict(orient="index")
    news_map = {}
    if isinstance(news, pd.DataFrame) and not news.empty and "Symbol" in news.columns:
        news_map = news.drop_duplicates("Symbol", keep="first").set_index("Symbol").to_dict(orient="index")
    rows: list[dict[str, Any]] = []
    for _, raw in unified.iterrows():
        row = raw.to_dict()
        sym = str(row.get("Symbol") or "")
        sess = best_session.get(sym, {})
        n = news_map.get(sym, {})
        event_permission = _no_wait_text(row.get("Event-Risk Permission") or n.get("Event-Risk Permission") or "CHECK", fallback="CAUTION")
        entry_permission = _no_wait_text(row.get("Entry Permission") or sess.get("Session Entry Permission") or "CHECK", fallback="CAUTION")
        rank = int(_num(row.get("Rank"), len(rows) + 1))
        rows.append({
            "Evidence Rank": rank,
            "Symbol": sym,
            "Timeframe": snap.timeframe,
            "Completed Broker Candle": snap.completed_broker_candle,
            "Next Allowed Refresh": _next_refresh_after_candle(snap.completed_broker_candle, snap.timeframe),
            "Refresh Gate": _refresh_gate_label(snap.timeframe),
            "Authority Rank Link": f"Rank {rank} in trusted table",
            "Authority Daily Bias": row.get("Stable Daily Bias"),
            "Probability 100 Pip Move 4H": row.get("Probability 100 Pip Move 4H"),
            "Projected 4H Move Pips": row.get("Projected 4H Move Pips"),
            "100 Pip 4H Target Status": row.get("100 Pip 4H Target Status"),
            "Entry Timing Permission": entry_permission,
            "Best Entry Session": sess.get("Session Name") or row.get("Best Session 1"),
            "Session Score": sess.get("Session Score") or row.get("Session Robustness Score"),
            "News Sentiment Bias": row.get("News Sentiment Bias") or n.get("Sentiment Bias"),
            "High-Impact Event": row.get("Active High-Impact Event") or n.get("High-Impact Headline"),
            "Event-Risk Permission": event_permission,
            "Absorption Status": row.get("Absorption Status") or n.get("Absorption Status"),
            "Impact Remaining": row.get("Impact Remaining") or n.get("Impact Remaining Percentage"),
            "Transition Risk 1H": row.get("Transition Risk 1H"),
            "Transition Risk 3H": row.get("Transition Risk 3H"),
            "Transition Risk 6H": row.get("Transition Risk 6H"),
            "Transition Risk 12H": row.get("Transition Risk 12H"),
            "Transition Risk 24H": row.get("Transition Risk 24H"),
            "Transition Risk 36H": row.get("Transition Risk 36H"),
            "Probability Profit 1H": row.get("Probability Profit 1H"),
            "Probability Profit 3H": row.get("Probability Profit 3H"),
            "Probability Profit 6H": row.get("Probability Profit 6H"),
            "Probability Profit 12H": row.get("Probability Profit 12H"),
            "Expected Return 1H": row.get("Expected Return 1H"),
            "Expected Return 3H": row.get("Expected Return 3H"),
            "Expected Return 6H": row.get("Expected Return 6H"),
            "Expected Return 12H": row.get("Expected Return 12H"),
            "Expected Return 24H": row.get("Expected Return 24H"),
            "Expected Return 36H": row.get("Expected Return 36H"),
            "Data Quality Grade": row.get("Data Quality Grade"),
            "Evidence Sample Size": row.get("Evidence Sample Size"),
            "Provider Used": row.get("Provider Used"),
            "Trust Role": "SUPPORTING_ONLY_ENTRY_TIMING_AND_VETO_EVIDENCE",
            "Can Override Authority Bias?": "NO",
            "snapshot_hash": snap.snapshot_hash,
            "daily_snapshot_id": snap.daily_snapshot_id,
            "parent_run_id": snap.parent_run_id,
            "generation_id": snap.generation_id,
            "broker_day": snap.broker_day,
            "publication_status": snap.publication_status,
        })
    return pd.DataFrame(rows).sort_values("Evidence Rank", kind="mergesort").reset_index(drop=True)

def build_session_table(unified: pd.DataFrame, snap: RunSnapshot) -> pd.DataFrame:
    rows=[]
    for _, row in unified.iterrows():
        for i, sess in enumerate(SESSION_NAMES, 1):
            pref = sess in {row.get("Best Session 1"), row.get("Best Session 2")}
            rows.append({"Session Rank": i if pref else i+20, "Session Name": sess, "Broker Start":"timezone-aware broker conversion required at runtime", "Broker End":"timezone-aware broker conversion required at runtime", "Symbol":row.get("Symbol"), "Whole-Day Bias":row.get("Stable Daily Bias"), "Session Bias":row.get("Stable Daily Bias") if pref else f"LOWER_PRIORITY_{row.get('Stable Daily Bias') or 'BUY_SELL'}", "Bias Agreement":"AGREE" if pref else "SUPPORTING_ONLY", "Session Entry Permission":"ALLOW" if pref and str(row.get("Event-Risk Permission")).upper() != "BLOCK" else "CAUTION", "Session Score":row.get("Session Robustness Score"), "Calibrated Probability":row.get("Calibrated Probability"), "Probability Profit 1H":row.get("Probability Profit 1H"), "Probability Profit 3H":row.get("Probability Profit 1H"), "Probability Profit 6H":row.get("Probability Profit 6H"), "Expected Return 1H":row.get("Expected Return 1H"), "Expected Return 3H":row.get("Expected Return 3H"), "Expected Return 6H":row.get("Expected Return 6H"), "Risk-Adjusted EV":row.get("Expected Return 6H"), "CVaR 95%":row.get("CVaR 95%"), "Historical Session Accuracy":"UNAVAILABLE", "Median MFE":"UNAVAILABLE", "Median MAE":"UNAVAILABLE", "Session-Normalized Volatility":"UNAVAILABLE", "Tick-Volume Percentile":"UNAVAILABLE", "Spread Percentile":"UNAVAILABLE", "Liquidity Score":"UNAVAILABLE", "Regime Compatibility":"OK" if pref else "CHECK", "Transition Risk":row.get("Transition Risk 6H"), "News Blackout Status":"BLOCK" if str(row.get("Event-Risk Permission")).upper()=="BLOCK" else "CLEAR_OR_UNKNOWN", "Active Event Risk":row.get("Active High-Impact Event"), "Evidence Sample Size":row.get("Evidence Sample Size"), "Validation Status":snap.publication_status, "Explanation":"Supporting session map only; does not override unified daily rank.", "snapshot_hash":snap.snapshot_hash, "daily_snapshot_id":snap.daily_snapshot_id, "parent_run_id":snap.parent_run_id, "generation_id":snap.generation_id, "broker_day":snap.broker_day, "timeframe":snap.timeframe, "completed_broker_candle":snap.completed_broker_candle, "publication_status":snap.publication_status})
    return pd.DataFrame(rows)

def build_news_event_table(unified: pd.DataFrame, snap: RunSnapshot) -> pd.DataFrame:
    rows=[]
    for i, row in unified.iterrows():
        sym=str(row.get("Symbol") or "")
        rows.append({"News Rank":int(row.get("Rank") or i+1),"Symbol":sym,"Sentiment Bias":row.get("News Sentiment Bias"),"Sentiment Probability":row.get("Calibrated Probability"),"Base-Currency Effect":sym[:3] or "UNAVAILABLE","Quote-Currency Effect":sym[3:6] or "UNAVAILABLE","Pair Direction Effect":row.get("Stable Daily Bias"),"High-Impact Headline":row.get("Active High-Impact Event") or "UNAVAILABLE","Event Type":"UNAVAILABLE","Affected Currency":"UNAVAILABLE","Source":"existing saved Field 10/news evidence","Source Quality":row.get("Data Quality Grade"),"News Release UTC":"UNAVAILABLE","News Release Broker Time":"UNAVAILABLE","Current Broker Time":snap.broker_time,"Event Age Minutes":"UNAVAILABLE","Scheduled / Unscheduled":"UNAVAILABLE","Actual Value":"UNAVAILABLE","Consensus Value":"UNAVAILABLE","Surprise Score":"UNAVAILABLE","Entity Relevance":"UNAVAILABLE","Pair Relevance":"CURRENT_SYMBOL","Novelty Score":"UNAVAILABLE","Duplicate Group":"UNAVAILABLE","FinBERT Tone":"OPTIONAL_UNAVAILABLE","Deterministic Fallback Tone":row.get("News Sentiment Bias"),"Sentiment Agreement":"CHECK","Abnormal Return":"UNAVAILABLE","Cumulative Abnormal Return":"UNAVAILABLE","Abnormal Volatility":"UNAVAILABLE","Abnormal Tick Volume":"UNAVAILABLE","Event Response Percentile":"UNAVAILABLE","Event Intensity":row.get("Impact Remaining"),"Estimated Impact Half-Life":"UNAVAILABLE","Expected Impact Time Left":"UNAVAILABLE","Impact Remaining Percentage":row.get("Impact Remaining"),"Absorption Percentage":row.get("Absorption Percentage"),"Absorption Status":row.get("Absorption Status"),"Next-1H Shock Probability":row.get("Next-1H Shock Probability","UNAVAILABLE"),"Reversal Risk":"CHECK","Event-Risk Permission":row.get("Event-Risk Permission"),"Evidence Sample Size":row.get("Evidence Sample Size"),"Model Version":"news_event_absorption_20260709","Explanation":"Supporting news/event table only; unavailable values are not invented.","snapshot_hash":snap.snapshot_hash,"daily_snapshot_id":snap.daily_snapshot_id,"parent_run_id":snap.parent_run_id,"generation_id":snap.generation_id,"broker_day":snap.broker_day,"timeframe":snap.timeframe,"completed_broker_candle":snap.completed_broker_candle,"publication_status":snap.publication_status})
    return pd.DataFrame(rows)

def build_dinner_background_table(unified: pd.DataFrame, background: pd.DataFrame, snap: RunSnapshot) -> pd.DataFrame:
    tabs={"Dinner Regime":"Hamilton + BOCPD + Bai-Perron background","Dinner Forecast":"CQR + adaptive conformal background","Dinner Reliability":"Brier + calibration + DSR background","Dinner Session":"Andersen-Bollerslev + Dacorogna background","Dinner Risk":"CVaR + Ledoit-Wolf background","Dinner News/Sentiment":"Tetlock + FinBERT background","Dinner Event Response":"MacKinlay event study + Hawkes background","Dinner Governance":"SPA + PBO + DSR background"}
    rows=[]
    for tab, model in tabs.items():
        for _, row in unified.iterrows():
            rows.append({"Dinner Inner Tab":tab,"Symbol":row.get("Symbol"),"Research Background":model,"input snapshot id":snap.daily_snapshot_id,"input broker candle":snap.completed_broker_candle,"input timeframe":snap.timeframe,"input symbol universe":" → ".join(snap.ordered_symbol_universe),"research model version":"dinner_research_background_20260709","input hash":snap.input_hash,"output hash":snap.output_hash,"sample size":row.get("Evidence Sample Size"),"data quality status":row.get("Data Quality Grade"),"incomplete reason if missing":"" if snap.publication_status=="COMPLETE" else "Parent snapshot is PARTIAL_READY; review failed symbols before final trust.","snapshot_hash":snap.snapshot_hash,"publication_status":snap.publication_status})
    return pd.DataFrame(rows)

def build_visualization_table(unified: pd.DataFrame, snap: RunSnapshot) -> pd.DataFrame:
    return pd.DataFrame([{"Section":"Field 10 Rank Overview","Symbol":r.get("Symbol"),"Rank":r.get("Rank"),"Bias":r.get("Stable Daily Bias"),"Risk":r.get("Transition Risk 6H"),"Reliability":r.get("Calibrated Probability"),"Data Quality":r.get("Data Quality Grade"),"Event Risk":r.get("Event-Risk Permission"),"Provider Risk":r.get("Provider Used"),"Sync Risk":"OK" if snap.publication_status=="COMPLETE" else "PARTIAL_READY","snapshot_hash":snap.snapshot_hash,"daily_snapshot_id":snap.daily_snapshot_id,"timeframe":snap.timeframe,"completed_broker_candle":snap.completed_broker_candle,"publication_status":snap.publication_status} for _, r in unified.iterrows()])

def build_export_manifest(snap: RunSnapshot) -> dict[str, Any]:
    files=[f"field10_merged_authority_entry_timing_rank_{snap.broker_day}_{snap.timeframe}_{snap.snapshot_hash}.csv",f"field10_unified_rank_{snap.broker_day}_{snap.timeframe}_{snap.snapshot_hash}.csv",f"dinner_evidence_{snap.broker_day}_{snap.timeframe}_{snap.snapshot_hash}.csv",f"data_visualization_{snap.broker_day}_{snap.timeframe}_{snap.snapshot_hash}.csv",f"background_function_status_{snap.broker_day}_{snap.timeframe}_{snap.snapshot_hash}.csv",f"full_snapshot_export_{snap.broker_day}_{snap.timeframe}_{snap.snapshot_hash}.zip"]
    return ExportManifest(snapshot_hash=snap.snapshot_hash,parent_run_id=snap.parent_run_id,broker_day=snap.broker_day,timeframe=snap.timeframe,completed_broker_candle=snap.completed_broker_candle,files=files,publication_status=snap.publication_status).__dict__

def authority_csv_bytes(frame: pd.DataFrame, snapshot: Mapping[str, Any] | None=None) -> bytes:
    out = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame(); snap = snapshot or {}
    for c, v in (("snapshot_hash",snap.get("snapshot_hash")),("parent_run_id",snap.get("parent_run_id")),("broker_day",snap.get("broker_day")),("timeframe",snap.get("timeframe")),("completed_broker_candle",snap.get("completed_broker_candle")),("publication_status",snap.get("publication_status"))):
        if c not in out.columns: out.insert(0,c,v or "UNAVAILABLE")
    return out.to_csv(index=False).encode("utf-8")

def full_snapshot_zip_bytes(state: Mapping[str, Any]) -> bytes:
    snap = state.get(UNIFIED_SNAPSHOT_KEY) if isinstance(state.get(UNIFIED_SNAPSHOT_KEY), Mapping) else {}
    buf=BytesIO()
    with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as zf:
        for name,key in (("field10_merged_authority_supporting_rank.csv",MERGED_TABLE_KEY),("field10_unified_rank.csv",UNIFIED_TABLE_KEY),("field10_session_rank.csv",SESSION_TABLE_KEY),("field10_news_event_rank.csv",NEWS_TABLE_KEY),("field10_supporting_evidence_entry_timing_rank.csv",SUPPORTING_TABLE_KEY),("dinner_research_evidence.csv",DINNER_TABLE_KEY),("data_visualization.csv",VIZ_TABLE_KEY)):
            frame=state.get(key)
            if isinstance(frame,pd.DataFrame): zf.writestr(name, authority_csv_bytes(frame,snap))
        zf.writestr("background_function_status.csv", authority_csv_bytes(function_status_frame(str(snap.get("snapshot_hash") or "")), snap))
        zf.writestr("snapshot_identity.json", json.dumps(snap, indent=2, default=str))
        zf.writestr("export_manifest.json", json.dumps(state.get(EXPORT_MANIFEST_KEY) or {}, indent=2, default=str))
    return buf.getvalue()

def persist_authority_tables(state: Mapping[str, Any]) -> dict[str, Any]:
    """Append an authority snapshot without overwriting an earlier identity.

    Repeating the exact same publication is idempotent.  Reusing the same
    snapshot id with different content is a hard conflict and leaves the
    original rows untouched.
    """
    report: dict[str, Any] = {"status": "NOT_ATTEMPTED", "ok": False}
    try:
        from core.field10_research_migration_20260709 import migrate_field10_research_authority
        db_path = _authority_db_path()
        migration = migrate_field10_research_authority(db_path)
        if not migration.get("ok"):
            report.update({"status": "MIGRATION_FAILED", "error": migration.get("error")})
            return report
        conn = sqlite3.connect(str(db_path), timeout=8.0)
        conn.row_factory = sqlite3.Row
    except Exception as exc:
        report.update({"status": "PERSISTENCE_UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"})
        return report

    snap = state.get(UNIFIED_SNAPSHOT_KEY) if isinstance(state.get(UNIFIED_SNAPSHOT_KEY), Mapping) else {}
    table = state.get(UNIFIED_TABLE_KEY) if isinstance(state.get(UNIFIED_TABLE_KEY), pd.DataFrame) else pd.DataFrame()
    snapshot_id = str(snap.get("daily_snapshot_id") or "")
    identity_state = state.get(AUTHORITY_IDENTITY_KEY) if isinstance(state.get(AUTHORITY_IDENTITY_KEY), Mapping) else {}
    authority_key = str(snap.get("authority_key") or identity_state.get("authority_key") or "")
    attempt_hash = stable_contract_hash({"snapshot": snap, "rows": table.to_dict(orient="records")})

    def record_attempt(status: str, reason: str = "") -> None:
        conn.execute(
            "INSERT INTO field10_authority_publication_attempt(authority_key,daily_snapshot_id,attempt_hash,status,reason) VALUES(?,?,?,?,?) ON CONFLICT(authority_key,attempt_hash) DO NOTHING",
            (authority_key, snapshot_id, attempt_hash, status, reason),
        )

    try:
        parent_values = (
            snapshot_id, snap.get("parent_run_id"), snap.get("generation_id"), snap.get("broker_day"),
            snap.get("timeframe"), snap.get("completed_broker_candle"), json.dumps(snap.get("ordered_symbol_universe") or []),
            snap.get("loaded_symbol_count"), snap.get("failed_symbol_count"), stable_hash(snap.get("ordered_symbol_universe") or []),
            snap.get("snapshot_hash"), snap.get("input_hash"), snap.get("output_hash"), snap.get("model_version"),
            snap.get("formula_version"), snap.get("created_at_broker_time"), snap.get("publication_status"),
            "" if snap.get("publication_status") == "COMPLETE" else "partial/missing child rows",
            json.dumps(snap.get("why_trust") or {}, default=str), authority_key,
            snap.get("canonical_symbol"), snap.get("provider_symbol"), snap.get("broker_timezone_policy"),
            snap.get("source_id"), snap.get("source_snapshot_hash"), snap.get("data_revision"),
            snap.get("feature_schema_hash"), snap.get("cross_device_parity_status") or _cross_device_parity_status(),
            snap.get("publication_mode") or "RESEARCH_ONLY", snap.get("authority_identity_json") or json.dumps(snap.get("authority_identity") or {}, sort_keys=True, default=str),
        )
        try:
            conn.execute(
                "INSERT INTO field10_unified_rank_snapshot(daily_snapshot_id,parent_run_id,generation_id,broker_day,timeframe,completed_broker_candle,ordered_symbol_universe,loaded_symbol_count,failed_symbol_count,universe_hash,snapshot_hash,input_hash,output_hash,model_version,formula_version,created_at_broker_time,publication_status,incomplete_reason,why_trust_json,authority_key,canonical_symbol,provider_symbol,broker_timezone_policy,source_id,source_snapshot_hash,data_revision,feature_schema_hash,cross_device_parity_status,publication_mode,authority_identity_json) VALUES(" + ",".join("?" for _ in parent_values) + ")",
                parent_values,
            )
        except sqlite3.IntegrityError:
            existing = conn.execute("SELECT snapshot_hash,input_hash,output_hash,authority_key FROM field10_unified_rank_snapshot WHERE daily_snapshot_id=?", (snapshot_id,)).fetchone()
            if not existing:
                raise
            same = tuple(str(existing[key] or "") for key in ("snapshot_hash", "input_hash", "output_hash", "authority_key")) == tuple(str(snap.get(key) or "") for key in ("snapshot_hash", "input_hash", "output_hash")) + (authority_key,)
            if not same:
                conn.rollback()
                record_attempt("CONFLICT_REJECTED", "immutable snapshot id already exists with different content")
                conn.commit()
                report.update({"status": "CONFLICT_REJECTED", "error": "immutable authority snapshot conflict", "snapshot_id": snapshot_id})
                return report

        for _, row in table.iterrows():
            raw = row.to_dict()
            # Preserve the publisher's column order so an exact restore is
            # byte/shape stable as well as value stable.
            row_json = json.dumps(raw, default=str)
            row_hash = stable_contract_hash({"snapshot_id": snapshot_id, "symbol": raw.get("Symbol"), "row": raw})
            values = (
                snapshot_id or raw.get("daily_snapshot_id"), raw.get("parent_run_id") or snap.get("parent_run_id"),
                raw.get("generation_id") or snap.get("generation_id"), raw.get("broker_day") or snap.get("broker_day"),
                raw.get("Timeframe") or snap.get("timeframe"), raw.get("completed_broker_candle") or snap.get("completed_broker_candle"),
                raw.get("Symbol"), int(_num(raw.get("Rank"), 0)), raw.get("Stable Daily Bias"), raw.get("Less-Risky Bias"),
                raw.get("Entry Permission"), raw.get("Data Quality Grade"), int(_num(raw.get("Evidence Sample Size"), 0)),
                raw.get("Provider Used"), raw.get("evidence_source"), row_json, raw.get("model_version") or "field10_research_authority_20260717",
                raw.get("Formula Version") or snap.get("formula_version") or "authority_score_20260717", raw.get("input_hash") or snap.get("input_hash"),
                stable_contract_hash(raw), snap.get("created_at_broker_time"), raw.get("publication_status") or snap.get("publication_status"),
                raw.get("No-Trade Reason"), authority_key, row_hash,
            )
            try:
                conn.execute(
                    "INSERT INTO field10_unified_rank_symbol(daily_snapshot_id,parent_run_id,generation_id,broker_day,timeframe,completed_broker_candle,symbol,rank,stable_daily_bias,less_risky_bias,entry_permission,data_quality_grade,sample_count,provider_used,evidence_source,row_json,model_version,formula_version,input_hash,output_hash,created_at_broker_time,publication_status,incomplete_reason,authority_key,row_hash) VALUES(" + ",".join("?" for _ in values) + ")",
                    values,
                )
            except sqlite3.IntegrityError:
                old = conn.execute("SELECT row_json,row_hash FROM field10_unified_rank_symbol WHERE daily_snapshot_id=? AND symbol=?", (snapshot_id, raw.get("Symbol"))).fetchone()
                if not old or (str(old["row_hash"] or "") != row_hash and str(old["row_json"] or "") != row_json):
                    raise RuntimeError(f"immutable symbol row conflict: {raw.get('Symbol')}")

        for key, table_name in ((SESSION_TABLE_KEY, "field10_daily_session_rank"), (NEWS_TABLE_KEY, "field10_daily_news_event_rank"), (BACKGROUND_TABLE_KEY, "field10_research_background_evidence"), (DINNER_TABLE_KEY, "dinner_research_background_evidence"), (VIZ_TABLE_KEY, "visualization_view_materialized")):
            frame = state.get(key)
            if not isinstance(frame, pd.DataFrame):
                continue
            for _, row in frame.iterrows():
                raw = row.to_dict()
                row_json = json.dumps(raw, default=str, sort_keys=True)
                row_hash = stable_contract_hash({"snapshot_id": snapshot_id, "table": table_name, "row": raw})
                values = (
                    snapshot_id, snap.get("parent_run_id"), snap.get("generation_id"), snap.get("broker_day"), snap.get("timeframe"),
                    snap.get("completed_broker_candle"), raw.get("Symbol"), row_json, "field10_research_authority_20260717",
                    snap.get("formula_version") or "authority_score_20260717", snap.get("input_hash"), stable_contract_hash(raw),
                    snap.get("created_at_broker_time"), snap.get("publication_status"), raw.get("incomplete reason if missing") or "",
                    authority_key, row_hash,
                )
                try:
                    conn.execute(
                        f"INSERT INTO {table_name}(daily_snapshot_id,parent_run_id,generation_id,broker_day,timeframe,completed_broker_candle,symbol,row_json,model_version,formula_version,input_hash,output_hash,created_at_broker_time,publication_status,incomplete_reason,authority_key,row_hash) VALUES(" + ",".join("?" for _ in values) + ")",
                        values,
                    )
                except sqlite3.IntegrityError:
                    # Exact repeated publication is idempotent; a different
                    # row_hash for the same identity is rejected below.
                    old = conn.execute(f"SELECT row_json,row_hash FROM {table_name} WHERE daily_snapshot_id=? AND row_hash=?", (snapshot_id, row_hash)).fetchone()
                    if not old:
                        raise RuntimeError(f"immutable child row conflict: {table_name}")
        record_attempt("APPENDED_OR_IDEMPOTENT")
        conn.commit()
        report.update({"ok": True, "status": "APPENDED_OR_IDEMPOTENT", "snapshot_id": snapshot_id, "authority_key": authority_key})
    except Exception as exc:
        conn.rollback()
        try:
            record_attempt("CONFLICT_REJECTED", f"{type(exc).__name__}: {exc}")
            conn.commit()
        except Exception:
            pass
        report.update({"status": "CONFLICT_REJECTED", "error": f"{type(exc).__name__}: {exc}", "snapshot_id": snapshot_id})
    finally:
        conn.close()
    if isinstance(state, MutableMapping):
        state["field10_persistence_report_20260717"] = report
    return report

def conflict_status_for_table(candidate: pd.DataFrame, trusted: pd.DataFrame, snapshot_hash: str) -> pd.DataFrame:
    if not isinstance(candidate,pd.DataFrame) or candidate.empty: return pd.DataFrame()
    out=candidate.copy(); col="Snapshot Hash" if "Snapshot Hash" in out.columns else "snapshot_hash" if "snapshot_hash" in out.columns else None
    out["Trust Status"] = "NOT_TRUSTED_NO_SNAPSHOT_HASH" if col is None else ("SUPPORTING_EVIDENCE" if snapshot_hash in set(out[col].astype(str)) else "STALE_RUN_ID")
    return out
