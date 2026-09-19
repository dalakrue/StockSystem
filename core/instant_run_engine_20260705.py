"""Durable cooperative instant-run state machine for Streamlit.

The engine gives the browser an immediate queued acknowledgement, executes the
existing protected calculation on a subsequent Streamlit pass, streams
per-symbol progress, and preserves a compact job journal across reruns/reloads.
It intentionally does not run Streamlit commands from unsafe background
threads; the protected calculation continues to own ``st.session_state``.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, Sequence
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import os
import tempfile
import uuid

VERSION = "instant-run-engine-20260705-v1"
JOB_KEY = "instant_run_job_20260705"
HISTORY_KEY = "instant_run_history_20260705"
LAST_RESULT_KEY = "instant_run_last_result_20260705"
ENGINE_RUNNING_KEY = "instant_run_engine_running_20260705"
RUN_LOCK_KEYS = (ENGINE_RUNNING_KEY, "settings_one_click_running_20260624", "multi_symbol_run_in_progress_20260701")

ACTIVE_STATUSES = {"QUEUED", "RUNNING"}
TERMINAL_STATUSES = {"COMPLETED", "PARTIAL", "FAILED", "CANCELLED"}
VALID_SCOPES = {"QUICK", "FULL", "LUNCH_CORE"}

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_JOURNAL = _PROJECT_ROOT / ".runtime" / "instant_run_job_20260705.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _parse(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _normalize_scope(value: Any) -> str:
    scope = str(value or "QUICK").strip().upper()
    return scope if scope in VALID_SCOPES else "QUICK"


def _normalize_symbols(values: Sequence[Any] | None) -> list[str]:
    result: list[str] = []
    for raw in values or []:
        symbol = str(raw or "").strip().upper().replace("/", "").replace("_", "").replace(" ", "")
        if symbol and symbol not in result:
            result.append(symbol)
    return result


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    """Create a bounded journal-safe representation without serializing secrets."""
    if depth > 5:
        return str(value)[:240]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value if not isinstance(value, str) else value[:1000]
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for key, item in list(value.items())[:120]:
            name = str(key)
            lowered = name.lower()
            if any(token in lowered for token in ("api_key", "apikey", "secret", "password", "token", "credential")):
                continue
            safe[name] = _json_safe(item, depth=depth + 1)
        return safe
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item, depth=depth + 1) for item in list(value)[:120]]
    if hasattr(value, "shape") and hasattr(value, "columns"):
        try:
            return {"type": type(value).__name__, "rows": int(len(value)), "columns": [str(c) for c in list(value.columns)[:80]]}
        except Exception:
            return {"type": type(value).__name__}
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)[:1000]


def _job_fingerprint(scope: str, symbols: Sequence[str], timeframe: str) -> str:
    raw = f"{scope}|{timeframe}|{'|'.join(symbols)}"
    return sha256(raw.encode("utf-8")).hexdigest()[:20]


def _journal_path(path: str | Path | None = None) -> Path:
    override = os.environ.get("ADX_INSTANT_RUN_JOURNAL")
    return Path(path or override or _DEFAULT_JOURNAL)




def journal_path_for_state(state: Mapping[str, Any], path: str | Path | None = None) -> Path:
    """Use a per-login journal so separate Streamlit users never share jobs."""
    if path is not None or os.environ.get("ADX_INSTANT_RUN_JOURNAL"):
        return _journal_path(path)
    account_identity = str(
        state.get("new7_auth_email")
        or state.get("authenticated_user")
        or ""
    ).strip().lower()
    # Authenticated accounts get reload recovery keyed to their login identity.
    # Guest/anonymous sessions receive an in-memory random identity so separate
    # visitors can never read or overwrite each other's job journal.
    if account_identity and account_identity not in {"guest", "anonymous", "default"}:
        identity = f"account:{account_identity}"
    else:
        session_key = "instant_run_session_identity_20260705"
        session_identity = str(state.get(session_key) or "").strip()
        if not session_identity:
            session_identity = uuid.uuid4().hex
            try:
                state[session_key] = session_identity
            except Exception:
                pass
        identity = f"session:{session_identity}"
    digest = sha256(identity.encode("utf-8")).hexdigest()[:20]
    return _PROJECT_ROOT / ".runtime" / "instant_run_jobs" / f"{digest}.json"


def _write_journal(job: Mapping[str, Any], path: str | Path | None = None) -> None:
    target = _journal_path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(_json_safe(dict(job)), ensure_ascii=False, sort_keys=True, indent=2)
        fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
    except Exception:
        # Journal persistence must never block the trading calculation.
        return


def _read_journal(path: str | Path | None = None) -> dict[str, Any] | None:
    target = _journal_path(path)
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def current_job(
    state: MutableMapping[str, Any], *,
    restore: bool = True,
    journal_path: str | Path | None = None,
) -> dict[str, Any] | None:
    journal_path = journal_path_for_state(state, journal_path)
    value = state.get(JOB_KEY)
    if isinstance(value, Mapping):
        return dict(value)
    if restore:
        restored = _read_journal(journal_path)
        if isinstance(restored, Mapping):
            state[JOB_KEY] = dict(restored)
            return dict(restored)
    return None


def _store_job(
    state: MutableMapping[str, Any], job: Mapping[str, Any], *,
    journal_path: str | Path | None = None,
) -> dict[str, Any]:
    journal_path = journal_path_for_state(state, journal_path)
    stored = dict(job)
    state[JOB_KEY] = stored
    _write_journal(stored, journal_path)
    return stored


def release_run_locks(state: MutableMapping[str, Any]) -> None:
    """Release every cooperative Settings calculation lock after any terminal path."""
    for key in RUN_LOCK_KEYS:
        state.pop(key, None)


def enqueue_run(
    state: MutableMapping[str, Any], *,
    scope: Any,
    symbols: Sequence[Any],
    timeframe: Any = "H4",
    start_delay_seconds: float = 0.75,
    journal_path: str | Path | None = None,
) -> dict[str, Any]:
    """Queue one unique run and immediately return a serializable job record."""
    journal_path = journal_path_for_state(state, journal_path)
    existing = current_job(state, restore=False, journal_path=journal_path)
    if isinstance(existing, Mapping) and str(existing.get("status") or "").upper() in ACTIVE_STATUSES:
        return {**dict(existing), "duplicate_click_ignored": True}
    # A previous terminal run must never disable a different calculation mode.
    release_run_locks(state)

    normalized_scope = _normalize_scope(scope)
    normalized_symbols = _normalize_symbols(symbols)
    if not normalized_symbols:
        raise ValueError("Select at least one symbol before running the calculation.")
    normalized_timeframe = str(timeframe or "H4").strip().upper() or "H4"
    created = _now()
    delay = max(0.0, min(float(start_delay_seconds), 5.0))
    job_id = f"IR-{created.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:10]}"
    job = {
        "engine_version": VERSION,
        "job_id": job_id,
        "status": "QUEUED",
        "scope": normalized_scope,
        "symbols": normalized_symbols,
        "timeframe": normalized_timeframe,
        "fingerprint": _job_fingerprint(normalized_scope, normalized_symbols, normalized_timeframe),
        "created_at": created.isoformat(),
        "not_before": (created + timedelta(seconds=delay)).isoformat(),
        "started_at": None,
        "completed_at": None,
        "updated_at": created.isoformat(),
        "progress_percent": 0.0,
        "current_symbol": normalized_symbols[0],
        "current_stage": "Queued — preparing calculation",
        "symbols_progress": {
            symbol: {"status": "WAITING", "percent": 0, "stage": "Queued"}
            for symbol in normalized_symbols
        },
        "result_summary": {},
        "error": None,
        "retryable": False,
        "recovery_count": 0,
    }
    state["settings_calculation_scope_20260625"] = normalized_scope
    state["instant_run_requested_job_id_20260705"] = job_id
    return _store_job(state, job, journal_path=journal_path)


def is_due(job: Mapping[str, Any], *, now: datetime | None = None) -> bool:
    if str(job.get("status") or "").upper() != "QUEUED":
        return False
    due = _parse(job.get("not_before"))
    return due is None or (now or _now()) >= due


def seconds_until_due(job: Mapping[str, Any], *, now: datetime | None = None) -> float:
    due = _parse(job.get("not_before"))
    if due is None:
        return 0.0
    return max(0.0, (due - (now or _now())).total_seconds())


def recover_stale_job(
    state: MutableMapping[str, Any], *,
    stale_after_seconds: float = 900.0,
    journal_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Recover a stale RUNNING marker left by a server restart or hard rerun."""
    journal_path = journal_path_for_state(state, journal_path)
    job = current_job(state, restore=True, journal_path=journal_path)
    if not isinstance(job, Mapping):
        return None
    value = dict(job)
    if str(value.get("status") or "").upper() != "RUNNING":
        return value
    updated = _parse(value.get("updated_at") or value.get("started_at"))
    age = (_now() - updated).total_seconds() if updated else float("inf")
    if age <= max(30.0, float(stale_after_seconds)):
        return value
    value.update({
        "status": "QUEUED",
        "not_before": _iso(),
        "updated_at": _iso(),
        "current_stage": "Recovered after interrupted Streamlit run",
        "recovery_count": int(value.get("recovery_count") or 0) + 1,
        "retryable": True,
    })
    return _store_job(state, value, journal_path=journal_path)


def claim_job(
    state: MutableMapping[str, Any], *,
    job_id: str | None = None,
    journal_path: str | Path | None = None,
) -> dict[str, Any] | None:
    journal_path = journal_path_for_state(state, journal_path)
    job = current_job(state, restore=True, journal_path=journal_path)
    if not isinstance(job, Mapping):
        return None
    value = dict(job)
    if job_id and str(value.get("job_id")) != str(job_id):
        return None
    if str(value.get("status") or "").upper() != "QUEUED" or not is_due(value):
        return value
    now = _iso()
    value.update({
        "status": "RUNNING",
        "started_at": value.get("started_at") or now,
        "updated_at": now,
        "current_stage": "Starting protected calculation",
        "progress_percent": max(1.0, float(value.get("progress_percent") or 0.0)),
        "error": None,
        "retryable": False,
    })
    state[ENGINE_RUNNING_KEY] = str(value.get("job_id") or "instant-run")
    return _store_job(state, value, journal_path=journal_path)


def publish_progress(
    state: MutableMapping[str, Any], snapshot: Mapping[str, Any] | None, *,
    journal_path: str | Path | None = None,
) -> dict[str, Any] | None:
    journal_path = journal_path_for_state(state, journal_path)
    job = current_job(state, restore=False, journal_path=journal_path)
    if not isinstance(job, Mapping):
        return None
    value = dict(job)
    source = dict(snapshot or {})
    raw_symbols = source.get("symbols")
    if isinstance(raw_symbols, Mapping):
        value["symbols_progress"] = _json_safe(raw_symbols)
    previous_percent = max(0.0, min(100.0, float(value.get("progress_percent") or 0.0)))
    incoming_percent = max(0.0, min(100.0, float(source.get("overall_percent") or previous_percent)))
    value.update({
        "status": "RUNNING",
        # Provider preparation and symbol calculation publish from different
        # bounded phases; never let the visible progress bar move backwards.
        "progress_percent": max(previous_percent, incoming_percent),
        "current_symbol": str(source.get("current_symbol") or value.get("current_symbol") or ""),
        "current_stage": str(source.get("current_stage") or value.get("current_stage") or "Calculating"),
        "elapsed_seconds": source.get("elapsed_seconds"),
        "estimated_remaining_seconds": source.get("estimated_remaining_seconds"),
        "updated_at": _iso(),
    })
    # Frequent progress changes stay in session state; write the disk journal only
    # at meaningful boundaries to avoid excessive flash/Cloud writes.
    state[JOB_KEY] = value
    percent = int(float(value.get("progress_percent") or 0))
    if percent in {0, 25, 50, 75, 100}:
        _write_journal(value, journal_path)
    return value


def _result_summary(result: Any) -> dict[str, Any]:
    mapping = dict(result) if isinstance(result, Mapping) else {"value": result}
    payload = mapping.get("result_payload") if isinstance(mapping.get("result_payload"), Mapping) else mapping
    summary = {
        "transaction_status": mapping.get("status"),
        "result_run_id": mapping.get("result_run_id") or payload.get("run_id") or payload.get("parent_run_id") or payload.get("calculation_generation"),
        "status": payload.get("status") or mapping.get("status"),
        "ok": payload.get("ok") if "ok" in payload else (str(mapping.get("status") or "").upper() == "COMPLETED"),
        "completed_symbols": payload.get("completed_symbols"),
        "failed_symbols": payload.get("failed_symbols"),
        "elapsed_seconds": payload.get("elapsed_seconds"),
        "calculation_scope": payload.get("calculation_scope"),
        "canonical_ok": bool((payload.get("canonical") or {}).get("ok")) if isinstance(payload.get("canonical"), Mapping) else None,
        "field10_selected_rows": ((payload.get("completion_contract") or {}).get("field10_row_count") if isinstance(payload.get("completion_contract"), Mapping) else None),
        "field10_selected_total": ((payload.get("completion_contract") or {}).get("selected_count") if isinstance(payload.get("completion_contract"), Mapping) else None),
        "field10_contract_status": ((payload.get("completion_contract") or {}).get("status") if isinstance(payload.get("completion_contract"), Mapping) else None),
        "errors": list(payload.get("errors") or [])[:20] if isinstance(payload.get("errors"), (list, tuple)) else [],
    }
    return _json_safe(summary)


def complete_job(
    state: MutableMapping[str, Any], result: Any, *,
    journal_path: str | Path | None = None,
) -> dict[str, Any]:
    journal_path = journal_path_for_state(state, journal_path)
    job = current_job(state, restore=False, journal_path=journal_path) or {}
    value = dict(job)
    mapping = dict(result) if isinstance(result, Mapping) else {}
    transaction_status = str(mapping.get("status") or "COMPLETED").upper()
    payload = mapping.get("result_payload") if isinstance(mapping.get("result_payload"), Mapping) else mapping
    payload_status = str(payload.get("status") or "").upper() if isinstance(payload, Mapping) else ""
    # A controller result such as RUNNING/ALREADY_RUNNING is not a completed
    # calculation and must never be presented as success.
    failed = transaction_status not in {"COMPLETED", "PARTIAL"} or payload_status == "FAILED"
    completion_contract = payload.get("completion_contract") if isinstance(payload, Mapping) and isinstance(payload.get("completion_contract"), Mapping) else {}
    contract_required = bool(payload.get("selected_symbols") or payload.get("symbol_status")) if isinstance(payload, Mapping) else False
    contract_failed = contract_required and not bool(completion_contract.get("ok"))
    partial = (payload_status == "PARTIAL" or transaction_status == "PARTIAL" or bool(payload.get("failed_symbols")) or contract_failed) if isinstance(payload, Mapping) else False
    final_status = "FAILED" if failed else "PARTIAL" if partial else "COMPLETED"
    previous_percent = max(0.0, min(100.0, float(value.get("progress_percent") or 0.0)))
    final_percent = 100.0 if final_status == "COMPLETED" else min(99.0, max(previous_percent, 1.0))
    value.update({
        "status": final_status,
        "completed_at": _iso(),
        "updated_at": _iso(),
        "progress_percent": final_percent,
        "current_stage": "Calculation failed" if failed else "Completed with partial results" if partial else "Completed",
        "result_summary": _result_summary(result),
        "error": str(mapping.get("error") or payload.get("error") or "")[:1000] if failed else None,
        "retryable": bool(mapping.get("retryable")) if failed else False,
    })
    release_run_locks(state)
    state[LAST_RESULT_KEY] = _json_safe(result)
    history = state.get(HISTORY_KEY)
    history_list = list(history) if isinstance(history, list) else []
    history_list.append({key: value.get(key) for key in ("job_id", "scope", "symbols", "timeframe", "status", "created_at", "started_at", "completed_at", "result_summary", "error")})
    state[HISTORY_KEY] = history_list[-20:]
    return _store_job(state, value, journal_path=journal_path)


def fail_job(
    state: MutableMapping[str, Any], error: BaseException | str, *,
    retryable: bool = True,
    journal_path: str | Path | None = None,
) -> dict[str, Any]:
    journal_path = journal_path_for_state(state, journal_path)
    job = current_job(state, restore=False, journal_path=journal_path) or {}
    value = dict(job)
    message = f"{type(error).__name__}: {error}" if isinstance(error, BaseException) else str(error)
    value.update({
        "status": "FAILED",
        "completed_at": _iso(),
        "updated_at": _iso(),
        "current_stage": "Failed safely — previous valid result preserved",
        "error": message[:1000],
        "retryable": bool(retryable),
    })
    release_run_locks(state)
    return _store_job(state, value, journal_path=journal_path)


def execute_queued_job(
    state: MutableMapping[str, Any],
    runner: Callable[[Mapping[str, Any], Callable[[Mapping[str, Any]], None]], Any], *,
    journal_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Claim and execute one queued job using the existing protected runner."""
    journal_path = journal_path_for_state(state, journal_path)
    job = claim_job(state, journal_path=journal_path)
    if not isinstance(job, Mapping) or str(job.get("status") or "").upper() != "RUNNING":
        return dict(job) if isinstance(job, Mapping) else None
    try:
        result = runner(job, lambda snapshot: publish_progress(state, snapshot, journal_path=journal_path))
        return complete_job(state, result, journal_path=journal_path)
    except BaseException as exc:
        return fail_job(state, exc, retryable=True, journal_path=journal_path)
    finally:
        release_run_locks(state)


def progress_rows(job: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(job, Mapping):
        return []
    symbols = _normalize_symbols(job.get("symbols") if isinstance(job.get("symbols"), Sequence) and not isinstance(job.get("symbols"), str) else [])
    raw = job.get("symbols_progress") if isinstance(job.get("symbols_progress"), Mapping) else {}
    rows: list[dict[str, Any]] = []
    for index, symbol in enumerate(symbols, start=1):
        item = raw.get(symbol) if isinstance(raw, Mapping) and isinstance(raw.get(symbol), Mapping) else {}
        rows.append({
            "#": index,
            "Symbol": symbol,
            "Status": str(item.get("status") or "WAITING"),
            "Progress %": float(item.get("percent") or 0.0),
            "Stage": str(item.get("stage") or "Queued"),
            "Scope": str(item.get("calculation_scope") or (job.get("scope") if index == 1 else "LUNCH_CORE")),
            "Available / Required Candles": f"{item.get('available_candles', '-')} / {item.get('required_candles', '-')}",
            "Data Quality": str(item.get("data_quality") or "CHECK"),
            "Publication": str(item.get("publication_status") or item.get("state") or item.get("status") or "WAITING"),
            "Validation / Failure Reason": str(item.get("rejection_reason") or item.get("error") or ""),
            "Error": str(item.get("error") or ""),
        })
    return rows


def clear_terminal_job(
    state: MutableMapping[str, Any], *,
    journal_path: str | Path | None = None,
) -> bool:
    journal_path = journal_path_for_state(state, journal_path)
    job = current_job(state, restore=False, journal_path=journal_path)
    if not isinstance(job, Mapping) or str(job.get("status") or "").upper() not in TERMINAL_STATUSES:
        return False
    state.pop(JOB_KEY, None)
    try:
        _journal_path(journal_path).unlink(missing_ok=True)
    except Exception:
        pass
    return True


__all__ = [
    "VERSION", "JOB_KEY", "HISTORY_KEY", "LAST_RESULT_KEY", "ENGINE_RUNNING_KEY", "RUN_LOCK_KEYS", "ACTIVE_STATUSES", "TERMINAL_STATUSES",
    "journal_path_for_state", "enqueue_run", "current_job", "recover_stale_job", "is_due", "seconds_until_due", "claim_job",
    "publish_progress", "execute_queued_job", "complete_job", "fail_job", "progress_rows", "clear_terminal_job", "release_run_locks",
]
