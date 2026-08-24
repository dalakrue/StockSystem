"""Secure OpenRouter backend for the independent AI Assistant.

The key is resolved server-side from Streamlit Secrets/environment or a temporary
session replacement.  It is never copied into prompt text, logs, UI widgets, or
persisted runtime caches.  Requests are bounded and grounded in the app's frozen
canonical evidence contract plus compact, already-published history summaries.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Mapping, MutableMapping

import httpx
import pandas as pd

BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openrouter/auto"
SESSION_KEY = "openrouter_api_key"
MODEL_KEY = "openrouter_model_20260628"
STATUS_KEY = "openrouter_connection_status_20260628"


def _secret_path(*parts: str) -> str:
    try:
        import streamlit as st
        value: Any = st.secrets
        for part in parts:
            value = value[part]
        return str(value or "").strip()
    except Exception:
        return ""


def resolve_openrouter_key(state: Mapping[str, Any] | None = None) -> str:
    state = state or {}
    return (
        _secret_path("api_keys", "openrouter")
        or _secret_path("openrouter", "api_key")
        or os.getenv("OPENROUTER_API_KEY", "").strip()
        or str(state.get(SESSION_KEY) or "").strip()
    )


def resolve_openrouter_model(state: Mapping[str, Any] | None = None) -> str:
    state = state or {}
    return (
        str(state.get(MODEL_KEY) or "").strip()
        or _secret_path("openrouter", "model")
        or os.getenv("OPENROUTER_MODEL", "").strip()
        or DEFAULT_MODEL
    )


def configuration_status(state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    state = state or {}
    secret_key = bool(
        _secret_path("api_keys", "openrouter")
        or _secret_path("openrouter", "api_key")
        or os.getenv("OPENROUTER_API_KEY", "").strip()
    )
    temporary = bool(str(state.get(SESSION_KEY) or "").strip())
    connected = state.get(STATUS_KEY) if isinstance(state.get(STATUS_KEY), Mapping) else {}
    return {
        "configured": bool(secret_key or temporary),
        "source": "Streamlit Secrets / environment" if secret_key else ("Temporary session replacement" if temporary else "Not configured"),
        "model": resolve_openrouter_model(state),
        "connected": bool(connected.get("ok")),
        "last_checked": connected.get("checked_at"),
        "status": connected.get("status", "NOT_CHECKED"),
    }


def _headers(key: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-Title": "ADX Quant Pro Canonical Assistant",
    }
    referer = os.getenv("OPENROUTER_HTTP_REFERER", "").strip()
    if referer:
        headers["HTTP-Referer"] = referer
    return headers


def validate_connection(
    state: MutableMapping[str, Any], *, key: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Validate the key with OpenRouter's models endpoint in one request."""
    token = str(key or resolve_openrouter_key(state) or "").strip()
    if not token:
        result = {"ok": False, "status": "KEY_MISSING", "message": "OpenRouter API key is not configured."}
        state[STATUS_KEY] = result
        return result
    owns_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=8.0))
    try:
        response = client.get(f"{BASE_URL}/models", headers=_headers(token))
        response.raise_for_status()
        payload = response.json()
        models = payload.get("data") if isinstance(payload, Mapping) else None
        result = {
            "ok": True,
            "status": "CONNECTED",
            "message": "OpenRouter key validated.",
            "models_visible": len(models) if isinstance(models, list) else None,
            "checked_at": pd.Timestamp.now(tz="UTC").isoformat(),
        }
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            payload = exc.response.json()
            detail = str((payload.get("error") or {}).get("message") or "") if isinstance(payload, Mapping) else ""
        except Exception:
            detail = ""
        result = {
            "ok": False,
            "status": f"HTTP_{exc.response.status_code}",
            "message": detail or "OpenRouter rejected the connection request.",
            "checked_at": pd.Timestamp.now(tz="UTC").isoformat(),
        }
    except Exception as exc:
        result = {
            "ok": False,
            "status": "NETWORK_ERROR",
            "message": f"{type(exc).__name__}: {exc}",
            "checked_at": pd.Timestamp.now(tz="UTC").isoformat(),
        }
    finally:
        if owns_client:
            client.close()
    state[STATUS_KEY] = result
    return result


def _safe_records(value: Any, *, rows: int = 12, columns: int = 18) -> list[dict[str, Any]]:
    if not isinstance(value, pd.DataFrame) or value.empty:
        return []
    frame = value.head(rows).iloc[:, :columns].copy()
    for column in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[column]):
            frame[column] = frame[column].astype(str)
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def compact_history_context(state: Mapping[str, Any]) -> dict[str, Any]:
    """Bounded read-only data-mining/NLP context from published app state."""
    keys = {
        "table1_decisions": "field1_table1_decision_history_20260628",
        "table4_bias": "field1_table4_current_20260627",
        "table5_integrated": "field1_table5_integrated_decision_collection_20260627",
        "priority": "canonical_priority_table_20260617",
    }
    result: dict[str, Any] = {}
    for label, key in keys.items():
        rows = _safe_records(state.get(key))
        if rows:
            result[label] = rows
    news = state.get("finnhub_ranked_news_20260626") or state.get("nlp_related_news_priority_20260615")
    if isinstance(news, list):
        result["ranked_news"] = [dict(item) for item in news[:10] if isinstance(item, Mapping)]
    elif isinstance(news, pd.DataFrame):
        result["ranked_news"] = _safe_records(news, rows=10, columns=12)

    # Bounded read-only Dinner thesis context. Module summaries and limitations
    # are sufficient for grounded questions without serializing entire 25-day
    # tables into an external request. No API key is ever included here.
    try:
        from research_quant.arert_lab import STATE_KEY
        envelope = state.get(STATE_KEY)
    except Exception:
        envelope = None
    if isinstance(envelope, Mapping):
        modules = envelope.get("modules") if isinstance(envelope.get("modules"), Mapping) else {}
        compact_modules: dict[str, Any] = {}
        for number, module in list(modules.items())[:20]:
            if not isinstance(module, Mapping):
                continue
            compact_modules[str(number)] = {
                "module_name": module.get("module_name"),
                "status": module.get("status"),
                "summary": module.get("summary"),
                "limitations": module.get("limitations"),
                "production_influence_enabled": module.get("production_influence_enabled"),
            }
        result["arert_dinner_research"] = {
            "metadata": envelope.get("metadata"),
            "model_version": envelope.get("model_version"),
            "parameter_version": envelope.get("parameter_version"),
            "selected_modules": envelope.get("selected_modules"),
            "modules": compact_modules,
        }
    return result


def _extract_answer(payload: Mapping[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], Mapping) else {}
    message = first.get("message") if isinstance(first.get("message"), Mapping) else {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, Mapping) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip()
    return ""


def generate_grounded_answer(
    question: str,
    contract: Mapping[str, Any],
    state: MutableMapping[str, Any],
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    key = resolve_openrouter_key(state)
    if not key:
        return {"ok": False, "status": "KEY_MISSING", "error": "OpenRouter API key is not configured."}
    model = resolve_openrouter_model(state)
    from services.airllm_backend_20260626 import compact_canonical_context
    canonical_json = compact_canonical_context(contract)
    history = compact_history_context(state)
    history_json = json.dumps(history, default=str, separators=(",", ":"))[:12000]
    system = (
        "You are a read-only quantitative research assistant embedded in ADX Quant Pro. "
        "Use only the supplied frozen canonical evidence and bounded published history. "
        "Never invent prices, accuracy, news, outcomes, API state, or calculations. "
        "Do not change or recommend bypassing protected BUY/SELL/WAIT/HOLD logic. "
        "Clearly distinguish production facts from research interpretation, and state unavailable facts as unavailable."
    )
    user = (
        f"CANONICAL_EVIDENCE={canonical_json}\n"
        f"PUBLISHED_HISTORY_AND_NLP={history_json}\n"
        f"QUESTION={str(question)[:2000]}"
    )
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.1,
        "max_tokens": 500,
    }
    owns_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0))
    started = time.perf_counter()
    max_attempts = 2
    last_error: dict[str, Any] = {"ok": False, "status": "FAILED", "error": "OpenRouter request did not complete."}
    try:
        for attempt in range(1, max_attempts + 1):
            try:
                response = client.post(f"{BASE_URL}/chat/completions", headers=_headers(key), json=payload)
                response.raise_for_status()
                body = response.json()
                answer = _extract_answer(body if isinstance(body, Mapping) else {})
                if not answer:
                    raise RuntimeError("OpenRouter returned no assistant text.")
                return {
                    "ok": True,
                    "status": "COMPLETE",
                    "answer": answer,
                    "model": model,
                    "attempts": attempt,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                }
            except httpx.HTTPStatusError as exc:
                detail = ""
                try:
                    body = exc.response.json()
                    detail = str((body.get("error") or {}).get("message") or "") if isinstance(body, Mapping) else ""
                except Exception:
                    pass
                last_error = {
                    "ok": False, "status": f"HTTP_{exc.response.status_code}",
                    "error": detail or "OpenRouter request failed.", "attempts": attempt,
                }
                retryable = exc.response.status_code == 429 or exc.response.status_code >= 500
                if not retryable or attempt >= max_attempts:
                    break
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = {"ok": False, "status": "NETWORK_ERROR", "error": f"{type(exc).__name__}: {exc}", "attempts": attempt}
                if attempt >= max_attempts:
                    break
            except Exception as exc:
                last_error = {"ok": False, "status": "FAILED", "error": f"{type(exc).__name__}: {exc}", "attempts": attempt}
                break
            time.sleep(0.35 * attempt)
        last_error["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        return last_error
    finally:
        if owns_client:
            client.close()


__all__ = [
    "BASE_URL", "DEFAULT_MODEL", "SESSION_KEY", "MODEL_KEY", "STATUS_KEY",
    "resolve_openrouter_key", "resolve_openrouter_model", "configuration_status",
    "validate_connection", "compact_history_context", "generate_grounded_answer",
]
